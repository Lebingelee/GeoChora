"""Selected NutAssembly Task Artifact, semantics, scene and public binding."""
from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
import math
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import numpy as np
from ...environment.task_definition import as_task_state_view

from ...artifacts import (
    ActionIntent, CanonicalStateView, EntityDefinition, InitializationContract,
    PoseWorld, SemanticDefinition, TaskArtifact, Timebase,
)
from ...artifacts.execution import ResetSample
from ...assembly.nut_assembly import build_nut_assembly_model_xml
from ...assembly.compiler import (
    ReferenceTaskDeclarationV1,
    reference_task_identity_fields,
)
from ...assembly.source import TaskSceneSource
from ...controllers.canonical.contracts import (digest, REFERENCE_POSE_ACTION_SCHEMA,
    reference_pose_action, reference_pose_action_space)
from ...controllers.canonical.execution import build_reference_position_controller
from ...controllers.canonical.production_r3 import (
    R3_PROFILE_PATH, load_r3_dynamic_profile,
)
from ...environment import TaskCompositionSpec
from ...environment.configuration import (
    load_yaml_mapping,
    overlay_public_env_config,
    resolve_env_config,
)
from ...environment.task_source import TaskArtifactDeclarationV1
from ...objects.nut_assembly import (
    NUTASSEMBLY_NOMINAL_V1_DIAG_INERTIA,
    NUTASSEMBLY_NOMINAL_V1_ID, NUTASSEMBLY_NOMINAL_V1_MASS,
    NUT_CONTACT_MARGIN, NUT_FREEJOINT_ARMATURE, NUT_FREEJOINT_DAMPING,
    NUT_HALF_HEIGHT, NUT_HANDLE_LOCAL_X, PEG_HALF_HEIGHT, ROUND_PEG_RADIUS,
    SQUARE_PEG_HALF_WIDTH,
)
from ...observations.selected_reference import build_selected_observation, selected_reference_observation_spaces
from ...registry import make_agent, make_object, make_scene, register_env
from ...robots.panda import panda_reference_control_binding
from ...robots.panda import PandaAgent
from ...runtime.sessions.source import RuntimeSource
from ...utils.rotation import quat_wxyz_to_matrix
from ...environment.reference_binding import ReferenceTaskBinding
from ...environment.reference_env import SelectedReferenceEnv
from .solution import (
    NutAssemblyNativeFeedbackSampleV1, NutAssemblyNativeIntervalReceiptV1,
    NutAssemblyOutcomeSolutionV1, NutAssemblySolutionConfig,
    OUTCOME_POLICY_ID,
)

CONFIG_PATH = Path(__file__).with_name("config.yaml")
REFERENCE_ENV_ID = "nut-assembly-outcome-reference-v1"
EEF = "panda-v1/ee"
NUT = "square-nut-v1"
PEG = "square-peg-v1"
FINGERS = ("panda-v1/finger_joint1", "panda-v1/finger_joint2")
SUCCESS = "nut_on_square_peg_canonical_state_v0"


from .task import (NutAssemblyTaskDefinition, semantic_definition, evaluate, sample_reset, _reset_seed)

