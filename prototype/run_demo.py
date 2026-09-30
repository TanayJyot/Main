"""Render a handful of sentences with the PopSign prototype lexicon.

    python prototype/run_demo.py                      # the built-in sentences
    python prototype/run_demo.py "the dog is hungry" "where is my book?"

Uses lexicon/popsign unless ASLYTICS_LEXICON_DIR says otherwise. Words the
lexicon lacks are skipped, not fatal, and the report says which. Videos and
the report (demo_report.json) go to .work/demo/, which git ignores, so a demo
run never overwrites the app's sample videos in static/.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LEXICON = REPO_ROOT / "lexicon" / "popsign"

# Chosen so most words are in PopSign's vocabulary; a few are not, to show
# skipping. Lower case, because text-to-gloss fingerspells capitalised words
# it takes for names, and PopSign has no alphabet.
SENTENCES = [
    "the dog is hungry",
    "my cat likes milk",
    "where is the blue book?",
    "please drink water",
    "the frog is green",
    "grandma and grandpa are happy",
    "the girl likes pizza and ice cream",
    "yesterday the boy saw a yellow bird in the tree",
    "it is hot outside, go to the pool",
    "thank you for the gift",
    "sam has 3 cats",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Render demo sentences with the prototype lexicon.")
    parser.add_argument("sentences", nargs="*", help="Sentences; default: a built-in set")
    args = parser.parse_args()

    if not os.environ.get("ASLYTICS_LEXICON_DIR"):
        os.environ["ASLYTICS_LEXICON_DIR"] = str(DEFAULT_LEXICON)
    demo_dir = REPO_ROOT / ".work" / "demo"
    os.environ.setdefault("ASLYTICS_VIDEO_DIR", str(demo_dir))
    os.environ.setdefault("ASLYTICS_WEB_VIDEO_DIR", str(demo_dir))
    lexicon = Path(os.environ["ASLYTICS_LEXICON_DIR"])
    if not any(lexicon.glob("*.pose")):
        print(f"no signs in {lexicon}. Build them first:\n"
              f"    python prototype/popsign_lexicon.py build --labels <dir of <label>.pose>",
              file=sys.stderr)
        return 1

    sys.path.insert(0, str(REPO_ROOT / "utils"))
    from generate_asl_video import GenerationError, generate_with_report

    report = []
    for index, sentence in enumerate(args.sentences or SENTENCES):
        started = time.time()
        entry = {"sentence": sentence}
        try:
            result = generate_with_report(sentence, f"demo_{index}.mp4", skip_missing=True)
            entry.update(signed=result["glosses"], spelled=result["spelled"],
                         skipped=result["skipped"], video=str(result["video"]))
        except GenerationError as error:
            entry.update(signed=[], error=str(error).splitlines()[0])
        entry["seconds"] = round(time.time() - started, 1)
        report.append(entry)

        signed = " ".join(entry["signed"]) or "-"
        print(f"\n{sentence}\n  signed:  {signed}")
        if entry.get("spelled"):
            print(f"  spelled: {' '.join(entry['spelled'])}")
        if entry.get("skipped"):
            print(f"  skipped: {' '.join(entry['skipped'])}")
        if entry.get("error"):
            print(f"  error:   {entry['error']}")
        if entry.get("video"):
            print(f"  video:   {entry['video']}  ({entry['seconds']} s)")

    signed = sum(len(e["signed"]) for e in report)
    spelled = sum(len(e.get("spelled", [])) for e in report)
    skipped = sum(len(e.get("skipped", [])) for e in report)
    print(f"\n{sum(1 for e in report if e.get('video'))}/{len(report)} sentences rendered; "
          f"{signed} words signed, {spelled} fingerspelled, {skipped} skipped.")

    out = demo_dir / "demo_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if any(e.get("video") for e in report) else 1


if __name__ == "__main__":
    sys.exit(main())
