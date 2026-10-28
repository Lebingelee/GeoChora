"""Bounded R03b static S1 and native fixed-tree S2 probe."""
from __future__ import annotations

import argparse
import builtins
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import traceback
import xml.etree.ElementTree as ET


def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(path)


def _expect_rejection(label, callback, results):
    try:
        callback()
    except Exception as exc:
        results.append({"case": label, "status": "REJECTED_BEFORE_NATIVE", "error": f"{type(exc).__name__}: {exc}"})
        return
    raise AssertionError(f"S1 negative case was admitted: {label}")


def run_s1(output_dir: Path):
    native_attempts = []
    original_import = builtins.__import__

    def reject_native_import(name, *args, **kwargs):
        if name == "mujoco" or name.startswith("mujoco."):
            native_attempts.append(name)
            raise AssertionError("S1 attempted to import MuJoCo before native authorization")
        return original_import(name, *args, **kwargs)

    builtins.__import__ = reject_native_import
    try:
        from dataclasses import replace as dataclass_replace
        from task_env.artifacts import (
            ExecutionSpec, FixedAttachmentPlanV1, FrameReference, LogicalAssemblyV1,
            LogicalAssemblyScenePinV1, PoseWorld, RobotInstance, decode_logical_assembly,
            resolve_logical_assembly,
        )
        from task_env.assembly.assets import _source_closure_digest
        from task_env.assembly.fixed_attachment import (
            lower_fixed_attachment_sources, validate_fixed_attachment_scene,
        )
        from task_env.assembly.logical_source import project_logical_assembly_source
        from task_env.assembly.source import TaskSceneSource
        from task_env.runtime.sessions.common import _SessionValues
        from task_env.runtime.sessions import api
        from task_env.runtime.sessions.source import source_asset_bytes
        from task_env.tasks.position_candidate.fixed_attachment_candidate import (
            ARM_ENTITY, ARM_XML, HAND_ENTITY, HAND_XML, LICENSE, MENAGERIE_ROOT,
            build_fixed_attachment_candidate,
        )

        candidate = build_fixed_attachment_candidate()
        assembly = decode_logical_assembly(candidate.assembly.to_mapping())
        resolved = resolve_logical_assembly(assembly, candidate.scene, ())
        projection = project_logical_assembly_source(assembly, candidate.scene, ())
        plan_result = validate_fixed_attachment_scene(candidate.attachment_plan, assembly, candidate.scene)
        if (resolved.root_logical_content_sha256 != candidate.attachment_plan.logical_content_sha256
                or [item.member.entity_id for item in resolved.leaves] != [ARM_ENTITY, HAND_ENTITY]
                or [item.entity.entity_id for item in projection.entities] != [ARM_ENTITY, HAND_ENTITY]):
            raise AssertionError("R01c codec/resolve/source projection did not preserve the two exact owners")
        # The pinned standalone Menagerie files omit an explicit timestep;
        # R03b admits that exact 3.8.1 default only when the compiled model is
        # later checked against the frozen 2 ms TaskArtifact timebase.
        values = object.__new__(_SessionValues)
        values._initialize_values(candidate.artifact, candidate.runtime_source, "mujoco")

        execution = ExecutionSpec("mujoco", "p1_2_scalar_cpu_v0", "none", "cpu", 31, "strict")
        materialized = []
        old_materialize = api._materialize_admitted
        api._materialize_admitted = lambda artifact, selected, source: materialized.append(
            (artifact, selected, source)
        ) or "S1_NATIVE_IO_STUB"
        try:
            result = api.materialize(candidate.artifact, execution, source=candidate.runtime_source)
            if result != "S1_NATIVE_IO_STUB" or len(materialized) != 1:
                raise AssertionError("S1 did not reach the production materialization admission boundary")
        finally:
            api._materialize_admitted = old_materialize

        negatives = []
        unplanned_source = dataclass_replace(
            candidate.runtime_source, fixed_attachment_plan=None,
            fixed_attachment_assembly=None, fixed_attachment_sources=None,
        )
        _expect_rejection("implicit timestep outside fixed Attachment route", lambda: object.__new__(
            _SessionValues
        )._initialize_values(candidate.artifact, unplanned_source, "mujoco"), negatives)
        wrong_timestep_root = ET.fromstring(candidate.runtime_source.scene_source.xml)
        wrong_timestep_root.find("option").set("timestep", "0.003")
        wrong_timestep_source = TaskSceneSource(
            ET.tostring(wrong_timestep_root, encoding="unicode"),
            candidate.runtime_source.scene_source.base_dir,
            candidate.runtime_source.scene_source.source_id,
        )
        _expect_rejection("explicit timestep mismatch on fixed Attachment route", lambda: object.__new__(
            _SessionValues
        )._initialize_values(
            candidate.artifact,
            dataclass_replace(candidate.runtime_source, scene_source=wrong_timestep_source),
            "mujoco",
        ), negatives)
        _expect_rejection("wrong Scene pin", lambda: validate_fixed_attachment_scene(
            dataclass_replace(candidate.attachment_plan,
                scene_pin=LogicalAssemblyScenePinV1(
                    "logical-assembly-scene-pin-v1", candidate.scene.scene_id,
                    candidate.scene.schema_version, "0" * 64,
                )), assembly, candidate.scene,
        ), negatives)
        wrong_assembly = dataclass_replace(candidate.assembly, assembly_id="panda-arm-hand-wrong")
        _expect_rejection("wrong Assembly identity at materialization", lambda: api.materialize(
            candidate.artifact, execution, source=dataclass_replace(
                candidate.runtime_source, fixed_attachment_assembly=wrong_assembly,
            ),
        ), negatives)
        wrong_child = TaskSceneSource(
            candidate.runtime_source.fixed_attachment_sources[HAND_ENTITY].xml + "\n",
            MENAGERIE_ROOT,
            candidate.runtime_source.fixed_attachment_sources[HAND_ENTITY].source_id,
        )
        _expect_rejection("wrong source bytes", lambda: api.materialize(
            candidate.artifact, execution, source=dataclass_replace(
                candidate.runtime_source,
                fixed_attachment_sources={
                    ARM_ENTITY: candidate.runtime_source.fixed_attachment_sources[ARM_ENTITY],
                    HAND_ENTITY: wrong_child,
                },
            ),
        ), negatives)
        _expect_rejection("wrong mount Frame", lambda: dataclass_replace(
            candidate.attachment_plan,
            parent_mount=FrameReference(ARM_ENTITY, "link7"),
        ), negatives)
        inverse_transform = PoseWorld((0.0, 0.0, 0.0), (0.9238795391929064, 0.0, 0.0, -0.38268341623423263))
        _expect_rejection("wrong T direction", lambda: api.materialize(
            candidate.artifact, execution, source=dataclass_replace(
                candidate.runtime_source,
                fixed_attachment_plan=dataclass_replace(
                    candidate.attachment_plan, parent_site_from_child_root=inverse_transform,
                ),
            ),
        ), negatives)
        _expect_rejection("duplicate child / cycle", lambda: dataclass_replace(
            candidate.attachment_plan, child_entity_id=ARM_ENTITY,
        ), negatives)
        extra_fields = candidate.attachment_plan.to_mapping()
        extra_fields["parent_edges"] = ["arm->hand", "other->hand"]
        _expect_rejection("multiple parent edge shape", lambda: FixedAttachmentPlanV1.from_mapping(extra_fields), negatives)
        _expect_rejection("extra independent root", lambda: dataclass_replace(
            candidate.scene,
            robots=candidate.scene.robots + (
                RobotInstance("robot-instance-v1", "unadmitted-root", (FrameReference("unadmitted-root", "root"),)),
            ),
        ), negatives)
        colliding_joints = dict(candidate.attachment_plan.native_joint_names)
        colliding_joints[f"{HAND_ENTITY}/finger_joint1"] = "joint1"
        _expect_rejection("native resource name collision", lambda: dataclass_replace(
            candidate.attachment_plan, native_joint_names=colliding_joints,
        ), negatives)
        swapped_joints = dict(candidate.attachment_plan.native_joint_names)
        swapped_joints[f"{ARM_ENTITY}/joint1"], swapped_joints[f"{ARM_ENTITY}/joint2"] = (
            swapped_joints[f"{ARM_ENTITY}/joint2"], swapped_joints[f"{ARM_ENTITY}/joint1"],
        )
        _expect_rejection("wrong native Joint order", lambda: lower_fixed_attachment_sources(
            parent_source=candidate.runtime_source.scene_source,
            source_by_entity=candidate.runtime_source.fixed_attachment_sources,
            scene=candidate.scene,
            plan=dataclass_replace(candidate.attachment_plan, native_joint_names=swapped_joints),
            assembly=assembly,
        ), negatives)
        missing_joints = dict(candidate.attachment_plan.native_joint_names)
        missing_joints.pop(f"{HAND_ENTITY}/finger_joint2")
        _expect_rejection("missing canonical/native inverse mapping", lambda: validate_fixed_attachment_scene(
            dataclass_replace(candidate.attachment_plan, native_joint_names=missing_joints),
            assembly, candidate.scene,
        ), negatives)
        _expect_rejection("missing tendon mapping", lambda: validate_fixed_attachment_scene(
            dataclass_replace(candidate.attachment_plan, native_tendon_names={}), assembly, candidate.scene,
        ), negatives)
        _expect_rejection("collision policy conflict", lambda: dataclass_replace(
            candidate.attachment_plan, collision_policy="disabled",
        ), negatives)
        _expect_rejection("external asset path escape", lambda: source_asset_bytes(
            MENAGERIE_ROOT,
            '<mujoco><compiler meshdir="assets"/><asset><mesh file="../../escape.obj"/></asset></mujoco>',
        ), negatives)

        def reject_modified_child(label, mutation):
            root = ET.fromstring(HAND_XML.read_text())
            mutation(root)
            xml = ET.tostring(root, encoding="unicode")
            child_sha = hashlib.sha256(xml.encode("utf-8")).hexdigest()
            child_source = TaskSceneSource(
                xml, MENAGERIE_ROOT,
                f"fixed-attachment-source-v1:{HAND_ENTITY}:{child_sha}",
            )
            closure = {
                "parent/scene.xml": ARM_XML.read_bytes(),
                "child/scene.xml": xml.encode("utf-8"),
                "license/LICENSE": LICENSE.read_bytes(),
            }
            closure.update({
                f"parent/{path}": content
                for path, content in source_asset_bytes(MENAGERIE_ROOT, ARM_XML.read_text()).items()
            })
            closure.update({
                f"child/{path}": content
                for path, content in source_asset_bytes(MENAGERIE_ROOT, xml).items()
            })
            modified_plan = dataclass_replace(
                candidate.attachment_plan,
                child_source_sha256=child_sha,
                source_closure_sha256=_source_closure_digest(closure),
            )
            modified_sources = {
                ARM_ENTITY: candidate.runtime_source.fixed_attachment_sources[ARM_ENTITY],
                HAND_ENTITY: child_source,
            }
            _expect_rejection(label, lambda: lower_fixed_attachment_sources(
                parent_source=modified_sources[ARM_ENTITY], source_by_entity=modified_sources,
                scene=candidate.scene, plan=modified_plan, assembly=assembly,
            ), negatives)

        reject_modified_child("omitted split tendon", lambda root: root.find("./tendon").clear())
        reject_modified_child("omitted finger equality", lambda root: root.find("./equality").clear())
        reject_modified_child("omitted Hand actuator", lambda root: root.find("./actuator").clear())
        if native_attempts:
            raise AssertionError(f"S1 attempted native import: {native_attempts}")
        if len(materialized) != 1:
            raise AssertionError("negative S1 cases crossed into native materialization")
        result = {
            "status": "PASS",
            "provider_free": True,
            "native_import_attempts": native_attempts,
            "native_compile_attempts": 0,
            "native_step_calls": 0,
            "actual_candidate_path": "task_env/tasks/position_candidate/fixed_attachment_candidate.py",
            "materialization_owner": "task_env/runtime/sessions/api.py::materialize",
            "codec_resolve_projection": {
                "assembly_sha256": assembly.identity_hash,
                "resolved_leaf_ids": [item.member.entity_id for item in resolved.leaves],
                "projection_sha256": projection.identity_sha256,
            },
            "static_plan_validation": {
                "scene_identity_sha256": plan_result["scene_identity_sha256"],
                "assembly_identity_sha256": plan_result["assembly_identity_sha256"],
                "native_frame_count": plan_result["native_frame_count"],
                "native_joint_count": plan_result["native_joint_count"],
                "native_actuator_count": plan_result["native_actuator_count"],
                "native_tendon_count": plan_result["native_tendon_count"],
            },
            "admission_reached_production_boundary": True,
            "rejections": negatives,
        }
        _write_json(output_dir / "s1_evidence.json", result)
        return result
    finally:
        builtins.__import__ = original_import


