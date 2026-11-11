"""Selected PickCube P1.6 task definition, construction and task semantics."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import inspect
import json
import math
from pathlib import Path
from typing import NamedTuple
import subprocess

import numpy as np
from ...environment.task_definition import as_task_state_view

from ...artifacts import (
    ActionIntent, CanonicalStateView, EntityDefinition, InitializationContract,
    PoseWorld, SemanticDefinition, TaskArtifact,
    Timebase, UniformDimension,
)
from ...artifacts.execution import ResetSample
from ...assembly import TaskReferences
from ...assembly.panda_box import (PandaBoxDeclaration, compile_panda_box_artifact,
                                   compile_panda_box_source, compile_panda_box_task)
from ...assembly.compiler import reference_task_identity_fields
from ...controllers.canonical import ProductionCanonicalPandaController
from ...controllers.canonical.contracts import digest, reference_pose_action_binding
from ...controllers.canonical.execution import ReferenceExecutionController
from ...environment import (
    RuntimeSnapshot,
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
from ...environment.task_definition import TaskDefinitionBase, as_task_state_view
from ...environment.task_source import compile_declared_artifact
from ...registry import make_agent, make_object, make_scene, register_env
from ...robots.panda import PandaAgent
from ...planners import AbsolutePosePlannerConfig
from ...runtime.sessions.control import ControlBinding
from ...robots.panda import PandaAgent, panda_reference_control_binding
from ...runtime.sessions.source import RuntimeSource
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
PICKCUBE_CONTROLLER_PROFILES = {
    "r1",
    "r1_split",
    "r3_continuous_v1",
    "r3_continuous_v1_pose_path_x20",
}
_PICKCUBE_R3_PROFILES = frozenset({
    "r3_continuous_v1",
    "r3_continuous_v1_pose_path_x20",
})
_PICKCUBE_POSTURE_PATH_ORIGINAL = "original"
_PICKCUBE_POSTURE_PATH_WORLD_X_ROUNDTRIP = "world_x_roundtrip_v1"
_NUT_ASSEMBLY_MAX_STAGE_PLAN_S = 6.0
PICKCUBE_R3_CONTINUOUS_PROFILE_V1 = {
    "schema_version": "pick-cube-r3-nut-aligned-profile-v2",
    "joint_velocity_limit_rad_s": 2.0,
    "gripper_force_limit_N": 10.0,
    "gripper_close_transition_s": 0.3333333333333333,
    "gripper_close_settle_s": 0.5,
    "postclose_hold_s": 0.1,
}

from .task import PickCubeTaskDefinition, semantic_definition, evaluate, sample_reset

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


def build_runtime_source(artifact: TaskArtifact, *, backend="cpu", resolved_config=None, lift_height_m=None, task_config=None) -> RuntimeSource:
    declaration = _declaration(lift_height_m=lift_height_m, task_config=task_config)
    if artifact.identity_hash != compile_panda_box_artifact(declaration).identity_hash:
        raise ValueError("selected P1.6 TaskArtifact required")
    if backend not in {"cpu", "cuda"}:
        raise ValueError("PickCube reference backend must be cpu or cuda")
    config = _environment_config() if resolved_config is None else resolved_config
    config = replace(config, runtime=replace(config.runtime, backend=backend))
    from ...runtime.sessions.source import snapshot_legacy_mjcf_source
    return snapshot_legacy_mjcf_source(compile_panda_box_source(declaration, artifact, config))


def _source_identity_files(controller, solution_type, *, profile_source=None):
    root = Path(__file__).resolve().parents[3]
    files = {Path(__file__).resolve(), Path(__file__).with_name("task.py").resolve(), CONFIG_PATH.resolve(),
             Path(inspect.getsourcefile(PickCubeSceneComposer)).resolve(),
             Path(inspect.getsourcefile(compile_panda_box_source)).resolve(),
             Path(__file__).parents[2].joinpath("assembly/compiler.py").resolve(),
             Path(inspect.getsourcefile(compile_declared_artifact)).resolve(),
             Path(inspect.getsourcefile(solution_type)).resolve(),
             Path(inspect.getsourcefile(AbsolutePosePlannerConfig)).resolve(),
             Path(inspect.getsourcefile(panda_reference_control_binding)).resolve(),
             root / "task_env/planners/contracts.py",
             root / "task_env/planners/completion.py",
             Path(inspect.getsourcefile(ReferenceTaskBinding)).resolve(),
             Path(inspect.getsourcefile(SelectedReferenceEnv)).resolve(),
             root / "task_env/environment/lifecycle.py",
             root / "task_env/runtime/sessions/api.py",
             root / "task_env/runtime/sessions/control.py",
             Path(inspect.getsourcefile(TaskArtifact)).resolve(),
             root / "task_env/recorders/reference_provenance.py",
             root / "task_env/utils/_paths.py",
             root / "task_env/recorders/position_metadata.py",
             root / "task_env/observations/selected_reference.py",
             Path(inspect.getsourcefile(RuntimeSource)).resolve()}
    if controller is not None:
        files.add(Path(inspect.getsourcefile(type(controller))).resolve())
    canonical = root / "task_env" / "controllers" / "canonical"
    files.update(path.resolve() for path in canonical.glob("*.py") if path.is_file())
    if profile_source is not None:
        files.add(Path(profile_source).resolve())
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(files)}


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
    posture_path_profile: object
    readiness: object


def _prepare_reference_source(*, backend="cpu", controller_profile="r1", resolved_config=None,
                              lift_height_m=None, task_config=None):
    """Compile Task source and readiness without constructing a Controller."""
    from .solution import PickCubeReadinessConfig

    task_config = _configuration() if task_config is None else task_config
    recipe = task_config["recipe"]
    if backend not in {"cpu", "cuda"}:
        raise ValueError("PickCube reference backend must be cpu or cuda")
    if controller_profile not in PICKCUBE_CONTROLLER_PROFILES:
        raise ValueError(f"unsupported PickCube controller_profile: {controller_profile!r}")
    declaration = _declaration(lift_height_m=lift_height_m, task_config=task_config)
    config = _environment_config() if resolved_config is None else resolved_config
    config = replace(config, runtime=replace(config.runtime, backend=backend))
    is_r3_profile = controller_profile in _PICKCUBE_R3_PROFILES
    dynamic_profile, profile_source = _r3_dynamic_profile() if is_r3_profile else (None, None)
    if is_r3_profile:
        config = _nut_aligned_environment_config(config)
    compiled = compile_panda_box_task(declaration, config=config)
    artifact, source = compiled.artifact, compiled.source
    posture_path_profile = (
        _PICKCUBE_POSTURE_PATH_WORLD_X_ROUNDTRIP
        if controller_profile == "r3_continuous_v1_pose_path_x20"
        else _PICKCUBE_POSTURE_PATH_ORIGINAL
    )
    planner_config = (
        _pickcube_r3_planner_config(dynamic_profile, artifact.timebase.control_dt)
        if is_r3_profile else None
    )
    readiness = PickCubeReadinessConfig.from_source(
        artifact, source,
        measured_tcp_clearance_gate=is_r3_profile,
        planner=planner_config,
        posture_path_profile=posture_path_profile,
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
    from ...runtime.sessions.source import snapshot_legacy_mjcf_source
    source = snapshot_legacy_mjcf_source(source)
    return _PreparedReferenceSource(task_config, recipe, config, is_r3_profile, dynamic_profile,
        profile_source, artifact, source, posture_path_profile, readiness)


def build_reference(*, backend="cpu", include_solution=True, controller_profile="r1", resolved_config=None, lift_height_m=None, task_config=None):
    """Construct the single selected P1.6 route without importing a provider."""
    from ...controllers.canonical import ProductionCanonicalPandaController
    from ...controllers.canonical.contracts import digest
    from .solution import PickCubeReadinessConfig, PickCubeReadinessSolution

    (task_config, recipe, config, is_r3_profile, dynamic_profile, profile_source,
     artifact, source, posture_path_profile, readiness) = _prepare_reference_source(
        backend=backend, controller_profile=controller_profile, resolved_config=resolved_config,
        lift_height_m=lift_height_m, task_config=task_config)
    from ...runtime.sessions.source import close_execution_source_on_failure
    with close_execution_source_on_failure(source):
        if controller_profile == "r1":
            controller = ProductionCanonicalPandaController.from_source(artifact, source)
        elif controller_profile == "r1_split":
            from ...controllers.canonical.split_panda_position import SplitPandaPositionControllerV1
            controller = SplitPandaPositionControllerV1(artifact, source)
        else:
            execution_controller = ReferenceExecutionController.from_source(
                artifact, source, profile=dynamic_profile, force_limit_N=10.0,
                joint_velocity_limit_rad_s=(
                    PICKCUBE_R3_CONTINUOUS_PROFILE_V1["joint_velocity_limit_rad_s"]
                ),
            )
            controller = execution_controller.hold.controller
        solution_identity = PickCubeReadinessSolution.identity_for_config(readiness)
        solution = PickCubeReadinessSolution(config=readiness) if include_solution else None
        base_controller_identity = None
        execution_profile = None
        if is_r3_profile:
            base_controller_identity = controller.identity
            execution_support_sha256 = {
                "arm_and_execution_wrapper": hashlib.sha256(
                    Path(inspect.getsourcefile(type(execution_controller.hold))).read_bytes()
                ).hexdigest(),
                "execution_controller": hashlib.sha256(
                    Path(inspect.getsourcefile(ReferenceExecutionController)).read_bytes()
                ).hexdigest(),
                "gripper_servo": hashlib.sha256(
                    Path(inspect.getsourcefile(type(execution_controller.inner))).read_bytes()
                ).hexdigest(),
            }
            execution_profile = {
                "arm_execution_profile": "controller-owned-hold-and-linear-native-ramp-v1",
                "arm_execution_request_profile": "pickcube-r3-hold-ramp-v1",
                "gripper_cadence": "native-gripper-500hz-v1",
                "gripper_control_hz": 500,
                "gripper_feedback_hz": 500,
                "outer_controller_hz": 100,
                "execution_support_sha256": execution_support_sha256,
            }
            controller.identity = digest({
                "construction_id": recipe["construction_id"],
                "base_controller_identity": base_controller_identity,
                **execution_profile,
            })
            controller = execution_controller
        root = Path(__file__).resolve().parents[3]
        revision = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        source_ids = _source_identity_files(controller, PickCubeReadinessSolution, profile_source=profile_source)
        construction_identity = reference_task_identity_fields(artifact, source, controller)
        resolved = {
            "construction_id": recipe["construction_id"], "task_recipe": task_config,
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
            resolved["task_controller_profile"]["posture_path_profile"] = posture_path_profile
            resolved["resolved_controller_profile"] = controller.rate_profile_mapping()
        elif controller_profile == 'r1_split':
            resolved['controller_profile'] = controller_profile
            resolved['controller_owners'] = (
                {'writer_id': controller.arm.writer_id, 'identity': controller.arm.identity},
                {'writer_id': controller.hand.writer_id, 'identity': controller.hand.identity},
            )
        return {
            "construction_id": recipe["construction_id"], "artifact": artifact, "source": source,
            "readiness": readiness, "controller": controller,
            "solution": solution,
            "solution_factory": lambda: PickCubeReadinessSolution(config=readiness),
            "solution_identity": solution_identity,
            "source_revision": revision, "source_sha256": source_ids,
            "recipe_identity": digest(resolved), "resolved_configuration": resolved,
        }


def build_isaac_reference(*, delivery_manifest, task_seed=31, horizon=1000,
                          include_solution=True, controller_profile="r3_continuous_v1",
                          resolved_config=None, task_config=None, physical_fixture=False,
                          controller_builder=None):
    """Build the exact F06 Isaac source through the existing PickCube owners."""
    if controller_profile != "r3_continuous_v1":
        raise ValueError("F06 Isaac freezes the existing r3_continuous_v1 profile")
    from ...controllers.canonical.kinematics import PANDA_PICKCUBE_EE_TCP_V1
    from ...controllers.canonical.contracts import digest
    from .solution import PickCubeReadinessSolution

    # The Task supplies action/readiness data; the selected Controller owns execution.
    if controller_builder is None:
        legacy = build_reference(backend="cpu", include_solution=False,
                                 controller_profile=controller_profile, resolved_config=resolved_config,
                                 task_config=task_config)
    else:
        prepared = _prepare_reference_source(backend="cpu", controller_profile=controller_profile,
                                             resolved_config=resolved_config, task_config=task_config)
        from ...runtime.sessions.source import close_execution_source_on_failure
        with close_execution_source_on_failure(prepared.source):
            source_ids = _source_identity_files(None, PickCubeReadinessSolution, profile_source=prepared.profile_source)
            legacy = {"source": prepared.source, "artifact": prepared.artifact, "readiness": prepared.readiness,
                      "source_sha256": source_ids,
                      "resolved_configuration": {"runtime_config": asdict(prepared.config),
                                                  "task_recipe": prepared.task_config,
                                                  "resolved_controller_gripper": asdict(prepared.config.robot.gripper)}}
    # USD owns an independent source; the temporary MJCF snapshot only serves
    # Task/readiness preparation and must not outlive construction.
    receipt = legacy["source"].execution_source_receipt
    try:
        robot = legacy["source"].agents[0]
        runtime_input = build_pickcube_isaac_runtime_input_v1(
            delivery_manifest, task_seed=task_seed, horizon=horizon, task_config=task_config,
            physical_fixture=physical_fixture, robot=robot,
        )
        manifest_path = Path(delivery_manifest).resolve(strict=True)
        panda_xml_path = manifest_path.parent / runtime_input.runtime_source.scene_source.loaded_delivery.delivery.source_entry_file
        panda_xml = panda_xml_path.read_text()
        from ...assembly.usd_delivery import load_usd_asset_delivery
        loaded = load_usd_asset_delivery(manifest_path)
        if hashlib.sha256(panda_xml.encode("utf-8")).hexdigest() != loaded.delivery.source_entry_sha256:
            raise ValueError("F06 kinematics Panda XML differs from the frozen source-entry bytes")
        action_config = legacy["source"].config.action
        physical = None
        if controller_builder is None:
            from ...controllers.canonical.position_profile import PandaPositionServoProfileV1
            dynamic_profile, _profile_source = _r3_dynamic_profile()
            controller = PandaPositionServoProfileV1.from_usd_source(
                runtime_input.artifact, runtime_input.runtime_source,
                execution=runtime_input.execution, kinematics_source_xml=panda_xml,
                config=action_config, pose_target_method="achieved_state_dls_v1",
                arm_tracking_method="production_r3_continuous_v1", arm_tracking_profile=dynamic_profile,
                arm_joint_velocity_limit_rad_s=PICKCUBE_R3_CONTINUOUS_PROFILE_V1["joint_velocity_limit_rad_s"],
                entity_id="panda-v1", hand_frame_id="ee", tcp_profile=PANDA_PICKCUBE_EE_TCP_V1,
            )
            position_plan, subject_identity, position_subjects = robot.compile_position_subjects(
                runtime_input.runtime_source, artifact=runtime_input.artifact,
                controller=controller, entity_id='panda-v1', end_frame_id='ee')
            controller._validate_plan(position_plan)
            from ...runtime.sessions.source import PositionSubjectPlanV1
            source = replace(runtime_input.runtime_source, position_subject_plan=PositionSubjectPlanV1(
                position_plan, subject_identity, position_subjects))
            runtime_input = replace(runtime_input, runtime_source=source)
            runtime_input.validate()
            controller.source = source
        else:
            physical = controller_builder(robot, runtime_input, panda_xml, action_config)
            from ...runtime.sessions.physical_control import PhysicalControlExecutionV1
            if type(physical) is not PhysicalControlExecutionV1 or len(physical.controllers) != 1:
                raise TypeError('USD Controller builder must return one physical execution')
            controller = physical.controllers[0]
        readiness = legacy["readiness"]
        solution_identity = PickCubeReadinessSolution.identity_for_config(readiness)
        solution = PickCubeReadinessSolution(config=readiness) if include_solution else None
        source_ids = dict(legacy["source_sha256"])
        if physical is not None:
            source_ids.pop("task_env/controllers/canonical/position_profile.py", None)
        identity_paths = (Path(__file__), Path(__file__).parents[2] / "runtime/sessions/source.py",
                          Path(__file__).parents[2] / "runtime/sessions/api.py",
                          Path(__file__).parents[2] / "controllers/canonical/kinematics.py")
        if physical is None:
            identity_paths += (Path(__file__).parents[2] / "controllers/canonical/position_profile.py",)
        for path in identity_paths:
            source_ids[path.resolve().relative_to(Path(__file__).parents[3]).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
        source_ids["f06_delivery_source_entry_sha256"] = loaded.delivery.source_entry_sha256
        source_ids["f06_delivery_manifest_sha256"] = loaded.manifest_bytes_sha256
        root = Path(__file__).resolve().parents[3]
        revision = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                           text=True).strip()
        effective_config = (legacy["resolved_configuration"]["runtime_config"]
                            if resolved_config is None else asdict(resolved_config))
        # Keep historical F06 source/configuration identity when the additive
        # gravity option is disabled; F06 does not yet admit the enabled route.
        if resolved_config is not None and not getattr(resolved_config, 'gravity_compensation', False):
            effective_config.pop('gravity_compensation', None)
        effective_config_sha = hashlib.sha256(json.dumps(
            effective_config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        resolved = {
            "construction_id": "pickcube-p16-reference-construction-v2",
            "task_recipe": legacy["resolved_configuration"]["task_recipe"],
            "artifact": runtime_input.artifact.to_mapping(),
            "artifact_sha256": runtime_input.artifact.identity_hash,
            "runtime_config": effective_config,
            "runtime_config_sha256": effective_config_sha,
            "readiness": asdict(readiness), "resolved_controller_action": asdict(action_config),
            "resolved_controller_gripper": legacy["resolved_configuration"]["resolved_controller_gripper"],
            "controller_identity": controller.identity,
            "solution_identity": solution_identity,
            "source_revision": revision,
            "source_sha256": source_ids,
            "runtime_source_id": runtime_input.runtime_source.source_id,
            "runtime_source_closure_sha256": runtime_input.runtime_source.source_closure_digest,
            "runtime_source_bindings": {name: dict(getattr(runtime_input.runtime_source, name))
                for name in ("joints", "bodies", "frames", "free_joints", "joint_targets")},
            "execution_spec_v1": runtime_input.execution.to_mapping(),
            "reset_plan_identity_sha256": runtime_input.reset_plan.identity_hash,
            "f06_delivery_manifest_sha256": runtime_input.delivery_manifest_sha256,
            "tcp_profile": PANDA_PICKCUBE_EE_TCP_V1.to_mapping(),
            "qualification": "NOT_REQUALIFIED",
        }
        result = {
            "construction_id": resolved["construction_id"],
            "robot": robot,
            "artifact": runtime_input.artifact,
            "source": runtime_input.runtime_source,
            "readiness": readiness,
            "controller": controller,
            **({} if physical is None else {"physical_execution": physical}),
            "solution": solution,
            "solution_factory": lambda: PickCubeReadinessSolution(config=readiness),
            "solution_identity": solution_identity,
            "source_revision": revision,
            "source_sha256": source_ids,
            "recipe_identity": digest(resolved),
            "resolved_configuration": resolved,
            "execution_spec_v1": runtime_input.execution,
            "reset_plan": runtime_input.reset_plan,
            "f06_pickcube_isaac_input": runtime_input,
            "session_admission_input": runtime_input,
            "f06_delivery_manifest_path": str(manifest_path),
            "kinematics_source_xml": panda_xml,
        }
    except BaseException as error:
        try:
            receipt.close()
        except BaseException as cleanup_error:
            error.add_note(f'temporary Task source cleanup also failed: {cleanup_error!r}')
        raise
    receipt.close()
    return result


def build_readiness_solution(*, backend="cpu", controller_profile="r3_continuous_v1"):
    """Build the task-owned PickCube readiness Solution for an external driver."""
    return build_reference(backend=backend, controller_profile=controller_profile)["solution"]


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
                           cube_force_z_N=None):
    if controller_profile not in PICKCUBE_CONTROLLER_PROFILES:
        raise ValueError(f"unsupported PickCube controller_profile: {controller_profile!r}")
    def adapt(value):
        if cube_force_z_N is not None:
            from ...controllers.canonical.contracts import digest
            value = dict(value)
            resolved = dict(value['resolved_configuration'])
            resolved['task_com_force_v1'] = {'cube_force_z_N': cube_force_z_N}
            value['resolved_configuration'] = resolved
            value['recipe_identity'] = digest(resolved)
        return value

    def build(provider):
        if provider == "isaacsim":
            if source_delivery_manifest is None:
                raise ValueError("F06 Isaac PickCube requires its explicit source_delivery_manifest")
            return build_isaac_reference(
                delivery_manifest=source_delivery_manifest, include_solution=False,
                controller_profile=controller_profile,
                **({"resolved_config": resolved_config} if resolved_config is not None else {}),
                **({"task_config": task_config} if task_config is not None else {}),
            )
        return adapt(build_reference(backend="cpu", include_solution=False, controller_profile=controller_profile, resolved_config=resolved_config, lift_height_m=lift_height_m, task_config=task_config))

    def build_external(provider):
        if provider == "isaacsim":
            return build_isaac_reference(
                delivery_manifest=source_delivery_manifest, include_solution=False,
                controller_profile=controller_profile,
                **({"resolved_config": resolved_config} if resolved_config is not None else {}),
                **({"task_config": task_config} if task_config is not None else {}),
            )
        return adapt(build_reference(backend="cpu", include_solution=False,
                               controller_profile=controller_profile, resolved_config=resolved_config, lift_height_m=lift_height_m, task_config=task_config))

    def build_seeded(provider, backend, seed, horizon):
        if provider == "isaacsim":
            if backend != "cuda" or source_delivery_manifest is None:
                raise ValueError("F06 Isaac PickCube requires CUDA and its explicit source delivery")
            return build_isaac_reference(
                delivery_manifest=source_delivery_manifest, task_seed=seed,
                horizon=horizon, include_solution=False, controller_profile=controller_profile,
                **({"resolved_config": resolved_config} if resolved_config is not None else {}),
                **({"task_config": task_config} if task_config is not None else {}),
            )
        return adapt(build_reference(backend="cpu", include_solution=False, controller_profile=controller_profile, resolved_config=resolved_config, lift_height_m=lift_height_m, task_config=task_config))

    def task_com_wrenches(env):
        from ...controllers.canonical.physical_commands import ExternalComWrenchSumSegmentV1
        return (ExternalComWrenchSumSegmentV1('external-com-wrench-sum-segment-v1',
            'pickcube-task-writer-v1', 'pickcube-task-cube-force-v1', 'cube-v1',
            0, env.artifact.timebase.control_substeps,
            (0., 0., cube_force_z_N), (0., 0., 0.)),)

    return ReferenceTaskBinding(
        build=build,
        **reference_pose_action_binding(), **selected_observation_binding(),
        scalar_control_binding=panda_reference_control_binding(),
        build_external=build_external,
        build_seeded=build_seeded,
        position_execution_info=lambda env: (
            position_execution_info(env.state, env.last_position_transition)
            if env.value.get('f06_pickcube_isaac_input') is not None else None
        ),
        position_execution_info_key='pickcube_position_execution_info_v1',
        legacy_position_expert_admission=lambda value: (
            value.get('f06_pickcube_isaac_input') is not None
        ),
        reset_runtime_input=lambda value: value.get('f06_pickcube_isaac_input'),
        position_control_binding=lambda value: ControlBinding(
            'panda-v1/gripper' if value.get('f06_pickcube_isaac_input') is not None
            else 'panda-main/gripper', 0.08
        ),
        validate_external_solution=_validate_external_readiness_solution,
        reset_sample=lambda artifact, seed: sample_reset(artifact, seed, lift_height_m=lift_height_m, task_config=task_config),
        evaluate=lambda state, semantics: evaluate(state, semantics, lift_height_m=lift_height_m, task_config=task_config),
        task_definition_factory=PickCubeTaskDefinition.from_artifact,
        task_state_projection=as_task_state_view,
        object_poses=(("cube-v1", "cube_v1"),),
        external_actions=True,
        external_solution_actions=True,
        task_com_wrench_factory=task_com_wrenches if cube_force_z_N is not None else None,
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
        if (options['reset_profile'] is not None
                and (options['profile'] != 'r3_continuous_v1' or options['gravity_compensation'])):
            raise ValueError('reset profile requires PickCube R3 without gravity compensation')
        from .physical_candidate import validate_physical_configuration
        validate_physical_configuration(**options)

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
    selected_execution_defaults = {
        "physics_provider": "geophys",
        "physics_backend": "cpu",
        "physics_device": "cpu",
    }

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
    def selected_binding(cls, config):
        profile = config.controller_profile
        if profile in cls.panda_effort_profiles:
            from .physical_candidate import physical_binding_from_config
            return physical_binding_from_config(config)
        cube_force_z_N = dict(getattr(config, 'task_parameters', ())).get('cube_force_z_N')
        if cube_force_z_N is not None and (config.physics_provider != 'mujoco'
                or config.environment.runtime.backend != 'cpu' or profile != 'r1'):
            raise ValueError('PickCube Task COM force requires the MuJoCo CPU R1 grouped interval')
        if profile == 'r1_split' and config.robot_uid is None:
            raise ValueError('split Position Controllers require an explicitly selected Robot source recipe')
        environment = (_nut_aligned_environment_config(config.environment)
                       if profile in _PICKCUBE_R3_PROFILES else config.environment)
        binding = make_reference_binding(
            controller_profile=profile, source_delivery_manifest=config.source_delivery_manifest,
            resolved_config=environment,
            lift_height_m=dict(config.task_parameters).get("lift_height_m"),
            task_config=json.loads(config.task_configuration_json),
            interval_provider=config.physics_provider,
            cube_force_z_N=cube_force_z_N,
        )

        if config.reset_profile is not None:
            from ...observations.selected_reference import switch_observation_space
            from ...environment.reset_switch import prepare_switch_reset
            binding = replace(binding,
                prepare_reset_switch=prepare_switch_reset,
                observation_space_factory=lambda _env: dict(switch_observation_space().spaces),
                observation_metadata={
                    'schema_version': config.reset_profile,
                    'hand_pose_frame': 'panda-v1/ee',
                    'joint_order': [*(f'panda-v1/joint{i}' for i in range(1, 8)),
                                    'panda-v1/finger_joint1', 'panda-v1/finger_joint2'],
                    'joint_position_units': ['rad'] * 7 + ['m'] * 2,
                    'joint_velocity_units': ['rad/s'] * 7 + ['m/s'] * 2,
                })
        return binding



from ...artifacts import (ExecutionSpecV1, RendererSelectionV1, ArticulationDefinition,
    AssetDefinition, EntityInstance, FrameDefinition, FrameReference, JointDefinition,
    SceneDefinition)
from ...artifacts.execution import EpisodeResetPlanV1
from ...environment import sample_episode_reset_plan, adapt_legacy_recipe_task_source, compile_task_artifact_v1
from ...assembly.source import UsdTaskSceneSourceV1
from ...assembly.usd_delivery import load_usd_asset_delivery, resolve_provider_representation
from ...runtime.sessions.source import UsdRuntimeSourceV1, UsdRuntimeInputV1

SCHEMA_VERSION = "pick-cube-isaac-scene-v1"
SCENE_RECIPE_ID = "pick-cube-isaac-desktop-scene-v1"
ISAAC_PROFILE_V1 = "isaac-gpu-physx-pickcube-f06-v1"
ISAAC_REPRESENTATION_V1 = "isaacsim-6.2.0.0-pickcube-desktop-v1"
ISAAC_DELIVERY_MANIFEST_SHA256_V1 = (
    "6cb07d216689d1e0b6f31ef127d9a511906be90c2acbecb9a30667cdebf113e2"
)


def build_pickcube_isaac_scene(task_config: dict, *, robot=None) -> SceneDefinition:
    """Compose the Panda source with task-owned PickCube entities and recipe."""
    from ...registry import AGENT_REGISTRY
    from ...runtime.sessions.source_scene_import import declare_panda_scene

    scene_id = str(task_config["recipe"]["scene_uid"])
    if robot is None:
        robot = AGENT_REGISTRY.create('panda-v1')
    panda_scene = declare_panda_scene(robot, entity_id="panda-v1", scene_id=scene_id)
    source_asset = panda_scene.assets[0]
    if not source_asset.source_content_sha256:
        raise ValueError("Panda importer must provide the consumed source closure digest")

    panda_asset = AssetDefinition(
        schema_version="asset-definition-v1",
        asset_id="f05-dg03-menagerie-panda-source-preserving-isaac-usd",
        asset_version="f05-dg03-isaac-usd-v4",
        source_reference=source_asset.source_reference,
        source_revision=source_asset.source_revision,
        source_content_sha256=source_asset.source_content_sha256,
        license_id="bsd-3-clause",
    )
    return build_pickcube_scene(task_config, robot_scene=panda_scene, robot_asset=panda_asset,
        ee_frame='ee', cube_frame='cube', cube_joint='cube_freejoint', table_frame='top')


def build_pickcube_scene(task_config, *, robot_scene, robot_asset, ee_frame, cube_frame, cube_joint, table_frame):
    """Compose Task entities with an already declared Robot and source frame names."""
    scene_id = robot_scene.scene_id
    robot_entity = replace(robot_scene.entities[0], asset_id=robot_asset.asset_id,
                           asset_version=robot_asset.asset_version)
    recipe_digest = hashlib.sha256(_canonical_task_recipe(task_config)).hexdigest()
    cube_asset = AssetDefinition(
        "asset-definition-v1", "pick-cube-cube-v1", "pick-cube-recipe-v1",
        "geochora-task-scene://pick-cube-v1/cube", SCENE_RECIPE_ID, recipe_digest,
    )
    tabletop_asset = AssetDefinition(
        "asset-definition-v1", "pick-cube-tabletop-v1", "pick-cube-recipe-v1",
        "geochora-task-scene://pick-cube-v1/tabletop", SCENE_RECIPE_ID, recipe_digest,
    )
    cube = EntityInstance(
        "entity-instance-v1", "cube-v1", cube_asset.asset_id, cube_asset.asset_version,
    )
    tabletop = EntityInstance(
        "entity-instance-v1", "tabletop-v1", tabletop_asset.asset_id,
        tabletop_asset.asset_version,
    )
    identity_pose = PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
    cube_articulation = ArticulationDefinition(
        "articulation-definition-v1",
        "cube-v1",
        "world",
        ("world", cube_frame),
        (JointDefinition(
            "joint-definition-v1",
            cube_joint,
            FrameReference("cube-v1", "world"),
            FrameReference("cube-v1", cube_frame),
            identity_pose,
            identity_pose,
            "floating",
            None,
            "xyz_meter_quaternion_wxyz",
            "linear_xyz_meter_per_second_angular_xyz_radian_per_second",
            7,
            6,
        ),),
    )
    return SceneDefinition(
        schema_version="scene-definition-v3",
        scene_id=scene_id,
        assets=(robot_asset, cube_asset, tabletop_asset),
        entities=(robot_entity, cube, tabletop),
        frames=(
            *robot_scene.frames,
            FrameDefinition("frame-definition-v1", robot_entity.entity_id, ee_frame, "runtime", None, None),
            FrameDefinition("frame-definition-v1", "cube-v1", "world", "runtime", None, None),
            FrameDefinition("frame-definition-v1", "cube-v1", cube_frame, "runtime", None, None),
            FrameDefinition("frame-definition-v1", "tabletop-v1", table_frame, "runtime", None, None),
        ),
        articulations=(*robot_scene.articulations, cube_articulation),
        robots=robot_scene.robots,
        actuator_resources=robot_scene.actuator_resources,
        control_groups=robot_scene.control_groups,
    )


def _canonical_task_recipe(task_config: dict) -> bytes:
    return json.dumps(
        {"schema_version": SCHEMA_VERSION, "recipe": task_config["recipe"]},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def compile_pickcube_isaac_task_artifact(task_config: dict, legacy_artifact, *, robot=None):
    """Compile the existing PickCube v0 semantics against its USD Scene."""
    if set(task_config) - {'recipe', 'environment', 'execution'}:
        raise ValueError('unsupported PickCube task config fields')
    scene = build_pickcube_isaac_scene(task_config, robot=robot)
    # Execution defaults are consumed by configuration, not Task Source.
    task_source = adapt_legacy_recipe_task_source({
        'recipe': task_config['recipe'], 'environment': task_config['environment'],
    })
    artifact = compile_task_artifact_v1(
        task_source, scene, legacy_artifact,
        frame_bindings={
            "panda-v1/base": FrameReference("panda-v1", "link0"),
            "panda-v1/ee": FrameReference("panda-v1", "ee"),
        },
    )
    # The v0 Artifact's reset/success pose is the cube Entity identity, while
    # RuntimeSourceV1 needs that pose bound to the cube's measured body Frame.
    # Keep this task-specific alias explicit in the v1 projection.
    bindings = dict(artifact.legacy_frame_bindings)
    bindings["cube-v1"] = FrameReference("cube-v1", "cube")
    from dataclasses import replace

    artifact = replace(artifact, legacy_frame_bindings=bindings)
    artifact.validate_scene(scene)
    return task_source, scene, artifact


def _source_bindings(scene: SceneDefinition, artifact: TaskArtifactV1):
    entry = "/F06Scene"
    body_paths = {
        "panda-v1/base": f"{entry}/panda/Geometry/link0",
        "cube-v1": f"{entry}/cube_v1",
    }
    frame_paths = {
        "panda-v1/ee": (
            f"{entry}/panda/Geometry/link0/link1/link2/link3/link4/"
            "link5/link6/link7/hand/ee"
        ),
        "tabletop-v1/top": f"{entry}/tabletop_v1/top",
    }
    scalar_joints = {}
    for articulation in scene.articulations:
        for joint in articulation.joints:
            if joint.kind in {"revolute", "continuous", "prismatic"}:
                semantic = f"{articulation.entity_id}/{joint.joint_id}"
                scalar_joints[semantic] = joint.joint_id
    required = set(artifact.legacy_joint_bindings)
    if set(scalar_joints) != required:
        raise ValueError("F06 USD binding map must cover every PickCube scalar Joint exactly")
    if set(body_paths) | set(frame_paths) != set(artifact.legacy_frame_bindings):
        raise ValueError("F06 USD body/frame map must cover every PickCube TaskArtifact runtime Frame")
    if set(artifact.initialization.poses_world) != {"cube-v1"}:
        raise ValueError("F06 PickCube reset must bind exactly the task-owned floating cube")
    return scalar_joints, body_paths, frame_paths, {"cube-v1": f"{entry}/cube_v1"}


def build_pickcube_isaac_runtime_input_v1(
    delivery_manifest: str | Path, *, task_seed: int = 31, horizon: int = 1000,
    task_config=None, physical_fixture=False, robot=None,
) -> UsdRuntimeInputV1:
    """Build the current PickCube Task and public USD source through Core owners."""

    if type(task_seed) is not int or task_seed < 0:
        raise ValueError("F06 PickCube task_seed must be a nonnegative integer")
    if type(horizon) is not int or not 1 <= horizon <= 1000:
        raise ValueError("F06 PickCube horizon must be an integer in [1, 1000]")
    path = Path(delivery_manifest).resolve(strict=True)
    loaded = load_usd_asset_delivery(path)
    manifest_sha = loaded.manifest_bytes_sha256
    if (manifest_sha != ISAAC_DELIVERY_MANIFEST_SHA256_V1
            or not loaded.locally_validated or loaded.source_verified
            or loaded.delivery.representation_id != ISAAC_REPRESENTATION_V1):
        raise ValueError("F06 builder requires the exact generated PickCube desktop delivery v1")

    task_config = _configuration() if task_config is None else task_config
    legacy_artifact = build_artifact(task_config=task_config)
    if physical_fixture not in (False, 'coexist', 'effort-only'):
        raise ValueError('F06 physical fixture must select coexist or effort-only')
    if physical_fixture:
        # The source and task recipe remain unchanged. This versioned Artifact
        # starts the coupled fingers inside their limits for force observation.
        positions = dict(legacy_artifact.initialization.joint_position)
        positions.update({'panda-v1/finger_joint1': .02, 'panda-v1/finger_joint2': .02})
        legacy_artifact = replace(legacy_artifact,
            artifact_id=('pickcube-f06-physical-effort-fixture-v1' if physical_fixture == 'coexist'
                         else 'pickcube-f06-physical-effort-no-drive-v1'),
            initialization=replace(legacy_artifact.initialization, joint_position=positions,
                                   reset_validity=('f06-physical-effort-interior-fingers-v1'
                                                   if physical_fixture == 'coexist'
                                                   else 'f06-physical-effort-no-drive-v1')))
    task_source, scene, artifact = compile_pickcube_isaac_task_artifact(
        task_config, legacy_artifact, robot=robot,
    )
    options = {
        "f06_goal": "PickCube-Harness-three-backend-example",
        "lowering": "pickcube-desktop-physx-native-mimic-v1",
        "delivery_manifest_sha256": manifest_sha,
        "task_scene_recipe_sha256": hashlib.sha256(
            _canonical_task_recipe(task_config)
        ).hexdigest(),
    }
    representation = resolve_provider_representation(
        loaded, provider="isaacsim", provider_build_identity="isaacsim-6.2.0.0",
        options=options,
    )
    task_scene_source = UsdTaskSceneSourceV1(
        "usd-task-scene-source-v1", loaded, representation,
        task_source.identity_hash, scene.identity_hash,
    )
    joints, bodies, frames, free_joints = _source_bindings(scene, artifact)
    source = UsdRuntimeSourceV1(
        "usd-runtime-source-v1", artifact, scene, task_scene_source,
        joints, bodies, frames, free_joints, joints,
    )
    reset_plan = sample_episode_reset_plan(
        task_source, scene, artifact, task_seed=task_seed,
    )
    execution = ExecutionSpecV1(
        "execution-spec-v1", "isaacsim", "cuda", ISAAC_PROFILE_V1,
        task_seed, "best_effort", RendererSelectionV1(
            "renderer-selection-v1", "none", "cpu", "none", None,
        ), "cuda:0", (),
    )
    policy = {
        'schema_version': 'usd-task-admission-policy-v1',
        'bindings': {
            'joints': dict(joints), 'joint_targets': dict(joints),
            'bodies': dict(bodies), 'frames': dict(frames), 'free_joints': dict(free_joints),
        },
        'controller_profile': 'r3_continuous_v1', 'horizon_min': 1, 'horizon_max': 1000,
    }
    result = UsdRuntimeInputV1(
        "pick-cube-isaac-runtime-input-v1", task_source, artifact, source,
        execution, reset_plan, "r3_continuous_v1", horizon, manifest_sha, policy,
    )
    from ...runtime.sessions.api import _validate_f06_pickcube_isaac_input
    _validate_f06_pickcube_isaac_input(result, artifact, execution, source)
    return result