def _native_feedback_sample(env, stage, index, state, feedback, target, applied, diagnostics,
                            provider_feedback_sample, request_boundary):
    metrics = None
    if stage == "close_gripper":
        _, observation_info, _ = env.observation(state)
        metrics = observation_info["task_metrics"]
    ee = state.pose_world["panda-v1/ee"]
    sample = NutAssemblyNativeFeedbackSampleV1(
        "nutassembly-native-feedback-sample-v1",
        env.provider,
        provider_feedback_sample.provider_materialization_id,
        env.artifact.identity_hash,
        env.value["source"].scene_source.source_id,
        env._source_xml_sha256(),
        request_boundary["controller_identity"],
        request_boundary["solution_identity"],
        request_boundary["episode_id"],
        request_boundary["reset_sample_id"],
        request_boundary["identity_hash"],
        float(state.simulation_time),
        int(state.control_step),
        int(index),
        int(provider_feedback_sample.actuator_force_measurement.sample_sequence),
        float(provider_feedback_sample.actuator_force_measurement.native_sample_time_s),
        float(env.artifact.timebase.physics_dt),
        str(provider_feedback_sample.actuator_force_measurement.phase),
        "valid" if provider_feedback_sample.actuator_force_measurement.valid else "invalid",
        tuple((*ee.position, *ee.quaternion_wxyz)),
        feedback,
        dict(diagnostics),
        provider_feedback_sample,
        target.identity_hash,
        applied.to_mapping(),
        None if metrics is None else bool(metrics.get("grasped_nut", False)),
    )
    return sample


def _native_interval_receipt(env, request_boundary, evaluation_boundary, native_samples, substeps):
    expected = env.artifact.timebase.control_substeps
    if expected != 5 or len(native_samples) != expected or len(substeps) != expected:
        raise ValueError("NutAssembly native interval requires five completed 2 ms applications")
    if tuple(index for index, _, _ in substeps) != tuple(range(expected)):
        raise ValueError("NutAssembly native interval substeps are missing or out of order")
    return NutAssemblyNativeIntervalReceiptV1(
        "nutassembly-native-interval-receipt-v1",
        env.provider,
        request_boundary["provider_materialization_id"],
        env.artifact.identity_hash,
        env.value["source"].scene_source.source_id,
        env._source_xml_sha256(),
        request_boundary["controller_identity"],
        request_boundary["solution_identity"],
        request_boundary["episode_id"],
        request_boundary["reset_sample_id"],
        request_boundary,
        evaluation_boundary,
        float(env.artifact.timebase.physics_dt),
        expected,
        len(native_samples),
        tuple(native_samples),
    )


def _observe_kwargs(env, native_samples, receipt):
    if not isinstance(receipt, NutAssemblyNativeIntervalReceiptV1):
        raise ValueError("NutAssembly Solution observation requires a completed native interval receipt")
    return {"readiness": env.controller.readiness(env.state, env.feedback),
        "native_samples": tuple(native_samples),
        "native_interval_receipt": receipt}

def _configuration():
    value = load_yaml_mapping(CONFIG_PATH)
    if (not isinstance(value, dict)
            or not {"recipe", "environment"}.issubset(value)
            or set(value) - {"recipe", "environment", "execution"}):
        raise ValueError("NutAssembly config.yaml must contain recipe, environment, and optional execution")
    if "execution" in value and not isinstance(value["execution"], dict):
        raise TypeError("NutAssembly execution defaults must be a mapping")
    recipe = value["recipe"]
    if (recipe.get("control_hz") != 100 or recipe.get("control_substeps") != 5
            or recipe.get("physics_dt") != 0.002 or recipe.get("control_dt") != 0.01
            or recipe.get("artifact_id") != "nut-assembly-square-v1/p1_8_e/nominal-v1"
            or recipe.get("outcome_policy", {}).get("policy_id") != OUTCOME_POLICY_ID
            or recipe.get("solution", {}).get("version") != NutAssemblyOutcomeSolutionV1.version):
        raise ValueError("NutAssembly admits only the selected 100 Hz Outcome V1 recipe")
    readiness = recipe["outcome_policy"]["readiness_allowlist"]
    if readiness != {"stage": "descend_to_handle", "reason": "stable_height_mismatch",
            "maximum_occurrences": 1, "maximum_height_residual_m": 0.0003,
            "minimum_pose_wait_s": 0.5, "pose_window_s": 0.2,
            "axis_span_m": 0.0001, "speed_m_s": 0.002}:
        raise ValueError("selected Outcome V1 readiness warning allowlist changed")
    controller = recipe["controller"]
    if (controller["force_target_N"] != 10.0 or controller["force_cap_N"] != 10.0
            or controller["gripper_overrides"].get("force_limit_N") != 10.0):
        raise ValueError("selected R3 force target/cap must remain 10 N")
    provider = recipe["providers"].get("mujoco", {})
    if provider.get("option_overrides") != {"noslip_iterations": 2}:
        raise ValueError("selected MuJoCo solver profile changed")
    asset, scene = recipe["asset"], recipe["scene"]
    if (asset["nut_mass_kg"] != NUTASSEMBLY_NOMINAL_V1_MASS
            or tuple(asset["nut_diagonal_inertia_kg_m2"]) != NUTASSEMBLY_NOMINAL_V1_DIAG_INERTIA
            or asset["nut_contact_margin_m"] != NUT_CONTACT_MARGIN
            or asset["freejoint_damping"] != NUT_FREEJOINT_DAMPING
            or asset["freejoint_armature"] != NUT_FREEJOINT_ARMATURE
            or scene["peg_half_height"] != PEG_HALF_HEIGHT
            or scene["square_peg_half_width"] != SQUARE_PEG_HALF_WIDTH
            or scene["round_peg_radius"] != ROUND_PEG_RADIUS):
        raise ValueError("selected nominal object and contact asset parameters changed")
    return value


