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
    candidate, _setup = build_native_input('menagerie-panda')
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

    candidate, _setup = build_native_input('menagerie-panda')
    wrong_execution = replace(candidate.execution, physics_device='cuda:0')
    rejected = replace(candidate, execution=wrong_execution)
    with pytest.raises(ValueError, match='exact GeoPhys CPU native execution identity'):
        rejected.validate()
    with pytest.raises(ValueError, match='restricted to the frozen Menagerie USD cell'):
        build_native_input('official-panda')


def test_f05_native_versioned_input_reaches_shared_factory_without_native_materialization(monkeypatch):
    from types import SimpleNamespace
    from task_env.registry import make_env
    from task_env.tasks.position_candidate import builder

    candidate, _setup = build_native_input('menagerie-panda')
    marker = object()
    captured = []

    def shared_factory(input_v1, *, horizon, environment_type):
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
