"""Coverage check: how much of everyday English does each sign lexicon cover?

Answers Part 2 step 1 of the plan: do we need the old lexicon's size, or do
the licensed datasets already cover what captions need?

Frequency source
----------------
There is no local caption corpus and scraping YouTube for one is what we are
trying to avoid, so this uses ``wordfreq``'s English list. It is built from
OpenSubtitles among other sources, which is the closest public proxy to
caption text. Treat the numbers as a proxy, not a measurement of *our*
captions.

Matching
--------
Signs are concept-level, so every frequency token is lemmatised (went -> go,
children -> child) before matching. ASL does not sign English articles,
copulas or most auxiliaries -- ``text-to-gloss`` drops them -- so coverage is
reported both over all tokens and over *signable* tokens with a small,
explicit drop list. Names and other out-of-vocabulary words would be
fingerspelled in practice; that fallback is not modelled here.

Outputs ``coverage.md`` and ``pilot_200.txt`` next to this script.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

import simplemma
from wordfreq import top_n_list, word_frequency

HERE = Path(__file__).parent
TOP_N = 50_000

# English tokens ASL does not sign as separate lexical items. Small on purpose;
# every entry is a token text-to-gloss would drop or fold into another sign.
NOT_SIGNED = {
    "a", "an", "the",
    "am", "is", "are", "was", "were", "be", "been", "being",
    "of", "to", "'s", "s", "t", "'t", "'re", "'ve", "'ll", "'m", "'d",
    "do", "does", "did",   # auxiliary use dominates in captions
    "have", "has", "had",  # ditto; HAVE as possession is in the lexicons anyway
}

# PopSign concatenates some multi-word concepts into one label. Map each to the
# English lemmas it actually covers.
POPSIGN_ALIASES = {
    "callonphone": {"call"},
    "frenchfries": {"fries"},
    "glasswindow": {"window", "glass"},
    "haveto": {"must"},
    "hesheit": {"he", "she", "it"},
    "icecream": {"icecream"},
    "minemy": {"mine", "my"},
    "thankyou": {"thank", "thanks"},
    "weus": {"we", "us"},
    "tv": {"tv"},
    "owie": {"ouch"},
    "shhh": {"shh"},
}


def lemma(word: str) -> str:
    return simplemma.lemmatize(word, lang="en").lower()


OLD_FILENAME: dict[str, str] = {}   # lemma -> actual .pose stem, filled by load_old_lexicon


def load_old_lexicon() -> set[str]:
    out = set()
    for line in (HERE / "old_lexicon_glosses.txt").read_text().split():
        if line in {"combined_output2", "ns"}:
            continue
        lem = lemma(re.sub(r"_\d+$", "", line))
        out.add(lem)
        OLD_FILENAME.setdefault(lem, line)   # first variant wins (bake_1 over bake_2)
    return out


def load_popsign() -> set[str]:
    out = set()
    for line in (HERE / "popsign_glosses.txt").read_text().split():
        key = line.lower()
        out |= POPSIGN_ALIASES.get(key, {lemma(key)})
    return out


def load_asl_citizen() -> set[str]:
    out = set()
    with open(HERE / "asl_citizen_vocab.csv", newline="") as f:
        for row in csv.DictReader(f):
            g = row["GLOSS"].strip().lower()
            g = re.sub(r"\d+$", "", g)           # SOCCER2 -> soccer
            g = re.sub(r"[^a-z]+", " ", g).strip()
            if not g:
                continue
            for part in g.split():
                out.add(lemma(part))
    return out


def frequency_by_lemma() -> dict[str, float]:
    freq: dict[str, float] = defaultdict(float)
    for w in top_n_list("en", TOP_N):
        if not re.fullmatch(r"[a-z]+", w):
            continue
        freq[lemma(w)] += word_frequency(w, "en")
    return freq


def coverage(freq: dict[str, float], lexicon: set[str], drop: set[str]) -> tuple[float, int, int]:
    """(token coverage, types covered in top-1000, types covered in top-5000)."""
    kept = {w: f for w, f in freq.items() if w not in drop}
    total = sum(kept.values())
    covered = sum(f for w, f in kept.items() if w in lexicon)
    ranked = sorted(kept, key=kept.get, reverse=True)
    top1k = sum(1 for w in ranked[:1000] if w in lexicon)
    top5k = sum(1 for w in ranked[:5000] if w in lexicon)
    return covered / total, top1k, top5k


def main() -> None:
    freq = frequency_by_lemma()
    old = load_old_lexicon()
    pop = load_popsign()
    citizen = load_asl_citizen()

    lexicons = {
        "Old lexicon (deployed, 842 files)": old,
        "PopSign ASL v1.0 (CC BY 4.0)": pop,
        "ASL Citizen (needs Microsoft email)": citizen,
        "PopSign + ASL Citizen": pop | citizen,
        "PopSign + ASL Citizen + old": pop | citizen | old,
    }

    lines = [
        "# Coverage check — English caption vocabulary vs sign lexicons",
        "",
        f"Frequency proxy: `wordfreq` English, top {TOP_N:,} surface forms, lemmatised. "
        "Includes OpenSubtitles, the nearest public stand-in for caption text.",
        "",
        "**Token coverage** = share of running words (by frequency mass) that have a sign. "
        "**Signable** excludes articles, copulas and auxiliaries that `text-to-gloss` drops "
        f"({len(NOT_SIGNED)} tokens, listed in `coverage.py`). Names are not handled; they would be fingerspelled.",
        "",
        "| lexicon | concepts | tokens covered (all) | tokens covered (signable) | of top-1,000 lemmas | of top-5,000 lemmas |",
        "|---|---|---|---|---|---|",
    ]
    for name, lex in lexicons.items():
        all_cov, _, _ = coverage(freq, lex, set())
        sig_cov, t1k, t5k = coverage(freq, lex, NOT_SIGNED)
        lines.append(f"| {name} | {len(lex):,} | {all_cov:.1%} | **{sig_cov:.1%}** | {t1k}/1000 | {t5k}/5000 |")

    # What does PopSign lack that the old lexicon had, weighted by frequency?
    kept = {w: f for w, f in freq.items() if w not in NOT_SIGNED}
    ranked = sorted(kept, key=kept.get, reverse=True)
    gap_pop = [w for w in ranked if w in old and w not in pop][:40]
    gap_union = [w for w in ranked if w in old and w not in (pop | citizen)][:40]
    missing_everywhere = [w for w in ranked[:300] if w not in (pop | citizen | old)][:40]
    lines += [
        "",
        "## Most frequent old-lexicon signs that PopSign lacks",
        "",
        ", ".join(gap_pop),
        "",
        "## Most frequent old-lexicon signs that PopSign + ASL Citizen still lack",
        "",
        ", ".join(gap_union) or "(none)",
        "",
        "## Most frequent signable lemmas in no lexicon at all (top 300 by frequency)",
        "",
        ", ".join(missing_everywhere),
    ]

    # Stratified 200-gloss pilot list, drawn from the OLD lexicon so every
    # synthetic sign has a baseline .pose to be scored against.
    old_ranked = [w for w in ranked if w in old]
    head, tail = old_ranked[:100], old_ranked[-100:]
    (HERE / "pilot_200.txt").write_text(
        "# 100 highest-frequency old-lexicon glosses (as .pose filenames)\n"
        + "\n".join(OLD_FILENAME[w] for w in head)
        + "\n\n# 100 lowest-frequency old-lexicon glosses (as .pose filenames)\n"
        + "\n".join(OLD_FILENAME[w] for w in tail) + "\n"
    )
    lines += [
        "",
        "## Pilot list",
        "",
        f"`pilot_200.txt`: 100 head + 100 tail glosses from the old lexicon "
        f"({len(old_ranked)} of its {len(old)} concepts appear in the top {TOP_N:,}). "
        "Every one has a baseline `.pose` to score a synthetic sign against.",
    ]

    (HERE / "coverage.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
