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
            scene_composer=GeoPhysSourceComposer(source.scene_source), create_render_source=False,
        )
        self._boundary = runtime.boundary
        compiled = runtime.compiled_scene
        names, data = compiled.references.names, compiled.scene_model.joint_data
        self._joint_addresses = {
            semantic: (int(data['jnt_qposadr'][names.joints[native]]),
                       int(data['jnt_dofadr'][names.joints[native]]))
            for semantic, native in source.joints.items()
        }
        self._free_addresses = {semantic: int(data['jnt_qposadr'][names.joints[native]])
                                for semantic, native in source.free_joints.items()}
        self._bodies = {semantic: names.bodies[native] for semantic, native in source.bodies.items()}
        self._frames = {semantic: names.sites[native] for semantic, native in source.frames.items()}
        self._target_actuators = {semantic: names.actuators[native] for semantic, native in source.joint_targets.items()}
        self._open_actuators = tuple(names.actuators[name] for name in source.open_actuators)
        self._ctrl_range = data['actuator_ctrlrange']
        self._initial = runtime.boundary.initial_state

    def reset(self, sample):
        self._validate_sample(sample)
        initial = self._initial
        positions = np.array(initial.qpos, copy=True)
        targets = np.array(initial.ctrl, copy=True)
        for name, value in sample.joint_position.items():
            positions[self._joint_addresses[name][0]] = value
        for name, requested in sample.poses_world.items():
            address = self._free_addresses[name]
            positions[address:address+7] = (*requested.position, *requested.quaternion_wxyz)
        for name, actuator in self._target_actuators.items():
            targets[actuator] = sample.joint_position[name]
        for actuator in self._open_actuators:
            targets[actuator] = self._ctrl_range[actuator, 1]
        self._boundary.apply_reset_state(EpisodePhysicsState(
            positions, np.zeros_like(initial.qvel), np.zeros_like(initial.qacc),
            targets, np.zeros_like(initial.act),
        ))
        return self._realized(sample)

    def snapshot(self):
        self._require_reset()
        readback = self._boundary.read_snapshot(SnapshotRequest(
            qacc=False, ctrl=False, body_pose=True, site_pose=True, simulation_time=True,
        ))
        positions = {name: float(readback.qpos[address[0]]) for name, address in self._joint_addresses.items()}
        velocities = {name: float(readback.qvel[address[1]]) for name, address in self._joint_addresses.items()}
        poses = {name: pose(readback.body_xpos[index], readback.body_xquat[index]) for name, index in self._bodies.items()}
        poses.update({name: pose(readback.site_xpos[index], readback.site_xquat[index]) for name, index in self._frames.items()})
        return self._state(positions, velocities, poses, readback.simulation_time)

    def step(self):
        self._require_reset()
        self._boundary.step(substeps=self._artifact.timebase.control_substeps)
        self._control_step += 1
        return self.snapshot()

    def close(self):
        if not self._closed:
            self._boundary.close()
            self._boundary = None
            self._closed = True
