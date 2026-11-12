"""小范围配置解析工具；配置类型的唯一事实来源在 environment/config.py。"""

from __future__ import annotations

from dataclasses import asdict, fields, is_dataclass, replace
import hashlib
import json
from pathlib import Path
from typing import Mapping, TypeVar

from ..artifacts.contracts import ExecutionSpecV2, RendererSelectionV1

from .config import (
    ActionConfig,
    AgentConfig,
    AssetConfig,
    ControlConfig,
    EpisodeConfig,
    ExecutionPlan,
    GripperConfig,
    ObjectConfig,
    ObservationConfig,
    RenderConfig,
    ResolvedEnvConfig,
    ResolvedSelectedConfig,
    RobotConfig,
    RobotControllerConfig,
    RuntimeConfig,
    SceneBuildConfig,
    TaskConfig,
)


T = TypeVar("T")

_CORE_SELECTED_EXECUTION_DEFAULTS = {
    "physics_provider": "geophys",
    "physics_backend": "cpu",
    "physics_device": "cpu",
    "render_default": {
        "schema_version": "renderer-selection-v1",
        "provider": "none",
        "backend": "cpu",
        "profile": "none",
        "device": None,
    },
}


PUBLIC_ENV_CONFIG_SECTIONS = frozenset(
    {"asset", "runtime", "robot", "control", "action", "observation", "render", "episode"}
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

    if values is None:
        return config
    if not isinstance(values, Mapping):
        raise TypeError(f"{type(config).__name__} overlay must be a mapping")
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
    """Load a safe YAML mapping and reject duplicate keys before they collapse."""

    config_path = Path(path)
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on installation
        raise RuntimeError(
            "YAML TaskEnv config requires PyYAML; install the project dependencies."
        ) from exc
    class UniqueKeySafeLoader(yaml.SafeLoader):
        def construct_mapping(self, node, deep=False):
            if isinstance(node, yaml.MappingNode):
                explicit_keys = set()
                for key_node, _ in node.value:
                    if key_node.tag == "tag:yaml.org,2002:merge":
                        continue
                    key = self.construct_object(key_node, deep=deep)
                    try:
                        duplicate = key in explicit_keys
                    except TypeError as exc:
                        raise yaml.constructor.ConstructorError(
                            "while constructing a mapping",
                            node.start_mark,
                            "found an unhashable mapping key",
                            key_node.start_mark,
                        ) from exc
                    if duplicate:
                        raise yaml.constructor.ConstructorError(
                            "while constructing a mapping",
                            node.start_mark,
                            f"found duplicate key {key!r}",
                            key_node.start_mark,
                        )
                    explicit_keys.add(key)
                self.flatten_mapping(node)
                return super().construct_mapping(node, deep=deep)
            return super().construct_mapping(node, deep=deep)

    with config_path.open("r", encoding="utf-8") as stream:
        loaded = yaml.load(stream, Loader=UniqueKeySafeLoader)
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
    for section, section_value in values.items():
        if not isinstance(section_value, Mapping):
            raise TypeError(f"{section} overlay must be a mapping")
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
        control=update_config(base.control, values.get("control")),
        action=update_config(base.action, values.get("action")),
        observation=update_config(base.observation, values.get("observation")),
        render=update_config(base.render, values.get("render")),
        episode=update_config(base.episode, values.get("episode")),
    )



