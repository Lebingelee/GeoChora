"""TaskEnv 冻结的环境 metadata 契约。"""

from __future__ import annotations

from dataclasses import dataclass
import math
from collections.abc import Mapping
import numpy as np
from typing import Any

from .config import CameraSpec, ResolvedEnvConfig
from .types import ActionModeSpec, ExternalActionContract, ObservationSchema


@dataclass(frozen=True)
class TaskEnvMetadata:
    env_name: str
    task_name: str
    task_version: str
    scene_uid: str
    agent_uids: tuple[str, ...]
    object_uids: tuple[str, ...]
    physics_engine: str
    physics_dt: float
    control_substeps: int
    external_action: ExternalActionContract | ActionModeSpec
    camera_specs: tuple[CameraSpec, ...]
    success_definition: str
    asset_version: str


def _action_schema(contract: ExternalActionContract | ActionModeSpec) -> dict[str, Any]:
    if isinstance(contract, ActionModeSpec):
        return {
            "schema_id": contract.schema_id,
            "schema_version": contract.schema_version,
            "controller_kind": contract.controller_kind,
            "reference": contract.reference,
            "reference_identity": contract.reference_identity,
            "dimension": contract.dimension,
            "components": contract.components,
            "low": contract.low,
            "high": contract.high,
            "translation_unit": contract.translation_unit,
            "max_translation_delta_m": contract.max_translation_delta_m,
            "max_rotation_delta_rad": contract.max_rotation_delta_rad,
            "max_absolute_rotvec_angle_rad": contract.max_absolute_rotvec_angle_rad,
            "rotation_representation": contract.rotation_representation,
            "quaternion_convention": contract.quaternion_convention,
            "gripper_convention": contract.gripper_convention,
            "joint_order": contract.joint_order,
            "controller_backend": contract.backend_provenance,
            "actuator_control_mode": "position",
        }
    return {
        "schema_id": contract.schema_id,
        "schema_version": contract.schema_version,
        # Native non-arm actions are public task actions, not controller
        # targets.  Keep the existing scalar ``low``/``high`` fields for
        # compatibility and add an explicit shape/dtype/bounds projection so
        # metadata consumers do not have to infer the Box contract.
        "kind": contract.mode,
        "mode": contract.mode,
        "dimension": contract.dimension,
        "shape": (contract.dimension,),
        "components": contract.components,
        "dtype": "float32",
        "low": contract.low,
        "high": contract.high,
        "bounds": {
            "low": tuple(float(contract.low) for _ in range(contract.dimension)),
            "high": tuple(float(contract.high) for _ in range(contract.dimension)),
        },
        "unit": contract.unit,
        "actuator_interpretation": contract.actuator_interpretation,
        "task_family": contract.task_family,
        "tree": {
            "root": "action",
            "leaves": tuple(f"action/{component}" for component in contract.components),
        },
        "controller_backend": contract.controller_backend,
        "actuator_control_mode": contract.actuator_control_mode,
        "gripper_convention": contract.gripper_convention,
        "gripper_close_value": contract.gripper_close_value,
        "gripper_open_value": contract.gripper_open_value,
    }


def observation_schema_metadata(schema: ObservationSchema | None) -> dict[str, Any]:
    """将 observation schema 转成 Gym checker 友好的只读元数据。"""

    if schema is None:
        return {
            "version": "",
            "groups": (),
            "leaf_fields": (),
            "group_semantics": {},
            "quaternion_convention": "wxyz",
        }
    group_semantics = {
        "state": "public task observation available to the policy",
        "privileged_state": "task-defined privileged/evaluation observation",
        # Preserve this historical namespace; it is not an alias for the
        # privileged_state group.
        "private_state": "legacy private observation namespace; meaning is unchanged",
        "rgb": "camera image modality",
        "depth": "camera depth modality",
        "vision": "legacy camera image modality group",
    }
    return {
        "version": schema.version,
        "groups": schema.field_names,
        "group_semantics": {
            group: group_semantics.get(group, "task-defined observation group")
            for group in schema.field_names
        },
        "leaf_fields": schema.leaf_field_names,
        "leaf_specs": tuple(
            {
                "path": field.name,
                "shape": field.shape,
                "dtype": field.dtype,
                "semantic": field.semantic,
                "unit": field.unit,
                "frame": field.frame,
                "time_reference": field.time_reference,
                "required": field.required,
                "visibility": _observation_visibility(field.name),
            }
            for field in schema.fields
        ),
        "quaternion_convention": schema.quaternion_convention,
    }


