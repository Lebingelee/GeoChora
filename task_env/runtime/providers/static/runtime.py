"""Static-template batch runtime assembled from the current RigidSolver model.

Execution remains capability-gated and task-agnostic. The original narrow
profile uses a fused device kernel for one fixed-root hinge/slide body with no
contact; ``articulated_fused_no_contact_v1`` uses one shared-model `(B, local_*)`
Torch runtime for generic free-root/hinge-tree no-contact dynamics;
``articulated_fused_ground_contact_v1`` uses the shared-model Torch kernel with
fixed local ground rows; ``articulated_ground_contact_v1`` uses the current
``RigidSolver`` semantic reference with exact-B local solvers and local contact
workspace; ``rigid_batch_v1`` delegates the homogeneous batch to the source
``BatchedRigidSolver`` under the same TaskEnv host runtime contract. Unsupported
topologies fail closed instead of falling back to ``SceneBatchRuntime``; the
fused ground-row capability is intentionally narrower than full contact.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import inspect
from math import ceil
from typing import Any

import numpy as np

from ....environment import ResolvedEnvConfig
from ....environment.types import StageUnavailableError
from ...contracts import (
    BatchResetResult,
    BatchState,
    BatchStepResult,
    DeviceBatchState,
    DeviceResetSelection,
    WorldRandomizationBatch,
    validate_device_reset_selection as validate_reset_selection_contract,
)
from .profile import (
    StaticTemplateCapability,
    resolve_static_template_profile,
)
from .model import StaticTemplateModel
from .execution import StaticTemplateExecutionPlan
from .provider import StaticTemplateProviderProtocol


def _accepts_selection(callable_value: Any) -> bool:
    try:
        parameters = inspect.signature(callable_value).parameters
    except (TypeError, ValueError):
        return False
    selection = parameters.get("selection")
    if selection is not None and selection.kind in {
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    }:
        return True
    return any(
        value.kind == inspect.Parameter.VAR_KEYWORD
        for value in parameters.values()
    )


def _provider_execution_facts(provider: object) -> Mapping[str, Any]:
    """Require the narrow provider-owned facts used by static planning."""

    publisher = getattr(provider, "execution_plan_facts", None)
    if not callable(publisher):
        raise StageUnavailableError(
            "static-template provider has no execution_plan_facts capability"
        )
    facts = publisher()
    if not isinstance(facts, Mapping):
        raise TypeError("static-template provider execution facts must be a mapping")
    return dict(facts)


def _as_array(
    mapping: Mapping[str, Any],
    name: str,
    shape: tuple[int, ...],
    *,
    dtype: np.dtype | type = np.float32,
    default: Any | None = None,
) -> np.ndarray:
    value = mapping.get(name, default)
    if value is None:
        if default is None:
            raise StageUnavailableError(
                f"static_template requires current RigidSolver model field {name!r}"
            )
        value = default
    array = np.asarray(value, dtype=dtype)
    if array.shape != shape:
        raise StageUnavailableError(
            f"static_template model field {name!r} has shape {array.shape}, "
            f"expected {shape}"
        )
    return np.ascontiguousarray(array)


def _world_randomization_enabled(config: ResolvedEnvConfig) -> bool:
    """Return the immutable construction-time randomization capability."""

    values = config.runtime.world_randomization
    if not isinstance(values, Mapping):
        return False
    return str(values.get("profile", "disabled")).strip().lower() != "disabled"


def _push_event_capacity(config: ResolvedEnvConfig) -> int:
    """Freeze a fixed push-schedule capacity from task-owned YAML values."""

    values = config.runtime.world_randomization
    push = values.get("push", {}) if isinstance(values, Mapping) else {}
    interval = float(push.get("interval_s", 5.0)) if isinstance(push, Mapping) else 5.0
    policy_dt = float(config.runtime.physics_dt) * int(config.runtime.control_substeps)
    interval_steps = max(1, int(ceil(interval / policy_dt)))
    capacity = int(ceil(max(1, int(config.episode.horizon)) / interval_steps))
    if isinstance(push, Mapping) and bool(push.get("on_reset_boundary", False)):
        capacity += 1
    return max(1, capacity)


def _object_array(objects: tuple[object, ...], name: str, default: Any) -> np.ndarray:
    values = []
    for obj in objects:
        value = getattr(obj, name, default)
        if name == "body_config":
            value = getattr(value, "mass", default)
        values.append(value)
    return np.asarray(values, dtype=np.float32)


@dataclass(frozen=True)
class StaticTemplateDescriptor:
    """Immutable local-topology and exact-B facts for a static batch."""

    num_envs: int
    backend: str
    body_count: int
    geom_count: int
    qpos_count: int
    qvel_count: int
    actuator_count: int
    site_count: int
    capability_profile: str = "hinge_or_slide_no_contact_v1"
    template_digest: str = ""
    shared_fields: tuple[str, ...] = ()
    world_state_fields: tuple[str, ...] = ()
    workspace_fields: tuple[str, ...] = ()
    compiled_field_names: tuple[str, ...] = ()

    @classmethod
    def from_compiled_scene(
        cls,
        *,
        compiled_scene: object,
        num_envs: int,
        backend: str,
        capability: StaticTemplateCapability | None = None,
    ) -> "StaticTemplateDescriptor":
        size = int(num_envs)
        if size < 1:
            raise ValueError("num_envs must be positive")
        model = getattr(compiled_scene, "scene_model", None)
        if model is None:
            raise ValueError("compiled_scene must expose scene_model")
        joint_data: dict[str, Any] = dict(getattr(model, "joint_data", None) or {})
        template_model = StaticTemplateModel.from_compiled_scene(compiled_scene)
        body_count = len(tuple(getattr(model, "objects", ()) or ()))
        geom_count = int(joint_data.get("n_geoms", body_count))
        qpos_count = int(joint_data.get("n_qpos", 0))
        qvel_count = int(joint_data.get("n_dof", 0))
        actuator_count = int(joint_data.get("n_actuators", 0))
        site_count = int(joint_data.get("n_sites", 0))
        if min(body_count, geom_count, qpos_count, qvel_count, actuator_count, site_count) < 0:
            raise ValueError("compiled scene topology counts cannot be negative")
        return cls(
            num_envs=size,
            backend=str(backend),
            body_count=body_count,
            geom_count=max(1, geom_count),
            qpos_count=qpos_count,
            qvel_count=qvel_count,
            actuator_count=actuator_count,
            site_count=site_count,
            capability_profile=(
                capability.profile
                if capability is not None
                else "hinge_or_slide_no_contact_v1"
            ),
            template_digest=template_model.template_digest,
            shared_fields=template_model.shared_fields,
            world_state_fields=template_model.world_state_fields,
            workspace_fields=template_model.workspace_fields,
            compiled_field_names=template_model.compiled_field_names,
        )

    @property
    def per_world_named_state_bytes_lower_bound(self) -> int:
        scalar_count = self.qpos_count + 2 * self.qvel_count + 2 * self.actuator_count
        spatial_count = 13 * self.body_count + 7 * self.geom_count + 7 * self.site_count
        return int(4 * (scalar_count + spatial_count))

    def resource_summary(self) -> dict[str, Any]:
        return {
            "kind": "static_template_batch",
            "layout": "static_template",
            "backend": self.backend,
            "num_envs": self.num_envs,
            "exact_batch": True,
            "capability_profile": self.capability_profile,
            "capability_status": "available",
            "template_digest": self.template_digest,
            "field_ownership": {
                "template_shared": list(self.shared_fields),
                "world_persistent": list(self.world_state_fields),
                "substep_workspace": list(self.workspace_fields),
            },
            "compiled_template_fields": list(self.compiled_field_names),
            "shared_template": {
                "bodies": self.body_count,
                "geoms": self.geom_count,
                "qpos": self.qpos_count,
                "qvel": self.qvel_count,
                "actuators": self.actuator_count,
                "sites": self.site_count,
            },
            "per_world_named_state_bytes_lower_bound": self.per_world_named_state_bytes_lower_bound,
            "status": "descriptor",
        }


def _contact_pairs_are_local_excluded(joint_data: Mapping[str, Any], geom_count: int) -> bool:
    """Return whether the no-contact profile can prove all geom pairs excluded."""

    body_ids = np.asarray(joint_data.get("geom_bodyid", ()), dtype=np.int32).reshape(-1)
    if body_ids.size != geom_count:
        return False
    raw_pairs = joint_data.get("contact_exclude_pairs", ())
    excludes = {
        tuple(sorted((int(pair[0]), int(pair[1]))))
        for pair in np.asarray(raw_pairs, dtype=np.int64).reshape(-1, 2)
    }
    for left in range(geom_count):
        for right in range(left + 1, geom_count):
            if body_ids[left] == body_ids[right]:
                continue
            if tuple(sorted((int(body_ids[left]), int(body_ids[right])))) not in excludes:
                return False
    return True


def _extract_static_model(
    *,
    compiled_scene: object,
    config: ResolvedEnvConfig,
    descriptor: StaticTemplateDescriptor,
) -> dict[str, np.ndarray | float | int | str]:
    model = getattr(compiled_scene, "scene_model", None)
    joint_data: dict[str, Any] = dict(getattr(model, "joint_data", None) or {})
    objects = tuple(getattr(model, "objects", ()) or ())
    if descriptor.backend not in {"cpu", "cuda"}:
        raise StageUnavailableError(
            "static_template currently supports only cpu/cuda; "
            f"requested backend={descriptor.backend!r}"
        )
    runtime = config.runtime
    if runtime.batch_physics_layout != "static_template":
        raise ValueError("static template runtime requires batch_physics_layout='static_template'")
    if descriptor.body_count != 2 or int(joint_data.get("n_joints", 0)) != 1:
        raise StageUnavailableError(
            "static_template capability hinge_or_slide_no_contact_v1 requires exactly "
            "two bodies and one joint"
        )
    if descriptor.qpos_count != 1 or descriptor.qvel_count != 1:
        raise StageUnavailableError(
            "static_template capability hinge_or_slide_no_contact_v1 requires one qpos and one dof"
        )
    if descriptor.actuator_count < 1:
        raise StageUnavailableError(
            "static_template direct-motor profile requires at least one actuator"
        )
    if int(joint_data.get("n_tendons", 0)) or int(joint_data.get("n_sensors", 0)):
        raise StageUnavailableError(
            "static_template capability hinge_or_slide_no_contact_v1 does not yet support tendons or sensors"
        )
    joint_type = int(_as_array(joint_data, "jnt_type", (1,), dtype=np.int32)[0])
    if joint_type not in (2, 3):
        raise StageUnavailableError(
            "static_template capability hinge_or_slide_no_contact_v1 supports only hinge/slide joints"
        )
    parent = int(_as_array(joint_data, "jnt_parent_body", (1,), dtype=np.int32)[0])
    child = int(_as_array(joint_data, "jnt_child_body", (1,), dtype=np.int32)[0])
    if parent < 0 or child != 1 or parent != 0:
        raise StageUnavailableError(
            "static_template capability requires body 0 as fixed root and body 1 as the joint child"
        )
    if len(tuple(runtime.gravity)) != 3:
        raise ValueError("gravity must be a three-component vector")
    if not _contact_pairs_are_local_excluded(joint_data, descriptor.geom_count):
        raise StageUnavailableError(
            "static_template no-contact profile requires every inter-body geom pair to be excluded"
        )

    for name in (
        "actuator_trnid",
        "actuator_trntype",
        "actuator_dyntype",
        "actuator_gaintype",
        "actuator_biastype",
    ):
        if descriptor.actuator_count:
            values = _as_array(joint_data, name, (descriptor.actuator_count,), dtype=np.int32)
            if name == "actuator_trnid" and np.any(values != 0):
                raise StageUnavailableError("static_template direct-motor profile requires all actuators to target joint 0")
            if name != "actuator_trnid" and np.any(values != 0):
                raise StageUnavailableError(
                    "static_template direct-motor profile requires zero actuator dynamics/gain/bias types"
                )

    if str(runtime.integrator).lower() not in {"euler", "implicitfast"}:
        raise StageUnavailableError(
            "static_template hinge_or_slide_no_contact_v1 supports integrator=euler or implicitfast"
        )

    body_pos = _as_array(joint_data, "body_pos", (descriptor.body_count, 3))
    body_quat = _as_array(joint_data, "body_quat", (descriptor.body_count, 4))
    body_ipos = _as_array(joint_data, "body_ipos", (descriptor.body_count, 3))
    body_iquat = _as_array(joint_data, "body_iquat", (descriptor.body_count, 4))
    body_parent = _as_array(joint_data, "body_parentid", (descriptor.body_count,), dtype=np.int32)
    body_mass = _object_array(objects, "body_config", 1.0)
    body_inertia = np.asarray(
        [np.asarray(getattr(obj, "body_inertia", (1.0, 1.0, 1.0)), dtype=np.float32) for obj in objects],
        dtype=np.float32,
    )
    if body_inertia.shape != (descriptor.body_count, 3):
        raise StageUnavailableError("static_template could not extract body inertia from current scene objects")
    body_gravcomp = _as_array(
        joint_data,
        "body_gravcomp",
        (descriptor.body_count,),
        default=np.zeros(descriptor.body_count, dtype=np.float32),
    )

    model_data: dict[str, np.ndarray | float | int | str] = {
        "body_pos": body_pos,
        "body_quat": body_quat,
        "body_ipos": body_ipos,
        "body_iquat": body_iquat,
        "body_parent": body_parent,
        "body_mass": body_mass,
        "body_inertia": body_inertia,
        "body_gravcomp": body_gravcomp,
        "jnt_parent_body": _as_array(joint_data, "jnt_parent_body", (1,), dtype=np.int32),
        "jnt_child_body": _as_array(joint_data, "jnt_child_body", (1,), dtype=np.int32),
        "jnt_type": np.asarray([joint_type], dtype=np.int32),
        "jnt_qposadr": _as_array(joint_data, "jnt_qposadr", (1,), dtype=np.int32),
        "jnt_dofadr": _as_array(joint_data, "jnt_dofadr", (1,), dtype=np.int32),
        "jnt_axis_parent": _as_array(joint_data, "jnt_axis_parent", (1, 3)),
        "jnt_axis_child": _as_array(joint_data, "jnt_axis_child", (1, 3)),
        "jnt_anchor_child": _as_array(joint_data, "jnt_anchor_child", (1, 3)),
        "jnt_damping": _as_array(joint_data, "jnt_damping", (1,)),
        "jnt_stiffness": _as_array(joint_data, "jnt_stiffness", (1,)),
        "jnt_ref": _as_array(joint_data, "jnt_ref", (1,)),
        "jnt_ref_pos": _as_array(joint_data, "jnt_ref_pos", (1,)),
        "jnt_armature": _as_array(joint_data, "jnt_armature", (1,)),
        "geom_bodyid": _as_array(joint_data, "geom_bodyid", (descriptor.geom_count,), dtype=np.int32),
        "geom_pos": _as_array(joint_data, "geom_pos", (descriptor.geom_count, 3)),
        "geom_quat": _as_array(joint_data, "geom_quat", (descriptor.geom_count, 4)),
        "site_bodyid": _as_array(
            joint_data,
            "site_bodyid",
            (descriptor.site_count,),
            dtype=np.int32,
            default=np.zeros(descriptor.site_count, dtype=np.int32),
        ),
        "site_pos": _as_array(
            joint_data,
            "site_pos",
            (descriptor.site_count, 3),
            default=np.zeros((descriptor.site_count, 3), dtype=np.float32),
        ),
        "site_quat": _as_array(
            joint_data,
            "site_quat",
            (descriptor.site_count, 4),
            default=np.tile(np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float32), (descriptor.site_count, 1)),
        ),
        "actuator_gear": _as_array(
            joint_data,
            "actuator_gear",
            (descriptor.actuator_count, 6),
            default=np.zeros((descriptor.actuator_count, 6), dtype=np.float32),
        ),
        "root_pos": _as_array(joint_data, "root_pos", (3,), default=np.zeros(3, dtype=np.float32)),
        "root_quat": _as_array(
            joint_data,
            "root_quat",
            (4,),
            default=np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
        ),
        "gravity": np.asarray(runtime.gravity, dtype=np.float32),
        "physics_dt": float(runtime.physics_dt),
        "integrator": str(runtime.integrator).lower(),
    }
    return model_data


def _extract_fused_articulated_model(
    *,
    compiled_scene: object,
    config: ResolvedEnvConfig,
    descriptor: StaticTemplateDescriptor,
) -> dict[str, np.ndarray | float | int | str]:
    """Extract the local model consumed by the fused world-local kernel.

    This boundary intentionally reads immutable compiled arrays only.  It does
    not create B copies of a solver, and it never rewrites body/geom IDs with a
    world offset.  Missing optional arrays are filled with the same defaults
    used by the current RigidSolver compiler.
    """

    from .fused import _build_actuator_moments

    model = getattr(compiled_scene, "scene_model", None)
    joint_data: dict[str, Any] = dict(getattr(model, "joint_data", None) or {})
    objects = tuple(getattr(model, "objects", ()) or ())
    nb, nj, nq, nd, na = descriptor.body_count, int(joint_data.get("n_joints", 0)), descriptor.qpos_count, descriptor.qvel_count, descriptor.actuator_count
    ng, ns = descriptor.geom_count, descriptor.site_count
    if nb < 1 or nj < 1 or nq < 1 or nd < 1:
        raise StageUnavailableError("fused articulated profile requires a non-empty articulated local template")

    def alias(names: tuple[str, ...], shape: tuple[int, ...], *, dtype=np.float32, default=None) -> np.ndarray:
        for name in names:
            if name in joint_data:
                return _as_array(joint_data, name, shape, dtype=dtype, default=default)
        return np.zeros(shape, dtype=dtype) if default is None else np.asarray(default, dtype=dtype).reshape(shape)

    body_mass = np.asarray([
        float(getattr(getattr(obj, "body_config", None), "mass", 1.0)) for obj in objects
    ], dtype=np.float32)
    if body_mass.shape != (nb,):
        body_mass = np.ones(nb, dtype=np.float32)
    body_inertia = np.asarray([
        np.asarray(getattr(obj, "body_inertia", (1.0, 1.0, 1.0)), dtype=np.float32).reshape(3)
        for obj in objects
    ], dtype=np.float32)
    if body_inertia.shape != (nb, 3):
        body_inertia = np.ones((nb, 3), dtype=np.float32)

    jnt_type = alias(("jnt_type",), (nj,), dtype=np.int32)
    jnt_qposadr = alias(("jnt_qposadr",), (nj,), dtype=np.int32)
    jnt_dofadr = alias(("jnt_dofadr",), (nj,), dtype=np.int32)
    jnt_child = alias(("jnt_child_body",), (nj,), dtype=np.int32)
    jnt_parent = alias(("jnt_parent_body",), (nj,), dtype=np.int32, default=np.full(nj, -1, dtype=np.int32))
    dof_counts = {0: 6, 1: 3, 2: 1, 3: 1, 4: 2}
    dof_joint = np.zeros(nd, dtype=np.int32)
    dof_subdof = np.zeros(nd, dtype=np.int32)
    for j in range(nj):
        start = int(jnt_dofadr[j])
        for local in range(dof_counts.get(int(jnt_type[j]), 0)):
            if 0 <= start + local < nd:
                dof_joint[start + local] = j
                dof_subdof[start + local] = local
    moments, coefficients = _build_actuator_moments(joint_data, n_act=na, n_joints=nj, n_dof=nd)

    runtime = config.runtime
    ground = getattr(model, "ground", None)
    ground_height = float(getattr(ground, "height", 0.0))
    ground_margin = float(getattr(ground, "contact_margin", 1.0e-6))
    # Compiler geometry types use the RigidSolver local enum.  Keeping these
    # fields in the immutable template is what makes contact world-local.
    geom_type = alias(("geom_type", "geom_shape_type"), (ng,), dtype=np.int32, default=np.zeros(ng, dtype=np.int32))
    geom_size = alias(("geom_size", "geom_shape_data", "geom_proxy_params"), (ng, 3), default=np.zeros((ng, 3), dtype=np.float32))
    geom_contype = alias(("geom_contype",), (ng,), dtype=np.int32, default=np.ones(ng, dtype=np.int32))
    geom_conaffinity = alias(("geom_conaffinity",), (ng,), dtype=np.int32, default=np.ones(ng, dtype=np.int32))
    geom_friction = alias(("geom_friction",), (ng, 3), default=np.ones((ng, 3), dtype=np.float32))
    return {
        "n_bodies": np.asarray(nb, dtype=np.int32),
        "n_geoms": np.asarray(ng, dtype=np.int32),
        "n_sites": np.asarray(ns, dtype=np.int32),
        "n_joints": np.asarray(nj, dtype=np.int32),
        "n_qpos": np.asarray(nq, dtype=np.int32),
        "n_dof": np.asarray(nd, dtype=np.int32),
        "n_actuators": np.asarray(na, dtype=np.int32),
        "body_pos_local": alias(("body_pos", "body_pos_local"), (nb, 3)),
        "body_quat_local": alias(("body_quat", "body_quat_local"), (nb, 4), default=np.tile(np.asarray([1, 0, 0, 0], dtype=np.float32), (nb, 1))),
        "body_parentid": alias(("body_parentid",), (nb,), dtype=np.int32, default=np.full(nb, -1, dtype=np.int32)),
        "body_jntadr": alias(("body_jntadr",), (nb,), dtype=np.int32),
        "body_jntnum": alias(("body_jntnum",), (nb,), dtype=np.int32, default=np.ones(nb, dtype=np.int32)),
        "body_mass": body_mass,
        "body_inertia": body_inertia,
        "body_ipos": alias(("body_ipos",), (nb, 3)),
        "body_iquat": alias(("body_iquat",), (nb, 4), default=np.tile(np.asarray([1, 0, 0, 0], dtype=np.float32), (nb, 1))),
        "body_gravcomp": alias(("body_gravcomp",), (nb,), default=np.zeros(nb, dtype=np.float32)),
        "jnt_type": jnt_type,
        "jnt_qposadr": jnt_qposadr,
        "jnt_dofadr": jnt_dofadr,
        "jnt_child_body": jnt_child,
        "jnt_parent_body": jnt_parent,
        "jnt_axis_parent": alias(("jnt_axis_parent",), (nj, 3)),
        "jnt_axis_child": alias(("jnt_axis_child",), (nj, 3)),
        "jnt_anchor_child": alias(("jnt_anchor_child",), (nj, 3)),
        "jnt_damping": alias(("jnt_damping",), (nj,)),
        "jnt_stiffness": alias(("jnt_stiffness",), (nj,)),
        "jnt_ref": alias(("jnt_ref",), (nj,)),
        "jnt_armature": alias(("jnt_armature",), (nj,)),
        "dof_joint": dof_joint,
        "dof_subdof": dof_subdof,
        "geom_bodyid": alias(("geom_bodyid",), (ng,), dtype=np.int32),
        "geom_pos": alias(("geom_pos", "geom_local_pos"), (ng, 3)),
        "geom_quat": alias(("geom_quat", "geom_local_quat"), (ng, 4), default=np.tile(np.asarray([1, 0, 0, 0], dtype=np.float32), (ng, 1))),
        "geom_type": geom_type,
        "geom_size": geom_size,
        "geom_contype": geom_contype,
        "geom_conaffinity": geom_conaffinity,
        "geom_friction": geom_friction,
        "site_bodyid": alias(("site_bodyid",), (ns,), dtype=np.int32),
        "site_pos": alias(("site_pos", "site_local_pos"), (ns, 3)),
        "site_quat": alias(("site_quat", "site_local_quat"), (ns, 4), default=np.tile(np.asarray([1, 0, 0, 0], dtype=np.float32), (ns, 1))),
        "actuator_moment_dofadr": moments,
        "actuator_moment_coef": coefficients,
        "root_pos": alias(("root_pos",), (3,), default=np.zeros(3, dtype=np.float32)),
        "root_quat": alias(("root_quat",), (4,), default=np.asarray([1, 0, 0, 0], dtype=np.float32)),
        "gravity": np.asarray(runtime.gravity, dtype=np.float32),
        "physics_dt": float(runtime.physics_dt),
        "integrator": str(runtime.integrator).lower(),
        "ground_height": ground_height,
        "ground_contact_margin": ground_margin,
        "contact_bias_relaxation": 0.2,
        "contact_bias_max_velocity": 0.25,
        "contact_solver_iterations": int(runtime.body_contact_solver_iterations or 1),
    }


class StaticTemplateBatchRuntime:
    """A homogeneous batch with shared local model and per-world device state."""

    @classmethod
    def from_compiled_scene(
        cls,
        *,
        compiled_scene: object,
        config: ResolvedEnvConfig,
        num_envs: int,
        backend: str,
    ) -> "StaticTemplateBatchRuntime":
        capability = resolve_static_template_profile(
            config.runtime.static_template.profile,
            compiled_scene=compiled_scene,
        )
        if config.runtime.enable_ground_contact is True and not capability.supports_ground_contact:
            raise StageUnavailableError(
                f"static-template profile {capability.profile!r} does not support ground contact"
            )
        if config.runtime.enable_domain_boundary_contact and not capability.supports_domain_boundary_contact:
            raise StageUnavailableError(
                f"static-template profile {capability.profile!r} does not support domain-boundary contact"
            )
        descriptor = StaticTemplateDescriptor.from_compiled_scene(
            compiled_scene=compiled_scene,
            num_envs=num_envs,
            backend=backend,
            capability=capability,
        )
        # Provider-owned bootstrap must run before Taichi initialization.  The
        # fused contact path imports its audited Triton handles at module load;
        # callers must not need an undocumented ``import triton`` prelude.
        from ....utils._device_stack import preload_device_stack
        preload_device_stack()

        from geophys.test_runtime import init_test_backend

        init_test_backend(str(backend))
        if capability.profile == "rigid_batch_v1":
            from ..geophys.rigid_batch import GeoPhysRigidBatchRuntime

            physics = GeoPhysRigidBatchRuntime.from_compiled_scene(
                compiled_scene=compiled_scene,
                config=config,
                num_envs=descriptor.num_envs,
            )
        elif capability.profile == "articulated_ground_contact_v1":
    # The first exact-B articulated profile is a semantic reference
            # kernel backed by exact-B local RigidSolver owners.  It is selected
            # through the same generic factory and keeps all contact IDs local;
            # the fused B-axis kernel remains an explicit future optimization.
            from .reference import StaticTemplateRigidSolverReference

            physics = StaticTemplateRigidSolverReference.from_compiled_scene(
                compiled_scene=compiled_scene,
                config=config,
                num_envs=descriptor.num_envs,
                backend=str(backend),
            )
        elif capability.profile in {"articulated_fused_no_contact_v1", "articulated_fused_ground_contact_v1"}:
            contact_enabled = capability.profile == "articulated_fused_ground_contact_v1"
            if contact_enabled and config.runtime.enable_ground_contact is False:
                raise StageUnavailableError(
                    "articulated_fused_ground_contact_v1 requires enable_ground_contact=True or None"
                )
            if (not contact_enabled and config.runtime.enable_ground_contact is True) or config.runtime.enable_domain_boundary_contact:
                raise StageUnavailableError(
                    f"{capability.profile} requires an explicit supported contact configuration"
                )
            model_data = _extract_fused_articulated_model(
                compiled_scene=compiled_scene,
                config=config,
                descriptor=descriptor,
            )
            from .fused import StaticTemplateFusedArticulated

            randomization_enabled = _world_randomization_enabled(config)
            contact_policy = config.runtime.static_template.contact
            if (
                contact_policy.fixed_topology_child_schur
                and capability.profile != "articulated_fused_ground_contact_v1"
            ):
                raise StageUnavailableError(
                    "fixed_topology_child_schur requires the "
                    "articulated_fused_ground_contact_v1 capability"
                )
            physics = StaticTemplateFusedArticulated(
                model=model_data,
                num_envs=descriptor.num_envs,
                control_substeps=int(config.runtime.control_substeps),
                backend=descriptor.backend,
                contact_enabled=contact_enabled,
                kinematics_backend=str(config.runtime.static_template.kinematics_backend),
                contact_precision=str(config.runtime.static_template.contact_precision),
                contact_response_backend=str(contact_policy.response_backend),
                fixed_topology_child_schur=bool(
                    contact_policy.fixed_topology_child_schur
                ),
                root_factor_6x6=bool(contact_policy.root_factor_6x6),
                cuda_graph=bool(config.runtime.static_template.cuda_graph),
                world_randomization_enabled=randomization_enabled,
                push_event_capacity=(
                    _push_event_capacity(config) if randomization_enabled else 0
                ),
            )
        else:
            model_data = _extract_static_model(
                compiled_scene=compiled_scene,
                config=config,
                descriptor=descriptor,
            )
            from .physics import StaticTemplatePhysics

            physics = StaticTemplatePhysics(
                model=model_data,
                num_envs=descriptor.num_envs,
                control_substeps=int(config.runtime.control_substeps),
                qpos_count=descriptor.qpos_count,
                qvel_count=descriptor.qvel_count,
                actuator_count=descriptor.actuator_count,
                body_count=descriptor.body_count,
                geom_count=descriptor.geom_count,
                site_count=descriptor.site_count,
                max_contact_pairs_per_world=capability.max_contact_pairs_per_world,
                max_constraint_rows_per_world=capability.max_constraint_rows_per_world,
                backend=descriptor.backend,
            )
        provider_facts = _provider_execution_facts(physics)
        if capability.profile == "articulated_ground_contact_v1":
            max_pairs = int(provider_facts.get("max_contact_pairs_per_world", 0))
            max_rows = int(provider_facts.get("max_constraint_rows_per_world", 0))
            if max_pairs > int(capability.max_contact_pairs_per_world):
                raise StageUnavailableError(
                    "articulated static contact workspace exceeds the selected "
                    f"per-world pair capacity ({max_pairs} > "
                    f"{capability.max_contact_pairs_per_world})"
                )
            if max_rows > int(capability.max_constraint_rows_per_world):
                raise StageUnavailableError(
                    "articulated static constraint workspace exceeds the selected "
                    f"per-world row capacity ({max_rows} > "
                    f"{capability.max_constraint_rows_per_world})"
                )
        initial = compiled_scene.initial_state
        initial_state = {
            name: np.repeat(
                np.asarray(getattr(initial, name), dtype=np.float32)[None, :],
                descriptor.num_envs,
                axis=0,
            )
            for name in ("qpos", "qvel", "qacc", "ctrl", "act")
        }
        runtime = cls(
            physics=physics,
            descriptor=descriptor,
            control_substeps=int(config.runtime.control_substeps),
            initial_state=initial_state,
            execution_plan=StaticTemplateExecutionPlan.from_runtime(
                descriptor=descriptor,
                capability=capability,
                provider_facts=provider_facts,
            ),
        )
        runtime._write_state(initial_state, np.ones(descriptor.num_envs, dtype=np.bool_))
        if config.runtime.prewarm:
            runtime.prewarm()
        return runtime

    def __init__(
        self,
        *,
        physics: StaticTemplateProviderProtocol,
        descriptor: StaticTemplateDescriptor,
        control_substeps: int,
        initial_state: Mapping[str, np.ndarray],
        execution_plan: StaticTemplateExecutionPlan | None = None,
    ) -> None:
        if int(control_substeps) < 1:
            raise ValueError("control_substeps must be positive")
        self._physics = physics
        self._descriptor = descriptor
        self.num_envs = descriptor.num_envs
        self.backend = descriptor.backend
        self.control_substeps = int(control_substeps)
        self._counts = {
            "qpos": descriptor.qpos_count,
            "qvel": descriptor.qvel_count,
            "qacc": descriptor.qvel_count,
            "ctrl": descriptor.actuator_count,
            "act": descriptor.actuator_count,
            "body": descriptor.body_count,
            "site": descriptor.site_count,
        }
        initial_values = self._normalize_write_state(initial_state)
        for value in initial_values.values():
            value.setflags(write=False)
        self._initial_state = initial_values
        self.execution_plan = execution_plan

    def apply_world_randomization(
        self,
        *,
        payload: WorldRandomizationBatch,
        mask: np.ndarray,
    ) -> None:
        """Forward a reset-boundary payload to a capable static runtime."""

        setter = getattr(self._physics, "apply_world_randomization", None)
        if not callable(setter):
            raise StageUnavailableError(
                "static-template physics implementation has no world randomization capability"
            )
        setter(payload=payload, mask=np.asarray(mask, dtype=np.bool_))

    def reset(self, *, state: Mapping[str, np.ndarray], mask: np.ndarray) -> BatchResetResult:
        reset_mask = np.asarray(mask, dtype=np.bool_)
        if reset_mask.shape != (self.num_envs,):
            raise ValueError("batch reset mask must have shape (B,)")
        current = self._read_state()
        values = self._normalize_write_state(state, current=current)
        merged = {name: np.asarray(current[name], dtype=np.float32).copy() for name in values}
        for name in values:
            merged[name][reset_mask] = values[name][reset_mask]
        self._write_state(merged, np.ones(self.num_envs, dtype=np.bool_))
        reset_workspace = getattr(self._physics, "reset_workspace", None)
        if callable(reset_workspace):
            reset_workspace(reset_mask)
        reset_randomization = getattr(self._physics, "reset_world_randomization", None)
        if callable(reset_randomization):
            reset_randomization(reset_mask)
        return BatchResetResult(state=BatchState(self._read_state()))

    def step(self, action: np.ndarray) -> BatchStepResult:
        value = np.asarray(action, dtype=np.float32)
        expected = (self.num_envs, self._counts["ctrl"])
        if value.shape != expected:
            raise ValueError(f"batch control action must have shape {expected}, got {value.shape}")
        if not np.isfinite(value).all():
            raise ValueError("batch control action must be finite")
        self._physics.write_ctrl(value)
        self._physics.step(self.control_substeps)
        return BatchStepResult(state=BatchState(self._read_state()))

    def read_device_state(self, names: tuple[str, ...]) -> DeviceBatchState:
        """Read named state tensors through the runtime's optional device path."""

        reader = getattr(self._physics, "read_device_state", None)
        if not callable(reader):
            raise StageUnavailableError(
                "static-template physics implementation has no device state capability"
            )
        return reader(tuple(str(name) for name in names))

    def set_profile_collector(self, collector) -> None:
        """将诊断分段 collector 转发到具体 static physics 实现。"""

        setter = getattr(self._physics, "set_profile_collector", None)
        if callable(setter):
            setter(collector)

    def step_device(self, control: Any) -> DeviceBatchState:
        """Apply one public control tick without a NumPy substep readback."""

        stepper = getattr(self._physics, "step_device", None)
        if not callable(stepper):
            raise StageUnavailableError(
                "static-template physics implementation has no device step capability"
            )
        result = stepper(control)
        if not isinstance(result, DeviceBatchState):
            raise TypeError(
                "static-template physics step_device() must return DeviceBatchState"
            )
        return result

    def reset_device(
        self,
        state: Mapping[str, Any],
        mask: Any,
        *,
        selection: DeviceResetSelection | None = None,
    ) -> DeviceBatchState:
        resetter = getattr(self._physics, "reset_device", None)
        if not callable(resetter):
            raise StageUnavailableError(
                "static-template physics implementation has no device reset capability"
            )
        if selection is not None and _accepts_selection(resetter):
            result = resetter(state, mask, selection=selection)
        else:
            result = resetter(state, mask)
        if not isinstance(result, DeviceBatchState):
            raise TypeError(
                "static-template physics reset_device() must return DeviceBatchState"
            )
        return result

    def validate_device_reset_selection(
        self,
        mask: Any,
        selection: DeviceResetSelection,
    ) -> None:
        validator = getattr(
            self._physics,
            "validate_device_reset_selection",
            None,
        )
        if callable(validator):
            validator(mask, selection)
            return
        validate_reset_selection_contract(
            selection,
            mask=mask,
            num_envs=self.num_envs,
            device=selection.device,
            require_data_pointer=True,
        )

    def resource_summary(self) -> dict[str, Any]:
        summary = self._descriptor.resource_summary()
        summary.update(self._physics.resource_summary())
        summary["runtime_adapter"] = type(self).__name__
        summary["physics_provider"] = type(self._physics).__name__
        summary["provider_surface"] = "static_template_provider_v1"
        summary["profile"] = self._descriptor.capability_profile
        summary["control_substeps"] = self.control_substeps
        summary["exact_batch"] = True
        summary["capacity_policy"] = "exact_batch"
        summary["status"] = "ready"
        summary["implementation_status"] = summary.get(
            "implementation_status", "fused_device_kernel"
        )
        methods_available = bool(
            callable(getattr(self._physics, "step_device", None))
            and callable(getattr(self._physics, "read_device_state", None))
            and callable(getattr(self._physics, "reset_device", None))
        )
        device_name = None
        if methods_available:
            try:
                device_name = str(self._physics.read_device_state(("qpos",)).device)
            except Exception:
                methods_available = False
        device_compatible = (
            device_name is not None
            and (
                self.backend != "cuda"
                or device_name.startswith("cuda")
            )
        )
        summary["device_transition"] = {
            "available": bool(methods_available and device_compatible),
            "runtime_method": "step_device",
            "zero_copy_substeps": bool(methods_available and device_compatible),
            "field_device": device_name,
            "reason": None if (methods_available and device_compatible) else (
                "solver fields are not on the requested simulator device"
                if methods_available else "runtime device methods are incomplete"
            ),
        }
        if self.execution_plan is not None:
            summary["execution_plan"] = self.execution_plan.as_dict()
        return summary

    def parallel_render_state_source(self) -> tuple[object, str]:
        """向 parallel renderer 提供 provider-owned 的独立渲染状态 port。"""

        source = getattr(self._physics, "render_state_source", None)
        if not callable(source):
            raise StageUnavailableError(
                "static-template provider has no render_state_source capability"
            )
        result = source()
        if (
            not isinstance(result, tuple)
            or len(result) != 2
            or not isinstance(result[1], str)
        ):
            raise TypeError(
                "static-template provider render_state_source() must return "
                "(owner, mode)"
            )
        return result

    def prewarm(self, profile: str = "interactive") -> None:
        del profile
        self._physics.prewarm()

    def close(self) -> None:
        close = getattr(self._physics, "close", None)
        if callable(close):
            close()

    def _normalize_write_state(
        self,
        state: Mapping[str, np.ndarray],
        *,
        current: Mapping[str, np.ndarray] | None = None,
    ) -> dict[str, np.ndarray]:
        allowed = ("qpos", "qvel", "qacc", "ctrl", "act")
        unknown = set(state) - set(allowed)
        if unknown:
            raise ValueError(f"static template reset contains unknown state fields: {sorted(unknown)}")
        result: dict[str, np.ndarray] = {}
        for name in allowed:
            width = self._counts[name]
            if name in state:
                value = np.asarray(state[name], dtype=np.float32)
                expected = (self.num_envs, width)
                if value.shape != expected:
                    raise ValueError(f"batch state {name} must have shape {expected}, got {value.shape}")
                if not np.isfinite(value).all():
                    raise ValueError(f"batch state {name} must be finite")
                result[name] = value.copy()
            elif current is not None:
                result[name] = np.asarray(current[name], dtype=np.float32).copy()
            else:
                result[name] = np.asarray(self._initial_state[name], dtype=np.float32).copy()
        return result

    def _write_state(self, state: Mapping[str, np.ndarray], mask: np.ndarray) -> None:
        del mask
        values = self._normalize_write_state(state)
        self._physics.write_state(values)
        self._physics.refresh()

    def _read_state(self) -> dict[str, np.ndarray]:
        return self._physics.read_state()


__all__ = ["StaticTemplateBatchRuntime", "StaticTemplateDescriptor"]