def _layered_execution_selection(*, provider, backend, device, renderer, runtime, values=None, selected=False):
    """Resolve shared layered facts without constructing a provider."""
    import sys
    host, engine, family = {
        "mujoco": ("standalone", "mujoco", "unknown"),
        "geophys": ("standalone", "geophys", "rigid"),
        "isaacsim": ("isaacsim", "physx", "physx"),
    }[provider]
    defaults = {
        "host": host, "engine": engine, "solver_family": family,
        "solver_algorithm": (runtime.rigid_solver_backend or "unknown") if provider == "geophys" else "unknown",
        "coupler": "not_applicable" if provider == "mujoco" else "unknown",
        "batch_layout": "scalar", "deployment": "in_process",
        "interpreter": sys.executable, "native_dt": None,
    }
    if selected:
        import os
        if provider == 'geophys':
            defaults.update(deployment='isolated_worker', interpreter=os.environ.get('GEOCHORA_GEOPHYS_PYTHON'))
        elif provider == 'isaacsim':
            defaults.update(deployment='isolated_worker', interpreter=os.environ.get('ISAAC_SIM_PYTHON'))
        elif os.environ.get('GEOCHORA_CORE_PYTHON'):
            configured_python = os.environ['GEOCHORA_CORE_PYTHON']
            defaults.update(interpreter=configured_python,
                            deployment=('in_process' if Path(configured_python).resolve() == Path(sys.executable).resolve()
                                        else 'isolated_worker'))
    values = {} if values is None else values
    route = {name: values.get(name, default) for name, default in defaults.items()}
    selection = ExecutionSpecV2(
        schema_version="execution-spec-v2", physics_provider=provider,
        physics_backend=backend, physics_device=device, physics_profile="unknown",
        provider_seed=None, determinism_mode="unknown", render_default=renderer,
        **route,
    )
    return selection, defaults


