"""Tests for pose_compare.py and stats.py. Run: python analysis/eval/test_pose_compare.py

Synthetic arrays only; no .pose files or pose_format needed.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import pose_compare as pc  # noqa: E402
import stats  # noqa: E402

RNG = np.random.default_rng(0)


def raw_sign(frames=30, seed=0, hands=True, offset=(300.0, 200.0), scale=100.0):
    """Raw pixel keypoints for a made-up sign: arms move, hands change shape."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 1, frames)
    arms = np.zeros((frames, 6, 2))
    arms[:, 0] = [-1, 0]; arms[:, 1] = [1, 0]                      # shoulders
    arms[:, 2] = [-1.2, 1]; arms[:, 3] = [1.2, 1]                  # elbows
    path = rng.normal(0, 0.6, (2, 2))
    arms[:, 4] = np.stack([-0.8 + path[0, 0] * t, 0.5 + path[0, 1] * np.sin(3 * t)], -1)
    arms[:, 5] = np.stack([0.8 + path[1, 0] * t, 0.5 + path[1, 1] * np.cos(3 * t)], -1)
    shape = rng.normal(0, 1, (21, 2)); shape[0] = 0; shape[9] = [0, 1]
    bend = rng.normal(0, 0.3, (21, 2)); bend[0] = 0; bend[9] = 0
    hand = shape[None] + bend[None] * t[:, None, None]
    left, right = hand * 0.3, hand * 0.3
    if not hands:
        left = right = np.full_like(hand, np.nan)
    to_px = lambda a: a * scale + np.asarray(offset)
    return to_px(arms), to_px(left), to_px(right)


def feats(**kwargs):
    return pc.normalise(*raw_sign(**kwargs), trim=False)


def test_identical_signs_have_zero_distance():
    a = feats(seed=1)
    assert pc.compare(a, a).distance < 1e-9


def test_position_and_scale_do_not_matter():
    """Who signed it and where they stood must drop out."""
    a = feats(seed=1)
    b = feats(seed=1, offset=(900.0, 50.0), scale=240.0)
    assert pc.compare(a, b).distance < 1e-6


def test_speed_does_not_matter_much():
    a = feats(seed=1, frames=30)
    b = feats(seed=1, frames=55)
    different = feats(seed=7, frames=30)
    assert pc.compare(a, b).distance < 0.25 * pc.compare(a, different).distance


def test_mirror_image_is_the_same_sign():
    a = feats(seed=2)
    assert pc.compare(a, a.mirrored()).distance < 1e-9
    assert pc.compare(a, a.mirrored()).mirrored


def test_mirror_invariance_can_be_turned_off():
    a = feats(seed=2)
    assert pc.compare(a, a.mirrored(), mirror_invariant=False).distance > 0.01


def test_different_signs_are_further_apart_than_same():
    a, b = feats(seed=3), feats(seed=4)
    assert pc.compare(a, b).distance > 0.05


def test_missing_hand_in_one_sign_is_penalised():
    a, b = feats(seed=5), feats(seed=5, hands=False)
    assert pc.compare(a, b).distance >= pc.HAND_PRESENCE_PENALTY * 0.4


def test_hands_missing_in_both_do_not_count_against():
    a, b = feats(seed=5, hands=False), feats(seed=5, hands=False)
    assert pc.compare(a, b).distance < 1e-9


def test_trim_drops_rest_frames_without_hands():
    arms, left, right = raw_sign(frames=20, seed=6)
    left[:5] = np.nan; right[:5] = np.nan; left[-3:] = np.nan; right[-3:] = np.nan
    trimmed = pc.normalise(arms, left, right, trim=True)
    assert trimmed.frames == 12


def test_hand_pck_is_one_for_identical_and_nan_when_unmeasured():
    a = feats(seed=8)
    _, path = pc.dtw(pc.frame_costs(a, a))
    assert pc.hand_pck(a, a, path)["left_hand_pck"] == 1.0
    empty = feats(seed=8, hands=False)
    _, path = pc.dtw(pc.frame_costs(empty, empty))
    assert np.isnan(pc.hand_pck(empty, empty, path)["left_hand_pck"])


def test_dtw_band_keeps_path_near_diagonal():
    cost = RNG.random((40, 40))
    _, path = pc.dtw(cost, band=0.1)
    assert max(abs(i - j) for i, j in path) <= 4 + 1


def test_normalise_rejects_clip_without_shoulders():
    arms, left, right = raw_sign()
    arms[:, :2] = np.nan
    try:
        pc.normalise(arms, left, right); raise AssertionError("should have raised")
    except ValueError:
        pass


def test_auc_extremes():
    assert stats.separation_auc([0.1, 0.2], [0.8, 0.9]) == 1.0
    assert stats.separation_auc([0.8, 0.9], [0.1, 0.2]) == 0.0
    assert stats.separation_auc([0.5], [0.5]) == 0.5


def test_bootstrap_interval_contains_estimate_and_ignores_nan():
    ci = stats.bootstrap_ci([1.0, 2.0, 3.0, float("nan"), 4.0])
    assert ci["n"] == 4 and ci["low"] <= ci["estimate"] <= ci["high"]


def test_top_k():
    d = {"a": 0.1, "b": 0.2, "c": 0.3}
    assert stats.top_k_hit(d, {"b"}, 2) and not stats.top_k_hit(d, {"c"}, 2)


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
