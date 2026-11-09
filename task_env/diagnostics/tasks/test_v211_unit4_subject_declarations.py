"""Provider-free tests for bounded Panda declaration and nested bindings."""
from dataclasses import replace
import pytest
from task_env.artifacts import FrameReference, JointReference
from task_env.diagnostics.tasks.test_phase_ii_01_r01b_logical_resolution import (
    _scene_v3, _assembly, _entity_member, _sub, _nested,
)
from task_env.runtime.sessions.physical_control import (
    ControlledSubjectV1, SubjectJointDeclarationV1, compile_declared_subject_binding,
)


def test_two_nested_edges_reach_shared_binding_without_flattening():
    scene = _scene_v3()
    leaf = _assembly(scene, 'unit4-leaf', (_sub(('drive',), JointReference('arm', 'drive'), 'joint'),))
    middle = _assembly(scene, 'unit4-middle', (_nested(('module',), leaf),))
    root = _assembly(scene, 'unit4-root', (_entity_member('arm', path=('owner',)), _nested(('robot',), middle)))
    children = {(middle.assembly_id, middle.revision): middle, (leaf.assembly_id, leaf.revision): leaf}
    path = ('robot', 'module', 'drive')
    subject = ControlledSubjectV1('arm-subject', 'arm', 'source-a', 'b'*64,
        'references_existing', 'fixed', FrameReference('arm', 'base'), None, (path,), ('writer',))
    declaration = SubjectJointDeclarationV1(path, 'drive', ('writer',), 'drive', 'gear', 1., (-5., 5.), 'disabled')
    result = compile_declared_subject_binding(scene, 'a'*64, 'source-a', 'b'*64,
        root, children, (subject,), (declaration,))
    assert result.binding.channels[0].component_path == path
    with pytest.raises(ValueError):
        compile_declared_subject_binding(scene, 'a'*64, 'source-a', 'b'*64,
            root, children, (subject,), (replace(declaration, component_path=('robot', 'drive')),))
    with pytest.raises(ValueError):
        compile_declared_subject_binding(scene, 'a'*64, 'source-a', 'b'*64,
            root, children, (subject,), (replace(declaration, owner_ids=('foreign',)),))


def test_assembled_robot_declaration_has_two_sources_without_native_import():
    from task_env.registry import make_agent
    agent = make_agent('panda-arm-hand-v1')
    assert len(agent.asset_manifest().mjcf_sources) == 2
    assert len(agent.reference_spec().joint_names) == 9
    assert len(agent.reference_spec().actuator_names) == 8
    assert agent.supported_controller_kinds() == ()
    assert agent.selected_controller_profiles() == ('r1', 'r1_split')
