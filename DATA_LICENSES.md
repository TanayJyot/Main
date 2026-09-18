# ASLytics — Data & Model Licence Audit

Scope: every dataset, pretrained model, and third-party corpus that the ASLytics
pipeline touches at build time or run time. Written for a commercial-use
assessment.

Pipeline recap (what consumes what):

```
YouTube URL
  -> utils/youtube_caption_utils.py      : youtube_transcript_api  -> caption text
  -> text-to-gloss/start.py              : StanfordNLP en_ewt models -> gloss list
  -> concatenate_pose_function/concatenate.py
       gloss_to_pose()                   : reads <gloss>.pose from a local lexicon  <-- THE DATASET
       concatenate_poses()               : pose-format (MIT)
  -> pose_format.PoseVisualizer          : MediaPipe Holistic skeleton -> mp4
  -> merge_asl_clips.py                  : moviepy -> final_asl_output.mp4
```

## 1. Inventory

| # | Data asset | Where it enters the code | Licence | Commercial use |
|---|---|---|---|---|
| 1 | **Per-gloss ASL sign lexicon** (`<gloss>.pose` files) | `concatenate.py:gloss_to_pose()` → `.gitignore/generated_pose/{vocab}.pose` | **Undeclared in this repo** — see §2 | **Almost certainly NO** |
| 2 | **UD English EWT treebank** (via StanfordNLP `en_ewt` models) | `text-to-gloss/start.py:51` `treebank='en_ewt'` | CC BY-SA 4.0 | Yes, with attribution + share-alike on the annotations |
| 3 | **MediaPipe Holistic** pretrained models | `mediapipe==0.10.21`, used by `pose-format` for pose estimation/rendering | Apache-2.0 | Yes |
| 4 | **YouTube caption transcripts** (runtime data, not a dataset) | `youtube_transcript_api` in `utils/youtube_caption_utils.py`, `server.py` | Not licensed to you — governed by YouTube ToS; the library scrapes an undocumented endpoint | Contractual risk, not a licence grant |
| 5 | `pose-format` sample `.pose` files (`tests/data/*.pose`) | test fixtures only, not shipped | MIT | Yes |
| 6 | Signspeech text-to-gloss **code** (not data) | all of `text-to-gloss/start.py` | **GPL-3.0-or-later** | Allowed, but copyleft — see §3 |

Nothing else in the tree is a dataset. `videos/*.mp4`, `static/videos/*.mp4`,
`pose_output*.mp4` and `concatenate_pose_function/output_*.mp4` are all
**outputs** of the renderer (x264-encoded MediaPipe skeleton renders), not
source sign footage.

## 2. The non-commercial dataset: the gloss→pose sign lexicon

**This is the asset that blocks commercial use.**

Evidence in the repo:

- `pose-master/pose-master/concatenate_pose_function/concatenate.py:120`
  ```python
  def gloss_to_pose(list_of_gloss: List[str]) -> List:
      for vocab in list_of_gloss:
          pose_data = load_pose(f'/home/ellie/GitHub/ASLytics-RBC/.gitignore/generated_pose/{vocab}.pose')
  ```
- The path is hardcoded to one developer's machine and deliberately placed
  under a directory named `.gitignore/`, so the lexicon was **never committed**
  and its provenance was never recorded.
- `pose-master/pose-master/requirements.txt` pins `selenium`, `webdriver-manager`
  and `beautifulsoup4` — none of which any other part of this pipeline uses.
  That combination only makes sense for **scraping sign videos from a dictionary
  website**, which were then run through `video_to_pose --format mediapipe`
  (see the `pose-format` README) to produce the `.pose` files.

So the `.pose` files are derived works of some ASL sign-video corpus, and the
project has no record of which one. **Every realistic candidate is
non-commercial.** The `.pose` files being "just keypoints" does not launder
this: they are derivative works of the source videos.

| Candidate source | Licence | Commercial |
|---|---|---|
| WLASL | Computational Use of Data Agreement (C-UDA); project states academic/computational use only | No |
| MS-ASL | Microsoft Research non-commercial research licence | No |
| ASL Citizen (Microsoft) | MSR licence: "non-commercial, non-revenue generating, research purposes only" | No |
| ASL-LEX 2.0 | CC BY-NC 4.0 (database); reference videos licensed separately | No |
| How2Sign | CC BY-NC 4.0 | No |
| Sem-Lex | CC BY-NC | No |
| SignSuisse (what the upstream `spoken-to-signed-translation` ships) | Non-commercial; also DSGS/LSF-CH/LIS-CH, not ASL | No |
| Signing Savvy / SpreadTheSign / Handspeak (scraped) | All rights reserved; ToS forbids scraping and redistribution | No |

**Action required:** identify the actual source before shipping. Ask whoever
built `generated_pose/` (the `/home/ellie/...` machine), or inspect the
`.pose` file headers and the original scraper. Until then, treat the lexicon as
non-commercial and unshippable.

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

## 4. Alternatives for the sign lexicon

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
- **Record provenance going forward.** Add a `DATA_SOURCES.md` entry for every
  corpus, with source URL, licence, download date, and commercial-use verdict,
  so this audit does not have to be reconstructed from import lists again.
