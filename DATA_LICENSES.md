# ASLytics — Data & Model Licence Audit

Scope: every dataset, pretrained model, and third-party corpus that the ASLytics
pipeline touches at build time or run time. Written for a commercial-use
assessment.

**Status, 2026-09-29.** This file was first written before the lexicon's
provenance was known, and it initially identified SHHQ as the blocker. Both have
since been settled, and this header reflects that. SHHQ turned out never to be
part of the product (§2); the real blocker is the scraped sign lexicon (§2b).

Pipeline recap (what consumes what):

```
YouTube URL
  -> utils/youtube_caption_utils.py      : youtube_transcript_api  -> caption text
  -> text-to-gloss/start.py              : StanfordNLP en_ewt models -> gloss list
  -> concatenate_pose_function/concatenate.py
       gloss_to_pose()                   : reads <gloss>.pose from the lexicon  <-- scraped, cannot ship (§2b)
       concatenate_poses()               : pose-format (MIT)
  -> pose_format.PoseVisualizer          : MediaPipe Holistic skeleton -> mp4
  -> merge_asl_clips.py                  : moviepy -> final_asl_output.mp4
```

**Bottom line:** one item blocks a commercial release — **the sign lexicon**,
842 `.pose` files scraped from ASL Signbank and Signing Savvy (§2b). The route
out is licensed video converted to `.pose` with the same pipeline: PopSign ASL
(CC BY 4.0, usable now) and ASL Citizen (commercial use requested from Microsoft;
awaiting reply). One item is a business decision rather than a blocker: GPL-3.0
code in `text-to-gloss/` (§3).

**Resolved:**

- **ASLytics' own code.** The original team's README licenses it CC BY-NC-SA 4.0.
  The code is owned by Japleen Kaur, so the owner can relicense it; recorded
  2026-09-29 on the user's report. If anyone else authored code in the original
  repository, their agreement is needed as well.
- **SHHQ.** Not in the product (§2).

## 1. Inventory

| # | Data asset | Where it enters the code | Licence | Commercial use |
|---|---|---|---|---|
| 1 | **Per-gloss ASL sign lexicon** (842 `<gloss>.pose` files) | `concatenate.py:gloss_to_pose()` via `lexicon_dir()` | Derived from **ASL Signbank (CC BY-NC-SA 4.0)** and **Signing Savvy (ToS forbids scraping)** — see §2b | **NO** |
| 2 | **UD English EWT treebank** (via StanfordNLP `en_ewt` models) | `text-to-gloss/start.py` `treebank='en_ewt'` | CC BY-SA 4.0 | Yes, with attribution + share-alike on the annotations |
| 3 | **MediaPipe Holistic** pretrained models | `mediapipe==0.10.21`, used by `pose-format` | Apache-2.0 | Yes |
| 4 | **YouTube caption transcripts** (runtime data, not a dataset) | `youtube_transcript_api` in `utils/youtube_caption_utils.py`, `server.py` | Not licensed to you — governed by YouTube ToS; the library scrapes an undocumented endpoint | Contractual risk, not a licence grant |
| 5 | `pose-format` sample `.pose` files (`tests/data/*.pose`) | test fixtures only, not shipped | MIT | Yes |
| 6 | Signspeech text-to-gloss **code** (not data) | all of `text-to-gloss/start.py` | **GPL-3.0-or-later**, © Javier O. Cordero Pérez | Allowed, but copyleft — see §3 |
| 7 | **PopSign ASL v1.0** (replacement candidate) | not yet integrated | CC BY 4.0 | Yes, with attribution |
| 8 | **ASL Citizen** (replacement candidate) | not yet integrated | Microsoft research licence; commercial use available on request | **Pending** — email sent, no reply yet |

Nothing else in the tree is a dataset. `videos/*.mp4`, `static/videos/*.mp4`,
`pose_output*.mp4` and `concatenate_pose_function/output_*.mp4` are all
**outputs** of the renderer (x264-encoded MediaPipe skeleton renders), not
source sign footage.

## 2. Resolved: SHHQ was never in the product

The first version of this audit identified SHHQ-1.0 as the blocker. That was
based on a dependency pin, `pose-to-video==0.0.1`, in
`pose-master/pose-master/requirements.txt`. That package's photorealistic
renderer models are trained on BIU-MG (permissive) and SHHQ-1.0 (non-commercial
research only; its agreement also covers "derived data", i.e. weights).

It turned out not to matter:

- the committed pipeline never imports `pose-to-video` — it renders stick
  figures with `pose_format.PoseVisualizer`, as `assets/result.png` shows;
- nothing photorealistic was ever trained or used by the project;
- the pin was dead, and has been removed.

