"""
Build a blind A/B rating sheet for human evaluation.

The automatic metrics are proxies. Whether a rendered sign is *readable* is a
judgement only a fluent signer can make, and it is the judgement the product
actually rests on. This generates a self-contained HTML page that shows each
sign from both models side by side, in randomised order with the model
identities hidden, and collects ratings as CSV.

Blinding is the point. A rater who knows which clip is "the new model" will
score it differently, and we would rather learn the truth now than after
shipping.

    python make_human_eval_sheet.py --a runs/baseline/clips --b runs/clean-v1/clips \
        --out review/sheet.html --seed 7
"""

from __future__ import annotations

import argparse
import html
import json
import os
import random
from typing import List, Tuple

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>ASL render review</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 0 auto; max-width: 900px; padding: 16px; }}
  .pair {{ border-top: 1px solid #ddd; padding: 24px 0; }}
  .videos {{ display: flex; gap: 16px; flex-wrap: wrap; }}
  .side {{ flex: 1 1 320px; }}
  video {{ width: 100%; background: #111; border-radius: 6px; }}
  .q {{ margin: 12px 0 4px; font-weight: 600; }}
  label {{ margin-right: 12px; white-space: nowrap; }}
  .gloss {{ font-size: 1.2em; font-weight: 700; }}
  #save {{ position: sticky; bottom: 0; width: 100%; padding: 14px; font-size: 1em;
           background: #1a7f37; color: #fff; border: 0; border-radius: 6px; cursor: pointer; }}
</style>
</head>
<body>
<h1>ASL render review</h1>
<p>For each sign, watch both clips and answer. The two clips come from two
different models; which is which is hidden, and the left/right order changes
every time. If neither is readable, say so — that is a useful answer.</p>
<form id="sheet">
{pairs}
</form>
<button id="save" type="button">Download ratings CSV</button>
<script>
const ORDER = {order_json};
document.getElementById('save').addEventListener('click', () => {{
  const rows = [['gloss','left_model','right_model','readable_left','readable_right','preferred','handshape_notes']];
  for (const item of ORDER) {{
    const get = (n) => (document.querySelector(`input[name="${{n}}_${{item.id}}"]:checked`) || {{}}).value || '';
    const notes = (document.querySelector(`textarea[name="notes_${{item.id}}"]`) || {{}}).value || '';
    rows.push([item.gloss, item.left, item.right, get('readable_left'), get('readable_right'),
               get('preferred'), notes.replace(/[\\n,]/g, ' ')]);
  }}
  const csv = rows.map(r => r.map(c => `"${{String(c).replace(/"/g,'""')}}"`).join(',')).join('\\n');
  const url = URL.createObjectURL(new Blob([csv], {{type: 'text/csv'}}));
  const a = document.createElement('a');
  a.href = url; a.download = 'ratings.csv'; a.click();
}});
</script>
</body>
</html>
"""

PAIR = """<div class="pair">
  <div class="gloss">{index}. {gloss}</div>
  <div class="videos">
    <div class="side"><video src="{left_src}" controls loop muted></video>
      <div class="q">Is this readable as "{gloss}"?</div>
      <label><input type="radio" name="readable_left_{id}" value="yes"> Yes</label>
      <label><input type="radio" name="readable_left_{id}" value="unsure"> Unsure</label>
      <label><input type="radio" name="readable_left_{id}" value="no"> No</label>
    </div>
    <div class="side"><video src="{right_src}" controls loop muted></video>
      <div class="q">Is this readable as "{gloss}"?</div>
      <label><input type="radio" name="readable_right_{id}" value="yes"> Yes</label>
      <label><input type="radio" name="readable_right_{id}" value="unsure"> Unsure</label>
      <label><input type="radio" name="readable_right_{id}" value="no"> No</label>
    </div>
  </div>
  <div class="q">Which is clearer?</div>
  <label><input type="radio" name="preferred_{id}" value="left"> Left</label>
  <label><input type="radio" name="preferred_{id}" value="right"> Right</label>
  <label><input type="radio" name="preferred_{id}" value="same"> No difference</label>
  <label><input type="radio" name="preferred_{id}" value="neither"> Neither is readable</label>
  <div class="q">What goes wrong with the handshape, if anything?</div>
  <textarea name="notes_{id}" rows="2" style="width:100%"></textarea>
</div>
"""


def shared_clips(dir_a: str, dir_b: str) -> List[str]:
    def clips(directory: str) -> set:
        return {name for name in os.listdir(directory) if name.lower().endswith((".mp4", ".webm"))}
    return sorted(clips(dir_a) & clips(dir_b))


def build(dir_a: str, dir_b: str, out_path: str, seed: int = 0) -> Tuple[str, int]:
    rng = random.Random(seed)
    names = shared_clips(dir_a, dir_b)
    if not names:
        raise SystemExit(f"no clips present in both {dir_a} and {dir_b}")

    out_dir = os.path.dirname(os.path.abspath(out_path))
    order, blocks = [], []
    presentation = names[:]
    rng.shuffle(presentation)

    for index, name in enumerate(presentation, start=1):
        gloss = os.path.splitext(name)[0].replace("_", " ")
        # Randomise which model lands on which side, per clip.
        flip = rng.random() < 0.5
        left_dir, right_dir = (dir_b, dir_a) if flip else (dir_a, dir_b)
        left_model, right_model = ("B", "A") if flip else ("A", "B")

        item_id = f"c{index:03d}"
        order.append({"id": item_id, "gloss": gloss, "left": left_model, "right": right_model})
        blocks.append(PAIR.format(
            index=index,
            id=item_id,
            gloss=html.escape(gloss),
            left_src=html.escape(os.path.relpath(os.path.join(left_dir, name), out_dir)),
            right_src=html.escape(os.path.relpath(os.path.join(right_dir, name), out_dir)),
        ))

    page = TEMPLATE.format(pairs="\n".join(blocks), order_json=json.dumps(order))
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(page)

    # The key maps A/B back to the real models. Keep it away from the raters.
    key_path = os.path.splitext(out_path)[0] + ".key.json"
    with open(key_path, "w", encoding="utf-8") as handle:
        json.dump({"A": dir_a, "B": dir_b, "seed": seed, "order": order}, handle, indent=2)

    return key_path, len(presentation)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a blind A/B review sheet.")
    parser.add_argument("--a", required=True, help="Clips from model A (e.g. the baseline)")
    parser.add_argument("--b", required=True, help="Clips from model B (e.g. the candidate)")
    parser.add_argument("--out", default="review/sheet.html")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    key_path, count = build(args.a, args.b, args.out, args.seed)
    print(f"wrote {args.out} with {count} pairs")
    print(f"unblinding key: {key_path} — do not send this to raters")


if __name__ == "__main__":
    main()
