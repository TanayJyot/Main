#!/bin/bash
# Render one sentence into an ASL skeleton video.
#
#     bash utils/generate_asl_video.sh "the cat is small" static/videos/caption_0.mp4
#
# The pipeline now lives in utils/generate_asl_video.py, which runs with or
# without conda and on Windows. This wrapper stays so existing callers
# (main.sh, old_main.sh) keep working. It needs only a Python to start from:
# $ASLYTICS_PYTHON, the repo's .venv, or python3 / python on PATH.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python="${ASLYTICS_PYTHON:-}"
if [ -z "$python" ]; then
  for candidate in "$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/.venv/Scripts/python.exe" python3 python; do
    # `python3` on Windows can be a Microsoft Store stub that prints an advert
    # and exits; actually running it is the only reliable test.
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import sys" >/dev/null 2>&1; then
      python="$candidate"
      break
    fi
  done
fi
if [ -z "$python" ]; then
  echo "error: no working Python found. Set ASLYTICS_PYTHON." >&2
  exit 1
fi

exec "$python" "$REPO_ROOT/utils/generate_asl_video.py" "$@"
