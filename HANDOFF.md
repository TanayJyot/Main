# Handoff: sign lexicon replacement, laptop session → cloud agent

Written for the Claude agent picking this up in a cloud environment. Read this
first, then `DATA_LICENSES.md` §2b and §4b for background. Written 2026-09-29.

```
branch   claude/handoff-lexicon-baseline   (stacked on claude/stage-a-runnable, PR #2)
remote   https://github.com/TanayJyot/Main
```

The previous version of this file sent the next agent to a GPU to retrain a
photorealistic renderer without SHHQ. **That plan is shelved** (section 2). It
is still in git history (`b416b33`) and `DATA_LICENSES.md` §6 if it is ever
needed again.

---

## 1. Where things stand

The product turns caption text into ASL by looking up one `.pose` file per
gloss and stitching them (`concatenate.py`), then rendering a stick figure with
`PoseVisualizer`. The blockers to commercial use, in current order:

| # | Blocker | Status |
|---|---|---|
| — | ASLytics code is CC BY-NC-SA 4.0 | **Resolved.** The user reports approval from the original authors. Not yet recorded in `DATA_LICENSES.md`; ask the human for who, when and scope (section 6) |
| 1 | **The sign lexicon.** 842 `.pose` files scraped from ASL Signbank (CC BY-NC-SA 4.0) and Signing Savvy (paid site, ToS forbids scraping) | **Open. This is the job.** Measurement done; baseline built; replacement not started |
| 2 | GPL-3.0 in `text-to-gloss/start.py` | Open, a business decision, not a blocker. Out of scope unless asked |
| 3 | SHHQ behind `pose-to-video` | **Not real.** Nothing photorealistic was ever trained; `pose-to-video==0.0.1` is only a dead pin at `pose-master/pose-master/requirements.txt:64` |

Facts established by running things, not assumed:

- **The old lexicon is 842 signs, a–p only**, not the ~4,400 the earlier notes
  and `DATA_LICENSES.md` assume. The scrape stopped partway through the
  alphabet. `analysis/coverage/old_lexicon_glosses.txt` is the list.
- **Coverage of everyday English** (signable tokens, wordfreq proxy; full table
  in `analysis/coverage/coverage.md`):

  | lexicon | signs | coverage |
  |---|---|---|
  | Old lexicon | 842 | 33.3% |
  | PopSign ASL v1.0 (CC BY 4.0, usable now) | 250 | 19.1% |
  | ASL Citizen (Microsoft, research licence; commercial needs an email) | 2,731 | 63.3% |
  | PopSign + ASL Citizen | | 64.6% |

  So ASL Citizen alone beats the old lexicon by ~2×. PopSign alone is a
  regression.
- **The old lexicon's format** is full MediaPipe Holistic: 5 components, 576
  points, XYZC, mixed fps (24/30/60), median 62 frames.
  `analysis/old_lexicon_pose_spec.json` has the exact spec. Any new `.pose`
  must match it or `concatenate.py` will not stitch it.
- **A baseline now exists.** Nothing was ever measured before; the "previous
  results" were a demo. `analysis/baseline/build_baseline.py` renders a fixed
  input set from the old lexicon: 200 single signs (`coverage/pilot_200.txt`,
  100 high-frequency + 100 tail) and 12 hand-glossed sentences. Verified on
  this branch 2026-09-29: all 212 render, ~8 min on a laptop CPU.

## 2. The user's constraints

- **No email to Microsoft yet.** The user wants to get as far as possible
  without it. ASL Citizen can be downloaded and used under its research
  licence for *evaluation*; nothing built from it may ship until they say yes.
  Never send email or contact anyone on the user's behalf.
- **No fluent signer is available.** The earlier plan's headline metric
  (blind recognition by a Deaf signer) cannot be run. Work that needs a signer
  gets prepared (sheets, clips) but not scored. Say so plainly rather than
  presenting an automatic metric as a substitute for it. This question was
  asked and never answered in the last session; the honest answer is in
  section 4, task 4.

## 3. Setup

```bash
git fetch origin && git checkout claude/handoff-lexicon-baseline
python -m venv .venv && . .venv/bin/activate      # Python 3.10 is known-good
pip install -r tools/requirements.txt -r analysis/requirements.txt
python tools/tests/test_toolkit.py                 # expect 30/30
```

`tools/requirements.lock` is the full freeze where everything passed, but it
was taken on win64. Use it as a reference for versions if something breaks, not
as an install target on Linux.

**Get the old lexicon.** It is not in this repo and must never be committed
here. It lives in the original team's public repo. On Linux a sparse,
blob-less checkout of just the `.pose` files is ~480 MB:

```bash
git clone --filter=blob:none --no-checkout \
    https://github.com/Japleen-Kaur2409/ASLytics-RBC.git ../ASLytics-RBC
git -C ../ASLytics-RBC sparse-checkout set --no-cone '/.gitignore/generated_pose/*.pose'
git -C ../ASLytics-RBC checkout main
export ASLYTICS_LEXICON_DIR=$PWD/../ASLytics-RBC/.gitignore/generated_pose
ls $ASLYTICS_LEXICON_DIR/*.pose | wc -l            # 843: 842 signs + one stray #combined_output2.pose
```

Then reproduce the baseline before building on it:

```bash
python analysis/baseline/build_baseline.py        # writes analysis/baseline/out/ (gitignored)
```

## 4. Tasks, in order

Each is doable without the email and without a signer.

**1. Drop the dead `pose-to-video` pin.** Delete line 64 of
`pose-master/pose-master/requirements.txt` and update `DATA_LICENSES.md` §2
and §6 to say SHHQ was never in the product (§2a already half-says it).
Also correct the "~4,400 signs" figure to 842 wherever it appears. Small, and it
stops the next reader chasing the wrong blocker.