def _observation_visibility(path: str) -> str:
    group = str(path).split(".", 1)[0]
    return {
        "state": "public",
        "privileged_state": "privileged",
        "private_state": "private",
        "rgb": "camera_modality",
        "depth": "camera_modality",
        "vision": "camera_modality",
    }.get(group, "task_defined")


def task_info_schema_metadata() -> dict[str, Any]:
    """Describe stable reset/step facts, required feedback and optional diagnostics."""

    fields: list[dict[str, Any]] = []

    def add(
        path: str,
        dtype: str,
        shape: tuple[int, ...] | str | None,
        *,
        phases: tuple[str, ...] = ("reset", "step"),
        unit: str = "not_applicable",
        frame: str = "not_applicable",
        category: str = "execution_fact",
        required: bool = True,
        nullable: bool = False,
        time_reference: str = "current_reset_or_step_boundary",
    ) -> None:
        fields.append(
            {
                "path": path,
                "dtype": dtype,
                "shape": shape,
                "unit": unit,
                "frame": frame,
                "time_reference": time_reference,
                "required": required,
                "nullable": nullable,
                "category": category,
                "phases": phases,
            }
        )

    add("seed", "int|null", (), phases=("reset",), nullable=True, time_reference="reset_request")
    add("reset_parameters", "mapping[str,value]", None, phases=("reset",))
    add("task_uid", "str", (), phases=("reset",))
    add("stage", "str", (), phases=("reset",))
    add("is_success", "bool", ())
    add("elapsed_steps", "int64", (), unit="control_step", time_reference="current_boundary")
    add("task_metrics", "mapping[str,task_defined_scalar]", None, unit="task_defined")
    add("reward_terms", "mapping[str,task_defined_scalar]", None, unit="task_defined")
    add("task_reward", "float64", (), unit="task_defined_reward")
    add("task_failure", "task_defined|null", None, nullable=True)
    add("success_definition", "str", ())
    add("observation_schema", "ObservationSchema", None, category="schema_reference")
    add("resolved_control_metadata", "mapping", None, phases=("reset",), category="schema_reference")
    add("simulation_time_s", "float64", (), unit="s", time_reference="current_boundary")

    add("action", "mapping", None, phases=("step",), category="required_feedback")
    for name in (
        "requested_action",
        "external_action",
        "controller_target",
        "requested_ctrl",
        "applied_ctrl",
        "universal_action",
    ):
        add(
            name,
            "numeric_array (shape/dtype from action or control owner)",
            "declared by action/controller schema",
            phases=("step",),
            category="required_feedback",
            time_reference="control_interval_applied_at_current_boundary",
        )
    for name in ("requested", "external", "controller_target", "requested_ctrl", "applied_ctrl", "universal_action"):
        add(
            f"action.{name}",
            "numeric_array (shape/dtype from action or control owner)",
            "declared by action/controller schema",
            phases=("step",),
            category="required_feedback",
            time_reference="control_interval_applied_at_current_boundary",
        )
    add("action.mode", "str", (), phases=("step",), category="required_feedback")

    for path in (
        "action.clipped",
        "action.action_clipped",
        "action.ctrl_clipped",
        "action_clipped",
        "ctrl_clipped",
    ):
        add(
            path,
            "bool",
            (),
            phases=("step",),
            category="optional_diagnostic",
            required=False,
        )
    add(
        "camera_capture",
        "mapping",
        None,
        category="optional_capture_reference",
        required=False,
    )
    return {
        "version": "task-env-info-v1",
        "requiredness": "required fields must be present; unavailable required values fail explicitly",
        "fields": tuple(fields),
    }