If photorealistic rendering is ever wanted, train on **BIU-MG only**. Its README
says: *"You are permitted to use this data for any purpose, including commercial
purposes, without restriction."* §4a and §6 keep the original SHHQ migration
plan for reference; they are shelved.

## 2b. The blocker: the gloss→pose sign lexicon

**Provenance, established 2026-09-29.** The lexicon is **842 `.pose` files**
covering glosses **a–p only** — the scrape stopped partway through the alphabet.
Earlier notes that put it at ~4,400 signs were wrong. It was built by scraping
sign videos from two sites and running them through
`video_to_pose --format mediapipe`:

| Source | Terms | Consequence |
|---|---|---|
| **ASL Signbank** | CC BY-NC-SA 4.0 | Non-commercial. Usable only as a reference for what a sign should look like. |
| **Signing Savvy** | Paid commercial site; terms forbid scraping | A terms-of-service problem, not a licence. There is nothing to comply with. |

The `.pose` files being "just keypoints" does not change this: they are derived
from the source videos. The lexicon lives only in the original team's repository
(`Japleen-Kaur2409/ASLytics-RBC`, under `.gitignore/generated_pose/`) and must
never be committed here.

**Its role from now on: a held-out test set.** Compare replacement signs against
it; never tune, select or filter replacements to be closer to it, and never
train on it. Doing so would make the replacement derived data of a
CC BY-NC-SA source.

**Replacement sources.** Coverage is the share of signable tokens in everyday
English; see `analysis/coverage/coverage.md`.

| Source | Signs | Coverage | Licence | Status |
|---|---|---|---|---|
| Old lexicon | 842 | 33% | Scraped | Cannot ship; test set only |
| PopSign ASL v1.0 | 250 | 19% | CC BY 4.0 | Usable now |
| ASL Citizen | 2,731 | 63% | Research; commercial on request | Email to Microsoft sent 2026-09-29; awaiting reply |
| PopSign + ASL Citizen | — | 65% | — | Needs Microsoft's yes |

Also checked and ruled out: WLASL (C-UDA, academic only), MS-ASL (research
only), ASL-LEX (CC BY-NC 4.0), How2Sign (CC BY-NC 4.0), Sem-Lex (non-commercial).
Some community dataset catalogues list WLASL, ASL Citizen and ASL-LEX as CC BY
4.0. They are wrong; always read the dataset's own licence page.

## 3. Second blocker (different kind): GPL-3.0 in `text-to-gloss/start.py`

Not a dataset, but it will bite the same commercial release. The file is
Signspeech, © 2019 Javier O. Cordero Pérez, **GPL-3.0-or-later**:

```
# Signspeech is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
```

GPL permits commercial use, but it is copyleft: distributing a product that
incorporates this file obliges you to release the corresponding source of the
combined work under GPL-3.0. Note the current design invokes it as a
**separate process** (`conda run ... python3 start.py`, see
`utils/generate_asl_video.sh:24`), which is the weaker coupling — but the file
itself is vendored into this repo, so the repo is a GPL distribution today.

Everything else is permissive: `pose-format` is MIT (`pose-master/pose-master/LICENSE.txt`),
MediaPipe is Apache-2.0, Flask/moviepy/scipy are BSD/MIT.

## 4a. Alternatives for SHHQ (the renderer's appearance data)

> **Shelved 2026-09-29.** SHHQ was never in the product (§2). Kept for reference
> in case photorealistic rendering is revisited.

The fix here is surgical, because only half the training mix is contaminated.

1. **Rebuild the appearance corpus from SHHQ's upstream sources — but not all
   of them.** SHHQ was crawled from Flickr, Pixabay and Pexels, and the
   restriction is imposed by Shanghai AI Lab's redistribution agreement rather
   than by the underlying images. Collecting an equivalent set directly gives
   you a clean chain of title. The platforms are **not** interchangeable for
   this purpose, though:
   - **Pixabay** — explicitly permits AI/ML training, with a contributor
     opt-out you must honour. The cleanest of the three.
   - **Flickr**, filtered to CC0 / CC BY — fine, licence is per image, so keep
     the per-image record.
   - **Unsplash** — only via the **Unsplash Lite Dataset**, whose terms grant
     ML training for internal business purposes. The general Unsplash Licence
     does not, and it bars compiling photos into a competing service;
     Unsplash+ forbids AI training outright.
   - **Pexels — do not use.** Its Terms prohibit scraping and data mining
     "including for machine learning purposes." Crawling it would trade one
     licence problem for another.

   Budget for segmentation masks, which SHHQ ships and you would generate
   yourself: BiRefNet (MIT) or SAM 1 / SAM 2 (Apache-2.0) both work. SAM 3 is
   under Meta's custom SAM Licence — check it before using.

   One risk this option carries and BIU-MG does not: stock licences convey
   image rights, **not model releases**. A generative model trained on
   identifiable people can reproduce their likeness, which is a
   right-of-publicity exposure independent of the image licence.
