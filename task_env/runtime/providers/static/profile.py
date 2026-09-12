"""Task-agnostic static-template profile and compatibility descriptors.

    The descriptor is deliberately independent of Taichi and of concrete task
    names. It is an internal validation/provenance boundary between the
    compiled scene and a static batch implementation. A profile may expose a
    semantic reference before its fused performance kernel is available;
    provenance records that distinction. It is not the Runtime Port's device
    admission authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from ....environment.types import StageUnavailableError


@dataclass(frozen=True)
class StaticTemplateCapability:
    """Immutable declaration of one static-template topology envelope."""

    profile: str
    supports_free_root: bool
    supports_tree_articulation: bool
    supports_ground_contact: bool
    supports_domain_boundary_contact: bool
    supports_self_contact: bool
    supports_tendons: bool
    supports_sensors: bool
    implementation_status: str
    max_contact_pairs_per_world: int
    max_constraint_rows_per_world: int = 0

    def __post_init__(self) -> None:
        if not str(self.profile).strip():
            raise ValueError("static-template capability profile cannot be empty")
        if self.implementation_status not in {"available", "planned"}:
            raise ValueError("static-template capability status must be available or planned")
        if int(self.max_contact_pairs_per_world) < 0:
            raise ValueError("max_contact_pairs_per_world cannot be negative")
        if int(self.max_constraint_rows_per_world) < 0:
            raise ValueError("max_constraint_rows_per_world cannot be negative")

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "supports_free_root": self.supports_free_root,
            "supports_tree_articulation": self.supports_tree_articulation,
            "supports_ground_contact": self.supports_ground_contact,
            "supports_domain_boundary_contact": self.supports_domain_boundary_contact,
            "supports_self_contact": self.supports_self_contact,
            "supports_tendons": self.supports_tendons,
            "supports_sensors": self.supports_sensors,
            "implementation_status": self.implementation_status,
            "max_contact_pairs_per_world": int(self.max_contact_pairs_per_world),
            "max_constraint_rows_per_world": int(self.max_constraint_rows_per_world),
        }


def static_template_compatibility_issues(
    capability: StaticTemplateCapability,
    *,
    compiled_scene: object,
) -> tuple[str, ...]:
    """Return deterministic topology reasons for rejecting a static profile.

    This validator deliberately consumes only compiled descriptor facts.  It
    does not instantiate a solver and it never changes ``merged_scene`` into a
    fallback.  Missing optional descriptor arrays are tolerated for synthetic
    fixtures; when present, they are checked against the public capability
    envelope.
    """

    model = getattr(compiled_scene, "scene_model", None)
    joint_data = dict(getattr(model, "joint_data", None) or {})
    issues: list[str] = []
    tendons = int(joint_data.get("n_tendons", 0) or 0)
    sensors = int(joint_data.get("n_sensors", 0) or 0)
    if tendons and not capability.supports_tendons:
        issues.append(f"tendons={tendons} are outside profile support")
    if sensors and not capability.supports_sensors:
        issues.append(f"sensors={sensors} are outside profile support")

    # MuJoCo joint types: free=0, ball=1, slide=2, hinge=3.  The first
    # articulated profile allows one free root and a hinge/slide tree, but no
    # ball joints or closed-loop/tendon topology.
    joint_types = joint_data.get("jnt_type")
    if joint_types is not None:
        values = np.asarray(joint_types, dtype=np.int64).reshape(-1)
        if capability.supports_tree_articulation:
            unsupported = sorted({int(value) for value in values if int(value) not in {0, 2, 3}})
            if unsupported:
                issues.append(f"joint types {unsupported} are outside free/hinge/slide support")
        elif values.size and any(int(value) not in {2, 3} for value in values):
            issues.append("free-root or non-hinge/slide joint topology is outside profile support")

    geom_types = joint_data.get("geom_type")
    if geom_types is not None:
        values = np.asarray(geom_types, dtype=np.int64).reshape(-1)
        # MuJoCo mesh/sdf/hfield types are not part of the first primitive
        # contact profile.  Plane and analytic primitive types remain allowed.
        unsupported = sorted({int(value) for value in values if int(value) >= 7})
        if unsupported:
            issues.append(f"mesh/non-primitive geom types {unsupported} are outside profile support")

    qpos = int(joint_data.get("n_qpos", 0) or 0)
    qvel = int(joint_data.get("n_dof", 0) or 0)
    if (
        capability.supports_tree_articulation
        and capability.profile != "rigid_batch_v1"
        and joint_types is not None
        and (qpos < 7 or qvel < 6)
    ):
        issues.append("articulated profile requires a free-root state (qpos>=7, qvel>=6)")
    return tuple(issues)


STATIC_TEMPLATE_CAPABILITIES: Mapping[str, StaticTemplateCapability] = {
    "hinge_or_slide_no_contact_v1": StaticTemplateCapability(
        profile="hinge_or_slide_no_contact_v1",
        supports_free_root=False,
        supports_tree_articulation=False,
        supports_ground_contact=False,
        supports_domain_boundary_contact=False,
        supports_self_contact=False,
        supports_tendons=False,
        supports_sensors=False,
        implementation_status="available",
        max_contact_pairs_per_world=0,
    ),
    # Generic fused `(B, local_*)` articulated dynamics.  The explicit
    # no-contact boundary is intentional: it allows the kernel to be tested
    # independently of the later local contact-row workspace.
    "articulated_fused_no_contact_v1": StaticTemplateCapability(
        profile="articulated_fused_no_contact_v1",
        supports_free_root=True,
        supports_tree_articulation=True,
        supports_ground_contact=False,
        supports_domain_boundary_contact=False,
        supports_self_contact=False,
        supports_tendons=False,
        supports_sensors=False,
        implementation_status="available",
        max_contact_pairs_per_world=0,
        max_constraint_rows_per_world=0,
    ),
    # Source-tree ``BatchedRigidSolver`` route.  Exact admission, including
    # actuator/contact/topology details, remains owned by the source batch
    # planner; this descriptor only declares the TaskEnv boundary and the
    # currently unsupported ground/domain policy.
    "rigid_batch_v1": StaticTemplateCapability(
        profile="rigid_batch_v1",
        supports_free_root=True,
        supports_tree_articulation=True,
        supports_ground_contact=False,
        supports_domain_boundary_contact=False,
        supports_self_contact=True,
        supports_tendons=False,
        supports_sensors=False,
        implementation_status="available",
        max_contact_pairs_per_world=4096,
        max_constraint_rows_per_world=16384,
    ),
    # Shared `(B, local_*)` analytic ground rows.  This profile is deliberately
    # separate from the exact-B reference until contact onset, friction and
    # masked-reset parity are measured against the reference engines.
    "articulated_fused_ground_contact_v1": StaticTemplateCapability(
        profile="articulated_fused_ground_contact_v1",
        supports_free_root=True,
        supports_tree_articulation=True,
        supports_ground_contact=True,
        supports_domain_boundary_contact=False,
        supports_self_contact=False,
        supports_tendons=False,
        supports_sensors=False,
        implementation_status="available",
        max_contact_pairs_per_world=0,
        max_constraint_rows_per_world=16384,
    ),
    # The semantic exact-B reference is available; a fused device kernel is a
    # separate performance exit gate and is reported in runtime provenance.
    "articulated_ground_contact_v1": StaticTemplateCapability(
        profile="articulated_ground_contact_v1",
        supports_free_root=True,
        supports_tree_articulation=True,
        supports_ground_contact=True,
        supports_domain_boundary_contact=True,
        supports_self_contact=True,
        supports_tendons=False,
        supports_sensors=False,
        # The first executable implementation is an isolated-world reference
        # kernel backed by the current RigidSolver.  It already enforces the
        # public local-world/contact/reset contract; the fused B-axis Taichi
        # kernel remains a later optimization and is recorded in provenance.
        implementation_status="available",
        # The limit is a per-world safety envelope, not a packed global ID
        # budget. The reference workspace may choose a smaller exact capacity
        # from the compiled local geometry count.
        max_contact_pairs_per_world=4096,
        max_constraint_rows_per_world=16384,
    ),
}


def get_static_template_capability(profile: str) -> StaticTemplateCapability:
    try:
        return STATIC_TEMPLATE_CAPABILITIES[str(profile)]
    except KeyError as exc:
        raise StageUnavailableError(
            f"unknown static-template capability profile: {profile!r}"
        ) from exc


def resolve_static_template_profile(
    requested: str,
    *,
    compiled_scene: object,
) -> StaticTemplateCapability:
    """Resolve a profile without silently selecting another physics layout.

    ``auto`` currently resolves the first narrow profile only when its
    topology validator accepts the scene. The broader articulated profile is
    explicit because it has a larger contact/resource envelope.
    """

    value = str(requested)
    if value != "auto":
        capability = get_static_template_capability(value)
        if capability.implementation_status != "available":
            raise StageUnavailableError(
                f"static-template profile {value!r} is declared but not implemented"
            )
        issues = static_template_compatibility_issues(
            capability,
            compiled_scene=compiled_scene,
        )
        if issues:
            raise StageUnavailableError(
                f"static-template profile {value!r} is incompatible with compiled topology: "
                + "; ".join(issues)
            )
        return capability

    model = getattr(compiled_scene, "scene_model", None)
    joint_data = dict(getattr(model, "joint_data", None) or {})
    body_count = len(tuple(getattr(model, "objects", ()) or ()))
    if (
        body_count == 2
        and int(joint_data.get("n_joints", 0)) == 1
        and int(joint_data.get("n_qpos", 0)) == 1
        and int(joint_data.get("n_dof", 0)) == 1
    ):
        narrow = STATIC_TEMPLATE_CAPABILITIES["hinge_or_slide_no_contact_v1"]
        issues = static_template_compatibility_issues(narrow, compiled_scene=compiled_scene)
        if not issues:
            return narrow
    raise StageUnavailableError(
        "static-template profile auto could not resolve an available capability "
        "for the compiled topology; requested topology requires a supported "
        "profile"
    )


__all__ = [
    "STATIC_TEMPLATE_CAPABILITIES",
    "StaticTemplateCapability",
    "get_static_template_capability",
    "resolve_static_template_profile",
]
