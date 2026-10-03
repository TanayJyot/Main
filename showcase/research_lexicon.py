"""Stack several lexicons into one research-preview lexicon.

    python showcase/research_lexicon.py --layer lexicon/aslc --layer lexicon/popsign \\
        [--layer lexicon/fingerspelling] --out lexicon/research

Each layer is a lexicon folder (a <word>.pose per word, and optionally
fs_<char>.pose letters, lexicon.json and ATTRIBUTION.txt). Where two layers
sign the same word, the earlier layer wins: put the best-recorded source
first. ASL Citizen was filmed on webcams with both hands in view; PopSign on a
phone held in one hand, so two-handed signs come out one-handed.

The result is research-only if any layer is (its lexicon.json says
research_only), and every page that shows it says so. It is never committed:
the folder gets a .gitignore of "*".
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
RESEARCH_LICENSE = "Research preview only: not for distribution or commercial use"


def _manifest(layer: Path) -> Dict[str, object]:
    try:
        return json.loads((layer / "lexicon.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _place(source: Path, target: Path) -> None:
    """Hard-link when possible (no extra disk), else copy."""
    if target.exists():
        target.unlink()
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def build(layers: List[Path], out_dir: Path) -> Dict[str, object]:
    if out_dir.exists():
        for old in out_dir.glob("*.pose"):
            old.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / ".gitignore").write_text("*\n", encoding="utf-8")

    words: Dict[str, str] = {}
    letters: Dict[str, str] = {}
    sources, credits, research_only, per_layer = [], [], False, {}
    for layer in layers:
        info = _manifest(layer)
        name = str(info.get("source") or layer.name)
        research_only = research_only or bool(info.get("research_only"))
        added = 0
        for clip in sorted(layer.glob("*.pose")):
            stem = clip.stem
            if stem.startswith("fs_"):
                if stem[3:] not in letters:
                    letters[stem[3:]] = name
                    _place(clip, out_dir / clip.name)
            elif stem not in words:
                words[stem] = name
                _place(clip, out_dir / clip.name)
                added += 1
        per_layer[name] = added
        if added or any(source == name for source in letters.values()):
            sources.append(name)
            credit = layer / "ATTRIBUTION.txt"
            if credit.exists():
                credits.append(credit.read_text(encoding="utf-8").strip())

    license_text = RESEARCH_LICENSE if research_only else "; ".join(
        sorted({str(_manifest(layer).get("license", "")) for layer in layers} - {""}))
    manifest = {
        "source": ", ".join(sources),
        "license": license_text,
        "research_only": research_only,
        "words_per_source": per_layer,
        "letters": sorted(letters),
        "words": dict(sorted(words.items())),
    }
    (out_dir / "lexicon.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    (out_dir / "ATTRIBUTION.txt").write_text("\n\n".join(credits) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--layer", action="append", type=Path, required=True,
                        help="A lexicon folder; repeat, best source first")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "lexicon" / "research")
    args = parser.parse_args()
    for layer in args.layer:
        if not layer.is_dir():
            parser.error(f"no such folder: {layer}")
    manifest = build(args.layer, args.out)
    print(f"{len(manifest['words'])} words -> {args.out}")
    for source, count in manifest["words_per_source"].items():
        print(f"  {count:5d} from {source}")
    if manifest["letters"]:
        print(f"  fingerspelling: {''.join(manifest['letters'])}")
    if manifest["research_only"]:
        print("RESEARCH PREVIEW ONLY: keep it on this machine.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
