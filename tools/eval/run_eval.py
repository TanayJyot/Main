"""
Score a renderer and, optionally, compare it against the frozen baseline.

This is the harness that has to exist *before* the SHHQ replacement is built.
Without a baseline number recorded on data we own, "we replicated our previous
results" is not a checkable claim.

    # once, against the current SHHQ-trained model
    python run_eval.py --renders runs/baseline --poses eval/poses \
        --real eval/real_frames --out runs/baseline/report.json

    # later, against each candidate
    python run_eval.py --renders runs/clean-v1 --poses eval/poses \
        --real eval/real_frames --out runs/clean-v1/report.json \
        --baseline runs/baseline/report.json

Expected layout: --renders and --poses hold one entry per clip, matched by
name (renders/<clip>/*.png next to poses/<clip>.pose).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metrics import psnr, regression_report, ssim, temporal_warp_error  # noqa: E402
from pose_fidelity import frames_in, score_sequence  # noqa: E402

# How much slip is acceptable per metric before we call it a regression.
# Hand fidelity is held tightest: it is the metric the product rests on.
DEFAULT_TOLERANCES = {
    "left_hand_pck": 0.02,
    "right_hand_pck": 0.02,
    "left_hand_detection_rate": 0.02,
    "right_hand_detection_rate": 0.02,
    "body_pck": 0.03,
    "left_hand_mpjpe": 0.05,
    "right_hand_mpjpe": 0.05,
    "body_mpjpe": 0.05,
    "ssim": 0.02,
    "psnr": 0.5,
    "temporal_warp_error": 1.0,
}


def clip_names(renders_dir: str, poses_dir: str) -> List[str]:
    rendered = {name for name in os.listdir(renders_dir)
                if os.path.isdir(os.path.join(renders_dir, name))}
    posed = {os.path.splitext(name)[0] for name in os.listdir(poses_dir)
             if name.endswith(".pose")}
    both = sorted(rendered & posed)
    for name in sorted(rendered - posed):
        print(f"  skipping {name}: no conditioning .pose")
    for name in sorted(posed - rendered):
        print(f"  skipping {name}: no rendered frames")
    return both


def image_metrics(render_dir: str, real_dir: str) -> Dict[str, float]:
    """Paired reconstruction quality, when a matching real clip exists."""
    import cv2

    rendered, real = frames_in(render_dir), frames_in(real_dir)
    if not rendered or not real:
        return {}

    psnr_values, ssim_values = [], []
    for render_path, real_path in zip(rendered, real):
        a, b = cv2.imread(render_path), cv2.imread(real_path)
        if a is None or b is None:
            continue
        if a.shape != b.shape:
            b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_AREA)
        psnr_values.append(psnr(a, b))
        ssim_values.append(ssim(a, b))

    if not psnr_values:
        return {}
    return {"psnr": float(np.mean(psnr_values)), "ssim": float(np.mean(ssim_values))}


def temporal_metrics(render_dir: str, max_frames: int = 60) -> Dict[str, float]:
    import cv2

    paths = frames_in(render_dir)[:max_frames]
    frames = [cv2.imread(path) for path in paths]
    frames = [frame for frame in frames if frame is not None]
    if len(frames) < 2:
        return {}
    return {"temporal_warp_error": temporal_warp_error(frames)}


def evaluate(renders_dir: str, poses_dir: str, real_dir: str = "",
             threshold: float = 0.2) -> Dict[str, object]:
    per_clip: Dict[str, Dict[str, float]] = {}

    for name in clip_names(renders_dir, poses_dir):
        render_dir = os.path.join(renders_dir, name)
        scores = score_sequence(frames_in(render_dir), os.path.join(poses_dir, f"{name}.pose"), threshold)
        scores.update(temporal_metrics(render_dir))
        if real_dir:
            candidate_real = os.path.join(real_dir, name)
            if os.path.isdir(candidate_real):
                scores.update(image_metrics(render_dir, candidate_real))
        per_clip[name] = scores
        print(f"  {name}: " + ", ".join(
            f"{k}={v:.3f}" for k, v in sorted(scores.items()) if np.isfinite(v)))

    # frames_scored is a count, not a quality signal — sum it, average the rest.
    aggregate: Dict[str, float] = {}
    keys = {key for scores in per_clip.values() for key in scores}
    for key in sorted(keys):
        values = [scores[key] for scores in per_clip.values()
                  if key in scores and np.isfinite(scores[key])]
        if not values:
            continue
        aggregate[key] = float(np.sum(values)) if key == "frames_scored" else float(np.mean(values))

    return {"aggregate": aggregate, "per_clip": per_clip, "clips": len(per_clip),
            "pck_threshold": threshold}


def main() -> None:
    parser = argparse.ArgumentParser(description="Score a renderer against conditioning poses.")
    parser.add_argument("--renders", required=True, help="Directory of per-clip frame directories")
    parser.add_argument("--poses", required=True, help="Directory of conditioning .pose files")
    parser.add_argument("--real", default="", help="Optional held-out real frames, same layout")
    parser.add_argument("--out", required=True, help="Where to write report.json")
    parser.add_argument("--baseline", default="", help="A previous report.json to compare against")
    parser.add_argument("--pck_threshold", type=float, default=0.2)
    args = parser.parse_args()

    report = evaluate(args.renders, args.poses, args.real, args.pck_threshold)

    if args.baseline:
        with open(args.baseline, "r", encoding="utf-8") as handle:
            baseline = json.load(handle)
        comparison = regression_report(baseline.get("aggregate", {}),
                                       report["aggregate"], DEFAULT_TOLERANCES)
        report["comparison"] = comparison
        report["baseline_report"] = args.baseline

        regressions = [key for key, row in comparison.items() if row["verdict"] == "REGRESSED"]
        print("\nvs baseline:")
        for key, row in sorted(comparison.items()):
            if row["verdict"] == "not measured":
                continue
            print(f"  {row['verdict']:>9}  {key}: {row['baseline']} -> {row['candidate']} "
                  f"({row['delta']:+.4f}, tol {row['tolerance']})")
        report["passed"] = not regressions

    directory = os.path.dirname(args.out)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(f"\nwrote {args.out} ({report['clips']} clips)")

    if args.baseline and not report.get("passed", True):
        print("\nRegressions above. Iterate on the corpus with hyperparameters fixed, "
              "so the difference stays attributable to the data swap.")
        sys.exit(1)


if __name__ == "__main__":
    main()
