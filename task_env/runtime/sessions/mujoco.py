"""Private MuJoCo peer adapter. No comparison/oracle or controller implementation."""
import xml.etree.ElementTree as ET
import math
import numpy as np

from .common import _SessionValues, pose


class _MuJoCoSession(_SessionValues):
    def __init__(self, artifact, source):
        self._initialize_values(artifact, source, 'mujoco')
        import mujoco
        self._mj = mujoco
        root = ET.fromstring(source.scene_source.xml)
        # Legacy GeoPhys importer accepts extended freejoint attributes. MuJoCo
        # represents these same damping/armature values as a type=free joint.
        for element in root.iter('freejoint'):
            element.tag = 'joint'
            element.set('type', 'free')
        # Asset home keyframes precede composed free bodies; execution requests
        # own initialization, so stale source keyframes are not materialized.
        for element in root.findall('keyframe'):
            root.remove(element)
        self._model = mujoco.MjModel.from_xml_string(ET.tostring(root, encoding='unicode'))
        self._data = mujoco.MjData(self._model)
        self._native_steps = 0
        if self._model.opt.timestep != artifact.timebase.physics_dt:
            raise ValueError('MuJoCo native timestep mismatch')
        self._joint_addresses = {
            semantic: self._addresses(native, free=False) for semantic, native in source.joints.items()
        }
        self._free_addresses = {semantic: self._addresses(native, free=True)[0]
                                for semantic, native in source.free_joints.items()}
        self._bodies = {semantic: self._model.body(native).id for semantic, native in source.bodies.items()}
        self._frames = {semantic: self._model.site(native).id for semantic, native in source.frames.items()}
        self._target_actuators = {semantic: self._model.actuator(native).id for semantic, native in source.joint_targets.items()}
        self._open_actuators = tuple(self._model.actuator(native).id for native in source.open_actuators)

    def _addresses(self, name, *, free):
        joint = self._model.joint(name).id
        allowed = (self._mj.mjtJoint.mjJNT_FREE,) if free else (self._mj.mjtJoint.mjJNT_HINGE, self._mj.mjtJoint.mjJNT_SLIDE)
        if self._model.jnt_type[joint] not in allowed:
            raise ValueError('unsupported source joint representation')
        return int(self._model.jnt_qposadr[joint]), int(self._model.jnt_dofadr[joint])

    def reset(self, sample):
        self._validate_sample(sample)
        self._mj.mj_resetData(self._model, self._data)
        self._native_steps = 0
        for name, value in sample.joint_position.items():
            self._data.qpos[self._joint_addresses[name][0]] = value
        for name, requested in sample.poses_world.items():
            address = self._free_addresses[name]
            self._data.qpos[address:address+7] = (*requested.position, *requested.quaternion_wxyz)
        self._data.qvel[:] = 0
        self._data.act[:] = 0
        for name, actuator in self._target_actuators.items():
            self._data.ctrl[actuator] = sample.joint_position[name]
        for actuator in self._open_actuators:
            self._data.ctrl[actuator] = self._model.actuator_ctrlrange[actuator, 1]
        self._mj.mj_forward(self._model, self._data)
        self._completed_actuator_force = self._data.actuator_force.copy()
        return self._realized(sample)

    def snapshot(self):
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
        if self._artifact.timebase.control_substeps > 1:
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
        return self._state(positions, velocities, poses, time)

    def control_feedback(self, state):
        from .control import feedback_value
        self._require_reset()
        if not hasattr(self, '_control_binding'):
            raise ValueError('control session admission required')
        return feedback_value(self, state, self._completed_actuator_force[self._open_actuators[0]])

    def apply_control(self, target):
        from .control import validate_target
        from ...controllers.canonical.contracts import AppliedCanonicalControl
        validate_target(self, target)
        clipped = False
        realized = {}
        for name, index in self._target_actuators.items():
            requested = target.arm_servo_position[name]
            low, high = self._model.actuator_ctrlrange[index]
            value = float(np.clip(requested, low, high)) if self._model.actuator_ctrllimited[index] else requested
            self._data.ctrl[index] = value
            realized[name] = value
            clipped = clipped or value != requested
        index = self._open_actuators[0]
        low, high = self._model.actuator_ctrlrange[index]
        opening = float(np.clip(target.gripper.servo_opening_m, 0, self._control_binding.opening_range_m))
        self._data.ctrl[index] = low + opening/self._control_binding.opening_range_m*(high-low)
        self._model.actuator_forcelimited[index] = 1
        self._model.actuator_forcerange[index] = (-target.gripper.force_limit_N, target.gripper.force_limit_N)
        return AppliedCanonicalControl('applied-canonical-control-v0', target.identity_hash, 'mujoco',
            realized, opening, target.gripper.force_limit_N, clipped,
            'named_position_servo_plus_affine_tendon_opening_force_limit_ZOH')

    def step(self):
        self._require_reset()
        for _ in range(self._artifact.timebase.control_substeps):
            self._mj.mj_step(self._model, self._data)
            self._native_steps += 1
            if hasattr(self, '_control_binding'):
                self._completed_actuator_force = self._data.actuator_force.copy()
        self._mj.mj_forward(self._model, self._data)
        self._control_step += 1
        return self.snapshot()

    def close(self):
        if not self._closed:
            self._data, self._model = None, None
            self._closed = True
