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

## What to expect

- **The vocabulary is small and childlike.** PopSign was recorded for a
  children's game: animals, family, food, colours, feelings. Everyday words
  like *I, you, good, eat, want, need, know, what, how* are missing, so most
  real captions come out partly signed.
- **No fingerspelling yet.** PopSign has no alphabet, so names and numbers are
  skipped. Google's ASL Fingerspelling data (CC BY) is the planned fix.
- **Text-to-gloss drops subject pronouns and articles**, so "I see a bird"
  signs SEE BIRD. That is the existing gloss step, not the lexicon.
- **One signer per sign, chosen automatically.** The selection rule looks only
  at hand-landmark quality, never at the old lexicon.

## Licence obligations

CC BY 4.0 requires crediting PopSign wherever its signs are shown:

- `build` writes `ATTRIBUTION.txt` and `lexicon.json` into the lexicon.
- The web pages read `lexicon.json` and show the credit line.

The lexicon folder carries its own `.gitignore`, so derived signs are never
committed.
