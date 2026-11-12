"""Selected PickCube P1.6 task definition, construction and task semantics."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass, replace
import hashlib
import inspect
import json
import math
from pathlib import Path
from typing import NamedTuple

import numpy as np

from ...artifacts import (
    ActionIntent, CanonicalStateView, EntityDefinition, InitializationContract,
    PoseWorld, SemanticDefinition, TaskArtifact,
    Timebase, UniformDimension,
)
from ...artifacts.execution import ResetSample
from ...assembly import TaskReferences
from ...assembly.panda_box import (PandaBoxDeclaration, compile_panda_box_artifact,
                                   compile_panda_box_mjcf_task, compile_panda_box_task)
from ...assembly.compiler import CompiledReferenceTaskV1, reference_task_identity_fields
from ...controllers.canonical import ProductionCanonicalPandaController
from ...controllers.canonical.contracts import digest, reference_pose_action_binding
from ...controllers.canonical.execution import (
    REFERENCE_POSITION_CONTROLLER_PROFILES, R3_REFERENCE_POSITION_PROFILES)
from ...environment import (
    RuntimeSnapshot, sample_episode_reset_plan,
    TaskCompositionSpec,
    TaskEvaluation,
    TaskEvaluationContextV1,
    TaskPredicateEvaluationV1,
    TaskPredicateResultV1,
)
from ...environment.configuration import (
    load_yaml_mapping,
    overlay_public_env_config,
    resolve_env_config,
)
from ...registry import make_agent, make_object, make_scene, register_env
from ...planners import AbsolutePosePlannerConfig
from ...runtime.sessions.control import position_control_binding_from_selected
from ...robots.panda import PandaAgent, panda_reference_control_binding
from ...environment.reference_binding import ReferenceTaskBinding
from ...environment.reference_env import SelectedReferenceEnv
from ...objects.pick_cube import (
    CUBE_CONTACT_MARGIN, CUBE_DIAG_INERTIA, CUBE_HALF_SIZE, CUBE_MASS,
    EE_SITE_NAME, PickCubeSceneComposer,
)
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

from .task import (semantic_definition, task_binding_fields, build_pickcube_scene,
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


def _source_identity_files(controller, solution_type, *, profile_source=None, provider=None, robot=None):
    root = Path(__file__).resolve().parents[3]
    from ...runtime.sessions.provenance import (construction_source_inventory,
                                                selected_reference_construction_sources)
    files = {Path(__file__).resolve(), Path(__file__).with_name("task.py").resolve(), CONFIG_PATH.resolve(),
             Path(inspect.getsourcefile(PickCubeSceneComposer)).resolve(),
             Path(inspect.getsourcefile(compile_panda_box_task)).resolve(),
             Path(inspect.getsourcefile(solution_type)).resolve(),
             root / "task_env/tasks/pick_cube/observation.py"}
    files.update(selected_reference_construction_sources(root))
    from ...runtime.sessions.source_composition_adapters import robot_construction_source_paths
    files.update(robot_construction_source_paths(PandaAgent() if robot is None else robot))
    if provider == 'mujoco':
        files.add(root / 'task_env/runtime/sessions/mujoco_composition.py')
    if provider == 'isaacsim':
        files.add(root / 'task_env/runtime/sessions/isaac_usd_admission.py')
    if controller is not None:
        files.add(Path(inspect.getsourcefile(type(controller))).resolve())
    if profile_source is not None:
        files.add(Path(profile_source).resolve())
    return construction_source_inventory(root, files)


def _r3_dynamic_profile():
    from ...controllers.canonical.production_r3 import R3_PROFILE_PATH, load_r3_dynamic_profile
    return load_r3_dynamic_profile(), R3_PROFILE_PATH


class _PreparedReferenceSource(NamedTuple):
    task_config: dict
    recipe: dict
    config: object
    is_r3_profile: bool
    dynamic_profile: object
    profile_source: object
    artifact: object
    source: object
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
    source_revision: str
    original_closure: str
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


def _prepare_reference_source(*, backend="cpu", controller_profile="r1", resolved_config=None,
                              lift_height_m=None, task_config=None, robot=None):
    """Prepare the Task source and readiness for a Position Solution."""

    task_config = _configuration() if task_config is None else task_config
    recipe = task_config["recipe"]
    config, is_r3_profile, dynamic_profile, profile_source = _resolve_readiness_declaration(
        task_config, controller_profile, resolved_config)
    declaration = _declaration(lift_height_m=lift_height_m, task_config=task_config)
    artifact = compile_panda_box_artifact(declaration, robot=robot)
    from .solution import PickCubeReadinessConfig
    readiness = PickCubeReadinessConfig.from_resolved_config(
        artifact, config, **_readiness_options(artifact, is_r3_profile=is_r3_profile,
                                               dynamic_profile=dynamic_profile))
    compiled = compile_panda_box_task(declaration, config=config, artifact=artifact,
                                      robot=robot, backend=backend, own_snapshot=True)
    return _PreparedReferenceSource(task_config, recipe, compiled.source.config, is_r3_profile,
        dynamic_profile, profile_source, compiled.artifact, compiled.source, readiness)


def _compile_mjcf_effort_source(request, *, reset_switch, task_config, resolved_config,
                                lift_height_m, robot):
    """Compile PickCube declarations through the shared Task/Robot source owners."""
    from ...runtime.sessions.source import close_execution_source_on_failure
    backend = request.backend
    if reset_switch:
        # The switchable route admits the R3 Solution, so it needs its
        # readiness data; the other effort profiles do not select R3.
        prepared = _prepare_reference_source(
            backend=backend, controller_profile='r3_continuous_v1', task_config=task_config,
            resolved_config=resolved_config, lift_height_m=lift_height_m, robot=robot)
        legacy_artifact, original, readiness = prepared.artifact, prepared.source, prepared.readiness
    else:
        compiled = compile_panda_box_task(
            _declaration(lift_height_m=lift_height_m, task_config=task_config),
            config=_nut_aligned_environment_config(resolved_config), robot=robot,
            backend=backend, own_snapshot=True)
        legacy_artifact, original, readiness = compiled.artifact, compiled.source, None
    with close_execution_source_on_failure(original):
        from ...runtime.sessions.provenance import construction_revision
        revision = construction_revision(Path(__file__).resolve().parents[3])
        if reset_switch:
            from .solution import PickCubeReadinessSolution
            solution_identity = PickCubeReadinessSolution.identity_for_config(readiness)
        return (CompiledReferenceTaskV1(legacy_artifact, original),
                _EffortSourceContext(task_config, original.agents[0], readiness,
                    solution_identity if reset_switch else None,
                    float(legacy_artifact.initialization.joint_position['panda-v1/finger_joint1']),
                    revision, original.source_closure_digest))


def _bind_mjcf_effort_control(compiled, context, selection, request, *, native_drive, control_kind,
                              reset_switch, cube_force_z_N):
    """Bind task semantics and provenance to the compiled effort capability."""
    composition = context.composition
    readiness, solution_identity = context.readiness, context.solution_identity
    factory, physical = selection
    source_sha256 = {'original_closure': context.original_closure,
                     'projected_closure': compiled.source.source_closure_digest}
    if reset_switch:
        from .solution import PickCubeReadinessSolution
    return {'artifact': compiled.artifact, 'source': compiled.source,
        'task_source': composition.task_source, 'construction_id': 'pickcube-mjcf-physical-v1',
        'source_revision': context.source_revision, 'source_sha256': source_sha256,
        'controller': physical.controllers[0], 'solution': None,
        **({'solution_factory': lambda: PickCubeReadinessSolution(config=readiness),
            'solution_identity': solution_identity, 'readiness': readiness,
            '_physical_controller_factory': factory} if reset_switch else {}),
        'physical_execution': physical,
        'resolved_configuration': {'provider': request.provider, 'backend': request.backend,
            'source_composition_intent_v1_sha256': composition.intent.identity_hash,
            'finger_initial_position_m': context.finger_position,
            'drive_mode': 'effort-only' if native_drive == 'disabled' else 'coexist',
            'control_kind': control_kind,
            **({'task_com_force_v1': {'cube_force_z_N': cube_force_z_N}}
               if cube_force_z_N is not None else {}),
            **source_sha256, 'physical_binding': physical.compiled.binding.identity_hash}}


def _compile_reference_position_source(request, *, controller_profile, resolved_config,
                                       lift_height_m, task_config, robot_uid, robot):
    selected_robot = make_agent(robot_uid) if robot is None else robot
    if selected_robot.uid != robot_uid:
        raise ValueError('selected Robot differs from the requested identity')
    profile_recipe = getattr(selected_robot, 'source_recipe_for_profile', None)
    robot_recipe = (profile_recipe(controller_profile) if callable(profile_recipe)
                    else selected_robot.source_recipe())
    reference_robot = selected_robot if robot_recipe.mode == 'reference-task-source' else None
    (task_config, recipe, config, is_r3_profile, dynamic_profile, profile_source,
     artifact, source, readiness) = _prepare_reference_source(
        backend=request.backend, controller_profile=controller_profile, resolved_config=resolved_config,
        lift_height_m=lift_height_m, task_config=task_config, robot=reference_robot)
    return (CompiledReferenceTaskV1(artifact, source),
            _PositionSourceContext(task_config, selected_robot, reference_robot,
                is_r3_profile, dynamic_profile, profile_source, readiness))


def _bind_reference_position_control(compiled, context, controller, request, *, controller_profile):
    from .solution import PickCubeReadinessSolution
    artifact, source = compiled.artifact, compiled.source
    task_config, recipe = context.task_config, context.task_config['recipe']
    is_r3_profile = context.is_r3_profile
    profile_source, readiness = context.profile_source, context.readiness
    source_intent, reset_plan = context.composition.intent, context.composition.reset_plan
    if is_r3_profile:
        execution_controller = controller
        controller = execution_controller.hold.controller
    solution_identity = PickCubeReadinessSolution.identity_for_config(readiness)
    base_controller_identity = None
    execution_profile = None
    if is_r3_profile:
        base_controller_identity = controller.identity
        execution_profile = execution_controller.identity_profile()
        execution_controller.bind_identity_provenance({
            "construction_id": recipe["construction_id"],
            "base_controller_identity": base_controller_identity,
            **execution_profile,
        })
        controller = execution_controller
    root = Path(__file__).resolve().parents[3]
    from ...runtime.sessions.provenance import construction_revision
    revision = construction_revision(root)
    source_ids = _source_identity_files(controller, PickCubeReadinessSolution,
        profile_source=profile_source, provider=request.provider, robot=context.robot)
    construction_identity = reference_task_identity_fields(artifact, source, controller)
    resolved = {
        "construction_id": recipe["construction_id"], "task_recipe": task_config,
        "input_source_composition_intent_v1_sha256": source_intent.identity_hash,
        "task_parameters_v1": {"lift_height_m": artifact.semantics.parameters_si["lift_height"]},
        "artifact": artifact.to_mapping(), **construction_identity,
        "readiness": asdict(readiness), "resolved_controller_action": asdict(controller.config),
        "resolved_controller_gripper": asdict(controller.gripper_config),
        "solution_identity": solution_identity,
        "source_revision": revision, "source_sha256": source_ids,
        "qualification": "NOT_REQUALIFIED",
    }
    if is_r3_profile:
        resolved["base_controller_identity"] = base_controller_identity
        resolved.update(execution_profile)
        resolved["controller_identity"] = controller.identity
    if is_r3_profile:
        resolved["controller_profile"] = controller_profile
        resolved["task_controller_profile"] = dict(PICKCUBE_R3_CONTINUOUS_PROFILE_V1)
        resolved["resolved_controller_profile"] = controller.rate_profile_mapping()
    elif controller_profile == 'r1_split':
        resolved['controller_profile'] = controller_profile
        resolved['controller_owners'] = (
            {'writer_id': controller.arm.writer_id, 'identity': controller.arm.identity},
            {'writer_id': controller.hand.writer_id, 'identity': controller.hand.identity},
        )
    return {
        "construction_id": recipe["construction_id"], "artifact": artifact, "source": source,
        **({'reset_plan': reset_plan} if reset_plan is not None else {}),
        "readiness": readiness, "controller": controller,
        "solution": None,
        "solution_factory": lambda: PickCubeReadinessSolution(config=readiness),
        "solution_identity": solution_identity,
        "source_revision": revision, "source_sha256": source_ids,
        "recipe_identity": digest(resolved), "resolved_configuration": resolved,
    }



def _compose_reference_source(compiled, context, request, *, controller_profile,
                               reference_robot, sample_reset):
    """Bind Task declarations to the source owner's explicit composition result."""
    from ...runtime.sessions.source_composition_adapters import compose_declared_reference_source
    composition = compose_declared_reference_source(
        compiled, robot=context.robot, controller_profile=controller_profile,
        existing_robot_entity='panda-v1', task_body_names=PickCubeReferenceEnv.robot_source_roots,
        task_site_transfers=PickCubeReferenceEnv.robot_source_site_transfers,
        compile_declaration=(lambda: compile_panda_box_mjcf_task(
            context.task_config, reference_robot, compiled.artifact,
            build_task_scene=build_pickcube_scene,
            compile_task_artifact=compile_pickcube_task_artifact))
            if reference_robot is not None else None,
        reset_seed=request.seed if sample_reset else None)
    return composition.compiled, context._replace(composition=composition)


