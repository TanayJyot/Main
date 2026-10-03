"""The lexicons the showcase compares, and the sentences it signs.

A tier is a name and a lexicon folder. By default:

  Today            lexicon/popsign    PopSign (CC BY 4.0): what we can ship now
  Research preview lexicon/research   ASL Citizen + PopSign (+ letters), built by
                                      showcase/research_lexicon.py; research only

Set ASLYTICS_SHOWCASE_TIERS to compare others, e.g.
    ASLYTICS_SHOWCASE_TIERS="Today=lexicon/popsign;Preview=lexicon/research"
Tiers whose folder has no signs are left out.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_TIERS = [
    ("Today: PopSign", "lexicon/popsign"),
    ("Research preview: ASL Citizen + PopSign", "lexicon/research"),
]

# Everyday sentences of the kind captions carry: appointments, weather,
# transport, family, safety. Lower case, because text-to-gloss takes capitalised
# words for names and spells them. "sam" is spelled when the lexicon has letters.
SENTENCES = [
    "the dog is hungry",
    "hello, my name is sam and i am deaf",
    "the doctor will see you tomorrow morning",
    "it will rain today, bring your umbrella",
    "do you want coffee or tea?",
    "the bus is late again",
    "please help me find the school",
    "thank you for coming to the meeting",
    "we love our family",
    "call 911 if there is a fire",
    "my birthday is next week",
    "where is the bathroom?",
]


@dataclass
class Tier:
    name: str
    path: Path
    source: str = ""
    license: str = ""
    research_only: bool = False
    words: List[str] = field(default_factory=list)
    letters: List[str] = field(default_factory=list)

    @property
    def slug(self) -> str:
        return "".join(c if c.isalnum() else "_" for c in self.name.lower()).strip("_")[:40]


def load(name: str, path: Path) -> Optional[Tier]:
    path = path if path.is_absolute() else REPO_ROOT / path
    if not path.is_dir():
        return None
    stems = sorted(p.stem for p in path.glob("*.pose"))
    if not stems:
        return None
    try:
        info = json.loads((path / "lexicon.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        info = {}
    return Tier(name=name, path=path, source=str(info.get("source", "")),
                license=str(info.get("license", "")), research_only=bool(info.get("research_only")),
                words=[s for s in stems if not s.startswith("fs_")],
                letters=[s[3:] for s in stems if s.startswith("fs_")])


def parse(spec: str) -> List[tuple]:
    out = []
    for part in spec.split(";"):
        if "=" in part:
            name, path = part.split("=", 1)
            if name.strip() and path.strip():
                out.append((name.strip(), path.strip()))
    return out


def tiers(spec: Optional[str] = None) -> List[Tier]:
    spec = spec if spec is not None else os.environ.get("ASLYTICS_SHOWCASE_TIERS", "")
    pairs = parse(spec) if spec.strip() else DEFAULT_TIERS
    return [tier for name, path in pairs if (tier := load(name, Path(path).expanduser()))]
