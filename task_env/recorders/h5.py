"""Versioned HDF5 writers for frozen public TaskEnv trajectories."""

from __future__ import annotations

import os
import json
import hashlib
import math
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
from collections.abc import Sequence

import numpy as np
import yaml

from .contracts import RecorderConfig
from .trajectory import FrozenTrajectory
from task_env.trajectory.metadata import dump_metadata, load_metadata, plain_metadata
from task_env.trajectory.canonical.episode import (
    BoundaryEventV1,
    EpisodeOutcomeV1,
    StructuredControlTransitionV1,
    single_writer_training_actions,
    validate_episode_records,
)


def h5_string_dtype():
    import h5py

    return h5py.string_dtype(encoding="utf-8")


def _text_dataset(group, name: str, text: str) -> None:
    group.create_dataset(name, data=np.asarray(text, dtype=h5_string_dtype()))


def _json_dataset(group, name: str, value: Any) -> None:
    import json

    _text_dataset(group, name, json.dumps(plain_metadata(value), sort_keys=True))


def _yaml_dataset(group, name: str, value: Any) -> None:
    _text_dataset(group, name, dump_metadata(value))


def _leaves(value: Any, prefix: str = "", *, flat_leaf: str = "state/pendulum"):
    if isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{prefix}/{key}" if prefix else str(key)
            yield from _leaves(item, child, flat_leaf=flat_leaf)
    else:
        # A state-only Box observation has no mapping root.  Give it the
        # stable generic state leaf used by the Pendulum schema instead of
        # attempting to create an H5 dataset with an empty name.
        yield (prefix or flat_leaf), np.asarray(value)


