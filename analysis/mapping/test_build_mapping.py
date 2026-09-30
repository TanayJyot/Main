"""Tests for build_mapping.py. Run: python analysis/mapping/test_build_mapping.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_mapping as bm  # noqa: E402


def test_old_variants_share_a_concept():
    mapping, _ = bm.parse_old(["bake_1", "bake_2", "children"])
    assert mapping["bake"] == ["bake_1", "bake_2"]
    assert mapping["child"] == ["children"], "surface forms must lemmatise"


def test_old_skips_non_signs_and_expands_contraction():
    mapping, notes = bm.parse_old(["combined_output2", "ns", "don't"])
    assert set(mapping) == {"do not"}
    assert "don't" in notes


def test_popsign_aliases_fan_out():
    mapping, _ = bm.parse_popsign(["hesheit", "apple"])
    assert {"he", "she", "it", "apple"} <= set(mapping)
    assert mapping["she"] == ["hesheit"]


def test_citizen_numbered_variants_collapse_to_one_concept():
    mapping, _ = bm.parse_citizen(["COOL1", "COOL3"])
    assert mapping["cool"] == ["COOL1", "COOL3"]


def test_citizen_phrase_is_not_split():
    """STAND-UP is one sign. Splitting it would credit a sign for UP."""
    mapping, notes = bm.parse_citizen(["STAND-UP"])
    assert set(mapping) == {"stand up"}
    assert "up" not in mapping


def test_citizen_fingerspelling_is_one_word():
    mapping, notes = bm.parse_citizen(["W.H.A.T"])
    assert set(mapping) == {"what"} and notes["W.H.A.T"] == "fingerspelled"


def test_citizen_markers_are_stripped_not_counted():
    mapping, notes = bm.parse_citizen(["STRETCH-CA", "WALK-TIGHTROPE-CL"])
    assert "stretch" in mapping and "ca" not in mapping and "cl" not in mapping
    assert "walk tightrope" in mapping


def test_citizen_slash_means_alternatives():
    mapping, _ = bm.parse_citizen(["HURDLE/TRIP1"])
    assert mapping["hurdle"] == ["HURDLE/TRIP1"] and mapping["trip"] == ["HURDLE/TRIP1"]


def test_variant_flags_mark_possible_sense_mismatch():
    rows, _ = bm.build(["cool"], [], ["COOL1", "COOL3"])
    (row,) = rows
    assert row["in_old"] and row["in_citizen"]
    assert "citizen has variants" in row["flags"]


def test_real_lists_cover_every_pilot_gloss():
    old, pop, cit = bm.load_sources()
    rows, _ = bm.build(old, pop, cit)
    files = {name for row in rows for name in row["old_files"].split("|") if name}
    missing = [name for name in bm.load_pilot() if name not in files]
    assert not missing, missing


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
