"""Selected PickCube P1.6 task definition, construction and task semantics."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import inspect
import json
import math
from pathlib import Path
import subprocess

import numpy as np

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
from ...controllers.canonical.contracts import digest
from ...controllers.canonical.execution import (
    ReferenceExecutionController, StableArmTargetHold,
)
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
from ...planners import AbsolutePosePlannerConfig
from ...robots.panda import PandaAgent
from ...runtime.sessions.source import RuntimeSource
from ...environment.reference_binding import ReferenceTaskBinding
from ...environment.reference_env import SelectedReferenceEnv
from ...objects.pick_cube import (
    CUBE_CONTACT_MARGIN, CUBE_DIAG_INERTIA, CUBE_HALF_SIZE, CUBE_MASS,
    EE_SITE_NAME, PickCubeSceneComposer,
)


CONFIG_PATH = Path(__file__).with_name("config.yaml")
EEF = "panda-v1/ee"
FINGERS = ("panda-v1/finger_joint1", "panda-v1/finger_joint2")
TASK_CONFIGURATION_KEYS = ("recipe", "environment")
PICKCUBE_CONTROLLER_PROFILES = {
    "r1",
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

from .task import semantic_definition, evaluate, sample_reset

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
    return compile_panda_box_source(declaration, artifact, config)


def _source_identity_files(controller, solution_type, *, profile_source=None):
    root = Path(__file__).resolve().parents[3]
    files = {Path(__file__).resolve(), Path(__file__).with_name("task.py").resolve(), CONFIG_PATH.resolve(),
             Path(inspect.getsourcefile(PickCubeSceneComposer)).resolve(),
             Path(inspect.getsourcefile(compile_panda_box_source)).resolve(),
             Path(__file__).parents[2].joinpath("assembly/compiler.py").resolve(),
             Path(inspect.getsourcefile(compile_declared_artifact)).resolve(),
             Path(inspect.getsourcefile(type(controller))).resolve(),
             Path(inspect.getsourcefile(solution_type)).resolve(),
             Path(inspect.getsourcefile(AbsolutePosePlannerConfig)).resolve(),
             Path(inspect.getsourcefile(ReferenceTaskBinding)).resolve(),
             Path(inspect.getsourcefile(SelectedReferenceEnv)).resolve(),
             Path(inspect.getsourcefile(TaskArtifact)).resolve(),
             root / "task_env/recorders/reference_provenance.py",
             root / "task_env/recorders/position_metadata.py",
             root / "task_env/observations/selected_reference.py",
             Path(inspect.getsourcefile(RuntimeSource)).resolve()}
    canonical = root / "task_env" / "controllers" / "canonical"
    files.update(path.resolve() for path in canonical.glob("*.py") if path.is_file())
    if profile_source is not None:
        files.add(Path(profile_source).resolve())
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(files)}


def _r3_dynamic_profile():
    from ...controllers.canonical.production_r3 import R3_PROFILE_PATH, load_r3_dynamic_profile
    return load_r3_dynamic_profile(), R3_PROFILE_PATH


def build_reference(*, backend="cpu", include_solution=True, controller_profile="r1", resolved_config=None, lift_height_m=None, task_config=None):
    """Construct the single selected P1.6 route without importing a provider."""
    from ...controllers.canonical import ProductionCanonicalPandaController
    from ...controllers.canonical.contracts import digest
    from .solution import PickCubeReadinessConfig, PickCubeReadinessSolution

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
    if controller_profile == "r1":
        controller = ProductionCanonicalPandaController.from_source(artifact, source)
    else:
        from ...controllers.canonical.production_r3 import ProductionCanonicalPandaControllerR3
        controller = ProductionCanonicalPandaControllerR3.from_source(
            artifact, source, profile=dynamic_profile,
            joint_velocity_limit_rad_s=(
                PICKCUBE_R3_CONTINUOUS_PROFILE_V1["joint_velocity_limit_rad_s"]
            ),
        )
    solution_identity = PickCubeReadinessSolution.identity_for_config(readiness)
    solution = PickCubeReadinessSolution(config=readiness) if include_solution else None
    base_controller_identity = None
    execution_profile = None
    if is_r3_profile:
        # Match NutAssembly's complete selected R3 execution chain while keeping
        # PickCube's Artifact, source, reset and Solution task-owned.
        controller.gripper_config = replace(
            controller.gripper_config, force_limit_N=10.0,
        )
        base_controller_identity = controller.identity
        arm_hold = StableArmTargetHold(controller)
        execution_controller = ReferenceExecutionController(
            arm_hold, artifact.timebase.control_dt, gripper_rate_hz=500,
        )
        execution_support_sha256 = {
            "arm_and_execution_wrapper": hashlib.sha256(
                Path(inspect.getsourcefile(StableArmTargetHold)).read_bytes()
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
    if controller_profile != "r1":
        resolved["controller_profile"] = controller_profile
        resolved["task_controller_profile"] = dict(PICKCUBE_R3_CONTINUOUS_PROFILE_V1)
        resolved["task_controller_profile"]["posture_path_profile"] = posture_path_profile
        resolved["resolved_controller_profile"] = controller.rate_profile_mapping()
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
                          resolved_config=None, task_config=None):
    """Build the exact F06 Isaac source through the existing PickCube owners."""
    if controller_profile != "r3_continuous_v1":
        raise ValueError("F06 Isaac freezes the existing r3_continuous_v1 profile")
    from ...controllers.canonical.position_profile import PandaPositionServoProfileV1
    from ...controllers.canonical.kinematics import PANDA_PICKCUBE_EE_TCP_V1
    from ...controllers.canonical.contracts import digest
    from .isaac import build_pickcube_isaac_runtime_input_v1
    from .solution import PickCubeReadinessSolution

    # Reuse the task's existing action/readiness configuration and production
    # R3 physical profile; only the source-bound position writer changes.
    legacy = build_reference(backend="cpu", include_solution=False,
                             controller_profile=controller_profile, resolved_config=resolved_config, task_config=task_config)
    runtime_input = build_pickcube_isaac_runtime_input_v1(
        delivery_manifest, task_seed=task_seed, horizon=horizon, task_config=task_config,
    )
    manifest_path = Path(delivery_manifest).resolve(strict=True)
    panda_xml_path = manifest_path.parent / runtime_input.runtime_source.scene_source.loaded_delivery.delivery.source_entry_file
    panda_xml = panda_xml_path.read_text()
    from ...assembly.usd_delivery import load_usd_asset_delivery
    loaded = load_usd_asset_delivery(manifest_path)
    if hashlib.sha256(panda_xml.encode("utf-8")).hexdigest() != loaded.delivery.source_entry_sha256:
        raise ValueError("F06 kinematics Panda XML differs from the frozen source-entry bytes")
    dynamic_profile, _profile_source = _r3_dynamic_profile()
    controller = PandaPositionServoProfileV1.from_usd_source(
        runtime_input.artifact, runtime_input.runtime_source,
        execution=runtime_input.execution, kinematics_source_xml=panda_xml,
        config=legacy["source"].config.action,
        pose_target_method="achieved_state_dls_v1",
        arm_tracking_method="production_r3_continuous_v1",
        arm_tracking_profile=dynamic_profile,
        arm_joint_velocity_limit_rad_s=(
            PICKCUBE_R3_CONTINUOUS_PROFILE_V1["joint_velocity_limit_rad_s"]
        ),
        entity_id="panda-v1", hand_frame_id="ee",
        tcp_profile=PANDA_PICKCUBE_EE_TCP_V1,
    )
    readiness = legacy["readiness"]
    solution_identity = PickCubeReadinessSolution.identity_for_config(readiness)
    solution = PickCubeReadinessSolution(config=readiness) if include_solution else None
    source_ids = dict(legacy["source_sha256"])
    for path in (Path(__file__), Path(__file__).with_name("isaac.py"),
                 Path(__file__).parents[2] / "controllers/canonical/position_profile.py",
                 Path(__file__).parents[2] / "controllers/canonical/kinematics.py"):
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
    effective_config_sha = hashlib.sha256(json.dumps(
        effective_config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    resolved = {
        "construction_id": "pickcube-p16-reference-construction-v2",
        "task_recipe": legacy["resolved_configuration"]["task_recipe"],
        "artifact": runtime_input.artifact.to_mapping(),
        "artifact_sha256": runtime_input.artifact.identity_hash,
        "runtime_config": effective_config,
        "runtime_config_sha256": effective_config_sha,
        "readiness": asdict(readiness), "resolved_controller_action": asdict(controller.config),
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
        "tcp_profile": controller.tcp_profile.to_mapping(),
        "qualification": "NOT_REQUALIFIED",
    }
    return {
        "construction_id": resolved["construction_id"],
        "artifact": runtime_input.artifact,
        "source": runtime_input.runtime_source,
        "readiness": readiness,
        "controller": controller,
        "solution": solution,
        "solution_factory": lambda: PickCubeReadinessSolution(config=readiness),
        "solution_identity": solution_identity,
        "source_revision": revision,
        "source_sha256": source_ids,
        "recipe_identity": digest(resolved),
        "resolved_configuration": resolved,
        "execution_spec_v1": runtime_input.execution,
        "reset_plan": runtime_input.reset_plan,
        "controller_binding_plan": None,
        "f06_pickcube_isaac_input": runtime_input,
        "session_admission_input": runtime_input,
        "f06_delivery_manifest_path": str(manifest_path),
        "kinematics_source_xml": panda_xml,
    }


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


def make_reference_binding(*, controller_profile="r1", source_delivery_manifest=None,
                           resolved_config=None, lift_height_m=None, task_config=None,
                           interval_provider=None):
    if controller_profile not in PICKCUBE_CONTROLLER_PROFILES:
        raise ValueError(f"unsupported PickCube controller_profile: {controller_profile!r}")
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
        return build_reference(backend="cpu", include_solution=False, controller_profile=controller_profile, resolved_config=resolved_config, lift_height_m=lift_height_m, task_config=task_config)

    def build_external(provider):
        if provider == "isaacsim":
            return build_isaac_reference(
                delivery_manifest=source_delivery_manifest, include_solution=False,
                controller_profile=controller_profile,
                **({"resolved_config": resolved_config} if resolved_config is not None else {}),
                **({"task_config": task_config} if task_config is not None else {}),
            )
        return build_reference(backend="cpu", include_solution=False,
                               controller_profile=controller_profile, resolved_config=resolved_config, lift_height_m=lift_height_m, task_config=task_config)

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
        return build_reference(backend="cpu", include_solution=False, controller_profile=controller_profile, resolved_config=resolved_config, lift_height_m=lift_height_m, task_config=task_config)

    return ReferenceTaskBinding(
        build=build,
        build_external=build_external,
        build_seeded=build_seeded,
        validate_external_solution=_validate_external_readiness_solution,
        reset_sample=lambda artifact, seed: sample_reset(artifact, seed, lift_height_m=lift_height_m, task_config=task_config),
        evaluate=lambda state, semantics: evaluate(state, semantics, lift_height_m=lift_height_m, task_config=task_config),
        object_poses=(("cube-v1", "cube_v1"),),
        external_actions=True,
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
    binding = make_reference_binding()

    uses_selected_public_config = True
    selected_controller_profiles = frozenset(PICKCUBE_CONTROLLER_PROFILES)
    selected_parameter_limits = {"lift_height_m": (0.01, 0.25)}
    selected_supports_isaac = True
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
    def from_reference_config(cls, config=None, *, render_mode=None, **kwargs):
        """Compatibility entry; parsing belongs to the common resolver."""
        from ...environment.configuration import resolve_task_env_config
        return cls.from_resolved_config(resolve_task_env_config(cls, config),
                                        render_mode=render_mode, **kwargs)

    @classmethod
    def from_resolved_config(cls, config, *, render_mode=None, **kwargs):
        from ...environment.config import ResolvedSelectedConfig
        if type(config) is not ResolvedSelectedConfig:
            raise TypeError("selected construction requires resolved configuration")
        if kwargs or render_mode is not None:
            raise ValueError('selected reference admits state-only execution without extra kwargs')
        provider = config.physics_provider
        backend = config.environment.runtime.backend
        horizon = config.environment.episode.horizon
        profile = config.controller_profile
        manifest = config.source_delivery_manifest
        if profile in _PICKCUBE_R3_PROFILES:
            config = replace(
                config,
                environment=_nut_aligned_environment_config(config.environment),
            )
        task_config = json.loads(config.task_configuration_json)
        binding = make_reference_binding(controller_profile=profile, source_delivery_manifest=manifest,
                                         resolved_config=config.environment,
                                         lift_height_m=dict(config.task_parameters).get("lift_height_m"),
                                         task_config=task_config,
                                         interval_provider=provider)
        if provider == 'isaacsim':
            initial = build_isaac_reference(delivery_manifest=manifest, task_seed=31,
                                            horizon=horizon, include_solution=False,
                                            controller_profile=profile, resolved_config=config.environment,
                                            task_config=task_config)
            env = cls(provider=provider, backend=backend, horizon=horizon, _binding=binding,
                      _execution_spec_v1=initial['execution_spec_v1'], _initial_value=initial)
        else:
            env = cls(provider=provider, backend=backend, horizon=horizon, _binding=binding)
        env.resolved_public_config = config
        return env
