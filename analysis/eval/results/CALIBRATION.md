# Metric calibration — old lexicon only

Run 2026-09-29 by `calibrate.py` on the 200 pilot signs (`analysis/coverage/pilot_200.txt`),
old lexicon fetched from the original team's repository. Raw numbers:
`calibration_old_only.json`. Distances are DTW-aligned, in normalised units
(arms: shoulder widths; hands: hand lengths). See `pose_compare.py`.

| Check | n | Median distance | Separation from different signs (AUC) |
|---|---|---|---|
| Different signs (null) | 2,000 pairs | 0.56 (5th pct 0.27, 95th 0.81) | — |
| Same sign, synthetically altered: speed ×0.7–1.4, jitter, mirrored half the time | 200 | 0.05 | **1.00** |
| Old-lexicon variants of one word (`bake_1` vs `bake_2`, …) | 5 | 0.47 | 0.76 |

Retrieval on the synthetic copies: the altered sign's nearest original, among
all 200, was itself **99.5%** of the time (chance: 0.5%).

## What this does and does not show

It shows the metric ignores what it should ignore: speed, handedness, small
noise, body size and framing.

It does **not** show that the metric can tell a correct replacement from a
wrong one. Real signers differ in ways a perturbation does not model, and real
same-sign distances may land anywhere up to the null's lower tail (0.27).
That is settled only by the real calibration: the same gloss from two or more
PopSign / ASL Citizen signers, which gives `real_separation_auc` in
`calibrate.py --new_manifest`. **Until that number exists, do not report
old-vs-new distances as evidence of quality.**

The old variant pairs are too few (5) to conclude anything. They may be
genuinely different signs for the same English word, which is also why
`gloss_mapping.csv` flags multi-variant concepts.
