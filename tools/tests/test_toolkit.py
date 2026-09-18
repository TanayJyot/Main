"""
Tests for the corpus and eval tooling.

Runs standalone (`python tools/tests/test_toolkit.py`) so it works without
pytest installed, and under pytest if it is. Needs only numpy, opencv and
Pillow — not mediapipe, torch or a GPU, which is the point of keeping the
geometry and metric code as pure functions.
"""

from __future__ import annotations

import os
import sys
import tempfile
import zipfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "corpus"))
sys.path.insert(0, os.path.join(HERE, "..", "eval"))

import clean_to_images  # noqa: E402
import filter_candidates as fc  # noqa: E402
import metrics  # noqa: E402
from provenance import LicenceError, Manifest, Record, check_optout, now_iso  # noqa: E402


# --------------------------------------------------------------------------
# provenance: the licence gate

def test_disallowed_sources_are_refused():
    for source in ("pexels", "shhq"):
        record = Record(image_id=f"x-{source}", source=source, source_url="http://example.test",
                        licence="whatever", retrieved_at=now_iso())
        try:
            record.validate()
        except LicenceError:
            continue
        raise AssertionError(f"{source} should have been refused")


def test_unknown_source_is_refused():
    record = Record(image_id="x", source="some-scraper", source_url="http://example.test",
                    licence="unknown", retrieved_at=now_iso())
    try:
        record.validate()
        raise AssertionError("unknown source should be refused")
    except LicenceError as error:
        assert "unknown source" in str(error)


def test_flickr_licence_allowlist():
    def make(licence):
        return Record(image_id="f", source="flickr", source_url="http://example.test",
                      licence=licence, retrieved_at=now_iso())

    make("cc0").validate()
    make("CC-BY-4.0").validate()  # case insensitive
    try:
        make("cc-by-nc-4.0").validate()
        raise AssertionError("non-commercial Flickr licence should be refused")
    except LicenceError:
        pass


def test_pixabay_needs_optout_check_before_training():
    record = Record(image_id="p1", source="pixabay", source_url="http://example.test",
                    licence="pixabay-content-license", retrieved_at=now_iso())
    record.validate()  # allowed as a record
    assert not record.is_training_ready(), "unknown opt-out must block training"

    record.ai_training_optout = "clear"
    assert record.is_training_ready()

    record.ai_training_optout = "opted-out"
    try:
        record.validate()
        raise AssertionError("an opted-out contributor must be refused outright")
    except LicenceError:
        pass


def test_manifest_roundtrip_and_queue():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "prov.jsonl")
        manifest = Manifest(path)
        manifest.add(Record(image_id="p1", source="pixabay", source_url="u",
                            licence="pixabay-content-license", retrieved_at=now_iso()))
        manifest.add(Record(image_id="p2", source="own-recording", source_url="u",
                            licence="commercial-release", retrieved_at=now_iso()))

        reloaded = Manifest(path)
        assert len(reloaded) == 2
        assert "p1" in reloaded and reloaded.get("p2").source == "own-recording"
        assert check_optout(reloaded) == ["p1"]
        summary = reloaded.summary()
        assert summary["total"] == 2 and summary["pending_checks"] == 1


# --------------------------------------------------------------------------
# filter_candidates: geometry predicates

