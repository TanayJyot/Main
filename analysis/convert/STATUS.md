# Lexicon conversion: status (laptop session)

Channel for the cloud session on `claude/lexicon-eval`. Newest entry first.

---

## Showcase v3: started (2026-10-07)

Owner confirmed **Signing Savvy** to me directly; SpreadTheSign, Lifeprint
and SignASL.org are **not yet confirmed to me**, so this run fetches Signing
Savvy only (`build_all.py --sites signingsavvy`, added in 729bc1a) plus ASL
Citizen. No `~/.kaggle/kaggle.json`, so FSboard and FLEURS-ASL are skipped.
100-word trial first, then the full run; ETA after the trial. Disk is tight
(29 GB free).

---

## Prototype run 2 (2026-09-30 ~05:30 UTC): trim + floor, plus three fixes

**Short version:** the trim was hidden by a cache bug, and the real cause of
the slow videos was frame rate, not idle time. Both are fixed on
`claude/popsign-prototype` @ 6046bdb. The TREE flip was my dominance rule,
fixed on `claude/lexicon-convert` @ 9ed9d02. demo_7: **28 s → 12.5 s**, no
handedness flip.

### Fixes (with tests)

1. **Frame rates (concatenate.py).** 75 of 239 PopSign signs are **120 fps**
   (the rest 30, one 60). `concatenate_poses()` played everything at the
   first pose's fps, so 120 fps signs ran **4x slow**. DRINK has 3.4 s of
   signing and filled 13.6 s. New `match_frame_rates()` resamples to the
   lowest fps in the sentence before joining. "please drink water"
   14.7 → 4.4 s. The old lexicon mixed 24/30/60, so **the original app had
   this bug too**. `tools/tests/test_concatenate_fps.py` 3/3; it fails on the
   old code (14.1 s vs 8.9 s expected).
2. **Clip cache (asl_renderer.py).** The key was glosses + `RENDER_VERSION`,
   so after rebuilding `lexicon/popsign` `run_demo.py` served the **old**
   videos. The first rerun after your trim showed demo_7 at exactly 28.0 s
   again. The key now includes each sign file's path, size and mtime.
   `RENDER_VERSION` → 2. New test in `test_renderer.py` (11/11).
3. **Dominance (my select_clips.py).** Wrist travel called TREE's untracked
   arm dominant (left hand seen in 1% of frames, right in 82%) and mirrored
   it. Now the hand seen in clearly more frames (> 0.2 apart) is dominant, and
   travel breaks near-ties. 12 of 246 picks changed (tree, doll, nose, orange,
   icecream, chin, finger, taste, dry, boat, farm, weus). As a side effect the
   presence floor now rejects **2** signs, not 16, because presence is now
   measured on the tracked hand.

### Build output (after all three fixes)

```
no clip for 4 labels: no please pretty scissors
left out 2 signs with hands seen in < 30% of frames: minemy yourself
254 words from 244 PopSign signs -> lexicon\popsign
average sign length 2.8 s -> 2.3 s after trimming
use it:  ASLYTICS_LEXICON_DIR=lexicon\popsign
```

Trimmed sign lengths: **median 2.12 s**, p90 4.09 s, max 7.38 s; **54 of 254
over 3 s**.

### Tests

`test_popsign_lexicon.py` 10/10, `test_pipeline_env.py` 10/10,
`test_renderer.py` 11/11, `test_concatenate_fps.py` 3/3,
`test_gloss_parse.py` 4/4.

### `run_demo.py` output (verbatim, filtered as before; cache cleared first)

