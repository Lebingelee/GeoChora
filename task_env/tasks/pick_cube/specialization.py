"""Selected PickCube P1.6 task definition, construction and task semantics."""

from __future__ import annotations

from collections import OrderedDict
from functools import partial
from dataclasses import asdict, replace
import hashlib
import json
import math
from pathlib import Path
from typing import NamedTuple

from ...artifacts import TaskArtifact, Timebase
from ...assembly.panda_box import (PandaBoxDeclaration, compile_panda_box_artifact,
                                   compile_panda_box_mjcf_task)
from ...controllers.canonical.contracts import digest, reference_pose_action_binding
from ...controllers.canonical.execution import (
    REFERENCE_POSITION_CONTROLLER_PROFILES, R3_REFERENCE_POSITION_PROFILES)
from ...environment.configuration import (
    load_yaml_mapping,
    overlay_public_env_config,
    resolve_env_config,
)
from ...registry import make_agent, register_env
from ...planners import AbsolutePosePlannerConfig
from ...runtime.sessions.control import position_control_binding_from_selected
from ...robots.panda import PandaAgent, panda_reference_control_binding
from ...environment.reference_binding import ReferenceTaskBinding
from ...environment.reference_env import SelectedReferenceEnv
from ...observations.selected_reference import selected_observation_binding


CONFIG_PATH = Path(__file__).with_name("config.yaml")
EEF = "panda-v1/ee"
FINGERS = ("panda-v1/finger_joint1", "panda-v1/finger_joint2")
TASK_CONFIGURATION_KEYS = ("recipe", "environment")
PICKCUBE_CONTROLLER_PROFILES = REFERENCE_POSITION_CONTROLLER_PROFILES
_PICKCUBE_R3_PROFILES = R3_REFERENCE_POSITION_PROFILES
_NUT_ASSEMBLY_MAX_STAGE_PLAN_S = 6.0
PICKCUBE_R3_CONTINUOUS_PROFILE_V1 = {
    "schema_version": "pick-cube-r3-nut-aligned-profile-v2",
    "joint_velocity_limit_rad_s": 2.0,
    "gripper_force_limit_N": 10.0,
    "gripper_close_transition_s": 0.3333333333333333,
    "gripper_close_settle_s": 0.5,
    "postclose_hold_s": 0.1,
}

from .task import (semantic_definition, task_binding_fields, build_pickcube_scene, position_execution_info,
    compile_pickcube_task_artifact, _canonical_task_recipe)

def _configuration() -> dict:
    data = load_yaml_mapping(CONFIG_PATH)
    if (not isinstance(data, dict)
            or not {"recipe", "environment"}.issubset(data)
            or set(data) - {"recipe", "environment", "execution"}):
        raise ValueError("PickCube config.yaml must define recipe, environment, and optional execution")
    if "execution" in data and not isinstance(data["execution"], dict):
        raise TypeError("PickCube execution defaults must be a mapping")
    recipe = data["recipe"]
    if recipe.get("control_hz") != 100 or recipe.get("artifact_id") != "pick-cube-v1/p1_6_experimental_100hz":
        raise ValueError("PickCube task admits only the selected P1.6 100 Hz recipe")
    return data


def _recipe() -> dict:
    return _configuration()["recipe"]


def _environment_config(data=None):
    data = _configuration() if data is None else data
    recipe = data["recipe"]
    base = resolve_env_config(
        task_uid=recipe["task_uid"], scene_uid=recipe["scene_uid"],
        agent_uids=tuple(recipe["agent_uids"]), object_uids=tuple(recipe["object_uids"]),
        success_definition=recipe["success_definition"],
    )
    config = overlay_public_env_config(base, data["environment"])
    runtime = replace(config.runtime, backend="cpu", prewarm=False,
        physics_dt=float(recipe["physics_dt"]), control_substeps=int(recipe["control_substeps"]))
    return replace(config, runtime=runtime, render=replace(config.render, camera_obs=False))


def _nut_aligned_environment_config(config):
    """Resolve the selected PickCube R3 source with NutAssembly's 10 N gripper cap."""
    return replace(
        config,
        robot=replace(
            config.robot,
            gripper=replace(
                config.robot.gripper,
                force_limit_N=PICKCUBE_R3_CONTINUOUS_PROFILE_V1["gripper_force_limit_N"],
            ),
        ),
    )


