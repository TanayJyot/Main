# Prototype: ASLytics on licensed signs only

This runs the whole pipeline (English → gloss → signs → skeleton video) using
**PopSign ASL v1.0** as its sign lexicon. PopSign is the one sign dataset we
hold that allows commercial use (CC BY 4.0). It has 250 signs, which are 261
words once labels like `hesheit` are split into *he, she, it*. See
[WORDS.md](WORDS.md) for every word, and for what ASL Citizen and the old
lexicon would add.

Words that PopSign lacks are **skipped**, not fatal: a sentence is signed as
far as the lexicon allows, and the skipped words are reported.

## Run it

Each step's commands are for PowerShell on the laptop. In bash, replace
`$env:NAME = "value"; ` with `NAME=value `.

**1. Convert PopSign to one `.pose` per sign.** This uses `analysis/convert/`
on `claude/lexicon-convert`. The result is a folder of `<label>.pose` (e.g.
`callonphone.pose`), one clip per label, mirrored to right-handed. It needs
MediaPipe, so do it on the GPU laptop.

**2. Build the lexicon.** This renames each clip to the words it signs and
writes the CC BY credit next to them:

```
python prototype/popsign_lexicon.py build --labels <that folder> --out lexicon/popsign
```

**3. Try it from the command line:**

```
python prototype/run_demo.py
python prototype/run_demo.py "the dog is hungry" "where is my book?"
```

Videos and `demo_report.json` go to `.work/demo/`.

**4. Or in the browser:**

```
$env:ASLYTICS_LEXICON_DIR = "lexicon/popsign"; $env:ASLYTICS_SKIP_MISSING = "1"; python app.py
```

Then open <http://127.0.0.1:5000/sentence>. Type a sentence to get a video,
with the signed and skipped words listed underneath. The YouTube page at `/`
also works, skipping the same way.

To see which words the loaded lexicon can sign:

```
python utils/generate_asl_video.py --words
```

## Fingerspelling (optional)

With letter clips in the lexicon, a word with no sign is spelled out letter by
letter instead of skipped. Names already come out of text-to-gloss as letters,
and numbers are spelled digit by digit. The letters come from Google's ASL
Fingerspelling data on Kaggle.

**Before downloading, you must:**

1. Join the Kaggle competition "Google - American Sign Language
   Fingerspelling Recognition" and accept its rules.
2. **Read the rules on using competition data outside the competition.**
3. Put a Kaggle API token in `%USERPROFILE%\.kaggle\kaggle.json`.

Accepting the rules is a legal agreement, so a person must do these steps.

Then download the phrase list and a few landmark files (each about 1 GB,
about 1,000 phrases; three or four are plenty):

```
pip install kaggle pandas pyarrow
kaggle competitions download -c asl-fingerspelling -f train.csv -p data/fingerspelling
kaggle competitions download -c asl-fingerspelling -f train_landmarks/5414471.parquet -p data/fingerspelling/train_landmarks
```

Unzip anything that arrives zipped. Pick parquet names from the `path` column
of `train.csv`.

Next, cut the phrases into letters. `--header-from` is any sign file from the
lexicon, so the letters share its layout:

```
python prototype/fingerspelling.py extract --data data/fingerspelling --header-from <popsign_labels>/dog.pose --out lexicon/fingerspelling
```

Finally, rebuild with the letters:

```
python prototype/popsign_lexicon.py build --labels <popsign_labels> --out lexicon/popsign --letters lexicon/fingerspelling
```

`lexicon/fingerspelling/fingerspelling.json` reports what was found:
characters, examples per character, and any character with no clean example.
The letters J and Z move rather than hold, so they may be missing.

## What to expect

- **The vocabulary is small and childlike.** PopSign was recorded for a
  children's game: animals, family, food, colours, feelings. Everyday words
  like *I, you, good, eat, want, need, know, what, how* are missing, so most
  real captions come out partly signed.
- **Fingerspelling needs letters.** PopSign has no alphabet. Without the
  letter clips (above), names, numbers and unknown words are skipped.
- **Text-to-gloss drops subject pronouns and articles**, so "I see a bird"
  signs SEE BIRD. That is the existing gloss step, not the lexicon.
- **One signer per sign, chosen automatically.** The selection rule looks only
  at hand-landmark quality, never at the old lexicon.
- **Signs are trimmed to the moving part.** PopSign signers hold the hand up
  for the whole recording, so without this each sign lasted 4–5 s. `build`
  keeps only the stretch where the hands move (`trim.py`).
- **Badly tracked signs are left out.** A sign whose hands were detected in
  under 30% of frames is skipped instead of shown wrongly
  (`--min-presence`). It is listed in `lexicon.json`.
- **Two-handed signs look one-handed.** PopSign was filmed on a phone held in
  one hand. That is a limit of the data.

## Licence obligations

CC BY 4.0 requires crediting PopSign wherever its signs are shown:

- `build` writes `ATTRIBUTION.txt` and `lexicon.json` into the lexicon.
- The web pages read `lexicon.json` and show the credit line.

The lexicon folder carries its own `.gitignore`, so derived signs are never
committed.
