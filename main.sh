#!/bin/bash
# Render one sentence into an ASL skeleton video.
#
#     bash main.sh "the cat is small" videos/caption_0.mp4
#
# This used to be a near-duplicate of utils/generate_asl_video.sh, with the
# same logic and the same hardcoded paths maintained in two places. It now
# delegates, so there is one implementation to keep working.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$REPO_ROOT/utils/generate_asl_video.sh" "$@"
