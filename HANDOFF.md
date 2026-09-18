# Handoff: SHHQ migration, cloud session → local machine

Written for the Claude agent picking this up on the user's GPU machine. Read
this first, then `DATA_LICENSES.md` §6 for the reasoning behind the plan and
`tools/README.md` for the command reference.

```
branch   claude/dataset-license-audit-d5szps
remote   https://github.com/TanayJyot/Main
```

Nothing in this branch has run against real data. Every finding below is
either evidence from the repo (cited) or a stated assumption. Do not treat the
assumptions as established.

---

## 1. Why this work exists

The project cannot ship commercially as-is. Three independent blockers, in
order of how well they are understood:

| # | Blocker | Status |
|---|---|---|
| 1 | **SHHQ-1.0** — the dataset the pose→video renderer models were finetuned on. Non-commercial research only; its release agreement bars commercial use of the images "and any portion of the **derived data**", which covers finetuned weights. | Identified, plan written, tooling built. **This is your job.** |
| 2 | **The gloss→pose lexicon** — `.pose` files with no recorded provenance. Every realistic ASL corpus is non-commercial. | Open. Fast path is asking a human; `tools/inspect_lexicon.py` is the slow path. |
| 3 | **GPL-3.0** in `text-to-gloss/start.py` (vendored Signspeech) — copyleft, not a use restriction. | Open, untouched. Out of scope unless asked. |

Full evidence for each is in `DATA_LICENSES.md`. Do not re-derive it.

## 2. The one thing that could end this immediately

`pose-to-video`'s `data/SHHQ/shhq_to_images.py` — the script that converts SHHQ
into training data — contains:

```python
for file in itertools.islice(tqdm(files), 0, 2):
```

**It processes two images per run.** Looks like debugging scaffolding left
upstream. If it was never patched locally, SHHQ contributed 2 images to
training, not 40,000, and the BIU-MG-only retrain (step 4 below) will match the
baseline immediately.

**Check this before planning any long work.** `pin_baseline.py` reads the
training archive's entry count and flags it automatically.

## 3. Two traps that will cost you hours

**MediaPipe version.** The legacy `mediapipe.solutions` API that `pose-format`
depends on has been removed. Verified by installing each version:

