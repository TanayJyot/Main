# SHHQ migration toolkit

Everything needed to run Phases 0–2 of the migration plan in
[`../DATA_LICENSES.md`](../DATA_LICENSES.md) §6 — that is, everything up to the
point where a GPU is required.

```
tools/
  pin_baseline.py            Phase 0: capture the current run before it is lost
  eval/
    metrics.py               PCK / MPJPE / SSIM / PSNR / temporal error
    pose_fidelity.py         re-run MediaPipe on renders, compare to conditioning pose
    run_eval.py              the harness CLI; writes report.json
    make_human_eval_sheet.py blind A/B rating sheet for signer review
  corpus/
    provenance.py            licence policy + manifest. The gate.
    fetch_pixabay.py         fetch images, recording provenance as it goes
    filter_candidates.py     keep only SHHQ-like frames
    make_masks.py            regenerate the masks SHHQ shipped
    clean_to_images.py       build frames.zip — drop-in for shhq_to_images.py
  tests/test_toolkit.py      runs without mediapipe/torch/GPU
```

Install: `pip install -r requirements.txt`. Test: `python tools/tests/test_toolkit.py`.

## Phase 0 — lock the baseline

Run this **on the training machine, before touching any data.** Once SHHQ is
gone the baseline cannot be rebuilt, so anything not captured here is lost.

```bash
python tools/pin_baseline.py \
    --pose_to_video ~/src/pose-to-video \
    --checkpoint    ~/runs/baseline/checkpoint-20 \
    --train_zip     ~/data/frames.zip \
    --train_sh      ~/src/pose-to-video/pose_to_video/conditional/controlnet/train.sh \
    --seed          42 \
    --out           runs/baseline/baseline.json
```

Then render the eval clips with the **current** model and score them:

```bash
python tools/eval/run_eval.py \
    --renders runs/baseline/clips \
    --poses   eval/poses \
    --real    eval/real_frames \
    --out     runs/baseline/report.json
```

`--poses` holds conditioning `.pose` files, one per clip; `--renders` holds one
frame directory per clip, matched by name. `--real` is optional and only used
for the paired PSNR/SSIM numbers, so held-out BIU-MG frames belong there.

The numbers in `report.json` are the definition of "our previous results" from
here on. Without them the migration has nothing to aim at.

## Phase 1 — measure what SHHQ was actually contributing

Retrain on BIU-MG alone with an otherwise identical config, render the same
clips, and score:

```bash
python tools/eval/run_eval.py \
    --renders runs/biu-only/clips --poses eval/poses --real eval/real_frames \
    --out runs/biu-only/report.json --baseline runs/baseline/report.json
```

It exits non-zero if anything regressed past the tolerances in
`run_eval.DEFAULT_TOLERANCES`. **If nothing regresses, the migration is done** —
BIU-MG is already cleared for commercial use, and no replacement corpus is
needed.

Check `baseline.json`'s `train_data.entries` before assuming the gap will be
large. Upstream's `shhq_to_images.py` wraps its loop in
`itertools.islice(files, 0, 2)`, so unless it was patched, only two SHHQ images
ever reached training.

## Phase 2 — build a replacement corpus, if Phase 1 says you need one

```bash
export PIXABAY_API_KEY=...
python tools/corpus/fetch_pixabay.py \
    --output_dir corpus/downloaded --manifest corpus/provenance.jsonl --target 8000

python tools/corpus/filter_candidates.py \
    --input_dir corpus/downloaded --output_dir corpus/raw \
    --rejects_log corpus/rejected.json

python tools/corpus/make_masks.py \
    --input_dir corpus/raw --output_dir corpus/masks --backend rembg

python tools/corpus/clean_to_images.py \
    --raw_img_dir corpus/raw --raw_seg_dir corpus/masks \
    --manifest corpus/provenance.jsonl \
    --output_path data/frames-clean.zip --resolution 512
```

Fetch over-collects deliberately: the filter is strict and most stock "full
body" photos are not.

### The licence gate

`provenance.py` holds the source policy, and it is enforced in code rather than
documented and hoped for. An image cannot enter `frames.zip` unless it carries a
provenance record whose source permits ML training. `pexels` and `shhq` are hard
denials; an unrecognised source is refused rather than waved through.

Pixabay permits ML training but lets contributors opt out, and its API does not
expose that flag. Records therefore start at `ai_training_optout="unknown"` and
the build **refuses** them. Work the queue:

```bash
python tools/corpus/fetch_pixabay.py --manifest corpus/provenance.jsonl \
    --output_dir corpus/downloaded --print_optout_queue
```

Confirm each on its page, then set `ai_training_optout="clear"` on the record.
`--allow_unverified_optout` exists for pipeline testing and must never be used
for a model you intend to ship.

If you take the recommended route in §6 step 7 — recording consented signers
rather than scraping stock — use `source="own-recording"`, which has no pending
checks and settles model releases at the same time.

### Matching the baseline exactly

`clean_to_images.py` keeps upstream's compositing constants (`blur_level=3`,
`gaussian=81`, `bg_color=(60, 174, 60)`), the top-square crop, Lanczos resize,
and the uncompressed `ZIP_STORED` archive with `<prefix>NNNNN/imgNNNNNNNN.png`
entries. Pass `--archive_prefix sshq` if you want the archive to be
structurally identical to the baseline's.

Changing any of those constants changes what the model sees at every pixel of
every training image, so change them only alongside a baseline retrain.

## Phase 3 — training

Needs a GPU and the real corpus; not runnable from here. See
[`../DATA_LICENSES.md`](../DATA_LICENSES.md) §6 Phase 3. The two rules that
matter:

- Retrain **from scratch**, never from `sign/sd-controlnet-mediapipe` — that
  checkpoint carries the SHHQ derivation forward.
- If you fall short, iterate on the **corpus**, with hyperparameters frozen.
  Changing both at once means the result can no longer be attributed to the
  data swap.

Then render the same eval clips, run `run_eval.py --baseline
runs/baseline/report.json`, and build the blind review sheet:

```bash
python tools/eval/make_human_eval_sheet.py \
    --a runs/baseline/clips --b runs/clean-v1/clips --out review/sheet.html --seed 7
```

The sheet randomises presentation order and which model appears on which side,
and writes the unblinding key to a sibling `.key.json` — keep that away from
raters. Ship on the signer ratings and hand-level PCK; FID is secondary, and a
better FID with worse hands is a regression for this product.