def _pickcube_r3_planner_config(dynamic_profile, control_dt):
    """Convert the frozen production R3 planner profile to 100 Hz per-tick limits."""
    planner = dynamic_profile["planner"]
    return AbsolutePosePlannerConfig.from_si_rates(
        control_dt_s=float(control_dt),
        translation_speed_m_s=float(planner["translation_speed_m_s"]),
        translation_acceleration_m_s2=float(planner["translation_acceleration_m_s2"]),
        rotation_speed_rad_s=float(planner["rotation_speed_rad_s"]),
        rotation_acceleration_rad_s2=float(planner["rotation_acceleration_rad_s2"]),
        settle_duration_s=float(planner["settle_duration_s"]),
        max_plan_duration_s=_NUT_ASSEMBLY_MAX_STAGE_PLAN_S,
    )


def _declaration(*, lift_height_m=None, task_config=None):
    recipe = _recipe() if task_config is None else task_config["recipe"]
    scene, reset = recipe["scene"], recipe["reset"]
    return PandaBoxDeclaration(
        task_id=recipe["task_uid"], artifact_id=recipe["artifact_id"],
        version=recipe["artifact_version"], object_id="cube-v1",
        success_definition=recipe["success_definition"],
        table_half_size=tuple(scene["table_half_size"]), table_top_z=scene["table_top_z"],
        table_center_xy=tuple(scene["table_center_xy"]),
        source_box_position=tuple(scene["initial_cube_position"]),
        source_box_quaternion_wxyz=tuple(scene["initial_cube_quaternion_wxyz"]),
        reset_center_xy=tuple(reset["center_xy"]), reset_half_extent_m=reset["half_extent_m"],
        semantics=semantic_definition(lift_height_m=lift_height_m, task_config=task_config),
        timebase=Timebase(float(recipe["physics_dt"]), int(recipe["control_substeps"]),
                          float(recipe["control_dt"])),
    )


def build_artifact(*, lift_height_m=None, task_config=None) -> TaskArtifact:
    return compile_panda_box_artifact(_declaration(lift_height_m=lift_height_m, task_config=task_config))


def _task_construction_source_paths():
    """Declare only the files that own PickCube task and Solution semantics."""
    return (Path(__file__).resolve(), Path(__file__).with_name('task.py').resolve(),
            CONFIG_PATH.resolve(), Path(__file__).with_name('solution.py').resolve(),
            Path(__file__).with_name('observation.py').resolve())


def _r3_dynamic_profile():
    from ...controllers.canonical.production_r3 import R3_PROFILE_PATH, load_r3_dynamic_profile
    return load_r3_dynamic_profile(), R3_PROFILE_PATH


class _TaskSourceFacts(NamedTuple):
    is_r3_profile: bool
    dynamic_profile: object
    readiness: object


class _PositionSourceContext(NamedTuple):
    task_config: dict
    robot: object
    reference_robot: object
    is_r3_profile: bool
    dynamic_profile: object
    profile_source: object
    readiness: object
    composition: object = None


class _EffortSourceContext(NamedTuple):
    task_config: dict
    robot: object
    readiness: object
    solution_identity: str | None
    finger_position: float
    composition: object = None


class _UsdSourceContext(NamedTuple):
    runtime_input: object
    robot: object
    action_config: object
    task_config: dict
    config: object
    readiness: object
    dynamic_profile: object
    source_sha256: dict


def _readiness_options(artifact, *, is_r3_profile, dynamic_profile):
    """Project the Task's readiness policy independently of source representation."""
    planner_config = (
        _pickcube_r3_planner_config(dynamic_profile, artifact.timebase.control_dt)
        if is_r3_profile else None
    )
    return dict(measured_tcp_clearance_gate=is_r3_profile, planner=planner_config,
        close_transition_steps=(
            max(1, int(math.ceil(
                PICKCUBE_R3_CONTINUOUS_PROFILE_V1["gripper_close_transition_s"]
                / artifact.timebase.control_dt - 1e-10
            ))) if is_r3_profile else None
        ),
        close_settle_steps=(
            max(1, int(math.ceil(
                PICKCUBE_R3_CONTINUOUS_PROFILE_V1["gripper_close_settle_s"]
                / artifact.timebase.control_dt - 1e-10
            ))) if is_r3_profile else 0
        ),
        postclose_hold_steps=(
            max(1, int(math.ceil(
                PICKCUBE_R3_CONTINUOUS_PROFILE_V1["postclose_hold_s"]
                / artifact.timebase.control_dt - 1e-10
            ))) if is_r3_profile else 0
        ),
    )