| version | `mediapipe.solutions` |
|---|---|
| 0.10.21 (the project's pin) | present |
| 0.10.30 | **gone** |
| 1.x | module does not exist |

A bare `pip install mediapipe` gets 1.x and breaks both the render pipeline and
the eval harness with an `AttributeError` deep in a worker. `tools/requirements.txt`
pins `<0.10.30`; `tools/mp_compat.py` fails with the pin instead of a traceback;
`tools/preflight.py` checks it. Do not "fix" a MediaPipe error by upgrading.

**Reduced pose components.** `concatenate.py` sets `is_reduce_holistic = True`,
which trims `POSE_LANDMARKS` from MediaPipe's 33 points to 8. Anything comparing
a conditioning pose against a fresh MediaPipe result **must match landmarks by
name**, never by index — position 11 is not the left shoulder in a reduced pose.
`tools/eval/pose_fidelity.py` already does this; don't undo it. It also reports
`<component>_points_compared`, so if that is 0 the metric is meaningless, not
perfect.

## 4. Run this, in this order

Everything here is CPU except steps 4 and 8.

```bash
git fetch origin && git checkout claude/dataset-license-audit-d5szps
pip install -r tools/requirements.txt

# 1. Prove the toolkit works before pointing it at real data.
python tools/tests/test_toolkit.py     # expect 30/30
python tools/smoke_test.py             # expect all pass, nothing skipped

# 2. Capture the baseline. Once SHHQ is gone this cannot be rebuilt.
python tools/pin_baseline.py \
    --pose_to_video <path> --checkpoint <path> --train_zip <path> \
    --train_sh <path> --seed <n> --out runs/baseline/baseline.json
#    ^ READ train_data.entries. See section 2.

# 3. Baseline numbers, on data we own. This defines "our previous results".
python tools/eval/run_eval.py --renders runs/baseline/clips \
    --poses eval/poses --real eval/real_frames --out runs/baseline/report.json

# 4. [GPU] Retrain on BIU-MG alone, identical config and seed.
python tools/preflight.py --pose_to_video <path> --train_zip <path> \
    --output_dir runs/biu-only --poses eval/poses \
    --baseline_report runs/baseline/report.json
# ... train ... then render the same clips and score:
python tools/eval/run_eval.py --renders runs/biu-only/clips \
    --poses eval/poses --real eval/real_frames \
    --out runs/biu-only/report.json --baseline runs/baseline/report.json
```

**If step 4 exits 0, stop. You are done.** BIU-MG is already cleared for
commercial use — its README says so explicitly — so a model trained on it alone
has no licence problem. Report that and do not build a replacement corpus.

Only if step 4 regresses:

```bash
# 5. Collect. Recording consented signers beats scraping stock — see below.
export PIXABAY_API_KEY=...
python tools/corpus/fetch_pixabay.py --output_dir corpus/downloaded \
    --manifest corpus/provenance.jsonl --target 8000

# 6. Filter to SHHQ's distribution, then regenerate its masks.
python tools/corpus/filter_candidates.py --input_dir corpus/downloaded \
    --output_dir corpus/raw --rejects_log corpus/rejected.json
python tools/corpus/make_masks.py --input_dir corpus/raw \
    --output_dir corpus/masks --backend rembg

# 7. Build the archive. Refuses anything without cleared provenance.
python tools/corpus/clean_to_images.py --raw_img_dir corpus/raw \
    --raw_seg_dir corpus/masks --manifest corpus/provenance.jsonl \
    --output_path data/frames-clean.zip --resolution 512

# 8. [GPU] Retrain FROM SCRATCH, score, then blind review.
python tools/eval/make_human_eval_sheet.py --a runs/baseline/clips \
    --b runs/clean-v1/clips --out review/sheet.html --seed 7
```

## 5. Rules you must not break

- **Never resume from `sign/sd-controlnet-mediapipe`** or any SHHQ-derived
  checkpoint. It carries the derivation forward and silently undoes the entire
  migration. `preflight.py` checks `--resume_from` for this.
- **Never use Pexels.** Its Terms prohibit scraping and data mining "including
  for machine learning purposes". `provenance.py` hard-denies it. Unsplash is
  usable *only* through the Unsplash Lite Dataset, not the general licence.
- **Never bypass the provenance gate.** `--allow_unverified_optout` is for
  pipeline testing only. If it was used, the archive cannot train a shipping
  model.
- **Never change the compositing constants** (`blur_level=3`, `gaussian=81`,
  `bg_color=(60,174,60)`), the top-square crop, or the archive layout without
  retraining the baseline too. They decide what the model sees at every pixel.
- **Iterate on the corpus, not hyperparameters.** If a candidate falls short,
  change corpus size, filter strictness or the clean:BIU-MG ratio with training
  config frozen. Changing both means the result can no longer be attributed to
  the data swap — which is the entire question.
- **Ship on hand-level PCK and the signer ratings**, not FID. A better FID with
  worse hands is a regression for this product: a blurred handshape is an
  unreadable sign.

## 6. Ask the human, don't guess

1. **Who built `.gitignore/generated_pose/`, and from what?** This is blocker #2
   and one question probably answers it. The path is hardcoded to
   `/home/ellie/GitHub/ASLytics-RBC/`.
2. **Who signed the SHHQ access agreement, and where did the trained weights
   go?** Local disks, HF Hub, demo videos, slide decks. Nothing derived from
   them can ship, and the agreement also bars redistribution.
3. **Was `shhq_to_images.py` patched?** See section 2.
4. **Record signers, or scrape stock?** `DATA_LICENSES.md` §6 step 7 recommends
   recording 5–10 consented signers: it gives diversity *in domain* rather than
   static non-signers, and settles model releases, which stock licences do not.
   It costs recording time. This is the user's call, not yours.

## 7. Definition of done

The renderer is clear when **all** of these hold:

- No SHHQ-derived data or weights in any shipping artefact, and none in the
  ancestry of the shipping checkpoint.
- Every training image has a provenance record whose source permits ML
  training, with no unresolved opt-out checks (`preflight.py` verifies).
- `run_eval.py --baseline runs/baseline/report.json` exits 0.
- A fluent signer has reviewed the blind A/B sheet and the candidate is not
  worse.

Blockers #2 and #3 remain separately open at that point. Say so; do not imply
the product is clear to ship.

## 8. What is in the branch

```
DATA_LICENSES.md   the audit and the migration plan. The authority.
HANDOFF.md         this file
tools/README.md    command reference for every script
tools/
  pin_baseline.py      capture the current run before it is lost
  preflight.py         pre-GPU checks: CUDA, packages, disk, provenance, ancestry
  smoke_test.py        end-to-end pipeline run on synthetic data
  inspect_lexicon.py   fingerprint the .pose lexicon (blocker #2)
  mp_compat.py         MediaPipe version guard
  eval/                metrics, pose fidelity, the harness, blind review sheet
  corpus/              provenance gate, fetch, filter, masks, archive builder
  tests/               30 tests, no GPU or mediapipe required
```

Nothing under `tools/` has been run against real data. The eval harness was
validated end to end against `pose-master/.../tests/data/mediapipe.pose`
rendered through `PoseVisualizer`, which is how the two bugs in section 3 were
found — but MediaPipe detects no person in a stick-figure render, so the
scoring path has never produced a non-NaN PCK. **Expect to debug it on first
contact with real renders**, and treat an all-NaN report as a harness problem
until proven otherwise.
