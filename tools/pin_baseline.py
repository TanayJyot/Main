"""
Capture everything needed to reproduce the current SHHQ-trained run.

Run this on the training machine, against the existing setup, BEFORE changing
any data. Once SHHQ is out of the picture the baseline cannot be rebuilt, so
whatever this does not record is lost.

    python pin_baseline.py --pose_to_video ~/src/pose-to-video \
        --checkpoint ~/runs/baseline/checkpoint-20 \
        --train_zip ~/data/frames.zip \
        --out runs/baseline/baseline.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import zipfile
from typing import Dict, List, Optional

# The upstream training configuration, recorded here so a mismatch is visible
# rather than assumed. Verify against the actual train.sh on the machine —
# if they differ, the file on disk is the truth and this is stale.
EXPECTED_TRAIN_CONFIG = {
    "pretrained_model": "runwayml/stable-diffusion-v1-5",
    "controlnet_model": "lllyasviel/sd-controlnet-openpose",
    "resolution": 512,
    "learning_rate": "1e-5",
    "num_train_epochs": 20,
    "train_batch_size": 4,
    "output_repo": "sign/sd-controlnet-mediapipe",
}


def run(command: List[str], cwd: Optional[str] = None) -> str:
    try:
        return subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                              timeout=120).stdout.strip()
    except Exception as error:
        return f"<failed: {error}>"


def git_state(repo_path: str) -> Dict[str, str]:
    if not os.path.isdir(repo_path):
        return {"error": f"not a directory: {repo_path}"}
    return {
        "path": os.path.abspath(repo_path),
        "commit": run(["git", "rev-parse", "HEAD"], repo_path),
        "branch": run(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo_path),
        "dirty": bool(run(["git", "status", "--porcelain"], repo_path)),
        "remote": run(["git", "remote", "get-url", "origin"], repo_path),
    }


def file_digest(path: str, chunk_size: int = 1 << 20) -> Dict[str, object]:
    """Hash a file. For a multi-GB checkpoint this is slow but worth it once."""
    if not os.path.exists(path):
        return {"path": path, "error": "missing"}
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return {"path": os.path.abspath(path), "sha256": digest.hexdigest(),
            "bytes": os.path.getsize(path)}


def directory_digest(path: str, suffixes=(".safetensors", ".bin", ".json", ".yaml")) -> Dict[str, object]:
    """Hash the weight and config files in a checkpoint directory."""
    if not os.path.isdir(path):
        return file_digest(path)
    entries = {}
    for root, _, filenames in os.walk(path):
        for filename in sorted(filenames):
            if filename.endswith(suffixes):
                full = os.path.join(root, filename)
                entries[os.path.relpath(full, path)] = file_digest(full)
    return {"path": os.path.abspath(path), "files": entries}


def zip_inventory(path: str) -> Dict[str, object]:
    """What actually went into training, and how much of it.

    Worth checking against expectations: upstream's shhq_to_images.py wraps its
    loop in itertools.islice(files, 0, 2), so an unpatched run contributes two
    SHHQ images rather than 40,000. If this count is tiny, that is why — and
    the SHHQ replacement is correspondingly easy.
    """
    if not os.path.exists(path):
        return {"path": path, "error": "missing"}
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
    prefixes: Dict[str, int] = {}
    for name in names:
        prefix = name.split("/")[0] if "/" in name else ""
        prefixes[prefix] = prefixes.get(prefix, 0) + 1
    return {
        "path": os.path.abspath(path),
        "entries": len(names),
        "bytes": os.path.getsize(path),
        "top_level_prefixes": dict(sorted(prefixes.items())[:20]),
        "sample": names[:5],
    }


def environment() -> Dict[str, object]:
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "pip_freeze": run([sys.executable, "-m", "pip", "freeze"]).splitlines(),
        "nvidia_smi": run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                           "--format=csv,noheader"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Pin the current training run for reproducibility.")
    parser.add_argument("--pose_to_video", default="", help="Path to a pose-to-video checkout")
    parser.add_argument("--checkpoint", default="", help="Trained weights file or directory")
    parser.add_argument("--train_zip", default="", help="The frames.zip the model was trained on")
    parser.add_argument("--train_sh", default="", help="The train.sh actually used")
    parser.add_argument("--eval_report", default="", help="report.json from run_eval.py")
    parser.add_argument("--seed", type=int, default=None, help="Training seed, if one was set")
    parser.add_argument("--out", default="runs/baseline/baseline.json")
    args = parser.parse_args()

    record: Dict[str, object] = {
        "expected_train_config": EXPECTED_TRAIN_CONFIG,
        "seed": args.seed,
        "environment": environment(),
        "aslytics_repo": git_state(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    }

    if args.pose_to_video:
        record["pose_to_video_repo"] = git_state(args.pose_to_video)
    if args.checkpoint:
        record["checkpoint"] = directory_digest(args.checkpoint)
    if args.train_zip:
        record["train_data"] = zip_inventory(args.train_zip)
    if args.train_sh and os.path.exists(args.train_sh):
        with open(args.train_sh, "r", encoding="utf-8") as handle:
            record["train_sh"] = handle.read()
    if args.eval_report and os.path.exists(args.eval_report):
        with open(args.eval_report, "r", encoding="utf-8") as handle:
            record["eval_report"] = json.load(handle)

    directory = os.path.dirname(args.out)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2)

    print(f"wrote {args.out}")
    missing = [name for name, value in
               [("pose_to_video", args.pose_to_video), ("checkpoint", args.checkpoint),
                ("train_zip", args.train_zip), ("eval_report", args.eval_report)]
               if not value]
    if missing:
        print(f"not captured: {', '.join(missing)} — fill these in before "
              f"retiring the SHHQ environment, they cannot be recovered later")

    train_data = record.get("train_data", {})
    if isinstance(train_data, dict) and isinstance(train_data.get("entries"), int) and train_data["entries"] < 100:
        print(f"\nNOTE: the training archive holds only {train_data['entries']} images. "
              f"Upstream's shhq_to_images.py processes just 2 files unless patched "
              f"(itertools.islice(files, 0, 2)) — check whether the SHHQ half of this "
              f"run was ever real.")


if __name__ == "__main__":
    main()