2. **Train on BIU-MG alone.** It is already explicitly cleared for commercial
   use. You lose SHHQ's appearance diversity, but for this product that is
   arguably the right trade: a single consistent signer identity is what you
   want on screen anyway, not a generative model that can render arbitrary
   humans.
3. **Buy the appearance data.** Licensed human-imagery sets (e.g. RenderPeople
   scans, stock libraries with model releases) come with commercial terms and
   model consent already handled. Most academic human-parsing corpora —
   DeepFashion, Market-1501, LIP — are research-only, so they are not a
   shortcut.
4. **Ship the stick-figure renderer.** This is what the code does today and what
   `assets/result.png` shows. It is fully clear: `pose-format` is MIT, MediaPipe
   is Apache-2.0. Photorealism is a product decision, not a requirement — and
   there is real debate in the Deaf community about avatar quality, so shipping
   a legible skeleton is a defensible choice rather than a fallback.

Whichever you pick, **retrain rather than finetune from `sign/sd-controlnet-mediapipe`**.
Continuing from those weights carries the SHHQ derivation forward.

## 4b. Alternatives for the sign lexicon

Ordered by how cleanly they support a commercial product.

1. **Commission your own recordings (recommended).** Hire Deaf ASL signers to
   record the vocabulary you need, with a written model release and a work-for-hire
   or perpetual commercial licence, then run `video_to_pose --format mediapipe`
   to produce `.pose` files. Full ownership, no attribution chain, and it is the
   ethically defensible route for a Deaf-accessibility product. A few thousand
   citation-form signs is a tractable recording effort.

2. **PopSign ASL v1.0** (Georgia Tech / Google) — released under **CC BY 4.0**,
   which permits commercial use with attribution. Smartphone-recorded isolated
   signs. Limitation: ~250-sign vocabulary, too small on its own for open-domain
   YouTube captions, but it is a legitimate seed/bootstrap set. *Verify the
   licence text on the official distribution before relying on it.*

3. **Licence a commercial dictionary.** Signing Savvy and SpreadTheSign both
   offer paid/negotiated licensing for their video libraries. This is the fastest
   route to broad vocabulary coverage with a clean paper trail, and it replaces
   scraping with a contract.

4. **Synthesise the lexicon instead of sourcing it.** Drive a 3D avatar from
   HamNoSys/SiGML notation (e.g. JASigning-style pipelines) or from SignWriting.
   The notation is descriptive data rather than recorded performance, which
   sidesteps video corpus licensing — at the cost of noticeably lower naturalness
   and a large authoring effort per sign.

Explicitly **not** alternatives, despite being the obvious search hits: WLASL,
MS-ASL, ASL Citizen, How2Sign, ASL-LEX, Sem-Lex and SignSuisse are all
non-commercial. Swapping one for another does not fix the problem.

**YouTube-ASL** deserves a note: Google released the *video ID list* under
CC BY 4.0, but the videos themselves stay under their own YouTube licences and
the YouTube ToS, so it does not give you a commercially redistributable lexicon.

## 5. Other items to close before a commercial release

- **YouTube captions (§1 item 4).** `youtube_transcript_api` pulls transcripts
  from an undocumented endpoint. For a shipped product, move to the official
  YouTube Data API `captions` endpoint under its terms, or have users supply
  their own transcripts.
- **UD English EWT (§1 item 2)** is fine commercially but is share-alike; keep the
  attribution. If you want to drop the obligation and the GPL in §3 at the same
  time, reimplement the gloss rules on **spaCy** (MIT, with MIT-licensed
  `en_core_web_*` models) — the logic in `start.py:getLemmaSequence` is a
  POS/dependency rule set that ports over directly.
- **Account for the SHHQ agreement.** Someone applied for access and accepted
  its terms. Find out who, what was trained, and where those weights and any
  rendered output now live (local disks, HF Hub, demo videos, slide decks).
  Nothing derived from them can go into the product, and the agreement's
  no-redistribution clause covers sharing the images internally too.
- **Record provenance going forward.** Add a `DATA_SOURCES.md` entry for every
  corpus, with source URL, licence, download date, and commercial-use verdict,
  so this audit does not have to be reconstructed from import lists again.

## 6. Migration plan: replacing SHHQ without losing quality

