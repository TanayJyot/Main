"""Compare two .pose recordings of a sign: DTW distance and hand-level PCK.

HANDOFF.md task 4. The question it answers is narrow: is recording B the same
sign as recording A, performed by someone else? It does not answer whether a
Deaf viewer can read B. Only a signer can answer that.

Poses are compared directly as keypoints. Rendering to video and re-detecting
(tools/eval/pose_fidelity.py) is not used: MediaPipe finds no person in a
stick-figure render, so that path only ever yields NaN.

What is compared
----------------
Two things carry a sign's identity, and each is normalised so that who signed
it, where they stood and how big they are drop out:

  arms   shoulders, elbows, wrists. Centred on the shoulder midpoint and
         divided by shoulder width, so location and movement survive but
         body size and camera framing do not.
  hands  all 21 landmarks per hand, relative to that hand's wrist and divided
         by wrist-to-middle-knuckle length. This is the handshape, and it is
         normalised separately because a handshape error is tiny against
         shoulder width but decisive for meaning.

x and y only. MediaPipe's z is too noisy to help.

Timing is removed with dynamic time warping, so a slow and a fast
performance of the same sign align. Left-handed signers are handled by also
comparing against the mirror image and keeping the closer of the two; ASL
signs are mirror-equivalent between left- and right-dominant signers.

Hands are often absent (the old lexicon is missing each hand in 56-63% of
frames, mostly at rest). A hand missing in both frames contributes nothing.
A hand present in one and missing in the other costs a fixed penalty, since a
one-handed and a two-handed sign differ.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

ARM_POINTS = ["LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_ELBOW",
              "RIGHT_ELBOW", "LEFT_WRIST", "RIGHT_WRIST"]
# Index pairs to swap when mirroring the arm points above.
ARM_MIRROR = [1, 0, 3, 2, 5, 4]

HAND_WRIST, HAND_MIDDLE_MCP = 0, 9

# Cost when a hand is present in one frame and absent in the other, in the
# same normalised units as the distances (roughly: one hand-length).
HAND_PRESENCE_PENALTY = 1.0
# Relative weight of handshape against arm position in the frame distance.
HAND_WEIGHT = 1.0
ARM_WEIGHT = 1.0


@dataclass
class SignFeatures:
    """A sign as normalised per-frame features. Missing values are NaN."""

    arms: np.ndarray          # (T, 6, 2)
    left_hand: np.ndarray     # (T, 21, 2)
    right_hand: np.ndarray    # (T, 21, 2)
    fps: float = 25.0

    @property
    def frames(self) -> int:
        return self.arms.shape[0]

    def mirrored(self) -> "SignFeatures":
        """The same sign performed with the other dominant hand."""
        arms = self.arms[:, ARM_MIRROR].copy()
        arms[..., 0] *= -1
        left = self.right_hand.copy()
        right = self.left_hand.copy()
        left[..., 0] *= -1
        right[..., 0] *= -1
        return SignFeatures(arms, left, right, self.fps)


# -- from raw keypoints ----------------------------------------------------------

def _nan_where_missing(points: np.ndarray, confidence: np.ndarray) -> np.ndarray:
    out = points.astype(float).copy()
    missing = (confidence <= 0) | ~np.isfinite(out).all(axis=-1) | (np.abs(out).sum(axis=-1) == 0)
    out[missing] = np.nan
    return out


def normalise(arms: np.ndarray, left_hand: np.ndarray, right_hand: np.ndarray,
              fps: float = 25.0, trim: bool = True) -> SignFeatures:
    """Normalise raw (T, P, 2) pixel keypoints, NaN where missing."""
    arms = np.asarray(arms, float)[..., :2]
    left_hand = np.asarray(left_hand, float)[..., :2]
    right_hand = np.asarray(right_hand, float)[..., :2]

    centre = (arms[:, 0] + arms[:, 1]) / 2                       # (T, 2)
    widths = np.linalg.norm(arms[:, 0] - arms[:, 1], axis=-1)
    widths = widths[np.isfinite(widths) & (widths > 0)]
    scale = float(np.median(widths)) if widths.size else np.nan
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("no frame with both shoulders visible; cannot normalise")

    norm_arms = (arms - centre[:, None, :]) / scale

    def hand_local(hand: np.ndarray) -> np.ndarray:
        wrist = hand[:, HAND_WRIST:HAND_WRIST + 1]
        size = np.linalg.norm(hand[:, HAND_MIDDLE_MCP] - hand[:, HAND_WRIST], axis=-1)
        size = np.where(size > 0, size, np.nan)
        return (hand - wrist) / size[:, None, None]

    features = SignFeatures(norm_arms, hand_local(left_hand), hand_local(right_hand), fps)
    return trim_to_signing(features) if trim else features


def trim_to_signing(features: SignFeatures) -> SignFeatures:
    """Drop leading and trailing frames where neither hand is visible.

    Recordings pad the sign with the signer standing at rest, and the amount
    of padding varies by source. Left in, it dominates the distance between
    two clips that sign identically.
    """
    present = (_hand_present(features.left_hand) | _hand_present(features.right_hand))
    if not present.any():
        return features
    first, last = int(np.argmax(present)), len(present) - int(np.argmax(present[::-1]))
    return SignFeatures(features.arms[first:last], features.left_hand[first:last],
                        features.right_hand[first:last], features.fps)


def _hand_present(hand: np.ndarray) -> np.ndarray:
    return np.isfinite(hand).all(axis=-1).any(axis=-1)


# -- distances -----------------------------------------------------------------

def _pointset_distance(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Mean point distance between every frame of a and every frame of b.

    a: (Ta, P, 2), b: (Tb, P, 2) -> (Ta, Tb), NaN where no point is valid in both.
    """
    diff = a[:, None] - b[None, :]                               # (Ta, Tb, P, 2)
    dist = np.sqrt((diff ** 2).sum(-1))                          # (Ta, Tb, P)
    # Pairs of frames with no point valid in both are NaN, and nanmean warns
    # about each one. That is expected here, not a problem to report.
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(dist, axis=-1)


