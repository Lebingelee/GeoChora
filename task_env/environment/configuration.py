"""小范围配置解析工具；配置类型的唯一事实来源在 environment/config.py。"""

from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from pathlib import Path
from typing import Mapping, TypeVar

from .config import (
    ActionConfig,
    AgentConfig,
    AssetConfig,
    EpisodeConfig,
    GripperConfig,
    ObjectConfig,
    ObservationConfig,
    RenderConfig,
    ResolvedEnvConfig,
    RobotConfig,
    RobotControllerConfig,
    RuntimeConfig,
    SceneBuildConfig,
    TaskConfig,
)


T = TypeVar("T")


PUBLIC_ENV_CONFIG_SECTIONS = frozenset(
    {"asset", "runtime", "robot", "action", "observation", "render", "episode"}
)

_LEGACY_GRIPPER_FIELDS = {
    "gripper_controller_kind": "kind",
    "experimental_gripper_hold_force_N": "force_limit_N",
    "experimental_gripper_opening_step_m": "opening_step_m",
    "experimental_gripper_force_deadband_N": "force_deadband_N",
    "experimental_gripper_force_adjust_step_m": "force_adjust_step_m",
}

def update_config(config: T, values: Mapping[str, object] | None) -> T:
    """拒绝未知参数后更新 frozen dataclass。"""

    if not values:
        return config
    allowed = {item.name for item in fields(config)}
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise KeyError(
            f"unknown {type(config).__name__} fields: {', '.join(unknown)}"
        )
    updates: dict[str, object] = {}
    for name, value in values.items():
        current = getattr(config, name)
        if is_dataclass(current) and isinstance(value, Mapping):
            value = update_config(current, value)
        updates[name] = value
    return replace(config, **updates)


def _deep_merge(
    base: Mapping[str, object], override: Mapping[str, object]
) -> dict[str, object]:
    """Merge user config without permitting unknown fields later in the flow."""

    merged = dict(base)
    # Nested gripper configuration replaces legacy task defaults so the
    # resulting mapping cannot contain two owners for the same policy.
    if "gripper" in override:
        for key in _LEGACY_GRIPPER_FIELDS:
            merged.pop(key, None)
    elif any(key in override for key in _LEGACY_GRIPPER_FIELDS):
        merged.pop("gripper", None)
    for key, value in override.items():
        if (
            key == "controller"
            and isinstance(value, Mapping)
            and isinstance(merged.get(key), Mapping)
            and "kind" in value
            and value["kind"] != merged[key].get("kind")
        ):
            # Controller kind determines the valid field set (notably
            # ``reference``).  Replacing it must not inherit a reference from
            # the task default of another controller kind.
            merged[key] = dict(value)
            continue
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_yaml_mapping(path: str | Path) -> Mapping[str, object]:
    """Load a config mapping with PyYAML's safe loader only."""

    config_path = Path(path)
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on installation
        raise RuntimeError(
            "YAML TaskEnv config requires PyYAML; install the project dependencies."
        ) from exc
    with config_path.open("r", encoding="utf-8") as stream:
        loaded = yaml.safe_load(stream)
    if loaded is None:
        return {}
    if not isinstance(loaded, Mapping):
        raise TypeError("TaskEnv YAML config root must be a mapping")
    return dict(loaded)


def _resolve_robot_config(values: Mapping[str, object] | None) -> RobotConfig:
    if not values:
        return RobotConfig()
    allowed = {
        "controller",
        "gripper",
        *_LEGACY_GRIPPER_FIELDS,
    }
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise KeyError(f"unknown RobotConfig fields: {', '.join(unknown)}")
    controller = values.get("controller")
    gripper = values.get("gripper")
    legacy_values = {
        new_name: values[old_name]
        for old_name, new_name in _LEGACY_GRIPPER_FIELDS.items()
        if old_name in values and values[old_name] is not None
    }
    if gripper is not None and legacy_values:
        raise ValueError(
            "robot.gripper cannot be combined with legacy flat gripper fields"
        )
    if gripper is None and legacy_values:
        # Keep existing task YAML and direct mapping callers working while they
        # migrate to the public ``robot.gripper`` shape.
        resolved_gripper = GripperConfig(**legacy_values)
    elif gripper is None:
        resolved_gripper = GripperConfig()
    elif isinstance(gripper, GripperConfig):
        resolved_gripper = gripper
    elif isinstance(gripper, Mapping):
        resolved_gripper = GripperConfig(**dict(gripper))
    else:
        raise TypeError("robot.gripper must be a mapping or GripperConfig")
    if controller is None:
        return RobotConfig(gripper=resolved_gripper)
    if isinstance(controller, RobotControllerConfig):
        return RobotConfig(controller=controller, gripper=resolved_gripper)
    if not isinstance(controller, Mapping):
        raise TypeError("robot.controller must be a mapping or RobotControllerConfig")
    return RobotConfig(
        controller=RobotControllerConfig(**dict(controller)),
        gripper=resolved_gripper,
    )


