"""
Fingerprint the gloss->pose lexicon to help identify where it came from.

DATA_LICENSES.md section 2b is still open: the `.pose` files are loaded from a
hardcoded path under `.gitignore/`, nobody recorded the source, and every
realistic ASL corpus is non-commercial. Asking the person who built the
directory is the fast path. This is the slow path, for when that fails.

A `.pose` file keeps more provenance than it looks. The header names the pose
estimator; the body carries frame rate and, when coordinates are in pixels, the
dimensions of the source video. Those three together narrow the field a lot:
frame rate separates broadcast-sourced corpora from webcam ones, and a tight
resolution cluster means a single studio while a scattered one means scraped
video from many sources.

This tool reports the fingerprint. It does not guess a dataset name — matching
it against a candidate corpus means downloading a sample of that corpus and
running this same script over it, which is the only comparison worth trusting.

    python tools/inspect_lexicon.py --lexicon_dir ~/.gitignore/generated_pose \
        --out lexicon_fingerprint.json
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from typing import Dict, List, Optional

import numpy as np


def load_pose(path: str):
    from pose_format import Pose

    with open(path, "rb") as handle:
        return Pose.read(handle.read())


def describe(path: str) -> Dict[str, object]:
    """Extract one file's fingerprint."""
    pose = load_pose(path)
    header, body = pose.header, pose.body
    data = np.asarray(body.data, dtype=float)

    components = [
        {"name": component.name, "points": len(component.points), "format": component.format}
        for component in header.components
    ]

    record: Dict[str, object] = {
        "file": os.path.basename(path),
        "bytes": os.path.getsize(path),
        "version": getattr(header, "version", None),
        "header_width": getattr(header, "width", None),
        "header_height": getattr(header, "height", None),
        "header_depth": getattr(header, "depth", None),
        "components": components,
        "component_names": [component["name"] for component in components],
        "total_points": sum(component["points"] for component in components),
        "fps": float(body.fps) if body.fps else None,
        "frames": int(data.shape[0]) if data.size else 0,
        "people": int(data.shape[1]) if data.ndim > 1 else None,
        "dimensions": int(data.shape[-1]) if data.size else None,
    }

    if record["fps"] and record["frames"]:
        record["duration_seconds"] = round(record["frames"] / record["fps"], 3)

    if data.size:
        confidence = np.asarray(body.confidence, dtype=float)
        present = data[confidence > 0] if confidence.size else data
        if present.size:
            coords = present.reshape(-1, data.shape[-1])
            record["coord_max"] = [round(float(v), 3) for v in np.nanmax(coords, axis=0)]
            record["coord_min"] = [round(float(v), 3) for v in np.nanmin(coords, axis=0)]
            # Normalised coordinates sit inside [0, 1]; pixel coordinates do not.
            # Pixel data is the useful case — its extent approximates the frame
            # size of the video the pose was estimated from.
            record["coordinate_space"] = "normalised" if float(np.nanmax(np.abs(coords))) <= 1.5 else "pixel"
        record["confidence_mean"] = round(float(np.nanmean(confidence)), 4) if confidence.size else None

    return record


def estimator_guess(component_names: List[str]) -> str:
    """Which pose estimator produced this. Structural, so it is reliable."""
    names = set(component_names)
    if {"POSE_LANDMARKS", "FACE_LANDMARKS"} & names:
        return "MediaPipe Holistic"
    if {"pose_keypoints_2d", "BODY_135"} & names:
        return "OpenPose"
    return "unknown"


