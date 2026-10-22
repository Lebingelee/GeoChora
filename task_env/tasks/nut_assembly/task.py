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
import yaml

from ...artifacts import (
    ActionIntent, CanonicalStateView, EntityDefinition, InitializationContract,
    PoseWorld, RequiredCapabilitySet, SemanticDefinition, TaskArtifact, Timebase,
    WorldDefinition,
)
from ...artifacts.execution import ResetSample
from ...assembly.nut_assembly import build_nut_assembly_model_xml
from ...assembly.source import TaskSceneSource
from ...controllers.canonical.contracts import digest
from ...controllers.canonical.execution import StableArmTargetHold
from ...controllers.canonical.production_r3 import ProductionCanonicalPandaControllerR3
from ...environment import TaskCompositionSpec
from ...environment.configuration import overlay_public_env_config, resolve_env_config
from ...objects.nut_assembly import (
    NUTASSEMBLY_NOMINAL_V1_DIAG_INERTIA,
    NUTASSEMBLY_NOMINAL_V1_ID, NUTASSEMBLY_NOMINAL_V1_MASS,
    NUT_CONTACT_MARGIN, NUT_FREEJOINT_ARMATURE, NUT_FREEJOINT_DAMPING,
    NUT_HALF_HEIGHT, NUT_HANDLE_LOCAL_X, PEG_HALF_HEIGHT, ROUND_PEG_RADIUS,
    SQUARE_PEG_HALF_WIDTH,
)
from ...registry import make_agent, make_object, make_scene, register_env
from ...robots.panda import PandaAgent
from ...runtime.sessions.source import RuntimeSource
from ...utils.rotation import quat_wxyz_to_matrix
from ..reference_env import ReferenceTaskBinding, SelectedReferenceEnv
from .solution import (
    NutAssemblyNativeFeedbackSampleV1, NutAssemblyNativeIntervalReceiptV1,
    NutAssemblyOutcomeSolutionV1, NutAssemblySolutionConfig,
    OUTCOME_POLICY_ID, ReferenceExecutionController,
)

CONFIG_PATH = Path(__file__).with_name("config.yaml")
REFERENCE_ENV_ID = "nut-assembly-outcome-reference-v1"
EEF = "panda-v1/ee"
NUT = "square-nut-v1"
PEG = "square-peg-v1"
FINGERS = ("panda-v1/finger_joint1", "panda-v1/finger_joint2")
SUCCESS = "nut_on_square_peg_canonical_state_v0"


def _configuration():
    value = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != {"recipe", "environment"}:
        raise ValueError("NutAssembly config.yaml must contain recipe and environment only")
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


def semantic_definition() -> SemanticDefinition:
    recipe = _recipe()
    p = recipe["semantic_parameters"]
    scene = recipe["scene"]
    return SemanticDefinition("semantics-v0", "nut_assembly_state_v0",
        (NUT, PEG, EEF), FINGERS,
        {**{key: float(value) for key, value in p.items()},
         "table_top_z": float(scene["table_top_z"]),
         "nut_half_height": float(NUT_HALF_HEIGHT),
         "nut_contact_margin": float(recipe["asset"]["nut_contact_margin_m"]),
         "nut_handle_local_x": float(NUT_HANDLE_LOCAL_X),
         "peg_half_height": float(scene["peg_half_height"])}, SUCCESS)