def make_landmarks(shoulder_dx=0.25, shoulder_dy=0.0, shoulder_dz=0.0,
                   head_y=0.05, ankle_y=0.95, visibility=0.9) -> np.ndarray:
    """A synthetic, upright, frontal figure that we then perturb per test."""
    landmarks = np.zeros((33, 4), dtype=float)
    landmarks[:, 3] = visibility
    landmarks[fc.NOSE] = [0.5, head_y, 0.0, visibility]
    landmarks[fc.L_SHOULDER] = [0.5 - shoulder_dx / 2, 0.25, 0.0, visibility]
    landmarks[fc.R_SHOULDER] = [0.5 + shoulder_dx / 2, 0.25 + shoulder_dy, shoulder_dz, visibility]
    landmarks[fc.L_HIP] = [0.45, 0.55, 0.0, visibility]
    landmarks[fc.R_HIP] = [0.55, 0.55, 0.0, visibility]
    landmarks[fc.L_KNEE] = [0.45, 0.75, 0.0, visibility]
    landmarks[fc.R_KNEE] = [0.55, 0.75, 0.0, visibility]
    landmarks[fc.L_ANKLE] = [0.45, ankle_y, 0.0, visibility]
    landmarks[fc.R_ANKLE] = [0.55, ankle_y, 0.0, visibility]
    return landmarks


def test_clean_figure_is_accepted():
    accepted, reasons = fc.evaluate(make_landmarks())
    assert accepted, reasons


def test_profile_is_rejected():
    accepted, reasons = fc.evaluate(make_landmarks(shoulder_dx=0.04))
    assert not accepted and "not frontal" in reasons


def test_turned_torso_is_rejected():
    # Shoulders far apart but at very different depths: someone facing away.
    accepted, reasons = fc.evaluate(make_landmarks(shoulder_dz=0.5))
    assert not accepted and "not frontal" in reasons


def test_occluded_legs_are_rejected():
    landmarks = make_landmarks()
    landmarks[fc.L_ANKLE, 3] = 0.1
    accepted, reasons = fc.evaluate(landmarks)
    assert not accepted and "not full body" in reasons


def test_distant_subject_is_rejected():
    accepted, reasons = fc.evaluate(make_landmarks(head_y=0.40, ankle_y=0.60))
    assert not accepted and "subject too small in frame" in reasons


def test_upside_down_is_rejected():
    landmarks = make_landmarks()
    landmarks[[fc.L_SHOULDER, fc.R_SHOULDER], 1] = 0.9  # shoulders below ankles
    accepted, reasons = fc.evaluate(landmarks)
    assert not accepted and "not upright" in reasons


# --------------------------------------------------------------------------
# metrics

def test_pck_and_mpjpe_on_known_offsets():
    # Kept off the origin: (0, 0) is the missing-point sentinel, see below.
    target = np.array([[1.0, 1.0], [11.0, 1.0], [1.0, 11.0], [11.0, 11.0]])
    predicted = target + np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 5.0], [0.0, 0.0]])

    # scale 10, threshold 0.2 -> 2.0 units. Three of four points are within it.
    assert abs(metrics.pck(predicted, target, scale=10.0, threshold=0.2) - 0.75) < 1e-9
    # distances 0, 1, 5, 0 -> mean 1.5, normalised by 10.
    assert abs(metrics.mpjpe(predicted, target, scale=10.0) - 0.15) < 1e-9


def test_origin_points_are_treated_as_missing():
    """MediaPipe and pose_format both write (0, 0) for a landmark they did not
    find, so the metrics must not score it as a real point at the origin. The
    cost is that a genuine landmark exactly at (0, 0) is dropped — acceptable,
    since that is the image corner."""
    target = np.array([[0.0, 0.0], [11.0, 1.0]])
    predicted = np.array([[0.0, 0.0], [11.0, 1.0]])
    # Only the second point is scored, and it matches exactly.
    assert metrics.pck(predicted, target, scale=10.0) == 1.0
    assert metrics.mpjpe(predicted, target, scale=10.0) == 0.0

    # A wrong prediction on the one real point is still caught.
    off = np.array([[0.0, 0.0], [31.0, 1.0]])
    assert metrics.pck(off, target, scale=10.0) == 0.0


def test_metrics_report_not_measured_rather_than_zero():
    empty = np.zeros((4, 2))
    assert np.isnan(metrics.pck(empty, empty, scale=10.0))
    assert np.isnan(metrics.mpjpe(empty, empty, scale=10.0))


