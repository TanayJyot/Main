# Showcase: what a bigger sign vocabulary makes possible

A **non-commercial** demo for Deaf community members. It shows the same
English sentences signed side by side:

| Column | Source | Use |
|---|---|---|
| **Fluent signer** (optional) | A Deaf translator signing the whole sentence: FLEURS-ASL or 2M-Flores-ASL (CC BY-SA 4.0) | Any use, with credit and share-alike |
| **Prototype** | PopSign, 254 words (CC BY 4.0) | Any use, with credit: the only signs a product may use today |
| **Community preview** | Every source in [sources.py](sources.py), best first: Signing Savvy, ASL Citizen, PopSign, then SpreadTheSign, ASL Signbank, Lifeprint (+ Handspeak and ASLCORE once they send files, + fingerspelling) | **Non-commercial only**, by permission |

All columns are drawn as the same skeleton, so the differences people see are
vocabulary and signing, not drawing. [COVERAGE.md](COVERAGE.md) has the numbers
behind the pitch. For example, 1,000 well-chosen signs would cover more
everyday words than all 2,731 of ASL Citizen's.

## Rules for showing it

- **Non-commercial only.** Signing Savvy and ASL Citizen gave ASLytics
  written permission to use their signs for non-commercial purposes; Handspeak,
  SpreadTheSign, Lifeprint, SignASL and ASLCORE gave permission by call, with
  written notes to follow ([DATA_LICENSES.md](../DATA_LICENSES.md) section 0).
  Until a written note says otherwise, each is treated as non-commercial. A community session, a demo or
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

One command builds everything: ASL Citizen, the dictionary sites, the stacked
lexicon, a report and the gallery. It needs MediaPipe and the open internet,
so run it on the laptop, from the repo folder:

```
.venv\Scripts\python showcase\build_all.py
```

- It takes 6 to 8 hours, mostly MediaPipe, and keeps the laptop awake while it
  runs. Stop it whenever you like; running it again carries on.
- `python showcase/build_all.py --status` shows where it has got to. The log is
  `.work/build_all/build.log`, and the result is summed up in
  `.work/build_all/REPORT.md`: words per source, and the most-used words still
  without a sign.
- `python showcase/build_all.py --limit 100` is a ten-minute trial on the 100
  most-used words, without ASL Citizen.
- The gallery is `.work/showcase/index.html`. For the live page, run
  `python app.py` and open <http://127.0.0.1:5000/showcase>.

### Where each source's signs come from

`python showcase/fetch_sites.py --list` prints this table.

| Source | How | Notes |
|---|---|---|
| Signing Savvy | fetched, every target word | The site's first meaning of a word is used. `manifest.csv` records which ("meaning 1 of 8") for a signer to review. |
| ASL Citizen | `citizen.py` | Up to 3 signers for each of 2,288 signs, about 4 GB of the 42.8 GB zip. |
| PopSign | already built | `lexicon/popsign` (prototype/README.md). |
| SpreadTheSign | fetched, missing words only | Entries spelled exactly like the word. |
| ASL Signbank, on SignASL.org | fetched, missing words only | SignASL has no signs of its own: every video there is another owner's. Only ASL Signbank's are taken (CC BY-NC-SA 4.0), and only when the gloss is the word itself. To add another owner once they agree, pass it to `signasl_lookup(owners=...)`. |
| Lifeprint | fetched, missing words only | Its videos are on YouTube, which we do not download from. The animated GIFs kept on lifeprint.com are used: small and jerky, so many will fail the hand-tracking floor. Ask Dr. Vicars for the video files if you want this layer to be good. |
| Handspeak | **needs files** | handspeak.com turns automated readers away, so nothing is fetched. Ask Handspeak for the videos. |
| ASLCORE | **needs files** | Its videos are streamed from Vimeo and its robots.txt asks for a minute between requests. Ask RIT/NTID for the videos. |
| Fingerspelling | `prototype/fingerspelling.py` | Included when `lexicon/fingerspelling` exists (prototype/README.md). |

Files from an owner go in `.work/<source>/videos/` (`.work/handspeak/videos/`,
`.work/aslcore/videos/`) named `<word>.mp4`, or `<word>__<n>.mp4` for a word's
second and later signs. The next `build_all.py` run converts and stacks them.

### How the fetcher behaves

[fetch_sites.py](fetch_sites.py) asks each site for one sign per word, in
[target_words.txt](target_words.txt) order (the most-used words first):

- at most one request a second per site, more slowly if the site's robots.txt
  asks, and nothing robots.txt rules out;
- Signing Savvy is asked for every word; the others only for words that no
  earlier source signs, so they get a few hundred requests, not thousands;
- it names itself in its User-Agent, resumes after a stop, and records each
  video's page URL in `.work/<site>/manifest.csv`;
- it tries five common words first and skips a site if none yields a video
  (the pages have changed), and it stops at the first refusal (403, or
  repeated 429).

### The steps by hand

`build_all.py` runs these; use them to redo one part.

```
python showcase/citizen.py fetch
python showcase/citizen.py convert
python showcase/citizen.py export --out lexicon/aslc
python showcase/fetch_sites.py --have lexicon/aslc --have lexicon/popsign
python showcase/video_lexicon.py --videos .work/signingsavvy/videos --out lexicon/signingsavvy `
  --source "Signing Savvy" --license "Non-commercial use only, by permission of Signing Savvy" `
  --non-commercial --credit "Signs from Signing Savvy (signingsavvy.com), used with permission for non-commercial purposes."
python showcase/stack_lexicons.py --layer lexicon/signingsavvy --layer lexicon/aslc --layer lexicon/popsign --out lexicon/community
python showcase/run_showcase.py
```

**Fluent-signer sentences (optional, recommended).**

- Take 10–15 short, everyday sentences from FLEURS-ASL
  (`kaggle.com/datasets/googleai/fleurs-asl`) or 2M-Flores-ASL
  (`huggingface.co/datasets/facebook/2M-Flores-ASL`).
- Save each as `<name>.mp4` with its English in `<name>.txt`, and its gloss
  in `<name>.gloss.txt` if the dataset has one, all in one folder.

```
python showcase/natural.py --clips data/natural --source "FLEURS-ASL (CC BY-SA 4.0)"
python showcase/run_showcase.py --natural .work/showcase/natural
```

## Sources we do not use, and why

| Source | Why not |
|---|---|
| ASL-LEX videos | Its terms allow "personal searches" only, and we have not asked. |
| The other owners on SignASL.org (StartASL, ASLSearch, ASL Bricks, Elemental ASL Concepts, YouTube uploaders and others) | SignASL shows their videos but cannot give permission for them. Each owner would have to be asked. |
| WLASL, MS-ASL, ChicagoFSWild | Scraped from those sites and YouTube without the signers' consent; academic use only; many links dead. |
| YouTube-ASL, YouTube-SL-25, OpenASL | Only lists of YouTube videos; the videos belong to their uploaders, and YouTube's terms forbid downloading. OpenASL is also no-derivatives. |
| NVIDIA ASL 1000, Sem-Lex, ASLLRP Sign Bank | Behind request forms; the team's call. |

[DATASETS.md](DATASETS.md) catalogues 30 sources with their licences.
