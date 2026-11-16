"""MuJoCo VFS lowering keeps distinct source assets with colliding basenames."""
import xml.etree.ElementTree as ET
import pytest
from task_env.runtime.sessions.mujoco import _lower_mjcf_vfs_assets


def test_flat_vfs_aliases_preserve_distinct_receipt_assets():
    xml = '<mujoco><asset><texture file="a/metal.png"/><texture file="b/metal.png"/></asset></mujoco>'
    lowered, assets, rows = _lower_mjcf_vfs_assets(xml, {'a/metal.png': b'a', 'b/metal.png': b'b'})
    names = [node.get('file') for node in ET.fromstring(lowered).findall('./asset/texture')]
    assert len(set(names)) == 2
    assert [assets[name] for name in names] == [b'a', b'b']
    assert [row['source_path'] for row in rows] == ['a/metal.png', 'b/metal.png']


def test_vfs_rejects_unbound_asset_and_closure_extras():
    xml = '<mujoco><asset><texture file="a/metal.png"/></asset></mujoco>'
    with pytest.raises(ValueError, match='missing'):
        _lower_mjcf_vfs_assets(xml, {'b/metal.png': b'b'})
    with pytest.raises(ValueError, match='unreferenced'):
        _lower_mjcf_vfs_assets(xml, {'a/metal.png': b'a', 'b/metal.png': b'b'})


def test_alias_preserves_implicit_mujoco_mesh_name():
    xml = '<mujoco><asset><mesh file="models/link0_0.stl"/></asset></mujoco>'
    lowered, assets, _ = _lower_mjcf_vfs_assets(xml, {'models/link0_0.stl': b'mesh'})
    mesh = ET.fromstring(lowered).find('./asset/mesh')
    assert mesh.get('name') == 'link0_0'
    assert assets[mesh.get('file')] == b'mesh'
