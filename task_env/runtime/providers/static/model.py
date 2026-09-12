"""Immutable, task-agnostic static-template model inventory.

This is the public extraction boundary for Stage 15.5.  It records which
compiled fields are shared topology versus mutable per-world state and gives
the exact compiled local template a deterministic digest.  It intentionally
does not own a solver or import Taichi.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from collections.abc import Mapping
from typing import Any

import numpy as np


def _digest_array(hasher: "hashlib._Hash", name: str, value: Any) -> None:
    array = np.ascontiguousarray(np.asarray(value))
    hasher.update(str(name).encode("utf-8"))
    hasher.update(str(array.dtype).encode("ascii"))
    hasher.update(repr(tuple(array.shape)).encode("ascii"))
    hasher.update(array.tobytes(order="C"))


@dataclass(frozen=True)
class StaticTemplateModel:
    """Compiled local model facts and explicit ownership inventory."""

    counts: Mapping[str, int]
    shared_fields: tuple[str, ...]
    world_state_fields: tuple[str, ...]
    workspace_fields: tuple[str, ...]
    template_digest: str
    compiled_field_names: tuple[str, ...] = ()

    @classmethod
    def from_compiled_scene(cls, compiled_scene: object) -> "StaticTemplateModel":
        model = getattr(compiled_scene, "scene_model", None)
        joint_data = dict(getattr(model, "joint_data", None) or {})
        counts = {
            "bodies": len(tuple(getattr(model, "objects", ()) or ())),
            "geoms": int(joint_data.get("n_geoms", 0)),
            "sites": int(joint_data.get("n_sites", 0)),
            "joints": int(joint_data.get("n_joints", 0)),
            "qpos": int(joint_data.get("n_qpos", 0)),
            "qvel": int(joint_data.get("n_dof", 0)),
            "actuators": int(joint_data.get("n_actuators", 0)),
            "tendons": int(joint_data.get("n_tendons", 0)),
            "sensors": int(joint_data.get("n_sensors", 0)),
        }
        hasher = hashlib.sha256()
        for key in sorted(joint_data):
            value = joint_data[key]
            if isinstance(value, (str, int, float, bool)):
                hasher.update(str(key).encode("utf-8"))
                hasher.update(repr(value).encode("utf-8"))
            else:
                try:
                    _digest_array(hasher, key, value)
                except (TypeError, ValueError):
                    hasher.update(str(key).encode("utf-8"))
                    hasher.update(repr(value).encode("utf-8"))
        return cls(
            counts=counts,
            shared_fields=(
                "body/joint/geom/site/actuator topology",
                "mass/inertia/gravity constants",
                "local name/address maps",
            ),
            world_state_fields=(
                "qpos", "qvel", "qacc", "ctrl", "act",
                "body_world_cache", "geom_world_cache", "site_world_cache",
            ),
            workspace_fields=(
                "broadphase_candidates", "contact_manifolds", "constraint_rows",
                "warmstart", "solver_diagnostics",
            ),
            template_digest=hasher.hexdigest(),
            compiled_field_names=tuple(sorted(str(key) for key in joint_data)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "counts": {str(key): int(value) for key, value in self.counts.items()},
            "shared_fields": list(self.shared_fields),
            "world_state_fields": list(self.world_state_fields),
            "workspace_fields": list(self.workspace_fields),
            "template_digest": self.template_digest,
            "compiled_field_names": list(self.compiled_field_names),
        }


__all__ = ["StaticTemplateModel"]
