"""Provider-free tests for source-bound subjects on the production control owner."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from task_env.artifacts.state import StateRequirements
from task_env.artifacts import FrameReference
from task_env.controllers.canonical.physical_commands import PhysicalCommandBatchV1
from task_env.diagnostics.tasks.test_v211_physical_control_contract import _case
from task_env.runtime.sessions.physical_control import (
    ControlledSubjectV1, PhysicalControlExecutionV1, validate_controlled_subjects,
)


def _fixture():
    plan, context, effort, _ = _case()
    subject = ControlledSubjectV1('subject-a', 'arm', 'source-a', 'b'*64, 'references_existing',
                                  'fixed', FrameReference('arm', 'base'), None,
                                  (('robot', 'arm-drive-joint'),), ('controller-a',))
    controller = SimpleNamespace(binding=plan.binding, identity='control-a', writer_id='controller-a',
        action_shape=(1,), compute=lambda action, view, ctx: PhysicalCommandBatchV1(
            'physical-command-batch-v1', ctx, (effort('effect-a', float(action[0])),), (), ()))
    req = StateRequirements('state-requirements-v1', 'controller', 'subject-a', ())
    execution = PhysicalControlExecutionV1(plan, (controller,), plan.scene, {}, {}, req, 1, (subject,))
    return execution, subject, context


def test_subject_controls_actual_named_batch_and_rejects_bad_declarations():
    execution, subject, context = _fixture()
    assert subject.identity_hash != replace(subject, root_mode='free').identity_hash
    with pytest.raises(ValueError, match='unit differs'):
        replace(execution.compiled.binding.channels[0], unit='N')
    batch = execution.controller_batch([1.25], object(), context)
    assert batch.joint_efforts[0].target_key == ('arm', 'drive', 'dof0')
    assert batch.joint_efforts[0].value == 1.25
    assert batch.joint_efforts[0].context == context
    with pytest.raises(ValueError, match='missing, duplicated or foreign'):
        validate_controlled_subjects(execution.compiled,
            (replace(subject, channel_paths=(('robot', 'absent'),)),), execution.controllers)
    with pytest.raises(ValueError, match='missing or foreign'):
        validate_controlled_subjects(execution.compiled,
            (replace(subject, source_id='other-source'),), execution.controllers)
    with pytest.raises(ValueError, match='missing or foreign'):
        validate_controlled_subjects(execution.compiled,
            (replace(subject, source_closure_sha256='c'*64),), execution.controllers)
    with pytest.raises(ValueError, match='root Frame is missing'):
        validate_controlled_subjects(execution.compiled,
            (replace(subject, root_frame=FrameReference('arm', 'absent')),), execution.controllers)
    with pytest.raises(ValueError, match='writer is missing'):
        validate_controlled_subjects(execution.compiled,
            (replace(subject, controller_writers=('foreign',)),), execution.controllers)
    with pytest.raises(ValueError, match='duplicate subject or entity'):
        validate_controlled_subjects(execution.compiled,
            (subject, replace(subject, subject_id='another')), execution.controllers)
    with pytest.raises(ValueError, match='parent is missing'):
        validate_controlled_subjects(execution.compiled,
            (replace(subject, root_mode='constrained', parent_subject_id='absent'),), execution.controllers)


def test_subject_default_effort_controller_is_bound_and_preserves_direct_identity():
    from task_env.controllers.canonical.physical_controller import DirectJointEffortControllerV1
    execution, subject, _ = _fixture()
    binding = execution.compiled.binding
    channel = binding.channels[0]
    controller = subject.default_effort_controller(binding, writer_id='controller-a', units=(channel.unit,))
    previous = DirectJointEffortControllerV1(binding, controller_id='controller-a',
                                            channel_keys=(f'{channel.entity_id}/{channel.joint_id}',))
    assert controller.identity == previous.identity
    with pytest.raises(ValueError, match='writer'):
        subject.default_effort_controller(binding, writer_id='foreign', units=(channel.unit,))
    with pytest.raises(ValueError, match='unit'):
        subject.default_effort_controller(binding, writer_id='controller-a', units=('wrong-unit',))
    with pytest.raises(ValueError, match='one explicit unit'):
        subject.default_effort_controller(binding, writer_id='controller-a', units=())
    with pytest.raises(ValueError, match='missing or ambiguous'):
        replace(subject, channel_paths=(('absent',),)).default_effort_controller(
            binding, writer_id='controller-a', units=(channel.unit,))
    with pytest.raises(ValueError, match='source'):
        replace(subject, source_id='foreign').default_effort_controller(
            binding, writer_id='controller-a', units=(channel.unit,))


def test_default_effort_checks_original_precision_before_float32_rounding():
    execution, subject, context = _fixture()
    binding = execution.compiled.binding
    channel = binding.channels[0]
    controller = subject.default_effort_controller(binding, writer_id='controller-a', units=(channel.unit,))
    with pytest.raises(ValueError, match='declared bounds'):
        controller.compute([channel.effort_range[1] + 1e-9], object(), context)


@pytest.mark.parametrize('version', [1, 2])
def test_typed_initial_state_uses_session_boundary_and_clock(version):
    from task_env.artifacts.state import (CanonicalStateViewV1, CanonicalStateViewV2,
        CanonicalStatePublicationV1, CanonicalStatePublicationV2, StateViewLifetime)
    from task_env.environment.reference_binding import validate_initial_state_publication
    _, _, context = _fixture()
    view_type = CanonicalStateViewV1 if version == 1 else CanonicalStateViewV2
    publication_type = CanonicalStatePublicationV1 if version == 1 else CanonicalStatePublicationV2
    view = view_type(f'canonical-state-v{version}', 'SI_right_handed_z_up_wxyz',
                     context.boundary, context.clock, (), (), ())
    lifetime = StateViewLifetime('state-view-lifetime-v1', 'material-a', context.boundary, 0,
                                 'owned_snapshot', 'retained')
    publication = publication_type(f'canonical-state-publication-v{version}', view, lifetime)
    session = SimpleNamespace(state_boundary_identity=lambda: context.boundary)
    state = SimpleNamespace(control_step=0, simulation_time=context.clock.simulation_time_s)
    assert validate_initial_state_publication(session, publication, state) is publication
    with pytest.raises(ValueError, match='boundary or clock'):
        validate_initial_state_publication(session, publication,
            SimpleNamespace(control_step=0, simulation_time=state.simulation_time + .1))
    with pytest.raises(ValueError, match='boundary or clock'):
        validate_initial_state_publication(SimpleNamespace(state_boundary_identity=lambda: None), publication, state)


def test_physical_execution_owns_controller_initialization_and_preflights_model():
    from task_env.artifacts.state import CanonicalStateViewV2, CanonicalStatePublicationV2, StateViewLifetime
    from task_env.environment.types import StageUnavailableError
    execution, _, context = _fixture()
    calls = []
    controller = execution.controllers[0]
    controller.bind_model = lambda model: calls.append(('model', model))
    controller.reset_from_realized_state = lambda view: calls.append(('reset', view))
    view = CanonicalStateViewV2('canonical-state-v2', 'SI_right_handed_z_up_wxyz',
                                context.boundary, context.clock, (), (), (), ())
    publication = CanonicalStatePublicationV2('canonical-state-publication-v2', view,
        StateViewLifetime('state-view-lifetime-v1', 'material-a', context.boundary, 0,
                          'owned_snapshot', 'retained'))
    with pytest.raises(StageUnavailableError, match='source dynamics model'):
        execution.initialize_controllers(SimpleNamespace(), publication)
    assert not calls
    execution.initialize_controllers(SimpleNamespace(physical_source_dynamics_model=lambda: 'source-model'), publication)
    assert calls == [('model', 'source-model'), ('reset', view)]


def test_foreign_controller_output_is_rejected_before_submission():
    execution, subject, context = _fixture()
    original = execution.controllers[0]
    wrong = replace(original.compute([1.0], None, context).joint_efforts[0], joint_id='other')
    bad = SimpleNamespace(binding=original.binding, identity=original.identity, writer_id=original.writer_id,
        action_shape=(1,), compute=lambda action, view, ctx: PhysicalCommandBatchV1(
            'physical-command-batch-v1', ctx, (wrong,), (), ()))
    changed = replace(execution, controllers=(bad,))
    with pytest.raises(ValueError, match='outside its subject'):
        changed.controller_batch([1.0], object(), context)


def test_nonposition_reference_close_releases_owned_camera_and_propagates_error():
    from task_env.environment.reference_env import SelectedReferenceEnv
    class Camera:
        calls = 0
        def close(self):
            self.calls += 1
    env = object.__new__(SelectedReferenceEnv)
    env.mixed_control_profile = False
    env.position_profile = False
    env._ui_render_provider = None
    env._camera_consumer = None
    camera = Camera()
    env._task_rgb_consumer = camera
    env.session = None
    env.value = {'source': SimpleNamespace(execution_source_receipt=None)}
    env.binding = SimpleNamespace(close_task_resources=None)
    env._close_reference_resources()
    env._close_reference_resources()
    assert camera.calls == 1
    assert env._task_rgb_consumer is None
    class FailedCamera:
        def close(self):
            raise RuntimeError('camera close failed')
    env._task_rgb_consumer = FailedCamera()
    with pytest.raises(RuntimeError, match='camera close failed'):
        env._close_reference_resources()
    assert env._task_rgb_consumer is None


def test_flat_and_nested_use_same_physical_resolver_and_subject_admission():
    from task_env.artifacts import JointReference
    from task_env.diagnostics.tasks.test_phase_ii_01_r01b_logical_resolution import (
        _scene_v3, _assembly, _entity_member, _sub,
    )
    from task_env.runtime.sessions.physical_control import compile_physical_control_binding
    nested, _, _, _ = _case()
    scene = _scene_v3()
    root = _assembly(scene, 'single-subject', (
        _entity_member('arm', path=('owner',)),
        _sub(('hinge',), JointReference('arm', 'drive'), 'joint'),
    ))
    channel = replace(nested.binding.channels[0], component_path=('hinge',))
    binding = replace(nested.binding, logical_assembly_sha256=root.logical_content_sha256,
                      channels=(channel,))
    flat = compile_physical_control_binding(scene, root, {}, binding)
    controller = SimpleNamespace(writer_id='controller-a')
    subject = ControlledSubjectV1('generic-one', 'arm', 'source-a', 'b'*64, 'owns_source', 'fixed',
                                  FrameReference('arm', 'base'), None, (('hinge',),), ('controller-a',))
    validate_controlled_subjects(flat, (subject,), (controller,))
    # The same subject semantics use the nested resolver, without task-name dispatch.
    nested_subject = replace(subject, channel_paths=(('robot', 'arm-drive-joint'),))
    validate_controlled_subjects(nested, (nested_subject,), (controller,))
    with pytest.raises(ValueError, match='source-owning subject needs'):
        empty_owner_root = _assembly(scene, 'referenced-only', (
            _sub(('hinge',), JointReference('arm', 'drive'), 'joint'),))
        no_owner_binding = replace(binding, logical_assembly_sha256=empty_owner_root.logical_content_sha256)
        no_owner = compile_physical_control_binding(scene, empty_owner_root, {}, no_owner_binding)
        validate_controlled_subjects(no_owner, (subject,), (controller,))


def test_legacy_closure_relocation_preserves_receipt_and_rejects_other_changes(monkeypatch, tmp_path):
    import task_env.assembly.assets as assets
    import task_env.utils._paths as paths
    from task_env.tasks.pick_cube.physical_candidate import _accept_original_panda_closure
    root = tmp_path / 'menagerie'
    monkeypatch.setattr(paths, 'MUJOCO_MENAGERIE_ROOT', root)
    current = str((root / 'franka_emika_panda' / 'assets').resolve()).encode()
    old = b'/home/lly/.codex/worktrees/v210-integration/Geochora/asset/external/mujoco_menagerie/franka_emika_panda/assets'
    original = {'canonical-source.xml': b'<compiler meshdir="' + current + b'"/>', 'assets/mesh.stl': b'original'}
    expected_bytes = {'canonical-source.xml': b'<compiler meshdir="' + old + b'"/>', 'assets/mesh.stl': b'original'}
    expected = '02f12b11e8215af606d9eed7f22c411dc5bbd74f7d956331b74400b5a1e6963d'
    monkeypatch.setattr(assets, '_source_closure_digest', lambda values: expected if values == expected_bytes else 'different')
    class Receipt:
        source_closure_digest = 'actual'
        closure_files = original
        def validate_snapshot(self):
            self.checked = True
    receipt = Receipt()
    assert _accept_original_panda_closure(receipt, 'actual')
    assert receipt.checked and receipt.closure_files == original
    assert not _accept_original_panda_closure(receipt, 'foreign')
    receipt.closure_files = dict(original, **{'assets/mesh.stl': b'modified'})
    assert not _accept_original_panda_closure(receipt, 'actual')
    receipt.closure_files = dict(original, **{'canonical-source.xml': original['canonical-source.xml'] + current})
    assert not _accept_original_panda_closure(receipt, 'actual')


def test_third_subject_can_bind_and_submit_without_public_task_dispatch():
    from task_env.artifacts import SceneDefinition, JointReference
    from task_env.diagnostics.tasks.test_phase_ii_01_r01b_logical_resolution import (
        _scene_v3, _assembly, _entity_member, _sub,
    )
    from task_env.runtime.sessions.physical_control import compile_physical_control_binding
    old, context, effort, _ = _case()
    def rename(value):
        if isinstance(value, str):
            return {'arm':'rotor','drive':'spin'}.get(value, value)
        if isinstance(value, list): return [rename(x) for x in value]
        if isinstance(value, dict): return {k:rename(v) for k,v in value.items()}
        return value
    scene = SceneDefinition.from_mapping(rename(_scene_v3().to_mapping()))
    root = _assembly(scene, 'rotor-assembly', (
        _entity_member('rotor', path=('owner',)),
        _sub(('spin',), JointReference('rotor', 'spin'), 'joint'),
    ))
    channel = replace(old.binding.channels[0], component_path=('spin',), entity_id='rotor',
                      joint_id='spin', axis_frame=FrameReference('rotor', 'base'))
    binding = replace(old.binding, scene_sha256=scene.identity_hash,
                      logical_assembly_sha256=root.logical_content_sha256, channels=(channel,))
    plan = compile_physical_control_binding(scene, root, {}, binding)
    subject = ControlledSubjectV1('rotor-subject','rotor','source-a','b'*64,'owns_source',
                                  'fixed',FrameReference('rotor','base'),None,(('spin',),),('controller-a',))
    joint = replace(effort('effect-a',1.0), entity_id='rotor', joint_id='spin',
                    axis_frame=FrameReference('rotor','base'))
    controller = SimpleNamespace(binding=binding, identity='rotor-controller', writer_id='controller-a',
        action_shape=(1,), compute=lambda action, view, ctx: PhysicalCommandBatchV1(
            'physical-command-batch-v1',ctx,(replace(joint,context=ctx,value=float(action[0])),),(),()))
    req = StateRequirements('state-requirements-v1','controller','rotor-subject',())
    execution = PhysicalControlExecutionV1(plan,(controller,),scene,{}, {},req,1,(subject,))
    actual = execution.controller_batch([1.5],None,context)
    assert actual.joint_efforts[0].target_key == ('rotor','spin','dof0')
    assert actual.joint_efforts[0].value == 1.5


def test_two_subject_controllers_combine_once_and_reject_parent_cycle():
    from task_env.artifacts import FixedAttachmentPlanV1, JointReference, PoseWorld
    from task_env.diagnostics.tasks.test_phase_ii_01_r01b_logical_resolution import (
        _scene_v3, _assembly, _entity_member, _sub,
    )
    from task_env.runtime.sessions.physical_control import compile_physical_control_binding
    old, context, effort, _ = _case(); scene = _scene_v3()
    root = _assembly(scene,'two-subjects',(
        _entity_member('arm',path=('arm-owner',)), _entity_member('hand',path=('hand-owner',)),
        _sub(('arm-joint',),JointReference('arm','drive'),'joint'),
        _sub(('hand-joint',),JointReference('hand','drive'),'joint'),))
    a=replace(old.binding.channels[0],component_path=('arm-joint',))
    b=replace(a,component_path=('hand-joint',),entity_id='hand',axis_frame=FrameReference('hand','base'),
              native_actuator='native-b',transmission_id='direct-b',owner_ids=('controller-b',))
    binding=replace(old.binding,scene_sha256=scene.identity_hash,
                    logical_assembly_sha256=root.logical_content_sha256,channels=(a,b))
    plan=compile_physical_control_binding(scene,root,{},binding)
    first=ControlledSubjectV1('first','arm','source-a','b'*64,'owns_source','fixed',
                              FrameReference('arm','base'),None,(('arm-joint',),),('controller-a',))
    identity=PoseWorld((0.,0.,0.),(1.,0.,0.,0.))
    attachment=FixedAttachmentPlanV1('fixed-attachment-plan-v1',root.assembly_id,root.revision,
        root.logical_content_sha256,root.scene_pin,'arm','hand','robot/shared','v1','robot/shared','v1',
        'c'*64,'d'*64,'e'*64,'b'*64,FrameReference('arm','base'),FrameReference('hand','base'),
        FrameReference('arm','tool'),FrameReference('hand','base'),'mount-site','hand-body',
        identity,identity,'hand-ns','fixed_child_root_under_parent_mount_no_free_joint',
        'source_preserved',.04,(),{'arm/base':'arm-body','hand/base':'hand-body'},
        {'arm/tool':'mount-site'},{'arm/drive':'joint-a'},{'arm/drive':'actuator-a'}, {})
    second=ControlledSubjectV1('second','hand','source-a','b'*64,'references_existing','constrained',
                               FrameReference('hand','base'),'first',(('hand-joint',),),('controller-b',),
                               attachment_plan=attachment)
    def controller(identity,writer,entity):
        joint=effort(identity,1.0)
        joint=replace(joint,entity_id=entity,axis_frame=FrameReference(entity,'base'),
                      contribution=replace(joint.contribution,owner_id=writer))
        return SimpleNamespace(binding=binding,identity=identity,writer_id=writer,action_shape=(1,),
            compute=lambda action,view,ctx: PhysicalCommandBatchV1('physical-command-batch-v1',ctx,
                (replace(joint,context=ctx,value=float(action[0])),),(),()))
    ca,cb=controller('input-a','controller-a','arm'),controller('input-b','controller-b','hand')
    requirements=StateRequirements('state-requirements-v1','controller','both',())
    execution=PhysicalControlExecutionV1(plan,(ca,cb),scene,{}, {},requirements,1,(first,second))
    batch=execution.controller_batch({'input-a':[1.0],'input-b':[2.0]},None,context)
    assert [(v.entity_id,v.value) for v in batch.joint_efforts] == [('arm',1.0),('hand',2.0)]
    with pytest.raises(ValueError,match='parent cycle'):
        validate_controlled_subjects(plan,(replace(first,root_mode='constrained',parent_subject_id='second'),second),(ca,cb))
    with pytest.raises(ValueError,match='source-bound attachment'):
        validate_controlled_subjects(plan,(first,replace(second,attachment_plan=None)),(ca,cb))


def test_two_controllers_conflict_is_rejected_after_subject_dispatch():
    from task_env.diagnostics.tasks.test_v211_physical_control_contract import _joint_receipt
    from task_env.runtime.sessions.physical_control import compile_physical_control_binding, prepare_physical_command_batch
    old, context, effort, assessment = _case()
    channel=replace(old.binding.channels[0],owner_ids=('controller-a','controller-b'))
    binding=replace(old.binding,channels=(channel,))
    plan=compile_physical_control_binding(old.scene,old.root,old.children,binding)
    subject=ControlledSubjectV1('subject','arm','source-a','b'*64,'references_existing','fixed',
        FrameReference('arm','base'),None,(('robot','arm-drive-joint'),),('controller-a','controller-b'))
    def make_controller(identity, writer, composition):
        item=effort(identity,1.0,composition)
        item=replace(item,contribution=replace(item.contribution,owner_id=writer))
        return SimpleNamespace(binding=binding,identity=identity,writer_id=writer,action_shape=(1,),
            compute=lambda action,view,ctx: PhysicalCommandBatchV1('physical-command-batch-v1',ctx,
                (replace(item,context=ctx),),(),()))
    ca=make_controller('a','controller-a','exclusive');cb=make_controller('b','controller-b','sum')
    req=StateRequirements('state-requirements-v1','controller','subject',())
    execution=PhysicalControlExecutionV1(plan,(ca,cb),plan.scene,{}, {},req,1,(subject,))
    batch=execution.controller_batch({'a':[1.],'b':[1.]},None,context)
    prior=assessment('joint_effort','sum')
    admit=replace(prior,request_identity=binding.identity_hash,
        rows=tuple(replace(row,object_ref=f'binding:{binding.identity_hash}') for row in prior.rows))
    with pytest.raises(ValueError,match='declared sum'):
        prepare_physical_command_batch(plan,batch,expected_context=context,
            assessment=admit,joint_build_receipt=_joint_receipt(plan,context))


def test_task_subject_declarations_preserve_hinge_and_wheel_order():
    from task_env.robots.pendulum import PendulumEntity
    from task_env.robots.two_wheel_balance import TwoWheelBalanceEntity
    plan, _, _, _ = _case(); template=plan.binding.channels[0]
    hinge=replace(template,joint_id='pendulum_hinge',native_actuator='pendulum_torque',
                  effort_range=(-2.,2.),native_range=(-2.,2.))
    pendulum=replace(plan.binding,channels=(hinge,))
    declaration=PendulumEntity().controlled_subject(binding=pendulum,entity_id='arm',
        root_frame='base',controller_writer='controller-a')
    assert declaration.channel_paths == (hinge.component_path,)
    left=replace(template,component_path=('left',),joint_id='left_wheel_hinge',
                 native_actuator='left_wheel_torque',transmission_id='left-drive',
                 effort_range=(-1.5,1.5),native_range=(-1.5,1.5))
    right=replace(left,component_path=('right',),joint_id='right_wheel_hinge',
                  native_actuator='right_wheel_torque',transmission_id='right-drive')
    wheel=replace(plan.binding,channels=(left,right))
    declaration=TwoWheelBalanceEntity().controlled_subject(binding=wheel,entity_id='arm',
        root_frame='base',controller_writer='controller-a')
    assert declaration.channel_paths == (('left',),('right',))
    with pytest.raises(ValueError,match='ordered left/right'):
        TwoWheelBalanceEntity().controlled_subject(binding=replace(wheel,channels=(right,left)),
            entity_id='arm',root_frame='base',controller_writer='controller-a')


def test_known_usd_task_rgb_source_boundary_remains_explicit(monkeypatch):
    """Record current rejection; this is not an Isaac SDK or RGB success."""
    from task_env.environment.reference_env import SelectedReferenceEnv
    from task_env.runtime.sessions import source as source_module
    from task_env.runtime.sessions.source import UsdRuntimeSourceV1
    source=object.__new__(UsdRuntimeSourceV1)
    object.__setattr__(source,'scene_definition',object())
    object.__setattr__(source,'scene_source',SimpleNamespace(source_closure_sha256='0'*64))
    env=SimpleNamespace(_task_rgb_config=(object(),'isaacsim'),value={'source':source},
                        artifact=SimpleNamespace(identity_hash='1'*64))
    monkeypatch.setattr(source_module,'position_joint_bindings_from_artifact',lambda *_:{})
    monkeypatch.setattr(source_module,'position_frame_bindings_from_artifact',lambda *_:{})
    with pytest.raises(TypeError,match='dynamic render source requires RuntimeSource'):
        SelectedReferenceEnv._prepare_task_rgb_state_binding(env)


def test_component_resolver_delegates_existing_panda_layout_to_subject():
    import numpy as np
    from task_env.robots.panda import PandaAgent
    from task_env.environment import ReferenceSpec
    from task_env.assembly.references import resolve_task_references
    panda=PandaAgent(); spec=panda.reference_spec()
    item=lambda name:SimpleNamespace(name=name)
    links=[SimpleNamespace(name=name,joints=[],sites=[]) for name in spec.body_names]
    links[0].joints=[item(name) for name in spec.joint_names]
    links[0].sites=[item(name) for name in spec.site_names]
    loader=SimpleNamespace(links=links,actuators=[item(name) for name in spec.actuator_names])
    model=SimpleNamespace(joint_data={'jnt_qposadr':np.arange(len(spec.joint_names)),
        'jnt_dofadr':np.arange(len(spec.joint_names)),
        'actuator_ctrlrange':np.zeros((len(spec.actuator_names),2)), 'geom_names':()})
    scene=SimpleNamespace(uid='empty-scene',reference_spec=lambda:ReferenceSpec())
    refs=resolve_task_references(loader_result=loader,scene_model=model,scene=scene,agents=(panda,),objects=())
    result=refs.agents[panda.uid]
    assert result.arm_joint_ids.tolist()==list(range(7))
    assert result.gripper_joint_ids.tolist()==[7,8]
    assert result.arm_actuator_ids.tolist()==list(range(7))
    assert result.gripper_actuator_ids.tolist()==[7]
    assert result.base_body_name=='link0' and result.eef_site_name=='nutassembly_ee_site'


def test_subject_root_mode_is_rechecked_against_runtime_source():
    execution, subject, _ = _fixture()
    execution=replace(execution,joint_bindings={'arm/drive':object()})
    source=SimpleNamespace(joints={'arm/drive':'hinge'},free_joints={},bodies={},frames={})
    execution.validate_source(scene=execution.scene,artifact_sha256='a'*64,
        source_id='source-a',source_closure_sha256='b'*64,source=source)
    source.joints={};source.free_joints={'arm/drive':'free'}
    with pytest.raises(ValueError,match='root mode differs'):
        execution.validate_source(scene=execution.scene,artifact_sha256='a'*64,
            source_id='source-a',source_closure_sha256='b'*64,source=source)