def validate_task_info(info: Mapping[str, Any], *, phase: str) -> None:
    """Fail closed when required public info or timebase data is absent/invalid."""

    if phase not in {"reset", "step"}:
        raise ValueError("TaskEnv info phase must be 'reset' or 'step'")
    if not isinstance(info, Mapping):
        raise TypeError(f"{phase} info must be a mapping")
    schema = task_info_schema_metadata()
    required_paths = tuple(
        field["path"]
        for field in schema["fields"]
        if field["required"] and phase in field["phases"]
    )
    field_by_path = {field["path"]: field for field in schema["fields"]}
    for path in required_paths:
        value: Any = info
        for part in path.split("."):
            if not isinstance(value, Mapping) or part not in value:
                raise ValueError(f"{phase} info is missing required field {path}")
            value = value[part]
        field_spec = field_by_path[path]
        if value is None and not field_spec["nullable"]:
            raise ValueError(f"{phase} info required field {path} is unavailable")
    for field_spec in schema["fields"]:
        path = field_spec["path"]
        if phase not in field_spec["phases"]:
            continue
        value: Any = info
        present = True
        for part in path.split("."):
            if not isinstance(value, Mapping) or part not in value:
                present = False
                break
            value = value[part]
        if not present:
            continue
        dtype = field_spec["dtype"]
        if dtype == "bool" and not isinstance(value, (bool, np.bool_)):
            raise TypeError(f"{phase} info {path} must be boolean")
        if dtype == "str" and not isinstance(value, str):
            raise TypeError(f"{phase} info {path} must be a string")
        if dtype == "int64":
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
                raise TypeError(f"{phase} info {path} must be an integer")
        if dtype == "int|null" and value is not None:
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
                raise TypeError(f"{phase} info {path} must be an integer or null")
        if dtype == "float64":
            try:
                number = float(value)
            except (TypeError, ValueError) as error:
                raise TypeError(f"{phase} info {path} must be numeric") from error
            if not math.isfinite(number):
                raise ValueError(f"{phase} info {path} must be finite")
        if dtype == "mapping" or dtype.startswith("mapping["):
            if not isinstance(value, Mapping):
                raise TypeError(f"{phase} info {path} must be a mapping")
        if dtype == "ObservationSchema" and not isinstance(value, ObservationSchema):
            raise TypeError(f"{phase} info {path} must be an ObservationSchema")
        if dtype.startswith("numeric_array"):
            array = np.asarray(value)
            if array.dtype.kind not in "fiu" or not np.isfinite(array).all():
                raise TypeError(f"{phase} info {path} must be a finite numeric array")

    try:
        simulation_time_s = float(info["simulation_time_s"])
    except (TypeError, ValueError) as error:
        raise ValueError(f"{phase} info simulation_time_s must be finite seconds") from error
    if not math.isfinite(simulation_time_s):
        raise ValueError(f"{phase} info simulation_time_s must be finite seconds")
    try:
        elapsed_steps = float(info["elapsed_steps"])
    except (TypeError, ValueError) as error:
        raise ValueError(f"{phase} info elapsed_steps must be a nonnegative integer") from error
    if (
        isinstance(info["elapsed_steps"], bool)
        or not math.isfinite(elapsed_steps)
        or not elapsed_steps.is_integer()
        or elapsed_steps < 0
    ):
        raise ValueError(f"{phase} info elapsed_steps must be a nonnegative integer")


