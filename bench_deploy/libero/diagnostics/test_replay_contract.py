"""Provider-free contracts for the current replay lifecycle and independent reader."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from task_env.controllers.canonical.contracts import (
    AppliedMixedActuatorCommandV1, MixedActuatorCommandV1,
)
from bench_deploy.libero.tasks.solution import solution_identity_v8
from bench_deploy.libero.trajectory import reader
from bench_deploy.libero.trajectory.worker import run_libero_replay


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _reseal(result):
    payload = {key: value for key, value in result.items() if key != "result_sha256"}
    result["result_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()


def _bundle(tmp_path, monkeypatch, *, mode="frozen-actions"):
    raw = b"synthetic-h5"
    h5_path = tmp_path / "trajectory.h5"
    h5_path.write_bytes(raw)
    schema = {"schema_id": "pose-v1"}
    action = [0.0] * 7 + [1.0]
    source_xml = b"<mujoco/>"
    source_id, episode_id, reset_id, materialization = "libero/source", "episode-1", "reset-1", "provider-1"
    task_hash, closure_digest, controller_id, plan_id = "a" * 64, "b" * 64, "c" * 64, "d" * 64
    manifest = [
        {"path": name, "size_bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
        for name, value in (("canonical-source.xml", source_xml), ("scene.xml", source_xml))
    ]
    closure_digest = hashlib.sha256(_canonical({"schema_version": "source-closure-v1", "files": manifest})).hexdigest()
    target = MixedActuatorCommandV1(
        "mixed-actuator-command-v1", plan_id, task_hash, source_id, closure_digest,
        controller_id, materialization, episode_id, reset_id, 0, 1, 0.05,
        {"joint1": 0.1, "finger_joint1": 0.02}, {"joint1": "N*m", "finger_joint1": "m"},
    )
    ack = AppliedMixedActuatorCommandV1(
        "applied-mixed-actuator-command-v1", target.identity_hash, "mujoco",
        dict(target.channel_values), dict(target.channel_units), False, "named-source-channels",
    )
    components = [f"a{index}" for index in range(8)]
    writer = {
        "writer_id": "libero-controller", "action_schema_id": schema["schema_id"],
        "components": components, "groups": [],
        "requested_action": {"values": action},
        "canonical_action": {"schema_version": "pose-v1", "interpreted_values": action},
        "controller_target": {"schema_version": target.schema_version,
                              "payload": target.to_mapping(), "identity_hash": target.identity_hash},
        "applied_control": {"schema_version": ack.schema_version,
                             "payload": ack.to_mapping(), "target_hash": ack.target_hash},
    }
    writer["groups"] = [{"entity_id": "panda-v1", "group_id": "mixed-actuation",
                         "action_components": components}]
    control = {"request": {"groups": [{"values": action}]}, "writer_controls": [writer]}
    contexts = [
        {"schema_version": "libero-boundary-v1", "control_step": index,
         "episode_id": episode_id, "source_id": source_id,
         "source_closure_digest": closure_digest, "reset_sample_id": reset_id,
         "provider_materialization_id": materialization}
        for index in (0, 1)
    ]
    solution_id = None
    resolver_id = None
    solution_schema = None
    if mode == "solution-v8":
        resolver_id = "f" * 64
        solution_id = solution_identity_v8(
            hashlib.sha256(source_xml).hexdigest(), closure_digest,
            arm_resolver_identity=resolver_id,
        )
        solution_schema = "libero-bowl-to-plate-solution-v8"
    env_meta = {"action_schema": schema, "task_context": {
        "task_artifact_identity_hash": task_hash, "source_id": source_id,
        "source_xml_sha256": hashlib.sha256(source_xml).hexdigest(),
        "source_closure_digest": closure_digest, "controller_identity": controller_id,
        "episode_id": episode_id, "reset_sample_id": reset_id,
        "provider_materialization_id": materialization, "solution_identity": solution_id,
    }}
    outcome = SimpleNamespace(
        episode_id=episode_id, final_boundary=1, end_reason="frozen_replay_complete",
        task_success=False,
    )
    monkeypatch.setattr(reader, "load_structured_control_records_h5", lambda _: {
        "transition_count": 1, "observation_count": 2, "outcome": outcome,
        "env_meta": env_meta, "boundary_contexts": contexts,
        "structured_controls": (SimpleNamespace(to_mapping=lambda: control),),
    })
    episode = {
        "episode_id": episode_id, "task_uid": "libero/task1", "provider": "mujoco",
        "task_artifact_identity_hash": task_hash, "source_id": source_id,
        "source_xml_sha256": hashlib.sha256(source_xml).hexdigest(),
        "source_closure_digest": closure_digest, "controller_identity": controller_id,
        "controller_profile_id": "osc-v6", "action_schema": schema,
        "solution_schema_version": solution_schema, "solution_identity": solution_id,
        "arm_resolver_identity": resolver_id,
        "reset_sample": {"sample_id": reset_id}, "action_trace": [
            {"index": 0, "action": action, "control_step": 0, "simulation_time_s": 0.05,
             "terminated": False, "truncated": False},
        ],
        "task_success": False, "predicate": {},
        "episode_end": {"outcome": {"end_reason": "frozen_replay_complete"}},
        "runtime_progress": {"provider_materialization_id": materialization},
        "source_receipt": {
            "schema_version": "runtime-execution-source-receipt-v1", "source_id": source_id,
            "canonical_xml_sha256": hashlib.sha256(source_xml).hexdigest(),
            "importer_xml_sha256": hashlib.sha256(source_xml).hexdigest(),
            "source_closure_digest": closure_digest, "files": manifest,
        },
        "recording": {"relative_path": "trajectory.h5", "bytes": len(raw),
                      "sha256": hashlib.sha256(raw).hexdigest(),
                      "transition_count": 1, "observation_count": 2},
    }
    result = {
        "schema_version": "libero-replay-result-v1", "status": "complete", "mode": mode,
        "task_uid": episode["task_uid"], "seed": 19, "row_index": 0,
        "episode": episode, "final_session_close_receipt": {
            "session_closed": True, "cleanup_completed": True,
            "cleanup_error": None, "task_resource_close_error": None,
        },
        "worker_error": None, "close_error": None,
    }
    _reseal(result)
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")
    return result, result_path, control, contexts, outcome


class _WorkerEnv:
    def __init__(self, root, *, fail_step=False):
        self.root, self.fail_step = root, fail_step
        self.provider = "mujoco"
        self.artifact = SimpleNamespace(task_id="libero/task1", identity_hash="a" * 64,
                                        timebase=SimpleNamespace(control_substeps=25))
        self.controller = SimpleNamespace(identity="c" * 64, profile_id="osc-v6")
        self.value = {"action_schema": {"schema_id": "pose-v1"}, "source": SimpleNamespace(
            execution_source_receipt=SimpleNamespace(
                canonical_xml_sha256="e" * 64,
                to_mapping=lambda: {"schema_version": "runtime-execution-source-receipt-v1"},
            ),
        )}
        self.close_receipt = None
        self.finish_reasons = []

    def reset(self, **_):
        return {}, {"episode_id": "episode-1"}

    def start_recording(self, path):
        self.path = path

    def step(self, _action):
        if self.fail_step:
            raise RuntimeError("partial replay failure")
        return {}, 0.0, False, False, {
            "control_step": 1, "simulation_time_s": 0.05,
            "episode_end_v1": {"outcome": {"end_reason": "frozen_replay_complete"}},
        }

    def finish_recording(self, reason):
        self.finish_reasons.append(reason)
        self.path.write_bytes(b"h5")
        return {"path": self.path, "transition_count": 1, "observation_count": 2}

    def get_runtime_progress_receipt(self):
        return {"episode_id": "episode-1", "control_step": 1, "native_step_count": 25}

    def close(self):
        self.close_receipt = {"session_closed": True, "cleanup_completed": True}


def test_runner_closes_cleanly_and_marks_partial_step_failure(tmp_path):
    env = _WorkerEnv(tmp_path / "success")
    good = run_libero_replay(env, output_dir=tmp_path / "success", action_sequence=[[0] * 8])
    assert good["status"] == "complete" and env.close_receipt["session_closed"]
    failed_env = _WorkerEnv(tmp_path / "failure", fail_step=True)
    failed = run_libero_replay(failed_env, output_dir=tmp_path / "failure", action_sequence=[[0] * 8])
    assert failed["status"] == "failed" and failed_env.finish_reasons == ["execution_fault"]
    assert failed_env.close_receipt["session_closed"]


@pytest.mark.parametrize("case", ["request", "target", "ack", "source", "boundary", "unavailable", "close", "counts"])
def test_independent_reader_rejects_replay_semantic_tampering(tmp_path, monkeypatch, case):
    result, result_path, control, contexts, outcome = _bundle(tmp_path, monkeypatch)
    writer = control["writer_controls"][0]
    if case == "request":
        control["request"]["groups"][0]["values"] = [1.0] + [0.0] * 7
    elif case == "target":
        writer["controller_target"]["payload"]["channel_values"]["joint1"] = 2.0
    elif case == "ack":
        writer["applied_control"]["payload"]["target_hash"] = "e" * 64
    elif case == "source":
        result["episode"]["source_id"] = "tampered-source"
    elif case == "boundary":
        contexts[-1]["control_step"] = 0
    elif case == "unavailable":
        result["episode"]["task_success"] = True
        result["episode"]["predicate"] = {"predicate": {"status": "unavailable"}}
        outcome.task_success = True
    elif case == "close":
        result["final_session_close_receipt"]["session_closed"] = False
    else:
        monkeypatch.setattr(reader, "load_structured_control_records_h5", lambda _: {
            "transition_count": 1, "observation_count": 1, "outcome": outcome,
            "env_meta": {"action_schema": {"schema_id": "pose-v1"}, "task_context": {}},
            "boundary_contexts": contexts, "structured_controls": (),
        })
    _reseal(result)
    result_path.write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises((ValueError, TypeError)):
        reader.consume_libero_replay_result(result_path)


def test_independent_reader_recomputes_the_v8_identity_hash(tmp_path, monkeypatch):
    _, result_path, _, _, _ = _bundle(tmp_path, monkeypatch, mode="solution-v8")
    assert reader.consume_libero_replay_result(result_path)["status"] == "verified_complete"
