"""R03a independent MuJoCo probe; native execution requires explicit contract approval.
Stdlib-only module import for authorized S1 checks does not load a provider.

Standalone MuJoCo CPU feasibility draft; not a GeoChora Runtime, Provider adapter,
TaskEnv, Recorder, Controller, benchmark, or qualification test.
"""
from __future__ import annotations

import argparse
import contextlib
import gc
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import resource
import signal
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path

EXPECTED_MUJOCO = "3.8.1"
PREFIX = "probe_hand_"

class CandidateBlocked(RuntimeError):
    pass

class CandidateCheckFailed(RuntimeError):
    pass

class SampledResourceLimit(RuntimeError):
    pass

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def approved_record(value: object, basis: str) -> bool:
    return (isinstance(value, dict) and value.get("decision") == "APPROVED"
            and isinstance(value.get("approved_by"), str) and bool(value["approved_by"].strip())
            and isinstance(value.get("reference"), str) and bool(value["reference"].strip())
            and value.get("candidate_basis_sha256") == basis)

def candidate_basis_sha256(contract: dict) -> str:
    basis = json.loads(json.dumps(contract))
    basis.pop("approvals", None)
    basis["artifacts"].pop("candidate_basis_sha256", None)
    return hashlib.sha256(canonical_json_bytes(basis)).hexdigest()

def find_repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".git").exists() and (candidate / "asset/external/mujoco_menagerie/franka_emika_panda").is_dir():
            return candidate
    raise CandidateBlocked("repository root with pinned Menagerie source was not found")

def git_value(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True, timeout=10)
    return result.stdout.strip()

def safe_number(value: object) -> float | str:
    number = float(value)
    if math.isfinite(number):
        return number
    if math.isnan(number):
        return "NaN"
    return "+Infinity" if number > 0 else "-Infinity"

def safe_array(value: object) -> list:
    return [safe_number(item) for item in value.flat]

def finite_array(value: object) -> bool:
    return all(math.isfinite(float(item)) for item in value.flat)

def snapshot_state(data: object) -> dict:
    return {"time_s": safe_number(data.time), "qpos": safe_array(data.qpos),
            "qvel": safe_array(data.qvel), "ctrl": safe_array(data.ctrl)}

def vectors_equal(a: list, b: list, tol: float) -> bool:
    return len(a) == len(b) and all(abs(float(x)-float(y)) <= tol for x,y in zip(a,b))

def hand_ctrl_for_finger_qpos(qpos_m: float, joint_range_m: list, ctrlrange: list) -> float:
    q_min, q_max = [float(value) for value in joint_range_m]
    ctrl_min, ctrl_max = [float(value) for value in ctrlrange]
    if q_max <= q_min:
        raise CandidateBlocked("Hand source joint range is not increasing")
    return ctrl_min + (float(qpos_m)-q_min)*(ctrl_max-ctrl_min)/(q_max-q_min)

def joint_range_overrun(qpos: float, lower: float, upper: float) -> float:
    return max(float(lower)-float(qpos), float(qpos)-float(upper), 0.0)

def enforce_joint_range(name: str, qpos: float, lower: float, upper: float, tolerance: float) -> float:
    overrun=joint_range_overrun(qpos,lower,upper)
    if overrun>float(tolerance):
        raise CandidateCheckFailed(f"joint range overrun for {name}: {qpos} not within [{lower},{upper}] (overrun={overrun}, tolerance={tolerance})")
    return overrun

def repo_and_artifact_preflight(repo: Path, contract_path: Path, contract: dict) -> dict:
    head = git_value(repo, "rev-parse", "HEAD")
    branch = git_value(repo, "branch", "--show-current")
    if head != contract["source"]["core_head"] or branch != contract["source"]["branch"]:
        raise CandidateBlocked(f"BLOCKED_CORE: expected {contract['source']['core_head']} on {contract['source']['branch']}; got {head} on {branch}")
    draft_hash = sha256_file(Path(__file__).resolve())
    manifest_path = contract_path.parent / contract["source_manifest"]["path"]
    manifest_hash = sha256_file(manifest_path)
    if manifest_hash != contract["source_manifest"]["sha256"]:
        raise CandidateBlocked("source_manifest.json hash differs from bound contract")
    if draft_hash != contract["artifacts"]["probe_draft_sha256"]:
        raise CandidateBlocked("probe_draft.py hash differs from bound contract")
    if manifest_hash != contract["artifacts"]["source_manifest_sha256"]:
        raise CandidateBlocked("source manifest artifact binding differs")
    basis = candidate_basis_sha256(contract)
    if basis != contract["artifacts"]["candidate_basis_sha256"]:
        raise CandidateBlocked("candidate basis hash differs")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["core"]["head"] != head or manifest["core"]["branch"] != branch:
        raise CandidateBlocked("source manifest Core identity differs from live Git identity")
    return {"core_head": head, "branch": branch, "probe_draft_sha256": draft_hash,
            "source_manifest_sha256": manifest_hash, "candidate_basis_sha256": basis}

def static_provider_preflight(contract: dict) -> dict:
    expected = contract["source"]["candidate_provider"]["installed_candidate_files"]
    observed = []
    try:
        metadata_version = importlib.metadata.version("mujoco")
    except importlib.metadata.PackageNotFoundError as exc:
        raise CandidateBlocked("BLOCKED_PROVIDER: mujoco distribution metadata missing") from exc
    if metadata_version != EXPECTED_MUJOCO:
        raise CandidateBlocked(f"BLOCKED_PROVIDER: expected package metadata {EXPECTED_MUJOCO}, got {metadata_version}")
    for row in expected:
        path = Path(row["path"])
        got = sha256_file(path) if path.is_file() else None
        observed.append({"role": row["role"], "path": str(path), "sha256": got})
        if got != row["sha256"]:
            raise CandidateBlocked(f"BLOCKED_PROVIDER: installed candidate hash mismatch for {row['role']}")
    return {"package_metadata_version": metadata_version, "installed_candidates_only": observed,
            "loaded_runtime": "NOT_YET_IMPORTED"}

