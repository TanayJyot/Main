"""Tests for fingerspelling: extraction from Kaggle-shaped data, and the renderer's plan.

    python prototype/test_fingerspelling.py

The extraction tests build a small fake competition folder: phrases in which
every character is a distinct handshape, held still, with movement between
characters, in the Kaggle parquet layout (one row per frame, columns
x_/y_/z_<group>_<i>, sequence_id index).
"""

import json
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import fingerspelling as fs  # noqa: E402

SAMPLE = HERE.parent / "pose-master" / "pose-master" / "src" / "python" / "tests" / "data" / "mediapipe.pose"
RATIO = 16 / 9          # image height / width of the fake camera
HOLD, MOVE = 9, 5       # frames per held character, per transition


def _shape(char: str) -> np.ndarray:
    """A distinct, fixed 21-point handshape per character, in true proportions."""
    rng = np.random.default_rng(ord(char))
    points = np.zeros((21, 3))
    for a, b in fs.HAND_BONES:
        points[b] = points[a] + np.append(rng.normal(0, 1, 2), 0) * 0.02 + np.array([0, -0.02, 0])
    return points


def _rotate(points: np.ndarray, angle: float) -> np.ndarray:
    c, s = np.cos(angle), np.sin(angle)
    out = points.copy()
    out[:, 0], out[:, 1] = c * points[:, 0] - s * points[:, 1], s * points[:, 0] + c * points[:, 1]
    return out


def _frames_for(phrase: str, rng, side: float = 0.35):
    """Right-hand frames (T, 21, 3) in image coordinates for a phrase, plus pose (T, 33, 3)."""
    chars = [c for c in phrase if c != " "]
    frames = []
    for i, char in enumerate(chars):
        held = _rotate(_shape(char), 0.3 * np.sin(i))
        frames += [held] * HOLD
        if i + 1 < len(chars):
            nxt = _rotate(_shape(chars[i + 1]), 0.3 * np.sin(i + 1))
            frames += [held + (nxt - held) * (k + 1) / (MOVE + 1) + np.array([0.03 * np.sin(k), 0, 0])
                       for k in range(MOVE)]
    hand = np.stack(frames) + np.array([side, 0.5, 0.0])
    hand = hand + rng.normal(0, 1e-4, hand.shape)
    hand[:, :, 1] = 0.5 + (hand[:, :, 1] - 0.5) / RATIO        # what a 16:9 portrait camera records
    pose = np.full((len(hand), 33, 3), np.nan)
    pose[:, 11] = [0.6, 0.7, 0]                                  # left shoulder, image right
    pose[:, 12] = [0.4, 0.7, 0]                                  # right shoulder, image left
    pose[:, 16] = hand[:, 0]                                     # right wrist
    return hand, pose


def _write_folder(root: Path, phrases, left_handed=()):
    import pandas as pd

    rng = np.random.default_rng(1)
    rows, meta = [], []
    for sequence_id, phrase in enumerate(phrases, start=100):
        hand, pose = _frames_for(phrase, rng, side=0.65 if sequence_id in left_handed else 0.35)
        empty_hand = np.full_like(hand, np.nan)
        groups = {"face": np.full((len(hand), 468, 3), np.nan), "pose": pose,
                  "left_hand": hand if sequence_id in left_handed else empty_hand,
                  "right_hand": empty_hand if sequence_id in left_handed else hand}
        for t in range(len(hand)):
            row = {"sequence_id": sequence_id, "frame": t}
            for group, values in groups.items():
                for i in range(values.shape[1]):
                    row[f"x_{group}_{i}"], row[f"y_{group}_{i}"], row[f"z_{group}_{i}"] = values[t, i]
            rows.append(row)
        meta.append({"path": "train_landmarks/1.parquet", "file_id": 1, "sequence_id": sequence_id,
                     "participant_id": sequence_id % 3, "phrase": phrase})
    (root / "train_landmarks").mkdir(parents=True)
    pd.DataFrame(rows).set_index("sequence_id").to_parquet(root / "train_landmarks" / "1.parquet")
    pd.DataFrame(meta).to_csv(root / "train.csv", index=False)


PHRASES = ["ab 12", "ba 21", "a1b2", "2b1a", "www.ab.com", "ab-12"]


def test_holds_finds_one_still_stretch_per_character():
    activity = np.array([0, 0, 0, 5, 5, 0, 0, 0, 5, 5, 0, 0, 0], dtype=float)
    assert fs.holds(activity, 3) == [(0, 3), (5, 8), (10, 13)]
    assert fs.holds(activity, 5) is None
    # A one-frame flicker inside a hold does not split it.
    flicker = np.array([0, 0, 1, 0, 0, 5, 5, 5, 0, 0, 0, 0], dtype=float)
    assert fs.holds(flicker, 2) == [(0, 5), (8, 12)]


def test_aspect_ratio_is_recovered_from_hand_rigidity():
    hands = []
    for char in "ab12":
        # A rigid hand turning through 170 degrees, then squashed the way a
        # camera with a 16:9 portrait image records normalised coordinates.
        true = np.stack([_rotate(_shape(char), a) for a in np.linspace(0, 3, 40)]) + np.array([0.5, 0.5, 0])
        true[:, :, 1] = 0.5 + (true[:, :, 1] - 0.5) / RATIO
        hands.append(true)
    assert abs(fs.estimate_aspect(hands) - RATIO) < 0.05, fs.estimate_aspect(hands)


