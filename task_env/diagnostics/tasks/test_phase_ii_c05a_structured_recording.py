"""Versioned structured action/event/outcome storage; not a replay qualification."""

from __future__ import annotations

import copy
import gzip
import json
from pathlib import Path

import numpy as np
import pytest

from task_env.controllers.canonical.contracts import (
    AppliedCanonicalControl,
    CanonicalControlTarget,
    digest,
)
from task_env.controllers.canonical.feedback import CanonicalControlFeedback
from task_env.artifacts.contracts import CanonicalStateView
from task_env.recorders import (
    RecorderConfig,
    TransitionRecorder,
    load_structured_control_records_h5,
    load_structured_training_actions_h5,
)
from task_env.trajectory.canonical.contracts import (
    BoundaryRecord,
    CanonicalTrajectoryV1,
    EpisodeMetadata,
    TransitionRecord,
)
from task_env.trajectory.canonical.episode import (
    BoundaryEventV1,
    EpisodeOutcomeV1,
    StructuredControlTransitionV1,
    single_writer_training_actions,
)
from task_env.trajectory.canonical.execution import (
    FILE_SCHEMA,
    SCHEMA,
    STRUCTURED_FILE_SCHEMA,
    STRUCTURED_SCHEMA,
    ExecutionRecorder,
    expand_snapshot,
    load as load_execution,
    save as save_execution,
    training_actions as execution_training_actions,
    validate as validate_execution,
)
from task_env.trajectory.canonical.h5 import (
    FILE_SCHEMA as CANONICAL_FILE_SCHEMA,
    FILE_SCHEMA_V1 as CANONICAL_FILE_SCHEMA_V1,
    load as load_canonical,
    save as save_canonical,
    training_actions as canonical_training_actions,
)
from task_env.trajectory.canonical.streaming import (
    load_streaming,
    save_streaming,
    validate_streaming,
    verify_roundtrip,
)
from task_env.trajectory.processing.transcode import TrajectoryValidationError, validate_trajectory

COMPONENTS = ("x", "y", "z", "qw", "qx", "qy", "qz", "gripper")
ACTION_SCHEMA = "panda-action-v1"


def _control(values, *, target_payload=None, applied_payload=None, writer_id="panda-controller"):
    values = tuple(float(value) for value in values)
    request = {
        "schema_version": "structured-action-request-v1",
        "scene_identity_hash": "1" * 64,
        "binding_identity_hash": "2" * 64,
        "groups": [
            {"schema_version": "control-group-action-v1", "entity_id": "panda-main",
             "group_id": "arm", "action_schema_id": ACTION_SCHEMA, "values": list(values[:7])},
            {"schema_version": "control-group-action-v1", "entity_id": "panda-main",
             "group_id": "gripper", "action_schema_id": ACTION_SCHEMA, "values": [values[7]]},
        ],
    }
    requested = {
        "mode": "absolute_pose",
        "reference": "world", "rotation_representation": "quaternion_wxyz",
        "values": list(values),
    }
    canonical = {
        "schema_version": "canonical-action-v0", "requested": requested,
        "interpreted_values": list(values), "resolved_world_pose": None, "clipped": False,
    }
    target_payload = target_payload or {"target": "fixture"}
    target_hash = digest(target_payload)
    applied_payload = applied_payload or {"ack": "fixture"}
    row = {
        "writer_id": writer_id, "action_schema_id": ACTION_SCHEMA,
        "components": list(COMPONENTS),
        "groups": [
            {"entity_id": "panda-main", "group_id": "arm", "action_components": list(COMPONENTS[:7])},
            {"entity_id": "panda-main", "group_id": "gripper", "action_components": ["gripper"]},
        ],
        "requested_action": requested,
        "canonical_action": canonical,
        "controller_target": {"schema_version": "canonical-control-v0", "payload": target_payload,
                              "identity_hash": target_hash},
        "applied_control": {"schema_version": "applied-canonical-control-v0", "payload": applied_payload,
                            "target_hash": target_hash},
    }
    return StructuredControlTransitionV1.from_mapping({
        "schema_version": "structured-control-transition-v1",
        "request": request,
        "writer_controls": [row],
    })


def _event(episode_id, boundary, sequence=0):
    return BoundaryEventV1(
        "boundary-event-v1", episode_id, boundary, sequence,
        f"{episode_id}:{boundary}:{sequence}", "capture_complete", "test",
        {"capture_id": f"capture-{boundary}"},
    )


