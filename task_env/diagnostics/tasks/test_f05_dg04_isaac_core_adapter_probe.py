"""Provider-free contract checks for the DG04 N1 bootstrap receipt parser."""

from __future__ import annotations

import pytest

from task_env.diagnostics.tasks.f05_dg04_isaac_core_adapter_probe import (
    _bootstrap_attempted_steps,
    _diagnostic_contact_reset_sample,
    _verify_paired_physics_response,
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


def _paired_response_receipts(*, physics_changes: bool):
    dynamic_trace = []
    fixed_trace = []
    for index in range(1, 41):
        dynamic_delta = 2e-5 if physics_changes and index == 20 else 0.0
        velocity_delta = 2e-4 if physics_changes and index == 20 else 0.0
        common = {
            "step_index": index,
            "rollout_control_value": 127.5,
        }
        dynamic_trace.append({
            **common,
            "public_frequency_readback_hz": 30.544888068141525,
            "post_step_finger_positions_m": [0.024, 0.04 + dynamic_delta],
            "post_step_finger_velocities_m_s": [0.0, velocity_delta],
        })
        fixed_trace.append({
            **common,
            "public_frequency_readback_hz": 31.830988618379067,
            "post_step_finger_positions_m": [0.024, 0.04],
            "post_step_finger_velocities_m_s": [0.0, 0.0],
        })
    shared = {
        "rollout_steps": 40,
        "rollout_reset_sample_id": "same-reset-sample",
        "rollout_control_value": 127.5,
        "rollout_initial_positions_m": [0.024, 0.04],
        "rollout_initial_velocities_m_s": [0.0, 0.0],
    }
    return {
        "source_dynamic": {**shared, "trace": dynamic_trace},
        "fixed_endpoint_ablation": {**shared, "trace": fixed_trace},
    }


def test_paired_response_detector_accepts_public_state_divergence():
    receipt = _verify_paired_physics_response(_paired_response_receipts(physics_changes=True))
    assert receipt["status"] == "PASS_PUBLIC_PHYSICS_RESPONSE_CHANGES_WITH_SOURCE_MAPPING"
    assert receipt["max_public_frequency_delta_hz"] > 0.1
    assert receipt["max_post_step_equality_residual_delta_m"] > 5e-6
    assert receipt["max_post_step_relative_velocity_delta_m_s"] > 1e-4


def test_paired_response_detector_rejects_changed_properties_when_physics_ignores_them():
    """Property readback alone must not pass when public post-step response is identical."""
    with pytest.raises(ValueError, match="max_post_step_equality_residual_delta_m"):
        _verify_paired_physics_response(_paired_response_receipts(physics_changes=False))


def test_dg03_public_physics_change_flush_is_required_before_step():
    from task_env.runtime.sessions.isaac_native_io import _flush_public_physics_changes

    calls = []

    class PublicSimulationInterface:
        def flush_changes(self):
            calls.append("flush_changes")

    _flush_public_physics_changes(PublicSimulationInterface())
    assert calls == ["flush_changes"]


def test_dg03_public_physics_change_flush_fails_closed_when_unavailable():
    from task_env.runtime.sessions.isaac_native_io import _flush_public_physics_changes

    with pytest.raises(RuntimeError, match="IPhysxSimulation.flush_changes"):
        _flush_public_physics_changes(object())


def test_contact_diagnostic_reset_preserves_task_reset_and_authors_one_mm_overlap():
    from task_env.tasks.position_candidate.builder import build_f05_dg03_isaac_usd_candidate
    from task_env.diagnostics.tasks.f05_dg04_isaac_core_adapter_probe import DELIVERY_MANIFEST

    input_v1, _candidate = build_f05_dg03_isaac_usd_candidate(DELIVERY_MANIFEST, horizon=8)
    source = input_v1.reset_plan.reset_sample
    probe = _diagnostic_contact_reset_sample(source)
    source_pose = source.poses_world["free-cube/free_cube"]
    probe_pose = probe.poses_world["free-cube/free_cube"]

    assert probe.sample_id != source.sample_id
    assert probe.task_artifact_hash == source.task_artifact_hash
    assert probe.task_seed == source.task_seed
    assert probe.joint_position == source.joint_position
    assert probe_pose.position[:2] == source_pose.position[:2] == (1.0, 0.5)
    assert probe_pose.quaternion_wxyz == source_pose.quaternion_wxyz
    assert probe_pose.position[2] == pytest.approx(0.504)
    cube_bottom_m = probe_pose.position[2] - 0.03
    support_top_m = 0.45 + 0.05 / 2.0
    assert support_top_m - cube_bottom_m == pytest.approx(0.001)
    source.validate()
    probe.validate()
