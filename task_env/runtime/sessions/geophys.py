"""Private GeoPhys projection using the existing scalar bootstrap and boundary."""
from copy import deepcopy
import numpy as np

from ...environment import EpisodePhysicsState, SnapshotRequest
from ..bootstrap import bootstrap_task_runtime
from .common import _SessionValues, pose
from .geophys_source import GeoPhysSourceComposer


class _GeoPhysSession(_SessionValues):
    def __init__(self, artifact, source):
        self._initialize_values(artifact, source, 'geophys')
        runtime = bootstrap_task_runtime(
            config=source.config, composition=source.composition, scene=source.scene,
            agents=source.agents, objects=source.objects,
            scene_composer=GeoPhysSourceComposer(
                source.scene_source,
                scene_definition=source.scene_definition,
                source_closure_digest=(
                    source.source_closure_digest
                    if source.scene_definition is not None else None
                ),
                execution_source_receipt=source.execution_source_receipt,
            ),
            create_render_source=False,
        )
        self._boundary = runtime.boundary
        compiled = runtime.compiled_scene
        names, data = compiled.references.names, compiled.scene_model.joint_data
        self._body_parentid = np.asarray(data['body_parentid'], dtype=np.int32).reshape(-1)
        self._body_jntnum = np.asarray(data['body_jntnum'], dtype=np.int32).reshape(-1)
        self._joint_addresses = {
            semantic: (int(data['jnt_qposadr'][names.joints[native]]),
                       int(data['jnt_dofadr'][names.joints[native]]))
            for semantic, native in source.joints.items()
        }
        self._free_addresses = {semantic: (int(data['jnt_qposadr'][names.joints[native]]),
                                           int(data['jnt_dofadr'][names.joints[native]]))
                                for semantic, native in source.free_joints.items()}
        self._bodies = {semantic: names.bodies[native] for semantic, native in source.bodies.items()}
        self._frames = {semantic: names.sites[native] for semantic, native in source.frames.items()}
        self._fixture_bodies = {
            name: int(names.bodies[source.bodies[name]]) for name in source.fixture_bodies
        }
        self._target_actuators = {semantic: names.actuators[native] for semantic, native in source.joint_targets.items()}
        self._open_actuators = tuple(names.actuators[name] for name in source.open_actuators)
        self._ctrl_range = data['actuator_ctrlrange']
        self._mixed_actuator_plan = source.mixed_actuator_plan
        self._mixed_controller_identity = None
        self._mixed_pending_target = None
        self._mixed_consumed_boundaries = set()
        self._mixed_fault = None
        self._inner_interval_active = False
        self._native_steps = 0
        self._last_close_receipt = None
        self._torque_actuators = {}
        self._position_actuators = {}
        self._mixed_channel_actuators = {}
        self._mixed_channel_records = {}
        self._last_reset_readback_v1 = None
        if self._mixed_actuator_plan is not None:
            self._initialize_mixed_actuator(source, names, data)
        self._initial = runtime.boundary.initial_state
        self._reset_force_measurement = None
        self._last_reset_force_sequence = 0
        self._force_source_generation = None
        self._last_actuator_force_measurement = None
        self._last_typed_force_publication = None

    def _initialize_mixed_actuator(self, source, names, data):
        """Bind every declared mixed channel to the compiled named GeoPhys model."""
        from ...controllers.canonical.contracts import MixedActuatorPlanV1

        plan = self._mixed_actuator_plan
        if type(plan) is not MixedActuatorPlanV1:
            raise TypeError('GeoPhys mixed actuation requires MixedActuatorPlanV1')
        plan.validate()
        if (plan.task_artifact_hash != self._artifact.identity_hash
                or plan.source_id != source.scene_source.source_id
                or plan.source_closure_digest != source.source_closure_digest):
            raise ValueError('GeoPhys mixed actuator plan differs from its Artifact/source closure')
        if int(data.get('n_actuators', 0)) != len(plan.channels):
            raise ValueError('GeoPhys compiled actuator count differs from the complete mixed plan')
        if set(names.actuators) != {item.actuator_name for item in plan.channels}:
            raise ValueError('GeoPhys compiled actuator names differ from the complete mixed plan')
        torque_names = set(source.torque_actuators.values())
        position_names = set(source.position_actuators.values())
        if torque_names & position_names or torque_names | position_names != set(names.actuators):
            raise ValueError('GeoPhys mixed source must bind every actuator exactly once')
        self._torque_actuators = {
            semantic: names.actuators[native]
            for semantic, native in source.torque_actuators.items()
        }
        self._position_actuators = {
            semantic: names.actuators[native]
            for semantic, native in source.position_actuators.items()
        }
        trntype = np.asarray(data['actuator_trntype'])
        trnid = np.asarray(data['actuator_trnid'])
        limited = np.asarray(data['actuator_ctrllimited'])
        ctrlrange = np.asarray(data['actuator_ctrlrange'])
        joint_types = np.asarray(data['jnt_type'])
        gears = np.asarray(data['actuator_gear'])
        gain_types = np.asarray(data['actuator_gaintype'])
        bias_types = np.asarray(data['actuator_biastype'])
        dynamic_types = np.asarray(data['actuator_dyntype'])
        gain_params = np.asarray(data['actuator_gainprm'])
        bias_params = np.asarray(data['actuator_biasprm'])
        if (trntype.shape[0] < len(plan.channels) or trnid.shape[0] < len(plan.channels)
                or limited.shape[0] < len(plan.channels) or ctrlrange.shape[0] < len(plan.channels)
                or gears.shape[0] < len(plan.channels) or gain_types.shape[0] < len(plan.channels)
                or bias_types.shape[0] < len(plan.channels) or dynamic_types.shape[0] < len(plan.channels)
                or gain_params.shape[0] < len(plan.channels) or bias_params.shape[0] < len(plan.channels)):
            raise ValueError('GeoPhys compiled actuator metadata is incomplete')
        for channel in plan.channels:
            actuator_id = names.actuators.get(channel.actuator_name)
            joint_id = names.joints.get(channel.joint_name)
            if actuator_id is None or joint_id is None:
                raise ValueError(f'GeoPhys mixed channel does not resolve by source name: {channel.semantic_id}')
            actuator_id, joint_id = int(actuator_id), int(joint_id)
            if int(trntype[actuator_id]) != 0 or int(trnid[actuator_id]) != joint_id:
                raise ValueError(f'GeoPhys actuator transmission differs from its named source Joint: {channel.semantic_id}')
            if (int(dynamic_types[actuator_id]) != 0
                    or gears.shape[1] != 6
                    or not np.allclose(gears[actuator_id], (1.0, 0, 0, 0, 0, 0), rtol=0.0, atol=1e-7)):
                raise ValueError(f'GeoPhys mixed actuator must use a unit-gain stateless scalar transmission: {channel.semantic_id}')
            low, high = (float(value) for value in ctrlrange[actuator_id])
            if (not bool(limited[actuator_id])
                    or not np.allclose((low, high), channel.control_range, rtol=0.0, atol=1e-7)):
                raise ValueError(f'GeoPhys actuator range differs from its source-bound plan: {channel.semantic_id}')
            if channel.semantic_id in source.torque_actuators:
                if (channel.drive_mode != 'joint_torque' or channel.unit != 'N*m'
                        or int(joint_types[joint_id]) != 2
                        or int(gain_types[actuator_id]) != 0
                        or int(bias_types[actuator_id]) != 0
                        or float(gain_params[actuator_id, 0]) != 1.0):
                    raise ValueError(f'GeoPhys torque source role differs from its plan: {channel.semantic_id}')
            elif channel.semantic_id in source.position_actuators:
                expected_unit = {2: 'rad', 3: 'm'}.get(int(joint_types[joint_id]))
                if (channel.drive_mode != 'joint_position' or channel.unit != expected_unit
                        or int(gain_types[actuator_id]) != 0
                        or int(bias_types[actuator_id]) != 1
                        or not np.isfinite(gain_params[actuator_id, 0])
                        or float(gain_params[actuator_id, 0]) <= 0.0
                        or float(bias_params[actuator_id, 0]) != 0.0
                        or float(bias_params[actuator_id, 2]) > 0.0
                        or not np.isclose(float(bias_params[actuator_id, 1]),
                                          -float(gain_params[actuator_id, 0]),
                                          rtol=0.0, atol=1e-5)):
                    raise ValueError(f'GeoPhys position source role differs from its plan: {channel.semantic_id}')
            else:
                raise ValueError(f'GeoPhys mixed channel lacks a RuntimeSource role: {channel.semantic_id}')
            self._mixed_channel_actuators[channel.semantic_id] = actuator_id
            self._mixed_channel_records[channel.semantic_id] = {
                'actuator_name': channel.actuator_name,
                'actuator_id': actuator_id,
                'joint_name': channel.joint_name,
                'joint_id': joint_id,
                'drive_mode': channel.drive_mode,
                'unit': channel.unit,
                'control_limited': True,
                'control_range': [low, high],
                'transmission_type': 'joint',
                'gain_type': int(gain_types[actuator_id]),
                'bias_type': int(bias_types[actuator_id]),
                'gainprm': [float(value) for value in gain_params[actuator_id]],
                'biasprm': [float(value) for value in bias_params[actuator_id]],
            }

    @property
    def compiled_layout_receipt(self):
        """Source-bound named layout evidence; native IDs stay in this adapter."""
        if self._mixed_actuator_plan is None:
            raise RuntimeError('compiled mixed actuator layout is unavailable for this session')
        nq = max(
            max((qpos + 1 for qpos, _ in self._joint_addresses.values()), default=0),
            max((qpos + 7 for qpos, _ in self._free_addresses.values()), default=0),
        )
        nv = max(
            max((dof + 1 for _, dof in self._joint_addresses.values()), default=0),
            max((dof + 6 for _, dof in self._free_addresses.values()), default=0),
        )
        return {
            'schema_version': 'compiled-model-layout-v1',
            'provider': 'geophys',
            'dimensions': {
                'nq': int(nq),
                'nv': int(nv),
                'nu': len(self._mixed_channel_actuators),
            },
            'source_id': self._source.scene_source.source_id,
            'source_closure_digest': self._source.source_closure_digest,
            'named_joint_addresses': {
                name: [int(qpos), int(dof)] for name, (qpos, dof) in self._joint_addresses.items()
            },
            'named_free_joint_addresses': {
                name: [int(qpos), int(dof)] for name, (qpos, dof) in self._free_addresses.items()
            },
            'named_torque_actuator_ids': dict(self._torque_actuators),
            'named_position_actuator_ids': dict(self._position_actuators),
            'named_actuator_channels': dict(self._mixed_channel_records),
        }

    @property
    def actuator_force_measurement(self):
        """Last adapter-validated signed sample, bound to this Core boundary."""
        return self._last_actuator_force_measurement

    def reset(self, sample):
        self._validate_sample(sample)
        if self._mixed_actuator_plan is not None:
            self._preflight_mixed_reset(sample)
        self._begin_reset()
        # A failed reset must not leave a previous episode's validated sample
        # visible through this adapter's diagnostic property.
        self._reset_force_measurement = None
        self._last_actuator_force_measurement = None
        self._last_typed_force_publication = None
        initial = self._initial
        positions = np.array(initial.qpos, copy=True)
        velocities = np.zeros_like(initial.qvel)
        targets = np.array(initial.ctrl, copy=True)
        if self._mixed_actuator_plan is not None:
            targets[:] = 0.0
        for name, value in sample.joint_position.items():
            positions[self._joint_addresses[name][0]] = value
            velocities[self._joint_addresses[name][1]] = sample.joint_velocity[name]
        for name, requested in sample.poses_world.items():
            address = self._free_addresses[name][0]
            positions[address:address+7] = (*requested.position, *requested.quaternion_wxyz)
            dof = self._free_addresses[name][1]
            velocities[dof:dof + 6] = sample.free_joint_velocity[name]
        for name, actuator in self._target_actuators.items():
            targets[actuator] = sample.joint_position[name]
        for name, actuator in self._position_actuators.items():
            targets[actuator] = sample.joint_position[name]
        for actuator in self._open_actuators:
            targets[actuator] = self._ctrl_range[actuator, 1]
        self._current_ctrl = np.array(targets, copy=True)
        force_measurement = self._boundary.apply_reset_state(EpisodePhysicsState(
            positions, velocities, np.zeros_like(initial.qacc),
            targets, np.zeros_like(initial.act),
        ), refresh_actuator_force=bool(getattr(self, '_force_feedback_required', False)),
            static_world_child_poses={
                self._fixture_bodies[name]: (
                    np.asarray(value.position, dtype=np.float32),
                    np.asarray(value.quaternion_wxyz, dtype=np.float32),
                )
                for name, value in sample.fixture_pose_world.items()
            })
        if force_measurement is not None:
            if not force_measurement.valid or force_measurement.phase != 'reset_forward':
                raise ValueError('GeoPhys reset did not publish a valid reset-forward actuator-force sample')
            if force_measurement.native_step_index != 0:
                raise ValueError('GeoPhys reset-forward force sample must reference native step 0')
            if force_measurement.sample_sequence <= self._last_reset_force_sequence:
                raise ValueError('GeoPhys reset reused a prior actuator-force sample')
            if self._force_source_generation is not None and (
                force_measurement.source_generation != self._force_source_generation
            ):
                raise ValueError('GeoPhys reset actuator-force sample belongs to another solver identity')
            self._force_source_generation = force_measurement.source_generation
        realized = self._realized(sample)
        if self._mixed_actuator_plan is not None:
            self._native_steps = 0
            self._mixed_consumed_boundaries.clear()
            self._mixed_pending_target = None
            self._mixed_fault = None
            state, free_joint_native = self._snapshot_with_native_free_joints()
            self._last_reset_readback_v1 = {
                'schema_version': 'geophys-runtime-reset-readback-v1',
                'source_id': self._source.scene_source.source_id,
                'source_closure_digest': self._source.source_closure_digest,
                'provider_materialization_id': self._provider_materialization_id,
                'episode_id': self._episode_id,
                'reset_sample_id': self._reset_sample_id,
                'simulation_time_s': float(state.simulation_time),
                'joint_position': dict(state.joint_position),
                'joint_velocity': dict(state.joint_velocity),
                'poses_world': {
                    name: {
                        'position_m': list(value.position),
                        'quaternion_wxyz': list(value.quaternion_wxyz),
                    }
                    for name, value in state.pose_world.items()
                    if name in self._source.free_joints
                },
                'free_joint_velocity': {
                    name: list(qvel) for name, (_, qvel) in free_joint_native.items()
                },
                'free_joint_velocity_frame': 'source_sampled_reset_qvel_v1',
                'fixture_pose_world': {
                    name: self._pose_mapping(self._fixture_pose_readback(name))
                    for name in self._source.fixture_bodies
                },
                'native_step_count': 0,
                'state_sync_count': 1,
                'reset_method': 'GeoPhysRuntimeBoundary.apply_reset_state',
            }
        if force_measurement is not None:
            from dataclasses import replace

            force_measurement = replace(
                force_measurement,
                episode_id=str(self._episode_id),
                reset_sample_id=str(self._reset_sample_id),
                evaluation_control_step=0,
                evaluation_simulation_time_s=0.0,
                actuator_id=str(self._source.open_actuators[0]),
            )
        self._reset_force_measurement = force_measurement
        if force_measurement is not None:
            self._last_reset_force_sequence = force_measurement.sample_sequence
        return realized

    @staticmethod
    def _pose_mapping(value):
        return {
            'position_m': list(value.position),
            'quaternion_wxyz': list(value.quaternion_wxyz),
        }

    def _fixture_pose_readback(self, name):
        from ...environment import SnapshotRequest

        readback = self._boundary.read_snapshot(SnapshotRequest(
            qacc=False, ctrl=False, body_pose=True, site_pose=False, simulation_time=False,
        ))
        body_id = self._fixture_bodies[name]
        return pose(readback.body_xpos[body_id], readback.body_xquat[body_id])

    def _preflight_mixed_reset(self, sample):
        """Reject source-bound reset values the public GeoPhys reset cannot realize."""
        if float(sample.simulation_time_s) != 0.0:
            raise ValueError('GeoPhys mixed reset currently supports source time zero only')
        if (set(sample.joint_position) != set(self._joint_addresses)
                or set(sample.poses_world) != set(self._free_addresses)
                or set(sample.free_joint_velocity) != set(self._free_addresses)):
            raise ValueError('GeoPhys mixed reset state names differ from the compiled source layout')
        if set(sample.fixture_pose_world) != set(self._source.fixture_bodies):
            raise ValueError('GeoPhys mixed reset fixture names differ from the compiled source')
        if any(float(value) != 0.0 for value in sample.joint_velocity.values()) or any(
            float(value) != 0.0
            for velocity in sample.free_joint_velocity.values()
            for value in velocity
        ):
            raise ValueError('GeoPhys mixed reset currently supports source zero-velocity samples only')
        for name, expected in sample.fixture_pose_world.items():
            body_id = self._fixture_bodies[name]
            if body_id >= self._body_parentid.size or int(self._body_parentid[body_id]) >= 0:
                raise ValueError(f'GeoPhys mixed reset fixture is not a direct world-root body: {name}')
            if body_id >= self._body_jntnum.size or int(self._body_jntnum[body_id]) != 0:
                raise ValueError(f'GeoPhys mixed reset fixture root must be fixed: {name}')
            expected.validate()

    @property
    def reset_readback_v1(self):
        if self._last_reset_readback_v1 is None:
            raise RuntimeError('GeoPhys reset readback is unavailable before an admitted mixed reset')
        return deepcopy(self._last_reset_readback_v1)

    @property
    def close_receipt(self):
        if not self._closed or self._last_close_receipt is None:
            raise RuntimeError('GeoPhys RuntimeSession close has not completed')
        return deepcopy(self._last_close_receipt)

    def _snapshot_with_native_free_joints(self):
        self._require_reset()
        readback = self._boundary.read_snapshot(SnapshotRequest(
            qacc=False, ctrl=False, body_pose=True, site_pose=True, simulation_time=True,
        ))
        positions = {name: float(readback.qpos[address[0]]) for name, address in self._joint_addresses.items()}
        velocities = {name: float(readback.qvel[address[1]]) for name, address in self._joint_addresses.items()}
        poses = {name: pose(readback.body_xpos[index], readback.body_xquat[index]) for name, index in self._bodies.items()}
        poses.update({name: pose(readback.site_xpos[index], readback.site_xquat[index]) for name, index in self._frames.items()})
        state = self._state(positions, velocities, poses, readback.simulation_time)
        free_joint_native = {
            name: (
                tuple(float(value) for value in readback.qpos[qpos:qpos + 7]),
                tuple(float(value) for value in readback.qvel[dof:dof + 6]),
            )
            for name, (qpos, dof) in self._free_addresses.items()
        }
        return state, free_joint_native

    def snapshot(self):
        self._require_reset()
        return self._snapshot_with_native_free_joints()[0]

    def _capture_actuator_force(self, state):
        self._require_reset()
        native = self._boundary.read_snapshot(SnapshotRequest(qacc=False, ctrl=True,
            body_pose=False, site_pose=False, actuator_force=True, simulation_time=True))
        if float(native.simulation_time) != float(state.simulation_time):
            raise ValueError('GeoPhys actuator-force readback is not at the requested evaluation boundary')
        actuator_index = self._open_actuators[0]
        if native.actuator_force is None or not np.all(np.isfinite(native.actuator_force)):
            raise ValueError('GeoPhys required actuator-force sample is non-finite or missing')
        if native.ctrl is None or not np.isfinite(native.ctrl[actuator_index]):
            raise ValueError('GeoPhys required actuator-force sample has no finite actuator input')
        signed_force_N = float(native.actuator_force[actuator_index])
        measurement = native.actuator_force_measurement
        if measurement is None:
            raise ValueError('GeoPhys required actuator-force sample has no validity contract')
        dt = float(self._artifact.timebase.physics_dt)
        native_sample_time_s = (
            0.0
            if measurement.phase == 'reset_forward'
            else max(0.0, float(measurement.native_step_index - 1) * dt)
        )
        from dataclasses import replace

        measurement = replace(
            measurement,
            episode_id=str(self._episode_id),
            reset_sample_id=str(self._reset_sample_id),
            evaluation_control_step=int(state.control_step),
            evaluation_simulation_time_s=float(state.simulation_time),
            actuator_id=str(self._source.open_actuators[0]),
            actuator_ctrl=float(native.ctrl[actuator_index]),
            signed_force_N=signed_force_N,
            native_sample_time_s=native_sample_time_s,
        )
        if measurement.source_generation != self._force_source_generation:
            raise ValueError('GeoPhys actuator-force sample belongs to another solver identity')
        if measurement.reset_sample_id != self._reset_sample_id:
            raise ValueError('GeoPhys actuator-force sample belongs to another ResetSample')
        if measurement.actuator_id != self._source.open_actuators[0]:
            raise ValueError('GeoPhys actuator-force sample has the wrong actuator identity')
        if measurement.valid:
            self._validate_actuator_force_measurement(state, native, measurement)
        self._last_actuator_force_measurement = measurement
        return native, measurement

    def _snapshot_typed_actuator_force_values(self, boundary, sample_clock, requirements):
        from ...artifacts import TypedActuatorForceStateValue, UnavailableStateValue

        if not getattr(self, '_r1_force_admitted', False):
            return (), tuple(UnavailableStateValue(
                'unavailable-state-value-v1', item.field_name, item.subject_kind,
                item.entity_id, item.subject_id, item.sample_domain,
                'GeoPhys typed actuator force is limited to the admitted Panda R1 source binding',
            ) for item in requirements)
        state = self.snapshot()
        if (state.control_step != boundary.control_step
                or float(state.simulation_time) != sample_clock.simulation_time_s):
            raise ValueError('typed force readback boundary changed during state publication')
        native, measurement = self._capture_actuator_force(state)
        actuator_index = self._open_actuators[0]
        values = []
        for item in requirements:
            if (item.entity_id, item.subject_id, item.unit) != (
                'panda-main', self._source.open_actuators[0], 'N',
            ):
                missing_requirements = requirements[len(values):]
                return tuple(values), tuple(UnavailableStateValue(
                    'unavailable-state-value-v1', requirement.field_name,
                    requirement.subject_kind, requirement.entity_id,
                    requirement.subject_id, requirement.sample_domain,
                    'GeoPhys bounded R1 force route only maps panda-main/actuator8 in N',
                ) for requirement in missing_requirements)
            values.append(TypedActuatorForceStateValue(
                'typed-actuator-force-state-v1',
                item.entity_id,
                item.subject_id,
                measurement.force_unit,
                measurement.signed_force_N if measurement.valid else None,
                measurement.actuator_ctrl if measurement.valid else None,
                measurement.valid,
                measurement.invalid_reason,
                measurement.source_generation,
                measurement.sample_sequence,
                measurement.state_revision,
                measurement.configuration_revision,
                self._source.source_closure_digest,
                self._provider_materialization_id,
                measurement.phase,
                measurement.native_step_index,
                float(self._artifact.timebase.physics_dt),
                float(measurement.native_sample_time_s or 0.0),
                str(self._episode_id),
                str(self._reset_sample_id),
                boundary.boundary_id,
                int(state.control_step),
                float(state.simulation_time),
            ))
            self._last_typed_force_publication = values[-1]
        return tuple(values), ()

    def control_feedback(self, state, *, actuator_force=None):
        from .control import feedback_value
        self._require_reset()
        if not hasattr(self, '_control_binding'):
            raise ValueError('control session admission required')
        if not getattr(self, '_force_feedback_required', False):
            raise ValueError('actuator-force feedback is not admitted for this Controller profile')
        if getattr(self, '_r1_force_admitted', False) and actuator_force is None:
            raise ValueError('plan-bound R1 feedback requires its current typed force publication')
        native, measurement = self._capture_actuator_force(state)
        if not measurement.valid:
            raise ValueError(
                'GeoPhys required actuator-force sample is invalid: '
                f'{measurement.invalid_reason or "unknown reason"}'
            )
        signed_force_N = float(measurement.signed_force_N)
        if actuator_force is not None:
            from ...artifacts import TypedActuatorForceStateValue
            if not isinstance(actuator_force, TypedActuatorForceStateValue):
                raise TypeError('typed Controller feedback requires TypedActuatorForceStateValue')
            if actuator_force != getattr(self, '_last_typed_force_publication', None):
                raise ValueError('typed actuator-force value is not the current RuntimeSession publication')
            if (actuator_force.actuator_id != measurement.actuator_id
                    or actuator_force.entity_id != 'panda-main'
                    or actuator_force.unit != measurement.force_unit
                    or actuator_force.signed_value != measurement.signed_force_N
                    or actuator_force.actuator_control_value != measurement.actuator_ctrl
                    or actuator_force.source_generation != measurement.source_generation
                    or actuator_force.sample_sequence != measurement.sample_sequence
                    or actuator_force.source_state_revision != measurement.state_revision
                    or actuator_force.configuration_revision != measurement.configuration_revision
                    or actuator_force.source_closure_digest != self._source.source_closure_digest
                    or actuator_force.provider_materialization_id != self._provider_materialization_id
                    or actuator_force.native_step_index != measurement.native_step_index
                    or actuator_force.sample_phase != measurement.phase
                    or actuator_force.episode_id != measurement.episode_id
                    or actuator_force.reset_sample_id != measurement.reset_sample_id):
                raise ValueError('typed actuator-force publication differs from the current Provider sample')
            signed_force_N = float(actuator_force.signed_value)
        return feedback_value(self, state, signed_force_N)

    def bind_mixed_controller(self, controller_identity):
        if self._mixed_actuator_plan is None:
            raise RuntimeError('mixed Controller binding is restricted to a mixed actuator source')
        if self._reset_done or self._mixed_controller_identity is not None:
            raise RuntimeError('mixed Controller must bind exactly once before reset')
        if (type(controller_identity) is not str or not controller_identity.strip()
                or controller_identity != self._mixed_actuator_plan.controller_identity):
            raise ValueError('mixed Controller identity differs from the source-bound plan')
        self._mixed_controller_identity = controller_identity

    def apply_mixed_actuator_command(self, target):
        from ...controllers.canonical.contracts import (
            AppliedMixedActuatorCommandV1, MixedActuatorCommandV1,
        )
        from ...environment import ControlCommand

        self._require_reset()
        if self._mixed_actuator_plan is None:
            raise RuntimeError('mixed actuator command requires an admitted source-bound plan')
        if self._mixed_fault is not None:
            raise RuntimeError('mixed actuator GeoPhys session is fault-latched')
        if type(target) is not MixedActuatorCommandV1:
            raise TypeError('GeoPhys mixed actuator route requires MixedActuatorCommandV1')
        target.validate()
        state = self.snapshot()
        if (target.controller_identity != self._mixed_controller_identity
                or target.plan_identity_hash != self._mixed_actuator_plan.identity_hash
                or target.task_artifact_hash != self._artifact.identity_hash
                or target.source_id != self._source.scene_source.source_id
                or target.source_closure_digest != self._source.source_closure_digest
                or target.provider_materialization_id != self._provider_materialization_id
                or target.episode_id != self._episode_id
                or target.reset_sample_id != self._reset_sample_id
                or target.control_step != self._control_step
                or target.state_revision != self._state_revision
                or target.simulation_time_s != state.simulation_time):
            raise ValueError('GeoPhys mixed target identity or boundary is stale/mismatched')
        boundary = (target.episode_id, target.reset_sample_id, target.control_step, target.state_revision)
        if boundary in self._mixed_consumed_boundaries or self._mixed_pending_target is not None:
            raise ValueError('GeoPhys mixed target boundary was already consumed or is still pending')
        channels = {item.semantic_id: item for item in self._mixed_actuator_plan.channels}
        requested = dict(target.channel_values)
        units = dict(target.channel_units)
        if set(requested) != set(channels) or set(units) != set(channels):
            raise ValueError('GeoPhys mixed command does not cover every declared source channel')
        ctrl = np.array(self._current_ctrl, copy=True)
        actual_values = {}
        clipped = False
        for semantic, channel in channels.items():
            value = float(requested[semantic])
            low, high = channel.control_range
            actuator_id = self._mixed_channel_actuators[semantic]
            actual_low, actual_high = (float(item) for item in self._ctrl_range[actuator_id])
            if (units[semantic] != channel.unit or not np.isfinite(value)
                    or not low <= value <= high
                    or not np.allclose((actual_low, actual_high), (low, high), rtol=0.0, atol=1e-7)):
                raise ValueError(f'GeoPhys mixed command differs from its typed source range: {semantic}')
            ctrl[actuator_id] = value
            actual_values[semantic] = value
        try:
            zeros = np.zeros_like(ctrl)
            applied = self._boundary.apply_control(ControlCommand(
                ctrl, zeros, zeros, ctrl, zeros, 'named_mixed_actuator',
            ))
            applied_ctrl = np.asarray(applied.applied_ctrl, dtype=np.float64)
            if applied_ctrl.shape != ctrl.shape or not np.isfinite(applied_ctrl).all():
                raise ValueError('GeoPhys mixed command did not return a finite actuator vector')
            actual_values = {
                semantic: float(applied_ctrl[actuator_id])
                for semantic, actuator_id in self._mixed_channel_actuators.items()
            }
            boundary_ctrl = np.asarray(ctrl, dtype=np.float32)
            represented_values = {
                semantic: float(boundary_ctrl[actuator_id])
                for semantic, actuator_id in self._mixed_channel_actuators.items()
            }
            # GeoPhys control storage is float32. Compare the applied vector to
            # the representable request written into that vector, so ordinary
            # float64-to-float32 rounding is not misreported as provider clipping.
            clipped = any(actual_values[key] != represented_values[key] for key in channels)
            if clipped:
                raise ValueError('GeoPhys clipped a source-range-validated mixed command')
            self._current_ctrl = np.array(applied_ctrl, copy=True)
        except BaseException as error:
            self._mixed_fault = {
                'phase': 'partial_control_apply',
                'error': f'{type(error).__name__}: {error}',
            }
            raise
        self._mixed_consumed_boundaries.add(boundary)
        self._mixed_pending_target = target
        result = AppliedMixedActuatorCommandV1(
            'applied-mixed-actuator-command-v1', target.identity_hash, 'geophys',
            actual_values, units, clipped,
            'source_bound_named_actuator_channels_zero_order_hold_v1',
        )
        result.validate()
        return result

    def step_mixed_actuator_interval(self, command_factory):
        from ...controllers.canonical.contracts import (
            AppliedMixedActuatorCommandV1, MixedActuatorCommandV1,
        )
        self._require_reset()
        if self._mixed_actuator_plan is None or self._mixed_fault is not None:
            raise RuntimeError('GeoPhys stepwise commands require an admitted, healthy mixed profile')
        if not callable(command_factory) or self._mixed_pending_target is not None:
            raise ValueError('GeoPhys mixed interval requires a callback and no pending command')
        if self._inner_interval_active:
            raise RuntimeError('GeoPhys mixed intervals cannot be nested')
        count = int(self._artifact.timebase.control_substeps)
        start_state = self.snapshot()
        start_revision = self._state_revision
        rows = []
        self._inner_interval_active = True
        try:
            for substep_index in range(count):
                before = self.snapshot()
                before_revision = self._state_revision
                target = command_factory(before, substep_index, count, before_revision)
                if type(target) is not MixedActuatorCommandV1:
                    raise TypeError('GeoPhys stepwise Controller must return MixedActuatorCommandV1')
                applied = self.apply_mixed_actuator_command(target)
                if type(applied) is not AppliedMixedActuatorCommandV1:
                    raise TypeError('GeoPhys returned an untyped mixed-control acknowledgement')
                if self._mixed_pending_target is not target:
                    raise RuntimeError('GeoPhys mixed interval lost the consumed target identity')
                self._boundary.step(substeps=1)
                self._native_steps += 1
                self._state_revision += 1
                self._mixed_pending_target = None
                after = self.snapshot()
                rows.append({
                    'substep_index': substep_index,
                    'target': target.to_mapping(),
                    'target_identity_sha256': target.identity_hash,
                    'applied': applied.to_mapping(),
                    'state_revision_before': before_revision,
                    'state_revision_after': self._state_revision,
                    'simulation_time_before_s': float(before.simulation_time),
                    'simulation_time_after_s': float(after.simulation_time),
                })
            self._control_step += 1
            self._inner_interval_active = False
            result_state = self.snapshot()
            if (result_state.control_step != start_state.control_step + 1
                    or self._state_revision != start_revision + count
                    or self._native_steps % count != 0):
                raise ValueError('GeoPhys interval did not close on its declared outer/native boundary')
            return result_state, {
                'schema_version': 'mixed-actuator-stepwise-interval-receipt-v1',
                'provider_name': 'geophys',
                'provider_materialization_id': self._provider_materialization_id,
                'episode_id': self._episode_id,
                'reset_sample_id': self._reset_sample_id,
                'start_control_step': int(start_state.control_step),
                'end_control_step': int(result_state.control_step),
                'start_state_revision': int(start_revision),
                'end_state_revision': int(self._state_revision),
                'native_substep_count': count,
                'physics_dt_s': float(self._artifact.timebase.physics_dt),
                'substeps': rows,
            }
        except BaseException as error:
            self._mixed_fault = {
                'phase': 'stepwise_interval',
                'error': f'{type(error).__name__}: {error}',
                'native_steps_completed': int(self._native_steps),
                'control_boundary': int(self._control_step),
                'substeps_completed': len(rows),
            }
            raise

    def read_contact_summary_v2(self, requested_pairs):
        from ...environment.types import ContactSummaryV2
        self._require_reset()
        normalized = tuple(sorted({tuple(sorted((str(a), str(b)))) for a, b in requested_pairs}))
        if any(len(pair) != 2 or pair[0] == pair[1] for pair in normalized):
            raise ValueError('GeoPhys contact query requires distinct named pairs')
        state = self.snapshot()
        return ContactSummaryV2.unavailable(
            source_id=self._source.scene_source.source_id,
            source_closure_digest=self._source.source_closure_digest,
            provider_materialization_id=self._provider_materialization_id,
            episode_id=self._episode_id,
            reset_sample_id=self._reset_sample_id,
            control_step=self._control_step,
            state_revision=self._state_revision,
            simulation_time_s=state.simulation_time,
            requested_pairs=normalized,
            reason='provider_contact_pair_query_not_implemented',
        )

    def _validate_actuator_force_measurement(self, state, native, measurement=None):
        measurement = measurement or native.actuator_force_measurement
        if measurement is None:
            raise ValueError('GeoPhys required actuator-force sample has no validity contract')
        if not measurement.valid:
            raise ValueError(
                'GeoPhys required actuator-force sample is invalid: '
                f'{measurement.invalid_reason or "unknown reason"}'
            )
        if measurement.force_unit != 'N':
            raise ValueError('GeoPhys required actuator-force sample unit must be N')
        if float(native.simulation_time) != float(state.simulation_time):
            raise ValueError('GeoPhys actuator-force sample time differs from evaluation boundary')
        if measurement.actuator_id != self._source.open_actuators[0]:
            raise ValueError('GeoPhys actuator-force sample has the wrong actuator identity')
        if measurement.reset_sample_id != self._reset_sample_id:
            raise ValueError('GeoPhys actuator-force sample belongs to another ResetSample')
        if self._force_source_generation is None or (
            measurement.source_generation != self._force_source_generation
        ):
            raise ValueError('GeoPhys actuator-force sample belongs to another solver identity')
        if native.actuator_force is None or not np.all(np.isfinite(native.actuator_force)):
            raise ValueError('GeoPhys required actuator-force sample is non-finite or missing')
        dt = float(self._artifact.timebase.physics_dt)
        expected_native_step = int(round(float(state.simulation_time) / dt))
        if abs(float(state.simulation_time) / dt - expected_native_step) > 1.0e-7:
            raise ValueError('GeoPhys actuator-force sample clock is not on a native-step boundary')
        steps_per_control = int(self._artifact.timebase.control_substeps)
        expected_from_control = int(state.control_step) * steps_per_control
        if self._inner_interval_active:
            valid_native_range = range(expected_from_control,
                                       expected_from_control + steps_per_control)
            if expected_native_step not in valid_native_range:
                raise ValueError('GeoPhys actuator-force sample is outside the active native interval')
        elif expected_native_step != expected_from_control:
            raise ValueError('GeoPhys actuator-force sample clock differs from the control boundary')
        if measurement.native_step_index != expected_native_step:
            raise ValueError('GeoPhys actuator-force sample native index does not match the state boundary')
        if (
            measurement.evaluation_control_step != int(state.control_step)
            or measurement.evaluation_simulation_time_s != float(state.simulation_time)
        ):
            raise ValueError('GeoPhys actuator-force sample belongs to another evaluation boundary')
        if expected_native_step == 0:
            reset_measurement = self._reset_force_measurement
            if (
                measurement.phase != 'reset_forward'
                or reset_measurement is None
                or measurement.sample_sequence != reset_measurement.sample_sequence
                or measurement.state_revision != reset_measurement.state_revision
                or measurement.configuration_revision != reset_measurement.configuration_revision
                or measurement.episode_id != reset_measurement.episode_id
                or measurement.reset_sample_id != reset_measurement.reset_sample_id
                or float(state.simulation_time) != 0.0
            ):
                raise ValueError('first R1 feedback is not the current reset-forward force sample')
            if measurement.native_sample_time_s != 0.0:
                raise ValueError('reset-forward force sample must use native time zero')
        else:
            if (
                measurement.phase != 'native_step_pre_integration'
                or measurement.sample_sequence <= self._last_reset_force_sequence
            ):
                raise ValueError('GeoPhys feedback is not from a completed native-step force sample')
            expected_sample_time = float(expected_native_step - 1) * dt
            if measurement.native_sample_time_s != expected_sample_time:
                raise ValueError('GeoPhys force sample phase/time does not match its native-step index')
            previous = self._last_actuator_force_measurement
            if previous is not None:
                if previous.episode_id != measurement.episode_id:
                    raise ValueError('GeoPhys actuator-force sample belongs to another episode')
                if previous.evaluation_simulation_time_s == float(state.simulation_time):
                    if (
                        previous.sample_sequence != measurement.sample_sequence
                        or previous.state_revision != measurement.state_revision
                        or previous.configuration_revision != measurement.configuration_revision
                    ):
                        raise ValueError('GeoPhys force sample changed within one native evaluation state')
                else:
                    elapsed_native_steps = int(round(
                        (float(state.simulation_time) - previous.evaluation_simulation_time_s) / dt
                    ))
                    if elapsed_native_steps <= 0 or abs(
                        (float(state.simulation_time) - previous.evaluation_simulation_time_s)
                        - elapsed_native_steps * dt
                    ) > 1.0e-10:
                        raise ValueError('GeoPhys force evaluation boundaries are not separated by native steps')
                    native_step_advance = measurement.native_step_index - previous.native_step_index
                    sample_sequence_advance = measurement.sample_sequence - previous.sample_sequence
                    if (native_step_advance != elapsed_native_steps
                            or sample_sequence_advance != elapsed_native_steps):
                        raise ValueError(
                            'GeoPhys native force sample does not match the completed native-step gap '
                            f'(expected {elapsed_native_steps}, native index advanced {native_step_advance}, '
                            f'sample sequence advanced {sample_sequence_advance})'
                        )

    def native_control_feedback_sample(self, state, feedback):
        """Return the exact validated force sample consumed by this feedback."""
        from ...controllers.canonical.feedback import NativeControlFeedbackSampleV1

        self._require_reset()
        measurement = self._last_actuator_force_measurement
        if (measurement is None or feedback.control_step != state.control_step
                or feedback.simulation_time != state.simulation_time
                or measurement.evaluation_control_step != state.control_step
                or measurement.evaluation_simulation_time_s != state.simulation_time
                or feedback.gripper.closing_force_N != max(0.0, -float(measurement.signed_force_N))):
            raise ValueError('GeoPhys native feedback sample is not the measured Controller input')
        sample = NativeControlFeedbackSampleV1(
            'native-control-feedback-sample-v1', self._provider,
            self._provider_materialization_id, self._source.scene_source.source_id,
            self._source.source_closure_digest, str(self._episode_id),
            str(self._reset_sample_id), feedback, measurement,
        )
        sample.validate()
        return sample

    def apply_control(self, target):
        if self._mixed_actuator_plan is not None:
            return self.apply_mixed_actuator_command(target)
        from .control import validate_target
        from ...controllers.canonical.contracts import AppliedCanonicalControl
        from ...environment import ControlCommand
        validate_target(self, target)
        ctrl = np.array(self._current_ctrl, copy=True)
        for name, value in target.arm_servo_position.items():
            ctrl[self._target_actuators[name]] = value
        index = getattr(self, '_open_actuators_by_semantic', {}).get(
            target.gripper.semantic_id, self._open_actuators[0],
        )
        control_binding = getattr(self, '_position_control_bindings_by_semantic', {}).get(
            target.gripper.semantic_id, self._control_binding,
        )
        low, high = self._ctrl_range[index]
        ctrl[index] = low + target.gripper.servo_opening_m / control_binding.opening_range_m * (high-low)
        self._boundary.set_actuator_force_limits((index,), target.gripper.force_limit_N)
        zeros = np.zeros_like(ctrl)
        applied = self._boundary.apply_control(ControlCommand(ctrl, zeros, zeros, ctrl, zeros, "canonical_position"))
        self._current_ctrl = np.array(applied.applied_ctrl, copy=True)
        realized = {name: float(applied.applied_ctrl[self._target_actuators[name]])
                    for name in target.arm_joint_order}
        opening = float((applied.applied_ctrl[index]-low)/(high-low)*control_binding.opening_range_m)
        return AppliedCanonicalControl('applied-canonical-control-v0', target.identity_hash, 'geophys',
            realized, opening, target.gripper.force_limit_N, applied.clipped,
            'named_position_servo_plus_affine_tendon_opening_force_limit_ZOH')

    def step(self):
        self._require_reset()
        if self._mixed_actuator_plan is not None:
            if self._mixed_fault is not None:
                raise RuntimeError('mixed actuator GeoPhys session is fault-latched')
            if self._mixed_pending_target is None:
                raise RuntimeError('GeoPhys mixed outer step requires one fresh named target')
            try:
                self._boundary.step(substeps=self._artifact.timebase.control_substeps)
                self._native_steps += int(self._artifact.timebase.control_substeps)
                self._control_step += 1
                self._state_revision += 1
                self._mixed_pending_target = None
                return self.snapshot()
            except BaseException as error:
                self._mixed_fault = {
                    'phase': 'outer_step',
                    'error': f'{type(error).__name__}: {error}',
                    'native_steps_completed': int(self._native_steps),
                }
                raise
        self._boundary.step(
            substeps=self._artifact.timebase.control_substeps,
            track_actuator_force=bool(getattr(self, '_force_feedback_required', False)),
        )
        self._control_step += 1
        self._state_revision += 1
        return self.snapshot()

    def _step_physics_once(self):
        self._require_reset()
        self._boundary.step(substeps=1)

    def close(self):
        if not self._closed:
            failure = None
            boundary_close_completed = False
            source_receipt_close_completed = None
            try:
                if self._boundary is not None:
                    self._boundary.close()
                boundary_close_completed = True
            except BaseException as error:
                failure = error
            receipt = getattr(self._source, 'execution_source_receipt', None)
            try:
                if receipt is not None:
                    receipt.close()
                    source_receipt_close_completed = True
            except BaseException as error:
                source_receipt_close_completed = False
                if failure is None:
                    failure = error
                else:
                    failure.add_note(
                        f'execution source snapshot cleanup also failed: {type(error).__name__}: {error}'
                    )
            self._boundary = None
            self._closed = True
            self._last_close_receipt = {
                'schema_version': 'geophys-runtime-close-v1',
                'provider_materialization_id': self._provider_materialization_id,
                'episode_id': self._episode_id,
                'reset_sample_id': self._reset_sample_id,
                'session_closed': True,
                'boundary_close_completed': bool(boundary_close_completed),
                'boundary_owner': 'process_owned_taichi_runtime',
                'execution_source_receipt_close_completed': source_receipt_close_completed,
                'cleanup_completed': failure is None,
                'cleanup_error': None if failure is None else {
                    'type': type(failure).__name__, 'message': str(failure),
                },
                'control_step': int(self._control_step),
                'native_step_count': int(self._native_steps),
                'source_id': self._source.scene_source.source_id,
                'source_closure_digest': self._source.source_closure_digest,
            }
            if failure is not None:
                raise failure
