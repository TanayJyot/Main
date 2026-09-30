#!/bin/bash
# Set up ASLytics.
#
#     bash install.sh            # a .venv in the repo (default; works on Windows)
#     bash install.sh --conda    # separate conda environments per half
#
# The default is one virtualenv. The gloss half (stanza) and the pose
# half (pose-format) install side by side on current torch, so the separate
# conda environments this script used to require are optional, not needed.
# On Windows run this from Git Bash, or run the three commands under
# "Without bash" in README.md from PowerShell.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="venv"
[ "${1:-}" = "--conda" ] && MODE="conda"

: "${ASLYTICS_GLOSS_ENV:=text-to-gloss}"
: "${ASLYTICS_POSE_ENV:=gloss-to-skeleton}"

download_models() {
  echo "==> downloading Stanza English models"
  "$@" -c "import stanza; stanza.download('en', package='ewt', processors='tokenize,mwt,pos,lemma,depparse')"
}

if [ "$MODE" = "conda" ]; then
  command -v conda >/dev/null 2>&1 || { echo "error: conda is not on PATH" >&2; exit 1; }

  echo "==> conda env $ASLYTICS_GLOSS_ENV (English -> gloss)"
  conda create -n "$ASLYTICS_GLOSS_ENV" python=3.10 -y
  conda run -n "$ASLYTICS_GLOSS_ENV" pip install -r "$REPO_ROOT/text-to-gloss/requirements.txt"
  download_models conda run -n "$ASLYTICS_GLOSS_ENV" python

  echo "==> conda env $ASLYTICS_POSE_ENV (gloss -> pose -> video)"
  conda create -n "$ASLYTICS_POSE_ENV" python=3.10 -y
  conda run -n "$ASLYTICS_POSE_ENV" pip install -r "$REPO_ROOT/requirements-render.txt"

  echo "==> Flask layer, in the current environment"
  python -m pip install -r "$REPO_ROOT/requirements.txt"
else
  base=""
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import sys" >/dev/null 2>&1; then
      base="$candidate"; break
    fi
  done
  [ -n "$base" ] || { echo "error: no working Python on PATH" >&2; exit 1; }

  echo "==> creating $REPO_ROOT/.venv"
  "$base" -m venv "$REPO_ROOT/.venv"
  venv_python="$REPO_ROOT/.venv/bin/python"
  [ -x "$venv_python" ] || venv_python="$REPO_ROOT/.venv/Scripts/python.exe"

  "$venv_python" -m pip install --upgrade pip
  "$venv_python" -m pip install -r "$REPO_ROOT/requirements.txt" \
      -r "$REPO_ROOT/text-to-gloss/requirements.txt" -r "$REPO_ROOT/requirements-render.txt"
  download_models "$venv_python"
fi

echo
echo "Remaining step: supply the sign lexicon (not in this repository)."
echo "  Put the .pose files in $REPO_ROOT/lexicon, or set ASLYTICS_LEXICON_DIR."
echo "Then check the setup:  python utils/aslytics_env.py"
