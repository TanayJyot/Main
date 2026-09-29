# Gloss mapping — old lexicon ↔ PopSign ↔ ASL Citizen

Built by `build_mapping.py` from the gloss lists in `analysis/coverage/`. Keyed by English concept (lemma or whole phrase). Full table: `gloss_mapping.csv`.

## Sources

| dataset | labels in list | concepts after matching |
|---|---|---|
| Old lexicon | 840 files | 824 |
| PopSign ASL v1.0 | 250 | 256 |
| ASL Citizen | 2731 | 2267 |

## Overlap with the old lexicon

Only concepts present in both can be compared old-vs-new.

| | concepts shared with old |
|---|---|
| PopSign | 110 |
| ASL Citizen | 679 |
| PopSign or ASL Citizen | 685 |
| Old only (no licensed replacement) | 139 |

Of the 679 old ∩ ASL Citizen concepts, **130** have more than one variant on at least one side. The same English word may be a different sign there, so evaluation reports these separately.

## Pilot list (`pilot_200.txt`)

| | pilot glosses |
|---|---|
| matched to a concept | 200 / 200 |
| covered by PopSign | 34 |
| covered by ASL Citizen | 153 |
| covered by either | 157 |
| covered by neither | 43 |

## Labels that needed special handling

- old `don't` — contraction, matched as 'do not'
- popsign `glasswindow` — covers glass, window
- popsign `hesheit` — covers he, it, she
- popsign `minemy` — covers mine, my
- popsign `thankyou` — covers thank, thanks
- popsign `weus` — covers us, we
- citizen `A-LINEBOB` — phrase, kept whole
- citizen `CHEW2MOUTH` — phrase, kept whole
- citizen `HURDLE/TRIP1` — alternatives: hurdle, trip
- citizen `HURDLE/TRIP2` — alternatives: hurdle, trip
- citizen `SKI-CA` — -CA marker (constructed action)
- citizen `SPLASH-CA` — -CA marker (constructed action)
- citizen `STAND-UP` — phrase, kept whole
- citizen `STAYAWAKE24HRS` — phrase, kept whole
- citizen `STRETCH-CA` — -CA marker (constructed action)
- citizen `THIS/IT` — alternatives: this, it
- citizen `TOOTHBRUSH-CA` — -CA marker (constructed action)
- citizen `W.H.A.T` — fingerspelled
- citizen `WALK-TIGHTROPE-CL` — -CL marker (classifier)
