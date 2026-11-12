"""Source-import adapter for a pinned agent Scene declaration.

The caller supplies Robot-owned semantic projection; this adapter owns source
parsing and closure collection and never creates a physics runtime.
"""
from pathlib import Path
import xml.etree.ElementTree as ET


def validate_declared_effort_transmissions(xml, declarations):
    """Verify MJCF motor mappings against the Robot's effort transmissions."""
    root = ET.fromstring(xml)
    section = root.find('./actuator')
    motors = root.findall('./actuator/motor')
    if section is None or len(section) != len(declarations) or len(motors) != len(declarations):
        raise ValueError('source motor count differs from Robot transmission declaration')
    for motor, declaration in zip(motors, declarations, strict=True):
        try:
            limits = tuple(float(value) for value in motor.get('ctrlrange', '').split())
            gear = float(motor.get('gear', ''))
        except ValueError as exc:
            raise ValueError('source motor transmission is invalid') from exc
        if (motor.get('name') != declaration.native_actuator
                or motor.get('joint') != declaration.joint_id
                or gear != declaration.transmission_coefficient
                or motor.get('ctrllimited') != 'true'
                or limits != declaration.native_range):
            raise ValueError('source motor transmission differs from Robot declaration')


def import_agent_source_scene(manifest, *, owner_uid, entity_id, scene_id, scene_factory):
    if manifest.owner_uid != owner_uid or len(manifest.mjcf_sources) != 1 or not manifest.asset_roots:
        raise ValueError('Agent Scene construction requires an owned MJCF source and asset roots')
    roots = tuple(path.resolve(strict=True) for path in manifest.asset_roots)
    if not any(manifest.mjcf_sources[0].resolve(strict=True).is_relative_to(root) for root in roots):
        raise ValueError('Agent MJCF source is outside its declared asset roots')
    from scene import SceneSource, import_scene_source
    from ...assembly.assets import _source_closure_digest
    imported = import_scene_source(
        SceneSource.mjcf_path(manifest.mjcf_sources[0], label=f'{owner_uid}:{manifest.source_revision}'),
        cache=False,
    )
    files = {}
    logical_paths = {}
    for raw in imported.dependency_paths:
        path = Path(raw).resolve(strict=True)
        matches = [(index, root) for index, root in enumerate(roots) if path.is_relative_to(root)]
        if not matches:
            raise ValueError('Agent importer dependency escaped its declared asset roots')
        index, root = matches[0]
        relative = path.relative_to(root).as_posix()
        logical = relative if index == 0 else f'root-{index}/{relative}'
        data = path.read_bytes()
        if logical in logical_paths and logical_paths[logical] != path:
            raise ValueError('Agent importer dependencies have conflicting logical paths')
        files[logical] = data
        logical_paths[logical] = path
    if not files:
        raise ValueError('Agent importer returned an empty source closure')
    return scene_factory(imported, manifest, entity_id=entity_id, scene_id=scene_id,
                         source_content_sha256=_source_closure_digest(files))


def declare_panda_scene(agent, *, entity_id=None, scene_id=None):
    """Build the provider-neutral Panda Scene declaration from its pinned source."""
    from ...robots.panda import _panda_scene_from_import
    return import_agent_source_scene(
        agent.asset_manifest(), owner_uid=agent.uid,
        entity_id=agent.uid if entity_id is None else entity_id,
        scene_id=agent.uid if scene_id is None else scene_id,
        scene_factory=_panda_scene_from_import,
    )
