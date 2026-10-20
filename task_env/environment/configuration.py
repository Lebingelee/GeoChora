"""小范围配置解析工具；配置类型的唯一事实来源在 environment/config.py。"""

from __future__ import annotations

from dataclasses import asdict, fields, is_dataclass, replace
import hashlib
import json
from pathlib import Path
from typing import Mapping, TypeVar

from .config import (
    ActionConfig,
    AgentConfig,
    AssetConfig,
    EpisodeConfig,
    ExecutionPlan,
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
    runtime_values = values.get("runtime")
    if isinstance(runtime_values, Mapping):
        layout = str(runtime_values.get("batch_physics_layout", "")).strip().lower()
        if layout == "static_template":
            raise ValueError(
                "runtime.batch_physics_layout='static_template' is retired; "
                "use 'merged_scene'. No runtime substitution is performed."
            )
        if "static_template" in runtime_values:
            raise ValueError(
                "runtime.static_template is retired with the static-template physics "
                "implementation; remove it and use 'merged_scene'. No runtime "
                "substitution is performed."
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
    earlier Stage 0--9 callers and is authoritative as supplied. Otherwise task
    defaults are deep-merged with the caller override (caller values win), then
    only public environment-owned sections are overlaid. Mapping/YAML users
    cannot replace task-owned scene, object, agent, or success-definition fields.
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


def _identity_value(value):
    """Convert resolved configuration values to deterministic JSON values."""

    if is_dataclass(value):
        return _identity_value(asdict(value))
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("resolved configuration identity requires string mapping keys")
        return {key: _identity_value(value[key]) for key in sorted(value)}
    if isinstance(value, (tuple, list)):
        return [_identity_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    # NumPy arrays/scalars are used by a small number of direct configuration
    # callers. Convert their data values without importing NumPy on the public
    # configuration path.
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return _identity_value(tolist())
    item = getattr(value, "item", None)
    if callable(item):
        return _identity_value(item())
    raise TypeError(
        "resolved configuration identity only supports data values; "
        f"got {type(value).__name__}"
    )


def _resolved_config_identity(config: ResolvedEnvConfig) -> str:
    payload = json.dumps(
        _identity_value(asdict(config)),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def resolve_execution_plan(
    environment_type,
    config: ResolvedEnvConfig,
    *,
    agents=(),
    render_mode=None,
    state_requirements=None,
) -> ExecutionPlan:
    """Build the current generic route's immutable static execution plan.

    This performs config-level admission only. It deliberately does not inspect
    provider manifests, materialize native resources, or claim reset
    realization. Selected-reference tasks retain their separate strict config
    route in ``SelectedReferenceEnv.from_reference_config``.
    """

    if not isinstance(config, ResolvedEnvConfig):
        raise TypeError("static execution planning requires a ResolvedEnvConfig")
    agent_uids = tuple(
        str(getattr(agent, "uid", agent)) for agent in (agents or config.agents.agent_uids)
    )
    if len(agent_uids) > 1:
        from .types import StageUnavailableError

        raise StageUnavailableError(
            "current BaseTaskEnv statically admits at most one agent; "
            "multi-agent materialization is not implemented"
        )

    controller_selections: tuple[tuple[str, str, str | None], ...] = ()
    if "panda-v1" in agent_uids:
        controller = config.robot.controller
        if controller is None:
            from .types import StageUnavailableError

            raise StageUnavailableError(
                "robot TaskEnv requires an explicit robot.controller config"
            )
        if controller.kind not in {"absolute_joint", "absolute_pose", "delta_pose"}:
            from .types import StageUnavailableError

            raise StageUnavailableError(
                f"unsupported robot controller kind {controller.kind!r}"
            )
        controller_selections = (
            ("panda-v1", controller.kind, controller.reference),
        )

    if state_requirements is not None:
        from ..artifacts.state import StateRequirements

        if not isinstance(state_requirements, StateRequirements):
            raise TypeError("state_requirements must be StateRequirements")

    normalized_render_mode = None
    if render_mode is not None:
        from ..render.base.contracts import normalize_render_mode

        normalized_render_mode = normalize_render_mode(render_mode).value

    environment_uid = str(
        getattr(environment_type, "uid", environment_type.__qualname__)
    )
    camera_owner = (
        "task_env.observations.capture.CameraObservationProvider"
        if config.render.camera_obs
        else "none"
    )
    ui_owner = (
        "task_env.render.providers.single.TaskEnvRenderProvider"
        if normalized_render_mode is not None
        else "none"
    )
    return ExecutionPlan(
        schema_version="execution-plan-v0",
        environment_uid=environment_uid,
        task_uid=config.task.task_uid,
        scene_uid=config.scene.scene_uid,
        agent_uids=agent_uids,
        object_uids=config.objects.object_uids,
        physics_provider="geophys",
        backend=config.runtime.backend,
        physics_dt=config.runtime.physics_dt,
        control_substeps=config.runtime.control_substeps,
        render_mode=normalized_render_mode,
        render_backend=config.render.backend,
        controller_selections=controller_selections,
        resource_owner_identities=(
            ("environment", f"{environment_type.__module__}.{environment_type.__qualname__}"),
            ("episode_lifecycle", "task_env.environment.lifecycle.SingleTaskLifecycleAdapter"),
            ("physics_boundary", "task_env.runtime.GeoPhysRuntimeBoundary"),
            ("camera_capture", camera_owner),
            ("ui_render", ui_owner),
        ),
        configuration_identity=_resolved_config_identity(config),
        state_requirements=state_requirements,
    )


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