def _recipe():
    return _configuration()["recipe"]


def _artifact_declaration(*, lift_height_m=None, task_config=None, robot=None) -> TaskArtifactDeclarationV1:
    recipe = _recipe() if task_config is None else task_config["recipe"]
    scene, reset, asset = recipe["scene"], recipe["reset"], recipe["asset"]
    robot_uids = tuple(recipe['agent_uids'])
    if len(robot_uids) != 1:
        raise ValueError('NutAssembly requires one declared Robot')
    robot = make_agent(robot_uids[0]) if robot is None else robot
    if robot.uid != robot_uids[0]:
        raise ValueError('Robot differs from NutAssembly task declaration')
    initialization = {"nut_pose": reset["nut_pose"], "joint_position": reset["joint_position"]}
    mass = float(asset["nut_mass_kg"])
    inertia = tuple(float(v) for v in asset["nut_diagonal_inertia_kg_m2"])
    if (mass != NUTASSEMBLY_NOMINAL_V1_MASS
            or inertia != tuple(NUTASSEMBLY_NOMINAL_V1_DIAG_INERTIA)):
        raise ValueError("selected nominal Nut asset profile changed")
    return TaskArtifactDeclarationV1(artifact_id=recipe["artifact_id"], task_id=recipe["task_uid"],
        version=recipe["artifact_version"], entities=(
            EntityDefinition("tabletop-v1", "static", "nut-assembly-square-v1/task-local/table",
                (), (), "box", "support_contact", {"top_z": float(scene["table_top_z"])}),
            robot.artifact_entity(),
            EntityDefinition("square-nut-v1", "movable",
                "nut-assembly-square-v1/task-local/square-nut/" + NUTASSEMBLY_NOMINAL_V1_ID,
                (), (), "authored_compound", "table_hand_peg_contact",
                {"mass": mass, **{f"inertia_{axis}": value for axis, value in zip("xyz", inertia)}}),
            EntityDefinition("square-peg-v1", "static", "nut-assembly-square-v1/task-local/square-peg",
                (), (), "box", "nut_contact", {"half_height": float(scene["peg_half_height"])}),
            EntityDefinition("round-peg-v1", "static", "nut-assembly-square-v1/task-local/round-peg",
                (), (), "cylinder", "nut_contact", {"half_height": float(scene["peg_half_height"])}),
        ), action=ActionIntent("absolute_pose", "world", "quaternion_wxyz", "arm_joint_position_and_gripper"),
        observations=tuple(recipe["observation_requirements"]),
        initialization=InitializationContract("initialization-v0",
            {"square-nut-v1": PoseWorld.from_mapping(initialization["nut_pose"])},
            dict(initialization["joint_position"]), (),
            "zero_named_joint_and_entity_velocities_arm_targets_at_initial_joints_gripper_open",
            "NA-S0_frozen_deterministic_semantic_joint_and_pose_request", 0),
        semantics=semantic_definition(lift_height_m=lift_height_m, task_config=task_config),
        timebase=Timebase(float(recipe["physics_dt"]), int(recipe["control_substeps"]), float(recipe["control_dt"])),
        capabilities=tuple(recipe["required_capabilities"]))