def _quat_multiply(left, right):
    w1, x1, y1, z1 = left
    w2, x2, y2, z2 = right
    return (
        w1*w2 - x1*x2 - y1*y2 - z1*z2,
        w1*x2 + x1*w2 + y1*z2 - z1*y2,
        w1*y2 - x1*z2 + y1*w2 + z1*x2,
        w1*z2 + x1*y2 - y1*x2 + z1*w2,
    )


def _rotate(q, vector):
    w, x, y, z = q
    vx, vy, vz = vector
    qv = (x, y, z)
    cross1 = (qv[1]*vz - qv[2]*vy, qv[2]*vx - qv[0]*vz, qv[0]*vy - qv[1]*vx)
    cross2 = (qv[1]*cross1[2] - qv[2]*cross1[1],
              qv[2]*cross1[0] - qv[0]*cross1[2],
              qv[0]*cross1[1] - qv[1]*cross1[0])
    return tuple(vector[i] + 2.0 * (w * cross1[i] + cross2[i]) for i in range(3))


def _compose(parent, child):
    rotated = _rotate(parent.quaternion_wxyz, child.position)
    return (
        tuple(parent.position[index] + rotated[index] for index in range(3)),
        _quat_multiply(parent.quaternion_wxyz, child.quaternion_wxyz),
    )


