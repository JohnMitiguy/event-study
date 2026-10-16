"""Tests for the output paths in scripts/run_opec.py.

scripts/ is not a package, so the script is loaded from its file path.
Loading it runs only the module-level code (imports and constants), not
main(), so nothing is downloaded or written.
"""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "run_opec.py"


def load_script():
    spec = importlib.util.spec_from_file_location("run_opec", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_main_output_paths():
    run_opec = load_script()
    assert run_opec.output_paths(official_time=False) == (
        Path("results") / "opec_results.csv",
        Path("results") / "opec_run_info.json",
        Path("charts") / "opec_events.png",
    )


def test_official_time_output_paths():
    run_opec = load_script()
    assert run_opec.output_paths(official_time=True) == (
        Path("results") / "opec_results_official_time.csv",
        Path("results") / "opec_run_info_official_time.json",
        Path("charts") / "opec_events_official_time.png",
    )


def test_official_time_never_overwrites_main_outputs():
    run_opec = load_script()
    main = set(run_opec.output_paths(official_time=False))
    official = set(run_opec.output_paths(official_time=True))
    assert main.isdisjoint(official)