def _build_readiness(artifact, config, *, is_r3_profile, dynamic_profile):
    """Bind the same task readiness policy to either admitted source representation."""
    from .solution import PickCubeReadinessConfig

    return PickCubeReadinessConfig.from_resolved_config(
        artifact, config, **_readiness_options(artifact, is_r3_profile=is_r3_profile,
                                               dynamic_profile=dynamic_profile))


def _resolve_readiness_declaration(task_config, controller_profile, resolved_config):
    """Resolve the Task's profile and action configuration for every source route."""
    if controller_profile not in PICKCUBE_CONTROLLER_PROFILES:
        raise ValueError(f"unsupported PickCube controller_profile: {controller_profile!r}")
    is_r3_profile = controller_profile in _PICKCUBE_R3_PROFILES
    dynamic_profile, profile_source = (_r3_dynamic_profile() if is_r3_profile else (None, None))
    config = _environment_config(task_config) if resolved_config is None else resolved_config
    if is_r3_profile:
        config = _nut_aligned_environment_config(config)
    return config, is_r3_profile, dynamic_profile, profile_source


def _prepare_reference_source(request, selected_robot, source_robot, *, source_format,
                              controller_profile, physical, reset_switch,
                              resolved_config, lift_height_m, task_config):
    """Prepare task semantics before the source adapter creates a resource."""
    from ...runtime.sessions.source_composition_adapters import PandaReferenceSourcePlan

    task_config = _configuration() if task_config is None else task_config
    readiness_profile = ('r3_continuous_v1' if reset_switch else 'r1') if physical and source_format == 'mjcf' else controller_profile
    if physical and source_format == 'mjcf' and not reset_switch:
        resolved_config = _nut_aligned_environment_config(resolved_config)
    config, is_r3_profile, dynamic_profile, profile_source = _resolve_readiness_declaration(
        task_config, readiness_profile, resolved_config)
    declaration = (None if source_format == 'usd' else
                   _declaration(lift_height_m=lift_height_m, task_config=task_config))
    artifact = readiness = None
    if source_format == 'usd':
        config = replace(config, runtime=replace(config.runtime, backend='cpu'))
        artifact = build_artifact(lift_height_m=lift_height_m, task_config=task_config)
    elif not physical or reset_switch:
        artifact = compile_panda_box_artifact(declaration, robot=source_robot)
    if artifact is not None:
        readiness = _build_readiness(artifact, config, is_r3_profile=is_r3_profile,
                                     dynamic_profile=dynamic_profile)
    recipe_hash = (hashlib.sha256(_canonical_task_recipe(task_config)).hexdigest()
                   if source_format == 'usd' else None)
    return PandaReferenceSourcePlan(task_config, config, declaration, artifact, recipe_hash, profile_source,
        _TaskSourceFacts(is_r3_profile, dynamic_profile, readiness))


def _reference_source_context(plan, compiled, runtime_input, selected_robot, source_robot, *,
                              source_format, physical, reset_switch):
    """Attach task readiness and identity to the adapter's compiled source."""
    facts = plan.facts
    if source_format == 'usd':
        return _UsdSourceContext(runtime_input, selected_robot, plan.config.action,
            plan.task_config, plan.config, facts.readiness, facts.dynamic_profile, plan.source_inventory)
    if not physical:
        return _PositionSourceContext(plan.task_config, selected_robot, source_robot,
            facts.is_r3_profile, facts.dynamic_profile, plan.profile_source, facts.readiness)
    solution_identity = None
    if reset_switch:
        from .solution import PickCubeReadinessSolution
        solution_identity = PickCubeReadinessSolution.identity_for_config(facts.readiness)
    return _EffortSourceContext(plan.task_config, compiled.source.agents[0], facts.readiness,
        solution_identity, float(compiled.artifact.initialization.joint_position['panda-v1/finger_joint1']))


