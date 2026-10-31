"""Run the frozen N1 source-USD tendon/actuator public-consumer probe."""

from __future__ import annotations

import argparse
import hashlib
import importlib.abc
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np


class _ForbiddenImportFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "mujoco" or fullname.startswith("mujoco."):
            raise RuntimeError("N1 must not import MuJoCo")
        if fullname == "omni" or fullname.startswith("omni."):
            raise RuntimeError("N1 must not import Isaac App/renderer")
        return None


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)
    directory_fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _record_step_attempt(counter_path: Path, plan: dict, *, completed: bool) -> dict:
    prior = json.loads(counter_path.read_text()) if counter_path.exists() else {"attempted_physics_steps": 0, "completed_physics_steps": 0}
    if completed:
        prior["completed_physics_steps"] += 1
    else:
        if prior["attempted_physics_steps"] >= int(plan["limits"]["physics_steps_reserved"]):
            raise RuntimeError("worker attempted to exceed its frozen physics-step reservation")
        prior["attempted_physics_steps"] += 1
    prior.update({"schema_version": "f05-dg02-step-counter-v1", "run_id": plan["run_id"], "physics_dt_s": 0.002})
    _atomic_json(counter_path, prior)
    return prior


def _verify(plan_path: Path, sidecar: Path) -> tuple[dict, str]:
    raw = plan_path.read_bytes()
    observed = hashlib.sha256(raw).hexdigest()
    if observed != sidecar.read_text(encoding="ascii").split()[0]:
        raise ValueError("N1 frozen plan hash mismatch")
    plan = json.loads(raw)
    if plan.get("schema_version") != "f05-dg02-n1-public-consumer-plan-v1":
        raise ValueError("unsupported N1 plan")
    for row in plan["code"]["tracked_inputs"]:
        path = Path(row["path"]).resolve(strict=True)
        if _sha(path) != row["sha256"]:
            raise ValueError(f"N1 code changed after plan freeze: {path}")
    for label in ("usd_stage", "delivery_manifest", "recipe", "source_inventory", "mjcf_source", "parent_model_compile_plan", "parent_model_compile_receipt"):
        row = plan["source"][label]
        if _sha(Path(row["path"]).resolve(strict=True)) != row["sha256"]:
            raise ValueError(f"N1 source input changed after plan freeze: {label}")
    runtime = plan["runtime"]
    python = Path(sys.executable).resolve(strict=True)
    if python != Path(runtime["python"]).resolve(strict=True) or _sha(python) != runtime["python_sha256"]:
        raise ValueError("N1 runtime Python identity mismatch")
    for directory in runtime["pythonpath"]:
        if not Path(directory).resolve(strict=True).is_dir():
            raise ValueError(f"N1 Python import path missing: {directory}")
    for raw_path, digest in runtime["file_sha256"].items():
        if _sha(Path(raw_path).resolve(strict=True)) != digest:
            raise ValueError(f"N1 frozen runtime file changed: {raw_path}")
    provider = Path(plan["input_identity"]["provider_worktree"]).resolve(strict=True)
    core = Path(plan["input_identity"]["core_worktree"]).resolve(strict=True)
    if subprocess.run(["git", "-C", str(provider), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip() != plan["input_identity"]["provider_input_head"]:
        raise ValueError("N1 provider HEAD changed")
    if subprocess.run(["git", "-C", str(core), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip() != plan["input_identity"]["core_input_head"]:
        raise ValueError("N1 Core HEAD changed")
    if subprocess.run(["git", "-C", str(core), "branch", "--show-current"], check=True, capture_output=True, text=True).stdout.strip() != plan["input_identity"]["core_branch"]:
        raise ValueError("N1 Core branch changed")
    if subprocess.run(["git", "-C", str(provider), "branch", "--show-current"], check=True, capture_output=True, text=True).stdout.strip() != plan["input_identity"]["provider_branch"]:
        raise ValueError("N1 provider branch changed")
    return plan, observed


def _finite(values) -> list[float]:
    out = np.asarray(values, dtype=np.float64).reshape(-1)
    if not np.isfinite(out).all():
        raise ValueError("N1 readback contains non-finite values")
    return [float(x) for x in out]


def run(plan_path: Path, plan_sha: Path, receipt_path: Path, counter_path: Path) -> dict:
    plan, plan_hash = _verify(plan_path.resolve(strict=True), plan_sha.resolve(strict=True))
    counter_path = counter_path.resolve()
    sys.meta_path.insert(0, _ForbiddenImportFinder())
    source = plan["source"]
    oracle = plan["oracle"]
    counters = {"public_init_taichi_calls": 0, "materialize_rigid_calls": 0, "public_solver_step_attempts": 0}
    steps = 0
    runtime_initialized = False
    receipt = {
        "schema_version": "f05-dg02-n1-public-consumer-receipt-v1",
        "run_id": plan["run_id"],
        "plan_path": str(plan_path.resolve()),
        "plan_sha256": plan_hash,
        "classification": plan["classification"],
        "source": source["source_identity"],
        "usd_stage_sha256": _sha(Path(source["usd_stage"]["path"])),
        "physics_steps_attempted": 0,
        "physics_steps_completed": 0,
        "backend_initialized": False,
        "result": "FAIL",
        "errors": [],
    }
    _atomic_json(counter_path, {"schema_version": "f05-dg02-step-counter-v1", "run_id": plan["run_id"], "attempted_physics_steps": 0, "completed_physics_steps": 0, "physics_dt_s": 0.002})
    try:
        from scene import SceneSource, import_scene_source
        from scene.solver_scene import solver_scene_to_articulation_config

        public_source = SceneSource.usd_path(Path(source["usd_stage"]["path"]), label=plan["run_id"])
        imported = import_scene_source(public_source, cache=False)
        if imported.format != "usd":
            raise ValueError(f"expected public USD import, got {imported.format!r}")
        solver_scene = imported.build_solver_scene_desc(mesh_collision_policy="strict")
        articulation = solver_scene_to_articulation_config(solver_scene, usd_joint_anchor_tolerance=0.0)
        validation_errors = articulation.validate()
        if validation_errors:
            raise ValueError(f"ArticulationConfig validation failed: {validation_errors}")
        model = imported.build_rigid_scene_model(
            mesh_collision_policy="strict",
            contact_geometry_policy="source",
            use_imported_meshes=True,
            usd_joint_anchor_tolerance=0.0,
        )
        joint_data = model.joint_data
        if not isinstance(joint_data, dict):
            raise TypeError("public RigidSceneModel has no compiled joint_data mapping")
        name_to_joint = joint_data.get("name_to_joint")
        if not isinstance(name_to_joint, dict):
            raise TypeError("compiled joint_data lacks source joint name map")
        qadr_values = np.asarray(joint_data["jnt_qposadr"], dtype=np.int64)
        dadr_values = np.asarray(joint_data["jnt_dofadr"], dtype=np.int64)
        qpos = np.asarray(joint_data["initial_qpos"], dtype=np.float32).copy()
        qvel = np.asarray(joint_data["initial_qvel"], dtype=np.float32).copy()
        required_names = ["finger_joint1", "finger_joint2", *[f"joint{i}" for i in range(1, 8)]]
        missing_names = [name for name in required_names if name not in name_to_joint]
        if missing_names:
            raise ValueError(f"public model joint map lacks required source names: {missing_names}")
        if qpos.shape != (int(joint_data["n_qpos"]),) or qvel.shape != (int(joint_data["n_dof"]),):
            raise ValueError("public model initial qpos/qvel do not match compiled coordinate counts")
        joint_map = {}
        for name in required_names:
            jidx = int(name_to_joint[name])
            joint_map[name] = {"joint_index": jidx, "qpos_address": int(qadr_values[jidx]), "dof_address": int(dadr_values[jidx])}
            if joint_map[name]["qpos_address"] < 0 or joint_map[name]["dof_address"] < 0:
                raise ValueError(f"source joint {name} does not map to scalar qpos/dof addresses")

        q1 = joint_map["finger_joint1"]["qpos_address"]
        q2 = joint_map["finger_joint2"]["qpos_address"]
        d1 = joint_map["finger_joint1"]["dof_address"]
        d2 = joint_map["finger_joint2"]["dof_address"]

        import geophys
        import taichi as ti
        from dataclasses import replace
        from solvers.rigid import (
            RigidContactConfig,
            RigidDynamicsConfig,
            RigidRuntimeConfig,
            RigidSolverConfig,
            materialize_rigid,
        )

        counters["public_init_taichi_calls"] += 1
        geophys.init_taichi(arch=ti.cpu, offline_cache=False)
        runtime_initialized = True
        if ti.cfg.arch != ti.cpu:
            raise RuntimeError(f"expected Taichi CPU, got {ti.cfg.arch}")
        receipt["backend_initialized"] = True

        base = RigidSolverConfig()
        config = replace(
            base,
            dynamics=RigidDynamicsConfig(dt=0.002, gravity=(0.0, 0.0, 0.0), integrator="implicitfast"),
            contact=RigidContactConfig(enable_ground_contact=False, enable_domain_boundary_contact=False, enable_ccd=False, broadphase="n2"),
            runtime=RigidRuntimeConfig(auto_prewarm=False),
        )
        counters["materialize_rigid_calls"] += 1
        solver = materialize_rigid(model, config=config)
        if int(solver.n_actuators) != 8 or int(solver.n_tendons) != 1 or int(solver.n_dof) != 15:
            raise ValueError(f"unexpected public solver model counts: actuators={solver.n_actuators}, tendons={solver.n_tendons}, dof={solver.n_dof}")

        actuator_names = [str(item.name) for item in articulation.actuators]
        actuator_index = {name: index for index, name in enumerate(actuator_names)}
        if actuator_names != oracle["source_actuator_names"]:
            raise ValueError(f"source actuator ordering changed: {actuator_names}")

        def controls_for(state_qpos: np.ndarray, ctrl8: float) -> np.ndarray:
            controls = np.zeros(int(solver.n_actuators), dtype=np.float32)
            for actuator in articulation.actuators:
                index = actuator_index[str(actuator.name)]
                target = str(actuator.target)
                if target in name_to_joint:
                    target_joint = int(name_to_joint[target])
                    controls[index] = state_qpos[int(qadr_values[target_joint])]
            controls[actuator_index["actuator8"]] = np.float32(ctrl8)
            return controls

        observations = []
        scenarios = [
            {"name": "asymmetric_tendon_and_ctrl_clipping", "q1": 0.01, "q2": 0.03, "dq1": 0.02, "dq2": 0.08, "ctrl8": 300.0},
            {"name": "scalar_force_cap", "q1": 1.05, "q2": 1.05, "dq1": 0.0, "dq2": 0.0, "ctrl8": 255.0},
        ]
        for scenario in scenarios:
            q = qpos.copy()
            v = qvel.copy()
            q[q1], q[q2] = np.float32(scenario["q1"]), np.float32(scenario["q2"])
            v[d1], v[d2] = np.float32(scenario["dq1"]), np.float32(scenario["dq2"])
            controls = controls_for(q, scenario["ctrl8"])
            pre_state = {"qpos": _finite(q), "qvel": _finite(v), "ctrl": _finite(controls)}
            solver.write_qpos(q)
            solver.write_qvel(v)
            solver.write_ctrl(controls)
            solver.synchronize_kinematic_state()

            _record_step_attempt(counter_path, plan, completed=False)
            counters["public_solver_step_attempts"] += 1
            steps += 1
            solver.step()
            _record_step_attempt(counter_path, plan, completed=True)

            force = _finite(solver.read_actuator_force())
            qfrc_act = _finite(solver.read_qfrc_actuator())
            qfrc_constraint = _finite(solver.read_qfrc_constraint())
            post_qpos = _finite(solver.read_qpos())
            post_qvel = _finite(solver.read_qvel())
            tendon_length = _finite(solver.read_tendon_length())
            tendon_velocity = _finite(solver.read_tendon_velocity())
            sample_status = solver.actuator_force_sample_status()
            tendon_length_from_state = 0.5 * (post_qpos[q1] + post_qpos[q2])
            tendon_velocity_from_state = 0.5 * (post_qvel[d1] + post_qvel[d2])
            observations.append({
                "scenario": scenario["name"],
                "pre_state": pre_state,
                "post_state": {"qpos": post_qpos, "qvel": post_qvel},
                "tendon_length_post": tendon_length,
                "tendon_velocity_post": tendon_velocity,
                "tendon_length_from_post_state": float(tendon_length_from_state),
                "tendon_velocity_from_post_state": float(tendon_velocity_from_state),
                "actuator_force_after_step": force,
                "qfrc_actuator_after_step": qfrc_act,
                "qfrc_constraint_after_step": qfrc_constraint,
                "actuator_force_sample_status": {name: getattr(sample_status, name) for name in (
                    "schema_version", "source_generation", "sample_sequence", "state_revision",
                    "configuration_revision", "native_step_index", "phase", "valid", "invalid_reason"
                )},
                "finger_addresses": {"qpos": [q1, q2], "dof": [d1, d2]},
            })

        state1 = observations[0]
        expected1 = oracle["test_state_1"]
        observed_force1 = state1["actuator_force_after_step"][actuator_index["actuator8"]]
        expected_tendon_force1 = expected1["expected_actuator_force"]
        expected_controller_force1 = [expected1["expected_each_finger_generalized_force"]] * 2
        observed_controller_force1 = [state1["qfrc_actuator_after_step"][d1], state1["qfrc_actuator_after_step"][d2]]
        raw_eq1 = [state1["qfrc_constraint_after_step"][d1], state1["qfrc_constraint_after_step"][d2]]
        errors = []
        if abs(observed_force1 - expected_tendon_force1) > oracle["epsilon"]["force_n"]:
            errors.append(f"source actuator8 expected {expected_tendon_force1} N in scenario 1, got {observed_force1}")
        if abs(state1["tendon_length_post"][0] - state1["tendon_length_from_post_state"]) > oracle["epsilon"]["length_m"]:
            errors.append("public tendon length readback disagrees with post-step qpos and source Jacobian")
        if abs(state1["tendon_velocity_post"][0] - state1["tendon_velocity_from_post_state"]) > oracle["epsilon"]["velocity_m_s"]:
            errors.append("public tendon velocity readback disagrees with post-step qvel and source Jacobian")
        if not state1["actuator_force_sample_status"]["valid"]:
            errors.append("public actuator-force sample is invalid after the source-model step")
        for observed, expected in zip(observed_controller_force1, expected_controller_force1):
            if abs(observed - expected) > oracle["epsilon"]["generalized_force_n"]:
                errors.append(f"tendon J^T force expected {expected_controller_force1}, got {observed_controller_force1}")
                break
        if abs(observed_force1 - expected_tendon_force1) <= oracle["epsilon"]["force_n"] and max(abs(x) for x in raw_eq1) < 1.0e-5:
            errors.append("active source joint equality produced no measurable constraint force for the asymmetric probe state")

        state2 = observations[1]
        observed_force2 = state2["actuator_force_after_step"][actuator_index["actuator8"]]
        expected_force2 = oracle["test_state_2"]["expected_clipped_actuator_force"]
        if abs(observed_force2 - expected_force2) > oracle["epsilon"]["force_n"]:
            errors.append(f"source force cap expected {expected_force2} N in scenario 2, got {observed_force2}")
        observed_projection2 = [state2["qfrc_actuator_after_step"][d1], state2["qfrc_actuator_after_step"][d2]]
        expected_projection2 = [oracle["test_state_2"]["expected_each_finger_generalized_force"]] * 2
        if any(abs(observed - expected) > oracle["epsilon"]["generalized_force_n"] for observed, expected in zip(observed_projection2, expected_projection2)):
            errors.append(f"force-capped tendon J^T projection expected {expected_projection2}, got {observed_projection2}")
        receipt.update({
            "provider_format": imported.format,
            "imported_semantic_hash": imported.ir_semantic_hash,
            "source_graph_hash": imported.source_graph_hash,
            "delivery_identity_sha256": source["delivery_identity_sha256"],
            "source_closure_sha256": source["source_closure_sha256"],
            "stage_sha256": _sha(Path(source["usd_stage"]["path"])),
            "public_model_counts": {"n_qpos": int(joint_data["n_qpos"]), "n_dof": int(joint_data["n_dof"]), "n_actuators": int(solver.n_actuators), "n_tendons": int(solver.n_tendons), "n_equalities": len(articulation.equalities)},
            "joint_name_to_index_qpos_dof": joint_map,
            "tendon_jacobian_addresses": {"joint_names": ["finger_joint1", "finger_joint2"], "dof_addresses": [d1, d2], "coefficients": [0.5, 0.5]},
            "actuators": [{"name": item.name, "target": item.target, "transmission": str(getattr(item.trn_type, "value", item.trn_type)), "gain_prm": _finite(item.gain_prm), "bias_prm": _finite(item.bias_prm), "ctrl_range": _finite(item.ctrl_range), "force_range": _finite(item.force_range)} for item in articulation.actuators],
            "equality_source": [{"name": item.name, "target1": item.target1, "target2": item.target2, "solref": _finite(item.solref), "solimp": _finite(item.solimp), "active": item.active} for item in articulation.equalities],
            "observations": observations,
            "step_counters": counters,
            "physics_steps_attempted": steps,
            "physics_steps_completed": json.loads(counter_path.read_text())["completed_physics_steps"],
            "errors": errors,
            "result": "PASS_PROBE" if not errors else "FAIL_PROBE",
        })
        if steps != int(plan["limits"]["physics_steps_reserved"]):
            receipt["errors"].append("worker did not consume exactly its frozen two-step reservation")
            receipt["result"] = "FAIL_PROBE"
    except BaseException as exc:
        receipt["errors"].append(f"{type(exc).__name__}: {exc}")
        receipt["result"] = "FAIL_PROBE"
    finally:
        receipt["physics_steps_attempted"] = int(json.loads(counter_path.read_text()).get("attempted_physics_steps", steps))
        receipt["physics_steps_completed"] = int(json.loads(counter_path.read_text()).get("completed_physics_steps", 0))
        receipt["step_counters"] = counters
        if runtime_initialized:
            try:
                import taichi as ti
                ti.reset()
            except BaseException as exc:
                receipt["errors"].append(f"Taichi cleanup: {type(exc).__name__}: {exc}")
                receipt["result"] = "FAIL_PROBE"
        _atomic_json(receipt_path.resolve(), receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--counter", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.plan, args.plan_sha256, args.receipt, args.counter)
    return 0 if result["result"] == "PASS_PROBE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