def evaluate(state: CanonicalStateView, semantics: SemanticDefinition | None = None):
    from ...environment import TaskEvaluation
    expected = semantic_definition()
    semantics = expected if semantics is None else semantics
    if not isinstance(state, CanonicalStateView) or semantics != expected:
        raise ValueError("unsupported canonical NutAssembly state/semantics")
    semantics.require_state(state)
    p = semantics.parameters_si
    nut, peg = state.pose_world[NUT], state.pose_world[PEG]
    position = np.asarray(nut.position)
    ee = np.asarray(state.pose_world[EEF].position)
    rotation = quat_wxyz_to_matrix(nut.quaternion_wxyz)
    handle = position + rotation @ np.array([p["nut_handle_local_x"], 0.0, 0.0])
    yaw = float(np.arctan2(rotation[1, 0], rotation[0, 0]))
    period = 0.5 * np.pi
    yaw_error = abs((yaw + 0.5 * period) % period - 0.5 * period)
    xy_error = float(np.linalg.norm(position[:2] - np.asarray(peg.position[:2])))
    z_error = float(position[2] - (p["table_top_z"] + p["nut_half_height"] + p["nut_contact_margin"]))
    ee_distance = float(np.linalg.norm(ee - position))
    handle_distance = float(np.linalg.norm(ee - handle))
    opening = float(sum(state.joint_position[name] for name in FINGERS))
    reached = handle_distance <= p["grasp_distance"]
    grasped = bool(reached and opening <= p["gripper_closed_opening"])
    lifted = bool(position[2] >= p["table_top_z"] + p["nut_half_height"] + p["lift_height"])
    hover = bool(lifted and xy_error <= p["hover_xy_tolerance"])
    aligned = bool(xy_error <= p["insert_xy_tolerance"] and yaw_error <= p["insert_yaw_tolerance"])
    passed = bool(position[2] <= peg.position[2] + p["peg_half_height"] - p["nut_contact_margin"])
    returned = bool(position[2] <= p["table_top_z"] + 3 * p["nut_half_height"])
    inserted = bool(aligned and passed and returned)
    gripper_released = bool(opening >= p["gripper_release_opening"])
    released = bool(inserted and gripper_released and ee_distance >= p["release_distance"])
    success = bool(inserted and released)
    metrics = {
        "reached_nut": bool(reached), "grasped_nut": bool(grasped),
        "lifted_nut": bool(lifted), "hovered_over_peg": bool(hover),
        "aligned_with_peg": bool(aligned), "peg_passed_through_nut_center": bool(passed),
        "nut_returned_to_table": bool(returned), "inserted_on_peg": bool(inserted),
        "gripper_released": bool(gripper_released), "released_nut": bool(released),
        "task_success": bool(success), "nut_x": float(position[0]),
        "nut_y": float(position[1]), "nut_z": float(position[2]), "nut_yaw": yaw,
        "table_seated_nut_max_z": p["table_top_z"] + 3 * p["nut_half_height"],
        "peg_xy_error": xy_error, "peg_z_error": z_error, "yaw_error": yaw_error,
        "eef_to_nut_dist": ee_distance, "eef_to_handle_dist": handle_distance,
        "gripper_opening": opening, "success_definition": True,
    }
    terms = {"reach": 0.10 * (1.0 - math.tanh(10.0 * handle_distance)),
             "grasp": 0.25 if grasped else 0.0, "lift": 0.25 if lifted else 0.0,
             "hover": 0.15 if hover else 0.0, "insert": 0.15 if inserted else 0.0,
             "release": 0.10 if released else 0.0, "success": 1.0 if success else 0.0}
    return TaskEvaluation(reward=float(sum(terms.values())), success=success,
        failure=False, metrics=metrics, reward_terms=terms)