def _resolve_selected_config(environment_type, config):
    """Resolve the formal task configuration into one build request."""
    supplied = config if isinstance(config, ResolvedSelectedConfig) else None
    if supplied is not None:
        if supplied.task_uid != environment_type.uid:
            raise ValueError("resolved configuration belongs to another task")
        config = {"execution": {"physics_provider": supplied.physics_provider,
                                "physics_backend": supplied.environment.runtime.backend,
                                "physics_device": supplied.physics_device,
                                "source_delivery_manifest": supplied.source_delivery_manifest,
                                "render_default": supplied.render_default.to_mapping()},
                  "episode": {"horizon": supplied.environment.episode.horizon, "seed": supplied.environment.episode.seed,
                              "ignore_done": supplied.environment.episode.ignore_done}}
        selection = supplied.execution_spec_v2
        config["execution"].update({
            name: getattr(selection, name) for name in (
                "host", "engine", "solver_family", "solver_algorithm", "coupler",
                "batch_layout", "deployment", "interpreter", "native_dt",
            )
        })
        config["task"] = dict(supplied.task_parameters)
        config['controller'] = {'parameters': json.loads(supplied.controller_parameters_json)}
        if supplied.gravity_compensation:
            config['controller']['gravity_compensation'] = True
        if supplied.native_drive is not None:
            config.setdefault('robot', {})['native_drive'] = supplied.native_drive
        if supplied.reset_profile is not None:
            config["execution"]["reset_profile"] = supplied.reset_profile
        if supplied.controller_profile is not None:
            config['controller']['profile_id'] = supplied.controller_profile
        if supplied.robot_uid is not None:
            config.setdefault("robot", {})["uid"] = supplied.robot_uid
    if isinstance(config, (str, Path)):
        config = load_yaml_mapping(config)
    if config is None:
        config = {}
    if not isinstance(config, Mapping):
        raise TypeError("selected TaskEnv config must be a mapping or YAML path")
    values = dict(config)
    allowed = {"execution", "episode", "task", "controller", "robot"}
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"unsupported selected TaskEnv config fields: {sorted(unknown)}")
    robot_selection = values.get('robot')
    robot_uid = None
    native_drive = None
    if robot_selection is not None:
        if not isinstance(robot_selection, Mapping) or set(robot_selection) - {'uid', 'native_drive'}:
            raise ValueError('selected robot configuration supports uid and native_drive only')
        native_drive = robot_selection.get('native_drive')
        if native_drive not in (None, 'position', 'disabled'):
            raise ValueError('unsupported Robot native drive selection')
        robot_uid = robot_selection.get('uid')
    choices = getattr(environment_type, 'selected_robot_uids', ())
    if robot_uid is None:
        robot_uid = getattr(environment_type, 'default_robot_source_uid', None)
        if robot_uid is None and len(choices) == 1:
            robot_uid = next(iter(choices))
    if type(robot_uid) is not str or not robot_uid.strip() or robot_uid != robot_uid.strip():
        raise ValueError('selected robot uid must be a nonempty trimmed string')
    if robot_uid not in choices:
        raise ValueError('selected task does not admit the requested robot')
    from ..registry import AGENT_REGISTRY
    AGENT_REGISTRY.get(robot_uid)
    controller = values.get('controller', {})
    if not isinstance(controller, Mapping) or set(controller) - {'profile_id', 'gravity_compensation', 'parameters'}:
        raise ValueError('unsupported selected Controller fields')
    parameters = controller.get('parameters', {})
    if not isinstance(parameters, Mapping) or set(parameters) - set(getattr(environment_type, 'selected_controller_parameters', ())):
        raise ValueError('unsupported selected Controller parameters')
    controller_parameters_json = json.dumps(dict(parameters), sort_keys=True, separators=(',', ':'), allow_nan=False)
    gravity_compensation = controller.get('gravity_compensation', False)
    if type(gravity_compensation) is not bool:
        raise TypeError('controller.gravity_compensation must be a boolean')
    sections = {}
    for name in ("execution", "episode", "task"):
        section = values.get(name, {})
        if not isinstance(section, Mapping):
            raise TypeError(f"{name} must be a mapping")
        sections[name] = dict(section)
    allowed_sections = {
        "execution": {"physics_provider", "physics_backend", "physics_device",
                      "source_delivery_manifest", "render_default", "host", "engine",
                      "solver_family", "solver_algorithm", "coupler", "batch_layout",
                      "deployment", "interpreter", "native_dt", "reset_profile"},
        "episode": {"horizon", "seed", "ignore_done"},
        "task": set(environment_type.selected_parameter_limits),
    }
    for name, section in sections.items():
        unknown = set(section) - allowed_sections[name]
        if unknown:
            raise KeyError(f"unsupported selected {name} fields: {sorted(unknown)}")
    requested_json = (supplied.requested_execution_json if supplied is not None else
                      json.dumps(_identity_value(sections["execution"]), sort_keys=True,
                                 separators=(",", ":"), allow_nan=False))
    configuration_loader = getattr(environment_type, "selected_task_configuration", None)
    task_configuration = configuration_loader() if configuration_loader is not None else None
    base = (environment_type.selected_default_config(task_configuration)
            if configuration_loader is not None else environment_type.selected_default_config())
    execution_defaults = dict(_CORE_SELECTED_EXECUTION_DEFAULTS)
    class_defaults = getattr(environment_type, "selected_execution_defaults", {})
    if callable(class_defaults):
        class_defaults = class_defaults()
    task_yaml_defaults = (
        {} if task_configuration is None else task_configuration.get("execution", {})
    )
    for source_name, source in (
        ("task class execution defaults", class_defaults),
        ("task YAML execution defaults", task_yaml_defaults),
        ("caller execution configuration", sections["execution"]),
    ):
        if not isinstance(source, Mapping):
            raise TypeError(f"{source_name} must be a mapping")
        unknown = set(source) - allowed_sections["execution"]
        if unknown:
            raise KeyError(f"unsupported {source_name} fields: {sorted(unknown)}")
        execution_defaults.update(source)

    provider = execution_defaults["physics_provider"]
    backend = execution_defaults["physics_backend"]
    device = execution_defaults["physics_device"]
    if (provider, backend, device) not in {("geophys", "cpu", "cpu"),
                                           ("mujoco", "cpu", "cpu"),
                                           ("isaacsim", "cuda", "cuda:0")}:
        raise ValueError(
            "unsupported selected physics provider/backend/device combination: "
            f"{provider!r}/{backend!r}/{device!r}"
        )
    renderer_value = execution_defaults["render_default"]
    renderer = (renderer_value if type(renderer_value) is RendererSelectionV1
                else RendererSelectionV1.from_mapping(renderer_value))
    if (renderer.provider, renderer.backend, renderer.profile, renderer.device) != (
            "none", "cpu", "none", None):
        raise ValueError(
            "selected reference currently admits only the state-only renderer selection; "
            "non-none renderer and physics-renderer combinations are unsupported"
        )
    default_profile = (environment_type.selected_default_controller_profile(task_configuration)
                       if configuration_loader is not None else environment_type.selected_default_controller_profile())
    profile = controller.get('profile_id', default_profile)
    if profile not in environment_type.selected_controller_profiles:
        raise ValueError(f"unsupported selected controller profile: {profile!r}")
    profile_routes = getattr(environment_type, 'controller_profile_routes', {})
    if profile in profile_routes and (provider, backend) not in profile_routes[profile]:
        raise ValueError(f'Controller profile {profile!r} is not admitted on {provider}/{backend}')
    reset_profile = execution_defaults.get('reset_profile')
    if reset_profile is not None:
        if type(reset_profile) is not str or not reset_profile.strip() or reset_profile != reset_profile.strip():
            raise ValueError('reset profile must be a nonempty trimmed string')
        if reset_profile not in getattr(environment_type, 'selected_reset_profiles', ()):
            raise ValueError('unsupported task reset profile')
    params = []
    for key, (lower, upper) in environment_type.selected_parameter_limits.items():
        if key not in sections["task"]:
            continue
        value = sections["task"][key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not lower <= value <= upper:
            raise ValueError(f"task.{key} must be within [{lower}, {upper}]")
        params.append((key, float(value)))
    manifest = execution_defaults.get("source_delivery_manifest")
    if provider == "isaacsim" and params:
        raise ValueError("task parameter overrides are not yet admitted by the Isaac source")
    if provider == "isaacsim":
        profiles = getattr(environment_type, 'selected_isaac_controller_profiles', frozenset())
        if not environment_type.selected_supports_isaac or manifest is None or profile not in profiles:
            raise ValueError("Isaac requires a declared Controller profile and an explicit source delivery manifest")
    elif manifest is not None:
        raise ValueError("source_delivery_manifest requires the supported Isaac route")
    seed = sections['episode'].get('seed', base.episode.seed)
    if seed is not None and (type(seed) is not int or seed < 0):
        raise ValueError('episode.seed must be a nonnegative integer or None')
    horizon = sections["episode"].get("horizon", base.episode.horizon)
    if type(horizon) is not int or not 1 <= horizon <= 6000:
        raise ValueError("selected reference horizon must be an integer in [1, 6000]")
    ignore_done = sections['episode'].get('ignore_done', base.episode.ignore_done)
    if type(ignore_done) is not bool:
        raise TypeError('episode.ignore_done must be a boolean')
    env = replace(base, runtime=replace(base.runtime, backend=backend),
                  control=replace(base.control, profile_id=profile),
                  episode=replace(base.episode, horizon=horizon, seed=seed, ignore_done=ignore_done))
    task_configuration_json = None
    if task_configuration is not None:
        # Keep physics/render defaults in their resolved execution owner.  The
        # task configuration snapshot remains recipe/environment data so this
        # additive execution layer does not change existing task identities.
        task_values = dict(task_configuration)
        task_values.pop("execution", None)
        task_configuration_json = json.dumps(
            task_values, sort_keys=True, separators=(",", ":"), allow_nan=False,
        )
    selection, route_defaults = _layered_execution_selection(
        provider=provider, backend=backend, device=device, renderer=renderer,
        runtime=env.runtime, values=execution_defaults, selected=True,
    )
    if gravity_compensation and (provider, backend, selection.deployment) != ('mujoco', 'cpu', 'in_process'):
        raise ValueError('gravity compensation currently requires in-process MuJoCo CPU')
    if gravity_compensation:
        if ('position_drive_gravity_compensation' not in
                getattr(AGENT_REGISTRY.get(robot_uid), 'control_capabilities', ())):
            raise ValueError('selected Robot does not declare position-drive gravity compensation')
    for name in ("host", "engine", "solver_family", "solver_algorithm", "coupler"):
        if getattr(selection, name) != route_defaults[name]:
            raise ValueError(f"static_config: requested {name} has no implemented adapter for {provider}")
    if selection.batch_layout != "scalar":
        raise ValueError("static_config: selected native batch is not implemented")
    if selection.deployment == "in_process":
        import sys
        if selection.interpreter is None or Path(selection.interpreter).resolve() != Path(sys.executable).resolve():
            raise ValueError("static_config: in-process deployment must use the current interpreter")
    if selection.native_dt is not None and selection.native_dt != env.runtime.physics_dt:
        raise ValueError("static_config: native dt differs from task timebase; no versioned mapping is implemented")
    validate = getattr(environment_type, 'validate_selected_configuration', None)
    if callable(validate):
        validate(provider=provider, backend=backend, profile=profile, robot_uid=robot_uid,
                 native_drive=native_drive, parameters=dict(parameters),
                 gravity_compensation=gravity_compensation, reset_profile=reset_profile,
                 source_delivery_manifest=manifest, execution_spec=selection, task_parameters=dict(params),
                 horizon=horizon)
    elif native_drive is not None or parameters:
        raise ValueError('task does not declare these Robot/Controller/source options')
    result = ResolvedSelectedConfig(
        environment=env,
        task_uid=environment_type.uid,
        gravity_compensation=gravity_compensation,
        reset_profile=reset_profile,
        robot_uid=robot_uid,
        native_drive=native_drive, controller_parameters_json=controller_parameters_json,
        source_delivery_manifest=manifest,
        task_parameters=tuple(sorted(params)),
        task_configuration_json=task_configuration_json,
        execution_spec_v2=selection,
        requested_execution_json=requested_json,
    )
    if supplied is not None and supplied != result:
        raise ValueError("resolved selected configuration contains unsupported overrides")
    if supplied is not None and requested_json is not None:
        original = {"execution": json.loads(requested_json),
                    "episode": {"horizon": result.environment.episode.horizon, "seed": result.environment.episode.seed,
                                "ignore_done": result.environment.episode.ignore_done},
                    "task": dict(result.task_parameters)}
        if result.robot_uid is not None:
            original["robot"] = {"uid": result.robot_uid}
        original['controller'] = {'parameters': json.loads(result.controller_parameters_json)}
        if result.gravity_compensation:
            original['controller']['gravity_compensation'] = True
        if result.native_drive is not None:
            original.setdefault('robot', {})['native_drive'] = result.native_drive
        if result.controller_profile is not None:
            original['controller']['profile_id'] = result.controller_profile
        reconstructed = _resolve_selected_config(environment_type, original)
        if (reconstructed.environment != result.environment
                or reconstructed.execution_spec_v2 != result.execution_spec_v2
                or reconstructed.source_delivery_manifest != result.source_delivery_manifest):
            raise ValueError("resolved selected requested execution does not match its selection")
    return result


def _normalize_controller_selection(config):
    """Decode the Controller selector for the retained component-only codec."""
    if isinstance(config, (str, Path)):
        config = load_yaml_mapping(config)
    if not isinstance(config, Mapping):
        return config
    controller = config.get('controller')
    if not isinstance(controller, Mapping) or 'profile_id' not in controller:
        return config
    values, controller = dict(config), dict(controller)
    profile = controller.pop('profile_id')
    section, key = 'control', 'profile_id'
    legacy = dict(values.get(section, {}))
    if key in legacy and legacy[key] != profile:
        raise ValueError(f'controller.profile_id conflicts with {section}.{key}')
    legacy[key] = profile
    values[section] = legacy
    if controller:
        values['controller'] = controller
    else:
        values.pop('controller')
    return values


def _resolve_task_env_config_impl(
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

    if getattr(environment_type, "uses_selected_public_config", False):
        return _resolve_selected_config(environment_type, config)
    config = _normalize_controller_selection(config)
    if isinstance(config, ResolvedEnvConfig):
        resolved = config
    else:
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
        resolved = overlay_public_env_config(base, merged)
    selected_profile = resolved.control.profile_id
    if selected_profile is not None:
        supported = tuple(getattr(environment_type, "selected_physical_controller_profiles", ()))
        if selected_profile not in supported:
            raise ValueError(f"unsupported task physical Controller profile: {selected_profile!r}")
    return resolved



def resolve_task_env_config(environment_type, config):
    """Resolve the common config and attach a stable receipt to static rejections."""
    try:
        return _resolve_task_env_config_impl(environment_type, config)
    except Exception as error:
        try:
            snapshot = _identity_value(config)
            json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError, OverflowError):
            snapshot = {"unserializable_type": f"{type(config).__module__}.{type(config).__qualname__}"}
        payload = {"task_uid": str(getattr(environment_type, "uid", "unknown")), "requested": snapshot}
        if isinstance(config, (str, Path)):
            try:
                payload["config_file_sha256"] = hashlib.sha256(Path(config).read_bytes()).hexdigest()
            except OSError:
                payload["config_file_sha256"] = None
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        identity = hashlib.sha256(encoded.encode()).hexdigest()
        message = str(error)
        reason = ('input_unavailable' if isinstance(error, OSError) else
                  'unknown_field' if isinstance(error, KeyError) else
                  'invalid_type' if isinstance(error, TypeError) else
                  'configuration_conflict' if 'conflict' in message else
                  'unsupported_configuration')
        error.phase = 'static_config'
        error.reason = reason
        error.request_identity = identity
        error.receipt = {'schema_version': 'configuration-rejection-v1', 'phase': error.phase,
                         'reason': reason, 'message': message, 'request_identity': identity,
                         'requested': snapshot, 'resolved': None,
                         'native_effective': {'status': 'unknown', 'reason': 'not built'}}
        raise


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
    identity_values = asdict(config)
    if identity_values.get("control", {}).get("profile_id") is None:
        identity_values.pop("control", None)
    payload = json.dumps(
        _identity_value(identity_values),
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
    agents = tuple(agents or ())
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
    declared_agents = agents or agent_uids
    if any(isinstance(agent, str) for agent in declared_agents):
        import importlib
        from ..registry import AGENT_REGISTRY
        importlib.import_module('task_env.robots')
        resolved_agents = []
        for agent in declared_agents:
            if isinstance(agent, str):
                try:
                    agent = AGENT_REGISTRY.get(agent)
                except KeyError:
                    # Leave unknown components to their registry boundary.
                    pass
            resolved_agents.append(agent)
        declared_agents = tuple(resolved_agents)
    for agent in declared_agents:
        kinds = getattr(agent, 'component_controller_kinds', ())
        if not kinds:
            continue
        controller = config.robot.controller
        if controller is None:
            from .types import StageUnavailableError

            raise StageUnavailableError(
                "robot TaskEnv requires an explicit robot.controller config"
            )
        if controller.kind not in kinds:
            from .types import StageUnavailableError

            raise StageUnavailableError(
                f"unsupported robot controller kind {controller.kind!r}"
            )
        controller_selections += ((str(agent.uid), controller.kind, controller.reference),)

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
    if config.render.camera_obs or normalized_render_mode is not None:
        renderer = RendererSelectionV1(
            "renderer-selection-v1", config.render.backend, config.runtime.backend,
            "unknown", None,
        )
    else:
        renderer = RendererSelectionV1("renderer-selection-v1", "none", "cpu", "none", None)
    selection, _ = _layered_execution_selection(
        provider="geophys", backend=config.runtime.backend,
        device="cpu" if config.runtime.backend == "cpu" else "unknown",
        renderer=renderer, runtime=config.runtime,
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
        execution_spec_v2=selection,
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
    control: Mapping[str, object] | None = None,
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
        control=update_config(ControlConfig(), control),
        action=update_config(ActionConfig(), action),
        observation=update_config(ObservationConfig(), observation),
        render=update_config(RenderConfig(), render),
        task=TaskConfig(
            task_uid=task_uid,
            success_definition=success_definition,
        ),
        episode=update_config(EpisodeConfig(), episode),
    )
