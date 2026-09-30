"""Build the prototype's sign lexicon from PopSign ASL v1.0 (CC BY 4.0).

PopSign is the one sign dataset we hold that allows commercial use. It has
250 signs, one label each. This turns one converted .pose per label into a
lexicon the renderer can load: one file per *word text-to-gloss emits*, since
the renderer looks signs up by gloss and PopSign's labels are not always that
word (`callonphone` is signed for "call", `hesheit` for "he", "she", "it").

    python prototype/popsign_lexicon.py build --labels DIR --out lexicon/popsign
    python prototype/popsign_lexicon.py words > prototype/WORDS.md

`--labels` is a directory of `<label>.pose`, one chosen clip per PopSign label,
already mirrored to right-hand dominant. Each sign is trimmed to the stretch
where the hands move (prototype/trim.py), and signs whose hands were barely
tracked are left out rather than shown wrongly. The laptop's analysis/convert/
scripts produce it: selection is by hand-landmark presence, fixed before any
clip was seen and never by comparison with the old lexicon.

The output directory holds signs derived from PopSign, so it must carry
PopSign's attribution wherever it goes (ATTRIBUTION.txt is written into it)
and it is not committed to this repository.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
COVERAGE = REPO_ROOT / "analysis" / "coverage"

# PopSign label -> the words text-to-gloss emits for it. Labels not listed map
# to themselves, lower-cased. Only add a word here if it is the *same sign*:
# mom is signed MOTHER, feet FOOT; but PopSign's `better` is not a sign for
# "good", so text-to-gloss lemmatising "better" to "good" stays a miss rather
# than showing the wrong sign.
ALIASES: Dict[str, List[str]] = {
    "callonphone": ["call"],
    "frenchfries": ["fries"],
    "glasswindow": ["window"],   # the sign is WINDOW; a drinking glass is a different sign
    "haveto": ["must"],          # text-to-gloss turns "have to" into HAVE, which is a different sign
    "hesheit": ["he", "she", "it"],
    "minemy": ["my", "mine"],
    "thankyou": ["thank"],       # "thank you" -> thank + you; YOU is not in PopSign
    "weus": ["we", "us"],
    "owie": ["owie", "ouch"],
    "shhh": ["shhh", "shh"],
    "feet": ["feet", "foot"],
    "mom": ["mom", "mother"],
    "dad": ["dad", "father"],
    "grandma": ["grandma", "grandmother"],
    "grandpa": ["grandpa", "grandfather"],
}

ATTRIBUTION = """\
Signs in this directory are derived from PopSign ASL v1.0
(Georgia Institute of Technology and collaborators; NeurIPS 2023 Datasets and
Benchmarks), https://signdata.cc.gatech.edu/, licensed under Creative Commons
Attribution 4.0 International (CC BY 4.0),
https://creativecommons.org/licenses/by/4.0/.