def _outcome(episode_id, final_boundary, reason="expert_endpoint", *, terminated=False,
             truncated=False, bootstrap=True, task_success=False):
    return EpisodeOutcomeV1(
        "episode-outcome-v1", episode_id, final_boundary, reason,
        terminated, truncated, bootstrap, task_success, None,
    )


def _generic_h5(tmp_path, *, transition_count=1):
    config = RecorderConfig(schema_version="v3", max_transitions=max(1, transition_count))
    recorder = TransitionRecorder(config)
    metadata = {
        "env_metadata": {
            "env_name": "fixture", "task_name": "fixture", "task_version": "1",
            "scene_uid": "fixture-scene", "agent_uids": ("panda",),
            "action_schema": {"schema_id": ACTION_SCHEMA, "schema_version": "panda-action-v1",
                              "controller_kind": "absolute_pose", "reference": "world",
                              "components": COMPONENTS},
            "observation_schema": {"leaf_specs": [{"path": "state.pose", "semantic": "state"}]},
        },
        "universal_action_schema": {"version": "panda-universal-action-v1", "dimension": 8,
                                    "components": COMPONENTS},
    }
    recorder.begin_episode(np.zeros(3, dtype=np.float32), {"seed": 1}, metadata)
    episode_id = "generic-episode"
    recorder.add_boundary_event(_event(episode_id, 0))
    for index in range(transition_count):
        values = (0.1, 0.2, 0.3, 1., 0., 0., 0., 0.5)
        recorder.append_transition(
            np.asarray(values, dtype=np.float32), np.asarray(values, dtype=np.float32),
            np.full(3, index + 1, dtype=np.float32), 0.0, False, False, False, {},
            structured_control=_control(values),
        )
        recorder.add_boundary_event(_event(episode_id, index + 1))
    reason = "expert_endpoint"
    trajectory = recorder.end_episode(
        reason, outcome=_outcome(episode_id, transition_count, reason, truncated=True, bootstrap=True),
    )
    path = recorder.save_h5(tmp_path, f"generic-{transition_count}.h5")
    return path, trajectory


def _execution_v3():
    source_path = Path(__file__).parents[1] / "phase1/integration/fixtures/execution_prefix_fixture.json.gz"
    source = json.loads(gzip.decompress(source_path.read_bytes()))
    value = copy.deepcopy(source)
    value["schema"] = STRUCTURED_SCHEMA
    value["structured_controls"] = []
    for transition in value["transitions"]:
        record = transition["record"]
        requested = record["requested_action"]
        writer = _control(
            requested["values"], target_payload=record["controller_target"],
            applied_payload=record["applied_control"],
        )
        # The execution record already owns these canonical controller values;
        # bind the generic structured envelope to the exact legacy values.
        row = writer.to_mapping()
        control_row = row["writer_controls"][0]
        control_row["requested_action"] = requested
        control_row["canonical_action"] = record["canonical_action"]
        control_row["controller_target"] = {
            "schema_version": record["controller_target"]["schema_version"],
            "payload": record["controller_target"],
            "identity_hash": digest(record["controller_target"]),
        }
        control_row["applied_control"] = {
            "schema_version": record["applied_control"]["schema_version"],
            "payload": record["applied_control"],
            "target_hash": record["applied_control"]["target_hash"],
        }
        value["structured_controls"].append(StructuredControlTransitionV1.from_mapping(row).to_mapping())
    episode_id = "execution-fixture"
    value["events"] = [_event(episode_id, len(value["transitions"])).to_mapping()]
    final_record = value["transitions"][-1]["record"]
    final_boundary = value["boundaries"][-1]["record"]
    terminated = bool(final_record["terminated"])
    truncated = bool(final_record["truncated"])
    value["outcome"] = _outcome(
        episode_id, len(value["transitions"]), value["stop_reason"],
        terminated=terminated, truncated=truncated,
        bootstrap=not terminated, task_success=bool(final_boundary["is_success"]),
    ).to_mapping()
    return value


