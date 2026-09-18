"""
Check the training machine is ready before any GPU time is spent.

A ControlNet run at 512x512 for 20 epochs is hours of GPU. Discovering at hour
three that the checkpoint directory was unwritable, or that the training
archive holds two images, is the expensive way to learn it. Every check here
is cheap and runs on CPU.

    python tools/preflight.py \
        --pose_to_video ~/src/pose-to-video \
        --train_zip ~/data/frames-clean.zip \
        --output_dir ~/runs/clean-v1 \
        --manifest corpus/provenance.jsonl
"""

from __future__ import annotations

import argparse
import importlib
import os
import shutil
import subprocess
import sys
import zipfile
from typing import Callable, List, Optional, Tuple

OK, WARN, FAIL = "ok", "warn", "FAIL"

# 20 epochs of SD-1.5 ControlNet at 512x512 does not fit comfortably below this.
MIN_VRAM_GB = 16
MIN_DISK_GB = 60


class Checks:
    def __init__(self) -> None:
        self.results: List[Tuple[str, str, str]] = []

    def add(self, status: str, name: str, detail: str = "") -> None:
        self.results.append((status, name, detail))

    def run(self, name: str, fn: Callable[[], Tuple[str, str]]) -> None:
        try:
            status, detail = fn()
        except Exception as error:  # a broken check is a failed check
            status, detail = FAIL, f"check raised: {error}"
        self.add(status, name, detail)

    def report(self) -> int:
        width = max(len(name) for _, name, _ in self.results)
        for status, name, detail in self.results:
            print(f"  {status:>4}  {name.ljust(width)}  {detail}")
        failures = sum(1 for status, _, _ in self.results if status == FAIL)
        warnings = sum(1 for status, _, _ in self.results if status == WARN)
        print(f"\n{len(self.results) - failures - warnings} ok, {warnings} warning(s), {failures} failure(s)")
        if failures:
            print("\nFix the failures before starting a run.")
        return 1 if failures else 0


def check_gpu() -> Tuple[str, str]:
    if not shutil.which("nvidia-smi"):
        return FAIL, "nvidia-smi not found — no usable GPU"
    output = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
        capture_output=True, text=True, timeout=60).stdout.strip()
    if not output:
        return FAIL, "nvidia-smi returned nothing"

    lines = output.splitlines()
    detail = " | ".join(lines)
    memories = []
    for line in lines:
        parts = [part.strip() for part in line.split(",")]
        if len(parts) > 1 and parts[1].endswith("MiB"):
            memories.append(int(parts[1].removesuffix("MiB").strip()) / 1024)
    if memories and max(memories) < MIN_VRAM_GB:
        return WARN, f"{detail} — under {MIN_VRAM_GB}GB, expect to reduce batch size or use gradient checkpointing"
    return OK, detail


def check_torch_cuda() -> Tuple[str, str]:
    try:
        torch = importlib.import_module("torch")
    except ImportError:
        return FAIL, "torch not installed"
    if not torch.cuda.is_available():
        return FAIL, f"torch {torch.__version__} cannot see CUDA — a CPU-only build will not train this"
    return OK, f"torch {torch.__version__}, {torch.cuda.device_count()} device(s), CUDA {torch.version.cuda}"


def check_packages() -> Tuple[str, str]:
    required = ["diffusers", "accelerate", "transformers", "safetensors"]
    missing = [name for name in required if importlib.util.find_spec(name) is None]
    if missing:
        return FAIL, f"missing: {', '.join(missing)}"
    versions = []
    for name in required:
        try:
            versions.append(f"{name} {importlib.import_module(name).__version__}")
        except Exception:
            versions.append(name)
    return OK, ", ".join(versions)


def check_xformers() -> Tuple[str, str]:
    if importlib.util.find_spec("xformers") is None:
        return WARN, "xformers not installed — training will work but use more memory"
    return OK, "installed"


