"""Common TaskEnv render request preparation and backend dispatch."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from ..base.backend import RenderBackend
from .backend_registry import create_render_backend, normalize_render_backend


@dataclass(frozen=True)
class RenderBuildRequest:
    """Immutable renderer construction inputs shared by all backends."""

    backend: str
    width: int
    height: int
    render_preset: str
    render_preset_overrides: Mapping[str, object] | None = None
    use_render_snapshot: bool | None = None
    render_snapshot_consumer: str = "slot"

    def __post_init__(self) -> None:
        if int(self.width) < 1 or int(self.height) < 1:
            raise ValueError("render width and height must be positive")
        if not str(self.render_preset).strip():
            raise ValueError("render_preset cannot be empty")
        if str(self.render_snapshot_consumer).strip() not in {
            "slot",
            "live",
        }:
            raise ValueError(
                "render_snapshot_consumer must be 'slot' or 'live'"
            )
        object.__setattr__(self, "backend", normalize_render_backend(self.backend))
        object.__setattr__(self, "width", int(self.width))
        object.__setattr__(self, "height", int(self.height))
        object.__setattr__(self, "render_preset", str(self.render_preset).strip())
        object.__setattr__(
            self,
            "render_snapshot_consumer",
            str(self.render_snapshot_consumer).strip(),
        )

    @classmethod
    def from_config(
        cls,
        config: object,
        *,
        backend: str | None = None,
        width: int | None = None,
        height: int | None = None,
        render_preset: str | None = None,
        render_preset_overrides: Mapping[str, object] | None = None,
        use_render_snapshot: bool | None = None,
        render_snapshot_consumer: str = "slot",
    ) -> "RenderBuildRequest":
        return cls(
            backend=str(
                backend
                if backend is not None
                else getattr(config, "backend", "raytracer")
            ),
            width=int(
                width if width is not None else getattr(config, "width", 640)
            ),
            height=int(
                height if height is not None else getattr(config, "height", 480)
            ),
            render_preset=str(
                render_preset
                if render_preset is not None
                else getattr(config, "render_preset", "interactive")
            ),
            render_preset_overrides=render_preset_overrides,
            use_render_snapshot=use_render_snapshot,
            render_snapshot_consumer=render_snapshot_consumer,
        )

    def with_overrides(self, **kwargs: object) -> "RenderBuildRequest":
        allowed = {
            "backend",
            "width",
            "height",
            "render_preset",
            "render_preset_overrides",
            "use_render_snapshot",
            "render_snapshot_consumer",
        }
        unknown = sorted(set(kwargs).difference(allowed))
        if unknown:
            raise TypeError(f"unknown render build request fields: {unknown}")
        return replace(self, **kwargs)

    def visualizer_kwargs(self) -> dict[str, object]:
        """Return only the stable common arguments accepted by source factories."""

        return {
            "width": self.width,
            "height": self.height,
            "render_preset": self.render_preset,
            "render_preset_overrides": self.render_preset_overrides,
            "use_render_snapshot": self.use_render_snapshot,
            "render_snapshot_consumer": self.render_snapshot_consumer,
        }

    def describe(self) -> dict[str, object]:
        return {
            "schema": "task_env.render_build_request.v1",
            "backend": self.backend,
            "width": self.width,
            "height": self.height,
            "render_preset": self.render_preset,
            "render_preset_overrides": (
                None
                if self.render_preset_overrides is None
                else dict(self.render_preset_overrides)
            ),
            "use_render_snapshot": self.use_render_snapshot,
            "render_snapshot_consumer": self.render_snapshot_consumer,
        }


class RenderProcessor:
    """Unified CPU-side render construction/lifecycle coordinator.

    It does not read solver fields or own frame buffers.  It only prepares a
    stable request, selects a TaskEnv backend implementation, and delegates
    scene construction to the existing ``src.visualization`` source.
    """

    def __init__(self, config: object, *, backend: str | None = None) -> None:
        self._request = RenderBuildRequest.from_config(config, backend=backend)
        self._backend: RenderBackend = create_render_backend(self._request.backend)

    @property
    def request(self) -> RenderBuildRequest:
        return self._request

    @property
    def backend(self) -> RenderBackend:
        return self._backend

    def build_visualizer(
        self,
        source: object,
        *,
        visualizer_kwargs: Mapping[str, object] | None = None,
        **request_overrides: object,
    ) -> object:
        request = self._request.with_overrides(**request_overrides)
        if request.backend != self._request.backend:
            backend = create_render_backend(request.backend)
        else:
            backend = self._backend
        return backend.create_visualizer(
            source,
            request=request,
            visualizer_kwargs=visualizer_kwargs,
        )

    def describe(self) -> dict[str, object]:
        return {
            "request": self._request.describe(),
            "backend": self._backend.descriptor.describe(),
        }


def build_task_visualizer(
    source: object,
    config: object,
    *,
    visualizer_kwargs: Mapping[str, object] | None = None,
    **request_overrides: object,
) -> object:
    """Convenience entry point for one-shot TaskEnv render construction."""

    return RenderProcessor(config).build_visualizer(
        source,
        visualizer_kwargs=visualizer_kwargs,
        **request_overrides,
    )


__all__ = [
    "RenderBuildRequest",
    "RenderProcessor",
    "build_task_visualizer",
]
