"""Private MuJoCo peer adapter. No comparison/oracle or controller implementation."""
import xml.etree.ElementTree as ET
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
        return self._state(positions, velocities, poses, data.time)

    def step(self):
        self._require_reset()
        for _ in range(self._artifact.timebase.control_substeps):
            self._mj.mj_step(self._model, self._data)
        self._mj.mj_forward(self._model, self._data)
        self._control_step += 1
        return self.snapshot()

    def close(self):
        if not self._closed:
            self._data, self._model = None, None
            self._closed = True