def _position_error(left, right):
    return math.sqrt(sum((left[index] - right[index]) ** 2 for index in range(3)))


def _rotation_error(left, right):
    dot = abs(sum(left[index] * right[index] for index in range(4)))
    return 2.0 * math.acos(min(1.0, max(-1.0, dot)))


def _relative_position(root_pose, child_pose):
    inverse_q = tuple((root_pose.quaternion_wxyz[0],) + tuple(-value for value in root_pose.quaternion_wxyz[1:]))
    delta = tuple(child_pose.position[index] - root_pose.position[index] for index in range(3))
    return _rotate(inverse_q, delta)


def _rss_bytes():
    try:
        with open("/proc/self/status", encoding="utf-8") as status:
            for line in status:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        return None
    return None


def _state_finite(state):
    values = [state.simulation_time]
    values.extend(state.joint_position.values())
    values.extend(state.joint_velocity.values())
    for value in state.pose_world.values():
        values.extend(value.position)
        values.extend(value.quaternion_wxyz)
    return all(math.isfinite(float(value)) for value in values)


def run_native_s2(output_dir: Path):
    from task_env.artifacts import ExecutionSpec
    from task_env.runtime.sessions import api
    from task_env.tasks.position_candidate.fixed_attachment_candidate import (
        ARM_ENTITY, HAND_ENTITY, build_fixed_attachment_candidate,
    )

    candidate = build_fixed_attachment_candidate()
    execution = ExecutionSpec("mujoco", "p1_2_scalar_cpu_v0", "none", "cpu", 31, "strict")
    evidence = {
        "status": "RUNNING",
        "task_id": "PHASE-II-01-R03B",
        "attempt": "001",
        "candidate": {
            "scene_identity_sha256": candidate.scene.identity_hash,
            "task_artifact_sha256": candidate.artifact.identity_hash,
            "assembly_identity_sha256": candidate.assembly.identity_hash,
            "attachment_plan_sha256": candidate.attachment_plan.identity_hash,
            "source_closure_sha256": candidate.runtime_source.source_closure_digest,
            "provider": "mujoco",
            "backend": "cpu",
        },
        "budgets": {
            "process_starts": 1, "materializations": 0, "resets": 0,
            "mj_forward": 0, "outer_intervals": 0, "mj_step": 0,
            "simulated_seconds": 0.0,
        },
        "trials": [],
        "failure": None,
        "failure_traceback": None,
        "rss_samples": [],
    }
    latest = {"status": "process_started", "mj_step_success_count": 0}
    _write_json(output_dir / "s2_checkpoint.json", latest)
    sessions = []
    reset_signatures = []
    try:
        for trial_index in (1, 2):
            trial = {
                "trial": trial_index,
                "status": "RUNNING",
                "provider_materialization_id": None,
                "episode_id": None,
                "reset_sample_id": candidate.reset_plan.reset_sample.sample_id,
                "receipt": None,
                "reset": None,
                "motion_samples": [],
                "mount_error_max": {"position_m": 0.0, "rotation_rad": 0.0},
                "warning_count_max": 0,
                "close_evidence": None,
                "oracle": None,
            }
            evidence["trials"].append(trial)
            evidence["budgets"]["materializations"] += 1
            session = api.materialize(candidate.artifact, execution, source=candidate.runtime_source)
            sessions.append(session)
            receipt = session.fixed_attachment_receipt
            trial["receipt"] = receipt
            trial["provider_materialization_id"] = session.provider_materialization_id
            if (receipt["provider_materialization_id"] != session.provider_materialization_id
                    or receipt["provider"] != "mujoco" or receipt["backend"] != "cpu"
                    or receipt["attachment_plan_sha256"] != candidate.attachment_plan.identity_hash):
                raise AssertionError("model-bound Attachment receipt does not bind this Core RuntimeSession")
            receipt_identity = receipt["receipt_identity_sha256"]
            evidence["rss_samples"].append({
                "trial": trial_index, "boundary": "after_materialize_before_reset",
                "rss_bytes": _rss_bytes(),
            })

            evidence["budgets"]["resets"] += 1
            realized = session.reset_plan(candidate.reset_plan)
            reset_state = realized.measured_state
            diagnostic = session.fixed_attachment_diagnostics
            evidence["rss_samples"].append({
                "trial": trial_index, "boundary": "after_reset",
                "rss_bytes": _rss_bytes(),
            })
            trial["episode_id"] = diagnostic["episode_id"]
            trial["reset"] = {
                "plan_identity_sha256": candidate.reset_plan.identity_hash,
                "plan_evidence": session.reset_plan_evidence,
                "realized": {
                    "joint_position": dict(reset_state.joint_position),
                    "joint_velocity": dict(reset_state.joint_velocity),
                    "pose_world": {
                        name: pose.to_mapping() for name, pose in reset_state.pose_world.items()
                    },
                    "simulation_time_s": reset_state.simulation_time,
                    "ctrl": diagnostic["ctrl"],
                    "native_step_count": diagnostic["native_step_count"],
                    "forward_call_count": diagnostic["forward_call_count"],
                },
            }
            latest = {
                "status": "reset_checkpoint",
                "trial": trial_index,
                "episode_id": diagnostic["episode_id"],
                "provider_materialization_id": diagnostic["provider_materialization_id"],
                "mj_step_success_count": evidence["budgets"]["mj_step"],
                "forward_call_count": evidence["budgets"]["mj_forward"] + diagnostic["forward_call_count"],
                "reset_state": trial["reset"]["realized"],
            }
            _write_json(output_dir / "s2_checkpoint.json", latest)
            if diagnostic["native_step_count"] != 0 or diagnostic["native_time_s"] != 0.0:
                raise AssertionError("ResetPlan reset unexpectedly stepped or advanced native time")
            if abs(float(reset_state.simulation_time)) > 1e-12 or reset_state.control_step != 0:
                raise AssertionError("ResetPlan realized a nonzero initial clock")
            if abs(diagnostic["ctrl"][receipt["native_actuator_mappings"][f"{HAND_ENTITY}/actuator8"]["ctrl_slot"]] - 242.25) > 1e-12:
                raise AssertionError("ResetPlan did not set the source Hand 0.076m opening ctrl 242.25")
            reset_signatures.append({
                "joint_position": dict(reset_state.joint_position),
                "joint_velocity": dict(reset_state.joint_velocity),
                "ctrl": diagnostic["ctrl"],
                "simulation_time_s": float(reset_state.simulation_time),
            })

            start_root = reset_state.pose_world[f"{HAND_ENTITY}/hand"]
            hand_start_positions = {
                name: _relative_position(
                    start_root, reset_state.pose_world[f"{HAND_ENTITY}/{name}"],
                ) for name in ("left_finger", "right_finger")
            }
            mount_position_max = 0.0
            mount_rotation_max = 0.0
            arm_peak = 0.0
            hand_root_rotation_peak = 0.0
            close_openings = []
            open_openings = []
            finger_displacements = {"left_finger": 0.0, "right_finger": 0.0}
            max_warning_count = sum(diagnostic["warning_counts"])
            if not _state_finite(reset_state):
                raise AssertionError("ResetPlan state contains a non-finite value")

            def consume_boundary(state, phase, interval_index, command):
                nonlocal mount_position_max, mount_rotation_max, arm_peak
                nonlocal hand_root_rotation_peak, max_warning_count
                evidence["budgets"]["outer_intervals"] += 1
                local_outer_interval = len(trial["motion_samples"]) + 1
                expected_time = local_outer_interval * 0.01
                runtime = session.fixed_attachment_diagnostics
                evidence["budgets"]["mj_step"] = sum(
                    item.get("close_evidence", {}).get("native_step_count", 0)
                    for item in evidence["trials"] if item.get("close_evidence")
                ) + runtime["native_step_count"]
                evidence["budgets"]["mj_forward"] = sum(
                    item.get("close_evidence", {}).get("forward_call_count", 0)
                    for item in evidence["trials"] if item.get("close_evidence")
                ) + runtime["forward_call_count"]
                evidence["budgets"]["simulated_seconds"] = evidence["budgets"]["mj_step"] * 0.002
                if state.control_step != local_outer_interval:
                    raise AssertionError("RuntimeSession boundary step is detached from the current Core episode")
                if not _state_finite(state):
                    raise AssertionError("RuntimeSession state contains a non-finite value")
                if abs(float(state.simulation_time) - expected_time) > 1e-12:
                    raise AssertionError("RuntimeSession public clock differs from the 0.01s outer boundary")
                if abs(runtime["native_time_s"] - expected_time) > 1e-12:
                    raise AssertionError("MuJoCo native clock differs from the 0.01s outer boundary")
                parent_site = state.pose_world[f"{ARM_ENTITY}/attachment_site"]
                child_root = state.pose_world[f"{HAND_ENTITY}/hand"]
                expected_position, expected_quaternion = _compose(
                    parent_site, candidate.attachment_plan.parent_site_from_child_root,
                )
                position_error = _position_error(child_root.position, expected_position)
                rotation_error = _rotation_error(child_root.quaternion_wxyz, expected_quaternion)
                mount_position_max = max(mount_position_max, position_error)
                mount_rotation_max = max(mount_rotation_max, rotation_error)
                joint_values = dict(state.joint_position)
                for canonical, mapping in receipt["native_joint_mappings"].items():
                    low, high = mapping["range"]
                    if not low - 1e-6 <= joint_values[canonical] <= high + 1e-6:
                        raise AssertionError(f"native Joint exceeded its source limits: {canonical}")
                for canonical, mapping in receipt["native_actuator_mappings"].items():
                    low, high = mapping["ctrl_range"]
                    ctrl = runtime["ctrl"][mapping["ctrl_slot"]]
                    if not math.isfinite(ctrl) or not low - 1e-12 <= ctrl <= high + 1e-12:
                        raise AssertionError(f"native actuator ctrl exceeded its source range: {canonical}")
                fingers = (joint_values[f"{HAND_ENTITY}/finger_joint1"],
                           joint_values[f"{HAND_ENTITY}/finger_joint2"])
                finger_mismatch = abs(fingers[0] - fingers[1])
                opening = sum(fingers)
                if phase == "hand_close":
                    close_openings.append(opening)
                elif phase == "hand_open":
                    open_openings.append(opening)
                relative_fingers = {
                    name: _relative_position(child_root, state.pose_world[f"{HAND_ENTITY}/{name}"])
                    for name in ("left_finger", "right_finger")
                }
                if phase.startswith("hand_"):
                    for name in finger_displacements:
                        finger_displacements[name] = max(
                            finger_displacements[name],
                            _position_error(relative_fingers[name], hand_start_positions[name]),
                        )
                q1 = joint_values[f"{ARM_ENTITY}/joint1"]
                arm_peak = max(arm_peak, abs(q1))
                hand_root_rotation_peak = max(
                    hand_root_rotation_peak,
                    _rotation_error(start_root.quaternion_wxyz, child_root.quaternion_wxyz),
                )
                max_warning_count = max(max_warning_count, sum(runtime["warning_counts"]))
                point = {
                    "phase": phase,
                    "phase_interval": interval_index,
                    "control_step": int(state.control_step),
                    "state_revision": int(runtime["state_revision"]),
                    "simulation_time_s": float(state.simulation_time),
                    "command": command,
                    "joint_position": joint_values,
                    "joint_velocity": dict(state.joint_velocity),
                    "pose_world": {
                        name: {"position": list(value.position), "quaternion_wxyz": list(value.quaternion_wxyz)}
                        for name, value in state.pose_world.items()
                    },
                    "hand_opening_measured_m": opening,
                    "finger_mismatch_m": finger_mismatch,
                    "mount_position_error_m": position_error,
                    "mount_rotation_error_rad": rotation_error,
                    "native_step_count": runtime["native_step_count"],
                    "forward_call_count": runtime["forward_call_count"],
                    "warning_counts": runtime["warning_counts"],
                }
                # Persist the state sample before checking any oracle threshold.
                trial["motion_samples"].append(point)
                trial["mount_error_max"] = {
                    "position_m": mount_position_max, "rotation_rad": mount_rotation_max,
                }
                latest.update({
                    "status": "motion_checkpoint", "trial": trial_index,
                    "phase": phase, "phase_interval": interval_index,
                    "control_step": int(state.control_step),
                    "mj_step_success_count": evidence["budgets"]["mj_step"],
                    "forward_call_count": evidence["budgets"]["mj_forward"],
                    "last_sample": point,
                })
                _write_json(output_dir / "s2_checkpoint.json", latest)
                if position_error > 1e-8 or rotation_error > 2e-7:
                    raise AssertionError("compiled dynamic mount invariant exceeded its fixed tolerance")
                if finger_mismatch > 1e-4:
                    raise AssertionError("source finger equality mismatch exceeded 1e-4m")
                if runtime["warning_counts"] and any(runtime["warning_counts"]):
                    raise AssertionError("MuJoCo warning count increased during the fixed-tree motion trial")

            for interval in range(64):
                if interval < 16:
                    arm_target = 0.1 * (interval + 1) / 16.0
                elif interval < 32:
                    arm_target = 0.1
                elif interval < 48:
                    arm_target = 0.1 * (1.0 - (interval - 31) / 16.0)
                else:
                    arm_target = 0.0
                command = session.apply_fixed_attachment_diagnostic_control(
                    receipt_identity, arm_joint1_target_rad=arm_target, hand_opening_m=0.076,
                )
                state = session.step()
                consume_boundary(state, "arm_mount_motion", interval + 1, command)
                if interval in {7, 15, 23, 31, 39, 47, 55, 63}:
                    evidence["rss_samples"].append({
                        "trial": trial_index, "phase": "arm_mount_motion",
                        "outer_interval": interval + 1, "rss_bytes": _rss_bytes(),
                    })

            arm_home_error = abs(float(session.snapshot().joint_position[f"{ARM_ENTITY}/joint1"]))
            for interval in range(64):
                if interval < 16:
                    opening_command = 0.076 + (0.004 - 0.076) * (interval + 1) / 16.0
                    phase = "hand_close"
                elif interval < 32:
                    opening_command = 0.004
                    phase = "hand_close"
                elif interval < 48:
                    opening_command = 0.004 + (0.076 - 0.004) * (interval - 31) / 16.0
                    phase = "hand_open"
                else:
                    opening_command = 0.076
                    phase = "hand_open"
                command = session.apply_fixed_attachment_diagnostic_control(
                    receipt_identity, arm_joint1_target_rad=0.0,
                    hand_opening_m=opening_command,
                )
                state = session.step()
                consume_boundary(state, phase, interval + 1, command)
                if interval in {7, 15, 23, 31, 39, 47, 55, 63}:
                    evidence["rss_samples"].append({
                        "trial": trial_index, "phase": "hand_open_close",
                        "outer_interval": interval + 1, "rss_bytes": _rss_bytes(),
                    })
            final_diagnostics = session.fixed_attachment_diagnostics
            trial["mount_error_max"] = {
                "position_m": mount_position_max, "rotation_rad": mount_rotation_max,
            }
            trial["warning_count_max"] = max_warning_count
            trial["oracle"] = {
                "arm_joint1_peak_abs_rad": arm_peak,
                "arm_joint1_return_home_error_rad": arm_home_error,
                "hand_root_rotation_during_arm_rad": hand_root_rotation_peak,
                "hand_closed_min_opening_m": min(close_openings),
                "hand_open_max_opening_m": max(open_openings),
                "hand_opening_excursion_m": max(open_openings) - min(close_openings),
                "finger_equality_mismatch_max_m": max(
                    item["finger_mismatch_m"] for item in trial["motion_samples"]
                ),
                "finger_body_displacement_relative_to_hand_m": finger_displacements,
                "clock_abs_error_max_s": max(
                    abs(item["simulation_time_s"] - item["control_step"] * 0.01)
                    for item in trial["motion_samples"]
                ),
                "finite_state": all(_state_finite(session.snapshot()) for _ in (0,)),
                "warnings_total": max_warning_count,
                "outer_intervals": len(trial["motion_samples"]),
                "mj_step": final_diagnostics["native_step_count"],
                "mj_forward": final_diagnostics["forward_call_count"],
                "simulated_seconds": final_diagnostics["native_time_s"],
            }
            latest.update({
                "status": "trial_oracle_checkpoint",
                "trial": trial_index,
                "oracle": trial["oracle"],
                "mj_step_success_count": evidence["budgets"]["mj_step"],
                "forward_call_count": evidence["budgets"]["mj_forward"],
            })
            _write_json(output_dir / "s2_checkpoint.json", latest)
            oracle = trial["oracle"]
            checks = {
                "arm peak >=0.08 rad": oracle["arm_joint1_peak_abs_rad"] >= 0.08,
                "arm return <=0.02 rad": oracle["arm_joint1_return_home_error_rad"] <= 0.02,
                "hand root rotation >=0.05 rad": oracle["hand_root_rotation_during_arm_rad"] >= 0.05,
                "closed opening <=0.02 m": oracle["hand_closed_min_opening_m"] <= 0.02,
                "open opening >=0.06 m": oracle["hand_open_max_opening_m"] >= 0.06,
                "opening excursion >=0.04 m": oracle["hand_opening_excursion_m"] >= 0.04,
                "left finger displacement >=0.02 m": finger_displacements["left_finger"] >= 0.02,
                "right finger displacement >=0.02 m": finger_displacements["right_finger"] >= 0.02,
                "finger mismatch <=1e-4 m": oracle["finger_equality_mismatch_max_m"] <= 1e-4,
                "mount position <=1e-8 m": mount_position_max <= 1e-8,
                "mount rotation <=2e-7 rad": mount_rotation_max <= 2e-7,
                "clock <=1e-12 s": oracle["clock_abs_error_max_s"] <= 1e-12,
                "warnings zero": max_warning_count == 0,
                "outer intervals 128": oracle["outer_intervals"] == 128,
                "mj_step count 640": oracle["mj_step"] == 640,
                "simulated time 1.28 s": abs(oracle["simulated_seconds"] - 1.28) <= 1e-12,
            }
            trial["oracle_checks"] = checks
            trial["status"] = "PASS" if all(checks.values()) else "FAIL"
            if not all(checks.values()):
                failed = [key for key, value in checks.items() if not value]
                raise AssertionError(f"R03b S2 physical oracle failed: {failed}")
            trial["status"] = "PASS"
            close_before = session.fixed_attachment_diagnostics
            session.close()
            trial["close_evidence"] = session.fixed_attachment_close_evidence
            if (trial["close_evidence"] is None
                    or not trial["close_evidence"]["session_closed"]
                    or not trial["close_evidence"]["model_released"]
                    or not trial["close_evidence"]["data_released"]):
                raise AssertionError("fixed Attachment RuntimeSession did not release its owned native resources")
            if trial["close_evidence"]["native_step_count"] != 640:
                raise AssertionError("close evidence differs from the 640-step trial")
            if trial["close_evidence"]["forward_call_count"] != 129:
                raise AssertionError("close evidence differs from the 129-forward trial")
            if close_before["control_step"] != 128:
                raise AssertionError("RuntimeSession control boundary count differs from 128")
            latest = {
                "status": "closed_trial_checkpoint", "trial": trial_index,
                "close_evidence": trial["close_evidence"],
                "mj_step_success_count": evidence["budgets"]["mj_step"],
                "forward_call_count": evidence["budgets"]["mj_forward"],
            }
            _write_json(output_dir / "s2_checkpoint.json", latest)

        first, second = reset_signatures
        reset_equal = all(
            first[name] == second[name]
            for name in ("joint_position", "joint_velocity", "ctrl", "simulation_time_s")
        )
        evidence["reset_reproducibility"] = {
            "joint_position_exact": first["joint_position"] == second["joint_position"],
            "joint_velocity_exact": first["joint_velocity"] == second["joint_velocity"],
            "ctrl_exact": first["ctrl"] == second["ctrl"],
            "time_exact": first["simulation_time_s"] == second["simulation_time_s"],
            "all_equal_within_1e-12": reset_equal,
        }
        if not reset_equal:
            raise AssertionError("two independent Core materializations did not reset to the same exact state")
        evidence["status"] = "PASS"
        _write_json(output_dir / "s2_evidence.json", evidence)
        _write_json(output_dir / "s2_checkpoint.json", {
            "status": "PASS", "trial_count": len(evidence["trials"]),
            "budgets": evidence["budgets"],
        })
        return evidence
    except BaseException as exc:
        evidence["status"] = "FAIL"
        evidence["failure"] = f"{type(exc).__name__}: {exc}"
        evidence["failure_traceback"] = traceback.format_exc()
        for session in sessions:
            try:
                session.close()
            except Exception:
                pass
        close_receipts = [
            session.fixed_attachment_close_evidence for session in sessions
            if session.fixed_attachment_close_evidence is not None
        ]
        evidence["budgets"]["mj_step"] = sum(
            item["native_step_count"] for item in close_receipts
        )
        evidence["budgets"]["mj_forward"] = sum(
            item["forward_call_count"] for item in close_receipts
        )
        evidence["budgets"]["outer_intervals"] = sum(
            len(item["motion_samples"]) for item in evidence["trials"]
        )
        evidence["budgets"]["simulated_seconds"] = evidence["budgets"]["mj_step"] * 0.002
        for trial, receipt in zip(evidence["trials"], close_receipts):
            trial["close_evidence"] = receipt
        _write_json(output_dir / "s2_evidence.json", evidence)
        _write_json(output_dir / "s2_checkpoint.json", {
            **latest,
            "status": "FAIL",
            "failure": evidence["failure"],
            "mj_step_success_count": evidence["budgets"]["mj_step"],
            "forward_call_count": evidence["budgets"]["mj_forward"],
        })
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--static-only", action="store_true")
    parser.add_argument("--native-s2", action="store_true")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.static_only == args.native_s2:
        parser.error("select exactly one of --static-only or --native-s2")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.static_only:
        result = run_s1(args.output_dir)
        print(json.dumps({"status": result["status"], "rejections": len(result["rejections"])}))
        return
    result = run_native_s2(args.output_dir)
    print(json.dumps({"status": result["status"], "budgets": result["budgets"]}, sort_keys=True))


if __name__ == "__main__":
    main()