```
the dog is hungry
  signed:  dog hungry
  video:   C:\Users\tjsin\Documents\Main-prototype\.work\demo\demo_0.mp4  (12.7 s)

my cat likes milk
  signed:  cat milk like
  skipped: my
  video:   C:\Users\tjsin\Documents\Main-prototype\.work\demo\demo_1.mp4  (12.6 s)

where is the blue book?
  signed:  blue book where
  video:   C:\Users\tjsin\Documents\Main-prototype\.work\demo\demo_2.mp4  (12.3 s)

please drink water
  signed:  water drink
  skipped: please
  video:   C:\Users\tjsin\Documents\Main-prototype\.work\demo\demo_3.mp4  (12.7 s)

the frog is green
  signed:  frog green
  video:   C:\Users\tjsin\Documents\Main-prototype\.work\demo\demo_4.mp4  (12.9 s)

grandma and grandpa are happy
  signed:  grandma grandpa happy
  skipped: and
  video:   C:\Users\tjsin\Documents\Main-prototype\.work\demo\demo_5.mp4  (12.1 s)

the girl likes pizza and ice cream
  signed:  pizza girl like
  skipped: and ice cream
  video:   C:\Users\tjsin\Documents\Main-prototype\.work\demo\demo_6.mp4  (12.8 s)

yesterday the boy saw a yellow bird in the tree
  signed:  yellow yesterday boy bird tree see
  video:   C:\Users\tjsin\Documents\Main-prototype\.work\demo\demo_7.mp4  (13.8 s)

it is hot outside, go to the pool
  signed:  pool outside go hot
  video:   C:\Users\tjsin\Documents\Main-prototype\.work\demo\demo_8.mp4  (13.0 s)

thank you for the gift
  signed:  gift thank
  skipped: you
  video:   C:\Users\tjsin\Documents\Main-prototype\.work\demo\demo_9.mp4  (13.1 s)

10/10 sentences rendered; 30 words signed, 7 skipped.
```

Video lengths (the "(N s)" above is generation time, not video length):
demo_0 6.2, demo_1 5.3, demo_2 4.1, demo_3 4.1, demo_4 3.3, demo_5 4.7,
demo_6 5.3, **demo_7 12.5 (was 28.0)**, demo_8 8.8, demo_9 7.0 s. No frozen
frames in any.

### Your four questions (contact sheets of demo_0 and demo_7; TREE is the two-handed sign)

1. **Is each sign roughly 1–2 s?** Mostly: median 2.1 s. But 54 signs are
   over 3 s. DOG is 5.05 s untrimmed: raise, ~3.5 s at the shoulder with
   finger movement (repeated snaps), lower. Hand-shape change keeps the whole
   hold "active", so the trim correctly keeps it.
2. **Is any sign cut off mid-movement?** None seen. HUNGRY's raw clip is only
   1.2 s (hand rises from rest to head height and holds), so nothing was cut.
   DOG's start is intact.
3. **Is the reach-for-the-phone tail gone?** My earlier diagnosis was
   **wrong**. The hand rising to head height at the end of demo_0 is the
   *whole* HUNGRY clip, not a tail. It doesn't match the usual description of
   HUNGRY (C-hand moving down the chest), so treat it as a questionable pick,
   not a trim problem.
4. **Does any handedness flip remain?** Not in demo_7 after fix 3. Every sign
   is on the figure's right. TREE now shows as a one-handed raised hand,
   consistent with PopSign's one-handed recordings.

### On the trim thresholds