> **Shelved 2026-09-29.** SHHQ was never in the product (§2). The current plan is
> the lexicon replacement in `HANDOFF.md`.

The goal is to end up with a renderer that scores the same as today's on data
you own. "The same" has to be measured, so the first phase is instrumentation,
not data collection.

### Phase 0 — Lock the baseline (before changing anything)

1. **Pin the current run.** Record the `pose-to-video` commit, the exact
   `train.sh` config (`runwayml/stable-diffusion-v1-5` +
   `lllyasviel/sd-controlnet-openpose`, 512×512, lr 1e-5, 20 epochs, batch 4),
   seeds, the environment lockfile, and a dataset manifest: which SHHQ images,
   which BIU-MG frames, and the train/val split.
2. **Build the eval harness now, on data you own** — held-out BIU-MG frames
   plus a fixed set of glosses from the lexicon:
   - **Pose fidelity:** re-run MediaPipe on each generated frame and compare to
     the conditioning skeleton (PCK / MPJPE), reported **separately for the
     hands**. Hand fidelity is what ASL legibility rests on and what diffusion
     models fail at; a whole-body average will hide it.
   - **Image quality:** FID/KID against held-out real signer frames;
     LPIPS/PSNR/SSIM on paired reconstructions.
   - **Temporal:** frame-to-frame warping error, to catch flicker that
     per-frame metrics miss entirely.
   - **Human:** a fixed panel of ~50 rendered signs rated for legibility by an
     ASL-fluent reviewer, ideally Deaf. This is the metric that decides the
     product; the others are proxies.
3. **Record baseline numbers.** Without these, "replicate our previous results"
   is not a checkable claim.
4. **Quarantine SHHQ.** Keep it on a research-only machine for comparison — that
   use is within its agreement — but never in product artefacts and never
   redistributed. Tag every SHHQ-derived checkpoint as unshippable.

### Phase 1 — Find out what SHHQ was actually buying (cheap, high information)

5. **Retrain on BIU-MG alone**, identical config and seed, and score it on the
   same harness. The gap to baseline is your replacement budget.
6. **If the gap is negligible, stop here.** SHHQ is 40K static images of people
   *not signing*, and the product renders one signer. The appearance diversity
   may be contributing less than its share of the training set suggests. This
   step costs one training run and can end the whole project.

### Phase 2 — Build a replacement corpus, if Phase 1 says you need one

7. **Preferred: record more signers.** BIU-MG is permissive because it was
   recorded with consent. Five to ten signers under written commercial releases
   gives you diversity *in domain* — people actually signing — rather than
   static standers, and it is likely to beat the SHHQ baseline rather than
   merely match it. It also removes the model-release exposure in §4a.
8. **Otherwise, collect a generic human corpus** from Pixabay / CC-licensed
   Flickr / the Unsplash Lite Dataset, per the constraints in §4a. Pexels is
   excluded.
9. **Match SHHQ's distribution** so the swap stays controlled: single person,
   full body visible, roughly frontal, 1024×512 crop, uncluttered background.
   Filter automatically — MediaPipe for full-body landmark visibility and a
   single subject, plus a frontality check on shoulder and hip keypoints.
10. **Regenerate the masks** with BiRefNet or SAM, then reuse pose-to-video's
    green-screen compositing. Write `clean_to_images.py` with the same CLI and
    the same `frames.zip` output contract as `shhq_to_images.py`, so `train.sh`
    does not change and the only variable is the data.
11. **Log provenance per image:** source URL, licence, retrieval date,
    contributor opt-out status.

### Phase 3 — Retrain and match

12. **Retrain from scratch** — SD-1.5 + sd-controlnet-openpose, never from
    `sign/sd-controlnet-mediapipe`, which would carry the SHHQ derivation
    forward. Same config, same seed.
13. **Score on the frozen harness.** If you fall short, iterate on the
    **corpus** — size, filter strictness, clean:BIU-MG ratio — with
    hyperparameters held fixed. Tuning both at once means you can no longer
    attribute the difference to the data swap.
14. **Ship when hand-PCK and the human legibility rating match baseline within
    tolerance.** FID is secondary; a lower FID with worse hands is a regression
    for this product.

### Phase 4 — Close out

15. Purge or quarantine SHHQ-derived weights and renders from everything
    product-adjacent — demo videos, decks, HF repos, teammates' disks.
16. **Note the remaining base-model question.** SD-1.5 ships under CreativeML
    OpenRAIL-M, which permits commercial use subject to use restrictions, but it
    was itself trained on LAION. The "derived weights" reasoning being applied
    to SHHQ is contested there rather than settled. That is a separate decision
    and worth making consciously rather than by default.