def validate_supported_candidate(contract: dict) -> None:
    b=contract["budgets"]; d=contract["dynamics"]; a=contract["actuation"]
    expected=(b["workers"],b["trials"],b["outer_intervals_per_phase_per_trial_max"],b["physics_dt_s"],b["substeps_per_outer_interval"],b["native_process_wall_timeout_s"],b["whole_probe_wall_budget_s"],b["sampled_rss_max_bytes"],b["incremental_evidence_max_bytes"])
    if expected != (1,2,64,0.002,5,120,600,2147483648,134217728):
        raise CandidateBlocked("contract budget differs from this single-file draft's supported candidate")
    if (d["timestep_s"], d["outer_interval_s"], d["native_steps_per_outer_interval"], d["max_total_outer_intervals"], d["max_total_mj_step_calls"]) != (0.002,0.01,5,384,1920):
        raise CandidateBlocked("contract dynamics totals differ from this draft's supported candidate")
    if d["integrator"]!="implicitfast" or d["preserved_global_solver_options"]["impratio"]!=10.0 or d["gravity_m_s2_expected"]!=[0.0,0.0,-9.81]:
        raise CandidateBlocked("integrator/gravity/impratio differs from checked source candidate")
    if b["outer_intervals_total_max"]!=384 or b["mj_step_calls_total_max"]!=1920 or b["simulated_seconds_total_max"]!=3.84 or b["mj_forward_calls_total_max"]!=389:
        raise CandidateBlocked("derived call or simulated-time budget is inconsistent")
    if a["arm"]["command_curve"] != {"intervals":64,"ramp_up":16,"hold_high":16,"ramp_return":16,"hold_home":16,"joint1_target_peak_rad":0.1}:
        raise CandidateBlocked("unsupported arm command curve")
    if a["hand"]["command_curve"] != {"intervals":64,"close_ramp":16,"hold_closed":16,"open_ramp":16,
                                        "hold_open":16,"close_ctrl":12.75,"open_ctrl":242.25}:
        raise CandidateBlocked("unsupported hand command curve")
    if contract["reset"]["arm_qpos_ctrl_rad"] != a["arm"]["home_qpos_and_ctrl_rad"]:
        raise CandidateBlocked("explicit reset Arm values differ from authored source/control contract")
    hand=a["hand"]; operating=hand["operating_targets"]
    expected_targets={"close_each_finger_qpos_m":0.002,"close_ctrl":12.75,
        "open_each_finger_qpos_m":0.038,"open_ctrl":242.25,"limit_margin_each_side_m":0.002}
    if operating != expected_targets:
        raise CandidateBlocked("Hand operating targets differ from the explicitly authorized interior case")
    q_range=hand["finger_joint_range_each_m"]; ctrlrange=hand["ctrlrange"]
    if q_range != [0.0,0.04] or ctrlrange != [0.0,255.0]:
        raise CandidateBlocked("Hand native joint range or actuator ctrlrange changed")
    if not (q_range[0] <= operating["close_each_finger_qpos_m"] < operating["open_each_finger_qpos_m"] <= q_range[1]):
        raise CandidateBlocked("Hand operating qpos targets are outside or unordered within source range")
    if not (ctrlrange[0] <= operating["close_ctrl"] < operating["open_ctrl"] <= ctrlrange[1]):
        raise CandidateBlocked("Hand operating commands are outside or unordered within native ctrlrange")
    for qpos_key,ctrl_key in (("close_each_finger_qpos_m","close_ctrl"),("open_each_finger_qpos_m","open_ctrl")):
        mapped=hand_ctrl_for_finger_qpos(operating[qpos_key],q_range,ctrlrange)
        if abs(mapped-operating[ctrl_key])>1e-12:
            raise CandidateBlocked(f"Hand qpos/ctrl mapping mismatch for {qpos_key}: {mapped}")
    if (contract["reset"]["hand_finger_qpos_m"] != [operating["open_each_finger_qpos_m"]]*2
            or contract["reset"]["hand_ctrl"] != operating["open_ctrl"]
            or hand["reset_qpos_m"] != [operating["open_each_finger_qpos_m"]]*2
            or hand["reset_ctrl"] != operating["open_ctrl"]):
        raise CandidateBlocked("Hand reset qpos/ctrl fields are not synchronized to the open operating target")
    if hand["command_curve"] != {"intervals":64,"close_ramp":16,"hold_closed":16,"open_ramp":16,"hold_open":16,
                                  "close_ctrl":operating["close_ctrl"],"open_ctrl":operating["open_ctrl"]}:
        raise CandidateBlocked("Hand command curve and operating targets differ")
    if contract["reset"]["seed"] is not None:
        raise CandidateBlocked("unsupported stochastic seed")
    initialization=contract["initialization"]
    if (initialization["reset_count"]!=2
            or initialization["hand_qpos_by_name_m"]!={name:operating["open_each_finger_qpos_m"] for name in hand["finger_joint_order"]}
            or "actuator8=242.25 (open operating target)" not in initialization["ctrl"]):
        raise CandidateBlocked("initialization hand reset fields are not synchronized to the interior open target")
    phases={item["name"]:item["control"] for item in d["phases_per_trial"]}
    if any("242.25" not in phases[name] for name in ("arm","load")):
        raise CandidateBlocked("Arm/load phases do not hold the approved open operating command")
    if contract["oracles"]["reset_repeat"]["qpos_qvel_ctrl_max_abs_delta"]!=0.0 or contract["oracles"]["reset_repeat"]["time_delta_max_s"]!=0.0:
        raise CandidateBlocked("unsupported repeated-reset oracle")
    if d["nonintegrating_calls"] != {"outer_boundary_refreshes":384,"reset_forward_calls":2,"load_balance_forward_calls":3,"total_mj_forward_calls":389,"mj_fullM_calls":1,"mj_jacBodyCom_calls":1,"additional_mj_step_calls":0}:
        raise CandidateBlocked("nonintegrating call budget differs")
    if [(item["name"],item["outer_intervals_max"]) for item in d["phases_per_trial"]] != [("arm",64),("hand",64),("load",64)]:
        raise CandidateBlocked("unsupported phase names/order/interval counts")
    source=contract["source"]; assembly=contract["assembly"]; hand=a["hand"]; arm=a["arm"]
    if source["candidate_provider"]["python_package"]!="mujoco==3.8.1" or source["candidate_provider"]["runtime"]!="MuJoCo native CPU only":
        raise CandidateBlocked("unsupported provider identity")
    if assembly["namespace_prefix"]!="probe_hand_" or assembly["expected_native_joint_order"]!=[f"joint{i}" for i in range(1,8)]+["probe_hand_finger_joint1","probe_hand_finger_joint2"]:
        raise CandidateBlocked("unsupported namespace or canonical/native joint order")
    if assembly["expected_native_actuator_order"]!=[f"actuator{i}" for i in range(1,8)]+["probe_hand_actuator8"]:
        raise CandidateBlocked("unsupported canonical/native actuator order")
    shape=assembly["required_compiled_shape"]
    if shape!={"nq":9,"nv":9,"nu":8,"neq":1,"ntendon":1,"njnt":9,"free_joints":0,"nkey":1,"nbody_excluding_world":12,"nsite":1,"nmesh":67,"ngeom":81,"nexclude":3}:
        raise CandidateBlocked("compiled-shape contract differs from the single-file draft")
    arm_names=[f"joint{i}" for i in range(1,8)]
    if arm["joint_order"]!=arm_names or arm["home_qpos_and_ctrl_rad"]!=[0.0,0.0,0.0,-1.57079,0.0,1.57079,-0.7853]:
        raise CandidateBlocked("unsupported arm joints or reset home")
    expected_ranges={"joint1":[-2.8973,2.8973],"joint2":[-1.7628,1.7628],"joint3":[-2.8973,2.8973],"joint4":[-3.0718,-0.0698],"joint5":[-2.8973,2.8973],"joint6":[-0.0175,3.7525],"joint7":[-2.8973,2.8973]}
    expected_forces={f"actuator{i}":[-87.0,87.0] if i<=4 else [-12.0,12.0] for i in range(1,8)}
    if arm["joint_ranges_rad"]!=expected_ranges or arm["actuator_ctrlrange_rad"]!=expected_ranges or arm["actuator_forcerange_Nm"]!=expected_forces:
        raise CandidateBlocked("arm axis/limit/control/torque contract differs from frozen source candidate")
    if hand["finger_joint_order"]!=["probe_hand_finger_joint1","probe_hand_finger_joint2"] or hand["finger_joint_range_each_m"]!=[0.0,0.04] or hand["ctrlrange"]!=[0.0,255.0] or hand["gainprm"]!=[0.01568627451,0.0,0.0] or hand["biasprm"]!=[0.0,-100.0,-10.0] or hand["forcerange_N"]!=[-100.0,100.0]:
        raise CandidateBlocked("Hand tendon actuator/limits contract differs from frozen source candidate")
    load=contract["oracles"]["external_load"]
    if load["force_world_N"]!=[1.0,0.0,0.0] or load["torque_Nm"]!=[0.0,0.0,0.0] or load["duration_outer_intervals"]!=64:
        raise CandidateBlocked("unsupported load vector/torque/duration")

def approval_gate(contract: dict, basis: str) -> list[str]:
    required=("maintainer_scope","native_execution_authorization","numerical_thresholds","resource_budget")
    return [name for name in required if not approved_record(contract["approvals"].get(name),basis)]

def parse_vector(element: ET.Element, field: str, default: list[float]) -> list[float]:
    raw = element.get(field)
    return [float(item) for item in raw.split()] if raw else list(default)


def q_normalize(q: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in q))
    if not math.isfinite(norm) or norm == 0.0:
        raise CandidateCheckFailed("invalid source quaternion")
    return [value / norm for value in q]


def q_conjugate(q: list[float]) -> list[float]:
    return [q[0], -q[1], -q[2], -q[3]]


def q_multiply(a: list[float], b: list[float]) -> list[float]:
    w, x, y, z = a
    W, X, Y, Z = b
    return [w * W - x * X - y * Y - z * Z,
            w * X + x * W + y * Z - z * Y,
            w * Y - x * Z + y * W + z * X,
            w * Z + x * Y - y * X + z * W]


def q_rotate(q: list[float], value: list[float]) -> list[float]:
    rotated = q_multiply(q_multiply(q, [0.0, *value]), q_conjugate(q))
    return rotated[1:]


def local_pose(element: ET.Element) -> tuple[list[float], list[float]]:
    return (parse_vector(element, "pos", [0.0, 0.0, 0.0]),
            q_normalize(parse_vector(element, "quat", [1.0, 0.0, 0.0, 0.0])))


def compose_pose(a: tuple[list[float], list[float]], b: tuple[list[float], list[float]]) -> tuple[list[float], list[float]]:
    pa, qa = a
    pb, qb = b
    rotated = q_rotate(qa, pb)
    return ([pa[i] + rotated[i] for i in range(3)], q_normalize(q_multiply(qa, qb)))


def inverse_pose(pose: tuple[list[float], list[float]]) -> tuple[list[float], list[float]]:
    position, quaternion = pose
    inverse_q = q_conjugate(quaternion)
    return (q_rotate(inverse_q, [-value for value in position]), inverse_q)


def close_vector(actual: list[float], expected: list[float], tolerance: float) -> bool:
    return len(actual) == len(expected) and max((abs(a - b) for a, b in zip(actual, expected)), default=0.0) <= tolerance


