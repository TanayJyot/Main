"""concatenate.py with signs recorded at different frame rates.

concatenate_poses() used to join frames and play them at the first pose's
fps, so a 120 fps sign next to a 30 fps one lasted 4x its real length (a third
of PopSign is 120 fps). These use the repository's fixture pose, not the
lexicon.

    python tools/tests/test_concatenate_fps.py
"""

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pose-master" / "pose-master" / "concatenate_pose_function"))
os.environ.setdefault("ASLYTICS_LEXICON_DIR", str(REPO))  # not used; keeps import quiet

import concatenate  # noqa: E402
from pose_format import Pose  # noqa: E402

FIXTURE = REPO / "pose-master" / "pose-master" / "src" / "python" / "tests" / "data" / "mediapipe.pose"


def fixture(fps_factor: float = 1.0) -> Pose:
    """The fixture, relabelled as recorded fps_factor times faster: same frames,
    so its real duration shrinks by that factor."""
    pose = Pose.read(FIXTURE.read_bytes())
    pose.body.fps = float(pose.body.fps) * fps_factor
    return pose


def seconds(pose: Pose) -> float:
    return len(pose.body.data) / float(pose.body.fps)


def test_match_frame_rates_keeps_each_duration():
    slow, fast = fixture(), fixture(4.0)
    matched = concatenate.match_frame_rates([slow, fast])
    assert len({round(float(p.body.fps), 3) for p in matched}) == 1
    for before, after in zip([fixture(), fixture(4.0)], matched):
        assert abs(seconds(after) - seconds(before)) < 2 / float(after.body.fps), (seconds(before), seconds(after))


def test_concatenated_length_is_the_sum_not_stretched():
    poses = [fixture(), fixture(4.0)]
    expected = sum(seconds(p) for p in [fixture(), fixture(4.0)])
    out = concatenate.concatenate_poses(poses, trim=False)
    # Smoothing blends the seam, so allow a little slack; the bug was +3x.
    assert abs(seconds(out) - expected) < 0.25 * expected, (seconds(out), expected)


def test_same_rate_is_untouched():
    poses = [fixture(), fixture()]
    matched = concatenate.match_frame_rates(poses)
    assert all(a is b for a, b in zip(poses, matched))


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