def _position_reference_builder(*, backend, controller_profile,
                                resolved_config, lift_height_m, task_config, robot_uid, robot):
    from ...environment.reference_binding import SourceBoundTaskBuilder
    from ...controllers.canonical.execution import build_reference_position_controller
    return SourceBoundTaskBuilder(
        lambda request: _compile_reference_position_source(request,
            controller_profile=controller_profile, resolved_config=resolved_config,
            lift_height_m=lift_height_m, task_config=task_config, robot_uid=robot_uid, robot=robot),
        None, backend=backend, allow_sampled_reset=False,
        source_composer=lambda compiled, context, request: _compose_reference_source(
            compiled, context, request, controller_profile=controller_profile,
            reference_robot=context.reference_robot, sample_reset=True),
        controller_factory=build_reference_position_controller,
        controller_options=lambda compiled, context, request: dict(
            profile_id=controller_profile, dynamic_profile=context.dynamic_profile,
            force_limit_N=10.0,
            joint_velocity_limit_rad_s=PICKCUBE_R3_CONTINUOUS_PROFILE_V1['joint_velocity_limit_rad_s']),
        compile_control=lambda compiled, context, selection, request: _bind_reference_position_control(
            compiled, context, selection, request,
            controller_profile=controller_profile))


def _compile_isaac_reference_source(request, *, delivery_manifest, controller_profile,
                                    resolved_config, task_config, lift_height_m,
                                    physical_fixture, robot):
    """Compile Task readiness and the admitted USD source before Controller binding."""
    from .solution import PickCubeReadinessConfig, PickCubeReadinessSolution

    task_config = _configuration() if task_config is None else task_config
    config, is_r3_profile, dynamic_profile, profile_source = _resolve_readiness_declaration(
        task_config, controller_profile, resolved_config)
    config = replace(config, runtime=replace(config.runtime, backend='cpu'))
    artifact = build_artifact(lift_height_m=lift_height_m, task_config=task_config)
    readiness = PickCubeReadinessConfig.from_resolved_config(
        artifact, config, **_readiness_options(artifact, is_r3_profile=is_r3_profile,
                                               dynamic_profile=dynamic_profile))
    source_ids = _source_identity_files(None, PickCubeReadinessSolution,
                                        profile_source=profile_source, provider='isaacsim')
    robot = make_agent('panda-v1') if robot is None else robot
    from ...runtime.sessions.isaac_usd_admission import compile_f06_task_input
    runtime_input = compile_f06_task_input(
        delivery_manifest=delivery_manifest, legacy_artifact=artifact, robot=robot,
        task_config=task_config, build_task_scene=build_pickcube_scene,
        compile_task_artifact=compile_pickcube_task_artifact,
        task_scene_recipe_sha256=hashlib.sha256(_canonical_task_recipe(task_config)).hexdigest(),
        seed=request.seed, horizon=request.horizon, physical_fixture=physical_fixture)
    if runtime_input.artifact.timebase != artifact.timebase:
        raise ValueError('USD Artifact timebase differs from the Task readiness declaration')
    runtime_input.runtime_source.scene_source.assert_fresh()
    return (CompiledReferenceTaskV1(runtime_input.artifact, runtime_input.runtime_source),
            _UsdSourceContext(runtime_input, robot, config.action, task_config, config,
                              readiness, dynamic_profile, source_ids))


