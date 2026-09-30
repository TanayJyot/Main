# Lexicon conversion: status (laptop session)

Channel for the cloud session on `claude/lexicon-eval`. Newest entry first.

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
