"""Focused regressions for selected MJCF capture and real named bindings."""
from dataclasses import replace
import xml.etree.ElementTree as ET

import pytest


def test_missing_referenced_mesh_fails_before_materialization():
    from task_env import make_env
    from task_env.runtime.sessions.source import snapshot_legacy_mjcf_source
    env = make_env('pick-cube-p16-reference-v1', config={'provider': 'mujoco'})
    try:
        original = env.value['source']
        root = ET.fromstring(original.scene_source.xml)
        next(node for node in root.iter('mesh') if node.get('file')).set('file', 'absent-mesh-for-test.obj')
        scene_source = replace(original.scene_source, xml=ET.tostring(root, encoding='unicode'))
        changed = replace(original, scene_source=scene_source, source_closure_digest=None,
                          execution_source_receipt=None)
        with pytest.raises(ValueError, match='asset is missing'):
            snapshot_legacy_mjcf_source(changed)
    finally:
        env.close()


def test_actual_named_actuator_and_frame_are_checked():
    from task_env import make_env
    from task_env.runtime.sessions.api import assess_selected_request
    env = make_env('pick-cube-p16-reference-v1', config={'provider': 'mujoco'})
    try:
        original = env.value['source']
        for changed in (replace(original, joint_targets={**original.joint_targets,
                                next(iter(original.joint_targets)): 'absent-actuator'}),
                        replace(original, frames={**original.frames,
                                next(iter(original.frames)): 'absent-frame'})):
            value = {**env.value, 'source': changed}
            assessed = assess_selected_request(
                selection=env.resolved_public_config.execution_spec_v2,
                artifact=env.artifact, source=changed, value=value, binding=env.binding,
                dependency_status='available', request_identity='a' * 64)
            source = next(row for row in assessed.rows if row.capability_id == 'source_closure')
            assert source.requirement_status == 'unsatisfied'
            assert 'missing named' in source.reason
            assert assessed.decision == 'rejected'
    finally:
        env.close()
