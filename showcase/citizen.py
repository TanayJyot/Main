"""Every ASL Citizen sign as a lexicon, for the research preview only.

ASL Citizen (Microsoft Research, 2023) has 2,731 signs recorded by 52 Deaf
and hard-of-hearing signers on their own webcams. Its licence allows research
use only and forbids distributing the data "or your modifications". So:

  - this runs on the laptop, and everything it makes stays there
    (.work/aslc and the --out folder both carry a .gitignore of "*");
  - the lexicon is marked research_only in its lexicon.json, and every page
    that shows it says so;
  - it is for showing people what a large, well-recorded vocabulary makes
    possible, never for the product.

Steps (each re-runnable; finished work is skipped):

    python showcase/citizen.py fetch     # split CSVs + up to 3 signers' clips per sign (~4.5 GB)
    python showcase/citizen.py convert   # MediaPipe Holistic -> .pose (~1-2 h on the laptop)
    python showcase/citizen.py export --out lexicon/aslc

Clip choice is content-blind, as for PopSign: per sign, the first
--max-signers participants in ID order, each participant's first clip by
filename; of those, the one whose signing hand was tracked in the most frames
(showcase/handedness.py). Left-handed clips are mirrored, each clip is trimmed
to its moving part (prototype/trim.py), and clips whose hands were barely
tracked are left out.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT / "prototype"))

ASLC_URL = ("https://download.microsoft.com/download/b/8/8/"
            "b88c0bae-e6c1-43e1-8726-98cf5af36ca4/ASL_Citizen.zip")
DATA = REPO_ROOT / ".work" / "aslc"
MAX_SIGNERS = 3
MIN_PRESENCE = 0.3        # same floor as the PopSign prototype

LICENSE = "Research use only (Microsoft Research licence); not for distribution or commercial use"

ATTRIBUTION = """\
Signs in this directory are derived from ASL Citizen (Microsoft Research):
A. Desai, L. Berger, F. O. Minakov, V. Milan, C. Singh, K. Pumphrey,
R. E. Ladner, H. Daumé III, A. X. Lu, N. Caselli, D. Bragg. "ASL Citizen: A
Community-Sourced Dataset for Advancing Isolated Sign Language Recognition."
NeurIPS 2023 Datasets and Benchmarks. https://www.microsoft.com/en-us/research/project/asl-citizen/

RESEARCH USE ONLY. ASL Citizen's licence does not permit distributing the
data or modifications of it, or commercial use. Show these signs only as a
research preview, from this machine; do not copy them elsewhere.

Changes: each video was converted to MediaPipe Holistic landmarks (.pose); one
clip per sign was chosen by hand-landmark presence; left-handed clips were
mirrored to right-handed; clips were trimmed to the signing; files were
renamed to the English words they sign.
"""

# Labels whose words differ from the label itself. Only the same sign: ME is
# the sign for "I"; THANKYOU is what "thank you" is signed with.
ALIASES: Dict[str, List[str]] = {
    "me": ["me", "i"],
    "thankyou": ["thank"],
}


# -- labels -> words --------------------------------------------------------------

def words_for(label: str) -> Tuple[int, int, List[str]]:
    """(rank, variant number, words) for one ASL Citizen gloss label.

    rank 0: a plain label (DOG), 1: a numbered variant (WANT1, WANT2),
    2: anything spelled with punctuation (THIS/IT, W.H.A.T, SKI-CA). When two
    labels give the same word, the lower (rank, variant) wins, so WANT1 is
    used for "want" and WHAT1 before the fingerspelled W.H.A.T.
    """
    match = re.fullmatch(r"(.*?)(\d*)", label.strip())
    base, digits = match.group(1), match.group(2)
    rank = 2 if re.search(r"[^A-Za-z]", base) else (1 if digits else 0)
    words = []
    for alternative in base.split("/"):
        word = alternative.lower().replace(".", "")
        word = re.sub(r"-(ca|cl)$", "", word)        # constructed action / classifier forms
        if re.fullmatch(r"[a-z]+", word):            # multi-word labels (STAND-UP) cannot match one gloss
            words += ALIASES.get(word, [word])
    return rank, int(digits) if digits else 0, words


def word_table(labels: Iterable[str]) -> Dict[str, str]:
    """word -> the label that signs it."""
    best: Dict[str, Tuple[Tuple[int, int, str], str]] = {}
    for label in labels:
        rank, variant, words = words_for(label)
        for word in words:
            key = (rank, variant, label)
            if word not in best or key < best[word][0]:
                best[word] = (key, label)
    return {word: label for word, (_, label) in sorted(best.items())}


# -- the split CSVs -----------------------------------------------------------------

def rows(data: Path = DATA) -> List[Dict[str, str]]:
    """Every clip: {"Participant ID", "Video file", "Gloss", ...}, from the zip's split CSVs."""
    splits = data / "splits"
    names = ["train.csv", "val.csv", "test.csv"]
    if not all((splits / n).exists() for n in names):
        from remotezip import RemoteZip
        splits.mkdir(parents=True, exist_ok=True)
        with RemoteZip(ASLC_URL, support_suffix_range=False) as archive:
            for name in names:
                (splits / name).write_bytes(archive.read(f"ASL_Citizen/splits/{name}"))
            (data / "use.txt").write_bytes(archive.read("ASL_Citizen/use.txt"))
    out = []
    for name in names:
        with open(splits / name, encoding="utf8", newline="") as handle:
            out += list(csv.DictReader(handle))
    return out


