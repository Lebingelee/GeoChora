"""Backend contract smoke for the TaskEnv render boundary.

This provider-free diagnostic checks request forwarding through the real
backend adapters. Only native construction endpoints are substituted: the
raytracer has its own scene builder, while rasterizer/Flora delegate to the
source factory. No window, renderer, or physics runtime is allocated.

Run from the repository root::

    PYTHONPATH=GeoPhys/src:. python -m task_env.diagnostics.render.backend_contract
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from types import ModuleType
from unittest.mock import patch

from task_env.render import (
    RenderProcessor,
    available_render_backends,
)


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class _RenderConfig:
    backend: str
    width: int = 320
    height: int = 240
    render_preset: str = "interactive"


class _FakeSceneSource:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def build_visualizer(self, **kwargs):
        self.calls.append(dict(kwargs))
        return {"backend": kwargs["backend"], "kwargs": dict(kwargs)}


def run_backend_contract_smoke() -> dict[str, object]:
    descriptors = available_render_backends()
    names = tuple(item.name for item in descriptors)
    expected = ("raytracer", "rasterizer", "flora")
    if names != expected:
        raise AssertionError(f"unexpected TaskEnv backend order: {names!r}")

    calls: dict[str, dict[str, object]] = {}
    for backend_name in expected:
        source = _FakeSceneSource()
        raytracer_calls = []
        registrations = []
        scene = ModuleType("task_env.render.raytracer.scene")

        def build_raytracer(prepared_source, *, visualizer_kwargs):
            if prepared_source is not source:
                raise AssertionError("raytracer lost the prepared source")
            raytracer_calls.append(dict(visualizer_kwargs))
            return {"backend": "raytracer", "kwargs": dict(visualizer_kwargs)}

        scene.build_raytracer_visualizer = build_raytracer
        visualization = ModuleType("visualization")
        visualization.__path__ = []
        flora = ModuleType("visualization.flora")
        flora.register_flora_backend = lambda: registrations.append("flora")
        with patch.dict("sys.modules", {
            scene.__name__: scene,
            visualization.__name__: visualization,
            flora.__name__: flora,
        }):
            processor = RenderProcessor(_RenderConfig(backend=backend_name))
            if registrations:
                raise AssertionError("Flora registered before visualizer construction")
            visualizer = processor.build_visualizer(source)
        if backend_name == "raytracer":
            if source.calls or len(raytracer_calls) != 1:
                raise AssertionError("raytracer must use its scene builder exactly once")
            call = {"backend": "raytracer", **raytracer_calls[0]}
        else:
            if len(source.calls) != 1 or raytracer_calls:
                raise AssertionError(f"backend {backend_name!r} must use its source factory once")
            call = source.calls[0]
        if registrations != (["flora"] if backend_name == "flora" else []):
            raise AssertionError("unexpected Flora registration count")
        if visualizer["backend"] != backend_name:
            raise AssertionError(
                f"backend {backend_name!r} was not passed to the scene source"
            )
        for field, expected_value in (
            ("width", 320),
            ("height", 240),
            ("render_preset", "interactive"),
            ("render_preset_overrides", None),
            ("use_render_snapshot", None),
            ("render_snapshot_consumer", "slot"),
        ):
            if call[field] != expected_value:
                raise AssertionError(
                    f"backend {backend_name!r} lost common field {field!r}"
                )
        calls[backend_name] = call

    result = {
        "schema": "task_env.render_backend_contract_smoke.v1",
        "backends": list(names),
        "source_calls": {
            name: {
                "backend": call["backend"],
                "width": call["width"],
                "height": call["height"],
            }
            for name, call in calls.items()
        },
    }
    LOGGER.info("TaskEnv render backend contract smoke passed: %s", result)
    return result


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    run_backend_contract_smoke()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
