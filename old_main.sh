#!/bin/bash
# Smoke test: render a fixed sentence, to check the pipeline end to end.
#
#     bash old_main.sh
#
# Kept because it is the quickest way to prove a fresh install works. The real
# implementation lives in utils/generate_asl_video.sh.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
sentence="${1:-analyze nothing}"

exec bash "$REPO_ROOT/utils/generate_asl_video.sh" "$sentence" "smoke_test.mp4"