def summarise(records: List[Dict[str, object]]) -> Dict[str, object]:
    def tally(key: str) -> Dict[str, int]:
        return dict(Counter(
            json.dumps(record.get(key)) if isinstance(record.get(key), list) else record.get(key)
            for record in records
        ).most_common(10))

    fps_values = [record["fps"] for record in records if record.get("fps")]
    frame_counts = [record["frames"] for record in records if record.get("frames")]
    widths = [record["coord_max"][0] for record in records
              if record.get("coordinate_space") == "pixel" and record.get("coord_max")]
    heights = [record["coord_max"][1] for record in records
               if record.get("coordinate_space") == "pixel" and len(record.get("coord_max") or []) > 1]

    summary: Dict[str, object] = {
        "files": len(records),
        "estimator": estimator_guess(records[0].get("component_names", []) if records else []),
        "component_sets": tally("component_names"),
        "fps_distribution": dict(Counter(fps_values).most_common(10)),
        "coordinate_space": tally("coordinate_space"),
        "header_dimensions": tally("header_width"),
    }

    if frame_counts:
        summary["frames"] = {
            "min": int(np.min(frame_counts)), "max": int(np.max(frame_counts)),
            "median": float(np.median(frame_counts)), "mean": round(float(np.mean(frame_counts)), 2),
        }
    if widths and heights:
        # A tight cluster means one recording setup — a studio or one signer.
        # A wide spread means video collected from many sources, i.e. scraped.
        summary["inferred_source_resolution"] = {
            "width": {"min": round(min(widths), 1), "max": round(max(widths), 1),
                      "median": round(float(np.median(widths)), 1)},
            "height": {"min": round(min(heights), 1), "max": round(max(heights), 1),
                       "median": round(float(np.median(heights)), 1)},
            "distinct_width_values": len({round(w) for w in widths}),
        }

    return summary


def interpret(summary: Dict[str, object]) -> List[str]:
    """Turn the fingerprint into leads. Deliberately not a dataset guess."""
    notes: List[str] = []

    fps_values = summary.get("fps_distribution") or {}
    if len(fps_values) == 1:
        notes.append(
            f"Single frame rate ({list(fps_values)[0]} fps) across every file — consistent with "
            f"one recording setup or one re-encode pass, not with video gathered from many sources."
        )
    elif len(fps_values) > 3:
        notes.append(
            f"{len(fps_values)} distinct frame rates — consistent with video collected from "
            f"multiple sources, which is what a scraped dictionary or an aggregated corpus "
            f"(e.g. WLASL, which pools several websites) looks like."
        )

    resolution = summary.get("inferred_source_resolution")
    if isinstance(resolution, dict):
        distinct = resolution.get("distinct_width_values", 0)
        if distinct == 1:
            notes.append(
                f"Every pose came from video of the same width ({resolution['width']['median']}px) — "
                f"a single studio or a single site's standard encode."
            )
        elif distinct > 5:
            notes.append(
                f"{distinct} distinct source widths — the videos were not produced together. "
                f"Points at an aggregated or scraped origin."
            )

    if summary.get("coordinate_space", {}).get('"normalised"'):
        notes.append(
            "Coordinates are normalised, so source resolution is not recoverable from the "
            "files. Frame rate and clip-length distribution are the remaining signals."
        )

    notes.append(
        "To identify the source: download a small sample of each candidate corpus, run this "
        "same script over it, and compare fingerprints. A name guessed from these numbers "
        "alone is not evidence, and the licence question needs evidence."
    )
    return notes


def main() -> None:
    parser = argparse.ArgumentParser(description="Fingerprint a .pose lexicon to trace its provenance.")
    parser.add_argument("--lexicon_dir", required=True, help="Directory of <gloss>.pose files")
    parser.add_argument("--out", default="lexicon_fingerprint.json")
    parser.add_argument("--limit", type=int, default=0, help="Inspect at most N files (0 = all)")
    args = parser.parse_args()

    if not os.path.isdir(args.lexicon_dir):
        parser.error(f"not a directory: {args.lexicon_dir}")

    filenames = sorted(name for name in os.listdir(args.lexicon_dir) if name.endswith(".pose"))
    if args.limit:
        filenames = filenames[:args.limit]
    if not filenames:
        parser.error(f"no .pose files in {args.lexicon_dir}")

    records, failures = [], {}
    for filename in filenames:
        try:
            records.append(describe(os.path.join(args.lexicon_dir, filename)))
        except Exception as error:  # a corrupt file should not stop the survey
            failures[filename] = str(error)

    summary = summarise(records)
    summary["unreadable"] = failures
    notes = interpret(summary)

    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump({"summary": summary, "notes": notes, "per_file": records}, handle, indent=2)

    print(f"inspected {len(records)} pose files ({len(failures)} unreadable)")
    print(json.dumps(summary, indent=2))
    print("\nLeads:")
    for note in notes:
        print(f"  - {note}")
    print(f"\nwrote {args.out}")
    print("\nThe fast path is still to ask whoever built the directory. Glosses are also a "
          "signal: compare the vocabulary list against each candidate corpus's word list.")


if __name__ == "__main__":
    main()