I see no sign cut mid-movement, so I **don't** suggest loosening it. It errs
long rather than short. The long signs are real holds or repetitions, not
idle. Capping repetitions (e.g. DOG's snaps) would need sign-specific
knowledge; I'd leave it for a signer's review. Not tuned against the old
lexicon.

---

## Prototype run: done (2026-09-30 ~04:10 UTC)

**Verdict: it works end to end, the signs are placed plausibly, but it is
too slow to read and some picks are bad data.** Details below. Not reviewed by
a signer.

### Lexicon

- 1,289 PopSign clips converted (<= 6 signers per label, `non-game/train`,
  `val` only when train had fewer than 6), 0 failures, 0 spec mismatches.
- `lexicon.json`: **257 words from 246 signs**. `labels_missing`: **no,
  please, pretty, scissors** (no non-game clips at all).
- 94 of 246 picks were mirrored (38%). Far more than left-handedness would
  explain; most likely signers holding the phone in the right hand.
- **Weak picks:** 32 labels whose best clip has hand presence < 0.3 (bad, bath,
  brother, can, chin, dad, dance, doll, dry, farm, finger, giraffe, go, hide,
  icecream, into, minemy, morning, nose, on, orange, pig, puzzle, shoe, sleep,
  taste, that, time, tree, weus, white, yourself). Minimum is 0.0.

### Tests

`test_popsign_lexicon.py` 6/6, `test_pipeline_env.py` 10/10,
`test_gloss_parse.py` 4/4 (new, see below). `aslytics_env.py` prints `ready`.

### `run_demo.py` output (verbatim; MediaPipe/TF log lines filtered)

```
the dog is hungry
  signed:  dog hungry
  video:   C:\Users\tjsin\Documents\Main-prototype\.work\demo\demo_0.mp4  (15.8 s)

my cat likes milk
  signed:  cat milk my like
  video:   C:\Users\tjsin\Documents\Main-prototype\.work\demo\demo_1.mp4  (10.1 s)

where is the blue book?
  signed:  blue book where
  video:   C:\Users\tjsin\Documents\Main-prototype\.work\demo\demo_2.mp4  (10.1 s)
  skipped (no sign in the lexicon): please

please drink water
  signed:  water drink
  skipped: please
  video:   C:\Users\tjsin\Documents\Main-prototype\.work\demo\demo_3.mp4  (11.2 s)

the frog is green
  signed:  frog green
  video:   C:\Users\tjsin\Documents\Main-prototype\.work\demo\demo_4.mp4  (9.8 s)
  skipped (no sign in the lexicon): and

grandma and grandpa are happy
  signed:  grandma grandpa happy
  skipped: and
  video:   C:\Users\tjsin\Documents\Main-prototype\.work\demo\demo_5.mp4  (12.4 s)
  skipped (no sign in the lexicon): and ice cream

the girl likes pizza and ice cream
  signed:  pizza girl like
  skipped: and ice cream
  video:   C:\Users\tjsin\Documents\Main-prototype\.work\demo\demo_6.mp4  (10.1 s)

yesterday the boy saw a yellow bird in the tree
  signed:  yellow yesterday boy bird tree see
  video:   C:\Users\tjsin\Documents\Main-prototype\.work\demo\demo_7.mp4  (12.5 s)

it is hot outside, go to the pool
  signed:  pool outside go hot
  video:   C:\Users\tjsin\Documents\Main-prototype\.work\demo\demo_8.mp4  (10.8 s)
  skipped (no sign in the lexicon): you

thank you for the gift
  signed:  gift thank
  skipped: you
  video:   C:\Users\tjsin\Documents\Main-prototype\.work\demo\demo_9.mp4  (9.8 s)

10/10 sentences rendered; 31 words signed, 6 skipped.
```

Total wall time 1 m 53 s for 10 sentences, about 10-16 s each. Most of that
is loading Stanza (~27 s) and rendering, not signing.

### What the videos look like (contact sheets of demo_0, demo_1, demo_7, plus "all animals are bad")

- **Good:** continuous motion, 0 frozen frames, no jumps at sign boundaries.
  Dominant hand is consistently on the figure's right, except below. Sign
  locations match the usual descriptions: BAD goes chin then down; ANIMAL is a
  claw at the chest; DOG is at the shoulder.
- **Too slow to read:** ~4-5 s per sign. `demo_7` (6 signs) is **28 s**.
  Cause: `concatenate.trim_pose()` keeps frames where wrist is above elbow,
  but PopSign signers keep the signing hand up the whole clip (phone in the
  other hand), so **nothing is trimmed**. Verified: animal 190 → 190 frames,
  bad 137 → 137. Clip tails include non-sign movement. At the end of
  `demo_0` the hand reaches above the head, probably reaching for the phone.
  **Fix needed:** a motion-based trim (keep frames where the dominant wrist
  moves), for PopSign at least.
- **Handedness flips mid-sentence on TREE** (`demo_7`, 16-25 s). TREE's only
  candidate has hand presence 0.015, so my dominance rule guessed from almost
  no data and mirrored it wrongly. **Fix needed (mine):** a minimum-presence
  floor. A label whose best clip is below it should be treated as missing,
  not shipped. Proposed 0.3: content-blind, but drops the 32 labels above.
  Your call.
- **One-handed signs only:** PopSign is phone-selfie data. Two-handed signs
  (ANIMAL, TREE) appear one-handed or with a partial second hand. The
  non-dominant arm is often a stub. Dataset limitation.

### `/sentence` page

`ASLYTICS_LEXICON_DIR=lexicon/popsign ASLYTICS_SKIP_MISSING=1 python app.py`:
GET shows the credit **"PopSign ASL v1.0 (CC BY 4.0)"**. POST "the cat is
happy" returned a page with `<video>` (served 200 `video/mp4`, 876 KB),
"Signed: cat happy", in **11.5 s**. The YouTube page `/` was **not tried**: it
renders every caption of a video, which is minutes of work, and
`youtube_transcript_api` is the scraping concern from HANDOFF.

### Fixes

1. **Pushed to `claude/popsign-prototype` @ 07798a3: stanfordnlp → Stanza.**
   stanfordnlp 0.2.0 cannot run on Python 3.10+:
   - torch 2.14: models fail to load ("Vector file is not provided"; the real
     cause is `torch.load` weights_only).
   - torch 2.5.1: `masked_fill_ only supports boolean masks, but got mask with
     dtype unsigned char` (depparse).
   - torch 1.13.1: some sentences work, others crash in the lemmatiser:
     `index_select(): Expected dtype int32 or int64 for index`.

   Stanza 1.14 (Apache-2.0, same EWT models) with torch 2.14 works. `start.py`
   changes only field names (id/head/deprel), and the gloss rules are
   untouched. New `tools/tests/test_gloss_parse.py`. Models now download from
   huggingface.co, **which your container blocks**; the command is in
   requirements.txt / README / install.sh.
2. **Needed, not done:** motion-based trim (above).
3. **Needed, not done (mine):** presence floor in `select_clips.py`
   (above).
4. **Small:** `run_demo.py` prints the "skipped (no sign in the lexicon)" line
   under the *previous* sentence: stderr is unbuffered, stdout is not.
5. **Small:** the repo tracks 8 `.pyc` files. Running `app.py` modifies two
   of them (`__pycache__/merge_asl_clips.cpython-310.pyc`,
   `utils/__pycache__/youtube_caption_utils.cpython-310.pyc`). Restored before
   committing; they should be untracked.
6. `stanfordnlp.download()` prompts interactively (moot after the swap).

### Environment

Prototype run from a separate worktree (`Documents/Main-prototype`) with its
own `.venv`: torch 2.14 CPU, stanza 1.14, mediapipe 0.10.21 (unchanged),
numpy 1.26.4. No GPU: pip MediaPipe's Holistic is CPU-only on every platform.
The exported label folder is at `Documents/popsign_labels`, outside git.

---

## Prototype run: started (2026-09-30 01:50 UTC)

PopSign only, per the new plan; the ASL Citizen conversion is stopped (files
kept, nothing deleted). **~1,400 PopSign clips** (250 labels, <= 6 signers,
`non-game/train` then `val` only if train has fewer than 6 signers):
59 labels downloaded, 306 clips ready to convert now. **ETA ~2 h**, bound by
the download (one Range request per tar entry). Conversion runs as labels
finish.

---

## Licence check, 2026-09-30 (read-only; only the 1.9 MB MS-ASL zip downloaded, nothing committed)

### 1. Hugging Face `akasheroor/American-Sign-Language-Dataset`: MIT tag is not credible

- **Where:** dataset card front matter `license: mit`; the card's `## License`
  section is **empty**. API tags: `license:mit`.
- **Card text (verbatim):** "This dataset contains **108,618 videos**
  representing **2,208 ASL words** [...] The videos were **scraped, collected
  from multiple sources, and preprocessed** [...]". Citation: "American Sign
  Language Dataset, collected and preprocessed by Zahid Yasin Mittha, 2025."
  No source list anywhere on the card.
- **What it is:** videos (mp4). The API lists 99,997 mp4s (listing caps at
  100k).
- **Where the videos come from, by filename:**
  - **55,752 (55.8%) have exactly ASL Citizen's filenames.** I matched them
    against the 83,399 names in ASL Citizen's own split CSVs, e.g.
    `0002081503807414009-INHALE.mp4`. So over half the dataset is ASL Citizen
    (MSR licence: "non-commercial, non-revenue generating, research purposes
    only"; "you may not distribute the data") re-uploaded under MIT.
  - 14,522 `WORD_video_N.mp4`; 895 `*_aug_N.mp4` augmentations; 26 named
    like `A • ASL Dictionary.mp4`, the page-title format of an online ASL
    dictionary (probably Handspeak, not verified); ~28,800 other
    (`pear_5.mp4`, `peas_20241119_195754_1.mp4`).
  - **No WLASL-style ids** (`NNNNN.mp4`): 0 found.
- **Verdict:** unusable. The MIT tag cannot relicense ASL Citizen, and the rest
  has no stated source.

### 2. Kaggle `asthalochanmohanta/american-sign-language-asl`

- **Licence field (Kaggle API `licenseName`):** "Apache 2.0".
- **Description (verbatim, complete):** "ASL Video Dataset: Diverse and
  Extensive Collection of ASL Gestures for Training and Evaluation in Machine
  Learning Models. Feel free to adjust the wording based on the specific
  features, focus, or characteristics of your video dataset. [...] Each file
  [...] represents a video captured at 30 frames per second (fps) with a
  resolution of 640 x 480 pixels." (The "feel free to adjust the wording"
  sentence is template text left in.)
- **What it is:** videos, 3,590 mp4s (3.37 GB): train 2,850 / val 404 /
  test 336. **47 words/phrases**: again, bad, bathroom, book, busy, do not
  want, eat, father, fine, finish, forget, go, good, happy, hello, help, how,
  i, learn, like, meet, milk, more, mother, my, name, need, nice, no, please,
  question, right, sad, same, see you letter [sic], thank you, want, what,
  when, where, which, who, why, wrong, yes, you, your.
- **Source:** not stated. Filenames are recording timestamps
  (`again_asl_video_2023-12-12_12-32-39.mp4`, Oct–Dec 2023), which suggests
  self-recorded by the uploader. **No signer count, no consent statement, no
  statement that the signers are fluent or Deaf.**
- **Note:** these 47 words are exactly PopSign's everyday-word gaps (I, you,
  want, need, what, how, eat...). Apache 2.0 would allow commercial use, but
  with unknown signers and no consent record I would not ship on it without
  contacting the uploader. That is the user's call.

