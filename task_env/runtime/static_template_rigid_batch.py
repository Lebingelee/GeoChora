"""Compatibility name for the source-tree homogeneous rigid batch adapter.

The first-class TaskEnv owner now lives in
:mod:`task_env.runtime.providers.geophys.rigid_batch`.  This
subclass keeps the existing ``rigid_batch_v1`` static-template profile and its
historical import path intact while delegating all BRS ABI translation to the
shared GeoPhys runtime implementation.
"""

from __future__ import annotations

from .providers.geophys.rigid_batch import GeoPhysRigidBatchRuntime


class StaticTemplateRigidBatch(GeoPhysRigidBatchRuntime):
    """Legacy static-template compatibility route for the BRS adapter."""

    runtime_kind = "static_template_src_rigid_batch"
    runtime_layout = "static_template"
    storage_owner_key = "task_env:rigid_batch"
    render_enabled = True

    def step(self, substeps: int | None = None) -> None:
        """Preserve the legacy write-control-then-step helper signature."""

        self.step_substeps(substeps)


__all__ = ["StaticTemplateRigidBatch"]