def build_artifact() -> TaskArtifact:
    recipe, scene, reset, asset = _recipe(), _recipe()["scene"], _recipe()["reset"], _recipe()["asset"]
    initialization = {"nut_pose": reset["nut_pose"], "joint_position": reset["joint_position"]}
    mass = float(asset["nut_mass_kg"])
    inertia = tuple(float(v) for v in asset["nut_diagonal_inertia_kg_m2"])
    if (mass != NUTASSEMBLY_NOMINAL_V1_MASS
            or inertia != tuple(NUTASSEMBLY_NOMINAL_V1_DIAG_INERTIA)):
        raise ValueError("selected nominal Nut asset profile changed")
    return TaskArtifact("task-artifact-v0", recipe["artifact_id"], recipe["task_uid"],
        recipe["artifact_version"],
        WorldDefinition("world-v0", "SI_right_handed_z_up_wxyz", (
            EntityDefinition("tabletop-v1", "static", "nut-assembly-square-v1/task-local/table",
                (), (), "box", "support_contact", {"top_z": float(scene["table_top_z"])}),
            EntityDefinition("panda-v1", "embodiment",
                "mujoco_menagerie/b846dd12bc459d776cccb3dee0b1d02acbf7a9c7/franka_emika_panda/panda.xml",
                ("panda-v1/base", EEF),
                ("panda-v1/joint1", "panda-v1/joint2", "panda-v1/joint3", "panda-v1/joint4",
                 "panda-v1/joint5", "panda-v1/joint6", "panda-v1/joint7", *FINGERS),
                "referenced_articulation", "arm_hand_finger_collision", {}),
            EntityDefinition("square-nut-v1", "movable",
                "nut-assembly-square-v1/task-local/square-nut/" + NUTASSEMBLY_NOMINAL_V1_ID,
                (), (), "authored_compound", "table_hand_peg_contact",
                {"mass": mass, **{f"inertia_{axis}": value for axis, value in zip("xyz", inertia)}}),
            EntityDefinition("square-peg-v1", "static", "nut-assembly-square-v1/task-local/square-peg",
                (), (), "box", "nut_contact", {"half_height": float(scene["peg_half_height"])}),
            EntityDefinition("round-peg-v1", "static", "nut-assembly-square-v1/task-local/round-peg",
                (), (), "cylinder", "nut_contact", {"half_height": float(scene["peg_half_height"])}),
        ), ActionIntent("absolute_pose", "world", "quaternion_wxyz", "arm_joint_position_and_gripper"),
        tuple(recipe["observation_requirements"]), ()),
        InitializationContract("initialization-v0",
            {"square-nut-v1": PoseWorld.from_mapping(initialization["nut_pose"])},
            dict(initialization["joint_position"]), (),
            "zero_named_joint_and_entity_velocities_arm_targets_at_initial_joints_gripper_open",
            "NA-S0_frozen_deterministic_semantic_joint_and_pose_request", 0),
        semantic_definition(),
        Timebase(float(recipe["physics_dt"]), int(recipe["control_substeps"]), float(recipe["control_dt"])),
        RequiredCapabilitySet(tuple(recipe["required_capabilities"])))


def sample_reset(artifact: TaskArtifact, task_seed: int = 19) -> ResetSample:
    expected = build_artifact()
    if not isinstance(artifact, TaskArtifact) or artifact.to_mapping() != expected.to_mapping():
        raise ValueError("selected NA-S0 TaskArtifact required")
    if type(task_seed) is not int or task_seed != 19:
        raise ValueError("selected NA-S0 uses fixed provenance seed19")
    initialization = artifact.initialization
    return ResetSample.create(schema_version="reset-sample-v0",
        task_artifact_hash=artifact.identity_hash, sampler_id=_recipe()["reset"]["sampler_id"],
        sampler_version=_recipe()["reset"]["sampler_version"], task_seed=task_seed,
        joint_position=dict(initialization.joint_position), poses_world=dict(initialization.poses_world),
        velocity_policy=_recipe()["reset"]["inherited_state_policy"],
        control_policy=_recipe()["reset"]["control_policy"],
        settle_steps=int(_recipe()["reset"]["settle_steps"]))


def _environment_config(*, backend='cpu', diagnostic=False):
    recipe = _recipe()
    base = resolve_env_config(task_uid=recipe["task_uid"], scene_uid=recipe["scene_uid"],
        agent_uids=tuple(recipe["agent_uids"]), object_uids=tuple(recipe["object_uids"]),
        success_definition=recipe["success_definition"])
    config = overlay_public_env_config(base, _configuration()["environment"])
    if backend != 'cpu' and not (diagnostic and backend == 'cuda'):
        raise ValueError('NutAssembly selected construction is CPU-only outside the cadence diagnostic')
    return replace(config, runtime=replace(config.runtime, backend=backend, prewarm=False,
        physics_dt=float(recipe["physics_dt"]), control_substeps=int(recipe["control_substeps"])),
        render=replace(config.render, camera_obs=False),
        robot=replace(config.robot, controller=replace(config.robot.controller,
            kind="absolute_pose", reference="world", rotation_representation="quaternion_wxyz")))


