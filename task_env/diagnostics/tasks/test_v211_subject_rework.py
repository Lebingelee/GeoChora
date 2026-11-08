"""Provider-free detectors for the phase-1 independent review findings."""
from dataclasses import replace
from types import SimpleNamespace
import json
import math
from pathlib import Path

import numpy as np
import pytest
from gymnasium.spaces import Box, Dict

from task_env.artifacts import FrameReference, JointReference, PoseWorld
from task_env.artifacts.state import StateRequirements
from task_env.diagnostics.tasks.test_v211_physical_control_contract import _case
from task_env.diagnostics.tasks.test_phase_ii_01_r01b_logical_resolution import (
    _scene_v3, _assembly, _entity_member, _sub,
)
from task_env.runtime.sessions.physical_control import (
    ControlledSubjectV1, PhysicalControlExecutionV1, SubjectJointDeclarationV1,
    compile_declared_subject_binding,
)


def _declaration_case(nested):
    old, _, _, _ = _case()
    scene = _scene_v3()
    if nested:
        root, children = old.root, old.children
        path = ('robot', 'arm-drive-joint')
    else:
        root = _assembly(scene, 'declared-flat', (
            _entity_member('arm', path=('owner',)),
            _sub(('drive',), JointReference('arm', 'drive'), 'joint'),))
        children, path = {}, ('drive',)
    subject = ControlledSubjectV1('rotor-subject', 'arm', 'source-a', 'b'*64,
        'references_existing', 'fixed', FrameReference('arm', 'base'), None,
        (path,), ('controller-a',))
    old_channel = old.binding.channels[0]
    declaration = SubjectJointDeclarationV1(path, 'drive', ('controller-a',),
        old_channel.native_actuator, old_channel.transmission_id,
        old_channel.transmission_coefficient, old_channel.native_range, old_channel.native_drive)
    return scene, root, children, subject, declaration


@pytest.mark.parametrize('nested', [False, True])
def test_subject_declaration_is_builder_input_for_flat_and_nested(nested):
    scene, root, children, subject, declaration = _declaration_case(nested)
    plan = compile_declared_subject_binding(scene, 'a'*64, 'source-a', 'b'*64,
        root, children, (subject,), (declaration,))
    channel = plan.binding.channels[0]
    assert (channel.component_path, channel.entity_id, channel.joint_id, channel.owner_ids) == (
        subject.channel_paths[0], 'arm', 'drive', ('controller-a',))
    with pytest.raises(ValueError, match='does not resolve'):
        compile_declared_subject_binding(scene, 'a'*64, 'source-a', 'b'*64,
            root, children, (subject,), (replace(declaration, joint_id='foreign'),))
    with pytest.raises(ValueError, match='writers differ'):
        compile_declared_subject_binding(scene, 'a'*64, 'source-a', 'b'*64,
            root, children, (subject,), (replace(declaration, owner_ids=('foreign',)),))


def test_controller_space_preserves_bounds_dtype_tree_and_multiple_controllers():
    bounded = Box(-2., 2., shape=(1,), dtype=np.float64)
    tree = Dict({'torque': Box(-1., 1., shape=(1,), dtype=np.float32)})
    a = SimpleNamespace(identity='bounded', action_shape=(1,), action_space=bounded)
    b = SimpleNamespace(identity='tree', action_space=tree)
    space = PhysicalControlExecutionV1.action_space(SimpleNamespace(controllers=(a,)))
    assert space.dtype == np.float64 and not space.contains(np.array([3.], dtype=np.float64))
    combined = PhysicalControlExecutionV1.action_space(SimpleNamespace(controllers=(a,b)))
    assert combined.spaces['bounded'] is bounded and combined.spaces['tree'] is tree
    assert combined.contains({'bounded': np.array([1.], dtype=np.float64),
                              'tree': {'torque': np.array([.5], dtype=np.float32)}})
    with pytest.raises(ValueError, match='shape differs'):
        PhysicalControlExecutionV1._controller_action_space(
            SimpleNamespace(action_shape=(2,), action_space=bounded))


def test_single_controller_action_tree_reaches_controller_unflattened():
    from task_env.diagnostics.tasks.test_v211_controlled_subjects import _fixture
    execution, _, context = _fixture()
    old = execution.controllers[0]
    tree = Dict({'torque': Box(-2., 2., shape=(1,), dtype=np.float32)})
    controller = SimpleNamespace(binding=old.binding, identity=old.identity,
        writer_id=old.writer_id, action_space=tree,
        compute=lambda action, view, ctx: old.compute(action['torque'], view, ctx))
    execution = replace(execution, controllers=(controller,))
    batch = execution.controller_batch({'torque': np.array([1.25], dtype=np.float32)}, None, context)
    assert batch.joint_efforts[0].value == 1.25


def test_pendulum_subject_supplies_shared_builder_without_existing_binding():
    from task_env.artifacts import SceneDefinition
    from task_env.robots.pendulum import PendulumEntity
    def rename(value):
        if isinstance(value, str):
            return {'arm': 'pendulum-body', 'drive': 'pendulum_hinge'}.get(value, value)
        if isinstance(value, list):
            return [rename(item) for item in value]
        if isinstance(value, dict):
            return {key: rename(item) for key, item in value.items()}
        return value
    scene = SceneDefinition.from_mapping(rename(_scene_v3().to_mapping()))
    root = _assembly(scene, 'pendulum-declaration-only', (
        _entity_member('pendulum-body', path=('owner',)),
        _sub(('hinge',), JointReference('pendulum-body', 'pendulum_hinge'), 'joint'),))
    subject, joints = PendulumEntity().physical_subject_declaration(
        source_id='source-a', source_closure_sha256='b'*64, entity_id='pendulum-body',
        root_frame='base', controller_writer='pendulum-controller', component_path=('hinge',))
    compiled = compile_declared_subject_binding(scene, 'a'*64, 'source-a', 'b'*64,
                                                root, {}, (subject,), joints)
    channel = compiled.binding.channels[0]
    assert (channel.joint_id, channel.native_actuator, channel.effort_range, channel.unit) == (
        'pendulum_hinge', 'pendulum_torque', (-2., 2.), 'N*m')
    assert subject.source_ownership == 'references_existing'


