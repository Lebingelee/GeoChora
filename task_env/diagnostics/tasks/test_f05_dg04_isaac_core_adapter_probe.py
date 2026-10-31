"""Provider-free contract checks for the DG04 N1 bootstrap receipt parser."""

from __future__ import annotations

import pytest

from task_env.diagnostics.tasks.f05_dg04_isaac_core_adapter_probe import (
    _bootstrap_attempted_steps,
)


def _bootstrap_receipt():
    return {
        "schema_version": "isaac-public-physics-bootstrap-v1",
        "step_index_before": 100,
        "step_index_after": 102,
        "physics_steps": 2,
        "simulation_time_before_s": 1.0,
        "simulation_time_after_s": 1.004,
        "physics_time_s": 0.004,
        "physics_dt_s": 0.002,
    }


def test_bootstrap_receipt_uses_public_counter_delta_and_timebase():
    assert _bootstrap_attempted_steps(_bootstrap_receipt()) == 2


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("schema_version", "other-bootstrap-v1"),
        ("step_index_before", True),
        ("step_index_after", 103),
        ("physics_steps", 2.0),
        ("simulation_time_before_s", False),
        ("simulation_time_after_s", 1.005),
        ("physics_time_s", float("nan")),
        ("physics_dt_s", 0.0),
        ("step_index_after", None),
    ),
)
def test_bootstrap_receipt_rejects_inexact_or_inconsistent_facts(key, value):
    receipt = _bootstrap_receipt()
    receipt[key] = value
    with pytest.raises(ValueError):
        _bootstrap_attempted_steps(receipt)


def test_bootstrap_receipt_rejects_non_mapping_input():
    with pytest.raises(TypeError):
        _bootstrap_attempted_steps(None)
