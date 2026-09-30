"""Which dataset labels may represent each pilot gloss.

Source: analysis/mapping/gloss_mapping.csv (concept-level). A concept can
group labels that are different ASL signs: `good` holds BEST, BETTER and GOOD,
`meet` holds MEET and MEETING, `hour` holds HOUR and 8HOUR. So, per pilot
gloss (an old-lexicon filename) and per dataset:

  1. exact: labels whose normalised form equals the gloss (lower-case,
     trailing variant digits and `_n` suffixes stripped). CALL1 and CALL2 both
     count for `call`.
  2. only if *neither* dataset has an exact label: every label of the
     gloss's concept (i -> ME, number -> NUMBERS, mittens -> mitten). If one
     dataset matches exactly, the other's concept-level labels are dropped:
     they were wrong signs every time (best -> PopSign `better`, late ->
     `later`, children -> `child`, call -> `callonphone`).

The rule uses only the English word, never the old lexicon's content.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

HERE = Path(__file__).parent
MAPPING = HERE.parent / "mapping" / "gloss_mapping.csv"
PILOT = HERE.parent / "coverage" / "pilot_200.txt"


def norm(label: str) -> str:
    return re.sub(r"(_\d+|\d+)$", "", label).lower()


def pilot_glosses() -> list[str]:
    return [l.strip() for l in PILOT.read_text(encoding="utf8").splitlines()
            if l.strip() and not l.startswith("#")]


def candidate_labels() -> dict[str, dict]:
    """gloss -> {concept, popsign: [labels], citizen: [labels], rule}"""
    by_old: dict[str, dict] = {}
    with open(MAPPING, encoding="utf8") as f:
        for row in csv.DictReader(f):
            for old in filter(None, row["old_files"].split("|")):
                by_old[old] = row
    out = {}
    for gloss in pilot_glosses():
        row = by_old[gloss]
        by_source = {s: [l for l in row[c].split("|") if l]
                     for s, c in [("popsign", "popsign_labels"), ("citizen", "citizen_labels")]}
        exact = {s: [l for l in ls if norm(l) == norm(gloss)] for s, ls in by_source.items()}
        any_exact = any(exact.values())
        entry = {"concept": row["concept"], "rule": {}}
        for source, labels in by_source.items():
            entry[source] = exact[source] if any_exact else labels
            entry["rule"][source] = ("exact" if exact[source] else
                                     "none" if any_exact or not labels else "concept")
        out[gloss] = entry
    return out


MAX_SIGNERS = 12
DATA = HERE / "data"


def citizen_candidates() -> dict[str, tuple[str, str]]:
    """video file -> (label, participant) for the ASL Citizen clips that may
    represent a pilot gloss. Content-blind cap, matching PopSign's: per label,
    participants in ID order (P1, P2, ...), first MAX_SIGNERS, and each
    participant's first clip by filename."""
    import csv
    from collections import defaultdict

    wanted = {l for c in candidate_labels().values() for l in c["citizen"]}
    by_label: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for split in ["train", "val", "test"]:
        with open(DATA / "aslc" / f"{split}.csv", encoding="utf8") as f:
            for r in csv.DictReader(f):
                if r["Gloss"] in wanted:
                    by_label[r["Gloss"]][r["Participant ID"]].append(r["Video file"])
    pid = lambda p: (int(p[1:]) if p[1:].isdigit() else 10**6, p)  # noqa: E731
    out = {}
    for label, participants in by_label.items():
        for p in sorted(participants, key=pid)[:MAX_SIGNERS]:
            out[sorted(participants[p])[0]] = (label, p)
    return out
