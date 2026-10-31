"""Compile and read the DG02 public GeoPhys host model on CPU, without stepping."""

from __future__ import annotations

import argparse
import hashlib
import importlib.abc
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np


class _ForbiddenImportFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "mujoco" or fullname.startswith("mujoco."):
            raise RuntimeError("DG02 N0 model compile must not import MuJoCo")
        if fullname == "omni" or fullname.startswith("omni."):
            raise RuntimeError("DG02 N0 model compile must not import Isaac App")
        return None


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite(values) -> list[float]:
    result = [float(value) for value in values]
    if not all(math.isfinite(value) for value in result):
        raise ValueError("DG02 N0 model receipt contains non-finite values")
    return result


def _verify_plan(plan_path: Path, sidecar_path: Path) -> tuple[dict, str]:
    raw = plan_path.read_bytes()
    observed_hash = hashlib.sha256(raw).hexdigest()
    expected_hash = sidecar_path.read_text(encoding="ascii").strip().split()[0]
    if observed_hash != expected_hash:
        raise ValueError("DG02 N0 plan SHA-256 mismatch")
    plan = json.loads(raw)
    if plan.get("schema_version") != "f05-dg02-n0-model-compile-plan-v1":
        raise ValueError("unsupported DG02 N0 plan")
    for row in plan["code"]["tracked_inputs"]:
        path = Path(row["path"]).resolve(strict=True)
        if _sha(path) != row["sha256"]:
            raise ValueError(f"N0 source code changed after plan freeze: {path}")
    for label in ("usd_stage", "delivery_manifest", "recipe", "source_inventory", "source_audit"):
        row = plan["source"][label]
        if _sha(Path(row["path"]).resolve(strict=True)) != row["sha256"]:
            raise ValueError(f"N0 frozen source changed: {label}")
    python = Path(sys.executable).resolve(strict=True)
    planned_python = Path(plan["runtime"]["python"]).resolve(strict=True)
    if python != planned_python:
        raise ValueError("N0 Python executable differs from frozen runtime")
    if _sha(planned_python) != plan["runtime"]["python_sha256"]:
        raise ValueError("N0 Python executable bytes differ from frozen runtime")
    for raw_path in plan["runtime"]["pythonpath"]:
        if not Path(raw_path).resolve(strict=True).is_dir():
            raise ValueError(f"N0 frozen Python module path is not a directory: {raw_path}")
    for raw_path, expected in plan["runtime"]["file_sha256"].items():
        path = Path(raw_path)
        if _sha(path) != expected:
            raise ValueError(f"N0 installed runtime bytes changed: {path}")
    provider = Path(plan["input_identity"]["provider_worktree"]).resolve(strict=True)
    observed_head = subprocess.run(
        ["git", "-C", str(provider), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if observed_head != plan["input_identity"]["provider_input_head"]:
        raise ValueError("GeoPhys provider HEAD changed after N0 plan freeze")
    core = Path(plan["input_identity"]["core_worktree"]).resolve(strict=True)
    observed_core_head = subprocess.run(
        ["git", "-C", str(core), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    observed_core_branch = subprocess.run(
        ["git", "-C", str(core), "branch", "--show-current"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if observed_core_head != plan["input_identity"]["core_input_head"] or observed_core_branch != plan["input_identity"]["core_branch"]:
        raise ValueError("Core checkout identity changed after N0 plan freeze")
    return plan, observed_hash


def audit(plan_path: Path, sidecar_path: Path) -> dict:
    plan_path = plan_path.resolve(strict=True)
    sidecar_path = sidecar_path.resolve(strict=True)
    plan, plan_sha = _verify_plan(plan_path, sidecar_path)
    stage_path = Path(plan["source"]["usd_stage"]["path"]).resolve(strict=True)
    counters = {"init_taichi": 0, "ti_init": 0, "ti_reset": 0, "solver_construct": 0}

    sys.meta_path.insert(0, _ForbiddenImportFinder())
    try:
        # Importing the public rigid package imports Taichi Forge at module
        # load. This N0 run authorizes that CPU module load but traps every
        # backend initialization/reset and every solver construction.
        import geophys

        def forbid_init_taichi(*_args, **_kwargs):
            counters["init_taichi"] += 1
            raise RuntimeError("N0 forbids GeoPhys init_taichi")

        geophys.init_taichi = forbid_init_taichi

        from scene import SceneSource, import_scene_source
        from scene.solver_scene import solver_scene_to_articulation_config

        imported = import_scene_source(SceneSource.usd_path(stage_path, label="f05-dg02-n0"), cache=False)
        if imported.format != "usd":
            raise ValueError(f"N0 imported unexpected format: {imported.format!r}")
        solver_scene = imported.build_solver_scene_desc(mesh_collision_policy="strict")
        articulation = solver_scene_to_articulation_config(solver_scene, usd_joint_anchor_tolerance=0.0)
        expected_joint_names = set(plan["oracle"]["source_joint_names"])
        source_joint_names = sorted(
            str(joint.dynamics.get("source_name"))
            for joint in imported.ir.joints
            if joint.dynamics.get("source_name") in expected_joint_names
        )
        errors = articulation.validate()
        if errors:
            raise ValueError(f"N0 ArticulationConfig validation failed: {errors}")

        import taichi as ti

        def forbid_ti_init(*_args, **_kwargs):
            counters["ti_init"] += 1
            raise RuntimeError("N0 forbids ti.init")

        def forbid_ti_reset(*_args, **_kwargs):
            counters["ti_reset"] += 1
            raise RuntimeError("N0 forbids ti.reset")

        ti.init = forbid_ti_init
        ti.reset = forbid_ti_reset

        from solvers.rigid import RigidSolver

        original_solver_init = RigidSolver.__init__

        def forbid_solver_construct(self, *_args, **_kwargs):
            counters["solver_construct"] += 1
            raise RuntimeError("N0 forbids RigidSolver construction")

        RigidSolver.__init__ = forbid_solver_construct
        try:
            model = imported.build_rigid_scene_model(
                mesh_collision_policy="strict",
                contact_geometry_policy="source",
                use_imported_meshes=True,
                usd_joint_anchor_tolerance=0.0,
            )
        finally:
            RigidSolver.__init__ = original_solver_init

        source_audit = json.loads(
            Path(plan["source"]["source_audit"]["path"]).read_text(encoding="utf-8")
        )
        recipe = json.loads(
            Path(plan["source"]["recipe"]["path"]).read_text(encoding="utf-8")
        )
        if source_audit["usd_stage_sha256"] != _sha(stage_path):
            raise ValueError("source geometry/material audit is not bound to the frozen USD stage")
        if source_audit["source_xml_sha256"] != plan["source"]["source_mjcf_sha256"]:
            raise ValueError("source geometry/material audit is not bound to the frozen MJCF source")
        recipe_material = recipe["feature_semantics"]["collision_material"]
        expected_collision_paths = tuple(
            sorted(
                str(row["shape"])
                for row in source_audit["panda"]["collision_material_bindings"]
            )
        )
        shape_by_source_path = {
            str(shape.source_ref.element_path): shape
            for shape in imported.ir.shapes
            if shape.source_ref is not None
        }
        missing_source_paths = sorted(set(expected_collision_paths) - set(shape_by_source_path))
        if missing_source_paths:
            raise ValueError(
                "USD semantic IR does not retain source-audited Panda collision paths: "
                f"{missing_source_paths}"
            )
        source_path_by_shape_id = {
            str(shape_by_source_path[path].shape_id): path
            for path in expected_collision_paths
        }
        expected_collision_names = tuple(sorted(source_path_by_shape_id))
        panda_collision_materials = []
        for link in articulation.links:
            for geom in link.geoms:
                role = str(getattr(geom.role, "value", geom.role))
                name = str(geom.name)
                if name not in expected_collision_names or role not in ("collision", "both"):
                    continue
                panda_collision_materials.append({
                    "link": str(link.name),
                    "name": name,
                    "source_path": source_path_by_shape_id[name],
                    "role": role,
                    "friction": _finite(geom.friction),
                    "sliding_friction_authored": bool(geom.sliding_friction_authored),
                    "static_friction": None if geom.static_friction is None else float(geom.static_friction),
                    "restitution": None if geom.restitution is None else float(geom.restitution),
                    "friction_combine_mode": geom.friction_combine_mode,
                    "restitution_combine_mode": geom.restitution_combine_mode,
                })
        observed_collision_names = tuple(sorted(row["name"] for row in panda_collision_materials))
        if observed_collision_names != expected_collision_names:
            raise ValueError(
                "public ArticulationConfig collision materials do not cover the source-audited Panda shapes: "
                f"expected={expected_collision_names}; observed={observed_collision_names}; "
                f"config_geoms={[(str(link.name), str(geom.name), str(getattr(geom.role, 'value', geom.role))) for link in articulation.links for geom in link.geoms]}"
            )
        if len({row["name"] for row in panda_collision_materials}) != len(panda_collision_materials):
            raise ValueError("public ArticulationConfig contains duplicate Panda collision shape names")

        contact_oracle = plan["oracle"]["panda_collision_material"]
        for key in (
            "source_effective_mjcf_geom_friction",
            "geophys_geom_config_friction",
            "usd_static_friction",
            "usd_restitution_target_only",
            "source_mjcf_restitution_parameter",
            "cross_solver_friction_law_equivalence_claim",
        ):
            recipe_key = {
                "source_effective_mjcf_geom_friction": "source_effective_mjcf_geom_friction",
                "geophys_geom_config_friction": "geophys_geom_config_friction_expected",
                "usd_static_friction": "usd_physics_material_api",
                "usd_restitution_target_only": "usd_physics_material_api",
                "source_mjcf_restitution_parameter": "source_mjcf_restitution_parameter",
                "cross_solver_friction_law_equivalence_claim": "cross_solver_friction_law_equivalence_claim",
            }[key]
            expected_recipe_value = recipe_material[recipe_key]
            if key in ("usd_static_friction", "usd_restitution_target_only"):
                expected_recipe_value = expected_recipe_value[
                    "static_friction" if key == "usd_static_friction" else "restitution"
                ]
            if contact_oracle[key] != expected_recipe_value:
                raise ValueError(f"N0 frozen material oracle differs from the v2 recipe at {key}")
        if contact_oracle["collision_shape_count"] != len(expected_collision_paths):
            raise ValueError("N0 frozen collision count differs from the source audit")
        expected_friction = contact_oracle["geophys_geom_config_friction"]
        expected_compiled_friction = _finite(np.asarray(expected_friction, dtype=np.float32))
        if expected_compiled_friction != contact_oracle["geophys_geom_config_friction_f32"]:
            raise ValueError("N0 frozen compiled-material oracle differs from the binary32 conversion")
        for row in panda_collision_materials:
            if row["friction"] != expected_friction:
                raise ValueError(f"public ArticulationConfig friction mismatch for {row['name']}")
            if not row["sliding_friction_authored"]:
                raise ValueError(f"public ArticulationConfig lost authored sliding friction for {row['name']}")
            if row["static_friction"] != contact_oracle["usd_static_friction"]:
                raise ValueError(f"public ArticulationConfig static friction mismatch for {row['name']}")
            if row["restitution"] != contact_oracle["usd_restitution_target_only"]:
                raise ValueError(f"public ArticulationConfig restitution target mismatch for {row['name']}")

        joint_data = model.joint_data or {}
        compiled_names = tuple(str(value) for value in joint_data.get("geom_names", ()))
        compiled_friction = np.asarray(joint_data.get("geom_friction", ()), dtype=np.float64)
        compiled_static_friction = np.asarray(joint_data.get("geom_static_friction", ()), dtype=np.float64).reshape(-1)
        compiled_restitution = np.asarray(joint_data.get("geom_restitution", ()), dtype=np.float64).reshape(-1)
        compiled_collision_materials = []
        for index, name in enumerate(compiled_names):
            if name not in expected_collision_names:
                continue
            if index >= len(compiled_friction) or index >= len(compiled_static_friction) or index >= len(compiled_restitution):
                raise ValueError("compiled public model contact arrays do not cover Panda collision shapes")
            compiled_collision_materials.append({
                "name": name,
                "friction": _finite(compiled_friction[index]),
                "static_friction": float(compiled_static_friction[index]),
                "restitution": float(compiled_restitution[index]),
            })
        compiled_collision_materials.sort(key=lambda row: row["name"])
        if tuple(row["name"] for row in compiled_collision_materials) != expected_collision_names:
            raise ValueError("compiled public rigid model does not preserve all source-audited Panda collision materials")
        for row in compiled_collision_materials:
            if row["friction"] != expected_compiled_friction:
                raise ValueError(f"compiled public model friction mismatch for {row['name']}")
            if row["static_friction"] != contact_oracle["usd_static_friction"]:
                raise ValueError(f"compiled public model static friction mismatch for {row['name']}")
            if row["restitution"] != contact_oracle["usd_restitution_target_only"]:
                raise ValueError(f"compiled public model restitution target mismatch for {row['name']}")

        actuators = [
            {
                "name": item.name,
                "transmission": str(getattr(item.trn_type, "value", item.trn_type)),
                "target": item.target,
                "dyn_type": str(getattr(item.dyn_type, "value", item.dyn_type)),
                "gain_type": str(getattr(item.gain_type, "value", item.gain_type)),
                "bias_type": str(getattr(item.bias_type, "value", item.bias_type)),
                "gear": _finite(item.gear),
                "dyn_prm": _finite(item.dyn_prm),
                "gain_prm": _finite(item.gain_prm),
                "bias_prm": _finite(item.bias_prm),
                "ctrl_limited": item.ctrl_limited,
                "ctrl_range": _finite(item.ctrl_range),
                "force_limited": item.force_limited,
                "force_range": _finite(item.force_range),
            }
            for item in articulation.actuators
        ]
        tendons = [
            {
                "name": item.name,
                "wraps": [
                    {"type": str(getattr(wrap.type, "value", wrap.type)), "target": wrap.target, "coefficient": wrap.divisor}
                    for wrap in item.wraps
                ],
                "limited": item.limited,
                "range": _finite(item.range),
                "stiffness": item.stiffness,
                "damping": item.damping,
                "friction_loss": item.friction_loss,
                "margin": item.margin,
                "solref_limit": _finite(item.solref_limit),
                "solimp_limit": _finite(item.solimp_limit),
                "solref_friction": _finite(item.solref_friction),
                "solimp_friction": _finite(item.solimp_friction),
            }
            for item in articulation.tendons
        ]
        equalities = [
            {
                "name": item.name,
                "type": str(getattr(item.type, "value", item.type)),
                "target1": item.target1,
                "target2": item.target2,
                "poly_coef": _finite(item.poly_coef),
                "solref": _finite(item.solref),
                "solimp": _finite(item.solimp),
                "active": item.active,
            }
            for item in articulation.equalities
        ]
        receipt = {
            "schema_version": "f05-dg02-n0-model-receipt-v1",
            "run_id": plan["run_id"],
            "plan_path": str(plan_path),
            "plan_sha256": plan_sha,
            "stage_path": str(stage_path),
            "stage_sha256": _sha(stage_path),
            "delivery_identity_sha256": plan["source"]["delivery_identity_sha256"],
            "source_closure_sha256": plan["source"]["source_closure_sha256"],
            "provider_format": imported.format,
            "imported_semantic_hash": imported.ir_semantic_hash,
            "source_graph_hash": imported.source_graph_hash,
            "ir_counts": {
                "bodies": len(imported.ir.bodies),
                "shapes": len(imported.ir.shapes),
                "joints": len(imported.ir.joints),
                "actuators": len(imported.ir.actuators),
                "transmissions": len(imported.ir.transmissions),
                "constraints": len(imported.ir.constraints),
                "materials": len(imported.ir.materials),
            },
            "source_joint_names": source_joint_names,
            "consumer_counts": {
                "solver_scene_actuators": len(solver_scene.actuators),
                "solver_scene_transmissions": len(solver_scene.transmissions),
                "solver_scene_constraints": len(solver_scene.constraints),
                "scalar_dof_count": articulation.n_dof,
                "link_count": articulation.n_links,
                "actuator_count": articulation.n_actuators,
                "tendon_count": len(articulation.tendons),
                "equality_count": len(articulation.equalities),
                "rigid_model_object_count": len(model.objects),
                "rigid_model_position_shape": list(model.positions.shape),
                "rigid_model_orientation_shape": list(model.orientations.shape),
            },
            "actuators": actuators,
            "tendons": tendons,
            "equalities": equalities,
            "panda_collision_materials": panda_collision_materials,
            "compiled_panda_collision_materials": compiled_collision_materials,
            "contact_material_scope": {
                "source_effective_mjcf_geom_friction": contact_oracle["source_effective_mjcf_geom_friction"],
                "usd_friction_law_equivalence_claim": contact_oracle["cross_solver_friction_law_equivalence_claim"],
                "source_mjcf_restitution_parameter": contact_oracle["source_mjcf_restitution_parameter"],
                "usd_restitution_equivalence_claim": contact_oracle["usd_restitution_equivalence_claim"],
            },
            "gravity": _finite(solver_scene.physics.gravity),
            "source_identity": plan["source"]["source_identity"],
            "backend_module_imported": "taichi_forge" in sys.modules,
            "backend_initialized": False,
            "physics_steps": 0,
            "tripwire_counts": counters,
        }
        oracle = plan["oracle"]
        if articulation.n_actuators != oracle["actuator_count"] or len(articulation.tendons) != oracle["tendon_count"] or len(articulation.equalities) != oracle["equality_count"]:
            raise ValueError("public rigid model consumer counts differ from the frozen source oracle")
        if sorted(row["name"] for row in actuators) != oracle["actuator_names"]:
            raise ValueError("public model does not preserve all source actuator names")
        if receipt["source_joint_names"] != oracle["source_joint_names"]:
            raise ValueError("public model does not preserve all nine source scalar-joint names")
        tendon = tendons[0]
        if tendon["name"] != oracle["tendon_name"] or tendon["wraps"] != oracle["tendon_wraps"]:
            raise ValueError("public fixed-tendon model differs from the frozen source wraps")
        equality = equalities[0]
        if equality["solref"] != oracle["equality_solref"] or equality["solimp"] != oracle["equality_solimp_authored"]:
            raise ValueError("public equality model differs from the authored soft-constraint values")
        actuator8 = next(row for row in actuators if row["name"] == "actuator8")
        for field in ("gain_prm", "bias_prm", "ctrl_range", "force_range"):
            if actuator8[field] != oracle["actuator8"][field]:
                raise ValueError(f"public actuator8 model differs from the source oracle at {field}")
        if any(counters.values()):
            raise ValueError(f"forbidden backend/solver operation occurred: {counters}")
        return receipt
    finally:
        sys.meta_path = [finder for finder in sys.meta_path if not isinstance(finder, _ForbiddenImportFinder)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.plan, args.plan_sha256)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