### 3. MS-ASL (download.microsoft.com, id=100121): C-UDA, and **URLs only**

- **Zip contents:** `README.md`, `MSASL_{train,val,test}.json`,
  `MSASL_classes.json`, `MSASL_synonym.json`,
  `C-UDA-0.1_annotated_discussion.pdf`. **No videos.** Each sample is a
  YouTube `url` + `start_time`/`end_time` + `box` + `signer_id`, e.g.
  `https://www.youtube.com/watch?v=C37R_Ix8-qs`. 25,513 samples, 1,000
  glosses, 222 signer ids.
- **README (verbatim):** "Licensed under the Computational Use of Data
  Agreement (C-UDA). Plaese refer to C-UDA-0.1_annotated_discussion.pdf for
  more information."
- **C-UDA 0.1, verbatim:**
  - "1.1. You may use, modify, and distribute the Data made available to you
    by the Data Provider under this C-UDA for Computational Use if you follow
    the C-UDA's terms."
  - "2.1 You agree that you will use the Data solely for Computational Use."
  - "3.1. You may redistribute the Data, so long as: 3.1.1. You include with
    any Data you redistribute all credit or attribution information that you
    received with the Data [...]; and 3.1.2. You bind each recipient to whom
    you redistribute the Data to the terms of the C-UDA."
  - "4.1. Data Provider does not represent or warrant that it has any rights
    whatsoever in the Data."
  - "5.1. 'Computational Use' means activities necessary to enable the use of
    Data (alone or along with other material) for analysis by a computer."
  - "5.5. 'Output' means the outcomes or results that you obtain from your use
    of Data that do not include more than a de minimis portion of the Data
    [...]. Artificial intelligence models trained on Data (and which do not
    include more than a de minimis portion of Data) are Output."
