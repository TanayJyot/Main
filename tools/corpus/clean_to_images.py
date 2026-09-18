"""
Drop-in replacement for pose-to-video's data/SHHQ/shhq_to_images.py.

Same CLI shape, same compositing maths, same archive contract, so
pose-to-video's train.sh does not change and the *only* variable between the
baseline run and the replacement run is which images went in.

Two deliberate differences from upstream:

1. Upstream wraps its file loop in `itertools.islice(tqdm(files), 0, 2)`, so it
   only ever processes TWO images. That looks like debugging scaffolding left
   in. We process the whole directory, and log the count so the difference is
   visible in the run log rather than silent.
2. A provenance manifest is required. An image with no record, or a record
   whose source forbids ML training, does not enter the archive. See
   provenance.py.

Usage:

    python clean_to_images.py \
        --raw_img_dir=corpus/raw \
        --raw_seg_dir=corpus/masks \
        --manifest=corpus/provenance.jsonl \
        --output_path=frames.zip \
        --resolution=512
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import zipfile
from contextlib import contextmanager
from typing import Iterator, List, Tuple

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from provenance import LicenceError, Manifest, check_optout  # noqa: E402

# Upstream's defaults. Do not change these without retraining the baseline too:
# the green is what the model learns to key out, and the blur radii shape the
# matte it sees at every pixel of every training image.
BLUR_LEVEL = 3
GAUSSIAN = 81
BG_COLOR = (60, 174, 60)


def remove_background(seg, raw, blur_level=BLUR_LEVEL, gaussian=GAUSSIAN, bg_color=BG_COLOR):
    """Composite `raw` onto a green background using `seg` as the matte.

    Byte-for-byte the same operation as upstream's remove_background().
    """
    seg = cv2.blur(seg, (blur_level, blur_level))

    empty = np.ones_like(seg)
    seg_bg = (empty - seg) * 255
    seg_bg = cv2.GaussianBlur(seg_bg, (gaussian, gaussian), 0)
    seg_bg = seg_bg * np.array(bg_color, dtype=float) / 255

    background_mask = cv2.cvtColor(255 - cv2.cvtColor(seg, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    masked_fg = (raw / 255) * (seg / 255)
    masked_bg = (seg_bg / 255) * (background_mask / 255)

    return np.uint8(cv2.add(masked_bg, masked_fg) * 255)


def cleared_files(img_dir: str, manifest: Manifest, allow_unverified_optout: bool) -> List[str]:
    """Filenames in img_dir that provenance clears for training.

    An image is matched to its record by filename stem, which is what the
    fetchers use as image_id.
    """
    cleared, missing, blocked, pending = [], [], [], []

    for filename in sorted(os.listdir(img_dir)):
        stem = os.path.splitext(filename)[0]
        record = manifest.get(stem)
        if record is None:
            missing.append(filename)
            continue
        try:
            record.validate()
        except LicenceError as error:
            blocked.append(f"{filename}: {error}")
            continue
        if not record.is_training_ready() and not allow_unverified_optout:
            pending.append(filename)
            continue
        cleared.append(filename)

    if missing:
        raise LicenceError(
            f"{len(missing)} image(s) have no provenance record, e.g. {missing[:3]}. "
            f"Every training image needs one — that is the whole point of this "
            f"pipeline. Fix the manifest or remove the files."
        )
    if blocked:
        raise LicenceError("Images blocked by licence policy:\n  " + "\n  ".join(blocked[:10]))
    if pending:
        raise LicenceError(
            f"{len(pending)} image(s) still need a contributor opt-out check, e.g. "
            f"{pending[:3]}. Resolve them (see provenance.check_optout) or pass "
            f"--allow_unverified_optout to build a throwaway archive for testing "
            f"only — never one you train a shipping model on."
        )
    return cleared


def square_images(img_dir: str, seg_dir: str, files: List[str], resolution: int = 512) -> Iterator[Tuple[str, Image.Image]]:
    """Composite, crop to square and resize. Yields (source filename, image)."""
    for filename in files:
        raw = cv2.imread(os.path.join(img_dir, filename))
        seg = cv2.imread(os.path.join(seg_dir, filename))
        if raw is None:
            raise FileNotFoundError(f"could not read image {filename}")
        if seg is None:
            raise FileNotFoundError(f"could not read mask for {filename} — run make_masks.py first")
        if raw.shape != seg.shape:
            raise ValueError(f"{filename}: mask shape {seg.shape} does not match image {raw.shape}")

        img = remove_background(seg, raw)
        _, img_width, _ = img.shape
        img = img[:img_width]  # top square crop, as upstream

        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(img, mode="RGB")
        img = img.resize((resolution, resolution), Image.LANCZOS)

        yield filename, img


@contextmanager
def open_writable_zip(dest: str):
    if os.path.dirname(dest) != "":
        os.makedirs(os.path.dirname(dest), exist_ok=True)
    zf = zipfile.ZipFile(file=dest, mode="w", compression=zipfile.ZIP_STORED)
    try:
        yield zf.writestr
    finally:
        zf.close()


def archive_name(idx: int, prefix: str) -> str:
    """Upstream's archive layout: <prefix>NNNNN/imgNNNNNNNN.png."""
    idx_str = f"{idx:08d}"
    return f"{prefix}{idx_str[:5]}/img{idx_str}.png"


