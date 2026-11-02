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
    PoseWorld, SemanticDefinition, TaskArtifact, Timebase,
)
from ...artifacts.execution import ResetSample
from ...assembly.nut_assembly import build_nut_assembly_model_xml
from ...assembly.compiler import compile_reference_source, panda_entity_declaration
from ...assembly.source import TaskSceneSource
from ...controllers.canonical.contracts import digest
from ...controllers.canonical.execution import StableArmTargetHold
from ...controllers.canonical.production_r3 import (
    ProductionCanonicalPandaControllerR3, R3_PROFILE_PATH, load_r3_dynamic_profile,
)
from ...environment import TaskCompositionSpec
from ...environment.configuration import overlay_public_env_config, resolve_env_config
from ...environment.task_source import compile_declared_artifact
from ...objects.nut_assembly import (
    NUTASSEMBLY_NOMINAL_V1_DIAG_INERTIA,
    NUTASSEMBLY_NOMINAL_V1_ID, NUTASSEMBLY_NOMINAL_V1_MASS,
    NUT_CONTACT_MARGIN, NUT_FREEJOINT_ARMATURE, NUT_FREEJOINT_DAMPING,
    NUT_HALF_HEIGHT, NUT_HANDLE_LOCAL_X, PEG_HALF_HEIGHT, ROUND_PEG_RADIUS,
    SQUARE_PEG_HALF_WIDTH,
)
from ...registry import make_agent, make_object, make_scene, register_env
from ...robots.panda import PandaAgent
from ...runtime.sessions.source import RuntimeSource, ExecutionSourceReceiptV1
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
R05B_NATIVE_FEEDBACK_PROFILE = 'nutassembly-native-feedback-v1'
R05B_CANONICAL_MENAGERIE_ASSET_ROOT = Path(
    '/home/lly/Program_Files/Geochora/asset/external/mujoco_menagerie/'
    'franka_emika_panda/assets'
)
R05B_CANONICAL_XML_SHA256 = '909759def6bbaa4c5644a100a36625400464cd571dcab1222f807efaaf1c225d'


from .task import (semantic_definition, evaluate, sample_reset, _reset_seed,
                   _native_feedback_sample, _native_interval_receipt, _observe_kwargs)

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


