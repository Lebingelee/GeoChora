"""Focused CLI boundary tests for the built-in PickCube Harness wrapper."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).with_name("pick_cube.py")
SPEC = importlib.util.spec_from_file_location("pick_cube_example_cli", SCRIPT)
pick_cube = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(pick_cube)


def test_optional_missing_engine_is_recorded_without_starting_a_worker(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pick_cube.importlib.util, "find_spec", lambda _name: None)
    output = tmp_path / "genesis-seed31"
    args = SimpleNamespace(
        controller_profile="r3_continuous_v1",
        horizon=1000,
        seed=31,
        provider="genesis",
        source_delivery_manifest=None,
        recording=None,
        harness_output_dir=output,
    )

    assert pick_cube._run_harness(args) == 0
    receipt = json.loads((output / "result" / "preflight.json").read_text())
    printed = json.loads(capsys.readouterr().out)
    assert receipt["disposition"] == "NOT_RUN_DEPENDENCY"
    assert receipt["native_starts"] == 0
    assert printed["provider"] == "genesis"
    assert not (output / "result" / "run_plan.json").exists()