def build_runtime_source(artifact: TaskArtifact, provider="geophys", *, backend='cpu', _diagnostic=False):
    if artifact.to_mapping() != build_artifact().to_mapping():
        raise ValueError("selected nominal NutAssembly Artifact required")
    if provider not in {"geophys", "mujoco"}:
        raise ValueError("selected provider must be geophys or mujoco")
    if backend != 'cpu' and not (_diagnostic and provider == 'geophys' and backend == 'cuda'):
        raise ValueError('selected NutAssembly source is CPU-only outside the GeoPhys CUDA diagnostic')
    recipe = _recipe()
    source_config = recipe["controller"]
    config = _environment_config(backend=backend, diagnostic=_diagnostic)
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
        nut_diagonal_inertia_kg_m2=tuple(recipe["asset"]["nut_diagonal_inertia_kg_m2"]))
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
    return RuntimeSource(artifact.identity_hash,
        TaskSceneSource(scene_xml, base, "nut-assembly-square-v1/canonical-source-nutassembly-nominal-v1"),
        {name: name.split("/", 1)[1] for name in artifact.initialization.joint_position},
        {"square-nut-v1": "SquareNut", "square-peg-v1": "peg1",
         "round-peg-v1": "peg2", "panda-v1/base": "link0"},
        {EEF: scene["ee_site_name"]}, {"square-nut-v1": "SquareNut_joint"},
        {f"panda-v1/joint{i}": f"actuator{i}" for i in range(1, 8)}, ("actuator8",),
        composition, config, make_scene(recipe["scene_uid"]),
        tuple(make_agent(uid) for uid in recipe["agent_uids"]),
        tuple(make_object(uid) for uid in recipe["object_uids"])), contact_profile


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _source_identity_files():
    root = Path(__file__).resolve().parents[3]
    relative = (
        "task_env/tasks/nut_assembly/__init__.py",
        "task_env/tasks/nut_assembly/task.py", "task_env/tasks/nut_assembly/solution.py",
        "task_env/tasks/nut_assembly/config.yaml", "task_env/assembly/nut_assembly.py",
        "task_env/objects/nut_assembly.py", "task_env/assembly/source.py",
        "task_env/tasks/reference_env.py", "task_env/tasks/canonical_solution_lifecycle.py",
        "task_env/runtime/sessions/common.py", "task_env/runtime/sessions/source.py",
        "task_env/trajectory/canonical/execution.py", "task_env/trajectory/canonical/streaming.py",
    )
    controller = root / "task_env/controllers/canonical"
    relative = (*relative, *(p.relative_to(root).as_posix() for p in controller.glob("*.py") if p.is_file()))
    return {name: _sha(root / name) for name in sorted(set(relative))}


