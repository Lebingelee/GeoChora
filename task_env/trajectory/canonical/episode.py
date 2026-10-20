"""Shared versioned episode records used by the existing trajectory formats."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
import re

from ...artifacts.contracts import Contract
from ...controllers.canonical.contracts import StructuredActionRequestV1

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _nonempty(value: object, field: str) -> None:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")


def _json_value(value: object) -> None:
    try:
        json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("episode payloads must contain finite JSON values") from exc


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _mapping_hash(value: Mapping[str, object]) -> str:
    encoded = json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BoundaryEventV1(Contract):
    """A non-physics event ordered at a real control boundary."""

    schema_version: str
    episode_id: str
    boundary_index: int
    event_sequence: int
    event_id: str
    event_type: str
    source: str
    payload: Mapping[str, object]

    def validate(self) -> None:
        if self.schema_version != "boundary-event-v1":
            raise ValueError("unsupported BoundaryEvent schema")
        for name, value in (("episode_id", self.episode_id), ("event_id", self.event_id),
                            ("event_type", self.event_type), ("source", self.source)):
            _nonempty(value, name)
        if type(self.boundary_index) is not int or self.boundary_index < 0:
            raise ValueError("BoundaryEvent boundary_index must be a nonnegative integer")
        if type(self.event_sequence) is not int or self.event_sequence < 0:
            raise ValueError("BoundaryEvent event_sequence must be a nonnegative integer")
        if not isinstance(self.payload, Mapping) or any(type(key) is not str for key in self.payload):
            raise ValueError("BoundaryEvent payload must be a string-keyed mapping")
        _json_value(dict(self.payload))


@dataclass(frozen=True)
class EpisodeOutcomeV1(Contract):
    """Final episode boundary facts; flags never rewrite an earlier transition."""

    schema_version: str
    episode_id: str
    final_boundary: int
    end_reason: str
    terminated: bool
    truncated: bool
    bootstrap_allowed: bool
    task_success: bool | None = None
    solution_completed: bool | None = None

    def validate(self) -> None:
        if self.schema_version != "episode-outcome-v1":
            raise ValueError("unsupported EpisodeOutcome schema")
        _nonempty(self.episode_id, "episode_id")
        _nonempty(self.end_reason, "end_reason")
        if type(self.final_boundary) is not int or self.final_boundary < 0:
            raise ValueError("EpisodeOutcome final_boundary must be a nonnegative integer")
        if type(self.terminated) is not bool or type(self.truncated) is not bool:
            raise ValueError("EpisodeOutcome flags must be bool")
        if type(self.bootstrap_allowed) is not bool:
            raise ValueError("EpisodeOutcome bootstrap_allowed must be bool")
        if self.terminated and self.truncated:
            raise ValueError("EpisodeOutcome cannot be both terminated and truncated")
        if self.terminated and self.bootstrap_allowed:
            raise ValueError("terminated outcomes cannot bootstrap")
        for name, value in (("task_success", self.task_success),
                            ("solution_completed", self.solution_completed)):
            if value is not None and type(value) is not bool:
                raise ValueError(f"EpisodeOutcome {name} must be bool or None")


@dataclass(frozen=True)
class StructuredControlTransitionV1(Contract):
    """Lossless action/control evidence attached to one real transition."""

    schema_version: str
    request: StructuredActionRequestV1
    writer_controls: tuple[Mapping[str, object], ...]

    def validate(self) -> None:
        if self.schema_version != "structured-control-transition-v1":
            raise ValueError("unsupported structured control transition schema")
        if not isinstance(self.request, StructuredActionRequestV1):
            raise TypeError("structured control transition requires a typed request")
        if not self.writer_controls:
            raise ValueError("structured control transition requires writer outputs")
        writer_ids = []
        covered_groups: set[tuple[str, str]] = set()
        requested_groups = {(group.entity_id, group.group_id): group for group in self.request.groups}
        for writer in self.writer_controls:
            if not isinstance(writer, Mapping) or set(writer) != {
                "writer_id", "action_schema_id", "components", "groups",
                "requested_action", "canonical_action", "controller_target", "applied_control",
            }:
                raise ValueError("structured writer control fields")
            writer_id = writer["writer_id"]
            _nonempty(writer_id, "writer_id")
            writer_ids.append(writer_id)
            action_schema_id = writer["action_schema_id"]
            _nonempty(action_schema_id, "action_schema_id")
            components = writer["components"]
            if not isinstance(components, (tuple, list)) or not components or any(
                type(value) is not str or not value.strip() for value in components
            ) or len(components) != len(set(components)):
                raise ValueError("writer action components must be unique names")
            groups = writer["groups"]
            if not isinstance(groups, (tuple, list)) or not groups:
                raise ValueError("writer action groups are required")
            values_by_component: dict[str, float] = {}
            for projection in groups:
                if not isinstance(projection, Mapping) or set(projection) != {
                    "entity_id", "group_id", "action_components",
                }:
                    raise ValueError("writer group projection fields")
                key = (projection["entity_id"], projection["group_id"])
                if key in covered_groups or key not in requested_groups:
                    raise ValueError("structured group projection is duplicate or absent from request")
                group = requested_groups[key]
                if group.action_schema_id != action_schema_id:
                    raise ValueError("group/writer action schema mismatch")
                names = projection["action_components"]
                if not isinstance(names, (tuple, list)) or len(names) != len(group.values):
                    raise ValueError("group/action component projection dimension mismatch")
                if any(type(name) is not str or name not in components for name in names):
                    raise ValueError("group projection references unknown action component")
                for name, value in zip(names, group.values, strict=True):
                    if name in values_by_component:
                        raise ValueError("structured action component has multiple group writers")
                    values_by_component[name] = value
                covered_groups.add(key)
            if set(values_by_component) != set(components):
                raise ValueError("groups do not cover the writer action schema exactly")

            requested = writer["requested_action"]
            canonical = writer["canonical_action"]
            if not isinstance(requested, Mapping) or not isinstance(canonical, Mapping):
                raise ValueError("requested/canonical action mappings are required")
            req_values = requested.get("values")
            can_values = canonical.get("interpreted_values")
            if not isinstance(req_values, (tuple, list)) or len(req_values) != len(components):
                raise ValueError("requested action values do not match component schema")
            expected_values = tuple(values_by_component[name] for name in components)
            if tuple(float(value) for value in req_values) != expected_values:
                raise ValueError("requested action does not preserve the complete structured request")
            if not isinstance(can_values, (tuple, list)) or len(can_values) != len(components):
                raise ValueError("canonical action values do not match component schema")
            if any(type(value) not in (int, float) or not math.isfinite(value) for value in (*req_values, *can_values)):
                raise ValueError("requested/canonical action values must be finite")
            if type(canonical.get("schema_version")) is not str or not canonical["schema_version"]:
                raise ValueError("canonical_action schema version is required")

            target = writer["controller_target"]
            applied = writer["applied_control"]
            if not isinstance(target, Mapping) or set(target) != {"schema_version", "payload", "identity_hash"}:
                raise ValueError("controller target envelope fields")
            if not isinstance(applied, Mapping) or set(applied) != {"schema_version", "payload", "target_hash"}:
                raise ValueError("applied control envelope fields")
            for envelope, name in ((target, "controller_target"), (applied, "applied_control")):
                _nonempty(envelope["schema_version"], f"{name}.schema_version")
                if not isinstance(envelope["payload"], Mapping):
                    raise ValueError(f"{name}.payload must be a mapping")
                _json_value(dict(envelope["payload"]))
            target_hash = target["identity_hash"]
            if type(target_hash) is not str or not _SHA256.fullmatch(target_hash):
                raise ValueError("controller target identity must be SHA-256")
            if target_hash != _mapping_hash(target["payload"]):
                raise ValueError("controller target identity does not hash its payload")
            if applied["target_hash"] != target_hash:
                raise ValueError("applied control does not acknowledge its controller target")
        if len(writer_ids) != len(set(writer_ids)):
            raise ValueError("duplicate structured writer controls")
        if covered_groups != set(requested_groups):
            raise ValueError("writer controls do not account for the complete structured request")


def validate_episode_records(
    events: Sequence[BoundaryEventV1], outcome: EpisodeOutcomeV1, transition_count: int,
) -> None:
    """Validate event order and final-boundary alignment for one format value."""
    if type(transition_count) is not int or transition_count < 0:
        raise ValueError("transition_count must be a nonnegative integer")
    if not isinstance(outcome, EpisodeOutcomeV1):
        raise TypeError("versioned trajectory requires EpisodeOutcomeV1")
    if outcome.final_boundary != transition_count:
        raise ValueError("EpisodeOutcome final boundary does not match T transitions")
    seen_ids: set[str] = set()
    next_sequence: dict[int, int] = {}
    previous_order = (-1, -1)
    for event in events:
        if not isinstance(event, BoundaryEventV1):
            raise TypeError("trajectory events must be BoundaryEventV1")
        if event.episode_id != outcome.episode_id:
            raise ValueError("BoundaryEvent/EpisodeOutcome episode identity mismatch")
        if event.boundary_index > transition_count:
            raise ValueError("BoundaryEvent points beyond final boundary")
        if event.event_id in seen_ids:
            raise ValueError("duplicate BoundaryEvent identity")
        seen_ids.add(event.event_id)
        order = (event.boundary_index, event.event_sequence)
        if order <= previous_order:
            raise ValueError("BoundaryEvents must be ordered by boundary and sequence")
        previous_order = order
        expected = next_sequence.get(event.boundary_index, 0)
        if event.event_sequence != expected:
            raise ValueError("BoundaryEvent sequence must be contiguous at each boundary")
        next_sequence[event.boundary_index] = expected + 1


def single_writer_training_actions(
    records: Sequence[StructuredControlTransitionV1], *,
    action_schema_id: str,
    components: Sequence[str],
) -> tuple[tuple[float, ...], ...]:
    """Project only an exact one-writer schema to a legacy training vector."""
    _nonempty(action_schema_id, "action_schema_id")
    order = tuple(components)
    if not order or len(order) != len(set(order)):
        raise ValueError("training action components must be unique and non-empty")
    projected = []
    for record in records:
        if not isinstance(record, StructuredControlTransitionV1) or len(record.writer_controls) != 1:
            raise ValueError("training conversion supports exactly one Controller writer")
        writer = record.writer_controls[0]
        if writer["action_schema_id"] != action_schema_id or tuple(writer["components"]) != order:
            raise ValueError("structured action schema cannot be losslessly projected to the requested learner")
        projected.append(tuple(float(v) for v in writer["requested_action"]["values"]))
    return tuple(projected)


__all__ = [
    "BoundaryEventV1", "EpisodeOutcomeV1", "StructuredControlTransitionV1",
    "single_writer_training_actions", "validate_episode_records",
]
