"""Provider-free checks for the DG01 formal worker and independent reader."""

from pathlib import Path

import h5py
import json
import pytest

from task_env.diagnostics.tasks.f05_dg01_core_cell import _phase_at
from task_env.diagnostics.tasks.f05_dg01_native_supervisor import _sample_period_s
from task_env.diagnostics.tasks.f05_dg01_h5_reader import (
    _mjcf_hand_fk,
    _mutate_h5,
    _verify_exit,
    _verify_dg01_horizon_outcome,
    _verify_controller_action_config,
    _verify_reset_write_receipt,
    _verify_selected_core_task_timebase,
)
from task_env.tasks.reference_env import _dg01_position_recording_receipt_failures


def test_schedule_lookup_requires_one_phase_and_preserves_boundaries():
    schedule = [
        {"start": 0, "stop": 50, "phase": "home"},
        {"start": 50, "stop": 100, "phase": "point"},
    ]
    assert _phase_at(0, schedule)["phase"] == "home"
    assert _phase_at(49, schedule)["phase"] == "home"
    assert _phase_at(50, schedule)["phase"] == "point"
    with pytest.raises(ValueError, match="no unique frozen schedule row"):
        _phase_at(100, schedule)
    with pytest.raises(ValueError, match="no unique frozen schedule row"):
        _phase_at(50, [*schedule, {"start": 50, "stop": 60, "phase": "overlap"}])


def test_native_supervisor_uses_a_poll_period_below_the_frozen_gap_ceiling():
    assert _sample_period_s({"sample_interval_s_max": 0.25, "sample_period_s": 0.2}) == 0.2
    assert _sample_period_s({"sample_interval_s_max": 0.25}) == 0.25
    with pytest.raises(ValueError, match="sample period"):
        _sample_period_s({"sample_interval_s_max": 0.25, "sample_period_s": 0.3})


def test_position_recording_binds_write_receipt_to_nested_canonical_target():
    from types import SimpleNamespace

    canonical = SimpleNamespace(identity_hash="canonical-target-identity")
    position_target = SimpleNamespace(
        identity_hash="outer-position-target-identity", target=canonical,
    )
    applied = SimpleNamespace(target_hash=canonical.identity_hash)
    model_receipt = {"identity_sha256": "model-receipt-identity"}
    write_receipt = {
        "target_identity_sha256": canonical.identity_hash,
        "source_closure_sha256": "source-closure-identity",
        "model_receipt_identity_sha256": model_receipt["identity_sha256"],
    }
    advances = tuple({"substep_index": index} for index in range(5))

    assert _dg01_position_recording_receipt_failures(
        write_receipt, model_receipt, "source-closure-identity", position_target,
        applied, 5, advances, 5,
    ) == ()
    wrong_outer_identity = {
        **write_receipt,
        "target_identity_sha256": position_target.identity_hash,
    }
    assert _dg01_position_recording_receipt_failures(
        wrong_outer_identity, model_receipt, "source-closure-identity",
        position_target, applied, 5, advances, 5,
    ) == ("position_write_target_identity",)


def test_independent_fk_applies_source_joint_before_child_body_transform(tmp_path: Path):
    xml_path = tmp_path / "panda_chain.xml"
    xml_path.write_text(
        '<mujoco><compiler angle="radian"/><worldbody>'
        '<body name="link0"><body name="link1" pos="1 0 0">'
        '<joint name="joint1" axis="0 0 1"/>'
        '<body name="hand" pos="1 0 0" quat="1 0 0 0"/>'
        '</body></body></worldbody></mujoco>',
        encoding="utf-8",
    )
    result = _mjcf_hand_fk(xml_path, {"joint1": 1.5707963267948966})
    assert result["position_m"] == pytest.approx([1.0, 1.0, 0.0], abs=1e-12)
    assert result["quaternion_wxyz"] == pytest.approx(
        [2**-0.5, 0.0, 0.0, 2**-0.5], abs=1e-12,
    )


def test_cold_reader_module_has_no_native_or_solver_imports():
    source = Path(__file__).with_name("f05_dg01_h5_reader.py").read_text(encoding="utf-8")
    assert "import mujoco" not in source
    assert "import taichi" not in source
    assert "import isaacsim" not in source
    assert "GeoPhys" not in source
    assert "task_env." not in source


def test_cold_reader_uses_generic_h5_v3_task_and_timebase_locations():
    metadata = {
        "environment": {
            "name": "SelectedReferenceEnv.F05Dg01MenagerieMujocoCore",
            "task_name": "phase-ii-f05-dg01-panda-cube",
        },
        "timebase": {"physics_dt": 0.002, "control_substeps": 5},
    }
    _verify_selected_core_task_timebase(metadata)
    metadata["timebase"]["control_substeps"] = 4
    with pytest.raises(ValueError, match="Task/timebase metadata"):
        _verify_selected_core_task_timebase(metadata)


def test_cold_reader_checks_direct_episode_outcome_mapping():
    outcome = {
        "final_boundary": 300,
        "end_reason": "horizon_reached",
        "terminated": False,
        "truncated": True,
        "task_success": None,
    }
    _verify_dg01_horizon_outcome(outcome)
    with pytest.raises(ValueError, match="horizon-truncated"):
        _verify_dg01_horizon_outcome({"outcome": outcome})


