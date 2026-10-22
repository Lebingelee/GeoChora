"""Private GeoPhys projection using the existing scalar bootstrap and boundary."""
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
                source_closure_digest=source.source_closure_digest,
            ),
            create_render_source=False,
        )
        self._boundary = runtime.boundary
        compiled = runtime.compiled_scene
        names, data = compiled.references.names, compiled.scene_model.joint_data
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
        self._target_actuators = {semantic: names.actuators[native] for semantic, native in source.joint_targets.items()}
        self._open_actuators = tuple(names.actuators[name] for name in source.open_actuators)
        self._ctrl_range = data['actuator_ctrlrange']
        self._initial = runtime.boundary.initial_state
        self._reset_force_measurement = None
        self._last_reset_force_sequence = 0
        self._force_source_generation = None
        self._last_actuator_force_measurement = None
        self._last_typed_force_publication = None

    @property
    def actuator_force_measurement(self):
        """Last adapter-validated signed sample, bound to this Core boundary."""
        return self._last_actuator_force_measurement

    def reset(self, sample):
        self._begin_reset()
        # A failed reset must not leave a previous episode's validated sample
        # visible through this adapter's diagnostic property.
        self._reset_force_measurement = None
        self._last_actuator_force_measurement = None
        self._last_typed_force_publication = None
        self._validate_sample(sample)
        initial = self._initial
        positions = np.array(initial.qpos, copy=True)
        targets = np.array(initial.ctrl, copy=True)
        for name, value in sample.joint_position.items():
            positions[self._joint_addresses[name][0]] = value
        for name, requested in sample.poses_world.items():
            address = self._free_addresses[name][0]
            positions[address:address+7] = (*requested.position, *requested.quaternion_wxyz)
        for name, actuator in self._target_actuators.items():
            targets[actuator] = sample.joint_position[name]
        for actuator in self._open_actuators:
            targets[actuator] = self._ctrl_range[actuator, 1]
        self._current_ctrl = np.array(targets, copy=True)
        force_measurement = self._boundary.apply_reset_state(EpisodePhysicsState(
            positions, np.zeros_like(initial.qvel), np.zeros_like(initial.qacc),
            targets, np.zeros_like(initial.act),
        ), refresh_actuator_force=bool(getattr(self, '_force_feedback_required', False)))
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
            self._boundary.close()
            self._boundary = None
            self._closed = True