def static_source_preflight(repo: Path, contract: dict, contract_path: Path) -> dict:
    source_root = repo / "asset/external/mujoco_menagerie/franka_emika_panda"
    arm_path = source_root / "panda_nohand.xml"
    hand_path = source_root / "hand.xml"
    license_path = source_root / "LICENSE"
    expected = {
        arm_path: contract["source"]["arm_xml"]["sha256"],
        hand_path: contract["source"]["hand_xml"]["sha256"],
    }
    observed = {"files": {}, "asset_references": [], "mount": {}, "source_manifest_sha256": None}
    for path, wanted in ((arm_path, expected[arm_path]), (hand_path, expected[hand_path])):
        got = sha256_file(path)
        observed["files"][str(path.relative_to(repo))] = got
        if got != wanted:
            raise CandidateBlocked(f"source SHA-256 mismatch: {path.relative_to(repo)}")
    manifest_path = contract_path.parent / contract["source_manifest"]["path"]
    manifest_hash = sha256_file(manifest_path)
    observed["source_manifest_sha256"] = manifest_hash
    if manifest_hash != contract["source_manifest"]["sha256"]:
        raise CandidateBlocked("source_manifest.json hash mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if sha256_file(license_path) != manifest["source_pair"]["license"]["sha256"]:
        raise CandidateBlocked("Menagerie license hash mismatch")

    unique_files = {row["path"]: row for row in manifest["source_pair"]["closure_files"]}
    closure_rows = []
    for rel, row in sorted(unique_files.items()):
        path = (repo / rel).resolve()
        if not path.is_file() or not path.is_relative_to(source_root.resolve()) or sha256_file(path) != row["sha256"]:
            raise CandidateBlocked(f"source closure hash/path mismatch: {rel}")
        closure_rows.append({"path": rel, "sha256": row["sha256"], "size_bytes": path.stat().st_size})
    closure_hash = hashlib.sha256(canonical_json_bytes(closure_rows)).hexdigest()
    if closure_hash != contract["source_manifest"]["source_pair_closure_sha256"] or closure_hash != manifest["source_pair"]["closure_sha256"]:
        raise CandidateBlocked("source-pair closure digest mismatch")
    for xml_path in (arm_path, hand_path):
        tree = ET.parse(xml_path)
        root = tree.getroot()
        compiler = root.find("compiler")
        meshdir = compiler.get("meshdir", "") if compiler is not None else ""
        for element in root.iter():
            rel = element.get("file")
            if not rel:
                continue
            resolved = (xml_path.parent / meshdir / rel).resolve()
            if not resolved.is_relative_to(source_root.resolve()) or not resolved.is_file():
                raise CandidateBlocked(f"source dependency escaped or missing: {rel}")
            repo_rel = resolved.relative_to(repo).as_posix()
            got = sha256_file(resolved)
            if repo_rel not in unique_files or got != unique_files[repo_rel]["sha256"]:
                raise CandidateBlocked(f"unmanifested or changed mesh: {repo_rel}")
            observed["asset_references"].append(repo_rel)

    arm = ET.parse(arm_path).getroot()
    hand = ET.parse(hand_path).getroot()
    arm_link7 = next((node for node in arm.iter("body") if node.get("name") == "link7"), None)
    attachment = arm_link7.find("./body[@name='attachment']") if arm_link7 is not None else None
    site = attachment.find("./site[@name='attachment_site']") if attachment is not None else None
    child_root = hand.find("./worldbody/body[@name='hand']")
    if arm_link7 is None or attachment is None or site is None or child_root is None:
        raise CandidateBlocked("required arm link7/attachment/site or hand root is missing")
    arm_worldbody = arm.find("worldbody")
    hand_worldbody = hand.find("worldbody")
    if arm_worldbody is None or [node.get("name") for node in arm_worldbody.findall("body")] != ["link0"]:
        raise CandidateBlocked("arm source must have exactly the authored link0 root")
    if hand_worldbody is None or [node.get("name") for node in hand_worldbody.findall("body")] != ["hand"]:
        raise CandidateBlocked("hand source must have exactly the authored hand root")
    if list(arm.iter("freejoint")) or list(hand.iter("freejoint")):
        raise CandidateBlocked("unexpected free root joint")
    if len([node for node in hand.iter("joint") if node.get("name", "").startswith("finger_joint")]) != 2:
        raise CandidateBlocked("expected exactly two source finger joints")
    fixed_tendons = [node for node in hand.iter("fixed") if node.get("name") == "split"]
    equalities = [child for node in hand.iter("equality") for child in node if child.tag == "joint"]
    actuator8 = [node for node in hand.iter("general") if node.get("name") == "actuator8"]
    if len(fixed_tendons) != 1 or len(equalities) != 1 or len(actuator8) != 1:
        raise CandidateBlocked("source must retain exactly one split tendon, equality and actuator8")
    tendon_rows = [node.attrib for node in fixed_tendons[0].iter("joint")]
    expected_tendon = [{"joint": "finger_joint1", "coef": "0.5"}, {"joint": "finger_joint2", "coef": "0.5"}]
    if tendon_rows != expected_tendon:
        raise CandidateBlocked("split tendon names/order/coefficients differ")
    eq = equalities[0]
    if (eq.get("joint1"), eq.get("joint2")) != ("finger_joint1", "finger_joint2"):
        raise CandidateBlocked("finger equality endpoints differ")
    if eq.get("solimp") != "0.95 0.99 0.001" or eq.get("solref") != "0.005 1":
        raise CandidateBlocked("finger equality solver parameters differ")
    finger_default = next((node for node in hand.iter("default") if node.get("class") == "finger"), None)
    finger_joint_default = finger_default.find("joint") if finger_default is not None else None
    if finger_joint_default is None or finger_joint_default.get("type") != "slide" or finger_joint_default.get("axis") != "0 1 0" or finger_joint_default.get("range") != "0 0.04":
        raise CandidateBlocked("finger axis/type/range inherited defaults differ")
    hand_actuator_source = actuator8[0]
    expected_actuator_attrs = {
        "tendon": "split",
        "ctrlrange": "0 255",
        "forcerange": "-100 100",
        "gainprm": "0.01568627451 0 0",
        "biasprm": "0 -100 -10",
    }
    if any(hand_actuator_source.get(name) != value for name, value in expected_actuator_attrs.items()):
        raise CandidateBlocked("hand actuator8 source parameters differ")
    arm_excludes = [node.attrib for node in arm.iter("exclude")]
    hand_excludes = [node.attrib for node in hand.iter("exclude")]
    if arm_excludes != [{"body1": "link0", "body2": "link1"}]:
        raise CandidateBlocked("arm collision exclusion set differs")
    if hand_excludes != [{"body1": "hand", "body2": "left_finger"}, {"body1": "hand", "body2": "right_finger"}]:
        raise CandidateBlocked("hand collision exclusion set differs")
    arm_named = {node.get("name") for node in arm.iter() if node.get("name")}
    hand_prefixed = {PREFIX + node.get("name") for node in hand.iter() if node.get("name")}
    if arm_named.intersection(hand_prefixed):
        raise CandidateBlocked("prefixed child resource collides with a parent name")
    home = ["0", "0", "0", "-1.57079", "0", "1.57079", "-0.7853"]
    arm_keys = [key for key in arm.iter("key")]
    if len(arm_keys) != 1 or arm_keys[0].get("name") != "home" or arm_keys[0].get("qpos", "").split() != home or arm_keys[0].get("ctrl", "").split() != home:
        raise CandidateBlocked("arm home keyframe differs from the reset source")
    if list(hand.iter("key")):
        raise CandidateBlocked("hand source unexpectedly contains a keyframe")

    prior = repo / "workspace/maintenance/phase_ii_01_plan_revision_20261023_001/prior_review/attachment_feasibility.xml"
    historical_expected = manifest["historical_inputs"]["attachment_feasibility.xml"]["sha256"]
    if sha256_file(prior) != historical_expected:
        raise CandidateBlocked("historical mount source hash mismatch")
    old_root = ET.parse(prior).getroot()
    old_link7 = next((node for node in old_root.iter("body") if node.get("name") == "link7"), None)
    old_frame = old_link7.find("./frame[@name='review_mount']") if old_link7 is not None else None
    old_hand = old_frame.find("./body[@name='review_hand_hand']") if old_frame is not None else None
    if old_frame is None or old_hand is None:
        raise CandidateBlocked("historical mount target is missing")

    link7_from_parent = compose_pose(local_pose(attachment), local_pose(site))
    link7_from_target = compose_pose(local_pose(old_frame), local_pose(old_hand))
    site_from_target = compose_pose(inverse_pose(link7_from_parent), link7_from_target)
    child_world_from_root = local_pose(child_root)
    site_from_child_world = compose_pose(site_from_target, inverse_pose(child_world_from_root))
    expected_mount = contract["assembly"]["T_parent_mount_from_child_mount"]
    expected_frame = contract["assembly"]["returned_attach_frame_compensation"]
    if not close_vector(site_from_target[0], expected_mount["pos_m"], 1e-10):
        raise CandidateBlocked("derived mount translation differs from the approved candidate")
    if not close_vector(site_from_target[1], expected_mount["quat_wxyz"], 2e-7):
        raise CandidateBlocked("derived mount rotation differs from the approved candidate")
    if not close_vector(site_from_child_world[0], expected_frame["pos_m"], 1e-10):
        raise CandidateBlocked("derived attach-frame translation differs")
    if not close_vector(site_from_child_world[1], expected_frame["quat_wxyz"], 2e-7):
        raise CandidateBlocked("derived attach-frame rotation differs")
    observed["mount"] = {
        "parent_site_from_hand_root": {"pos_m": site_from_target[0], "quat_wxyz": site_from_target[1]},
        "parent_site_from_child_worldbody": {"pos_m": site_from_child_world[0], "quat_wxyz": site_from_child_world[1]},
        "historical_target_wrt_link7": {"pos_m": link7_from_target[0], "quat_wxyz": link7_from_target[1]},
    }
    return observed


def object_id(mujoco, model, object_type, name: str) -> int:
    result = int(mujoco.mj_name2id(model, object_type, name))
    if result < 0:
        raise CandidateCheckFailed(f"native name missing: {name}")
    return result


def object_names(mujoco, model, object_type, count: int) -> list[str | None]:
    return [mujoco.mj_id2name(model, object_type, idx) for idx in range(count)]


def matrix3(flat) -> list[list[float]]:
    values = [float(value) for value in flat]
    return [values[0:3], values[3:6], values[6:9]]


def matmul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def matvec(a: list[list[float]], b: list[float]) -> list[float]:
    return [sum(a[i][j] * b[j] for j in range(3)) for i in range(3)]


def quaternion_matrix(q) -> list[list[float]]:
    w, x, y, z = [float(value) for value in q]
    return [[1 - 2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
            [2*(x*y+z*w), 1 - 2*(x*x+z*z), 2*(y*z-x*w)],
            [2*(x*z-y*w), 2*(y*z+x*w), 1 - 2*(x*x+y*y)]]


def rotation_error(actual: list[list[float]], expected: list[list[float]]) -> float:
    delta = matmul([[expected[j][i] for j in range(3)] for i in range(3)], actual)
    sine = 0.5 * math.sqrt((delta[2][1]-delta[1][2])**2 + (delta[0][2]-delta[2][0])**2 + (delta[1][0]-delta[0][1])**2)
    cosine = max(-1.0, min(1.0, 0.5*(sum(delta[i][i] for i in range(3))-1.0)))
    return math.atan2(sine, cosine)


def flat_finite(array) -> bool:
    return all(math.isfinite(float(value)) for value in array.flat)


def warning_counts(data) -> list[int]:
    return [int(item.number) for item in data.warning]


def verify_model(mujoco: object, model: object, contract: dict) -> dict:
    assembly = contract["assembly"]
    shape = assembly["required_compiled_shape"]
    dimensions = ("nq", "nv", "nu", "neq", "ntendon", "njnt", "nkey")
    actual = {key: int(getattr(model, key)) for key in dimensions}
    expected_dimensions = {key: int(shape[key]) for key in dimensions}
    if actual != expected_dimensions:
        raise CandidateCheckFailed(f"compiled dimensions differ: expected={expected_dimensions}, actual={actual}")
    for model_field, expected_value in (("nbody", shape["nbody_excluding_world"] + 1), ("nsite", shape["nsite"]), ("nmesh", shape["nmesh"]), ("ngeom", shape["ngeom"]), ("nexclude", shape["nexclude"])):
        if int(getattr(model, model_field)) != int(expected_value):
            raise CandidateCheckFailed(f"compiled {model_field} differs: expected={expected_value}, actual={getattr(model, model_field)}")
    joint_names = object_names(mujoco, model, mujoco.mjtObj.mjOBJ_JOINT, model.njnt)
    actuator_names = object_names(mujoco, model, mujoco.mjtObj.mjOBJ_ACTUATOR, model.nu)
    if joint_names != assembly["expected_native_joint_order"]:
        raise CandidateCheckFailed(f"joint order mismatch: {joint_names}")
    if actuator_names != assembly["expected_native_actuator_order"]:
        raise CandidateCheckFailed(f"actuator order mismatch: {actuator_names}")
    body_order = [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, idx) for idx in range(1, model.nbody)]
    if body_order != assembly["expected_native_body_order_excluding_world"]:
        raise CandidateCheckFailed(f"body order mismatch: {body_order}")
    site_order = object_names(mujoco, model, mujoco.mjtObj.mjOBJ_SITE, model.nsite)
    if site_order != assembly["expected_native_site_order"]:
        raise CandidateCheckFailed(f"site order mismatch: {site_order}")
    free_type = int(mujoco.mjtJoint.mjJNT_FREE)
    if sum(int(value) == free_type for value in model.jnt_type) != shape["free_joints"]:
        raise CandidateCheckFailed("unexpected free root joint")
    joint_map = {}
    for idx, name in enumerate(joint_names):
        joint_map[name] = {"id": idx, "qpos_address": int(model.jnt_qposadr[idx]), "dof_address": int(model.jnt_dofadr[idx]), "type": int(model.jnt_type[idx]), "axis": [float(v) for v in model.jnt_axis[idx]], "range": [float(v) for v in model.jnt_range[idx]]}
    if sorted(row["qpos_address"] for row in joint_map.values()) != list(range(9)) or sorted(row["dof_address"] for row in joint_map.values()) != list(range(9)):
        raise CandidateCheckFailed("native joint address mapping is not a nine-scalar bijection")
    scalar_types = {int(mujoco.mjtJoint.mjJNT_HINGE), int(mujoco.mjtJoint.mjJNT_SLIDE)}
    if any(row["type"] not in scalar_types for row in joint_map.values()):
        raise CandidateCheckFailed("all expected joints must be scalar hinge/slide joints")
    expected_ranges = dict(contract["actuation"]["arm"]["joint_ranges_rad"])
    expected_ranges.update({name: contract["actuation"]["hand"]["finger_joint_range_each_m"] for name in contract["actuation"]["hand"]["finger_joint_order"]})
    for name, expected_range in expected_ranges.items():
        if not close_vector(joint_map[name]["range"], expected_range, 1e-12):
            raise CandidateCheckFailed(f"joint range mismatch for {name}: {joint_map[name]['range']}")
    for name in contract["actuation"]["arm"]["joint_order"]:
        if not close_vector([float(v) for v in model.jnt_axis[joint_map[name]["id"]]], contract["actuation"]["arm"]["joint_axes"][name], 1e-12):
            raise CandidateCheckFailed(f"joint axis mismatch for {name}")
    for name in contract["actuation"]["hand"]["finger_joint_order"]:
        if not close_vector([float(v) for v in model.jnt_axis[joint_map[name]["id"]]], contract["actuation"]["hand"]["joint_axis"], 1e-12):
            raise CandidateCheckFailed(f"finger joint axis mismatch for {name}")
    actuator_map = {name: idx for idx, name in enumerate(actuator_names)}
    arm_actuation = contract["actuation"]["arm"]
    for index, joint_name in enumerate(arm_actuation["joint_order"]):
        aid = actuator_map[f"actuator{index+1}"]
        if int(model.actuator_ctrllimited[aid]) != 1 or not close_vector([float(v) for v in model.actuator_ctrlrange[aid]], arm_actuation["actuator_ctrlrange_rad"][joint_name], 1e-12):
            raise CandidateCheckFailed(f"arm actuator control range changed: actuator{index+1}")
        if int(model.actuator_forcelimited[aid]) != 1 or not close_vector([float(v) for v in model.actuator_forcerange[aid]], arm_actuation["actuator_forcerange_Nm"][f"actuator{index+1}"], 1e-12):
            raise CandidateCheckFailed(f"arm actuator force range changed: actuator{index+1}")
    hand_actuator = actuator_map["probe_hand_actuator8"]
    hand_contract = contract["actuation"]["hand"]
    if int(model.actuator_ctrllimited[hand_actuator]) != 1 or not close_vector([float(v) for v in model.actuator_ctrlrange[hand_actuator]], hand_contract["ctrlrange"], 1e-12):
        raise CandidateCheckFailed("hand actuator ctrlrange changed")
    if int(model.actuator_forcelimited[hand_actuator]) != 1 or not close_vector([float(v) for v in model.actuator_forcerange[hand_actuator]], hand_contract["forcerange_N"], 1e-12):
        raise CandidateCheckFailed("hand actuator forcerange changed")
    tendon_id = object_id(mujoco, model, mujoco.mjtObj.mjOBJ_TENDON, "probe_hand_split")
    actuator_id = actuator_map["probe_hand_actuator8"]
    if int(model.actuator_trnid[actuator_id][0]) != tendon_id:
        raise CandidateCheckFailed("hand actuator is not driven by the split tendon")
    finger_names = contract["assembly"]["canonical_to_native"]
    jid1 = object_id(mujoco, model, mujoco.mjtObj.mjOBJ_JOINT, finger_names["hand.finger_joint1"])
    jid2 = object_id(mujoco, model, mujoco.mjtObj.mjOBJ_JOINT, finger_names["hand.finger_joint2"])
    if int(model.eq_obj1id[0]) != jid1 or int(model.eq_obj2id[0]) != jid2:
        if int(model.eq_obj1id[0]) != jid2 or int(model.eq_obj2id[0]) != jid1:
            raise CandidateCheckFailed("compiled equality endpoints do not bind both finger joints")
    if int(model.eq_type[0]) != int(mujoco.mjtEq.mjEQ_JOINT):
        raise CandidateCheckFailed("compiled equality is not the source joint equality")
    if abs(float(model.opt.timestep) - contract["dynamics"]["timestep_s"]) > 1e-15:
        raise CandidateCheckFailed("native timestep differs from 2 ms")
    if not close_vector([float(v) for v in model.opt.gravity], contract["dynamics"]["gravity_m_s2_expected"], 1e-12):
        raise CandidateCheckFailed("native gravity differs from candidate default")
    if int(model.opt.integrator) != int(mujoco.mjtIntegrator.mjINT_IMPLICITFAST) or abs(float(model.opt.impratio) - 10.0) > 1e-12:
        raise CandidateCheckFailed("native integrator or impratio differs from source")
    body_map = {name: object_id(mujoco, model, mujoco.mjtObj.mjOBJ_BODY, name) for name in assembly["expected_native_body_order_excluding_world"]}
    site_map = {name: object_id(mujoco, model, mujoco.mjtObj.mjOBJ_SITE, name) for name in assembly["expected_native_site_order"]}
    native_to_canonical = {native: canonical for canonical, native in assembly["canonical_to_native"].items() if canonical != "hand.equality"}
    actuator_resource_map = {name: {"id": idx, "ctrlrange": [float(v) for v in model.actuator_ctrlrange[idx]], "forcerange": [float(v) for v in model.actuator_forcerange[idx]], "transmission_ids": [int(v) for v in model.actuator_trnid[idx]]} for name, idx in actuator_map.items()}
    equality_map = {"id": 0, "type": int(model.eq_type[0]), "endpoint_names": [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, int(model.eq_obj1id[0])), mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, int(model.eq_obj2id[0]))]}
    tendon_map = {"probe_hand_split": tendon_id}
    return {"shape": {**actual, "nbody_excluding_world": model.nbody - 1, "nsite": model.nsite, "nmesh": model.nmesh, "ngeom": model.ngeom, "nexclude": model.nexclude}, "body_order": body_order, "site_order": site_order, "joint_order": joint_names, "actuator_order": actuator_names, "body_map": body_map, "site_map": site_map, "joint_map": joint_map, "actuator_map": actuator_map, "actuator_resource_map": actuator_resource_map, "tendon_map": tendon_map, "equality_map": equality_map, "canonical_to_native": assembly["canonical_to_native"], "native_to_canonical": native_to_canonical}


