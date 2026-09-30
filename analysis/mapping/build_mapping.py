"""Gloss mapping table: old lexicon <-> PopSign <-> ASL Citizen.

HANDOFF.md task 2. Every later step keys off this table: conversion (which
PopSign / ASL Citizen clips to convert for a pilot gloss), and evaluation
(which old .pose a new one is compared against).

Keyed by English **concept** (a lemma, or a whole phrase), with every label
each dataset uses for it:

    concept, old_files, popsign_labels, citizen_labels, ...

Matching reuses coverage.py's ``lemma`` and ``POPSIGN_ALIASES`` so the two
never disagree about what a word is. It differs from coverage.py's ASL
Citizen parsing in one deliberate way. coverage.py splits every label into
words, which is fine for a coverage estimate but wrong for a mapping:
``STAND-UP`` is one sign, not STAND plus UP, and ``W.H.A.T`` is a
fingerspelled word, not four letters. Here those stay whole.

**A concept is not a sign.** Lemmatising merges English words that are
different ASL signs: `good` holds BEST, BETTER and GOOD; `meet` holds MEET and
MEETING; `old` holds OLD and OLDEST. Use this table to find *candidate*
labels, never to decide that two labels are the same sign. For per-gloss
decisions use the exact-first rule in analysis/convert/labels.py: labels whose
own word equals the gloss, falling back to the concept only when no dataset
has one. (Found by the conversion session, 2026-09-29.)

A shared concept is not a guarantee of the same sign either. ASL Citizen numbers
distinct signs that share an English word (COOL1 and COOL3 need not mean the
same thing), and the old lexicon does the same (bake_1, bake_2). The table
lists every variant and flags concepts where either side has more than one,
so evaluation can report them separately instead of scoring a sense mismatch
as a bad sign.

Outputs, next to this script:
    gloss_mapping.csv   the table
    mapping.md          counts, overlaps, pilot coverage, parse exceptions
"""

from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
COVERAGE = HERE.parent / "coverage"
sys.path.insert(0, str(COVERAGE))

from coverage import NOT_SIGNED, POPSIGN_ALIASES, lemma  # noqa: E402

# ASL Citizen suffixes that annotate *how* a sign is made rather than naming a
# different word: CA = constructed action, CL = classifier.
CITIZEN_MARKERS = {"CA", "CL"}

# Old-lexicon files that are not signs.
OLD_NOT_SIGNS = {"combined_output2", "ns"}


def concept_of(text: str) -> str:
    """Lemmatise a word, or each word of a phrase, into one concept key."""
    words = re.findall(r"[a-z]+", text.lower())
    return " ".join(lemma(word) for word in words)


# -- parsers: each returns {concept: [label, ...]} plus notes -------------------

def parse_old(names):
    mapping, notes = defaultdict(list), {}
    for name in names:
        if name in OLD_NOT_SIGNS:
            continue
        base = re.sub(r"_\d+$", "", name)
        if base == "don't":
            # Contraction: text-to-gloss expands it before lookup.
            key = "do not"
            notes[name] = "contraction, matched as 'do not'"
        else:
            key = concept_of(base)
        mapping[key].append(name)
    return mapping, notes


def parse_popsign(labels):
    mapping, notes = defaultdict(list), {}
    for label in labels:
        low = label.lower()
        if low in POPSIGN_ALIASES:
            concepts = sorted(POPSIGN_ALIASES[low])
            if len(concepts) > 1:
                notes[label] = f"covers {', '.join(concepts)}"
        else:
            concepts = [concept_of(low)]
        for key in concepts:
            mapping[key].append(label)
    return mapping, notes


def parse_citizen(labels):
    """ASL Citizen labels: SOCCER2, HURDLE/TRIP1, STRETCH-CA, W.H.A.T, STAND-UP."""
    mapping, notes = defaultdict(list), {}
    for label in labels:
        body = re.sub(r"\d+$", "", label.strip())

        if re.fullmatch(r"(?:[A-Z]\.)+[A-Z]\.?", body):
            # W.H.A.T -- a fingerspelled word.
            key = concept_of(body.replace(".", ""))
            notes[label] = "fingerspelled"
            mapping[key].append(label)
            continue

        parts = body.split("-")
        if len(parts) > 1 and parts[-1] in CITIZEN_MARKERS:
            notes[label] = f"-{parts[-1]} marker ({'constructed action' if parts[-1] == 'CA' else 'classifier'})"
            parts = parts[:-1]
        body = "-".join(parts)

        # "/" separates alternative English words for one sign.
        alternatives = body.split("/")
        if len(alternatives) > 1:
            notes[label] = (notes.get(label, "") + "; " if label in notes else "") + \
                f"alternatives: {', '.join(a.lower() for a in alternatives)}"

        for alternative in alternatives:
            # A hyphen inside what is left joins a phrase: STAND-UP is one sign.
            key = concept_of(alternative.replace("-", " "))
            if " " in key and label not in notes:
                notes[label] = "phrase, kept whole"
            if key:
                mapping[key].append(label)
    return mapping, notes


# -- loading -------------------------------------------------------------------

def load_sources():
    old_names = (COVERAGE / "old_lexicon_glosses.txt").read_text().split()
    popsign_labels = (COVERAGE / "popsign_glosses.txt").read_text().split()
    with open(COVERAGE / "asl_citizen_vocab.csv", newline="") as handle:
        citizen_labels = [row["GLOSS"] for row in csv.DictReader(handle) if row["GLOSS"].strip()]
    return old_names, popsign_labels, citizen_labels


