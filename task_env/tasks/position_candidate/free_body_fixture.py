"""Versioned, collision-free free-body fixture composed through the existing Scene owner."""
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET

from ...artifacts import SceneDefinition
from .source import _a05_scene

_FIXTURE = Path(__file__).with_name('assets') / 'v211_4b_free_body.xml'
_FIXTURE_SHA256 = '5a62dac869f69e982b754d33daadc8f757d7f6266e178d77d1d25f708bb622cf'


def fixture_scene():
    raw = _FIXTURE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != _FIXTURE_SHA256:
        raise ValueError('free-body fixture bytes differ from the versioned declaration')
    mapping = _a05_scene().to_mapping()
    mapping['scene_id'] = 'panda-free-body-point-wrench-v1'
    mapping['assets'].append({'schema_version': 'asset-definition-v1', 'asset_id': 'v211-free-body-v1',
        'asset_version': 'v1', 'license_id': None, 'source_content_sha256': _FIXTURE_SHA256,
        'source_reference': 'geochora-task-scene://v211/free-body', 'source_revision': 'v1'})
    mapping['entities'].append({'schema_version': 'entity-instance-v1', 'entity_id': 'probe',
        'asset_id': 'v211-free-body-v1', 'asset_version': 'v1'})
    mapping['frames'].extend([
        {'schema_version': 'frame-definition-v1', 'entity_id': 'probe', 'frame_id': name,
         'frame_kind': 'runtime', 'parent': None, 'pose_parent': None}
        for name in ('world', 'probe_body')])
    identity = {'position': [0., 0., 0.], 'quaternion_wxyz': [1., 0., 0., 0.]}
    mapping['articulations'].append({'schema_version': 'articulation-definition-v1', 'entity_id': 'probe',
        'root_frame_id': 'world', 'link_frame_ids': ['world', 'probe_body'], 'joints': [{
            'schema_version': 'joint-definition-v1', 'joint_id': 'probe_free',
            'parent_frame': {'entity_id': 'probe', 'frame_id': 'world'},
            'child_frame': {'entity_id': 'probe', 'frame_id': 'probe_body'},
            'pose_parent_from_joint': identity, 'pose_child_from_joint': identity,
            'kind': 'floating', 'axis': None, 'position_representation': 'xyz_meter_quaternion_wxyz',
            'velocity_representation': 'linear_xyz_meter_per_second_angular_xyz_radian_per_second',
            'position_size': 7, 'velocity_size': 6}]})
    return SceneDefinition.from_mapping(mapping)


def compose_fixture_xml(xml):
    """Compose immutable fixture bytes before the Scene source is projected and hashed."""
    raw = _FIXTURE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != _FIXTURE_SHA256:
        raise ValueError('free-body fixture bytes changed')
    root = ET.fromstring(xml)
    option = root.find('option')
    if option is None:
        option = ET.SubElement(root, 'option')
    option.set('gravity', '0 0 0')
    option.set('integrator', 'implicitfast')
    fixture = ET.fromstring(raw)
    root.find('worldbody').append(fixture.find('./worldbody/body'))
    return ET.tostring(root, encoding='unicode')