def build_artifact(*, lift_height_m=None, task_config=None, robot=None) -> TaskArtifact:
    """Compile the task declaration for the selected Robot."""
    return _artifact_declaration(lift_height_m=lift_height_m, task_config=task_config, robot=robot).compile()


def _environment_config(*, backend='cpu', task_config=None):
    if backend != 'cpu':
        raise ValueError('NutAssembly reference source requires CPU')
    task_config = _configuration() if task_config is None else task_config
    recipe = task_config["recipe"]
    base = resolve_env_config(task_uid=recipe["task_uid"], scene_uid=recipe["scene_uid"],
        agent_uids=tuple(recipe["agent_uids"]), object_uids=tuple(recipe["object_uids"]),
        success_definition=recipe["success_definition"])
    config = overlay_public_env_config(base, task_config["environment"])
    return replace(config, runtime=replace(config.runtime, backend=backend, prewarm=False,
        physics_dt=float(recipe["physics_dt"]), control_substeps=int(recipe["control_substeps"])),
        render=replace(config.render, camera_obs=False))


def build_runtime_source(artifact: TaskArtifact, provider="geophys", *, backend='cpu',
                         resolved_config=None,
                         lift_height_m=None, task_config=None, robot=None):
    task_config = _configuration() if task_config is None else task_config
    robot = make_agent(task_config['recipe']['agent_uids'][0]) if robot is None else robot
    if artifact.to_mapping() != build_artifact(lift_height_m=lift_height_m, task_config=task_config, robot=robot).to_mapping():
        raise ValueError("selected nominal NutAssembly Artifact required")
    if provider not in {"geophys", "mujoco"}:
        raise ValueError("selected provider must be geophys or mujoco")
    if backend != 'cpu':
        raise ValueError('NutAssembly reference source requires CPU')
    recipe = task_config["recipe"]
    source_config = recipe["controller"]
    config = (_environment_config(backend=backend, task_config=task_config)
              if resolved_config is None else resolved_config)
    config = replace(config,
        action=replace(config.action, **source_config["action_overrides"]),
        robot=replace(config.robot,
            gripper=replace(config.robot.gripper, **source_config["gripper_overrides"])))
    scene = recipe["scene"]
    scene_parameters = {**scene, "physics_dt": recipe["physics_dt"],
        "nut_contact_margin_m": recipe["asset"]["nut_contact_margin_m"],
        "freejoint_damping": recipe["asset"]["freejoint_damping"],
        "freejoint_armature": recipe["asset"]["freejoint_armature"]}
    scene_xml, base = build_nut_assembly_model_xml(scene_parameters,
        nut_mass_kg=float(recipe["asset"]["nut_mass_kg"]),
        nut_diagonal_inertia_kg_m2=tuple(recipe["asset"]["nut_diagonal_inertia_kg_m2"]),
        robot_source=robot.single_mjcf_source())
    contact_profile = None
    if provider == "mujoco":
        overrides = recipe["providers"]["mujoco"]["option_overrides"]
        if overrides != {"noslip_iterations": 2}:
            raise ValueError("selected MuJoCo provider profile changed")
        root = ET.fromstring(scene_xml)
        option = root.find("option")
        if option is None:
            raise ValueError("MJCF source has no option element")
        for key, value in overrides.items():
            option.set(key, str(value))
        scene_xml = ET.tostring(root, encoding="unicode")
        contact_profile = {"provider": "mujoco", "version": "mujoco-coulomb-noslip2-v1",
            "native_version_tested": recipe["providers"]["mujoco"]["native_version_tested"],
            "model_option_overrides": overrides}
    composition = TaskCompositionSpec(recipe["task_uid"], recipe["scene_uid"],
        tuple(recipe["agent_uids"]), tuple(recipe["object_uids"]),
        success_definition=recipe["success_definition"])
    runtime_source = ReferenceTaskDeclarationV1(
        artifact=_artifact_declaration(lift_height_m=lift_height_m, task_config=task_config, robot=robot),
        composition=composition,
        bodies={"square-nut-v1": "SquareNut", "square-peg-v1": "peg1",
                "round-peg-v1": "peg2", "panda-v1/base": "link0"},
        frames={EEF: scene["ee_site_name"]},
        free_joints={"square-nut-v1": "SquareNut_joint"},
        joint_targets={f"panda-v1/joint{i}": f"actuator{i}" for i in range(1, 8)},
        open_actuators=("actuator8",),
    ).compile_source(
        artifact,
        scene_source=TaskSceneSource(scene_xml, base,
            "nut-assembly-square-v1/canonical-source-nutassembly-nominal-v1"),
        config=config, agents=(robot,),
    )
    from ...runtime.sessions.source import snapshot_legacy_mjcf_source
    runtime_source = snapshot_legacy_mjcf_source(runtime_source)
    return runtime_source, contact_profile


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _source_identity_files():
    root = Path(__file__).resolve().parents[3]
    relative = (
        "task_env/tasks/nut_assembly/__init__.py",
        "task_env/tasks/nut_assembly/task.py", "task_env/tasks/nut_assembly/specialization.py",
        "task_env/tasks/nut_assembly/solution.py",
        "task_env/tasks/nut_assembly/config.yaml", "task_env/assembly/nut_assembly.py",
        "task_env/assembly/r05b_trusted_execution_source_manifest.json",
        "task_env/assembly/compiler.py", "task_env/environment/task_source.py",
        "task_env/objects/nut_assembly.py", "task_env/assembly/source.py", "task_env/robots/panda.py",
        "task_env/environment/reference_env.py", "task_env/environment/reference_binding.py",
        "task_env/environment/lifecycle.py",
        "task_env/artifacts/contracts.py",
        "task_env/recorders/reference_provenance.py", "task_env/utils/_paths.py",
        "task_env/recorders/position_metadata.py",
        "task_env/observations/selected_reference.py",
        "task_env/planners/completion.py",
        "task_env/runtime/sessions/api.py", "task_env/runtime/sessions/control.py",
        "task_env/runtime/sessions/position_subject_binding.py",
        "task_env/runtime/sessions/source_composition_adapters.py",
        "task_env/robots/assembled_panda.py", "task_env/robots/source_recipe.py",
        "task_env/runtime/sessions/common.py", "task_env/runtime/sessions/source.py",
        "task_env/trajectory/canonical/execution.py", "task_env/trajectory/canonical/streaming.py",
        "task_env/planners/cartesian.py", "task_env/planners/contracts.py",
    )
    controller = root / "task_env/controllers/canonical"
    relative = (*relative, R3_PROFILE_PATH.relative_to(root).as_posix(),
                *(p.relative_to(root).as_posix() for p in controller.glob("*.py") if p.is_file()))
    return {name: _sha(root / name) for name in sorted(set(relative))}


