"""Sign the same sentences with each lexicon, side by side, for a live showing.

    python showcase/run_showcase.py                          # built-in sentences
    python showcase/run_showcase.py "where is the library?"  # your own

For each sentence: English -> gloss once, then one render per tier
(showcase/tiers.py), then one comparison video with the tiers next to each
other. Everything goes to .work/showcase/ (never committed):

    compare_<n>.mp4     the side-by-side video
    index.html          a gallery of them, with what each tier signed, spelled
                        and missed, and the credits; open it in a browser
    report.json         the same as data

The research-preview tier uses ASL Citizen, whose licence allows research use
only and forbids distributing the data or modifications. Show the gallery from
this machine; do not upload or send the videos.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT / "utils"))

import tiers as tiering  # noqa: E402
from stitch import Panel, side_by_side  # noqa: E402

OUT = REPO_ROOT / ".work" / "showcase"


def run(sentences, tiers, out: Path = OUT, natural=None) -> list:
    """natural: entries from natural.load(); each adds its sentence, with the
    fluent signer's render as the first panel."""
    import aslytics_env as env
    from generate_asl_video import GenerationError, generate_with_report, text_to_gloss

    out.mkdir(parents=True, exist_ok=True)
    (out / ".gitignore").write_text("*\n", encoding="utf-8")
    report = []
    jobs = [(entry["sentence"], entry) for entry in natural or []] + [(s, None) for s in sentences]
    for index, (sentence, fluent) in enumerate(jobs):
        started = time.time()
        entry = {"sentence": sentence, "tiers": []}
        if fluent:
            entry["natural"] = {"source": fluent.get("source", ""), "gloss": fluent.get("gloss", "")}
        try:
            glosses = text_to_gloss(sentence)
        except GenerationError as error:
            entry["error"] = str(error).splitlines()[0]
            report.append(entry)
            print(f"\n{sentence}\n  error: {entry['error']}")
            continue
        entry["glosses"] = glosses
        print(f"\n{sentence}\n  glosses: {' '.join(glosses) or '-'}")
        panels = []
        if fluent:
            panels.append(Panel(f"Fluent signer: {fluent.get('source', 'natural')}", Path(fluent["video"])))
        for tier in tiers:
            result = {"tier": tier.name, "signed": [], "spelled": [], "skipped": [], "video": None}
            if glosses:
                try:
                    done = generate_with_report(sentence, f"{index}_{tier.slug}.mp4", glosses=glosses,
                                                skip_missing=True, publish_dir=out / "tiers",
                                                lexicon_dir=tier.path)
                    result.update(signed=done["glosses"], spelled=done["spelled"],
                                  skipped=done["skipped"], video=str(done["video"]))
                except GenerationError as error:
                    # Nothing signable: every gloss is missing from this tier.
                    result["skipped"] = list(dict.fromkeys(glosses))
                    result["error"] = str(error).splitlines()[0]
            entry["tiers"].append(result)
            print(f"  {tier.name}: signed {' '.join(result['signed']) or '-'}"
                  + (f" | spelled {' '.join(result['spelled'])}" if result["spelled"] else "")
                  + (f" | missing {' '.join(result['skipped'])}" if result["skipped"] else ""))
            panels.append(Panel(tier.name, Path(result["video"]) if result["video"] else None,
                                result["signed"], result["spelled"], result["skipped"], tier.non_commercial))
        video = side_by_side(panels, sentence, out / f"compare_{index}.mp4", env.ffmpeg())
        entry["compare"] = video.name
        entry["seconds"] = round(time.time() - started, 1)
        report.append(entry)
        print(f"  -> {video}  ({entry['seconds']} s)")

    (out / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    (out / "index.html").write_text(gallery(report, tiers), encoding="utf-8")
    return report


def totals(report, tiers) -> dict:
    """tier name -> {"signed", "spelled", "missing", "words"} over all sentences."""
    out = {tier.name: {"signed": 0, "spelled": 0, "missing": 0} for tier in tiers}
    for entry in report:
        for result in entry.get("tiers", []):
            counts = out[result["tier"]]
            counts["signed"] += len(result["signed"])
            counts["spelled"] += len(result["spelled"])
            counts["missing"] += len(result["skipped"])
    for counts in out.values():
        counts["words"] = counts["signed"] + counts["spelled"] + counts["missing"]
    return out


def gallery(report, tiers) -> str:
    esc = html.escape
    summary = totals(report, tiers)
    rows = "".join(
        f"<tr><td>{esc(name)}</td><td>{len(t.words):,}</td>"
        f"<td>{c['signed']}</td><td>{c['spelled']}</td><td>{c['missing']}</td>"
        f"<td><b>{(c['signed'] / c['words'] if c['words'] else 0):.0%}</b></td></tr>"
        for t in tiers for name, c in [(t.name, summary[t.name])])
    cards = []
    for entry in report:
        if "compare" not in entry:
            cards.append(f"<section><h2>{esc(entry['sentence'])}</h2>"
                         f"<p class=miss>{esc(entry.get('error', ''))}</p></section>")
            continue
        lines = "".join(
            f"<li><b>{esc(r['tier'])}</b>: signed <span class=ok>{esc(' '.join(r['signed']) or '-')}</span>"
            + (f"; spelled <span class=sp>{esc(' '.join(r['spelled']))}</span>" if r["spelled"] else "")
            + (f"; missing <span class=miss>{esc(' '.join(r['skipped']))}</span>" if r["skipped"] else "")
            + "</li>" for r in entry["tiers"])
        cards.append(f"<section><h2>{esc(entry['sentence'])}</h2>"
                     f"<p class=gloss>Our gloss: {esc(' '.join(entry.get('glosses', [])))}</p>"
                     + (f"<p class=gloss>Fluent signer ({esc(entry['natural']['source'])})"
                        + (f", their gloss: {esc(entry['natural']['gloss'])}" if entry['natural']['gloss'] else "")
                        + "</p>" if entry.get("natural") else "") +
                     f"<video src='{esc(entry['compare'])}' controls loop muted playsinline></video>"
                     f"<ul>{lines}</ul></section>")
    credits = "".join(f"<li><b>{esc(t.name)}</b>: {esc(t.source)} ({esc(t.license)})</li>" for t in tiers)
    restricted = any(t.non_commercial for t in tiers)
    warning = ("<p class=warn>Non-commercial use only. Signs from Signing Savvy and ASL Citizen are used "
               "with their permission for non-commercial purposes; credit them wherever these videos are "
               "shown.</p>") if restricted else ""
    return f"""<!doctype html>
<html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>ASLytics Showcase</title>
<style>
 :root {{ --bg:#fff; --fg:#1a1a1a; --muted:#666; --ok:#2e7d32; --sp:#1565c0; --miss:#b71c1c; --warn:#8a5a00; --card:#f5f5f5; }}
 @media (prefers-color-scheme: dark) {{ :root {{ --bg:#141414; --fg:#eee; --muted:#aaa; --ok:#81c784;
   --sp:#90caf9; --miss:#ef9a9a; --warn:#ffcc80; --card:#1f1f1f; }} }}
 body {{ background:var(--bg); color:var(--fg); font:16px/1.5 system-ui,sans-serif; max-width:1100px; margin:0 auto; padding:16px; }}
 section {{ background:var(--card); border-radius:10px; padding:12px 16px; margin:16px 0; }}
 video {{ width:100%; border-radius:6px; background:#000; }}
 table {{ border-collapse:collapse; }} td,th {{ padding:4px 10px; border-bottom:1px solid #8884; text-align:left; }}
 .ok {{ color:var(--ok); }} .sp {{ color:var(--sp); }} .miss {{ color:var(--miss); }} .gloss {{ color:var(--muted); }}
 .warn {{ color:var(--warn); font-weight:600; }}
</style></head><body>
<h1>What a bigger sign dataset makes possible</h1>
{warning}
<p>Each sentence is signed by every lexicon side by side. <span class=ok>Signed</span> words have a sign;
<span class=sp>spelled</span> words are fingerspelled; <span class=miss>missing</span> words are left out.</p>
<table><tr><th>Lexicon</th><th>Words it knows</th><th>Signed</th><th>Spelled</th><th>Missing</th><th>Share signed</th></tr>
{rows}</table>
{''.join(cards)}
<h2>Credits</h2><ul>{credits}</ul>
<p class=gloss>Skeleton videos made with MediaPipe Holistic and pose-format. Not reviewed by a Deaf signer yet.</p>
</body></html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("sentences", nargs="*", help="Sentences; default: the built-in set")
    parser.add_argument("--tiers", default=None,
                        help='"Name=folder;Name=folder" (default: ASLYTICS_SHOWCASE_TIERS or tiers.py)')
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--natural", type=Path, default=None,
                        help="Folder made by showcase/natural.py: fluent-signer sentences to compare against")
    parser.add_argument("--only-natural", action="store_true", help="Skip the built-in sentences")
    args = parser.parse_args()

    found = tiering.tiers(args.tiers)
    if not found:
        print("no lexicons found. Build lexicon/popsign (prototype/README.md) and lexicon/community "
              "(showcase/README.md) first.", file=sys.stderr)
        return 1
    for tier in found:
        print(f"{tier.name}: {len(tier.words):,} words, {len(tier.letters)} letters  [{tier.path}]")
    import natural as fluent_signing

    natural = fluent_signing.load(args.natural) if args.natural else []
    if args.natural and not natural:
        print(f"no natural.json in {args.natural}; run showcase/natural.py first", file=sys.stderr)
    sentences = args.sentences or ([] if args.only_natural else tiering.SENTENCES)
    report = run(sentences, found, args.out, natural)
    print()
    for name, counts in totals(report, found).items():
        share = counts["signed"] / counts["words"] if counts["words"] else 0
        print(f"{name}: {counts['signed']}/{counts['words']} words signed ({share:.0%}), "
              f"{counts['spelled']} spelled, {counts['missing']} missing")
    print(f"\nopen {args.out / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