def overlay_public_env_config(
    base: ResolvedEnvConfig,
    values: Mapping[str, object] | None,
) -> ResolvedEnvConfig:
    """Overlay only user-owned common fields onto task-owned topology."""

    if not values:
        return base
    unknown = sorted(set(values) - PUBLIC_ENV_CONFIG_SECTIONS)
    if unknown:
        raise KeyError(
            "TaskEnv public config cannot override task topology/semantics: "
            + ", ".join(unknown)
        )
    return replace(
        base,
        asset=update_config(base.asset, values.get("asset")),
        runtime=update_config(base.runtime, values.get("runtime")),
        robot=(
            _resolve_robot_config(values["robot"])
            if "robot" in values
            else base.robot
        ),
        action=update_config(base.action, values.get("action")),
        observation=update_config(base.observation, values.get("observation")),
        render=update_config(base.render, values.get("render")),
        episode=update_config(base.episode, values.get("episode")),
    )


def resolve_task_env_config(
    environment_type,
    config: ResolvedEnvConfig | Mapping[str, object] | str | Path | None,
) -> ResolvedEnvConfig:
    """Resolve task defaults plus an optional public YAML/mapping override.

    A pre-resolved config is retained as the compatibility entry point for
    earlier Stage 0--9 callers; mapping/YAML users cannot replace task-owned
    scene, object, agent, or success-definition fields.
    """

    if isinstance(config, ResolvedEnvConfig):
        return config
    base = environment_type.default_config()
    default_path = environment_type.default_config_path()
    merged: dict[str, object] = {}
    if default_path is not None:
        merged = _deep_merge(merged, load_yaml_mapping(default_path))
    if config is not None:
        override = load_yaml_mapping(config) if isinstance(config, (str, Path)) else config
        if not isinstance(override, Mapping):
            raise TypeError("TaskEnv config must be ResolvedEnvConfig, mapping, or YAML path")
        merged = _deep_merge(merged, override)
    return overlay_public_env_config(base, merged)


def resolve_env_config(
    *,
    task_uid: str,
    scene_uid: str,
    agent_uids: tuple[str, ...] = (),
    object_uids: tuple[str, ...] = (),
    success_definition: str = "none",
    asset: Mapping[str, object] | None = None,
    runtime: Mapping[str, object] | None = None,
    robot: Mapping[str, object] | None = None,
    action: Mapping[str, object] | None = None,
    observation: Mapping[str, object] | None = None,
    render: Mapping[str, object] | None = None,
    episode: Mapping[str, object] | None = None,
) -> ResolvedEnvConfig:
    """构建已解析配置，不接受无限制 kwargs 透传。"""

    return ResolvedEnvConfig(
        asset=update_config(AssetConfig(), asset),
        scene=SceneBuildConfig(scene_uid=scene_uid),
        agents=AgentConfig(agent_uids=tuple(agent_uids)),
        objects=ObjectConfig(object_uids=tuple(object_uids)),
        runtime=update_config(RuntimeConfig(), runtime),
        robot=_resolve_robot_config(robot),
        action=update_config(ActionConfig(), action),
        observation=update_config(ObservationConfig(), observation),
        render=update_config(RenderConfig(), render),
        task=TaskConfig(
            task_uid=task_uid,
            success_definition=success_definition,
        ),
        episode=update_config(EpisodeConfig(), episode),
    )