def _compile_reference_source(request, *, resolved_config=None, lift_height_m=None,
                              task_config=None, robot=None):
    task_config = _configuration() if task_config is None else task_config
    recipe = task_config['recipe']
    robot = make_agent(recipe['agent_uids'][0]) if robot is None else robot
    artifact = build_artifact(lift_height_m=lift_height_m, task_config=task_config, robot=robot)
    source, contact_profile = build_runtime_source(
        artifact, request.provider, backend=request.backend, resolved_config=resolved_config,
        lift_height_m=lift_height_m, task_config=task_config, robot=robot)
    return {'artifact': artifact, 'source': source, '_task_config': task_config,
            '_contact_profile': contact_profile}


def _bind_reference_controller(value, request, *, include_solution, resolved_config=None):
    from ...controllers.canonical.contracts import digest
    artifact, source = value['artifact'], value['source']
    task_config, contact_profile = value['_task_config'], value['_contact_profile']
    recipe, provider = task_config['recipe'], request.provider
    dynamic = load_r3_dynamic_profile()
    controller_profile = (resolved_config.control.profile_id if resolved_config is not None
                          else NutAssemblyReferenceEnv.selected_default_controller_profile())
    execution_controller = build_reference_position_controller(
        artifact, source, profile_id=controller_profile, dynamic_profile=dynamic,
        gripper_rate_hz=500, force_limit_N=recipe['controller']['force_cap_N'])
    controller = execution_controller.hold.controller
    settings = dict(recipe["solution"]["config"])
    settings["grasp_offset"] = tuple(settings["grasp_offset"])
    settings["table_top_z_m"] = float(recipe["scene"]["table_top_z"])
    settings["nut_contact_margin_m"] = float(recipe["asset"]["nut_contact_margin_m"])
    solution_config = NutAssemblySolutionConfig(**settings)
    base_controller_identity = controller.identity
    solution_arguments = dict(config=solution_config,
        control_dt=artifact.timebase.control_dt, physics_dt_s=artifact.timebase.physics_dt,
        provider=provider, task_artifact_hash=artifact.identity_hash,
        source_id=source.scene_source.source_id,
        source_closure_digest=source.source_closure_digest,
        source_xml_sha256=hashlib.sha256(source.scene_source.xml.encode()).hexdigest(),
        base_controller_identity=base_controller_identity,
        require_native_feedback_contract=True)
    description = NutAssemblyOutcomeSolutionV1.describe(**solution_arguments)
    solution = NutAssemblyOutcomeSolutionV1(**solution_arguments) if include_solution else None
    solution_type = NutAssemblyOutcomeSolutionV1
    source_files = _source_identity_files()
    construction_id = recipe["construction_id"]
    controller_identity = {"construction_id": construction_id,
        "base_controller_identity": base_controller_identity,
        "solution_identity": description["identity"],
        "construction_source_sha256": source_files["task_env/tasks/nut_assembly/specialization.py"],
        "execution_support_sha256": source_files["task_env/tasks/nut_assembly/solution.py"],
        "cadence": "native-gripper-500hz-v1",
        "arm_execution_profile": "controller-owned-hold-and-linear-native-ramp-v1",
        "native_feedback_contract": "nutassembly-native-feedback-sample-v1"}
    execution_controller.bind_identity_provenance(controller_identity)
    root = Path(__file__).resolve().parents[3]
    revision = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    construction_identity = reference_task_identity_fields(
        artifact, source, controller, include_runtime_config_sha256=False,
    )
    resolved = {"construction_id": construction_id, "artifact": artifact.to_mapping(),
        **construction_identity, "solution_config": asdict(solution_config),
        "solution_parameters": {name: getattr(solution_type, name) for name in (
            "version", "outward_handle_offset_m", "descend_endpoint_command_bias_m",
            "minimum_pose_wait_s", "pose_window_s", "pose_span_m", "pose_speed_m_s",
            "postclose_hold_s", "servo_height_compensation_m", "stable_height_tolerance_m")},
        "task_recipe": task_config,
        "task_parameters_v1": {"lift_height_m": artifact.semantics.parameters_si["lift_height"]},
        "dynamic_profile": dynamic,
        "physical_profile": controller.physical_profile,
        "resolved_controller_action": asdict(controller.config),
        "resolved_controller_gripper": asdict(controller.gripper_config),
        "base_controller_identity": base_controller_identity,
        "solution_identity": description["identity"], "guard_policy": description["policy_mapping"],
        "guard_policy_identity": description["policy_identity"],
        "outcome_policy": description["outcome_policy_mapping"],
        "outcome_policy_identity": description["outcome_policy_identity"],
        "completion_policy": "on_expert_terminal_stage",
        "arm_execution_profile": "controller-owned-hold-and-linear-native-ramp-v1",
        "native_feedback_contract": "nutassembly-native-feedback-sample-v1",
        "gripper_control_hz": 500,
        "gripper_feedback_hz": 500,
        "contact_profile": "MuJoCo NoSlip2" if provider == "mujoco" else "GeoPhys native Row-PGS",
        "provider_contact_profile": contact_profile,
        "source_revision": revision, "source_sha256": source_files,
        "qualification": "NOT_REQUALIFIED",
        }
    return {"construction_id": construction_id, "artifact": artifact, "source": source,
        "controller": execution_controller,
        "controller_identity": controller.identity,
        "solution": solution,
        "solution_factory": lambda: solution_type(**solution_arguments),
        "solution_identity": description["identity"], "solution_config": solution_config,
        "recipe": resolved, "resolved_configuration": resolved,
        "recipe_identity": digest(resolved), "close_authorization_policy": {
            **description["policy_mapping"], "identity": description["policy_identity"]},
        "allowed_close_authorization_guards": [solution_type.primary_guard_id, solution_type.alternative_guard_id],
        "execution_policy": {"policy_id": OUTCOME_POLICY_ID,
            "diagnostic_continuation": False, "strict_expert_gate": "preserved-with-bounded-readiness-warning",
            "grants_full_expert_pass": False, "outcome_completion": True},
        "source_revision": revision, "source_sha256": source_files,
        "_execution_provider": provider,
        "_contact_profile": contact_profile}



