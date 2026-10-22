"""诊断意义：对 PickCube R1 reset-force 首样做受限双 Provider native 验收。

执行角色：诊断性真实 native probe；不是 C02b 完整验收或 Qualification。
受测来源：PickCube production-r1 legacy selected route、GeoPhys CPU、MuJoCo CPU。
运行方式：分别运行 --provider geophys 与 --provider mujoco，写入独立 ignored JSON 文件。

Run once per provider in a fresh process. This exercises the existing selected
PickCube source and R1 Controller route; it does not admit the structured
plan-bound raw-force requirement or qualify C02b.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

from task_env.tasks import PickCubeReferenceEnv


def _jsonable(value):
    if hasattr(value, "to_mapping"):
        return value.to_mapping()
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _close_action(env):
    ee = env.state.pose_world["panda-v1/ee"]
    return np.asarray((*ee.position, *ee.quaternion_wxyz, -1.0), dtype=np.float64)


def _actuator_law(xml: str):
    root = ET.fromstring(xml)
    actuator = root.find("./actuator/general[@name='actuator8']")
    if actuator is None:
        raise AssertionError("PickCube source lacks actuator8")
    defaults = root.find(f"./default/default[@class='{actuator.get('class', '')}']/general")
    attributes = {} if defaults is None else dict(defaults.attrib)
    attributes.update(actuator.attrib)
    if attributes.get("dyntype", "none") != "none":
        raise AssertionError("S2 oracle only accepts the audited non-activation actuator8 law")
    if attributes.get("gaintype", "fixed") != "fixed":
        raise AssertionError("unexpected actuator8 gain law")
    if attributes.get("biastype", "none") != "affine":
        raise AssertionError("unexpected actuator8 bias law")
    tendon_name = actuator.get("tendon")
    tendon = root.find(f"./tendon/fixed[@name='{tendon_name}']")
    if tendon is None:
        raise AssertionError("actuator8 tendon transmission is missing")
    coefficients = tuple(
        (str(joint.get("joint")), float(joint.get("coef", "1")))
        for joint in tendon.findall("joint")
    )
    return {
        "actuator_id": "actuator8",
        "transmission": tendon_name,
        "coefficients": coefficients,
        "gain_type": attributes.get("gaintype", "fixed"),
        "gainprm": tuple(float(item) for item in attributes["gainprm"].split()),
        "bias_type": attributes.get("biastype", "none"),
        "biasprm": tuple(float(item) for item in attributes["biasprm"].split()),
        "dyntype": attributes.get("dyntype", "none"),
        "ctrlrange": tuple(float(item) for item in attributes["ctrlrange"].split()),
        "source_forcerange": tuple(float(item) for item in attributes["forcerange"].split()),
    }


def _reset_force_oracle(law, state, measurement, force_limit_N):
    q = state.joint_position
    qd = state.joint_velocity
    length = sum(
        coefficient * float(q[f"panda-v1/{joint}"])
        for joint, coefficient in law["coefficients"]
    )
    velocity = sum(
        coefficient * float(qd[f"panda-v1/{joint}"])
        for joint, coefficient in law["coefficients"]
    )
    ctrl_low, ctrl_high = law["ctrlrange"]
    ctrl = float(np.clip(measurement.actuator_ctrl, ctrl_low, ctrl_high))
    gain = law["gainprm"][0]
    b0, b_length, b_velocity = law["biasprm"][:3]
    unsaturated = gain * ctrl + b0 + b_length * length + b_velocity * velocity
    signed_force = float(np.clip(unsaturated, -force_limit_N, force_limit_N))
    return {
        "length_m": length,
        "velocity_m_per_s": velocity,
        "ctrl": ctrl,
        "unsaturated_signed_force_N": unsaturated,
        "expected_signed_force_N": signed_force,
        "force_limit_N": float(force_limit_N),
    }


def _state_signature(state):
    return {
        "control_step": int(state.control_step),
        "simulation_time_s": float(state.simulation_time),
        "joint_position": dict(state.joint_position),
        "joint_velocity": dict(state.joint_velocity),
    }


def _assert_same_state(before, after):
    if before["control_step"] != after["control_step"]:
        raise AssertionError("readback changed the control clock")
    if before["simulation_time_s"] != after["simulation_time_s"]:
        raise AssertionError("readback changed the simulation clock")
    for group in ("joint_position", "joint_velocity"):
        if before[group].keys() != after[group].keys() or not np.allclose(
            list(before[group].values()), list(after[group].values()), rtol=0.0, atol=1e-9
        ):
            raise AssertionError(f"readback changed {group}")


def run_geophys(env):
    law = _actuator_law(env.value["source"].scene_source.xml)
    if env.value["source"].scene_source.source_id != "task-env-pick-cube":
        raise AssertionError("the probe did not materialize the existing PickCube source")
    if env.artifact.timebase.physics_dt != 0.002 or env.artifact.timebase.control_substeps != 5:
        raise AssertionError("PickCube S2 must use the audited 5 x 2 ms control interval")

    initial = env.session.actuator_force_measurement
    if not initial.valid or initial.phase != "reset_forward" or initial.native_step_index != 0:
        raise AssertionError("initial PickCube force sample failed its reset-forward gate")
    initial_episode_id = initial.episode_id
    initial_feedback = float(env.feedback.gripper.closing_force_N)
    initial_state = _state_signature(env.state)

    applied = []
    original_apply = env.session.apply_control

    def capture_apply(target):
        acknowledgement = original_apply(target)
        applied.append({"target": target, "acknowledgement": acknowledgement})
        return acknowledgement

    env.session.apply_control = capture_apply
    close_trials = []
    for _ in range(5):
        env.step(_close_action(env))
        measurement = env.session.actuator_force_measurement
        close_trials.append({
            "state": _state_signature(env.state),
            "measurement": _jsonable(measurement),
            "closing_force_N": float(env.feedback.gripper.closing_force_N),
        })
        if abs(float(measurement.signed_force_N)) > 1.0e-4:
            break
    if not close_trials or abs(close_trials[-1]["measurement"]["signed_force_N"]) <= 1.0e-4:
        raise AssertionError("real PickCube R1 close did not produce a nonzero signed force sample")
    if not applied:
        raise AssertionError("R1 target was not applied through the existing session")
    force_limit_N = float(applied[-1]["acknowledgement"].gripper_force_limit_N)
    if force_limit_N != float(env.controller.gripper_config.force_limit_N):
        raise AssertionError("R1 force limit differs from the applied acknowledgement")
    nonzero_measurement = env.session.actuator_force_measurement
    nonzero_sample = _jsonable(nonzero_measurement)
    nonzero_sample["reset_sample_id"] = env.sample.sample_id

    # A second read at the same completed boundary is read-only for state,
    # clocks, and R1 memory.
    before_read_state = _state_signature(env.state)
    before_read_memory = _jsonable(env.controller.memory())
    before_read_sample = env.session.actuator_force_measurement
    reread_feedback = env.session.control_feedback(env.state)
    after_read_state = _state_signature(env.session.snapshot())
    after_read_memory = _jsonable(env.controller.memory())
    _assert_same_state(before_read_state, after_read_state)
    if before_read_memory != after_read_memory:
        raise AssertionError("force readback changed R1 Controller memory")
    if reread_feedback.gripper.closing_force_N != max(0.0, -before_read_sample.signed_force_N):
        raise AssertionError("raw signed force did not use the existing canonical projection")
    if before_read_sample.phase != "native_step_pre_integration":
        raise AssertionError("completed-step force has the wrong evaluation phase")
    if before_read_sample.native_step_index != int(env.state.control_step) * 5:
        raise AssertionError("completed native sample index differs from the control clock")
    if before_read_sample.native_sample_time_s != (before_read_sample.native_step_index - 1) * 0.002:
        raise AssertionError("pre-integration force sample time is wrong")

    reset_trials = []
    previous_episode = before_read_sample.episode_id
    previous_sequence = before_read_sample.sample_sequence
    previous_revision = before_read_sample.state_revision
    for reset_index in range(2):
        realized = env.session.reset(env.sample)
        state = env.session.snapshot()
        feedback = env.session.control_feedback(state)
        measurement = env.session.actuator_force_measurement
        if not measurement.valid or measurement.phase != "reset_forward":
            raise AssertionError("reset did not publish a valid reset-forward force sample")
        if measurement.native_step_index != 0 or measurement.native_sample_time_s != 0.0:
            raise AssertionError("reset sample retained a prior native step or time")
        if measurement.episode_id == previous_episode:
            raise AssertionError("reset reused the prior episode identity")
        if measurement.reset_sample_id != env.sample.sample_id or realized.reset_sample_id != env.sample.sample_id:
            raise AssertionError("reset force sample belongs to another ResetSample")
        if measurement.sample_sequence <= previous_sequence:
            raise AssertionError("reset reused or rewound the native sample sequence")
        if measurement.state_revision <= previous_revision:
            raise AssertionError("reset force measurement does not reflect restored state writes")
        if measurement.actuator_id != "actuator8" or measurement.force_unit != "N":
            raise AssertionError("reset sample identity or unit is wrong")
        if measurement.actuator_ctrl is None or measurement.signed_force_N is None:
            raise AssertionError("reset sample omitted actual actuator input or signed force")
        oracle = _reset_force_oracle(law, state, measurement, force_limit_N)
        if abs(measurement.signed_force_N - oracle["expected_signed_force_N"]) > 0.02:
            raise AssertionError(
                "reset-forward force differs from the source-derived actuator law: "
                f"sample={measurement.signed_force_N}, oracle={oracle['expected_signed_force_N']}"
            )
        if state.control_step != 0 or state.simulation_time != 0.0:
            raise AssertionError("same-session reset advanced physics")
        r1_before = _jsonable(env.controller.memory())
        env.controller.reset(state, feedback)
        r1_after_reset = _jsonable(env.controller.memory())
        reread = env.session.control_feedback(state)
        r1_after_read = _jsonable(env.controller.memory())
        if r1_after_reset != r1_after_read:
            raise AssertionError("reset force readback changed R1 memory")
        env.state, env.feedback = state, feedback
        env.obs, env.info, env.evaluation = env.observation(state)
        env._stopped = False
        env._episode_mode = None
        reset_trials.append({
            "reset_index": reset_index + 1,
            "realized_reset_sample_id": realized.reset_sample_id,
            "state": _state_signature(state),
            "r1_feedback_closing_force_N": float(feedback.gripper.closing_force_N),
            "measurement": _jsonable(measurement),
            "oracle": oracle,
            "r1_memory_before_reset": r1_before,
            "r1_memory_after_reset": r1_after_reset,
            "r1_memory_after_read": r1_after_read,
        })
        previous_episode = measurement.episode_id
        previous_sequence = measurement.sample_sequence
        previous_revision = measurement.state_revision

    # The first actual closing compute in the last reset episode receives the
    # adapter-validated current reset sample and then advances the real R1.
    first_closing_sample = env.session.actuator_force_measurement
    first_closing_feedback = env.feedback
    compute_capture = {}
    original_compute = env.controller.compute

    def capture_compute(state, feedback, requested):
        compute_capture["measurement"] = _jsonable(env.session.actuator_force_measurement)
        compute_capture["feedback_closing_force_N"] = float(feedback.gripper.closing_force_N)
        compute_capture["memory_before"] = _jsonable(env.controller.memory())
        canonical, target = original_compute(state, feedback, requested)
        compute_capture["target"] = _jsonable(target)
        compute_capture["memory_after"] = _jsonable(env.controller.memory())
        return canonical, target

    env.controller.compute = capture_compute
    env.step(_close_action(env))
    env.controller.compute = original_compute
    expected_feedback = max(0.0, -float(first_closing_sample.signed_force_N))
    if compute_capture["feedback_closing_force_N"] != expected_feedback:
        raise AssertionError("first closing compute did not consume the current signed reset sample")
    if compute_capture["measurement"]["episode_id"] != first_closing_sample.episode_id:
        raise AssertionError("first closing compute consumed a sample from another reset")
    if first_closing_feedback.gripper.closing_force_N != expected_feedback:
        raise AssertionError("selected R1 reset feedback differs from the signed sample projection")

    return {
        "result": "PASS",
        "provider": "geophys",
        "backend": "cpu",
        "native_execution_backend": "Taichi CPU x64",
        "task_id": env.artifact.task_id,
        "artifact_identity": env.artifact.identity_hash,
        "reset_sample_id": env.sample.sample_id,
        "task_seed": env.sample.task_seed,
        "source_id": env.value["source"].scene_source.source_id,
        "source_xml_sha256": env.value["resolved_configuration"]["source_xml_sha256"],
        "controller": {
            "class": type(env.controller).__name__,
            "identity": env.controller.identity,
            "config": _jsonable(env.controller.gripper_config),
        },
        "timebase": env.artifact.timebase.to_mapping(),
        "actuator_law": {
            **law,
            "coefficients": list(law["coefficients"]),
            "refresh_oracle_atol_N": 0.02,
        },
        "initial_reset_sample": {
            "measurement": _jsonable(initial),
            "closing_force_N_consumed_by_controller_reset": initial_feedback,
            "state": initial_state,
        },
        "nonzero_completed_step_sample": nonzero_sample,
        "nonzero_r1_close_trials": close_trials,
        "completed_step_read_only_check": {
            "before_state": before_read_state,
            "after_state": after_read_state,
            "controller_memory_before": before_read_memory,
            "controller_memory_after": after_read_memory,
            "canonical_closing_force_N": float(reread_feedback.gripper.closing_force_N),
        },
        "same_session_resets": reset_trials,
        "first_closing_compute_after_final_reset": compute_capture,
        "execution_note": (
            "native_step_index is directly published by the GeoPhys rigid solver completion hook; "
            "it is not inferred from the control clock. Force phase is pre-integration for the "
            "last native step completed at each outer boundary."
        ),
        "admission_note": (
            "This is the existing selected PickCube production-r1 route. It does not satisfy or "
            "alter plan-bound structured raw-force admission, which remains blocked."
        ),
    }


def run_mujoco(env):
    if env.value["source"].scene_source.source_id != "task-env-pick-cube":
        raise AssertionError("the probe did not materialize the existing PickCube source")
    if env.artifact.timebase.physics_dt != 0.002 or env.artifact.timebase.control_substeps != 5:
        raise AssertionError("PickCube S2 must use the audited 5 x 2 ms control interval")
    initial_state = _state_signature(env.state)
    initial_feedback = float(env.feedback.gripper.closing_force_N)
    env.step(_close_action(env))
    if env.state.control_step != 1 or abs(env.state.simulation_time - 0.01) > 1e-9:
        raise AssertionError("MuJoCo did not complete one 100 Hz / five-substep interval")
    after = {
        "state": _state_signature(env.state),
        "closing_force_N": float(env.feedback.gripper.closing_force_N),
    }
    return {
        "result": "PASS",
        "provider": "mujoco",
        "backend": "cpu",
        "task_id": env.artifact.task_id,
        "artifact_identity": env.artifact.identity_hash,
        "reset_sample_id": env.sample.sample_id,
        "task_seed": env.sample.task_seed,
        "source_id": env.value["source"].scene_source.source_id,
        "source_xml_sha256": env.value["resolved_configuration"]["source_xml_sha256"],
        "controller": {
            "class": type(env.controller).__name__,
            "identity": env.controller.identity,
            "config": _jsonable(env.controller.gripper_config),
        },
        "timebase": env.artifact.timebase.to_mapping(),
        "reset_boundary": {
            "state": initial_state,
            "canonical_closing_force_N": initial_feedback,
            "source_semantics": "existing MuJoCo adapter runs mj_forward and caches actuator force on reset",
        },
        "completed_step_boundary": {
            **after,
            "source_semantics": (
                "existing MuJoCo adapter uses its completed-step pre-integration force cache; "
                "the public legacy API exposes canonical feedback, not raw sample metadata"
            ),
        },
        "execution_note": "MuJoCo comparison is semantic; force values need not match GeoPhys.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("geophys", "mujoco"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    env = PickCubeReferenceEnv(provider=args.provider, backend="cpu", horizon=6000)
    try:
        env.reset(seed=31)
        result = run_geophys(env) if args.provider == "geophys" else run_mujoco(env)
        result["process_id"] = __import__("os").getpid()
        result["python_version"] = __import__("sys").version
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps(result, indent=2, sort_keys=True))
    finally:
        env.close()


if __name__ == "__main__":
    main()