def mount_measurement(mujoco: object, model: object, data: object, site_id: int, child_body_id: int, contract: dict) -> dict:
    mount = contract["assembly"]["T_parent_mount_from_child_mount"]
    p_pc = mount["pos_m"]
    r_wp = matrix3(data.site_xmat[site_id])
    p_wp = [float(v) for v in data.site_xpos[site_id]]
    q_pc = mount["quat_wxyz"]
    r_pc = quaternion_matrix(q_pc)
    p_expected = [p_wp[i] + matvec(r_wp, p_pc)[i] for i in range(3)]
    r_expected = matmul(r_wp, r_pc)
    p_actual = [float(v) for v in data.xpos[child_body_id]]
    r_actual = matrix3(data.xmat[child_body_id])
    p_error = math.sqrt(sum((p_actual[i]-p_expected[i])**2 for i in range(3)))
    r_error = rotation_error(r_actual, r_expected)
    return {"position_error_m": p_error, "rotation_geodesic_error_rad": r_error, "child_root_pos_world_m": p_actual, "parent_site_pos_world_m": p_wp}



def runtime_package_identity(mujoco: object, contract: dict) -> dict:
    provider=contract["source"]["candidate_provider"]
    expected={row["role"]:row for row in provider["installed_candidate_files"]}
    module_path=Path(mujoco.__file__).resolve()
    binding=sys.modules.get("mujoco._functions")
    if binding is None or not getattr(binding,"__file__",None):
        raise CandidateBlocked("BLOCKED_PROVIDER: loaded _functions binding module is unavailable")
    binding_path=Path(binding.__file__).resolve()
    maps_path=Path("/proc/self/maps")
    if not maps_path.is_file():
        raise CandidateBlocked("BLOCKED_PROVIDER: /proc/self/maps unavailable for loaded-core identity")
    mapped=set()
    with maps_path.open(encoding="utf-8") as stream:
        for line in stream:
            fields=line.rstrip().split()
            if fields and fields[-1].startswith("/") and "libmujoco.so" in fields[-1]:
                mapped.add(Path(fields[-1].replace(" (deleted)","")).resolve())
    core_expected=Path(expected["native_core_library"]["path"]).resolve()
    if mapped != {core_expected}:
        raise CandidateBlocked(f"BLOCKED_PROVIDER: loaded MuJoCo core mapping mismatch: {sorted(map(str,mapped))}")
    checks=(("python_package_init",module_path),("python_binding_extension",binding_path),("native_core_library",core_expected))
    loaded=[]
    for role,path in checks:
        got=sha256_file(path)
        if path != Path(expected[role]["path"]).resolve() or got != expected[role]["sha256"]:
            raise CandidateBlocked(f"BLOCKED_PROVIDER: loaded {role} identity mismatch")
        loaded.append({"role":role,"path":str(path),"sha256":got})
    version_int=int(mujoco.mj_version())
    version_string=str(mujoco.mj_versionString())
    if version_int != provider["expected_native_version_int"] or version_string != provider["expected_native_version_string"]:
        raise CandidateBlocked(f"BLOCKED_PROVIDER: loaded native version {version_int}/{version_string}")
    if importlib.metadata.version("mujoco") != EXPECTED_MUJOCO or getattr(mujoco,"__version__",None) != EXPECTED_MUJOCO:
        raise CandidateBlocked("BLOCKED_PROVIDER: loaded Python package version mismatch")
    return {"package_metadata_version":importlib.metadata.version("mujoco"),"module_version":mujoco.__version__,
            "native_version_int":version_int,"native_version_string":version_string,"loaded_files":loaded,
            "mapped_core_libraries":[str(path) for path in sorted(mapped)],"platform":platform.platform(),
            "machine":platform.machine(),"backend":"CPU; no renderer, CUDA or EGL"}

