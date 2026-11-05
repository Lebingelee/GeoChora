"""Focused production-consumer checks for G03/3a request-bound layout."""
from dataclasses import replace
from types import SimpleNamespace as NS
import sys

import pytest

from task_env import make_env
from task_env.artifacts import CapabilityAssessmentV1, ExecutionSpec
from task_env.runtime.sessions.api import PROFILE, assess_selected_request, materialize
from task_env.runtime.sessions.provenance import probe_interpreter_environment, assess_declared_dependencies


@pytest.fixture
def selected():
    env = make_env('pick-cube-p16-reference-v1', config={'provider': 'mujoco'})
    try:
        environment = probe_interpreter_environment(sys.executable)
        dependency = assess_declared_dependencies('mujoco', environment)
        assert dependency['status'] == 'available'
        yield env, dependency['status']
    finally:
        env.close()


def test_actual_declaration_requires_concrete_object_check(selected):
    env, dependency = selected
    assessment = assess_selected_request(selection=env.resolved_public_config.execution_spec_v2,
        artifact=env.artifact, source=env.value['source'], value=env.value,
        binding=env.binding, dependency_status=dependency, request_identity='a'*64)
    pending = [r for r in assessment.rows if r.requirement_status == 'unknown']
    assert assessment.decision == 'pending_native_build'
    assert any(r.object_ref.startswith('joint:') for r in pending)
    assert any(r.object_ref.startswith('actuator:') for r in pending)
    assert all(r.build_oracle == 'task_env.runtime.sessions.mujoco:check_mujoco_named_layout' for r in pending)
    row = replace(pending[0], build_oracle='task_env.runtime.sessions.api:_materialize_admitted')
    assert CapabilityAssessmentV1('capability-assessment-v1', 'a'*64, 'static_preflight', (row,)).decision == 'rejected'
    wrong_object = replace(pending[0], capability_id='joint_state_query', object_ref='state:frame:robot/hand:frame_pose_world:evaluation_boundary:writer')
    assert CapabilityAssessmentV1('capability-assessment-v1', 'a'*64, 'static_preflight', (wrong_object,)).decision == 'rejected'
    optional = replace(row, requiredness='optional', reason='not available for this optional state')
    assert CapabilityAssessmentV1('capability-assessment-v1', 'a'*64, 'static_preflight', (optional,)).decision == 'static_admitted'


def _sdk_model(source, *, bad_type=False):
    import xml.etree.ElementTree as ET
    joints = list(dict.fromkeys([*source.joints.values(), *source.free_joints.values()]))
    bodies = list(dict.fromkeys(source.bodies.values()))
    sites = list(dict.fromkeys(source.frames.values()))
    actuators = list(dict.fromkeys([*source.joint_targets.values(), *source.open_actuators]))
    ids = {name:i for i,name in enumerate(joints)}
    model = NS(nq=len(joints)+6, nv=len(joints)+5, opt=NS(timestep=.002))
    model.jnt_type = [0 if x in source.free_joints.values() else 3 for x in joints]
    if bad_type: model.jnt_type[ids[next(iter(source.joints.values()))]] = 1
    model.jnt_qposadr = list(range(len(joints)))
    model.jnt_dofadr = list(range(len(joints)))
    model.actuator_trntype = [0]*len(actuators)
    model.actuator_trnid = [[0, 0] for _ in actuators]
    for semantic, native in source.joint_targets.items():
        model.actuator_trnid[actuators.index(native)][0] = ids[source.joints[semantic]]
    tendon_names = []
    for native in source.open_actuators:
        node = next(node for node in ET.fromstring(source.scene_source.xml).find('actuator')
                    if node.get('name') == native)
        if node.get('tendon'):
            tendon_names.append(node.get('tendon'))
            model.actuator_trntype[actuators.index(native)] = 3
            model.actuator_trnid[actuators.index(native)][0] = tendon_names.index(node.get('tendon'))
        else:
            model.actuator_trnid[actuators.index(native)][0] = ids[node.get('joint')]
    model.tendon = lambda name: NS(id=tendon_names.index(name))
    model.joint = lambda name: NS(id=ids[name])
    model.body = lambda name: NS(id=bodies.index(name))
    model.site = lambda name: NS(id=sites.index(name))
    model.actuator = lambda name: NS(id=actuators.index(name))
    return model