**2. Build the gloss mapping table.** Three naming schemes have to line up:
old lexicon filenames (`abhor.pose`, surface forms like `children`), PopSign
labels, and ASL Citizen labels (several variants per concept).
`analysis/coverage/coverage.py` already lemmatises and matches for coverage;
reuse its matching rather than writing a second one. Output one table: gloss → old file → PopSign
label(s) → ASL Citizen label(s). Everything below keys off it.

**3. Convert licensed video to `.pose`, pilot glosses only.** Download PopSign
and ASL Citizen (research use), and convert *only* the clips for glosses in
`pilot_200.txt` that each dataset covers. Use `video_to_pose --format
mediapipe` from `pose-format`, with `mediapipe==0.10.21`. Match
`old_lexicon_pose_spec.json`. Two things the old pipeline never had to handle:

- **Multiple signers per gloss.** Pick one clip per gloss by a written rule
  (e.g. highest mean hand-landmark confidence), not by eye.
- **Left-handed signers.** Detect the dominant hand and mirror to right, or a
  stitched sentence flips hands mid-sentence.

Keep raw video and converted `.pose` out of git. They go in a gitignored
directory like `analysis/baseline/out/`.

**4. Automatic comparison against the baseline.** For each pilot gloss, compute
DTW distance on normalised keypoints and hand-level PCK between the new `.pose`
and the old one. `tools/eval/metrics.py` has `pck`, `mpjpe` and
`hand_scale`/`shoulder_scale`, and `tools/eval/pose_fidelity.py` has
`align_by_name`. There is **no DTW and no bootstrap in the repo yet**; write
both (DTW to time-align before PCK, bootstrap over glosses for intervals).
**First calibrate the metric:** compute the same distance between *different*
glosses in the old lexicon. If same-gloss/different-signer distances are not
clearly separated from different-gloss distances, the metric cannot tell a
right sign from a wrong one, and you should say so rather than report it.

This is what can be done without a signer. It can show that a replacement is
*the same sign performed differently*. It cannot show that a Deaf viewer can
read it, and it is not a substitute for task 6.

Compare keypoints directly. Do **not** route this through
`tools/eval/pose_fidelity.py`'s render-then-re-detect path: MediaPipe finds
no person in a stick-figure render, so that path has only ever produced NaN.

**5. Render the replacement set with the same fixed inputs.** Re-run
`build_baseline.py` with `ASLYTICS_LEXICON_DIR` pointed at a directory that
mixes new `.pose` files with old ones for gaps, so that old and new clips exist
for the same 212 inputs. Then build the blind A/B sheet with
`tools/eval/make_human_eval_sheet.py`, ready for whenever a signer exists.

**6. Needs a signer. Prepare only.** Blind recognition on the 200 clips and
sentence-level A/B on the 12 sentences. Recognition compounds per sentence:
at 90% per sign an 8-sign line is read ~43% of the time. This is why it
matters and why task 4 cannot replace it.

**Optional, after 1–5:** a 200-sign synthetic pilot (LLM writes phonological
parameters → rule-based animator → `.pose`) for tail glosses no dataset covers.
Expect high error on rare signs. Fingerspelling and numbers are the one area
where synthetic is safe; if you build anything synthetic, start there.

## 5. Rules you must not break

- **The old lexicon is a test set.** Compare against it; never tune, filter
  or select new signs to be closer to it, and never train on it. Doing so makes
  the output derived data of a CC BY-NC-SA source and reopens the blocker.
- **Nothing from the old lexicon or ASL Citizen is committed.** That includes
  `.pose` files and renders. `analysis/.gitignore` covers `baseline/out/`;
  extend it for anything new. Scripts, gloss lists, specs and metric outputs
  are fine.
- **Do not upgrade MediaPipe past 0.10.21.** 0.10.30 removed
  `mediapipe.solutions`, which `pose-format` needs; 1.x breaks everything with
  an `AttributeError` deep in a worker.
- **`concatenate.py` reduces the holistic pose** (`is_reduce_holistic = True`,
  33 body points → 8). Match landmarks by name, never by index.
- **Do not reintroduce `/home/ellie/...` paths.** Use `ASLYTICS_LEXICON_DIR` /
  `lexicon_dir()` from PR #2.
- **Don't contact anyone.** The emails (Microsoft for ASL Citizen, the
  Signbank authors) are the user's to send.

## 6. Ask the human, don't guess

1. **The authors' approval for the code licence:** who gave it, when, in what
   form, and does it cover commercial use? Needed for a dated line in
   `DATA_LICENSES.md`.
2. **Is PR #2 going to merge?** This branch is stacked on it. If it is
   rejected, `build_baseline.py` needs its own lexicon path resolution back.
3. **Is a signer ever likely?** If never, the realistic ship path is ASL
   Citizen (licensed) plus a smaller vocabulary, not synthetic signs, because
   nothing can validate synthetic ones.

## 7. What is in the branch

```
HANDOFF.md                         this file
DATA_LICENSES.md                   the licence audit (partly out of date: see task 1)
analysis/
  coverage/coverage.py             coverage check; writes coverage.md, pilot_200.txt
  coverage/*.txt, *.csv            gloss lists: old lexicon, PopSign, ASL Citizen
  old_lexicon_pose_spec.json       the .pose format new files must match
  baseline/build_baseline.py       renders the fixed 200-sign + 12-sentence set
  requirements.txt                 simplemma, wordfreq
tools/                             licence/provenance toolkit, eval harness, 30 tests
tools/requirements.lock            known-good freeze (win64, Python 3.10.11)
```

The user's own notes (an Obsidian vault on their laptop) are not reachable
from here. Everything in them that matters is in this file.
