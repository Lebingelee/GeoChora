"""Private MuJoCo peer adapter. No comparison/oracle or controller implementation."""
import xml.etree.ElementTree as ET
import math
import numpy as np

from .common import _SessionValues, pose
from .source import lower_mujoco_scene_source, source_asset_bytes


def _source_asset_bytes(base_dir, source_xml):
    """Backward-compatible private spelling for the shared source owner."""

    return source_asset_bytes(base_dir, source_xml)


class _MuJoCoSession(_SessionValues):
    def __init__(self, artifact, source):
        self._initialize_values(artifact, source, 'mujoco')
        import mujoco
        self._mj = mujoco
        assets = None
        if source.scene_definition is not None:
            source_xml, assets = lower_mujoco_scene_source(
                source.scene_source,
                source.scene_definition,
                source.source_closure_digest,
            )
        else:
            source_xml = source.scene_source.xml
            legacy_root = ET.fromstring(source_xml)
            for element in legacy_root.iter('freejoint'):
                element.tag = 'joint'
                element.set('type', 'free')
            for element in legacy_root.findall('keyframe'):
                legacy_root.remove(element)
            source_xml = ET.tostring(legacy_root, encoding='unicode')
        root = ET.fromstring(source_xml)
        self._model = mujoco.MjModel.from_xml_string(
            ET.tostring(root, encoding='unicode'), assets=assets,
        )
        self._data = mujoco.MjData(self._model)
        self._native_steps = 0
        self._force_sample_sequence = 0
        self._force_configuration_revision = 0
        self._last_force_limit_N = None
        self._completed_actuator_ctrl = None
        self._completed_force_measurement = None
        if self._model.opt.timestep != artifact.timebase.physics_dt:
            raise ValueError('MuJoCo native timestep mismatch')
        self._joint_addresses = {
            semantic: self._addresses(native, free=False) for semantic, native in source.joints.items()
        }
        self._free_addresses = {semantic: self._addresses(native, free=True)
                                for semantic, native in source.free_joints.items()}
        self._bodies = {semantic: self._model.body(native).id for semantic, native in source.bodies.items()}
        self._frames = {semantic: self._model.site(native).id for semantic, native in source.frames.items()}
        self._target_actuators = {semantic: self._model.actuator(native).id for semantic, native in source.joint_targets.items()}
        self._open_actuators = tuple(self._model.actuator(native).id for native in source.open_actuators)
        self._validate_canonical_scene_model()

    def _cache_completed_actuator_force(self):
        """Read force only when the admitted Controller state contract requires it."""
        if getattr(self, '_force_feedback_required', False):
            self._completed_actuator_force = self._data.actuator_force.copy()
            self._completed_actuator_ctrl = self._data.ctrl.copy()
            self._force_sample_sequence += 1
            from ...environment.types import ActuatorForceMeasurementV1
            self._completed_force_measurement = ActuatorForceMeasurementV1(
                'task-env-actuator-force-sample-v1', 1,
                self._force_sample_sequence, self._native_steps,
                self._force_configuration_revision, self._native_steps,
                'reset_forward' if self._native_steps == 0 else 'native_step_pre_integration',
                True, 'N', None,
            )
        else:
            self._completed_actuator_force = None
            self._completed_actuator_ctrl = None
            self._completed_force_measurement = None

    def _validate_canonical_scene_model(self):
        scene = self._source.scene_definition
        if scene is None:
            return
        frame_ids = {
            frame.frame_id
            for frame in scene.frames or ()
            if frame.frame_kind == 'runtime'
        }
        for name in sorted(frame_ids):
            body_id = self._mj.mj_name2id(self._model, self._mj.mjtObj.mjOBJ_BODY, name)
            site_id = self._mj.mj_name2id(self._model, self._mj.mjtObj.mjOBJ_SITE, name)
            if body_id < 0 and site_id < 0:
                raise ValueError(f'canonical runtime Frame {name!r} is absent from the MuJoCo model')

        expected_joint_type = {
            'revolute': self._mj.mjtJoint.mjJNT_HINGE,
            'continuous': self._mj.mjtJoint.mjJNT_HINGE,
            'prismatic': self._mj.mjtJoint.mjJNT_SLIDE,
        }
        for articulation in scene.articulations or ():
            for joint in articulation.joints:
                if joint.kind == 'fixed':
                    expected_type = None
                else:
                    expected_type = expected_joint_type.get(joint.kind)
                    if expected_type is None:
                        raise ValueError(
                            f'MuJoCo D01b does not admit canonical Joint kind {joint.kind!r}'
                        )
                try:
                    parent_id = self._model.body(joint.parent_frame.frame_id).id
                    child_id = self._model.body(joint.child_frame.frame_id).id
                except Exception as exc:
                    raise ValueError(
                        f'canonical Joint {joint.joint_id!r} endpoints must resolve to MuJoCo bodies'
                    ) from exc
                if int(self._model.body_parentid[child_id]) != parent_id:
                    raise ValueError(
                        f'canonical Joint {joint.joint_id!r} parent/child topology differs in MuJoCo'
                    )
                if expected_type is None:
                    continue
                joint_id = self._mj.mj_name2id(
                    self._model, self._mj.mjtObj.mjOBJ_JOINT, joint.joint_id,
                )
                if joint_id < 0:
                    raise ValueError(f'canonical Joint {joint.joint_id!r} is absent from MuJoCo')
                if (
                    self._model.jnt_type[joint_id] != expected_type
                    or int(self._model.jnt_bodyid[joint_id]) != child_id
                ):
                    raise ValueError(
                        f'canonical Joint {joint.joint_id!r} type/child binding differs in MuJoCo'
                    )
                if not np.allclose(
                    self._model.jnt_axis[joint_id], joint.axis, rtol=0.0, atol=1.0e-9,
                ):
                    raise ValueError(
                        f'canonical Joint {joint.joint_id!r} axis differs in MuJoCo'
                    )

    def _addresses(self, name, *, free):
        joint = self._model.joint(name).id
        allowed = (self._mj.mjtJoint.mjJNT_FREE,) if free else (self._mj.mjtJoint.mjJNT_HINGE, self._mj.mjtJoint.mjJNT_SLIDE)
        if self._model.jnt_type[joint] not in allowed:
            raise ValueError('unsupported source joint representation')
        return int(self._model.jnt_qposadr[joint]), int(self._model.jnt_dofadr[joint])

    def reset(self, sample):
        self._begin_reset()
        self._validate_sample(sample)
        self._mj.mj_resetData(self._model, self._data)
        self._native_steps = 0
        self._force_sample_sequence = 0
        self._force_configuration_revision = 0
        self._last_force_limit_N = None
        self._completed_force_measurement = None
        for name, value in sample.joint_position.items():
            self._data.qpos[self._joint_addresses[name][0]] = value
        for name, requested in sample.poses_world.items():
            address = self._free_addresses[name][0]
            self._data.qpos[address:address+7] = (*requested.position, *requested.quaternion_wxyz)
        self._data.qvel[:] = 0
        self._data.act[:] = 0
        for name, actuator in self._target_actuators.items():
            self._data.ctrl[actuator] = sample.joint_position[name]
        for actuator in self._open_actuators:
            self._data.ctrl[actuator] = self._model.actuator_ctrlrange[actuator, 1]
        self._current_ctrl = self._data.ctrl.copy()
        self._mj.mj_forward(self._model, self._data)
        self._cache_completed_actuator_force()
        return self._realized(sample)

    def _snapshot_with_native_free_joints(self):
        self._require_reset()
        data = self._data
        positions = {name: float(data.qpos[address[0]]) for name, address in self._joint_addresses.items()}
        velocities = {name: float(data.qvel[address[1]]) for name, address in self._joint_addresses.items()}
        poses = {name: pose(data.xpos[index], data.xquat[index]) for name, index in self._bodies.items()}
        for name, index in self._frames.items():
            quaternion = np.zeros(4)
            self._mj.mju_mat2Quat(quaternion, data.site_xmat[index])
            poses[name] = pose(data.site_xpos[index], quaternion)
        time = data.time
        if self._artifact.timebase.control_substeps > 1 and not self._inner_interval_active:
            if self._native_steps != self._control_step * self._artifact.timebase.control_substeps:
                raise ValueError('MuJoCo native/canonical step-count mismatch')
            expected = self._native_steps * self._artifact.timebase.physics_dt
            # Standard binary64 summation roundoff bound, not a physics tolerance.
            nu = self._native_steps * 2.0**-53
            if nu >= 1:
                raise ValueError('native clock accumulation bound unavailable')
            bound = nu / (1.0 - nu) * abs(expected) + math.ulp(expected)
            self._native_time_audit = {'native_time_s': float(data.time),
                'completed_native_steps': self._native_steps, 'expected_native_elapsed_s': expected,
                'binary64_summation_roundoff_bound_s': bound}
            if not math.isfinite(data.time) or abs(data.time - expected) > bound:
                raise ValueError('MuJoCo measured native time/count mismatch')
            time = self._control_step * self._artifact.timebase.control_dt
        elif self._inner_interval_active:
            time = float(data.time)
        state = self._state(positions, velocities, poses, time)
        free_joint_native = {
            name: (
                tuple(float(value) for value in data.qpos[qpos:qpos + 7]),
                tuple(float(value) for value in data.qvel[dof:dof + 6]),
            )
            for name, (qpos, dof) in self._free_addresses.items()
        }
        return state, free_joint_native

    def snapshot(self):
        self._require_reset()
        return self._snapshot_with_native_free_joints()[0]

    def control_feedback(self, state):
        from .control import feedback_value
        self._require_reset()
        if not hasattr(self, '_control_binding'):
            raise ValueError('control session admission required')
        if not getattr(self, '_force_feedback_required', False):
            raise ValueError('actuator-force feedback is not admitted for this Controller profile')
        return feedback_value(self, state, self._completed_actuator_force[self._open_actuators[0]])

    def native_control_feedback_sample(self, state, feedback):
        """Publish provenance for the exact cached force used by control_feedback()."""
        from ...controllers.canonical.feedback import NativeControlFeedbackSampleV1
        from ...environment.types import ActuatorForceMeasurementV1

        self._require_reset()
        index = self._open_actuators[0]
        if (not getattr(self, '_force_feedback_required', False)
                or self._completed_actuator_force is None
                or self._completed_actuator_ctrl is None
                or self._completed_force_measurement is None):
            raise ValueError('MuJoCo native force sample is not admitted for this Controller profile')
        signed_force = float(self._completed_actuator_force[index])
        actuator_ctrl = float(self._completed_actuator_ctrl[index])
        native_index = int(self._native_steps)
        sample_time = (0.0 if native_index == 0 else
                       float(native_index - 1) * self._artifact.timebase.physics_dt)
        measurement = ActuatorForceMeasurementV1(
            'task-env-actuator-force-sample-v1', 1,
            self._completed_force_measurement.sample_sequence,
            self._state_revision if native_index == 0 else native_index,
            self._force_configuration_revision, native_index,
            'reset_forward' if native_index == 0 else 'native_step_pre_integration',
            True, 'N', None, str(self._episode_id), str(self._reset_sample_id),
            int(state.control_step), float(state.simulation_time),
            str(self._source.open_actuators[0]), actuator_ctrl, signed_force, sample_time,
        )
        if feedback.gripper.closing_force_N != max(0.0, -signed_force):
            raise ValueError('MuJoCo native force sample differs from canonical Controller feedback')
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
        validate_target(self, target)
        clipped = False
        realized = {}
        for name, requested in target.arm_servo_position.items():
            index = self._target_actuators[name]
            low, high = self._model.actuator_ctrlrange[index]
            value = float(np.clip(requested, low, high)) if self._model.actuator_ctrllimited[index] else requested
            self._data.ctrl[index] = value
            realized[name] = value
            clipped = clipped or value != requested
        index = getattr(self, '_open_actuators_by_semantic', {}).get(
            target.gripper.semantic_id, self._open_actuators[0],
        )
        if self._last_force_limit_N != float(target.gripper.force_limit_N):
            self._force_configuration_revision += 1
            self._last_force_limit_N = float(target.gripper.force_limit_N)
        control_binding = getattr(self, '_position_control_bindings_by_semantic', {}).get(
            target.gripper.semantic_id, self._control_binding,
        )
        low, high = self._model.actuator_ctrlrange[index]
        opening = float(np.clip(target.gripper.servo_opening_m, 0, control_binding.opening_range_m))
        self._data.ctrl[index] = low + opening/control_binding.opening_range_m*(high-low)
        self._model.actuator_forcelimited[index] = 1
        self._model.actuator_forcerange[index] = (-target.gripper.force_limit_N, target.gripper.force_limit_N)
        self._current_ctrl = self._data.ctrl.copy()
        return AppliedCanonicalControl('applied-canonical-control-v0', target.identity_hash, 'mujoco',
            realized, opening, target.gripper.force_limit_N, clipped,
            'named_position_servo_plus_affine_tendon_opening_force_limit_ZOH')

    def step(self):
        self._require_reset()
        for _ in range(self._artifact.timebase.control_substeps):
            self._mj.mj_step(self._model, self._data)
            self._native_steps += 1
            self._cache_completed_actuator_force()
        self._mj.mj_forward(self._model, self._data)
        self._control_step += 1
        self._state_revision += 1
        return self.snapshot()

    def _step_physics_once(self):
        self._require_reset()
        self._mj.mj_step(self._model, self._data)
        self._native_steps += 1
        self._cache_completed_actuator_force()
        self._mj.mj_forward(self._model, self._data)

    def close(self):
        if not self._closed:
            self._data, self._model = None, None
            self._closed = True