def test_extract_writes_one_clip_per_character():
    from pose_format import Pose

    with tempfile.TemporaryDirectory() as tmp:
        data, out = Path(tmp) / "data", Path(tmp) / "out"
        _write_folder(data, PHRASES, left_handed={102})
        report = fs.extract(data, out, SAMPLE, fps=30.0)

        # Punctuation phrases are not used: "." and "-" may be signed.
        assert report["sequences_read"] == len(PHRASES)
        assert report["phrases_split_cleanly"] == 4, report
        assert sorted(report["characters"]) == ["1", "2", "a", "b"]
        assert "z" in report["characters_missing"]
        assert all(info["examples"] == 4 for info in report["characters"].values())

        header = Pose.read(SAMPLE.read_bytes()).header
        for char in "ab12":
            pose = Pose.read((out / f"fs_{char}.pose").read_bytes())
            assert [c.name for c in pose.header.components] == [c.name for c in header.components]
            assert pose.body.fps == 30.0
            assert fs.MIN_CLIP_FRAMES <= len(pose.body.data) <= HOLD + 2 * fs.CLIP_MARGIN, char

        assert json.loads((out / "fingerspelling.json").read_text())["license"].startswith("CC BY 4.0")
        assert "Fingerspelling" in (out / "ATTRIBUTION.txt").read_text()
        assert (out / ".gitignore").read_text() == "*\n"


def test_every_example_holds_its_own_characters_shape():
    """Each clip cut from a phrase is nearer its own character's handshape
    than any other character's: holds are paired with the right characters."""
    def expected(char, position):
        return fs.handshape(_rotate(_shape(char), 0.3 * np.sin(position))[None]
                            * np.array([1, 1 / RATIO, 1]), RATIO)[0]

    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "data"
        _write_folder(data, PHRASES)
        checked = 0
        for seq in fs.read_sequences(data):
            chars = [c for c in seq.phrase if c != " "]
            for position, example in enumerate(fs.examples_from(seq, RATIO)):
                distances = {c: np.linalg.norm(example.shape - expected(c, position)) for c in "ab12"}
                assert min(distances, key=distances.get) == example.char, (seq.phrase, distances)
                assert chars[position] == example.char
                checked += 1
        assert checked == 16


def test_left_side_signing_is_mirrored_to_the_right_side():
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "data"
        _write_folder(data, ["ab"], left_handed={100})
        (seq,) = list(fs.read_sequences(data))
        assert fs._needs_mirror(seq, 0, 10)
        _write_folder(Path(tmp) / "right", ["ab"])
        (seq,) = list(fs.read_sequences(Path(tmp) / "right"))
        assert not fs._needs_mirror(seq, 0, 10)


# -- the renderer's plan ---------------------------------------------------------

def _service(names):
    from asl_renderer import RenderService

    tmp = tempfile.mkdtemp()
    for name in names:
        (Path(tmp) / f"{name}.pose").write_bytes(b"")
    return RenderService(lexicon_directory=tmp, clip_cache=False)


LETTERS = [f"fs_{c}" for c in "abcdefghijklmnopqrstuvwxyz0123456789"]


def test_plan_signs_what_it_can_and_spells_the_rest():
    service = _service(["dog", "milk"] + LETTERS)
    plan = service.plan(["dog", "you", "milk"])
    assert plan["signed"] == ["dog", "milk"]
    assert plan["spelled"] == ["you"]
    assert plan["sequence"] == ["dog", "fs_y", "fs_o", "fs_u", "milk"]
    assert plan["skipped"] == []


def test_plan_spells_names_given_as_letters():
    service = _service(["dog"] + LETTERS)
    plan = service.plan(["s", "a", "m", "dog"])
    assert plan["spelled"] == ["sam"]
    assert plan["sequence"] == ["fs_s", "fs_a", "fs_m", "dog"]


def test_plan_does_not_spell_the_pronoun_i_but_does_spell_digits():
    service = _service(["cat"] + LETTERS)
    plan = service.plan(["i", "3", "cat"])
    assert plan["skipped"] == ["i"]
    assert plan["spelled"] == ["3"]
    assert plan["sequence"] == ["fs_3", "cat"]


def test_plan_without_letters_skips_like_before():
    service = _service(["dog", "milk"])
    plan = service.plan(["dog", "you", "milk", "you"])
    assert plan == {"sequence": ["dog", "milk"], "signed": ["dog", "milk"],
                    "spelled": [], "skipped": ["you"]}


def test_plan_skips_a_word_with_a_missing_letter():
    service = _service(["dog"] + [f"fs_{c}" for c in "abc"])
    plan = service.plan(["cab", "zoo", "dog"])
    assert plan["spelled"] == ["cab"]
    assert plan["skipped"] == ["zoo"]


def test_build_merges_letters_and_their_credit():
    import popsign_lexicon as pl

    with tempfile.TemporaryDirectory() as tmp:
        labels, letters, out = Path(tmp) / "labels", Path(tmp) / "letters", Path(tmp) / "out"
        labels.mkdir()
        letters.mkdir()
        (labels / "dog.pose").write_bytes(b"dog")
        (letters / "fs_a.pose").write_bytes(b"a")
        (letters / "ATTRIBUTION.txt").write_text(fs.ATTRIBUTION)
        manifest = pl.build(labels, out, trim=False, letters_dir=letters)
        assert (out / "fs_a.pose").read_bytes() == b"a"
        assert manifest["letters"] == ["a"]
        assert "Fingerspelling" in manifest["source"]
        credit = (out / "ATTRIBUTION.txt").read_text()
        assert "PopSign" in credit and "Fingerspelling" in credit


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")
