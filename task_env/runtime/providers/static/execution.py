"""Internal task-agnostic static-template execution plan.

The plan is the small provider-owned inventory shared by the current semantic
reference and the fused kernel.  It deliberately contains no
task name, solver import, or packed global body/geom identifier.  The plan is
also useful in metadata: a benchmark can distinguish a real ``(B, local)``
kernel from the exact-B local-solver reference without inspecting private
runtime objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


def _shape_map(num_envs: int, descriptor: object, *, max_pairs: int, max_rows: int) -> dict[str, tuple[int, ...]]:
    worlds = int(num_envs)
    bodies = int(getattr(descriptor, "body_count", 0))
    geoms = int(getattr(descriptor, "geom_count", 0))
    sites = int(getattr(descriptor, "site_count", 0))
    qpos = int(getattr(descriptor, "qpos_count", 0))
    qvel = int(getattr(descriptor, "qvel_count", 0))
    actuators = int(getattr(descriptor, "actuator_count", 0))
    dof = max(1, qvel)
    return {
        "qpos": (worlds, qpos),
        "qvel": (worlds, qvel),
        "qacc": (worlds, qvel),
        "ctrl": (worlds, actuators),
        "act": (worlds, actuators),
        "body_world_pos": (worlds, bodies, 3),
        "body_world_quat": (worlds, bodies, 4),
        "geom_world_pos": (worlds, geoms, 3),
        "geom_world_quat": (worlds, geoms, 4),
        "site_world_pos": (worlds, sites, 3),
        "site_world_quat": (worlds, sites, 4),
        # Fixed-shape dynamics scratch follows the origin/parallel_xxy
        # pipeline, but is an inventory only until the fused kernel owns it.
        "mass_matrix": (worlds, dof, dof),
        "mass_factor": (worlds, dof, dof),
        "crb_spatial_inertia": (worlds, bodies, 3, 3),
        "crb_mass_com": (worlds, bodies, 3),
        "crb_mass": (worlds, bodies),
        "rne_linear_acc": (worlds, bodies, 3),
        "rne_angular_acc": (worlds, bodies, 3),
        "candidate_pair": (worlds, max(0, int(max_pairs))),
        "constraint_row": (worlds, max(0, int(max_rows))),
        "reset_mask": (worlds,),
    }


@dataclass(frozen=True)
class StaticTemplateExecutionPlan:
    """Immutable static-batch route and fixed-shape workspace inventory."""

    profile: str
    backend: str
    num_envs: int
    addressing: str
    execution_route: str
    fused_kernel: bool
    state_shapes: Mapping[str, tuple[int, ...]]
    workspace_shapes: Mapping[str, tuple[int, ...]]
    reset_semantics: str
    global_id_policy: str

    @classmethod
    def from_runtime(
        cls,
        *,
        descriptor: object,
        capability: object,
        provider_facts: Mapping[str, Any] | None = None,
        physics: object | None = None,
        workspace: object | None = None,
    ) -> "StaticTemplateExecutionPlan":
        """Build an immutable plan from provider-published layout facts.

        Workspace and kernel layout are mutable-provider concerns.  Reading
        provider private attributes here made the facade and plan dependent on
        each implementation's storage naming, so providers now publish this
        small immutable fact set through their internal surface.
        """

        # Keep the previously accepted keyword shape for callers that used
        # this exported plan helper directly.  The compatibility path still
        # requires the provider-owned method and deliberately ignores the old
        # workspace object; it never resumes private storage inspection.
        del workspace
        if provider_facts is None and physics is not None:
            publisher = getattr(physics, "execution_plan_facts", None)
            if not callable(publisher):
                raise TypeError(
                    "static-template physics must expose execution_plan_facts()"
                )
            provider_facts = publisher()
        if not isinstance(provider_facts, Mapping):
            raise TypeError("static-template provider facts must be a mapping")
        max_pairs = int(provider_facts.get("max_contact_pairs_per_world", 0))
        max_rows = int(provider_facts.get("max_constraint_rows_per_world", 0))
        shapes = _shape_map(
            int(getattr(descriptor, "num_envs")),
            descriptor,
            max_pairs=max_pairs,
            max_rows=max_rows,
        )
        contact_slots = int(
            provider_facts.get("contact_workspace_slots_per_world", 0)
        )
        if contact_slots:
            worlds = int(getattr(descriptor, "num_envs"))
            bodies = int(getattr(descriptor, "body_count", 0))
            dof = max(1, int(getattr(descriptor, "qvel_count", 0)))
            shapes.update({
                "ground_contact_active": (worlds, bodies),
                "ground_contact_count": (worlds, bodies),
                "body_contact_active": (worlds, bodies),
                "body_contact_count": (worlds, bodies),
                "ground_contact_row": (worlds, contact_slots),
                "ground_contact_jacobian": (worlds, contact_slots, dof),
            })
        state_names = {
            "qpos", "qvel", "qacc", "ctrl", "act", "body_world_pos",
            "body_world_quat", "geom_world_pos", "geom_world_quat",
            "site_world_pos", "site_world_quat",
        }
        if contact_slots:
            state_names.update({
                "ground_contact_active", "ground_contact_count",
                "body_contact_active", "body_contact_count",
            })
        fused = bool(provider_facts.get("fused_kernel", False))
        execution_route = str(
            provider_facts.get(
                "execution_route",
                "fused_world_local" if fused else "isolated_world_reference",
            )
        )
        return cls(
            profile=str(getattr(capability, "profile", "unknown")),
            backend=str(getattr(descriptor, "backend", "unknown")),
            num_envs=int(getattr(descriptor, "num_envs")),
            addressing="world_local_tuple",
            execution_route=execution_route,
            fused_kernel=fused,
            state_shapes={name: shapes[name] for name in sorted(state_names)},
            workspace_shapes={
                name: shapes[name]
                for name in sorted(set(shapes) - state_names)
            },
            reset_semantics="masked_world_reset_then_workspace_clear",
            global_id_policy="forbidden",
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "backend": self.backend,
            "num_envs": int(self.num_envs),
            "addressing": self.addressing,
            "execution_route": self.execution_route,
            "fused_kernel": bool(self.fused_kernel),
            "state_shapes": {name: list(shape) for name, shape in self.state_shapes.items()},
            "workspace_shapes": {name: list(shape) for name, shape in self.workspace_shapes.items()},
            "reset_semantics": self.reset_semantics,
            "global_id_policy": self.global_id_policy,
        }


__all__ = ["StaticTemplateExecutionPlan"]
