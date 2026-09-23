"""
Tests for asl_renderer.RenderService.

Uses this repository's own test pose as a stand-in lexicon, so these run
without the real sign lexicon (which is not in the repository).

    python tools/tests/test_renderer.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, REPO)

FIXTURE = os.path.join(REPO, "pose-master", "pose-master", "src", "python",
                       "tests", "data", "mediapipe.pose")


def make_lexicon(directory, glosses=("hello", "world", "cat")):
    os.makedirs(directory, exist_ok=True)
    for gloss in glosses:
        shutil.copy(FIXTURE, os.path.join(directory, f"{gloss}.pose"))
    return directory


def service(tmp, **kwargs):
    from asl_renderer import RenderService

    return RenderService(lexicon_directory=make_lexicon(os.path.join(tmp, "lexicon")),
                         cache_directory=os.path.join(tmp, "clips"), **kwargs)


def test_lexicon_is_discovered():
    with tempfile.TemporaryDirectory() as tmp:
        assert service(tmp).available_glosses() == {"hello", "world", "cat"}


def test_missing_glosses_are_reported_together():
    """One caption can miss several glosses. Reporting the first only means
    rediscovering the next on the following run."""
    from asl_renderer import MissingGlosses

    with tempfile.TemporaryDirectory() as tmp:
        svc = service(tmp)
        assert svc.missing_from(["hello", "zebra", "world", "quokka"]) == ["zebra", "quokka"]
        try:
            svc.render(["hello", "zebra", "quokka"], os.path.join(tmp, "out.mp4"))
            raise AssertionError("should have raised")
        except MissingGlosses as error:
            assert error.missing == ["zebra", "quokka"]


def test_missing_report_deduplicates_and_keeps_order():
    with tempfile.TemporaryDirectory() as tmp:
        assert service(tmp).missing_from(["zebra", "hello", "zebra"]) == ["zebra"]


def test_pose_cache_serves_repeats():
    with tempfile.TemporaryDirectory() as tmp:
        svc = service(tmp)
        svc.pose_for("hello")
        svc.pose_for("hello")
        assert svc._poses.hits == 1 and svc._poses.misses == 1


def test_pose_cache_evicts_beyond_capacity():
    with tempfile.TemporaryDirectory() as tmp:
        svc = service(tmp, pose_cache_size=2)
        for gloss in ("hello", "world", "cat"):
            svc.pose_for(gloss)
        assert len(svc._poses) == 2, "LRU should have evicted the oldest"


def test_warm_skips_unknown_glosses():
    with tempfile.TemporaryDirectory() as tmp:
        svc = service(tmp)
        assert svc.warm(["hello", "zebra", "world"]) == 2


def test_cache_key_is_order_sensitive_and_version_sensitive():
    """A different sign order is a different sentence, and a render change must
    not be served from a cache built before it."""
    import asl_renderer

    with tempfile.TemporaryDirectory() as tmp:
        svc = service(tmp)
        assert svc.cache_key(["hello", "world"]) != svc.cache_key(["world", "hello"])
        assert svc.cache_key(["hello"]) == svc.cache_key(["hello"])

        before = svc.cache_key(["hello", "world"])
        original = asl_renderer.RENDER_VERSION
        try:
            asl_renderer.RENDER_VERSION = original + 1
            assert svc.cache_key(["hello", "world"]) != before
        finally:
            asl_renderer.RENDER_VERSION = original


def test_render_caches_and_second_call_hits():
    with tempfile.TemporaryDirectory() as tmp:
        svc = service(tmp)
        first, hit_first = svc.render(["hello", "world"], os.path.join(tmp, "a.mp4"))
        second, hit_second = svc.render(["hello", "world"], os.path.join(tmp, "b.mp4"))

        assert not hit_first and hit_second
        assert os.path.exists(first) and os.path.exists(second)
        assert os.path.getsize(first) == os.path.getsize(second) > 0
        assert svc.cache_report()["clip_hit_rate"] == 0.5


def test_cached_pose_is_not_corrupted_by_a_previous_render():
    """The trap this cache could easily have introduced.

    concatenate_poses trims and normalises its inputs in place. Handing it the
    cached Pose object directly would leave the trimmed remains in the cache,
    so the next caption using that gloss would render something shorter and
    subtly wrong -- and it would only show up on the second occurrence, which
    is a miserable thing to debug.
    """
    with tempfile.TemporaryDirectory() as tmp:
        svc = service(tmp)

        baseline, _ = svc.render(["hello", "world"], os.path.join(tmp, "baseline.mp4"))
        baseline_size = os.path.getsize(baseline)

        # Reuse "hello" in a different sequence, which runs concatenation over
        # the cached pose again.
        svc.render(["hello", "cat"], os.path.join(tmp, "other.mp4"))

        # Render the original sequence from scratch, bypassing the clip cache.
        fresh = service(tmp, clip_cache=False)
        fresh_path = os.path.join(tmp, "fresh.mp4")
        fresh.pose_for("hello")
        fresh.render(["hello", "cat"], os.path.join(tmp, "warmup.mp4"))
        fresh.render(["hello", "world"], fresh_path)

        assert os.path.getsize(fresh_path) == baseline_size, (
            "a cached pose was mutated by an earlier render")


def test_empty_gloss_sequence_is_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            service(tmp).render([], os.path.join(tmp, "out.mp4"))
            raise AssertionError("should have raised")
        except ValueError:
            pass


def main() -> int:
    tests = [(name, value) for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    failures = []
    for name, test in tests:
        try:
            test()
            print(f"  ok    {name}")
        except Exception as error:  # noqa: BLE001 - this is the reporter
            failures.append(name)
            print(f"  FAIL  {name}: {type(error).__name__}: {error}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