def _reference_builder(*, include_solution, resolved_config=None, lift_height_m=None,
                       task_config=None, robot=None):
    from ...environment.reference_binding import SourceBoundTaskBuilder
    backend = resolved_config.runtime.backend if resolved_config is not None else 'cpu'
    return SourceBoundTaskBuilder(
        lambda request: _compile_reference_source(request, resolved_config=resolved_config,
            lift_height_m=lift_height_m, task_config=task_config, robot=robot),
        None, backend=backend,
        compile_control=lambda value, request: _bind_reference_controller(value, request,
            include_solution=include_solution, resolved_config=resolved_config))


def _build_reference(*, provider, include_solution, resolved_config=None, lift_height_m=None,
                     task_config=None, robot=None):
    from ...environment.reference_binding import TaskBuildRequest
    builder = _reference_builder(include_solution=include_solution, resolved_config=resolved_config,
        lift_height_m=lift_height_m, task_config=task_config, robot=robot)
    return builder(TaskBuildRequest(provider, builder.backend, 31, 1000, None, None))


def build_reference(*, provider="mujoco", include_solution=True, resolved_config=None, lift_height_m=None, task_config=None, robot=None):
    """Build the unchanged selected 100 Hz/500 Hz reference route."""
    return _build_reference(
        provider=provider, include_solution=include_solution,
        resolved_config=resolved_config,
        lift_height_m=lift_height_m, task_config=task_config, robot=robot,
    )