def _bind_mjcf_effort_control(compiled, context, selection, request, *, reset_switch, cube_force_z_N):
    """Bind task reset and Solution semantics to the compiled effort capability."""
    readiness, solution_identity = context.readiness, context.solution_identity
    if reset_switch:
        from .solution import PickCubeReadinessSolution
    return {'construction_id': 'pickcube-mjcf-physical-v1',
        **({'solution_factory': lambda: PickCubeReadinessSolution(config=readiness),
            'solution_identity': solution_identity, 'readiness': readiness} if reset_switch else {}),
        'resolved_configuration': {'finger_initial_position_m': context.finger_position,
            **({'task_com_force_v1': {'cube_force_z_N': cube_force_z_N}}
               if cube_force_z_N is not None else {})}}


def _bind_reference_position_control(compiled, context, controller, request, *, controller_profile):
    """Return PickCube task semantics for the source-bound Controller."""
    from .solution import PickCubeReadinessSolution

    artifact = compiled.artifact
    task_config, recipe = context.task_config, context.task_config['recipe']
    readiness = context.readiness
    solution_identity = PickCubeReadinessSolution.identity_for_config(readiness)
    resolved = {
        'construction_id': recipe['construction_id'], 'task_recipe': task_config,
        'task_parameters_v1': {'lift_height_m': artifact.semantics.parameters_si['lift_height']},
        'readiness': asdict(readiness), 'solution_identity': solution_identity,
        'qualification': 'NOT_REQUALIFIED',
    }
    if context.is_r3_profile:
        resolved['task_controller_profile'] = dict(PICKCUBE_R3_CONTINUOUS_PROFILE_V1)
    return {'construction_id': recipe['construction_id'], 'readiness': readiness,
        'solution_factory': lambda: PickCubeReadinessSolution(config=readiness),
        'solution_identity': solution_identity, 'resolved_configuration': resolved}


def _bind_isaac_reference_control(compiled, context, selection, request):
    from ...controllers.canonical.kinematics import PANDA_PICKCUBE_EE_TCP_V1
    from .solution import PickCubeReadinessSolution
    action_config = context.action_config
    readiness = context.readiness
    solution_identity = PickCubeReadinessSolution.identity_for_config(readiness)
    resolved = {
        "construction_id": "pickcube-p16-reference-construction-v2",
        "task_recipe": context.task_config,
        "readiness": asdict(readiness), "resolved_controller_action": asdict(action_config),
        "resolved_controller_gripper": asdict(context.config.robot.gripper),
        "solution_identity": solution_identity,
        "tcp_profile": PANDA_PICKCUBE_EE_TCP_V1.to_mapping(),
        "qualification": "NOT_REQUALIFIED",
    }
    return {
        "construction_id": resolved["construction_id"],
        "readiness": readiness,
        "solution_factory": lambda: PickCubeReadinessSolution(config=readiness),
        "solution_identity": solution_identity,
        "resolved_configuration": resolved,
    }


def build_readiness_solution(*, backend="cpu", controller_profile="r3_continuous_v1"):
    """Build the external Solution from Task and Robot declarations, without a source lease."""
    from .solution import PickCubeReadinessSolution

    robot = make_agent('panda-v1')
    robot.source_recipe_for_profile(controller_profile)
    task_config = _configuration()
    config, is_r3_profile, dynamic_profile, _ = _resolve_readiness_declaration(
        task_config, controller_profile, None)
    if backend not in {'cpu', 'cuda'}:
        raise ValueError('PickCube reference backend must be cpu or cuda')
    artifact = build_artifact(task_config=task_config)
    readiness = _build_readiness(artifact, config, is_r3_profile=is_r3_profile,
                                 dynamic_profile=dynamic_profile)
    return PickCubeReadinessSolution(config=readiness)


def _validate_external_readiness_solution(value, solution):
    from .solution import PickCubeReadinessSolution

    if not isinstance(solution, PickCubeReadinessSolution):
        raise TypeError("PickCube external lifecycle requires PickCubeReadinessSolution")
    if solution.readiness_config.identity != value["readiness"].identity:
        raise ValueError("external Solution readiness configuration does not match the selected source")
    if solution.identity != value["solution_identity"]:
        raise ValueError("external Solution identity does not match the selected task implementation")


