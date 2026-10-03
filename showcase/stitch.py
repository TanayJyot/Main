"""Put several renders of one sentence side by side, labelled, in one video.

Each panel is a tier's video, letterboxed to the same square, with the tier's
name above and what it signed below. Panels play in step; a shorter one holds
its last frame. A panel whose tier could sign nothing shows a blank square
saying so. Research-only tiers are marked on the video itself, so the mark
travels with any screenshot.

Text is drawn with OpenCV's built-in font, which is ASCII only.
"""

from __future__ import annotations

import subprocess
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

PANEL = 420                 # square panel, pixels
HEADER, FOOTER, TOP = 56, 96, 64
GAP = 8
FPS = 30.0
HOLD_SECONDS = 1.0          # still frame at the end, so the last sign can be read
BG, PANEL_BG = (24, 24, 24), (0, 0, 0)
WHITE, GREY, GREEN, BLUE, RED, AMBER = ((255, 255, 255), (170, 170, 170), (120, 200, 120),
                                        (240, 170, 90), (90, 90, 230), (60, 190, 250))
FONT = cv2.FONT_HERSHEY_SIMPLEX


@dataclass
class Panel:
    title: str
    video: Optional[Path]                 # None: nothing could be signed
    signed: List[str] = field(default_factory=list)
    spelled: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    research_only: bool = False


def _ascii(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def _frames(video: Path) -> tuple:
    capture = cv2.VideoCapture(str(video))
    fps = capture.get(cv2.CAP_PROP_FPS) or FPS
    frames = []
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        frames.append(_letterbox(frame))
    capture.release()
    return frames, fps


def _letterbox(frame: np.ndarray) -> np.ndarray:
    h, w = frame.shape[:2]
    scale = PANEL / max(h, w)
    resized = cv2.resize(frame, (max(1, round(w * scale)), max(1, round(h * scale))),
                         interpolation=cv2.INTER_AREA)
    out = np.zeros((PANEL, PANEL, 3), np.uint8)
    out[:] = PANEL_BG
    y, x = (PANEL - resized.shape[0]) // 2, (PANEL - resized.shape[1]) // 2
    out[y:y + resized.shape[0], x:x + resized.shape[1]] = resized
    return out


def _text(image, text, x, y, color=WHITE, scale=0.5, thickness=1):
    cv2.putText(image, _ascii(text), (x, y), FONT, scale, color, thickness, cv2.LINE_AA)


def _lines(text: str, width_px: int, scale: float) -> List[str]:
    char_px = 20 * scale       # Hershey simplex is about 20 px per char at scale 1
    return textwrap.wrap(_ascii(text), max(8, int(width_px / char_px))) or [""]


def _blank(message: str) -> np.ndarray:
    out = np.zeros((PANEL, PANEL, 3), np.uint8)
    for i, line in enumerate(_lines(message, PANEL - 40, 0.6)):
        _text(out, line, 20, PANEL // 2 + i * 24, GREY, 0.6)
    return out


def _chrome(panel: Panel, width: int) -> tuple:
    """(header image, footer image) for one panel."""
    header = np.zeros((HEADER, width, 3), np.uint8)
    header[:] = BG
    for i, line in enumerate(_lines(panel.title, width - 16, 0.55)[:2]):
        _text(header, line, 8, 22 + i * 22, WHITE, 0.55, 1)
    footer = np.zeros((FOOTER, width, 3), np.uint8)
    footer[:] = BG
    total = len(panel.signed) + len(panel.spelled) + len(panel.skipped)
    rows = [(f"{len(panel.signed)} of {total} words signed"
             + (f", {len(panel.spelled)} spelled" if panel.spelled else ""), WHITE)]
    if panel.skipped:
        rows.append(("missing: " + " ".join(panel.skipped), RED))
    if panel.spelled:
        rows.append(("spelled: " + " ".join(panel.spelled), BLUE))
    y = 20
    for text, color in rows:
        for line in _lines(text, width - 16, 0.45)[:1]:
            _text(footer, line, 8, y, color, 0.45)
            y += 20
    if panel.research_only:
        _text(footer, "RESEARCH PREVIEW - NOT FOR DISTRIBUTION", 8, FOOTER - 8, AMBER, 0.45, 1)
    return header, footer


def side_by_side(panels: List[Panel], caption: str, out: Path, ffmpeg: Optional[str] = None) -> Path:
    """Write the comparison video to out (H.264 if ffmpeg is given) and return it."""
    sources = []
    for panel in panels:
        if panel.video and Path(panel.video).exists():
            frames, fps = _frames(Path(panel.video))
        else:
            frames, fps = [], FPS
        sources.append((frames or [_blank("Nothing in this sentence could be signed with this lexicon.")],
                        fps))
    seconds = max(len(frames) / fps for frames, fps in sources) + HOLD_SECONDS
    count = max(1, int(round(seconds * FPS)))

    width = len(panels) * PANEL + (len(panels) + 1) * GAP
    height = TOP + HEADER + PANEL + FOOTER + GAP
    top = np.zeros((TOP, width, 3), np.uint8)
    top[:] = BG
    for i, line in enumerate(_lines(f'"{caption}"', width - 24, 0.7)[:2]):
        _text(top, line, 12, 28 + i * 28, WHITE, 0.7, 2)
    chrome = [_chrome(panel, PANEL) for panel in panels]

    out.parent.mkdir(parents=True, exist_ok=True)
    raw = out.with_suffix(".raw.mp4")
    writer = cv2.VideoWriter(str(raw), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (width, height))
    try:
        for index in range(count):
            t = index / FPS
            canvas = np.zeros((height, width, 3), np.uint8)
            canvas[:] = BG
            canvas[:TOP] = top
            for n, ((frames, fps), (header, footer)) in enumerate(zip(sources, chrome)):
                x = GAP + n * (PANEL + GAP)
                frame = frames[min(int(t * fps), len(frames) - 1)]
                canvas[TOP:TOP + HEADER, x:x + PANEL] = header
                canvas[TOP + HEADER:TOP + HEADER + PANEL, x:x + PANEL] = frame
                canvas[TOP + HEADER + PANEL:TOP + HEADER + PANEL + FOOTER, x:x + PANEL] = footer
            writer.write(canvas)
    finally:
        writer.release()

    if ffmpeg:
        done = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(raw), "-vcodec", "libx264",
                               "-pix_fmt", "yuv420p", str(out)], capture_output=True, text=True)
        if done.returncode == 0:
            raw.unlink()
            return out
    raw.replace(out)
    return out
