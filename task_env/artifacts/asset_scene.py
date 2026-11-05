"""Preparation handoff for a bounded Panda/rigid-object USD scene.

These contracts bind declarations and raw evidence. They do not load USD,
execute checkers, admit a runtime, or declare task success.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import re

from .contracts import (
    AssetDefinition, Contract, UsdDeliveryFileV1, _SHA256, _name,
)


PANDA_RIGID_SCENE_PROFILE_V1 = "panda-rigid-picklift-isaac-v1"
REQUIRED_PREPARATION_CHECKS_V1 = frozenset({
    "usd-composition", "dependency-closure", "robot-source-bindings",
    "rigid-object-geometry", "support-and-initial-state", "required-claims",
    "material-and-render", "physx-static-stability",
})


def _prim_path(value: str, label: str) -> None:
    if (not value.startswith("/") or value == "/" or value.endswith("/")
            or any(not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", part)
                   for part in value[1:].split("/"))):
        raise ValueError(f"{label} must be a canonical absolute prim path")


def _digest(value: str, label: str) -> None:
    if not _SHA256.fullmatch(value):
        raise ValueError(f"{label} must be lowercase SHA-256 hex")


@dataclass(frozen=True)
class PandaRigidSceneBindingsV1(Contract):
    schema_version: str
    scene_root: str
    robot_root: str
    articulation_root: str
    robot_base: str
    tcp_frame: str
    target_body: str
    support_body: str
    support_top: str
    joint_paths: Mapping[str, str]
    joint_body_paths: Mapping[str, tuple[str, str]]

    def validate(self):
        if self.schema_version != "panda-rigid-scene-bindings-v1":
            raise ValueError("unsupported Panda rigid scene binding schema")
        roles = ("scene_root", "robot_root", "articulation_root", "robot_base",
                 "tcp_frame", "target_body", "support_body", "support_top")
        for role in roles:
            _prim_path(getattr(self, role), role)
        for role in roles[1:]:
            if not getattr(self, role).startswith(self.scene_root + "/"):
                raise ValueError(f"{role} must belong to the declared scene root")
        if len({self.robot_root, self.target_body, self.support_body}) != 3:
            raise ValueError("robot, target and support must be distinct")
        for left, right in ((self.robot_root, self.target_body),
                            (self.robot_root, self.support_body),
                            (self.target_body, self.support_body)):
            if left.startswith(right + "/") or right.startswith(left + "/"):
                raise ValueError("robot, target and support subtrees must be disjoint")
        for role in ("articulation_root", "robot_base", "tcp_frame"):
            if not (getattr(self, role) == self.robot_root
                    or getattr(self, role).startswith(self.robot_root + "/")):
                raise ValueError(f"{role} must be inside the robot subtree")
        if not self.support_top.startswith(self.support_body + "/"):
            raise ValueError("support_top must belong to the support subtree")
        expected = {f"joint{i}" for i in range(1, 8)} | {
            "finger_joint1", "finger_joint2",
        }
        if set(self.joint_paths) != expected:
            raise ValueError("Panda bindings must cover exactly seven arm and two finger joints")
        if len(set(self.joint_paths.values())) != len(expected):
            raise ValueError("Panda joints must bind distinct prims")
        for name, path in self.joint_paths.items():
            _prim_path(path, name)
            if not path.startswith(self.robot_root + "/"):
                raise ValueError("joint prim must be inside the robot subtree")
        if set(self.joint_body_paths) != expected:
            raise ValueError("Panda joint body bindings must cover every named joint")
        for name, endpoints in self.joint_body_paths.items():
            if (type(endpoints) is not tuple or len(endpoints) != 2
                    or any(type(path) is not str for path in endpoints)):
                raise TypeError(f"joint body binding for {name} must contain two paths")
            for path in endpoints:
                _prim_path(path, f"{name} body")
                if not (path == self.robot_root
                        or path.startswith(self.robot_root + "/")):
                    raise ValueError("Panda joint bodies must be inside the robot subtree")


@dataclass(frozen=True)
class RigidMeshGeometryV1(Contract):
    schema_version: str
    visual_mesh_prims: tuple[str, ...]
    collision_mesh_prims: tuple[str, ...]
    mesh_content_sha256: Mapping[str, str]
    local_aabb_min_m: tuple[float, float, float]
    local_aabb_max_m: tuple[float, float, float]
    mass_kg: float
    collision_approximation: str
    approximation_losses: tuple[str, ...]

    def validate(self):
        if self.schema_version != "rigid-mesh-geometry-v1":
            raise ValueError("unsupported rigid mesh geometry schema")
        for label in ("visual_mesh_prims", "collision_mesh_prims"):
            values = getattr(self, label)
            if not values or len(set(values)) != len(values):
                raise ValueError(f"{label} must contain unique actual mesh prims")
            for path in values:
                _prim_path(path, label)
        expected_meshes = set(self.visual_mesh_prims) | set(self.collision_mesh_prims)
        if set(self.mesh_content_sha256) != expected_meshes:
            raise ValueError("geometry hashes must cover exactly the declared visual and collision meshes")
        for path, digest in self.mesh_content_sha256.items():
            _digest(digest, f"mesh content for {path}")
        if any(hi <= lo for lo, hi in zip(
                self.local_aabb_min_m, self.local_aabb_max_m, strict=True)):
            raise ValueError("rigid object AABB must have positive extent on every axis")
        if self.mass_kg <= 0:
            raise ValueError("rigid object mass must be positive")
        if self.collision_approximation not in {"convexHull", "convexDecomposition"}:
            raise ValueError("first rigid-object profile requires an explicit mesh convex approximation")
        if (not self.approximation_losses
                or len(set(self.approximation_losses)) != len(self.approximation_losses)
                or any(not item.strip() for item in self.approximation_losses)):
            raise ValueError("record mesh collision approximation and its losses explicitly")


@dataclass(frozen=True)
class AssetPreparationEvidenceV1(Contract):
    schema_version: str
    check: str
    status: str
    input_preparation_sha256: str
    checker_sha256: str
    result: UsdDeliveryFileV1
    tool_versions: Mapping[str, str]
    scope: str
    metrics: Mapping[str, object]

    def validate(self):
        if self.schema_version != "asset-preparation-evidence-v1":
            raise ValueError("unsupported asset preparation evidence schema")
        _name(self.check)
        if self.status not in {"pass", "fail", "execution_error", "not_run", "not_applicable"}:
            raise ValueError("unsupported asset preparation evidence status")
        _digest(self.input_preparation_sha256, "input preparation")
        _digest(self.checker_sha256, "checker")
        self.result.validate()
        if not self.tool_versions:
            raise ValueError("preparation evidence must identify the actual tool versions")
        if not self.scope.strip():
            raise ValueError("preparation evidence must state its coverage")


@dataclass(frozen=True)
class AssetScenePreparationV1(Contract):
    schema_version: str
    preparation_id: str
    profile_id: str
    request: UsdDeliveryFileV1
    delivery_manifest: UsdDeliveryFileV1
    delivery_closure_sha256: str
    robot_source_identity_sha256: str
    target_asset: AssetDefinition
    target_source_files: tuple[UsdDeliveryFileV1, ...]
    source_terms: UsdDeliveryFileV1
    bindings: PandaRigidSceneBindingsV1
    geometry: RigidMeshGeometryV1
    evidence: tuple[AssetPreparationEvidenceV1, ...]

    def validate(self):
        if self.schema_version != "asset-scene-preparation-v1":
            raise ValueError("unsupported asset scene preparation schema")
        _name(self.preparation_id)
        if self.profile_id != PANDA_RIGID_SCENE_PROFILE_V1:
            raise ValueError("unsupported asset scene preparation profile")
        for label in ("request", "delivery_manifest", "source_terms"):
            getattr(self, label).validate()
        _digest(self.delivery_closure_sha256, "delivery closure")
        _digest(self.robot_source_identity_sha256, "robot source identity")
        self.target_asset.validate()
        if not self.target_asset.source_content_sha256 or not self.target_asset.license_id:
            raise ValueError("real target needs a source content hash and declared source terms")
        if not self.target_source_files:
            raise ValueError("real target requires its source byte inventory")
        paths = [item.path for item in self.target_source_files]
        if paths != sorted(set(paths)):
            raise ValueError("target source inventory must be unique and sorted")
        for item in self.target_source_files:
            item.validate()
        self.bindings.validate()
        self.geometry.validate()
        for path in (*self.geometry.visual_mesh_prims, *self.geometry.collision_mesh_prims):
            if not path.startswith(self.bindings.target_body + "/"):
                raise ValueError("target geometry must belong to the declared target rigid body")
        checks = [item.check for item in self.evidence]
        if len(checks) != len(set(checks)):
            raise ValueError("duplicate preparation evidence checks")
        result_paths = [item.result.path for item in self.evidence]
        if len(result_paths) != len(set(result_paths)):
            raise ValueError("preparation evidence must preserve each raw result separately")
        for item in self.evidence:
            item.validate()
            if item.input_preparation_sha256 != self.input_identity_hash:
                raise ValueError("preparation evidence belongs to another preparation input")

    @property
    def input_identity_hash(self):
        """Bind checker results to declarations without introducing a hash cycle."""
        value = self.to_mapping()
        value.pop("evidence")
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(raw.encode()).hexdigest()

    def require_passed(self):
        """Gate preparation coverage, without promoting it to runtime admission."""
        self.validate()
        by_check = {item.check: item for item in self.evidence}
        missing = REQUIRED_PREPARATION_CHECKS_V1 - by_check.keys()
        if missing:
            raise ValueError(f"required preparation checks missing: {sorted(missing)}")
        failed = sorted(name for name in REQUIRED_PREPARATION_CHECKS_V1
                        if by_check[name].status != "pass")
        if failed:
            raise ValueError(f"required preparation checks are not passing: {failed}")
        claims = by_check["required-claims"].metrics
        if (any(type(claims.get(key)) is not int
                for key in ("required_count", "executed_count", "passed_count"))
                or claims["required_count"] < 1
                or claims.get("executed_count") != claims["required_count"]
                or claims.get("passed_count") != claims["required_count"]):
            raise ValueError("required claims must be nonempty, executed and passing")
        static = by_check["physx-static-stability"].metrics
        if (type(static.get("target_checked")) is not bool
                or not static["target_checked"]
                or type(static.get("duration_s")) not in (int, float)
                or static["duration_s"] < 5):
            raise ValueError("static stability must include the actual target for at least five seconds")
        render = by_check["material-and-render"].metrics
        if render.get("nonblank") is not True or render.get("viewed") is not True:
            raise ValueError("actual rendered asset evidence must be nonblank and viewed")

    @property
    def identity_hash(self):
        self.validate()
        raw = json.dumps(self.to_mapping(), sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(raw.encode()).hexdigest()
