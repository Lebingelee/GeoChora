"""Source-bound v2 tendon/equality consumer probe for the DG02 Goal."""

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
    prior = json.loads(counter_path.read_text())
    reserve = int(plan["limits"]["physics_steps_reserved"])
    if completed:
        prior["completed_physics_steps"] += 1
    else:
        if prior["attempted_physics_steps"] >= reserve:
            raise RuntimeError("worker attempted to exceed its frozen physics-step reservation")
        prior["attempted_physics_steps"] += 1
    prior.update({"schema_version": "f05-dg02-step-counter-v1", "run_id": plan["run_id"], "physics_dt_s": 0.002})
    _atomic_json(counter_path, prior)
    return prior


def _verify(plan_path: Path, sidecar: Path) -> tuple[dict, str]:
    raw = plan_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != sidecar.read_text(encoding="ascii").split()[0]:
        raise ValueError("N1 semantic plan hash mismatch")
    plan = json.loads(raw)
    if plan.get("schema_version") != "f05-dg02-n1-public-consumer-plan-v1":
        raise ValueError("unsupported N1 public-consumer plan")
    for row in plan["code"]["tracked_inputs"]:
        path = Path(row["path"]).resolve(strict=True)
        if _sha(path) != row["sha256"]:
            raise ValueError(f"N1 code changed after plan freeze: {path}")
    source = plan["source"]
    source_files = (
        "usd_stage",
        "delivery_manifest",
        "recipe",
        "source_inventory",
        "source_audit",
        "mjcf_source",
        "parent_model_compile_plan",
        "parent_model_compile_receipt",
        "parent_model_compile_worker_receipt",
        "diagnostic_variants_manifest",
        "equality_positive_variant_stage",
        "equality_negative_variant_stage",
        "equality_removed_variant_stage",
        "original_physical_oracle",
    )
    for label in source_files:
        if label in source and _sha(Path(source[label]["path"]).resolve(strict=True)) != source[label]["sha256"]:
            raise ValueError(f"N1 frozen source input changed: {label}")
    identity = plan["input_identity"]
    for key, branch_key, head_key in (
        ("provider_worktree", "provider_branch", "provider_input_head"),
        ("core_worktree", "core_branch", "core_input_head"),
    ):
        repo = Path(identity[key]).resolve(strict=True)
        head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        branch = subprocess.run(["git", "-C", str(repo), "branch", "--show-current"], check=True, capture_output=True, text=True).stdout.strip()
        if head != identity[head_key] or branch != identity[branch_key]:
            raise ValueError(f"N1 frozen repository identity changed: {key}")
    runtime = plan["runtime"]
    python = Path(sys.executable).resolve(strict=True)
    if python != Path(runtime["python"]).resolve(strict=True) or _sha(python) != runtime["python_sha256"]:
        raise ValueError("N1 runtime Python identity mismatch")
    for directory in runtime["pythonpath"]:
        if not Path(directory).resolve(strict=True).is_dir():
            raise ValueError(f"N1 Python import path missing: {directory}")
    for raw_path, expected in runtime["file_sha256"].items():
        if _sha(Path(raw_path).resolve(strict=True)) != expected:
            raise ValueError(f"N1 frozen runtime file changed: {raw_path}")
    return plan, digest


def _finite(values) -> list[float]:
    result = np.asarray(values, dtype=np.float64).reshape(-1)
    if not np.isfinite(result).all():
        raise ValueError("N1 readback contains non-finite values")
    return [float(value) for value in result]


