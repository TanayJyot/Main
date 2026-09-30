"""Tests for the prototype lexicon builder and skip-missing rendering.

    python prototype/test_popsign_lexicon.py
"""

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import popsign_lexicon as pl  # noqa: E402


def test_labels_map_to_the_words_text_to_gloss_emits():
    assert pl.glosses_for("callonphone") == ["call"]
    assert pl.glosses_for("hesheit") == ["he", "she", "it"]
    assert pl.glosses_for("TV") == ["tv"]
    assert pl.glosses_for("dog") == ["dog"]


def test_a_different_sign_is_never_aliased():
    table = pl.word_table()
    # PopSign's BETTER is not GOOD, and GLASSWINDOW is not a drinking glass.
    assert "good" not in table
    assert "glass" not in table
    assert table["better"] == "better"
    assert table["window"] == "glasswindow"


def test_every_popsign_label_yields_a_word():
    table = pl.word_table()
    assert len(pl.popsign_labels()) == 250
    assert set(table.values()) == set(pl.popsign_labels())


def test_build_copies_renames_and_credits():
    with tempfile.TemporaryDirectory() as tmp:
        labels, out = Path(tmp) / "labels", Path(tmp) / "out"
        labels.mkdir()
        (labels / "callonphone.pose").write_bytes(b"call")
        (labels / "TV.pose").write_bytes(b"tv")
        (labels / "dog.pose").write_bytes(b"dog")
        manifest = pl.build(labels, out)

        assert (out / "call.pose").read_bytes() == b"call"
        assert (out / "tv.pose").read_bytes() == b"tv"
        assert not (out / "callonphone.pose").exists()
        assert manifest["words"] == {"call": "callonphone", "dog": "dog", "tv": "TV"}
        assert "cat" in manifest["labels_missing"]
        assert "CC BY 4.0" in (out / "ATTRIBUTION.txt").read_text()
        assert (out / ".gitignore").read_text() == "*\n"
        assert json.loads((out / "lexicon.json").read_text())["license"] == "CC BY 4.0"


def test_split_available_keeps_order_and_reports_missing():
    from asl_renderer import RenderService

    with tempfile.TemporaryDirectory() as tmp:
        for name in ("dog", "milk", "bake_1"):
            (Path(tmp) / f"{name}.pose").write_bytes(b"")
        service = RenderService(lexicon_directory=tmp, clip_cache=False)
        kept, missing = service.split_available(["dog", "you", "milk", "you", "bake", "zebra"])
        assert kept == ["dog", "milk", "bake"]
        assert missing == ["you", "zebra"]


def test_word_list_is_current():
    committed = (HERE / "WORDS.md").read_text(encoding="utf-8")
    assert committed == pl.words_markdown(), "run: python prototype/popsign_lexicon.py words > prototype/WORDS.md"


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")
