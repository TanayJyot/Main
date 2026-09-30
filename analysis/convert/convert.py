"""Convert downloaded clips to .pose, in parallel.

Same call as pose-format's `video_to_pose --format mediapipe`, run in-process
so a worker pays MediaPipe's startup once per process instead of once per clip.
Requires mediapipe==0.10.21 (see HANDOFF.md section 5).

Output matches analysis/old_lexicon_pose_spec.json: full Holistic, 5
components, 576 points, XYZC. check_spec() verifies every file.

    data/aslc/videos/<id>-<GLOSS>.mp4   -> data/pose/aslc/<id>-<GLOSS>.pose
                                           (only labels.citizen_candidates())
    data/popsign/<sign>/<clip>.mp4      -> data/pose/popsign/<sign>/<clip>.pose

Re-running skips clips already converted. Failures are logged to
data/pose/failed.txt and do not stop the run.

Usage:
    python convert.py [--workers N]
    python convert.py --popsign-only --max-signers 6        (prototype)
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from labels import citizen_candidates

HERE = Path(__file__).parent
DATA = HERE / "data"
SPEC = HERE.parent / "old_lexicon_pose_spec.json"


def popsign_clips(max_signers: int | None = None) -> list[Path]:
    """PopSign clips on disk; with max_signers, only each label's first
    max_signers signers in ID order (the prototype's content-blind cap)."""
    from fetch import signer

    out = []
    # Only labels whose download finished: fetch.py writes .done last.
    for label_dir in sorted(p for p in (DATA / "popsign").iterdir() if (p / ".done").exists()):
        clips = sorted(label_dir.glob("*.mp4"))
        keep = sorted({signer(c.name) for c in clips})[:max_signers]
        out += [c for c in clips if signer(c.name) in keep]
    return out


def jobs(popsign_only: bool = False, max_signers: int | None = None) -> list[tuple[Path, Path]]:
    out = []
    if not popsign_only:
        for name in sorted(citizen_candidates()):
            mp4 = DATA / "aslc" / "videos" / name
            out.append((mp4, DATA / "pose" / "aslc" / (mp4.stem + ".pose")))
    for mp4 in popsign_clips(max_signers):
        out.append((mp4, DATA / "pose" / "popsign" / mp4.parent.name / (mp4.stem + ".pose")))
    return [(src, dst) for src, dst in out if not dst.exists()]


def convert_one(src: str, dst: str) -> str | None:
    os.environ.setdefault("GLOG_minloglevel", "2")
    from pose_format.bin.pose_estimation import pose_video
    try:
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        tmp = dst + ".part"
        with contextlib.redirect_stdout(io.StringIO()):
            pose_video(src, tmp, "mediapipe", progress=False)
        os.replace(tmp, dst)
        return None
    except Exception as e:  # noqa: BLE001 - one bad clip must not stop the batch
        return f"{src}\t{type(e).__name__}: {e}"


def check_spec(pose_path: Path, expected: list[tuple[str, int, str]]) -> str | None:
    from pose_format import Pose
    pose = Pose.read(pose_path.read_bytes())
    got = [(c.name, len(c.points), c.format) for c in pose.header.components]
    return None if got == expected else f"{pose_path}: {got}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--popsign-only", action="store_true")
    ap.add_argument("--max-signers", type=int, default=None)
    args = ap.parse_args()

    todo = jobs(args.popsign_only, args.max_signers)
    print(f"{len(todo)} clips to convert with {args.workers} workers", flush=True)
    failed = []
    with ProcessPoolExecutor(args.workers) as pool:
        futures = [pool.submit(convert_one, str(s), str(d)) for s, d in todo]
        for i, f in enumerate(as_completed(futures), 1):
            if err := f.result():
                failed.append(err)
            if i % 100 == 0 or i == len(futures):
                print(f"  {i}/{len(futures)} ({len(failed)} failed)", flush=True)
    if failed:
        (DATA / "pose").mkdir(parents=True, exist_ok=True)
        with open(DATA / "pose" / "failed.txt", "a", encoding="utf8") as f:
            f.write("\n".join(failed) + "\n")

    spec = json.loads(SPEC.read_text(encoding="utf8"))["specs"][0]["components"]
    expected = [(c["name"], c["points"], c["format"]) for c in spec]
    bad = [e for p in sorted((DATA / "pose").rglob("*.pose")) if (e := check_spec(p, expected))]
    print(f"spec check: {len(bad)} mismatches")
    for b in bad[:10]:
        print("  " + b)


if __name__ == "__main__":
    main()
