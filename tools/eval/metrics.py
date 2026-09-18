"""
Metrics for comparing a candidate renderer against the frozen baseline.

Everything here is a pure function over numpy arrays, so the harness can be
tested without a GPU, a model, or any of the heavy optional dependencies.

The design decision that matters: hand accuracy is scored separately from body
accuracy, and normalised by hand size rather than by body size. A whole-body
average is dominated by the torso, which is easy, and will happily report a
model as unchanged while its fingers turn to mush. For ASL that is the only
error that matters — a blurred hand is an unreadable sign.
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

import numpy as np

# MediaPipe Holistic landmark indices, within each component.
POSE_L_SHOULDER, POSE_R_SHOULDER = 11, 12
HAND_WRIST, HAND_MIDDLE_MCP = 0, 9


def _valid_mask(a: np.ndarray, b: np.ndarray, confidence: Optional[np.ndarray]) -> np.ndarray:
    """Points present in both sets, and confident if confidence is supplied."""
    finite = np.isfinite(a).all(axis=-1) & np.isfinite(b).all(axis=-1)
    nonzero = (np.abs(a).sum(axis=-1) > 0) & (np.abs(b).sum(axis=-1) > 0)
    valid = finite & nonzero
    if confidence is not None:
        valid = valid & (confidence > 0)
    return valid


def mpjpe(predicted: np.ndarray, target: np.ndarray, scale: float,
          confidence: Optional[np.ndarray] = None) -> float:
    """Mean per-joint position error, normalised by `scale`.

    predicted/target are (..., P, 2 or 3). Returns NaN when nothing is valid,
    which the aggregator treats as "not measured" rather than as zero error.
    """
    predicted, target = np.asarray(predicted, float), np.asarray(target, float)
    valid = _valid_mask(predicted, target, confidence)
    if not valid.any() or scale <= 0:
        return float("nan")
    distances = np.linalg.norm(predicted - target, axis=-1)
    return float(distances[valid].mean() / scale)


def pck(predicted: np.ndarray, target: np.ndarray, scale: float, threshold: float = 0.2,
        confidence: Optional[np.ndarray] = None) -> float:
    """Fraction of joints within `threshold * scale` of the target."""
    predicted, target = np.asarray(predicted, float), np.asarray(target, float)
    valid = _valid_mask(predicted, target, confidence)
    if not valid.any() or scale <= 0:
        return float("nan")
    distances = np.linalg.norm(predicted - target, axis=-1)
    return float((distances[valid] <= threshold * scale).mean())


def scale_between(landmarks: np.ndarray, index_a: int, index_b: int) -> float:
    """Median distance between two landmarks across all frames.

    Indices are passed in rather than hardcoded because a .pose file need not
    carry MediaPipe's full landmark layout. `reduce_holistic` — which this
    project's own concatenate.py enables — trims POSE_LANDMARKS from 33 points
    to 8, so position 11 is not necessarily the left shoulder. Callers resolve
    the index by point name; see pose_fidelity.align_by_name.
    """
    landmarks = np.asarray(landmarks, float)
    if landmarks.ndim < 2:
        return 0.0
    point_count = landmarks.shape[-2]
    if not (0 <= index_a < point_count and 0 <= index_b < point_count):
        return 0.0

    distances = np.linalg.norm(landmarks[..., index_a, :2] - landmarks[..., index_b, :2], axis=-1)
    distances = distances[np.isfinite(distances) & (distances > 0)]
    return float(np.median(distances)) if distances.size else 0.0


def shoulder_scale(pose_landmarks: np.ndarray, left: int = POSE_L_SHOULDER,
                   right: int = POSE_R_SHOULDER) -> float:
    """Shoulder width — the natural normaliser for body-level error."""
    return scale_between(pose_landmarks, left, right)


def hand_scale(hand_landmarks: np.ndarray, wrist: int = HAND_WRIST,
               knuckle: int = HAND_MIDDLE_MCP) -> float:
    """Wrist to middle-finger MCP — normalises hand error by hand size.

    Without this, a hand error of a few pixels looks negligible against a
    shoulder-width normaliser even when the handshape is destroyed.
    """
    return scale_between(hand_landmarks, wrist, knuckle)


def psnr(a: np.ndarray, b: np.ndarray, data_range: float = 255.0) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    mse = float(np.mean((a - b) ** 2))
    if mse == 0:
        return float("inf")
    return float(10 * np.log10((data_range ** 2) / mse))


def _uniform_filter(image: np.ndarray, size: int) -> np.ndarray:
    """Box filter via a summed-area table. Avoids a scipy dependency."""
    pad = size // 2
    padded = np.pad(image, pad, mode="reflect")
    cumulative = padded.cumsum(axis=0).cumsum(axis=1)
    cumulative = np.pad(cumulative, ((1, 0), (1, 0)), mode="constant")
    height, width = image.shape
    bottom_right = cumulative[size:size + height, size:size + width]
    top_right = cumulative[0:height, size:size + width]
    bottom_left = cumulative[size:size + height, 0:width]
    top_left = cumulative[0:height, 0:width]
    return (bottom_right - top_right - bottom_left + top_left) / (size * size)


def ssim(a: np.ndarray, b: np.ndarray, data_range: float = 255.0, window: int = 7) -> float:
    """Structural similarity, greyscale, single scale.

    Matches skimage closely enough for tracking a regression; use skimage if you
    need to quote a number against published work.
    """
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.ndim == 3:
        a = a.mean(axis=2)
    if b.ndim == 3:
        b = b.mean(axis=2)
    if a.shape != b.shape:
        raise ValueError(f"shape mismatch: {a.shape} vs {b.shape}")

    c1, c2 = (0.01 * data_range) ** 2, (0.03 * data_range) ** 2
    mu_a, mu_b = _uniform_filter(a, window), _uniform_filter(b, window)
    sigma_a = _uniform_filter(a * a, window) - mu_a ** 2
    sigma_b = _uniform_filter(b * b, window) - mu_b ** 2
    sigma_ab = _uniform_filter(a * b, window) - mu_a * mu_b

    numerator = (2 * mu_a * mu_b + c1) * (2 * sigma_ab + c2)
    denominator = (mu_a ** 2 + mu_b ** 2 + c1) * (sigma_a + sigma_b + c2)
    return float(np.mean(numerator / denominator))


def temporal_flicker(frames: Sequence[np.ndarray]) -> float:
    """Mean absolute difference between consecutive frames.

    A crude but honest flicker proxy: per-frame metrics cannot see it at all,
    and identity instability across frames is the most common failure of a
    per-frame diffusion renderer. `temporal_warp_error` is the better measure
    where optical flow is available.
    """
    if len(frames) < 2:
        return float("nan")
    diffs = [float(np.abs(np.asarray(b, float) - np.asarray(a, float)).mean())
             for a, b in zip(frames, frames[1:])]
    return float(np.mean(diffs))


def temporal_warp_error(frames: Sequence[np.ndarray]) -> float:
    """Flicker with real motion discounted, by warping along optical flow.

    Falls back to temporal_flicker when cv2 is unavailable.
    """
    try:
        import cv2
    except ImportError:
        return temporal_flicker(frames)

    if len(frames) < 2:
        return float("nan")

    errors = []
    for previous, current in zip(frames, frames[1:]):
        previous, current = np.asarray(previous), np.asarray(current)
        previous_grey = cv2.cvtColor(previous.astype(np.uint8), cv2.COLOR_RGB2GRAY) if previous.ndim == 3 else previous.astype(np.uint8)
        current_grey = cv2.cvtColor(current.astype(np.uint8), cv2.COLOR_RGB2GRAY) if current.ndim == 3 else current.astype(np.uint8)

        flow = cv2.calcOpticalFlowFarneback(previous_grey, current_grey, None,
                                            0.5, 3, 15, 3, 5, 1.2, 0)
        height, width = previous_grey.shape
        grid_x, grid_y = np.meshgrid(np.arange(width, dtype=np.float32),
                                     np.arange(height, dtype=np.float32))
        warped = cv2.remap(previous.astype(np.float32),
                           grid_x + flow[..., 0], grid_y + flow[..., 1],
                           interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        errors.append(float(np.abs(warped - current.astype(np.float32)).mean()))

    return float(np.mean(errors))


def regression_report(baseline: Dict[str, float], candidate: Dict[str, float],
                      tolerances: Optional[Dict[str, float]] = None) -> Dict[str, dict]:
    """Compare two metric dicts and say, per metric, whether it regressed.

    `tolerances` gives the allowed slip per metric. Metrics where higher is
    better (pck, ssim, psnr) and where lower is better are handled separately —
    getting that backwards is the easiest way to ship a regression believing it
    is an improvement.
    """
    higher_is_better = ("pck", "ssim", "psnr", "training_ready")
    tolerances = tolerances or {}
    report = {}

    for key in sorted(set(baseline) | set(candidate)):
        before, after = baseline.get(key), candidate.get(key)
        if before is None or after is None or not np.isfinite(before) or not np.isfinite(after):
            report[key] = {"baseline": before, "candidate": after, "verdict": "not measured"}
            continue

        better_up = any(token in key for token in higher_is_better)
        delta = after - before
        slack = tolerances.get(key, 0.0)
        passed = (delta >= -slack) if better_up else (delta <= slack)
        report[key] = {
            "baseline": round(before, 6),
            "candidate": round(after, 6),
            "delta": round(delta, 6),
            "tolerance": slack,
            "higher_is_better": better_up,
            "verdict": "ok" if passed else "REGRESSED",
        }

    return report