def _action_schema(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    env_metadata = metadata.get("env_metadata", {})
    if not isinstance(env_metadata, Mapping):
        raise ValueError("record metadata env_metadata must be a mapping")
    schema = env_metadata.get("action_schema", {})
    if not isinstance(schema, Mapping):
        raise ValueError("record metadata action_schema must be a mapping")
    components = schema.get("components")
    if not isinstance(components, (tuple, list)):
        raise ValueError("record metadata action_schema lacks components")
    names = tuple(str(name) for name in components)
    if not names or len(set(names)) != len(names):
        raise ValueError("action_schema components must be non-empty and unique")
    return schema


def _universal_action_schema(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the task-family-specific runtime-facing action schema."""

    schema = metadata.get("universal_action_schema")
    if not schema:
        env_metadata = metadata.get("env_metadata", {})
        if isinstance(env_metadata, Mapping):
            schema = env_metadata.get("universal_action_schema")
    if schema:
        if not isinstance(schema, Mapping):
            raise ValueError("record metadata universal_action_schema must be a mapping")
        return schema
    # A small compatibility fallback for pre-Stage-12 synthetic/Panda
    # metadata that predates the public schema projection.
    return {
        "version": "panda-universal-action-v1",
        "dimension": 8,
        "components": (
            "joint1", "joint2", "joint3", "joint4",
            "joint5", "joint6", "joint7", "gripper",
        ),
    }


def _stable_scalars(infos: tuple[dict[str, Any], ...], group_name: str) -> dict[str, np.ndarray]:
    if not infos:
        return {}
    expected = set(infos[0].get(group_name, {}).keys())
    result = {key: [] for key in expected}
    for info in infos:
        values = info.get(group_name, {})
        if set(values.keys()) != expected:
            raise ValueError(f"{group_name} keys changed within trajectory")
        for key, value in values.items():
            if not isinstance(value, (bool, int, float, np.bool_, np.number)):
                raise ValueError(f"{group_name}.{key} must be a scalar")
            result[key].append(value)
    return {key: np.asarray(values) for key, values in result.items()}


def _flat_observation_leaf_path(metadata: Mapping[str, Any]) -> str:
    raw = metadata.get("env_metadata", {})
    schema = raw.get("observation_schema", {}) if isinstance(raw, Mapping) else {}
    specs = schema.get("leaf_specs", ()) if isinstance(schema, Mapping) else ()
    if len(specs) == 1 and isinstance(specs[0], Mapping):
        path = str(specs[0].get("path", ""))
        if path:
            return path.replace(".", "/")
    return "state/pendulum"


def _write_raw_observations(
    root,
    observations: tuple[Any, ...],
    config: RecorderConfig,
    metadata: Mapping[str, Any],
) -> list[dict[str, Any]]:
    flat_leaf = _flat_observation_leaf_path(metadata)
    first_paths = [path for path, _ in _leaves(observations[0], flat_leaf=flat_leaf)]
    for observation in observations[1:]:
        if [path for path, _ in _leaves(observation, flat_leaf=flat_leaf)] != first_paths:
            raise ValueError("observation leaf paths must stay fixed within a trajectory")
    leaves: list[dict[str, Any]] = []
    for path in first_paths:
        values = [
            dict(_leaves(current, flat_leaf=flat_leaf))[path]
            for current in observations
        ]
        first = values[0]
        if any(value.shape != first.shape or value.dtype != first.dtype for value in values):
            raise ValueError(f"observation leaf {path} shape/dtype changed within a trajectory")
        data = np.stack(values)
        root.create_dataset(
            f"obs/{path}", data=data, compression=config.h5_compression,
            compression_opts=config.h5_compression_level, chunks=(1, *data.shape[1:]),
        )
        leaves.append({"path": path, "shape": list(first.shape), "dtype": str(first.dtype)})
    return leaves


def _write_action(root, actions: tuple[np.ndarray, ...], schema: Mapping[str, Any]) -> list[dict[str, Any]]:
    components = tuple(str(name) for name in schema["components"])
    data = np.stack(actions) if actions else np.empty((0, len(components)), dtype=np.float32)
    if data.ndim != 2 or data.shape[1] != len(components):
        raise ValueError("recorded action shape does not match action_schema components")
    result = []
    for index, component in enumerate(components):
        root.create_dataset(f"action/{component}", data=data[:, index : index + 1])
        result.append({"name": component, "shape": [1], "dtype": str(data.dtype), "index": index})
    return result


def _env_meta(trajectory: FrozenTrajectory, observation_leaves: list[dict[str, Any]], action_leaves: list[dict[str, Any]], *, h5_version: str = "v2") -> dict[str, Any]:
    metadata = trajectory.record_metadata
    raw = metadata.get("env_metadata", {})
    if not isinstance(raw, Mapping):
        raise ValueError("record metadata env_metadata must be a mapping")
    schema_metadata = raw.get("observation_schema", {})
    field_specs = (
        schema_metadata.get("leaf_specs", ())
        if isinstance(schema_metadata, Mapping)
        else ()
    )
    semantics = {
        str(spec.get("path")): str(spec.get("semantic", ""))
        for spec in field_specs if isinstance(spec, Mapping)
    }
    grouped: dict[str, dict[str, Any]] = {}
    for leaf in observation_leaves:
        root, _, name = leaf["path"].partition("/")
        group = grouped.setdefault(root, {"order": [], "leaves": {}})
        group["order"].append(name)
        group["leaves"][name] = {"shape": leaf["shape"], "dtype": leaf["dtype"], "semantic": semantics.get(leaf["path"].replace("/", "."), "")}
    source_action_schema = _action_schema(metadata)
    controller_kind = source_action_schema.get("controller_kind")
    reference = source_action_schema.get("reference")
    if controller_kind == "absolute_joint":
        arm_mode = "absolute_joint"
        reference = None
    elif controller_kind == "delta_pose":
        arm_mode = "delta"
    elif source_action_schema.get("mode") not in (None, "no_op"):
        arm_mode = "native"
        reference = None
    else:
        arm_mode = "absolute"
    for spec in raw.get("camera_specs", ()):
        if not isinstance(spec, Mapping) or not spec.get("rgb"):
            continue
        name = str(spec["name"])
        if "rgb" in grouped and name in grouped["rgb"]["leaves"]:
            source_layout = spec.get("rgb_layout", "HWC")
            grouped["rgb"]["leaves"][name].update({
                "layout": "CHW",
                "source_layout": source_layout,
                "semantic": "rgb",
            })
    rich_observation = {"order": list(grouped), "camera_order": list(raw.get("camera_names", ())), **grouped}
    observation_shapes = {
        group: {name: leaf["shape"] for name, leaf in value.get("leaves", {}).items()}
        for group, value in grouped.items()
    }
    action_order = [leaf["name"] for leaf in action_leaves]
    action_schema = {
        "schema_id": source_action_schema.get("schema_id"),
        "schema_version": source_action_schema.get("schema_version"),
        "reference": source_action_schema.get("reference"),
        "controller_kind": source_action_schema.get("controller_kind"),
        "contract": dict(source_action_schema),
        "order": action_order,
        "components": [{**leaf, "semantic": leaf["name"]} for leaf in action_leaves],
    }
    for key in (
        "kind",
        "mode",
        "shape",
        "dtype",
        "low",
        "high",
        "bounds",
        "unit",
        "actuator_interpretation",
        "task_family",
    ):
        if key in source_action_schema:
            action_schema[key] = source_action_schema[key]
    universal_schema = _universal_action_schema(metadata)
    action_protocol = (
        {
            "mode": {"native": source_action_schema.get("mode")},
            "reference": None,
            "action_equals_universal_action": True,
        }
        if controller_kind is None and source_action_schema.get("mode") not in (None, "no_op")
        else {
            "mode": {"arm": arm_mode, "gripper": "absolute"},
            "reference": reference,
        }
    )
    result = {
        "schema": {"id": "task-env-h5", "version": h5_version},
        "environment": {"name": raw.get("env_name"), "task_name": raw.get("task_name"), "task_version": raw.get("task_version"), "scene_uid": raw.get("scene_uid"), "agent_uids": raw.get("agent_uids", ())},
        "timebase": {
            "physics_dt": raw.get("physics_dt"), "control_substeps": raw.get("control_substeps"),
            "control_frequency": raw.get("control_frequency"),
        },
        # ``obs`` and ``action`` are shape maps consumed by agent_factory's
        # resolver.  Rich semantics live beside them so JSON/YAML readers do
        # not have to guess whether a metadata value is a shape or a schema.
        "obs": {"order": list(grouped), "camera_order": list(raw.get("camera_names", ())), **observation_shapes},
        "observation_schema": rich_observation,
        "observation_order": {group: value.get("order", []) for group, value in grouped.items()},
        "action": {leaf["name"]: leaf["shape"] for leaf in action_leaves},
        "action_order": action_order,
        "action_schema": action_schema,
        "action_protocol": action_protocol,
        "replay_context": ({
            "seed": trajectory.reset_info.get("seed"),
            "options": trajectory.reset_info.get("options", {}),
            "reset_parameters": trajectory.reset_info.get("reset_parameters", {}),
        } if isinstance(trajectory.reset_info, Mapping) and "seed" in trajectory.reset_info else {}),
        "universal_action": universal_schema,
        "batch_provenance": metadata.get("batch_provenance", {}),
        "batch_physics_layout": raw.get("batch_physics_layout"),
        "runtime_resource_summary": raw.get("runtime_resource_summary", {}),
        "reference_profile": raw.get("reference_profile", {}),
        "conversion_capabilities": raw.get("conversion_capabilities", {}),
        "trajectory": {"observation_count_semantics": "T+1", "transition_count_semantics": "T"},
    }
    return result


def _write_common_transition_data(root, trajectory: FrozenTrajectory) -> None:
    schema = _universal_action_schema(trajectory.record_metadata)
    dimension = int(schema.get("dimension", 0))
    universal = (
        np.stack(trajectory.universal_actions).astype(np.float32, copy=False)
        if trajectory.universal_actions
        else np.empty((0, dimension), dtype=np.float32)
    )
    if universal.ndim != 2 or universal.shape[1] != dimension:
        raise ValueError("universal_action shape does not match universal_action_schema")
    is_panda_v1 = schema.get("version") == "panda-universal-action-v1" or (
        dimension == 8 and not schema.get("components")
    )
    if is_panda_v1:
        if dimension != 8:
            raise ValueError("Panda v1 universal_action must have shape (T, 8)")
        root.create_dataset("universal_action/arm_joint_position", data=universal[:, :7])
        root.create_dataset("universal_action/gripper", data=universal[:, 7:8])
    else:
        components = tuple(str(name) for name in schema.get("components", ()))
        if len(components) != dimension or len(set(components)) != dimension:
            raise ValueError("universal_action_schema components must match its dimension")
        for index, component in enumerate(components):
            root.create_dataset(
                f"universal_action/{component}",
                data=universal[:, index : index + 1],
            )
    root.create_dataset("reward", data=np.asarray(trajectory.rewards, dtype=np.float32))
    root.create_dataset("success", data=np.asarray(trajectory.successes, dtype=np.bool_))
    root.create_dataset("terminated", data=np.asarray(trajectory.terminated, dtype=np.bool_))
    root.create_dataset("truncated", data=np.asarray(trajectory.truncated, dtype=np.bool_))
    for group_name, h5_group in (("task_metrics", "info/task_metrics"), ("reward_terms", "info/reward_terms")):
        for key, values in _stable_scalars(trajectory.infos, group_name).items():
            root.create_dataset(f"{h5_group}/{key}", data=values)


def _save_v2(root, trajectory: FrozenTrajectory, config: RecorderConfig) -> None:
    root.attrs.update(schema_id="task-env-h5", schema_version="v2", transition_count=trajectory.transition_count, observation_count=len(trajectory.observations), episode_complete=True, stop_reason=trajectory.stop_reason)
    leaves = _write_raw_observations(
        root,
        trajectory.observations,
        config,
        trajectory.record_metadata,
    )
    action_leaves = _write_action(root, trajectory.actions, _action_schema(trajectory.record_metadata))
    _write_common_transition_data(root, trajectory)
    meta = root.require_group("meta")
    env_meta = _env_meta(trajectory, leaves, action_leaves)
    _yaml_dataset(meta, "env_meta", env_meta)
    _yaml_dataset(meta, "env_cfg", trajectory.record_metadata.get("resolved_config", {}))
    if not config.meta_only:
        _yaml_dataset(meta, "episode_meta", {
            "reset_info": trajectory.reset_info, "stop_reason": trajectory.stop_reason,
            "transition_count": trajectory.transition_count, "observation_count": len(trajectory.observations),
        })


def _save_v3(root, trajectory: FrozenTrajectory, config: RecorderConfig) -> None:
    if trajectory.outcome is None:
        raise ValueError("task-env-h5 v3 requires EpisodeOutcomeV1")
    if trajectory.transition_count and (
        len(trajectory.structured_controls) != trajectory.transition_count
        or any(control is None for control in trajectory.structured_controls)
    ):
        raise ValueError("task-env-h5 v3 requires structured control evidence for every transition")
    validate_episode_records(trajectory.boundary_events, trajectory.outcome, trajectory.transition_count)
    root.attrs.update(
        schema_id="task-env-h5", schema_version="v3",
        transition_count=trajectory.transition_count,
        observation_count=len(trajectory.observations), episode_complete=True,
        stop_reason=trajectory.stop_reason,
    )
    leaves = _write_raw_observations(root, trajectory.observations, config, trajectory.record_metadata)
    action_leaves = _write_action(root, trajectory.actions, _action_schema(trajectory.record_metadata))
    _write_common_transition_data(root, trajectory)
    meta = root.require_group("meta")
    env_meta = _env_meta(trajectory, leaves, action_leaves, h5_version="v3")
    _yaml_dataset(meta, "env_meta", env_meta)
    _yaml_dataset(meta, "env_cfg", trajectory.record_metadata.get("resolved_config", {}))
    controls = [None if item is None else item.to_mapping() for item in trajectory.structured_controls]
    _json_dataset(meta, "structured_controls_v1_json", controls)
    _json_dataset(meta, "boundary_events_v1_json", [event.to_mapping() for event in trajectory.boundary_events])
    _json_dataset(meta, "episode_outcome_v1_json", trajectory.outcome.to_mapping())
    _json_dataset(meta, "training_projection_v1_json", {
        "rule": "explicit-single-writer-schema-v1",
        "source": "structured_controls_v1_json",
        "automatic_flattening": False,
    })
    camera_extension = _camera_observation_extension(trajectory)
    if camera_extension is not None:
        contract, boundaries, recording_binding = camera_extension
        _json_dataset(meta, "camera_observation_contract_v1_json", contract)
        _json_dataset(meta, "camera_observations_v1_json", boundaries)
        _json_dataset(meta, "camera_recording_binding_v1_json", recording_binding)
    f05_typed_state_extension = _f05_typed_state_extension(trajectory)
    if f05_typed_state_extension is not None:
        _json_dataset(meta, "f05_public_typed_state_witness_v1_json", f05_typed_state_extension)


def _f05_typed_state_extension(trajectory: FrozenTrajectory):
    """Persist the public T+1 typed-state snapshots for the bounded F05 profile only."""
    metadata = trajectory.record_metadata.get("env_metadata", {})
    profile = metadata.get("reference_profile", {}) if isinstance(metadata, Mapping) else {}
    if not isinstance(profile, Mapping) or profile.get("profile_id") not in {
            "f05-geophys-usd-position-synthetic-io-s1-v1",
            "geophys-usd-position-f05-native-v1",
    }:
        return None
    if profile.get("typed_state_h5_witness_schema_version") != "f05-public-typed-state-witness-v1":
        raise ValueError("F05 recording metadata does not declare the typed T+1 H5 witness")
    public_infos = [trajectory.reset_info, *trajectory.infos]
    if len(public_infos) != len(trajectory.observations):
        raise ValueError("F05 typed-state witness requires one public reset/step info per T+1 observation")
    rows = []
    for index, info in enumerate(public_infos):
        if not isinstance(info, Mapping):
            raise TypeError("F05 public reset/step info must be a mapping")
        state = info.get("canonical_state_view_v1")
        boundary = info.get("state_boundary_identity")
        clock = info.get("state_sample_clock")
        if not isinstance(state, Mapping) or not isinstance(boundary, Mapping) or not isinstance(clock, Mapping):
            raise ValueError(f"F05 public reset/step info {index} lacks typed state, boundary or clock")
        if state.get("boundary") != boundary or state.get("sample_clock") != clock:
            raise ValueError(f"F05 public typed state {index} differs from its public boundary/clock")
        rows.append({
            "boundary_index": index,
            "state_boundary_identity": dict(boundary),
            "state_sample_clock": dict(clock),
            "canonical_state_view_v1": dict(state),
        })
    return {
        "schema_version": "f05-public-typed-state-witness-v1",
        "source": "SelectedReferenceEnv public reset/step info captured by Generic H5 v3 Recorder",
        "observation_count": len(trajectory.observations),
        "rows": rows,
    }


def _camera_observation_extension(trajectory: FrozenTrajectory):
    """Build camera metadata plus bindings to independent Generic H5 v3 records."""

    from task_env.observations.canonical_camera.consumer import (
        CAMERA_IDS,
        CameraObservationConfigV1,
        validate_camera_observation_boundaries,
    )

    raw_contract = trajectory.record_metadata.get("camera_observation_contract_v1")
    reset_record = trajectory.reset_info.get("camera_observation_v1")
    transition_records = tuple(info.get("camera_observation_v1") for info in trajectory.infos)
    if raw_contract is None:
        if reset_record is not None or any(item is not None for item in transition_records):
            raise ValueError("camera metadata was recorded without its versioned contract")
        return None
    if not isinstance(raw_contract, Mapping):
        raise ValueError("camera observation contract must be a mapping")
    contract = CameraObservationConfigV1.from_mapping(dict(raw_contract))
    contract.capacity(max(1, trajectory.transition_count))
    records = [reset_record, *transition_records]
    boundaries = validate_camera_observation_boundaries(
        records, expected_count=len(trajectory.observations),
    )
    first = boundaries[0]
    expected_geometry = {
        item.camera_id: item.identity_hash
        for item in contract.geometries(first.captures[0].capture_identity.task_artifact_hash)
    }
    stable = None
    for boundary in boundaries:
        identity = boundary.captures[0].capture_identity
        current = (
            identity.task_artifact_hash,
            identity.render_source_identity_hash,
            identity.execution_spec_identity_hash,
            identity.provider_manifest_identity_hash,
            identity.state_boundary.scene_identity_hash,
            identity.state_boundary.scene_instance_id,
            identity.state_boundary.provider_materialization_id,
            identity.state_boundary.episode_id,
            identity.state_boundary.reset_sample_id,
        )
        if stable is None:
            stable = current
        elif current != stable:
            raise ValueError("camera metadata identity drift within one H5 episode")
        for capture in boundary.captures:
            if capture.capture_identity.camera_geometry_identity_hash != expected_geometry[capture.camera_id]:
                raise ValueError("stored camera metadata does not match its authored mount contract")
    boundary_values = [item.to_mapping() for item in boundaries]
    recording_binding = _camera_recording_binding_from_trajectory(trajectory, boundaries)
    return contract.to_mapping(), boundary_values, recording_binding


def _camera_recording_binding_from_trajectory(trajectory: FrozenTrajectory, camera_boundaries):
    """Bind opt-in camera metadata to real recorder observations, info, controls and outcome."""

    from task_env.artifacts.state import StateBoundaryIdentity, StateSampleClock

    transition_count = trajectory.transition_count
    if len(trajectory.observations) != transition_count + 1 or len(trajectory.infos) != transition_count:
        raise ValueError("camera recording requires aligned T transitions and T+1 observations")
    record_infos = [trajectory.reset_info, *trajectory.infos]
    if len(camera_boundaries) != len(record_infos):
        raise ValueError("camera recording requires one reset/transition record per observation boundary")

    raw_env_metadata = trajectory.record_metadata.get("env_metadata")
    if not isinstance(raw_env_metadata, Mapping):
        raise ValueError("camera recording requires the independent Position record metadata")
    profile = raw_env_metadata.get("reference_profile")
    if not isinstance(profile, Mapping):
        raise ValueError("camera recording requires the Position reference_profile identity anchor")
    required_profile = (
        "writer_id", "controller_identity", "control_binding_plan_identity_hash",
        "task_artifact_identity_hash", "scene_identity_hash", "reset_sample_id",
        "source_closure_digest",
    )
    if any(not profile.get(name) for name in required_profile):
        raise ValueError("camera recording reference_profile is missing a required source/control identity")

    records = []
    state_digests = []
    for index, (info, camera_boundary, observation) in enumerate(
        zip(record_infos, camera_boundaries, trajectory.observations, strict=True)
    ):
        if not isinstance(info, Mapping):
            raise ValueError("camera recording reset/transition info must be a mapping")
        raw_boundary = info.get("state_boundary_identity")
        raw_clock = info.get("state_sample_clock")
        if not isinstance(raw_boundary, Mapping) or not isinstance(raw_clock, Mapping):
            raise ValueError("camera recording reset/transition info lacks an independent state boundary or clock")
        boundary = StateBoundaryIdentity.from_mapping(raw_boundary)
        clock = StateSampleClock.from_mapping(raw_clock)
        boundary_id = info.get("state_boundary_id")
        if boundary_id != boundary.boundary_id:
            raise ValueError("recorded state_boundary_id does not match its typed reset/transition identity")
        if (boundary.control_step != index or clock.sample_index != index
                or clock.clock_domain != "evaluation_boundary"):
            raise ValueError("recorded Position boundary/clock order is not contiguous from reset")
        if "control_step" in info and info["control_step"] != index:
            raise ValueError("recorded info control_step does not match its T/T+1 boundary")
        if "simulation_time_s" in info and float(info["simulation_time_s"]) != clock.simulation_time_s:
            raise ValueError("recorded info simulation clock does not match state_sample_clock")
        if (camera_boundary.boundary_index != index
                or camera_boundary.state_boundary_id != boundary.boundary_id
                or camera_boundary.simulation_time_s != clock.simulation_time_s):
            raise ValueError("camera boundary does not match independent reset/transition identity and clock")
        for capture in camera_boundary.captures:
            identity = capture.capture_identity
            if identity.state_boundary != boundary or identity.sample_clock != clock:
                raise ValueError("camera capture does not match independent reset/transition state identity and clock")

        observation_leaves = dict(_leaves(observation))
        digest_value = observation_leaves.get("state/boundary_identity_sha256")
        if (not isinstance(digest_value, np.ndarray)
                or digest_value.dtype != np.dtype(np.uint8)
                or digest_value.shape != (32,)):
            raise ValueError("camera recording requires a 32-byte uint8 Position state boundary digest at every boundary")
        digest_hex = bytes(digest_value).hex()
        expected_digest = boundary.boundary_id.removeprefix("state-boundary-")
        if digest_hex != expected_digest:
            raise ValueError("camera boundary identity does not match the actual Position state observation digest")
        state_digests.append(bytes(digest_value))
        records.append({
            "boundary_index": index,
            "state_boundary_identity": boundary.to_mapping(),
            "state_boundary_id": boundary.boundary_id,
            "state_sample_clock": clock.to_mapping(),
        })

    outcome = trajectory.outcome
    if not isinstance(outcome, EpisodeOutcomeV1):
        raise ValueError("camera recording requires the finalized typed EpisodeOutcomeV1")
    first_identity = StateBoundaryIdentity.from_mapping(records[0]["state_boundary_identity"])
    if (outcome.episode_id != first_identity.episode_id
            or outcome.final_boundary != transition_count):
        raise ValueError("finalized EpisodeOutcome does not match the recorded camera episode and boundary")

    artifact_hash = str(profile["task_artifact_identity_hash"])
    scene_hash = str(profile["scene_identity_hash"])
    reset_sample_id = str(profile["reset_sample_id"])
    source_closure_digest = str(profile["source_closure_digest"])
    plan_hash = str(profile["control_binding_plan_identity_hash"])
    if (first_identity.scene_identity_hash != scene_hash
            or first_identity.reset_sample_id != reset_sample_id):
        raise ValueError("Position reference_profile does not match the actual reset boundary")
    for camera_boundary in camera_boundaries:
        identity = camera_boundary.captures[0].capture_identity
        if (identity.task_artifact_hash != artifact_hash
                or identity.state_boundary.scene_identity_hash != scene_hash
                or identity.state_boundary.reset_sample_id != reset_sample_id
                or identity.state_boundary.episode_id != outcome.episode_id):
            raise ValueError("camera identity does not match independent Position source/profile and episode metadata")

    controls = tuple(trajectory.structured_controls)
    if transition_count and (len(controls) != transition_count or any(item is None for item in controls)):
        raise ValueError("camera recording requires one structured Position control per transition")
    typed_controls = tuple(item for item in controls if item is not None)
    from task_env.controllers.canonical.contracts import PositionControlTargetV1
    from task_env.trajectory.canonical.episode import single_writer_training_actions

    for index, control in enumerate(typed_controls):
        control.validate()
        if (control.request.scene_identity_hash != scene_hash
                or control.request.binding_identity_hash != plan_hash
                or len(control.writer_controls) != 1):
            raise ValueError("camera recording structured control does not match the single Position source binding")
        writer = control.writer_controls[0]
        if writer.get("writer_id") != profile["writer_id"]:
            raise ValueError("camera recording structured control writer does not match reference_profile")
        canonical_action = writer.get("canonical_action")
        raw_target = canonical_action.get("position_target_v1") if isinstance(canonical_action, Mapping) else None
        if not isinstance(raw_target, Mapping):
            raise ValueError("camera recording structured control lacks its typed PositionControlTargetV1")
        target = PositionControlTargetV1.from_mapping(dict(raw_target))
        previous = StateBoundaryIdentity.from_mapping(records[index]["state_boundary_identity"])
        previous_clock = StateSampleClock.from_mapping(records[index]["state_sample_clock"])
        if (target.source_boundary != previous or target.sample_clock != previous_clock
                or target.writer_id != profile["writer_id"]
                or target.controller_identity != profile["controller_identity"]
                or target.binding_identity_hash != plan_hash
                or target.source_closure_digest != source_closure_digest
                or target.target.task_artifact_hash != artifact_hash
                or canonical_action.get("position_target_identity_hash") != target.identity_hash):
            raise ValueError("camera recording structured control is not bound to the preceding real state boundary")

    if typed_controls:
        action_schema = _action_schema(trajectory.record_metadata)
        projected = single_writer_training_actions(
            typed_controls, action_schema_id=action_schema["schema_id"],
            components=tuple(action_schema["components"]),
        )
        actual_actions = np.stack(trajectory.actions).astype(np.float32, copy=False)
        projected_actions = np.asarray(projected, dtype=np.float32).reshape(actual_actions.shape)
        if not np.array_equal(actual_actions, projected_actions):
            raise ValueError("camera recording structured control order differs from stored action order")

    for boundary in camera_boundaries:
        for capture in boundary.captures:
            if capture.capture_identity.state_boundary.boundary_id != (
                "state-boundary-" + state_digests[boundary.boundary_index].hex()
            ):
                raise ValueError("camera recording boundary digest changed during validation")

    return {
        "schema_version": "camera-recording-binding-v1",
        "observation_count": transition_count + 1,
        "transition_count": transition_count,
        "episode_id": outcome.episode_id,
        "final_boundary": outcome.final_boundary,
        "task_artifact_identity_hash": artifact_hash,
        "scene_identity_hash": scene_hash,
        "reset_sample_id": reset_sample_id,
        "source_closure_digest": source_closure_digest,
        "writer_id": str(profile["writer_id"]),
        "controller_identity": str(profile["controller_identity"]),
        "control_binding_plan_identity_hash": plan_hash,
        "boundaries": records,
    }


def _validate_camera_recording_binding(
    raw_binding, camera_boundaries, state_digests, env_meta, structured_records,
    projected_actions, observation_count, transition_count,
):
    """Strictly cross-check camera metadata against independent stored owner data."""

    from task_env.artifacts.state import StateBoundaryIdentity, StateSampleClock
    from task_env.controllers.canonical.contracts import PositionControlTargetV1

    required = {
        "schema_version", "observation_count", "transition_count", "episode_id",
        "final_boundary", "task_artifact_identity_hash", "scene_identity_hash",
        "reset_sample_id", "source_closure_digest", "writer_id", "controller_identity",
        "control_binding_plan_identity_hash", "boundaries",
    }
    if not isinstance(raw_binding, dict) or set(raw_binding) != required:
        raise ValueError("camera recording binding has unknown or missing fields")
    if raw_binding["schema_version"] != "camera-recording-binding-v1":
        raise ValueError("unsupported camera recording binding version")
    if (raw_binding["observation_count"] != observation_count
            or raw_binding["transition_count"] != transition_count
            or raw_binding["final_boundary"] != transition_count
            or len(raw_binding["boundaries"]) != observation_count):
        raise ValueError("camera recording binding T/T+1 counts disagree with the finalized H5 episode")
    profile = env_meta.get("reference_profile") if isinstance(env_meta, Mapping) else None
    if not isinstance(profile, Mapping):
        raise ValueError("camera recording H5 lacks independent Position reference_profile metadata")
    for field in (
        "task_artifact_identity_hash", "scene_identity_hash", "reset_sample_id",
        "source_closure_digest", "writer_id", "controller_identity",
        "control_binding_plan_identity_hash",
    ):
        if raw_binding[field] != profile.get(field):
            raise ValueError(f"camera recording binding {field} disagrees with independent reference_profile")

    decoded = []
    expected_boundary_fields = {
        "boundary_index", "state_boundary_identity", "state_boundary_id", "state_sample_clock",
    }
    for index, (entry, camera_boundary, digest_bytes) in enumerate(
        zip(raw_binding["boundaries"], camera_boundaries, state_digests, strict=True)
    ):
        if not isinstance(entry, dict) or set(entry) != expected_boundary_fields:
            raise ValueError("camera recording boundary anchor has unknown or missing fields")
        identity = StateBoundaryIdentity.from_mapping(entry["state_boundary_identity"])
        clock = StateSampleClock.from_mapping(entry["state_sample_clock"])
        if (entry["boundary_index"] != index
                or entry["state_boundary_id"] != identity.boundary_id
                or identity.control_step != index
                or clock.sample_index != index
                or clock.clock_domain != "evaluation_boundary"):
            raise ValueError("camera recording boundary anchor has invalid identity/order/clock")
        if (bytes(digest_bytes).hex() != identity.boundary_id.removeprefix("state-boundary-")
                or camera_boundary.boundary_index != index
                or camera_boundary.state_boundary_id != identity.boundary_id
                or camera_boundary.simulation_time_s != clock.simulation_time_s):
            raise ValueError("camera sidecar does not match stored state digest and record clock")
        if (identity.episode_id != raw_binding["episode_id"]
                or identity.scene_identity_hash != raw_binding["scene_identity_hash"]
                or identity.reset_sample_id != raw_binding["reset_sample_id"]):
            raise ValueError("camera recording boundary episode/reset/source does not match its independent anchor")
        for capture in camera_boundary.captures:
            if (capture.capture_identity.state_boundary != identity
                    or capture.capture_identity.sample_clock != clock
                    or capture.capture_identity.task_artifact_hash != raw_binding["task_artifact_identity_hash"]):
                raise ValueError("camera capture identity disagrees with independent H5 boundary/source anchors")
        decoded.append((identity, clock))

    outcome = structured_records.get("outcome")
    if (not isinstance(outcome, EpisodeOutcomeV1)
            or outcome.episode_id != raw_binding["episode_id"]
            or outcome.final_boundary != transition_count):
        raise ValueError("camera recording episode does not match finalized typed EpisodeOutcome")
    controls = tuple(structured_records.get("structured_controls", ()))
    if len(controls) != transition_count or len(projected_actions) != transition_count:
        raise ValueError("camera recording control order/count does not match finalized transitions")
    for index, control in enumerate(controls):
        if control is None:
            raise ValueError("camera recording requires structured control evidence for every transition")
        control.validate()
        if (control.request.scene_identity_hash != raw_binding["scene_identity_hash"]
                or control.request.binding_identity_hash != raw_binding["control_binding_plan_identity_hash"]
                or len(control.writer_controls) != 1):
            raise ValueError("camera recording structured control disagrees with its independent Position binding")
        writer = control.writer_controls[0]
        if writer.get("writer_id") != raw_binding["writer_id"]:
            raise ValueError("camera recording control order has a mismatched writer identity")
        canonical_action = writer.get("canonical_action")
        raw_target = canonical_action.get("position_target_v1") if isinstance(canonical_action, Mapping) else None
        if not isinstance(raw_target, Mapping):
            raise ValueError("camera recording structured control lacks PositionControlTargetV1")
        target = PositionControlTargetV1.from_mapping(dict(raw_target))
        if (target.source_boundary != decoded[index][0]
                or target.sample_clock != decoded[index][1]
                or target.writer_id != raw_binding["writer_id"]
                or target.controller_identity != raw_binding["controller_identity"]
                or target.binding_identity_hash != raw_binding["control_binding_plan_identity_hash"]
                or target.source_closure_digest != raw_binding["source_closure_digest"]
                or target.target.task_artifact_hash != raw_binding["task_artifact_identity_hash"]
                or canonical_action.get("position_target_identity_hash") != target.identity_hash):
            raise ValueError("camera recording structured control is not aligned to its source boundary/clock")
    return raw_binding


def _save_v1(root, trajectory: FrozenTrajectory, config: RecorderConfig) -> None:
    """Historical writer retained for its fixed v1 regression fixture only."""
    root.attrs.update(schema_id=config.schema_id, schema_version=config.schema_version, transition_count=trajectory.transition_count, observation_count=len(trajectory.observations), episode_complete=True, stop_reason=trajectory.stop_reason)
    layout = {"leaves": [], "flatten_observation_paths": list(config.flatten_observation_paths)}
    first_paths = [path for path, _ in _leaves(trajectory.observations[0])]
    selected = tuple(config.flatten_observation_paths)
    for group in selected:
        paths = [path for path in first_paths if path == group or path.startswith(f"{group}/")]
        if not paths:
            raise ValueError(f"flatten observation path does not exist: {group}")
        rows = [np.concatenate([dict(_leaves(obs))[path].reshape(-1) for path in paths]).astype(np.float32) for obs in trajectory.observations]
        root.create_dataset(f"obs/{group}", data=np.stack(rows))
    for path in first_paths:
        if any(path == group or path.startswith(f"{group}/") for group in selected):
            continue
        values = [dict(_leaves(obs))[path] for obs in trajectory.observations]
        first = values[0]
        data = np.stack(values)
        if path.startswith("vision/rgb/") and np.issubdtype(first.dtype, np.floating):
            data = np.rint(np.clip(data, 0.0, 1.0) * 255.0).astype(np.uint8)
        root.create_dataset(f"obs/{path}", data=data, compression=config.h5_compression, compression_opts=config.h5_compression_level, chunks=(1, *data.shape[1:]))
    _write_action(root, trajectory.actions, _action_schema(trajectory.record_metadata))
    _write_common_transition_data(root, trajectory)
    meta = root.require_group("meta")
    _json_dataset(meta, "env_metadata_json", trajectory.record_metadata)
    _json_dataset(meta, "reset_info_json", trajectory.reset_info)
    _json_dataset(meta, "recorder_config_json", config.__dict__)
    _json_dataset(meta, "layout_json", layout)


def save_trajectory_h5(trajectory: FrozenTrajectory, config: RecorderConfig, *, path: Path | str | None, name: str | None, index: int) -> Path:
    import h5py

    trajectory.validate()
    directory = Path.cwd() if path is None else Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    filename = name or f"traj_{index:03d}_{datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%m%d%H%M')}.h5"
    if not filename.endswith(".h5"):
        filename += ".h5"
    target = directory / filename
    if target.exists():
        raise FileExistsError(f"refusing to overwrite {target}")
    temporary = directory / f".{filename}.tmp"
    if temporary.exists():
        raise FileExistsError(f"temporary output already exists: {temporary}")
    try:
        with h5py.File(temporary, "w") as root:
            if config.schema_version == "v2":
                _save_v2(root, trajectory, config)
            elif config.schema_version == "v3":
                _save_v3(root, trajectory, config)
            else:
                _save_v1(root, trajectory, config)
        os.replace(temporary, target)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    return target


def save_trajectory_collection_h5(
    trajectories: Sequence[FrozenTrajectory],
    config: RecorderConfig,
    *,
    path: Path | str | None,
    name: str | None,
) -> Path:
    """Write multiple trajectories into one ``traj_000``-grouped H5 file."""

    import h5py

    if config.schema_version != "v2":
        raise ValueError("trajectory collections support only task-env-h5/v2")
    if not trajectories:
        raise ValueError("trajectory collection requires at least one trajectory")
    directory = Path.cwd() if path is None else Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    filename = name or "trajectories.h5"
    if not filename.endswith(".h5"):
        filename += ".h5"
    target = directory / filename
    if target.exists():
        raise FileExistsError(f"refusing to overwrite {target}")
    temporary = directory / f".{filename}.tmp"
    if temporary.exists():
        raise FileExistsError(f"temporary output already exists: {temporary}")
    try:
        with h5py.File(temporary, "w") as root:
            root.attrs.update(
                schema_id="task-env-h5",
                schema_version="v2",
                container_type="trajectory_collection",
                container_version="v1",
                trajectory_count=len(trajectories),
            )
            for index, trajectory in enumerate(trajectories):
                trajectory.validate()
                group = root.create_group(f"traj_{index:03d}")
                _save_v2(group, trajectory, config)
        os.replace(temporary, target)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    return target


def append_trajectory_collection_h5(
    trajectory: FrozenTrajectory,
    config: RecorderConfig,
    *,
    path: Path | str | None,
    name: str | None,
    index: int,
) -> Path:
    """Append one completed v2 trajectory and flush its grouped H5 container.

    This is intentionally episode-granular: a successful trajectory is durable
    before the next ``env.reset()`` begins, while observations remain buffered
    only for the current episode.
    """

    import h5py

    if config.schema_version != "v2":
        raise ValueError("trajectory collections support only task-env-h5/v2")
    if index < 0:
        raise ValueError("trajectory collection index must be non-negative")
    trajectory.validate()
    directory = Path.cwd() if path is None else Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    filename = name or "trajectories.h5"
    if not filename.endswith(".h5"):
        filename += ".h5"
    target = directory / filename
    group_name = f"traj_{index:03d}"
    created = not target.exists()
    with h5py.File(target, "x" if created else "r+") as root:
        if created:
            root.attrs.update(
                schema_id="task-env-h5",
                schema_version="v2",
                container_type="trajectory_collection",
                container_version="v1",
                trajectory_count=0,
            )
        elif (
            str(root.attrs.get("schema_id", "")) != "task-env-h5"
            or str(root.attrs.get("schema_version", "")) != "v2"
            or str(root.attrs.get("container_type", "")) != "trajectory_collection"
        ):
            raise ValueError(f"not a task-env-h5/v2 trajectory collection: {target}")
        if group_name in root:
            raise FileExistsError(f"trajectory group already exists: {target}:{group_name}")
        group = root.create_group(group_name)
        try:
            _save_v2(group, trajectory, config)
        except Exception:
            del root[group_name]
            raise
        root.attrs["trajectory_count"] = int(index) + 1
        root.flush()
    return target


def _read_text(root, path: str) -> str:
    value = root[path][()]
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _inspect_v2_group(group) -> dict[str, Any]:
    result = {
        "schema_id": str(group.attrs.get("schema_id", "")),
        "schema_version": str(group.attrs.get("schema_version", "")),
        "transition_count": int(group.attrs.get("transition_count", 0)),
        "observation_count": int(group.attrs.get("observation_count", 0)),
    }
    result["env_meta"] = load_metadata(_read_text(group, "meta/env_meta"))
    result["env_cfg"] = load_metadata(_read_text(group, "meta/env_cfg"))
    if "meta/episode_meta" in group:
        result["episode_meta"] = load_metadata(_read_text(group, "meta/episode_meta"))
    return result


def inspect_trajectory_h5(path: Path | str) -> dict[str, Any]:
    """Inspect a v1 or v2 container without interpreting action values."""
    import h5py

    with h5py.File(Path(path), "r") as root:
        if str(root.attrs.get("container_type", "")) == "trajectory_collection":
            trajectories = []
            for name in sorted(key for key in root if str(key).startswith("traj_")):
                trajectories.append({"name": name, **_inspect_v2_group(root[name])})
            return {
                "schema_id": str(root.attrs.get("schema_id", "")),
                "schema_version": str(root.attrs.get("schema_version", "")),
                "container_type": "trajectory_collection",
                "trajectory_count": len(trajectories),
                "trajectories": trajectories,
            }
        result = {"schema_id": str(root.attrs.get("schema_id", "")), "schema_version": str(root.attrs.get("schema_version", "")), "transition_count": int(root.attrs.get("transition_count", 0)), "observation_count": int(root.attrs.get("observation_count", 0))}
        if result["schema_version"] in {"v2", "v3"}:
            result.update(_inspect_v2_group(root))
        elif "meta/layout_json" in root:
            result["layout"] = json.loads(_read_text(root, "meta/layout_json"))
    return result


def load_structured_control_records_h5(path: Path | str) -> dict[str, Any]:
    """Read and validate the v3 structured-control/event/outcome payload."""
    import h5py

    with h5py.File(Path(path), "r") as root:
        if str(root.attrs.get("schema_id", "")) != "task-env-h5" or str(root.attrs.get("schema_version", "")) != "v3":
            raise ValueError("structured control reader requires task-env-h5/v3")
        episode_complete = root.attrs.get("episode_complete")
        if not isinstance(episode_complete, (bool, np.bool_)) or not bool(episode_complete):
            raise ValueError("task-env-h5/v3 reader requires a finalized episode")
        required = {
            "meta/structured_controls_v1_json", "meta/boundary_events_v1_json",
            "meta/episode_outcome_v1_json", "meta/training_projection_v1_json", "meta/env_meta",
        }
        if any(name not in root for name in required):
            raise ValueError("task-env-h5/v3 structured records are incomplete")
        controls_raw = json.loads(_read_text(root, "meta/structured_controls_v1_json"))
        events_raw = json.loads(_read_text(root, "meta/boundary_events_v1_json"))
        outcome_raw = json.loads(_read_text(root, "meta/episode_outcome_v1_json"))
        training_projection = json.loads(_read_text(root, "meta/training_projection_v1_json"))
        env_meta = load_metadata(_read_text(root, "meta/env_meta"))
        transition_count = int(root.attrs["transition_count"])
        observation_count = int(root.attrs["observation_count"])
        stop_reason = str(root.attrs.get("stop_reason", ""))
    if observation_count != transition_count + 1 or len(controls_raw) != transition_count:
        raise ValueError("task-env-h5/v3 T/T+1 or structured control count mismatch")
    if transition_count and any(item is None for item in controls_raw):
        raise ValueError("task-env-h5/v3 has an unrecorded structured control transition")
    controls = tuple(
        None if item is None else StructuredControlTransitionV1.from_mapping(item)
        for item in controls_raw
    )
    events = tuple(BoundaryEventV1.from_mapping(item) for item in events_raw)
    outcome = EpisodeOutcomeV1.from_mapping(outcome_raw)
    validate_episode_records(events, outcome, transition_count)
    if outcome.end_reason != stop_reason:
        raise ValueError("EpisodeOutcome end_reason does not match the stored stop reason")
    return {
        "schema_id": "task-env-h5", "schema_version": "v3",
        "transition_count": transition_count, "observation_count": observation_count,
        "env_meta": env_meta, "structured_controls": controls,
        "boundary_events": events, "outcome": outcome,
        "training_projection": training_projection,
    }


def load_leaf_control_records_h5(path: Path | str) -> dict[str, Any]:
    """Independently validate R02c leaf Target/command/Ack against v3 metadata and observations."""
    from task_env.artifacts.state import StateBoundaryIdentity, StateSampleClock
    from task_env.controllers.canonical.leaf_profiles import decode_leaf_application_ack, decode_leaf_target
    from task_env.runtime.sessions.leaf_control import LeafPreparedCommandV1

    generic = load_structured_control_records_h5(path)
    profile = generic['env_meta'].get('reference_profile')
    if isinstance(profile, Mapping) and profile.get('profile_id') == 'r03c-attached-entity-position-leaves-v1':
        return _load_attached_leaf_control_records_h5(Path(path), generic, profile)
    required_profile = {
        'schema_version', 'profile_id', 'task_artifact_identity_hash',
        'task_source_identity_sha256', 'scene_identity_hash', 'source_id',
        'source_closure_digest', 'effective_leaf_plan_identity_sha256',
        'preset_identity_sha256', 'reset_plan_identity_hash', 'reset_sample_id',
        'provider', 'provider_version', 'provider_build_sha256', 'backend',
        'physics_dt_s', 'control_substeps', 'control_dt_s',
        'materialization_identity_sha256', 'configuration_revision', 'writers',
    }
    if (not isinstance(profile, Mapping) or set(profile) != required_profile
            or profile.get('schema_version') != 'leaf-position-recording-profile-v1'
            or profile.get('profile_id') != 'r02c-independent-position-leaves-v1'):
        raise ValueError('task-env-h5/v3 does not contain the exact R02c leaf recording profile')
    writers = profile['writers']
    if not isinstance(writers, list) or len(writers) != 2:
        raise ValueError('R02c H5 metadata must identify exactly two leaf writers')
    writer_by_id = {}
    for writer in writers:
        if not isinstance(writer, Mapping) or set(writer) != {
            'writer_id', 'profile_kind', 'action_schema_id', 'binding_identity_sha256',
            'effective_configuration_identity_sha256', 'member_path', 'entity_id',
            'control_group_id', 'joint_order', 'actuator_order',
        }:
            raise ValueError('R02c H5 writer binding metadata has unknown or missing fields')
        if writer['writer_id'] in writer_by_id:
            raise ValueError('R02c H5 writer identity is duplicated')
        writer_by_id[writer['writer_id']] = writer
    if {item.get('profile_kind') for item in writers} != {'arm_position', 'hand_position'}:
        raise ValueError('R02c H5 must bind one Arm and one Position Hand leaf')
    if (profile['provider'], profile['provider_version'], profile['backend'],
            profile['physics_dt_s'], profile['control_substeps'], profile['control_dt_s']) != (
            'mujoco', '3.8.1', 'cpu', 0.002, 5, 0.01):
        raise ValueError('R02c H5 Provider/timebase metadata differs from the admitted source route')
    transition_count = generic['transition_count']
    observation_count = generic['observation_count']
    if transition_count != 64 or observation_count != 65:
        raise ValueError('R02c H5 requires exactly 64 transitions and 65 observations')
    with __import__('h5py').File(Path(path), 'r') as root:
        if 'obs/state/boundary_identity_sha256' not in root:
            raise ValueError('R02c H5 lacks the independent stored state-boundary observation')
        state_boundary_digests = np.asarray(root['obs/state/boundary_identity_sha256'][...])
    if state_boundary_digests.shape != (65, 32) or state_boundary_digests.dtype != np.uint8:
        raise ValueError('R02c H5 state-boundary observation has the wrong shape or dtype')
    controls = generic['structured_controls']
    for index, control in enumerate(controls):
        if (control is None or control.request.scene_identity_hash != profile['scene_identity_hash']
                or control.request.binding_identity_hash != profile['effective_leaf_plan_identity_sha256']):
            raise ValueError(f'R02c transition {index} is not bound to the H5 Scene/plan')
        if len(control.writer_controls) != 2:
            raise ValueError(f'R02c transition {index} must record exactly two leaf writers')
        records = {item['writer_id']: item for item in control.writer_controls}
        if set(records) != set(writer_by_id):
            raise ValueError(f'R02c transition {index} omits or duplicates a leaf writer')
        seen_slots = set()
        for writer_id, writer_meta in writer_by_id.items():
            row = records[writer_id]
            canonical = row['canonical_action']
            if not isinstance(canonical, Mapping) or canonical.get('schema_version') != 'leaf-canonical-action-v1':
                raise ValueError(f'R02c transition {index}/{writer_id} lacks a versioned canonical command')
            for key, expected in (
                ('source_closure_sha256', profile['source_closure_digest']),
                ('effective_plan_identity_sha256', profile['effective_leaf_plan_identity_sha256']),
                ('materialization_identity_sha256', profile['materialization_identity_sha256']),
                ('configuration_identity_sha256', writer_meta['effective_configuration_identity_sha256']),
            ):
                if canonical.get(key) != expected:
                    raise ValueError(f'R02c transition {index}/{writer_id} has mismatched {key}')
            target = decode_leaf_target(row['controller_target']['payload'])
            if (target.identity_hash != row['controller_target']['identity_hash']
                    or target.writer_id != writer_id
                    or target.binding_identity_hash != writer_meta['binding_identity_sha256']
                    or target.scene_identity_hash != profile['scene_identity_hash']
                    or target.source_closure_sha256 != profile['source_closure_digest']
                    or target.action_schema_id != writer_meta['action_schema_id']
                    or tuple(ref.joint_id for ref in target.joint_order) != tuple(writer_meta['joint_order'])
                    or tuple(ref.actuator_id for ref in target.actuator_order) != tuple(writer_meta['actuator_order'])
                    or any(ref.entity_id != writer_meta['entity_id']
                           for ref in (*target.joint_order, *target.actuator_order))
                    or canonical.get('target_identity_sha256') != target.identity_hash):
                raise ValueError(f'R02c transition {index}/{writer_id} Target identity/source mismatch')
            if json.dumps(plain_metadata(row['requested_action'].get('payload')), sort_keys=True, separators=(',', ':'),
                          allow_nan=False) != json.dumps(target.action.to_mapping(), sort_keys=True,
                                                       separators=(',', ':'), allow_nan=False):
                raise ValueError(f'R02c transition {index}/{writer_id} requested Action differs from the Target')
            command = LeafPreparedCommandV1.from_mapping(canonical['prepared_command'])
            if (command.command_identity_sha256 != canonical.get('command_identity_sha256')
                    or command.target != target or command.writer_id != writer_id
                    or command.effective_plan_identity_sha256 != profile['effective_leaf_plan_identity_sha256']
                    or command.binding_identity_sha256 != writer_meta['binding_identity_sha256']
                    or command.effective_configuration_identity_sha256
                    != writer_meta['effective_configuration_identity_sha256']
                    or command.materialization_identity_sha256 != profile['materialization_identity_sha256']
                    or command.state_boundary != target.source_boundary
                    or command.state_configuration_revision != profile['configuration_revision']):
                raise ValueError(f'R02c transition {index}/{writer_id} prepared command identity mismatch')
            ack = decode_leaf_application_ack(canonical['application_ack'])
            applied = row['applied_control']
            applied_payload = applied['payload']
            applied_ack = decode_leaf_application_ack(applied_payload['ack'])
            if (ack != applied_ack or applied['target_hash'] != target.identity_hash
                    or ack.target_identity_hash != target.identity_hash
                    or applied_payload.get('writer_id') != writer_id
                    or applied_payload.get('command_identity_sha256') != command.command_identity_sha256
                    or applied_payload.get('materialization_identity_sha256') != profile['materialization_identity_sha256']
                    or ack.writer_id != writer_id
                    or ack.binding_identity_hash != writer_meta['binding_identity_sha256']
                    or ack.source_closure_sha256 != profile['source_closure_digest']
                    or ack.scene_identity_hash != profile['scene_identity_hash']
                    or ack.joint_order != target.joint_order
                    or ack.actuator_order != target.actuator_order
                    or ack.source_boundary != target.source_boundary
                    or ack.source_sample_clock != target.sample_clock
                    or ack.application_sample_clock != target.sample_clock):
                raise ValueError(f'R02c transition {index}/{writer_id} application Ack/command mismatch')
            slots = tuple(item.ctrl_slot for item in command.slot_values)
            if (tuple(applied_payload.get('applied_slots', ())) != slots
                    or seen_slots.intersection(slots)):
                raise ValueError(f'R02c transition {index}/{writer_id} duplicate/mismatched native ctrl slots')
            seen_slots.update(slots)
            source = target.source_boundary
            next_boundary = StateBoundaryIdentity.from_mapping(canonical['next_boundary'])
            if (source.control_step != index or next_boundary.control_step != index + 1
                    or ack.source_boundary != source
                    or ack.application_boundary.control_step != index
                    or (source.episode_id, source.reset_sample_id, source.scene_identity_hash,
                        source.provider_materialization_id) != (
                        next_boundary.episode_id, next_boundary.reset_sample_id,
                        next_boundary.scene_identity_hash, next_boundary.provider_materialization_id)
                    or target.sample_clock.sample_index != index
                    or not math.isclose(
                        target.sample_clock.simulation_time_s,
                        index * profile['control_dt_s'], rel_tol=0.0, abs_tol=1e-12,
                    )
                    or ack.application_sample_clock != target.sample_clock):
                raise ValueError(f'R02c transition {index}/{writer_id} boundary/clock sequence mismatch')
            if (canonical.get('source_boundary') != source.to_mapping()
                    or canonical.get('application_boundary') != ack.application_boundary.to_mapping()):
                raise ValueError(f'R02c transition {index}/{writer_id} Target/Ack boundaries disagree')
            for boundary_index, boundary in ((index, source), (index + 1, next_boundary)):
                digest = bytes(state_boundary_digests[boundary_index]).hex()
                if digest != boundary.boundary_id.removeprefix('state-boundary-'):
                    raise ValueError(f'R02c transition {index}/{writer_id} boundary differs from stored observation')
    generic['leaf_profile'] = profile
    generic['leaf_writer_ids'] = tuple(sorted(writer_by_id))
    return generic


def _load_attached_leaf_control_records_h5(path: Path, generic: dict[str, Any], profile: Mapping) -> dict[str, Any]:
    """Strict offline reader for the R03c fixed Attachment + two Entity leaf receipt chain."""
    from task_env.artifacts.state import StateBoundaryIdentity
    from task_env.controllers.canonical.leaf_profiles import decode_leaf_application_ack, decode_leaf_target
    from task_env.runtime.sessions.leaf_control import LeafPreparedCommandV1

    required = {
        'schema_version', 'profile_id', 'task_artifact_identity_hash', 'task_source_identity_sha256',
        'scene_identity_hash', 'source_id', 'source_closure_digest',
        'effective_leaf_plan_identity_sha256', 'preset_identity_sha256', 'reset_plan_identity_hash',
        'reset_sample_id', 'provider', 'provider_version', 'provider_build_sha256', 'backend',
        'physics_dt_s', 'control_substeps', 'control_dt_s', 'materialization_identity_sha256',
        'configuration_revision', 'attachment_plan_identity_sha256', 'assembly_identity_sha256',
        'attachment_receipt', 'attachment_receipt_identity_sha256', 'leaf_materialization_receipt',
        'leaf_materialization_receipt_identity_sha256', 'provider_materialization_id', 'episode_id',
        'arm_active', 'hand_active', 'writers',
    }
    if set(profile) != required or profile.get('schema_version') != 'leaf-position-recording-profile-v1':
        raise ValueError('R03c H5 metadata does not match the exact attached-leaf profile schema')
    if (profile['provider'], profile['provider_version'], profile['backend'],
            profile['physics_dt_s'], profile['control_substeps'], profile['control_dt_s']) != (
            'mujoco', '3.8.1', 'cpu', 0.002, 5, 0.01):
        raise ValueError('R03c H5 Provider/timebase differs from the bounded native contract')
    if (type(profile['arm_active']) is not bool or type(profile['hand_active']) is not bool
            or profile['episode_id'] not in {'E1', 'E2', 'E3', 'E4'}):
        raise ValueError('R03c H5 episode identity/activity metadata is invalid')
    if (generic['transition_count'], generic['observation_count']) != (64, 65):
        raise ValueError('R03c H5 requires exactly 64 transitions and 65 observations')

    attachment = profile['attachment_receipt']
    if not isinstance(attachment, Mapping):
        raise ValueError('R03c H5 lacks its same-Env fixed Attachment model receipt')
    receipt_payload = dict(attachment)
    receipt_hash = receipt_payload.pop('receipt_identity_sha256', None)
    calculated_receipt_hash = hashlib.sha256(json.dumps(
        receipt_payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False,
    ).encode()).hexdigest()
    if (receipt_hash != calculated_receipt_hash
            or receipt_hash != profile['attachment_receipt_identity_sha256']
            or attachment.get('schema_version') != 'fixed-attachment-model-receipt-v1'
            or attachment.get('provider') != 'mujoco' or attachment.get('backend') != 'cpu'
            or attachment.get('provider_materialization_id') != profile['provider_materialization_id']
            or attachment.get('task_artifact_sha256') != profile['task_artifact_identity_hash']
            or attachment.get('scene_identity_sha256') != profile['scene_identity_hash']
            or attachment.get('assembly_identity_sha256') != profile['assembly_identity_sha256']
            or attachment.get('attachment_plan_sha256') != profile['attachment_plan_identity_sha256']
            or attachment.get('source_closure_sha256') != profile['source_closure_digest']):
        raise ValueError('R03c Attachment receipt identity/source/Runtime binding mismatch')
    dimensions = attachment.get('dimensions', {})
    if tuple(dimensions.get(key) for key in ('nq', 'nv', 'nu', 'njnt', 'neq', 'ntendon')) != (9, 9, 8, 9, 1, 1):
        raise ValueError('R03c Attachment receipt dimensions differ from the exact fixed tree')
    fixed_root = attachment.get('fixed_root', {})
    if (fixed_root.get('parent_entity_id'), fixed_root.get('child_entity_id'),
            fixed_root.get('parent_mount'), fixed_root.get('child_mount'), fixed_root.get('root_policy')) != (
            'panda-arm', 'panda-hand', 'panda-arm/attachment_site', 'panda-hand/hand',
            'fixed_child_root_under_parent_mount_no_free_joint'):
        raise ValueError('R03c fixed Attachment root receipt is not the selected two-Entity mount')

    canonical_native = {
        'joints': {
            **{f'panda-arm/joint{i}': f'joint{i}' for i in range(1, 8)},
            'panda-hand/finger_joint1': 'probe_hand_finger_joint1',
            'panda-hand/finger_joint2': 'probe_hand_finger_joint2',
        },
        'actuators': {**{f'panda-arm/actuator{i}': f'actuator{i}' for i in range(1, 8)},
                      'panda-hand/actuator8': 'probe_hand_actuator8'},
        'bodies': {'panda-arm/link7': 'link7', 'panda-hand/hand': 'probe_hand_hand'},
        'tendons': {'panda-hand/split': 'probe_hand_split'},
    }
    for receipt_key, section_key in (('native_joint_mappings', 'joints'),
                                     ('native_actuator_mappings', 'actuators'),
                                     ('native_body_mappings', 'bodies'),
                                     ('native_tendon_mappings', 'tendons')):
        mappings = attachment.get(receipt_key)
        if not isinstance(mappings, Mapping):
            raise ValueError(f'R03c Attachment receipt omits {receipt_key}')
        for canonical, native_name in canonical_native[section_key].items():
            if mappings.get(canonical, {}).get('native_name') != native_name:
                raise ValueError(f'R03c Attachment native map mismatch for {canonical}')

    leaf_receipt = profile['leaf_materialization_receipt']
    if not isinstance(leaf_receipt, Mapping):
        raise ValueError('R03c H5 lacks its leaf materialization receipt')
    leaf_identity_payload = {
        'schema_version': leaf_receipt['schema_version'],
        'provenance_kind': leaf_receipt['provenance_kind'],
        'scene_identity_sha256': leaf_receipt['scene_identity_sha256'],
        'source_closure_sha256': leaf_receipt['source_closure_sha256'],
        'effective_plan_identity_sha256': leaf_receipt['effective_plan_identity_sha256'],
        'provider_name': leaf_receipt['provider_name'], 'provider_version': leaf_receipt['provider_version'],
        'provider_build_sha256': leaf_receipt['provider_build_sha256'], 'backend': leaf_receipt['backend'],
        'materialization_id': leaf_receipt['materialization_id'],
        'configuration_revision': leaf_receipt['configuration_revision'],
        'dimensions': tuple(leaf_receipt[name] for name in ('nq', 'nv', 'nu', 'njnt', 'nbody', 'neq', 'ntendon')),
        'joints': leaf_receipt['joints'], 'actuators': leaf_receipt['actuators'],
        'frames': leaf_receipt['frames'], 'tendons': leaf_receipt['tendons'],
        'equality_identities': leaf_receipt['equality_identities'],
    }
    if leaf_receipt.get('fixed_attachment_receipt_identity_sha256') is not None:
        leaf_identity_payload['fixed_attachment_receipt_identity_sha256'] = (
            leaf_receipt['fixed_attachment_receipt_identity_sha256']
        )
    leaf_hash = hashlib.sha256(json.dumps(
        leaf_identity_payload, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False,
    ).encode()).hexdigest()
    if (leaf_hash != profile['leaf_materialization_receipt_identity_sha256']
            or leaf_hash != profile['materialization_identity_sha256']
            or leaf_receipt.get('fixed_attachment_receipt_identity_sha256') != receipt_hash
            or leaf_receipt.get('materialization_id') != profile['provider_materialization_id']
            or leaf_receipt.get('effective_plan_identity_sha256') != profile['effective_leaf_plan_identity_sha256']
            or leaf_receipt.get('scene_identity_sha256') != profile['scene_identity_hash']
            or leaf_receipt.get('source_closure_sha256') != profile['source_closure_digest']
            or leaf_receipt.get('provider_name') != profile['provider']
            or leaf_receipt.get('provider_version') != profile['provider_version']
            or leaf_receipt.get('provider_build_sha256') != profile['provider_build_sha256']
            or leaf_receipt.get('backend') != profile['backend']
            or leaf_receipt.get('configuration_revision') != profile['configuration_revision']):
        raise ValueError('R03c leaf receipt is not bound to the same Attachment Runtime/plan')

    writers = profile['writers']
    if not isinstance(writers, list) or len(writers) != 2:
        raise ValueError('R03c H5 must bind exactly two Entity leaf writers')
    expected_writer_fields = {
        'writer_id', 'profile_kind', 'action_schema_id', 'binding_identity_sha256',
        'effective_configuration_identity_sha256', 'member_path', 'entity_id',
        'control_group_id', 'joint_order', 'actuator_order', 'tcp_frame',
    }
    writer_by_id = {}
    for writer in writers:
        if not isinstance(writer, Mapping) or set(writer) != expected_writer_fields:
            raise ValueError('R03c writer metadata has an unknown or missing bound field')
        if writer['writer_id'] in writer_by_id:
            raise ValueError('R03c writer identity is duplicated')
        writer_by_id[writer['writer_id']] = writer
    expected_owner = {
        'panda-arm/arm-position-leaf': ('arm_position', 'panda-arm', 'arm-position', ['arm']),
        'panda-hand/hand-position-leaf': ('hand_position', 'panda-hand', 'hand-position', ['hand']),
    }
    for writer_id, (kind, entity, group, path_members) in expected_owner.items():
        writer = writer_by_id.get(writer_id)
        if (writer is None or writer['profile_kind'] != kind or writer['entity_id'] != entity
                or writer['control_group_id'] != group or writer['member_path'] != path_members):
            raise ValueError(f'R03c writer {writer_id} is not bound to its exact Assembly Entity/Group')
    leaf_joints = {item['canonical_joint']['entity_id'] + '/' + item['canonical_joint']['joint_id']: item
                   for item in leaf_receipt['joints']}
    leaf_actuators = {item['canonical_actuator']['entity_id'] + '/' + item['canonical_actuator']['actuator_id']: item
                      for item in leaf_receipt['actuators']}
    leaf_frames = {item['canonical_frame']['entity_id'] + '/' + item['canonical_frame']['frame_id']: item
                   for item in leaf_receipt['frames']}
    for writer_id, writer in writer_by_id.items():
        for entity, joint in writer['joint_order']:
            key = f'{entity}/{joint}'
            mapped = leaf_joints.get(key)
            if mapped is None or mapped['native_name'] != canonical_native['joints'][key]:
                raise ValueError(f'R03c leaf Joint native receipt mismatch: {key}')
        for entity, actuator in writer['actuator_order']:
            key = f'{entity}/{actuator}'
            mapped = leaf_actuators.get(key)
            if mapped is None or mapped['native_name'] != canonical_native['actuators'][key]:
                raise ValueError(f'R03c leaf Actuator native receipt mismatch: {key}')
            attachment_actuator = attachment['native_actuator_mappings'][key]
            if (mapped['ctrl_slot'] != attachment_actuator['ctrl_slot']
                    or mapped['native_actuator_id'] != attachment_actuator['actuator_id']):
                raise ValueError(f'R03c leaf Actuator slot differs from Attachment receipt: {key}')
        entity, frame = writer['tcp_frame']
        key = f'{entity}/{frame}'
        mapped = leaf_frames.get(key)
        if mapped is None or mapped['native_name'] != canonical_native['bodies'][key]:
            raise ValueError(f'R03c leaf TCP native receipt mismatch: {key}')

    with __import__('h5py').File(path, 'r') as root:
        required_arrays = {
            'obs/state/boundary_identity_sha256': ((65, 32), np.dtype(np.uint8)),
            'obs/state/entities/panda-arm/joint_position': ((65, 7), np.dtype(np.float32)),
            'obs/state/entities/panda-hand/joint_position': ((65, 2), np.dtype(np.float32)),
            'obs/state/entities/panda-arm/hand_pose': ((65, 7), np.dtype(np.float32)),
            'obs/state/entities/panda-hand/hand_pose': ((65, 7), np.dtype(np.float32)),
        }
        arrays = {}
        for dataset_path, (shape, dtype) in required_arrays.items():
            if dataset_path not in root:
                raise ValueError(f'R03c H5 lacks stored typed observation {dataset_path}')
            array = np.asarray(root[dataset_path][...])
            if array.shape != shape or array.dtype != dtype or not np.isfinite(array).all():
                raise ValueError(f'R03c H5 stored observation shape/dtype/finite mismatch: {dataset_path}')
            arrays[dataset_path] = array
        arm = arrays['obs/state/entities/panda-arm/joint_position']
        fingers = arrays['obs/state/entities/panda-hand/joint_position']
        opening = fingers.sum(axis=1)
        home = np.asarray((0.0, 0.0, 0.0, -1.57079, 0.0, 1.57079, -0.7853), dtype=np.float64)
        if np.max(np.abs(arm[-1].astype(np.float64) - home)) > 0.02:
            raise ValueError('R03c stored Arm final state is outside the home-return gate')
        if profile['arm_active'] and np.max(np.abs(arm[:, 0].astype(np.float64) - home[0])) < 0.08:
            raise ValueError('R03c stored Arm motion does not reach the required joint1 excursion')
        if float(opening[-1]) < 0.06:
            raise ValueError('R03c stored Hand opening does not return to the final open gate')
        if profile['hand_active'] and (
                float(np.min(opening[16:33])) > 0.02
                or float(np.max(opening) - np.min(opening)) < 0.04
                or np.max(np.abs(fingers[:, 0] - fingers[:, 1])) > 1e-4):
            raise ValueError('R03c stored Hand motion/equality differs from its closed-phase gate')
        hand_pose = arrays['obs/state/entities/panda-hand/hand_pose'][:, 3:7].astype(np.float64)
        norms = np.linalg.norm(hand_pose, axis=1, keepdims=True)
        if np.any(norms <= 1e-12):
            raise ValueError('R03c stored Hand rotation contains a zero quaternion')
        quats = hand_pose / norms
        dots = np.clip(np.abs(quats @ quats[0]), 0.0, 1.0)
        rotation_excursion = float(np.max(2.0 * np.arccos(dots)))
        if profile['arm_active'] and rotation_excursion < 0.05:
            raise ValueError('R03c stored attached Hand root did not follow active Arm rotation')
        state_boundary_digests = arrays['obs/state/boundary_identity_sha256']

    controls = generic['structured_controls']
    for index, control in enumerate(controls):
        if (control is None or control.request.scene_identity_hash != profile['scene_identity_hash']
                or control.request.binding_identity_hash != profile['effective_leaf_plan_identity_sha256']):
            raise ValueError(f'R03c transition {index} is not bound to the H5 Scene/plan')
        if len(control.writer_controls) != 2:
            raise ValueError(f'R03c transition {index} must record exactly two writers')
        records = {item['writer_id']: item for item in control.writer_controls}
        if set(records) != set(writer_by_id):
            raise ValueError(f'R03c transition {index} omits or duplicates an Entity writer')
        seen_slots = set()
        for writer_id, writer_meta in writer_by_id.items():
            row = records[writer_id]
            canonical = row['canonical_action']
            for key, expected_value in (
                ('source_closure_sha256', profile['source_closure_digest']),
                ('effective_plan_identity_sha256', profile['effective_leaf_plan_identity_sha256']),
                ('materialization_identity_sha256', profile['materialization_identity_sha256']),
                ('configuration_identity_sha256', writer_meta['effective_configuration_identity_sha256']),
            ):
                if canonical.get(key) != expected_value:
                    raise ValueError(f'R03c transition {index}/{writer_id} mismatched {key}')
            target = decode_leaf_target(row['controller_target']['payload'])
            expected_joints = tuple((entity, joint) for entity, joint in writer_meta['joint_order'])
            expected_actuators = tuple((entity, actuator) for entity, actuator in writer_meta['actuator_order'])
            if (target.identity_hash != row['controller_target']['identity_hash']
                    or target.writer_id != writer_id
                    or target.binding_identity_hash != writer_meta['binding_identity_sha256']
                    or target.scene_identity_hash != profile['scene_identity_hash']
                    or target.source_closure_sha256 != profile['source_closure_digest']
                    or target.action_schema_id != writer_meta['action_schema_id']
                    or tuple((ref.entity_id, ref.joint_id) for ref in target.joint_order) != expected_joints
                    or tuple((ref.entity_id, ref.actuator_id) for ref in target.actuator_order) != expected_actuators):
                raise ValueError(f'R03c transition {index}/{writer_id} Target binding mismatch')
            if json.dumps(plain_metadata(row['requested_action'].get('payload')), sort_keys=True,
                          separators=(',', ':'), allow_nan=False) != json.dumps(
                    target.action.to_mapping(), sort_keys=True, separators=(',', ':'), allow_nan=False):
                raise ValueError(f'R03c transition {index}/{writer_id} Action differs from typed Target')
            command = LeafPreparedCommandV1.from_mapping(canonical['prepared_command'])
            if (command.command_identity_sha256 != canonical.get('command_identity_sha256')
                    or command.target != target or command.writer_id != writer_id
                    or command.effective_plan_identity_sha256 != profile['effective_leaf_plan_identity_sha256']
                    or command.binding_identity_sha256 != writer_meta['binding_identity_sha256']
                    or command.effective_configuration_identity_sha256
                    != writer_meta['effective_configuration_identity_sha256']
                    or command.materialization_identity_sha256 != profile['materialization_identity_sha256']
                    or command.state_boundary != target.source_boundary
                    or command.state_configuration_revision != profile['configuration_revision']):
                raise ValueError(f'R03c transition {index}/{writer_id} prepared command mismatch')
            ack = decode_leaf_application_ack(canonical['application_ack'])
            applied = row['applied_control']
            payload = applied['payload']
            applied_ack = decode_leaf_application_ack(payload['ack'])
            slots = tuple(item.ctrl_slot for item in command.slot_values)
            if (ack != applied_ack or ack.target_identity_hash != target.identity_hash
                    or ack.writer_id != writer_id
                    or ack.binding_identity_hash != writer_meta['binding_identity_sha256']
                    or ack.source_closure_sha256 != profile['source_closure_digest']
                    or ack.scene_identity_hash != profile['scene_identity_hash']
                    or ack.joint_order != target.joint_order or ack.actuator_order != target.actuator_order
                    or ack.source_boundary != target.source_boundary
                    or ack.source_sample_clock != target.sample_clock
                    or ack.application_sample_clock != target.sample_clock
                    or payload.get('writer_id') != writer_id
                    or payload.get('materialization_identity_sha256') != profile['materialization_identity_sha256']
                    or tuple(payload.get('applied_slots', ())) != slots
                    or applied.get('target_hash') != target.identity_hash
                    or seen_slots.intersection(slots)):
                raise ValueError(f'R03c transition {index}/{writer_id} Ack/slot evidence mismatch')
            seen_slots.update(slots)
            if any(not 0 <= item.ctrl_slot < dimensions['nu'] for item in command.slot_values):
                raise ValueError(f'R03c transition {index}/{writer_id} slot exceeds fixed model dimensions')
            for item in command.slot_values:
                key = f'{item.actuator.entity_id}/{item.actuator.actuator_id}'
                mapped = leaf_actuators.get(key)
                if mapped is None or item.ctrl_slot != mapped['ctrl_slot']:
                    raise ValueError(f'R03c transition {index}/{writer_id} command slot differs from its Actuator receipt')
            source = target.source_boundary
            next_boundary = StateBoundaryIdentity.from_mapping(canonical['next_boundary'])
            if (source.control_step != index or next_boundary.control_step != index + 1
                    or source.reset_sample_id != profile['reset_sample_id']
                    or source.provider_materialization_id != profile['provider_materialization_id']
                    or (source.episode_id, source.reset_sample_id, source.scene_identity_hash,
                        source.scene_instance_id, source.provider_materialization_id)
                    != (next_boundary.episode_id, next_boundary.reset_sample_id, next_boundary.scene_identity_hash,
                        next_boundary.scene_instance_id, next_boundary.provider_materialization_id)
                    or (ack.application_boundary.episode_id, ack.application_boundary.reset_sample_id,
                        ack.application_boundary.scene_identity_hash, ack.application_boundary.scene_instance_id,
                        ack.application_boundary.provider_materialization_id, ack.application_boundary.control_step)
                    != (source.episode_id, source.reset_sample_id, source.scene_identity_hash,
                        source.scene_instance_id, source.provider_materialization_id, source.control_step)
                    or target.sample_clock.sample_index != index
                    or not math.isclose(target.sample_clock.simulation_time_s,
                                        index * profile['control_dt_s'], rel_tol=0.0, abs_tol=1e-12)
                    or canonical.get('source_boundary') != source.to_mapping()
                    or canonical.get('application_boundary') != ack.application_boundary.to_mapping()):
                raise ValueError(f'R03c transition {index}/{writer_id} boundary/clock sequence mismatch')
            for boundary_index, boundary in ((index, source), (index + 1, next_boundary)):
                if bytes(state_boundary_digests[boundary_index]).hex() != boundary.boundary_id.removeprefix('state-boundary-'):
                    raise ValueError(f'R03c transition {index}/{writer_id} boundary differs from stored observation')
        if seen_slots != set(range(dimensions['nu'])):
            raise ValueError(f'R03c transition {index} does not bind the exact disjoint 7+1 slots')
    generic['leaf_profile'] = profile
    generic['leaf_writer_ids'] = tuple(sorted(writer_by_id))
    generic['attachment_receipt_identity_sha256'] = receipt_hash
    generic['stored_motion_oracle'] = {
        'arm_peak_joint1_rad': float(np.max(np.abs(arm[:, 0].astype(np.float64)))),
        'hand_final_opening_m': float(opening[-1]),
        'hand_rotation_excursion_rad': rotation_excursion,
    }
    return generic


def load_camera_observations_h5(path: Path | str) -> dict[str, Any]:
    """Strictly read the opt-in camera metadata extension on Generic H5 v3."""

    import h5py
    from task_env.observations.canonical_camera.consumer import (
        CameraObservationConfigV1,
        validate_camera_observation_boundaries,
    )

    with h5py.File(Path(path), "r") as root:
        if (str(root.attrs.get("schema_id", "")) != "task-env-h5"
                or str(root.attrs.get("schema_version", "")) != "v3"):
            raise ValueError("camera observation reader requires task-env-h5/v3")
        episode_complete = root.attrs.get("episode_complete")
        if not isinstance(episode_complete, (bool, np.bool_)) or not bool(episode_complete):
            raise ValueError("camera observation reader requires a finalized episode")
        required = {
            "meta/camera_observation_contract_v1_json",
            "meta/camera_observations_v1_json",
            "meta/camera_recording_binding_v1_json",
            "meta/env_meta",
        }
        if any(name not in root for name in required):
            raise ValueError("task-env-h5/v3 camera observation extension is incomplete")
        contract_raw = json.loads(_read_text(root, "meta/camera_observation_contract_v1_json"))
        observations_raw = json.loads(_read_text(root, "meta/camera_observations_v1_json"))
        raw_recording_binding = json.loads(_read_text(root, "meta/camera_recording_binding_v1_json"))
        observation_count = int(root.attrs.get("observation_count", -1))
        transition_count = int(root.attrs.get("transition_count", -1))
        env_meta = load_metadata(_read_text(root, "meta/env_meta"))
        if observation_count != transition_count + 1:
            raise ValueError("camera observation reader requires T+1 observation boundaries")
        contract = CameraObservationConfigV1.from_mapping(contract_raw)
        contract.capacity(max(1, transition_count))
        boundaries = validate_camera_observation_boundaries(
            observations_raw, expected_count=observation_count,
        )
        state_digest_path = "obs/state/boundary_identity_sha256"
        if state_digest_path not in root:
            raise ValueError("camera recording requires the actual Position state boundary digest dataset")
        state_digest_dataset = root[state_digest_path]
        if (state_digest_dataset.shape != (observation_count, 32)
                or state_digest_dataset.dtype != np.dtype(np.uint8)):
            raise ValueError("Position state boundary digest dataset must be T+1 rows of 32 uint8 bytes")
        state_digests = tuple(bytes(np.asarray(state_digest_dataset[index])) for index in range(observation_count))
        artifact_hash = boundaries[0].captures[0].capture_identity.task_artifact_hash
        geometries = {
            item.camera_id: item for item in contract.geometries(artifact_hash)
        }
        expected_boundary_identity = None
        for boundary in boundaries:
            for capture in boundary.captures:
                identity = capture.capture_identity
                geometry = geometries[capture.camera_id]
                if identity.camera_geometry_identity_hash != geometry.identity_hash:
                    raise ValueError("camera capture references another CameraGeometry")
                common_identity = (
                    identity.task_artifact_hash,
                    identity.render_source_identity_hash,
                    identity.execution_spec_identity_hash,
                    identity.provider_manifest_identity_hash,
                    identity.state_boundary.scene_identity_hash,
                    identity.state_boundary.scene_instance_id,
                    identity.state_boundary.provider_materialization_id,
                    identity.state_boundary.episode_id,
                    identity.state_boundary.reset_sample_id,
                )
                if expected_boundary_identity is None:
                    expected_boundary_identity = common_identity
                elif common_identity != expected_boundary_identity:
                    raise ValueError("camera observation identity changed inside one stored episode")
                for modality, expected_shape, expected_dtype in (
                    ("rgb", (observation_count, 3, contract.height, contract.width), np.dtype(np.uint8)),
                    ("depth", (observation_count, contract.height, contract.width), np.dtype(np.float32)),
                    ("entity_mask", (observation_count, contract.height, contract.width), np.dtype(np.uint32)),
                ):
                    dataset_path = f"obs/{modality}/{capture.camera_id}"
                    if dataset_path not in root:
                        raise ValueError(f"stored camera modality is missing: {dataset_path}")
                    dataset = root[dataset_path]
                    if dataset.shape != expected_shape or dataset.dtype != expected_dtype:
                        raise ValueError(f"stored camera modality schema mismatch: {dataset_path}")
                rgb = np.asarray(root[f"obs/rgb/{capture.camera_id}"][boundary.boundary_index])
                depth = np.asarray(root[f"obs/depth/{capture.camera_id}"][boundary.boundary_index])
                mask = np.asarray(root[f"obs/entity_mask/{capture.camera_id}"][boundary.boundary_index])
                if not np.isfinite(depth).all() or np.any(depth < 0):
                    raise ValueError("stored camera optical-Z depth is invalid")
                allowed_labels = {0, *(item.label for item in capture.canonical_label_map.labels)}
                if not set(np.unique(mask).tolist()).issubset(allowed_labels):
                    raise ValueError("stored Entity mask contains a label absent from its capture-bound LabelMap")
                mask_digest = hashlib.sha256(np.ascontiguousarray(mask).tobytes(order="C")).hexdigest()
                if mask_digest != capture.mask_sha256:
                    raise ValueError("stored Entity mask bytes do not match the capture-bound mask digest")
    structured_records = load_structured_control_records_h5(path)
    if structured_records["transition_count"] != transition_count:
        raise ValueError("camera recording transition count disagrees with typed structured records")
    projected_actions = load_structured_training_actions_h5(path)
    recording_binding = _validate_camera_recording_binding(
        raw_recording_binding, boundaries, state_digests, env_meta, structured_records,
        projected_actions, observation_count, transition_count,
    )
    return {
        "schema_version": "camera-observation-boundary-v1",
        "recording_binding_schema_version": recording_binding["schema_version"],
        "contract": contract,
        "observation_count": observation_count,
        "transition_count": transition_count,
        "boundaries": boundaries,
        "recording_binding": recording_binding,
        "env_meta": env_meta,
    }


def load_structured_training_actions_h5(path: Path | str) -> tuple[tuple[float, ...], ...]:
    """Apply the explicit lossless one-writer rule; never flatten arbitrary trees."""
    loaded = load_structured_control_records_h5(path)
    if loaded["training_projection"] != {
        "rule": "explicit-single-writer-schema-v1",
        "source": "structured_controls_v1_json",
        "automatic_flattening": False,
    }:
        raise ValueError("unknown structured training projection rule")
    schema = loaded["env_meta"].get("action_schema", {})
    schema_id = schema.get("schema_id")
    components = schema.get("order", ())
    if not schema_id or not components:
        raise ValueError("training conversion requires an explicit action schema identity and component order")
    controls = loaded["structured_controls"]
    if any(control is None for control in controls):
        raise ValueError("training conversion requires structured controls for every transition")
    projected = single_writer_training_actions(controls, action_schema_id=schema_id, components=components)
    import h5py
    with h5py.File(Path(path), "r") as root:
        stored = np.stack(
            [np.asarray(root[f"action/{name}"]).reshape(-1) for name in components], axis=1
        ) if components else np.empty((len(projected), 0), dtype=np.float32)
    expected = np.asarray(projected, dtype=np.float32).reshape(len(projected), len(components))
    if stored.shape != expected.shape or not np.array_equal(stored, expected):
        raise ValueError("stored action vector does not equal the explicit structured projection")
    return projected


def load_structured_training_episode_h5(path: Path | str) -> dict[str, Any]:
    """Load the declared v3 action/end consumer without rewriting step flags.

    Per-transition Gymnasium flags remain exactly as stored. The final outcome
    and bootstrap decision are returned separately because an external Stop
    does not retroactively turn the last already-returned transition into a
    truncation.
    """
    import h5py

    loaded = load_structured_control_records_h5(path)
    actions = load_structured_training_actions_h5(path)
    transition_count = loaded["transition_count"]
    with h5py.File(Path(path), "r") as root:
        terminated = np.asarray(root["terminated"], dtype=np.bool_)
        truncated = np.asarray(root["truncated"], dtype=np.bool_)
    if terminated.shape != (transition_count,) or truncated.shape != (transition_count,):
        raise ValueError("structured training episode transition flags must have length T")
    outcome = loaded["outcome"]
    if outcome.final_boundary != transition_count:
        raise ValueError("structured training episode outcome boundary does not match T")
    bootstrap = np.logical_not(np.logical_or(terminated, truncated))
    if transition_count:
        # Outcome is the final boundary policy, while the transition arrays
        # retain the original Gymnasium result returned by env.step().
        bootstrap[-1] = outcome.bootstrap_allowed
    return {
        "actions": actions,
        "transition_terminated": tuple(bool(value) for value in terminated),
        "transition_truncated": tuple(bool(value) for value in truncated),
        "transition_bootstrap_allowed": tuple(bool(value) for value in bootstrap),
        "final_outcome": outcome,
        "final_boundary": outcome.final_boundary,
        "end_reason": outcome.end_reason,
        "terminated": outcome.terminated,
        "truncated": outcome.truncated,
        "bootstrap_allowed": outcome.bootstrap_allowed,
    }


__all__ = [
    "append_trajectory_collection_h5",
    "inspect_trajectory_h5",
    "load_structured_control_records_h5",
    "load_structured_training_actions_h5",
    "load_structured_training_episode_h5",
    "save_trajectory_collection_h5",
    "save_trajectory_h5",
]