def _bind_isaac_reference_control(compiled, context, selection, request, *, resolved_config):
    from ...controllers.canonical.kinematics import PANDA_PICKCUBE_EE_TCP_V1
    from .solution import PickCubeReadinessSolution
    runtime_input, controller, physical = selection
    robot, action_config = context.robot, context.action_config
    scene_source = runtime_input.runtime_source.scene_source
    loaded, panda_xml = scene_source.loaded_delivery, scene_source.xml
    manifest_path = loaded.manifest_path
    readiness = context.readiness
    solution_identity = PickCubeReadinessSolution.identity_for_config(readiness)
    from ...runtime.sessions.isaac_usd_admission import f06_construction_source_inventory
    from ...runtime.sessions.provenance import construction_revision
    source_ids = f06_construction_source_inventory(
        runtime_input, context.source_sha256, task_path=__file__, physical=physical is not None)
    root = Path(__file__).resolve().parents[3]
    revision = construction_revision(root)
    effective_config = (asdict(context.config)
                        if resolved_config is None else asdict(resolved_config))
    # Keep historical F06 source/configuration identity when the additive
    # gravity option is disabled; F06 does not yet admit the enabled route.
    if resolved_config is not None and not getattr(resolved_config, 'gravity_compensation', False):
        effective_config.pop('gravity_compensation', None)
    effective_config_sha = hashlib.sha256(json.dumps(
        effective_config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    resolved = {
        "construction_id": "pickcube-p16-reference-construction-v2",
        "task_recipe": context.task_config,
        **runtime_input.construction_identity_fields(),
        "runtime_config": effective_config,
        "runtime_config_sha256": effective_config_sha,
        "readiness": asdict(readiness), "resolved_controller_action": asdict(action_config),
        "resolved_controller_gripper": asdict(context.config.robot.gripper),
        "controller_identity": controller.identity,
        "solution_identity": solution_identity,
        "source_revision": revision,
        "source_sha256": source_ids,
        "f06_delivery_manifest_sha256": runtime_input.delivery_manifest_sha256,
        "tcp_profile": PANDA_PICKCUBE_EE_TCP_V1.to_mapping(),
        "qualification": "NOT_REQUALIFIED",
    }
    return {
        "construction_id": resolved["construction_id"],
        "robot": robot,
        "artifact": runtime_input.artifact,
        "source": runtime_input.runtime_source,
        "readiness": readiness,
        "controller": controller,
        **({} if physical is None else {"physical_execution": physical}),
        "solution": None,
        "solution_factory": lambda: PickCubeReadinessSolution(config=readiness),
        "solution_identity": solution_identity,
        "source_revision": revision,
        "source_sha256": source_ids,
        "recipe_identity": digest(resolved),
        "resolved_configuration": resolved,
        "execution_spec_v1": runtime_input.execution,
        "reset_plan": runtime_input.reset_plan,
        "session_admission_input": runtime_input,
        "f06_delivery_manifest_path": str(manifest_path),
        "kinematics_source_xml": panda_xml,
    }


def _isaac_reference_builder(*, delivery_manifest, controller_profile,
                             resolved_config, task_config, lift_height_m, physical_fixture,
                             physical_kind, physical_drive, robot):
    if controller_profile != 'r3_continuous_v1':
        raise ValueError('F06 Isaac freezes the existing r3_continuous_v1 profile')
    from ...environment.reference_binding import SourceBoundTaskBuilder
    from ...controllers.canonical.kinematics import PANDA_PICKCUBE_EE_TCP_V1
    from ...runtime.sessions.source_composition_adapters import build_usd_panda_control
    return SourceBoundTaskBuilder(
        lambda request: _compile_isaac_reference_source(request,
            delivery_manifest=delivery_manifest, controller_profile=controller_profile,
            resolved_config=resolved_config, task_config=task_config, lift_height_m=lift_height_m,
            physical_fixture=physical_fixture, robot=robot),
        None, backend='cuda', allow_sampled_reset=False,
        controller_factory=build_usd_panda_control,
        controller_options=lambda compiled, context, request: dict(
            runtime_input=context.runtime_input, robot=context.robot,
            controller_profile=controller_profile, action_config=context.action_config,
            dynamic_profile=context.dynamic_profile,
            velocity_limit=PICKCUBE_R3_CONTINUOUS_PROFILE_V1['joint_velocity_limit_rad_s'],
            tcp_profile=PANDA_PICKCUBE_EE_TCP_V1, end_frame_id='ee', physical_kind=physical_kind,
            native_drive=physical_drive,
            effort_settings=panda_effort_task_settings(physical_kind) if physical_kind is not None else None),
        compile_control=lambda compiled, context, selection, request: _bind_isaac_reference_control(
            compiled, context, selection, request,
            resolved_config=resolved_config))


def build_readiness_solution(*, backend="cpu", controller_profile="r3_continuous_v1"):
    """Build the external Solution from Task and Robot declarations, without a source lease."""
    from .solution import PickCubeReadinessConfig, PickCubeReadinessSolution

    robot = make_agent('panda-v1')
    robot.source_recipe_for_profile(controller_profile)
    task_config = _configuration()
    config, is_r3_profile, dynamic_profile, _ = _resolve_readiness_declaration(
        task_config, controller_profile, None)
    if backend not in {'cpu', 'cuda'}:
        raise ValueError('PickCube reference backend must be cpu or cuda')
    artifact = build_artifact(task_config=task_config)
    readiness = PickCubeReadinessConfig.from_resolved_config(
        artifact, config, **_readiness_options(artifact, is_r3_profile=is_r3_profile,
                                               dynamic_profile=dynamic_profile))
    return PickCubeReadinessSolution(config=readiness)


def _validate_external_readiness_solution(value, solution):
    from .solution import PickCubeReadinessSolution

    if not isinstance(solution, PickCubeReadinessSolution):
        raise TypeError("PickCube external lifecycle requires PickCubeReadinessSolution")
    if solution.readiness_config.identity != value["readiness"].identity:
        raise ValueError("external Solution readiness configuration does not match the selected source")
    if solution.identity != value["solution_identity"]:
        raise ValueError("external Solution identity does not match the selected task implementation")


def position_execution_info(state, last_position_transition):
    """Project the exact PickCube Position boundary into Solution readiness."""
    from .solution import PickCubePositionExecutionInfoV1

    positions = state.joint_position
    velocities = state.joint_velocity
    measured = float(sum(
        float(positions[f'panda-v1/finger_joint{index}']) for index in (1, 2)
    ))
    # Normalize only the submicrometer lower-limit residue observed in PhysX.
    if -1e-6 <= measured < 0.0:
        measured = 0.0
    measured_speed = float(sum(
        abs(float(velocities[f'panda-v1/finger_joint{index}'])) for index in (1, 2)
    ))
    target = measured
    if last_position_transition is not None:
        target = float(last_position_transition[1].target.gripper.opening_m)
    ready = bool(target <= 0.045 and measured <= 0.045 and measured_speed <= 0.005)
    result = PickCubePositionExecutionInfoV1(
        'pickcube-position-execution-info-v1', int(state.control_step),
        float(state.simulation_time), measured, measured_speed, target, ready,
    )
    result.validate()
    return result


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
    if runtime_input:
        if source_delivery_manifest is None:
            raise ValueError('F06 Isaac PickCube requires CUDA and its explicit source delivery')
        builder = _isaac_reference_builder(
            delivery_manifest=source_delivery_manifest,
            controller_profile='r3_continuous_v1' if physical else controller_profile,
            resolved_config=resolved_config, task_config=task_config, lift_height_m=lift_height_m,
            robot=robot, physical_fixture=(('effort-only' if physical_drive == 'disabled' else 'coexist')
                                           if physical else False),
            physical_kind=physical_kind, physical_drive=physical_drive)
    elif physical:
        from ...environment.reference_binding import SourceBoundTaskBuilder
        from ...runtime.sessions.source_composition_adapters import compile_panda_effort_selection
        builder = SourceBoundTaskBuilder(
            lambda request: _compile_mjcf_effort_source(request, reset_switch=reset_switch,
                task_config=task_config, resolved_config=resolved_config,
                lift_height_m=lift_height_m, robot=robot),
            lambda value, request: sample_episode_reset_plan(
                value['task_source'], value['source'].scene_definition,
                value['artifact'], task_seed=request.seed),
            backend=backend, reuse_source=True, allow_sampled_reset=False,
            source_composer=lambda compiled, context, request: _compose_reference_source(
                compiled, context, request, controller_profile=physical_profile_id,
                reference_robot=context.robot, sample_reset=False),
            controller_factory=compile_panda_effort_selection,
            controller_options=lambda compiled, context, request: dict(
                robot=context.robot, scene=context.composition.scene, intent=context.composition.intent,
                controller_profile=physical_profile_id, native_drive=physical_drive,
                kind=physical_kind, config=compiled.source.config.action,
                source_xml=context.composition.projected_xml, end_frame_id='nutassembly_ee_site',
                task_settings=panda_effort_task_settings, dynamic_parameters=reset_switch,
                gripper_force_limit_N=(compiled.source.config.robot.gripper.force_limit_N
                                       if reset_switch else None)),
            compile_control=lambda compiled, context, selection, request: _bind_mjcf_effort_control(
                compiled, context, selection, request, native_drive=physical_drive, control_kind=physical_kind,
                reset_switch=reset_switch, cube_force_z_N=cube_force_z_N))
    else:
        builder = _position_reference_builder(
            backend=backend, controller_profile=controller_profile,
            resolved_config=resolved_config, lift_height_m=lift_height_m,
            task_config=task_config, robot_uid=robot_uid, robot=robot)

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
            hand_frame_id='ee' if runtime_input else 'hand', runtime_input=runtime_input,
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
        position_execution_info_key='pickcube_position_execution_info_v1',
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

    @classmethod
    def selected_supports_observer(cls, config):
        options = json.loads(config.controller_parameters_json)
        kind = cls.panda_effort_profiles.get(config.controller_profile)
        return ((config.physics_provider == 'isaacsim' and kind is not None)
                or (config.physics_provider == 'mujoco' and options.get('reset_selection', False))
                or (config.physics_provider == 'geophys' and kind == 'joint'
                    and not options.get('reset_selection', False)))
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
