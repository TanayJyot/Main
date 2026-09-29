"""Build the baseline artefacts from the old lexicon.

Part 3 blocker #1: the original "results" were a demo, nothing was measured.
This renders a fixed set of inputs through the *old* pipeline so a signer can
score them later, and so any replacement lexicon is compared against the same
inputs.

Two artefact sets:

  signs/       one clip per gloss in ../coverage/pilot_200.txt -- for blind
               recognition (step 6 of the plan)
  sentences/   the fixed sentence set below, concatenated with
               concatenate.py exactly as main.sh did -- for end-to-end A/B
               (step 8)

The gloss step is hand-written. text-to-gloss/start.py cannot run here (it
needs the Azure Speech SDK and the dead stanfordnlp package), so the sentence
set is already in gloss form using only words the lexicon has. The script
refuses to run if any gloss is missing, so the set cannot silently drift.

This is evaluation use of non-commercial data. Nothing here ships.

Usage:
    ASLYTICS_LEXICON_DIR=<path to generated_pose> python build_baseline.py [--signs-only]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import cv2
from pose_format import Pose
from pose_format.pose_visualizer import PoseVisualizer

HERE = Path(__file__).parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "pose-master" / "pose-master" / "concatenate_pose_function"))
import concatenate  # noqa: E402  (the original module, reads ASLYTICS_LEXICON_DIR)

POSE_DIR = Path(concatenate.lexicon_dir())

# Fixed sentence set. Gloss order is English order, which is what the old
# pipeline produced for simple sentences. Every token must exist as
# <token>.pose in the lexicon.
SENTENCES = {
    "s01": ["i", "love", "my", "family"],
    "s02": ["my", "mother", "cook", "dinner"],
    "s03": ["dog", "eat", "breakfast"],
    "s04": ["children", "play", "game"],
    "s05": ["i", "go", "hospital", "monday"],
    "s06": ["boy", "drink", "milk"],
    "s07": ["i", "learn", "english"],
    "s08": ["police", "help", "people"],
    "s09": ["girl", "paint", "house"],
    "s10": ["grandmother", "make", "cookie"],
    "s11": ["cat", "hide", "behind", "chair"],
    "s12": ["man", "buy", "new", "car"],
}


def read_pilot() -> list[str]:
    out = []
    for line in (HERE.parent / "coverage" / "pilot_200.txt").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def render(pose: Pose, path: Path) -> int:
    """Write the stick-figure render with OpenCV. pose-format's own save_video
    needs vidgear + an ffmpeg binary; this needs neither."""
    vis = PoseVisualizer(pose)
    writer = None
    n = 0
    for frame in vis.draw():
        if writer is None:
            h, w = frame.shape[:2]
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), float(pose.body.fps), (w, h))
        writer.write(frame)
        n += 1
    if writer is not None:
        writer.release()
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--signs-only", action="store_true")
    ap.add_argument("--out", default=str(HERE / "out"))
    args = ap.parse_args()
    out = Path(args.out)

    if not POSE_DIR.is_dir():
        sys.exit(f"lexicon not found at {POSE_DIR}; set ASLYTICS_LEXICON_DIR")

    pilot = read_pilot()
    needed = set(pilot) | {g for s in SENTENCES.values() for g in s}
    missing = sorted(g for g in needed if not (POSE_DIR / f"{g}.pose").exists())
    if missing:
        sys.exit(f"{len(missing)} glosses not in lexicon: {missing[:20]}")

    manifest = {"lexicon": str(POSE_DIR), "n_lexicon": len(list(POSE_DIR.glob("*.pose"))),
                "signs": {}, "sentences": {}}

    (out / "signs").mkdir(parents=True, exist_ok=True)
    for i, g in enumerate(pilot, 1):
        pose = concatenate.load_pose(str(POSE_DIR / f"{g}.pose"))
        n = render(pose, out / "signs" / f"{g}.mp4")
        manifest["signs"][g] = {"frames": n, "fps": pose.body.fps}
        if i % 25 == 0:
            print(f"  signs {i}/{len(pilot)}")

    if not args.signs_only:
        (out / "sentences").mkdir(parents=True, exist_ok=True)
        for sid, glosses in SENTENCES.items():
            poses = concatenate.gloss_to_pose(glosses)
            pose = concatenate.concatenate_poses(poses)
            concatenate.save_pose(pose, str(out / "sentences" / f"{sid}.pose"))
            n = render(pose, out / "sentences" / f"{sid}.mp4")
            manifest["sentences"][sid] = {"gloss": glosses, "frames": n, "fps": pose.body.fps}
            print(f"  {sid}: {' '.join(glosses)}  ({n} frames)")

    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
