"""Tests for the conda-free pipeline: utils/aslytics_env.py, render_glosses.py.

    python tools/tests/test_pipeline_env.py
"""

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "utils"))

import aslytics_env as env  # noqa: E402
import render_glosses as rg  # noqa: E402


class Environ:
    """Temporarily set and clear environment variables."""

    def __init__(self, **values):
        self.values, self.saved = values, {}

    def __enter__(self):
        for key, value in self.values.items():
            self.saved[key] = os.environ.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def __exit__(self, *exc):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_parses_start_py_output():
    out = "Text to process: x\n\nResult: [...]\nGloss sequence: ['cat', 'small']\n"
    assert rg.glosses_from_start_output(out) == ["cat", "small"]


def test_takes_the_last_gloss_line():
    out = "Gloss sequence: ['old']\nGloss sequence: ['new', 'one']\n"
    assert rg.glosses_from_start_output(out) == ["new", "one"]


def test_no_gloss_line_means_no_glosses():
    assert rg.glosses_from_start_output("Traceback (most recent call last): ...") == []


def test_code_in_gloss_output_is_not_executed():
    """The shell pipeline pasted this list into Python source. Caption text
    reaches it, so a crafted caption could run code. literal_eval refuses."""
    marker = REPO / ".work" / "pwned"
    marker.unlink(missing_ok=True)
    hostile = f"Gloss sequence: __import__('pathlib').Path({str(marker)!r}).touch()"
    assert rg.glosses_from_start_output(hostile) == []
    assert not marker.exists()


def test_python_runner_prefers_explicit_interpreter():
    with Environ(ASLYTICS_RUNNER="python", ASLYTICS_POSE_PYTHON="/opt/pose/python",
                 ASLYTICS_PYTHON="/opt/shared/python"):
        assert env.runner(env.POSE).command == ["/opt/pose/python"]
        assert env.runner(env.GLOSS).command == ["/opt/shared/python"]


def test_python_runner_falls_back_to_current_interpreter():
    with Environ(ASLYTICS_RUNNER="python", ASLYTICS_POSE_PYTHON=None, ASLYTICS_PYTHON=None):
        command = env.runner(env.POSE).command
        venv = env._venv_python()
        assert command == [venv or sys.executable]


def test_auto_without_conda_uses_python():
    with Environ(ASLYTICS_RUNNER="auto", PATH="/nonexistent", ASLYTICS_PYTHON="/x/python"):
        assert env.runner(env.GLOSS).command == ["/x/python"]


def test_bad_runner_mode_is_rejected():
    with Environ(ASLYTICS_RUNNER="docker"):
        try:
            env.runner(env.POSE)
            raise AssertionError("should have raised")
        except ValueError:
            pass


def test_ffmpeg_override_and_fallback():
    with Environ(ASLYTICS_FFMPEG="/custom/ffmpeg"):
        assert env.ffmpeg() == "/custom/ffmpeg"
    with Environ(ASLYTICS_FFMPEG=None, PATH="/nonexistent"):
        found = env.ffmpeg()
        try:
            import imageio_ffmpeg  # noqa: F401
            assert found and "ffmpeg" in found, found
        except ImportError:
            assert found is None


def test_lexicon_dir_override():
    with Environ(ASLYTICS_LEXICON_DIR="/some/where"):
        assert env.lexicon_dir() == Path("/some/where")


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, test in tests:
        try:
            test(); print(f"  ok    {name}")
        except Exception as error:  # noqa: BLE001
            failed += 1; print(f"  FAIL  {name}: {error!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
