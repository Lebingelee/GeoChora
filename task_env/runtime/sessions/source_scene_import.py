"""Source-import adapter for a pinned agent Scene declaration.

The caller supplies Robot-owned semantic projection; this adapter owns source
parsing and closure collection and never creates a physics runtime.
"""
from pathlib import Path


def import_agent_source_scene(manifest, *, owner_uid, entity_id, scene_id, scene_factory):
    if len(manifest.mjcf_sources) != 1 or len(manifest.asset_roots) != 1:
        raise ValueError('Agent Scene construction requires one declared MJCF root')
    from scene import SceneSource, import_scene_source
    from ...assembly.assets import _source_closure_digest
    imported = import_scene_source(
        SceneSource.mjcf_path(manifest.mjcf_sources[0], label=f'{owner_uid}:{manifest.source_revision}'),
        cache=False,
    )
    root = manifest.asset_roots[0].resolve(strict=True)
    files = {}
    for raw in imported.dependency_paths:
        path = Path(raw).resolve(strict=True)
        try:
            logical = path.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError('Agent importer dependency escaped its declared asset root') from exc
        files[logical] = path.read_bytes()
    if not files:
        raise ValueError('Agent importer returned an empty source closure')
    return scene_factory(imported, manifest, entity_id=entity_id, scene_id=scene_id,
                         source_content_sha256=_source_closure_digest(files))
