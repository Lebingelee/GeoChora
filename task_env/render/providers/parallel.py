"""Renderer-agnostic contracts for parallel TaskEnv world selection.

P2-S18a owns selection and layout only. A concrete static-template or
merged-scene source supplies the actual frame in a later backend stage; this
module never reads physics fields or creates one solver per world.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite
from typing import Protocol, Sequence

import numpy as np

from ..base.contracts import RenderMode, RenderUnavailableError, normalize_render_mode


@dataclass(frozen=True)
class ParallelRenderLayout:
    """Pure grid transform configuration for selected parallel worlds."""

    cell_width: float = 4.0
    cell_depth: float = 4.0
    columns: int = 4
    padding: float = 0.5

    def __post_init__(self) -> None:
        for name in ("cell_width", "cell_depth", "padding"):
            value = float(getattr(self, name))
            if not isfinite(value):
                raise ValueError(f"parallel render {name} must be finite")
            if name != "padding" and value <= 0.0:
                raise ValueError(f"parallel render {name} must be positive")
            if name == "padding" and value < 0.0:
                raise ValueError("parallel render padding must be non-negative")
            object.__setattr__(self, name, value)
        if isinstance(self.columns, bool) or not isinstance(
            self.columns, (int, np.integer)
        ):
            raise ValueError("parallel render columns must be an integer")
        columns = int(self.columns)
        if columns < 1:
            raise ValueError("parallel render columns must be positive")
        object.__setattr__(self, "columns", columns)

    def grid_shape(self, count: int) -> tuple[int, int]:
        world_count = int(count)
        if world_count < 1:
            raise ValueError("parallel render world count must be positive")
        columns = min(self.columns, world_count)
        return columns, int(ceil(world_count / columns))

    def transform_for(self, ordinal: int, count: int) -> tuple[float, ...]:
        """Return a row-major 4x4 world-to-cell translation transform."""

        world_count = int(count)
        index = int(ordinal)
        columns, rows = self.grid_shape(world_count)
        if index < 0 or index >= world_count:
            raise IndexError("parallel render ordinal is outside the selected grid")
        column = index % columns
        row = index // columns
        x = (column - 0.5 * (columns - 1)) * (self.cell_width + self.padding)
        y = (row - 0.5 * (rows - 1)) * (self.cell_depth + self.padding)
        return (
            1.0, 0.0, 0.0, float(x),
            0.0, 1.0, 0.0, float(y),
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        )

    def transforms_for(
        self,
        world_ids: Sequence[int],
    ) -> tuple[tuple[float, ...], ...]:
        selected = tuple(int(world_id) for world_id in world_ids)
        return tuple(
            self.transform_for(ordinal, len(selected))
            for ordinal in range(len(selected))
        )

    def describe(self) -> dict[str, object]:
        return {
            "cell_width": float(self.cell_width),
            "cell_depth": float(self.cell_depth),
            "columns": int(self.columns),
            "padding": float(self.padding),
            "transform_space": "renderer_world_translation",
        }


class ParallelRenderSourceProtocol(Protocol):
    """Backend boundary consumed by :class:`ParallelRenderProvider`."""

    def set_parallel_render_hard(self, enabled: bool) -> None:
        """Select the bounded asset path instead of primitive geometry."""

    def set_parallel_render_budget_bypass(self, enabled: bool) -> None:
        """Enable an explicit diagnostic bypass of render budget preflight."""

    def render_parallel(
        self,
        *,
        world_ids: tuple[int, ...],
        world_transforms: tuple[tuple[float, ...], ...],
        snapshot: object,
        width: int,
        height: int,
    ) -> np.ndarray:
        """Render only the selected worlds into one grid scene."""

    def present_parallel(
        self,
        *,
        frame: np.ndarray,
        world_ids: tuple[int, ...],
        world_transforms: tuple[tuple[float, ...], ...],
    ) -> None:
        """Present one already rendered parallel frame in human mode."""

    def set_render_control_keys(self, *, toggle: str, disable: str) -> None:
        """Configure training-window-only input bindings."""

    def poll_render_events(self) -> dict[str, bool]:
        """Pump the headed window without rendering a frame."""

    def consume_render_events(self) -> dict[str, bool]:
        """Consume events captured while rendering the latest frame."""


class ParallelRenderProvider:
    """Own parallel selection/layout without owning physics or solver state."""

    def __init__(
        self,
        *,
        num_envs: int,
        render_source: ParallelRenderSourceProtocol | None = None,
        width: int = 640,
        height: int = 480,
        layout: ParallelRenderLayout | None = None,
    ) -> None:
        if isinstance(num_envs, bool) or not isinstance(num_envs, (int, np.integer)):
            raise ValueError("parallel render num_envs must be an integer")
        total = int(num_envs)
        if total < 1:
            raise ValueError("parallel render num_envs must be positive")
        if int(width) < 1 or int(height) < 1:
            raise ValueError("parallel render width and height must be positive")
        self.num_envs = total
        self.width = int(width)
        self.height = int(height)
        self.layout = layout or ParallelRenderLayout()
        self._render_source = render_source
        self._parallel_render_num = 1
        self._closed = False

    @property
    def parallel_render_num(self) -> int:
        return int(self._parallel_render_num)

    @property
    def world_ids(self) -> tuple[int, ...]:
        return tuple(range(self._parallel_render_num))

    @property
    def world_transforms(self) -> tuple[tuple[float, ...], ...]:
        return self.layout.transforms_for(self.world_ids)

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("parallel render provider is closed")

    def _require_source(self) -> ParallelRenderSourceProtocol:
        self._require_open()
        source = self._render_source
        if source is None or not callable(getattr(source, "render_parallel", None)):
            raise RenderUnavailableError(
                "parallel rendering has no static-template/merged-scene render source"
            )
        return source

    def set_parallel_render_num(self, count: int) -> None:
        if isinstance(count, bool) or not isinstance(count, (int, np.integer)):
            raise ValueError("parallel_render_num must be an integer")
        value = int(count)
        if value < 1 or value > self.num_envs:
            raise ValueError(
                "parallel_render_num must satisfy 1 <= parallel_render_num <= num_envs"
            )
        self._parallel_render_num = value
        source = self._render_source
        set_count = getattr(source, "set_parallel_render_num", None)
        if callable(set_count):
            set_count(value)

    def set_parallel_render_hard(self, enabled: bool) -> None:
        source = self._render_source
        setter = getattr(source, "set_parallel_render_hard", None)
        if callable(setter):
            setter(bool(enabled))

    def set_parallel_render_budget_bypass(self, enabled: bool) -> None:
        source = self._render_source
        setter = getattr(source, "set_parallel_render_budget_bypass", None)
        if callable(setter):
            setter(bool(enabled))

    def set_parallel_render_layout(
        self,
        *,
        cell_width: float | None = None,
        cell_depth: float | None = None,
        columns: int | None = None,
        padding: float | None = None,
    ) -> None:
        self.layout = ParallelRenderLayout(
            cell_width=self.layout.cell_width if cell_width is None else cell_width,
            cell_depth=self.layout.cell_depth if cell_depth is None else cell_depth,
            columns=self.layout.columns if columns is None else columns,
            padding=self.layout.padding if padding is None else padding,
        )
        source = self._render_source
        set_layout = getattr(source, "set_parallel_render_layout", None)
        if callable(set_layout):
            set_layout()

    def set_render_control_keys(self, *, toggle: str, disable: str) -> None:
        """Set keys used by the optional training render controller."""

        source = self._render_source
        setter = getattr(source, "set_render_control_keys", None)
        if callable(setter):
            setter(toggle=str(toggle), disable=str(disable))

    def poll_render_events(self) -> dict[str, bool]:
        """Pump renderer input without acquiring a physics snapshot."""

        self._require_open()
        source = self._render_source
        poll = getattr(source, "poll_render_events", None)
        if not callable(poll):
            return {"running": True, "toggle": False, "disable": False}
        result = poll()
        return {
            "running": bool(getattr(result, "running", result.get("running", True) if isinstance(result, dict) else True)),
            "toggle": bool(getattr(result, "toggle", result.get("toggle", False) if isinstance(result, dict) else False)),
            "disable": bool(getattr(result, "disable", result.get("disable", False) if isinstance(result, dict) else False)),
        }

    def consume_render_events(self) -> dict[str, bool]:
        """Return input events captured by the most recent human frame."""

        self._require_open()
        source = self._render_source
        consume = getattr(source, "consume_render_events", None)
        if not callable(consume):
            return {"running": True, "toggle": False, "disable": False}
        result = consume()
        if isinstance(result, dict):
            return {
                "running": bool(result.get("running", True)),
                "toggle": bool(result.get("toggle", False)),
                "disable": bool(result.get("disable", False)),
            }
        return {
            "running": bool(getattr(result, "running", True)),
            "toggle": bool(getattr(result, "toggle", False)),
            "disable": bool(getattr(result, "disable", False)),
        }

    def render(
        self,
        *,
        mode: RenderMode | str,
        snapshot: object = None,
    ) -> np.ndarray | None:
        normalized = normalize_render_mode(mode)
        source = self._require_source()
        world_ids = self.world_ids
        world_transforms = self.world_transforms
        set_mode = getattr(source, "set_parallel_render_mode", None)
        if callable(set_mode):
            set_mode(normalized)
        frame = source.render_parallel(
            world_ids=world_ids,
            world_transforms=world_transforms,
            snapshot=snapshot,
            width=self.width,
            height=self.height,
        )
        frame = np.asarray(frame, dtype=np.float32)
        expected = (self.height, self.width, 3)
        if frame.shape != expected:
            raise RuntimeError(
                "parallel renderer returned an unexpected frame shape: "
                f"expected {expected}, got {frame.shape}"
            )
        if not np.isfinite(frame).all():
            raise RuntimeError("parallel renderer returned non-finite pixels")
        frame = np.ascontiguousarray(np.clip(frame, 0.0, 1.0), dtype=np.float32)
        if normalized is RenderMode.RGB_ARRAY:
            return frame
        present = getattr(source, "present_parallel", None)
        if not callable(present):
            raise RenderUnavailableError(
                "parallel render source does not expose headed presentation"
            )
        present(
            frame=frame,
            world_ids=world_ids,
            world_transforms=world_transforms,
        )
        return None

    def describe(self) -> dict[str, object]:
        report = {
            "schema": "task_env.parallel_render.v1",
            "num_envs": int(self.num_envs),
            "parallel_render_num": int(self.parallel_render_num),
            "world_ids": list(self.world_ids),
            "layout": self.layout.describe(),
            "source_attached": self._render_source is not None,
        }
        read_metrics = getattr(self._render_source, "read_metrics", None)
        if callable(read_metrics):
            report["metrics"] = dict(read_metrics())
        return report

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        close = getattr(self._render_source, "close", None)
        if callable(close):
            close()

    def close_render(self) -> None:
        """Close only renderer-owned resources; keep the physics runtime alive."""

        self.close()


__all__ = [
    "ParallelRenderLayout",
    "ParallelRenderProvider",
    "ParallelRenderSourceProtocol",
]
