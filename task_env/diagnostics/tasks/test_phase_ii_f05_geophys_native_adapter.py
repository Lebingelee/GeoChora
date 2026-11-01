"""Provider-free checks for the F05 GeoPhys native adapter's public I/O seam."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from task_env.diagnostics.tasks.f05_source_control_support import (
    build_native_input,
    lower_public_model,
)
from task_env.runtime.sessions.geophys_source import compile_geophys_usd_position_drive_receipt
from task_env.runtime.sessions.geophys_native_io import F05GeoPhysUsdNativeIO
from task_env.runtime.sessions.native_io import NativeRuntimeIOMetadataV1


class _PublicBoundaryDouble:
    def __init__(self, solver, body_pose, *, dt):
        self.solver = solver
        self.body_pose = body_pose
        self.dt = dt
        self.simulation_time = 0.0
        self.reset_writes = []
        self.steps = 0
        self.close_count = 0

    def apply_reset_state(self, state):
        self.reset_writes.append(state)
        self.solver.qpos = np.array(state.qpos, copy=True)
        self.solver.qvel = np.array(state.qvel, copy=True)
        self.solver.ctrl = np.array(state.ctrl, copy=True)
        self.simulation_time = 0.0

    def read_snapshot(self, _request):
        return SimpleNamespace(
            body_xpos=self.body_pose[0], body_xquat=self.body_pose[1],
            simulation_time=self.simulation_time,
        )

    def step(self, *, substeps):
        assert substeps == 1
        self.steps += 1
        self.solver.native_step_index += 1
        self.simulation_time += self.dt

    def close(self):
        self.close_count += 1


class _PublicSolverDouble:
    def __init__(self, model):
        data = model.joint_data
        self.qpos = np.array(data['initial_qpos'], dtype=np.float32, copy=True)
        self.qvel = np.array(data['initial_qvel'], dtype=np.float32, copy=True)
        self.ctrl = np.asarray(
            data.get('initial_ctrl', np.zeros(int(data['n_actuators']))),
            dtype=np.float32,
        ).copy()
        self.linear = np.array(model.linear_velocities, dtype=np.float64, copy=True)
        self.angular = np.array(model.angular_velocities, dtype=np.float64, copy=True)
        self.native_step_index = 0

    def actuator_force_sample_status(self):
        return SimpleNamespace(native_step_index=self.native_step_index)

    def read_qpos(self):
        return self.qpos.copy()

    def read_qvel(self):
        return self.qvel.copy()

    def write_ctrl(self, value):
        self.ctrl = np.asarray(value, dtype=np.float32).copy()

    def read_ctrl(self):
        return self.ctrl.copy()

    def read_linear_velocities(self):
        return self.linear.copy()

    def read_angular_velocities(self):
        return self.angular.copy()


class _LeaseDouble:
    def __init__(self):
        self.close_count = 0

    def close(self):
        self.close_count += 1


class _RaisingBoundary:
    def __init__(self):
        self.close_count = 0

    def close(self):
        self.close_count += 1
        raise ValueError('primary boundary cleanup error')


class _RaisingLease(_LeaseDouble):
    def close(self):
        self.close_count += 1
        raise RuntimeError('secondary snapshot lease cleanup error')


def test_f05_native_adapter_binds_public_model_and_core_io_without_engine_init():
    candidate = build_native_input('menagerie-panda')
    imported, model, _bridge, report = lower_public_model(candidate.runtime_source)
    receipt = compile_geophys_usd_position_drive_receipt(
        candidate.runtime_source, imported, model, candidate.execution,
        provider_build_identity=candidate.host_model_producer_identity.actual_provider_build_identity,
        provenance_kind='native_runtime',
        host_model_producer_identity=candidate.host_model_producer_identity,
    )
    adapter = F05GeoPhysUsdNativeIO.__new__(F05GeoPhysUsdNativeIO)
    adapter.artifact = candidate.artifact
    adapter.execution = candidate.execution
    adapter.source = candidate.runtime_source
    adapter.input_v1 = candidate
    adapter.drive_receipt = receipt
    adapter.import_mapping_report = report
    adapter._bind_public_model(imported, model)
    adapter._native_step_count = 0
    adapter._native_step_counter_baseline = 0
    adapter._closed = False
    adapter._dg02_contact_observation = False
    lease = _LeaseDouble()
    adapter._composer = lease
    adapter._runtime = SimpleNamespace(solver=_PublicSolverDouble(model))
    adapter._metadata = adapter._build_metadata()

    assert type(adapter._metadata) is NativeRuntimeIOMetadataV1
    assert adapter._metadata.provider_build_identity == candidate.host_model_producer_identity.actual_provider_build_identity
    assert len(adapter._joint_addresses) == 9
    assert len(adapter._body_addresses) == len(candidate.runtime_source.bodies)
    assert set(adapter._free_addresses) == {'square-peg-instance/peg1'}
    assert adapter._joint_addresses['panda-main/joint1'][0] == int(
        model.joint_data['jnt_qposadr'][model.joint_data['name_to_joint']['joint1']]
    )
    assert adapter._joint_addresses['panda-main/joint1'][1] == int(
        model.joint_data['jnt_dofadr'][model.joint_data['name_to_joint']['joint1']]
    )

    body_positions = np.asarray(model.positions, dtype=np.float32).copy()
    body_orientations = np.asarray(model.orientations, dtype=np.float32).copy()
    solver = adapter._runtime.solver
    boundary = _PublicBoundaryDouble(solver, (body_positions, body_orientations),
                                     dt=candidate.artifact.timebase.physics_dt)
    adapter._boundary = boundary
    adapter._initial_state = __import__('task_env.environment', fromlist=['EpisodePhysicsState']).EpisodePhysicsState(
        qpos=np.asarray(model.joint_data['initial_qpos'], dtype=np.float32),
        qvel=np.asarray(model.joint_data['initial_qvel'], dtype=np.float32),
        qacc=np.zeros(int(model.joint_data['n_dof']), dtype=np.float32),
        ctrl=np.asarray(model.joint_data.get('initial_ctrl', np.zeros(int(model.joint_data['n_actuators']))), dtype=np.float32),
        act=np.asarray(model.joint_data.get('initial_act', np.zeros(int(model.joint_data['n_actuators']))), dtype=np.float32),
    )
    sample = candidate.reset_plan.reset_sample
    arm = {f'panda-main/joint{i}': sample.joint_position[f'panda-main/joint{i}']
           for i in range(1, 8)}
    opening = sum(sample.joint_position[f'panda-main/finger_joint{i}'] for i in (1, 2))
    targets = receipt.commands(arm, opening)
    reset = adapter.write_reset(sample, targets)
    assert not reset.partial and reset.velocities_zeroed
    assert len(boundary.reset_writes) == 1 and boundary.steps == 0
    assert not np.any(boundary.reset_writes[0].qvel)
    assert not np.any(boundary.reset_writes[0].qacc)

    readback = adapter.read_state()
    assert readback.simulation_time_s == 0.0
    assert set(readback.joint_position) == set(candidate.runtime_source.joints)
    assert set(readback.free_joint_readback) == set(candidate.runtime_source.free_joints)
    assert boundary.steps == 0
    solver.native_step_index += 1
    with pytest.raises(RuntimeError, match='native-step index mismatch'):
        adapter.read_state()
    solver.native_step_index -= 1

    ack = adapter.write_position_targets('a' * 64, targets)
    ack.validate('a' * 64, targets)
    assert set(ack.native_names) == {row.native_dof_name for row in receipt.drives}
    assert boundary.steps == 0

    advances = [adapter.advance() for _ in range(5)]
    assert boundary.steps == 5
    assert [item.native_step_index for item in advances] == [1, 2, 3, 4, 5]
    assert advances[-1].simulation_time_s == pytest.approx(0.01)
    adapter.close()
    adapter.close()
    assert boundary.close_count == 1
    assert lease.close_count == 1


def test_f05_native_candidate_rejects_wrong_device_and_source_family_before_runtime():
    from dataclasses import replace

    candidate = build_native_input('menagerie-panda')
    wrong_execution = replace(candidate.execution, physics_device='cuda:0')
    rejected = replace(candidate, execution=wrong_execution)
    with pytest.raises(ValueError, match='exact GeoPhys CPU native execution identity'):
        rejected.validate()
    with pytest.raises(ValueError, match='restricted to the frozen Menagerie USD cell'):
        build_native_input('official-panda')


@pytest.mark.parametrize('unsupported', ['timebase', 'capability'])
def test_f05_native_materialization_rejects_unsupported_artifact_before_native_factory(monkeypatch, unsupported):
    from dataclasses import replace
    from task_env.artifacts.execution import ResetSample
    from task_env.runtime.sessions import api, geophys_native_io

    candidate = build_native_input('menagerie-panda')
    if unsupported == 'timebase':
        artifact = replace(candidate.artifact, timebase=replace(
            candidate.artifact.timebase, physics_dt=.004, control_dt=.02,
        ))
        expected = '100 Hz / five 2 ms physics steps'
    else:
        artifact = replace(candidate.artifact, required_capabilities=replace(
            candidate.artifact.required_capabilities,
            names=tuple(sorted(set(candidate.artifact.required_capabilities.names) | {'rgb_camera'})),
        ))
        expected = 'unsupported TaskArtifact capabilities'
    source = replace(candidate.runtime_source, task_artifact=artifact)
    sample_values = candidate.reset_plan.reset_sample.to_mapping()
    sample_values['task_artifact_hash'] = artifact.identity_hash
    plan = replace(candidate.reset_plan, reset_sample=ResetSample.create(**sample_values))
    rejected = replace(candidate, artifact=artifact, runtime_source=source, reset_plan=plan)
    native_calls = []

    def forbidden_factory(**_kwargs):
        native_calls.append(True)
        raise AssertionError('unsupported Artifact reached native factory')

    monkeypatch.setattr(geophys_native_io, 'create_f05_geophys_native_io', forbidden_factory)
    with pytest.raises(ValueError, match=expected):
        api.materialize(
            artifact, rejected.execution, source=source,
            _session_admission_input=rejected,
        )
    assert not native_calls


def test_f05_native_versioned_input_reaches_shared_factory_without_native_materialization(monkeypatch):
    from types import SimpleNamespace
    from task_env.registry import make_env
    from task_env.tasks.position_candidate import builder

    candidate = build_native_input('menagerie-panda')
    marker = object()
    captured = []

    def shared_factory(input_v1, *, horizon, environment_type, controller_config=None):
        assert controller_config is None
        captured.append((input_v1, horizon, environment_type.__name__))
        return SimpleNamespace(env=marker)

    monkeypatch.setattr(builder, 'build_versioned_position_candidate', shared_factory)
    created = make_env('panda-position-servo-candidate-v1',
                       config={'versioned_input': candidate, 'horizon': 100})

    assert created is marker
    assert captured == [(candidate, 100, 'PositionCandidateEnv')]


def test_f05_public_com_velocity_reference_point_oracle_uses_rotated_offset():
    # Non-identity orientation and nonzero COM offset distinguish body-origin
    # velocity from world-COM velocity and catch a missing/crossed cross product.
    orientation = (np.cos(np.pi / 4), 0.0, 0.0, np.sin(np.pi / 4))
    rotation = F05GeoPhysUsdNativeIO._rotation_wxyz(orientation)
    offset_body = np.asarray((0.1, -0.2, 0.05), dtype=np.float64)
    omega_world = np.asarray((0.0, 0.0, 2.0), dtype=np.float64)
    origin_velocity_world = np.asarray((1.0, 2.0, 3.0), dtype=np.float64)
    actual = origin_velocity_world + np.cross(omega_world, rotation @ offset_body)
    np.testing.assert_allclose(actual, (0.8, 2.4, 3.0), rtol=0.0, atol=1e-12)


def test_f05_native_initial_state_defaults_absent_public_ctrl_and_act_to_zero():
    data = {
        'initial_qpos': np.asarray([0.1, 0.2], dtype=np.float64),
        'initial_qvel': np.asarray([0.3], dtype=np.float64),
        'n_dof': 1,
        'n_actuators': 2,
    }

    state = F05GeoPhysUsdNativeIO._initial_state_from_public_model(data)

    np.testing.assert_array_equal(state.qpos, np.asarray([0.1, 0.2], dtype=np.float32))
    np.testing.assert_array_equal(state.qvel, np.asarray([0.3], dtype=np.float32))
    np.testing.assert_array_equal(state.qacc, np.zeros(1, dtype=np.float32))
    np.testing.assert_array_equal(state.ctrl, np.zeros(2, dtype=np.float32))
    np.testing.assert_array_equal(state.act, np.zeros(2, dtype=np.float32))


def test_f05_adapter_close_preserves_primary_cleanup_error_and_releases_lease_once():
    adapter = F05GeoPhysUsdNativeIO.__new__(F05GeoPhysUsdNativeIO)
    boundary = _RaisingBoundary()
    lease = _RaisingLease()
    adapter._boundary = boundary
    adapter._composer = lease
    adapter._closed = False
    with pytest.raises(ValueError, match='primary boundary cleanup error') as caught:
        adapter.close()
    assert boundary.close_count == 1
    assert lease.close_count == 1
    assert any('secondary snapshot lease cleanup error' in note for note in caught.value.__notes__)
    adapter.close()
    assert boundary.close_count == 1
    assert lease.close_count == 1


def test_f05_geophys_drive_numeric_oracle_units_offsets_and_unsupported_law(tmp_path):
    """Check public-model mapping against an independent affine-force oracle."""
    import json
    from types import SimpleNamespace

    from task_env.artifacts import JointReference
    from task_env.runtime.sessions.geophys_source import (
        compile_geophys_usd_position_drive_receipt,
        inspect_usd_position_drive_model,
    )
    from task_env.runtime.sessions.leaf_control import (
        GeoPhysUsdPositionDriveReceiptV1, GeoPhysUsdPositionDriveV1,
    )
    from task_env.diagnostics.tasks.f05_source_control_support import lower_public_model

    input_v1 = build_native_input("menagerie-panda")
    source = input_v1.runtime_source
    imported, model, _bridge, _report = lower_public_model(source)
    actual_receipt = compile_geophys_usd_position_drive_receipt(
        source, imported, model, input_v1.execution,
        provider_build_identity=input_v1.host_model_producer_identity.actual_provider_build_identity,
        provenance_kind='native_runtime',
        host_model_producer_identity=input_v1.host_model_producer_identity,
    )
    actual_rows = inspect_usd_position_drive_model(source, imported, model)["rows"]
    data = model.joint_data
    actual_oracle = []
    ir_joints = {
        str(joint.dynamics.get("source_name")): joint
        for joint in imported.ir.joints if joint.dynamics.get("source_name")
    }
    for row in actual_rows:
        drive = ir_joints[row["native_joint"]].dynamics.to_dict()["usd_drives"][0]
        angular = drive["axis"] == "angular"
        coordinate_scale = np.pi / 180.0 if angular else float(imported.ir.metadata.length_unit_m)
        effort_scale = float(imported.ir.metadata.mass_unit_kg) * float(imported.ir.metadata.length_unit_m) ** (2 if angular else 1)
        gain_scale = effort_scale / coordinate_scale
        q_index = int(data["name_to_joint"][row["native_joint"]])
        actuator_index = int(data["name_to_actuator"][row["native_actuator"]])
        q0 = float(np.asarray(data["qpos0"])[np.asarray(data["jnt_qposadr"])[q_index]])
        k = float(drive["stiffness"]) * gain_scale
        d = float(drive["damping"]) * gain_scale
        scale = k * float(drive["target_position"]) * coordinate_scale
        scale += d * float(drive["target_velocity"]) * coordinate_scale
        cap = None if drive["max_force"] is None else float(drive["max_force"]) * effort_scale
        assert row["position_unit"] == ("radian" if angular else "meter")
        assert np.isclose(-np.asarray(data["actuator_biasprm"])[actuator_index, 1], k, rtol=1e-5, atol=1e-5)
        assert np.isclose(-np.asarray(data["actuator_biasprm"])[actuator_index, 2], d, rtol=1e-5, atol=1e-5)
        assert np.isclose(np.asarray(data["actuator_biasprm"])[actuator_index, 0], scale, rtol=1e-5, atol=1e-5)
        assert np.isclose(row["joint_q0"], q0, rtol=0.0, atol=1e-12)
        if cap is not None:
            assert np.allclose(row["compiled_force_range"], (-cap, cap), rtol=1e-5, atol=1e-5)
        actual_oracle.append({
            "joint": row["canonical_joint"], "unit": row["position_unit"],
            "coordinate_scale": coordinate_scale, "effort_scale": effort_scale,
            "stiffness_compiled": k, "damping_compiled": d,
            "source_bias0": scale, "q0": q0, "force_cap": cap,
        })

    # A separate numeric vector spans nonzero authored rest targets/velocity,
    # affine gain, coordinate offset, q0, two length/mass systems, and both
    # angular and prismatic coordinates. It checks the receipt consumer's
    # ctrl mapping against the public law f = gain*ctrl+b0-k*q-d*qd.
    canonical = [f"panda-main/joint{i}" for i in range(1, 8)] + [
        "panda-main/finger_joint1", "panda-main/finger_joint2",
    ]
    rows = []
    oracle_units = []
    for i, semantic in enumerate(canonical):
        angular = i < 7
        length_m, mass_kg = ((0.01, 0.25) if i % 2 == 0 else (0.4, 3.0))
        coordinate_scale = np.pi / 180.0 if angular else length_m
        effort_scale = mass_kg * length_m ** (2 if angular else 1)
        gain_scale = effort_scale / coordinate_scale
        authored_k, authored_d = 43.0 + i, 5.0 + i
        stiffness, damping = authored_k * gain_scale, authored_d * gain_scale
        authored_rest = 0.17 if angular else 0.012
        authored_rest_velocity = -0.09 if angular else 0.004
        bias0 = stiffness * authored_rest * coordinate_scale + damping * authored_rest_velocity * coordinate_scale
        name = f"usd_joint_{i}"
        dof_index = (4 * i) % 9
        actuator_index = (5 * i + 1) % 9
        finger = semantic.endswith(("finger_joint1", "finger_joint2"))
        rows.append(GeoPhysUsdPositionDriveV1(
            "geophys-usd-position-drive-v1", JointReference("panda-main", semantic.split("/", 1)[1]),
            name, dof_index, f"actuator_{i}", actuator_index,
            "meter" if finger else "radian", 0.0 if finger else -4.0, 0.04 if finger else 4.0,
            1.25 + i, bias0, stiffness, damping,
            authored_rest_velocity * coordinate_scale,
            0.0015 if finger else 0.013, 0.02 if finger else 0.006,
            True, -1e9, 1e9, True, -1000.0 - i, 1000.0 + i,
        ))
        oracle_units.append({
            "joint": semantic, "length_unit_m": length_m, "mass_unit_kg": mass_kg,
            "coordinate_scale": coordinate_scale, "effort_scale": effort_scale,
            "gain_scale": gain_scale, "authored_rest_target": authored_rest,
            "authored_rest_velocity": authored_rest_velocity,
            "coordinate_offset": rows[-1].coordinate_offset, "joint_q0": rows[-1].joint_q0,
        })
    execution = input_v1.execution
    receipt = GeoPhysUsdPositionDriveReceiptV1(
        "geophys-usd-position-drive-receipt-v1", "synthetic_fixture",
        source.scene_definition.identity_hash, source.source_closure_digest,
        actual_receipt.public_model_identity_sha256, execution.identity_hash,
        actual_receipt.provider_build_identity, execution.physics_profile,
        execution.physics_backend, execution.physics_device, execution.determinism_mode,
        0.002, 5, "panda-main/position-servo-v1", 9, tuple(reversed(rows)),
    )
    arm_targets = {f"panda-main/joint{i}": 0.11 + 0.01 * i for i in range(1, 8)}
    targets = receipt.commands(arm_targets, 0.06)
    assert tuple(index for index, _name, _value in targets) == tuple(range(9))
    assert [value for _index, name, value in targets if name in {"usd_joint_7", "usd_joint_8"}] == [0.03, 0.03]
    actual_controls = receipt.control_inputs(targets)
    target_by_name = {name: value for _index, name, value in targets}
    row_by_name = {row.native_dof_name: row for row in rows}
    expected_controls = []
    for row in rows:
        q_target = target_by_name[row.native_dof_name] + row.coordinate_offset
        ctrl = (row.stiffness * q_target + row.damping * row.desired_velocity - row.bias0) / row.gain
        public_force = row.gain * ctrl + row.bias0 - row.stiffness * q_target - row.damping * row.desired_velocity
        assert abs(public_force) <= 1e-10 * max(1.0, abs(row.bias0), abs(row.stiffness * q_target))
        hold_ctrl = (row.stiffness * row.joint_q0 - row.bias0) / row.gain
        hold_force = row.gain * hold_ctrl + row.bias0 - row.stiffness * row.joint_q0
        assert abs(hold_force) <= 1e-10 * max(1.0, abs(row.bias0))
        expected_controls.append((row.native_actuator_index, row.native_actuator_name, ctrl))
    assert actual_controls == tuple(sorted(expected_controls))
    with pytest.raises(ValueError, match="model-bound receipt"):
        bad_targets = list(targets)
        index, name, _value = bad_targets[0]
        bad_targets[0] = (index, name, float("nan"))
        receipt.control_inputs(tuple(bad_targets))

    def proxy_import_with(drive_change):
        proxy_joints = []
        for joint in imported.ir.joints:
            native_name = joint.dynamics.get("source_name")
            dynamics = joint.dynamics.to_dict()
            if native_name == "joint1":
                drive = dict(dynamics["usd_drives"][0])
                drive_change(drive)
                dynamics["usd_drives"] = (drive,)
            proxy_dynamics = SimpleNamespace(
                get=lambda key, default=None, d=dynamics: d.get(key, default),
                to_dict=lambda d=dynamics: d,
            )
            proxy_joints.append(SimpleNamespace(
                dynamics=proxy_dynamics, type=joint.type, limits=joint.limits,
            ))
        return SimpleNamespace(ir=SimpleNamespace(
            metadata=imported.ir.metadata, joints=tuple(proxy_joints),
        ))

    with pytest.raises(ValueError, match="does not admit 'acceleration' drive semantics"):
        inspect_usd_position_drive_model(
            source, proxy_import_with(lambda drive: drive.__setitem__("type", "acceleration")), model,
        )
    with pytest.raises(ValueError, match="stiffness unit conversion"):
        inspect_usd_position_drive_model(
            source, proxy_import_with(lambda drive: drive.__setitem__("stiffness", float("nan"))), model,
        )
    output_root = tmp_path
    (output_root / "numeric_oracle.json").write_text(json.dumps({
        "schema_version": "f05-geophys-drive-numeric-oracle-v1",
        "actual_menagerie_public_model": actual_oracle,
        "independent_numeric_vectors": oracle_units,
        "custom_receipt_identity_sha256": receipt.identity_sha256,
        "native_index_order": [name for _index, name, _value in targets],
        "actuator_order": [name for _index, name, _value in actual_controls],
        "control_inputs": [list(row) for row in actual_controls],
        "source_max_force_is_receipt_metadata_not_core_force_limit_ack": True,
        "unsupported_semantics_rejections": ["acceleration", "non-finite authored stiffness"],
    }, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def test_f05_native_materialization_requires_exact_candidate_admission():
    from task_env.runtime.sessions.api import materialize

    candidate = build_native_input('menagerie-panda')
    assert candidate.runtime_source.scene_source.locally_validated is True
    assert candidate.runtime_source.scene_source.source_verified is False
    with pytest.raises(ValueError, match='F05 GeoPhys native profile requires its exact versioned source admission input'):
        materialize(
            candidate.artifact, candidate.execution, source=candidate.runtime_source,
        )