def conversion_capability_metadata(
    schema: ObservationSchema | None,
    external_action: ExternalActionContract | ActionModeSpec,
) -> dict[str, Any]:
    """Describe which offline control conversions have complete evidence.

    This is a declarative recording contract.  It neither performs conversion
    nor changes online controller behaviour.
    """

    if isinstance(external_action, ExternalActionContract) and external_action.mode != "no_op":
        return {
            "schema_version": "task-env-conversion-capabilities-v1",
            "evidence": {
                "universal_action": {
                    "path": "universal_action",
                    "available": True,
                    "schema_id": external_action.schema_id,
                    "schema_version": external_action.schema_version,
                },
            "resolved_universal_joint_target": {
                "path": "universal_action",
                "available": False,
            },
            },
            "absolute_pose": {
                "action_target_available": False,
                "to_joint_position": False,
                "to_delta_ee": False,
                "to_delta_base": False,
            },
        }

    if isinstance(external_action, ExternalActionContract) and external_action.mode == "no_op":
        return {
            "schema_version": "task-env-conversion-capabilities-v1",
            "evidence": {
                "universal_action": {
                    "path": "universal_action",
                    "available": True,
                    "schema_id": external_action.schema_id,
                    "schema_version": external_action.schema_version,
                },
            },
            "absolute_pose": {
                "action_target_available": False,
                "to_joint_position": False,
                "to_delta_ee": False,
                "to_delta_base": False,
            },
        }

    paths = frozenset(() if schema is None else schema.leaf_field_names)
    has_ee_world = "state.ee_pose_world" in paths
    has_base_world = "private_state.robot_base_pose_world" in paths
    is_absolute_pose = (
        isinstance(external_action, ActionModeSpec)
        and external_action.controller_kind == "absolute_pose"
    )
    return {
        "schema_version": "task-env-conversion-capabilities-v1",
        "evidence": {
            "ee_pose_world": {
                "path": "state.ee_pose_world",
                "available": has_ee_world,
            },
            "base_pose_world": {
                "path": "private_state.robot_base_pose_world",
                "available": has_base_world,
            },
            "resolved_universal_joint_target": {
                "path": "universal_action",
                "available": True,
            },
        },
        "absolute_pose": {
            "action_target_available": is_absolute_pose,
            "to_joint_position": is_absolute_pose,
            "to_delta_ee": is_absolute_pose and has_ee_world,
            "to_delta_base": is_absolute_pose and has_ee_world and has_base_world,
        },
    }


def camera_spec_metadata(spec: CameraSpec) -> dict[str, Any]:
    return {
        "name": spec.name,
        "width": spec.width,
        "height": spec.height,
        "rgb": spec.rgb,
        "depth": spec.depth,
        "rgb_layout": spec.rgb_layout,
        "rgb_dtype": spec.rgb_dtype,
        "frame": spec.frame,
        "parent": spec.parent,
        "position": spec.position,
        "quaternion_wxyz": spec.quaternion_wxyz,
        "fov_y": spec.fov_y,
        "near": spec.near,
        "far": spec.far,
    }