def test_real_materializer_runs_layout_helper_with_sdk_terminal_fixture(selected, monkeypatch):
    env, _ = selected
    source=env.value['source']
    sdk = NS(mjtJoint=NS(mjJNT_FREE=0, mjJNT_HINGE=3, mjJNT_SLIDE=2),
             mjtTrn=NS(mjTRN_JOINT=0, mjTRN_TENDON=3), MjData=lambda model: NS())
    def compile_model(xml, assets):
        assert source.execution_source_receipt is not None and assets
        model = _sdk_model(source, bad_type=compile_model.bad_type)
        if compile_model.bad_open:
            actuator_names = list(dict.fromkeys([*source.joint_targets.values(), *source.open_actuators]))
            model.actuator_trnid[actuator_names.index(source.open_actuators[0])][0] = -1
        return model
    compile_model.bad_type=False
    compile_model.bad_open=False
    sdk.MjModel=NS(from_xml_string=compile_model)
    monkeypatch.setitem(sys.modules, 'mujoco', sdk)  # Only the SDK terminal is synthetic.
    execution=ExecutionSpec('mujoco', PROFILE, 'none', 'cpu', 31, 'strict')
    session=materialize(env.artifact, execution, source=source)
    try:
        facts=session.build_layout_facts
        assert facts['helper'].endswith(':check_mujoco_named_layout')
        assert set(facts['objects']['joints']) == set(source.joints)
        assert set(source.joint_targets) <= set(facts['objects']['actuators'])
    finally:
        session.close()
    compile_model.bad_type=True
    with pytest.raises(ValueError, match='joint type'):
        materialize(env.artifact, execution, source=source)
    compile_model.bad_type=False
    compile_model.bad_open=True
    with pytest.raises(ValueError, match='opening actuator transmission differs'):
        materialize(env.artifact, execution, source=source)


def test_geophys_adapter_checks_actual_source_with_public_terminal_fixture(selected):
    from task_env.runtime.sessions.geophys import check_geophys_named_layout
    source = selected[0].value['source']
    joint_names = list(dict.fromkeys((*source.joints.values(), *source.free_joints.values())))
    actuator_names = list(dict.fromkeys((*source.joint_targets.values(), *source.open_actuators)))
    names = NS(joints={name: i for i, name in enumerate(joint_names)},
               bodies={name: i for i, name in enumerate(dict.fromkeys(source.bodies.values()))},
               sites={name: i for i, name in enumerate(dict.fromkeys(source.frames.values()))},
               actuators={name: i for i, name in enumerate(actuator_names)})
    types = [0 if name in source.free_joints.values() else 2 for name in joint_names]
    transmissions = [0] * len(actuator_names)
    for semantic, native in source.joint_targets.items():
        transmissions[names.actuators[native]] = names.joints[source.joints[semantic]]
    data = {'jnt_type': types, 'jnt_qposadr': list(range(len(joint_names))),
            'jnt_dofadr': list(range(len(joint_names))), 'n_qpos': len(joint_names) + 6,
            'n_dof': len(joint_names) + 5, 'actuator_trntype': [0] * len(actuator_names),
            'actuator_trnid': transmissions}
    import numpy as np
    snapshot = NS(qpos=np.zeros(data['n_qpos']), qvel=np.zeros(data['n_dof']),
                  ctrl=np.zeros(len(actuator_names)),
                  body_xpos=np.zeros((len(names.bodies), 3)), body_xquat=np.zeros((len(names.bodies), 4)),
                  site_xpos=np.zeros((len(names.sites), 3)), site_xquat=np.zeros((len(names.sites), 4)))
    boundary = NS(read_snapshot=lambda request: snapshot)
    facts = check_geophys_named_layout(names, data, source, boundary)
    semantic = next(iter(source.joint_targets))
    assert facts['actuators'][semantic]['joint_id'] == names.joints[source.joints[semantic]]
    wrong = list(transmissions)
    wrong[names.actuators[source.joint_targets[semantic]]] = -1
    with pytest.raises(ValueError, match='transmission mismatch'):
        check_geophys_named_layout(names, {**data, 'actuator_trnid': wrong}, source, boundary)
    snapshot.ctrl = np.zeros(0)
    with pytest.raises(ValueError, match='control channel lacks'):
        check_geophys_named_layout(names, data, source, boundary)


def test_isaac_helper_public_terminal_shape_fixture():
    from task_env.runtime.sessions.isaac_native_io import check_isaac_named_layout
    source=NS(joints={'robot/joint1':'j1'}, free_joints={'object/root':'free'},
              bodies={'object/root':'body'}, frames={'robot/hand':'site'},
              joint_targets={'robot/joint1':'j1'}, open_actuators=())
    views={'object/root':object(),'robot/hand':object()}; free={'object/root':object()}
    read=lambda: ({'robot/joint1':0.}, {'robot/joint1':0.}, views, free)
    assert check_isaac_named_layout(source,('j1',),views,free,read)['actuators']['robot/joint1']['id']==0
    with pytest.raises(ValueError, match='joint state missing'):
        check_isaac_named_layout(source,('other',),views,free,read)


