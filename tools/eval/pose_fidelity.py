"""
Did the renderer actually draw the pose it was told to draw?

Re-runs MediaPipe Holistic on each generated frame and compares the landmarks
it recovers against the conditioning skeleton the renderer was given. This is
the metric that catches the failure that matters: a frame that looks like a
plausible human but is not making the right handshape scores well on FID and
is useless as ASL.

Landmarks are matched **by name**, never by position. A `.pose` file does not
have to carry MediaPipe's full layout: `reduce_holistic`, which this project's
own concatenate.py enables, trims POSE_LANDMARKS from 33 points down to 8
(shoulders, elbows, wrists, hips). Comparing that against a fresh 33-point
MediaPipe result positionally would silently compare a shoulder to an eyebrow,
or skip every frame and report a confident NaN. Matching on names makes the
overlap explicit and reports what was actually scored.

Body and hands are scored separately, each normalised by its own scale — see
metrics.py.
"""

from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import mp_compat  # noqa: E402

from metrics import mpjpe, pck, scale_between  # noqa: E402

# Component names as pose_format's MediaPipe Holistic header spells them.
POSE_COMPONENT = "POSE_LANDMARKS"
LEFT_HAND_COMPONENT = "LEFT_HAND_LANDMARKS"
RIGHT_HAND_COMPONENT = "RIGHT_HAND_LANDMARKS"

COMPONENTS = (POSE_COMPONENT, LEFT_HAND_COMPONENT, RIGHT_HAND_COMPONENT)
LABELS = {POSE_COMPONENT: "body", LEFT_HAND_COMPONENT: "left_hand",
          RIGHT_HAND_COMPONENT: "right_hand"}

# The point pair each component's error is normalised by.
SCALE_POINTS = {
    POSE_COMPONENT: ("LEFT_SHOULDER", "RIGHT_SHOULDER"),
    LEFT_HAND_COMPONENT: ("WRIST", "MIDDLE_FINGER_MCP"),
    RIGHT_HAND_COMPONENT: ("WRIST", "MIDDLE_FINGER_MCP"),
}


def read_conditioning_pose(pose_path: str):
    """Load the .pose file that conditioned the render."""
    from pose_format import Pose

    with open(pose_path, "rb") as handle:
        return Pose.read(handle.read())


def component_points(pose, component_name: str) -> Optional[Tuple[int, int, List[str]]]:
    """(start, end, point names) for one component within the flat landmark axis."""
    offset = 0
    for component in pose.header.components:
        if component.name == component_name:
            return offset, offset + len(component.points), list(component.points)
        offset += len(component.points)
    return None


def conditioning_landmarks(pose, component_name: str) -> Tuple[Optional[np.ndarray], List[str]]:
    """((frames, points, 2) pixel coordinates, point names) for one component."""
    found = component_points(pose, component_name)
    if found is None:
        return None, []
    start, end, names = found
    data = np.asarray(pose.body.data)  # (frames, people, points, dims)
    if data.size == 0:
        return None, names
    return data[:, 0, start:end, :2], names


def mediapipe_point_names(component_name: str) -> List[str]:
    """The landmark names MediaPipe emits, in the order it emits them.

    Taken from the live enums rather than hardcoded, so a MediaPipe update that
    reorders or renames points is picked up instead of silently mis-matched.
    """
    solutions = mp_compat.solutions()
    if component_name == POSE_COMPONENT:
        return [landmark.name for landmark in solutions.pose.PoseLandmark]
    return [landmark.name for landmark in solutions.hands.HandLandmark]


def align_by_name(target: np.ndarray, target_names: Sequence[str],
                  predicted: np.ndarray, predicted_names: Sequence[str]
                  ) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """Reduce both landmark sets to the points they share, in a common order.

    Returns (target subset, predicted subset, shared names). Empty arrays when
    nothing overlaps, which the caller reports rather than treating as a score.
    """
    predicted_index = {name: index for index, name in enumerate(predicted_names)}
    shared, target_rows, predicted_rows = [], [], []

    for target_row, name in enumerate(target_names):
        predicted_row = predicted_index.get(name)
        if predicted_row is None:
            continue
        shared.append(name)
        target_rows.append(target_row)
        predicted_rows.append(predicted_row)

    if not shared:
        empty = np.zeros((0, target.shape[-1] if target.ndim else 2))
        return empty, empty, []

    return target[..., target_rows, :], predicted[..., predicted_rows, :], shared