def load_pilot():
    return [line.strip() for line in (COVERAGE / "pilot_200.txt").read_text().splitlines()
            if line.strip() and not line.startswith("#")]


def build(old_names, popsign_labels, citizen_labels):
    old, old_notes = parse_old(old_names)
    pop, pop_notes = parse_popsign(popsign_labels)
    cit, cit_notes = parse_citizen(citizen_labels)

    rows = []
    for key in sorted(set(old) | set(pop) | set(cit)):
        flags = []
        if len(old.get(key, [])) > 1:
            flags.append("old has variants")
        if len(cit.get(key, [])) > 1:
            flags.append("citizen has variants")
        if " " in key:
            flags.append("phrase")
        if key in NOT_SIGNED:
            flags.append("not signed by text-to-gloss")
        rows.append({
            "concept": key,
            "old_files": "|".join(sorted(old.get(key, []))),
            "popsign_labels": "|".join(sorted(set(pop.get(key, [])))),
            "citizen_labels": "|".join(sorted(set(cit.get(key, [])))),
            "in_old": int(key in old),
            "in_popsign": int(key in pop),
            "in_citizen": int(key in cit),
            "flags": "; ".join(flags),
        })
    notes = {"old": old_notes, "popsign": pop_notes, "citizen": cit_notes}
    return rows, notes


def summarise(rows, notes, pilot, source_counts):
    def count(predicate):
        return sum(1 for row in rows if predicate(row))

    by_file = {}
    for row in rows:
        for name in filter(None, row["old_files"].split("|")):
            by_file[name] = row

    pilot_rows = [by_file.get(name) for name in pilot]
    unmatched_pilot = [name for name, row in zip(pilot, pilot_rows) if row is None]
    pilot_rows = [row for row in pilot_rows if row is not None]

    shared_old_cit = [row for row in rows if row["in_old"] and row["in_citizen"]]
    ambiguous = [row for row in shared_old_cit if "variants" in row["flags"]]

    lines = [
        "# Gloss mapping — old lexicon ↔ PopSign ↔ ASL Citizen",
        "",
        "Built by `build_mapping.py` from the gloss lists in `analysis/coverage/`. "
        "Keyed by English concept (lemma or whole phrase). Full table: `gloss_mapping.csv`.",
        "",
        "## Sources",
        "",
        "| dataset | labels in list | concepts after matching |",
        "|---|---|---|",
        f"| Old lexicon | {source_counts['old']} files | {count(lambda r: r['in_old'])} |",
        f"| PopSign ASL v1.0 | {source_counts['popsign']} | {count(lambda r: r['in_popsign'])} |",
        f"| ASL Citizen | {source_counts['citizen']} | {count(lambda r: r['in_citizen'])} |",
        "",
        "## Overlap with the old lexicon",
        "",
        "Only concepts present in both can be compared old-vs-new.",
        "",
        "| | concepts shared with old |",
        "|---|---|",
        f"| PopSign | {count(lambda r: r['in_old'] and r['in_popsign'])} |",
        f"| ASL Citizen | {len(shared_old_cit)} |",
        f"| PopSign or ASL Citizen | {count(lambda r: r['in_old'] and (r['in_popsign'] or r['in_citizen']))} |",
        f"| Old only (no licensed replacement) | {count(lambda r: r['in_old'] and not r['in_popsign'] and not r['in_citizen'])} |",
        "",
        f"Of the {len(shared_old_cit)} old ∩ ASL Citizen concepts, **{len(ambiguous)}** have more "
        "than one variant on at least one side. The same English word may be a different sign "
        "there, so evaluation reports these separately.",
        "",
        "## Pilot list (`pilot_200.txt`)",
        "",
        "| | pilot glosses |",
        "|---|---|",
        f"| matched to a concept | {len(pilot_rows)} / {len(pilot)} |",
        f"| covered by PopSign | {sum(r['in_popsign'] for r in pilot_rows)} |",
        f"| covered by ASL Citizen | {sum(r['in_citizen'] for r in pilot_rows)} |",
        f"| covered by either | {sum(1 for r in pilot_rows if r['in_popsign'] or r['in_citizen'])} |",
        f"| covered by neither | {sum(1 for r in pilot_rows if not r['in_popsign'] and not r['in_citizen'])} |",
    ]
    if unmatched_pilot:
        lines += ["", f"Unmatched pilot entries: {', '.join(unmatched_pilot)}"]

    lines += [
        "",
        "## Warning: a concept is not a sign",
        "",
        "Lemmatising merges different ASL signs into one concept: `good` holds "
        "BEST, BETTER and GOOD; `meet` holds MEET and MEETING. This table lists "
        "*candidate* labels. For per-gloss decisions, match the exact word first "
        "and fall back to the concept only when no dataset has it; see "
        "`analysis/convert/labels.py`. The coverage figures in "
        "`analysis/coverage/coverage.md` use the same lemmatising, so they may "
        "be slightly optimistic.",
    ]

    lines += ["", "## Labels that needed special handling", ""]
    for source, entries in notes.items():
        for label, note in sorted(entries.items()):
            lines.append(f"- {source} `{label}` — {note}")
    return "\n".join(lines) + "\n"


def main() -> None:
    old_names, popsign_labels, citizen_labels = load_sources()
    rows, notes = build(old_names, popsign_labels, citizen_labels)

    with open(HERE / "gloss_mapping.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    report = summarise(rows, notes, load_pilot(), {
        "old": len([n for n in old_names if n not in OLD_NOT_SIGNS]),
        "popsign": len(popsign_labels),
        "citizen": len(citizen_labels),
    })
    (HERE / "mapping.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
