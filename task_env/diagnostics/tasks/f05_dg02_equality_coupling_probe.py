"""Source-bound, public-API equality coupling probe for the DG02 Goal."""

from __future__ import annotations

import argparse
import hashlib
import importlib.abc
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np


class _ForbiddenImportFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "mujoco" or fullname.startswith("mujoco."):
            raise RuntimeError("DG02 USD coupling probe must not import MuJoCo")
        if fullname == "omni" or fullname.startswith("omni."):
            raise RuntimeError("DG02 USD coupling probe must not import Isaac App/renderer")
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


def _count_step(counter_path: Path, plan: dict, *, completed: bool) -> None:
    row = json.loads(counter_path.read_text())
    reserved = int(plan["limits"]["physics_steps_reserved"])
    if completed:
        row["completed_physics_steps"] += 1
    else:
        if row["attempted_physics_steps"] >= reserved:
            raise RuntimeError("coupling worker would exceed its frozen physics-step reservation")
        row["attempted_physics_steps"] += 1
    _atomic_json(counter_path, row)


def _verify(plan_path: Path, sidecar: Path) -> tuple[dict, str]:
    raw = plan_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != sidecar.read_text(encoding="ascii").split()[0]:
        raise ValueError("DG02 coupling plan hash mismatch")
    plan = json.loads(raw)
    if plan.get("schema_version") != "f05-dg02-equality-coupling-plan-v1":
        raise ValueError("unsupported DG02 equality-coupling plan")
    if os.environ.get("F05_NATIVE_RUN_ID") != plan["run_id"]:
        raise ValueError("supervisor run identity is not bound to this coupling plan")
    if os.environ.get("F05_NATIVE_RUN_PLAN_SHA256") != digest:
        raise ValueError("supervisor run-plan SHA-256 is not bound to this coupling plan")
    runtime = plan["runtime"]
    runtime_hash = hashlib.sha256(json.dumps(runtime, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if os.environ.get("F05_NATIVE_RUNTIME_ENVIRONMENT_SHA256") != runtime_hash:
        raise ValueError("supervisor runtime identity is not bound to the frozen plan")
    if runtime["environment"].get("GEOPHYS_TAICHI_ARCH") != "cpu" or runtime["environment"].get("CUDA_VISIBLE_DEVICES") != "":
        raise ValueError("coupling probe plan is not explicitly CPU-only")
    if Path(sys.executable).resolve(strict=True) != Path(runtime["python"]).resolve(strict=True):
        raise ValueError("coupling probe Python executable differs from frozen runtime")
    if _sha(Path(sys.executable).resolve(strict=True)) != runtime["python_sha256"]:
        raise ValueError("coupling probe Python executable hash differs from frozen runtime")
    for raw_path, expected in runtime["file_sha256"].items():
        if _sha(Path(raw_path).resolve(strict=True)) != expected:
            raise ValueError(f"coupling runtime file changed after plan freeze: {raw_path}")
    for directory in runtime["pythonpath"]:
        if not Path(directory).resolve(strict=True).is_dir():
            raise ValueError(f"coupling Python import path missing: {directory}")
    for row in plan["code"]["tracked_inputs"]:
        path = Path(row["path"]).resolve(strict=True)
        if _sha(path) != row["sha256"]:
            raise ValueError(f"coupling code changed after plan freeze: {path}")
    identity = plan["input_identity"]
    for repo_key, branch_key, head_key in (
        ("core_worktree", "core_branch", "core_input_head"),
        ("provider_worktree", "provider_branch", "provider_input_head"),
    ):
        repo = Path(identity[repo_key]).resolve(strict=True)
        head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        branch = subprocess.run(["git", "-C", str(repo), "branch", "--show-current"], check=True, capture_output=True, text=True).stdout.strip()
        if head != identity[head_key] or branch != identity[branch_key]:
            raise ValueError(f"frozen coupling repository identity mismatch: {repo_key}")
    for key, row in plan["source"].items():
        if isinstance(row, dict) and {"path", "sha256"}.issubset(row):
            if _sha(Path(row["path"]).resolve(strict=True)) != row["sha256"]:
                raise ValueError(f"frozen coupling source input changed: {key}")
    return plan, digest


def _finite(values) -> list[float]:
    result = np.asarray(values, dtype=np.float64).reshape(-1)
    if not np.isfinite(result).all():
        raise ValueError("public solver readback contains non-finite values")
    return [float(value) for value in result]


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


def _public_model(stage_path: Path, label: str):
    from scene import SceneSource, import_scene_source
    from scene.solver_scene import solver_scene_to_articulation_config

    imported = import_scene_source(SceneSource.usd_path(stage_path, label=label), cache=False)
    if imported.format != "usd":
        raise ValueError(f"expected public USD importer, received {imported.format!r}")
    scene_desc = imported.build_solver_scene_desc(mesh_collision_policy="strict")
    articulation = solver_scene_to_articulation_config(scene_desc, usd_joint_anchor_tolerance=0.0)
    errors = articulation.validate()
    if errors:
        raise ValueError(f"public ArticulationConfig validation failed: {errors}")
    model = imported.build_rigid_scene_model(
        mesh_collision_policy="strict",
        contact_geometry_policy="source",
        use_imported_meshes=True,
        usd_joint_anchor_tolerance=0.0,
    )
    data = model.joint_data
    names = data["name_to_joint"]
    qadr = np.asarray(data["jnt_qposadr"], dtype=np.int64)
    dadr = np.asarray(data["jnt_dofadr"], dtype=np.int64)
    addresses = {}
    for name in [f"joint{i}" for i in range(1, 8)] + ["finger_joint1", "finger_joint2"]:
        if name not in names:
            raise ValueError(f"public source model lost joint {name}")
        index = int(names[name])
        addresses[name] = {"joint_index": index, "qpos": int(qadr[index]), "dof": int(dadr[index])}
    return imported, scene_desc, articulation, model, data, addresses


def _run_variant(plan: dict, row: dict, label: str, expected_active: bool, counter_path: Path, ti, config, started: float) -> dict:
    source, oracle = plan["source"], plan["oracle"]
    stage_path = Path(row["path"]).resolve(strict=True)
    if _sha(stage_path) != row["sha256"]:
        raise ValueError(f"{label} USD stage changed after plan freeze")
    imported, scene_desc, articulation, model, data, addresses = _public_model(stage_path, label)
    if len(articulation.actuators) != 8 or len(articulation.equalities) != 1:
        raise ValueError(f"{label} public source feature count differs from 8 actuators/1 equality")
    expected_names = oracle["source_actuator_names"]
    if [str(item.name) for item in articulation.actuators] != expected_names:
        raise ValueError(f"{label} source actuator ordering changed")
    expected_values = oracle["source_actuator_values"]
    observed_actuators = []
    for item, expected in zip(articulation.actuators, expected_values):
        actual = {
            "name": str(item.name),
            "target": str(item.target),
            "gain_type": str(getattr(item.gain_type, "value", item.gain_type)),
            "gain_prm": _finite(item.gain_prm),
            "bias_type": str(getattr(item.bias_type, "value", item.bias_type)),
            "bias_prm": _finite(item.bias_prm),
            "ctrl_range": _finite(item.ctrl_range),
            "force_range": _finite(item.force_range),
        }
        for key in ("gain_prm", "bias_prm", "ctrl_range", "force_range"):
            if not np.allclose(actual[key], expected[key], rtol=0.0, atol=1.0e-7):
                raise ValueError(f"{label} source actuator {actual['name']} {key} changed")
        observed_actuators.append(actual)
    equality = articulation.equalities[0]
    equality_values = {
        "name": str(equality.name),
        "target1": str(equality.target1),
        "target2": str(equality.target2),
        "solref": _finite(equality.solref),
        "solimp": _finite(equality.solimp),
        "active": bool(equality.active),
    }
    expected_eq = oracle["equality"]
    if equality_values["active"] is not expected_active:
        raise ValueError(f"{label} equality active state differs from frozen counterfactual")
    if equality_values["solref"] != expected_eq["solref"] or equality_values["solimp"] != expected_eq["solimp"]:
        raise ValueError(f"{label} equality compliance differs from the original source")
    if equality_values["target1"] != "finger_joint1" or equality_values["target2"] != "finger_joint2":
        raise ValueError(f"{label} equality target joints changed")

    from solvers.rigid import RigidContactConfig, RigidDynamicsConfig, RigidRuntimeConfig, RigidSolverConfig, materialize_rigid
    solver_config = config
    solver = materialize_rigid(model, config=solver_config)
    if int(solver.n_actuators) != 8 or int(solver.n_tendons) != 1 or int(solver.n_dof) != 15:
        raise ValueError(f"{label} public solver model dimensions changed")
    actuator_indices = {str(item.name): index for index, item in enumerate(articulation.actuators)}
    selected_index = actuator_indices.get("actuator8")
    if selected_index is None:
        raise ValueError(f"{label} public actuator8 missing")
    qpos = np.asarray(data["initial_qpos"], dtype=np.float32).copy()
    qvel = np.asarray(data["initial_qvel"], dtype=np.float32).copy()
    qvel.fill(0.0)
    home = oracle["equality"]["arm_home_qpos"]
    for joint, value in home.items():
        qpos[addresses[joint]["qpos"]] = np.float32(value)
    q1_index = addresses["finger_joint1"]["qpos"]
    q2_index = addresses["finger_joint2"]["qpos"]
    d1_index = addresses["finger_joint1"]["dof"]
    d2_index = addresses["finger_joint2"]["dof"]
    qpos[q1_index], qpos[q2_index] = np.float32(0.028), np.float32(0.012)
    qvel[d1_index], qvel[d2_index] = np.float32(0.0), np.float32(0.0)
    controls = np.zeros(int(solver.n_actuators), dtype=np.float32)
    for actuator in articulation.actuators:
        target = str(actuator.target)
        if target in addresses:
            controls[actuator_indices[str(actuator.name)]] = qpos[addresses[target]["qpos"]]
    controls[selected_index] = np.float32(255.0)
    solver.write_qpos(qpos)
    solver.write_qvel(qvel)
    solver.write_ctrl(controls)
    solver.synchronize_kinematic_state()

    before_enable = [solver.read_actuator_enabled(i) for i in range(int(solver.n_actuators))]
    if before_enable != [True] * 8:
        raise ValueError(f"{label} source actuators were not all enabled before isolation: {before_enable}")
    disabled_ack = solver.set_actuator_enabled(int(selected_index), False)
    after_enable = [solver.read_actuator_enabled(i) for i in range(int(solver.n_actuators))]
    expected_enable = [True] * 8
    expected_enable[int(selected_index)] = False
    if disabled_ack is not False or after_enable != expected_enable:
        raise ValueError(f"{label} public API did not disable only actuator8: {after_enable}")
    ctrl_after_disable = _finite(solver.read_ctrl())
    if ctrl_after_disable != _finite(controls) or ctrl_after_disable[selected_index] != 255.0:
        raise ValueError(f"{label} actuator disable changed the nonzero authored control input")

    initial_length = float(solver.read_tendon_length()[0])
    initial_rate = float(solver.read_tendon_velocity()[0])
    source_actuator = articulation.actuators[selected_index]
    expected_enabled_scalar = (
        float(source_actuator.gain_prm[0]) * min(max(float(controls[selected_index]), float(source_actuator.ctrl_range[0])), float(source_actuator.ctrl_range[1]))
        + float(source_actuator.bias_prm[0])
        + float(source_actuator.bias_prm[1]) * initial_length
        + float(source_actuator.bias_prm[2]) * initial_rate
    )
    if expected_enabled_scalar <= 1.0:
        raise ValueError(f"{label} frozen nonzero drive input is not a sensitive actuator-off detector: {expected_enabled_scalar} N")
    initial_gap = float(qpos[q1_index] - qpos[q2_index])
    samples = []
    max_arm_error = 0.0
    max_disabled_force = 0.0
    max_contacts = {"active_body_count": 0, "contact_count_sum": 0, "normal_impulse_sum_Ns": 0.0, "tangent_impulse_l1_Ns": 0.0}
    last_constraint = np.zeros(int(solver.n_dof), dtype=np.float64)
    for step_index in range(1, 251):
        if time.monotonic() - started > float(plan["limits"]["worker_wall_s_max"]):
            raise TimeoutError("coupling worker reached its frozen wall limit")
        _count_step(counter_path, plan, completed=False)
        solver.step()
        _count_step(counter_path, plan, completed=True)
        next_qpos = np.asarray(solver.read_qpos(), dtype=np.float64)
        next_qvel = np.asarray(solver.read_qvel(), dtype=np.float64)
        force = _finite(solver.read_actuator_force())
        qfrc_actuator = _finite(solver.read_qfrc_actuator())
        last_constraint = np.asarray(solver.read_qfrc_constraint(), dtype=np.float64)
        contact = _contact_summary(solver)
        for key, value in contact.items():
            max_contacts[key] = max(max_contacts[key], value)
        max_disabled_force = max(max_disabled_force, abs(force[selected_index]))
        arm_positions = {joint: float(next_qpos[addresses[joint]["qpos"]]) for joint in home}
        arm_error = max(abs(arm_positions[joint] - float(home[joint])) for joint in home)
        max_arm_error = max(max_arm_error, arm_error)
        samples.append({
            "step": step_index,
            "time_s": step_index * 0.002,
            "finger_q_m": [float(next_qpos[q1_index]), float(next_qpos[q2_index])],
            "finger_qvel_m_s": [float(next_qvel[d1_index]), float(next_qvel[d2_index])],
            "finger_gap_m": float(next_qpos[q1_index] - next_qpos[q2_index]),
            "tendon_length_m": float(solver.read_tendon_length()[0]),
            "tendon_rate_m_s": float(solver.read_tendon_velocity()[0]),
            "actuator8_scalar_force_N": force[selected_index],
            "actuator8_enabled": solver.read_actuator_enabled(int(selected_index)),
            "actuator8_ctrl": float(solver.read_ctrl()[selected_index]),
            "arm_max_abs_home_error_rad": arm_error,
            "max_abs_qfrc_actuator_N": max(abs(value) for value in qfrc_actuator),
            "qfrc_constraint_N": _finite(last_constraint),
            "contact": contact,
        })

    final_qpos = np.asarray(solver.read_qpos(), dtype=np.float64)
    final_qvel = np.asarray(solver.read_qvel(), dtype=np.float64)
    final_gap = float(final_qpos[q1_index] - final_qpos[q2_index])
    result = {
        "variant": label,
        "variant_stage_sha256": _sha(stage_path),
        "variant_semantics": "active source equality" if expected_active else "same source equality record with active=false; physical coupling absent",
        "imported_semantic_hash": imported.ir_semantic_hash,
        "source_graph_hash": imported.source_graph_hash,
        "model_dimensions": {"n_qpos": int(data["n_qpos"]), "n_dof": int(solver.n_dof), "n_actuators": int(solver.n_actuators), "n_tendons": int(solver.n_tendons), "n_equalities": len(articulation.equalities)},
        "source_actuators": observed_actuators,
        "source_equality": equality_values,
        "actuator_control": {
            "selected_name": "actuator8",
            "selected_index": int(selected_index),
            "enabled_before": before_enable,
            "disabled_ack": disabled_ack,
            "enabled_during_probe": after_enable,
            "ctrl_after_disable": ctrl_after_disable,
            "expected_enabled_scalar_force_at_initial_state_N": expected_enabled_scalar,
            "measured_disabled_scalar_force_max_abs_N": max_disabled_force,
        },
        "initial_state": {
            "finger_q_m": [float(qpos[q1_index]), float(qpos[q2_index])],
            "finger_gap_m": initial_gap,
            "tendon_length_m": initial_length,
            "tendon_rate_m_s": initial_rate,
            "arm_home_qpos_rad": {name: float(home[name]) for name in home},
        },
        "final_state": {
            "finger_q_m": [float(final_qpos[q1_index]), float(final_qpos[q2_index])],
            "finger_qvel_m_s": [float(final_qvel[d1_index]), float(final_qvel[d2_index])],
            "finger_gap_m": final_gap,
            "tendon_length_m": float(solver.read_tendon_length()[0]),
            "tendon_rate_m_s": float(solver.read_tendon_velocity()[0]),
            "arm_qpos_rad": {joint: float(final_qpos[addresses[joint]["qpos"]]) for joint in home},
        },
        "max_arm_abs_home_error_rad": max_arm_error,
        "max_contact_summary": max_contacts,
        "final_qfrc_constraint_N": _finite(last_constraint),
        "samples": samples,
        "physics_steps": 250,
    }
    del solver, model, data, articulation, scene_desc, imported
    import gc
    gc.collect()
    # Ensure a second scenario cannot silently share solver state.
    return result


def run(plan_path: Path, sidecar: Path, receipt_path: Path, counter_path: Path) -> dict:
    plan_path = plan_path.resolve(strict=True)
    plan, plan_hash = _verify(plan_path, sidecar.resolve(strict=True))
    started = time.monotonic()
    counter_path = counter_path.resolve()
    _atomic_json(counter_path, {
        "schema_version": "f05-dg02-step-counter-v1",
        "run_id": plan["run_id"],
        "attempted_physics_steps": 0,
        "completed_physics_steps": 0,
        "physics_dt_s": 0.002,
    })
    sys.meta_path.insert(0, _ForbiddenImportFinder())
    receipt = {
        "schema_version": "f05-dg02-equality-coupling-receipt-v1",
        "run_id": plan["run_id"],
        "plan_path": str(plan_path),
        "plan_sha256": plan_hash,
        "classification": plan["classification"],
        "core_head": plan["input_identity"]["core_input_head"],
        "provider_head": plan["input_identity"]["provider_input_head"],
        "source_stage_sha256": plan["source"]["usd_stage"]["sha256"],
        "backend": "taichi-forge CPU",
        "backend_initialized": False,
        "physics_steps_attempted": 0,
        "physics_steps_completed": 0,
        "result": "FAIL",
        "errors": [],
    }
    runtime_initialized = False
    try:
        import geophys
        import taichi as ti
        from dataclasses import replace
        from solvers.rigid import RigidContactConfig, RigidDynamicsConfig, RigidRuntimeConfig, RigidSolverConfig

        if os.environ.get("GEOPHYS_TAICHI_ARCH") != "cpu" or os.environ.get("CUDA_VISIBLE_DEVICES") != "":
            raise RuntimeError("worker process is not pinned to CPU with CUDA devices hidden")
        geophys.init_taichi(arch=ti.cpu, offline_cache=False)
        runtime_initialized = True
        receipt["backend_initialized"] = True
        if ti.cfg.arch != ti.cpu:
            raise RuntimeError(f"expected Taichi CPU backend, got {ti.cfg.arch}")
        config = replace(
            RigidSolverConfig(),
            dynamics=RigidDynamicsConfig(dt=0.002, gravity=(0.0, 0.0, 0.0), integrator="implicitfast"),
            contact=RigidContactConfig(enable_ground_contact=False, enable_domain_boundary_contact=False, enable_ccd=False, broadphase="n2"),
            runtime=RigidRuntimeConfig(auto_prewarm=False),
        )
        source = plan["source"]
        variants = plan["oracle"]["coupling_variants"]
        results = {}
        for key, source_key, expected_active in (
            ("active", "coupling_active_variant_stage", True),
            ("inactive", "coupling_inactive_variant_stage", False),
        ):
            results[key] = _run_variant(
                plan,
                source[source_key],
                f"DG02_COUPLING_{key.upper()}",
                expected_active,
                counter_path,
                ti,
                config,
                started,
            )

        detector = plan["oracle"]["coupling_variants"]
        active_gap = abs(float(results["active"]["final_state"]["finger_gap_m"]))
        inactive_gap = abs(float(results["inactive"]["final_state"]["finger_gap_m"]))
        errors = []
        if active_gap > float(detector["relation_abs_error_max_m"]):
            errors.append(f"active source equality failed 0.5s relation gate: |gap|={active_gap} m")
        if inactive_gap <= float(detector["relation_abs_error_max_m"]):
            errors.append(f"inactive-equality counterfactual unexpectedly met relation gate: |gap|={inactive_gap} m")
        if abs(float(results["inactive"]["final_state"]["finger_gap_m"]) - float(results["inactive"]["initial_state"]["finger_gap_m"])) > float(detector["inactive_gap_drift_max_m"]):
            errors.append("inactive-equality counterfactual finger gap drift exceeded its frozen no-coupling bound")
        for key in ("active", "inactive"):
            value = results[key]
            if int(value["physics_steps"]) != 250:
                errors.append(f"{key} route did not execute exactly 250 native steps")
            if value["actuator_control"]["enabled_during_probe"] != [True] * 7 + [False]:
                errors.append(f"{key} route did not isolate only actuator8")
            if value["actuator_control"]["ctrl_after_disable"][-1] != 255.0:
                errors.append(f"{key} route did not retain nonzero source control during actuator isolation")
            if value["actuator_control"]["measured_disabled_scalar_force_max_abs_N"] > float(detector["disabled_actuator_force_max_abs_N"]):
                errors.append(f"{key} route disabled actuator still produced scalar force")
            if value["max_arm_abs_home_error_rad"] > float(detector["arm_home_error_max_rad"]):
                errors.append(f"{key} route arm did not remain within the frozen hold envelope")
            contact = value["max_contact_summary"]
            if contact["active_body_count"] or contact["contact_count_sum"] or contact["normal_impulse_sum_Ns"] > 1.0e-8 or contact["tangent_impulse_l1_Ns"] > 1.0e-8:
                errors.append(f"{key} route had diagnostic contact interference: {contact}")
        counter = json.loads(counter_path.read_text())
        reserved = int(plan["limits"]["physics_steps_reserved"])
        if counter["attempted_physics_steps"] != reserved or counter["completed_physics_steps"] != reserved:
            errors.append(f"coupling route step counts differ from exact reservation: {counter}")
        receipt.update({
            "runtime_environment_sha256": os.environ["F05_NATIVE_RUNTIME_ENVIRONMENT_SHA256"],
            "source_delivery_identity_sha256": source["delivery_identity_sha256"],
            "source_closure_sha256": source["source_closure_sha256"],
            "source_graph_hashes": {key: value["source_graph_hash"] for key, value in results.items()},
            "variants": results,
            "detector": detector,
            "step_counter": counter,
            "wall_seconds": time.monotonic() - started,
            "errors": errors,
            "result": "PASS_SOURCE_USD_EQUALITY_COUPLING" if not errors else "FAIL_SOURCE_USD_EQUALITY_COUPLING",
        })
    except BaseException as exc:
        receipt["errors"].append(f"{type(exc).__name__}: {exc}")
        receipt["result"] = "FAIL_SOURCE_USD_EQUALITY_COUPLING"
    finally:
        counter = json.loads(counter_path.read_text()) if counter_path.exists() else {}
        receipt["physics_steps_attempted"] = int(counter.get("attempted_physics_steps", 0))
        receipt["physics_steps_completed"] = int(counter.get("completed_physics_steps", 0))
        if runtime_initialized:
            try:
                import taichi as ti
                ti.reset()
            except BaseException as exc:
                receipt["errors"].append(f"Taichi cleanup: {type(exc).__name__}: {exc}")
                receipt["result"] = "FAIL_SOURCE_USD_EQUALITY_COUPLING"
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
    return 0 if result["result"] == "PASS_SOURCE_USD_EQUALITY_COUPLING" else 1


if __name__ == "__main__":
    raise SystemExit(main())