def _build_reference(*, provider, include_solution, backend, gripper_control_hz, diagnostic):
    """Build the single selected 100 Hz route without importing native providers."""
    from ...controllers.canonical.contracts import digest
    recipe = _recipe()
    artifact = build_artifact()
    source, contact_profile = build_runtime_source(
        artifact, provider, backend=backend, _diagnostic=diagnostic,
    )
    dynamic = recipe["controller"]["dynamic_profile"]
    controller = ProductionCanonicalPandaControllerR3.from_source(artifact, source, profile=dynamic)
    # The accepted R3 route fixes a 10 N force target/cap while preserving its
    # controller law and task-facing close authorization.
    controller.gripper_config = replace(controller.gripper_config, force_limit_N=10.0)
    holder = StableArmTargetHold(controller)
    settings = dict(recipe["solution"]["config"])
    settings["grasp_offset"] = tuple(settings["grasp_offset"])
    settings["table_top_z_m"] = float(recipe["scene"]["table_top_z"])
    settings["nut_contact_margin_m"] = float(recipe["asset"]["nut_contact_margin_m"])
    solution_config = NutAssemblySolutionConfig(**settings)
    base_controller_identity = controller.identity
    solution = NutAssemblyOutcomeSolutionV1(config=solution_config,
        control_dt=artifact.timebase.control_dt, physics_dt_s=artifact.timebase.physics_dt,
        provider=provider, task_artifact_hash=artifact.identity_hash,
        source_id=source.scene_source.source_id,
        source_closure_digest=source.source_closure_digest,
        source_xml_sha256=hashlib.sha256(source.scene_source.xml.encode()).hexdigest(),
        base_controller_identity=base_controller_identity,
        require_native_feedback_contract=True)
    source_files = _source_identity_files()
    construction_id = recipe["construction_id"]
    controller_identity = {"construction_id": construction_id,
        "base_controller_identity": base_controller_identity,
        "solution_identity": solution.identity,
        "construction_source_sha256": source_files["task_env/tasks/nut_assembly/task.py"],
        "execution_support_sha256": source_files["task_env/tasks/nut_assembly/solution.py"],
        "cadence": ("native-gripper-500hz-v1" if gripper_control_hz == 500
                    else "equal-gripper-100hz-v1"),
        "arm_execution_profile": "controller-owned-hold-and-linear-native-ramp-v1",
        "native_feedback_contract": "nutassembly-native-feedback-sample-v1"}
    if diagnostic:
        controller_identity.update({
            'diagnostic_experiment': 'nutassembly-gripper-cadence-v1',
            'physics_backend': backend,
            'gripper_control_hz': gripper_control_hz,
        })
    controller.identity = digest(controller_identity)
    root = Path(__file__).resolve().parents[3]
    revision = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    resolved = {"construction_id": construction_id, "artifact": artifact.to_mapping(),
        "artifact_sha256": artifact.identity_hash,
        "runtime_config": asdict(source.config), "solution_config": asdict(solution_config),
        "solution_parameters": {name: getattr(solution, name) for name in (
            "version", "outward_handle_offset_m", "descend_endpoint_command_bias_m",
            "minimum_pose_wait_s", "pose_window_s", "pose_span_m", "pose_speed_m_s",
            "postclose_hold_s", "servo_height_compensation_m", "stable_height_tolerance_m")},
        "task_recipe": _configuration(), "dynamic_profile": dynamic,
        "physical_profile": controller.physical_profile,
        "resolved_controller_action": asdict(controller.config),
        "resolved_controller_gripper": asdict(controller.gripper_config),
        "controller_identity": controller.identity, "base_controller_identity": base_controller_identity,
        "solution_identity": solution.identity, "guard_policy": solution.policy_mapping,
        "guard_policy_identity": solution.policy_identity,
        "outcome_policy": solution.outcome_policy_mapping,
        "outcome_policy_identity": solution.outcome_policy_identity,
        "completion_policy": "on_expert_terminal_stage",
        "arm_execution_profile": "controller-owned-hold-and-linear-native-ramp-v1",
        "native_feedback_contract": "nutassembly-native-feedback-sample-v1",
        "gripper_feedback_hz": 500,
        **({"diagnostic_experiment": "nutassembly-gripper-cadence-v1",
            "physics_backend": backend,
            "gripper_control_hz": gripper_control_hz}
           if diagnostic else {}),
        "contact_profile": "MuJoCo NoSlip2" if provider == "mujoco" else "GeoPhys native Row-PGS",
        "provider_contact_profile": contact_profile,
        "source_xml_sha256": hashlib.sha256(source.scene_source.xml.encode()).hexdigest(),
        "source_revision": revision, "source_sha256": source_files,
        "qualification": "NOT_REQUALIFIED",
        "runtime_source_bindings": {name: dict(getattr(source, name)) for name in (
            "joints", "bodies", "frames", "free_joints", "joint_targets")},
        "runtime_open_actuators": list(source.open_actuators)}
    return {"construction_id": construction_id, "artifact": artifact, "source": source,
        "controller": ReferenceExecutionController(
            holder, artifact.timebase.control_dt, gripper_rate_hz=gripper_control_hz,
        ),
        "controller_identity": controller.identity,
        "solution": solution if include_solution else None,
        "solution_identity": solution.identity, "solution_config": solution_config,
        "recipe": resolved, "resolved_configuration": resolved,
        "recipe_identity": digest(resolved), "close_authorization_policy": {
            **solution.policy_mapping, "identity": solution.policy_identity},
        "allowed_close_authorization_guards": [solution.primary_guard_id, solution.alternative_guard_id],
        "execution_policy": {"policy_id": OUTCOME_POLICY_ID,
            "diagnostic_continuation": False, "strict_expert_gate": "preserved-with-bounded-readiness-warning",
            "grants_full_expert_pass": False, "outcome_completion": True},
        "source_revision": revision, "source_sha256": source_files,
        "_execution_provider": provider,
        "_contact_profile": contact_profile}


