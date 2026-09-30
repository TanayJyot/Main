"""Letters and digits for fingerspelling, from Google's ASL Fingerspelling data.

The prototype skips any word PopSign has no sign for. Fingerspelling is how
ASL itself handles such words (names, places, rare words), so with a clip per
letter the renderer can spell a missing word instead of dropping it.

Source: "Google - American Sign Language Fingerspelling Recognition" on Kaggle
(asl-fingerspelling). MediaPipe Holistic landmarks, no video, of phrases
(addresses, phone numbers, URLs, names) fingerspelled by 100+ Deaf signers,
reported as CC BY 4.0. **Check the competition's rules for use of the data
outside the competition before shipping anything built from it.**

The data holds whole phrases, not single letters. A fingerspelled letter is a
handshape held briefly, with movement between letters, so each phrase is cut
at its holds:

  1. Keep phrases made only of letters, digits and spaces (spaces are not
     signed), whose signing hand is tracked in most frames.
  2. Measure how fast the signing hand changes shape and moves, per frame.
  3. Find a stillness threshold at which the phrase splits into exactly as
     many holds as it has characters. If none does (a doubled letter such as
     LL, or a moving letter such as J or Z blurring into its neighbours), the
     phrase is skipped: only phrases that split cleanly are used.
  4. Pair holds with characters in order.

For each character, the clip used is the medoid: the example whose handshape
is closest to all the others of that character, which is robust to the odd
misaligned phrase. Selection looks only at this dataset, never at another
lexicon.

    python prototype/fingerspelling.py extract --data <kaggle folder> \\
        --header-from lexicon/popsign/dog.pose --out lexicon/fingerspelling
    python prototype/popsign_lexicon.py build --labels ... --letters lexicon/fingerspelling

`--data` is the unpacked competition folder: train.csv and/or
supplemental_metadata.csv, plus whichever of their landmark parquet files
were downloaded (a few are enough). Output: fs_<char>.pose per character,
fingerspelling.json (what was found, and from how many phrases), and
ATTRIBUTION.txt. Derived data: keep it out of git.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# MediaPipe landmark names, in the index order the Kaggle columns use.
POSE_NAMES = [
    "NOSE", "LEFT_EYE_INNER", "LEFT_EYE", "LEFT_EYE_OUTER", "RIGHT_EYE_INNER", "RIGHT_EYE",
    "RIGHT_EYE_OUTER", "LEFT_EAR", "RIGHT_EAR", "MOUTH_LEFT", "MOUTH_RIGHT", "LEFT_SHOULDER",
    "RIGHT_SHOULDER", "LEFT_ELBOW", "RIGHT_ELBOW", "LEFT_WRIST", "RIGHT_WRIST", "LEFT_PINKY",
    "RIGHT_PINKY", "LEFT_INDEX", "RIGHT_INDEX", "LEFT_THUMB", "RIGHT_THUMB", "LEFT_HIP",
    "RIGHT_HIP", "LEFT_KNEE", "RIGHT_KNEE", "LEFT_ANKLE", "RIGHT_ANKLE", "LEFT_HEEL",
    "RIGHT_HEEL", "LEFT_FOOT_INDEX", "RIGHT_FOOT_INDEX",
]
HAND_NAMES = [
    "WRIST", "THUMB_CMC", "THUMB_MCP", "THUMB_IP", "THUMB_TIP", "INDEX_FINGER_MCP",
    "INDEX_FINGER_PIP", "INDEX_FINGER_DIP", "INDEX_FINGER_TIP", "MIDDLE_FINGER_MCP",
    "MIDDLE_FINGER_PIP", "MIDDLE_FINGER_DIP", "MIDDLE_FINGER_TIP", "RING_FINGER_MCP",
    "RING_FINGER_PIP", "RING_FINGER_DIP", "RING_FINGER_TIP", "PINKY_MCP", "PINKY_PIP",
    "PINKY_DIP", "PINKY_TIP",
]
HAND_BONES = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10),
              (10, 11), (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (0, 17),
              (17, 18), (18, 19), (19, 20)]

# Kaggle column group -> (pose_format component, point names or None for "0".."n-1").
GROUPS = {
    "pose": ("POSE_LANDMARKS", POSE_NAMES),
    "face": ("FACE_LANDMARKS", None),
    "left_hand": ("LEFT_HAND_LANDMARKS", HAND_NAMES),
    "right_hand": ("RIGHT_HAND_LANDMARKS", HAND_NAMES),
}
SIZES = {"pose": 33, "face": 468, "left_hand": 21, "right_hand": 21}

SIGNED = re.compile(r"^[a-z0-9 ]+$")
MIN_TRACKED = 0.8          # signing hand seen in at least this share of frames
MIN_HOLD_FRAMES = 3
CLIP_MARGIN = 2            # frames kept either side of a hold
MIN_CLIP_FRAMES = 8
MAX_EXAMPLES = 200         # per character, for the medoid

ATTRIBUTION = """\
Fingerspelling clips (fs_*.pose) are derived from "Google - American Sign
Language Fingerspelling Recognition" (Google; Kaggle competition
asl-fingerspelling), reported as licensed under Creative Commons Attribution
4.0 International (CC BY 4.0), https://creativecommons.org/licenses/by/4.0/.