def test_two_wheel_declaration_keeps_left_right_without_existing_binding():
    from task_env.robots.two_wheel_balance import TwoWheelBalanceEntity
    subject, joints = TwoWheelBalanceEntity().physical_subject_declaration(
        source_id='source-a', source_closure_sha256='b'*64, entity_id='vehicle',
        root_frame='base', controller_writer='wheels',
        component_paths=(('robot','left'), ('robot','right')))
    assert subject.channel_paths == (('robot','left'), ('robot','right'))
    assert tuple((item.joint_id, item.native_actuator, item.native_range) for item in joints) == (
        ('left_wheel_hinge', 'left_wheel_torque', (-1.5, 1.5)),
        ('right_wheel_hinge', 'right_wheel_torque', (-1.5, 1.5)))


def test_declared_two_subjects_drive_two_controller_batch():
    from task_env.controllers.canonical.physical_commands import PhysicalCommandBatchV1
    old, context, effort, _ = _case()
    scene = _scene_v3()
    root = _assembly(scene, 'two-declared-subjects', (
        _entity_member('arm', path=('arm-owner',)), _entity_member('hand', path=('hand-owner',)),
        _sub(('arm-joint',), JointReference('arm', 'drive'), 'joint'),
        _sub(('hand-joint',), JointReference('hand', 'drive'), 'joint')))
    subjects = tuple(ControlledSubjectV1(name, name, 'source-a', 'b'*64,
        'references_existing', 'fixed', FrameReference(name, 'base'), None,
        ((name+'-joint',),), (name+'-writer',)) for name in ('arm','hand'))
    declarations = tuple(SubjectJointDeclarationV1((name+'-joint',), 'drive',
        (name+'-writer',), name+'-actuator', name+'-transmission', 1., (-5.,5.), 'disabled')
        for name in ('arm','hand'))
    compiled = compile_declared_subject_binding(scene, 'a'*64, 'source-a', 'b'*64,
                                                root, {}, subjects, declarations)
    def make_controller(name):
        def compute(action, view, ctx):
            joint = effort(name+'-effect', float(action[0]))
            joint = replace(joint, entity_id=name, axis_frame=FrameReference(name,'base'),
                            contribution=replace(joint.contribution, owner_id=name+'-writer'))
            return PhysicalCommandBatchV1('physical-command-batch-v1', ctx, (joint,), (), ())
        return SimpleNamespace(binding=compiled.binding, identity=name+'-controller',
                               writer_id=name+'-writer', action_shape=(1,), compute=compute)
    controllers = tuple(make_controller(name) for name in ('arm','hand'))
    req = StateRequirements('state-requirements-v1', 'controller', 'two-subjects', ())
    execution = PhysicalControlExecutionV1(compiled, controllers, scene, {}, {}, req, 1, subjects)
    batch = execution.controller_batch({'arm-controller':[1.], 'hand-controller':[2.]}, None, context)
    assert [(item.entity_id, item.value) for item in batch.joint_efforts] == [('arm',1.), ('hand',2.)]


def test_saved_pickcube_state_uses_site_for_observation_and_evaluation():
    from task_env.tasks.pick_cube.physical_candidate import _direct_physical_observation
    source = Path('workspace/maintenance/v211_g05_5c_human_diagnostic_attempt001/phase1/runs/mujoco-slice-015/result.json')
    raw = json.loads(source.read_text())['before']
    def pose(value): return PoseWorld(tuple(value['position']), tuple(value['quaternion_wxyz']))
    frames = [SimpleNamespace(frame=SimpleNamespace(**v['frame']), pose_world=pose(v['pose_world']))
              for v in raw['frames']]
    joints = [SimpleNamespace(entity_id=v['entity_id'], joint_id=v['joint_id'],
              position=v['position'], velocity=v['velocity']) for v in raw['joints']]
    lookup = {(f.frame.entity_id, f.frame.frame_id): f.pose_world for f in frames}
    site, hand, cube = lookup['panda-v1','nutassembly_ee_site'], lookup['panda-v1','hand'], lookup['cube-v1','PickCube']
    boundary = SimpleNamespace(boundary_id='state-boundary-'+'0'*64, to_mapping=lambda: {})
    view = SimpleNamespace(joints=joints, frames=frames, boundary=boundary,
                           sample_clock=SimpleNamespace(to_mapping=lambda: {}))
    state = SimpleNamespace(convention=raw['convention'], control_step=0, simulation_time=0.,
        joint_position={}, joint_velocity={}, pose_world={'panda-v1/ee':site,'cube-v1':cube})
    seen = {}
    def evaluate(value, semantics):
        seen['ee'] = value.pose_world['panda-v1/ee'].position
        return SimpleNamespace(success=False, failure=False, metrics={})
    env = SimpleNamespace(typed_state=SimpleNamespace(view=view),
        binding=SimpleNamespace(evaluate=evaluate), artifact=SimpleNamespace(semantics=None))
    obs, _, _ = _direct_physical_observation(env, state)
    assert seen['ee'] == site.position
    assert np.allclose(obs['state']['ee_pose'][:3], site.position, atol=1e-7)
    assert np.allclose(obs['state']['hand_pose'][:3], hand.position, atol=1e-7)
    assert math.dist(site.position, hand.position) == pytest.approx(.0584, abs=1e-12)
