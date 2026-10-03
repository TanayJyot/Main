"""Natural signing: a whole sentence signed by a fluent signer, as a skeleton.

ASLytics strings one sign per word together. A Deaf translator signs the whole
sentence: ASL word order, facial grammar, signs flowing into each other. This
puts the two next to each other, drawn the same way, so people can see the gap
a sentence-level dataset would close.

Sources that allow this (sentence videos by Deaf translators, with English):

  2M-Flores-ASL (Meta, CC BY-SA 4.0)  huggingface.co/datasets/facebook/2M-Flores-ASL
  FLEURS-ASL    (Google, CC BY-SA 4.0) kaggle.com/datasets/googleai/fleurs-asl

Put clips in a folder as <name>.mp4 with the English sentence in <name>.txt
(and, if the dataset has one, its gloss in <name>.gloss.txt). Then:

    python showcase/natural.py --clips data/natural --out .work/showcase/natural

writes <name>.mp4 skeleton renders and natural.json, which run_showcase.py
--natural picks up. Needs mediapipe==0.10.21, like the lexicon conversion.
Derived from CC BY-SA data, so the renders must be credited and shared alike;
they are still not committed here.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent


def to_pose(video: Path, target: Path) -> Path:
    os.environ.setdefault("GLOG_minloglevel", "2")
    from pose_format.bin.pose_estimation import pose_video

    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        with contextlib.redirect_stdout(io.StringIO()):
            pose_video(str(video), str(target) + ".part", "mediapipe", progress=False)
        os.replace(str(target) + ".part", target)
    return target


def render(pose_path: Path, video: Path) -> Path:
    """Draw the pose exactly as the pipeline draws a sentence of signs: through
    concatenate_poses (same reduction, normalisation and smoothing) and
    PoseVisualizer, so the only difference people see is the signing."""
    sys.path.insert(0, str(REPO_ROOT))
    from pose_format import Pose
    from pose_format.pose_visualizer import PoseVisualizer

    from asl_renderer import concatenate_poses

    pose = concatenate_poses([Pose.read(pose_path.read_bytes())])
    visualizer = PoseVisualizer(pose)
    visualizer.save_video(str(video), visualizer.draw())
    return video


def build(clips: Path, out: Path, source: str = "2M-Flores-ASL (CC BY-SA 4.0)") -> List[Dict[str, str]]:
    out.mkdir(parents=True, exist_ok=True)
    (out / ".gitignore").write_text("*\n", encoding="utf-8")
    entries = []
    for video in sorted(clips.glob("*.mp4")):
        text_file = video.with_suffix(".txt")
        if not text_file.exists():
            print(f"  skip {video.name}: no {text_file.name}", file=sys.stderr)
            continue
        gloss_file = video.with_name(video.stem + ".gloss.txt")
        try:
            pose_path = to_pose(video, out / f"{video.stem}.pose")
            rendered = render(pose_path, out / f"{video.stem}.raw.mp4")
        except Exception as error:  # noqa: BLE001 - one bad clip must not stop the rest
            print(f"  skip {video.name}: {type(error).__name__}: {error}", file=sys.stderr)
            continue
        entries.append({"name": video.stem, "source": source, "sentence": text_file.read_text(encoding="utf-8").strip(),
                        "gloss": gloss_file.read_text(encoding="utf-8").strip() if gloss_file.exists() else "",
                        "video": str(rendered)})
        print(f"  {video.stem}: {entries[-1]['sentence'][:70]}")
    (out / "natural.json").write_text(json.dumps(entries, indent=1), encoding="utf-8")
    return entries


def load(folder: Path) -> List[Dict[str, str]]:
    try:
        return json.loads((folder / "natural.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--clips", type=Path, required=True, help="Folder of <name>.mp4 + <name>.txt")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / ".work" / "showcase" / "natural")
    parser.add_argument("--source", default="2M-Flores-ASL (CC BY-SA 4.0)",
                        help="Dataset and licence, shown as the panel's credit")
    args = parser.parse_args()
    entries = build(args.clips, args.out, args.source)
    print(f"{len(entries)} sentences -> {args.out}")
    return 0 if entries else 1


if __name__ == "__main__":
    sys.exit(main())
