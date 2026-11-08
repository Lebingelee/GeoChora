"""Pure contract tests; no asset/source parsing or native provider use."""
from dataclasses import replace

import pytest

from task_env.assembly.source_composition import (
    CompositionAttachmentV2, CompositionMaterializationReceiptV1, CompositionSourceV1,
    CompositionSourceV2, SourceCompositionPlanV1, SourceCompositionRequestV2,
)


def _plan():
    return SourceCompositionPlanV1(
        task_source=CompositionSourceV1('task-source', 'a' * 64, ('table', 'cube', 'robot')),
        task_entity_ids=('table', 'cube'), existing_robot_entity_ids=('robot',),
        robot_uid='assembled', robot_sources=(
            CompositionSourceV1('arm-source', 'b' * 64, ('arm',)),
            CompositionSourceV1('hand-source', 'c' * 64, ('hand',)),
        ), mode='replace', assembly_identity_sha256='d' * 64,
        attachment_identity_sha256='e' * 64, task_entity_source_roots=(('table','table-root'),('cube','cube-root')),
        replaced_robot_source_roots=('old-robot-root',), task_free_joints=(('cube','cube-free'),),
    )


def test_replacement_retains_task_and_validates_receipt():
    plan = _plan()
    assert plan.entity_ids == ('table', 'cube', 'arm', 'hand')
    receipt = CompositionMaterializationReceiptV1(plan.identity_hash,
        (('task-source', 'a' * 64), ('arm-source', 'b' * 64), ('hand-source', 'c' * 64)),
        (('table', 't'), ('cube', 'c'), ('arm', 'a'), ('hand', 'h')), 'materialization-1')
    receipt.validate_against(plan)
    with pytest.raises(ValueError, match='coverage'):
        replace(receipt, entity_native_names=receipt.entity_native_names[:-1]).validate_against(plan)
    with pytest.raises(ValueError, match='closure'):
        replace(receipt, source_closures=(('task-source', 'f' * 64), *receipt.source_closures[1:])).validate_against(plan)
    with pytest.raises(ValueError, match='unique'):
        replace(receipt, entity_native_names=(('table', 't'), ('cube', 't'), ('arm', 'a'), ('hand', 'h'))).validate_against(plan)


def test_ownership_collisions_and_missing_task_are_rejected():
    plan = _plan()
    with pytest.raises(ValueError, match='task source roots'):
        replace(plan, task_entity_ids=('table',))
    with pytest.raises(ValueError, match='unique and disjoint'):
        replace(plan, robot_sources=(CompositionSourceV1('arm', 'b' * 64, ('cube',)),))
    with pytest.raises(ValueError, match='unique and disjoint'):
        replace(plan, robot_sources=(CompositionSourceV1('arm', 'b' * 64, ('arm',)),
                                     CompositionSourceV1('hand', 'c' * 64, ('arm',))))


def test_reference_uses_existing_robot_without_duplicate_entity():
    source = CompositionSourceV1('task', 'a' * 64, ('cube', 'robot'))
    robot = CompositionSourceV1('task', 'a' * 64, ('robot',))
    plan = SourceCompositionPlanV1(source, ('cube',), ('robot',), 'integrated', (robot,),
                                   'reference', 'd' * 64)
    assert plan.entity_ids == ('cube', 'robot')
    with pytest.raises(ValueError, match='closure'):
        replace(plan, robot_sources=(replace(robot, closure_sha256='b' * 64),))
    with pytest.raises(ValueError, match='retain'):
        replace(plan, robot_sources=(replace(robot, entity_ids=('other',)),))


