"""Narrow internal provider surface for the static-template facade.

The facade owns the TaskEnv batch ABI.  Static physics providers own mutable
state, workspaces, device graphs, and randomization realization.  These
protocols describe only the seams needed by the facade; they are deliberately
not a common solver base class and are not part of the public runtime API.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

import numpy as np

from ...contracts import DeviceBatchState, WorldRandomizationBatch


class StaticTemplateProviderProtocol(Protocol):
    """Core host/provider surface required by ``StaticTemplateBatchRuntime``."""

    num_envs: int
    backend: str

    def write_state(self, state: Mapping[str, np.ndarray]) -> None: ...

    def write_ctrl(self, ctrl: np.ndarray) -> None: ...

    def read_state(self) -> Mapping[str, np.ndarray]: ...

    def refresh(self) -> None: ...

    def step(self, substeps: int) -> None: ...

    def resource_summary(self) -> Mapping[str, Any]: ...

    def prewarm(self) -> None: ...

    def close(self) -> None: ...

    def execution_plan_facts(self) -> Mapping[str, Any]: ...

    def render_state_source(self) -> tuple[object, str]: ...


class StaticTemplateDeviceProviderProtocol(Protocol):
    """Optional device capability; the facade forwards it without ownership."""

    def read_device_state(self, names: tuple[str, ...]) -> DeviceBatchState: ...

    def step_device(self, control: Any) -> DeviceBatchState: ...

    def reset_device(self, state: Mapping[str, Any], mask: Any) -> DeviceBatchState: ...


class StaticTemplateRandomizationProviderProtocol(Protocol):
    """Optional provider-owned randomization realization and reset hooks."""

    def apply_world_randomization(
        self,
        *,
        payload: WorldRandomizationBatch,
        mask: np.ndarray,
    ) -> None: ...

    def reset_world_randomization(self, mask: np.ndarray) -> None: ...


class StaticTemplateWorkspaceProviderProtocol(Protocol):
    """Optional provider-owned reset workspace boundary."""

    def reset_workspace(self, mask: np.ndarray) -> None: ...


__all__ = [
    "StaticTemplateDeviceProviderProtocol",
    "StaticTemplateProviderProtocol",
    "StaticTemplateRandomizationProviderProtocol",
    "StaticTemplateWorkspaceProviderProtocol",
]
