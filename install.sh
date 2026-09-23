#!/bin/bash
# Create the three environments ASLytics needs.
#
#     bash install.sh
#
# Three, because the gloss step and the pose step need incompatible versions of
# torch and numpy, and the Flask layer needs neither.
#
# `conda activate` does not work in a non-interactive script without shell
# hooks, so this uses `conda run` throughout. The previous version called
# `conda activate` and pointed pip at two files that do not exist
# (text-to-gloss/requirements.txt when the file was requirement.txt, and
# pose-master/pose-master.txt), so every install silently did nothing.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

: "${ASLYTICS_GLOSS_ENV:=text-to-gloss}"
: "${ASLYTICS_POSE_ENV:=gloss-to-skeleton}"

if ! command -v conda >/dev/null 2>&1; then
  echo "error: conda is not on PATH. Install Miniconda first." >&2
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "warning: ffmpeg is not on PATH. Video encoding will fail." >&2
  echo "         apt install ffmpeg   /   brew install ffmpeg" >&2
fi

echo "==> $ASLYTICS_GLOSS_ENV (English -> gloss)"
conda create -n "$ASLYTICS_GLOSS_ENV" python=3.10 -y
conda run -n "$ASLYTICS_GLOSS_ENV" pip install -r "$REPO_ROOT/text-to-gloss/requirements.txt"

echo "==> downloading StanfordNLP English models (~250MB)"
conda run -n "$ASLYTICS_GLOSS_ENV" python -c \
  "import stanfordnlp; stanfordnlp.download('en', force=True)"

echo "==> $ASLYTICS_POSE_ENV (gloss -> pose -> video)"
conda create -n "$ASLYTICS_POSE_ENV" python=3.9 -y
conda run -n "$ASLYTICS_POSE_ENV" pip install -r "$REPO_ROOT/pose-master/pose-master/requirements.txt"

echo "==> Flask layer, in the current environment"
pip install -r "$REPO_ROOT/requirements.txt"

echo
echo "Done. Remaining step: supply the sign lexicon."
echo "  The per-gloss .pose files are not in this repository. Put them in"
echo "  $REPO_ROOT/lexicon, or set ASLYTICS_LEXICON_DIR to point at them."
echo "  See README.md."
