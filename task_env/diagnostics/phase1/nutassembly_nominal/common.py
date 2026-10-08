"""Provider-neutral identities/configuration for the frozen nominal profile."""
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import yaml

from ....controllers.canonical import ProductionCanonicalPandaController
from ....controllers.canonical.contracts import digest
from ....tasks.nut_assembly.assets import (
    NUTASSEMBLY_NOMINAL_V1_ID,
    NUTASSEMBLY_NOMINAL_V1_MASS,
    NUTASSEMBLY_NOMINAL_V1_DIAG_INERTIA,
)
from ....tasks.nut_assembly.canonical_artifact import build_nominal_candidate
from ....tasks.nut_assembly.canonical_source import build_runtime_source
from ....tasks.nut_assembly.canonical_solution import (
    CanonicalNutAssemblyConfig,
    NutAssemblyCanonicalSolutionV1,
)


PROFILE_PATH = Path("task_env/tasks/nut_assembly/profiles/nutassembly-nominal-v1.json")
RATE_NAMES = ("NA-TB500", "NA-TB100", "NA-TB50")
PROVIDERS = ("geophys", "mujoco", "sapien", "genesis")


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_profile(path=PROFILE_PATH):
    path = Path(path)
    profile = json.loads(path.read_text())
    schema_to_id = {
        "nutassembly-nominal-profile-v1": "nutassembly-nominal-v1",
        "nutassembly-nominal-profile-v2": "nutassembly-nominal-v2",
    }
    schema = profile.get("schema_version")
    if schema not in schema_to_id:
        raise ValueError("unsupported nominal NutAssembly profile")
    if profile.get("profile_id") != schema_to_id[schema]:
        raise ValueError("nominal profile identity mismatch")
    asset = profile["asset"]
    if float(asset["mass_kg"]) != NUTASSEMBLY_NOMINAL_V1_MASS:
        raise ValueError("nominal mass differs from frozen profile")
    if tuple(float(v) for v in asset["diagonal_inertia_kg_m2"]) != NUTASSEMBLY_NOMINAL_V1_DIAG_INERTIA:
        raise ValueError("nominal inertia differs from frozen profile")
    if profile["controller"]["force_limit_N"] != 30.0 or profile["controller"]["force_deadband_N"] != 1.0:
        raise ValueError("controller force contract differs from frozen nominal profile")
    if profile["solution"]["fallback_min_closing_force_N"] != 25.0:
        raise ValueError("solution fallback differs from frozen nominal profile")
    if profile["solution"]["fallback_window_s"] != 0.1 or profile["solution"]["fallback_opening_span_max_m"] != 0.0005:
        raise ValueError("stable-grasp fallback window differs from frozen profile")
    if asset.get("geometry_profile_identity") != NUTASSEMBLY_NOMINAL_V1_ID + "/same-followup-compound-geometry":
        raise ValueError("nominal geometry identity differs from the frozen 0.1 kg asset")
    return profile


def source_normalized_xml(source):
    xml = source.scene_source.xml
    meshdir = str(Path(source.scene_source.base_dir) / "assets")
    if meshdir not in xml:
        raise ValueError("Panda asset root is not explicit in source XML")
    return xml.replace(meshdir, "${PANDA_ASSET_ROOT}/assets")


def source_recipe(artifact, source, profile, profile_path=PROFILE_PATH):
    bindings = {
        key: dict(getattr(source, key))
        for key in ("joints", "bodies", "frames", "free_joints", "joint_targets")
    }
    normalized = source_normalized_xml(source)
    recipe = {
        "schema": "nutassembly-source-recipe-v1",
        "profile_id": profile["profile_id"],
        "task_artifact_hash": artifact.identity_hash,
        "normalized_source_xml_sha256": hashlib.sha256(normalized.encode()).hexdigest(),
        "semantic_bindings": bindings,
        "gravity_m_s2": [0.0, 0.0, -9.81],
        "physics_dt_s": artifact.timebase.physics_dt,
        "control_substeps": artifact.timebase.control_substeps,
        "control_dt_s": artifact.timebase.control_dt,
        "nut_asset": dict(next(entity.parameters_si for entity in artifact.world.entities
                                if entity.semantic_id == "square-nut-v1")),
        "source_config_action": asdict(source.config.action),
        "source_config_gripper": asdict(source.config.robot.gripper),
        "asset_profile_sha256": sha256_file(profile_path),
    }
    return recipe


