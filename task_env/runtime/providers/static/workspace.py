"""World-local contact workspace for static-template runtimes.

The first no-contact profile constructs this with zero capacity.  The
articulated/contact profile will use the same shape with a finite per-world
capacity.  No array in this module encodes a global ``B * local_id`` body or
geom identifier.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, order=True)
class LocalPairKey:
    """Stable sortable identity; deliberately not a packed integer key."""

    world_id: int
    local_pair_id: int

    def __post_init__(self) -> None:
        if int(self.world_id) < 0 or int(self.local_pair_id) < 0:
            raise ValueError("local pair key indices must be non-negative")


class StaticTemplateContactWorkspace:
    """Per-world candidate/manifold/row storage with exact-B allocation."""

    def __init__(self, *, num_envs: int, max_pairs_per_world: int, max_rows_per_world: int) -> None:
        self.num_envs = int(num_envs)
        self.max_pairs_per_world = int(max_pairs_per_world)
        self.max_rows_per_world = int(max_rows_per_world)
        if self.num_envs < 1:
            raise ValueError("num_envs must be positive")
        if self.max_pairs_per_world < 0 or self.max_rows_per_world < 0:
            raise ValueError("workspace capacities cannot be negative")
        pair_shape = (self.num_envs, self.max_pairs_per_world)
        row_shape = (self.num_envs, self.max_rows_per_world)
        self.active_pair = np.zeros(pair_shape, dtype=np.bool_)
        self.pair_geom_a = np.full(pair_shape, -1, dtype=np.int32)
        self.pair_geom_b = np.full(pair_shape, -1, dtype=np.int32)
        self.pair_penetration = np.zeros(pair_shape, dtype=np.float32)
        self.active_row = np.zeros(row_shape, dtype=np.bool_)
        self.row_pair = np.full(row_shape, -1, dtype=np.int32)
        self.row_warmstart = np.zeros(row_shape, dtype=np.float32)

    def reset(self, mask: np.ndarray | None = None) -> None:
        selected = (
            np.ones(self.num_envs, dtype=np.bool_)
            if mask is None
            else np.asarray(mask, dtype=np.bool_)
        )
        if selected.shape != (self.num_envs,):
            raise ValueError("workspace reset mask must have shape (B,)")
        self.active_pair[selected] = False
        self.pair_geom_a[selected] = -1
        self.pair_geom_b[selected] = -1
        self.pair_penetration[selected] = 0.0
        self.active_row[selected] = False
        self.row_pair[selected] = -1
        self.row_warmstart[selected] = 0.0

    def key(self, world_id: int, local_pair_id: int) -> LocalPairKey:
        key = LocalPairKey(int(world_id), int(local_pair_id))
        if key.world_id >= self.num_envs:
            raise IndexError("world_id is outside exact-B workspace")
        if key.local_pair_id >= self.max_pairs_per_world:
            raise IndexError("local_pair_id exceeds per-world contact capacity")
        return key

    def resource_summary(self) -> dict[str, int | str]:
        return {
            "addressing": "world_local_tuple",
            "num_envs": self.num_envs,
            "max_contact_pairs_per_world": self.max_pairs_per_world,
            "max_constraint_rows_per_world": self.max_rows_per_world,
            "contact_workspace_bytes": int(
                self.active_pair.nbytes
                + self.pair_geom_a.nbytes
                + self.pair_geom_b.nbytes
                + self.pair_penetration.nbytes
                + self.active_row.nbytes
                + self.row_pair.nbytes
                + self.row_warmstart.nbytes
            ),
        }


__all__ = ["LocalPairKey", "StaticTemplateContactWorkspace"]