def _execution_v3_through_recorder():
    value = _execution_v3()
    metadata = EpisodeMetadata.from_mapping(value["metadata"])
    recorder = ExecutionRecorder(metadata, value["recipe"], schema=STRUCTURED_SCHEMA)
    first = value["boundaries"][0]
    recorder.boundary(
        BoundaryRecord.from_mapping(first["record"]),
        expand_snapshot(first["owners"], value["blobs"]),
        first["stage"], first["task_metrics_raw"], first["native_time"],
    )
    if value["events"][0]["boundary_index"] == 0:
        recorder.event(BoundaryEventV1.from_mapping(value["events"][0]))
    else:
        recorder.event(_event("execution-fixture", 0))
    for index, transition in enumerate(value["transitions"]):
        interval = transition["interval"]
        recorder.begin(interval["control_step"], interval["physics_dt"], interval["control_substeps"])
        for substep in interval["substeps"]:
            recorder.applied_substep(
                substep["index"], CanonicalStateView.from_mapping(substep["state"]),
                CanonicalControlFeedback.from_mapping(substep["feedback"]),
                CanonicalControlTarget.from_mapping(substep["target"]),
                AppliedCanonicalControl.from_mapping(substep["applied"]),
                {"inner_update_performed": substep["updated"]},
            )
        recorder.append(
            TransitionRecord.from_mapping(transition["record"]),
            BoundaryRecord.from_mapping(value["boundaries"][index + 1]["record"]),
            expand_snapshot(value["boundaries"][index + 1]["owners"], value["blobs"]),
            value["boundaries"][index + 1]["stage"], transition["native_audit"],
            value["boundaries"][index + 1]["task_metrics_raw"],
            value["boundaries"][index + 1]["native_time"],
            structured_control=StructuredControlTransitionV1.from_mapping(value["structured_controls"][index]),
        )
        next_boundary = index + 1
        for event in value["events"]:
            if event["boundary_index"] == next_boundary:
                recorder.event(BoundaryEventV1.from_mapping(event))
    return recorder.freeze(value["stop_reason"], outcome=EpisodeOutcomeV1.from_mapping(value["outcome"]))


def test_shared_episode_contracts_enforce_boundary_sequence_and_bootstrap():
    outcome = _outcome("e0", 0, terminated=True, bootstrap=False)
    assert outcome.final_boundary == 0
    with pytest.raises(ValueError, match="terminated outcomes cannot bootstrap"):
        _outcome("e0", 0, terminated=True, bootstrap=True)
    with pytest.raises(ValueError, match="sequence must be contiguous"):
        from task_env.trajectory.canonical.episode import validate_episode_records
        validate_episode_records((_event("e0", 0, 1),), _outcome("e0", 0), 0)


def test_generic_h5_v3_roundtrip_events_outcome_and_explicit_training_projection(tmp_path):
    path, trajectory = _generic_h5(tmp_path)
    loaded = load_structured_control_records_h5(path)
    assert loaded["schema_version"] == "v3"
    assert loaded["observation_count"] == loaded["transition_count"] + 1 == 2
    assert loaded["boundary_events"] == trajectory.boundary_events
    assert loaded["outcome"] == trajectory.outcome
    assert load_structured_training_actions_h5(path) == ((0.1, 0.2, 0.3, 1., 0., 0., 0., 0.5),)
    import h5py
    with h5py.File(path, "r") as handle:
        assert int(handle.attrs["transition_count"]) == 1
        assert handle["terminated"][:].tolist() == [False]
        assert handle["truncated"][:].tolist() == [False]
    with pytest.raises(TrajectoryValidationError, match="does not flatten task-env-h5/v3"):
        validate_trajectory(path)
    with h5py.File(path, "r+") as handle:
        handle["action/x"][0, 0] = 0.9
    with pytest.raises(ValueError, match="does not equal the explicit structured projection"):
        load_structured_training_actions_h5(path)


def test_generic_h5_v3_allows_zero_transition_outcome_without_pseudo_action(tmp_path):
    path, trajectory = _generic_h5(tmp_path, transition_count=0)
    loaded = load_structured_control_records_h5(path)
    assert trajectory.transition_count == loaded["transition_count"] == 0
    assert loaded["observation_count"] == 1
    assert loaded["structured_controls"] == ()
    assert loaded["outcome"].final_boundary == 0
    assert load_structured_training_actions_h5(path) == ()


