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

    def reset(self, sample):
        self._begin_reset()
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
        self._boundary.apply_reset_state(EpisodePhysicsState(
            positions, np.zeros_like(initial.qvel), np.zeros_like(initial.qacc),
            targets, np.zeros_like(initial.act),
        ))
        return self._realized(sample)

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

    def control_feedback(self, state):
        from .control import feedback_value
        self._require_reset()
        if not hasattr(self, '_control_binding'):
            raise ValueError('control session admission required')
        if not getattr(self, '_force_feedback_required', False):
            raise ValueError('actuator-force feedback is not admitted for this Controller profile')
        native = self._boundary.read_snapshot(SnapshotRequest(qacc=False, ctrl=False,
            body_pose=False, site_pose=False, actuator_force=True))
        return feedback_value(self, state, native.actuator_force[self._open_actuators[0]])

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
        self._boundary.step(substeps=self._artifact.timebase.control_substeps)
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