def _public_import_model(stage_path: Path, label: str):
    from scene import SceneSource, import_scene_source
    from scene.solver_scene import solver_scene_to_articulation_config

    imported = import_scene_source(SceneSource.usd_path(stage_path, label=label), cache=False)
    if imported.format != "usd":
        raise ValueError(f"expected public USD import for {label}, got {imported.format!r}")
    solver_scene = imported.build_solver_scene_desc(mesh_collision_policy="strict")
    articulation = solver_scene_to_articulation_config(solver_scene, usd_joint_anchor_tolerance=0.0)
    validation_errors = articulation.validate()
    if validation_errors:
        raise ValueError(f"public ArticulationConfig validation failed for {label}: {validation_errors}")
    model = imported.build_rigid_scene_model(
        mesh_collision_policy="strict",
        contact_geometry_policy="source",
        use_imported_meshes=True,
        usd_joint_anchor_tolerance=0.0,
    )
    joint_data = model.joint_data
    if not isinstance(joint_data, dict) or not isinstance(joint_data.get("name_to_joint"), dict):
        raise TypeError(f"public RigidSceneModel for {label} lacks joint name map")
    names = joint_data["name_to_joint"]
    qadr = np.asarray(joint_data["jnt_qposadr"], dtype=np.int64)
    dadr = np.asarray(joint_data["jnt_dofadr"], dtype=np.int64)
    address_map = {}
    for name in ("finger_joint1", "finger_joint2", *[f"joint{i}" for i in range(1, 8)]):
        if name not in names:
            raise ValueError(f"public model {label} lacks source joint {name}")
        index = int(names[name])
        address_map[name] = {"joint_index": index, "qpos": int(qadr[index]), "dof": int(dadr[index])}
        if address_map[name]["qpos"] < 0 or address_map[name]["dof"] < 0:
            raise ValueError(f"source joint {name} does not resolve to scalar qpos/dof")
    return imported, solver_scene, articulation, model, joint_data, address_map


def _solver_config():
    from dataclasses import replace
    from solvers.rigid import RigidContactConfig, RigidDynamicsConfig, RigidRuntimeConfig, RigidSolverConfig

    return replace(
        RigidSolverConfig(),
        dynamics=RigidDynamicsConfig(dt=0.002, gravity=(0.0, 0.0, 0.0), integrator="implicitfast"),
        contact=RigidContactConfig(enable_ground_contact=False, enable_domain_boundary_contact=False, enable_ccd=False, broadphase="n2"),
        runtime=RigidRuntimeConfig(auto_prewarm=False),
    )


