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
        manifest = pl.build(labels, out, trim=False)

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


# -- trimming and the presence floor, on the repository's own test pose ------

SAMPLE = HERE.parent / "pose-master" / "pose-master" / "src" / "python" / "tests" / "data" / "mediapipe.pose"


def _sample():
    from pose_format import Pose

    return Pose.read(SAMPLE.read_bytes())


def _popsign_like(seconds_still=3.0):
    """The sample's frames 60-120 of signing, with the pose frozen for
    seconds_still before and after: a signer holding the hand up while the
    phone records, which the renderer's elbow-based trim cannot remove."""
    import numpy as np
    import numpy.ma as ma

    pose = _sample()
    fps = pose.body.fps
    data, conf = pose.body.data[60:120], pose.body.confidence[60:120]
    still = int(seconds_still * fps)
    rng = np.random.default_rng(0)

    def hold(frame_data, frame_conf):
        jitter = rng.normal(0, 1e-4, (still,) + frame_data.shape)
        return (ma.array(np.repeat(frame_data.data[None], still, 0) + jitter,
                         mask=np.repeat(ma.getmaskarray(frame_data)[None], still, 0)),
                np.repeat(frame_conf[None], still, 0))

    head, head_conf = hold(data[0], conf[0])
    tail, tail_conf = hold(data[-1], conf[-1])
    pose.body.data = ma.concatenate([head, data, tail])
    pose.body.confidence = np.concatenate([head_conf, conf, tail_conf])
    return pose, fps


def test_trim_cuts_a_held_hand_down_to_the_signing():
    import trim

    pose, fps = _popsign_like()
    _, before, after = trim.trim_to_signing(pose)
    assert before == 60 + 2 * int(3.0 * fps)
    # 60 frames of signing plus at most the padding either side.
    assert 40 <= after <= 60 + 2 * round(trim.PAD * fps) + 2, (before, after)


def test_trim_leaves_a_still_clip_whole():
    import numpy as np

    import trim

    pose = _sample()
    pose.body.data = pose.body.data[:1].repeat(50, axis=0)
    pose.body.confidence = np.repeat(pose.body.confidence[:1], 50, axis=0)
    _, before, after = trim.trim_to_signing(pose)
    assert before == after == 50


def test_hand_presence_counts_frames_with_a_hand():
    import trim

    pose = _sample()
    assert 0.8 < trim.hand_presence(pose) <= 1.0
    pose.body.confidence[:, :, 136:] = 0     # both hands' 42 points, never seen
    assert trim.hand_presence(pose) == 0.0


def test_build_trims_and_rejects_barely_seen_signs():
    with tempfile.TemporaryDirectory() as tmp:
        labels, out = Path(tmp) / "labels", Path(tmp) / "out"
        labels.mkdir()
        from io import BytesIO

        def write(pose, name):
            buffer = BytesIO()
            pose.write(buffer)
            (labels / f"{name}.pose").write_bytes(buffer.getvalue())

        held, _ = _popsign_like()
        write(held, "dog")
        unseen = _sample()
        unseen.body.confidence[:, :, 136:] = 0
        write(unseen, "tree")

        manifest = pl.build(labels, out)
        assert manifest["words"] == {"dog": "dog"}
        assert manifest["labels_rejected_low_hand_presence"] == {"tree": 0.0}
        before, after = manifest["seconds_before_after_trim"]["dog"]
        assert after < before / 2
        assert not (out / "tree.pose").exists()


def test_word_list_is_current():
    committed = (HERE / "WORDS.md").read_text(encoding="utf-8")
    assert committed == pl.words_markdown(), "run: python prototype/popsign_lexicon.py words > prototype/WORDS.md"


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")