def _participant_order(participant: str):
    digits = re.sub(r"\D", "", participant)
    return (int(digits) if digits else 10 ** 6, participant)


def candidates(all_rows: List[Dict[str, str]], labels: Iterable[str],
               max_signers: int = MAX_SIGNERS) -> Dict[str, List[str]]:
    """label -> video files: the first max_signers participants by ID, one clip each."""
    wanted = set(labels)
    by_label: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))
    for row in all_rows:
        if row["Gloss"] in wanted:
            by_label[row["Gloss"]][row["Participant ID"]].append(row["Video file"])
    return {label: [sorted(clips[p])[0] for p in sorted(clips, key=_participant_order)[:max_signers]]
            for label, clips in sorted(by_label.items())}


def plan(data: Path = DATA, max_signers: int = MAX_SIGNERS):
    all_rows = rows(data)
    table = word_table({row["Gloss"] for row in all_rows})
    return table, candidates(all_rows, set(table.values()), max_signers)


# -- fetch and convert -------------------------------------------------------------

def _retry(fn, attempts: int = 6):
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as error:  # noqa: BLE001 - re-raised on the last attempt
            if getattr(error, "code", None) == 404 or attempt == attempts - 1:
                raise
            time.sleep(2 ** attempt)


def fetch(data: Path = DATA, max_signers: int = MAX_SIGNERS, workers: int = 8) -> int:
    """Download the candidate clips (~0.55 MB each) out of the 42.8 GB zip by HTTP Range."""
    from remotezip import RemoteZip

    _, chosen = plan(data, max_signers)
    videos = data / "videos"
    videos.mkdir(parents=True, exist_ok=True)
    todo = [v for clips in chosen.values() for v in clips if not (videos / v).exists()]
    print(f"ASL Citizen: {sum(map(len, chosen.values()))} clips for {len(chosen)} signs; "
          f"{len(todo)} to download", flush=True)

    def worker(chunk: List[str]) -> int:
        archive = _retry(lambda: RemoteZip(ASLC_URL, support_suffix_range=False))
        for i, name in enumerate(chunk):
            part = videos / (name + ".part")
            part.write_bytes(_retry(lambda: archive.read(f"ASL_Citizen/videos/{name}")))
            part.replace(videos / name)
            if i % 200 == 0:
                print(f"  {name}", flush=True)
        archive.close()
        return len(chunk)

    chunks = [c for c in (todo[i::workers] for i in range(workers)) if c]
    with ThreadPoolExecutor(max(1, len(chunks))) as pool:
        done = sum(pool.map(worker, chunks))
    print(f"ASL Citizen: downloaded {done}")
    return done


def _convert_one(source: str, target: str):
    os.environ.setdefault("GLOG_minloglevel", "2")
    import contextlib
    import io

    from pose_format.bin.pose_estimation import pose_video
    try:
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        part = target + ".part"
        with contextlib.redirect_stdout(io.StringIO()):
            pose_video(source, part, "mediapipe", progress=False)
        os.replace(part, target)
        return None
    except Exception as error:  # noqa: BLE001 - one bad clip must not stop the batch
        return f"{source}\t{type(error).__name__}: {error}"


def convert(data: Path = DATA, workers: int = max(1, (os.cpu_count() or 2) - 2)) -> int:
    """mp4 -> .pose with MediaPipe Holistic (mediapipe==0.10.21, as for PopSign)."""
    todo = [(v, data / "pose" / (v.stem + ".pose")) for v in sorted((data / "videos").glob("*.mp4"))]
    todo = [(s, t) for s, t in todo if not t.exists()]
    print(f"{len(todo)} clips to convert with {workers} workers", flush=True)
    failed = []
    with ProcessPoolExecutor(workers) as pool:
        futures = [pool.submit(_convert_one, str(s), str(t)) for s, t in todo]
        for i, future in enumerate(as_completed(futures), 1):
            if error := future.result():
                failed.append(error)
            if i % 200 == 0 or i == len(futures):
                print(f"  {i}/{len(futures)} ({len(failed)} failed)", flush=True)
    if failed:
        with open(data / "pose" / "failed.txt", "a", encoding="utf8") as handle:
            handle.write("\n".join(failed) + "\n")
    return len(todo) - len(failed)