def build_outcome_solution(*, provider="mujoco"):
    """Build the task-owned external Solution for its matching selected source."""
    return build_reference(provider=provider)["solution"]


def _validate_external_solution(value, solution):
    if not isinstance(solution, NutAssemblyOutcomeSolutionV1):
        raise TypeError("NutAssembly external lifecycle requires Outcome Solution V1")
    expected = {
        "identity": value["solution_identity"],
        "provider": value["_execution_provider"],
        "task_artifact_hash": value["artifact"].identity_hash,
        "source_id": value["source"].scene_source.source_id,
        "source_closure_digest": value["source"].source_closure_digest,
        "source_xml_sha256": hashlib.sha256(value["source"].scene_source.xml.encode()).hexdigest(),
        "base_controller_identity": value["recipe"]["base_controller_identity"],
    }
    if (solution.require_native_feedback_contract is not True
            or solution.config != value["solution_config"]
            or solution.control_dt != value["artifact"].timebase.control_dt
            or solution.physics_dt_s != value["artifact"].timebase.physics_dt
            or any(getattr(solution, name) != expected_value for name, expected_value in expected.items())):
        raise ValueError("NutAssembly external Solution identity does not match the selected source/controller")


def _binding(resolved_config=None, lift_height_m=None, task_config=None, robot=None):
    task_config = _configuration() if task_config is None else task_config
    declaration = NutAssemblyTaskDefinition.from_artifact(
        build_artifact(lift_height_m=lift_height_m, task_config=task_config, robot=robot),
        task_config['recipe']['reset'],
    )
    return ReferenceTaskBinding(build=_reference_builder(include_solution=False,
            resolved_config=resolved_config, lift_height_m=lift_height_m,
            task_config=task_config, robot=robot),
        action_schema=REFERENCE_POSE_ACTION_SCHEMA, action_space_factory=reference_pose_action_space,
        prepare_action=reference_pose_action, scalar_control_binding=panda_reference_control_binding(),
        observation_space_factory=selected_reference_observation_spaces, observation_projection=build_selected_observation,
        reset_sample=declaration.sample_reset,
        evaluate=declaration.evaluate,
        task_definition_factory=lambda artifact: NutAssemblyTaskDefinition.from_artifact(
            artifact, task_config['recipe']['reset']),
        task_state_projection=as_task_state_view,
        object_poses=((NUT, "square_nut_v1"), (PEG, "square_peg_v1")),
        external_actions=False, interval_mode="native", recorder_mode="execution",
        external_action_error="selected NutAssembly requires a source-bound ExpertAction; unguarded external actions are not admitted",
        reset_seed=_reset_seed, observe_expert_kwargs=_observe_kwargs,
        native_sample_factory=_native_feedback_sample,
        native_interval_receipt_factory=_native_interval_receipt,
        validate_external_solution=_validate_external_solution,
        control_request_required=True,
        external_solution_actions=True,
        expert_uses_public_observation=True,
        runtime_episode_identity=True,
        record_native_substeps=True, abort_solution_on_runtime_error=True)


@register_env()
class NutAssemblyReferenceEnv(SelectedReferenceEnv):
    uid = REFERENCE_ENV_ID
    uses_selected_public_config = True
    selected_controller_profiles = frozenset(('r3_continuous_v1',))
    selected_parameter_limits = {"lift_height_m": (0.01, 0.15)}
    selected_supports_isaac = False
    selected_robot_uids = frozenset(('panda-v1',))
    robot_source_roots = (('tabletop-v1', 'grasp_table'), ('square-nut-v1', 'SquareNut'),
                          ('square-peg-v1', 'peg1'), ('round-peg-v1', 'peg2'))
    robot_source_site_transfers = (('hand', 'nutassembly_ee_site', 'hand'),)
    default_robot_source_uid = 'panda-v1'
    @staticmethod
    def selected_task_configuration():
        return _configuration()

    @staticmethod
    def selected_default_config(task_config=None):
        return _environment_config(task_config=task_config)

    @staticmethod
    def selected_default_controller_profile(task_config=None):
        return 'r3_continuous_v1'

    @classmethod
    def selected_binding(cls, config, *, robot=None):
        return _binding(config.environment, dict(config.task_parameters).get("lift_height_m"),
                        json.loads(config.task_configuration_json), robot=robot)
