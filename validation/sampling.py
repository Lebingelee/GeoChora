"""Offline sampled geometric evidence, separate from full task qualification.

This extension consumes named world poses and explicit asset geometry, never
solver state, planner phase names, reference labels, or task IDs. Results use the standalone
PredicateResult. A positive geometric witness is not proof of grasp/contact
causality, asset preservation, training readiness, or Judge approval.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from collections.abc import Mapping, Sequence
import math

import numpy as np

from validation.results import PredicateResult


@dataclass(frozen=True)
class MeasurementPolicy:
    """Explicit diagnostic measurement resolution, not source-task acceptance."""

    distance_tolerance_m: float = 0.001
    max_sample_gap_s: float = 0.05

    def __post_init__(self):
        for value in asdict(self).values():
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ValueError("measurement policy values must be finite and positive")


def predicate(value: bool | None, reason="measurement_unavailable") -> PredicateResult:
    if value is None:
        return PredicateResult.unavailable(reason)
    if type(value) is not bool:
        raise TypeError("predicate must be bool or None")
    return PredicateResult.available(value)


def conjunction(values: Sequence[PredicateResult]) -> PredicateResult:
    if not values:
        raise ValueError("empty required predicate set")
    if any(v.status == "available" and v.value is False for v in values):
        return predicate(False)
    missing = next((v for v in values if v.status != "available"), None)
    return predicate(None, missing.reason or "predicate_unavailable") if missing else predicate(True)


def disjunction(values: Sequence[PredicateResult]) -> PredicateResult:
    if not values:
        return predicate(None, "candidate_set_unavailable")
    if any(v.status == "available" and v.value is True for v in values):
        return predicate(True)
    missing = next((v for v in values if v.status != "available"), None)
    return predicate(None, missing.reason or "predicate_unavailable") if missing else predicate(False)


def result_mapping(result: PredicateResult) -> dict:
    return {"status": result.status, "value": result.value, "reason": result.reason}


def _time_axis(times_s):
    times = np.asarray(times_s, dtype=float)
    if times.ndim != 1 or not len(times) or not np.isfinite(times).all():
        raise ValueError("nonempty finite one-dimensional timestamps required")
    if times[0] < 0 or np.any(np.diff(times) <= 0):
        raise ValueError("timestamps must be nonnegative and strictly increasing")
    return times


def ordered_witness(
    times_s, conditions: Mapping[str, Sequence[bool | None]], order: Sequence[str],
    *, policy: MeasurementPolicy, recording_complete: bool,
) -> tuple[PredicateResult, tuple[int, ...]]:
    """Existential subsequence of distinct samples, with three-valued absence.

    This is a finite-record query, not lifecycle's rising-edge commit engine:
    repeated conditions and recovery attempts are allowed. Positive witnesses
    must be strictly ordered. Unknown samples can prevent a negative conclusion.
    A gap invalidates the query rather than silently bridging missing evidence.
    A negative result means no matching sequence in this complete sampled record,
    not that a brief unsampled real-world event was impossible.
    """
    times = _time_axis(times_s)
    if type(recording_complete) is not bool:
        raise TypeError("recording_complete must be bool")
    if not order or any(name not in conditions for name in order):
        raise ValueError("order must name supplied predicates")
    for values in conditions.values():
        if len(values) != len(times) or any(v is not None and type(v) is not bool for v in values):
            raise ValueError("condition series must contain aligned bool/None values")
    if np.any(np.diff(times) > policy.max_sample_gap_s + 1e-9):
        return predicate(None, "sample_gap"), ()
    known, possible = [], 0
    for index in range(len(times)):
        if len(known) < len(order) and conditions[order[len(known)]][index] is True:
            known.append(index)
        if possible < len(order) and conditions[order[possible]][index] is not False:
            possible += 1
    if len(known) == len(order):
        return predicate(True), tuple(known)
    if not recording_complete or possible == len(order):
        return predicate(None, "recording_incomplete" if not recording_complete else "sequence_evidence_missing"), tuple(known)
    return predicate(False), tuple(known)


def _points(values, length):
    if values is None:
        return np.full((length, 3), np.nan)
    result = np.asarray(values, dtype=float)
    if result.shape != (length, 3) or np.isinf(result).any():
        raise ValueError("positions must have shape (T,3); missing samples use NaN")
    return result


def in_local_frame(points, origins, quaternions_wxyz):
    """World points -> moving rigid frame. Missing/invalid rotations stay unknown."""
    points, origins = np.asarray(points, float), np.asarray(origins, float)
    q = np.asarray(quaternions_wxyz, float)
    if points.shape != origins.shape or points.ndim != 2 or points.shape[1] != 3 or q.shape != (len(points), 4):
        raise ValueError("unaligned rigid-frame arrays")
    norms = np.linalg.norm(q, axis=1)
    valid = np.isfinite(q).all(1) & (np.abs(norms - 1) < 1e-4)
    q = q / np.where(valid, norms, np.nan)[:, None]
    # Inverse quaternion rotation; scalar-first source convention is explicit.
    v = points - origins
    xyz = -q[:, 1:]
    cross = 2 * np.cross(xyz, v)
    return v + q[:, :1] * cross + np.cross(xyz, cross)


def _observations(values, known):
    return [bool(v) if ok else None for v, ok in zip(values, known)]


def sphere_inside(points_local, radius_m, bounds, tolerance_m):
    """Whole-sphere containment in an explicitly bound rectangular cavity."""
    p = np.asarray(points_local, float)
    lower, upper = np.asarray(bounds, float)
    if not math.isfinite(radius_m) or radius_m <= 0 or not np.isfinite([lower, upper]).all() or np.any(lower >= upper):
        raise ValueError("invalid sphere/cavity geometry")
    margin = np.minimum(p - radius_m - lower, upper - p - radius_m).min(axis=1)
    return _observations(margin >= -tolerance_m, np.isfinite(p).all(axis=1))


def sphere_on_surface(points, radius_m, surface_bounds, tolerance_m):
    p = np.asarray(points, float)
    lower, upper = np.asarray(surface_bounds, float)
    # Conservative full footprint, with floor height taken from source geometry.
    horizontal = ((p[:, :2] - radius_m >= lower[:2] - tolerance_m)
                  & (p[:, :2] + radius_m <= upper[:2] + tolerance_m)).all(axis=1)
    support = np.abs(p[:, 2] - radius_m - upper[2]) <= tolerance_m
    return _observations(horizontal & support, np.isfinite(p).all(axis=1))


def _and_series(*series):
    return [conjunction([predicate(v) for v in row]).value for row in zip(*series)]


def _at(values, index):
    return predicate(values[index])


def _suffix_all(values):
    """At each sample, was this relation maintained through the record end?"""
    result = [None] * len(values)
    remaining = predicate(True)
    for index in range(len(values) - 1, -1, -1):
        remaining = conjunction([predicate(values[index]), remaining])
        result[index] = remaining.value
    return result


def evaluate_drawer_geometry(
    *, criterion: dict, times_s, positions: Mapping[str, object],
    orientations_wxyz: Mapping[str, object], geometry: dict,
    recording_complete: bool, policy: MeasurementPolicy = MeasurementPolicy(),
) -> dict:
    """Bounded reusable sphere/drawer family projection; no dataset-specific IDs.

    geometry names spheres, one container and gripper links, with metres/WXYZ
    explicitly bound by the input adapter. Gripper clearance uses source-derived
    enclosing radii and is sufficient geometric separation, not a grasp detector.
    Actual grasp, support force and provenance requirements remain unverified.
    """
    times = _time_axis(times_s)
    n, eps = len(times), policy.distance_tolerance_m
    if type(recording_complete) is not bool:
        raise TypeError("recording_complete must be bool")
    kind = criterion.get("kind")
    supported = {
        "drawer_open": {"kind", "drawer", "grasp_handle", "opening_allows_existing_ball"},
        "drawer_store_close": {"kind", "drawer", "object_type", "order", "contents_remain_inside"},
        "store_and_retrieve": {"kind", "drawer", "same_ball", "order"},
    }
    base = {"scope": "sampled_geometric_projection", "measurement_policy": asdict(policy),
            "task_success": None, "physical_execution": result_mapping(predicate(None, "contact_causality_and_asset_audit_required")),
            "candidates": {}, "limitations": ["Geometric support/clearance are not contact-force or grasp proofs.",
            "False means no matching sampled witness, not impossibility of an unsampled event.",
            "Measurement tolerance is explicit diagnostic policy, not a change to original acceptance."]}
    if kind not in supported or set(criterion) != supported[kind]:
        return {**base, "geometric_goal": result_mapping(predicate(None, "unsupported_criterion"))}
    expected = {
        "drawer_open": {"grasp_handle": True, "opening_allows_existing_ball": True},
        "drawer_store_close": {"object_type": "ball", "contents_remain_inside": True,
                               "order": ["open", "pick", "place", "release", "close"]},
        "store_and_retrieve": {"same_ball": True,
                               "order": ["pick_table", "place_drawer", "release", "regrasp_drawer", "place_table", "release"]},
    }
    if any(criterion[k] != v or (type(v) is bool and type(criterion[k]) is not bool) for k, v in expected[kind].items()):
        return {**base, "geometric_goal": result_mapping(predicate(None, "unsupported_criterion_values"))}
    container = geometry["container"]
    if criterion["drawer"] != container["name"]:
        raise ValueError("criterion/container binding mismatch")
    drawer = _points(positions.get(container["name"]), n)
    orientation = orientations_wxyz.get(container["name"], np.full((n, 4), np.nan))
    axis = np.asarray(container["opening_axis_world"], float)
    if axis.shape != (3,) or not np.isclose(np.linalg.norm(axis), 1):
        raise ValueError("opening axis must be a unit vector")
    opening = (drawer - np.asarray(container["closed_origin_world_m"])) @ axis
    spheres = geometry["spheres"]
    if not spheres:
        return {**base, "geometric_goal": result_mapping(predicate(None, "candidate_set_unavailable"))}
    ball_diameter = 2 * min(float(s["radius_m"]) for s in spheres.values())
    opened = _observations(opening > ball_diameter + eps, np.isfinite(drawer).all(1))
    closed = _observations(np.abs(opening) <= eps, np.isfinite(drawer).all(1))
    temporal_ok = recording_complete and not np.any(np.diff(times) > policy.max_sample_gap_s + 1e-9)
    if kind == "drawer_open":
        goal = _at(opened, -1) if temporal_ok else predicate(None, "recording_incomplete_or_gapped")
        return {**base, "geometric_goal": result_mapping(goal),
                "final_opening_m": float(opening[-1]) if np.isfinite(opening[-1]) else None,
                "required_ball_diameter_m": ball_diameter}
    candidates = []
    for name, sphere in spheres.items():
        radius = float(sphere["radius_m"])
        world = _points(positions.get(name), n)
        local = in_local_frame(world, drawer, orientation)
        inside = sphere_inside(local, radius, container["cavity_bounds_local_m"], eps)
        floor = container["cavity_bounds_local_m"][0][2]
        floor_support = _observations(np.abs(local[:, 2] - radius - floor) <= eps, np.isfinite(local).all(1))
        table = sphere_on_surface(world, radius, geometry["table_bounds_world_m"], eps)
        clear_parts = []
        for link, enclosing_radius in geometry["gripper_enclosing_radii_m"].items():
            other = _points(positions.get(link), n)
            distance = np.linalg.norm(world - other, axis=1)
            clear_parts.append(_observations(distance > radius + enclosing_radius + eps, np.isfinite(distance)))
        clearance = _and_series(*clear_parts) if clear_parts else [None] * n
        # Height changes are observations only. They do not assert a grasp caused them.
        above_table = _observations(world[:, 2] - radius > geometry["table_bounds_world_m"][1][2] + eps, np.isfinite(world).all(1))
        above_rim = _observations(local[:, 2] - radius > container["cavity_bounds_local_m"][1][2] + eps, np.isfinite(local).all(1))
        conditions = {"opened": opened, "above_table": above_table,
                      "released_in_drawer": _and_series(inside, floor_support, clearance),
                      "above_drawer_rim": above_rim,
                      "released_on_table": _and_series(table, clearance), "closed": closed}
        # A later recovery may supply a new valid release. Closing an empty drawer
        # and putting a ball inside afterwards cannot satisfy store-and-close.
        conditions["released_and_remains_inside"] = _and_series(conditions["released_in_drawer"], _suffix_all(inside))
        conditions["closed_with_contents"] = _and_series(closed, inside)
        order = (["opened", "above_table", "released_and_remains_inside", "closed_with_contents"]
                 if kind == "drawer_store_close" else
                 ["above_table", "released_in_drawer", "above_drawer_rim", "released_on_table"])
        sequence, witness = ordered_witness(times, conditions, order, policy=policy, recording_complete=recording_complete)
        final = (conjunction([_at(conditions["released_in_drawer"], -1), _at(closed, -1)])
                 if kind == "drawer_store_close" else _at(conditions["released_on_table"], -1))
        goal = conjunction([_at(table, 0), sequence, final]) if temporal_ok else predicate(None, "recording_incomplete_or_gapped")
        candidates.append(goal)
        base["candidates"][name] = {"geometric_goal": result_mapping(goal),
            "sequence": result_mapping(sequence), "final_relation": result_mapping(final),
            "witness": [{"condition": order[j], "sample_index": i, "time_s": float(times[i])} for j, i in enumerate(witness)],
            "final_position_world_m": world[-1].tolist() if np.isfinite(world[-1]).all() else None}
    base["geometric_goal"] = result_mapping(disjunction(candidates))
    return base
