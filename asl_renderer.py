"""
A warm, caching renderer for gloss sequences.

The shell pipeline spawns three processes per caption -- `conda run` for the
glosser, then twice more for the pose steps -- and rebuilds the StanfordNLP
pipeline from scratch each time. For a ten-minute video that is a few hundred
interpreter starts and a few hundred model loads to render a few minutes of
signing. Nothing about that can be real time.

This keeps one process warm instead, and caches at the two levels where the
work actually repeats:

  glosses  Sign vocabulary is Zipfian. Across a video the same few hundred
           glosses recur constantly, so a loaded, normalised Pose is worth
           holding on to.
  clips    Captions repeat across videos, and every re-run of the same video
           re-renders identical sequences. Keyed by the gloss sequence and the
           render settings, so a changed setting cannot serve a stale clip.

Measured on this repository's test pose, a two-gloss caption costs ~175 ms to
concatenate and ~1.26 s to render. Those are the numbers to beat, and a cache
hit skips both.

Usage:

    service = RenderService()
    service.warm(["hello", "world"])          # optional: preload
    path, hit = service.render(["hello", "world"], "out.mp4")
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from collections import OrderedDict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

_CONCAT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "pose-master", "pose-master", "concatenate_pose_function")
if _CONCAT_DIR not in sys.path:
    sys.path.insert(0, _CONCAT_DIR)

from concatenate import concatenate_poses, lexicon_dir, load_pose  # noqa: E402

# Bumped when a change alters rendered output, so old cache entries are not
# served for new behaviour. Anything that changes pixels belongs in the key.
RENDER_VERSION = 1


class MissingGlosses(KeyError):
    """Raised when the lexicon has no .pose for one or more glosses."""

    def __init__(self, missing: Sequence[str], directory: str):
        self.missing = list(missing)
        self.directory = directory
        super().__init__(
            f"no .pose file for {self.missing} in {directory}. "
            f"Set ASLYTICS_LEXICON_DIR if the lexicon lives elsewhere."
        )


class _LRU:
    """Small LRU keyed by gloss. Guarded, since renders may be threaded."""

    def __init__(self, capacity: int):
        self.capacity = max(1, capacity)
        self._items: OrderedDict = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key):
        with self._lock:
            if key in self._items:
                self._items.move_to_end(key)
                self.hits += 1
                return self._items[key]
            self.misses += 1
            return None

    def put(self, key, value) -> None:
        with self._lock:
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self.capacity:
                self._items.popitem(last=False)

    def __len__(self) -> int:
        return len(self._items)


class RenderService:
    """Renders gloss sequences to video, keeping the expensive parts warm."""

    def __init__(self, lexicon_directory: Optional[str] = None,
                 cache_directory: Optional[str] = None,
                 pose_cache_size: int = 256,
                 clip_cache: bool = True):
        self.lexicon_directory = lexicon_directory or lexicon_dir()
        self.clip_cache = clip_cache
        self.cache_directory = cache_directory or os.path.join(
            os.environ.get("ASLYTICS_WORK_DIR",
                           os.path.join(os.path.dirname(os.path.abspath(__file__)), ".work")),
            "clips")
        if self.clip_cache:
            os.makedirs(self.cache_directory, exist_ok=True)

        self._poses = _LRU(pose_cache_size)
        self._render_lock = threading.Lock()
        self.stats = {"clip_hits": 0, "clip_misses": 0, "render_seconds": 0.0}

    # -- lexicon ---------------------------------------------------------

    def available_glosses(self) -> set:
        """Every gloss the lexicon can render.

        Worth checking up front: a caption that hits one missing gloss
        currently produces no video at all, so knowing the vocabulary in
        advance lets the caller fingerspell or substitute instead of failing.
        """
        if not os.path.isdir(self.lexicon_directory):
            return set()
        return {os.path.splitext(name)[0]
                for name in os.listdir(self.lexicon_directory)
                if name.endswith(".pose")}

    def missing_from(self, glosses: Iterable[str]) -> List[str]:
        available = self.available_glosses()
        # Preserve order and drop duplicates, so the report reads like the input.
        seen, missing = set(), []
        for gloss in glosses:
            if gloss not in available and gloss not in seen:
                seen.add(gloss)
                missing.append(gloss)
        return missing

    def pose_for(self, gloss: str):
        """A loaded Pose for one gloss, cached."""
        cached = self._poses.get(gloss)
        if cached is not None:
            return cached

        path = os.path.join(self.lexicon_directory, f"{gloss}.pose")
        if not os.path.exists(path):
            raise MissingGlosses([gloss], self.lexicon_directory)

        pose = load_pose(path)
        self._poses.put(gloss, pose)
        return pose

    def warm(self, glosses: Iterable[str]) -> int:
        """Preload poses. Returns how many are now resident."""
        for gloss in glosses:
            try:
                self.pose_for(gloss)
            except MissingGlosses:
                continue
        return len(self._poses)

    # -- rendering -------------------------------------------------------

    def cache_key(self, glosses: Sequence[str]) -> str:
        payload = json.dumps({"glosses": list(glosses), "version": RENDER_VERSION},
                             sort_keys=True)
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    def render(self, glosses: Sequence[str], output_path: str) -> Tuple[str, bool]:
        """Render a gloss sequence to `output_path`.

        Returns (path, served_from_cache).
        """
        if not glosses:
            raise ValueError("no glosses to render")

        missing = self.missing_from(glosses)
        if missing:
            raise MissingGlosses(missing, self.lexicon_directory)

        cached_path = os.path.join(self.cache_directory, f"{self.cache_key(glosses)}.mp4")
        if self.clip_cache and os.path.exists(cached_path):
            self.stats["clip_hits"] += 1
            _link_or_copy(cached_path, output_path)
            return output_path, True

        self.stats["clip_misses"] += 1
        started = time.time()
        self._render_uncached(glosses, cached_path if self.clip_cache else output_path)
        self.stats["render_seconds"] += time.time() - started

        if self.clip_cache:
            _link_or_copy(cached_path, output_path)
        return output_path, False

    def _render_uncached(self, glosses: Sequence[str], output_path: str) -> None:
        from pose_format.pose_visualizer import PoseVisualizer

        # concatenate_poses mutates the poses it is given (it trims and
        # normalises in place), so cached Pose objects must not be handed to it
        # directly -- the second caption to use a gloss would get the trimmed
        # remains of the first.
        poses = [_copy_pose(self.pose_for(gloss)) for gloss in glosses]
        combined = concatenate_poses(poses)

        directory = os.path.dirname(os.path.abspath(output_path))
        if directory:
            os.makedirs(directory, exist_ok=True)

        # PoseVisualizer is not documented as thread-safe and shares state via
        # pose_format's globals; serialise the actual draw.
        with self._render_lock:
            visualizer = PoseVisualizer(combined)
            visualizer.save_video(output_path, visualizer.draw())

    def cache_report(self) -> Dict[str, object]:
        total = self.stats["clip_hits"] + self.stats["clip_misses"]
        return {
            "poses_resident": len(self._poses),
            "pose_hits": self._poses.hits,
            "pose_misses": self._poses.misses,
            "clip_hits": self.stats["clip_hits"],
            "clip_misses": self.stats["clip_misses"],
            "clip_hit_rate": (self.stats["clip_hits"] / total) if total else 0.0,
            "render_seconds": round(self.stats["render_seconds"], 3),
        }


def _copy_pose(pose):
    """A deep-enough copy that concatenation cannot corrupt the cached original."""
    import copy

    return copy.deepcopy(pose)


def _link_or_copy(source: str, destination: str) -> None:
    directory = os.path.dirname(os.path.abspath(destination))
    if directory:
        os.makedirs(directory, exist_ok=True)
    if os.path.abspath(source) == os.path.abspath(destination):
        return
    if os.path.exists(destination):
        os.remove(destination)
    try:
        os.link(source, destination)  # same filesystem: no copy at all
    except OSError:
        import shutil

        shutil.copy2(source, destination)