def native_identity(mujoco: object, model: object, contract: dict, loaded: dict) -> dict:
    option_snapshot={}
    for name in dir(model.opt):
        if name.startswith("_"): continue
        try: value=getattr(model.opt,name)
        except Exception: continue
        if callable(value): continue
        if isinstance(value,(bool,int,float,str)): option_snapshot[name]=value
        elif hasattr(value,"tolist"): option_snapshot[name]=value.tolist()
        elif isinstance(value,(tuple,list)): option_snapshot[name]=list(value)
    return {"loaded_runtime":loaded,"model_timestep_s":float(model.opt.timestep),
            "model_gravity_m_s2":[float(v) for v in model.opt.gravity],"model_integrator":int(model.opt.integrator),
            "model_impratio":float(model.opt.impratio),"full_public_model_option_snapshot":option_snapshot}

def reset_trial(mujoco, model, data, maps, contract):
    mujoco.mj_resetData(model,data)
    home=contract["reset"]["arm_qpos_ctrl_rad"]
    for i,name in enumerate(contract["actuation"]["arm"]["joint_order"]):
        jid=maps["joint_ids"][name]; qadr=int(model.jnt_qposadr[jid]); dadr=int(model.jnt_dofadr[jid])
        data.qpos[qadr]=home[i]; data.qvel[dadr]=0.0; data.ctrl[maps["actuator_ids"][f"actuator{i+1}"]]=home[i]
    for i,name in enumerate(contract["actuation"]["hand"]["finger_joint_order"]):
        jid=maps["joint_ids"][name]; data.qpos[int(model.jnt_qposadr[jid])]=contract["reset"]["hand_finger_qpos_m"][i]
        data.qvel[int(model.jnt_dofadr[jid])]=0.0
    data.ctrl[maps["actuator_ids"]["probe_hand_actuator8"]]=contract["reset"]["hand_ctrl"]
    data.qfrc_applied[:]=0.0; data.xfrc_applied[:]=0.0
    before=snapshot_state(data); mujoco.mj_forward(model,data); after=snapshot_state(data)
    if before != after: raise CandidateCheckFailed("mj_forward during reset changed integration state")
    return after

def state_sample(mujoco, model, data, maps, trial, phase, index, site_id, hand_id, left_id, right_id, warning_base, contract):
    arrays={"qpos":data.qpos,"qvel":data.qvel,"qacc":data.qacc,"qacc_smooth":data.qacc_smooth,
            "ctrl":data.ctrl,"xpos":data.xpos,"xquat":data.xquat,"site_xpos":data.site_xpos,"site_xmat":data.site_xmat}
    finite={name:finite_array(value) for name,value in arrays.items()}
    row={"trial":trial,"phase":phase,"outer_index":index,"time_s":safe_number(data.time),
         **{name:safe_array(value) for name,value in arrays.items()},"finite_arrays":finite,
         "joint_positions_by_native_name":{},"hand_root_pos_world_m":safe_array(data.xpos[hand_id]),
         "hand_root_quat_world_wxyz":safe_array(data.xquat[hand_id]),
         "left_finger_body_pos_world_m":safe_array(data.xpos[left_id]),
         "right_finger_body_pos_world_m":safe_array(data.xpos[right_id]),
         "terminal_finger_body_positions_hand_frame_m":None,
         "mount":None,"ncon":int(data.ncon),"warning_counts":warning_counts(data)}
    for name,jid in maps["joint_ids"].items(): row["joint_positions_by_native_name"][name]=safe_number(data.qpos[int(model.jnt_qposadr[jid])])
    if all(finite.values()):
        row["mount"]=mount_measurement(mujoco,model,data,site_id,hand_id,contract)
        row["terminal_finger_body_positions_hand_frame_m"]={"left":hand_local_position(data,hand_id,left_id),"right":hand_local_position(data,hand_id,right_id)}
    row["warning_delta"]=[now-before for now,before in zip(row["warning_counts"],warning_base)]
    return row

def validate_sample(row, model, maps, contract):
    if not all(row["finite_arrays"].values()): raise CandidateCheckFailed(f"non-finite state captured at trial={row['trial']} phase={row['phase']} interval={row['outer_index']}: {row['finite_arrays']}")
    mount=row["mount"]; gate=contract["oracles"]["fixed_mount"]
    if mount["position_error_m"]>gate["position_error_max_m"] or mount["rotation_geodesic_error_rad"]>gate["rotation_geodesic_error_max_rad"]:
        raise CandidateCheckFailed(f"fixed mount oracle failed: {mount}")
    if any(value>0 for value in row["warning_delta"]): raise CandidateCheckFailed(f"native warning counter increased: {row['warning_delta']}")
    limit=contract["oracles"]["state_limits_clock"]["joint_range_overrun_max_rad_or_m"]
    for name,jid in maps["joint_ids"].items():
        q=float(row["joint_positions_by_native_name"][name]); lo,hi=[float(v) for v in model.jnt_range[jid]]
        enforce_joint_range(name,q,lo,hi,limit)

def vector_sub(a,b): return [float(a[i])-float(b[i]) for i in range(3)]
def vector_norm(a): return math.sqrt(sum(float(v)*float(v) for v in a))
def hand_local_position(data, hand_id, finger_id):
    r=matrix3(data.xmat[hand_id]); delta=vector_sub(data.xpos[finger_id],data.xpos[hand_id])
    return [sum(r[j][i]*delta[j] for j in range(3)) for i in range(3)]

def relative_body_position(row, field):
    r=quaternion_matrix(row["hand_root_quat_world_wxyz"])
    delta=vector_sub(row[field],row["hand_root_pos_world_m"])
    return [sum(r[j][i]*delta[j] for j in range(3)) for i in range(3)]

def current_rss_bytes():
    status=Path("/proc/self/status")
    if not status.is_file(): return None
    for line in status.read_text(encoding="utf-8").splitlines():
        if line.startswith("VmRSS:"): return int(line.split()[1])*1024
    return None

def output_bytes(output: Path) -> int:
    return sum(p.stat().st_size for p in output.iterdir() if p.is_file() and not p.name.endswith(".tmp"))

def write_evidence(output: Path, evidence: dict):
    path=output/"probe_evidence.json"; temp=output/"probe_evidence.json.tmp"
    with temp.open("w",encoding="utf-8") as stream:
        json.dump(evidence,stream,ensure_ascii=False,indent=2,allow_nan=False); stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
    temp.replace(path)

def write_hash_manifest(output: Path):
    rows=[]
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name!="sha256.manifest" and not path.name.endswith(".tmp"):
            rows.append(f"{sha256_file(path)}  {path.name}")
    with (output/"sha256.manifest").open("w",encoding="utf-8") as stream:
        stream.write("# SHA-256 index; excludes its own bytes and transient .tmp files.\n"+"\n".join(rows)+"\n")

def record_stage(evidence, trial_record, stage, data=None):
    trial_record["progress"]["stage"]=stage
    if data is not None:
        snap=snapshot_state(data); trial_record["progress"]["last_public_clock_s"]=snap["time_s"]
        trial_record["progress"]["last_public_state"]=snap
    evidence["current_stage"]=stage

def check_resources(contract, output, evidence, trial_record, stage):
    budgets=contract["budgets"]; rss=current_rss_bytes(); disk=output_bytes(output)
    sample={"stage":stage,"sampled_current_rss_bytes":rss,"sampled_output_directory_bytes":disk,"overshoot_possible_until_boundary":True}
    evidence["resource_samples"].append(sample); trial_record["resource_samples"].append(sample)
    if rss is not None and rss>budgets["sampled_rss_max_bytes"]: raise SampledResourceLimit(f"sampled current RSS exceeded cap after outer boundary: {rss}")
    if disk>budgets["incremental_evidence_max_bytes"]: raise SampledResourceLimit(f"sampled output bytes exceeded cap after outer boundary: {disk}")
    if time.monotonic()-evidence["started_monotonic"]>budgets["whole_probe_wall_budget_s"]: raise SampledResourceLimit("whole-probe 600 s elapsed-time sample exceeded")

