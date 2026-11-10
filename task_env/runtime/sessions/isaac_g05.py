"""G05 source-bound Isaac USD source construction.

This module owns only the representation/source admission facts for the
unit-5 simple-effort route.  It does not start Isaac or perform physics.
"""
from __future__ import annotations

from pathlib import Path

from ...artifacts import TaskArtifactV1, SceneDefinition
from ...assembly.source import UsdTaskSceneSourceV1
from ...assembly.usd_delivery import (
    LoadedUsdDeliveryV1, load_usd_asset_delivery, resolve_provider_representation,
)
from .source import UsdRuntimeSourceV1


G05_ISAAC_EFFORT_PROFILE = 'isaac-gpu-physx-g05-5c-effort-v1'
G05_ISAAC_BUILD_IDENTITY = 'isaacsim-6.2.0.0'


def ensure_g05_isaac_app_open() -> object:
    """Open the process-owned Isaac App before G05 USD inspection.

    The G05 source loader is intentionally still responsible for the complete
    Core/USD closure and its source identity.  This helper only moves the
    existing process App owner ahead of that check so Kit's USD libraries are
    established before any ``pxr`` import.  The owner is the same singleton
    later consumed by native materialization; this function never constructs a
    second App owner.
    """
    from .isaac_native_io import _process_app_owner

    owner = _process_app_owner()
    owner.open()
    return owner


def load_g05_isaac_delivery(manifest_path: str | Path) -> LoadedUsdDeliveryV1:
    """Load the exact local derived delivery used by a G05 task."""
    loaded = load_usd_asset_delivery(manifest_path)
    if (not loaded.locally_validated or loaded.source_verified
            or loaded.delivery.representation_format != 'usd'):
        raise ValueError('G05 Isaac requires a locally validated, non-upstream USD delivery')
    if loaded.delivery.representation_id != 'isaacsim-6.2.0.0-g05-mjcf-v1':
        raise ValueError('G05 Isaac delivery representation is not the reviewed 6.2 MJCF route')
    return loaded


def build_g05_isaac_runtime_source(*, manifest_path: str | Path,
                                   artifact: TaskArtifactV1,
                                   scene: SceneDefinition,
                                   task_source_identity_sha256: str,
                                   joints: dict[str, str],
                                   bodies: dict[str, str],
                                   frames: dict[str, str] | None = None,
                                   free_joints: dict[str, str] | None = None,
                                   joint_targets: dict[str, str] | None = None) -> UsdRuntimeSourceV1:
    """Bind one task artifact/scene to the reviewed local Isaac USD delivery."""
    if type(artifact) is not TaskArtifactV1 or type(scene) is not SceneDefinition:
        raise TypeError('G05 Isaac source requires exact TaskArtifactV1 and SceneDefinition')
    loaded = load_g05_isaac_delivery(manifest_path)
    asset = loaded.delivery.asset_definition
    declared = {(item.asset_id, item.asset_version): item for item in scene.assets}
    if declared.get((asset.asset_id, asset.asset_version)) != asset:
        raise ValueError('G05 USD delivery AssetDefinition differs from the task Scene asset')
    representation = resolve_provider_representation(
        loaded,
        provider='isaacsim',
        provider_build_identity=G05_ISAAC_BUILD_IDENTITY,
        options={'task_route': 'g05-5c-simple-effort-v1'},
    )
    scene_source = UsdTaskSceneSourceV1(
        'usd-task-scene-source-v1', loaded, representation,
        task_source_identity_sha256, scene.identity_hash,
    )
    source = UsdRuntimeSourceV1(
        'usd-runtime-source-v1', artifact, scene, scene_source,
        joints, bodies, frames or {}, free_joints or {},
        joint_targets if joint_targets is not None else joints,
    )
    source.validate()
    return source


__all__ = [
    'G05_ISAAC_BUILD_IDENTITY', 'G05_ISAAC_EFFORT_PROFILE',
    'ensure_g05_isaac_app_open',
    'build_g05_isaac_runtime_source', 'load_g05_isaac_delivery',
]