def check_mediapipe() -> Tuple[str, str]:
    """MediaPipe 1.0 dropped the Solutions API that pose-format still uses.

    A fresh `pip install mediapipe` on a new machine gets 1.x and breaks both
    the rendering pipeline and the eval harness — with an AttributeError deep
    in a worker, which is an expensive place to find out.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import mp_compat  # noqa: PLC0415

    try:
        import mediapipe  # noqa: PLC0415
    except ImportError:
        return FAIL, f"mediapipe not installed — need {mp_compat.REQUIRED_PIN}"

    version = getattr(mediapipe, "__version__", "unknown")
    if not mp_compat.available():
        return FAIL, (f"mediapipe {version} has no Solutions API (removed in 1.0). "
                      f"pose-format needs it. Install {mp_compat.REQUIRED_PIN}")
    return OK, f"mediapipe {version} with Solutions API"


def check_repo(path: str) -> Tuple[str, str]:
    if not path:
        return WARN, "not provided"
    if not os.path.isdir(path):
        return FAIL, f"not a directory: {path}"
    train_sh = os.path.join(path, "pose_to_video", "conditional", "controlnet", "train.sh")
    if not os.path.exists(train_sh):
        return WARN, f"found the checkout but not {os.path.relpath(train_sh, path)}"
    return OK, f"{path} (train.sh present)"


def check_train_zip(path: str) -> Tuple[str, str]:
    if not path:
        return WARN, "not provided"
    if not os.path.exists(path):
        return FAIL, f"missing: {path}"
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    except zipfile.BadZipFile:
        return FAIL, f"not a readable zip: {path}"

    images = [name for name in names if name.lower().endswith((".png", ".jpg", ".jpeg"))]
    size_gb = os.path.getsize(path) / (1 << 30)
    detail = f"{len(images)} images, {size_gb:.2f}GB"

    if len(images) < 100:
        return FAIL, (f"{detail} — far too few. Upstream's shhq_to_images.py processes only "
                      f"two files per run (itertools.islice(files, 0, 2)); if this archive "
                      f"came from it unpatched, that is why")
    return OK, detail


def check_provenance(path: str) -> Tuple[str, str]:
    """A training archive with unresolved licence checks is not shippable."""
    if not path:
        return WARN, "not provided — you will not be able to prove what the model was trained on"
    if not os.path.exists(path):
        return FAIL, f"missing: {path}"

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "corpus"))
    from provenance import Manifest, check_optout  # noqa: PLC0415

    manifest = Manifest(path)
    pending = check_optout(manifest)
    summary = manifest.summary()
    if pending:
        return FAIL, (f"{len(pending)} of {summary['total']} records still need a contributor "
                      f"opt-out check — resolve before training a shipping model")
    return OK, f"{summary['total']} records, all cleared ({summary['by_source']})"


def check_no_shhq_ancestry(output_dir: str, resume_from: str) -> Tuple[str, str]:
    """The one mistake that silently undoes the whole migration."""
    contaminated = "sd-controlnet-mediapipe"
    if resume_from and contaminated in resume_from:
        return FAIL, (f"resuming from {resume_from!r} carries the SHHQ derivation forward — "
                      f"retrain from scratch instead")
    if output_dir and contaminated in os.path.abspath(output_dir):
        return WARN, f"output path mentions {contaminated!r}; make sure this is a fresh run"
    return OK, "no resume from an SHHQ-derived checkpoint"


def check_disk(path: str) -> Tuple[str, str]:
    target = path or os.getcwd()
    while target and not os.path.exists(target):
        parent = os.path.dirname(target)
        if parent == target:
            break
        target = parent
    usage = shutil.disk_usage(target or os.getcwd())
    free_gb = usage.free / (1 << 30)
    detail = f"{free_gb:.1f}GB free at {target}"
    if free_gb < MIN_DISK_GB:
        return FAIL, f"{detail} — checkpoints alone will exceed this"
    return OK, detail


def check_writable(path: str) -> Tuple[str, str]:
    if not path:
        return WARN, "not provided"
    os.makedirs(path, exist_ok=True)
    probe = os.path.join(path, ".preflight-probe")
    try:
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("ok")
        os.remove(probe)
    except OSError as error:
        return FAIL, f"not writable: {error}"
    return OK, path


def check_eval_assets(poses_dir: str, baseline_report: str) -> Tuple[str, str]:
    """You cannot claim you matched a baseline you never recorded."""
    problems = []
    if poses_dir and not os.path.isdir(poses_dir):
        problems.append(f"no conditioning poses at {poses_dir}")
    if baseline_report and not os.path.exists(baseline_report):
        problems.append(f"no baseline report at {baseline_report}")
    if not poses_dir and not baseline_report:
        return WARN, "not provided — run Phase 0 before training a candidate"
    if problems:
        return FAIL, "; ".join(problems)
    return OK, "conditioning poses and baseline report present"


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-flight checks before a training run.")
    parser.add_argument("--pose_to_video", default="")
    parser.add_argument("--train_zip", default="")
    parser.add_argument("--manifest", default="")
    parser.add_argument("--output_dir", default="")
    parser.add_argument("--resume_from", default="", help="Checkpoint you intend to resume from, if any")
    parser.add_argument("--poses", default="", help="Conditioning .pose directory used for eval")
    parser.add_argument("--baseline_report", default="", help="runs/baseline/report.json")
    args = parser.parse_args()

    print("pre-flight\n")
    checks = Checks()
    checks.run("gpu", check_gpu)
    checks.run("torch + cuda", check_torch_cuda)
    checks.run("training packages", check_packages)
    checks.run("xformers", check_xformers)
    checks.run("mediapipe api", check_mediapipe)
    checks.run("pose-to-video checkout", lambda: check_repo(args.pose_to_video))
    checks.run("training archive", lambda: check_train_zip(args.train_zip))
    checks.run("provenance", lambda: check_provenance(args.manifest))
    checks.run("no SHHQ ancestry", lambda: check_no_shhq_ancestry(args.output_dir, args.resume_from))
    checks.run("disk space", lambda: check_disk(args.output_dir))
    checks.run("output writable", lambda: check_writable(args.output_dir))
    checks.run("eval assets", lambda: check_eval_assets(args.poses, args.baseline_report))

    sys.exit(checks.report())


if __name__ == "__main__":
    main()