def test_hand_scale_is_independent_of_body_scale():
    """The reason hands get their own normaliser."""
    hand = np.zeros((21, 3))
    hand[metrics.HAND_WRIST] = [0, 0, 0]
    hand[metrics.HAND_MIDDLE_MCP] = [0, 8, 0]
    assert abs(metrics.hand_scale(hand) - 8.0) < 1e-9

    pose = np.zeros((33, 3))
    pose[metrics.POSE_L_SHOULDER] = [0, 0, 0]
    pose[metrics.POSE_R_SHOULDER] = [100, 0, 0]
    assert abs(metrics.shoulder_scale(pose) - 100.0) < 1e-9

    # A 4px finger error is 50% of hand scale but 4% of shoulder scale: scoring
    # hands against the body scale would hide it entirely.
    moved = hand.copy()
    moved[metrics.HAND_MIDDLE_MCP] += [4, 0, 0]
    by_hand = metrics.pck(moved[:, :2], hand[:, :2], metrics.hand_scale(hand), threshold=0.2)
    by_body = metrics.pck(moved[:, :2], hand[:, :2], metrics.shoulder_scale(pose), threshold=0.2)
    assert by_hand < by_body


def test_ssim_and_psnr_on_identical_images():
    rng = np.random.default_rng(0)
    image = rng.integers(0, 255, size=(48, 48), dtype=np.uint8).astype(float)
    assert abs(metrics.ssim(image, image) - 1.0) < 1e-6
    assert metrics.psnr(image, image) == float("inf")


def test_ssim_drops_on_noise():
    rng = np.random.default_rng(1)
    image = rng.integers(0, 255, size=(48, 48), dtype=np.uint8).astype(float)
    noisy = np.clip(image + rng.normal(0, 40, image.shape), 0, 255)
    assert metrics.ssim(image, noisy) < 0.9


def test_regression_report_respects_metric_direction():
    baseline = {"left_hand_pck": 0.80, "body_mpjpe": 0.10}
    # PCK fell (worse) and MPJPE fell (better).
    candidate = {"left_hand_pck": 0.70, "body_mpjpe": 0.05}
    report = metrics.regression_report(baseline, candidate, {"left_hand_pck": 0.02})
    assert report["left_hand_pck"]["verdict"] == "REGRESSED"
    assert report["body_mpjpe"]["verdict"] == "ok"

    within = metrics.regression_report(baseline, {"left_hand_pck": 0.79}, {"left_hand_pck": 0.02})
    assert within["left_hand_pck"]["verdict"] == "ok"


def test_temporal_flicker_is_zero_for_a_still_sequence():
    frame = np.full((16, 16, 3), 128, dtype=np.uint8)
    assert metrics.temporal_flicker([frame, frame, frame]) == 0.0


# --------------------------------------------------------------------------
# clean_to_images: the archive builder

def _write_corpus(tmp, count=3, with_records=True, source="own-recording"):
    import cv2

    img_dir, seg_dir = os.path.join(tmp, "raw"), os.path.join(tmp, "masks")
    os.makedirs(img_dir), os.makedirs(seg_dir)
    manifest = Manifest(os.path.join(tmp, "prov.jsonl"))

    for i in range(count):
        name = f"img-{i}.png"
        image = np.full((200, 100, 3), 200, dtype=np.uint8)
        mask = np.zeros((200, 100, 3), dtype=np.uint8)
        mask[40:160, 25:75] = 255  # a blob standing in for a person
        cv2.imwrite(os.path.join(img_dir, name), image)
        cv2.imwrite(os.path.join(seg_dir, name), mask)
        if with_records:
            manifest.add(Record(image_id=f"img-{i}", source=source, source_url="u",
                                licence="commercial-release" if source == "own-recording" else "pixabay-content-license",
                                retrieved_at=now_iso()))
    return img_dir, seg_dir, manifest.path