def build_artifact(*, lift_height_m=None, task_config=None) -> TaskArtifact:
    recipe = _recipe() if task_config is None else task_config["recipe"]
    scene, reset, asset = recipe["scene"], recipe["reset"], recipe["asset"]
    initialization = {"nut_pose": reset["nut_pose"], "joint_position": reset["joint_position"]}
    mass = float(asset["nut_mass_kg"])
    inertia = tuple(float(v) for v in asset["nut_diagonal_inertia_kg_m2"])
    if (mass != NUTASSEMBLY_NOMINAL_V1_MASS
            or inertia != tuple(NUTASSEMBLY_NOMINAL_V1_DIAG_INERTIA)):
        raise ValueError("selected nominal Nut asset profile changed")
    return compile_declared_artifact(artifact_id=recipe["artifact_id"], task_id=recipe["task_uid"],
        version=recipe["artifact_version"], entities=(
            EntityDefinition("tabletop-v1", "static", "nut-assembly-square-v1/task-local/table",
                (), (), "box", "support_contact", {"top_z": float(scene["table_top_z"])}),
            panda_entity_declaration(),
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


def _environment_config(*, backend='cpu', diagnostic=False, native_feedback_profile=False, task_config=None):
    task_config = _configuration() if task_config is None else task_config
    recipe = task_config["recipe"]
    base = resolve_env_config(task_uid=recipe["task_uid"], scene_uid=recipe["scene_uid"],
        agent_uids=tuple(recipe["agent_uids"]), object_uids=tuple(recipe["object_uids"]),
        success_definition=recipe["success_definition"])
    config = overlay_public_env_config(base, task_config["environment"])
    if backend != 'cpu' and not ((diagnostic or native_feedback_profile)
                                  and backend == 'cuda'):
        raise ValueError('NutAssembly CUDA requires its explicit cadence or native-feedback profile')
    # R05b and the cadence experiment bind a frozen source configuration whose
    # episode value is 1000; the environment's selected horizon remains separate.
    source_episode = replace(config.episode, horizon=1000) if (diagnostic or native_feedback_profile) else config.episode
    return replace(config, runtime=replace(config.runtime, backend=backend, prewarm=False,
        physics_dt=float(recipe["physics_dt"]), control_substeps=int(recipe["control_substeps"])),
        render=replace(config.render, camera_obs=False), episode=source_episode)


def _r05b_execution_source(source):
    """Freeze canonical XML and every referenced asset into one importer snapshot."""
    xml = source.scene_source.xml
    root = ET.fromstring(xml)
    compiler = root.find('compiler')
    if compiler is None:
        raise ValueError('R05b source requires the existing NutAssembly compiler element')
    current_meshdir = compiler.get('meshdir', '')
    current_root = Path(current_meshdir).resolve()
    checkout = Path(__file__).resolve().parents[3]
    expected_asset_root = (checkout / 'asset/external/mujoco_menagerie/'
                           'franka_emika_panda/assets').resolve()
    if current_root != expected_asset_root:
        raise ValueError('R05b Panda meshdir does not resolve to the pinned Menagerie asset owner')
    canonical_meshdir = R05B_CANONICAL_MENAGERIE_ASSET_ROOT.as_posix()
    canonical_xml = xml.replace(current_meshdir, canonical_meshdir)
    canonical_bytes = canonical_xml.encode('utf-8')
    if hashlib.sha256(canonical_bytes).hexdigest() != R05B_CANONICAL_XML_SHA256:
        raise ValueError('R05b canonical source XML differs from its frozen source identity')
    importer_xml = canonical_xml.replace(canonical_meshdir, 'assets')
    importer_bytes = importer_xml.encode('utf-8')
    asset_files = {}
    for node in root.iter():
        raw_path = node.get('file')
        if raw_path is None:
            continue
        if node.tag == 'include':
            raise ValueError('R05b NutAssembly source unexpectedly contains MJCF includes')
        if node.tag not in {'mesh', 'skin'}:
            raise ValueError(f'R05b NutAssembly source has an unaudited external asset kind: {node.tag}')
        if Path(raw_path).is_absolute() or '\\' in raw_path:
            raise ValueError(f'R05b source asset reference must be relative: {raw_path!r}')
        logical = Path(raw_path)
        if any(part in {'', '.', '..'} for part in logical.parts):
            raise ValueError(f'R05b source asset reference escapes its root: {raw_path!r}')
        resolved = (current_root / logical).resolve()
        try:
            resolved.relative_to(current_root)
        except ValueError as exc:
            raise ValueError('R05b source asset escaped the pinned Menagerie tree') from exc
        if not resolved.is_file():
            raise ValueError(f'R05b source asset is missing: {logical.as_posix()}')
        key = (Path('assets') / logical).as_posix()
        if key in asset_files:
            raise ValueError(f'R05b source contains a duplicate asset path: {key}')
        asset_files[key] = resolved.read_bytes()
    if not asset_files:
        raise ValueError('R05b source closure must include the Panda mesh dependencies')
    receipt = ExecutionSourceReceiptV1.create(
        source_id=source.scene_source.source_id,
        canonical_xml=canonical_bytes,
        importer_xml=importer_bytes,
        closure_files={'canonical-source.xml': canonical_bytes, **asset_files},
        expected_canonical_xml_sha256=R05B_CANONICAL_XML_SHA256,
    )
    from dataclasses import replace as dataclass_replace
    canonical_source = TaskSceneSource(
        canonical_xml, receipt.snapshot_root, source.scene_source.source_id,
    )
    return dataclass_replace(
        source, scene_source=canonical_source, execution_source_receipt=receipt,
    )


def build_runtime_source(artifact: TaskArtifact, provider="geophys", *, backend='cpu',
                         _diagnostic=False, _native_feedback_profile=False, resolved_config=None,
                         lift_height_m=None, task_config=None):
    task_config = _configuration() if task_config is None else task_config
    if artifact.to_mapping() != build_artifact(lift_height_m=lift_height_m, task_config=task_config).to_mapping():
        raise ValueError("selected nominal NutAssembly Artifact required")
    if provider not in {"geophys", "mujoco"}:
        raise ValueError("selected provider must be geophys or mujoco")
    if backend != 'cpu' and not ((_diagnostic or _native_feedback_profile)
                                 and provider == 'geophys' and backend == 'cuda'):
        raise ValueError('selected NutAssembly CUDA source requires an explicit GeoPhys profile')
    recipe = task_config["recipe"]
    source_config = recipe["controller"]
    config = (_environment_config(backend=backend, diagnostic=_diagnostic,
                                  native_feedback_profile=_native_feedback_profile, task_config=task_config)
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
    runtime_source = compile_reference_source(
        artifact=artifact,
        scene_source=TaskSceneSource(scene_xml, base, "nut-assembly-square-v1/canonical-source-nutassembly-nominal-v1"),
        bodies={"square-nut-v1": "SquareNut", "square-peg-v1": "peg1",
                "round-peg-v1": "peg2", "panda-v1/base": "link0"},
        frames={EEF: scene["ee_site_name"]}, free_joints={"square-nut-v1": "SquareNut_joint"},
        joint_targets={f"panda-v1/joint{i}": f"actuator{i}" for i in range(1, 8)},
        open_actuators=("actuator8",), composition=composition, config=config,
    )
    if _native_feedback_profile:
        if provider != 'geophys':
            raise ValueError('R05b native feedback profile is GeoPhys-only')
        runtime_source = _r05b_execution_source(runtime_source)
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
        "task_env/assembly/compiler.py", "task_env/environment/task_source.py",
        "task_env/objects/nut_assembly.py", "task_env/assembly/source.py",
        "task_env/tasks/reference_env.py", "task_env/tasks/canonical_solution_lifecycle.py",
        "task_env/runtime/sessions/common.py", "task_env/runtime/sessions/source.py",
        "task_env/trajectory/canonical/execution.py", "task_env/trajectory/canonical/streaming.py",
    )
    controller = root / "task_env/controllers/canonical"
    relative = (*relative, R3_PROFILE_PATH.relative_to(root).as_posix(),
                *(p.relative_to(root).as_posix() for p in controller.glob("*.py") if p.is_file()))
    return {name: _sha(root / name) for name in sorted(set(relative))}


def _build_reference(*, provider, include_solution, backend, gripper_control_hz,
                     diagnostic, native_feedback_profile=False, resolved_config=None, lift_height_m=None, task_config=None):
    """Build the single selected 100 Hz route without importing native providers."""
    from ...controllers.canonical.contracts import digest
    task_config = _configuration() if task_config is None else task_config
    recipe = task_config["recipe"]
    artifact = build_artifact(lift_height_m=lift_height_m, task_config=task_config)
    source, contact_profile = build_runtime_source(
        artifact, provider, backend=backend, _diagnostic=diagnostic,
        _native_feedback_profile=native_feedback_profile, resolved_config=resolved_config,
        lift_height_m=lift_height_m, task_config=task_config,
    )
    dynamic = load_r3_dynamic_profile()
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
        "controller_identity": controller.identity, "base_controller_identity": base_controller_identity,
        "solution_identity": description["identity"], "guard_policy": description["policy_mapping"],
        "guard_policy_identity": description["policy_identity"],
        "outcome_policy": description["outcome_policy_mapping"],
        "outcome_policy_identity": description["outcome_policy_identity"],
        "completion_policy": "on_expert_terminal_stage",
        "arm_execution_profile": "controller-owned-hold-and-linear-native-ramp-v1",
        "native_feedback_contract": "nutassembly-native-feedback-sample-v1",
        "gripper_control_hz": gripper_control_hz,
        "gripper_feedback_hz": 500,
        **({"diagnostic_experiment": "nutassembly-gripper-cadence-v1",
            "physics_backend": backend} if diagnostic else {}),
        **({"native_feedback_profile": R05B_NATIVE_FEEDBACK_PROFILE}
           if native_feedback_profile else {}),
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


def build_reference(*, provider="mujoco", include_solution=True, resolved_config=None, lift_height_m=None, task_config=None):
    """Build the unchanged selected 100 Hz/500 Hz reference route."""
    return _build_reference(
        provider=provider, include_solution=include_solution,
        backend='cpu', gripper_control_hz=500, diagnostic=False, resolved_config=resolved_config,
        lift_height_m=lift_height_m, task_config=task_config,
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


def build_native_feedback_reference(*, backend, gripper_control_hz=500, include_solution=True):
    """Build the bounded normal GeoPhys force-feedback profile admitted by R05b."""
    if backend not in {'cpu', 'cuda'}:
        raise ValueError('R05b native feedback backend must be cpu or cuda')
    if gripper_control_hz not in {100, 500}:
        raise ValueError('R05b native feedback law cadence must be 100 or 500 Hz')
    return _build_reference(
        provider='geophys', include_solution=include_solution,
        backend=backend, gripper_control_hz=gripper_control_hz, diagnostic=False,
        native_feedback_profile=True,
    )


def build_outcome_solution(*, provider="mujoco"):
    """Build the task-owned external Solution for its matching selected source."""
    return build_reference(provider=provider)["solution"]


def build_gripper_cadence_diagnostic_solution(*, backend, gripper_control_hz):
    """Build the task-owned Solution instance bound to one diagnostic cadence."""
    return build_gripper_cadence_diagnostic_reference(
        backend=backend, gripper_control_hz=gripper_control_hz,
    )["solution"]


def build_native_feedback_solution(*, backend, gripper_control_hz=500):
    """Build the task-owned Solution for the admitted normal R05b profile."""
    return build_native_feedback_reference(
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


def _binding(resolved_config=None, lift_height_m=None, task_config=None):
    return ReferenceTaskBinding(build=lambda provider: build_reference(provider=provider, include_solution=False,
                                                                      resolved_config=resolved_config,
                                                                      lift_height_m=lift_height_m, task_config=task_config),
        reset_sample=lambda artifact, seed: sample_reset(artifact, seed, lift_height_m=lift_height_m, task_config=task_config),
        evaluate=lambda state, semantics: evaluate(state, semantics, lift_height_m=lift_height_m, task_config=task_config),
        object_poses=((NUT, "square_nut_v1"), (PEG, "square_peg_v1")),
        external_actions=False, interval_mode="native", recorder_mode="execution",
        external_action_error="selected NutAssembly requires step_expert; unguarded external actions are not admitted",
        reset_seed=_reset_seed, observe_expert_kwargs=_observe_kwargs,
        native_sample_factory=_native_feedback_sample,
        native_interval_receipt_factory=_native_interval_receipt,
        build_external=lambda provider: build_reference(provider=provider, include_solution=False,
                                                        resolved_config=resolved_config,
                                                        lift_height_m=lift_height_m, task_config=task_config),
        build_gripper_cadence_diagnostic=lambda provider, backend, gripper_control_hz, include_solution:
            build_gripper_cadence_diagnostic_reference(
                backend=backend, gripper_control_hz=gripper_control_hz,
                include_solution=include_solution,
            ),
        build_native_feedback_profile=lambda provider, backend, gripper_control_hz, include_solution:
            build_native_feedback_reference(
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
    uses_selected_public_config = True
    selected_controller_profiles = frozenset()
    selected_parameter_limits = {"lift_height_m": (0.01, 0.15)}
    selected_supports_isaac = False

    @staticmethod
    def selected_task_configuration():
        return _configuration()

    @staticmethod
    def selected_default_config(task_config=None):
        return _environment_config(task_config=task_config)

    @staticmethod
    def selected_default_controller_profile(task_config=None):
        return None

    @classmethod
    def from_reference_config(cls, config=None, *, render_mode=None, **kwargs):
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
        env = cls(provider=config.physics_provider, backend=config.environment.runtime.backend,
                  horizon=config.environment.episode.horizon,
                  _binding=_binding(config.environment, dict(config.task_parameters).get("lift_height_m"),
                                    json.loads(config.task_configuration_json)))
        env.resolved_public_config = config
        return env

    @classmethod
    def for_gripper_cadence_diagnostic(cls, *, backend, gripper_control_hz, horizon=6000):
        """Create the explicit bounded GeoPhys cadence experiment selection."""
        return cls(provider='geophys', backend=backend, horizon=horizon,
                   _diagnostic_gripper_control_hz=gripper_control_hz)

    @classmethod
    def for_native_feedback_profile(cls, *, backend, gripper_control_hz=500, horizon=6000):
        """Create the explicit normal R05b GeoPhys native-feedback route."""
        return cls(provider='geophys', backend=backend, horizon=horizon,
                   _native_feedback_gripper_control_hz=gripper_control_hz)
