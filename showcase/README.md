# Showcase: what our own ASL dataset would make possible

A demo for Deaf community members. It shows the same English sentences signed
three ways, side by side:

| Column | Source | Can we ship it? |
|---|---|---|
| **Fluent signer** (optional) | A Deaf translator signing the whole sentence, from 2M-Flores-ASL or FLEURS-ASL (CC BY-SA 4.0) | Yes, with credit and share-alike |
| **Today** | Our prototype: PopSign, 254 words (CC BY 4.0) | Yes |
| **Research preview** | ASL Citizen's 2,731 signs + PopSign (+ fingerspelling) | **No.** Research only |

All three are drawn as the same skeleton, so the differences people see are
vocabulary and signing, not drawing. [COVERAGE.md](COVERAGE.md) has the numbers
behind the pitch, such as "1,000 well-chosen signs would cover more everyday
words than all 2,731 of ASL Citizen's".

## Rules for showing it

- **The research preview stays on the laptop.** ASL Citizen's licence allows
  "non-commercial, non-revenue generating, research purposes" only and forbids
  distributing "the data or your modifications". Show the gallery or the
  `/showcase` page from the laptop in the room or on a screen share. Do not
  upload, post, email or hand out the videos. Every research-preview frame
  says so on the video itself.
- **Frame it as research and consultation, not a product.** ASL Citizen's
  datasheet also says it should not be used for technology that "purports to
  replace sign language interpreters". This demo asks the community what they
  would want; it is not an interpreter replacement. The safest course is to
  ask Microsoft (ASL_Citizen@microsoft.com) before the session. That is the
  team's call.
- **Credit every source on screen.** The gallery and the page list them.
- Nothing here commits sign data. Every output folder carries a `.gitignore`
  of `*`.

## Build it (on the GPU laptop)

PowerShell. In bash, replace `$env:NAME = "value"; ` with `NAME=value `.

**1. PopSign lexicon.** Already built as `lexicon/popsign` (prototype/README.md).

**2. ASL Citizen, every sign.** This downloads about 6,900 clips (≤ 3 signers
for each of 2,288 signs, about 4 GB) out of the 42.8 GB zip, then converts
them. It needs mediapipe 0.10.21.

```
python showcase/citizen.py words      # how many signs and clips; reads only the CSVs
python showcase/citizen.py fetch
python showcase/citizen.py convert
python showcase/citizen.py export --out lexicon/aslc
```

**3. Stack the lexicons** (best-recorded first; add `--layer lexicon/fingerspelling`
once the letters exist):

```
python showcase/research_lexicon.py --layer lexicon/aslc --layer lexicon/popsign --out lexicon/research
```

**4. Fluent-signer sentences (optional, recommended).** Take 10–15 sentences
from 2M-Flores-ASL (`huggingface.co/datasets/facebook/2M-Flores-ASL`) or
FLEURS-ASL (`kaggle.com/datasets/googleai/fleurs-asl`). Pick short, everyday
ones. Put each as `<name>.mp4` + `<name>.txt` (English), and `<name>.gloss.txt`
if the dataset has a gloss, in one folder:

```
python showcase/natural.py --clips data/natural --source "2M-Flores-ASL (CC BY-SA 4.0)"
```

**5. Render the gallery:**

```
python showcase/run_showcase.py --natural .work/showcase/natural
```

Open `.work/showcase/index.html`. Each sentence has one side-by-side video and
a list of what each column signed, spelled and missed.

**6. Live, for people to type their own sentences:**

```
python app.py
```

Then open <http://127.0.0.1:5000/showcase>. The columns come from
`ASLYTICS_SHOWCASE_TIERS` (default: `lexicon/popsign` and `lexicon/research`).

## Sources we did not use, and why

| Source | Why not |
|---|---|
| Handspeak, Lifeprint (ASLU), Signing Savvy, Spread the Sign, ASL-LEX videos | Their terms forbid copying, downloading or using videos in apps without permission. The old lexicon was partly scraped from Signing Savvy; that is why it cannot ship. |
| WLASL, MS-ASL, ChicagoFSWild | Scraped from those sites and YouTube without the signers' consent; academic use only; many links dead. |
| YouTube-ASL, YouTube-SL-25, OpenASL | Only lists of YouTube videos; the videos belong to their uploaders, and YouTube's terms forbid downloading. OpenASL is also no-derivatives. |
| ASL Signbank (about 4,400 signs, CC BY-NC-SA) | **Allowed** for a non-commercial demo with credit, and the best extra vocabulary. Not used yet: ask its maintainers before a bulk download. Contacting them is the team's call. |
| NVIDIA ASL 1000 | Licence is for "access to technology for the Deaf community" with no redistribution; a request form is needed. The team's call. |
| Sem-Lex (3,149 signs), ASLLRP Sign Bank (about 6,000) | Research or education only, behind request forms. |

[DATASETS.md](DATASETS.md) catalogues 30 sources with their licences.
