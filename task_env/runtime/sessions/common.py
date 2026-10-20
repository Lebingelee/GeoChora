"""Shared value checks/projection only; no solver abstraction."""
import math
import xml.etree.ElementTree as ET

from ...artifacts import CanonicalStateView, PoseWorld
from ...artifacts.execution import RealizedInitialState
from ...controllers.canonical.contracts import digest


def pose(position, quaternion):
    q = tuple(float(v) for v in quaternion)
    norm = math.sqrt(sum(v*v for v in q))
    if not math.isfinite(norm) or norm < 1e-12:
        raise ValueError('invalid provider quaternion')
    return PoseWorld(tuple(float(v) for v in position), tuple(v/norm for v in q))


def validate_reset_realization(
    sample,
    realized,
    *,
    joint_atol: float = 1.0e-6,
    pose_position_atol: float = 1.0e-6,
    pose_orientation_atol: float = 1.0e-6,
) -> dict[str, object]:
    """Check requested reset values against provider readback before rollout."""

    tolerances = (joint_atol, pose_position_atol, pose_orientation_atol)
    if any(not math.isfinite(value) or value < 0.0 for value in tolerances):
        raise ValueError('realization tolerances must be finite and nonnegative')
    if realized.reset_sample_id != sample.sample_id:
        raise ValueError('realized state does not belong to the requested ResetSample')
    state = realized.measured_state
    missing_joints = sorted(set(sample.joint_position) - set(state.joint_position))
    missing_poses = sorted(set(sample.poses_world) - set(state.pose_world))
    if missing_joints or missing_poses:
        raise ValueError(
            f'reset realization is missing requested state: joints={missing_joints}, poses={missing_poses}'
        )
    joint_errors = {
        name: abs(float(state.joint_position[name]) - float(expected))
        for name, expected in sample.joint_position.items()
    }
    pose_position_errors = {}
    pose_orientation_errors = {}
    for name, expected in sample.poses_world.items():
        actual = state.pose_world[name]
        pose_position_errors[name] = max(
            abs(float(actual.position[index]) - float(expected.position[index]))
            for index in range(3)
        )
        direct = math.sqrt(sum(
            (float(actual.quaternion_wxyz[index]) - float(expected.quaternion_wxyz[index])) ** 2
            for index in range(4)
        ))
        antipodal = math.sqrt(sum(
            (float(actual.quaternion_wxyz[index]) + float(expected.quaternion_wxyz[index])) ** 2
            for index in range(4)
        ))
        pose_orientation_errors[name] = min(direct, antipodal)
    if any(error > joint_atol for error in joint_errors.values()):
        raise ValueError(f'reset joint realization exceeds tolerance: {joint_errors}')
    if any(error > pose_position_atol for error in pose_position_errors.values()):
        raise ValueError(f'reset pose position realization exceeds tolerance: {pose_position_errors}')
    if any(error > pose_orientation_atol for error in pose_orientation_errors.values()):
        raise ValueError(f'reset pose orientation realization exceeds tolerance: {pose_orientation_errors}')
    return {
        'reset_sample_id': sample.sample_id,
        'provider_name': realized.provider_name,
        'joint_max_abs_error': max(joint_errors.values(), default=0.0),
        'pose_position_max_abs_error': max(pose_position_errors.values(), default=0.0),
        'pose_orientation_max_error': max(pose_orientation_errors.values(), default=0.0),
        'tolerances': {
            'joint_atol': joint_atol,
            'pose_position_atol': pose_position_atol,
            'pose_orientation_atol': pose_orientation_atol,
        },
    }


class _SessionValues:
    def _initialize_values(self, artifact, source, provider):
        self._artifact, self._source, self._provider = artifact, source, provider
        self._closed, self._reset_done, self._control_step = False, False, 0
        self._inner_interval_active = False
        root = ET.fromstring(source.scene_source.xml)
        option = root.find('option')
        if option is None or float(option.get('timestep', 'nan')) != artifact.timebase.physics_dt:
            raise ValueError('source/native physics timestep mismatch')

    def _require_open(self):
        if self._closed:
            raise RuntimeError('session is closed')

    def _require_reset(self):
        self._require_open()
        if not self._reset_done:
            raise RuntimeError('reset required before snapshot/step')

    def _validate_sample(self, sample):
        self._require_open()
        if sample.task_artifact_hash != self._artifact.identity_hash:
            raise ValueError('reset sample/Artifact mismatch')
        if set(sample.joint_position) != set(self._source.joints) or set(sample.poses_world) != set(self._source.free_joints):
            raise ValueError('reset semantic bindings mismatch')
        if sample.settle_steps != 0:
            raise ValueError('nonzero settle steps unsupported in P1.2')

    def _state(self, joints, velocities, poses, time):
        return CanonicalStateView('canonical-state-v0', 'SI_right_handed_z_up_wxyz',
                                  self._control_step, float(time), joints, velocities, poses)

    def _realized(self, sample):
        self._reset_done, self._control_step = True, 0
        return RealizedInitialState('realized-initial-state-v0', sample.sample_id,
                                    self._provider, self.snapshot(), 0)

    def step_control_interval(self, held_target, gripper_inner_servo, *, audit=None,
                              diagnostic_readback=None, interval_observer=None, arm_schedule=None):
        """Opt-in arm-ZOH interval with a shared physics-rate gripper update.

        Existing ``step()`` remains unchanged. Providers implement only
        ``_step_physics_once``; this shared method owns the canonical feedback,
        inner-servo, held-arm, and outer-boundary contract.
        """
        from dataclasses import replace
        self._require_reset()
        start = self.snapshot()
        if arm_schedule is not None:
            arm_schedule.begin(held_target)
        if audit is not None:
            audit.begin_inner_interval(start)
        substep_rows = []
        last_target = None
        last_applied = None
        self._inner_interval_active = True
        try:
            for substep_index in range(self._artifact.timebase.control_substeps):
                state = self.snapshot()
                feedback = self.control_feedback(state)
                gripper_target, diagnostics = gripper_inner_servo.inner_gripper_step(state, feedback)
                target = replace(held_target, gripper=gripper_target)
                if arm_schedule is not None:
                    target = arm_schedule.target(target, substep_index, self._artifact.timebase.control_substeps)
                last_applied = self.apply_control(target)
                if arm_schedule is not None:
                    arm_schedule.applied(last_applied)
                if audit is None:
                    self._step_physics_once()
                else:
                    audit.execute_inner_substep(target, self._step_physics_once)
                if interval_observer is not None:
                    interval_observer(substep_index, state, feedback, target, last_applied, diagnostics)
                row = dict(diagnostics)
                row.update({
                    "substep_index": substep_index,
                    "control_step": state.control_step,
                    "simulation_time_s": state.simulation_time,
                    "target_hash": target.identity_hash,
                    "arm_target_hash": digest({
                        "arm_position": dict(target.arm_position),
                        "arm_servo_position": dict(target.arm_servo_position),
                    }),
                    "applied_control": last_applied.to_mapping(),
                })
                if diagnostic_readback is not None:
                    try:
                        row["native_contact_diagnostic"] = diagnostic_readback(self)
                    except Exception as exc:  # diagnostic availability must not affect control
                        row["native_contact_diagnostic"] = {
                            "available": False,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                substep_rows.append(row)
                last_target = target
        finally:
            self._inner_interval_active = False
        self._control_step += 1
        final_state = self.snapshot()
        if audit is not None:
            audit.complete_inner_interval(final_state)
        return final_state, last_target, last_applied, substep_rows