def write_progress_row(stream, row):
    stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False,separators=(",",":"))+"\n"); stream.flush()

def run_load_balance_oracle(mujoco, np, model, data, hand_id, contract, trial, evidence, output):
    gate=contract["oracles"]["load_balance"]; state_gate=contract["oracles"]["external_load"]; state=snapshot_state(data)
    record={"initial_state":state,"calls":[],"phase":"pre-load balance diagnostic","qacc_smooth_units":"hinge rad/s^2; slide m/s^2"}
    trial["load_balance_oracle"]=record
    evidence["current_stage"]="trial_2_load_balance_no_load_forward"; trial["progress"]["stage"]=evidence["current_stage"]; write_evidence(output,evidence)
    data.xfrc_applied[:]=0.0; before=float(data.time); mujoco.mj_forward(model,data); evidence["mj_forward_calls"]+=1
    no_load=[float(v) for v in data.qacc_smooth]; record["calls"].append({"kind":"no_load_forward","clock_s":safe_number(data.time),"qacc_smooth":[safe_number(v) for v in no_load]})
    evidence["current_stage"]="trial_2_load_balance_loaded_forward"; trial["progress"]["stage"]=evidence["current_stage"]; write_evidence(output,evidence)
    load=contract["oracles"]["external_load"]
    data.xfrc_applied[hand_id,0:6]=[float(v) for v in load["force_world_N"]+load["torque_Nm"]]
    mujoco.mj_forward(model,data); evidence["mj_forward_calls"]+=1
    loaded=[float(v) for v in data.qacc_smooth]; record["calls"].append({"kind":"loaded_forward","clock_s":safe_number(data.time),"qacc_smooth":[safe_number(v) for v in loaded]})
    jacp=np.zeros((3,int(model.nv)),dtype=np.float64); jacr=np.zeros((3,int(model.nv)),dtype=np.float64)
    mujoco.mj_jacBodyCom(model,data,jacp,jacr,hand_id)
    dense=np.zeros((int(model.nv),int(model.nv)),dtype=np.float64)
    mujoco.mj_fullM(model,dense,data.qM)
    delta=np.asarray(loaded)-np.asarray(no_load); lhs=dense@delta; rhs=jacp.T@np.asarray(contract["oracles"]["external_load"]["force_world_N"],dtype=np.float64)
    residual=lhs-rhs; hinge_abs=float(np.max(np.abs(residual[:7]))); slide_abs=float(np.max(np.abs(residual[7:])))
    hinge_scale=float(np.max(np.abs(rhs[:7]))); slide_scale=float(np.max(np.abs(rhs[7:])))
    hinge_rel=hinge_abs/max(hinge_scale,gate["relative_denominator_floor_by_dof_unit"])
    slide_rel=slide_abs/max(slide_scale,gate["relative_denominator_floor_by_dof_unit"])
    projection=float(np.max(np.abs(rhs[:7])))
    if not np.isfinite(np.asarray(no_load)).all() or not np.isfinite(np.asarray(loaded)).all() or not np.isfinite(lhs).all() or not np.isfinite(rhs).all():
        record["non_finite_balance_arrays"]=True
    record["result"]={"mass_times_acceleration_delta_by_dof":safe_array(lhs),"jacobian_transpose_force_by_dof":safe_array(rhs),
      "residual_by_dof":safe_array(residual),"hinge_residual_abs_max_Nm":safe_number(hinge_abs),"slide_residual_abs_max_N":safe_number(slide_abs),
      "hinge_residual_relative":safe_number(hinge_rel),"slide_residual_relative":safe_number(slide_rel),"arm_projection_inf_norm_Nm":safe_number(projection),
      "dof_units":gate["dof_units"]}
    # Restore the pre-diagnostic public state: only wrench was perturbed; no integration occurred.
    evidence["current_stage"]="trial_2_load_balance_restore_forward"; trial["progress"]["stage"]=evidence["current_stage"]; write_evidence(output,evidence)
    data.xfrc_applied[:]=0.0; mujoco.mj_forward(model,data); evidence["mj_forward_calls"]+=1; restored=snapshot_state(data)
    record["calls"].append({"kind":"wrench_cleared_restore_forward","clock_s":safe_number(data.time),"qacc_smooth":safe_array(data.qacc_smooth)})
    record["restored_state"]=restored; record["wrench_cleared"]=bool(np.all(data.xfrc_applied==0.0))
    record["clock_unchanged"]=abs(float(data.time)-before)<=state_gate["state_and_force_clock_abs_delta_max_s"]
    record["state_unchanged"]=(vectors_equal(state["qpos"],restored["qpos"],state_gate["state_and_force_qpos_abs_delta_max"]) and vectors_equal(state["qvel"],restored["qvel"],state_gate["state_and_force_qvel_abs_delta_max"]) and vectors_equal(state["ctrl"],restored["ctrl"],state_gate["state_and_force_ctrl_abs_delta_max"]))
    write_evidence(output,evidence)
    if record.get("non_finite_balance_arrays"): raise CandidateCheckFailed("load balance diagnostic returned non-finite values")
    if not record["wrench_cleared"] or not record["clock_unchanged"] or not record["state_unchanged"]: raise CandidateCheckFailed("load diagnostic changed state/clock or failed to clear force")
    hinge_limit=gate["absolute_residual_max_per_dof"]+gate["relative_residual_max_per_dof"]*hinge_scale
    slide_limit=gate["absolute_residual_max_per_dof"]+gate["relative_residual_max_per_dof"]*slide_scale
    record["result"].update({"acceptance_metric":"absolute_plus_relative_group_inf", "hinge_residual_limit_Nm":hinge_limit, "slide_residual_limit_N":slide_limit})
    write_evidence(output,evidence)
    if hinge_abs>hinge_limit or slide_abs>slide_limit:
        raise CandidateCheckFailed(f"load generalized-force balance residual exceeded candidate tolerance: {record['result']}")
    if projection<=gate["arm_projection_inf_norm_min_Nm"]: raise CandidateCheckFailed(f"arm load projection degenerate: {projection} Nm")
    return record