def context(rate, profile_path=PROFILE_PATH, dynamic_profile_path=None):
    profile_path = Path(profile_path)
    profile = read_profile(profile_path)
    artifact = build_nominal_candidate(rate)
    source = build_runtime_source(artifact)
    controller_profile = profile["controller"]
    if source.config.robot.gripper.force_limit_N != 30.0:
        raise ValueError("resolved controller force target must remain 30 N")
    if source.config.robot.gripper.force_deadband_N != 1.0:
        raise ValueError("resolved controller deadband must remain 1 N")
    dynamic_profile = None
    resolved_dynamic_path = None
    if profile["schema_version"] == "nutassembly-nominal-profile-v1":
        source = replace(
            source,
            config=replace(
                source.config,
                action=replace(source.config.action, **controller_profile["action_overrides"]),
                robot=replace(
                    source.config.robot,
                    gripper=replace(source.config.robot.gripper, **controller_profile["gripper_overrides"]),
                ),
            ),
        )
        solution_config = CanonicalNutAssemblyConfig(
            grasp_min_closing_force_N=float(profile["solution"]["fallback_min_closing_force_N"])
        )
        controller = ProductionCanonicalPandaController.from_source(artifact, source)
    else:
        from ....controllers.canonical.production_r2 import ProductionCanonicalPandaControllerR2
        configured_path = Path(controller_profile.get("dynamic_profile_file", "dynamic_profile.yaml"))
        if dynamic_profile_path:
            resolved_dynamic_path = Path(dynamic_profile_path)
        elif configured_path.is_absolute() or configured_path.exists():
            resolved_dynamic_path = configured_path
        else:
            resolved_dynamic_path = profile_path.parent / configured_path
        dynamic_profile = yaml.safe_load(resolved_dynamic_path.read_text())
        source = replace(
            source,
            config=replace(
                source.config,
                action=replace(source.config.action, **controller_profile.get("action_overrides", {})),
                robot=replace(
                    source.config.robot,
                    gripper=replace(source.config.robot.gripper, **controller_profile.get("gripper_overrides", {})),
                ),
            ),
        )
        solution_values = dict(profile["solution"]["config"])
        solution_values.update(dynamic_profile["planner"])
        solution_config = CanonicalNutAssemblyConfig(**solution_values)
        controller = ProductionCanonicalPandaControllerR2.from_source(
            artifact, source, profile=dynamic_profile
        )
    solution = NutAssemblyCanonicalSolutionV1(config=solution_config, control_dt=artifact.timebase.control_dt)
    recipe = source_recipe(artifact, source, profile, profile_path)
    readiness_identity = digest({
        "schema": "canonical-control-readiness-v1",
        "source_sha256": sha256_file("task_env/controllers/canonical/readiness.py"),
        "semantics": "controller close_ready remains independent from solution fallback",
    })
    return {
        "profile": profile,
        "artifact": artifact,
        "source": source,
        "controller": controller,
        "solution_config": solution_config,
        "solution": solution,
        "recipe": recipe,
        "recipe_identity": digest(recipe),
        "readiness_identity": readiness_identity,
        "controller_identity": controller.identity,
        "solution_identity": solution.identity,
        "profile_path": str(profile_path),
        "profile_sha256": sha256_file(profile_path),
        "dynamic_profile": dynamic_profile,
        "dynamic_profile_path": None if resolved_dynamic_path is None else str(resolved_dynamic_path),
        "dynamic_profile_sha256": None if resolved_dynamic_path is None else sha256_file(resolved_dynamic_path),
    }


def identities(rate, profile_path=PROFILE_PATH, dynamic_profile_path=None):
    values = context(rate, profile_path=profile_path, dynamic_profile_path=dynamic_profile_path)
    return {
        "task_artifact_hash": values["artifact"].identity_hash,
        "source_xml_sha256": hashlib.sha256(values["source"].scene_source.xml.encode()).hexdigest(),
        "source_recipe_hash": values["recipe_identity"],
        "normalized_source_xml_sha256": values["recipe"]["normalized_source_xml_sha256"],
        "controller_identity": values["controller_identity"],
        "solution_identity": values["solution_identity"],
        "readiness_identity": values["readiness_identity"],
        "reset_sample_hash": None,
        "timebase": values["artifact"].timebase.to_mapping(),
        "asset_profile_sha256": values["profile_sha256"],
        "dynamic_profile_sha256": values["dynamic_profile_sha256"],
    }
