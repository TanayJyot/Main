"""Cut a sign clip down to the signing, and measure how well its hands were seen.

The renderer's own trim (concatenate.trim_pose) keeps frames where a wrist is
above its elbow. That suits the old lexicon, where signers start and end with
hands down. PopSign signers record a selfie with the phone in one hand and
keep the signing hand raised for the whole clip, so that trim removes nothing:
a sign that takes one second stays a six-second clip, and a six-word sentence
became a 28-second video.

This trims by motion instead: keep the stretch where the hands move. It looks
only at the clip itself, never at another lexicon.

    activity(t) = the larger of
                  - the faster wrist's speed, in shoulder widths per second
                  - how fast either hand's shape changes (fingers relative to
                    wrist, in hand lengths per second)

Frames where the smoothed activity is above a fraction of the clip's own
high-activity level count as active. Gaps shorter than MERGE_GAP are joined;
the longest active stretch is kept, padded by PAD at each end. If nothing
sensible is found, the clip is returned whole.
"""

from __future__ import annotations

import warnings
from typing import Dict, Optional, Tuple

import numpy as np

SMOOTH_SECONDS = 0.2    # moving-average window for activity
THRESHOLD = 0.25        # fraction of the clip's 90th-percentile activity
MERGE_GAP = 0.3         # seconds: stiller moments inside one sign
PAD = 0.15              # seconds kept before and after the active stretch
MIN_SECONDS = 0.4       # never cut a sign shorter than this


def _component_offsets(header) -> Dict[str, Tuple[int, int]]:
    offsets, start = {}, 0
    for component in header.components:
        offsets[component.name] = (start, start + len(component.points))
        start += len(component.points)
    return offsets


def _points(pose, component: str, names=None):
    """(frames, points, 2) positions with NaN where undetected, for person 0."""
    offsets = _component_offsets(pose.header)
    if component not in offsets:
        return None
    lo, hi = offsets[component]
    comp = next(c for c in pose.header.components if c.name == component)
    index = [lo + comp.points.index(n) for n in names] if names else list(range(lo, hi))
    xy = np.asarray(pose.body.data[:, 0, index, :2].filled(np.nan), dtype=float)
    conf = np.asarray(pose.body.confidence[:, 0, index], dtype=float)
    xy[conf <= 0] = np.nan
    # (0, 0) is how some converters write a missing point.
    xy[np.all(xy == 0, axis=-1)] = np.nan
    return xy


def _speed(xy: np.ndarray, fps: float) -> np.ndarray:
    """Per-frame speed of each point, NaN-safe; returns (frames,) max over points."""
    step = np.linalg.norm(np.diff(xy, axis=0), axis=-1) * fps
    with np.errstate(all="ignore"):
        per_frame = np.nanmax(np.where(np.isnan(step), -np.inf, step), axis=1)
    per_frame[~np.isfinite(per_frame)] = 0.0
    return np.concatenate([[0.0], per_frame])


def activity(pose) -> np.ndarray:
    """How much the hands are signing in each frame, scale-free."""
    with warnings.catch_warnings():
        # A hand that is never detected gives all-NaN medians; handled below.
        warnings.simplefilter("ignore", RuntimeWarning)
        return _activity(pose)


def _activity(pose) -> np.ndarray:
    fps = float(pose.body.fps) or 30.0
    frames = pose.body.data.shape[0]

    body = _points(pose, "POSE_LANDMARKS",
                   ["LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_WRIST", "RIGHT_WRIST"])
    shoulder = np.nanmedian(np.linalg.norm(body[:, 0] - body[:, 1], axis=-1)) if body is not None else np.nan
    if not np.isfinite(shoulder) or shoulder <= 0:
        shoulder = 1.0
    wrists = _speed(body[:, 2:] / shoulder, fps) if body is not None else np.zeros(frames)

    shape = np.zeros(frames)
    for hand in ("LEFT_HAND_LANDMARKS", "RIGHT_HAND_LANDMARKS"):
        xy = _points(pose, hand)
        if xy is None:
            continue
        relative = xy - xy[:, :1]                                  # fingers relative to wrist
        length = np.nanmedian(np.linalg.norm(xy[:, 9] - xy[:, 0], axis=-1))   # wrist -> middle MCP
        if not np.isfinite(length) or length <= 0:
            continue
        shape = np.maximum(shape, _speed(relative / length, fps) * 0.25)  # hand lengths are ~1/4 shoulder

    raw = np.maximum(wrists, shape)
    window = max(1, int(round(SMOOTH_SECONDS * fps)))
    return np.convolve(raw, np.ones(window) / window, mode="same")


def signing_window(pose) -> Optional[Tuple[int, int]]:
    """(start, end) frames of the signing, or None to keep the clip whole."""
    frames = pose.body.data.shape[0]
    fps = float(pose.body.fps) or 30.0
    if frames < 3:
        return None
    level = activity(pose)
    high = np.quantile(level, 0.9)
    if high <= 0:
        return None
    active = level > THRESHOLD * high

    # Runs of active frames, joining gaps shorter than MERGE_GAP.
    runs, start, gap = [], None, int(round(MERGE_GAP * fps))
    for t, on in enumerate(active):
        if on and start is None:
            start = t
        elif not on and start is not None:
            runs.append([start, t])
            start = None
    if start is not None:
        runs.append([start, frames])
    if not runs:
        return None
    merged = [runs[0]]
    for s, e in runs[1:]:
        if s - merged[-1][1] <= gap:
            merged[-1][1] = e
        else:
            merged.append([s, e])

    s, e = max(merged, key=lambda run: run[1] - run[0])
    pad = int(round(PAD * fps))
    s, e = max(0, s - pad), min(frames, e + pad)
    shortest = int(round(MIN_SECONDS * fps))
    if e - s < shortest:
        middle = (s + e) // 2
        s, e = max(0, middle - shortest // 2), min(frames, middle + shortest // 2)
    return s, e


def trim_to_signing(pose):
    """The pose cut to its signing window, in place; returns (pose, before, after)."""
    before = pose.body.data.shape[0]
    window = signing_window(pose)
    if window is not None:
        s, e = window
        pose.body.data = pose.body.data[s:e]
        pose.body.confidence = pose.body.confidence[s:e]
    return pose, before, pose.body.data.shape[0]


def hand_presence(pose) -> float:
    """Fraction of frames in which the better-seen hand was detected.

    A sign whose hands were barely tracked cannot be shown faithfully: the
    renderer draws a stub, and which hand is dominant is a guess. PopSign's
    TREE, seen in 1.5% of frames, was mirrored wrongly for that reason.
    """
    best = 0.0
    for hand in ("LEFT_HAND_LANDMARKS", "RIGHT_HAND_LANDMARKS"):
        xy = _points(pose, hand, ["WRIST"])
        if xy is not None and len(xy):
            best = max(best, float(np.mean(~np.isnan(xy[:, 0, 0]))))
    return best