# -- export -------------------------------------------------------------------------

def _prepare(pose):
    """(trimmed .pose bytes, hand presence after trimming, seconds before, after)."""
    import trim as trimming

    fps = float(pose.body.fps) or 30.0
    pose, before, after = trimming.trim_to_signing(pose)
    buffer = BytesIO()
    pose.write(buffer)
    return buffer.getvalue(), trimming.hand_presence(pose), round(before / fps, 2), round(after / fps, 2)


def choose(paths: List[Path]):
    """(best Pose, its score, its path), or None if none could be read."""
    from pose_format import Pose

    from handedness import score

    scored = []
    for path in paths:
        try:
            pose = Pose.read(path.read_bytes())
            scored.append((score(pose), path, pose))
        except Exception as error:  # noqa: BLE001 - an unreadable clip is skipped
            print(f"  skip {path.name}: {error}", file=sys.stderr)
    if not scored:
        return None
    result, path, pose = min(scored, key=lambda s: (-s[0]["presence"], -s[0]["visibility"], s[1].name))
    return pose, result, path


def export(out_dir: Path, data: Path = DATA, max_signers: int = MAX_SIGNERS,
           min_presence: float = MIN_PRESENCE, table=None, chosen=None) -> Dict[str, object]:
    from handedness import mirror

    if table is None or chosen is None:
        table, chosen = plan(data, max_signers)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / ".gitignore").write_text("*\n", encoding="utf-8")
    words_by_label: Dict[str, List[str]] = defaultdict(list)
    for word, label in table.items():
        words_by_label[label].append(word)

    built, missing, rejected, picks = {}, [], {}, {}
    for label, words in sorted(words_by_label.items()):
        paths = [data / "pose" / (Path(v).stem + ".pose") for v in chosen.get(label, [])]
        best = choose([p for p in paths if p.exists()])
        if best is None:
            missing.append(label)
            continue
        pose, result, path = best
        if result["dominant"] == "LEFT":
            pose = mirror(pose)
        data_bytes, presence, before, after = _prepare(pose)
        if presence < min_presence:
            rejected[label] = round(presence, 3)
            continue
        for word in words:
            (out_dir / f"{word}.pose").write_bytes(data_bytes)
            built[word] = label
        picks[label] = {"clip": path.name, "mirrored": result["dominant"] == "LEFT",
                        "presence": round(presence, 3), "candidates": len(paths),
                        "seconds_before_after_trim": [before, after]}

    (out_dir / "ATTRIBUTION.txt").write_text(ATTRIBUTION, encoding="utf-8")
    manifest = {
        "source": "ASL Citizen (Microsoft Research)",
        "license": LICENSE,
        "research_only": True,
        "words": dict(sorted(built.items())),
        "labels_missing": missing,
        "labels_rejected_low_hand_presence": rejected,
        "min_presence": min_presence,
        "picks": picks,
    }
    (out_dir / "lexicon.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--data", type=Path, default=DATA, help="Working folder (default .work/aslc)")
    parser.add_argument("--max-signers", type=int, default=MAX_SIGNERS)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("fetch", help="Download the candidate clips")
    c = sub.add_parser("convert", help="Convert downloaded clips to .pose")
    c.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    e = sub.add_parser("export", help="Choose, mirror and trim one clip per sign")
    e.add_argument("--out", type=Path, default=REPO_ROOT / "lexicon" / "aslc")
    e.add_argument("--min-presence", type=float, default=MIN_PRESENCE)
    sub.add_parser("words", help="Print how many words each label gives (needs only the CSVs)")
    args = parser.parse_args()

    args.data.mkdir(parents=True, exist_ok=True)
    (args.data / ".gitignore").write_text("*\n", encoding="utf-8")
    if args.command == "fetch":
        fetch(args.data, args.max_signers)
    elif args.command == "convert":
        convert(args.data, args.workers)
    elif args.command == "words":
        table, chosen = plan(args.data, args.max_signers)
        print(f"{len(table)} words from {len(set(table.values()))} signs "
              f"({sum(map(len, chosen.values()))} candidate clips)")
    else:
        manifest = export(args.out, args.data, args.max_signers, args.min_presence)
        print(f"{len(manifest['words'])} words from {len(manifest['picks'])} ASL Citizen signs -> {args.out}")
        if manifest["labels_missing"]:
            print(f"no converted clip for {len(manifest['labels_missing'])} signs", file=sys.stderr)
        if manifest["labels_rejected_low_hand_presence"]:
            print(f"left out {len(manifest['labels_rejected_low_hand_presence'])} barely tracked signs",
                  file=sys.stderr)
        print("RESEARCH USE ONLY: keep it on this machine.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