def test_cold_reader_binds_position_action_config_to_the_frozen_plan():
    profile = {
        "controller_action_config": {"joint_position_correction_gain": 1.0},
        "controller_identity_sha256": "controller-identity",
        "control_binding_plan_identity_sha256": "binding-plan-identity",
    }
    plan = {
        "controller_action_config": {"joint_position_correction_gain": 1.0},
        "controller_identity_sha256": "controller-identity",
        "controller_binding_plan_identity_sha256": "binding-plan-identity",
    }
    _verify_controller_action_config(profile, plan)
    plan["controller_action_config"]["joint_position_correction_gain"] = 2.5
    with pytest.raises(ValueError, match="ActionConfig"):
        _verify_controller_action_config(profile, plan)
    plan["controller_action_config"]["joint_position_correction_gain"] = 1.0
    plan["controller_identity_sha256"] = "different-controller"
    with pytest.raises(ValueError, match="ActionConfig"):
        _verify_controller_action_config(profile, plan)
    plan["controller_identity_sha256"] = "controller-identity"
    plan["controller_binding_plan_identity_sha256"] = "different-binding-plan"
    with pytest.raises(ValueError, match="ActionConfig"):
        _verify_controller_action_config(profile, plan)


def test_cold_reader_stale_time_negative_mutates_the_checked_clock(tmp_path: Path):
    path = tmp_path / "typed.h5"
    with h5py.File(path, "w") as h5:
        meta = h5.create_group("meta")
        dtype = h5py.string_dtype(encoding="utf-8")
        meta.create_dataset(
            "f05_public_typed_state_witness_v1_json",
            data=json.dumps({
                "rows": [{}, {"canonical_state_view_v1": {
                    "sample_clock": {"simulation_time_s": 0.01},
                }}],
            }), dtype=dtype,
        )
    _mutate_h5(path, "stale_time")
    with h5py.File(path, "r") as h5:
        value = json.loads(h5["meta/f05_public_typed_state_witness_v1_json"][()].decode())
    assert value["rows"][1]["canonical_state_view_v1"]["sample_clock"]["simulation_time_s"] == 0.008


def test_cold_reader_exit_gate_requires_the_frozen_start_sampling_and_wall_limits():
    plan = {"limits": {
        "start_mem_available_bytes_min": 6 * 1024**3,
        "sample_interval_s_max": 0.25,
        "worker_wall_s_max": 300,
        "group_rss_bytes_max": 4 * 1024**3,
        "abort_mem_available_bytes_below": 1 * 1024**3,
    }}
    receipt = {
        "schema_version": "f05-dg01-native-supervisor-receipt-v1",
        "run_id": "run", "worker_exit_code": 0,
        "resource_violation": None,
        "child_process_group_remaining_after_cleanup": False,
        "lock_released": True,
        "start_mem_available_bytes": 7 * 1024**3,
        "sample_count": 2,
        "sample_interval_s_max_observed": 0.2,
        "wall_seconds": 20,
        "maximum_process_group_rss_bytes": 512 * 1024**2,
        "minimum_mem_available_bytes": 6 * 1024**3,
    }
    _verify_exit(receipt, plan, "run")
    for field, value in (
        ("start_mem_available_bytes", 5 * 1024**3),
        ("sample_interval_s_max_observed", 0.3),
        ("wall_seconds", 301),
    ):
        mutated = {**receipt, field: value}
        with pytest.raises(ValueError, match="exit/resource/process/lock"):
            _verify_exit(mutated, plan, "run")


def test_dg01_mujoco_reset_receipt_covers_source_joints_free_body_and_actuators():
    from types import SimpleNamespace

    from task_env.runtime.sessions.mujoco import _dg01_native_reset_write_receipt

    source = SimpleNamespace(
        joints={"panda-main/joint1": "joint1", "panda-main/finger_joint1": "finger_joint1"},
        free_joints={"free-cube/free_cube": "cube_freejoint"},
        joint_targets={"panda-main/joint1": "actuator1"},
        open_actuators=("actuator8",),
    )
    receipt = _dg01_native_reset_write_receipt(
        SimpleNamespace(sample_id="reset-sample"), source,
    )
    assert receipt.schema_version == "native-reset-write-receipt-v1"
    assert receipt.written_joint_names == ("panda-main/finger_joint1", "panda-main/joint1")
    assert receipt.written_free_joint_names == ("free-cube/free_cube",)
    assert receipt.reset_target_names == ("actuator1", "actuator8")
    assert receipt.velocities_zeroed is True and receipt.partial is False


def test_cold_reader_rejects_partial_or_cross_bound_reset_write_receipts():
    source_mappings = {
        "joints": {"panda-main/joint1": "joint1"},
        "free_joints": {"free-cube/free_cube": "cube_freejoint"},
        "joint_targets": {"panda-main/joint1": "actuator1"},
        "open_actuators": ["actuator8"],
    }
    profile = {
        "source_mappings": source_mappings,
        "reset_sample_id": "reset-sample",
        "reset_write_receipt": {
            "schema_version": "native-reset-write-receipt-v1",
            "reset_sample_id": "reset-sample",
            "written_joint_names": ["panda-main/joint1"],
            "written_free_joint_names": ["free-cube/free_cube"],
            "reset_target_names": ["actuator1", "actuator8"],
            "velocities_zeroed": True,
            "partial": False,
        },
    }
    _verify_reset_write_receipt(profile)
    partial = {**profile, "reset_write_receipt": {**profile["reset_write_receipt"], "partial": True}}
    with pytest.raises(ValueError, match="ResetPlan write receipt"):
        _verify_reset_write_receipt(partial)
    cross_bound = {**profile, "reset_write_receipt": {
        **profile["reset_write_receipt"], "reset_sample_id": "other-reset",
    }}
    with pytest.raises(ValueError, match="ResetPlan write receipt"):
        _verify_reset_write_receipt(cross_bound)
