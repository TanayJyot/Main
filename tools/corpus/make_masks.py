"""
Generate the segmentation masks that SHHQ shipped and a fresh corpus does not.

clean_to_images.py expects a mask directory laid out exactly like SHHQ's
`segments/`: one mask per image, same filename, same dimensions, white
foreground on black.

Two backends, both commercially usable:

  rembg     — BiRefNet / U2Net under the hood, MIT. Easiest to install.
  sam       — Segment Anything 1 or 2, Apache-2.0. Heavier, better edges.

SAM 3 is under Meta's custom SAM Licence rather than Apache-2.0; check its terms
before adding it as a backend.

    python make_masks.py --input_dir corpus/raw --output_dir corpus/masks --backend rembg
"""

from __future__ import annotations

import argparse
import os
from typing import Callable

import cv2
import numpy as np


def _to_bgr_mask(alpha: np.ndarray, threshold: int = 127) -> np.ndarray:
    """Alpha channel -> 3-channel binary mask, matching SHHQ's mask format."""
    binary = np.where(alpha > threshold, 255, 0).astype(np.uint8)
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)


def rembg_backend(model_name: str = "birefnet-general") -> Callable[[np.ndarray], np.ndarray]:
    from rembg import new_session, remove

    session = new_session(model_name)

    def segment(image_bgr: np.ndarray) -> np.ndarray:
        rgba = remove(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGBA), session=session)
        return _to_bgr_mask(rgba[:, :, 3])

    return segment


def sam_backend(checkpoint: str, model_type: str = "vit_h") -> Callable[[np.ndarray], np.ndarray]:
    """SAM prompted with a centre box, then the largest mask is kept.

    Our corpus is single-subject and roughly centred by filter_candidates.py, so
    a box prompt is reliable without any per-image interaction.
    """
    import torch
    from segment_anything import SamPredictor, sam_model_registry

    device = "cuda" if torch.cuda.is_available() else "cpu"
    sam = sam_model_registry[model_type](checkpoint=checkpoint).to(device)
    predictor = SamPredictor(sam)

    def segment(image_bgr: np.ndarray) -> np.ndarray:
        height, width = image_bgr.shape[:2]
        predictor.set_image(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
        # Inset box: the subject fills most of the frame after filtering.
        box = np.array([width * 0.1, height * 0.02, width * 0.9, height * 0.98])
        masks, scores, _ = predictor.predict(box=box[None, :], multimask_output=True)
        best = masks[int(np.argmax(scores))]
        return _to_bgr_mask((best * 255).astype(np.uint8))

    return segment


def largest_component(mask_bgr: np.ndarray) -> np.ndarray:
    """Drop stray blobs — reflections, bystanders, background objects."""
    gray = cv2.cvtColor(mask_bgr, cv2.COLOR_BGR2GRAY)
    count, labels, stats, _ = cv2.connectedComponentsWithStats((gray > 127).astype(np.uint8), connectivity=8)
    if count <= 2:  # background + at most one component
        return mask_bgr
    # Label 0 is the background.
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    cleaned = np.where(labels == largest, 255, 0).astype(np.uint8)
    return cv2.cvtColor(cleaned, cv2.COLOR_GRAY2BGR)


def coverage(mask_bgr: np.ndarray) -> float:
    gray = cv2.cvtColor(mask_bgr, cv2.COLOR_BGR2GRAY)
    return float((gray > 127).mean())


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SHHQ-compatible segmentation masks.")
    parser.add_argument("--input_dir", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--backend", choices=["rembg", "sam"], default="rembg")
    parser.add_argument("--rembg_model", default="birefnet-general")
    parser.add_argument("--sam_checkpoint", default="sam_vit_h_4b8939.pth")
    parser.add_argument("--min_coverage", type=float, default=0.08,
                        help="Reject masks covering less of the frame than this — "
                             "usually a failed segmentation rather than a small subject")
    parser.add_argument("--max_coverage", type=float, default=0.85,
                        help="Reject masks covering more than this — usually the "
                             "background leaked into the foreground")
    args = parser.parse_args()

    segment = (rembg_backend(args.rembg_model) if args.backend == "rembg"
               else sam_backend(args.sam_checkpoint))

    os.makedirs(args.output_dir, exist_ok=True)
    written, skipped = 0, {}

    for filename in sorted(os.listdir(args.input_dir)):
        path = os.path.join(args.input_dir, filename)
        image = cv2.imread(path)
        if image is None:
            skipped[filename] = "unreadable"
            continue

        mask = largest_component(segment(image))
        fraction = coverage(mask)
        if not args.min_coverage <= fraction <= args.max_coverage:
            skipped[filename] = f"coverage {fraction:.3f} outside bounds"
            continue

        # Same filename, so clean_to_images.py pairs them by name.
        cv2.imwrite(os.path.join(args.output_dir, filename), mask)
        written += 1

    print(f"wrote {written} masks -> {args.output_dir}")
    if skipped:
        print(f"skipped {len(skipped)}:")
        for filename, reason in list(skipped.items())[:20]:
            print(f"  {filename}: {reason}")
        print("Images without a mask will be rejected by clean_to_images.py — "
              "remove them from the raw directory or re-run with another backend.")


if __name__ == "__main__":
    main()