def test_training_projection_rejects_more_than_one_writer():
    record = _control((0.1, 0.2, 0.3, 1., 0., 0., 0., 0.5))
    mapping = record.to_mapping()
    writer = mapping["writer_controls"][0]
    second = copy.deepcopy(writer)
    writer["groups"] = [writer["groups"][0]]
    writer["components"] = list(COMPONENTS[:7])
    writer["requested_action"]["values"] = writer["requested_action"]["values"][:7]
    writer["canonical_action"]["interpreted_values"] = writer["canonical_action"]["interpreted_values"][:7]
    second["writer_id"] = "gripper-controller"
    second["groups"] = [second["groups"][1]]
    second["components"] = ["gripper"]
    second["requested_action"]["values"] = [0.5]
    second["canonical_action"]["interpreted_values"] = [0.5]
    mapping["writer_controls"] = [writer, second]
    multi = StructuredControlTransitionV1.from_mapping(mapping)
    with pytest.raises(ValueError):
        single_writer_training_actions((multi,), action_schema_id=ACTION_SCHEMA, components=COMPONENTS)


def test_execution_v3_resident_streaming_h5_and_training_loaders_preserve_old_versions(tmp_path):
    value = _execution_v3_through_recorder()
    validate_execution(value)
    resident = tmp_path / "resident-v3.h5"
    streamed = tmp_path / "streamed-v3.h5"
    save_execution(resident, value)
    save_streaming(streamed, value, chunk_bytes=257)
    assert load_execution(resident) == value
    assert load_streaming(streamed, chunk_bytes=127) == value
    assert verify_roundtrip(streamed, value, chunk_bytes=511)["byte_exact"] is True
    assert validate_streaming(streamed, chunk_bytes=257)["semantic_validation"] == "PASS"
    assert execution_training_actions(value, action_schema_id=ACTION_SCHEMA, components=COMPONENTS)
    with pytest.raises(ValueError):
        multi = copy.deepcopy(value)
        for row in multi["structured_controls"]:
            row["writer_controls"].append(copy.deepcopy(row["writer_controls"][0]))
            row["writer_controls"][1]["writer_id"] = "second-writer"
        execution_training_actions(multi, action_schema_id=ACTION_SCHEMA, components=COMPONENTS)
    legacy = copy.deepcopy(value)
    legacy["schema"] = SCHEMA
    legacy.pop("structured_controls")
    legacy.pop("events")
    legacy.pop("outcome")
    assert validate_execution(legacy) is legacy
    assert FILE_SCHEMA == "task-env-canonical-execution-v2"
    assert STRUCTURED_FILE_SCHEMA == "task-env-canonical-execution-v3"

    zero = copy.deepcopy(value)
    zero["boundaries"] = zero["boundaries"][:1]
    zero["transitions"] = []
    zero["structured_controls"] = []
    zero["events"] = [_event("zero-step", 0).to_mapping()]
    zero["outcome"] = _outcome("zero-step", 0, zero["stop_reason"]).to_mapping()
    validate_execution(zero)
    zero_path = tmp_path / "zero-step-v3.h5"
    save_streaming(zero_path, zero, chunk_bytes=193)
    assert len(load_streaming(zero_path)["transitions"]) == 0
    assert len(load_streaming(zero_path)["boundaries"]) == 1


def test_execution_h5_readers_reject_unknown_file_version(tmp_path):
    import h5py

    unknown = tmp_path / "unknown-execution-v99.h5"
    with h5py.File(unknown, "w") as handle:
        handle.attrs["schema"] = "task-env-canonical-execution-v99"
        handle.attrs["logical_hash"] = "0" * 64
        handle.create_dataset("logical_json_utf8", data=np.asarray([], dtype=np.uint8))
        handle.create_dataset("control_step", data=np.asarray([], dtype=np.int64))
        handle.create_dataset("native_step_index", data=np.asarray([], dtype=np.int64))

    with pytest.raises(ValueError, match="H5 execution schema"):
        load_execution(unknown)
    with pytest.raises(ValueError, match="H5 execution schema"):
        load_streaming(unknown)


def test_execution_v3_rejects_cross_layer_identity_mismatch():
    value = _execution_v3()

    wrong_request = copy.deepcopy(value)
    wrong_request["structured_controls"][0]["writer_controls"][0]["requested_action"]["values"][0] += 0.01
    with pytest.raises(ValueError, match="does not preserve the complete structured request"):
        validate_execution(wrong_request)

    wrong_ack = copy.deepcopy(value)
    wrong_ack["structured_controls"][0]["writer_controls"][0]["applied_control"]["target_hash"] = "f" * 64
    with pytest.raises(ValueError, match="does not acknowledge its controller target"):
        validate_execution(wrong_ack)

    wrong_episode = copy.deepcopy(value)
    wrong_episode["outcome"]["episode_id"] = "another-episode"
    with pytest.raises(ValueError, match="episode identity mismatch"):
        validate_execution(wrong_episode)

    wrong_event_boundary = copy.deepcopy(value)
    wrong_event_boundary["events"][0]["boundary_index"] = len(value["transitions"]) + 1
    with pytest.raises(ValueError, match="points beyond final boundary"):
        validate_execution(wrong_event_boundary)

    wrong_boundary = copy.deepcopy(value)
    wrong_boundary["boundaries"][-1]["record"]["simulation_time"] += 0.001
    with pytest.raises(ValueError, match="state boundary mismatch"):
        validate_execution(wrong_boundary)

    wrong_profile = copy.deepcopy(value)
    wrong_profile["metadata"]["controller_identity"] = "f" * 64
    with pytest.raises(ValueError, match="owner identity mismatch"):
        validate_execution(wrong_profile)


