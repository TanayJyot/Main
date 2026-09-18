"""
MediaPipe API compatibility.

MediaPipe 1.0 removed the legacy Solutions API (`mediapipe.solutions.pose`,
`mediapipe.solutions.holistic`). A bare `pip install mediapipe` on a fresh
machine now gets 1.x, where `mp.solutions` does not exist at all and every
script that touches it dies with an AttributeError.

That matters beyond this toolkit: `pose-format`'s own `utils/holistic.py` uses
the legacy API, and this project pins `mediapipe==0.10.21` in
pose-master/pose-master/requirements.txt — which is correct, and which a fresh
install on a new machine will silently not reproduce.

Rather than maintain a second code path against the Tasks API whose landmark
naming does not line up with pose-format's components, this module fails loudly
and tells you the pin. Everything here needs the legacy API because
pose-format does.
"""

from __future__ import annotations

from typing import Any

# Verified by hand: 0.10.21 has the Solutions API, 0.10.30 does not.
REQUIRED_PIN = "mediapipe>=0.10.9,<0.10.30"


class MediaPipeAPIError(ImportError):
    """Raised when the installed MediaPipe has no Solutions API."""


def _solutions() -> Any:
    try:
        import mediapipe as mp
    except ImportError as error:
        raise MediaPipeAPIError(f"mediapipe is not installed. Install {REQUIRED_PIN}") from error

    solutions = getattr(mp, "solutions", None)
    if solutions is None:
        version = getattr(mp, "__version__", "unknown")
        raise MediaPipeAPIError(
            f"mediapipe {version} has no Solutions API — it was removed in 1.0, and both "
            f"this toolkit and pose-format depend on it.\n"
            f"Install {REQUIRED_PIN} (this project already pins 0.10.21 for the same reason)."
        )
    return solutions


def solutions() -> Any:
    """The legacy `mediapipe.solutions` module, or a clear error."""
    return _solutions()


def pose_landmarker(**kwargs) -> Any:
    """mp.solutions.pose.Pose, as a context manager."""
    defaults = {"static_image_mode": True, "model_complexity": 2, "min_detection_confidence": 0.5}
    defaults.update(kwargs)
    return _solutions().pose.Pose(**defaults)


def holistic_landmarker(**kwargs) -> Any:
    """mp.solutions.holistic.Holistic, as a context manager."""
    defaults = {"static_image_mode": True, "model_complexity": 2, "refine_face_landmarks": False}
    defaults.update(kwargs)
    return _solutions().holistic.Holistic(**defaults)


def available() -> bool:
    try:
        _solutions()
        return True
    except MediaPipeAPIError:
        return False