def test_archive_is_built_with_upstream_naming():
    with tempfile.TemporaryDirectory() as tmp:
        img_dir, seg_dir, manifest_path = _write_corpus(tmp, count=3)
        out = os.path.join(tmp, "frames.zip")
        report = clean_to_images.build(img_dir, seg_dir, manifest_path, out,
                                       resolution=64, prefix="sshq")

        assert report["images_written"] == 3
        with zipfile.ZipFile(out) as archive:
            names = sorted(archive.namelist())
            assert names[0] == "sshq00000/img00000000.png"
            assert len(names) == 3
            # Stored uncompressed, as upstream does.
            assert all(info.compress_type == zipfile.ZIP_STORED for info in archive.infolist())
        assert os.path.exists(os.path.join(tmp, "frames.provenance.json"))


def test_build_processes_every_image_not_just_two():
    """Upstream's islice(files, 0, 2) is the bug this guards against."""
    with tempfile.TemporaryDirectory() as tmp:
        img_dir, seg_dir, manifest_path = _write_corpus(tmp, count=5)
        report = clean_to_images.build(img_dir, seg_dir, manifest_path,
                                       os.path.join(tmp, "frames.zip"), resolution=32)
        assert report["images_written"] == 5, "all five images must reach the archive"


def test_build_refuses_images_without_provenance():
    with tempfile.TemporaryDirectory() as tmp:
        img_dir, seg_dir, manifest_path = _write_corpus(tmp, count=2, with_records=False)
        open(manifest_path, "a").close()
        try:
            clean_to_images.build(img_dir, seg_dir, manifest_path, os.path.join(tmp, "f.zip"))
            raise AssertionError("must refuse images with no provenance record")
        except LicenceError as error:
            assert "no provenance record" in str(error)


def test_build_refuses_pending_optout_unless_overridden():
    with tempfile.TemporaryDirectory() as tmp:
        img_dir, seg_dir, manifest_path = _write_corpus(tmp, count=2, source="pixabay")
        try:
            clean_to_images.build(img_dir, seg_dir, manifest_path, os.path.join(tmp, "f.zip"))
            raise AssertionError("must refuse unverified opt-out status")
        except LicenceError as error:
            assert "opt-out" in str(error)

        report = clean_to_images.build(img_dir, seg_dir, manifest_path,
                                       os.path.join(tmp, "f.zip"), resolution=32,
                                       allow_unverified_optout=True)
        assert report["images_written"] == 2


def test_compositing_keys_the_background_green():
    import cv2

    raw = np.full((40, 40, 3), 255, dtype=np.uint8)
    seg = np.zeros((40, 40, 3), dtype=np.uint8)
    seg[10:30, 10:30] = 255

    out = clean_to_images.remove_background(seg, raw)
    corner = out[0, 0]  # BGR, far from the blur radius of the subject
    assert corner[1] > corner[0] and corner[1] > corner[2], f"corner should be green, got {corner}"
    assert out.shape == raw.shape and out.dtype == np.uint8


def test_mask_shape_mismatch_is_caught():
    with tempfile.TemporaryDirectory() as tmp:
        import cv2
        img_dir, seg_dir, manifest_path = _write_corpus(tmp, count=1)
        # Overwrite the mask with a differently sized one.
        cv2.imwrite(os.path.join(seg_dir, "img-0.png"), np.zeros((50, 50, 3), dtype=np.uint8))
        try:
            clean_to_images.build(img_dir, seg_dir, manifest_path, os.path.join(tmp, "f.zip"))
            raise AssertionError("mismatched mask should raise")
        except ValueError as error:
            assert "does not match" in str(error)


def main() -> int:
    tests = [(name, value) for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    failures = []
    for name, test in tests:
        try:
            test()
            print(f"  ok    {name}")
        except Exception as error:  # noqa: BLE001 - this is the test reporter
            failures.append((name, error))
            print(f"  FAIL  {name}: {error}")

    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
