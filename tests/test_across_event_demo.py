"""Tests for events_needed() in scripts/across_event_demo.py.

scripts/ is not a package, so the script is loaded from its file path.
Loading it runs only the module-level code (imports and constants), not
main(), so no simulation runs and no charts are written.
"""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "across_event_demo.py"


def load_script():
    spec = importlib.util.spec_from_file_location("across_event_demo", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_events_needed_assumptions():
    """The numbers below hold only under these assumptions (see the events_needed docstring)."""
    demo = load_script()
    assert demo.TARGET_POWER == 0.80
    assert demo.LEVEL == 0.05
    assert demo.ASSUMED_EFFECT == 0.01
    assert demo.ASSUMED_DAILY_STD == 0.01


@pytest.mark.parametrize(("window", "expected"), [((-1, 1), 26), ((0, 0), 10), ((-5, 5), 89)])
def test_events_needed(window, expected):
    assert load_script().events_needed(window) == expected
