"""Render a gloss sequence to video. Runs in the pose environment.

Reads glosses either as arguments or, with --start-output -, from the stdout
of text-to-gloss/start.py on stdin. The shell pipeline used to extract them
with grep and sed and paste the result into the source of an inline Python
program. Caption text reaches the glosses, so that was a code-injection path
as well as fragile; this parses the printed list with ast.literal_eval.

    python utils/render_glosses.py --out-video out.mp4 hello world
    python text-to-gloss/start.py "hello world" | \\
        python utils/render_glosses.py --start-output - --out-video out.mp4

Exit codes: 0 rendered, 2 no glosses found, 3 glosses missing from the
lexicon (listed on stderr).
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

MARKER = "Gloss sequence:"


def glosses_from_start_output(text: str) -> List[str]:
    """The list start.py prints after 'Gloss sequence:', or [] if none."""
    for line in reversed(text.splitlines()):
        if MARKER in line:
            literal = line.split(MARKER, 1)[1].strip()
            try:
                value = ast.literal_eval(literal)
            except (ValueError, SyntaxError):
                return []
            if isinstance(value, (list, tuple)):
                return [str(item).strip().lower() for item in value if str(item).strip()]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Render glosses to an ASL skeleton video.")
    parser.add_argument("glosses", nargs="*", help="Glosses, in order")
    parser.add_argument("--start-output", help="Read start.py's stdout from this file, or - for stdin")
    parser.add_argument("--out-video", required=True)
    args = parser.parse_args()

    glosses = list(args.glosses)
    if args.start_output:
        text = sys.stdin.read() if args.start_output == "-" else Path(args.start_output).read_text()
        glosses += glosses_from_start_output(text)
    if not glosses:
        print("no glosses to render", file=sys.stderr)
        return 2

    from asl_renderer import MissingGlosses, RenderService

    service = RenderService()
    try:
        path, cached = service.render(glosses, args.out_video)
    except MissingGlosses as error:
        print(json.dumps({"missing": error.missing, "lexicon": error.directory}), file=sys.stderr)
        return 3

    print(json.dumps({"glosses": glosses, "video": path, "cached": cached}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
