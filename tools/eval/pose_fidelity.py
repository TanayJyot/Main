"""
Did the renderer actually draw the pose it was told to draw?

Re-runs MediaPipe Holistic on each generated frame and compares the landmarks
it recovers against the conditioning skeleton the renderer was given. This is
the metric that catches the failure that matters: a frame that looks like a
plausible human but is not making the right handshape scores well on FID and
is useless as ASL.

Body and hands are scored separately, each normalised by its own scale — see
metrics.py for why.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import numpy as np

from metrics import hand_scale, mpjpe, pck, shoulder_scale

# Component names as pose_format's MediaPipe Holistic header spells them.
POSE_COMPONENT = "POSE_LANDMARKS"
LEFT_HAND_COMPONENT = "LEFT_HAND_LANDMARKS"
RIGHT_HAND_COMPONENT = "RIGHT_HAND_LANDMARKS"


def read_conditioning_pose(pose_path: str):
    """Load the .pose file that conditioned the render."""
    from pose_format import Pose

    with open(pose_path, "rb") as handle:
        return Pose.read(handle.read())


def component_slice(pose, component_name: str) -> Optional[Tuple[int, int]]:
    """(start, end) indices of a component within the flat landmark axis."""
    offset = 0
    for component in pose.header.components:
        if component.name == component_name:
            return offset, offset + len(component.points)
        offset += len(component.points)
    return None


def conditioning_landmarks(pose, component_name: str) -> Optional[np.ndarray]:
    """(frames, points, 2) pixel coordinates for one component, or None."""
    bounds = component_slice(pose, component_name)
    if bounds is None:
        return None
    start, end = bounds
    data = np.asarray(pose.body.data)  # (frames, people, points, dims)
    if data.size == 0:
        return None
    return data[:, 0, start:end, :2]


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

    Returns body/left-hand/right-hand PCK and MPJPE, plus hand_detection_rate:
    the fraction of frames where MediaPipe found a hand at all. That last one
    is not a nicety — a renderer that produces mittens scores a vacuous PCK on
    the few frames it does detect, and the detection rate is what exposes it.
    """
    import cv2
    import mediapipe as mp

    pose = read_conditioning_pose(pose_path)
    targets = {name: conditioning_landmarks(pose, name)
               for name in (POSE_COMPONENT, LEFT_HAND_COMPONENT, RIGHT_HAND_COMPONENT)}

    body_target = targets[POSE_COMPONENT]
    body_scale = shoulder_scale(body_target) if body_target is not None else 0.0

    accumulated: Dict[str, List[float]] = {}
    hands_found = {LEFT_HAND_COMPONENT: 0, RIGHT_HAND_COMPONENT: 0}
    frames_scored = 0

    with mp.solutions.holistic.Holistic(static_image_mode=True, model_complexity=2,
                                        refine_face_landmarks=False) as model:
        for index, frame_path in enumerate(frame_paths):
            frame = cv2.imread(frame_path)
            if frame is None:
                continue
            observed = holistic_landmarks(frame, model)
            frames_scored += 1

            for name, target_sequence in targets.items():
                if target_sequence is None or index >= len(target_sequence):
                    continue
                predicted = observed.get(name)
                if predicted is None:
                    continue  # counted via hand_detection_rate below
                if name in hands_found:
                    hands_found[name] += 1

                target = target_sequence[index]
                if predicted.shape[0] != target.shape[0]:
                    continue

                scale = body_scale if name == POSE_COMPONENT else hand_scale(target)
                if scale <= 0:
                    continue

                label = {POSE_COMPONENT: "body", LEFT_HAND_COMPONENT: "left_hand",
                         RIGHT_HAND_COMPONENT: "right_hand"}[name]
                accumulated.setdefault(f"{label}_pck", []).append(pck(predicted, target, scale, threshold))
                accumulated.setdefault(f"{label}_mpjpe", []).append(mpjpe(predicted, target, scale))

    scores = {key: float(np.nanmean(values)) if values else float("nan")
              for key, values in accumulated.items()}

    for name, label in ((LEFT_HAND_COMPONENT, "left_hand"), (RIGHT_HAND_COMPONENT, "right_hand")):
        expected = targets[name]
        # Only frames whose conditioning pose actually contains a hand count
        # against the detection rate.
        expected_frames = 0 if expected is None else min(len(expected), frames_scored)
        scores[f"{label}_detection_rate"] = (hands_found[name] / expected_frames) if expected_frames else float("nan")

    scores["frames_scored"] = float(frames_scored)
    return scores


def frames_in(directory: str) -> List[str]:
    names = sorted(name for name in os.listdir(directory)
                   if name.lower().endswith((".png", ".jpg", ".jpeg")))
    return [os.path.join(directory, name) for name in names]