- **Correction for DATA_LICENSES.md:** its table says MS-ASL is a "Microsoft
  Research non-commercial research licence". The shipped licence is C-UDA,
  which has **no non-commercial clause**. But (a) the "Data" is URLs; the
  videos belong to YouTube uploaders, and 4.1 disclaims any rights in them;
  (b) a sign lexicon of `.pose` files is arguably Data in modified form, not
  de-minimis Output. So it is not a clean commercial source either. The
  project page (microsoft.com/en-us/research/project/ms-asl/) states no
  licence.

### 4 and 5. Google Kaggle competitions `asl-signs` and `asl-fingerspelling`: **not verified**

The Data tabs and rules need a Kaggle login. The API returned `401
Unauthenticated` and there are no Kaggle credentials on this laptop. What
third-party sources say, **not verbatim from Kaggle**:

- `asl-fingerspelling`: described as "provided by Google under CC-BY (CC BY
  4.0)". MediaPipe 0.9.0.1 landmarks (face 468, hands 21+21, pose 33), **no
  video**, of fingerspelled phrases, addresses, phone numbers and URLs by
  "over 100 Deaf signers" on smartphone selfie cameras. Continuous phrases,
  not isolated letters, so a per-letter fallback needs segmentation.
  (Sources: hackster.io "Insightful Datasets for ASL recognition";
  kaggle.com/competitions/asl-fingerspelling.)
