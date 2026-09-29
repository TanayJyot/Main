"""Pick one clip per pilot gloss by a fixed rule, then build the mixed lexicon.

The rule is written down before any result exists and never looks at the old
lexicon's content:

  dominant hand  the hand whose wrist (POSE_LANDMARKS) travels further,
                 normalised by shoulder width
  score          fraction of frames in which the dominant hand's landmarks
                 were detected
  tie-breaks     mean visibility of the dominant wrist, then filename

Per gloss, the best clip of each source is found. The one marked `selected`
(the clip that represents the gloss) is PopSign's when PopSign has the gloss,
because PopSign is CC BY 4.0 and ASL Citizen is evaluation-only until Microsoft
replies. Every other clip is `calibration`: same sign, other signers, for
calibrate.py's same-sign-different-signer distances (capped per source so one
gloss does not dominate).

Left-dominant selections are mirrored to right-dominant: x is reflected, and
left/right hand components and LEFT_*/RIGHT_* body points are swapped. Face
mesh indices are not re-paired (the geometry is mirrored, the labels are not);
the renderer does not care, a face-aware metric would.

Outputs (gitignored):
  out/manifest.csv       path,concept,source,label,signer,role + rule columns
  out/lexicon_mixed/     <gloss>.pose: new sign where one exists, else the
                         old lexicon's file, for build_baseline.py (task 5)
  out/selection.json     per-gloss summary

Usage:
    ASLYTICS_LEXICON_DIR=<old lexicon> python select_clips.py
"""

from __future__ import annotations

import csv
import json
import os
import shutil
from collections import defaultdict
from pathlib import Path

import numpy as np
from pose_format import Pose

from labels import candidate_labels

HERE = Path(__file__).parent
DATA = HERE / "data"
OUT = HERE / "out"
CALIBRATION_PER_SOURCE = 6


def component_slice(pose: Pose, name: str) -> slice:
    start = 0
    for c in pose.header.components:
        if c.name == name:
            return slice(start, start + len(c.points))
        start += len(c.points)
    raise KeyError(name)


def point_index(pose: Pose, component: str, point: str) -> int:
    s = component_slice(pose, component)
    names = next(c.points for c in pose.header.components if c.name == component)
    return s.start + names.index(point)


def score(pose: Pose) -> dict:
    data = np.asarray(pose.body.data[:, 0, :, :2].filled(0) if np.ma.isMaskedArray(pose.body.data)
                      else pose.body.data[:, 0, :, :2])
    conf = np.asarray(pose.body.confidence[:, 0, :])
    idx = {p: point_index(pose, "POSE_LANDMARKS", p)
           for p in ["LEFT_WRIST", "RIGHT_WRIST", "LEFT_SHOULDER", "RIGHT_SHOULDER"]}
    shoulder = np.linalg.norm(data[:, idx["LEFT_SHOULDER"]] - data[:, idx["RIGHT_SHOULDER"]], axis=-1)
    scale = float(np.median(shoulder[shoulder > 0])) if (shoulder > 0).any() else 1.0

    def travel(p: str) -> float:
        xy = data[:, idx[p]]
        return float(np.linalg.norm(np.diff(xy, axis=0), axis=-1).sum() / scale)

    dominant = "LEFT" if travel("LEFT_WRIST") > travel("RIGHT_WRIST") else "RIGHT"
    hand = component_slice(pose, f"{dominant}_HAND_LANDMARKS")
    presence = float((conf[:, hand].max(axis=1) > 0).mean()) if len(conf) else 0.0
    visibility = float(conf[:, idx[f"{dominant}_WRIST"]].mean()) if len(conf) else 0.0
    return {"dominant": dominant, "presence": presence, "visibility": visibility}


def mirror(pose: Pose) -> Pose:
    width = pose.header.dimensions.width
    data = pose.body.data.copy()
    conf = pose.body.confidence.copy()
    for c in pose.header.components:
        s = component_slice(pose, c.name)
        if c.name == "POSE_WORLD_LANDMARKS":
            data[:, :, s, 0] = -data[:, :, s, 0]      # metres, centred on the hips
        else:
            data[:, :, s, 0] = width - data[:, :, s, 0]
    swaps = [(component_slice(pose, "LEFT_HAND_LANDMARKS"), component_slice(pose, "RIGHT_HAND_LANDMARKS"))]
    for comp in ["POSE_LANDMARKS", "POSE_WORLD_LANDMARKS"]:
        names = next(c.points for c in pose.header.components if c.name == comp)
        for n in names:
            if n.startswith("LEFT_"):
                a, b = point_index(pose, comp, n), point_index(pose, comp, "RIGHT_" + n[5:])
                swaps.append((slice(a, a + 1), slice(b, b + 1)))
    for a, b in swaps:
        data[:, :, a], data[:, :, b] = data[:, :, b].copy(), data[:, :, a].copy()
        conf[:, :, a], conf[:, :, b] = conf[:, :, b].copy(), conf[:, :, a].copy()
    pose.body.data, pose.body.confidence = data, conf
    return pose