def make_reference_binding(*, controller_profile="r1", source_delivery_manifest=None,
                           resolved_config=None, lift_height_m=None, task_config=None,
                           interval_provider=None,
                           cube_force_z_N=None, robot_uid="panda-v1", robot=None,
                           physical_kind=None, physical_drive=None, physical_profile_id=None, reset_switch=False,
                           space_policy='dynamic'):
    if controller_profile not in PICKCUBE_CONTROLLER_PROFILES:
        raise ValueError(f"unsupported PickCube controller_profile: {controller_profile!r}")
    physical = physical_kind is not None
    if physical != (physical_drive is not None):
        raise ValueError('physical Controller kind and drive must be declared together')

    def adapt(value):
        if cube_force_z_N is not None:
            from ...controllers.canonical.contracts import digest
            value = dict(value)
            resolved = dict(value['resolved_configuration'])
            resolved['task_com_force_v1'] = {'cube_force_z_N': cube_force_z_N}
            value['resolved_configuration'] = resolved
            value['recipe_identity'] = digest(resolved)
        return value

    # Resolve the selected source strategy once at binding construction.
    # Each resulting builder still consumes the same TaskBuildRequest.
    selected_provider = interval_provider or ('isaacsim' if source_delivery_manifest else None)
    runtime_input = selected_provider == 'isaacsim'
    backend = resolved_config.runtime.backend if resolved_config is not None else 'cpu'
    from ...runtime.sessions.source_composition_adapters import build_panda_reference_stages
    velocity_limit = PICKCUBE_R3_CONTINUOUS_PROFILE_V1['joint_velocity_limit_rad_s']
    if runtime_input:
        if source_delivery_manifest is None:
            raise ValueError('F06 Isaac PickCube requires CUDA and its explicit source delivery')
        from ...controllers.canonical.kinematics import PANDA_PICKCUBE_EE_TCP_V1
        from ...runtime.sessions.isaac_usd_admission import F06_PICKCUBE_CONTROLLER_PROFILE
        profile = F06_PICKCUBE_CONTROLLER_PROFILE if physical else controller_profile
        finish = _bind_isaac_reference_control
        source_format, tcp_profile = 'usd', PANDA_PICKCUBE_EE_TCP_V1
    else:
        source_format, tcp_profile = 'mjcf', None
        if physical:
            profile = physical_profile_id
            finish = partial(_bind_mjcf_effort_control, reset_switch=reset_switch,
                             cube_force_z_N=cube_force_z_N)
        else:
            profile = controller_profile
            finish = partial(_bind_reference_position_control, controller_profile=controller_profile)
    prepare = partial(_prepare_reference_source, source_format=source_format,
        controller_profile=profile, physical=physical, reset_switch=reset_switch,
        resolved_config=resolved_config, lift_height_m=lift_height_m, task_config=task_config)
    source_context = partial(_reference_source_context, source_format=source_format,
                             physical=physical, reset_switch=reset_switch)
    builder = build_panda_reference_stages(
        source_format=source_format, backend=backend, controller_profile=profile,
        prepare_source=prepare, source_context=source_context, compile_control=finish,
        robot_uid=robot_uid, robot=robot, delivery_manifest=source_delivery_manifest,
        build_task_scene=build_pickcube_scene, compile_task_artifact=compile_pickcube_task_artifact,
        task_source_path=__file__, task_source_paths=_task_construction_source_paths(),
        resolved_config=resolved_config,
        physical_kind=physical_kind, native_drive=physical_drive, reset_selection=reset_switch,
        task_settings=panda_effort_task_settings, existing_robot_entity='panda-v1',
        task_body_names=PickCubeReferenceEnv.robot_source_roots,
        task_site_transfers=PickCubeReferenceEnv.robot_source_site_transfers,
        scene_compiler=partial(compile_panda_box_mjcf_task,
            build_task_scene=build_pickcube_scene, compile_task_artifact=compile_pickcube_task_artifact),
        force_limit_N=10.0, velocity_limit=velocity_limit, tcp_profile=tcp_profile)

    def build(request):
        allowed = ({selected_provider} if selected_provider is not None else {'mujoco', 'geophys'})
        if request.provider not in allowed:
            raise ValueError('requested provider differs from the selected source route')
        value = builder(request)
        return adapt(value) if not physical and not runtime_input else value

    if physical:
        from .task import physical_task_binding
        from ...controllers.canonical.r3_effort import panda_effort_reset_capability
        return physical_task_binding(build=build, task_config=task_config, lift_height_m=lift_height_m,
            runtime_input=runtime_input,
            validate_solution=_validate_external_readiness_solution,
            reset_capability=(panda_effort_reset_capability(physical_kind, space_policy)
                              if reset_switch else None), cube_force_z_N=cube_force_z_N)

    return ReferenceTaskBinding(
        build=build,
        **reference_pose_action_binding(), **selected_observation_binding(),
        scalar_control_binding=panda_reference_control_binding(),
        position_execution_info=lambda env: (
            position_execution_info(env.state, env.last_position_transition)
            if env.value.get('session_admission_input') is not None else None
        ),
        position_execution_info_key='pickcube_position_execution_info_v2',
        reset_runtime_input=lambda value: value.get('session_admission_input'),
        position_control_binding=position_control_binding_from_selected,
        validate_external_solution=_validate_external_readiness_solution,
        **task_binding_fields(task_config=task_config, lift_height_m=lift_height_m,
                              cube_force_z_N=cube_force_z_N),
        external_actions=True,
        external_solution_actions=True,
        interval_mode=(
            "native"
            if interval_provider in {"mujoco", "geophys"}
            and controller_profile in _PICKCUBE_R3_PROFILES
            else "grouped"
        ),
        recorder_mode="canonical",
        reset_expert_kwargs=lambda env: {"execution_info": env.expert_execution_info()},
        observe_expert_kwargs=lambda env, guard_samples: {"execution_info": env.expert_execution_info()},
    )