def _source_equality_oracle(mass: np.ndarray, *, d1: int, d2: int, q1: float, q2: float, v1: float, v2: float, solref, solimp, dt: float) -> dict:
    """Independent Python transcription of the frozen bilateral scalar row law."""
    matrix = np.asarray(mass, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or not np.isfinite(matrix).all():
        raise ValueError("public mass matrix is invalid for equality oracle")
    jacobian = np.zeros(matrix.shape[0], dtype=np.float64)
    jacobian[d1], jacobian[d2] = 1.0, -1.0
    response = np.linalg.solve(matrix, jacobian)
    weight = float(jacobian @ response)
    diagonal_a, diagonal_b = float(matrix[d1, d1]), float(matrix[d2, d2])
    if min(weight, diagonal_a, diagonal_b) <= 1.0e-12:
        raise ValueError("public mass matrix has non-positive equality response")
    residual = float(q1 - q2)
    free_velocity = float(v1 - v2)
    dmax = min(max(float(solimp[1]), 1.0e-4), 0.9999)
    width = max(float(solimp[2]), 1.0e-10)
    impedance = dmax if abs(residual) / width >= 1.0 else float(solimp[0])
    timeconst = max(float(solref[0]), 2.0 * float(dt))
    dampratio = max(float(solref[1]), 1.0e-4)
    stiffness = 1.0 / (dmax * dmax * timeconst * timeconst * dampratio * dampratio + 1.0e-20)
    damping = 2.0 / (dmax * timeconst + 1.0e-20)
    if float(solref[0]) <= 0.0:
        stiffness = -float(solref[0]) / (dmax * dmax + 1.0e-20)
    if float(solref[1]) <= 0.0:
        damping = -float(solref[1]) / (dmax + 1.0e-20)
    regularization = 1.0 / diagonal_a + 1.0 / diagonal_b
    softness = regularization * (1.0 - impedance) / max(impedance, 1.0e-12)
    target_velocity = free_velocity + float(dt) * (-stiffness * impedance * residual - damping * free_velocity)
    impulse = (target_velocity - free_velocity) / (weight + softness)
    expected_qfrc = jacobian * impulse / float(dt)
    return {
        "residual": residual,
        "free_velocity": free_velocity,
        "mass_response_weight": weight,
        "regularization": regularization,
        "stiffness": stiffness,
        "damping": damping,
        "impedance": impedance,
        "softness": softness,
        "target_velocity": target_velocity,
        "expected_impulse_Ns": impulse,
        "expected_qfrc_constraint_N": _finite(expected_qfrc),
    }


def _contact_summary(solver) -> dict:
    state = solver.read_body_contact_state()
    active = np.asarray(state.get("active", ()), dtype=np.int64)
    count = np.asarray(state.get("count", ()), dtype=np.int64)
    normal = np.asarray(state.get("normal_impulse", ()), dtype=np.float64)
    tangent = np.asarray(state.get("tangent_impulse", ()), dtype=np.float64)
    return {
        "active_body_count": int(np.count_nonzero(active)),
        "contact_count_sum": int(np.sum(count)),
        "normal_impulse_sum_Ns": float(np.sum(normal)),
        "tangent_impulse_l1_Ns": float(np.sum(np.abs(tangent))),
    }


def _zero_solver_refs(*values) -> None:
    import gc

    del values
    gc.collect()


def run(plan_path: Path, plan_sha: Path, receipt_path: Path, counter_path: Path) -> dict:
    plan_path = plan_path.resolve(strict=True)
    plan, plan_hash = _verify(plan_path, plan_sha.resolve(strict=True))
    counter_path = counter_path.resolve()
    sys.meta_path.insert(0, _ForbiddenImportFinder())
    source, oracle = plan["source"], plan["oracle"]
    counters = {"public_usd_imports": 0, "public_rigid_model_builds": 0, "materialize_rigid_calls": 0, "public_solver_step_attempts": 0}
    steps = 0
    runtime_initialized = False
    receipt = {
        "schema_version": "f05-dg02-n1-semantic-probe-receipt-v1",
        "run_id": plan["run_id"],
        "plan_path": str(plan_path),
        "plan_sha256": plan_hash,
        "classification": plan["classification"],
        "source_identity": source.get("source_identity"),
        "source_stage_sha256": _sha(Path(source["usd_stage"]["path"])),
        "physics_steps_attempted": 0,
        "physics_steps_completed": 0,
        "backend_initialized": False,
        "result": "FAIL",
        "errors": [],
    }
    _atomic_json(counter_path, {"schema_version": "f05-dg02-step-counter-v1", "run_id": plan["run_id"], "attempted_physics_steps": 0, "completed_physics_steps": 0, "physics_dt_s": 0.002})
    try:
        imported, solver_scene, articulation, model, joint_data, address_map = _public_import_model(Path(source["usd_stage"]["path"]), "DG02_N1_V2_SOURCE_USD")
        counters["public_usd_imports"] += 1
        counters["public_rigid_model_builds"] += 1
        if imported.ir_semantic_hash != plan["source"].get("expected_ir_semantic_hash", imported.ir_semantic_hash):
            raise ValueError("public USD semantic hash differs from frozen source identity")
        if len(articulation.actuators) != 8 or len(articulation.equalities) != 1:
            raise ValueError("source-bound public ArticulationConfig lost actuator/equality rows")
        if [str(item.name) for item in articulation.actuators] != oracle["source_actuator_names"]:
            raise ValueError("source actuator ordering differs from frozen source")
        source_actuators = oracle["source_actuator_values"]
        observed_actuators = []
        for item, expected in zip(articulation.actuators, source_actuators):
            row = {
                "name": str(item.name),
                "target": str(item.target),
                "transmission": str(getattr(item.trn_type, "value", item.trn_type)),
                "gain_type": str(getattr(item.gain_type, "value", item.gain_type)),
                "gain_prm": _finite(item.gain_prm),
                "bias_type": str(getattr(item.bias_type, "value", item.bias_type)),
                "bias_prm": _finite(item.bias_prm),
                "ctrl_range": _finite(item.ctrl_range),
                "force_range": _finite(item.force_range),
            }
            for field in ("gain_prm", "bias_prm", "ctrl_range", "force_range"):
                if len(row[field]) != len(expected[field]) or not np.allclose(row[field], expected[field], rtol=0.0, atol=1.0e-7):
                    raise ValueError(f"source actuator {row['name']} {field} differs from N0_008 exact consumer receipt")
            if row["name"] != expected["name"] or row["target"] != expected["target"] or row["transmission"] != expected["transmission"]:
                raise ValueError(f"source actuator identity changed: {row}")
            observed_actuators.append(row)
        if not any(item["name"] == "actuator8" and item["target"] == "split" and item["transmission"].lower().endswith("tendon") for item in observed_actuators):
            raise ValueError("public source model lost actuator8's fixed-tendon transmission")

        import geophys
        import taichi as ti
        from solvers.rigid import materialize_rigid

        counters["public_init_taichi_calls"] = 1
        geophys.init_taichi(arch=ti.cpu, offline_cache=False)
        runtime_initialized = True
        receipt["backend_initialized"] = True
        if ti.cfg.arch != ti.cpu:
            raise RuntimeError(f"expected Taichi CPU, got {ti.cfg.arch}")
        config = _solver_config()
        counters["materialize_rigid_calls"] += 1
        solver = materialize_rigid(model, config=config)
        if int(solver.n_actuators) != 8 or int(solver.n_tendons) != 1 or int(solver.n_dof) != 15:
            raise ValueError(f"unexpected public source solver counts: actuators={solver.n_actuators}, tendons={solver.n_tendons}, dof={solver.n_dof}")
        actuator_index = {str(item.name): index for index, item in enumerate(articulation.actuators)}
        q1, q2 = address_map["finger_joint1"]["qpos"], address_map["finger_joint2"]["qpos"]
        d1, d2 = address_map["finger_joint1"]["dof"], address_map["finger_joint2"]["dof"]
        base_qpos = np.asarray(joint_data["initial_qpos"], np.float32).copy()
        base_qvel = np.asarray(joint_data["initial_qvel"], np.float32).copy()

        def controls_for(state_qpos, ctrl8):
            controls = np.zeros(int(solver.n_actuators), dtype=np.float32)
            for actuator in articulation.actuators:
                target = str(actuator.target)
                if target in joint_data["name_to_joint"]:
                    target_joint = int(joint_data["name_to_joint"][target])
                    controls[actuator_index[str(actuator.name)]] = state_qpos[int(joint_data["jnt_qposadr"][target_joint])]
            controls[actuator_index["actuator8"]] = np.float32(ctrl8)
            return controls

        observations = []
        scenarios = (
            {"name": "asymmetric_tendon_and_ctrl_clipping", "q1": 0.01, "q2": 0.03, "dq1": 0.02, "dq2": 0.08, "ctrl8": 300.0},
            {"name": "scalar_force_cap", "q1": 1.05, "q2": 1.05, "dq1": 0.0, "dq2": 0.0, "ctrl8": 255.0},
        )
        errors = []
        for scenario in scenarios:
            q, v = base_qpos.copy(), base_qvel.copy()
            q[q1], q[q2] = np.float32(scenario["q1"]), np.float32(scenario["q2"])
            v[d1], v[d2] = np.float32(scenario["dq1"]), np.float32(scenario["dq2"])
            controls = controls_for(q, scenario["ctrl8"])
            solver.write_qpos(q)
            solver.write_qvel(v)
            solver.write_ctrl(controls)
            solver.synchronize_kinematic_state()
            tendon_length_pre = _finite(solver.read_tendon_length())
            tendon_velocity_pre = _finite(solver.read_tendon_velocity())
            expected_pre_length = 0.5 * (float(q[q1]) + float(q[q2]))
            expected_pre_velocity = 0.5 * (float(v[d1]) + float(v[d2]))
            if abs(tendon_length_pre[0] - expected_pre_length) > oracle["epsilon"]["length_m"]:
                errors.append(f"pre-step public tendon length mismatch in {scenario['name']}: {tendon_length_pre[0]} vs {expected_pre_length}")
            if abs(tendon_velocity_pre[0] - expected_pre_velocity) > oracle["epsilon"]["velocity_m_s"]:
                errors.append(f"pre-step public tendon velocity mismatch in {scenario['name']}: {tendon_velocity_pre[0]} vs {expected_pre_velocity}")
            pre_state = {"qpos": _finite(q), "qvel": _finite(v), "ctrl": _finite(solver.read_ctrl())}
            _record_step_attempt(counter_path, plan, completed=False)
            counters["public_solver_step_attempts"] += 1
            steps += 1
            solver.step()
            _record_step_attempt(counter_path, plan, completed=True)
            force = _finite(solver.read_actuator_force())
            qfrc_act = _finite(solver.read_qfrc_actuator())
            qfrc_constraint = _finite(solver.read_qfrc_constraint())
            post_qpos, post_qvel = _finite(solver.read_qpos()), _finite(solver.read_qvel())
            observations.append({
                "scenario": scenario["name"],
                "pre_state": pre_state,
                "tendon_length_pre_step": tendon_length_pre,
                "tendon_velocity_pre_step": tendon_velocity_pre,
                "tendon_length_pre_expected_from_qpos": expected_pre_length,
                "tendon_velocity_pre_expected_from_qvel": expected_pre_velocity,
                "tendon_length_post_step": _finite(solver.read_tendon_length()),
                "tendon_velocity_post_step": _finite(solver.read_tendon_velocity()),
                "post_state": {"qpos": post_qpos, "qvel": post_qvel},
                "actuator_force_after_step": force,
                "qfrc_actuator_after_step": qfrc_act,
                "qfrc_constraint_after_step": qfrc_constraint,
                "actuator_force_sample_status": {name: getattr(solver.actuator_force_sample_status(), name) for name in (
                    "schema_version", "source_generation", "sample_sequence", "state_revision", "configuration_revision", "native_step_index", "phase", "valid", "invalid_reason"
                )},
                "finger_addresses": {"qpos": [q1, q2], "dof": [d1, d2]},
            })

        state1, state2 = observations
        expected1, expected2 = oracle["test_state_1"], oracle["test_state_2"]
        force1 = state1["actuator_force_after_step"][actuator_index["actuator8"]]
        projection1 = [state1["qfrc_actuator_after_step"][d1], state1["qfrc_actuator_after_step"][d2]]
        if abs(force1 - expected1["expected_actuator_force"]) > oracle["epsilon"]["force_n"]:
            errors.append(f"source tendon actuator expected {expected1['expected_actuator_force']} N, got {force1}")
        if any(abs(x - expected1["expected_each_finger_generalized_force"]) > oracle["epsilon"]["generalized_force_n"] for x in projection1):
            errors.append(f"source tendon J^T projection expected .75/.75 N, got {projection1}")
        force2 = state2["actuator_force_after_step"][actuator_index["actuator8"]]
        projection2 = [state2["qfrc_actuator_after_step"][d1], state2["qfrc_actuator_after_step"][d2]]
        if abs(force2 - expected2["expected_clipped_actuator_force"]) > oracle["epsilon"]["force_n"]:
            errors.append(f"source tendon scalar force cap expected -100 N, got {force2}")
        if any(abs(x - expected2["expected_each_finger_generalized_force"]) > oracle["epsilon"]["generalized_force_n"] for x in projection2):
            errors.append(f"source tendon capped J^T projection expected -50/-50 N, got {projection2}")
        if any(not item["actuator_force_sample_status"]["valid"] for item in observations):
            errors.append("source actuator force readback was invalid for a completed step")
        source_equality = [{"name": str(item.name), "target1": str(item.target1), "target2": str(item.target2), "solref": _finite(item.solref), "solimp": _finite(item.solimp), "active": bool(item.active)} for item in articulation.equalities]
        removed_relation_preflight = oracle["variant_preflight"].get("removed_relation_negative")
        if not removed_relation_preflight or removed_relation_preflight.get("status") != "EXPECTED_IMPORT_REJECTION":
            errors.append("removed-equality negative was not rejected by the frozen public import preflight")
        source_info = {
            "provider_format": imported.format,
            "imported_semantic_hash": imported.ir_semantic_hash,
            "source_graph_hash": imported.source_graph_hash,
            "delivery_identity_sha256": source["delivery_identity_sha256"],
            "source_closure_sha256": source["source_closure_sha256"],
            "source_stage_sha256": _sha(Path(source["usd_stage"]["path"])),
            "public_model_counts": {"n_qpos": int(joint_data["n_qpos"]), "n_dof": int(joint_data["n_dof"]), "n_actuators": int(solver.n_actuators), "n_tendons": int(solver.n_tendons), "n_equalities": len(articulation.equalities)},
            "joint_name_to_index_qpos_dof": address_map,
            "tendon_jacobian_source": {"joint_names": ["finger_joint1", "finger_joint2"], "dof_addresses": [d1, d2], "coefficients": [0.5, 0.5]},
            "actuators": observed_actuators,
            "equality_source": source_equality,
            "observations": observations,
        }
        receipt["source_consumer"] = source_info
        del solver, model, joint_data, articulation, solver_scene, imported
        import gc
        gc.collect()

        equality_results = {}
        for variant_name, stage_key, expected_equalities in (
            ("positive", "equality_positive_variant_stage", 1),
            ("negative", "equality_negative_variant_stage", 1),
        ):
            equality_stage_path = Path(source[stage_key]["path"])
            imp, scene_desc, art, diagnostic_model, data, addresses = _public_import_model(equality_stage_path, f"DG02_N1_EQUALITY_{variant_name.upper()}")
            counters["public_usd_imports"] += 1
            counters["public_rigid_model_builds"] += 1
            if len(art.actuators) != 8 or len(art.equalities) != expected_equalities:
                raise ValueError(f"{variant_name} equality public consumer count mismatch")
            if any(any(float(x) != 0.0 for x in tuple(item.gain_prm) + tuple(item.bias_prm)) for item in art.actuators):
                raise ValueError(f"{variant_name} equality isolation left an actuator gain/bias active")
            if variant_name == "positive":
                if not art.equalities[0].active or _finite(art.equalities[0].solref) != oracle["equality"]["solref"] or _finite(art.equalities[0].solimp) != oracle["equality"]["solimp"]:
                    raise ValueError("positive equality variant did not preserve exact source compliance")
            elif art.equalities[0].active:
                raise ValueError("inactive equality negative did not preserve the relation with active=false")
            counters["materialize_rigid_calls"] += 1
            equality_solver = materialize_rigid(diagnostic_model, config=config)
            if int(equality_solver.n_actuators) != 8 or int(equality_solver.n_tendons) != 1 or int(equality_solver.n_dof) != 15:
                raise ValueError(f"{variant_name} equality solver model counts changed")
            eq_q1 = addresses["finger_joint1"]["qpos"]
            eq_q2 = addresses["finger_joint2"]["qpos"]
            eq_d1 = addresses["finger_joint1"]["dof"]
            eq_d2 = addresses["finger_joint2"]["dof"]
            eq_qpos = np.asarray(data["initial_qpos"], np.float32).copy()
            eq_qvel = np.asarray(data["initial_qvel"], np.float32).copy()
            arm_home_qpos = oracle["equality"]["arm_home_qpos"]
            for joint_name, home_value in arm_home_qpos.items():
                if joint_name not in addresses:
                    raise ValueError(f"frozen original home pose refers to unknown source joint {joint_name}")
                eq_qpos[addresses[joint_name]["qpos"]] = np.float32(home_value)
            eq_qpos[eq_q1], eq_qpos[eq_q2] = np.float32(oracle["equality"]["finger_joint1_q"]), np.float32(oracle["equality"]["finger_joint2_q"])
            eq_qvel[eq_d1], eq_qvel[eq_d2] = np.float32(oracle["equality"]["finger_joint1_dq"]), np.float32(oracle["equality"]["finger_joint2_dq"])
            eq_ctrl = np.zeros(int(equality_solver.n_actuators), np.float32)
            equality_solver.write_qpos(eq_qpos)
            equality_solver.write_qvel(eq_qvel)
            equality_solver.write_ctrl(eq_ctrl)
            equality_solver.synchronize_kinematic_state()
            pre_gap = float(eq_qpos[eq_q1] - eq_qpos[eq_q2])
            pre_velocity = [float(eq_qvel[eq_d1]), float(eq_qvel[eq_d2])]
            _record_step_attempt(counter_path, plan, completed=False)
            counters["public_solver_step_attempts"] += 1
            steps += 1
            equality_solver.step()
            _record_step_attempt(counter_path, plan, completed=True)
            qfrc = np.asarray(equality_solver.read_qfrc_constraint(), dtype=np.float64)
            post_qpos = np.asarray(equality_solver.read_qpos(), dtype=np.float64)
            post_qvel = np.asarray(equality_solver.read_qvel(), dtype=np.float64)
            qM = np.asarray(equality_solver.read_qM(), dtype=np.float64)
            contact = _contact_summary(equality_solver)
            actuator_force = _finite(equality_solver.read_actuator_force())
            observed_gap = float(post_qpos[eq_q1] - post_qpos[eq_q2])
            row = {
                "variant": variant_name,
                "variant_stage_sha256": _sha(equality_stage_path),
                "public_model_counts": {"n_dof": int(equality_solver.n_dof), "n_actuators": int(equality_solver.n_actuators), "n_tendons": int(equality_solver.n_tendons), "n_equalities": len(art.equalities)},
                "source_equalities": [{"name": str(item.name), "target1": str(item.target1), "target2": str(item.target2), "solref": _finite(item.solref), "solimp": _finite(item.solimp), "active": bool(item.active)} for item in art.equalities],
                "pre_state": {"q1": float(eq_qpos[eq_q1]), "q2": float(eq_qpos[eq_q2]), "dq1": pre_velocity[0], "dq2": pre_velocity[1], "gap": pre_gap, "arm_home_qpos": {name: float(eq_qpos[addresses[name]["qpos"]]) for name in arm_home_qpos}},
                "post_state": {"q1": float(post_qpos[eq_q1]), "q2": float(post_qpos[eq_q2]), "dq1": float(post_qvel[eq_d1]), "dq2": float(post_qvel[eq_d2]), "gap": observed_gap},
                "qfrc_constraint_N": _finite(qfrc),
                "public_dense_mass_matrix_shape": list(qM.shape),
                "contact_summary": contact,
                "actuator_force_after_step_N": actuator_force,
            }
            if variant_name == "positive":
                row["independent_source_row_law_oracle"] = _source_equality_oracle(
                    qM,
                    d1=eq_d1,
                    d2=eq_d2,
                    q1=float(eq_qpos[eq_q1]),
                    q2=float(eq_qpos[eq_q2]),
                    v1=pre_velocity[0],
                    v2=pre_velocity[1],
                    solref=oracle["equality"]["solref"],
                    solimp=oracle["equality"]["solimp"],
                    dt=float(oracle["equality"]["dt"]),
                )
                expected_qfrc = np.asarray(row["independent_source_row_law_oracle"]["expected_qfrc_constraint_N"], dtype=np.float64)
                actual_qfrc = np.asarray(_finite(qfrc), dtype=np.float64)
                diff = np.abs(actual_qfrc - expected_qfrc)
                tolerance = max(float(oracle["epsilon"]["equality_force_n_abs_floor"]), float(np.max(np.abs(expected_qfrc))) * float(oracle["epsilon"]["equality_force_relative"]))
                row["independent_source_row_law_oracle"]["max_absolute_force_error_N"] = float(np.max(diff))
                row["independent_source_row_law_oracle"]["frozen_force_tolerance_N"] = tolerance
                if float(np.max(diff)) > tolerance:
                    errors.append(f"positive equality qfrc differs from independent source row law by {float(np.max(diff))} N > {tolerance} N")
                if not abs(observed_gap) < abs(pre_gap) - float(oracle["equality"]["positive_minimum_gap_reduction_m"]):
                    errors.append(f"active source equality did not reduce gap: before={pre_gap}, after={observed_gap}")
                if contact["active_body_count"] or contact["contact_count_sum"] or contact["normal_impulse_sum_Ns"] > 1.0e-8 or contact["tangent_impulse_l1_Ns"] > 1.0e-8:
                    errors.append(f"positive equality diagnostic had contact interference: {contact}")
                if max(abs(x) for x in actuator_force) > 1.0e-6:
                    errors.append("positive equality diagnostic actuator force was not zero")
            else:
                if np.max(np.abs(qfrc)) > float(oracle["equality"]["negative_maximum_constraint_force_N"]):
                    errors.append("inactive-equality negative control produced a constraint force")
                if abs(observed_gap - pre_gap) > float(oracle["equality"]["negative_maximum_gap_change_m"]):
                    errors.append("inactive-equality negative control changed the joint gap")
                if contact["active_body_count"] or contact["contact_count_sum"] or contact["normal_impulse_sum_Ns"] > 1.0e-8 or contact["tangent_impulse_l1_Ns"] > 1.0e-8:
                    errors.append(f"negative equality diagnostic had contact interference: {contact}")
                if max(abs(x) for x in actuator_force) > 1.0e-6:
                    errors.append("negative equality diagnostic actuator force was not zero")
            equality_results[variant_name] = row
            del equality_solver, diagnostic_model, data, art, scene_desc, imp
            gc.collect()

        receipt.update({
            "provider_format": "usd",
            "source_graph_hash": source_info["source_graph_hash"],
            "imported_semantic_hash": source_info["imported_semantic_hash"],
            "delivery_identity_sha256": source["delivery_identity_sha256"],
            "source_closure_sha256": source["source_closure_sha256"],
            "diagnostic_equality_variants": equality_results,
            "removed_relation_negative_preflight": removed_relation_preflight,
            "step_counters": counters,
            "physics_steps_attempted": steps,
            "physics_steps_completed": json.loads(counter_path.read_text())["completed_physics_steps"],
            "errors": errors,
            "result": "PASS_V2_PUBLIC_CONSUMERS" if not errors else "FAIL_V2_PUBLIC_CONSUMERS",
        })
        if steps != int(plan["limits"]["physics_steps_reserved"]):
            receipt["errors"].append("worker did not consume exactly the frozen four-step reservation")
            receipt["result"] = "FAIL_V2_PUBLIC_CONSUMERS"
    except BaseException as exc:
        receipt["errors"].append(f"{type(exc).__name__}: {exc}")
        receipt["result"] = "FAIL_V2_PUBLIC_CONSUMERS"
    finally:
        counter = json.loads(counter_path.read_text())
        receipt["physics_steps_attempted"] = int(counter.get("attempted_physics_steps", steps))
        receipt["physics_steps_completed"] = int(counter.get("completed_physics_steps", 0))
        receipt["step_counters"] = counters
        if runtime_initialized:
            try:
                import taichi as ti
                ti.reset()
            except BaseException as exc:
                receipt["errors"].append(f"Taichi cleanup: {type(exc).__name__}: {exc}")
                receipt["result"] = "FAIL_V2_PUBLIC_CONSUMERS"
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
    return 0 if result["result"] == "PASS_V2_PUBLIC_CONSUMERS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