def aslc_signers() -> dict[str, tuple[str, str]]:
    """video file -> (label, participant)"""
    out = {}
    for split in ["train", "val", "test"]:
        with open(DATA / "aslc" / f"{split}.csv", encoding="utf8") as f:
            for r in csv.DictReader(f):
                out[r["Video file"]] = (r["Gloss"], r["Participant ID"])
    return out


def candidates(gloss: str, labels: dict, signers: dict) -> list[dict]:
    out = []
    for label in labels["popsign"]:
        for p in sorted((DATA / "pose" / "popsign" / label).glob("*.pose")):
            signer = p.stem.split("-")[0].removeprefix("gtsignstudy")
            out.append({"path": p, "source": "popsign", "label": label, "signer": f"popsign:{signer}"})
    wanted = set(labels["citizen"])
    for p in sorted((DATA / "pose" / "aslc").glob("*.pose")):
        label, participant = signers.get(p.stem + ".mp4", ("", ""))
        if label in wanted:
            out.append({"path": p, "source": "citizen", "label": label, "signer": f"citizen:{participant}"})
    return out


def main() -> None:
    old_dir = Path(os.environ.get("ASLYTICS_LEXICON_DIR", ""))
    if not old_dir.is_dir():
        raise SystemExit("set ASLYTICS_LEXICON_DIR to the old lexicon (used only to fill gaps)")
    signers = aslc_signers()
    mixed = OUT / "lexicon_mixed"
    if mixed.exists():
        shutil.rmtree(mixed)
    mixed.mkdir(parents=True)

    rows, summary = [], {}
    for gloss, labels in candidate_labels().items():
        scored = []
        for c in candidates(gloss, labels, signers):
            try:
                c.update(score(Pose.read(c["path"].read_bytes())))
            except Exception as e:  # noqa: BLE001 - an unreadable clip is skipped, not fatal
                print(f"  skip {c['path'].name}: {e}")
                continue
            scored.append(c)
        key = lambda c: (-c["presence"], -c["visibility"], c["path"].name)  # noqa: E731
        best = {s: min((c for c in scored if c["source"] == s), key=key, default=None)
                for s in ["popsign", "citizen"]}
        chosen = best["popsign"] or best["citizen"]
        if chosen is None:
            shutil.copy(old_dir / f"{gloss}.pose", mixed / f"{gloss}.pose")
            summary[gloss] = {"source": "old", "candidates": 0}
            continue

        pose = Pose.read(chosen["path"].read_bytes())
        if chosen["dominant"] == "LEFT":
            pose = mirror(pose)
        with open(mixed / f"{gloss}.pose", "wb") as f:
            pose.write(f)

        per_source = defaultdict(int)
        for c in sorted(scored, key=key):
            role = "selected" if c is chosen else "calibration"
            if role == "calibration":
                # One clip per signer, capped per source.
                if per_source[c["source"]] >= CALIBRATION_PER_SOURCE or any(
                        r["signer"] == c["signer"] and r["concept"] == labels["concept"] for r in rows):
                    continue
                per_source[c["source"]] += 1
            rows.append({"path": str(c["path"].resolve()), "concept": labels["concept"], "source": c["source"],
                         "label": c["label"], "signer": c["signer"], "role": role, "gloss": gloss,
                         "source_best": int(c is best[c["source"]]), "dominant": c["dominant"],
                         "presence": round(c["presence"], 3), "visibility": round(c["visibility"], 3),
                         "label_rule": labels["rule"][c["source"]]})
        summary[gloss] = {"source": chosen["source"], "label": chosen["label"], "clip": chosen["path"].name,
                          "mirrored": chosen["dominant"] == "LEFT", "presence": round(chosen["presence"], 3),
                          "candidates": len(scored)}

    # Keep the old files for every other gloss too, so sentences still render.
    for old in old_dir.glob("*.pose"):
        if not (mixed / old.name).exists():
            shutil.copy(old, mixed / old.name)

    with open(OUT / "manifest.csv", "w", newline="", encoding="utf8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (OUT / "selection.json").write_text(json.dumps(summary, indent=1), encoding="utf8")
    by = defaultdict(int)
    for s in summary.values():
        by[s["source"]] += 1
    print(f"pilot glosses: {dict(by)}; manifest rows: {len(rows)}; "
          f"mirrored: {sum(1 for s in summary.values() if s.get('mirrored'))}")


if __name__ == "__main__":
    main()
