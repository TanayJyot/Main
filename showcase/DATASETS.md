# ASL sign data: what exists and what we may use

Research notes, October 2026. Licences are quoted from each dataset's own page
where it could be read. **Unverified** marks what could not be checked (most
dataset sites are blocked from the cloud session). Always read the dataset's
own licence page before use: some community catalogues list WLASL, ASL Citizen
and ASL-LEX as CC BY 4.0, and they are wrong.

## The catalogue

### Isolated signs (one sign per clip): what a lexicon is made of

| Dataset | Size | Signers | Licence | Commercial | Community demo | Get it |
|---|---|---|---|---|---|---|
| **PopSign ASL v1.0** (Georgia Tech, 2023) | 250 signs, ~200k phone videos | 47 Deaf adults | CC BY 4.0 | ✅ | ✅ | signdata.cc.gatech.edu |
| **Google ISLR "asl-signs"** (Kaggle, 2023) | same 250 signs, ~94k sequences, landmarks only | 21 Deaf | CC BY 4.0 | ✅ | ✅ | Kaggle competition |
| **ASL Citizen** (Microsoft Research, 2023) | 2,731 signs, 83,399 webcam videos | 52 Deaf/HoH | "solely for non-commercial, non-revenue generating, research purposes"; "may not distribute the data or your modifications" | ❌ (non-commercial permission granted to ASLytics, 2026-10-03) | ✅ by permission, with credit | download.microsoft.com, 42.8 GB zip |
| **ASL Signbank** (Hochgesang et al.; aslsignbank.com) | ~4,400 entries, one citation video each | — | CC BY-NC-SA 4.0; "You are welcome to re-use and share the images and videos" | ❌ | ✅ with credit; ask before bulk download | per entry |
| **Sem-Lex** (BU and others, 2023) | 3,149 signs, 91,148 videos | 41 Deaf | behind a Google Form, unverified | assume ❌ | read the form first | github.com/leekezar/SemLex |
| **ASLLRP Sign Bank / ASLLVD** (Boston University) | ~6,000 entries; ASLLVD >3,300 signs | native signers | "research and education … cannot be redistributed without permission. Commercial use … not allowed" | ❌ | ask ASLLRP | dai.cs.rutgers.edu |
| **NVIDIA ASL 1000** (NVIDIA + ASDC, 2025) | ~1,000 signs, human-checked landmarks and video | fluent | NVIDIA Data License: use "to advance access to technology for the Deaf community"; no redistribution; revocable | not barred, but purpose-limited; get it confirmed | probably ✅ if only avatar output is shown | request form, then AWS |
| **ASL-LEX 2.0** | 2,723 signs of metadata | — | database CC BY-NC 4.0; videos "solely for personal searches" | ❌ | metadata only | asl-lex.org |
| **3D-LEX** (UvA, 2024) | 1,000 signs, motion capture | — | unverified | ? | ? | contact authors |
| **ASL-100-RGBD** (RIT/CUNY) | 100 signs | 22 fluent | authorised academics only | ❌ | ❌ | Databrary |
| **Purdue RVL-SLLL** (2002) | 104 signs, alphabet, numbers | 14 Deaf | signed agreement, unverified | presumably ❌ | ? | by post |
| **WLASL** (2020) | 2,000 glosses, scraped | 119, no consent | C-UDA + "No commercial usage" | ❌ | ❌ do not use | YouTube links, many dead |
| **MS-ASL** (Microsoft, 2019) | 1,000 signs, scraped from YouTube | 222, no consent | C-UDA | ❌ | ❌ do not use | URL list |

### Fingerspelling

| Dataset | Size | Licence | Commercial | Notes |
|---|---|---|---|---|
| **Google ASL Fingerspelling** (Kaggle, 2023) | >3M characters, >100 Deaf signers, landmarks | CC BY | ✅ | `prototype/fingerspelling.py` uses it; needs the competition rules accepted |
| **FSboard** (Google, 2024) | 3.2M characters, 147 paid Deaf signers | CC BY 4.0 | ✅ | video or landmarks: unverified |
| ChicagoFSWild / FSWild+ | 7k / 55k sequences from YouTube | no licence found | ❌ | scraped, not needed |

### Whole sentences: natural signing, word order, facial grammar

| Dataset | Size | Signers | Licence | Commercial | Notes |
|---|---|---|---|---|---|
| **2M-Flores-ASL** (Meta, 2024) | all FLORES-200 dev sentences, 1080p, **gloss per sentence** | ASL translators, native signers | CC BY-SA 4.0 | ✅ share-alike | best for the "fluent signer" column; glosses let single signs be cut out |
| **FLEURS-ASL** (Google, 2024) | FLORES sentences | 5 Certified Deaf Interpreters | CC BY-SA 4.0 | ✅ share-alike | |
| **How2Sign** (2021) | 80 h, 35k sentences, keypoints | 11 (6 deaf/HoH) | CC BY-NC 4.0, "research purposes only" | ❌ | |
| **DailyMoth-70h** (Meta, 2024) | 70 h of news | 1 native Deaf signer, licensed from the creator | CC BY-NC 4.0 | ❌ | |
| **ASL STEM Wiki** (Microsoft, 2024) | 300 h, STEM articles | 37 interpreters incl. Deaf | same licence as ASL Citizen | ❌ | |
| YouTube-ASL, YouTube-SL-25 (Google) | 984 h / 3,200 h | >2,500, no consent | CC BY 4.0 for the **ID list only** | ❌ for videos | videos are the uploaders'; YouTube's terms forbid downloading |
| OpenASL (TTIC) | 288 h from YouTube | | CC BY-NC-ND 4.0 | ❌ | no derivatives at all |

### Dictionary websites

| Site | What its terms say | May we scrape? |
|---|---|---|
| Handspeak | "Any duplication or reproduction, distribution … without the required prior written consent … is prohibited" | ❌ |
| Lifeprint / ASLU | "you do not have permission to use ASLU materials to make apps of any kind" | ❌ |
| Signing Savvy | may not "reproduce, publish, transmit, distribute, display, modify, create derivative works" | ✅ for ASLytics, non-commercial: permission granted 2026-10-03 |
| Spread the Sign | "It is not allowed to download or use our videos or data without permission" | ❌ |
| ASL-LEX videos | "solely for personal searches" | ❌ |
| ASL Signbank | CC BY-NC-SA 4.0, reuse invited | ✅ non-commercial, ask before bulk download |

## What this means for us

- **Commercial, today:** PopSign (250 signs), Google's fingerspelling, and
  signs cut from 2M-Flores-ASL / FLEURS-ASL sentences (share-alike).
  NVIDIA ASL 1000 if NVIDIA confirms. ASL Citizen and Signing Savvy only if
  they extend their permission to commercial use.
- **Community demo, non-commercial:** ASL Citizen and Signing Savvy, both by
  permission for non-commercial use (DATA_LICENSES.md §0). ASL Signbank could
  be added too (ask first).
- **Never:** dictionary sites that have not given permission, WLASL, MS-ASL,
  YouTube-sourced sets.
- **Our own dataset is the way out.** Paid, consented Deaf signers, recorded
  for the words people actually caption, owned under a licence we choose.
  [COVERAGE.md](COVERAGE.md) shows 1,000 well-chosen signs would cover more
  everyday English than ASL Citizen's 2,731.