Changes: phrases were cut into single characters at held handshapes; one
example per character was chosen (the medoid handshape); left-side signing was
mirrored; landmarks were converted to .pose.
"""


# -- reading the data ------------------------------------------------------------

@dataclass
class Sequence:
    sequence_id: int
    participant: str
    phrase: str
    frames: Dict[str, np.ndarray]     # group -> (T, points, 3), NaN where missing


def _group_columns(columns) -> Dict[str, List[Tuple[str, str, str]]]:
    out = {}
    for group, size in SIZES.items():
        names = [(f"x_{group}_{i}", f"y_{group}_{i}", f"z_{group}_{i}") for i in range(size)]
        if all(n in columns for triple in names for n in triple):
            out[group] = names
    return out


def read_sequences(data_dir: Path, max_files: Optional[int] = None):
    """Yield every sequence whose landmark file has been downloaded."""
    import pandas as pd

    tables = [data_dir / name for name in ("train.csv", "supplemental_metadata.csv")]
    meta = pd.concat([pd.read_csv(t) for t in tables if t.exists()], ignore_index=True)
    if meta.empty:
        raise SystemExit(f"no train.csv or supplemental_metadata.csv in {data_dir}")

    files = 0
    for rel_path, rows in meta.groupby("path"):
        path = data_dir / rel_path
        if not path.exists():
            continue
        files += 1
        if max_files and files > max_files:
            break
        table = pd.read_parquet(path)
        groups = _group_columns(table.columns)
        wanted = set(rows["sequence_id"])
        for sequence_id, frame_rows in table.groupby(level=0) if table.index.name == "sequence_id" \
                else table.groupby("sequence_id"):
            if sequence_id not in wanted:
                continue
            frame_rows = frame_rows.sort_values("frame") if "frame" in frame_rows else frame_rows
            row = rows[rows["sequence_id"] == sequence_id].iloc[0]
            frames = {group: np.stack([frame_rows[list(c)].to_numpy(dtype=float) for c in cols], axis=1)
                      for group, cols in groups.items()}
            yield Sequence(int(sequence_id), str(row["participant_id"]), str(row["phrase"]), frames)


# -- geometry ------------------------------------------------------------------

def estimate_aspect(hands: List[np.ndarray]) -> float:
    """Height / width of the camera image, from how rigid the hand looks.

    Kaggle coordinates are divided by image width and height separately, and
    the image size is not recorded. With the wrong ratio a hand's bones seem to
    stretch as it rotates, so the ratio that keeps bone lengths steadiest over
    many frames is the right one.
    """
    candidates = np.linspace(0.4, 2.5, 85)
    scores = np.zeros_like(candidates)
    for xy in hands:
        xy = xy[~np.isnan(xy[:, 0, 0])][:, :, :2]
        if len(xy) < 5:
            continue
        for i, ratio in enumerate(candidates):
            scaled = xy * np.array([1.0, ratio])
            lengths = np.stack([np.linalg.norm(scaled[:, a] - scaled[:, b], axis=-1)
                                for a, b in HAND_BONES], axis=1)
            scores[i] += np.mean(np.std(lengths, axis=0) / (np.mean(lengths, axis=0) + 1e-9))
    return float(candidates[int(np.argmin(scores))]) if scores.any() else 1.0


def signing_hand(sequence: Sequence) -> Optional[str]:
    seen = {group: float(np.mean(~np.isnan(sequence.frames[group][:, 0, 0])))
            for group in ("left_hand", "right_hand") if group in sequence.frames}
    if not seen:
        return None
    group = max(seen, key=seen.get)
    return group if seen[group] >= MIN_TRACKED else None


def handshape(hand: np.ndarray, ratio: float) -> np.ndarray:
    """(T, 21, 3) -> (T, 63): relative to the wrist, in hand lengths."""
    scaled = hand * np.array([1.0, ratio, 1.0])
    relative = scaled - scaled[:, :1]
    size = np.linalg.norm(relative[:, 9, :2], axis=-1, keepdims=True)[:, :, None]
    with np.errstate(invalid="ignore", divide="ignore"):
        return (relative / size).reshape(len(hand), -1)


def motion(hand: np.ndarray, ratio: float) -> np.ndarray:
    """Per-frame change of handshape plus wrist travel, gaps filled."""
    shape = handshape(hand, ratio)
    wrist = hand[:, 0, :2] * np.array([1.0, ratio])
    size = np.nanmedian(np.linalg.norm((hand[:, 9, :2] - hand[:, 0, :2]) * np.array([1.0, ratio]), axis=-1))
    change = np.linalg.norm(np.diff(shape, axis=0), axis=1)
    travel = np.linalg.norm(np.diff(wrist, axis=0), axis=1) / (size if size > 0 else 1.0)
    value = np.concatenate([[0.0], change + 0.5 * travel])
    value[np.isnan(value)] = np.nanmax(value) if np.isfinite(np.nanmax(value)) else 1.0
    return np.convolve(value, np.ones(3) / 3, mode="same")


def _still_runs(activity: np.ndarray, threshold: float) -> List[Tuple[int, int]]:
    still = activity <= threshold
    runs, start = [], None
    for t, s in enumerate(still):
        if s and start is None:
            start = t
        elif not s and start is not None:
            runs.append([start, t])
            start = None
    if start is not None:
        runs.append([start, len(still)])
    joined = []
    for run in runs:
        if joined and run[0] - joined[-1][1] <= 1:
            joined[-1][1] = run[1]
        else:
            joined.append(run)
    return [(s, e) for s, e in joined if e - s >= MIN_HOLD_FRAMES]


def holds(activity: np.ndarray, count: int) -> Optional[List[Tuple[int, int]]]:
    """`count` still stretches, as (start, end) frames, or None if no threshold gives exactly that.

    Thresholds are tried from loose to strict. A loose one merges holds across
    quick transitions (too few stretches); going stricter separates them, then
    narrows each hold to its stillest frames, until it starts breaking holds
    into pieces. The strictest threshold of that first run of thresholds
    giving exactly `count` is used: holds separated, as tight as they stay
    whole. Gaps of one frame are closed first, so a flicker inside a hold does
    not split it.
    """
    best = None
    for q in np.linspace(0.8, 0.05, 61):
        runs = _still_runs(activity, np.quantile(activity, q))
        if len(runs) == count:
            best = runs
        elif best is not None:
            break
    return best


# -- cutting phrases into characters -------------------------------------------

@dataclass
class Example:
    char: str
    sequence: Sequence
    start: int
    end: int
    hand: str
    shape: np.ndarray                 # mean handshape over the hold, mirrored to one side


def examples_from(sequence: Sequence, ratio: float) -> List[Example]:
    phrase = sequence.phrase.lower()
    if not SIGNED.match(phrase):
        return []
    chars = [c for c in phrase if c != " "]
    hand = signing_hand(sequence)
    if hand is None or not chars:
        return []
    frames = sequence.frames[hand]
    found = holds(motion(frames, ratio), len(chars))
    if found is None:
        return []

    shape = handshape(frames, ratio)
    if hand == "left_hand":
        # Compare left-side signing with right-side signing as a mirror image.
        shape = shape.reshape(len(shape), 21, 3) * np.array([-1.0, 1.0, 1.0])
        shape = shape.reshape(len(shape), -1)
    out = []
    for char, (s, e) in zip(chars, found):
        mean = np.nanmean(shape[s:e], axis=0)
        if np.isnan(mean).any():
            continue
        middle = (s + e) // 2
        s, e = max(0, s - CLIP_MARGIN), min(len(frames), e + CLIP_MARGIN)
        if e - s < MIN_CLIP_FRAMES:
            s = max(0, middle - MIN_CLIP_FRAMES // 2)
            e = min(len(frames), s + MIN_CLIP_FRAMES)
        out.append(Example(char, sequence, s, e, hand, mean))
    return out


def medoid(examples: List[Example]) -> Example:
    shapes = np.stack([e.shape for e in examples])
    distances = np.linalg.norm(shapes[:, None] - shapes[None], axis=-1).sum(axis=1)
    return examples[int(np.argmin(distances))]


# -- writing .pose -------------------------------------------------------------

def to_pose(example: Example, header, ratio: float, fps: float, width: float = 1080.0):
    """The example's frames as a Pose with `header`'s components.

    Points the header has but the data lacks (e.g. POSE_WORLD_LANDMARKS) get
    confidence 0. The clip is mirrored when the signing hand is on the other
    side of the body from PopSign's, which puts every sign on the same side.
    """
    from pose_format import Pose
    from pose_format.numpy import NumPyPoseBody

    seq, s, e = example.sequence, example.start, example.end
    frames = e - s
    total = sum(len(c.points) for c in header.components)
    dims = header.num_dims() if hasattr(header, "num_dims") else 3
    data = np.zeros((frames, 1, total, dims), dtype=np.float32)
    conf = np.zeros((frames, 1, total), dtype=np.float32)

    mirror = _needs_mirror(seq, s, e)
    height = width * ratio
    offset = 0
    for component in header.components:
        group = next((g for g, (name, _) in GROUPS.items() if name == component.name), None)
        if group is not None and group in seq.frames:
            names = GROUPS[group][1] or [str(i) for i in range(SIZES[group])]
            source = seq.frames[group][s:e]
            for j, point in enumerate(component.points):
                if point not in names:
                    continue
                xyz = source[:, names.index(point)]
                ok = ~np.isnan(xyz[:, 0])
                x = (1.0 - xyz[:, 0]) if mirror else xyz[:, 0]
                values = np.stack([x * width, xyz[:, 1] * height, xyz[:, 2] * width], axis=1)[:, :dims]
                data[ok, 0, offset + j] = values[ok]
                conf[ok, 0, offset + j] = 1.0
        offset += len(component.points)

    body = NumPyPoseBody(fps=fps, data=np.ma.masked_array(data, mask=np.repeat((conf == 0)[..., None], dims, -1)),
                         confidence=conf)
    return Pose(header, body)


def _needs_mirror(seq: Sequence, s: int, e: int) -> bool:
    """True if the signing hand sits on the image's right of the shoulders.

    PopSign signs, once converted, all have the signing hand on the image's
    left; fingerspelling is made to match.
    """
    pose = seq.frames.get("pose")
    hand = seq.frames.get("right_hand") if signing_hand(seq) == "right_hand" else seq.frames.get("left_hand")
    if pose is None or hand is None:
        return False
    middle = np.nanmean((pose[s:e, 11, 0] + pose[s:e, 12, 0]) / 2)
    wrist = np.nanmean(hand[s:e, 0, 0])
    return bool(np.isfinite(middle) and np.isfinite(wrist) and wrist > middle)


# -- the command -----------------------------------------------------------------

def extract(data_dir: Path, out_dir: Path, header_from: Path, fps: float,
            max_files: Optional[int] = None) -> Dict[str, object]:
    from io import BytesIO

    from pose_format import Pose

    header = Pose.read(header_from.read_bytes()).header
    sequences = list(read_sequences(data_dir, max_files))
    signing = [seq for seq in sequences if signing_hand(seq)]
    ratio = estimate_aspect([seq.frames[signing_hand(seq)] for seq in signing[:200]])

    by_char: Dict[str, List[Example]] = defaultdict(list)
    phrases_used = 0
    for seq in signing:
        found = examples_from(seq, ratio)
        phrases_used += bool(found)
        for example in found:
            if len(by_char[example.char]) < MAX_EXAMPLES:
                by_char[example.char].append(example)

    out_dir.mkdir(parents=True, exist_ok=True)
    chosen = {}
    for char, examples in sorted(by_char.items()):
        best = medoid(examples)
        pose = to_pose(best, header, ratio, fps)
        buffer = BytesIO()
        pose.write(buffer)
        (out_dir / f"fs_{char}.pose").write_bytes(buffer.getvalue())
        chosen[char] = {"examples": len(examples), "sequence_id": best.sequence.sequence_id,
                        "participant": best.sequence.participant, "frames": best.end - best.start}

    wanted = [chr(c) for c in range(ord("a"), ord("z") + 1)] + [str(d) for d in range(10)]
    report = {
        "source": "Google ASL Fingerspelling (Kaggle asl-fingerspelling)",
        "license": "CC BY 4.0 (reported; check the competition rules)",
        "sequences_read": len(sequences),
        "sequences_with_a_tracked_hand": len(signing),
        "phrases_split_cleanly": phrases_used,
        "aspect_ratio_h_over_w": round(ratio, 3),
        "fps": fps,
        "characters": chosen,
        "characters_missing": [c for c in wanted if c not in chosen],
    }
    (out_dir / "fingerspelling.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out_dir / "ATTRIBUTION.txt").write_text(ATTRIBUTION, encoding="utf-8")
    (out_dir / ".gitignore").write_text("*\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    x = sub.add_parser("extract", help="Cut phrases into one clip per character")
    x.add_argument("--data", required=True, type=Path, help="Unpacked asl-fingerspelling folder")
    x.add_argument("--header-from", required=True, type=Path,
                   help="Any .pose from the lexicon, so the letters share its layout")
    x.add_argument("--out", type=Path, default=Path("lexicon") / "fingerspelling")
    x.add_argument("--fps", type=float, default=30.0,
                   help="Frame rate of the recordings (not stated in the data; default 30)")
    x.add_argument("--max-files", type=int, help="Read at most this many landmark files")
    args = parser.parse_args()

    report = extract(args.data, args.out, args.header_from, args.fps, args.max_files)
    print(f"{report['sequences_read']} phrases read, {report['phrases_split_cleanly']} split cleanly "
          f"into characters; image aspect {report['aspect_ratio_h_over_w']}")
    for char, info in report["characters"].items():
        print(f"  {char}: medoid of {info['examples']} examples, {info['frames']} frames")
    if report["characters_missing"]:
        print(f"no clean example for: {' '.join(report['characters_missing'])}", file=sys.stderr)
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