REFERENCE_ENV_ID = _recipe()["reference_env_id"]


def panda_effort_task_settings(kind):
    """Supply PickCube's TCP and reference tuning to the shared Controller builder."""
    from ...controllers.canonical.kinematics import PANDA_PICKCUBE_EE_TCP_V1

    r3_profile = velocity_limit = None
    if kind in {'r3-pose', 'r3-mass-pose'}:
        r3_profile, _ = _r3_dynamic_profile()
        velocity_limit = PICKCUBE_R3_CONTINUOUS_PROFILE_V1['joint_velocity_limit_rad_s']
    return {'tcp_profile': PANDA_PICKCUBE_EE_TCP_V1, 'r3_profile': r3_profile,
            'joint_velocity_limit_rad_s': velocity_limit}


@register_env()
class PickCubeReferenceEnv(SelectedReferenceEnv):
    """Public selected P1.6 route, registered beside its task definition."""

    uid = REFERENCE_ENV_ID

    uses_selected_public_config = True
    panda_effort_profiles = PandaAgent.effort_controller_profiles()
    selected_controller_profiles = frozenset(PICKCUBE_CONTROLLER_PROFILES) | frozenset(panda_effort_profiles)
    selected_controller_parameters = frozenset(('reset_selection', 'action_space_policy'))
    selected_reset_profiles = frozenset(('pickcube-state-only-switch-v1',))

    @staticmethod
    def validate_selected_configuration(**options):
        if options['provider'] == 'isaacsim' and set(options['task_parameters']) - {'lift_height_m'}:
            raise ValueError('Isaac PickCube does not support the requested Task parameter')
        if (options['reset_profile'] is not None
                and (options['profile'] != 'r3_continuous_v1' or options['gravity_compensation'])):
            raise ValueError('reset profile requires PickCube R3 without gravity compensation')
        profile = options['profile']
        parameters = options['parameters']
        native_drive = options['native_drive']
        if profile not in PandaAgent.effort_controller_profiles():
            if native_drive is not None or parameters:
                raise ValueError('Robot/Controller/source options require a declared physical profile')
            return
        from ...controllers.canonical.r3_effort import resolve_panda_effort_options
        from ...runtime.sessions.source_composition_adapters import validate_effort_source_route
        kind, drive, switch, _policy = resolve_panda_effort_options(profile, native_drive, parameters)
        validate_effort_source_route(provider=options['provider'], backend=options['backend'],
            deployment=options['execution_spec'].deployment,
            source_delivery_manifest=options['source_delivery_manifest'],
            drive=drive, kind=kind, reset_selection=switch)
        if (options['robot_uid'] != 'panda-v1' or options['gravity_compensation']
                or options['reset_profile'] is not None):
            raise ValueError('physical profile requires its declared Panda source without Position-only options')
        if options['provider'] == 'isaacsim':
            if parameters or set(options['task_parameters']) - {'lift_height_m'}:
                raise ValueError('Isaac physical control does not admit MJCF-only options')
            if options['horizon'] > 1000:
                raise ValueError('Isaac physical source horizon must be in [1, 1000]')
        if ('cube_force_z_N' in options['task_parameters'] and
                (options['provider'], drive, kind, switch) != ('mujoco', 'position', 'direct', False)):
            raise ValueError('PickCube Task COM force requires MuJoCo direct coexist control')

    selected_parameter_limits = {"lift_height_m": (0.01, 0.25), "cube_force_z_N": (-30., 30.)}
    selected_supports_isaac = True
    selected_isaac_controller_profiles = frozenset(('r3_continuous_v1',)) | frozenset(panda_effort_profiles)
    selected_robot_uids = frozenset(("panda-v1", "panda-arm-hand-v1"))
    robot_source_roots = (('tabletop-v1', 'grasp_table'), ('cube-v1', 'PickCube'))
    robot_source_site_transfers = (('hand', 'nutassembly_ee_site', 'hand'),)
    default_robot_source_uid = 'panda-v1'
    @staticmethod
    def selected_task_configuration():
        return _configuration()

    @staticmethod
    def selected_default_config(task_config=None):
        return _environment_config(task_config)

    @staticmethod
    def selected_default_controller_profile(task_config=None):
        return (_recipe() if task_config is None else task_config["recipe"])["default_controller_profile"]

    @classmethod
    def selected_binding(cls, config, *, robot=None):
        profile = config.controller_profile
        if profile in cls.panda_effort_profiles:
            from ...controllers.canonical.r3_effort import resolve_panda_effort_options
            kind, drive, switch, policy = resolve_panda_effort_options(
                profile, config.native_drive, json.loads(config.controller_parameters_json))
            return make_reference_binding(source_delivery_manifest=config.source_delivery_manifest,
                resolved_config=config.environment, task_config=json.loads(config.task_configuration_json),
                lift_height_m=dict(config.task_parameters).get('lift_height_m'),
                cube_force_z_N=dict(config.task_parameters).get('cube_force_z_N'), robot=robot,
                interval_provider=config.physics_provider, physical_kind=kind, physical_drive=drive,
                physical_profile_id=profile, reset_switch=switch, space_policy=policy)
        cube_force_z_N = dict(getattr(config, 'task_parameters', ())).get('cube_force_z_N')
        if cube_force_z_N is not None and (config.physics_provider != 'mujoco'
                or config.environment.runtime.backend != 'cpu' or profile != 'r1'):
            raise ValueError('PickCube Task COM force requires the MuJoCo CPU R1 grouped interval')
        environment = (_nut_aligned_environment_config(config.environment)
                       if profile in _PICKCUBE_R3_PROFILES else config.environment)
        binding = make_reference_binding(
            controller_profile=profile, source_delivery_manifest=config.source_delivery_manifest,
            resolved_config=environment,
            lift_height_m=dict(config.task_parameters).get("lift_height_m"),
            task_config=json.loads(config.task_configuration_json),
            interval_provider=config.physics_provider,
            cube_force_z_N=cube_force_z_N, robot_uid=config.robot_uid, robot=robot,
        )

        if config.reset_profile is not None:
            from .observation import build_switch_observation, switch_observation_space
            from ...environment.reset_switch import prepare_switch_reset
            binding = replace(binding,
                prepare_reset_switch=prepare_switch_reset,
                observation_space_factory=lambda _env: OrderedDict(switch_observation_space().spaces),
                observation_projection=build_switch_observation,
                observation_metadata={
                    'schema_version': config.reset_profile,
                    'field_metadata': {'privileged_state.cube_body_pose': (
                        'task object pose [x,y,z,qw,qx,qy,qz]', 'm + unit quaternion', 'world')},
                    'hand_pose_frame': 'panda-v1/ee',
                    'joint_order': [*(f'panda-v1/joint{i}' for i in range(1, 8)),
                                    'panda-v1/finger_joint1', 'panda-v1/finger_joint2'],
                    'joint_position_units': ['rad'] * 7 + ['m'] * 2,
                    'joint_velocity_units': ['rad/s'] * 7 + ['m/s'] * 2,
                })
        return binding
