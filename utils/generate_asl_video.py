"""Render one sentence of English into an ASL skeleton video.

    python utils/generate_asl_video.py "the cat is small" caption_0.mp4
    python utils/generate_asl_video.py --glosses "cat small" caption_0.mp4
    python utils/generate_asl_video.py --skip-missing "the dog is hungry" out.mp4
    python utils/generate_asl_video.py --words

The second form skips the English-to-gloss step, which is useful for testing
the render half on its own. --skip-missing signs the words the lexicon has
and leaves out the rest instead of failing (also ASLYTICS_SKIP_MISSING=1).
--words lists every word the current lexicon can sign.

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
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

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


def lexicon_words() -> List[str]:
    """Every word the current lexicon can sign, as the renderer would look it up."""
    directory = env.lexicon_dir()
    if not directory.is_dir():
        return []
    stems = {path.stem for path in directory.glob("*.pose")}
    return sorted(stems | {re.sub(r"_\d+$", "", stem) for stem in stems})


def generate(sentence: str, output_name: str, glosses: Optional[List[str]] = None,
             skip_missing: Optional[bool] = None) -> Path:
    """Run the whole pipeline for one sentence and return the published video."""
    return generate_with_report(sentence, output_name, glosses, skip_missing)["video"]


def generate_with_report(sentence: str, output_name: str, glosses: Optional[List[str]] = None,
                         skip_missing: Optional[bool] = None,
                         publish_dir: Optional[Path] = None) -> Dict[str, object]:
    """generate(), also returning which glosses were signed and which skipped.

    {"video": Path, "glosses": [...signed], "skipped": [...not in lexicon]}

    publish_dir, if given, receives the finished video instead of
    $ASLYTICS_VIDEO_DIR and $ASLYTICS_WEB_VIDEO_DIR.
    """
    if skip_missing is None:
        skip_missing = env_skip_missing()
    filename = Path(output_name).name
    stem = Path(filename).stem
    work = env.work_dir()
    raw_video = work / f"{stem}.raw.mp4"
    final = (Path(publish_dir) if publish_dir else env.video_dir()) / filename
    published = (Path(publish_dir) if publish_dir else env.web_video_dir()) / filename
    final.parent.mkdir(parents=True, exist_ok=True)
    published.parent.mkdir(parents=True, exist_ok=True)

    label = sentence or " ".join(glosses or [])

    # 1. English -> gloss sequence, unless given.
    render_args = ["--out-video", str(raw_video)]
    if skip_missing:
        render_args.append("--skip-missing")
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

    report = _last_json(result.stdout)
    return {"video": published, "glosses": report.get("glosses", []),
            "skipped": report.get("skipped", [])}


def env_skip_missing() -> bool:
    return os.environ.get("ASLYTICS_SKIP_MISSING", "").strip().lower() in ("1", "true", "yes")


def _last_json(text: str) -> Dict[str, object]:
    for line in reversed((text or "").strip().splitlines()):
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a sentence into an ASL skeleton video.")
    parser.add_argument("sentence", nargs="?", default="")
    parser.add_argument("output", help="Output filename, e.g. caption_0.mp4")
    parser.add_argument("--glosses", help="Space-separated glosses; skips text-to-gloss")
    parser.add_argument("--check", action="store_true", help="Only report whether the setup is ready")
    parser.add_argument("--skip-missing", action="store_true", default=None,
                        help="Sign the words the lexicon has and skip the rest")
    parser.add_argument("--words", action="store_true", help="List the words the lexicon can sign")

    # --words needs no output filename, which argparse would otherwise demand.
    if "--words" in sys.argv[1:]:
        words = lexicon_words()
        print("\n".join(words))
        print(f"{len(words)} words in {env.lexicon_dir()}", file=sys.stderr)
        return 0 if words else 1

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
        report = generate_with_report(args.sentence, args.output, glosses, args.skip_missing)
    except GenerationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    if report["skipped"]:
        print(f"Skipped (no sign in the lexicon): {' '.join(report['skipped'])}")
    print(f"Final video: {report['video']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
