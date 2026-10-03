"""Which hand signs a clip, how well it was tracked, and mirroring to right-handed.

The same rule the laptop's analysis/convert/select_clips.py uses for PopSign,
so every showcase lexicon picks clips the way the prototype does:

  dominant hand  the hand detected in clearly more frames (> 0.2 apart);
                 otherwise the one whose wrist travels further, normalised by
                 shoulder width
  score          fraction of frames in which the dominant hand was detected
  tie-breaks     mean visibility of the dominant wrist, then filename

It looks only at tracking quality, never at what the sign looks like and
never at another lexicon.
"""

from __future__ import annotations

from typing import Dict

import numpy as np


def component_slice(pose, name: str) -> slice:
    start = 0
    for component in pose.header.components:
        if component.name == name:
            return slice(start, start + len(component.points))
        start += len(component.points)
    raise KeyError(name)


def point_index(pose, component: str, point: str) -> int:
    names = next(c.points for c in pose.header.components if c.name == component)
    return component_slice(pose, component).start + names.index(point)


def score(pose) -> Dict[str, object]:
    """{"dominant": "LEFT" | "RIGHT", "presence": float, "visibility": float}"""
    raw = pose.body.data[:, 0, :, :2]
    data = np.asarray(raw.filled(0) if np.ma.isMaskedArray(raw) else raw, dtype=float)
    conf = np.asarray(pose.body.confidence[:, 0, :], dtype=float)
    idx = {p: point_index(pose, "POSE_LANDMARKS", p)
           for p in ["LEFT_WRIST", "RIGHT_WRIST", "LEFT_SHOULDER", "RIGHT_SHOULDER"]}
    shoulder = np.linalg.norm(data[:, idx["LEFT_SHOULDER"]] - data[:, idx["RIGHT_SHOULDER"]], axis=-1)
    scale = float(np.median(shoulder[shoulder > 0])) if (shoulder > 0).any() else 1.0

    def travel(point: str) -> float:
        return float(np.linalg.norm(np.diff(data[:, idx[point]], axis=0), axis=-1).sum() / scale)

    def seen(side: str) -> float:
        hand = component_slice(pose, f"{side}_HAND_LANDMARKS")
        return float((conf[:, hand].max(axis=1) > 0).mean()) if len(conf) else 0.0

    seen_by_side = {"LEFT": seen("LEFT"), "RIGHT": seen("RIGHT")}
    if abs(seen_by_side["LEFT"] - seen_by_side["RIGHT"]) > 0.2:
        dominant = max(seen_by_side, key=seen_by_side.get)
    else:
        dominant = "LEFT" if travel("LEFT_WRIST") > travel("RIGHT_WRIST") else "RIGHT"
    visibility = float(conf[:, idx[f"{dominant}_WRIST"]].mean()) if len(conf) else 0.0
    return {"dominant": dominant, "presence": seen_by_side[dominant], "visibility": visibility}


def mirror(pose):
    """Reflect x and swap left/right hands and LEFT_*/RIGHT_* body points, in place."""
    width = pose.header.dimensions.width
    data = pose.body.data.copy()
    conf = pose.body.confidence.copy()
    for component in pose.header.components:
        s = component_slice(pose, component.name)
        if component.name == "POSE_WORLD_LANDMARKS":
            data[:, :, s, 0] = -data[:, :, s, 0]      # metres, centred on the hips
        else:
            data[:, :, s, 0] = width - data[:, :, s, 0]
    names = {c.name for c in pose.header.components}
    swaps = [(component_slice(pose, "LEFT_HAND_LANDMARKS"), component_slice(pose, "RIGHT_HAND_LANDMARKS"))]
    for comp in ["POSE_LANDMARKS", "POSE_WORLD_LANDMARKS"]:
        if comp not in names:
            continue
        points = next(c.points for c in pose.header.components if c.name == comp)
        for name in points:
            if name.startswith("LEFT_") and "RIGHT_" + name[5:] in points:
                a, b = point_index(pose, comp, name), point_index(pose, comp, "RIGHT_" + name[5:])
                swaps.append((slice(a, a + 1), slice(b, b + 1)))
    for a, b in swaps:
        data[:, :, a], data[:, :, b] = data[:, :, b].copy(), data[:, :, a].copy()
        conf[:, :, a], conf[:, :, b] = conf[:, :, b].copy(), conf[:, :, a].copy()
    pose.body.data, pose.body.confidence = data, conf
    return pose
