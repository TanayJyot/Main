"""Calibrate the old-vs-new sign metric, then (given new signs) run it.

Two modes.

**Old lexicon only** (runnable now):

  null       DTW distance between *different* pilot signs. This is what
             "unrelated" looks like.
  synthetic  each pilot sign against a perturbed copy of itself: resampled to
             a different speed, jittered, and mirrored half the time. This
             checks the metric ignores what it should ignore (speed,
             handedness, small noise). It is **not** a substitute for a real
             second signer: real signers differ in ways a perturbation does
             not model.
  variants   old-lexicon files sharing a word (bake_1 vs bake_2). Reported
             separately, because they may be genuinely different signs.

**With new signs** (`--new_manifest`, once converted clips exist):

  same-gloss distance, hand-PCK and retrieval (is the new sign nearest to its
  own old counterpart among every old sign?), each with a bootstrap interval.
  If the manifest has two or more signers for a gloss, their pairwise
  distances give the real calibration: same sign, different signer.

The manifest is a CSV with columns `path,concept,source,label,signer,role`.
`role` is `selected` for the one clip the conversion's written rule chose to
represent a gloss, or `calibration` for extra clips of the same gloss by other
signers. Only `selected` clips are scored against the old lexicon, so a gloss
with five calibration clips does not count five times; every clip of a gloss
feeds the same-sign-different-signer calibration. A missing `role` means
`selected`.

The right answer for a clip is the old file(s) for its **exact** word, taken
from an optional `gloss` column (the pilot's old-lexicon filename): `bake`
matches bake_1 and bake_2, and nothing else. Matching by concept instead
would count a new BEST that lands nearest the old GOOD as a hit, because
lemmatising merges best, better and good into one concept although they are
different signs. Without a `gloss` column the concept is used, with a
warning. An optional `label_rule` column (exact / concept, from
analysis/convert/labels.py) splits the results, since a concept-fallback clip
may be a different sign by design.

Nothing here selects or filters new signs by their distance to the old
lexicon. Those numbers are outputs only; feeding them back into which clip
represents a gloss would make the replacement derived from scraped data.

    python analysis/eval/calibrate.py --old $ASLYTICS_LEXICON_DIR
    python analysis/eval/calibrate.py --old $ASLYTICS_LEXICON_DIR \
        --new_manifest analysis/convert/out/manifest.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from pose_compare import SignFeatures, compare, load_features  # noqa: E402
from stats import bootstrap_ci, separation_auc, top_k_hit  # noqa: E402

MAPPING = HERE.parent / "mapping" / "gloss_mapping.csv"
PILOT = HERE.parent / "coverage" / "pilot_200.txt"


def load_pilot():
    return [line.strip() for line in PILOT.read_text().splitlines()
            if line.strip() and not line.startswith("#")]


def base_word(name: str) -> str:
    """Old filename or dataset label -> the word it names: bake_2 -> bake, CALL1 -> call."""
    return re.sub(r"(_\d+|\d+)$", "", name).lower()


def load_mapping():
    with open(MAPPING, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def perturb(features: SignFeatures, rng: np.random.Generator) -> SignFeatures:
    """Same sign, performed differently: speed, jitter, handedness."""
    factor = rng.uniform(0.7, 1.4)
    frames = features.frames
    new_len = max(2, int(round(frames * factor)))
    index = np.clip(np.round(np.linspace(0, frames - 1, new_len)).astype(int), 0, frames - 1)

    def jitter(array, scale):
        return array[index] + rng.normal(0, scale, array[index].shape)

    out = SignFeatures(jitter(features.arms, 0.03), jitter(features.left_hand, 0.05),
                       jitter(features.right_hand, 0.05), features.fps)
    return out.mirrored() if rng.random() < 0.5 else out


def summarise_distances(values):
    finite = [v for v in values if np.isfinite(v)]
    if not finite:
        return {"n": 0}
    array = np.asarray(finite)
    return {"n": len(finite), "mean": float(array.mean()),
            "p05": float(np.quantile(array, 0.05)), "median": float(np.median(array)),
            "p95": float(np.quantile(array, 0.95))}


def old_only(old_dir: str, null_pairs: int, seed: int):
    rng_py, rng = random.Random(seed), np.random.default_rng(seed)
    pilot = load_pilot()

    features = {}
    for name in pilot:
        path = os.path.join(old_dir, f"{name}.pose")
        try:
            features[name] = load_features(path)
        except Exception as error:  # a broken file should not stop calibration
            print(f"  skip {name}: {error}")
    names = sorted(features)
    print(f"loaded {len(names)} pilot signs")

    null = []
    for _ in range(null_pairs):
        a, b = rng_py.sample(names, 2)
        null.append(compare(features[a], features[b]).distance)

    synthetic, synthetic_hits = [], 0
    perturbed = {name: perturb(features[name], rng) for name in names}
    for name in names:
        synthetic.append(compare(features[name], perturbed[name]).distance)

    # Retrieval on the synthetic copies against every pilot original.
    for name in names:
        distances = {other: compare(features[other], perturbed[name]).distance for other in names}
        synthetic_hits += top_k_hit(distances, {name}, 1)

    variants = []
    by_word = defaultdict(list)
    for path in Path(old_dir).glob("*_[0-9]*.pose"):
        by_word[re.sub(r"_\d+$", "", path.stem)].append(path)
    for paths in by_word.values():
        if len(paths) >= 2:
            try:
                a, b = load_features(str(paths[0])), load_features(str(paths[1]))
                variants.append(compare(a, b).distance)
            except Exception:
                continue

    return {
        "signs": len(names),
        "null_different_signs": summarise_distances(null),
        "synthetic_same_sign": summarise_distances(synthetic),
        "synthetic_separation_auc": separation_auc(synthetic, null),
        "synthetic_top1_retrieval": synthetic_hits / len(names) if names else float("nan"),
        "retrieval_chance": 1 / len(names) if names else float("nan"),
        "old_variant_pairs": summarise_distances(variants),
        "old_variant_separation_auc": separation_auc(variants, null),
    }, null


def with_new(old_dir: str, manifest_path: str, null):
    mapping = {row["concept"]: row for row in load_mapping()}
    with open(manifest_path, newline="", encoding="utf-8") as handle:
        entries = list(csv.DictReader(handle))

    old_features = {}
    for path in sorted(Path(old_dir).glob("*.pose")):
        if path.stem.startswith("#"):
            continue
        try:
            old_features[path.stem] = load_features(str(path))
        except Exception:
            continue

    if entries and not entries[0].get("gloss"):
        print("  warning: manifest has no gloss column; scoring against whole concepts, "
              "which counts a different sign of the same root (BEST vs GOOD) as correct")

    per_gloss, by_concept_signer = [], defaultdict(list)
    for entry in entries:
        row = mapping.get(entry["concept"])
        if row is None or not row["old_files"]:
            continue
        gloss = (entry.get("gloss") or "").strip()
        if gloss:
            correct = {name for name in old_features if base_word(name) == base_word(gloss)}
        else:
            correct = set(filter(None, row["old_files"].split("|")))
        if not correct:
            continue
        new = load_features(entry["path"])
        # Calibration pairs group by exact gloss when known, so two clips are
        # only called "the same sign" if they carry the same word.
        by_concept_signer[gloss or entry["concept"]].append((entry.get("signer", ""), new))
        if (entry.get("role") or "selected").strip() != "selected":
            continue

        distances = {name: compare(old, new).distance for name, old in old_features.items()}
        own = min((name for name in correct if name in distances), key=distances.get, default=None)
        if own is None:
            continue
        detail = compare(old_features[own], new)
        per_gloss.append({
            "concept": entry["concept"], "gloss": gloss, "source": entry["source"],
            "label": entry["label"], "label_rule": (entry.get("label_rule") or "").strip(),
            "flagged_variants": "variants" in row["flags"],
            "distance": detail.distance,
            "left_hand_pck": detail.left_hand_pck, "right_hand_pck": detail.right_hand_pck,
            "top1": top_k_hit(distances, correct, 1), "top5": top_k_hit(distances, correct, 5),
        })

    # Same gloss, different signers. Pairs from one signer are skipped: they
    # would make the metric look better at separating signs than it is.
    same_signer_pairs = []
    for signs in by_concept_signer.values():
        for i in range(len(signs)):
            for j in range(i + 1, len(signs)):
                (signer_a, a), (signer_b, b) = signs[i], signs[j]
                if signer_a and signer_a == signer_b:
                    continue
                same_signer_pairs.append(compare(a, b).distance)

    def block(rows):
        return {
            "glosses": len(rows),
            "distance": bootstrap_ci([r["distance"] for r in rows]),
            "top1_retrieval": bootstrap_ci([float(r["top1"]) for r in rows]),
            "top5_retrieval": bootstrap_ci([float(r["top5"]) for r in rows]),
            "left_hand_pck": bootstrap_ci([r["left_hand_pck"] for r in rows]),
            "right_hand_pck": bootstrap_ci([r["right_hand_pck"] for r in rows]),
        }

    return {
        "retrieval_chance": 1 / len(old_features) if old_features else float("nan"),
        "all_selected": block(per_gloss),
        "unambiguous": block([r for r in per_gloss if not r["flagged_variants"]]),
        "variant_flagged": block([r for r in per_gloss if r["flagged_variants"]]),
        # Concept-fallback clips (i -> ME) are a different English word by
        # design; report them apart so they cannot drag the headline either way.
        "exact_label": block([r for r in per_gloss if r["label_rule"] in ("", "exact")]),
        "concept_fallback": block([r for r in per_gloss if r["label_rule"] == "concept"]),
        "by_source": {source: block([r for r in per_gloss if r["source"] == source])
                      for source in sorted({r["source"] for r in per_gloss})},
        "real_same_sign_different_signer": summarise_distances(same_signer_pairs),
        "real_separation_auc": separation_auc(same_signer_pairs, null),
    }, per_gloss


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate and run the old-vs-new sign metric.")
    parser.add_argument("--old", default=os.environ.get("ASLYTICS_LEXICON_DIR", ""),
                        help="Old lexicon directory (never committed)")
    parser.add_argument("--new_manifest", default="", help="CSV: path,concept,source,label,signer")
    parser.add_argument("--null_pairs", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default=str(HERE / "results"))
    args = parser.parse_args()
    if not args.old or not os.path.isdir(args.old):
        parser.error("point --old (or ASLYTICS_LEXICON_DIR) at the old lexicon")

    os.makedirs(args.out, exist_ok=True)
    report, null = old_only(args.old, args.null_pairs, args.seed)
    if args.new_manifest:
        report["new"], per_gloss = with_new(args.old, args.new_manifest, null)
        with open(os.path.join(args.out, "per_gloss.json"), "w") as handle:
            json.dump(per_gloss, handle, indent=2)

    with open(os.path.join(args.out, "calibration.json"), "w") as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
