"""TaskEnv RayTracer scene construction boundary."""

from __future__ import annotations

from typing import Mapping

from visualization.snapshot_source import create_scene_render_snapshot_binding

from ..base.contracts import RenderBackendBuildError
from .visualizer import RaytracerSceneVisualizer


def build_raytracer_visualizer(
    source: object,
    *,
    visualizer_kwargs: Mapping[str, object] | None = None,
) -> object:
    """Build the TaskEnv RayTracer visualizer with stable snapshot ownership.

    This mirrors only the internal-raytracer branch of the public scene-source
    factory.  It is intentionally kept here so the TaskEnv backend can select
    its visualizer subclass without modifying the frequently changing public
    ``src.visualization.scene_source`` factory.
    """

    kwargs = dict(visualizer_kwargs or {})
    kwargs.pop("backend", None)
    representation = kwargs.pop("representation", None)
    mpm_representation = kwargs.pop("mpm_representation", None)
    particle_representations = kwargs.pop("particle_representations", None)
    use_render_snapshot = kwargs.pop("use_render_snapshot", None)
    snapshot_consumer = str(
        kwargs.pop("render_snapshot_consumer", "slot")
    ).strip()

    apply_representation = getattr(source, "_apply_build_representation", None)
    if callable(apply_representation):
        apply_representation(representation)
    apply_mpm_representation = getattr(
        source,
        "_apply_mpm_build_representation",
        None,
    )
    if callable(apply_mpm_representation):
        apply_mpm_representation(mpm_representation)
    if particle_representations is not None:
        set_particle_representations = getattr(
            source,
            "set_particle_representations",
            None,
        )
        if not callable(set_particle_representations):
            raise RenderBackendBuildError(
                "RayTracer source does not support particle representations"
            )
        set_particle_representations(particle_representations)

    render_source = source
    snapshot_binding = None
    if use_render_snapshot is None:
        use_render_snapshot = True
    can_snapshot = getattr(source, "_can_use_render_snapshot", None)
    if bool(use_render_snapshot) and callable(can_snapshot) and can_snapshot():
        snapshot_binding = create_scene_render_snapshot_binding(
            source,
            consumer_mode=snapshot_consumer,
        )
        render_source = snapshot_binding.snapshot_source

    visualizer = RaytracerSceneVisualizer(render_source, **kwargs)
    if snapshot_binding is not None:
        set_publisher = getattr(
            visualizer,
            "set_render_snapshot_publisher",
            None,
        )
        if not callable(set_publisher):
            raise RenderBackendBuildError(
                "RayTracer visualizer does not accept render snapshots"
            )
        set_publisher(snapshot_binding.publisher)
    return visualizer


__all__ = ["build_raytracer_visualizer"]