def execute_native_candidate(contract, repo, output, evidence, step_stream):
    # First and only MuJoCo import is behind the complete approval and static-source gate.
    import numpy as np
    import mujoco
    evidence["native_imported"]=True
    evidence["current_stage"]="verify_loaded_native_identity"
    loaded=runtime_package_identity(mujoco,contract)  # Must finish before MjSpec construction/compile/step.
    evidence["loaded_runtime_identity"]=loaded; write_evidence(output,evidence)
    arm_path=repo/contract["source"]["arm_xml"]["path"]; hand_path=repo/contract["source"]["hand_xml"]["path"]
    parent=child=attached_frame=model=data=None
    stage="load_arm_spec"
    try:
        evidence["current_stage"]=stage; write_evidence(output,evidence); parent=mujoco.MjSpec.from_file(str(arm_path))
        stage="load_hand_spec"; evidence["current_stage"]=stage; write_evidence(output,evidence); child=mujoco.MjSpec.from_file(str(hand_path))
        site=parent.site("attachment_site")
        if site is None: raise CandidateCheckFailed("parent attachment_site missing")
        stage="attach_hand_at_attachment_site"; evidence["current_stage"]=stage; write_evidence(output,evidence); attached_frame=parent.attach(child,site=site,prefix=PREFIX)
        compensation=contract["assembly"]["returned_attach_frame_compensation"]
        attached_frame.pos=compensation["pos_m"]; attached_frame.quat=compensation["quat_wxyz"]
        stage="serialize_derived_source"; evidence["current_stage"]=stage; write_evidence(output,evidence); derived=output/"assembled_source.mjz"; parent.to_zip(str(derived))
        evidence["derived_source"]={"path":derived.name,"sha256":sha256_file(derived),"size_bytes":derived.stat().st_size}
        stage="compile_attached_model"; evidence["current_stage"]=stage; write_evidence(output,evidence); model=parent.compile()
        stage="verify_compiled_model"; evidence["current_stage"]=stage; write_evidence(output,evidence); mapping=verify_model(mujoco,model,contract); evidence["model_mapping"]=mapping
        evidence["native_model_identity"]=native_identity(mujoco,model,contract,loaded)
        data=mujoco.MjData(model)
        joint_ids={name:object_id(mujoco,model,mujoco.mjtObj.mjOBJ_JOINT,name) for name in contract["assembly"]["expected_native_joint_order"]}
        actuator_ids={name:object_id(mujoco,model,mujoco.mjtObj.mjOBJ_ACTUATOR,name) for name in contract["assembly"]["expected_native_actuator_order"]}
        maps={"joint_ids":joint_ids,"actuator_ids":actuator_ids}
        site_id=object_id(mujoco,model,mujoco.mjtObj.mjOBJ_SITE,"attachment_site")
        hand_id=object_id(mujoco,model,mujoco.mjtObj.mjOBJ_BODY,"probe_hand_hand")
        left_id=object_id(mujoco,model,mujoco.mjtObj.mjOBJ_BODY,"probe_hand_left_finger")
        right_id=object_id(mujoco,model,mujoco.mjtObj.mjOBJ_BODY,"probe_hand_right_finger")
        evidence["trials"]=[]; first_reset=None; budget=contract["budgets"]; dyn=contract["dynamics"]
        for trial_index in range(budget["trials"]):
            trial_no=trial_index+1; trial={"trial":trial_no,"load_enabled":trial_index==1,"status":"INCOMPLETE",
              "samples":[],"resource_samples":[],"progress":{"stage":"trial_registered","successful_mj_step_calls":0,
              "integrated_outer_intervals":0,"refreshed_outer_boundaries":0,"validated_outer_intervals":0,
              "completed_outer_boundaries":0,"last_public_clock_s":None,"last_public_state":None,"completed_phases":[]}}
            evidence["trials"].append(trial); record_stage(evidence,trial,"reset_started")
            reset_state=reset_trial(mujoco,model,data,maps,contract); evidence["mj_forward_calls"]+=1; warning_base=warning_counts(data)
            if any(value>0 for value in warning_base): raise CandidateCheckFailed(f"warning counter nonzero immediately after reset forward: {warning_base}")
            if first_reset is None: first_reset=reset_state
            elif reset_state!=first_reset: raise CandidateCheckFailed("repeated explicit reset state differs exactly")
            reset_row=state_sample(mujoco,model,data,maps,trial_no,"reset_forward",0,site_id,hand_id,left_id,right_id,warning_base,contract)
            trial["samples"].append(reset_row); validate_sample(reset_row,model,maps,contract)
            trial["reset_state"]=reset_state; record_stage(evidence,trial,"reset_forward_sampled",data); write_evidence(output,evidence)
            home=list(contract["reset"]["arm_qpos_ctrl_rad"]); substeps=budget["substeps_per_outer_interval"]
            outer_dt=dyn["outer_interval_s"]; step_dt=dyn["timestep_s"]
            def do_outer(phase, interval, arm_targets, hand_target, loaded_flag):
                stage_name=f"trial_{trial_no}_{phase}_interval_{interval}"
                record_stage(evidence,trial,stage_name,data)
                for i in range(7): data.ctrl[actuator_ids[f"actuator{i+1}"]]=arm_targets[i]
                data.ctrl[actuator_ids["probe_hand_actuator8"]]=hand_target
                data.xfrc_applied[:]=0.0
                if loaded_flag:
                    load=contract["oracles"]["external_load"]
                    data.xfrc_applied[hand_id,0:6]=[float(v) for v in load["force_world_N"]+load["torque_Nm"]]
                integrated_start=snapshot_state(data); start_time=float(data.time)
                for substep in range(substeps):
                    record_stage(evidence,trial,f"{stage_name}_mj_step_{substep+1}",data)
                    try:
                        mujoco.mj_step(model,data)
                    except Exception:
                        failed_stage=f"{stage_name}_mj_step_{substep+1}_raised"
                        evidence["current_stage"]=failed_stage
                        trial["progress"]["failed_step_call_state"]=snapshot_state(data)
                        trial["progress"]["stage"]=failed_stage
                        raise
                    trial["progress"]["successful_mj_step_calls"]+=1
                    evidence["successful_mj_step_calls"]+=1
                    trial["progress"]["last_public_clock_s"]=safe_number(data.time)
                    trial["progress"]["last_public_state"]=snapshot_state(data)
                    write_progress_row(step_stream,{"trial":trial_no,"phase":phase,"outer_interval":interval,"substep":substep+1,
                       "successful_mj_step_calls_total":evidence["successful_mj_step_calls"],"clock_s":safe_number(data.time),"state":snapshot_state(data)})
                integrated_end=snapshot_state(data); clock_delta=float(data.time)-start_time
                if abs(clock_delta-outer_dt)>contract["oracles"]["state_limits_clock"]["outer_clock_abs_error_max_s"]:
                    raise CandidateCheckFailed(f"outer integration clock delta {clock_delta} differs from {outer_dt}")
                trial["progress"]["integrated_outer_intervals"]+=1
                trial["progress"]["last_integrated_state"]=integrated_end
                trial["progress"]["last_integrated_clock_s"]=integrated_end["time_s"]
                before_refresh=snapshot_state(data); record_stage(evidence,trial,f"{stage_name}_post_step_pre_refresh",data)
                mujoco.mj_forward(model,data); evidence["mj_forward_calls"]+=1
                after_refresh=snapshot_state(data)
                post_refresh_stage=f"{stage_name}_post_refresh_validate"
                record_stage(evidence,trial,post_refresh_stage,data)
                trial["progress"]["refreshed_outer_boundaries"]+=1
                if before_refresh!=after_refresh: raise CandidateCheckFailed("nonintegrating outer-boundary mj_forward changed qpos/qvel/ctrl/time")
                row=state_sample(mujoco,model,data,maps,trial_no,phase,interval,site_id,hand_id,left_id,right_id,warning_base,contract)
                row["integration"]={"pre_outer_state":integrated_start,"post_step_pre_refresh_state":integrated_end,
                    "post_refresh_state":after_refresh,"clock_delta_s":clock_delta,"mj_step_calls_this_interval":substeps,
                    "qacc_phase":"post-refresh at the integrated end state","qacc_smooth_phase":"post-refresh unconstrained acceleration at integrated end state under the current control/wrench"}
                row["external_force_world_N"]=list(contract["oracles"]["external_load"]["force_world_N"]) if loaded_flag else [0.0,0.0,0.0]
                row["sample_validation"]={"stage":post_refresh_stage,"result":"PENDING"}
                trial["samples"].append(row)
                trial["progress"]["last_public_clock_s"]=after_refresh["time_s"]
                trial["progress"]["last_public_state"]=after_refresh
                # Persist the post-refresh sample before the acceptance oracle can raise.
                write_evidence(output,evidence)
                try:
                    validate_sample(row,model,maps,contract)
                except Exception as exc:
                    row["sample_validation"]={"stage":post_refresh_stage,"result":"FAIL",
                        "exception_type":type(exc).__name__,"message":str(exc)}
                    trial["progress"]["failed_sample"]={"phase":phase,"outer_interval":interval,
                        "validation_stage":post_refresh_stage,"exception_type":type(exc).__name__,"message":str(exc)}
                    trial["progress"]["stage"]=post_refresh_stage
                    evidence["current_stage"]=post_refresh_stage
                    write_evidence(output,evidence)
                    raise
                row["sample_validation"]["result"]="PASS"
                trial["progress"]["validated_outer_intervals"]+=1
                # Compatibility alias: this counts oracle-validated boundaries only.
                trial["progress"]["completed_outer_boundaries"]=trial["progress"]["validated_outer_intervals"]
                record_stage(evidence,trial,f"{stage_name}_post_refresh_validated",data)
                check_resources(contract,output,evidence,trial,stage_name); write_evidence(output,evidence)
                return row
            arm=contract["actuation"]["arm"]; curve=arm["command_curve"]; arm_rows=[]
            for i in range(1,curve["ramp_up"]+1):
                targets=list(home); targets[0]=curve["joint1_target_peak_rad"]*i/curve["ramp_up"]; arm_rows.append(do_outer("arm",i,targets,contract["reset"]["hand_ctrl"],False))
            for j in range(curve["hold_high"]): arm_rows.append(do_outer("arm",curve["ramp_up"]+j+1,list(home[:0])+[curve["joint1_target_peak_rad"]]+home[1:],contract["reset"]["hand_ctrl"],False))
            for j in range(1,curve["ramp_return"]+1):
                targets=list(home); targets[0]=curve["joint1_target_peak_rad"]*(1-j/curve["ramp_return"]); arm_rows.append(do_outer("arm",curve["ramp_up"]+curve["hold_high"]+j,targets,contract["reset"]["hand_ctrl"],False))
            for j in range(curve["hold_home"]): arm_rows.append(do_outer("arm",48+j+1,list(home),contract["reset"]["hand_ctrl"],False))
            start_joint1=float(trial["reset_state"]["qpos"][int(model.jnt_qposadr[joint_ids["joint1"]])])
            measured=[float(row["joint_positions_by_native_name"]["joint1"]) for row in arm_rows]
            peak=max(abs(q-start_joint1) for q in measured); return_error=abs(measured[-1]-home[0])
            root0=trial["samples"][0]["hand_root_quat_world_wxyz"]
            root_rot=max(rotation_error(quaternion_matrix(row["hand_root_quat_world_wxyz"]),quaternion_matrix(root0)) for row in arm_rows)
            trial["arm_motion"]={"joint1_peak_delta_rad":peak,"joint1_return_error_rad":return_error,"hand_root_rotation_peak_delta_rad":root_rot}
            arm_gate=contract["oracles"]["arm_motion"]
            if peak<arm_gate["joint1_measured_peak_delta_min_rad"] or return_error>arm_gate["return_error_max_rad"]: raise CandidateCheckFailed(f"arm motion oracle failed: {trial['arm_motion']}")
            if root_rot<contract["oracles"]["hand_root_during_arm_motion"]["rotation_geodesic_delta_min_rad"]: raise CandidateCheckFailed(f"hand root motion oracle failed: {root_rot}")
            trial["progress"]["completed_phases"].append("arm"); write_evidence(output,evidence)
            # Hand displacement is referenced to the measured state at the start of this phase.
            hand_start_q={name:float(data.qpos[int(model.jnt_qposadr[joint_ids[name]])]) for name in contract["actuation"]["hand"]["finger_joint_order"]}
            hand_start_left=hand_local_position(data,hand_id,left_id); hand_start_right=hand_local_position(data,hand_id,right_id)
            hand_rows=[]; hc=contract["actuation"]["hand"]["command_curve"]
            hand_close_ctrl=hc["close_ctrl"]; hand_open_ctrl=hc["open_ctrl"]
            for j in range(1,hc["close_ramp"]+1):
                ctrl=hand_open_ctrl+(hand_close_ctrl-hand_open_ctrl)*j/hc["close_ramp"]
                hand_rows.append(do_outer("hand",j,list(home),ctrl,False))
            for j in range(hc["hold_closed"]): hand_rows.append(do_outer("hand",hc["close_ramp"]+j+1,list(home),hand_close_ctrl,False))
            for j in range(1,hc["open_ramp"]+1):
                ctrl=hand_close_ctrl+(hand_open_ctrl-hand_close_ctrl)*j/hc["open_ramp"]
                hand_rows.append(do_outer("hand",hc["close_ramp"]+hc["hold_closed"]+j,list(home),ctrl,False))
            for j in range(hc["hold_open"]): hand_rows.append(do_outer("hand",48+j+1,list(home),hand_open_ctrl,False))
            j1,j2=contract["actuation"]["hand"]["finger_joint_order"]
            openings=[float(r["joint_positions_by_native_name"][j1])+float(r["joint_positions_by_native_name"][j2]) for r in hand_rows]
            close_min=min(openings[:32]); open_max=max(openings[32:]); mismatch=max(abs(float(r["joint_positions_by_native_name"][j1])-float(r["joint_positions_by_native_name"][j2])) for r in hand_rows)
            hand_start_row=arm_rows[-1]
            hand_start_left=hand_start_row["terminal_finger_body_positions_hand_frame_m"]["left"]
            hand_start_right=hand_start_row["terminal_finger_body_positions_hand_frame_m"]["right"]
            finger_delta={name:[float(r["joint_positions_by_native_name"][name])-hand_start_q[name] for r in hand_rows] for name in (j1,j2)}
            left_exc=max(vector_norm(vector_sub(r["terminal_finger_body_positions_hand_frame_m"]["left"],hand_start_left)) for r in hand_rows)
            right_exc=max(vector_norm(vector_sub(r["terminal_finger_body_positions_hand_frame_m"]["right"],hand_start_right)) for r in hand_rows)
            local_excursion={"left":left_exc,"right":right_exc}
            trial["hand_motion"]={"opening_min_closed_m":close_min,"opening_max_open_m":open_max,"opening_excursion_m":open_max-close_min,
               "equality_joint_mismatch_max_m":mismatch,"finger_joint_delta_from_hand_phase_start_m":finger_delta,
               "terminal_finger_hand_relative_excursion_m":local_excursion,"hand_phase_start_finger_qpos_m":hand_start_q}
            hg=contract["oracles"]["hand_motion"]
            if close_min>hg["close_opening_max_m"] or open_max<hg["open_opening_min_m"] or open_max-close_min<hg["opening_delta_min_m"] or mismatch>hg["equality_joint_mismatch_max_m"]:
                raise CandidateCheckFailed(f"hand motion oracle failed: {trial['hand_motion']}")
            if min(local_excursion.values())<hg["terminal_finger_body_displacement_min_m"]:
                raise CandidateCheckFailed(f"one finger joint did not move enough relative to phase start: {trial['hand_motion']}")
            trial["progress"]["completed_phases"].append("hand"); write_evidence(output,evidence)
            # Crucially snapshot before starting either load loop, not after it.
            record_stage(evidence,trial,"pre_load_state_capture",data)
            pre_load_state=snapshot_state(data); trial["pre_load_state"]=pre_load_state
            if trial_index==0: evidence["baseline_pre_load_state"]=pre_load_state
            else:
                record_stage(evidence,trial,"paired_pre_load_state_compare",data)
                baseline=evidence["baseline_pre_load_state"]
                if not (vectors_equal(pre_load_state["qpos"],baseline["qpos"],contract["oracles"]["external_load"]["pre_load_state_equality"]["qpos_abs_delta_max"]) and
                        vectors_equal(pre_load_state["qvel"],baseline["qvel"],contract["oracles"]["external_load"]["pre_load_state_equality"]["qvel_abs_delta_max"]) and
                        vectors_equal(pre_load_state["ctrl"],baseline["ctrl"],contract["oracles"]["external_load"]["pre_load_state_equality"]["ctrl_abs_delta_max"]) and
                        abs(float(pre_load_state["time_s"])-float(baseline["time_s"]))<=contract["oracles"]["external_load"]["pre_load_state_equality"]["clock_abs_delta_max_s"]):
                    raise CandidateCheckFailed("paired trial pre-load states differ")
                run_load_balance_oracle(mujoco,np,model,data,hand_id,contract,trial,evidence,output)
            trial["progress"]["completed_phases"].append("pre_load"); write_evidence(output,evidence)
            load_rows=[]
            for interval in range(1,65): load_rows.append(do_outer("load",interval,list(home),contract["reset"]["hand_ctrl"],trial_index==1))
            trial["load_end_state"]=snapshot_state(data); trial["progress"]["completed_phases"].append("load"); trial["status"]="COMPLETED"
            write_evidence(output,evidence)
        expected_steps=budget["trials"]*sum(item["outer_intervals_max"] for item in dyn["phases_per_trial"])*budget["substeps_per_outer_interval"]
        expected_forward=budget["trials"] + dyn["nonintegrating_calls"]["outer_boundary_refreshes"] + dyn["nonintegrating_calls"]["load_balance_forward_calls"]
        if evidence["successful_mj_step_calls"]!=expected_steps or evidence["mj_forward_calls"]!=expected_forward:
            raise CandidateCheckFailed(f"public-call count mismatch: steps={evidence['successful_mj_step_calls']}/{expected_steps}, forward={evidence['mj_forward_calls']}/{expected_forward}")
        baseline_samples=[row for row in evidence["trials"][0]["samples"] if row["phase"]=="load"]
        loaded_samples=[row for row in evidence["trials"][1]["samples"] if row["phase"]=="load"]
        deltas=[]
        for x,y in zip(baseline_samples,loaded_samples):
            deltas.append({name:float(y["joint_positions_by_native_name"][name])-float(x["joint_positions_by_native_name"][name]) for name in contract["actuation"]["arm"]["joint_order"]})
        evidence["load_trajectory_response_report_only"]={"per_outer_interval_arm_qpos_delta_rad":deltas,
            "max_abs_delta_rad":max(abs(v) for row in deltas for v in row.values()),"minimum_threshold":None,
            "reason":"No source-only evidence supports a positive minimum trajectory displacement; balance oracle tests applied load independently."}
        evidence["result"]="COMPLETED_CANDIDATE_SOURCE_DYNAMICS_PROBE"; evidence["current_stage"]="completed"
    except Exception as exc:
        if evidence.get("trials"):
            current=evidence["trials"][-1]
            current["progress"]["failure_state_snapshot"]=snapshot_state(data) if data is not None else None
            current["progress"]["stage"]=evidence.get("current_stage")
        evidence["result"]="FAIL"; evidence["failure"]={"stage":evidence.get("current_stage"),"type":type(exc).__name__,"message":str(exc),"traceback":traceback.format_exc()}
        raise
    finally:
        # MjData/MjModel/MjSpec have no explicit close method; release each owned reference once.
        data=None; model=None; attached_frame=None; child=None; parent=None; gc.collect()

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract",required=True); parser.add_argument("--output-dir",required=True)
    args=parser.parse_args(); output=Path(args.output_dir).resolve(); output.mkdir(parents=True,exist_ok=False)
    evidence={"task_id":"PHASE-II-01-R03A","slice":"R03a","attempt":"002","case_id":"INTERIOR_HAND_COMMANDS",
      "result":"INCOMPLETE","native_imported":False,
      "started_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"started_monotonic":time.monotonic(),
      "successful_mj_step_calls":0,"mj_forward_calls":0,"trials":[],"resource_samples":[]}
    contract=None; code=1; previous=signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM,lambda signum,frame:(_ for _ in ()).throw(TimeoutError("outer timeout sent SIGTERM")))
    with (output/"stdout.log").open("w",encoding="utf-8") as stdout, (output/"stderr.log").open("w",encoding="utf-8") as stderr, (output/"step_trace.jsonl").open("w",encoding="utf-8",buffering=1) as steps:
      try:
        with contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
          contract_path=Path(args.contract).resolve(); contract=json.loads(contract_path.read_text(encoding="utf-8"))
          evidence["input_contract_sha256"]=sha256_file(contract_path); repo=find_repo_root()
          validate_supported_candidate(contract)
          evidence["input_identity"]=repo_and_artifact_preflight(repo,contract_path,contract)
          evidence["provider_installed_candidate"]=static_provider_preflight(contract)
          evidence["static_source_preflight"]=static_source_preflight(repo,contract,contract_path)
          missing=approval_gate(contract,evidence["input_identity"]["candidate_basis_sha256"])
          if missing:
            evidence["result"]="BLOCKED_SCOPE"; evidence["execution_blockers"]=[f"missing/unbound explicit approval: {item}" for item in missing]; code=2
          else:
            evidence["execution_state"]="RUNNING_NATIVE_PROBE"; evidence["current_stage"]="native_import_after_approval"
            write_evidence(output,evidence)
            execute_native_candidate(contract,repo,output,evidence,steps); code=0
      except CandidateBlocked as exc:
        evidence["result"]="BLOCKED_PROVIDER" if "BLOCKED_PROVIDER" in str(exc) else "BLOCKED_CORE_OR_SCOPE"
        evidence["failure"]={"stage":evidence.get("current_stage","preflight"),"type":type(exc).__name__,"message":str(exc),"traceback":traceback.format_exc()}; code=2
      except ImportError as exc:
        evidence["result"]="BLOCKED_PROVIDER"; evidence["failure"]={"stage":"native_import","type":type(exc).__name__,"message":str(exc),"traceback":traceback.format_exc()}; code=2
      except SampledResourceLimit as exc:
        evidence["result"]="RESOURCE_LIMIT_STOPPED"; evidence["failure"]={"stage":evidence.get("current_stage"),"type":type(exc).__name__,"message":str(exc),"traceback":traceback.format_exc()}; code=3
      except TimeoutError as exc:
        evidence["result"]="TIMEOUT_OR_TERMINATED"; evidence["failure"]={"stage":evidence.get("current_stage"),"type":type(exc).__name__,"message":str(exc),"traceback":traceback.format_exc()}; code=124
      except Exception as exc:
        if "failure" not in evidence: evidence["failure"]={"stage":evidence.get("current_stage","execution"),"type":type(exc).__name__,"message":str(exc),"traceback":traceback.format_exc()}
        evidence["result"]="FAIL"; code=1
      finally:
        evidence["ended_utc"]=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()); evidence["wall_seconds_observed"]=time.monotonic()-evidence["started_monotonic"]
        evidence["peak_rss_bytes_observed"]=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
        evidence["final_current_rss_bytes_observed"]=current_rss_bytes(); evidence["output_bytes_observed"]=output_bytes(output)
        evidence["python"]={"version":sys.version.split()[0],"executable":sys.executable,"platform":platform.platform()}
        if evidence.get("result")=="INCOMPLETE": evidence["result"]="INCOMPLETE"
        try: write_evidence(output,evidence)
        except Exception: stderr.write("FAILED TO SAVE FINAL EVIDENCE\n"+traceback.format_exc()); code=1
    signal.signal(signal.SIGTERM,previous); write_hash_manifest(output); return code

if __name__ == "__main__":
    raise SystemExit(main())
