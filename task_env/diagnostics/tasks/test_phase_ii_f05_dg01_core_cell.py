"""Provider-free checks for the DG01 formal worker and independent reader."""

from pathlib import Path

import h5py
import json
import pytest

from task_env.diagnostics.tasks.f05_dg01_core_cell import _phase_at
from task_env.diagnostics.tasks.f05_dg01_h5_reader import (
    _mjcf_hand_fk,
    _mutate_h5,
    _verify_exit,
)


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