def test_existing_versioned_multichannel_feedback_is_projected_and_missing_required_rejected():
    from task_env.artifacts import StateRequirements
    from task_env.diagnostics.tasks.test_phase_ii_c02a_controller_bindings import _binding, _scene
    from task_env.runtime.sessions.control import compile_control_binding_plan, project_controller_feedback
    scene = _scene()
    original = _binding()
    # The existing force field is represented but not supported by this route;
    # making it optional preserves its explicit unavailable requirement.
    fields = tuple(replace(item, requiredness='optional') if item.field_name == 'actuator_force' else item
                   for item in original.feedback_requirements.requirements)
    binding = replace(original, feedback_requirements=StateRequirements(
        'state-requirements-v1', 'controller', original.writer_id, fields))
    plan = compile_control_binding_plan(scene, (binding,))
    projected = project_controller_feedback(plan)
    assert len(plan.resource_writers) == 8 and len(binding.groups) == 2
    assert any(req.field_name == 'joint_position' and writer == binding.writer_id for writer, req in projected)
    assert any(req.field_name == 'actuator_force' and req.requiredness == 'optional' for _, req in projected)
    frame = next(item for item in fields if item.subject_kind == 'frame')
    missing = replace(frame, subject_id='nonexistent_frame')
    changed = tuple(missing if item is frame else item for item in fields)
    with pytest.raises(ValueError, match='unknown Frame'):
        compile_control_binding_plan(scene, (replace(binding, feedback_requirements=StateRequirements(
            'state-requirements-v1', 'controller', binding.writer_id, changed)),))
    optional_frame = replace(missing, requiredness='optional')
    changed = tuple(optional_frame if item is frame else item for item in fields)
    optional_plan = compile_control_binding_plan(scene, (replace(binding, feedback_requirements=StateRequirements(
        'state-requirements-v1', 'controller', binding.writer_id, changed)),))
    assert any(req.subject_id == 'nonexistent_frame' and req.requiredness == 'optional'
               for _, req in project_controller_feedback(optional_plan))


def test_represented_effort_is_explicitly_classified_by_assessment_consumer(selected):
    from task_env.diagnostics.tasks.test_phase_ii_c02a_controller_bindings import _binding, _scene
    from task_env.runtime.sessions.control import compile_control_binding_plan, project_controller_feedback
    from task_env.runtime.sessions.api import CAPABILITIES, project_feedback_assessment
    env, _ = selected
    plan = compile_control_binding_plan(_scene(), (_binding(),))
    rows = project_feedback_assessment(project_controller_feedback(plan), env.artifact,
        env.value['source'], set(CAPABILITIES), 'task_env.runtime.sessions.mujoco:check_mujoco_named_layout')
    force = next(row for row in rows if row[0] == 'actuator_force_query')
    assert force[1].startswith('state:actuator:panda-main/actuator8:actuator_force:')
    assert force[2:5] == ('required', False, 'unsatisfied')
    assert 'Core adapter does not implement' in force[5] and force[6] is None


def test_existing_schema_rejects_unknown_wrench_vocabulary():
    from task_env.artifacts import RequiredCapabilitySet, StateFieldRequirement
    with pytest.raises(ValueError, match='capability'):
        RequiredCapabilitySet(('body_wrench',))
    with pytest.raises(ValueError, match='unsupported state field'):
        StateFieldRequirement('state-field-requirement-v1', 'typed_load', 'entity',
                              'robot', 'robot', 'required', 'evaluation_boundary',
                              'newton', 'body_wrench')


def test_leaf_feedback_uses_existing_logical_assembly_resolver():
    from task_env.diagnostics.tasks.test_phase_ii_01_r02b_leaf_execution import _case
    from task_env.runtime.sessions.control import project_leaf_feedback
    scene, root, _, _, plan = _case()
    projected = project_leaf_feedback(scene, root, {}, plan)
    assert {writer for writer, _ in projected} == {'arm-writer', 'hand-writer'}
    assert any(req.subject_kind == 'joint' for _, req in projected)
    assert any(req.subject_kind == 'frame' for _, req in projected)


def test_existing_mixed_declarations_reach_assessment_and_concrete_layout_check(selected, monkeypatch):
    from task_env.diagnostics.tasks import test_r07c_libero_core_env_s1 as fixture
    from task_env.runtime.sessions.mujoco import check_mujoco_named_layout
    selected_env, dependency = selected
    selection = selected_env.resolved_public_config.execution_spec_v2
    # Build the existing typed input without its legacy origin substitutes.
    env = fixture._synthetic_mixed_candidate(monkeypatch, install_fake_sdk=False)
    try:
        source, artifact = env.value['source'], env.artifact
        assessment = assess_selected_request(selection=selection, artifact=artifact, source=source,
            value=env.value, binding=env.binding, dependency_status=dependency, request_identity='b'*64)
        assert assessment.decision == 'pending_native_build'
        assert {r.object_ref for r in assessment.rows if r.capability_id == 'joint_torque_actuation'} >= {
            'actuator:torque_orchid', 'actuator:torque_cobalt'}
        world = fixture._World()
        model = fixture._FakeModel(source.scene_source.xml, world)
        mj = NS(mjtJoint=NS(mjJNT_FREE=0, mjJNT_HINGE=1, mjJNT_SLIDE=2),
                mjtTrn=NS(mjTRN_JOINT=0))
        facts = check_mujoco_named_layout(model, mj, source)
        assert facts['actuators']['slide_fern']['native'] == 'servo_fern'
        actuator = facts['actuators']['torque_orchid']['id']
        model.actuator_trnid[actuator, 0] = -1
        with pytest.raises(ValueError, match='mixed actuator transmission mismatch'):
            check_mujoco_named_layout(model, mj, source)
    finally:
        env.close()
