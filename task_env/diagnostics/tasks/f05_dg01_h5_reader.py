"""Cold, provider-free semantic reader for a DG01 two-episode Core cell."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile
import xml.etree.ElementTree as ET

import h5py
import yaml


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _text(dataset) -> str:
    value = dataset[()]
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if hasattr(value, "item"):
        value = value.item()
    return str(value)


def _read_h5(path: Path) -> dict:
    with h5py.File(path, "r") as h5:
        env_meta = yaml.safe_load(_text(h5["meta/env_meta"]))
        controls = json.loads(_text(h5["meta/structured_controls_v1_json"]))
        outcome = json.loads(_text(h5["meta/episode_outcome_v1_json"]))
        typed = json.loads(_text(h5["meta/f05_public_typed_state_witness_v1_json"]))
        witness = json.loads(_text(h5["meta/dg01_native_run_witness_v1_json"]))
        metrics = {
            key: h5[f"info/task_metrics/{key}"][...].tolist()
            for key in h5.get("info/task_metrics", {})
        }
        return {
            "attrs": {key: h5.attrs[key] for key in h5.attrs},
            "env_meta": env_meta,
            "controls": controls,
            "outcome": outcome,
            "typed": typed,
            "witness": witness,
            "metrics": metrics,
            "terminated": h5["terminated"][...].tolist(),
            "truncated": h5["truncated"][...].tolist(),
            "success": h5["success"][...].tolist(),
            "obs_count": int(h5.attrs["observation_count"]),
            "transition_count": int(h5.attrs["transition_count"]),
        }


def _fail(message: str) -> None:
    raise ValueError(message)


def _near(value, target, *, atol=1e-9, rtol=1e-8) -> bool:
    return abs(float(value) - float(target)) <= atol + rtol * abs(float(target))


def _state_map(row: dict) -> tuple[dict, dict]:
    view = row["canonical_state_view_v1"]
    joints = {
        f"{item['entity_id']}/{item['joint_id']}": item
        for item in view["joints"]
    }
    frames = {
        f"{item['frame']['entity_id']}/{item['frame']['frame_id']}": item["pose_world"]
        for item in view["frames"]
    }
    return joints, frames


def _qmul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw*bw-ax*bx-ay*by-az*bz,
        aw*bx+ax*bw+ay*bz-az*by,
        aw*by-ax*bz+ay*bw+az*bx,
        aw*bz+ax*by-ay*bx+az*bw,
    )


def _qnorm(q):
    length = math.sqrt(sum(value * value for value in q))
    if length <= 1e-15:
        _fail("MJCF kinematics encountered a zero quaternion")
    return tuple(value / length for value in q)


def _qrotate(q, vector):
    q = _qnorm(q)
    pure = (0.0, float(vector[0]), float(vector[1]), float(vector[2]))
    conjugate = (q[0], -q[1], -q[2], -q[3])
    result = _qmul(_qmul(q, pure), conjugate)
    return result[1:]


def _add(a, b):
    return tuple(float(x) + float(y) for x, y in zip(a, b, strict=True))


def _axis_angle(axis, angle):
    axis = tuple(float(value) for value in axis)
    length = math.sqrt(sum(value * value for value in axis))
    if length <= 1e-15:
        _fail("MJCF hinge axis is zero")
    scale = math.sin(float(angle) / 2.0) / length
    return _qnorm((math.cos(float(angle)/2.0), *(value * scale for value in axis)))


def _vec(element, name, size, default):
    raw = element.attrib.get(name)
    if raw is None:
        return tuple(default)
    values = tuple(float(value) for value in raw.split())
    if len(values) != size:
        _fail(f"unsupported MJCF {name} vector length: {len(values)}")
    return values


def _rotation(element):
    if "quat" in element.attrib:
        return _qnorm(_vec(element, "quat", 4, (1, 0, 0, 0)))
    if any(name in element.attrib for name in ("euler", "axisangle", "xyaxes", "zaxis")):
        _fail("independent FK reader only accepts the source's authored quaternion transforms")
    return (1.0, 0.0, 0.0, 0.0)


def _mjcf_hand_fk(xml_path: Path, arm_q: dict[str, float]) -> dict:
    """Small independent FK for the frozen Panda MJCF body/joint chain."""
    root = ET.parse(xml_path).getroot()
    compiler = root.find("compiler")
    if compiler is not None and compiler.attrib.get("angle", "radian") != "radian":
        _fail("independent FK reader requires radian MJCF joint values")
    worldbody = root.find("worldbody")
    if worldbody is None:
        _fail("derived DG01 MJCF has no worldbody")
    result = {}

    def walk(body, parent_position, parent_quaternion):
        body_position = _vec(body, "pos", 3, (0, 0, 0))
        body_quaternion = _rotation(body)
        position = _add(parent_position, _qrotate(parent_quaternion, body_position))
        quaternion = _qnorm(_qmul(parent_quaternion, body_quaternion))
        joints = list(body.findall("joint"))
        joints.extend(body.findall("freejoint"))
        for joint in joints:
            name = joint.attrib.get("name")
            if not name:
                _fail("independent FK requires named joints")
            if name not in arm_q:
                # Fingers and the floating cube do not affect the Panda hand frame.
                continue
            kind = joint.attrib.get("type", "hinge")
            if kind != "hinge":
                _fail(f"unsupported Panda chain joint type: {kind}")
            axis = _vec(joint, "axis", 3, (0, 0, 1))
            anchor = _vec(joint, "pos", 3, (0, 0, 0))
            reference = float(joint.attrib.get("ref", 0.0))
            angle = arm_q[name] - reference
            pivot_world = _add(position, _qrotate(quaternion, anchor))
            joint_rotation = _axis_angle(axis, angle)
            quaternion = _qnorm(_qmul(quaternion, joint_rotation))
            rotated_anchor = _qrotate(quaternion, anchor)
            position = tuple(pivot_world[index] - rotated_anchor[index]
                             for index in range(3))
        name = body.attrib.get("name")
        if name == "hand":
            result["hand_body"] = {
                "position_m": list(position),
                "quaternion_wxyz": list(quaternion),
            }
        for site in body.findall("site"):
            site_name = site.attrib.get("name")
            if site_name in {"hand", "tcp", "hand_site"}:
                site_position = _vec(site, "pos", 3, (0, 0, 0))
                site_quaternion = _rotation(site)
                result["hand"] = {
                    "position_m": list(_add(position, _qrotate(quaternion, site_position))),
                    "quaternion_wxyz": list(_qnorm(_qmul(quaternion, site_quaternion))),
                }
        for child in body.findall("body"):
            walk(child, position, quaternion)

    for body in worldbody.findall("body"):
        walk(body, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
    if "hand" not in result:
        # The Scene's canonical hand Frame binds the source hand Body origin.
        if "hand_body" not in result:
            _fail("independent FK could not find the source Panda hand Body")
        result["hand"] = result["hand_body"]
    return result["hand"]


def _quat_error(a, b):
    dot = abs(sum(float(x) * float(y) for x, y in zip(a, b, strict=True)))
    return 2.0 * math.acos(min(1.0, max(-1.0, dot)))


def _expected_profile(plan):
    frozen = plan["frozen_source"]
    return {
        "task_source_identity_sha256": frozen["task_source_identity_sha256"],
        "task_artifact_identity_sha256": frozen["task_artifact_identity_sha256"],
        "scene_identity_sha256": frozen["scene_identity_sha256"],
        "source_closure_sha256": frozen["source_closure_sha256"],
        "panda_source_closure_sha256": frozen["panda_source_closure_sha256"],
        "panda_xml_sha256": frozen["panda_xml_sha256"],
        "task_scene_recipe_sha256": frozen["recipe_sha256"],
        "derived_scene_xml_sha256": frozen["source_xml_sha256"],
        "runtime_lowered_xml_sha256": frozen["runtime_lowered_xml_sha256"],
        "model_receipt_identity_sha256": frozen["model_receipt_identity_sha256"],
    }


def _verify_reset_write_receipt(profile: dict) -> None:
    source = profile.get("source_mappings", {})
    receipt = profile.get("reset_write_receipt", {})
    expected_targets = sorted({
        *source.get("joint_targets", {}).values(),
        *source.get("open_actuators", ()),
    })
    if (receipt.get("schema_version") != "native-reset-write-receipt-v1"
            or receipt.get("reset_sample_id") != profile.get("reset_sample_id")
            or sorted(receipt.get("written_joint_names", ())) != sorted(source.get("joints", {}))
            or sorted(receipt.get("written_free_joint_names", ())) != sorted(source.get("free_joints", {}))
            or receipt.get("reset_target_names") != expected_targets
            or receipt.get("velocities_zeroed") is not True
            or receipt.get("partial") is not False):
        _fail("DG01 H5 public ResetPlan write receipt is missing, partial or cross-bound")


def _verify_selected_core_task_timebase(env_meta: dict) -> None:
    """Verify the task and clock at their Generic H5 v3 metadata locations."""
    environment = env_meta.get("environment", {})
    timebase = env_meta.get("timebase", {})
    if (environment.get("name") != "SelectedReferenceEnv.F05Dg01MenagerieMujocoCore"
            or environment.get("task_name") != "phase-ii-f05-dg01-panda-cube"
            or timebase.get("physics_dt") != 0.002
            or timebase.get("control_substeps") != 5):
        _fail("DG01 H5 selected Core Task/timebase metadata differs from the frozen route")


def _verify_dg01_horizon_outcome(outcome: dict) -> None:
    """Check the direct EpisodeOutcomeV1 mapping stored by Generic H5 v3."""
    if (outcome.get("final_boundary") != 300
            or outcome.get("end_reason") != "horizon_reached"
            or outcome.get("terminated") is not False
            or outcome.get("truncated") is not True
            or outcome.get("task_success") is not None):
        _fail("DG01 lifecycle outcome must be horizon-truncated with unknown lifecycle success")


def _verify_controller_action_config(profile: dict, plan: dict) -> None:
    expected = plan.get("controller_action_config")
    actual = profile.get("controller_action_config")
    if not isinstance(expected, dict) or actual != expected:
        _fail("DG01 H5 Position ActionConfig differs from the frozen controller profile")


def verify_h5(path: Path, *, plan: dict, run_id: str, episode_index: int,
              expected_h5_sha256: str | None = None,
              derived_xml_path: Path | None = None,
              kinematics_xml_path: Path | None = None) -> dict:
    path = path.resolve()
    if not path.is_file() or path.stat().st_size < 4096:
        _fail("DG01 H5 is missing, empty or not durably sized")
    actual_h5_sha256 = _sha256(path)
    if expected_h5_sha256 is not None and actual_h5_sha256 != expected_h5_sha256:
        _fail("DG01 H5 byte SHA-256 differs from the independent outer receipt")
    data = _read_h5(path)
    attrs = data["attrs"]
    if (attrs.get("schema_id") != "task-env-h5" or attrs.get("schema_version") != "v3"
            or not bool(attrs.get("episode_complete"))):
        _fail("DG01 H5 container is not a complete task-env-h5/v3 episode")
    if data["transition_count"] != 300 or data["obs_count"] != 301:
        _fail("DG01 H5 must contain T=300 and T+1=301")
    profile = data["env_meta"].get("reference_profile", {})
    if profile.get("profile_id") != "f05-dg01-mujoco-core-v1":
        _fail("DG01 H5 reference profile identity mismatch")
    _verify_controller_action_config(profile, plan)
    env_metadata = data["env_meta"]
    _verify_selected_core_task_timebase(env_metadata)
    for field, expected in _expected_profile(plan).items():
        actual = (profile.get("model_receipt_identity_sha256") if field == "model_receipt_identity_sha256"
                  else profile.get(field))
        if actual != expected:
            _fail(f"DG01 H5 frozen provenance mismatch at {field}")
    if profile.get("provenance_kind") != "native_runtime" or profile.get("runtime_admitted") is not True:
        _fail("DG01 H5 is not bound to the native Core runtime route")
    _verify_reset_write_receipt(profile)
    for relative, expected_sha in plan["code_sha256"].items():
        if relative in profile.get("code_sha256", {}) and profile["code_sha256"][relative] != expected_sha:
            _fail(f"DG01 H5 code provenance changed: {relative}")
    model = profile.get("model_receipt")
    if not isinstance(model, dict) or model.get("identity_sha256") != plan["frozen_source"]["model_receipt_identity_sha256"]:
        _fail("DG01 H5 model receipt identity mismatch")
    model_payload = {key: value for key, value in model.items() if key != "identity_sha256"}
    model_identity = hashlib.sha256(json.dumps(
        model_payload, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()
    if model_identity != model.get("identity_sha256"):
        _fail("DG01 public model receipt inner semantic digest is invalid")
    if model.get("dimensions") != {"nq": 16, "nv": 15, "nu": 8, "njnt": 10,
                                    "neq": 1, "ntendon": 1}:
        _fail("DG01 H5 public compiled-model dimensions differ from the frozen receipt")
    if (profile.get("task_predicate", {}).get("evaluator") != "f05_dg01_cube_lift_height_v1"
            or not _near(profile.get("task_predicate", {}).get("parameters_si", {}).get("lift_threshold_z_m", float("nan")), 0.585)):
        _fail("DG01 H5 Task predicate semantics/threshold differ from frozen DG01 Task")
    cube_body = model.get("bodies", {}).get("free-cube/free_cube", {})
    if (cube_body.get("mass_kg") != 0.1
            or cube_body.get("com_position_local_m") != [0.0, 0.0, 0.0]
            or cube_body.get("inertia_kg_m2") != [6e-05, 6e-05, 6e-05]):
        _fail("DG01 H5 cube mass/COM/inertia receipt differs from exact compiled model")
    tendon = model.get("tendon", {})
    wraps = tendon.get("wraps", [])
    if (len(wraps) != 2 or [item.get("parameter") for item in wraps] != [0.5, 0.5]
            or tendon.get("stiffness") != 0.0 or tendon.get("damping") != 0.0):
        _fail("DG01 H5 exact split tendon coefficient/law changed")
    equality = model.get("equality", {})
    if (model.get("dimensions", {}).get("neq") != 1 or equality.get("type") != 2
            or equality.get("solref") != [0.005, 1.0]):
        _fail("DG01 H5 exact source finger equality receipt changed")
    scalar_joints = model.get("scalar_joints", {})
    expected_address = {f"panda-main/joint{index}": index - 1 for index in range(1, 8)}
    for name, address in expected_address.items():
        joint = scalar_joints.get(name)
        if not isinstance(joint, dict) or joint.get("qpos_address") != address or joint.get("dof_address") != address:
            _fail(f"DG01 H5 named joint address mismatch: {name}")

    witness = data["witness"]
    if (witness.get("schema_version") != "f05-dg01-native-run-witness-v1"
            or witness.get("run_id") != run_id
            or witness.get("episode_index") != episode_index
            or witness.get("run_plan_sha256") != plan["plan_sha256"]
            or witness.get("model_receipt_identity_sha256") != model.get("identity_sha256")
            or witness.get("control_intervals") != 300
            or witness.get("accepted_physics_steps") != 1500
            or witness.get("reset_physics_steps") != 0):
        _fail("DG01 H5 native-run witness is stale, cross-run or incomplete")
    if data["typed"].get("observation_count") != 301 or len(data["typed"].get("rows", [])) != 301:
        _fail("DG01 H5 typed-state extension is not T+1")
    if len(data["controls"]) != 300:
        _fail("DG01 H5 structured control evidence is not T")
    outcome = data["outcome"]
    _verify_dg01_horizon_outcome(outcome)
    if data["terminated"] != [False] * 300 or data["truncated"] != [False] * 299 + [True]:
        _fail("DG01 T-length lifecycle flags do not represent one complete horizon")

    joints_rows, frames_rows = [], []
    episode_ids, times = set(), []
    cube_z, cube_vz = [], []
    cube_start = cube_quaternion_start = cube_reset_twist = None
    hand_position_errors, hand_orientation_errors = [], []
    derived_path = derived_xml_path
    xml_path = kinematics_xml_path
    if derived_path is None or xml_path is None:
        _fail("DG01 cold reader needs the derived and runtime-lowered source XMLs")
    if _sha256(derived_path) != profile.get("derived_scene_xml_sha256"):
        _fail("DG01 source XML byte identity differs from the H5 profile")
    if _sha256(xml_path) != profile.get("runtime_lowered_xml_sha256"):
        _fail("DG01 runtime-lowered MJCF byte identity differs from the H5 profile")
    for index, row in enumerate(data["typed"]["rows"]):
        if row.get("boundary_index") != index:
            _fail("DG01 typed-state boundary rows are not contiguous")
        view = row["canonical_state_view_v1"]
        boundary, clock = view["boundary"], view["sample_clock"]
        if (boundary.get("control_step") != index
                or clock.get("sample_index") != index
                or clock.get("clock_domain") != "evaluation_boundary"
                or not _near(clock.get("simulation_time_s"), index * 0.01, atol=1e-12, rtol=0.0)):
            _fail("DG01 typed-state native clock is stale or discontinuous")
        episode_ids.add(boundary.get("episode_id"))
        times.append(float(clock["simulation_time_s"]))
        joints, frames = _state_map(row)
        joints_rows.append(joints)
        frames_rows.append(frames)
        for joint_name in (f"panda-main/joint{j}" for j in range(1, 8)):
            item = joints.get(joint_name)
            if item is None or item.get("position_representation") != "radian" or item.get("velocity_representation") != "radian_per_second":
                _fail(f"DG01 typed-state joint unit mismatch: {joint_name}")
        for finger_name in ("finger_joint1", "finger_joint2"):
            item = joints.get(f"panda-main/{finger_name}")
            if item is None or item.get("position_representation") != "meter" or item.get("velocity_representation") != "meter_per_second":
                _fail(f"DG01 typed-state finger unit mismatch: {finger_name}")
        cube = frames.get("free-cube/free_cube")
        if cube is None:
            _fail("DG01 typed-state H5 lacks the free cube frame")
        cube_z.append(float(cube["position"][2]))
        if index == 0:
            cube_start = [float(value) for value in cube["position"]]
            cube_quaternion_start = [float(value) for value in cube["quaternion_wxyz"]]
            free_joint = joints.get("free-cube/cube_freejoint")
            if free_joint is None:
                free_joint = next((item for item in joints.values()
                                   if item.get("entity_id") == "free-cube"
                                   and item.get("kind") == "floating"), None)
            if free_joint is None or len(free_joint.get("velocity", [])) != 6:
                _fail("DG01 reset lacks typed free-cube twist for the reset physical gate")
            cube_reset_twist = [float(value) for value in free_joint["velocity"]]
        hand = frames.get("panda-main/hand")
        if hand is None:
            _fail("DG01 typed-state H5 lacks Panda hand frame")
        arm_q = {f"joint{j}": float(joints[f"panda-main/joint{j}"]["position"][0])
                 for j in range(1, 8)}
        fk = _mjcf_hand_fk(xml_path, arm_q)
        hand_position_errors.append(math.sqrt(sum(
            (float(a) - float(b)) ** 2
            for a, b in zip(hand["position"], fk["position_m"], strict=True)
        )))
        hand_orientation_errors.append(_quat_error(hand["quaternion_wxyz"], fk["quaternion_wxyz"]))
    if len(episode_ids) != 1 or not next(iter(episode_ids)):
        _fail("DG01 H5 typed boundaries do not bind one lifecycle episode")
    if (cube_start is None or cube_quaternion_start is None or cube_reset_twist is None
            or any(abs(actual - expected) > 0.005
                   for actual, expected in zip(cube_start, (1.0, 0.5, 0.9), strict=True))
            or _quat_error(cube_quaternion_start, (1.0, 0.0, 0.0, 0.0)) > 1e-8
            or max(abs(value) for value in cube_reset_twist) > 0.02):
        _fail("DG01 reset cube position/orientation/twist misses the original physical gate")
    if max(hand_position_errors) > 0.01 or max(hand_orientation_errors) > 0.08:
        _fail("DG01 independent source-MJCF FK does not match typed hand Frame")
    cube_vz = [0.0]
    cube_vz.extend((cube_z[index] - cube_z[index - 1]) / 0.01 for index in range(1, len(cube_z)))
    drop_m = cube_z[0] - min(cube_z)
    if cube_z[0] < 0.895 or drop_m < 0.2 or min(cube_vz) > -0.3:
        _fail("DG01 free cube did not reset/fall under source gravity through Core")
    settled = cube_z[-10:]
    settled_mean = sum(settled) / len(settled)
    if (not 0.485 <= settled_mean <= 0.535
            or max(abs(value - settled_mean) for value in settled) > 0.005
            or max(abs(value) for value in cube_vz[-10:]) > 0.08):
        _fail("DG01 cube did not settle within original support/rest thresholds")

    controls = data["controls"]
    schedule = plan["schedule"]
    home = plan["home_joint_position_rad"]
    per_phase = {}
    final_support_contact_missing = False
    arm_excursion = max(abs(float(joints["panda-main/joint1"]["position"][0]) - home["joint1"])
                        for joints in joints_rows)
    for interval_index, control in enumerate(controls):
        phase = next(item for item in schedule if item["start"] <= interval_index < item["stop"])
        writer_rows = control.get("writer_controls", [])
        if len(writer_rows) != 1:
            _fail("DG01 structured transition does not have exactly one Core writer")
        writer = writer_rows[0]
        applied = writer.get("applied_control", {}).get("payload", {})
        write = applied.get("mujoco_position_write_receipt_v1", {})
        advances = applied.get("mujoco_interval_advance_receipts_v1", [])
        if len(advances) != 5 or applied.get("mujoco_interval_advance_attempts") != 5:
            _fail(f"DG01 transition {interval_index} lacks five accepted native advances")
        target = writer.get("canonical_action", {}).get("position_target_v1", {}).get("target", {})
        target_arm = target.get("arm_position", {})
        target_servo = target.get("arm_servo_position", {})
        expected_arm = {
            f"panda-main/joint{joint_index}": float(home[f"joint{joint_index}"])
            + float(phase["arm_offsets_rad"][joint_index - 1])
            for joint_index in range(1, 8)
        }
        request_groups = control.get("request", {}).get("groups", [])
        arm_groups = [item for item in request_groups if item.get("group_id") == "arm"]
        if len(arm_groups) != 1:
            _fail("DG01 structured request omits its unique arm group")
        requested_pose = arm_groups[0].get("values", [])
        expected_pose = _mjcf_hand_fk(xml_path, {
            f"joint{joint_index}": expected_arm[f"panda-main/joint{joint_index}"]
            for joint_index in range(1, 8)
        })
        if (len(requested_pose) != 7
                or any(not _near(requested_pose[index], expected_pose["position_m"][index], atol=2e-8)
                       for index in range(3))
                or _quat_error(requested_pose[3:7], expected_pose["quaternion_wxyz"]) > 2e-7):
            _fail(f"DG01 interval {interval_index} Cartesian request is not source FK of frozen schedule")
        arm_writes = write.get("arm_actuator_controls", {})
        for name in expected_arm:
            if (name not in target_arm or name not in target_servo
                    or name not in arm_writes
                    or not _near(arm_writes[name].get("requested_ctrl", float("nan")), target_servo[name], atol=1e-10, rtol=0.0)):
                _fail(f"DG01 interval {interval_index} Core arm request/target/write binding mismatch")
        gripper = write.get("gripper", {})
        if (not _near(gripper.get("requested_opening_m", float("nan")), phase["opening_m"])
                or gripper.get("effective_force_range_N") != [-5.0, 5.0]
                or write.get("model_receipt_identity_sha256") != model.get("identity_sha256")):
            _fail(f"DG01 interval {interval_index} Core write receipt lost request/cap/model binding")
        session_episode = write.get("episode_id")
        if session_episode not in episode_ids:
            _fail("DG01 Core write receipt crossed an episode identity")
        if (not _near(advances[0].get("time_before_s"), interval_index * 0.01, atol=1e-12, rtol=0.0)
                or not _near(advances[-1].get("time_after_s"), (interval_index + 1) * 0.01, atol=1e-12, rtol=0.0)):
            _fail(f"DG01 interval {interval_index} substep clocks are stale")
        expected_index = interval_index * 5
        for substep_index, advance in enumerate(advances):
            step = expected_index + substep_index + 1
            if (advance.get("substep_index") != substep_index
                    or advance.get("native_step_index") != step
                    or not _near(advance.get("time_before_s"), (step - 1) * 0.002, atol=1e-12, rtol=0.0)
                    or not _near(advance.get("time_after_s"), step * 0.002, atol=1e-12, rtol=0.0)):
                _fail("DG01 native substep index/time mismatch")
            tendon_readback = advance.get("gripper_tendon_readback", {})
            actuator = model.get("actuators", {}).get("actuator8", {})
            gain = actuator.get("gain_parameters", [None])[0]
            bias = actuator.get("bias_parameters", [])
            if len(bias) < 3:
                _fail("DG01 model receipt omits source tendon actuator bias")
            predicted = (float(gain) * float(tendon_readback.get("control", float("nan")))
                         + float(bias[0]) + float(bias[1]) * float(tendon_readback.get("length_m", float("nan")))
                         + float(bias[2]) * float(tendon_readback.get("length_rate_m_s", float("nan"))))
            force = float(tendon_readback.get("scalar_force_N", float("nan")))
            clipped = max(-5.0, min(5.0, predicted))
            if (not _near(force, clipped, atol=1e-6, rtol=1e-7)
                    or abs(force) > 5.0 + 1e-7):
                _fail("DG01 native tendon scalar law/cap does not match source model and Core request")
            actuator_id = int(tendon_readback.get("actuator_id", -1))
            ctrl_vector = advance.get("actuator_ctrl", [])
            if (actuator_id < 0 or actuator_id >= len(ctrl_vector)
                    or not _near(tendon_readback.get("control", float("nan")),
                                 ctrl_vector[actuator_id], atol=1e-9, rtol=0.0)):
                _fail("DG01 native tendon control differs from the model-wide Core ctrl vector")
            moment = tendon_readback.get("tendon_generalized_force_moment", [])
            projected = tendon_readback.get("finger_qfrc_actuator_N", [])
            prediction = tendon_readback.get("scalar_force_from_moment_prediction_N", [])
            if len(moment) != 2 or len(projected) != 2 or len(prediction) != 2:
                _fail("DG01 native Core receipt lacks sparse tendon moment/projection values")
            if any(not _near(value, 0.5, atol=1e-9, rtol=0.0) for value in moment):
                _fail("DG01 native Core tendon Jacobian differs from the original split source law")
            if any(not _near(projected[i], prediction[i], atol=2e-6, rtol=1e-6)
                   for i in range(2)):
                _fail("DG01 native Core actuator force does not equal tendon Jacobian projection")
            contact = advance.get("cube_support_contact", {})
            task_geoms = model.get("task_geometries", {})
            expected_cube_id = task_geoms.get("free_cube_geom", {}).get("geom_id")
            expected_support_id = task_geoms.get("support_geom", {}).get("geom_id")
            if (contact.get("cube_geom_id") != expected_cube_id
                    or contact.get("support_geom_id") != expected_support_id):
                _fail("DG01 Core contact receipt is not bound to exact cube/support geometry")
            if interval_index >= 290 and int(contact.get("contact_count", 0)) < 1:
                final_support_contact_missing = True
        per_phase.setdefault(phase["phase"], []).append(interval_index)

    if final_support_contact_missing:
        _fail("DG01 final settled window lacks cube/support contact receipts")

    # Boundary samples are indexed by post-step control step; each interval's
    # requested phase owns boundaries [start+1, stop].
    for phase in schedule:
        first, stop = int(phase["start"]), int(phase["stop"])
        target = [float(home[f"joint{j}"]) + float(phase["arm_offsets_rad"][j-1])
                  for j in range(1, 8)]
        late = joints_rows[stop - 9:stop + 1]
        errors = [abs(float(row[f"panda-main/joint{j}"]["position"][0]) - target[j-1])
                  for row in late for j in range(1, 8)]
        if phase["phase"] in {"unloaded_home_hold", "final_hold"} and max(errors) > 0.025:
            _fail(f"DG01 {phase['phase']} late target error exceeds 0.025 rad")
        if phase["phase"] == "unloaded_point" and max(errors) > 0.025:
            _fail("DG01 point hold late target error exceeds 0.025 rad")
        if phase["phase"] == "unloaded_return" and max(errors) > 0.04:
            _fail("DG01 home return late target error exceeds 0.04 rad")
        velocities = [abs(float(row[f"panda-main/joint{j}"]["velocity"][0]))
                      for row in late for j in range(1, 8)]
        if max(velocities) > 0.1:
            _fail(f"DG01 {phase['phase']} late joint velocity exceeds 0.1 rad/s")
        for j in range(1, 8):
            positions = [float(row[f"panda-main/joint{j}"]["position"][0]) for row in late]
            if max(positions) - min(positions) > 0.005:
                _fail(f"DG01 {phase['phase']} late joint position oscillation exceeds 5 mrad")
    if arm_excursion < 0.015:
        _fail("DG01 arm joint1 excursion did not exceed original minimum")
    close = joints_rows[191:201]
    close_sums = [sum(float(row[f"panda-main/finger_joint{i}"]["position"][0])
                      for i in (1, 2)) for row in close]
    opened = joints_rows[291:301]
    open_sums = [sum(float(row[f"panda-main/finger_joint{i}"]["position"][0])
                     for i in (1, 2)) for row in opened]
    if max(close_sums) > 0.03 or min(open_sums) < 0.055:
        _fail("DG01 gripper close/open physical tracking misses frozen thresholds")
    if max(open_sums) - min(close_sums) < 0.015:
        _fail("DG01 physical gripper opening excursion is below the frozen minimum")
    finger_difference = [abs(float(row["panda-main/finger_joint1"]["position"][0])
                             - float(row["panda-main/finger_joint2"]["position"][0]))
                         for row in opened]
    if max(finger_difference) > 0.002:
        _fail("DG01 late equality finger symmetry exceeds the frozen 2 mm threshold")
    raw_pred = data["metrics"].get("raw_lift_height_predicate")
    threshold = data["metrics"].get("lift_threshold_z_m")
    if raw_pred is None or len(raw_pred) != 300 or threshold is None or len(threshold) != 300:
        _fail("DG01 raw Task predicate/threshold is not recorded for all transitions")
    for index, (predicate, value) in enumerate(zip(raw_pred, cube_z[1:], strict=True)):
        if bool(predicate) != (float(value) >= 0.585):
            _fail(f"DG01 Task predicate does not match measured cube height at transition {index}")
    if data["success"] != [bool(value) for value in raw_pred]:
        _fail("DG01 H5 generic raw evaluator success differs from Task metrics")
    task_end = outcome.get("boundary_event", {}).get("payload", {}).get("task_predicate_v1", {})
    if (task_end.get("raw_predicate") != bool(raw_pred[-1])
            or task_end.get("lifecycle_valid_success") is not None
            or task_end.get("lifecycle_valid_success_assessed") is not False):
        _fail("DG01 end event conflates raw Task predicate and lifecycle success")
    return {
        "episode_index": episode_index,
        "episode_id": next(iter(episode_ids)),
        "h5_sha256": actual_h5_sha256,
        "transition_count": 300,
        "observation_count": 301,
        "accepted_physics_steps": 1500,
        "reset_physics_steps": 0,
        "fk_position_error_max_m": max(hand_position_errors),
        "fk_orientation_error_max_rad": max(hand_orientation_errors),
        "cube_drop_m": drop_m,
        "cube_settled_center_mean_z_m": settled_mean,
        "cube_contact_receipts": sum(
            int(advance["cube_support_contact"]["contact_count"] > 0)
            for control in controls for advance in control["writer_controls"][0]["applied_control"]["payload"]["mujoco_interval_advance_receipts_v1"]
        ),
        "arm_joint1_excursion_rad": arm_excursion,
        "gripper_closed_sum_max_m": max(close_sums),
        "gripper_open_sum_min_m": min(open_sums),
    }


def _verify_exit(receipt: dict, plan: dict, run_id: str) -> None:
    if (receipt.get("schema_version") != "f05-dg01-native-supervisor-receipt-v1"
            or receipt.get("run_id") != run_id
            or receipt.get("worker_exit_code") != 0
            or receipt.get("resource_violation") is not None
            or receipt.get("child_process_group_remaining_after_cleanup") is not False
            or receipt.get("lock_released") is not True
            or receipt.get("start_mem_available_bytes", 0)
                < plan["limits"]["start_mem_available_bytes_min"]
            or receipt.get("sample_count", 0) < 1
            or receipt.get("sample_interval_s_max_observed", float("inf"))
                > plan["limits"]["sample_interval_s_max"]
            or receipt.get("wall_seconds", float("inf"))
                > plan["limits"]["worker_wall_s_max"]
            or receipt.get("maximum_process_group_rss_bytes", 1 << 62) > plan["limits"]["group_rss_bytes_max"]
            or receipt.get("minimum_mem_available_bytes", 0) < plan["limits"]["abort_mem_available_bytes_below"]):
        _fail("DG01 native supervisor exit/resource/process/lock receipt failed")


def _mutate_h5(path: Path, mutation: str):
    with h5py.File(path, "r+") as h5:
        meta = h5["meta"]
        def replace_json(name, transform):
            value = json.loads(_text(meta[name]))
            transform(value)
            del meta[name]
            dtype = h5py.string_dtype(encoding="utf-8")
            meta.create_dataset(name, data=json.dumps(value, sort_keys=True), dtype=dtype)
        if mutation == "source_closure":
            def change(value): value["reference_profile"]["source_closure_sha256"] = "0" * 64
            raw = yaml.safe_load(_text(meta["env_meta"]))
            change(raw); del meta["env_meta"]
            dtype = h5py.string_dtype(encoding="utf-8")
            meta.create_dataset("env_meta", data=yaml.safe_dump(raw, sort_keys=True), dtype=dtype)
        elif mutation == "model_shape":
            def change(value): value["reference_profile"]["model_receipt"]["dimensions"]["nq"] = 17
            raw = yaml.safe_load(_text(meta["env_meta"]))
            change(raw); del meta["env_meta"]
            dtype = h5py.string_dtype(encoding="utf-8")
            meta.create_dataset("env_meta", data=yaml.safe_dump(raw, sort_keys=True), dtype=dtype)
        elif mutation == "joint_address":
            raw = yaml.safe_load(_text(meta["env_meta"]))
            raw["reference_profile"]["model_receipt"]["scalar_joints"]["panda-main/joint1"]["qpos_address"] = 99
            del meta["env_meta"]
            dtype = h5py.string_dtype(encoding="utf-8")
            meta.create_dataset("env_meta", data=yaml.safe_dump(raw, sort_keys=True), dtype=dtype)
        elif mutation == "unit":
            def change(value):
                for joint in value["rows"][1]["canonical_state_view_v1"]["joints"]:
                    if joint["entity_id"] == "panda-main" and joint["joint_id"] == "joint1":
                        joint["position_representation"] = "meter"
                        break
            replace_json("f05_public_typed_state_witness_v1_json", change)
        elif mutation == "com":
            raw = yaml.safe_load(_text(meta["env_meta"]))
            raw["reference_profile"]["model_receipt"]["bodies"]["free-cube/free_cube"]["com_position_local_m"][0] = 0.001
            del meta["env_meta"]
            dtype = h5py.string_dtype(encoding="utf-8")
            meta.create_dataset("env_meta", data=yaml.safe_dump(raw, sort_keys=True), dtype=dtype)
        elif mutation == "reset_write_receipt":
            raw = yaml.safe_load(_text(meta["env_meta"]))
            raw["reference_profile"]["reset_write_receipt"]["partial"] = True
            del meta["env_meta"]
            dtype = h5py.string_dtype(encoding="utf-8")
            meta.create_dataset("env_meta", data=yaml.safe_dump(raw, sort_keys=True), dtype=dtype)
        elif mutation == "tendon_coefficient":
            raw = yaml.safe_load(_text(meta["env_meta"]))
            raw["reference_profile"]["model_receipt"]["tendon"]["wraps"][0]["parameter"] = 0.6
            del meta["env_meta"]
            dtype = h5py.string_dtype(encoding="utf-8")
            meta.create_dataset("env_meta", data=yaml.safe_dump(raw, sort_keys=True), dtype=dtype)
        elif mutation in {"force_clip", "equality", "task_predicate", "stale_time", "cross_run"}:
            def change_controls(value):
                applied = value[0]["writer_controls"][0]["applied_control"]["payload"]
                if mutation == "force_clip":
                    applied["mujoco_position_write_receipt_v1"]["gripper"]["effective_force_range_N"] = [-50.0, 50.0]
                elif mutation == "equality":
                    raw = yaml.safe_load(_text(meta["env_meta"]))
                    raw["reference_profile"]["model_receipt"]["equality"]["type"] = 0
                    del meta["env_meta"]
                    dtype = h5py.string_dtype(encoding="utf-8")
                    meta.create_dataset("env_meta", data=yaml.safe_dump(raw, sort_keys=True), dtype=dtype)
            if mutation in {"force_clip", "equality"}:
                replace_json("structured_controls_v1_json", change_controls)
            elif mutation == "task_predicate":
                h5["info/task_metrics/raw_lift_height_predicate"][0] = False
            elif mutation == "stale_time":
                def change(value):
                    value["rows"][1]["canonical_state_view_v1"]["sample_clock"]["simulation_time_s"] = 0.008
                replace_json("f05_public_typed_state_witness_v1_json", change)
            elif mutation == "cross_run":
                def change(value): value["run_id"] = "different-run"
                replace_json("dg01_native_run_witness_v1_json", change)
        else:
            raise ValueError(f"unknown DG01 mutation: {mutation}")
        h5.flush()


def run_reader(plan_path: Path, worker_result_path: Path, supervisor_path: Path,
               output: Path, *, make_negatives: bool = True) -> dict:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["plan_sha256"] = _sha256(plan_path)
    worker = json.loads(worker_result_path.read_text(encoding="utf-8"))
    supervisor = json.loads(supervisor_path.read_text(encoding="utf-8"))
    run_id = plan["run_id"]
    _verify_exit(supervisor, plan, run_id)
    if (worker.get("run_id") != run_id
            or worker.get("run_plan_sha256") != plan["plan_sha256"]
            or worker.get("same_environment_object") is not True
            or worker.get("environment_closed") is not True
            or worker.get("integration_steps") != 3000
            or worker.get("expected_integration_steps") != 3000
            or worker.get("distinct_provider_materializations") != 2
            or len(worker.get("episodes", [])) != 2):
        _fail("DG01 worker result does not bind the complete same-Env two-episode plan")
    derived_xml = Path(worker["source_files"]["derived_task_scene_xml"]["path"])
    if _sha256(derived_xml) != worker["source_files"]["derived_task_scene_xml"]["sha256"]:
        _fail("DG01 derived scene XML source receipt hash mismatch")
    lowered_xml = Path(worker["source_files"]["runtime_lowered_scene_xml"]["path"])
    if _sha256(lowered_xml) != worker["source_files"]["runtime_lowered_scene_xml"]["sha256"]:
        _fail("DG01 runtime-lowered scene XML source receipt hash mismatch")
    summaries = []
    seen_episodes = set()
    total_steps = 0
    for entry in worker["episodes"]:
        episode_index = int(entry["episode_index"])
        h5_path = Path(entry["h5_path"])
        summary = verify_h5(
            h5_path, plan=plan, run_id=run_id, episode_index=episode_index,
            expected_h5_sha256=entry["h5_sha256"], derived_xml_path=derived_xml,
            kinematics_xml_path=lowered_xml,
        )
        if summary["episode_id"] != entry["episode_id"]:
            _fail("DG01 H5 episode id differs from worker run receipt")
        seen_episodes.add(summary["episode_id"])
        total_steps += summary["accepted_physics_steps"]
        summaries.append(summary)
    if len(seen_episodes) != 2 or total_steps != 3000:
        _fail("DG01 formal H5 set reuses an episode or has incomplete native steps")

    negative_results = []
    if make_negatives:
        negative_root = output / "negative_mutations"
        negative_root.mkdir(parents=True, exist_ok=False)
        source = Path(worker["episodes"][0]["h5_path"])
        for mutation in (
            "source_closure", "model_shape", "joint_address", "unit", "com",
            "tendon_coefficient", "force_clip", "equality", "reset_write_receipt", "task_predicate",
            "stale_time", "cross_run", "durable_file",
        ):
            mutated = negative_root / f"{mutation}.h5"
            shutil.copy2(source, mutated)
            if mutation == "durable_file":
                with mutated.open("r+b") as stream:
                    stream.truncate(512)
                    stream.flush()
            else:
                _mutate_h5(mutated, mutation)
            outer_hash = _sha256(mutated)
            try:
                verify_h5(
                    mutated, plan=plan, run_id=run_id, episode_index=0,
                    expected_h5_sha256=outer_hash, derived_xml_path=derived_xml,
                    kinematics_xml_path=lowered_xml,
                )
            except (ValueError, KeyError, IndexError, TypeError, OSError) as error:
                negative_results.append({
                    "mutation": mutation,
                    "outer_rehashed_sha256": outer_hash,
                    "rejected": True,
                    "reason": str(error),
                    "file_bytes": mutated.stat().st_size,
                })
            else:
                _fail(f"DG01 independent reader accepted semantic mutation {mutation}")
        # A syntactically readable HDF5 with a stale native-exit receipt must fail.
        mutated_receipt = copy.deepcopy(supervisor)
        mutated_receipt["worker_exit_code"] = 1
        try:
            _verify_exit(mutated_receipt, plan, run_id)
        except ValueError as error:
            negative_results.append({
                "mutation": "exit_code_zero", "rejected": True,
                "reason": str(error),
            })
        else:
            _fail("DG01 independent reader accepted nonzero worker exit")
        if len(negative_results) != 14:
            _fail("DG01 H5/control negative mutation matrix is incomplete")
    output.mkdir(parents=True, exist_ok=True)
    result = {
        "schema_version": "f05-dg01-cold-reader-result-v1",
        "run_id": run_id,
        "plan_sha256": plan["plan_sha256"],
        "worker_exit_code": supervisor["worker_exit_code"],
        "episodes": summaries,
        "accepted_physics_steps": total_steps,
        "negative_mutations": negative_results,
        "negative_mutations_passed": len(negative_results),
    }
    result_path = output / "cold_reader_result.json"
    with result_path.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--worker-result", required=True, type=Path)
    parser.add_argument("--supervisor", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--no-negatives", action="store_true")
    args = parser.parse_args(argv)
    result = run_reader(
        args.plan, args.worker_result, args.supervisor, args.output,
        make_negatives=not args.no_negatives,
    )
    print(json.dumps({
        "run_id": result["run_id"],
        "accepted_physics_steps": result["accepted_physics_steps"],
        "episodes": len(result["episodes"]),
        "negative_mutations_passed": result["negative_mutations_passed"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
