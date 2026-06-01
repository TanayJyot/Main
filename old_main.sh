#!/bin/bash

# 1. run start.py and get the gloss
raw_output=$(conda run -n signspeech python3 /home/ellie/GitHub/ASLytics-RBC/text-to-gloss/start.py "analyze nothing")

# 2. gloss sequence
gloss_string=$(echo "$raw_output" | grep "Gloss sequence:" | sed -E "s/.*\[(.*)\]/\1/")
gloss_py_list=$(echo "$gloss_string" | sed "s/'/\"/g" | sed 's/, */, /g')

echo "Extracted gloss list: [$gloss_py_list]"

cd /home/ellie/GitHub/ASLytics-RBC/pose-master/pose-master/concatenate_pose_function

# 3. execute pose
python3 - <<EOF
from concatenate import gloss_to_pose, concatenate_poses, save_pose

gloss_list = [$gloss_py_list]
print("Using gloss list:", gloss_list)

pose_directory = gloss_to_pose(gloss_list)
result_pose = concatenate_poses(pose_directory)
save_pose(result_pose, "/home/ellie/GitHub/ASLytics-RBC/.gitignore/generated_pose/combined_output2.pose")
EOF

# 4. get the video
python3 - <<EOF
from pose_format import Pose
from pose_format.pose_visualizer import PoseVisualizer

with open("/home/ellie/GitHub/ASLytics-RBC/.gitignore/generated_pose/combined_output2.pose", "rb") as f:
    pose = Pose.read(f.read())

visualizer = PoseVisualizer(pose)
visualizer.save_video("pose_output.mp4", visualizer.draw())
EOF

# 5. optional: fix the type of video
ffmpeg -y -i pose_output.mp4 -vcodec libx264 -acodec aac pose_output_fixed.mp4
echo "Final output saved to: pose_output_fixed.mp4"