- `asl-signs`: landmarks from PopSign, which its paper says "will be provided
  under the Creative Commons CC-BY 4.0 license". I found no statement of the
  competition data's own licence or rules.
- **Still open:** the rules' restriction on use outside the competition.
  Needs someone logged in to Kaggle to read Rules → "Competition Data".

### 6. Lingua Libre: **0 ASL recordings**

- Lingua Libre's own item for ASL is **Q806575** (Q14759 is Wikidata's id; it
  has no label on Lingua Libre).
- SPARQL `SELECT (COUNT(?r) AS ?n) WHERE { ?r prop:P2 entity:Q2 ; prop:P4
  entity:Q806575 }` returns **0**. The one entity linking to Q806575 is a
  speaker profile (type Q3), not a recording. So there are no ASL sign videos
  there, and no distinct words.

---

## 2026-09-29, 20:10 local: converting; ETA ~1 h, then calibrate

- Downloads done for ASL Citizen (5,253 clips, 2.9 GB); PopSign still
  running (one clip per signer). Both needed retries: this connection drops
  mid-read every few thousand requests.
- **Candidate cap:** ASL Citizen now uses at most 12 participants per label
  (ID order, each participant's first clip by filename), matching PopSign's
  12-signer cap. Content-blind. 2,064 ASL Citizen clips instead of 5,253,
  because MediaPipe is the bottleneck: ~90 ms/frame, 32 clips/min with 8
  processes (more processes were slower).
- `mirror()` verified: dominance flips, detection scores unchanged, mirroring
  twice returns the original.
- Next: `select_clips.py` → `out/manifest.csv` → your `calibrate.py
  --new_manifest` here, results pushed to `analysis/convert/results/`. Then
  task 5.

---

## 2026-09-29, later: downloads running; label rule; manifest plan

Merged `claude/lexicon-eval` into this branch for `gloss_mapping.csv`. Thanks,
the mapping is what fetch and selection now key off.

### Please check: concept groups mix different signs

Keyed by concept, the table puts distinct ASL signs together:
`good` = BEST|BETTER|GOOD, `meet` = MEET|MEETING, `hour` = HOUR|8HOUR,
`old` = OLD|OLDEST, `call` = CALL1|CALL2 + PopSign `callonphone`. Taken at
concept level, pilot `best` would be represented by PopSign `better`, `late`
by `later`, `children` by `child`.

My rule, in `labels.py`, fixed before seeing any clip:

1. **exact**: labels equal to the pilot word after lower-casing and stripping
   variant digits (CALL1, CALL2 → call).
2. **concept fallback** only if *neither* dataset has an exact label. Six
   glosses use it: i→ME, it→THIS/IT + `hesheit`, she→`hesheit`,
   thing→THINGS, number→NUMBERS, mittens→`mitten`.

Result: 157 of 200 pilot glosses covered (PopSign 29, ASL Citizen 153),
43 old-only. You may want the same distinction in `calibrate.py`'s
multi-variant reporting.

### The manifest cannot travel, so I will run calibrate.py here

ASL Citizen's licence (`use.txt`, MSR) forbids distributing the data "or your
modifications", so converted `.pose` files cannot reach your container. Plan:
I produce `out/manifest.csv` in your schema, run
`analysis/eval/calibrate.py --new_manifest` locally against the old lexicon,
and commit only the JSON/markdown results under `analysis/convert/results/`.
If you change `calibrate.py`, push and I will re-run.

Manifest details, for when you read the results:

- `role=selected`: one clip per gloss. **PopSign preferred when it has the
  gloss** (CC BY 4.0, shippable), otherwise ASL Citizen.
- `role=calibration`: up to 6 other signers per source per gloss, one clip
  per signer.
- Extra columns: `gloss`, `source_best` (1 = best clip of that source, so you
  can also score ASL Citizen's pick where PopSign won), `dominant`,
  `presence`, `visibility`, `label_rule`.
- Selected left-dominant clips are mirrored in the mixed lexicon; the manifest
  paths point at the un-mirrored conversions, since your metric is
  mirror-invariant.

### Download method

- PopSign: remote tar listing via Range, first clip per signer, ≤12 signers
  per label, from `non-game/{train,val}`: ~1.5 GB instead of 19 GB.
- ASL Citizen: 5,253 clips for 172 labels via `remotezip` (~2.8 GB). Note:
  the Microsoft CDN sometimes rejects suffix ranges (`bytes=-N`) with 501;
  `support_suffix_range=False` fixes it.

Scripts: `fetch.py`, `convert.py`, `labels.py`, `select_clips.py`.

---

## 2026-09-29: environment report; split accepted

**Split accepted as proposed.** I take tasks 3 and 5 (download, convert,
re-render, end-to-end test); you take 1, 2 and 4. I stay inside
`analysis/convert/` on this branch.

### Environment

| | |
|---|---|
| OS | Windows 11 (10.0.26200), Git Bash + PowerShell |
| GPU | RTX 3070 Ti Laptop, 8 GB, driver 596.21 (MediaPipe runs on CPU here regardless) |
| Free disk | 101 GB on C: |
| Python | 3.10.11, `.venv` in the repo |
| mediapipe | 0.10.21 |
| pose-format | 0.14.1, `video_to_pose` on PATH in the venv |
| OpenCV | 4.11.0 |
| ffmpeg | yes (`C:\PATH_Programs\ffmpeg`) |
| conda | **no** |
| Old lexicon | on disk: 843 `.pose` (842 + stray `#combined_output2.pose`), `C:\Users\tjsin\Documents\ASLytics-RBC\.gitignore\generated_pose` |
| Checkout | `TanayJyot/Main` at `C:\Users\tjsin\Documents\Main`, this branch cut from `main` @ `9b4fa39` |
| Network | reaches signdata.cc.gatech.edu and download.microsoft.com. Laptop, so possibly on mobile data at times |

### Dataset access: what the downloads actually look like

Full downloads are not needed, and I will not do them.

- **PopSign v1.0 is 1.1 TB** in total. It is served as one tar per
  `category/split/sign`. For `boy`: `game/train` 3.4 GB, `game/test` 570 MB,
  **`non-game/train` 24 MB**, `non-game/val` 9 MB, `non-game/test` empty.
  Plan: `non-game/train` (+ `non-game/val`) only. These are the deliberate,
  non-game recordings, which is closer to citation form anyway.
- **ASL Citizen is one 42.8 GB zip**, but the server honours HTTP Range. I
  read the central directory remotely: 83,399 mp4s, median 0.54 MB, named
  `<id>-<GLOSS>.mp4`, plus `splits/{train,val,test}.csv` and `use.txt`. Plan:
  pull only the clips for pilot glosses via `remotezip`. Estimate: a few GB.

### Pilot coverage, first cut

Of the 200 glosses in `pilot_200.txt`, **26** match a PopSign label exactly
(case-insensitive). ASL Citizen's count comes next, from the split CSVs. I
will use exact / lemma matching for now and switch to your
`analysis/mapping/` table when you push it; please note here or on your branch
when it lands.

### Selection rule (fixed before looking at any clip)

Per gloss, per dataset, choose the clip with the **highest mean hand-landmark
presence** (fraction of frames where the dominant-hand landmarks are detected,
ties broken by mean visibility of the dominant wrist, then by filename). No
reference to the old lexicon. Dominant hand = the hand with more wrist
displacement over the clip; if left, mirror X (and swap left/right hand
components) before saving.

### Next

1. Pull ASL Citizen split CSVs + `use.txt`; count pilot coverage.
2. Download PopSign `non-game/{train,val}` for the matching pilot glosses.
3. Pull ASL Citizen clips for pilot glosses.
4. Convert, select, mirror, check against `old_lexicon_pose_spec.json`.

Nothing derived from any dataset is committed; `analysis/convert/.gitignore`
excludes the data directories.
