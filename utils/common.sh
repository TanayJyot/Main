#!/bin/bash
# Shared setup for the ASL generation scripts.
#
# Source this, do not execute it:
#     source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
#
# Every path used to be hardcoded to one developer's home directory, so the
# scripts only ran on that machine. Everything is now resolved relative to the
# repository, with environment variables to override.

# Resolve the repository root from this file's location, following symlinks.
_common_sh_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$_common_sh_dir/.." && pwd)"
export REPO_ROOT

# Conda environments, as created by install.sh.
: "${ASLYTICS_GLOSS_ENV:=text-to-gloss}"     # runs text-to-gloss/start.py
: "${ASLYTICS_POSE_ENV:=gloss-to-skeleton}"  # runs the pose-format steps
export ASLYTICS_GLOSS_ENV ASLYTICS_POSE_ENV

# The per-gloss .pose lexicon. Not in the repository — see DATA_LICENSES.md
# section 2b for the provenance question, and README.md for how to supply it.
#
# The legacy location is a directory literally named `.gitignore`, which
# collides with the gitignore *file* a repository normally has at its root. It
# is still honoured so existing checkouts keep working, but move it to
# `lexicon/` when convenient.
if [ -z "${ASLYTICS_LEXICON_DIR:-}" ]; then
  if [ -d "$REPO_ROOT/.gitignore/generated_pose" ]; then
    ASLYTICS_LEXICON_DIR="$REPO_ROOT/.gitignore/generated_pose"
  else
    ASLYTICS_LEXICON_DIR="$REPO_ROOT/lexicon"
  fi
fi
export ASLYTICS_LEXICON_DIR

# Scratch space for intermediate .pose files and unconverted video.
: "${ASLYTICS_WORK_DIR:=$REPO_ROOT/.work}"
export ASLYTICS_WORK_DIR
mkdir -p "$ASLYTICS_WORK_DIR"

# Where finished clips go.
: "${ASLYTICS_VIDEO_DIR:=$REPO_ROOT/videos}"
: "${ASLYTICS_WEB_VIDEO_DIR:=$REPO_ROOT/static/videos}"
export ASLYTICS_VIDEO_DIR ASLYTICS_WEB_VIDEO_DIR

# Fail early and legibly rather than part-way through a render.
aslytics_require() {
  local missing=0

  if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "error: ffmpeg is not on PATH. Install it (apt install ffmpeg / brew install ffmpeg)." >&2
    missing=1
  fi

  if ! command -v conda >/dev/null 2>&1; then
    echo "error: conda is not on PATH. See install.sh." >&2
    missing=1
  else
    local env
    for env in "$ASLYTICS_GLOSS_ENV" "$ASLYTICS_POSE_ENV"; do
      if ! conda env list | awk '{print $1}' | grep -qx "$env"; then
        echo "error: conda environment '$env' does not exist. Run: bash install.sh" >&2
        missing=1
      fi
    done
  fi

  if [ ! -d "$ASLYTICS_LEXICON_DIR" ]; then
    echo "error: no sign lexicon at $ASLYTICS_LEXICON_DIR" >&2
    echo "       The .pose files are not in the repository. Set ASLYTICS_LEXICON_DIR" >&2
    echo "       to point at them, or see README.md to generate them." >&2
    missing=1
  fi

  return $missing
}