def _hand_cost(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    present_a, present_b = _hand_present(a), _hand_present(b)
    both = present_a[:, None] & present_b[None, :]
    one = present_a[:, None] ^ present_b[None, :]

    cost = np.zeros((len(a), len(b)))
    if both.any():
        with np.errstate(invalid="ignore", all="ignore"):
            shape = _pointset_distance(a, b)
        cost = np.where(both, np.nan_to_num(shape, nan=HAND_PRESENCE_PENALTY), cost)
    cost = np.where(one, HAND_PRESENCE_PENALTY, cost)
    return cost


def frame_costs(a: SignFeatures, b: SignFeatures) -> np.ndarray:
    """(Ta, Tb) matrix of per-frame distances."""
    with np.errstate(invalid="ignore", all="ignore"):
        arms = _pointset_distance(a.arms, b.arms)
    arms = np.nan_to_num(arms, nan=HAND_PRESENCE_PENALTY)
    hands = (_hand_cost(a.left_hand, b.left_hand) + _hand_cost(a.right_hand, b.right_hand)) / 2
    return (ARM_WEIGHT * arms + HAND_WEIGHT * hands) / (ARM_WEIGHT + HAND_WEIGHT)


def dtw(cost: np.ndarray, band: Optional[float] = None) -> Tuple[float, List[Tuple[int, int]]]:
    """Dynamic time warping over a precomputed cost matrix.

    Returns (mean cost along the optimal path, path). Averaging over the path
    rather than summing keeps long and short signs on the same scale.

    `band`, if given, is a Sakoe-Chiba constraint as a fraction of the longer
    sequence: it stops DTW from matching the whole of one sign to a single
    frame of the other, which otherwise lets unrelated signs look close.
    """
    n, m = cost.shape
    if n == 0 or m == 0:
        return float("inf"), []

    acc = np.full((n + 1, m + 1), np.inf)
    acc[0, 0] = 0.0
    width = None if band is None else max(int(np.ceil(band * max(n, m))), abs(n - m) + 1)

    for i in range(1, n + 1):
        lo, hi = 1, m
        if width is not None:
            centre = int(round(i * m / n))
            lo, hi = max(1, centre - width), min(m, centre + width)
        for j in range(lo, hi + 1):
            acc[i, j] = cost[i - 1, j - 1] + min(acc[i - 1, j], acc[i, j - 1], acc[i - 1, j - 1])

    path, i, j = [], n, m
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        moves = [(acc[i - 1, j - 1], i - 1, j - 1), (acc[i - 1, j], i - 1, j), (acc[i, j - 1], i, j - 1)]
        _, i, j = min(moves, key=lambda move: move[0])
    path.reverse()
    return float(acc[n, m] / len(path)), path


def hand_pck(a: SignFeatures, b: SignFeatures, path: Sequence[Tuple[int, int]],
             threshold: float = 0.2) -> Dict[str, float]:
    """Handshape agreement along an aligned path.

    Fraction of hand landmarks within `threshold` hand-lengths of their
    counterpart, over aligned frame pairs where the hand is present in both.
    NaN when the hand is never present in both, which is reported as "not
    measured" and is not the same as zero.
    """
    out = {}
    for name in ("left_hand", "right_hand"):
        hand_a, hand_b = getattr(a, name), getattr(b, name)
        hits, total = 0, 0
        for i, j in path:
            pa, pb = hand_a[i], hand_b[j]
            valid = np.isfinite(pa).all(-1) & np.isfinite(pb).all(-1)
            if not valid.any():
                continue
            dist = np.linalg.norm(pa[valid] - pb[valid], axis=-1)
            hits += int((dist <= threshold).sum())
            total += int(valid.sum())
        out[f"{name}_pck"] = hits / total if total else float("nan")
    return out


@dataclass
class Comparison:
    distance: float
    mirrored: bool
    left_hand_pck: float
    right_hand_pck: float
    path_length: int


def compare(a: SignFeatures, b: SignFeatures, band: Optional[float] = 0.5,
            mirror_invariant: bool = True) -> Comparison:
    """Distance between two signs, taking the better of B and B-mirrored."""
    candidates = [(False, b)] + ([(True, b.mirrored())] if mirror_invariant else [])
    best = None
    for mirrored, other in candidates:
        distance, path = dtw(frame_costs(a, other), band)
        if best is None or distance < best[0]:
            best = (distance, mirrored, other, path)
    distance, mirrored, other, path = best
    pck = hand_pck(a, other, path)
    return Comparison(distance, mirrored, pck["left_hand_pck"], pck["right_hand_pck"], len(path))


# -- loading real .pose files ------------------------------------------------------

def features_from_pose(pose, trim: bool = True) -> SignFeatures:
    """Build SignFeatures from a pose_format Pose, by landmark name."""
    offsets, names = {}, {}
    offset = 0
    for component in pose.header.components:
        offsets[component.name] = offset
        names[component.name] = list(component.points)
        offset += len(component.points)

    data = np.asarray(pose.body.data)[:, 0]              # (T, points, dims)
    confidence = np.asarray(pose.body.confidence)[:, 0]  # (T, points)

    def take(component: str, wanted: Optional[List[str]] = None) -> np.ndarray:
        if component not in offsets:
            count = len(wanted) if wanted else 21
            return np.full((data.shape[0], count, 2), np.nan)
        base = offsets[component]
        indices = ([base + names[component].index(point) for point in wanted]
                   if wanted else list(range(base, base + len(names[component]))))
        return _nan_where_missing(data[:, indices, :2], confidence[:, indices])

    return normalise(take("POSE_LANDMARKS", ARM_POINTS),
                     take("LEFT_HAND_LANDMARKS"), take("RIGHT_HAND_LANDMARKS"),
                     float(pose.body.fps or 25.0), trim=trim)


def load_features(path: str, trim: bool = True) -> SignFeatures:
    from pose_format import Pose

    with open(path, "rb") as handle:
        return features_from_pose(Pose.read(handle.read()), trim=trim)
