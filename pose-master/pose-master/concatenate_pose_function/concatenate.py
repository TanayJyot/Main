from typing import List, Tuple

import numpy as np
from pose_format import Pose
from pose_format.utils.generic import reduce_holistic, correct_wrists, pose_normalization_info, normalize_pose_size

from smoothing import smooth_concatenate_poses

import os
from pose_format import Pose
from io import BytesIO  

from typing import List

class ConcatenationSettings:
    is_reduce_holistic = True


def normalize_pose(pose: Pose) -> Pose:
    return pose.normalize(pose_normalization_info(pose.header))


def get_signing_boundary(pose: Pose, wrist_index: int, elbow_index: int) -> Tuple[int, int]:
    # Ideally, this could use a sign language detection model.

    pose_length = len(pose.body.data)

    wrist_exists = pose.body.confidence[:, 0, wrist_index] > 0
    first_non_zero_index = np.argmax(wrist_exists).tolist()
    last_non_zero_index = pose_length - np.argmax(wrist_exists[::-1])

    wrist_y = pose.body.data[:, 0, wrist_index, 1]
    elbow_y = pose.body.data[:, 0, elbow_index, 1]

    wrist_above_elbow = wrist_y < elbow_y
    first_active_frame = np.argmax(wrist_above_elbow).tolist()
    last_active_frame = pose_length - np.argmax(wrist_above_elbow[::-1])

    return (max(first_non_zero_index, first_active_frame - 5),
            min(last_non_zero_index, last_active_frame + 5))

def trim_pose(pose, start=True, end=True):
    if len(pose.body.data) == 0:
        raise ValueError("Cannot trim an empty pose")

    first_frame = len(pose.body.data)
    last_frame = 0

    hands = ["LEFT", "RIGHT"]
    for hand in hands:
        wrist_index = pose.header._get_point_index(f"POSE_LANDMARKS", f"{hand}_WRIST")
        elbow_index = pose.header._get_point_index(f"POSE_LANDMARKS", f"{hand}_ELBOW")
        boundary_start, boundary_end = get_signing_boundary(pose, wrist_index, elbow_index)
        first_frame = min(first_frame, boundary_start)
        last_frame = max(last_frame, boundary_end)

    if not start:
        first_frame = 0
    if not end:
        last_frame = len(pose.body.data)

    pose.body.data = pose.body.data[first_frame:last_frame]
    pose.body.confidence = pose.body.confidence[first_frame:last_frame]
    return pose


def concatenate_poses(poses: List[Pose], trim=True) -> Pose:
    if ConcatenationSettings.is_reduce_holistic:
        print('Reducing poses...')
        poses = [reduce_holistic(p) for p in poses]

    print('Normalizing poses...')
    poses = [normalize_pose(p) for p in poses]

    # Trim the poses to only include the parts where the hands are visible
    if trim:
        print('Trimming poses...')
        poses = [trim_pose(p, i > 0, i < len(poses) - 1) for i, p in enumerate(poses)]

    # Concatenate all poses
    print('Smooth concatenating poses...')
    pose = smooth_concatenate_poses(poses)

    # Correct the wrists (should be after smoothing)
    print('Correcting wrists...')
    pose = correct_wrists(pose)

    # Scale the newly created pose
    print('Scaling pose...')
    normalize_pose_size(pose)

    return pose


# -------- Load function for Pose Format (.pose) --------
def load_pose(filepath):
    """Loads a Pose object from a .pose file using pose_format library."""
    filepath = os.path.expanduser(filepath)
    with open(filepath, "rb") as f:
        pose = Pose.read(f.read())
    return pose

def save_pose(pose: Pose, filepath: str):
    """Saves a Pose object to a .pose file using pose_format library."""
    filepath = os.path.expanduser(filepath)
    # Create an in-memory buffer (BytesIO)
    buffer = BytesIO()
    # Write pose data to the buffer
    pose.write(buffer) 
    # Now save the content from the buffer to a file
    with open(filepath, 'wb') as f:
        f.write(buffer.getvalue())  # Write the in-memory data to the file
    print(f"Pose saved to: {filepath}")

# Load pose files
# pose1 = load_pose('~/Desktop/pose/signpose_videos/analyze.pose')
# pose2 = load_pose('~/Desktop/pose/signpose_videos/absolutely_nothing.pose')

# how it will be used with ['word1', 'word2']
def gloss_to_pose(list_of_gloss: List[str]) -> List:
    list_of_pose = []
    for vocab in list_of_gloss:
        pose_data = load_pose(f'/home/ellie/GitHub/ASLytics-RBC/.gitignore/generated_pose/{vocab}.pose')
        list_of_pose.append(pose_data)
    return list_of_pose

# Concatenate
# pose_directory = gloss_to_pose(['analyze', 'absolutely_nothing'])
# result_pose = concatenate_poses(pose_directory)
# # result_pose = concatenate_poses([pose1, pose2])

# # Print or save result
# save_pose(result_pose, '/home/ellie/GitHub/ASLytics-RBC/.gitignore/generated_pose/combined_output2.pose')
# print("Result:", result_pose)
