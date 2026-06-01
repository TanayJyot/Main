# merge_asl_clips.py
from moviepy import *
import os

def load_clip_with_duration(path, target_duration):
    clip = mpe.VideoFileClip(path)
    if abs(clip.duration - target_duration) > 0.1:
        speed = clip.duration / target_duration
        clip = clip.fx(mpe.vfx.speedx, factor=speed)
    clip = clip.set_duration(target_duration)
    return clip

def merge_asl_video_clips(video_dir, captions_with_time, output_path, total_duration):
    clips = []
    for idx, cap in enumerate(captions_with_time):
        filename = f"caption_{idx}.mp4"
        filepath = os.path.join(video_dir, filename)
        if os.path.exists(filepath):
            clip = load_clip_with_duration(filepath, cap["duration"])
            # put the clip to the right time
            clip = clip.set_start(cap["start"])
            clips.append(clip)
        else:
            print(f"Missing: {filepath}, skipping...")

    if clips:
        # background
        background = mpe.ColorClip(size=(512, 512), color=(0,0,0), duration=total_duration)

        # cover
        final = mpe.CompositeVideoClip([background] + clips)
        final.write_videofile(output_path, codec='libx264')
        print(f"✅ Final ASL video saved to {output_path}")
    else:
        print("⚠️ No clips to merge.")
