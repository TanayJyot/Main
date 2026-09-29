"""
Composite the per-caption ASL clips onto one timeline.

Each clip is stretched or squeezed to fill its caption's slot and placed at
that caption's start time, so the ASL track stays in sync with the source
video's captions.

This module previously called `mpe.VideoFileClip(...)` after `from moviepy
import *`, which never defines `mpe` — so the first call raised NameError. It
also mixed MoviePy 1.x methods (`set_duration`, `fx`) with the 2.x import
style. The small compat layer below papers over the 1.x/2.x split, since which
one is installed varies by machine and the rename is the only difference that
matters here.
"""

import os

from moviepy import ColorClip, CompositeVideoClip, VideoFileClip, vfx

# Matches the frame size PoseVisualizer renders at.
CANVAS_SIZE = (512, 512)
BACKGROUND_COLOR = (0, 0, 0)


def _with_duration(clip, duration):
    # MoviePy 2.x renamed the `set_*` builders to `with_*`.
    setter = getattr(clip, "with_duration", None) or clip.set_duration
    return setter(duration)


def _with_start(clip, start):
    setter = getattr(clip, "with_start", None) or clip.set_start
    return setter(start)


def _with_speed(clip, factor):
    """Multiply playback speed by `factor`."""
    if hasattr(clip, "with_effects"):  # 2.x
        return clip.with_effects([vfx.MultiplySpeed(factor)])
    return clip.fx(vfx.speedx, factor)  # 1.x


def load_clip_with_duration(path, target_duration):
    """Open a clip and make it exactly `target_duration` seconds long."""
    clip = VideoFileClip(path)
    if target_duration and target_duration > 0 and abs(clip.duration - target_duration) > 0.1:
        clip = _with_speed(clip, clip.duration / target_duration)
    return _with_duration(clip, target_duration)


def merge_asl_video_clips(video_dir, captions_with_time, output_path, total_duration):
    """Lay each caption's clip onto a black canvas at its caption's start time.

    `captions_with_time` entries need "start" and "duration", and may carry a
    "file" naming the clip for that caption; without one the clip is assumed to
    be caption_<position>.mp4.

    Returns the number of clips placed, so the caller can tell "nothing was
    generated" apart from "everything was generated".
    """
    clips = []
    missing = []

    for idx, cap in enumerate(captions_with_time):
        # Each entry names its own file. Inferring caption_{idx}.mp4 from the
        # loop counter silently mis-timed the whole track whenever a caption
        # was skipped: the files kept the original caption numbering while the
        # list had closed up around the gap.
        filepath = os.path.join(video_dir, cap.get("file", f"caption_{idx}.mp4"))
        if not os.path.exists(filepath):
            missing.append(filepath)
            continue
        clip = load_clip_with_duration(filepath, cap["duration"])
        clips.append(_with_start(clip, cap["start"]))

    if missing:
        print(f"Missing {len(missing)} clip(s), skipping: {missing[:5]}")

    if not clips:
        print("No clips to merge.")
        return 0

    background = ColorClip(size=CANVAS_SIZE, color=BACKGROUND_COLOR,
                           duration=total_duration)
    final = CompositeVideoClip([background] + clips)
    try:
        # yuv420p so browsers will actually play the result.
        final.write_videofile(output_path, codec="libx264",
                              ffmpeg_params=["-pix_fmt", "yuv420p"])
    finally:
        # Each VideoFileClip holds an ffmpeg subprocess and a file handle.
        for clip in clips:
            clip.close()
        final.close()

    print(f"Final ASL video saved to {output_path}")
    return len(clips)