def _request_v2(*, mode='replace', empty_task=False):
    task_entities = () if empty_task else ('table', 'cube')
    old_robot = () if mode == 'add' or empty_task else ('panda-v1',)
    task_source = CompositionSourceV2('task-v2', 'a' * 64, (*task_entities, *old_robot))
    if mode == 'reference':
        robot_sources = (CompositionSourceV2('task-v2', 'a' * 64, ('panda-v1',)),)
        attachments = ()
    elif mode == 'add':
        robot_sources = (CompositionSourceV2('standalone-arm', 'b' * 64, ('arm',)),)
        attachments = ()
    else:
        robot_sources = (CompositionSourceV2('arm-source', 'b' * 64, ('arm',)),
                         CompositionSourceV2('hand-source', 'c' * 64, ('hand',)))
        attachments = (CompositionAttachmentV2('arm', 'link7', 'hand', 'hand',
            'fixed-panda-hand-v1', 'arm-source', 'b' * 64, 'hand-source', 'c' * 64),)
    return SourceCompositionRequestV2('source-composition-request-v2', task_source,
        task_entities, old_robot, 'panda', robot_sources, mode, 'd' * 64,
        attachments, (('arm', 'arm-effort', 'arm-writer'),) if mode == 'replace' else ())


def test_v2_composition_supports_empty_task_add_reference_and_replace():
    empty_add = _request_v2(mode='add', empty_task=True)
    assert empty_add.task_entity_ids == ()
    assert empty_add.entity_ids == ('arm',)
    assert len(empty_add.identity_hash) == 64

    added = _request_v2(mode='add')
    assert added.existing_robot_entity_ids == ()
    assert added.entity_ids == ('table', 'cube', 'arm')

    referenced = _request_v2(mode='reference')
    assert referenced.entity_ids == ('table', 'cube', 'panda-v1')

    replaced = _request_v2()
    assert replaced.entity_ids == ('table', 'cube', 'arm', 'hand')
    assert replaced.attachments[0].child_entity_id == 'hand'


def test_v2_rejects_source_entity_attachment_and_writer_collisions():
    request = _request_v2()
    with pytest.raises(ValueError, match='partition'):
        replace(request, task_entity_ids=('table',))
    with pytest.raises(ValueError, match='provenance'):
        replace(request, attachments=(replace(request.attachments[0], child_closure_sha256='f' * 64),))
    with pytest.raises(ValueError, match='outside the composition'):
        replace(request, attachments=(replace(request.attachments[0], child_entity_id='missing'),))
    with pytest.raises(ValueError, match='only one writer'):
        replace(request, resource_writers=(('arm', 'arm-effort', 'arm-writer'),
                                           ('arm', 'arm-effort', 'other-writer')))
    with pytest.raises(ValueError, match='acyclic'):
        replace(request, attachments=(
            CompositionAttachmentV2('arm', 'link7', 'hand', 'hand', 'fixed-v1',
                'arm-source', 'b' * 64, 'hand-source', 'c' * 64),
            CompositionAttachmentV2('hand', 'hand', 'arm', 'link7', 'fixed-v1',
                'hand-source', 'c' * 64, 'arm-source', 'b' * 64)))
    with pytest.raises(ValueError, match='unsupported'):
        replace(request, schema_version='source-composition-request-v9')