def build(img_dir: str, seg_dir: str, manifest_path: str, output_path: str,
          resolution: int = 512, prefix: str = "clean",
          allow_unverified_optout: bool = False) -> dict:
    manifest = Manifest(manifest_path)
    files = cleared_files(img_dir, manifest, allow_unverified_optout)
    if not files:
        raise LicenceError("no images cleared for training — nothing to build")

    index = {}
    with open_writable_zip(output_path) as save_frame_bytes:
        for idx, (filename, img) in enumerate(square_images(img_dir, seg_dir, files, resolution)):
            name = archive_name(idx, prefix)
            image_bits = io.BytesIO()
            img.save(image_bits, format="png", compress_level=0, optimize=False)
            save_frame_bytes(name, image_bits.getbuffer())
            index[name] = os.path.splitext(filename)[0]

    report = {
        "output_path": output_path,
        "images_written": len(index),
        "resolution": resolution,
        "archive_prefix": prefix,
        "compositing": {"blur_level": BLUR_LEVEL, "gaussian": GAUSSIAN, "bg_color": list(BG_COLOR)},
        "provenance": manifest.summary(),
        "archive_to_image_id": index,
    }

    sidecar = os.path.splitext(output_path)[0] + ".provenance.json"
    with open(sidecar, "w", encoding="utf-8") as handle:
        import json
        json.dump(report, handle, indent=2)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a training archive from a provenance-cleared image corpus.")
    parser.add_argument("--raw_img_dir", type=str, required=True, help="Folder of raw images")
    parser.add_argument("--raw_seg_dir", type=str, required=True, help="Folder of segmentation masks")
    parser.add_argument("--manifest", type=str, required=True, help="Provenance JSONL (see provenance.py)")
    parser.add_argument("--output_path", type=str, default="frames.zip", help="Path to output zip file")
    parser.add_argument("--resolution", type=int, default=512, choices=[256, 512, 1024])
    parser.add_argument("--archive_prefix", type=str, default="clean",
                        help="Directory prefix inside the zip. Upstream uses 'sshq'; "
                             "pass that for a byte-comparable A/B against the baseline.")
    parser.add_argument("--allow_unverified_optout", action="store_true",
                        help="Build even with unresolved opt-out checks. Testing only.")
    args = parser.parse_args()

    for path, label in [(args.raw_img_dir, "Raw image directory"), (args.raw_seg_dir, "Mask directory")]:
        if not os.path.exists(path):
            parser.error(f"{label} does not exist: {path}")
    if not os.path.exists(args.manifest):
        parser.error(f"Manifest does not exist: {args.manifest}")
    if not args.output_path.endswith(".zip"):
        parser.error("Output path must end with .zip")

    try:
        report = build(args.raw_img_dir, args.raw_seg_dir, args.manifest, args.output_path,
                       args.resolution, args.archive_prefix, args.allow_unverified_optout)
    except LicenceError as error:
        parser.exit(2, f"refusing to build: {error}\n")

    print(f"wrote {report['images_written']} images to {report['output_path']}")
    print(f"provenance: {report['provenance']}")
    if args.allow_unverified_optout:
        print("WARNING: built with unverified opt-out checks. Do not train a shipping model on this.")


if __name__ == "__main__":
    main()
