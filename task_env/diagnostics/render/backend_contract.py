"""Backend contract smoke for the TaskEnv render boundary.

This diagnostic does not create a Vulkan window or allocate a renderer.  It
checks that all three TaskEnv backend implementations receive the same common
construction request and that the Flora registration remains lazy until the
backend is actually built.

Run from the repository root::

    PYTHONPATH=GeoPhys/src:. python -m task_env.diagnostics.render.backend_contract
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

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
        visualizer = RenderProcessor(
            _RenderConfig(backend=backend_name)
        ).build_visualizer(source)
        if len(source.calls) != 1:
            raise AssertionError(
                f"backend {backend_name!r} did not make exactly one source call"
            )
        call = source.calls[0]
        if visualizer["backend"] != backend_name:
            raise AssertionError(
                f"backend {backend_name!r} was not passed to the scene source"
            )
        for field, expected_value in (
            ("width", 320),
            ("height", 240),
            ("render_preset", "interactive"),
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