def test_panda_robot_recipes_require_no_asset_reads_or_provider_imports(monkeypatch):
    import builtins
    from pathlib import Path
    import task_env.robots  # Register both declarations before applying the provider import guard.
    from task_env.registry import AGENT_REGISTRY

    original_import = builtins.__import__
    def guarded_import(name, *args, **kwargs):
        if any(token in name for token in ('mujoco_composition', 'RuntimeSource', 'mujoco', 'scene')):
            raise AssertionError(f'Robot declaration imported provider parser: {name}')
        return original_import(name, *args, **kwargs)
    def guarded_read(_path, *args, **kwargs):
        raise AssertionError('Robot declaration read an asset file')

    monkeypatch.setattr(builtins, '__import__', guarded_import)
    monkeypatch.setattr(Path, 'read_bytes', guarded_read)
    monkeypatch.setattr(Path, 'open', guarded_read)
    recipes = {}
    for uid in ('panda-v1', 'panda-arm-hand-v1'):
        agent = AGENT_REGISTRY.create(uid)
        recipe = agent.source_recipe()
        recipes[uid] = recipe
        assert recipe.robot_uid == uid
        assert len(recipe.identity_hash) == 64
        assert recipe.control_profiles
        assert not hasattr(agent, 'compose_task_source')

    from types import SimpleNamespace
    from task_env.assembly.source_composition import build_source_composition_intent_v1
    task_source = SimpleNamespace(source_id='pickcube-task-source',
                                  source_closure_digest='a' * 64)
    integrated = build_source_composition_intent_v1(
        task_source=task_source, task_entity_ids=('tabletop', 'cube'),
        existing_robot_entity_ids=('panda-v1',), robot_recipe=recipes['panda-v1'])
    assembled = build_source_composition_intent_v1(
        task_source=task_source, task_entity_ids=('tabletop', 'cube'),
        existing_robot_entity_ids=('panda-v1',), robot_recipe=recipes['panda-arm-hand-v1'],
        task_site_transfers=(('hand', 'nutassembly_ee_site', 'hand'),))
    assert integrated.mode == 'reference'
    assert integrated.task_entity_ids == ('tabletop', 'cube')
    assert integrated.resource_writers == recipes['panda-v1'].resource_writers
    assert assembled.mode == 'replace'
    assert assembled.component_edges == recipes['panda-arm-hand-v1'].component_edges
    assert assembled.task_site_transfers == (('hand', 'nutassembly_ee_site', 'hand'),)
    assert tuple(source.source_revision for source in assembled.robot_sources) == (
        'b846dd12bc459d776cccb3dee0b1d02acbf7a9c7',
        'b846dd12bc459d776cccb3dee0b1d02acbf7a9c7')
    assert len(integrated.identity_hash) == len(assembled.identity_hash) == 64

    import inspect
    from task_env.robots.assembled_panda import AssembledPandaAgent
    from task_env.robots.panda import PandaAgent
    for agent_type in (AssembledPandaAgent, PandaAgent):
        source = inspect.getsource(agent_type)
        assert 'RuntimeSource' not in source
        assert 'mujoco_composition' not in source
        assert 'derive_task_compatible_attachment' not in source
        assert 'PandaFixedSourceDeclarationV1' not in source