def build_reference(*, provider="mujoco", include_solution=True):
    """Build the unchanged selected 100 Hz/500 Hz reference route."""
    return _build_reference(
        provider=provider, include_solution=include_solution,
        backend='cpu', gripper_control_hz=500, diagnostic=False,
    )


def build_gripper_cadence_diagnostic_reference(
    *, backend, gripper_control_hz, include_solution=True,
):
    """Build the exact GeoPhys CPU/CUDA R3 cadence experiment, not a capability."""
    if backend not in {'cpu', 'cuda'}:
        raise ValueError('GeoPhys cadence diagnostic backend must be cpu or cuda')
    if gripper_control_hz not in {100, 500}:
        raise ValueError('GeoPhys cadence diagnostic gripper cadence must be 100 or 500 Hz')
    return _build_reference(
        provider='geophys', include_solution=include_solution,
        backend=backend, gripper_control_hz=gripper_control_hz, diagnostic=True,
    )


def _reset_seed(seed):
    if seed not in (19, None):
        raise ValueError("selected NutAssembly NA-S0 has fixed provenance seed19")
    return 19 if seed is None else seed


def build_outcome_solution(*, provider="mujoco"):
    """Build the task-owned external Solution for its matching selected source."""
    return build_reference(provider=provider)["solution"]


def build_gripper_cadence_diagnostic_solution(*, backend, gripper_control_hz):
    """Build the task-owned Solution instance bound to one diagnostic cadence."""
    return build_gripper_cadence_diagnostic_reference(
        backend=backend, gripper_control_hz=gripper_control_hz,
    )["solution"]


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
    if (not solution.require_native_feedback_contract
            or any(getattr(solution, name) != expected_value for name, expected_value in expected.items())):
        raise ValueError("NutAssembly external Solution identity does not match the selected source/controller")


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
        hashlib.sha256(env.value["source"].scene_source.xml.encode()).hexdigest(),
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
        hashlib.sha256(env.value["source"].scene_source.xml.encode()).hexdigest(),
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


def _binding():
    return ReferenceTaskBinding(build=lambda provider: build_reference(provider=provider),
        reset_sample=sample_reset, evaluate=evaluate,
        object_poses=((NUT, "square_nut_v1"), (PEG, "square_peg_v1")),
        external_actions=False, interval_mode="native", recorder_mode="execution",
        external_action_error="selected NutAssembly requires step_expert; unguarded external actions are not admitted",
        reset_seed=_reset_seed, observe_expert_kwargs=_observe_kwargs,
        native_sample_factory=_native_feedback_sample,
        native_interval_receipt_factory=_native_interval_receipt,
        build_external=lambda provider: build_reference(provider=provider, include_solution=False),
        build_gripper_cadence_diagnostic=lambda provider, backend, gripper_control_hz, include_solution:
            build_gripper_cadence_diagnostic_reference(
                backend=backend, gripper_control_hz=gripper_control_hz,
                include_solution=include_solution,
            ),
        validate_external_solution=_validate_external_solution,
        control_request_required=True,
        expert_uses_public_observation=True,
        runtime_episode_identity=True,
        record_native_substeps=True, abort_solution_on_runtime_error=True)


@register_env()
class NutAssemblyReferenceEnv(SelectedReferenceEnv):
    uid = REFERENCE_ENV_ID
    binding = _binding()

    @classmethod
    def for_gripper_cadence_diagnostic(cls, *, backend, gripper_control_hz, horizon=6000):
        """Create the explicit bounded GeoPhys cadence experiment selection."""
        return cls(provider='geophys', backend=backend, horizon=horizon,
                   _diagnostic_gripper_control_hz=gripper_control_hz)


__all__ = ["NutAssemblyReferenceEnv", "REFERENCE_ENV_ID", "build_artifact",
    "build_reference", "build_outcome_solution", "build_runtime_source", "evaluate",
    "sample_reset", "semantic_definition", "build_gripper_cadence_diagnostic_reference",
    "build_gripper_cadence_diagnostic_solution"]
