"""
Filter a raw image corpus down to SHHQ-like candidates.

SHHQ is single-person, full-body, roughly frontal, uncluttered background,
1024x512. If the replacement corpus has a different distribution then a change
in the trained model cannot be attributed to the licence swap — you would be
measuring two things at once. This script enforces the same shape.

The geometry predicates are pure functions over a landmark array so they can be
tested without running MediaPipe. `screen()` is the one entry point that needs
the model.

Usage:
    python filter_candidates.py --input_dir corpus/downloaded --output_dir corpus/raw \
        --manifest corpus/provenance.jsonl --rejects_log corpus/rejected.json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

# MediaPipe Pose landmark indices we care about.
NOSE = 0
L_SHOULDER, R_SHOULDER = 11, 12
L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26
L_ANKLE, R_ANKLE = 27, 28

FULL_BODY_POINTS = (NOSE, L_SHOULDER, R_SHOULDER, L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANKLE, R_ANKLE)


@dataclass
class Thresholds:
    """Tuned to SHHQ's look. Loosen only if you also loosen the baseline."""

    min_visibility: float = 0.6      # per-landmark confidence for full-body points
    min_shoulder_ratio: float = 0.18  # shoulder width / body height — rejects profiles
    max_shoulder_tilt: float = 0.25   # |dy| / shoulder width — rejects lying down / heavy roll
    max_depth_skew: float = 0.45      # |z_left - z_right| / shoulder width — rejects turned torsos
    min_body_fraction: float = 0.45   # subject height / image height — rejects tiny distant subjects
    min_resolution: int = 512         # shorter edge, before cropping


def _visible(landmarks: np.ndarray, index: int, threshold: float) -> bool:
    return bool(landmarks[index, 3] >= threshold)


def is_full_body(landmarks: np.ndarray, thresholds: Thresholds) -> bool:
    """Every landmark from nose to ankles is confidently present."""
    return all(_visible(landmarks, i, thresholds.min_visibility) for i in FULL_BODY_POINTS)


def body_height(landmarks: np.ndarray) -> float:
    head_y = landmarks[NOSE, 1]
    foot_y = max(landmarks[L_ANKLE, 1], landmarks[R_ANKLE, 1])
    return float(abs(foot_y - head_y))


def shoulder_width(landmarks: np.ndarray) -> float:
    return float(abs(landmarks[L_SHOULDER, 0] - landmarks[R_SHOULDER, 0]))


def is_frontal(landmarks: np.ndarray, thresholds: Thresholds) -> bool:
    """Reject profiles and strongly turned torsos.

    Three independent signals, because any one alone is easy to fool: shoulders
    far apart horizontally, shoulders roughly level, and shoulders at a similar
    depth.
    """
    width = shoulder_width(landmarks)
    height = body_height(landmarks)
    if height <= 0 or width <= 0:
        return False

    if width / height < thresholds.min_shoulder_ratio:
        return False

    tilt = abs(landmarks[L_SHOULDER, 1] - landmarks[R_SHOULDER, 1]) / width
    if tilt > thresholds.max_shoulder_tilt:
        return False

    depth_skew = abs(landmarks[L_SHOULDER, 2] - landmarks[R_SHOULDER, 2]) / width
    return depth_skew <= thresholds.max_depth_skew


def is_upright(landmarks: np.ndarray) -> bool:
    """Shoulders above hips, hips above ankles. Image coordinates grow downward."""
    shoulder_y = (landmarks[L_SHOULDER, 1] + landmarks[R_SHOULDER, 1]) / 2
    hip_y = (landmarks[L_HIP, 1] + landmarks[R_HIP, 1]) / 2
    ankle_y = (landmarks[L_ANKLE, 1] + landmarks[R_ANKLE, 1]) / 2
    return bool(shoulder_y < hip_y < ankle_y)


def fills_frame(landmarks: np.ndarray, thresholds: Thresholds) -> bool:
    """Subject occupies enough of the frame to survive the square crop."""
    return body_height(landmarks) >= thresholds.min_body_fraction