def test_v1_composition_hash_schema_remains_frozen():
    import hashlib
    import json
    plan = _plan()
    expected = hashlib.sha256(json.dumps(
        {'schema_version': 'source-composition-plan-v1', **__import__('dataclasses').asdict(plan)},
        sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    assert plan.identity_hash == expected


def test_selected_robot_configuration_roundtrips_and_rejects_unknown():
    import task_env.robots  # Register the actual Robot owners, without building source.
    from task_env.environment.config import ResolvedEnvConfig
    from task_env.environment.configuration import resolve_task_env_config

    class Task:
        uid = 'composition-test-task'
        uses_selected_public_config = True
        selected_controller_profiles = frozenset()
        selected_parameter_limits = {}
        selected_supports_isaac = False
        selected_robot_uids = frozenset(('panda-v1', 'panda-arm-hand-v1'))

        @staticmethod
        def selected_default_config():
            return ResolvedEnvConfig()

        @staticmethod
        def selected_default_controller_profile():
            return None

    default = resolve_task_env_config(Task, None)
    assert default.robot_uid is None
    for uid in Task.selected_robot_uids:
        chosen = resolve_task_env_config(Task, {'robot': {'uid': uid}})
        assert chosen.robot_uid == uid
        assert resolve_task_env_config(Task, chosen) == chosen
    with pytest.raises(ValueError, match='does not admit'):
        resolve_task_env_config(Task, {'robot': {'uid': 'other'}})
    with pytest.raises(ValueError, match='exactly uid'):
        resolve_task_env_config(Task, {'robot': {'uid': 'panda-v1', 'extra': 1}})


def test_mujoco_projection_preserves_task_world_and_rejects_source_drift():
    import hashlib
    import xml.etree.ElementTree as ET
    from task_env.runtime.sessions.mujoco_composition import extract_task_world_mjcf

    xml = ('<mujoco><worldbody><light name="lamp"/><body name="robot"/>'
           '<body name="table"/><body name="cube"><freejoint name="cube-free" '
           'damping="0.8" armature="0.01"/></body></worldbody></mujoco>')
    kw = dict(task_xml=xml, expected_xml_sha256=hashlib.sha256(xml.encode()).hexdigest(),
              retained_roots=('table', 'cube'), replaced_robot_roots=('robot',))
    result = ET.fromstring(extract_task_world_mjcf(**kw))
    world = result.find('worldbody')
    assert [x.get('name') for x in world] == ['lamp', 'table', 'cube']
    assert world.find("body[@name='cube']/joint").attrib == {
        'name': 'cube-free', 'damping': '0.8', 'armature': '0.01', 'type': 'free'}
    with pytest.raises(ValueError, match='digest'):
        extract_task_world_mjcf(**{**kw, 'task_xml': xml + ' '})
    with pytest.raises(ValueError, match='partition'):
        extract_task_world_mjcf(**{**kw, 'retained_roots': ('cube',)})
    with pytest.raises(ValueError, match='disjoint'):
        extract_task_world_mjcf(**{**kw, 'replaced_robot_roots': ('cube',)})


def test_duplicate_world_element_requires_identical_task_owned_copy():
    import xml.etree.ElementTree as ET
    from task_env.runtime.sessions.mujoco_composition import coalesce_identical_world_elements
    robot = '<mujoco><worldbody><light name="top" pos="0 0 2"/><body name="robot"/></worldbody></mujoco>'
    task = '<mujoco><worldbody><light name="top" pos="0 0 2"/><body name="cube"/></worldbody></mujoco>'
    lowered, names = coalesce_identical_world_elements(robot_xml=robot, task_world_xml=task)
    assert names == (('light', 'top'),)
    assert ET.fromstring(lowered).find('worldbody/light') is None
    with pytest.raises(ValueError, match='conflicting'):
        coalesce_identical_world_elements(robot_xml=robot, task_world_xml=task.replace('0 0 2', '0 0 3'))


def test_task_site_transfer_preserves_attributes_and_rejects_ambiguity():
    import hashlib
    import xml.etree.ElementTree as ET
    from task_env.runtime.sessions.mujoco_composition import transfer_declared_task_site
    task = '<mujoco><worldbody><body name="hand"><site name="tcp" pos="0 0 .0584" group="6"/></body></worldbody></mujoco>'
    robot = '<mujoco><worldbody><body name="new-hand"/></worldbody></mujoco>'
    args = dict(task_xml=task, expected_xml_sha256=hashlib.sha256(task.encode()).hexdigest(),
                source_body='hand', site_name='tcp', robot_xml=robot, target_body='new-hand')
    result = ET.fromstring(transfer_declared_task_site(**args))
    assert result.find('.//body/site').attrib == {'name': 'tcp', 'pos': '0 0 .0584', 'group': '6'}
    with pytest.raises(ValueError, match='digest'):
        transfer_declared_task_site(**{**args, 'task_xml': task + ' '})
    with pytest.raises(ValueError, match='exactly once'):
        transfer_declared_task_site(**{**args, 'site_name': 'missing'})
    with pytest.raises(ValueError, match='already exists'):
        transfer_declared_task_site(**{**args, 'robot_xml': robot.replace('<body name="new-hand"/>', '<body name="new-hand"><site name="tcp"/></body>')})


def test_task_site_transfers_are_part_of_plan_identity():
    plan = _plan()
    site = ('hand', 'tcp', 'hand')
    updated = replace(plan, task_site_transfers=(site,))
    assert updated.identity_hash != plan.identity_hash
    with pytest.raises(ValueError, match='unique'):
        replace(plan, task_site_transfers=(site, site))
    with pytest.raises(ValueError, match='requires'):
        replace(plan, task_site_transfers=(('hand', 'tcp'),))


def test_one_controller_can_bind_multiple_entities_only_through_resolved_assembly():
    from task_env.artifacts.state import StateRequirements
    from task_env.diagnostics.tasks.test_phase_ii_01_r01b_logical_resolution import (
        _scene_v3, _primary_closure, _assembly, _entity_member,
    )
    from task_env.environment.types import ActionModeSpec
    from task_env.runtime.sessions.control import (
        ControllerBindingV1, ControlGroupActionProjectionV1, compile_control_binding_plan,
    )
    scene = _scene_v3()
    root, branch, arm, hand, children = _primary_closure(scene)
    action = ActionModeSpec('compound-action', 'task-env-action-v2', 'absolute_joint',
        None, None, ('a', 'b', 'c'), (-1., -1., -1.), (1., 1., 1.))
    feedback = StateRequirements('state-requirements-v1', 'controller', 'writer', ())
    binding = ControllerBindingV1('controller-binding-v1', 'writer', action, 'feedback', 'v1',
        feedback, tuple(ControlGroupActionProjectionV1('control-group-action-projection-v1',
            entity, group, (component,)) for entity, group, component in (
            ('arm', 'arm-main', 'a'), ('arm', 'arm-hand', 'b'), ('hand', 'hand-main', 'c'))))
    with pytest.raises(ValueError, match='resolved logical Assembly'):
        compile_control_binding_plan(scene, (binding,))
    plan = compile_control_binding_plan(scene, (binding,), logical_assembly=root,
                                        assembly_children=children)
    assert plan.assembly_identity_hash == root.logical_content_sha256
    assert len(plan.resource_writers) == 3
    assert {writer for _, _, writer in plan.resource_writers} == {'writer'}
    incomplete = _assembly(scene, 'incomplete-owner', (_entity_member('arm'),))
    with pytest.raises(ValueError, match='resolved logical Assembly'):
        compile_control_binding_plan(scene, (binding,), logical_assembly=incomplete)
    with pytest.raises(ValueError):
        compile_control_binding_plan(scene, (binding,), logical_assembly=root, assembly_children={})


def test_position_subject_binding_rejects_missing_or_foreign_joint():
    from dataclasses import replace
    from task_env.artifacts import FrameReference
    from task_env.artifacts.state import StateRequirements
    from task_env.diagnostics.tasks.test_phase_ii_01_r01b_logical_resolution import (
        _scene_v3, _assembly, _entity_member, _sub, _nested,
    )
    from task_env.artifacts import JointReference
    from task_env.environment.types import ActionModeSpec
    from task_env.runtime.sessions.control import (ControllerBindingV1, ControlGroupActionProjectionV1,
        compile_control_binding_plan, validate_position_control_subjects)
    from task_env.runtime.sessions.physical_control import ControlledSubjectV1
    scene = _scene_v3()
    arm = _assembly(scene, 'subject-arm', (_entity_member('arm'), _sub(('joint',), JointReference('arm', 'drive'), 'joint')))
    hand = _assembly(scene, 'subject-hand', (_entity_member('hand'), _sub(('joint',), JointReference('hand', 'drive'), 'joint')))
    root = _assembly(scene, 'subject-root', (_nested(('a',), arm), _nested(('h',), hand)))
    children = {(a.assembly_id, a.revision): a for a in (arm, hand)}
    action = ActionModeSpec('subject-action', 'task-env-action-v2', 'absolute_joint', None, None,
                            ('a', 'b', 'c'), (-1.,)*3, (1.,)*3)
    requirements = StateRequirements('state-requirements-v1', 'controller', 'writer', ())
    binding = ControllerBindingV1('controller-binding-v1', 'writer', action, 'feedback', 'v1',
        requirements, tuple(ControlGroupActionProjectionV1('control-group-action-projection-v1', e, g, (a,))
                            for e,g,a in (('arm','arm-main','a'),('arm','arm-hand','b'),('hand','hand-main','c'))))
    plan = compile_control_binding_plan(scene, (binding,), logical_assembly=root, assembly_children=children)
    subjects = tuple(ControlledSubjectV1(e, e, 'source', 'a'*64, 'references_existing', 'fixed',
        FrameReference(e, 'base'), None, ((path, 'joint'),), ('writer',)) for e,path in (('arm','a'),('hand','h')))
    kwargs = dict(scene=scene, root=root, children=children, subjects=subjects, plan=plan)
    assert len(validate_position_control_subjects(**kwargs)) == 64
    with pytest.raises(ValueError, match='own joint'):
        validate_position_control_subjects(**{**kwargs, 'subjects': (subjects[0], replace(subjects[1], channel_paths=(('a','joint'),)))})
    with pytest.raises(ValueError, match='writers'):
        validate_position_control_subjects(**{**kwargs, 'subjects': (replace(subjects[0], controller_writers=('wrong',)), subjects[1])})
    cycle = (replace(subjects[0], root_mode='constrained', parent_subject_id='hand'),
             replace(subjects[1], root_mode='constrained', parent_subject_id='arm'))
    with pytest.raises(ValueError, match='parent cycle'):
        validate_position_control_subjects(**{**kwargs, 'subjects': cycle})
    missing = (replace(subjects[0], root_mode='constrained', parent_subject_id='missing'), subjects[1])
    with pytest.raises(ValueError, match='parent is missing'):
        validate_position_control_subjects(**{**kwargs, 'subjects': missing})


def test_position_subject_owns_native_actuators_exclusively():
    from types import SimpleNamespace
    from task_env.runtime.sessions.mujoco import _MuJoCoSession
    session = SimpleNamespace(_reset_done=False,
                              _source=SimpleNamespace(position_subject_binding=object()))
    with pytest.raises(ValueError, match='cannot share position-subject'):
        _MuJoCoSession.bind_physical_control(session, object())


def test_joint_ownership_rejects_swapped_source_mapping():
    from task_env.assembly.source_composition import PositionSubjectControlBindingV1
    from task_env.runtime.sessions.control import ControlBindingPlanV1
    plan = ControlBindingPlanV1('control-binding-plan-v1', 'a'*64, (), ())
    object.__setattr__(plan, '_compiled', True)
    # No fabricated plan can advertise resources it did not compile.
    with pytest.raises(ValueError, match='cover'):
        PositionSubjectControlBindingV1(plan, 'b'*64, (('robot','actuator1','a1'),),
            (('robot/j1','robot','j1','j1','actuator1'),))


def test_failed_robot_source_adapter_releases_owned_task_snapshot(monkeypatch):
    from types import SimpleNamespace
    from task_env.tasks.pick_cube import specialization
    receipt = SimpleNamespace(closed=False)
    def close(): receipt.closed = True
    receipt.close = close
    source = SimpleNamespace(execution_source_receipt=receipt)
    monkeypatch.setattr(specialization, 'build_reference', lambda **kwargs: {
        'source': source, 'artifact': object(), 'controller': object()})
    def fail(_source, **_kwargs):
        raise ValueError('rejected robot source')
    binding = specialization.make_reference_binding(controller_profile='r1', robot_source_adapter=fail)
    with pytest.raises(ValueError, match='rejected robot source'):
        binding.build('mujoco')
    assert receipt.closed


def test_failed_robot_identity_projection_releases_task_snapshot(monkeypatch):
    from types import SimpleNamespace
    from task_env.tasks.pick_cube import specialization
    from task_env.assembly import compiler
    receipt = SimpleNamespace(closed=False)
    receipt.close = lambda: setattr(receipt, 'closed', True)
    source = SimpleNamespace(execution_source_receipt=receipt)
    monkeypatch.setattr(specialization, 'build_reference', lambda **kwargs: {
        'source': source, 'artifact': object(), 'controller': object(), 'resolved_configuration': {}})
    def fail(*_args, **_kwargs):
        raise ValueError('identity projection failed')
    monkeypatch.setattr(compiler, 'reference_task_identity_fields', fail)
    binding = specialization.make_reference_binding(controller_profile='r1',
        robot_source_adapter=lambda source, **_kwargs: source)
    with pytest.raises(ValueError, match='identity projection failed'):
        binding.build('mujoco')
    assert receipt.closed
