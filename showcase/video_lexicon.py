"""Turn a folder of sign videos named by word into a lexicon.

For dictionary-style sources such as Signing Savvy: one clip per word, already
downloaded (by a source-specific fetcher) into a folder as

    <word>.mp4          or, when the source has several signs for a word,
    <word>__<n>.mp4     n = the source's own variant number (1 = its first)

    python showcase/video_lexicon.py --videos .work/signingsavvy/videos \\
        --out lexicon/signingsavvy --source "Signing Savvy" \\
        --license "Non-commercial use only, by permission of Signing Savvy" --non-commercial \\
        --credit "Signs from Signing Savvy (signingsavvy.com), used with permission."

Each word takes the source's first variant: variants are usually different
signs for different meanings, so the source's own order is the only safe
choice without a signer to judge. Clips are converted with MediaPipe Holistic
(mediapipe==0.10.21), mirrored to right-handed when signed left-handed,
trimmed to the moving part, and dropped if the hands were barely tracked;
the same steps as PopSign and ASL Citizen. Output carries a .gitignore of "*".
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "prototype"))

import citizen  # noqa: E402  (shares conversion, choice and trimming)

NAME = re.compile(r"^([a-z0-9]+)(?:__(\d+))?$")


def variants(videos: Path) -> Dict[str, List[Tuple[int, Path]]]:
    """word -> [(variant number, video)], lowest first. Other names are ignored."""
    out: Dict[str, List[Tuple[int, Path]]] = defaultdict(list)
    for video in sorted(videos.glob("*.mp4")):
        match = NAME.match(video.stem.lower())
        if match:
            out[match.group(1)].append((int(match.group(2) or 1), video))
    return {word: sorted(found) for word, found in sorted(out.items())}


def convert(videos: Path, poses: Path, workers: int) -> int:
    todo = [(v, poses / (v.stem + ".pose")) for v in sorted(videos.glob("*.mp4"))]
    todo = [(s, t) for s, t in todo if not t.exists()]
    print(f"{len(todo)} clips to convert with {workers} workers", flush=True)
    failed = []
    with ProcessPoolExecutor(workers) as pool:
        futures = [pool.submit(citizen._convert_one, str(s), str(t)) for s, t in todo]
        for i, future in enumerate(as_completed(futures), 1):
            if error := future.result():
                failed.append(error)
            if i % 200 == 0 or i == len(futures):
                print(f"  {i}/{len(futures)} ({len(failed)} failed)", flush=True)
    if failed:
        poses.mkdir(parents=True, exist_ok=True)
        with open(poses / "failed.txt", "a", encoding="utf8") as handle:
            handle.write("\n".join(failed) + "\n")
    return len(todo) - len(failed)


def export(videos: Path, poses: Path, out_dir: Path, source: str, license_text: str, credit: str,
           non_commercial: bool, min_presence: float = citizen.MIN_PRESENCE) -> Dict[str, object]:
    from handedness import mirror

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / ".gitignore").write_text("*\n", encoding="utf-8")
    built, missing, rejected, picks = {}, [], {}, {}
    for word, found in variants(videos).items():
        number, video = found[0]
        best = citizen.choose([p for p in [poses / (video.stem + ".pose")] if p.exists()])
        if best is None:
            missing.append(word)
            continue
        pose, result, path = best
        if result["dominant"] == "LEFT":
            pose = mirror(pose)
        data, presence, before, after = citizen._prepare(pose)
        if presence < min_presence:
            rejected[word] = round(presence, 3)
            continue
        (out_dir / f"{word}.pose").write_bytes(data)
        built[word] = video.name
        picks[word] = {"clip": video.name, "variant": number, "variants": len(found),
                       "mirrored": result["dominant"] == "LEFT", "presence": round(presence, 3),
                       "seconds_before_after_trim": [before, after]}

    restriction = "\n\nNON-COMMERCIAL USE ONLY." if non_commercial else ""
    (out_dir / "ATTRIBUTION.txt").write_text(
        f"{credit}{restriction}\n\nChanges: converted to MediaPipe Holistic landmarks (.pose); the "
        "source's first sign per word; left-handed clips mirrored; trimmed to the signing.\n",
        encoding="utf-8")
    manifest = {"source": source, "license": license_text, "non_commercial": non_commercial,
                "words": built, "missing": missing, "rejected_low_hand_presence": rejected,
                "min_presence": min_presence, "picks": picks}
    (out_dir / "lexicon.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--videos", type=Path, required=True, help="Folder of <word>.mp4 / <word>__<n>.mp4")
    parser.add_argument("--poses", type=Path, help="Where converted .pose files go (default: beside --videos)")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source", required=True, help="Source name, shown on pages and videos")
    parser.add_argument("--license", required=True, help="Licence or permission, shown on pages")
    parser.add_argument("--credit", required=True, help="Credit line written to ATTRIBUTION.txt")
    parser.add_argument("--non-commercial", action="store_true", help="Mark the lexicon non-commercial")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    parser.add_argument("--min-presence", type=float, default=citizen.MIN_PRESENCE)
    parser.add_argument("--skip-convert", action="store_true")
    args = parser.parse_args()
    if not args.videos.is_dir():
        parser.error(f"no such folder: {args.videos}")
    poses = args.poses or args.videos.parent / "pose"
    if not args.skip_convert:
        convert(args.videos, poses, args.workers)
    manifest = export(args.videos, poses, args.out, args.source, args.license, args.credit,
                      args.non_commercial, args.min_presence)
    print(f"{len(manifest['words'])} words -> {args.out}; {len(manifest['missing'])} unconverted, "
          f"{len(manifest['rejected_low_hand_presence'])} barely tracked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