def named_scale(landmarks: np.ndarray, names: Sequence[str], component_name: str) -> float:
    """Normalising distance, resolved by point name rather than by index."""
    first, second = SCALE_POINTS[component_name]
    lookup = {name: index for index, name in enumerate(names)}
    if first not in lookup or second not in lookup:
        return 0.0
    return scale_between(landmarks, lookup[first], lookup[second])


def holistic_landmarks(frame_bgr, holistic_model) -> Dict[str, Optional[np.ndarray]]:
    """Run MediaPipe Holistic on one frame, in pixel coordinates."""
    import cv2

    height, width = frame_bgr.shape[:2]
    result = holistic_model.process(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))

    def to_pixels(landmark_list) -> Optional[np.ndarray]:
        if landmark_list is None:
            return None
        return np.array([[lm.x * width, lm.y * height] for lm in landmark_list.landmark], dtype=float)

    return {
        POSE_COMPONENT: to_pixels(result.pose_landmarks),
        LEFT_HAND_COMPONENT: to_pixels(result.left_hand_landmarks),
        RIGHT_HAND_COMPONENT: to_pixels(result.right_hand_landmarks),
    }


def score_sequence(frame_paths: List[str], pose_path: str, threshold: float = 0.2) -> Dict[str, float]:
    """Score one rendered clip against the pose it was conditioned on.

    Returns per-component PCK and MPJPE, plus two diagnostics that stop a
    vacuous result looking like a good one:

      <component>_detection_rate — how often MediaPipe found the part at all. A
        renderer that produces mittens posts a fine PCK on the handful of
        frames where a hand is detected; this is what exposes it.
      <component>_points_compared — how many landmarks the comparison actually
        used. If this is 0 the metric is meaningless, not perfect.
    """
    import cv2

    pose = read_conditioning_pose(pose_path)
    targets, target_names = {}, {}
    for name in COMPONENTS:
        targets[name], target_names[name] = conditioning_landmarks(pose, name)

    predicted_names = {name: mediapipe_point_names(name) for name in COMPONENTS}

    accumulated: Dict[str, List[float]] = {}
    detected = {name: 0 for name in COMPONENTS}
    points_compared = {name: 0 for name in COMPONENTS}
    frames_scored = 0

    with mp_compat.holistic_landmarker() as model:
        for index, frame_path in enumerate(frame_paths):
            frame = cv2.imread(frame_path)
            if frame is None:
                continue
            observed = holistic_landmarks(frame, model)
            frames_scored += 1

            for name in COMPONENTS:
                target_sequence = targets[name]
                if target_sequence is None or index >= len(target_sequence):
                    continue
                predicted = observed.get(name)
                if predicted is None:
                    continue  # reflected in detection_rate below
                detected[name] += 1

                target_points, predicted_points, shared = align_by_name(
                    target_sequence[index], target_names[name], predicted, predicted_names[name])
                if not shared:
                    continue
                points_compared[name] = len(shared)

                scale = named_scale(target_points, shared, name)
                if scale <= 0:
                    continue

                label = LABELS[name]
                accumulated.setdefault(f"{label}_pck", []).append(
                    pck(predicted_points, target_points, scale, threshold))
                accumulated.setdefault(f"{label}_mpjpe", []).append(
                    mpjpe(predicted_points, target_points, scale))

    scores = {key: float(np.nanmean(values)) if values else float("nan")
              for key, values in accumulated.items()}

    for name in COMPONENTS:
        label = LABELS[name]
        target_sequence = targets[name]
        # Only frames whose conditioning pose contains this component count.
        expected = 0 if target_sequence is None else min(len(target_sequence), frames_scored)
        scores[f"{label}_detection_rate"] = (detected[name] / expected) if expected else float("nan")
        scores[f"{label}_points_compared"] = float(points_compared[name])

    scores["frames_scored"] = float(frames_scored)
    return scores


def frames_in(directory: str) -> List[str]:
    names = sorted(name for name in os.listdir(directory)
                   if name.lower().endswith((".png", ".jpg", ".jpeg")))
    return [os.path.join(directory, name) for name in names]
