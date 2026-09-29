#!/bin/bash
# Render one sentence of English into an ASL skeleton video.
#
#     bash utils/generate_asl_video.sh "the cat is small" static/videos/caption_0.mp4
#
# Only the basename of the output path is used; the file is written to
# $ASLYTICS_VIDEO_DIR and copied to $ASLYTICS_WEB_VIDEO_DIR for Flask to serve.

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

sentence="$1"
original_output_path="$2"

aslytics_require || exit 1

mkdir -p "$ASLYTICS_VIDEO_DIR" "$ASLYTICS_WEB_VIDEO_DIR"

filename="$(basename "$original_output_path")"
output_path="$ASLYTICS_VIDEO_DIR/$filename"

# Keep intermediates per-sentence so concurrent renders cannot overwrite each
# other's pose file, which they previously did by sharing one fixed name.
work_pose="$ASLYTICS_WORK_DIR/${filename%.*}.pose"
work_video="$ASLYTICS_WORK_DIR/${filename%.*}.raw.mp4"

echo "Generating ASL video for: $sentence"

# 1. English -> ASL gloss sequence.
raw_output="$(conda run --no-capture-output -n "$ASLYTICS_GLOSS_ENV" \
    python3 "$REPO_ROOT/text-to-gloss/start.py" "$sentence")"

gloss_string="$(echo "$raw_output" | grep "Gloss sequence:" | sed -E "s/.*\[(.*)\]/\1/")"
gloss_py_list="$(echo "$gloss_string" | sed "s/'/\"/g" | sed 's/, */, /g')"

if [ -z "$gloss_string" ]; then
    echo "error: no gloss sequence produced for: $sentence" >&2
    exit 1
fi

echo "Extracted gloss list: [$gloss_py_list]"

# 2. Gloss sequence -> a single concatenated pose.
conda run --no-capture-output -n "$ASLYTICS_POSE_ENV" python3 - <<EOF || exit 1
import sys
sys.path.insert(0, "$REPO_ROOT/pose-master/pose-master/concatenate_pose_function")
from concatenate import gloss_to_pose, concatenate_poses, save_pose

gloss_list = [$gloss_py_list]
try:
    poses = gloss_to_pose(gloss_list)
    save_pose(concatenate_poses(poses), "$work_pose")
except Exception as error:
    print("Failed to generate pose:", error, file=sys.stderr)
    sys.exit(1)
EOF

# 3. Pose -> video frames.
conda run --no-capture-output -n "$ASLYTICS_POSE_ENV" python3 - <<EOF || exit 1
import sys
from pose_format import Pose
from pose_format.pose_visualizer import PoseVisualizer

try:
    with open("$work_pose", "rb") as f:
        pose = Pose.read(f.read())
    visualizer = PoseVisualizer(pose)
    visualizer.save_video("$work_video", visualizer.draw())
except Exception as error:
    print("Failed to visualize pose:", error, file=sys.stderr)
    sys.exit(1)
EOF

# 4. Re-encode to something browsers will play, then publish.
ffmpeg -y -loglevel error -i "$work_video" -vcodec libx264 -pix_fmt yuv420p "$output_path"
cp "$output_path" "$ASLYTICS_WEB_VIDEO_DIR/$filename"

echo "Final video: $ASLYTICS_WEB_VIDEO_DIR/$filename"