def gym_metadata_dict(
    metadata: TaskEnvMetadata,
    *,
    observation_schema: ObservationSchema | None = None,
    stage: str = "stage4_gym_contract",
) -> dict[str, Any]:
    """构建 ``gymnasium.Env.metadata`` 使用的普通 dict。"""

    action_schema = _action_schema(metadata.external_action)
    external_action = metadata.external_action
    if isinstance(external_action, ActionModeSpec):
        external_action_mode = external_action.controller_kind
        controller_backend = external_action.backend_provenance
    else:
        external_action_mode = external_action.mode
        controller_backend = external_action.controller_backend
    obs_schema = observation_schema_metadata(observation_schema)
    conversion_capabilities = conversion_capability_metadata(
        observation_schema,
        external_action,
    )
    record_state_keys = tuple(
        field.split(".", 1)[1]
        for field in obs_schema["leaf_fields"]
        if field.startswith("state.")
    )
    privileged_state_keys = tuple(
        field.split(".", 1)[1]
        for field in obs_schema["leaf_fields"]
        if field.startswith("privileged_state.")
    )
    public_metadata = {
        "render_modes": [],
        "stage": stage,
        "env_name": metadata.env_name,
        "task_name": metadata.task_name,
        "task_version": metadata.task_version,
        "scene_uid": metadata.scene_uid,
        "agent_uids": metadata.agent_uids,
        "object_uids": metadata.object_uids,
        "physics_engine": metadata.physics_engine,
        "physics_dt": metadata.physics_dt,
        "control_substeps": metadata.control_substeps,
        "control_frequency": 1.0 / (metadata.physics_dt * metadata.control_substeps),
        "external_action_mode": external_action_mode,
        "controller_backend": controller_backend,
        "actuator_control_mode": (
            "position"
            if isinstance(external_action, ActionModeSpec)
            else external_action.actuator_control_mode
        ),
        "action_schema": action_schema,
        "observation_schema": obs_schema,
        "info_schema": task_info_schema_metadata(),
        "conversion_capabilities": conversion_capabilities,
        "record_state_keys": record_state_keys,
        "privileged_state_keys": privileged_state_keys,
        "camera_names": tuple(spec.name for spec in metadata.camera_specs),
        "camera_specs": tuple(camera_spec_metadata(spec) for spec in metadata.camera_specs),
        "success_definition": metadata.success_definition,
        "asset_version": metadata.asset_version,
    }
    if isinstance(external_action, ExternalActionContract) and external_action.mode != "no_op":
        public_metadata["universal_action_schema"] = {
            "schema_id": external_action.schema_id,
            "schema_version": external_action.schema_version,
            "kind": external_action.mode,
            "dimension": external_action.dimension,
            "shape": (external_action.dimension,),
            "components": external_action.components,
            "dtype": "float32",
            "bounds": {
                "low": tuple(
                    float(external_action.low)
                    for _ in range(external_action.dimension)
                ),
                "high": tuple(
                    float(external_action.high)
                    for _ in range(external_action.dimension)
                ),
            },
            "unit": external_action.unit,
            "actuator_interpretation": external_action.actuator_interpretation,
            "task_family": external_action.task_family,
            "provenance": "task_env_native_action_adapter",
        }
    elif isinstance(external_action, ExternalActionContract):
        public_metadata["universal_action_schema"] = {
            "schema_id": external_action.schema_id,
            "schema_version": external_action.schema_version,
            "kind": external_action.mode,
            "dimension": external_action.dimension,
            "shape": (external_action.dimension,),
            "components": external_action.components,
            "dtype": "float32",
            "bounds": {"low": (), "high": ()},
            "unit": external_action.unit,
            "actuator_interpretation": external_action.actuator_interpretation,
            "task_family": external_action.task_family,
            "provenance": "task_env_noop_identity_adapter",
        }
    else:
        public_metadata["universal_action_schema"] = {
            "version": "panda-universal-action-v1",
            "dimension": 8,
            "components": (
                "joint1", "joint2", "joint3", "joint4", "joint5", "joint6", "joint7", "gripper"
            ),
            "arm_joint_order": (
                "joint1", "joint2", "joint3", "joint4", "joint5", "joint6", "joint7"
            ),
            "gripper_convention": "normalized_signed_scalar",
            "dtype": "float32",
            "provenance": "action_adapter_resolved_joint_target_before_position_servo",
        }
    return public_metadata


def build_stage0_metadata(
    env_name: str,
    config: ResolvedEnvConfig,
) -> TaskEnvMetadata:
    """从 resolved config 构建只读 metadata，不访问 runtime。"""

    task_name, _, task_version = config.task.task_uid.partition("-v")
    return TaskEnvMetadata(
        env_name=env_name,
        task_name=task_name,
        task_version=task_version or "1",
        scene_uid=config.scene.scene_uid,
        agent_uids=config.agents.agent_uids,
        object_uids=config.objects.object_uids,
        physics_engine="GeoPhys",
        physics_dt=config.runtime.physics_dt,
        control_substeps=config.runtime.control_substeps,
        external_action=(
            ActionModeSpec.from_controller_config(config.robot.controller)
            if config.robot.controller is not None
            else ExternalActionContract.for_mode("no_op")
        ),
        camera_specs=config.render.cameras,
        success_definition=config.task.success_definition,
        asset_version=config.asset.asset_version,
    )
