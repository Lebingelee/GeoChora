"""Bound GeoPhys USD provider adapter for the F05 Menagerie native cell.

This module implements only the lowest NativeRuntimeIOV1 seam. Core retains
construction, admission, reset ownership, control policy, typed publication,
recording and episode lifecycle.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from ...environment import EpisodePhysicsState, SnapshotRequest
from ...runtime.bootstrap import GeoPhysRuntimeBoundary
from .free_joint_state import PublicRigidBodyReadbackV1
from .native_io import (
    NativeAdvanceReceiptV1,
    NativePositionWriteAckV1,
    NativeResetWriteReceiptV1,
    NativeRuntimeIOMetadataV1,
    NativeRuntimeReadbackV1,
)


def create_f05_geophys_native_io(*, artifact, execution, source, input_v1):
    """Construct the exact admitted F05 adapter; all imports stay in the worker."""
    return F05GeoPhysUsdNativeIO(
        artifact=artifact, execution=execution, source=source, input_v1=input_v1,
    )


class F05GeoPhysUsdNativeIO:
    """One source lease and one public GeoPhys host runtime for F05."""

    execution_provenance_kind = 'native_runtime'

    def __init__(self, *, artifact, execution, source, input_v1):
        from ...tasks.position_candidate.builder import F05NativePositionCandidateInputV1

        if type(input_v1) is not F05NativePositionCandidateInputV1:
            raise TypeError('F05 GeoPhys adapter requires the exact native candidate input')
        input_v1.validate()
        if (artifact is not input_v1.artifact or source is not input_v1.runtime_source
                or execution.identity_hash != input_v1.execution.identity_hash):
            raise ValueError('F05 GeoPhys adapter inputs differ from the admitted candidate')
        if __import__('os').environ.get('GEOPHYS_TAICHI_BACKEND') != 'taichi-forge':
            raise ValueError('F05 native worker requires the frozen taichi-forge backend gate')

        self.artifact, self.execution, self.source, self.input_v1 = artifact, execution, source, input_v1
        self._composer = None
        self._boundary = None
        self._runtime = None
        self._closed = False
        self._native_step_count = 0
        self._last_control_values = None
        self._metadata = None
        try:
            import os
            self.native_run_id = os.environ.get('F05_NATIVE_RUN_ID')
            self.native_run_plan_sha256 = os.environ.get('F05_NATIVE_RUN_PLAN_SHA256')
            self.runtime_environment_sha256 = os.environ.get('F05_NATIVE_RUNTIME_ENVIRONMENT_SHA256')
            if (not self.native_run_id or not self._is_sha256(self.native_run_plan_sha256)
                    or not self._is_sha256(self.runtime_environment_sha256)):
                raise ValueError('F05 native adapter requires a frozen run-plan/runtime identity before backend init')
            input_v1.host_model_producer_identity.validate_current_tree()
            from geophys import init_taichi
            init_taichi(arch='cpu', cpu_max_num_threads=4)

            from scene import import_scene_source
            from simulation import assemble_mjcf_articulated_runtime
            from solvers.rigid import RigidGroundConfig
            from ...runtime.sessions.geophys_source import (
                GeoPhysSourceComposer,
                compile_geophys_usd_position_drive_receipt,
            )

            self._composer = GeoPhysSourceComposer(source)
            public_source, _bridge_id = self._composer.build_scene_source(None, ())
            imported = import_scene_source(public_source, cache=False)
            model = self._composer.build_scene_model(imported, None)
            self.import_mapping_report = self._composer.usd_mapping_report
            provider_build = input_v1.host_model_producer_identity.actual_provider_build_identity
            receipt = compile_geophys_usd_position_drive_receipt(
                source, imported, model, execution,
                provider_build_identity=provider_build,
                provenance_kind='native_runtime',
                host_model_producer_identity=input_v1.host_model_producer_identity,
            )
            self.drive_receipt = receipt
            self._bind_public_model(imported, model)

            data = model.joint_data
            self._initial_state = self._initial_state_from_public_model(data)
            runtime = assemble_mjcf_articulated_runtime(
                imported,
                scene_model=model,
                apply_mjcf_options=True,
                default_dt=float(artifact.timebase.physics_dt),
                default_gravity=(0.0, 0.0, -9.81),
                default_integrator='implicitfast',
                solver_kwargs={
                    'dt': float(artifact.timebase.physics_dt),
                    'gravity': (0.0, 0.0, -9.81),
                    'integrator': 'implicitfast',
                    'ground': RigidGroundConfig(
                        height=-1.0, visible=False, contact_margin=0.0,
                    ),
                    'enable_ground_contact': False,
                    'enable_domain_boundary_contact': False,
                    'rigid_solver_backend': 'row_pgs',
                    'prewarm_kernels': False,
                },
                create_simulator=True,
                create_render_source=False,
            )
            self._runtime = runtime
            self._boundary = GeoPhysRuntimeBoundary(
                physics=runtime.solver,
                scheduler=runtime.simulator,
                physics_dt=float(artifact.timebase.physics_dt),
                ctrl_range=data['actuator_ctrlrange'],
                initial_state=self._initial_state,
            )
            self._metadata = self._build_metadata()
            self._native_step_counter_baseline = self._public_step_index()
            if self._native_step_counter_baseline != 0:
                raise RuntimeError('GeoPhys public native-step counter shows hidden bootstrap physics')
        except BaseException as primary:
            if self._boundary is not None:
                try:
                    self._boundary.close()
                except BaseException as cleanup_error:
                    primary.add_note(
                        'GeoPhys boundary cleanup after native-adapter construction also failed: '
                        f'{type(cleanup_error).__name__}: {cleanup_error}'
                    )
            try:
                self._release_lease_once()
            except BaseException as cleanup_error:
                primary.add_note(
                    'USD snapshot lease cleanup after native-adapter construction also failed: '
                    f'{type(cleanup_error).__name__}: {cleanup_error}'
                )
            raise

    def _bind_public_model(self, imported, model):
        data = model.joint_data
        joint_names = data.get('name_to_joint')
        actuator_names = data.get('name_to_actuator')
        qpos_addresses = np.asarray(data.get('jnt_qposadr'), dtype=np.int64).reshape(-1)
        dof_addresses = np.asarray(data.get('jnt_dofadr'), dtype=np.int64).reshape(-1)
        if not isinstance(joint_names, dict) or not isinstance(actuator_names, dict):
            raise ValueError('public GeoPhys model is missing named Joint/Actuator metadata')
        self._joint_addresses = {}
        for canonical, native in self.source.joints.items():
            if native not in joint_names:
                raise ValueError(f'public GeoPhys model lacks required named Joint {native!r}')
            index = int(joint_names[native])
            if index < 0 or index >= len(qpos_addresses) or index >= len(dof_addresses):
                raise ValueError(f'public GeoPhys Joint address is invalid for {native!r}')
            self._joint_addresses[canonical] = (
                int(qpos_addresses[index]), int(dof_addresses[index]), index,
            )
        ir_free = [
            joint for joint in imported.ir.joints
            if joint.type == 'free' and joint.source_ref is not None
            and joint.source_ref.element_path == '/F04Scene/free_cube'
        ]
        if len(ir_free) != 1:
            raise ValueError('public USD IR must expose exactly one frozen free-cube root Joint')
        free_native_name = str(ir_free[0].dynamics.get('source_name', ''))
        if free_native_name not in joint_names:
            raise ValueError('public GeoPhys model lacks the resolved implicit free-root Joint')
        free_index = int(joint_names[free_native_name])
        self._free_addresses = {
            semantic: (
                int(qpos_addresses[free_index]), int(dof_addresses[free_index]), free_index,
            ) for semantic in self.source.free_joints
        }

        semantic_body_ids = data.get('semantic_body_ids')
        if not isinstance(semantic_body_ids, dict):
            raise ValueError('public GeoPhys model lacks its imported semantic body mapping')
        path_to_ir_id = {}
        for body in imported.ir.bodies:
            path = None if body.source_ref is None else body.source_ref.element_path
            if path is not None:
                if path in path_to_ir_id:
                    raise ValueError(f'ambiguous public USD body source path {path!r}')
                path_to_ir_id[path] = body.body_id
        self._body_addresses = {}
        for semantic, path in self.source.bodies.items():
            body_ir_id = path_to_ir_id.get(path)
            if body_ir_id is None or body_ir_id not in semantic_body_ids:
                raise ValueError(f'public USD body mapping is incomplete for {semantic!r}')
            self._body_addresses[semantic] = int(semantic_body_ids[body_ir_id])
        self._free_body_addresses = {
            semantic: self._body_addresses[semantic]
            for semantic in self.source.free_joints
            if semantic in self._body_addresses
        }
        if set(self._free_body_addresses) != set(self.source.free_joints):
            raise ValueError('free-body readback lacks the exact canonical public Body mapping')
        if self.source.frames:
            raise ValueError('frozen F05 route does not admit unbound native Site Frames')
        if len(self._joint_addresses) != 9 or len(self._body_addresses) != len(self.source.bodies):
            raise ValueError('public model mapping does not cover the complete frozen Panda/Frame source')

        actuator_by_name = dict(actuator_names)
        self._actuator_indices = {}
        for drive in self.drive_receipt.drives:
            if drive.native_actuator_name not in actuator_by_name:
                raise ValueError(f'public model lacks receipt Actuator {drive.native_actuator_name!r}')
            actual_index = int(actuator_by_name[drive.native_actuator_name])
            if actual_index != drive.native_actuator_index:
                raise ValueError('public model Actuator order changed after receipt compilation')
            self._actuator_indices[drive.native_actuator_name] = actual_index
        if len(self._actuator_indices) != 9:
            raise ValueError('public model does not expose nine unique Panda Actuator channels')
        self._body_com_offsets = np.asarray(data['body_ipos'], dtype=np.float64)

    @staticmethod
    def _initial_state_from_public_model(data):
        """Build a reset seed from public model arrays, defaulting absent controls to zero."""
        n_actuators = int(data['n_actuators'])
        return EpisodePhysicsState(
            qpos=np.asarray(data['initial_qpos'], dtype=np.float32).copy(),
            qvel=np.asarray(data['initial_qvel'], dtype=np.float32).copy(),
            qacc=np.zeros(int(data['n_dof']), dtype=np.float32),
            ctrl=np.asarray(data.get('initial_ctrl', np.zeros(n_actuators)), dtype=np.float32).copy(),
            act=np.asarray(data.get('initial_act', np.zeros(n_actuators)), dtype=np.float32).copy(),
        )

    @staticmethod
    def _is_sha256(value):
        return (isinstance(value, str) and len(value) == 64
                and all(char in '0123456789abcdef' for char in value))

    def _public_step_index(self):
        solver = None if self._runtime is None else self._runtime.solver
        status_reader = None if solver is None else getattr(solver, 'actuator_force_sample_status', None)
        if not callable(status_reader):
            raise RuntimeError('GeoPhys public actuator-force status lacks its native-step cross-check')
        status = status_reader()
        value = getattr(status, 'native_step_index', None)
        if type(value) is not int or value < 0:
            raise RuntimeError('GeoPhys public actuator-force status has an invalid native-step index')
        return value

    def _require_public_step_index(self, expected):
        actual = self._public_step_index()
        if actual != expected:
            raise RuntimeError(
                f'GeoPhys public native-step index mismatch: expected {expected}, observed {actual}'
            )
        return actual

    def _build_metadata(self):
        rows = tuple(sorted(self.drive_receipt.drives, key=lambda row: row.native_dof_index))
        return NativeRuntimeIOMetadataV1(
            'native-runtime-io-metadata-v1', self.source.source_id,
            self.source.source_closure_digest, self.source.scene_definition.identity_hash,
            self.artifact.identity_hash, self.execution.identity_hash,
            'geophys', self.input_v1.host_model_producer_identity.actual_provider_build_identity,
            'cpu', 'cpu', 'best_effort', self.artifact.timebase.physics_dt,
            self.artifact.timebase.control_substeps,
            tuple(row.native_dof_name for row in rows),
            {row.native_dof_name: (row.lower_limit, row.upper_limit) for row in rows},
            self.input_v1.host_model_producer_identity.identity_sha256,
        )

    def metadata(self):
        if self._metadata is None:
            raise RuntimeError('F05 native metadata is unavailable before public model binding')
        return self._metadata

    def bootstrap_receipt(self):
        """Return independently serializable facts from the live public model binding."""
        if self._boundary is None:
            raise RuntimeError('F05 GeoPhys bootstrap receipt requires an open native runtime')
        self._require_public_step_index(self._native_step_counter_baseline + self._native_step_count)
        return {
            'schema_version': 'f05-geophys-public-bootstrap-receipt-v1',
            'source_id': self.source.source_id,
            'source_closure_sha256': self.source.source_closure_digest,
            'scene_identity_sha256': self.source.scene_definition.identity_hash,
            'task_artifact_identity_sha256': self.artifact.identity_hash,
            'execution_identity_sha256': self.execution.identity_hash,
            'requested_target_build_identity': self.input_v1.host_model_producer_identity.requested_target_build_identity,
            'actual_execution_build_identity': self.metadata().provider_build_identity,
            'native_run_id': self.native_run_id,
            'native_run_plan_sha256': self.native_run_plan_sha256,
            'runtime_environment_sha256': self.runtime_environment_sha256,
            'public_native_step_counter': 'actuator_force_sample_status.native_step_index',
            'native_step_counter_baseline': self._native_step_counter_baseline,
            'native_step_index_at_reset': self._public_step_index(),
            'host_model_producer_identity_sha256': self.input_v1.host_model_producer_identity.identity_sha256,
            'public_model_identity_sha256': self.drive_receipt.public_model_identity_sha256,
            'drive_receipt_identity_sha256': self.drive_receipt.identity_sha256,
            'public_import_mapping_report': self.import_mapping_report,
            'named_joint_addresses': {
                name: {'qpos_address': values[0], 'dof_address': values[1],
                       'public_joint_index': values[2]}
                for name, values in self._joint_addresses.items()
            },
            'named_free_joint_addresses': {
                name: {'qpos_address': values[0], 'dof_address': values[1],
                       'public_joint_index': values[2]}
                for name, values in self._free_addresses.items()
            },
            'canonical_body_indices': dict(self._body_addresses),
            'free_body_com_offset_body_m': {
                name: self._body_com_offsets[index].astype(float).tolist()
                for name, index in self._free_body_addresses.items()
            },
            'execution': {
                'backend': 'cpu', 'device': 'cpu', 'rigid_solver_backend': 'row_pgs',
                'integrator': 'implicitfast', 'physics_dt_s': self.artifact.timebase.physics_dt,
                'control_substeps': self.artifact.timebase.control_substeps,
                'cpu_max_num_threads': 4,
                'prewarm': False, 'renderer': False,
            },
        }

    def write_reset(self, sample, position_targets):
        self.source.assert_fresh()
        controls = self.drive_receipt.control_inputs(tuple(position_targets))
        qpos = np.array(self._initial_state.qpos, copy=True)
        qvel = np.zeros_like(self._initial_state.qvel)
        qacc = np.zeros_like(self._initial_state.qacc)
        ctrl = np.array(self._initial_state.ctrl, copy=True)
        act = np.zeros_like(self._initial_state.act)
        for semantic, value in sample.joint_position.items():
            qpos[self._joint_addresses[semantic][0]] = np.float32(value)
        for semantic, pose in sample.poses_world.items():
            qadr = self._free_addresses[semantic][0]
            qpos[qadr:qadr + 7] = np.asarray(
                (*pose.position, *pose.quaternion_wxyz), dtype=np.float32,
            )
        for actuator_index, _name, value in controls:
            ctrl[actuator_index] = np.float32(value)
        self._boundary.apply_reset_state(EpisodePhysicsState(
            qpos=qpos, qvel=qvel, qacc=qacc, ctrl=ctrl, act=act,
        ))
        actual_ctrl = np.asarray(self._runtime.solver.read_ctrl(), dtype=np.float32)
        if (actual_ctrl.shape != ctrl.shape or not np.isfinite(actual_ctrl).all()
                or not np.array_equal(actual_ctrl, ctrl)):
            raise RuntimeError('GeoPhys public reset ctrl readback differs from the frozen affine hold state')
        self._native_step_count = 0
        self._require_public_step_index(self._native_step_counter_baseline)
        self._last_control_values = actual_ctrl.copy()
        return NativeResetWriteReceiptV1(
            'native-reset-write-receipt-v1', sample.sample_id,
            tuple(sorted(self.source.joints)), tuple(sorted(self.source.free_joints)),
            tuple(name for _index, name, _value in position_targets), True, False,
        )

    @staticmethod
    def _rotation_wxyz(q):
        w, x, y, z = (float(item) for item in q)
        return np.asarray((
            (1 - 2*(y*y + z*z), 2*(x*y - z*w), 2*(x*z + y*w)),
            (2*(x*y + z*w), 1 - 2*(x*x + z*z), 2*(y*z - x*w)),
            (2*(x*z - y*w), 2*(y*z + x*w), 1 - 2*(x*x + y*y)),
        ), dtype=np.float64)

    def read_state(self):
        if self._boundary is None or self._runtime is None:
            raise RuntimeError('F05 native runtime is closed')
        self.source.assert_fresh()
        self._require_public_step_index(self._native_step_counter_baseline + self._native_step_count)
        snapshot = self._boundary.read_snapshot(SnapshotRequest(
            qacc=False, ctrl=False, body_pose=True, site_pose=False,
            simulation_time=True,
        ))
        solver = self._runtime.solver
        qpos = np.asarray(solver.read_qpos(), dtype=np.float64)
        qvel = np.asarray(solver.read_qvel(), dtype=np.float64)
        linear = np.asarray(solver.read_linear_velocities(), dtype=np.float64)
        angular = np.asarray(solver.read_angular_velocities(), dtype=np.float64)
        positions = np.asarray(snapshot.body_xpos, dtype=np.float64)
        orientations = np.asarray(snapshot.body_xquat, dtype=np.float64)
        joint_positions = {
            semantic: float(qpos[qadr])
            for semantic, (qadr, _dadr, _index) in self._joint_addresses.items()
        }
        joint_velocities = {
            semantic: float(qvel[dadr])
            for semantic, (_qadr, dadr, _index) in self._joint_addresses.items()
        }
        frame_poses = {}
        for semantic, index in self._body_addresses.items():
            frame_poses[semantic] = self._pose(positions[index], orientations[index])
        free_readback = {}
        for semantic, index in self._free_body_addresses.items():
            origin_position = np.asarray(positions[index], dtype=np.float64)
            quaternion = np.asarray(orientations[index], dtype=np.float64)
            omega_world = np.asarray(angular[index], dtype=np.float64)
            com_offset_body = np.asarray(self._body_com_offsets[index], dtype=np.float64)
            offset_world = self._rotation_wxyz(quaternion) @ com_offset_body
            linear_origin_world = np.asarray(linear[index], dtype=np.float64)
            linear_com_world = linear_origin_world + np.cross(omega_world, offset_world)
            frame_ref = self.artifact.legacy_frame_bindings[semantic]
            free_readback[semantic] = PublicRigidBodyReadbackV1(
                'public-rigid-body-readback-v1', frame_ref,
                tuple(float(item) for item in origin_position),
                tuple(float(item) for item in quaternion),
                tuple(float(item) for item in com_offset_body),
                tuple(float(item) for item in linear_com_world),
                tuple(float(item) for item in omega_world),
                'world', 'center_of_mass',
            )
        return NativeRuntimeReadbackV1(
            'native-runtime-readback-v1', joint_positions, joint_velocities,
            frame_poses, free_readback, float(snapshot.simulation_time),
        )

    @staticmethod
    def _pose(position, quaternion):
        from ...artifacts import PoseWorld
        p = tuple(float(item) for item in np.asarray(position).reshape(3))
        q = tuple(float(item) for item in np.asarray(quaternion).reshape(4))
        norm = math.sqrt(sum(value * value for value in q))
        if not math.isfinite(norm) or norm < 1e-12:
            raise ValueError('GeoPhys public body orientation is invalid')
        return PoseWorld(p, tuple(value / norm for value in q))

    def write_position_targets(self, target_identity_sha256, targets):
        self.source.assert_fresh()
        self._require_public_step_index(self._native_step_counter_baseline + self._native_step_count)
        controls = self.drive_receipt.control_inputs(tuple(targets))
        ctrl = np.asarray(self._runtime.solver.read_ctrl(), dtype=np.float32).copy()
        for actuator_index, _name, value in controls:
            ctrl[actuator_index] = np.float32(value)
        self._runtime.solver.write_ctrl(ctrl)
        actual_ctrl = np.asarray(self._runtime.solver.read_ctrl(), dtype=np.float32)
        if actual_ctrl.shape != ctrl.shape or not np.isfinite(actual_ctrl).all():
            raise ValueError('GeoPhys public ctrl readback has an invalid shape or non-finite value')
        drives = {row.native_dof_name: row for row in self.drive_receipt.drives}
        ack_names = tuple(name for _index, name, _value in targets)
        ack_values = []
        for _index, name, _target in targets:
            drive = drives[name]
            if drive.stiffness <= 0.0:
                raise ValueError(f'GeoPhys Position drive {name!r} has no invertible stiffness')
            native_ctrl = float(actual_ctrl[drive.native_actuator_index])
            expected_ctrl = float(next(value for i, n, value in controls if n == drive.native_actuator_name))
            tolerance = max(1e-8, abs(float(np.spacing(np.float32(expected_ctrl)))) * 1.5)
            if abs(native_ctrl - expected_ctrl) > tolerance:
                raise ValueError(f'GeoPhys public ctrl readback differs from the affine Position command for {name!r}')
            actual_target = (
                (drive.gain * native_ctrl + drive.bias0
                 - drive.damping * drive.desired_velocity) / drive.stiffness
                - drive.coordinate_offset
            )
            ack_values.append(float(actual_target))
        self._last_control_values = actual_ctrl.copy()
        return NativePositionWriteAckV1(
            'native-position-write-ack-v1', target_identity_sha256,
            ack_names, tuple(ack_values), False, len(ack_names),
        )

    def advance(self):
        if self._boundary is None:
            raise RuntimeError('F05 native runtime is closed')
        self.source.assert_fresh()
        previous_index = self._native_step_counter_baseline + self._native_step_count
        self._require_public_step_index(previous_index)
        self._boundary.step(substeps=1)
        self._require_public_step_index(previous_index + 1)
        self._native_step_count += 1
        dt = float(self.artifact.timebase.physics_dt)
        return NativeAdvanceReceiptV1(
            'native-advance-receipt-v1', 1, self._native_step_count,
            self._native_step_count * dt,
        )

    def _release_lease_once(self):
        composer, self._composer = self._composer, None
        if composer is not None:
            composer.close()

    def close(self):
        if self._closed:
            return
        self._closed = True
        primary = None
        try:
            if self._boundary is not None:
                self._boundary.close()
        except BaseException as error:
            primary = error
        finally:
            try:
                self._release_lease_once()
            except BaseException as cleanup_error:
                if primary is None:
                    primary = cleanup_error
                else:
                    primary.add_note(
                        'USD snapshot lease cleanup after GeoPhys boundary close also failed: '
                        f'{type(cleanup_error).__name__}: {cleanup_error}'
                    )
        if primary is not None:
            raise primary


__all__ = ['F05GeoPhysUsdNativeIO', 'create_f05_geophys_native_io']
