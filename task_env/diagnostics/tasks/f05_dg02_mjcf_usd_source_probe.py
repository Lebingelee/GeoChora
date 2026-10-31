"""Pair the DG02 Panda source through GeoPhys' public MJCF and USD consumers.

This is a bounded fixed-state/fixed-control source-law diagnostic. It is not a
Core task run, online R3 controller run, qualification, or format-equivalence
claim. The MJCF scene adds only the frozen DG02 support and free cube primitives
to the exact protected Menagerie Panda XML so the public host models have the
same task-scene entities as the source-bound USD stage.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.abc
import json
import math
import os
import subprocess
import sys
import traceback
from pathlib import Path

import numpy as np


class _ForbiddenImportFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "mujoco" or fullname.startswith("mujoco."):
            raise RuntimeError("GeoPhys source comparison must not import MuJoCo")
        if fullname == "omni" or fullname.startswith("omni."):
            raise RuntimeError("GeoPhys source comparison must not import an App/renderer")
        return None


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _verify(plan_path: Path, sidecar: Path) -> tuple[dict, str]:
    raw = plan_path.read_bytes()
    observed = hashlib.sha256(raw).hexdigest()
    if observed != sidecar.read_text(encoding="ascii").split()[0]:
        raise ValueError("DG02 MJCF/USD comparison plan SHA-256 mismatch")
    plan = json.loads(raw)
    if plan.get("schema_version") != "f05-dg02-n1-public-consumer-plan-v1":
        raise ValueError("unsupported DG02 source-comparison plan schema")
    for row in plan["code"]["tracked_inputs"]:
        path = Path(row["path"]).resolve(strict=True)
        if _sha(path) != row["sha256"]:
            raise ValueError(f"source-comparison code changed after freeze: {path}")
    for row in plan["source"].values():
        if isinstance(row, dict) and {"path", "sha256"}.issubset(row):
            path = Path(row["path"]).resolve(strict=True)
            if _sha(path) != row["sha256"]:
                raise ValueError(f"source-comparison input changed after freeze: {path}")
    identity = plan["input_identity"]
    for repo_key, head_key, branch_key in (
        ("core_worktree", "core_input_head", "core_branch"),
        ("provider_worktree", "provider_input_head", "provider_branch"),
    ):
        repo = Path(identity[repo_key]).resolve(strict=True)
        head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        branch = subprocess.run(
            ["git", "-C", str(repo), "branch", "--show-current"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        if head != identity[head_key] or branch != identity[branch_key]:
            raise ValueError(f"source-comparison {repo_key} identity changed")
    runtime = plan["runtime"]
    python = Path(sys.executable).resolve(strict=True)
    if python != Path(runtime["python"]).resolve(strict=True) or _sha(python) != runtime["python_sha256"]:
        raise ValueError("source-comparison Python runtime identity mismatch")
    for path, expected in runtime["file_sha256"].items():
        if _sha(Path(path).resolve(strict=True)) != expected:
            raise ValueError(f"source-comparison runtime component changed: {path}")
    expected_steps = int(plan.get("oracle", {}).get("expected_step_count", 0))
    if expected_steps <= 0 or int(plan["limits"]["physics_steps_reserved"]) != expected_steps:
        raise ValueError("source-comparison reservation must match its frozen expected step count")
    return plan, observed


def _finite(values, label: str) -> list[float]:
    result = np.asarray(values, dtype=np.float64).reshape(-1)
    if not np.isfinite(result).all():
        raise ValueError(f"{label} contains non-finite values")
    return [float(value) for value in result]


def _step_counter(path: Path, plan: dict, *, completed: bool) -> None:
    row = json.loads(path.read_text(encoding="utf-8"))
    reserve = int(plan["limits"]["physics_steps_reserved"])
    if completed:
        row["completed_physics_steps"] += 1
    else:
        if row["attempted_physics_steps"] >= reserve:
            raise RuntimeError("source-comparison worker exceeded its frozen step reservation")
        row["attempted_physics_steps"] += 1
    row["schema_version"] = "f05-dg02-step-counter-v1"
    row["run_id"] = plan["run_id"]
    row["physics_dt_s"] = 0.002
    _atomic_json(path, row)


def _public_model(source: dict, fmt: str, label: str):
    from scene import SceneSource, import_scene_source
    from scene.solver_scene import solver_scene_to_articulation_config

    if fmt == "usd":
        declared = SceneSource.usd_path(
            Path(source["usd_stage"]["path"]), label=label,
        )
    elif fmt == "mjcf":
        xml = Path(source["mjcf_task_scene_variant"]["path"]).read_text(encoding="utf-8")
        declared = SceneSource.mjcf_string(
            xml,
            base_dir=Path(source["mjcf_source"]["path"]).resolve().parent,
            label=label,
        )
    else:
        raise ValueError(f"unsupported source format: {fmt}")
    imported = import_scene_source(declared, cache=False)
    if imported.format != fmt:
        raise ValueError(f"public importer returned {imported.format!r} for {fmt!r}")
    solver_scene = imported.build_solver_scene_desc(mesh_collision_policy="strict")
    articulation = solver_scene_to_articulation_config(
        solver_scene, usd_joint_anchor_tolerance=0.0,
    )
    validation_errors = articulation.validate()
    if validation_errors:
        raise ValueError(f"public ArticulationConfig validation failed for {fmt}: {validation_errors}")
    model = imported.build_rigid_scene_model(
        mesh_collision_policy="strict",
        contact_geometry_policy="source",
        use_imported_meshes=True,
        usd_joint_anchor_tolerance=0.0,
    )
    joint_data = model.joint_data
    if not isinstance(joint_data, dict) or not isinstance(joint_data.get("name_to_joint"), dict):
        raise TypeError(f"public {fmt} host model lacks the source joint map")
    name_to_joint = joint_data["name_to_joint"]
    qadr = np.asarray(joint_data["jnt_qposadr"], dtype=np.int64)
    dadr = np.asarray(joint_data["jnt_dofadr"], dtype=np.int64)
    names = ["finger_joint1", "finger_joint2", *[f"joint{i}" for i in range(1, 8)]]
    addresses = {}
    for name in names:
        if name not in name_to_joint:
            raise ValueError(f"public {fmt} host model lacks source joint {name}")
        index = int(name_to_joint[name])
        addresses[name] = {
            "joint_index": index,
            "qpos": int(qadr[index]),
            "dof": int(dadr[index]),
        }
        if min(addresses[name]["qpos"], addresses[name]["dof"]) < 0:
            raise ValueError(f"public {fmt} source joint {name} is not scalar")
    return imported, articulation, model, joint_data, addresses


def _plain(values):
    if isinstance(values, dict):
        return {str(key): _plain(value) for key, value in values.items()}
    if isinstance(values, (tuple, list)):
        return [_plain(value) for value in values]
    if isinstance(values, np.ndarray):
        return _plain(values.tolist())
    if isinstance(values, (np.floating, np.integer)):
        return values.item()
    if isinstance(values, float):
        if not math.isfinite(values):
            raise ValueError("host source model contains a non-finite field")
        return values
    if isinstance(values, (str, int, bool)) or values is None:
        return values
    if hasattr(values, "__dataclass_fields__"):
        return {key: _plain(getattr(values, key)) for key in values.__dataclass_fields__}
    if hasattr(values, "value"):
        return _plain(values.value)
    return str(values)


def _diff_paths(left, right, path="") -> list[dict]:
    differences = []
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right)):
            child = f"{path}.{key}" if path else str(key)
            if key not in left or key not in right:
                differences.append({"path": child, "usd": left.get(key), "mjcf": right.get(key)})
            else:
                differences.extend(_diff_paths(left[key], right[key], child))
        return differences
    if isinstance(left, list) and isinstance(right, list):
        if path.endswith(".host_model_objects"):
            left_by_key = {item["object_key"]: item for item in left}
            right_by_key = {item["object_key"]: item for item in right}
            for key in sorted(set(left_by_key) | set(right_by_key)):
                child = f"{path}[object_key={key!r}]"
                if key not in left_by_key or key not in right_by_key:
                    differences.append({
                        "path": child,
                        "usd": left_by_key.get(key),
                        "mjcf": right_by_key.get(key),
                    })
                else:
                    differences.extend(_diff_paths(left_by_key[key], right_by_key[key], child))
            return differences
        if path.endswith(".body_inertia_kg_m2"):
            # The host model stores principal moments in a local eigenbasis.
            # Their vector order is not a shared world-frame axis contract.
            left, right = sorted(left), sorted(right)
        if len(left) != len(right):
            differences.append({"path": f"{path}.length", "usd": len(left), "mjcf": len(right)})
        for index, (a, b) in enumerate(zip(left, right)):
            differences.extend(_diff_paths(a, b, f"{path}[{index}]"))
        return differences
    if left != right:
        differences.append({"path": path, "usd": left, "mjcf": right})
    return differences


def _field_array(field):
    if field is None:
        return None
    return np.asarray(field.to_numpy() if hasattr(field, "to_numpy") else field)


def _contact_snapshot(contacts, model) -> dict:
    raw_count = _field_array(getattr(contacts, "body_contact_count", None))
    count = None if raw_count is None else int(raw_count.reshape(-1)[0])
    active = _field_array(getattr(contacts, "body_contact_active", None))
    body_a = _field_array(getattr(contacts, "body_contact_body_a", None))
    body_b = _field_array(getattr(contacts, "body_contact_body_b", None))
    friction = _field_array(getattr(contacts, "body_contact_friction", None))
    detailed_fields = {
        "body_contact_point": "point_m",
        "body_contact_normal": "normal",
        "body_contact_penetration": "penetration_m",
        "body_contact_normal_impulse": "normal_impulse_Ns",
        "body_contact_tangent_impulse": "tangent_impulse_Ns",
    }
    details = {key: _field_array(getattr(contacts, key, None)) for key in detailed_fields}
    active_indices = (
        np.flatnonzero(active.reshape(-1).astype(bool)).tolist()
        if active is not None else list(range(max(0, count or 0)))
    )
    object_keys = [str(getattr(item, "object_key", "")) for item in model.objects]

    def body_key(raw_id):
        body_id = int(raw_id)
        return object_keys[body_id] if 0 <= body_id < len(object_keys) else None

    pairs = []
    if body_a is not None and body_b is not None:
        a_flat, b_flat = body_a.reshape(-1), body_b.reshape(-1)
        for index in active_indices:
            if index >= min(a_flat.size, b_flat.size):
                continue
            row = {
                "slot": int(index),
                "body_a_id": int(a_flat[index]),
                "body_b_id": int(b_flat[index]),
                "body_a_key": body_key(a_flat[index]),
                "body_b_key": body_key(b_flat[index]),
            }
            if friction is not None and index < friction.shape[0]:
                row["friction_channels"] = _finite(friction[index], "contact friction channels")
            for field_name, output_name in detailed_fields.items():
                values = details[field_name]
                if values is not None and index < values.shape[0]:
                    row[output_name] = _finite(values[index], f"contact {output_name}")
            pairs.append(row)
    return {
        "body_contact_count": count,
        "active_slot_count": len(active_indices),
        "body_id_mapping_basis": "enumerated public model.objects ordered by body id",
        "body_pairs": pairs,
    }


def _model_without_source_body_contacts(model):
    """Build an in-memory counterfactual model with only contact masks cleared."""
    from dataclasses import replace

    joint_data = dict(model.joint_data or {})
    for field_name in ("geom_contype", "geom_conaffinity"):
        values = np.asarray(joint_data.get(field_name, ()), dtype=np.int32).copy()
        if values.size == 0:
            raise ValueError(f"cannot isolate equality without public {field_name} data")
        joint_data[field_name] = np.zeros_like(values)
    objects = tuple(
        replace(item, contype=0, conaffinity=0)
        for item in model.objects
    )
    return replace(model, objects=objects, joint_data=joint_data)


def _model_with_reference_joint_passives(model, reference_joint_data, joint_names):
    """Align only named MJCF joint damping/armature to a paired USD host model.

    This is an explicitly diagnostic in-memory counterfactual. The parsed
    source, imported IR, and persisted host models are left untouched.
    """
    from dataclasses import replace

    joint_data = dict(model.joint_data or {})
    reference_names = reference_joint_data.get("name_to_joint", {})
    model_names = joint_data.get("name_to_joint", {})
    for field_name in ("jnt_damping", "jnt_armature"):
        values = np.asarray(joint_data.get(field_name, ()), dtype=np.float32).copy()
        reference_values = np.asarray(reference_joint_data.get(field_name, ()), dtype=np.float32)
        if values.size == 0 or reference_values.size == 0:
            raise ValueError(f"cannot align counterfactual joint passive field {field_name}")
        for name in joint_names:
            if name not in model_names or name not in reference_names:
                raise ValueError(f"counterfactual joint passive map lacks {name}")
            values[int(model_names[name])] = reference_values[int(reference_names[name])]
        joint_data[field_name] = values
    return replace(model, joint_data=joint_data)


def _model_receipt(fmt: str, imported, articulation, model, joint_data, addresses) -> dict:
    actuators = [_plain(item) for item in articulation.actuators]
    equalities = [_plain(item) for item in articulation.equalities]
    tendons = [_plain(item) for item in getattr(articulation, "tendons", ())]
    host_objects = []
    for item in getattr(model, "objects", ()):
        fact = getattr(item, "geometry_fact", None)
        body = getattr(item, "body_config", None)
        vertices = None if fact is None else getattr(fact, "mesh_vertices", None)
        indices = None if fact is None else getattr(fact, "mesh_indices", None)
        host_objects.append({
            "object_key": str(getattr(item, "object_key", "")),
            "mass_kg": None if body is None else float(body.mass),
            "gravity_scale": None if body is None else float(body.gravity_scale),
            "linear_damping": None if body is None else float(body.linear_damping),
            "angular_damping": None if body is None else float(body.angular_damping),
            "contype": int(getattr(item, "contype", -1)),
            "conaffinity": int(getattr(item, "conaffinity", -1)),
            "body_inertia_kg_m2": _finite(getattr(item, "body_inertia", []), "host body inertia"),
            "material": _plain(getattr(item, "material_model", None)),
            "geometry": {
                "kind": _plain(getattr(fact, "kind", None)),
                "shape": _plain(getattr(fact, "shape", None)),
                "mesh_vertex_count": None if vertices is None else int(len(vertices)),
                "mesh_index_count": None if indices is None else int(len(indices)),
            },
        })
    host_objects.sort(key=lambda row: row["object_key"])
    return {
        "format": fmt,
        "imported_semantic_hash": imported.ir_semantic_hash,
        "source_graph_hash": imported.source_graph_hash,
        "public_model_counts": {
            "n_qpos": int(joint_data["n_qpos"]),
            "n_dof": int(joint_data["n_dof"]),
            "n_geoms": int(joint_data.get("n_geoms", -1)),
            "n_actuators": len(articulation.actuators),
            "n_tendons": len(tendons),
            "n_equalities": len(equalities),
        },
        "joint_name_to_index_qpos_dof": addresses,
        "joint_passive_parameters": {
            name: {
                "damping": float(np.asarray(joint_data["jnt_damping"])[row["joint_index"]]),
                "armature": float(np.asarray(joint_data["jnt_armature"])[row["joint_index"]]),
            }
            for name, row in addresses.items()
        },
        "actuators": actuators,
        "tendons": tendons,
        "equalities": equalities,
        "host_model_object_count": len(getattr(model, "objects", ())),
        "host_model_objects": host_objects,
    }


def _solver_config():
    from dataclasses import replace
    from solvers.rigid import (
        RigidContactConfig, RigidDynamicsConfig, RigidRuntimeConfig, RigidSolverConfig,
    )
    return replace(
        RigidSolverConfig(),
        dynamics=RigidDynamicsConfig(
            dt=0.002, gravity=(0.0, 0.0, 0.0), integrator="implicitfast",
        ),
        contact=RigidContactConfig(
            enable_ground_contact=False,
            enable_domain_boundary_contact=False,
            enable_ccd=False,
            broadphase="n2",
        ),
        runtime=RigidRuntimeConfig(auto_prewarm=False),
    )


def _run_representation(fmt: str, model_bundle, reference_consumer: dict,
                        plan: dict, counter_path: Path, reference_joint_data=None) -> dict:
    from solvers.rigid import materialize_rigid

    imported, articulation, model, joint_data, addresses = model_bundle
    source_contact_override = not bool(plan.get("source_body_contacts_enabled", True))
    runtime_model = _model_without_source_body_contacts(model) if source_contact_override else model
    passive_override = bool(plan.get("align_mjcf_joint_passives_to_usd_counterfactual", False)) and fmt == "mjcf"
    if passive_override:
        if reference_joint_data is None:
            raise ValueError("MJCF passive counterfactual requires the paired USD public joint model")
        runtime_model = _model_with_reference_joint_passives(
            runtime_model, reference_joint_data,
            ("finger_joint1", "finger_joint2", *[f"joint{i}" for i in range(1, 8)]),
        )
    runtime_joint_data = runtime_model.joint_data or {}
    runtime_passives = {
        name: {
            "damping": float(np.asarray(runtime_joint_data["jnt_damping"])[row["joint_index"]]),
            "armature": float(np.asarray(runtime_joint_data["jnt_armature"])[row["joint_index"]]),
        }
        for name, row in addresses.items()
    }
    solver = materialize_rigid(runtime_model, config=_solver_config())
    actuator_names = [str(item.name) for item in articulation.actuators]
    reference_actuators = [str(item["name"]) for item in reference_consumer["actuators"]]
    if actuator_names != reference_actuators or len(actuator_names) != 8:
        raise ValueError(f"{fmt} actuator names/order differ from the frozen USD reference")
    qpos_seed = np.asarray(joint_data["initial_qpos"], dtype=np.float32).copy()
    qvel_seed = np.asarray(joint_data["initial_qvel"], dtype=np.float32).copy()
    name_map = reference_consumer["joint_name_to_index_qpos_dof"]
    dof_by_name = {name: row["dof"] for name, row in addresses.items()}
    qpos_by_name = {name: row["qpos"] for name, row in addresses.items()}
    observations = []
    for reference in reference_consumer["observations"]:
        scenario = reference["scenario"]
        qpos = qpos_seed.copy()
        qvel = qvel_seed.copy()
        if "pre_state_by_joint" in reference:
            for name in addresses:
                pair = reference["pre_state_by_joint"][name]
                qpos[qpos_by_name[name]] = np.float32(pair["q"])
                qvel[dof_by_name[name]] = np.float32(pair["dq"])
            ctrl = np.asarray(
                [reference["ctrl_by_actuator"][name] for name in actuator_names],
                dtype=np.float32,
            )
        else:
            source_pre = reference["pre_state"]
            for name in addresses:
                source_address = name_map[name]
                qpos[qpos_by_name[name]] = np.float32(source_pre["qpos"][source_address["qpos"]])
                qvel[dof_by_name[name]] = np.float32(source_pre["qvel"][source_address["dof"]])
            ctrl = np.asarray(source_pre["ctrl"], dtype=np.float32)
        if ctrl.shape != (len(actuator_names),):
            raise ValueError("frozen USD source-control vector has an unexpected shape")
        solver.write_qpos(qpos)
        solver.write_qvel(qvel)
        solver.write_ctrl(ctrl)
        solver.synchronize_kinematic_state()
        tendon_pre = _finite(solver.read_tendon_length(), f"{fmt} tendon pre length")
        tendon_rate_pre = _finite(solver.read_tendon_velocity(), f"{fmt} tendon pre rate")
        _step_counter(counter_path, plan, completed=False)
        solver.step()
        _step_counter(counter_path, plan, completed=True)
        force = _finite(solver.read_actuator_force(), f"{fmt} actuator force")
        qfrc_act = _finite(solver.read_qfrc_actuator(), f"{fmt} actuator generalized force")
        qfrc_constraint = _finite(solver.read_qfrc_constraint(), f"{fmt} constraint generalized force")
        post_qpos = _finite(solver.read_qpos(), f"{fmt} post qpos")
        post_qvel = _finite(solver.read_qvel(), f"{fmt} post qvel")
        tendon_post = _finite(solver.read_tendon_length(), f"{fmt} tendon post length")
        tendon_rate_post = _finite(solver.read_tendon_velocity(), f"{fmt} tendon post rate")
        contacts = solver.query_diagnostics(__import__(
            "runtime.diagnostics", fromlist=["DiagnosticsConfig"],
        ).DiagnosticsConfig(contacts=True)).contacts
        contact_snapshot = _contact_snapshot(contacts, model)
        observations.append({
            "scenario": scenario,
            "same_as_usd_reference_input": True,
            "pre_state_by_joint": {
                name: {
                    "q": float(qpos[qpos_by_name[name]]),
                    "dq": float(qvel[dof_by_name[name]]),
                } for name in addresses
            },
            "ctrl_by_actuator": {name: float(ctrl[i]) for i, name in enumerate(actuator_names)},
            "tendon_length_pre_m": tendon_pre,
            "tendon_velocity_pre_m_s": tendon_rate_pre,
            "actuator_force_after_step_N": dict(zip(actuator_names, force)),
            "joint_post_by_name": {
                name: {
                    "q": float(post_qpos[qpos_by_name[name]]),
                    "dq": float(post_qvel[dof_by_name[name]]),
                    "qfrc_actuator_N": float(qfrc_act[dof_by_name[name]]),
                    "qfrc_constraint_N": float(qfrc_constraint[dof_by_name[name]]),
                } for name in addresses
            },
            "tendon_length_post_m": tendon_post,
            "tendon_velocity_post_m_s": tendon_rate_post,
            "body_contact_count_after_step": contact_snapshot["body_contact_count"],
            "body_contact_pairs_after_step": contact_snapshot["body_pairs"],
            "body_contact_active_slot_count_after_step": contact_snapshot["active_slot_count"],
        })
    del solver
    return {
        "format": fmt,
        "model": _model_receipt(fmt, imported, articulation, model, joint_data, addresses),
        "observations": observations,
        "source_body_contact_mask_override": source_contact_override,
        "runtime_joint_passive_override_to_usd": passive_override,
        "runtime_joint_passive_parameters": runtime_passives,
    }


def run(plan_path: Path, sidecar: Path, receipt_path: Path, counter_path: Path) -> dict:
    plan, plan_hash = _verify(plan_path.resolve(strict=True), sidecar.resolve(strict=True))
    source = plan["source"]
    output = plan["output"]
    counter_path = counter_path.resolve()
    _atomic_json(counter_path, {
        "schema_version": "f05-dg02-step-counter-v1",
        "run_id": plan["run_id"],
        "attempted_physics_steps": 0,
        "completed_physics_steps": 0,
        "physics_dt_s": 0.002,
    })
    receipt = {
        "schema_version": "f05-dg02-mjcf-usd-source-pair-receipt-v1",
        "run_id": plan["run_id"],
        "plan_path": str(plan_path.resolve()),
        "plan_sha256": plan_hash,
        "classification": plan["classification"],
        "source": {
            "original_mjcf_sha256": _sha(Path(source["mjcf_source"]["path"])),
            "mjcf_task_scene_variant_sha256": _sha(Path(source["mjcf_task_scene_variant"]["path"])),
            "usd_stage_sha256": _sha(Path(source["usd_stage"]["path"])),
        },
        "physics_steps_attempted": 0,
        "physics_steps_completed": 0,
        "backend_initialized": False,
        "result": "FAIL_SOURCE_PAIR_PROBE",
        "errors": [],
    }
    runtime_initialized = False
    try:
        sys.meta_path.insert(0, _ForbiddenImportFinder())
        reference_receipt = json.loads(
            Path(source["usd_reference_probe_receipt"]["path"]).read_text(encoding="utf-8")
        )
        if reference_receipt.get("result") != "PASS_V2_PUBLIC_CONSUMERS":
            raise ValueError("bound USD source-consumer reference did not pass")
        reference_consumer = reference_receipt["source_consumer"]
        if reference_consumer.get("source_stage_sha256") != receipt["source"]["usd_stage_sha256"]:
            raise ValueError("bound USD reference does not use the frozen DG02 USD stage")
        if reference_consumer.get("delivery_identity_sha256") != source["delivery_identity_sha256"]:
            raise ValueError("bound USD reference has a different source delivery identity")

        usd_bundle = _public_model(source, "usd", plan["run_id"] + "-usd")
        mjcf_bundle = _public_model(source, "mjcf", plan["run_id"] + "-mjcf")
        usd_summary = _model_receipt("usd", *usd_bundle)
        mjcf_summary = _model_receipt("mjcf", *mjcf_bundle)
        if usd_summary["public_model_counts"]["n_actuators"] != 8 or mjcf_summary["public_model_counts"]["n_actuators"] != 8:
            raise ValueError("paired public models did not preserve all eight source actuators")
        if usd_summary["public_model_counts"]["n_tendons"] != 1 or mjcf_summary["public_model_counts"]["n_tendons"] != 1:
            raise ValueError("paired public models did not preserve the source tendon")
        if usd_summary["public_model_counts"]["n_equalities"] != 1 or mjcf_summary["public_model_counts"]["n_equalities"] != 1:
            raise ValueError("paired public models did not preserve the source equality")

        import geophys
        import taichi as ti
        geophys.init_taichi(arch=ti.cpu, offline_cache=False)
        runtime_initialized = True
        if ti.cfg.arch != ti.cpu:
            raise RuntimeError(f"expected CPU backend, got {ti.cfg.arch}")
        receipt["backend_initialized"] = True
        stimuli = dict(reference_consumer)
        stimuli["observations"] = [
            *(reference_consumer["observations"] if plan.get("include_usd_reference_scenarios", True) else []),
            *plan.get("additional_scenarios", []),
        ]
        usd_pair = _run_representation("usd", usd_bundle, stimuli, plan, counter_path)
        mjcf_pair = _run_representation(
            "mjcf", mjcf_bundle, stimuli, plan, counter_path,
            reference_joint_data=usd_bundle[3],
        )

        differences = []
        for usd_obs, mjcf_obs in zip(usd_pair["observations"], mjcf_pair["observations"]):
            if usd_obs["scenario"] != mjcf_obs["scenario"]:
                raise ValueError("paired source scenario ordering differs")
            actuator_delta = {
                name: abs(usd_obs["actuator_force_after_step_N"][name]
                          - mjcf_obs["actuator_force_after_step_N"][name])
                for name in usd_obs["actuator_force_after_step_N"]
            }
            joint_delta = {}
            for name in usd_obs["joint_post_by_name"]:
                a, b = usd_obs["joint_post_by_name"][name], mjcf_obs["joint_post_by_name"][name]
                joint_delta[name] = {
                    field: abs(a[field] - b[field])
                    for field in ("q", "dq", "qfrc_actuator_N", "qfrc_constraint_N")
                }
            differences.append({
                "scenario": usd_obs["scenario"],
                "actuator_force_abs_delta_N": actuator_delta,
                "joint_state_and_force_abs_delta": joint_delta,
                "tendon_length_abs_delta_m": abs(usd_obs["tendon_length_pre_m"][0] - mjcf_obs["tendon_length_pre_m"][0]),
                "tendon_rate_abs_delta_m_s": abs(usd_obs["tendon_velocity_pre_m_s"][0] - mjcf_obs["tendon_velocity_pre_m_s"][0]),
                "body_contact_counts": {
                    "usd": usd_obs["body_contact_count_after_step"],
                    "mjcf": mjcf_obs["body_contact_count_after_step"],
                },
                "body_contact_pairs": {
                    "usd": sorted(
                        (row["body_a_key"], row["body_b_key"])
                        for row in usd_obs["body_contact_pairs_after_step"]
                    ),
                    "mjcf": sorted(
                        (row["body_a_key"], row["body_b_key"])
                        for row in mjcf_obs["body_contact_pairs_after_step"]
                    ),
                    "body_pair_multiset_match": sorted(
                        (row["body_a_key"], row["body_b_key"])
                        for row in usd_obs["body_contact_pairs_after_step"]
                    ) == sorted(
                        (row["body_a_key"], row["body_b_key"])
                        for row in mjcf_obs["body_contact_pairs_after_step"]
                    ),
                },
            })
        reference_descriptors_match = (
            usd_summary["actuators"] == mjcf_summary["actuators"]
            and usd_summary["equalities"] == mjcf_summary["equalities"]
            and usd_summary["tendons"] == mjcf_summary["tendons"]
        )
        def without_generated_equality_name(rows):
            return [{key: value for key, value in row.items() if key != "name"} for row in rows]

        source_law_descriptors_match = (
            usd_summary["actuators"] == mjcf_summary["actuators"]
            and without_generated_equality_name(usd_summary["equalities"])
                == without_generated_equality_name(mjcf_summary["equalities"])
            and usd_summary["tendons"] == mjcf_summary["tendons"]
        )
        receipt.update({
            "provider": "GeoPhys",
            "backend": "CPU / taichi-forge",
            "integrator": "implicitfast",
            "dt_s": 0.002,
            "gravity_m_s2": [0.0, 0.0, 0.0],
            "contact_mode": {
                "source_body_contacts_enabled": bool(plan.get("source_body_contacts_enabled", True)),
                "diagnostic_variant": plan.get("diagnostic_variant", "source_contact_enabled_public_source_pair"),
                "source_body_contact_mask_override_applied_to_runtime_model": {
                    "usd": usd_pair["source_body_contact_mask_override"],
                    "mjcf": mjcf_pair["source_body_contact_mask_override"],
                },
                "mjcf_joint_passive_override_to_usd_applied_to_runtime_model": mjcf_pair["runtime_joint_passive_override_to_usd"],
                "implicit_ground_contact_enabled": False,
                "domain_boundary_contact_enabled": False,
                "ccd_enabled": False,
                "broadphase": "n2",
            },
            "task_scene_match": {
                "support_box_m": [0.35, 0.35, 0.05],
                "support_center_m": [1.0, 0.5, 0.45],
                "free_cube_edge_m": 0.06,
                "free_cube_center_m": [1.0, 0.5, 0.9],
                "free_cube_mass_kg": 0.1,
                "basis": "frozen F04Scene prims in source USD; MJCF counterpart is a separately hashed diagnostic composition",
            },
            "frozen_usd_reference_identity": {
                "path": source["usd_reference_probe_receipt"]["path"],
                "sha256": source["usd_reference_probe_receipt"]["sha256"],
            },
            "public_host_model_descriptor_match": reference_descriptors_match,
            "source_law_descriptor_match_ignoring_generated_equality_name": source_law_descriptors_match,
            "host_model_comparison_alignment": {
                "body_objects": "keyed by object_key",
                "body_inertia": "principal moments compared after sorting; raw principal basis vectors remain preserved in models",
                "generated_equality_name": "reported as a raw metadata difference; original MJCF equality has no authored name",
            },
            "models": {"usd": usd_pair["model"], "mjcf": mjcf_pair["model"]},
            "public_host_model_field_differences": _diff_paths(
                usd_pair["model"], mjcf_pair["model"], "model",
            ),
            "paired_fixed_control_observations": {
                "stimuli_source": "exact named Panda q/dq and actuator ctrl vectors from the frozen DG02 USD public-consumer probe",
                "usd": usd_pair["observations"],
                "mjcf": mjcf_pair["observations"],
                "absolute_differences": differences,
            },
            "physics_steps_attempted": int(json.loads(counter_path.read_text())["attempted_physics_steps"]),
            "physics_steps_completed": int(json.loads(counter_path.read_text())["completed_physics_steps"]),
            "errors": [],
            "result": "PASS_MJCF_USD_PUBLIC_SOURCE_PAIR_PROBE",
            "interpretation": "Probe completion is not an equivalence verdict; body objects are aligned by key, principal inertia values by basis-invariant sorting, and contact pairs plus fixed-input deltas are retained for review against the independent source-law oracle.",
            "claim_limit": "Four-step fixed-state/fixed-control GeoPhys public-consumer diagnostic only; does not exercise online R3, formal Core, long-horizon stability, or qualify representation equivalence.",
        })
        expected_steps = int(plan["oracle"]["expected_step_count"])
        if receipt["physics_steps_attempted"] != expected_steps or receipt["physics_steps_completed"] != expected_steps:
            raise ValueError("paired source probe did not consume exactly its frozen step reservation")
    except BaseException as exc:
        receipt["errors"].append(f"{type(exc).__name__}: {exc}")
        receipt["traceback"] = traceback.format_exc()
        receipt["result"] = "FAIL_MJCF_USD_PUBLIC_SOURCE_PAIR_PROBE"
    finally:
        counter = json.loads(counter_path.read_text(encoding="utf-8"))
        receipt["physics_steps_attempted"] = int(counter["attempted_physics_steps"])
        receipt["physics_steps_completed"] = int(counter["completed_physics_steps"])
        if runtime_initialized:
            try:
                import taichi as ti
                ti.reset()
            except BaseException as exc:
                receipt["errors"].append(f"Taichi cleanup: {type(exc).__name__}: {exc}")
                receipt["result"] = "FAIL_MJCF_USD_PUBLIC_SOURCE_PAIR_PROBE"
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
    return 0 if result["result"] == "PASS_MJCF_USD_PUBLIC_SOURCE_PAIR_PROBE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
