"""Render one sentence of English into an ASL skeleton video.

    python utils/generate_asl_video.py "the cat is small" caption_0.mp4
    python utils/generate_asl_video.py --glosses "cat small" caption_0.mp4

The second form skips the English-to-gloss step, which is useful for testing
the render half on its own.

This is the pipeline's one implementation. It replaces the bash version,
which needed conda and broke on Windows; utils/generate_asl_video.sh,
main.sh and old_main.sh now just call this. See aslytics_env.py for how the
two halves' Python environments are found.

Only the basename of the output path is used: the video is written to
$ASLYTICS_VIDEO_DIR and copied to $ASLYTICS_WEB_VIDEO_DIR for Flask to serve.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aslytics_env as env  # noqa: E402

START_PY = env.REPO_ROOT / "text-to-gloss" / "start.py"
RENDER_PY = env.REPO_ROOT / "utils" / "render_glosses.py"

# First use downloads nothing but does load a few hundred MB of NLP models.
GLOSS_TIMEOUT = 600
RENDER_TIMEOUT = 600


class GenerationError(RuntimeError):
    """A step failed. The message says which, and why."""


def _tail(text: str, lines: int = 8) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


def generate(sentence: str, output_name: str, glosses: Optional[List[str]] = None) -> Path:
    """Run the whole pipeline for one sentence and return the published video."""
    filename = Path(output_name).name
    stem = Path(filename).stem
    work = env.work_dir()
    raw_video = work / f"{stem}.raw.mp4"
    final = env.video_dir() / filename
    published = env.web_video_dir() / filename
    final.parent.mkdir(parents=True, exist_ok=True)
    published.parent.mkdir(parents=True, exist_ok=True)

    label = sentence or " ".join(glosses or [])

    # 1. English -> gloss sequence, unless given.
    render_args = ["--out-video", str(raw_video)]
    stdin = None
    if glosses:
        render_args += list(glosses)
    else:
        result = env.runner(env.GLOSS).run(START_PY, sentence, timeout=GLOSS_TIMEOUT)
        if result.returncode != 0:
            raise GenerationError(f"text-to-gloss failed for {label!r}:\n{_tail(result.stderr)}")
        render_args += ["--start-output", "-"]
        stdin = result.stdout

    # 2. Gloss sequence -> skeleton video.
    result = env.runner(env.POSE).run(RENDER_PY, *render_args, stdin=stdin, timeout=RENDER_TIMEOUT)
    if result.returncode == 2:
        raise GenerationError(f"no gloss sequence produced for {label!r}")
    if result.returncode == 3:
        missing = json.loads(result.stderr.strip().splitlines()[-1]).get("missing", [])
        raise GenerationError(f"no sign in the lexicon for {missing} (for {label!r})")
    if result.returncode != 0:
        raise GenerationError(f"rendering failed for {label!r}:\n{_tail(result.stderr)}")

    # 3. Re-encode to something browsers will play, then publish.
    ffmpeg = env.ffmpeg()
    if ffmpeg is None:
        raise GenerationError("ffmpeg not found; see `python utils/aslytics_env.py`")
    encode = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(raw_video),
                             "-vcodec", "libx264", "-pix_fmt", "yuv420p", str(final)],
                            capture_output=True, text=True)
    if encode.returncode != 0:
        raise GenerationError(f"ffmpeg failed:\n{_tail(encode.stderr)}")
    if final.resolve() != published.resolve():
        shutil.copy2(final, published)
    return published


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a sentence into an ASL skeleton video.")
    parser.add_argument("sentence", nargs="?", default="")
    parser.add_argument("output", help="Output filename, e.g. caption_0.mp4")
    parser.add_argument("--glosses", help="Space-separated glosses; skips text-to-gloss")
    parser.add_argument("--check", action="store_true", help="Only report whether the setup is ready")
    args = parser.parse_args()

    if args.check:
        problems = env.check()
        print("ready" if not problems else "not ready:\n  - " + "\n  - ".join(problems))
        return 1 if problems else 0

    glosses = args.glosses.split() if args.glosses else None
    if not glosses and not args.sentence.strip():
        parser.error("give a sentence, or --glosses")

    print(f"Generating ASL video for: {args.sentence or ' '.join(glosses)}")
    try:
        path = generate(args.sentence, args.output, glosses)
    except GenerationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"Final video: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
