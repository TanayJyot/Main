"""Tests for the research-preview showcase tools.

    python showcase/test_showcase.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "prototype"))

import citizen  # noqa: E402
import stack_lexicons  # noqa: E402

SAMPLE = HERE.parent / "pose-master" / "pose-master" / "src" / "python" / "tests" / "data" / "mediapipe.pose"


def test_labels_become_the_words_text_to_gloss_emits():
    assert citizen.words_for("DOG") == (0, 0, ["dog"])
    assert citizen.words_for("WANT2") == (1, 2, ["want"])
    assert citizen.words_for("THIS/IT")[2] == ["this", "it"]
    assert citizen.words_for("W.H.A.T")[2] == ["what"]
    assert citizen.words_for("SKI-CA")[2] == ["ski"]
    assert citizen.words_for("STAND-UP")[2] == []          # two words cannot match one gloss
    assert citizen.words_for("ME")[2] == ["me", "i"]


def test_the_plainest_label_wins_a_word():
    table = citizen.word_table(["WANT2", "WANT1", "W.H.A.T", "WHAT1", "SKI-CA", "SKI", "THIS/IT", "IT"])
    assert table["want"] == "WANT1"
    assert table["what"] == "WHAT1"
    assert table["ski"] == "SKI"
    assert table["it"] == "IT"
    assert table["this"] == "THIS/IT"


def test_candidates_are_the_first_signers_by_id_one_clip_each():
    rows = [{"Gloss": "DOG", "Participant ID": p, "Video file": f}
            for p, f in [("P10", "a.mp4"), ("P2", "c.mp4"), ("P2", "b.mp4"), ("P1", "d.mp4"), ("P3", "e.mp4")]]
    rows.append({"Gloss": "CAT", "Participant ID": "P1", "Video file": "x.mp4"})
    assert citizen.candidates(rows, {"DOG"}, max_signers=3) == {"DOG": ["d.mp4", "b.mp4", "e.mp4"]}


def _write(pose, path):
    with open(path, "wb") as handle:
        pose.write(handle)


def test_export_picks_the_best_tracked_clip_and_marks_non_commercial():
    from pose_format import Pose

    with tempfile.TemporaryDirectory() as tmp:
        data, out = Path(tmp) / "data", Path(tmp) / "out"
        (data / "pose").mkdir(parents=True)
        good = Pose.read(SAMPLE.read_bytes())
        _write(good, data / "pose" / "1-DOG.pose")
        worse = Pose.read(SAMPLE.read_bytes())
        worse.body.confidence[: len(worse.body.confidence) // 2, :, 136:] = 0   # hands unseen half the time
        _write(worse, data / "pose" / "0-DOG.pose")
        unseen = Pose.read(SAMPLE.read_bytes())
        unseen.body.confidence[:, :, 136:] = 0
        _write(unseen, data / "pose" / "2-CAT.pose")

        manifest = citizen.export(out, data, table={"dog": "DOG", "cat": "CAT", "me": "ME"},
                                  chosen={"DOG": ["0-DOG.mp4", "1-DOG.mp4"], "CAT": ["2-CAT.mp4"],
                                          "ME": ["3-ME.mp4"]})
        assert manifest["words"] == {"dog": "DOG"}
        assert manifest["picks"]["DOG"]["clip"] == "1-DOG.pose"
        assert manifest["labels_rejected_low_hand_presence"] == {"CAT": 0.0}
        assert manifest["labels_missing"] == ["ME"]
        assert manifest["non_commercial"] is True
        assert (out / "dog.pose").exists() and not (out / "cat.pose").exists()
        assert (out / ".gitignore").read_text() == "*\n"
        assert "NON-COMMERCIAL USE ONLY" in (out / "ATTRIBUTION.txt").read_text()


def test_mirror_twice_is_the_identity():
    import numpy as np
    from pose_format import Pose

    from handedness import mirror, score

    pose = Pose.read(SAMPLE.read_bytes())
    before = np.asarray(pose.body.data.filled(0)).copy()
    side = score(pose)
    once = mirror(pose)
    flipped = score(once)
    assert flipped["dominant"] != side["dominant"]
    assert abs(flipped["presence"] - side["presence"]) < 1e-9
    twice = mirror(once)
    assert np.allclose(np.asarray(twice.body.data.filled(0)), before)


def _layer(root: Path, name: str, words, non_commercial=False, letters=()):
    layer = root / name
    layer.mkdir()
    for word in words:
        (layer / f"{word}.pose").write_bytes(f"{name}:{word}".encode())
    for char in letters:
        (layer / f"fs_{char}.pose").write_bytes(f"{name}:{char}".encode())
    (layer / "lexicon.json").write_text(json.dumps({"source": name, "license": f"{name} licence",
                                                    "non_commercial": non_commercial}))
    (layer / "ATTRIBUTION.txt").write_text(f"credit {name}")
    return layer


def test_layers_stack_best_first_and_any_non_commercial_layer_marks_the_whole():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        a = _layer(root, "ASL Citizen", ["dog", "you"], non_commercial=True)
        b = _layer(root, "PopSign", ["dog", "frog"])
        c = _layer(root, "Letters", [], letters="ab")
        out = root / "out"
        manifest = stack_lexicons.build([a, b, c], out)
        assert (out / "dog.pose").read_bytes() == b"ASL Citizen:dog"
        assert (out / "frog.pose").read_bytes() == b"PopSign:frog"
        assert (out / "fs_a.pose").exists()
        assert manifest["words_per_source"] == {"ASL Citizen": 2, "PopSign": 1, "Letters": 0}
        assert manifest["source"] == "ASL Citizen, PopSign, Letters"
        assert manifest["non_commercial"] and "Non-commercial" in manifest["license"]
        credit = (out / "ATTRIBUTION.txt").read_text()
        assert "credit ASL Citizen" in credit and "credit PopSign" in credit and "credit Letters" in credit
        assert (out / ".gitignore").read_text() == "*\n"


def test_layers_without_restricted_data_keep_their_licences():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        manifest = stack_lexicons.build([_layer(root, "PopSign", ["dog"])], root / "out")
        assert not manifest["non_commercial"]
        assert manifest["license"] == "PopSign licence"


def test_showcase_renders_each_tier_side_by_side():
    """Real renders, with text-to-gloss stubbed: two tiers made from the sample pose."""
    import cv2

    sys.path.insert(0, str(HERE.parent / "utils"))
    import generate_asl_video
    import run_showcase
    import tiers as tiering

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, words, restricted in [("small", ["dog"], False), ("big", ["dog", "cat"], True)]:
            folder = root / name
            folder.mkdir()
            for word in words:
                (folder / f"{word}.pose").write_bytes(SAMPLE.read_bytes())
            (folder / "lexicon.json").write_text(json.dumps({"source": name, "license": "test",
                                                            "non_commercial": restricted}))
        found = tiering.tiers(f"Small={root / 'small'};Big={root / 'big'};Gone={root / 'nothing'}")
        assert [t.name for t in found] == ["Small", "Big"]
        assert found[1].non_commercial and found[1].words == ["cat", "dog"]

        original = generate_asl_video.text_to_gloss
        generate_asl_video.text_to_gloss = lambda sentence: ["cat", "zebra"] if "zebra" in sentence else ["dog", "cat"]
        old_env = {k: os.environ.get(k) for k in ("ASLYTICS_WORK_DIR",)}
        os.environ["ASLYTICS_WORK_DIR"] = str(root / "work")
        try:
            report = run_showcase.run(["the dog and cat", "cat zebra"], found, root / "out")
        finally:
            generate_asl_video.text_to_gloss = original
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        small, big = report[0]["tiers"]
        assert small["signed"] == ["dog"] and small["skipped"] == ["cat"]
        assert big["signed"] == ["dog", "cat"] and big["skipped"] == []
        # "cat zebra": nothing at all for the small tier, which shows a blank panel.
        assert report[1]["tiers"][0]["video"] is None
        assert report[1]["tiers"][0]["skipped"] == ["cat", "zebra"]

        video = cv2.VideoCapture(str(root / "out" / report[0]["compare"]))
        width = video.get(cv2.CAP_PROP_FRAME_WIDTH)
        frames = video.get(cv2.CAP_PROP_FRAME_COUNT)
        video.release()
        assert width > 2 * 400 and frames > 30
        page = (root / "out" / "index.html").read_text()
        assert "compare_0.mp4" in page and "Non-commercial" in page
        totals = run_showcase.totals(report, found)
        assert totals["Big"] == {"signed": 3, "spelled": 0, "missing": 1, "words": 4}

        # A fluent signer's sentence becomes the first of three panels.
        natural = [{"sentence": "the dog", "source": "Flores", "gloss": "DOG",
                    "video": str(root / "out" / report[0]["compare"])}]
        generate_asl_video.text_to_gloss = lambda sentence: ["dog"]
        os.environ["ASLYTICS_WORK_DIR"] = str(root / "work")
        try:
            again = run_showcase.run([], found, root / "out2", natural)
        finally:
            generate_asl_video.text_to_gloss = original
            os.environ.pop("ASLYTICS_WORK_DIR", None)
        assert again[0]["natural"] == {"source": "Flores", "gloss": "DOG"}
        video = cv2.VideoCapture(str(root / "out2" / again[0]["compare"]))
        assert video.get(cv2.CAP_PROP_FRAME_WIDTH) > 3 * 400
        video.release()
        assert "their gloss: DOG" in (root / "out2" / "index.html").read_text()


def test_video_lexicon_takes_each_words_first_variant():
    import video_lexicon
    from pose_format import Pose

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        videos, poses, out = root / "videos", root / "pose", root / "out"
        videos.mkdir()
        poses.mkdir()
        for name in ["right__2", "right__1", "hello", "ice-cream", "cat"]:
            (videos / f"{name}.mp4").write_bytes(b"")
        assert [n for n, _ in video_lexicon.variants(videos)["right"]] == [1, 2]
        assert "ice" not in video_lexicon.variants(videos) and "ice-cream" not in video_lexicon.variants(videos)

        sample = Pose.read(SAMPLE.read_bytes())
        _write(sample, poses / "right__1.pose")
        _write(sample, poses / "hello.pose")
        unseen = Pose.read(SAMPLE.read_bytes())
        unseen.body.confidence[:, :, 136:] = 0
        _write(unseen, poses / "right__2.pose")      # a worse variant 2 must not be preferred or matter
        manifest = video_lexicon.export(videos, poses, out, "Test Source", "NC licence", "Credit line.",
                                        non_commercial=True)
        assert manifest["words"] == {"hello": "hello.mp4", "right": "right__1.mp4"}
        assert manifest["missing"] == ["cat"]
        assert manifest["picks"]["right"]["variant"] == 1 and manifest["picks"]["right"]["variants"] == 2
        assert manifest["non_commercial"] is True
        assert "NON-COMMERCIAL USE ONLY" in (out / "ATTRIBUTION.txt").read_text()
        assert (out / ".gitignore").read_text() == "*\n"



def test_citizen_converts_only_chosen_clips():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        (data / "videos").mkdir()
        (data / "pose").mkdir()
        for name in ("a.mp4", "b.mp4", "stray.mp4", "done.mp4"):
            (data / "videos" / name).write_bytes(b"x")
        (data / "pose" / "done.pose").write_bytes(b"x")
        todo = citizen.convert_todo(data, {"DOG": ["a.mp4", "done.mp4"], "CAT": ["b.mp4", "absent.mp4"]})
        assert sorted(s.name for s, _ in todo) == ["a.mp4", "b.mp4"]


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} passed")
