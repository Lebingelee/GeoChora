"""Audit the frozen DG02 USD through public GeoPhys import/model owners.

The run is S-stage host lowering only: it imports USD semantics, creates the
provider's public rigid model description, and must not initialize a solver.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.abc
import json
import math
import sys
from pathlib import Path


class _ForbiddenEngineFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "mujoco" or fullname.startswith("mujoco."):
            raise RuntimeError("DG02 host model audit must not import MuJoCo")
        if fullname == "taichi_forge" or fullname.startswith("taichi_forge."):
            raise RuntimeError("DG02 host model audit must not import a native backend")
        if fullname == "omni" or fullname.startswith("omni."):
            raise RuntimeError("DG02 host model audit must not import Isaac App")
        return None


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_tuple(values) -> list[float]:
    result = [float(value) for value in values]
    if not all(math.isfinite(value) for value in result):
        raise ValueError("model receipt contains non-finite values")
    return result


def audit(stage_path: Path, plan_path: Path, plan_sha256_path: Path) -> dict:
    stage_path = stage_path.resolve(strict=True)
    plan_path = plan_path.resolve(strict=True)
    plan_sha256_path = plan_sha256_path.resolve(strict=True)
    plan_raw = plan_path.read_bytes()
    plan_sha = hashlib.sha256(plan_raw).hexdigest()
    expected_plan_sha = plan_sha256_path.read_text(encoding="ascii").strip().split()[0]
    if plan_sha != expected_plan_sha:
        raise ValueError("frozen G2 plan SHA-256 mismatch")
    plan = json.loads(plan_raw)
    if plan.get("schema_version") != "f05-dg02-g2-host-plan-v1":
        raise ValueError("unsupported G2 host plan schema")
    if _sha(stage_path) != plan["source"]["usd_stage_sha256"]:
        raise ValueError("USD stage bytes differ from the frozen G2 plan")
    for row in plan["code"]["tracked_inputs"]:
        path = Path(row["path"]).resolve(strict=True)
        if _sha(path) != row["sha256"]:
            raise ValueError(f"G2 implementation source changed after plan freeze: {path}")
    if _sha(Path(plan["source"]["delivery_manifest_path"]).resolve(strict=True)) != plan["source"]["delivery_manifest_sha256"]:
        raise ValueError("USD delivery manifest changed after G2 plan freeze")
    sys.meta_path.insert(0, _ForbiddenEngineFinder())
    try:
        from scene import SceneSource, import_scene_source
        from scene.solver_scene import solver_scene_to_articulation_config

        imported = import_scene_source(SceneSource.usd_path(stage_path, label="f05-dg02-host-g2"), cache=False)
        ir = imported.ir
        solver_scene = imported.build_solver_scene_desc(mesh_collision_policy="strict")
        articulation = solver_scene_to_articulation_config(solver_scene, usd_joint_anchor_tolerance=0.0)
        validation_errors = articulation.validate()
        if validation_errors:
            raise ValueError(f"public articulation config failed validation: {validation_errors}")
        scene_model = imported.build_rigid_scene_model(
            mesh_collision_policy="strict",
            contact_geometry_policy="source",
            use_imported_meshes=True,
            usd_joint_anchor_tolerance=0.0,
        )
        actuators = [
            {
                "name": item.name,
                "trn_type": str(getattr(item.trn_type, "value", item.trn_type)),
                "target": item.target,
                "dyn_type": str(getattr(item.dyn_type, "value", item.dyn_type)),
                "gain_type": str(getattr(item.gain_type, "value", item.gain_type)),
                "bias_type": str(getattr(item.bias_type, "value", item.bias_type)),
                "gain_prm": _finite_tuple(item.gain_prm),
                "bias_prm": _finite_tuple(item.bias_prm),
                "ctrl_limited": item.ctrl_limited,
                "ctrl_range": _finite_tuple(item.ctrl_range),
                "force_limited": item.force_limited,
                "force_range": _finite_tuple(item.force_range),
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
                "range": _finite_tuple(item.range),
                "stiffness": item.stiffness,
                "damping": item.damping,
                "friction_loss": item.friction_loss,
            }
            for item in articulation.tendons
        ]
        equalities = [
            {
                "type": str(getattr(item.type, "value", item.type)),
                "name": item.name,
                "target1": item.target1,
                "target2": item.target2,
                "poly_coef": _finite_tuple(item.poly_coef),
                "solref": _finite_tuple(item.solref),
                "solimp": _finite_tuple(item.solimp),
                "active": item.active,
            }
            for item in articulation.equalities
        ]
        source_semantics = next(
            block for block in ir.extensions
            if block.namespace == "GeoChora.F05SourceSemantics"
        )
        receipt = {
            "schema_version": "f05-dg02-g2-host-model-receipt-v1",
            "run_id": plan["run_id"],
            "plan_path": str(plan_path),
            "plan_sha256": plan_sha,
            "stage_path": str(stage_path),
            "stage_sha256": _sha(stage_path),
            "provider_format": imported.format,
            "imported_semantic_hash": imported.ir_semantic_hash,
            "source_graph_hash": imported.source_graph_hash,
            "source_identity": source_semantics.payload["source_identity"],
            "ir_counts": {
                "bodies": len(ir.bodies),
                "shapes": len(ir.shapes),
                "joints": len(ir.joints),
                "actuators": len(ir.actuators),
                "transmissions": len(ir.transmissions),
                "constraints": len(ir.constraints),
                "materials": len(ir.materials),
                "capabilities": len(ir.capability_report.entries),
            },
            "source_joint_names": sorted(str(joint.dynamics.get("source_name")) for joint in ir.joints if joint.dynamics.get("source_name")),
            "source_actuators_ir": [
                {
                    "name": item.parameters.get("source_name"),
                    "target_kind": item.target_kind,
                    "source_target": item.parameters.get("source_target"),
                    "gain_prm": _finite_tuple(item.parameters.get("gain_prm", ())),
                    "bias_prm": _finite_tuple(item.parameters.get("bias_prm", ())),
                    "ctrl_range": _finite_tuple(item.limits.get("ctrl_range", ())),
                    "force_range": _finite_tuple(item.limits.get("force_range", ())),
                }
                for item in ir.actuators
            ],
            "consumer_counts": {
                "solver_scene_actuators": len(solver_scene.actuators),
                "solver_scene_transmissions": len(solver_scene.transmissions),
                "solver_scene_constraints": len(solver_scene.constraints),
                "articulation_scalar_dofs": articulation.n_dof,
                "articulation_links": articulation.n_links,
                "articulation_actuators": articulation.n_actuators,
                "articulation_tendons": len(articulation.tendons),
                "articulation_equalities": len(articulation.equalities),
                "rigid_model_objects": len(scene_model.objects),
                "rigid_model_positions_shape": list(scene_model.positions.shape),
            },
            "actuators": actuators,
            "tendons": tendons,
            "equalities": equalities,
            "physics": {
                "gravity": _finite_tuple(solver_scene.physics.gravity),
                "time_step_hint": solver_scene.physics.time_step_hint,
            },
            "engine_initialized": False,
            "physics_steps": 0,
            "tripwires": ["MuJoCo import blocked", "taichi-forge import blocked", "omni import blocked"],
        }
        if imported.format != "usd":
            raise ValueError(f"public importer selected unexpected source format {imported.format!r}")
        if (len(articulation.actuators), len(articulation.tendons), len(articulation.equalities)) != (8, 1, 1):
            raise ValueError("existing rigid consumer shape must be 8 source actuators, 1 fixed tendon, and 1 equality")
        if sorted(item["name"] for item in actuators) != [f"actuator{i}" for i in range(1, 9)]:
            raise ValueError("public actuator consumer does not preserve all eight source names")
        if len(tendons[0]["wraps"]) != 2 or [item["coefficient"] for item in tendons[0]["wraps"]] != [0.5, 0.5]:
            raise ValueError("fixed-tendon consumer lost source wrap Jacobian coefficients")
        if equalities[0]["solref"] != [0.005, 1.0] or equalities[0]["solimp"] != [0.95, 0.99, 0.001]:
            raise ValueError("compliant equality consumer differs from authored source parameters")
        return receipt
    finally:
        sys.meta_path = [finder for finder in sys.meta_path if not isinstance(finder, _ForbiddenEngineFinder)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", type=Path)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    result = audit(args.stage, args.plan, args.plan_sha256)
    raw = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if args.receipt:
        args.receipt.write_text(raw, encoding="utf-8")
    print(raw, end="")


if __name__ == "__main__":
    main()
