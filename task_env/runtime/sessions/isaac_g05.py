"""G05 source-bound Isaac USD source construction.

This module owns only the representation/source admission facts for the
unit-5 simple-effort route.  It does not start Isaac or perform physics.
"""
from __future__ import annotations

from pathlib import Path

from ...artifacts import TaskArtifactV1, SceneDefinition
from ...assembly.usd_delivery import (
    LoadedUsdDeliveryV1, load_usd_asset_delivery,
)
from .source import UsdRuntimeSourceV1, build_usd_runtime_source


G05_ISAAC_EFFORT_PROFILE = 'isaac-gpu-physx-g05-5c-effort-v1'
G05_ISAAC_BUILD_IDENTITY = 'isaacsim-6.2.0.0'


def load_g05_isaac_delivery(manifest_path: str | Path) -> LoadedUsdDeliveryV1:
    """Load the exact local derived delivery used by a G05 task."""
    loaded = load_usd_asset_delivery(manifest_path)
    _validate_g05_isaac_delivery(loaded)
    return loaded


def _validate_g05_isaac_delivery(loaded):
    if type(loaded) is not LoadedUsdDeliveryV1:
        raise TypeError('G05 Isaac requires a verified USD delivery')
    if (not loaded.locally_validated or loaded.source_verified
            or loaded.delivery.representation_format != 'usd'):
        raise ValueError('G05 Isaac requires a locally validated, non-upstream USD delivery')
    if loaded.delivery.representation_id != 'isaacsim-6.2.0.0-g05-mjcf-v1':
        raise ValueError('G05 Isaac delivery representation is not the reviewed 6.2 MJCF route')


def _usd_articulation_bodies(articulation, body_names):
    """Lower declared articulation frames to the admitted USD hierarchy."""
    paths = {articulation.root_frame_id: f'Geometry/{articulation.root_frame_id}'}
    remaining = list(articulation.joints)
    while remaining:
        ready = [joint for joint in remaining if joint.parent_frame.frame_id in paths]
        if not ready:
            raise ValueError('subject articulation cannot resolve USD body paths')
        for joint in ready:
            paths[joint.child_frame.frame_id] = paths[joint.parent_frame.frame_id] + '/' + joint.child_frame.frame_id
            remaining.remove(joint)
    return {key: paths[name] for key, name in body_names.items()}


def build_g05_isaac_runtime_source(*, delivery: LoadedUsdDeliveryV1,
                                   artifact: TaskArtifactV1,
                                   scene: SceneDefinition,
                                   task_source_identity_sha256: str,
                                   joints: dict[str, str],
                                   articulation,
                                   body_names: dict[str, str],
                                   frames: dict[str, str] | None = None,
                                   free_joints: dict[str, str] | None = None,
                                   joint_targets: dict[str, str] | None = None) -> UsdRuntimeSourceV1:
    """Bind one task artifact/scene to the reviewed local Isaac USD delivery."""
    if type(artifact) is not TaskArtifactV1 or type(scene) is not SceneDefinition:
        raise TypeError('G05 Isaac source requires exact TaskArtifactV1 and SceneDefinition')
    _validate_g05_isaac_delivery(delivery)
    loaded = delivery
    asset = loaded.delivery.asset_definition
    declared = {(item.asset_id, item.asset_version): item for item in scene.assets}
    if declared.get((asset.asset_id, asset.asset_version)) != asset:
        raise ValueError('G05 USD delivery AssetDefinition differs from the task Scene asset')
    source = build_usd_runtime_source(loaded=loaded, provider='isaacsim',
        provider_build_identity=G05_ISAAC_BUILD_IDENTITY,
        options={'task_route': 'g05-5c-simple-effort-v1'},
        task_source_identity_sha256=task_source_identity_sha256, artifact=artifact, scene=scene,
        joints=joints, bodies=_usd_articulation_bodies(articulation, body_names),
        frames=frames or {}, free_joints=free_joints or {},
        joint_targets=joint_targets if joint_targets is not None else joints)
    source.validate()
    return source


__all__ = [
    'G05_ISAAC_BUILD_IDENTITY', 'G05_ISAAC_EFFORT_PROFILE',
    'build_g05_isaac_runtime_source', 'load_g05_isaac_delivery',
]