def evaluate(landmarks: np.ndarray, thresholds: Optional[Thresholds] = None) -> Tuple[bool, List[str]]:
    """Run every predicate. Returns (accepted, reasons for rejection).

    `landmarks` is (33, 4): normalised x, y, z, visibility — MediaPipe Pose's
    output layout, with x and y in [0, 1] relative to the image.
    """
    thresholds = thresholds or Thresholds()
    reasons = []

    if landmarks.shape[0] < 33 or landmarks.shape[1] < 4:
        return False, ["landmark array is not (33, 4)"]
    if not is_full_body(landmarks, thresholds):
        reasons.append("not full body")
        # The remaining predicates read landmarks this one just called unreliable.
        return False, reasons
    if not is_upright(landmarks):
        reasons.append("not upright")
    if not is_frontal(landmarks, thresholds):
        reasons.append("not frontal")
    if not fills_frame(landmarks, thresholds):
        reasons.append("subject too small in frame")

    return not reasons, reasons


def to_landmark_array(pose_landmarks) -> np.ndarray:
    """MediaPipe result -> (33, 4) array."""
    return np.array([[lm.x, lm.y, lm.z, lm.visibility] for lm in pose_landmarks.landmark], dtype=float)


def screen(image_path: str, pose_model, thresholds: Optional[Thresholds] = None) -> Tuple[bool, List[str]]:
    """Screen one image file. Needs cv2 and an initialised MediaPipe Pose."""
    import cv2

    image = cv2.imread(image_path)
    if image is None:
        return False, ["unreadable"]

    thresholds = thresholds or Thresholds()
    height, width = image.shape[:2]
    if min(height, width) < thresholds.min_resolution:
        return False, [f"resolution {width}x{height} below {thresholds.min_resolution}"]

    result = pose_model.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    if result.pose_landmarks is None:
        return False, ["no person detected"]

    return evaluate(to_landmark_array(result.pose_landmarks), thresholds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter downloaded images to SHHQ-like candidates.")
    parser.add_argument("--input_dir", required=True)
    parser.add_argument("--output_dir", required=True, help="Accepted images are copied here")
    parser.add_argument("--rejects_log", default="rejected.json")
    parser.add_argument("--min_visibility", type=float, default=Thresholds.min_visibility)
    parser.add_argument("--min_body_fraction", type=float, default=Thresholds.min_body_fraction)
    args = parser.parse_args()

    import mediapipe as mp

    thresholds = Thresholds(min_visibility=args.min_visibility,
                            min_body_fraction=args.min_body_fraction)
    os.makedirs(args.output_dir, exist_ok=True)

    accepted: List[str] = []
    rejected: Dict[str, List[str]] = {}

    # static_image_mode + model_complexity=2 is slow but this runs once, and a
    # missed landmark here costs a bad training image forever.
    with mp.solutions.pose.Pose(static_image_mode=True, model_complexity=2,
                                min_detection_confidence=0.5) as pose_model:
        for filename in sorted(os.listdir(args.input_dir)):
            path = os.path.join(args.input_dir, filename)
            if not os.path.isfile(path):
                continue
            ok, reasons = screen(path, pose_model, thresholds)
            if ok:
                shutil.copy2(path, os.path.join(args.output_dir, filename))
                accepted.append(filename)
            else:
                rejected[filename] = reasons

    with open(args.rejects_log, "w", encoding="utf-8") as handle:
        json.dump(rejected, handle, indent=2)

    print(f"accepted {len(accepted)}, rejected {len(rejected)} -> {args.output_dir}")
    tally: Dict[str, int] = {}
    for reasons in rejected.values():
        for reason in reasons:
            tally[reason] = tally.get(reason, 0) + 1
    for reason, count in sorted(tally.items(), key=lambda kv: -kv[1]):
        print(f"  {count:5d}  {reason}")


if __name__ == "__main__":
    main()
