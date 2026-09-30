"""text-to-gloss/start.py against Stanza's parse structure, without models.

stanfordnlp named the fields index / governor / dependency_relation; Stanza
names them id / head / deprel. These tests feed start.translate() a parse built
by hand in Stanza's shape, so a field-name regression fails here instead of
deep inside a caption run. The parses are what Stanza 1.14 (EWT) produced for
these sentences on 2026-09-30.

    python tools/tests/test_gloss_parse.py
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "text-to-gloss"))

import start  # noqa: E402  (does not build the pipeline on import)


class Word:
    """The Stanza Word fields start.py reads. No stanfordnlp names."""

    def __init__(self, id, head, text, lemma, upos, deprel):
        self.id, self.head, self.text, self.lemma = id, head, text, lemma
        self.upos, self.xpos, self.deprel = upos, upos, deprel


class Token:
    def __init__(self, word):
        self.words = [word]


class Sentence:
    def __init__(self, rows):
        self.tokens = [Token(Word(*row)) for row in rows]


def gloss(rows):
    return [w["lemma"] for w in start.translate(Sentence(rows))[0]]


def test_copula_and_determiner_dropped():
    rows = [(1, 2, "all", "all", "DET", "det"), (2, 4, "animals", "animal", "NOUN", "nsubj"),
            (3, 4, "are", "be", "AUX", "cop"), (4, 0, "bad", "bad", "ADJ", "root")]
    assert gloss(rows) == ["animal", "bad"], gloss(rows)


def test_sentence_that_crashed_stanfordnlp():
    # stanfordnlp 0.2.0's lemmatiser raised index_select() on this sentence.
    rows = [(1, 3, "after", "after", "ADP", "case"), (2, 3, "the", "the", "DET", "det"),
            (3, 7, "bath", "bath", "NOUN", "obl"), (4, 5, "the", "the", "DET", "det"),
            (5, 7, "aunt", "aunt", "NOUN", "nsubj"), (6, 7, "is", "be", "AUX", "cop"),
            (7, 0, "awake", "awake", "ADJ", "root")]
    assert gloss(rows) == ["bath", "aunt", "awake"], gloss(rows)


def test_numbers_are_kept():
    # The NUM branch used to build a list and never add it: numbers vanished.
    rows = [(1, 2, "sam", "sam", "PROPN", "nsubj"), (2, 0, "has", "have", "VERB", "root"),
            (3, 4, "3", "3", "NUM", "nummod"), (4, 2, "cats", "cat", "NOUN", "obj")]
    assert "3" in gloss(rows), gloss(rows)


def test_time_word_fronted():
    rows = [(1, 4, "yesterday", "yesterday", "NOUN", "obl:unmarked"), (2, 3, "the", "the", "DET", "det"),
            (3, 4, "boy", "boy", "NOUN", "nsubj"), (4, 0, "saw", "see", "VERB", "root"),
            (5, 7, "a", "a", "DET", "det"), (6, 7, "yellow", "yellow", "ADJ", "amod"),
            (7, 4, "bird", "bird", "NOUN", "obj"), (8, 10, "in", "in", "ADP", "case"),
            (9, 10, "the", "the", "DET", "det"), (10, 4, "tree", "tree", "NOUN", "obl")]
    assert gloss(rows) == ["yellow", "yesterday", "boy", "bird", "tree", "see"], gloss(rows)


def test_pipeline_env_requires_stanza():
    sys.path.insert(0, str(REPO / "utils"))
    import aslytics_env

    assert aslytics_env.REQUIRED_MODULES[aslytics_env.GLOSS] == ["stanza"]


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, test in tests:
        try:
            test(); print(f"  ok    {name}")
        except Exception as error:  # noqa: BLE001
            failed += 1; print(f"  FAIL  {name}: {error!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