def test_execution_v3_does_not_finalize_a_partial_native_interval():
    value = _execution_v3()
    recorder = __import__("task_env.trajectory.canonical.execution", fromlist=["ExecutionRecorder"]).ExecutionRecorder(
        EpisodeMetadata.from_mapping(value["metadata"]), value["recipe"], schema=STRUCTURED_SCHEMA,
    )
    recorder.begin(0, value["metadata"]["timebase"]["physics_dt"], value["metadata"]["timebase"]["control_substeps"])
    with pytest.raises(ValueError, match="incomplete effective interval"):
        recorder.freeze("partial", outcome=_outcome("partial", 0, "partial"))


def test_canonical_outer_v1_roundtrip_and_v0_file_identity_remains_distinct(tmp_path):
    source_path = Path(__file__).parents[1] / "phase1/integration/fixtures/execution_prefix_fixture.json.gz"
    source = json.loads(gzip.decompress(source_path.read_bytes()))
    metadata = EpisodeMetadata.from_mapping(source["metadata"])
    boundaries = tuple(BoundaryRecord.from_mapping(value["record"]) for value in source["boundaries"])
    transitions = tuple(TransitionRecord.from_mapping(value["record"]) for value in source["transitions"])
    controls = []
    for transition in transitions:
        requested = transition.requested_action
        control = _control(
            requested.values,
            target_payload=transition.controller_target.to_mapping(),
            applied_payload=transition.applied_control.to_mapping(),
        ).to_mapping()
        control["writer_controls"][0]["requested_action"] = requested.to_mapping()
        control["writer_controls"][0]["canonical_action"] = transition.canonical_action.to_mapping()
        controls.append(StructuredControlTransitionV1.from_mapping(control))
    episode_id = "canonical-fixture"
    outcome = _outcome(episode_id, len(transitions), "fixture_end", task_success=boundaries[-1].is_success)
    value = CanonicalTrajectoryV1(
        "canonical-trajectory-v1", metadata, boundaries, transitions, tuple(controls),
        (_event(episode_id, len(transitions)),), outcome, "fixture_end",
    )
    value.validate()
    incompatible_metadata = EpisodeMetadata.from_mapping(
        {**metadata.to_mapping(), "controller_identity": "f" * 64}
    )
    with pytest.raises(ValueError, match="target identity/order mismatch"):
        CanonicalTrajectoryV1(
            "canonical-trajectory-v1", incompatible_metadata, boundaries, transitions,
            tuple(controls), (_event(episode_id, len(transitions)),), outcome, "fixture_end",
        )
    path = tmp_path / "canonical-v1.h5"
    save_canonical(path, value)
    loaded = load_canonical(path)
    assert loaded == value
    assert canonical_training_actions(loaded, action_schema_id=ACTION_SCHEMA, components=COMPONENTS)
    assert CANONICAL_FILE_SCHEMA == "task-env-canonical-trajectory-v0"
    assert CANONICAL_FILE_SCHEMA_V1 == "task-env-canonical-trajectory-v1"

    zero = CanonicalTrajectoryV1(
        "canonical-trajectory-v1", metadata, (boundaries[0],), (), (),
        (_event("canonical-zero", 0),), _outcome("canonical-zero", 0, "zero_step"), "zero_step",
    )
    zero_path = tmp_path / "canonical-zero-v1.h5"
    save_canonical(zero_path, zero)
    zero_loaded = load_canonical(zero_path)
    assert zero_loaded.transitions == () and len(zero_loaded.boundaries) == 1
    assert canonical_training_actions(zero_loaded, action_schema_id=ACTION_SCHEMA, components=COMPONENTS) == ()
