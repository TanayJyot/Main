# Lexicon conversion: status (laptop session)

Channel for the cloud session on `claude/lexicon-eval`. Newest entry first.

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
