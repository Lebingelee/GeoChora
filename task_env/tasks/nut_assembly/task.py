"""NutAssembly registration, reset, reward and success semantics."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

import numpy as np

from ...environment import EpisodePhysicsState, RuntimeSnapshot, TaskEvaluation
from ...environment.task_definition import TaskDefinitionBase
from ...assembly import TaskReferences
from ...registry import register_env
from ..base import BaseTaskEnv
from ...utils.rotation import quat_wxyz_to_matrix
from .assets import (
    NUT_CONTACT_MARGIN,
    NUT_HALF_HEIGHT,
    NUT_HANDLE_LOCAL_X,
    PEG_HALF_HEIGHT,
    PEG_X,
    PEG_Y_OFFSET,
    PEG_Z,
    TABLE_TOP_Z,
)


@dataclass(frozen=True)
class NutAssemblyVariantSpec:
    env_id: str
    task_uid: str
    variant: str
    scene_uid: str
    agent_uids: tuple[str, ...]
    object_uids: tuple[str, ...]
    success_definition: str
    scene_profile: str
    sensor_profile: str
    reset_profile: str
    expert_profile: str
    reward_profile: str
    language_templates: tuple[str, ...] = ()


NUT_ASSEMBLY_SQUARE_SPEC = NutAssemblyVariantSpec(
    env_id="nut-assembly-square-v1", task_uid="nut-assembly-square-v1", variant="square",
    scene_uid="tabletop-v1", agent_uids=("panda-v1",),
    object_uids=("square-nut-v1", "square-peg-v1", "round-peg-v1"),
    success_definition="nut_on_square_peg_v1",
    scene_profile="tabletop_panda_square_nut_pegs_v1",
    sensor_profile="state_privileged_optional_base_hand_camera_v1",
    reset_profile="deterministic_hand_above_square_nut_handle_v1",
    expert_profile="public_delta_pose_stage_machine_v1",
    reward_profile="nut_on_square_peg_release_shaping_v1",
    language_templates=("assemble the square nut onto the square peg",),
)
NUT_ASSEMBLY_ENV_ID = NUT_ASSEMBLY_SQUARE_SPEC.env_id
NUT_ASSEMBLY_TASK_UID = NUT_ASSEMBLY_SQUARE_SPEC.task_uid
NUT_ASSEMBLY_VARIANT = NUT_ASSEMBLY_SQUARE_SPEC.variant
NUT_ASSEMBLY_SUCCESS_DEFINITION = NUT_ASSEMBLY_SQUARE_SPEC.success_definition
NUT_ASSEMBLY_SCENE_UID = NUT_ASSEMBLY_SQUARE_SPEC.scene_uid
NUT_ASSEMBLY_AGENT_UIDS = NUT_ASSEMBLY_SQUARE_SPEC.agent_uids
NUT_ASSEMBLY_OBJECT_UIDS = NUT_ASSEMBLY_SQUARE_SPEC.object_uids
NUT_ASSEMBLY_EXPERT_PROFILE = NUT_ASSEMBLY_SQUARE_SPEC.expert_profile
NUT_ASSEMBLY_RESET_PROFILE = NUT_ASSEMBLY_SQUARE_SPEC.reset_profile
NUT_ASSEMBLY_SENSOR_PROFILE = NUT_ASSEMBLY_SQUARE_SPEC.sensor_profile


_PANDA_UID = "panda-v1"
_SQUARE_NUT_UID = "square-nut-v1"
_PEG_TOP_Z = PEG_Z + PEG_HALF_HEIGHT
_TABLE_SEATED_NUT_Z = TABLE_TOP_Z + NUT_HALF_HEIGHT + NUT_CONTACT_MARGIN
_INSERT_XY_TOLERANCE = 0.030
_TABLE_SEATED_NUT_MAX_Z = TABLE_TOP_Z + 3.0 * NUT_HALF_HEIGHT
_INSERT_YAW_TOLERANCE = 0.35
_LIFT_HEIGHT = 0.050
_HOVER_XY_TOLERANCE = 0.050
_GRASP_DISTANCE = 0.090
_GRIPPER_CLOSED_OPENING = 0.045
_GRIPPER_RELEASE_OPENING = 0.065
_GRIPPER_RELEASE_CTRL = 200.0
_RELEASE_DISTANCE = 0.055


def _quat_yaw_wxyz(quat: np.ndarray) -> float:
    rotation = quat_wxyz_to_matrix(quat)
    return float(math.atan2(rotation[1, 0], rotation[0, 0]))


def _square_yaw_error(yaw: float) -> float:
    period = 0.5 * math.pi
    return abs(float((yaw + 0.5 * period) % period - 0.5 * period))


def _distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)))


@dataclass(frozen=True)
class NutAssemblyTaskDefinition(TaskDefinitionBase):
    """Versioned NutAssembly reward/success/release evaluation."""

    references: TaskReferences
    success_definition: str = NUT_ASSEMBLY_SUCCESS_DEFINITION

    def __post_init__(self) -> None:
        if self.success_definition != NUT_ASSEMBLY_SUCCESS_DEFINITION:
            raise ValueError(
                "NutAssemblyTaskDefinition only implements "
                f"{NUT_ASSEMBLY_SUCCESS_DEFINITION!r}, got "
                f"{self.success_definition!r}"
            )
        if _PANDA_UID not in self.references.agents:
            raise KeyError("NutAssemblyTaskDefinition requires panda-v1 references")
        if _SQUARE_NUT_UID not in self.references.objects:
            raise KeyError("NutAssemblyTaskDefinition requires square-nut-v1 references")

    def reset(self, snapshot: RuntimeSnapshot) -> TaskEvaluation:
        return self._evaluate(snapshot)

    def evaluate(
        self,
        previous_snapshot: RuntimeSnapshot,
        action: np.ndarray,
        current_snapshot: RuntimeSnapshot,
    ) -> TaskEvaluation:
        del previous_snapshot, action
        return self._evaluate(current_snapshot)

    def _evaluate(self, snapshot: RuntimeSnapshot) -> TaskEvaluation:
        panda = self.references.agents[_PANDA_UID]
        nut_ref = self.references.objects[_SQUARE_NUT_UID]
        if snapshot.site_xpos is None:
            raise ValueError("NutAssembly evaluation requires site_xpos")
        if snapshot.ctrl is None:
            raise ValueError("NutAssembly evaluation requires ctrl")

        nut_qpos_adr = int(nut_ref.qpos_ids[0])
        nut_qpos = np.asarray(
            snapshot.qpos[nut_qpos_adr : nut_qpos_adr + 7],
            dtype=np.float64,
        )
        if nut_qpos.shape != (7,):
            raise ValueError("SquareNut qpos must contain freejoint pose")
        nut_pos = nut_qpos[:3]
        nut_quat = nut_qpos[3:7]
        handle_pos = nut_pos + quat_wxyz_to_matrix(nut_quat) @ np.array(
            [NUT_HANDLE_LOCAL_X, 0.0, 0.0],
            dtype=np.float64,
        )
        eef_pos = np.asarray(
            snapshot.site_xpos[int(panda.eef_site_id)],
            dtype=np.float64,
        )
        peg_target = np.array([PEG_X, PEG_Y_OFFSET, _TABLE_SEATED_NUT_Z], dtype=np.float64)
        peg_xy_error = float(np.linalg.norm(nut_pos[:2] - peg_target[:2]))
        peg_z_error = float(nut_pos[2] - peg_target[2])
        yaw_error = _square_yaw_error(_quat_yaw_wxyz(nut_quat))
        eef_to_nut_dist = _distance(eef_pos, nut_pos)
        eef_to_handle_dist = _distance(eef_pos, handle_pos)
        gripper_qpos = np.asarray(snapshot.qpos[panda.gripper_qpos_ids], dtype=np.float64)
        gripper_opening = float(np.sum(gripper_qpos))
        gripper_ctrl = float(snapshot.ctrl[int(panda.gripper_actuator_ids[0])])

        reached_nut = eef_to_handle_dist <= _GRASP_DISTANCE
        gripper_closed = gripper_opening <= _GRIPPER_CLOSED_OPENING
        grasped_nut = bool(reached_nut and gripper_closed)
        lifted_nut = bool(nut_pos[2] >= TABLE_TOP_Z + NUT_HALF_HEIGHT + _LIFT_HEIGHT)
        hovered_over_peg = bool(lifted_nut and peg_xy_error <= _HOVER_XY_TOLERANCE)
        aligned_with_peg = bool(peg_xy_error <= _INSERT_XY_TOLERANCE and yaw_error <= _INSERT_YAW_TOLERANCE)
        peg_passed_through_nut_center = bool(nut_pos[2] <= _PEG_TOP_Z - NUT_CONTACT_MARGIN)
        nut_returned_to_table = bool(nut_pos[2] <= _TABLE_SEATED_NUT_MAX_Z)
        inserted_on_peg = bool(
            aligned_with_peg
            and peg_passed_through_nut_center
            and nut_returned_to_table
        )
        gripper_released = bool(
            gripper_opening >= _GRIPPER_RELEASE_OPENING
            or gripper_ctrl >= _GRIPPER_RELEASE_CTRL
        )
        released_nut = bool(
            inserted_on_peg
            and gripper_released
            and eef_to_nut_dist >= _RELEASE_DISTANCE
        )
        task_success = bool(inserted_on_peg and released_nut)

        reward_terms = {
            "reach": 0.10 * float(1.0 - math.tanh(10.0 * eef_to_handle_dist)),
            "grasp": 0.25 if grasped_nut else 0.0,
            "lift": 0.25 if lifted_nut else 0.0,
            "hover": 0.15 if hovered_over_peg else 0.0,
            "insert": 0.15 if inserted_on_peg else 0.0,
            "release": 0.10 if inserted_on_peg and released_nut else 0.0,
            "success": 1.0 if task_success else 0.0,
        }
        metrics = {
            "reached_nut": bool(reached_nut),
            "grasped_nut": bool(grasped_nut),
            "lifted_nut": bool(lifted_nut),
            "hovered_over_peg": bool(hovered_over_peg),
            "aligned_with_peg": bool(aligned_with_peg),
            "peg_passed_through_nut_center": bool(peg_passed_through_nut_center),
            "nut_returned_to_table": bool(nut_returned_to_table),
            "inserted_on_peg": bool(inserted_on_peg),
            "gripper_released": bool(gripper_released),
            "released_nut": bool(released_nut),
            "task_success": bool(task_success),
            "nut_x": float(nut_pos[0]),
            "nut_y": float(nut_pos[1]),
            "nut_z": float(nut_pos[2]),
            "table_seated_nut_max_z": float(_TABLE_SEATED_NUT_MAX_Z),
            "peg_xy_error": float(peg_xy_error),
            "peg_z_error": float(peg_z_error),
            "yaw_error": float(yaw_error),
            "eef_to_nut_dist": float(eef_to_nut_dist),
            "eef_to_handle_dist": float(eef_to_handle_dist),
            "gripper_opening": float(gripper_opening),
            "gripper_ctrl": float(gripper_ctrl),
            "success_definition": self.success_definition == NUT_ASSEMBLY_SUCCESS_DEFINITION,
        }
        return TaskEvaluation(
            reward=sum(reward_terms.values()),
            success=task_success,
            failure=False,
            metrics=metrics,
            reward_terms=reward_terms,
        )


_ARM_DOF = 7
_INITIAL_ARM_ALIGN_STEPS = 80
_INITIAL_ARM_ALIGN_TOLERANCE = 0.015
_INITIAL_HAND_SITE_TARGET_FROM_HANDLE = np.array([0.0, 0.0, 0.12], dtype=np.float64)
_GRIPPER_TARGET_ROTATION = np.diag([1.0, -1.0, -1.0]).astype(np.float64)
_IK_DAMPING = 2.0e-2
_IK_POSITION_GAIN = 0.9
_IK_MAX_DELTA_Q = 0.10
_IK_ROTATION_GAIN = 0.65
_IK_ROTATION_ROW_WEIGHT = 0.22


def _apply_episode_state_to_solver(solver: object, state: EpisodePhysicsState) -> None:
    if state.qpos.size:
        solver.write_qpos(state.qpos)
    if state.qvel.size:
        solver.write_qvel(state.qvel)
        solver.write_qacc(state.qacc)
    if state.ctrl.size:
        solver.write_ctrl(state.ctrl)
        solver.write_act(state.act)
    solver.synchronize_kinematic_state(update_site_jacobians=False)


def _episode_state_from_solver(solver: object) -> EpisodePhysicsState:
    n_actuators = int(getattr(solver, "n_actuators", 0))
    act = np.asarray(solver.read_act(), dtype=np.float32).copy() if n_actuators else np.zeros(0, dtype=np.float32)
    return EpisodePhysicsState(
        qpos=np.asarray(solver.read_qpos(), dtype=np.float32).copy(),
        qvel=np.asarray(solver.read_qvel(), dtype=np.float32).copy(),
        qacc=np.asarray(solver.read_qacc(), dtype=np.float32).copy(),
        ctrl=np.asarray(solver.read_ctrl(), dtype=np.float32).copy(), act=act,
    )


def _arm_ctrl_limits(scene_model: object) -> np.ndarray:
    joint_data = scene_model.joint_data
    ctrlrange = np.asarray(joint_data.get("actuator_ctrlrange", np.zeros((0, 2))), dtype=np.float64)
    if ctrlrange.shape[0] < _ARM_DOF:
        return np.tile(np.array([-np.inf, np.inf], dtype=np.float64), (_ARM_DOF, 1))
    limits = ctrlrange[:_ARM_DOF].copy()
    limited = np.asarray(joint_data.get("actuator_ctrllimited", np.ones(ctrlrange.shape[0])), dtype=np.int32)
    for actuator_id in range(min(_ARM_DOF, limited.shape[0])):
        if int(limited[actuator_id]) == 0:
            limits[actuator_id] = (-np.inf, np.inf)
    return limits


class NutAssemblyResetSampler:
    """Resolve the deterministic NutAssembly initial alignment at assembly time."""

    def resolve_initial_state(self, *, solver: object, compiled_scene) -> EpisodePhysicsState:
        references = compiled_scene.references
        if "panda-v1" not in references.agents or "square-nut-v1" not in references.objects:
            return compiled_scene.initial_state
        _apply_episode_state_to_solver(solver, compiled_scene.initial_state)
        agent_ref = references.agents["panda-v1"]
        nut_ref = references.objects["square-nut-v1"]
        site_id, nut_qpos_adr = int(agent_ref.eef_site_id), int(nut_ref.qpos_ids[0])
        arm_ctrl_limits = _arm_ctrl_limits(compiled_scene.scene_model)
        qpos, ctrl = np.asarray(solver.read_qpos(), dtype=np.float32).copy(), np.asarray(solver.read_ctrl(), dtype=np.float32).copy()
        for _iteration in range(_INITIAL_ARM_ALIGN_STEPS):
            nut_qpos = np.asarray(solver.read_qpos(), dtype=np.float64)[nut_qpos_adr:nut_qpos_adr + 7]
            handle_position = nut_qpos[:3] + quat_wxyz_to_matrix(nut_qpos[3:7]) @ np.array([NUT_HANDLE_LOCAL_X, 0.0, 0.0])
            solver.refresh_site_jacobians()
            current_position = np.asarray(solver.read_site_world_pos()[site_id], dtype=np.float64)
            current_rotation = quat_wxyz_to_matrix(np.asarray(solver.read_site_world_quat()[site_id], dtype=np.float64))
            jacp = np.asarray(solver.read_site_jacp()[site_id, agent_ref.arm_dof_ids], dtype=np.float64).T
            jacr = np.asarray(solver.read_site_jacr()[site_id, agent_ref.arm_dof_ids], dtype=np.float64).T
            position_error = handle_position + _INITIAL_HAND_SITE_TARGET_FROM_HANDLE - current_position
            from ...utils.rotation import rotation_vector_error
            rotation_error = rotation_vector_error(current_rotation, _GRIPPER_TARGET_ROTATION)
            jacobian = np.vstack([jacp, _IK_ROTATION_ROW_WEIGHT * jacr])
            error = np.concatenate([position_error, _IK_ROTATION_ROW_WEIGHT * _IK_ROTATION_GAIN * rotation_error])
            delta_q = jacobian.T @ np.linalg.solve(jacobian @ jacobian.T + (_IK_DAMPING * _IK_DAMPING) * np.eye(6), error)
            arm_target = np.clip(qpos[agent_ref.arm_qpos_ids].astype(np.float64) + _IK_POSITION_GAIN * np.clip(delta_q, -_IK_MAX_DELTA_Q, _IK_MAX_DELTA_Q), arm_ctrl_limits[:_ARM_DOF, 0], arm_ctrl_limits[:_ARM_DOF, 1])
            qpos[agent_ref.arm_qpos_ids] = arm_target.astype(np.float32)
            ctrl[agent_ref.arm_actuator_ids] = arm_target.astype(np.float32)
            if agent_ref.gripper_qpos_ids.size:
                qpos[agent_ref.gripper_qpos_ids] = np.float32(0.04)
            if agent_ref.gripper_actuator_ids.size:
                ctrl[agent_ref.gripper_actuator_ids] = np.float32(agent_ref.ctrl_range[agent_ref.gripper_actuator_ids[0], 1])
            solver.write_qpos(qpos); solver.write_ctrl(ctrl); solver.synchronize_kinematic_state(update_site_jacobians=False)
            if float(np.linalg.norm(position_error)) <= _INITIAL_ARM_ALIGN_TOLERANCE and float(np.linalg.norm(rotation_error)) <= 0.20:
                break
        if int(getattr(solver, "n_actuators", 0)) > 0:
            solver.write_act(np.zeros(int(solver.n_actuators), dtype=np.float32))
        solver.synchronize_kinematic_state(update_site_jacobians=False)
        return _episode_state_from_solver(solver)


@register_env()
class NutAssemblyEnv(BaseTaskEnv):
    variant_spec = NUT_ASSEMBLY_SQUARE_SPEC
    uid, task_uid, scene_uid = NUT_ASSEMBLY_ENV_ID, NUT_ASSEMBLY_TASK_UID, NUT_ASSEMBLY_SCENE_UID
    agent_uids, object_uids = NUT_ASSEMBLY_AGENT_UIDS, NUT_ASSEMBLY_OBJECT_UIDS
    success_definition, sensor_profile, reset_profile = NUT_ASSEMBLY_SUCCESS_DEFINITION, NUT_ASSEMBLY_SENSOR_PROFILE, NUT_ASSEMBLY_RESET_PROFILE

    @classmethod
    def default_config_path(cls) -> Path:
        del cls
        return Path(__file__).resolve().with_name("default.yaml")

    def create_scene_composer(self):
        from .assets import NutAssemblySceneComposer
        return NutAssemblySceneComposer()

    def create_reset_sampler(self):
        return NutAssemblyResetSampler()

    def create_task_definition(self, compiled_scene):
        return NutAssemblyTaskDefinition(references=compiled_scene.references, success_definition=self.config.task.success_definition)


__all__ = [
    "NUT_ASSEMBLY_AGENT_UIDS", "NUT_ASSEMBLY_ENV_ID", "NUT_ASSEMBLY_EXPERT_PROFILE",
    "NUT_ASSEMBLY_OBJECT_UIDS", "NUT_ASSEMBLY_RESET_PROFILE", "NUT_ASSEMBLY_SCENE_UID",
    "NUT_ASSEMBLY_SENSOR_PROFILE", "NUT_ASSEMBLY_SQUARE_SPEC", "NUT_ASSEMBLY_SUCCESS_DEFINITION",
    "NUT_ASSEMBLY_TASK_UID", "NutAssemblyEnv", "NutAssemblyResetSampler", "NutAssemblyTaskDefinition",
]
