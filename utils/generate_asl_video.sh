#!/bin/bash

# generate_asl_video.sh
sentence="$1"
original_output_path="$2"

# Create both output folders if needed
video_output_dir="/home/ellie/GitHub/ASLytics-RBC/videos"
web_output_dir="/home/ellie/GitHub/ASLytics-RBC/static/videos"

mkdir -p "$video_output_dir"
mkdir -p "$web_output_dir"

# Extract filename only (e.g., caption_0.mp4)
filename=$(basename "$original_output_path")

# Absolute output path (where the ASL pipeline saves initially)
output_path="$video_output_dir/$filename"

echo "🟢 Generating ASL video for: $sentence"

# 1. Get gloss sequence
raw_output=$(conda run -n signspeech python3 /home/ellie/GitHub/ASLytics-RBC/text-to-gloss/start.py "$sentence")

# 2. Extract gloss string list
gloss_string=$(echo "$raw_output" | grep "Gloss sequence:" | sed -E "s/.*\[(.*)\]/\1/")
gloss_py_list=$(echo "$gloss_string" | sed "s/'/\"/g" | sed 's/, */, /g')

echo "🔤 Extracted gloss list: [$gloss_py_list]"

# 3. Generate pose from gloss
cd /home/ellie/GitHub/ASLytics-RBC/pose-master/pose-master/concatenate_pose_function

python3 - <<EOF
from concatenate import gloss_to_pose, concatenate_poses, save_pose

gloss_list = [$gloss_py_list]
try:
    pose_directory = gloss_to_pose(gloss_list)
    result_pose = concatenate_poses(pose_directory)
    save_pose(result_pose, "/home/ellie/GitHub/ASLytics-RBC/.gitignore/generated_pose/combined_output2.pose")
except Exception as e:
    print("⚠️ Failed to generate pose:", e)
    exit(1)
EOF

# 4. Visualize and save to pose_output.mp4
python3 - <<EOF
from pose_format import Pose
from pose_format.pose_visualizer import PoseVisualizer

try:
    with open("/home/ellie/GitHub/ASLytics-RBC/.gitignore/generated_pose/combined_output2.pose", "rb") as f:
        pose = Pose.read(f.read())

    visualizer = PoseVisualizer(pose)
    visualizer.save_video("pose_output.mp4", visualizer.draw())
except Exception as e:
    print("⚠️ Failed to visualize pose:", e)
    exit(1)
EOF

# 5. Convert to proper format using ffmpeg
ffmpeg -y -i pose_output.mp4 -vcodec libx264 -acodec aac "$output_path"

# 6. Copy final video to Flask static folder
cp "$output_path" "$web_output_dir/$filename"

echo "✅ Final video copied to: $web_output_dir/$filename"
