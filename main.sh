#!/bin/bash

# main.sh
sentence="$1"
original_output_path="$2"

# Set default video output directory
video_output_dir="/home/ellie/GitHub/ASLytics-RBC/videos"
mkdir -p "$video_output_dir"  # Make sure the folder exists

# Extract filename from original output path (ignore folder), save under videos/
filename=$(basename "$original_output_path")
output_path="$video_output_dir/$filename"

echo "Generating ASL video for: $sentence"

# 1. Run start.py and get the gloss
raw_output=$(conda run -n signspeech python3 /home/ellie/GitHub/ASLytics-RBC/text-to-gloss/start.py "$sentence")

# 2. Extract gloss sequence
gloss_string=$(echo "$raw_output" | grep "Gloss sequence:" | sed -E "s/.*\[(.*)\]/\1/")
gloss_py_list=$(echo "$gloss_string" | sed "s/'/\"/g" | sed 's/, */, /g')

echo "Extracted gloss list: [$gloss_py_list]"

# 3. Generate pose from gloss
cd /home/ellie/GitHub/ASLytics-RBC/pose-master/pose-master/concatenate_pose_function

python3 - <<EOF
from concatenate import gloss_to_pose, concatenate_poses, save_pose

gloss_list = [$gloss_py_list]
print("Using gloss list:", gloss_list)

pose_directory = gloss_to_pose(gloss_list)
result_pose = concatenate_poses(pose_directory)
save_pose(result_pose, "/home/ellie/GitHub/ASLytics-RBC/.gitignore/generated_pose/combined_output2.pose")
EOF

# 4. Visualize and save video
python3 - <<EOF
from pose_format import Pose
from pose_format.pose_visualizer import PoseVisualizer

with open("/home/ellie/GitHub/ASLytics-RBC/.gitignore/generated_pose/combined_output2.pose", "rb") as f:
    pose = Pose.read(f.read())

visualizer = PoseVisualizer(pose)
visualizer.save_video("pose_output.mp4", visualizer.draw())
EOF

# 5. Fix video format and move to final output path
ffmpeg -y -i pose_output.mp4 -vcodec libx264 -acodec aac "$output_path"

echo "Final output saved to: $output_path"
