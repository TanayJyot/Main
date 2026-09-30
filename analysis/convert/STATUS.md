# Lexicon conversion: status (laptop session)

Channel for the cloud session on `claude/lexicon-eval`. Newest entry first.

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
