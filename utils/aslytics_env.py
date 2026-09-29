"""Where things live and how to run them, on any OS, with or without conda.

The pipeline used to be bash scripts calling `conda run`. That broke on
Windows three ways: no conda, `bash` launched from Python resolving to WSL's
bash (which cannot see a Windows virtualenv), and Git Bash's /c/Users/...
paths meaning nothing to Windows Python. Everything that decides paths and
interpreters now lives here, in Python, so it behaves the same everywhere.

How the pipeline's two halves are run (ASLYTICS_RUNNER):

  auto    (default) conda if it is installed and has the named environment,
          otherwise plain Python.
  conda   `conda run -n <env> python`. Environments from install.sh.
  python  a Python interpreter directly. Which one, in order:
            ASLYTICS_GLOSS_PYTHON / ASLYTICS_POSE_PYTHON  (per half)
            ASLYTICS_PYTHON                                (both halves)
            <repo>/.venv                                   (if present)
            the interpreter running this code

The two halves can share one environment: stanfordnlp and pose-format install
side by side on current torch, so a single .venv is the simplest setup.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

GLOSS, POSE = "gloss", "pose"

# What each half must be able to import, and the conda environment install.sh
# creates for it.
REQUIRED_MODULES = {GLOSS: ["stanfordnlp"], POSE: ["pose_format", "scipy", "vidgear"]}
CONDA_ENVS = {GLOSS: ("ASLYTICS_GLOSS_ENV", "text-to-gloss"),
              POSE: ("ASLYTICS_POSE_ENV", "gloss-to-skeleton")}
PYTHON_VARS = {GLOSS: "ASLYTICS_GLOSS_PYTHON", POSE: "ASLYTICS_POSE_PYTHON"}


# -- paths ----------------------------------------------------------------------

def lexicon_dir() -> Path:
    """Same resolution as concatenate.lexicon_dir(), kept in step with it."""
    override = os.environ.get("ASLYTICS_LEXICON_DIR")
    if override:
        return Path(override).expanduser()
    legacy = REPO_ROOT / ".gitignore" / "generated_pose"
    return legacy if legacy.is_dir() else REPO_ROOT / "lexicon"


def work_dir() -> Path:
    """Scratch space: intermediate video and the render cache.

    Everything here is derived from whichever lexicon is loaded, which may be
    one that must never be committed. The repository has no root .gitignore
    (the legacy lexicon directory is itself named .gitignore), so the folder
    ignores itself.
    """
    path = Path(os.environ.get("ASLYTICS_WORK_DIR", REPO_ROOT / ".work"))
    path.mkdir(parents=True, exist_ok=True)
    marker = path / ".gitignore"
    if not marker.exists():
        marker.write_text("# Derived renders; never commit.\n*\n")
    return path


def video_dir() -> Path:
    return Path(os.environ.get("ASLYTICS_VIDEO_DIR", REPO_ROOT / "videos"))


def web_video_dir() -> Path:
    return Path(os.environ.get("ASLYTICS_WEB_VIDEO_DIR", REPO_ROOT / "static" / "videos"))


# -- interpreters ---------------------------------------------------------------

def _venv_python() -> Optional[str]:
    for candidate in (REPO_ROOT / ".venv" / "bin" / "python",
                      REPO_ROOT / ".venv" / "Scripts" / "python.exe"):
        if candidate.exists():
            return str(candidate)
    return None


def _conda_env_exists(name: str) -> bool:
    conda = shutil.which("conda")
    if not conda:
        return False
    try:
        listing = subprocess.run([conda, "env", "list"], capture_output=True, text=True,
                                 timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return any(line.split() and line.split()[0] == name for line in listing.splitlines())


@dataclass
class Runner:
    """How to launch Python for one half of the pipeline."""

    half: str
    command: List[str]   # prefix; append a script path and its arguments
    description: str

    def run(self, script: Path, *args: str, stdin: Optional[str] = None,
            timeout: Optional[float] = None) -> subprocess.CompletedProcess:
        return subprocess.run([*self.command, str(script), *args], input=stdin,
                              capture_output=True, text=True, timeout=timeout,
                              cwd=str(REPO_ROOT))


def runner(half: str) -> Runner:
    mode = os.environ.get("ASLYTICS_RUNNER", "auto").lower()
    if mode not in {"auto", "conda", "python"}:
        raise ValueError(f"ASLYTICS_RUNNER must be auto, conda or python, not {mode!r}")

    env_var, default_env = CONDA_ENVS[half]
    env_name = os.environ.get(env_var, default_env)

    if mode == "conda" or (mode == "auto" and _conda_env_exists(env_name)):
        conda = shutil.which("conda")
        if not conda:
            raise RuntimeError("ASLYTICS_RUNNER=conda but conda is not on PATH")
        return Runner(half, [conda, "run", "--no-capture-output", "-n", env_name, "python"],
                      f"conda env '{env_name}'")

    python = (os.environ.get(PYTHON_VARS[half]) or os.environ.get("ASLYTICS_PYTHON")
              or _venv_python() or sys.executable)
    return Runner(half, [python], f"python {python}")


def ffmpeg() -> Optional[str]:
    """ffmpeg on PATH, else the binary bundled with imageio-ffmpeg.

    MoviePy already depends on imageio-ffmpeg, so the fallback means one fewer
    thing to install by hand, which matters most on Windows.
    """
    explicit = os.environ.get("ASLYTICS_FFMPEG")
    if explicit:
        return explicit
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


# -- preflight --------------------------------------------------------------------

def check(require_lexicon: bool = True) -> List[str]:
    """Every missing prerequisite, reported together. Empty means ready."""
    problems = []

    if ffmpeg() is None:
        problems.append("ffmpeg not found: install it, or `pip install imageio-ffmpeg`, "
                        "or set ASLYTICS_FFMPEG")

    for half in (GLOSS, POSE):
        try:
            run = runner(half)
        except Exception as error:
            problems.append(f"{half} step: {error}")
            continue
        probe = "import " + ", ".join(REQUIRED_MODULES[half])
        try:
            result = subprocess.run([*run.command, "-c", probe], capture_output=True,
                                    text=True, timeout=180)
        except (OSError, subprocess.SubprocessError) as error:
            problems.append(f"{half} step: cannot start {run.description}: {error}")
            continue
        if result.returncode != 0:
            last = (result.stderr.strip().splitlines() or ["unknown error"])[-1]
            problems.append(f"{half} step ({run.description}) cannot import "
                            f"{', '.join(REQUIRED_MODULES[half])}: {last}")

    if require_lexicon and not lexicon_dir().is_dir():
        problems.append(f"no sign lexicon at {lexicon_dir()}. The .pose files are not in the "
                        f"repository; set ASLYTICS_LEXICON_DIR to point at them.")
    return problems


def describe() -> Dict[str, str]:
    out = {"repo": str(REPO_ROOT), "lexicon": str(lexicon_dir()),
           "ffmpeg": ffmpeg() or "(missing)"}
    for half in (GLOSS, POSE):
        try:
            out[f"{half} runner"] = runner(half).description
        except Exception as error:
            out[f"{half} runner"] = f"(error: {error})"
    return out


if __name__ == "__main__":
    for key, value in describe().items():
        print(f"{key:>13}: {value}")
    issues = check()
    print("\nready" if not issues else "\nnot ready:\n  - " + "\n  - ".join(issues))
    sys.exit(1 if issues else 0)
