"""Robot Scene imports must own every dependency in their declared roots."""

from types import SimpleNamespace

import pytest

from task_env.assembly.assets import _source_closure_digest
from task_env.runtime.sessions.source_scene_import import import_agent_source_scene


def test_scene_import_hashes_dependencies_from_each_declared_root(tmp_path, monkeypatch):
    import scene

    first = tmp_path / 'model'
    second = tmp_path / 'meshes'
    first.mkdir()
    second.mkdir()
    source = first / 'model.xml'
    mesh = second / 'part.stl'
    source.write_text('<mujoco/>')
    mesh.write_bytes(b'mesh bytes')
    manifest = SimpleNamespace(owner_uid='robot', mjcf_sources=(source,),
                               asset_roots=(first, second), source_revision='r1')
    imported = SimpleNamespace(dependency_paths=(source, mesh))
    monkeypatch.setattr(scene, 'import_scene_source', lambda *args, **kwargs: imported)
    def declare():
        return import_agent_source_scene(manifest, owner_uid='robot', entity_id='robot',
            scene_id='scene', scene_factory=lambda _imported, _manifest, **kw: kw)

    value = declare()
    assert value['source_content_sha256'] == _source_closure_digest({
        'model.xml': source.read_bytes(), 'root-1/part.stl': mesh.read_bytes()})
    mesh.write_bytes(b'changed mesh bytes')
    assert declare()['source_content_sha256'] != value['source_content_sha256']

    outside = tmp_path / 'outside.stl'
    outside.write_bytes(b'outside')
    imported.dependency_paths = (source, outside)
    with pytest.raises(ValueError, match='escaped'):
        declare()
    with pytest.raises(ValueError, match='owned MJCF'):
        import_agent_source_scene(manifest, owner_uid='other', entity_id='robot',
                                  scene_id='scene', scene_factory=lambda *a, **kw: kw)

    collision = first / 'root-1' / 'part.stl'
    collision.parent.mkdir()
    collision.write_bytes(mesh.read_bytes())
    imported.dependency_paths = (source, mesh, collision)
    with pytest.raises(ValueError, match='conflicting logical paths'):
        declare()
