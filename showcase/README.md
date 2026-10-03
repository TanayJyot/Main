# Showcase: what a bigger sign vocabulary makes possible

A **non-commercial** demo for Deaf community members. It shows the same
English sentences signed side by side:

| Column | Source | Use |
|---|---|---|
| **Fluent signer** (optional) | A Deaf translator signing the whole sentence: FLEURS-ASL or 2M-Flores-ASL (CC BY-SA 4.0) | Any use, with credit and share-alike |
| **Prototype** | PopSign, 254 words (CC BY 4.0) | Any use, with credit: the only signs a product may use today |
| **Community preview** | Signing Savvy + ASL Citizen + PopSign (+ fingerspelling) | **Non-commercial only**, by permission |

All columns are drawn as the same skeleton, so the differences people see are
vocabulary and signing, not drawing. [COVERAGE.md](COVERAGE.md) has the numbers
behind the pitch. For example, 1,000 well-chosen signs would cover more
everyday words than all 2,731 of ASL Citizen's.

## Rules for showing it

- **Non-commercial only.** Signing Savvy and ASL Citizen gave ASLytics
  permission to use their signs for non-commercial purposes
  ([DATA_LICENSES.md](../DATA_LICENSES.md)). A community session, a demo or
  a research write-up is fine. A paid product, an ad or a sales pitch is not.
  Every page and every community-preview video says "non-commercial use only".
- **Credit every source on screen.** The gallery, the `/showcase` page and the
  deck list them. Each lexicon folder's `ATTRIBUTION.txt` has the wording.
- **Ask before posting videos publicly.** The permissions say non-commercial
  use. Check with the two sources before putting videos on social media or a
  public site.
- **It is not a replacement for interpreters.** Present it as research and
  consultation: we are asking what the community wants.
- Nothing here commits sign data. Every output folder carries a `.gitignore`
  of `*`.

## Build it (on the GPU laptop)

PowerShell. In bash, replace `$env:NAME = "value"; ` with `NAME=value `.

**1. PopSign lexicon.** Already built as `lexicon/popsign` (prototype/README.md).

**2. ASL Citizen, every sign.** This downloads about 6,900 clips: up to 3
signers for each of 2,288 signs, about 4 GB out of the 42.8 GB zip. Then it
converts them. It needs mediapipe 0.10.21.

```
python showcase/citizen.py words      # how many signs and clips; reads only the CSVs
python showcase/citizen.py fetch
python showcase/citizen.py convert
python showcase/citizen.py export --out lexicon/aslc
```

**3. Signing Savvy.** First fetch one video per word into
`.work/signingsavvy/videos/`:

- Name each `<word>.mp4`, or `<word>__<n>.mp4` when the site lists several
  signs for a word.
- Look words up in [target_words.txt](target_words.txt) order, the most-used
  first.
- Fetch politely: at most one page a second, resume after a stop, and record
  each video's page URL.

Then:

```
python showcase/video_lexicon.py --videos .work/signingsavvy/videos --out lexicon/signingsavvy `
  --source "Signing Savvy" --license "Non-commercial use only, by permission of Signing Savvy" `
  --non-commercial --credit "Signs from Signing Savvy (signingsavvy.com), used with permission for non-commercial purposes."
```

**4. Stack the lexicons**, best-recorded first. Add `--layer lexicon/fingerspelling`
once the letters exist (prototype/README.md, Fingerspelling; FSboard on Kaggle
is CC BY 4.0 and needs no competition rules).

```
python showcase/stack_lexicons.py --layer lexicon/signingsavvy --layer lexicon/aslc --layer lexicon/popsign --out lexicon/community
```

**5. Fluent-signer sentences (optional, recommended).**

- Take 10–15 short, everyday sentences from FLEURS-ASL
  (`kaggle.com/datasets/googleai/fleurs-asl`) or 2M-Flores-ASL
  (`huggingface.co/datasets/facebook/2M-Flores-ASL`).
- Save each as `<name>.mp4` with its English in `<name>.txt`, and its gloss
  in `<name>.gloss.txt` if the dataset has one, all in one folder.

Then:

```
python showcase/natural.py --clips data/natural --source "FLEURS-ASL (CC BY-SA 4.0)"
```

**6. Render the gallery:**

```
python showcase/run_showcase.py --natural .work/showcase/natural
```

Open `.work/showcase/index.html`. Each sentence has one side-by-side video and
a list of what each column signed, spelled and missed.

**7. Live, so people can type their own sentences:**

```
python app.py
```

Then open <http://127.0.0.1:5000/showcase>. The columns come from
`ASLYTICS_SHOWCASE_TIERS` (default: `lexicon/popsign` and `lexicon/community`).

## Sources we do not use, and why

| Source | Why not |
|---|---|
| Handspeak, Lifeprint (ASLU), Spread the Sign, ASL-LEX videos | Their terms forbid copying or using videos in apps without permission, and we have not asked them. |
| WLASL, MS-ASL, ChicagoFSWild | Scraped from those sites and YouTube without the signers' consent; academic use only; many links dead. |
| YouTube-ASL, YouTube-SL-25, OpenASL | Only lists of YouTube videos; the videos belong to their uploaders, and YouTube's terms forbid downloading. OpenASL is also no-derivatives. |
| ASL Signbank (about 4,400 signs, CC BY-NC-SA) | Allowed for non-commercial use with credit, so it could be added. Ask its maintainers before a bulk download. |
| NVIDIA ASL 1000, Sem-Lex, ASLLRP Sign Bank | Behind request forms; the team's call. |

[DATASETS.md](DATASETS.md) catalogues 30 sources with their licences.