Changes: each video was converted to MediaPipe Holistic landmarks (.pose); one
clip per sign was chosen by hand-landmark presence; left-handed clips were
mirrored to right-handed; files were renamed to the English words they sign.
"""


def popsign_labels() -> List[str]:
    return (COVERAGE / "popsign_glosses.txt").read_text().split()


def glosses_for(label: str) -> List[str]:
    return ALIASES.get(label.lower(), [label.lower()])


def word_table() -> Dict[str, str]:
    """word -> PopSign label, for every word the prototype lexicon can sign."""
    table = {}
    for label in popsign_labels():
        for word in glosses_for(label):
            table.setdefault(word, label)
    return table


# A sign whose hands were detected in fewer frames than this is left out
# rather than shown: the renderer would draw a stub, and which hand is
# dominant would be a guess (PopSign's TREE, seen in 1.5% of frames, came out
# mirrored mid-sentence). Content-blind: it looks at tracking quality only.
MIN_PRESENCE = 0.3


def build(labels_dir: Path, out_dir: Path, trim: bool = True,
          min_presence: float = MIN_PRESENCE) -> Dict[str, object]:
    """Write the lexicon. With trim, each sign is cut to its signing (trim.py)
    and signs whose hands were barely tracked are rejected; without it, files
    are copied as they are."""
    out_dir.mkdir(parents=True, exist_ok=True)
    built, missing, rejected, seconds = {}, [], {}, {}
    for label in popsign_labels():
        source = next((path for path in (labels_dir / f"{label}.pose",
                                         labels_dir / f"{label.lower()}.pose") if path.exists()), None)
        if source is None:
            missing.append(label)
            continue
        data = source.read_bytes()
        if trim:
            data, presence, before, after = _prepare(data)
            if presence < min_presence:
                rejected[label] = round(presence, 3)
                continue
            seconds[label] = [before, after]
        for word in glosses_for(label):
            (out_dir / f"{word}.pose").write_bytes(data)
            built[word] = label

    (out_dir / "ATTRIBUTION.txt").write_text(ATTRIBUTION, encoding="utf-8")
    manifest = {
        "source": "PopSign ASL v1.0",
        "license": "CC BY 4.0",
        "words": dict(sorted(built.items())),
        "labels_missing": missing,
        "labels_rejected_low_hand_presence": rejected,
        "min_presence": min_presence if trim else None,
        "seconds_before_after_trim": seconds,
    }
    (out_dir / "lexicon.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    # Keep derived signs out of git even if the directory sits inside the repo.
    (out_dir / ".gitignore").write_text("*\n", encoding="utf-8")
    return manifest


def _prepare(data: bytes):
    """(trimmed .pose bytes, hand presence in the kept window, seconds before, after)."""
    from io import BytesIO

    from pose_format import Pose

    import trim as trimming

    pose = Pose.read(data)
    fps = float(pose.body.fps) or 30.0
    pose, before, after = trimming.trim_to_signing(pose)
    buffer = BytesIO()
    pose.write(buffer)
    return (buffer.getvalue(), trimming.hand_presence(pose),
            round(before / fps, 2), round(after / fps, 2))


# -- the word list --------------------------------------------------------------

def _columns(words: List[str], per_line: int = 12) -> str:
    rows = [", ".join(words[i:i + per_line]) for i in range(0, len(words), per_line)]
    return "\n".join(rows)


def citizen_signs() -> int:
    with open(COVERAGE / "asl_citizen_vocab.csv", newline="") as handle:
        return sum(1 for row in csv.DictReader(handle) if row["GLOSS"].strip())


def old_files() -> int:
    names = (COVERAGE / "old_lexicon_glosses.txt").read_text().split()
    return len([name for name in names if name not in {"combined_output2", "ns"}])


def citizen_words() -> List[str]:
    with open(COVERAGE / "asl_citizen_vocab.csv", newline="") as handle:
        labels = [row["GLOSS"].strip() for row in csv.DictReader(handle) if row["GLOSS"].strip()]
    return sorted({re.sub(r"\d+$", "", label).lower() for label in labels})


def old_words() -> List[str]:
    names = (COVERAGE / "old_lexicon_glosses.txt").read_text().split()
    return sorted({re.sub(r"_\d+$", "", name) for name in names} - {"combined_output2", "ns"})


def words_markdown() -> str:
    table = word_table()
    words = sorted(table)
    renamed = [f"`{word}` ← PopSign `{label}`" for word, label in sorted(table.items())
               if word != label.lower()]
    citizen, old = citizen_words(), old_words()
    lines = [
        "# Words we can sign",
        "",
        "Generated by `python prototype/popsign_lexicon.py words`. Do not edit by hand.",
        "",
        "| Source | Words | Commercial use | In the prototype |",
        "|---|---|---|---|",
        f"| PopSign ASL v1.0 | {len(popsign_labels())} signs → {len(words)} words | ✅ CC BY 4.0, with attribution | **yes** |",
        f"| ASL Citizen | {citizen_signs()} signs → {len(citizen)} words | ❌ research only, until Microsoft agrees | no |",
        f"| Old lexicon (scraped) | {old_files()} files → {len(old)} words | ❌ not licensed | no; test set only |",
        "",
        "## 1. PopSign: what the prototype signs",
        "",
        "These are the words text-to-gloss must produce for a sign to appear. Any "
        "other word in a sentence is skipped. PopSign was recorded for a children's "
        "game, so the vocabulary is everyday words: animals, family, food, colours, "
        "the home, feelings.",
        "",
        _columns(words),
        "",
        "Words that are signed with a differently named PopSign label:",
        "",
        *[f"- {line}" for line in renamed],
        "",
        "Not in PopSign, so always skipped: common words such as *I, you, good, eat, want, "
        "need, know, name, what, how*. Nor the alphabet, so names and numbers cannot yet "
        "be fingerspelled.",
        "",
        "## 2. ASL Citizen: research only",
        "",
        "Would take the vocabulary to about 2,700 words. It needs Microsoft's permission "
        "(ASL_Citizen@microsoft.com) before a product can use it. Variant numbers are "
        "dropped here, so COOL1 and COOL3 are both listed once as `cool`.",
        "",
        _columns(citizen),
        "",
        "## 3. Old lexicon: not licensed",
        "",
        "Scraped from ASL Signbank (CC BY-NC-SA) and Signing Savvy (terms forbid it). "
        "Used only to measure how close the new signs are to the old; never shipped.",
        "",
        _columns(old),
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="Build the lexicon from converted PopSign clips")
    b.add_argument("--labels", required=True, type=Path, help="Directory of <label>.pose")
    b.add_argument("--out", type=Path, default=REPO_ROOT / "lexicon" / "popsign")
    b.add_argument("--no-trim", action="store_true",
                   help="Copy clips as they are: no motion trim, no presence floor")
    b.add_argument("--min-presence", type=float, default=MIN_PRESENCE,
                   help=f"Reject signs whose hands were seen in fewer frames (default {MIN_PRESENCE})")
    sub.add_parser("words", help="Print the word list as Markdown")
    args = parser.parse_args()

    if args.command == "words":
        sys.stdout.write(words_markdown())
        return 0

    if not args.labels.is_dir():
        parser.error(f"no such directory: {args.labels}")
    manifest = build(args.labels, args.out, trim=not args.no_trim, min_presence=args.min_presence)
    signs = len(set(manifest["words"].values()))
    print(f"{len(manifest['words'])} words from {signs} PopSign signs -> {args.out}")
    if manifest["labels_missing"]:
        print(f"no clip for {len(manifest['labels_missing'])} labels: "
              f"{' '.join(manifest['labels_missing'])}", file=sys.stderr)
    rejected = manifest["labels_rejected_low_hand_presence"]
    if rejected:
        print(f"left out {len(rejected)} signs with hands seen in < {args.min_presence:.0%} of frames: "
              f"{' '.join(rejected)}", file=sys.stderr)
    timings = manifest["seconds_before_after_trim"].values()
    if timings:
        before = sum(t[0] for t in timings) / len(timings)
        after = sum(t[1] for t in timings) / len(timings)
        print(f"average sign length {before:.1f} s -> {after:.1f} s after trimming")
    print(f"use it:  ASLYTICS_LEXICON_DIR={args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
