"""Build the whole community lexicon and the showcase with one command.

    python showcase/build_all.py              # everything; safe to stop and re-run
    python showcase/build_all.py --status     # where a run has got to
    python showcase/build_all.py --limit 100  # a short trial: the 100 most-used words, no ASL Citizen

Run it on the laptop (it needs MediaPipe and the open internet), from the repo
folder, with the project's Python:  .venv\\Scripts\\python showcase\\build_all.py

What it does, in order. Finished work is skipped on a re-run:

  1. check     Python packages, disk space, the PopSign lexicon
  2. aslc      ASL Citizen: download (~4 GB), convert, export -> lexicon/aslc
  3. fetch     dictionary sites, one sign per word, politely (fetch_sites.py);
               runs in the background while ASL Citizen converts
  4. convert   each site's videos -> lexicon/<site>; then a second, short fetch
               for words whose first source turned out unusable
  5. stack     every layer, best first -> lexicon/community
  6. report    what was built, per source, and what is still missing
  7. showcase  the side-by-side gallery -> .work/showcase/index.html

A failed step is reported and the later ones still run with what exists.
Progress is written to .work/build_all/status.json and build.log. Expect a
full run to take 6 to 8 hours on the laptop, mostly MediaPipe; the laptop is
kept awake while it runs.

Sources whose owners have to send files (showcase/sources.py: Handspeak,
ASLCORE) are picked up when their videos are in .work/<source>/videos/ as
<word>.mp4.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT / "prototype"))

import fetch_sites  # noqa: E402
import sources  # noqa: E402

STATE = REPO_ROOT / ".work" / "build_all"
STEPS = ["check", "aslc", "fetch", "convert", "stack", "report", "showcase"]
NEEDED = {"mediapipe": "mediapipe==0.10.21", "pose_format": "pose-format", "cv2": "opencv-python-headless",
          "PIL": "pillow", "numpy": "numpy", "remotezip": "remotezip"}
MIN_FREE_GB = 10


# -- log and status ------------------------------------------------------------------------

class Run:
    def __init__(self, state: Path = STATE):
        self.state = state
        state.mkdir(parents=True, exist_ok=True)
        (state / ".gitignore").write_text("*\n", encoding="utf-8")
        self.log_path = state / "build.log"
        self.status_path = state / "status.json"
        self.status: Dict[str, object] = {"started": _now(), "pid": os.getpid(), "steps": {}}
        self.background: Optional[subprocess.Popen] = None     # fetch_sites.py, while ASL Citizen converts

    def log(self, text: str) -> None:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {text}"
        print(line, flush=True)
        with open(self.log_path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def mark(self, step: str, state: str, detail: str = "") -> None:
        entry = self.status["steps"].setdefault(step, {})
        entry["state"] = state
        entry["started" if state == "running" else "finished"] = _now()
        if detail:
            entry["detail"] = detail
        self.status["updated"] = _now()
        self.status_path.write_text(json.dumps(self.status, indent=1), encoding="utf-8")

    def script(self, name: str, *args: object) -> int:
        """Run one of the repo's scripts, copying its output into the log. Returns its exit code."""
        argv = [sys.executable, str(REPO_ROOT / name), *map(str, args)]
        self.log("$ " + " ".join(argv[1:]))
        process = subprocess.Popen(argv, cwd=REPO_ROOT, env=_env(), stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        for line in process.stdout:
            self.log("  " + line.rstrip())
        return process.wait()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _env() -> Dict[str, str]:
    return {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


def keep_awake() -> None:
    """Ask Windows not to sleep while this process runs. Ends with the process."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
        except Exception:  # noqa: BLE001 - only a convenience
            pass


def poses(folder: Path) -> int:
    return sum(1 for _ in folder.glob("*.pose")) if folder.is_dir() else 0


def clips(folder: Path) -> int:
    return sum(1 for _ in folder.glob("*.mp4")) if folder.is_dir() else 0


# -- steps -----------------------------------------------------------------------------------

def _missing_packages() -> List[str]:
    return [package for module, package in NEEDED.items() if importlib.util.find_spec(module) is None]


def check(run: Run, args) -> str:
    problems = []
    missing = _missing_packages()
    if missing and not args.no_install:
        run.log("installing " + " ".join(missing))
        subprocess.call([sys.executable, "-m", "pip", "install", "--quiet", *missing], env=_env())
        importlib.invalidate_caches()
        missing = _missing_packages()
    if missing:
        problems.append("missing Python packages: pip install " + " ".join(missing))
    try:
        version = importlib.metadata.version("mediapipe")
        if version != "0.10.21":
            problems.append(f"mediapipe is {version}; pose-format needs 0.10.21")
    except importlib.metadata.PackageNotFoundError:
        pass
    free = shutil.disk_usage(REPO_ROOT).free / 1e9
    if free < MIN_FREE_GB:
        problems.append(f"only {free:.0f} GB free on this drive; {MIN_FREE_GB} GB needed")
    if not poses(sources.BY_KEY["popsign"].lexicon):
        run.log("note: lexicon/popsign is empty, so the stack will have no PopSign layer "
                "(prototype/README.md builds it)")
    if problems:
        raise RuntimeError("; ".join(problems))
    return f"{free:.0f} GB free"


def have_words(run: Run) -> Path:
    """Words the gap-filling sites need not be asked for: PopSign's, and ASL Citizen's."""
    words = set(fetch_sites.lexicon_words(sources.BY_KEY["popsign"].lexicon))
    aslc = sources.BY_KEY["aslc"].lexicon
    if poses(aslc):
        words |= fetch_sites.lexicon_words(aslc)
    else:
        try:
            import citizen
            table, _ = citizen.plan()
            words |= set(table)
        except Exception as error:  # noqa: BLE001 - without the list we just ask for more words
            run.log(f"note: ASL Citizen's word list is not available yet ({error})")
    path = run.state / "have_words.txt"
    path.write_text("\n".join(sorted(words)) + "\n", encoding="utf-8")
    return path


def start_fetch(run: Run, args, site_keys: List[str], log_name: str) -> subprocess.Popen:
    argv = [sys.executable, str(HERE / "fetch_sites.py"), "--sites", ",".join(site_keys),
            "--have-file", str(have_words(run)), "--delay", str(args.delay)]
    if args.limit:
        argv += ["--limit", str(args.limit)]
    run.log("$ " + " ".join(argv[1:]) + f"   (output in .work/build_all/{log_name})")
    handle = open(run.state / log_name, "a", encoding="utf-8")
    return subprocess.Popen(argv, cwd=REPO_ROOT, env=_env(), stdout=handle, stderr=subprocess.STDOUT)


def aslc(run: Run, args) -> str:
    for command in ("fetch", "convert"):
        extra = ["--workers", args.workers] if command == "convert" else []
        if code := run.script("showcase/citizen.py", command, *extra):
            raise RuntimeError(f"citizen.py {command} exited with {code}")
        if command == "fetch" and run.background is None and "fetch" in args.steps:
            run.background = start_fetch(run, args, [s.key for s in sources.fetched()], "fetch_sites.log")
    if code := run.script("showcase/citizen.py", "export", "--out", sources.BY_KEY["aslc"].lexicon):
        raise RuntimeError(f"citizen.py export exited with {code}")
    return f"{poses(sources.BY_KEY['aslc'].lexicon)} words"


def fetch(run: Run, args) -> str:
    if run.background is None:
        run.background = start_fetch(run, args, [s.key for s in sources.fetched()], "fetch_sites.log")
    run.log("waiting for the dictionary sites (progress in .work/build_all/fetch_sites.log)")
    code = run.background.wait()
    counts = {s.key: clips(s.videos) for s in sources.fetched()}
    detail = ", ".join(f"{key} {count}" for key, count in counts.items())
    if code:
        raise RuntimeError(f"fetch_sites.py exited with {code}; videos so far: {detail}")
    return detail


def to_lexicon(run: Run, args, source: sources.Source) -> int:
    argv = ["--videos", source.videos, "--out", source.lexicon, "--source", source.name,
            "--license", source.license, "--credit", source.credit, "--workers", args.workers]
    if source.non_commercial:
        argv.append("--non-commercial")
    if code := run.script("showcase/video_lexicon.py", *argv):
        raise RuntimeError(f"video_lexicon.py for {source.key} exited with {code}")
    return poses(source.lexicon)


def convert(run: Run, args) -> str:
    built, failed = {}, []
    todo = [s for s in sources.dictionary() if clips(s.videos)]
    first = [s for s in todo if s.key in fetch_sites.FULL_SITES]
    rest = [s for s in todo if s.key not in fetch_sites.FULL_SITES]
    for source in first:
        try:
            built[source.key] = to_lexicon(run, args, source)
        except RuntimeError as error:
            failed.append(str(error))
    # Second, short fetch: words whose sign from Signing Savvy or ASL Citizen
    # could not be used (not converted, or hands barely tracked) are asked of
    # the gap-filling sites. Words already looked up are not asked again.
    gap_sites = [s.key for s in sources.fetched() if s.key not in fetch_sites.FULL_SITES]
    if gap_sites and "fetch" in args.steps:
        have = [str(sources.BY_KEY[k].lexicon) for k in ("signingsavvy", "aslc", "popsign")
                if poses(sources.BY_KEY[k].lexicon)]
        argv = ["--sites", ",".join(gap_sites), "--delay", args.delay]
        for folder in have:
            argv += ["--have", folder]
        if args.limit:
            argv += ["--limit", args.limit]
        if run.script("showcase/fetch_sites.py", *argv):
            failed.append("second fetch failed")
        rest = [s for s in sources.dictionary() if clips(s.videos) and s.key not in fetch_sites.FULL_SITES]
    for source in rest:
        try:
            built[source.key] = to_lexicon(run, args, source)
        except RuntimeError as error:
            failed.append(str(error))
    detail = ", ".join(f"{key} {count}" for key, count in built.items()) or "no site videos to convert"
    if failed:
        raise RuntimeError("; ".join(failed) + f" (built: {detail})")
    return detail


def layers() -> List[Path]:
    return [s.lexicon for s in sources.SOURCES if poses(s.lexicon)]


def stack(run: Run, args) -> str:
    found = layers()
    if not found:
        raise RuntimeError("no lexicon layers exist yet")
    argv: List[object] = []
    for layer in found:
        argv += ["--layer", layer]
    out = REPO_ROOT / "lexicon" / "community"
    if code := run.script("showcase/stack_lexicons.py", *argv, "--out", out):
        raise RuntimeError(f"stack_lexicons.py exited with {code}")
    return f"{len(fetch_sites.lexicon_words(out))} words from {len(found)} layers"


def report_text(community: Path, targets: List[str], work: Path) -> str:
    """REPORT.md: what was built, from where, and what is still missing."""
    try:
        info = json.loads((community / "lexicon.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        info = {}
    words = fetch_sites.lexicon_words(community)
    lines = ["# Community lexicon: build report", "", f"Built {_now()}.", "",
             f"**{len(words):,} words**" + (f", letters: {''.join(info.get('letters', []))}"
                                            if info.get("letters") else ", no fingerspelling letters"),
             "", "NON-COMMERCIAL USE ONLY." if info.get("non_commercial") else "", "",
             "## Words used from each source", "",
             "Where two sources sign the same word, the one listed first is used.", "",
             "| Source | Words used |", "|---|---|"]
    for name, count in (info.get("words_per_source") or {}).items():
        lines.append(f"| {name} | {count:,} |")
    lines += ["", "## Target words covered", "",
              "Of the most-used signable English words (showcase/target_words.txt), by count. "
              "showcase/coverage_curve.py gives the share weighted by how often each word is used.", "",
              "| Most-used words | Have a sign |", "|---|---|"]
    for size in (250, 500, 1000, 2000, 5000):
        top = targets[:size]
        if len(top) == size:
            covered = sum(1 for w in top if w in words)
            lines.append(f"| top {size:,} | {covered:,} ({covered / size:.0%}) |")
    gaps = [w for w in targets if w not in words][:80]
    lines += ["", "## The most-used words still without a sign", "", ", ".join(gaps) or "none", "",
              "## Each source", "",
              "| Source | Videos | Words built | Not converted | Hands barely tracked | Note |",
              "|---|---|---|---|---|---|"]
    for source in sources.SOURCES:
        try:
            lexicon = json.loads((source.lexicon / "lexicon.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            lexicon = {}
        try:
            summary = json.loads((work / source.key / "summary.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            summary = {}
        note = str(summary.get("stopped") or "")
        if not note and not poses(source.lexicon):
            note = source.why_no_fetcher or "not built"
        missing = lexicon.get("missing", lexicon.get("labels_missing", []))
        rejected = lexicon.get("rejected_low_hand_presence", lexicon.get("labels_rejected_low_hand_presence", {}))
        lines.append(f"| {source.name} | {clips(work / source.key / 'videos') or ''} | "
                     f"{poses(source.lexicon) or ''} | {len(missing) or ''} | {len(rejected) or ''} | {note} |")
    return "\n".join(lines) + "\n"


def report(run: Run, args) -> str:
    community = REPO_ROOT / "lexicon" / "community"
    targets = fetch_sites.read_words(HERE / "target_words.txt")
    text = report_text(community, targets, REPO_ROOT / ".work")
    (run.state / "REPORT.md").write_text(text, encoding="utf-8")
    for line in text.splitlines():
        run.log("  " + line)
    return "REPORT.md written"


def showcase(run: Run, args) -> str:
    if code := run.script("showcase/run_showcase.py"):
        raise RuntimeError(f"run_showcase.py exited with {code}")
    return "open .work/showcase/index.html"


RUNNERS: Dict[str, Callable[[Run, object], str]] = {
    "check": check, "aslc": aslc, "fetch": fetch, "convert": convert,
    "stack": stack, "report": report, "showcase": showcase,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--only", help=f"Comma-separated steps to run, of: {', '.join(STEPS)}")
    parser.add_argument("--skip", default="", help="Comma-separated steps to leave out")
    parser.add_argument("--limit", type=int, help="Trial run: only the first N target words; skips ASL Citizen")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2),
                        help="MediaPipe processes")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between requests to one site")
    parser.add_argument("--no-install", action="store_true", help="Do not pip install missing packages")
    parser.add_argument("--status", action="store_true", help="Print the last run's status and stop")
    args = parser.parse_args()

    if args.status:
        path = STATE / "status.json"
        if not path.exists():
            print("no run yet")
            return 1
        status = json.loads(path.read_text(encoding="utf-8"))
        print(f"started {status.get('started')}, last update {status.get('updated')}")
        for step in STEPS:
            entry = status.get("steps", {}).get(step)
            if entry:
                print(f"  {step:9s} {entry.get('state', ''):8s} {entry.get('detail', '')}")
        return 0

    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    if args.limit:
        skip.add("aslc")
    chosen = [s.strip() for s in args.only.split(",")] if args.only else STEPS
    for step in list(chosen) + list(skip):
        if step not in STEPS:
            parser.error(f"unknown step: {step}")
    args.steps = [s for s in STEPS if s in chosen and s not in skip]

    run = Run()
    keep_awake()
    run.log(f"build_all: {', '.join(args.steps)}")
    failed = []
    try:
        for step in args.steps:
            run.mark(step, "running")
            began = time.monotonic()
            try:
                detail = RUNNERS[step](run, args)
                run.mark(step, "done", detail)
                run.log(f"{step}: done in {(time.monotonic() - began) / 60:.0f} min. {detail}")
            except Exception as error:  # noqa: BLE001 - later steps still run with what exists
                failed.append(step)
                run.mark(step, "failed", f"{type(error).__name__}: {error}")
                run.log(f"{step}: FAILED. {error}")
                if step == "check":
                    break
    finally:
        if run.background is not None and run.background.poll() is None:
            run.background.terminate()
    run.log("finished" + (f"; failed steps: {', '.join(failed)}" if failed else " with every step done"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
