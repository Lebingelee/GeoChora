"""Current provider-free physical-control contracts and fake adapter checks."""
from dataclasses import replace
import pytest

from task_env.artifacts import FrameReference
from task_env.artifacts.contracts import CapabilityAssessmentRowV1, CapabilityAssessmentV1
from task_env.artifacts.state import StateBoundaryIdentity, StateSampleClock
from task_env.controllers.canonical.physical_commands import (
    PhysicalCommandBatchV1, PhysicalControlBindingV1, PhysicalCommandContextV1,
    ContributionPolicyV1, JointEffortV1, PhysicalJointChannelV1, PhysicalJointBuildReceiptV1,
)
from task_env.runtime.sessions.physical_control import (
    compile_physical_control_binding, prepare_physical_command_batch,
)
from task_env.diagnostics.tasks.physical_contract_fixtures import _case, _joint_receipt, _scene_v3, _primary_closure

def test_nested_binding_explicit_sum_and_stale_rejected():
    plan, context, effort, assessment = _case()
    batch = PhysicalCommandBatchV1('physical-command-batch-v1', context,
                                    (effort('force-a', 1.25), effort('force-b', 2.0)), (), ())
    resolved = prepare_physical_command_batch(plan, batch, expected_context=context,
                                               assessment=assessment('joint_effort', 'sum'), joint_build_receipt=_joint_receipt(plan,context))
    assert resolved.joints[0].value == pytest.approx(3.25, abs=1e-12)
    assert resolved.accepted_receipt.stage == 'accepted'
    with pytest.raises(ValueError, match='stale or foreign'):
        prepare_physical_command_batch(plan, batch, expected_context=replace(context, generation=2),
                                       assessment=assessment('joint_effort', 'sum'), joint_build_receipt=_joint_receipt(plan,context))
    conflict = replace(batch, joint_efforts=(effort('force-a', 1, 'exclusive'), effort('force-b', 1)))
    with pytest.raises(ValueError, match='declared sum'):
        prepare_physical_command_batch(plan, conflict, expected_context=context,
                                       assessment=assessment('joint_effort', 'sum'), joint_build_receipt=_joint_receipt(plan,context))


def test_scene_physical_explicit_sum_and_duplicate_effect_admission():
    from types import SimpleNamespace
    from task_env.artifacts.state import StateRequirements
    from task_env.runtime.sessions.control_submission import prepare_physical_scene_interval
    from task_env.runtime.sessions.physical_control import PhysicalControlExecutionV1

    plan, context, effort, assessment = _case()
    controller = SimpleNamespace(identity='controller-identity', writer_id='controller-a',
                                 binding=plan.binding, compute=lambda *_: None)
    execution = PhysicalControlExecutionV1(plan, (controller,), plan.scene, {}, {},
        StateRequirements('state-requirements-v1', 'controller', 'controller-a', ()), 1)
    session = SimpleNamespace(_physical_port=SimpleNamespace(execution=execution),
        _physical_controller_versions=execution.controller_versions(),
        physical_control_generation=1, _artifact=SimpleNamespace(
            timebase=SimpleNamespace(control_substeps=5, physics_dt=.002, control_dt=.01)))
    batch = PhysicalCommandBatchV1('physical-command-batch-v1', context,
        (effort('force-a', 1.25), effort('force-b', 2.0)), (), ())
    resolved = prepare_physical_command_batch(plan, batch, expected_context=context,
        assessment=assessment('joint_effort', 'sum'), joint_build_receipt=_joint_receipt(plan, context))
    # Synthetic fixture explicitly mocks the native-build marker; no native
    # capability is claimed by this contract test.
    resolved = replace(resolved, mapping_provenance=('native_build',))
    interval = prepare_physical_scene_interval(session=session, execution=execution, resolved=resolved)
    assert [item.composition for item in interval.contributions] == ['sum', 'sum']
    assert [item.physical_effect_id for item in interval.contributions] == ['force-a', 'force-b']
    assert all(item.controller_generation is None for item in interval.contributions)
    controller.generation = 7
    with pytest.raises(ValueError, match='versions differ from materialization'):
        prepare_physical_scene_interval(session=session, execution=execution, resolved=resolved)
    session._physical_controller_versions = execution.controller_versions()
    assert all(item.controller_generation == 7 for item in
               prepare_physical_scene_interval(session=session, execution=execution, resolved=resolved).contributions)
    duplicate = replace(batch.joint_efforts[1], contribution=replace(
        batch.joint_efforts[1].contribution, physical_effect_id='force-a'))
    bad_batch = replace(batch, joint_efforts=(batch.joint_efforts[0], duplicate))
    forged = replace(resolved, input_batch=bad_batch,
                     accepted_receipt=replace(resolved.accepted_receipt, batch_sha256=bad_batch.identity_hash))
    with pytest.raises(ValueError, match='duplicate effect'):
        prepare_physical_scene_interval(session=session, execution=execution, resolved=forged)
    foreign = replace(batch.joint_efforts[0], contribution=replace(
        batch.joint_efforts[0].contribution, owner_id='foreign-writer'))
    bad_batch = replace(batch, joint_efforts=(foreign, batch.joint_efforts[1]))
    forged = replace(resolved, input_batch=bad_batch,
                     accepted_receipt=replace(resolved.accepted_receipt, batch_sha256=bad_batch.identity_hash))
    with pytest.raises(ValueError, match='not an admitted Controller'):
        prepare_physical_scene_interval(session=session, execution=execution, resolved=forged)
    wrong_axis = replace(batch.joint_efforts[0], axis=(1., 0., 0.))
    bad_batch = replace(batch, joint_efforts=(wrong_axis, batch.joint_efforts[1]))
    forged = replace(resolved, input_batch=bad_batch,
                     accepted_receipt=replace(resolved.accepted_receipt, batch_sha256=bad_batch.identity_hash))
    with pytest.raises(ValueError, match='differs from its bound channel'):
        prepare_physical_scene_interval(session=session, execution=execution, resolved=forged)


def test_binding_roundtrip_and_unknown_capability_fail_closed():
    plan, context, effort, assessment = _case()
    assert PhysicalControlBindingV1.from_mapping(plan.binding.to_mapping()) == plan.binding
    batch = PhysicalCommandBatchV1('physical-command-batch-v1', context, (effort('force-a', 1),), (), ())
    with pytest.raises(ValueError, match='build mapping receipt'):
        prepare_physical_command_batch(plan, batch, expected_context=context, assessment=assessment('joint_effort'))
    with pytest.raises(ValueError, match='incomplete'):
        prepare_physical_command_batch(plan, batch, expected_context=context, assessment=assessment(), joint_build_receipt=_joint_receipt(plan,context))
    assert PhysicalCommandBatchV1.from_mapping(batch.to_mapping()) == batch


def test_synthetic_mapping_is_never_native_build_evidence():
    plan, context, effort, assessment = _case()
    batch = PhysicalCommandBatchV1('physical-command-batch-v1', context,
                                   (effort('force-a', 1),), (), ())
    declared = assessment('joint_effort', 'sum')
    result = prepare_physical_command_batch(plan, batch, expected_context=context,
        assessment=declared, joint_build_receipt=_joint_receipt(plan, context))
    assert result.mapping_provenance == ('synthetic_fixture',)
    native = replace(declared, phase='native_build',
                     rows=tuple(replace(row, phase='native_build') for row in declared.rows))
    with pytest.raises(ValueError, match='synthetic mapping cannot support'):
        prepare_physical_command_batch(plan, batch, expected_context=context,
            assessment=native, joint_build_receipt=_joint_receipt(plan, context))


def test_mujoco_physical_port_rechecks_resolved_values_and_duplicate():
    """A synthetic port tests rejection only; it is not native evidence."""
    import numpy as np
    from types import SimpleNamespace
    from task_env.runtime.sessions.mujoco_physical import MuJoCoPhysicalPort

    plan, context, effort, _ = _case()
    batch = PhysicalCommandBatchV1('physical-command-batch-v1', context,
                                   (effort('force-a', 1),), (), ())
    data = SimpleNamespace(qfrc_applied=np.zeros(1), xfrc_applied=np.zeros((1, 6)))
    session = SimpleNamespace(_require_open=lambda: None, _require_reset=lambda: None,
        state_boundary_identity=lambda: context.boundary,
        snapshot_v2=lambda **kwargs: SimpleNamespace(view=SimpleNamespace(
            boundary=context.boundary, sample_clock=context.clock)),
        _artifact=SimpleNamespace(timebase=SimpleNamespace(control_dt=.01)),
        _data=data, _model=SimpleNamespace(nv=1), provider_materialization_id='material-a')
    port = object.__new__(MuJoCoPhysicalPort)
    port.session, port.binding = session, plan.binding
    port.execution = SimpleNamespace(compiled=plan, scene=plan.scene, generation=1,
                                      joint_bindings={}, frame_bindings={}, requirements=None)
    port.dofs, port.bodies = {plan.binding.channels[0].target_key: 0}, {}
    port.equality_ids = ()
    port.pending, port.pending_values, port.consumed = None, None, set()
    admitted = prepare_physical_command_batch(plan, batch, expected_context=context,
        assessment=port.assessment(plan.binding), joint_build_receipt=port.joints(plan.binding))
    forged = replace(admitted, joints=(replace(admitted.joints[0], value=2.),))
    with pytest.raises(ValueError, match='independent session admission'):
        port.write(forged)
    assert data.qfrc_applied[0] == 0
    ack = port.write(admitted)
    assert ack.stage == 'native_write_ack' and data.qfrc_applied[0] == 1
    with pytest.raises(ValueError, match='stale, duplicated or already pending'):
        port.write(admitted)
    port.finish_interval()
    assert data.qfrc_applied[0] == 0
    with pytest.raises(ValueError, match='stale, duplicated or already pending'):
        port.write(admitted)
    port.consumed.clear()
    port.equality_ids = (0,)
    data.eq_active = np.array([0])
    with pytest.raises(ValueError, match='equality is not active'):
        port.write(admitted)
    assert data.qfrc_applied[0] == 0
    port.equality_ids = ()
    def concurrent_write(*args):
        data.qfrc_applied[0] = 7.
        return np.array([1.])
    port._project_current = concurrent_write
    with pytest.raises(RuntimeError, match='changed before owned write'):
        port.write(admitted)
    assert data.qfrc_applied[0] == 7. and port.pending is None


def test_mujoco_physical_interval_clears_buffer_on_advance_failure():
    """Exercise the adapter's failure cleanup without a native model."""
    import numpy as np
    from types import SimpleNamespace
    from task_env.runtime.sessions.mujoco import _MuJoCoSession
    from task_env.runtime.sessions.mujoco_physical import MuJoCoPhysicalPort

    session = object.__new__(_MuJoCoSession)
    session._require_reset = lambda: None
    session._artifact = SimpleNamespace(timebase=SimpleNamespace(control_substeps=5))
    session._model, session._data = object(), SimpleNamespace(qfrc_applied=np.array([1.]), xfrc_applied=np.zeros((1, 6)))
    def fail_step(*args):
        raise RuntimeError('simulated native step failure')
    session._mj = SimpleNamespace(mj_step=fail_step)
    port = object.__new__(MuJoCoPhysicalPort)
    port.session, port.pending, port.pending_values = session, 'boundary', np.array([1.])
    port.pending_joints, port.pending_wrenches = np.array([1.]), ()
    session._physical_port = port
    with pytest.raises(RuntimeError, match='simulated native step failure'):
        session.step()
    assert session._data.qfrc_applied[0] == 0
    assert port.pending is None and port.pending_values is None


def test_mujoco_physical_build_mapping_checks_axis_gear_and_drive():
    """Synthetic compiled layout detects changed source mappings before writing."""
    import numpy as np
    from types import SimpleNamespace
    from task_env.artifacts.state import StateRequirements
    from task_env.runtime.sessions.mujoco_physical import MuJoCoPhysicalPort
    from task_env.runtime.sessions.physical_control import PhysicalControlExecutionV1

    original, _, _, _ = _case()
    binding = replace(original.binding, channels=(replace(original.binding.channels[0], native_drive='position'),))
    plan = compile_physical_control_binding(original.scene, original.root, original.children, binding)
    controller = SimpleNamespace(binding=binding, compute=lambda *args: None,
                                  identity='controller-test', writer_id='controller-a', action_shape=(1,))
    execution = PhysicalControlExecutionV1(plan, (controller,), plan.scene, {'arm/drive': object()}, {},
        StateRequirements('state-requirements-v1', 'controller', 'controller-a', ()), 1)
    source = SimpleNamespace(scene_definition=plan.scene, source_id='source-a',
        source_closure_digest='b'*64, joints={'arm/drive': 'native-joint'}, free_joints={}, bodies={}, frames={})
    model = SimpleNamespace(joint=lambda name: SimpleNamespace(id=0), actuator=lambda name: SimpleNamespace(id=0),
        jnt_type=np.array([3]), jnt_axis=np.array([[0., 0., 1.]]), jnt_dofadr=np.array([0]),
        actuator_forcelimited=np.array([1]), actuator_forcerange=np.array([[-5., 5.]]),
        actuator_gear=np.array([[1., 0., 0., 0., 0., 0.]]), actuator_biastype=np.array([1]),
        actuator_gaintype=np.array([0]), actuator_dyntype=np.array([0]),
        actuator_gainprm=np.array([[1.]]), actuator_biasprm=np.array([[0., -1., 0.]]),
        actuator_trntype=np.array([0]), actuator_trnid=np.array([[0, -1]]))
    mj = SimpleNamespace(mjtJoint=SimpleNamespace(mjJNT_HINGE=3, mjJNT_SLIDE=2),
        mjtBias=SimpleNamespace(mjBIAS_AFFINE=1), mjtGain=SimpleNamespace(mjGAIN_FIXED=0),
        mjtDyn=SimpleNamespace(mjDYN_NONE=0), mjtTrn=SimpleNamespace(mjTRN_JOINT=0, mjTRN_TENDON=3))
    session = SimpleNamespace(_source=source, _artifact=SimpleNamespace(identity_hash='a'*64),
        _provider='mujoco', _mixed_actuator_plan=None, _model=model, _mj=mj)
    assert MuJoCoPhysicalPort(session, execution).dofs[binding.channels[0].target_key] == 0
    model.jnt_axis[0] = (0., 1., 0.)
    with pytest.raises(ValueError, match='joint axis'):
        MuJoCoPhysicalPort(session, execution)
    model.jnt_axis[0] = (0., 0., 1.)
    model.actuator_gear[0, 0] = 2.
    with pytest.raises(ValueError, match='range, gear or position drive'):
        MuJoCoPhysicalPort(session, execution)
    model.actuator_gear[0, 0] = 1.
    model.actuator_biasprm[0, 1] = 0.
    with pytest.raises(ValueError, match='range, gear or position drive'):
        MuJoCoPhysicalPort(session, execution)
    # A valid body binding must reject an unverified RK4 model before write.
    from task_env.controllers.canonical.physical_commands import PhysicalBodyBindingV1
    model.actuator_biasprm[0, 1] = -1.
    body = PhysicalBodyBindingV1('physical-body-binding-v1', 'arm', 'base',
                                FrameReference('arm','base'), 'native-body', ('controller-a',))
    body_binding = replace(binding, bodies=(body,))
    body_plan = compile_physical_control_binding(original.scene, original.root, original.children, body_binding)
    controller.binding = body_binding
    source.bodies = {'arm/base': 'native-body'}
    model.body = lambda name: SimpleNamespace(id=1)
    model.opt = SimpleNamespace(integrator=1)
    mj.mjtIntegrator = SimpleNamespace(mjINT_IMPLICITFAST=3)
    body_execution = PhysicalControlExecutionV1(body_plan, (controller,), body_plan.scene,
        {'arm/drive': object()}, {'arm/base': FrameReference('arm','base')},
        StateRequirements('state-requirements-v1', 'controller', 'controller-a', ()), 1)
    with pytest.raises(ValueError, match='implicitfast integrator'):
        MuJoCoPhysicalPort(session, body_execution)
    # The isolated fixture must set the provider's actuation-disable bit,
    # without changing tendon/equality declarations or the original XML.
    session._artifact.artifact_id = 'pickcube-mjcf-physical-effort-no-drive-v1'
    session._build_layout_facts = {}
    model.opt = SimpleNamespace(disableflags=0)
    model.nu = 2  # One undeclared native actuator must prevent global isolation.
    mj.mjtDisableBit = SimpleNamespace(mjDSBL_ACTUATION=4)
    controller.binding = original.binding
    source.bodies, source.frames = {}, {}
    isolated = PhysicalControlExecutionV1(original, (controller,), original.scene,
        {'arm/drive': object()}, {}, StateRequirements('state-requirements-v1', 'controller', 'controller-a', ()), 1)
    with pytest.raises(ValueError, match='every actuator to be declared'):
        MuJoCoPhysicalPort(session, isolated)
    assert model.opt.disableflags == 0
    model.nu = 1
    MuJoCoPhysicalPort(session, isolated)
    assert model.opt.disableflags == 4
    assert session._build_layout_facts['physical_drive_override']['source_mjcf_modified'] is False


def test_mujoco_physical_preflight_rejects_missing_or_wrong_dependency(monkeypatch):
    """Preflight checks dependency metadata without importing the native SDK."""
    from importlib import metadata
    from types import SimpleNamespace
    from task_env.environment.types import StageUnavailableError
    from task_env.runtime.sessions.mujoco_physical import preflight_physical_mujoco
    from task_env.runtime.sessions.physical_control import PhysicalControlExecutionV1

    execution = object.__new__(PhysicalControlExecutionV1)
    calls = []
    monkeypatch.setattr(PhysicalControlExecutionV1, 'validate_source', lambda self, **kwargs: calls.append(kwargs))
    artifact = SimpleNamespace(identity_hash='a'*64)
    source = SimpleNamespace(scene_definition=object(), source_id='source-a', source_closure_digest='b'*64)
    monkeypatch.setattr(metadata, 'version', lambda name: '3.8.1')
    preflight_physical_mujoco(execution, artifact, source)
    assert calls[-1]['source'] is source
    monkeypatch.setattr(metadata, 'version', lambda name: '9.0')
    with pytest.raises(StageUnavailableError, match='3.8.1'):
        preflight_physical_mujoco(execution, artifact, source)
    def absent(name):
        raise metadata.PackageNotFoundError(name)
    monkeypatch.setattr(metadata, 'version', absent)
    with pytest.raises(StageUnavailableError, match='dependency is unavailable'):
        preflight_physical_mujoco(execution, artifact, source)


@pytest.mark.parametrize('drive', ['position', 'implicit_pd', 'unknown'])
def test_explicit_pd_rejects_uncoordinated_native_drive(drive):
    original, context, effort, assessment = _case()
    binding = replace(original.binding, channels=(replace(original.binding.channels[0], native_drive=drive),))
    plan = compile_physical_control_binding(original.scene, original.root, original.children, binding)
    old = assessment('joint_effort', 'sum')
    capability = replace(old, request_identity=binding.identity_hash,
        rows=tuple(replace(row, object_ref=f'binding:{binding.identity_hash}') for row in old.rows))
    command = replace(effort('full-pd', 1.), controller_law='explicit_full_pd')
    batch = PhysicalCommandBatchV1('physical-command-batch-v1', context, (command,), (), ())
    with pytest.raises(ValueError, match='uncoordinated native drive'):
        prepare_physical_command_batch(plan, batch, expected_context=context,
            assessment=capability, joint_build_receipt=_joint_receipt(plan, context))


def test_explicit_pd_with_disabled_native_drive_is_admitted():
    plan, context, effort, assessment = _case()
    command = replace(effort('full-pd', 1.), controller_law='explicit_full_pd')
    batch = PhysicalCommandBatchV1('physical-command-batch-v1', context, (command,), (), ())
    result = prepare_physical_command_batch(plan, batch, expected_context=context,
        assessment=assessment('joint_effort', 'sum'), joint_build_receipt=_joint_receipt(plan, context))
    assert result.joints[0].value == 1.


def test_wrench_fixed_oracle_uses_frame_and_offset_without_provider():
    from math import sqrt
    from task_env.artifacts.contracts import PoseWorld
    from task_env.artifacts.state import CanonicalStateViewV2, TypedFrameStateValue
    from task_env.controllers.canonical.physical_commands import BodyWrenchV1, PhysicalBodyBindingV1, PhysicalBodyBuildReceiptV1
    scene = _scene_v3()
    root, _, _, _, catalog = _primary_closure(scene)
    body = PhysicalBodyBindingV1('physical-body-binding-v1', 'arm', 'tool-body',
                                 FrameReference('arm', 'base'), 'native-body', ('caller',))
    binding = PhysicalControlBindingV1('physical-control-binding-v1', scene.identity_hash,
        'a'*64, 'source-a', 'b'*64, root.logical_content_sha256, (), (body,))
    plan = compile_physical_control_binding(scene, root, catalog, binding)
    boundary = StateBoundaryIdentity('state-boundary-identity-v1', 'episode-a',
        'reset-'+'d'*64, scene.identity_hash, 'instance-a', 'material-a', 0, 0)
    clock = StateSampleClock('state-sample-clock-v1', 'evaluation_boundary', 0, 0.)
    context = PhysicalCommandContextV1('physical-command-context-v1', 'source-a',
        'b'*64, 'a'*64, boundary, clock, 0, 1, .01, .01)
    state = CanonicalStateViewV2('canonical-state-v2', 'SI_right_handed_z_up_wxyz',
        boundary, clock, (), (
            TypedFrameStateValue('typed-frame-state-v1', FrameReference('arm','base'),
                                 PoseWorld((0,0,0), (1,0,0,0))),
            TypedFrameStateValue('typed-frame-state-v1', FrameReference('arm','tool'),
                                 PoseWorld((0,0,0), (sqrt(.5),0,0,sqrt(.5)))),
        ), ())
    policy = ContributionPolicyV1('physical-contribution-policy-v1', 'load-a', 'effect-a',
                                   'caller', 'exclusive', 'reject_outside', 'one_interval')
    wrench = BodyWrenchV1('body-wrench-v1', context, policy, 'arm', 'tool-body',
        FrameReference('arm','tool'), (1,0,0), FrameReference('arm','base'),
        (1,0,0), FrameReference('arm','base'), (1,0,0), (0,0,0))
    batch = PhysicalCommandBatchV1('physical-command-batch-v1', context, (), (wrench,), ())
    caps = ('body_force', 'body_torque', 'body_frame', 'body_offset_point')
    assessment = CapabilityAssessmentV1('capability-assessment-v1', binding.identity_hash,
        'static_preflight', tuple(CapabilityAssessmentRowV1('capability-assessment-row-v1', c,
        f'binding:{binding.identity_hash}', 'required', 'supported', 'implemented', 'available',
        'none', 'static_preflight', 'synthetic test declaration', None, None) for c in caps))
    body_receipt = PhysicalBodyBuildReceiptV1('physical-body-build-receipt-v1', binding.identity_hash,
        'b'*64, 'material-a', (body,), 'synthetic_fixture')
    result = prepare_physical_command_batch(plan, batch, expected_context=context,
        assessment=assessment, state=state, body_build_receipt=body_receipt)
    assert result.body_wrenches[0].force_world_N == pytest.approx((0, 1, 0), abs=1e-12)
    assert result.body_wrenches[0].torque_at_body_origin_world_Nm == pytest.approx((0, 0, 1), abs=1e-12)
    with pytest.raises(ValueError, match='frame state is stale'):
        stale = replace(state, boundary=replace(boundary, state_revision=1))
        prepare_physical_command_batch(plan, batch, expected_context=context,
                                       assessment=assessment, state=stale, body_build_receipt=body_receipt)
    # Reference differs from point: torque is about reference, not the point.
    shifted = replace(wrench, point=(0, 0, 0), moment_reference=(1, 0, 0))
    shifted_batch = replace(batch, body_wrenches=(shifted,))
    shifted_result = prepare_physical_command_batch(plan, shifted_batch, expected_context=context,
        assessment=assessment, state=state, body_build_receipt=body_receipt)
    assert shifted_result.body_wrenches[0].torque_at_body_origin_world_Nm == pytest.approx((0, 0, 1), abs=1e-12)
    with pytest.raises(ValueError, match='build mapping receipt'):
        prepare_physical_command_batch(plan, batch, expected_context=context, assessment=assessment, state=state)

def test_pure_controller_consumes_named_state_and_replaceable_model():
    from task_env.artifacts.state import CanonicalStateViewV2, TypedJointStateValue, StateRequirements
    from task_env.controllers.canonical.model import ControllerModelRequirementV1, AffineJointBiasModelV1
    from task_env.controllers.canonical.physical_controller import LinearEffortProfileV1, LinearEffortControllerV1
    plan, context, _, assessment = _case()
    requirement = ControllerModelRequirementV1('controller-model-requirement-v1',
        'affine-example', 'geochora', 'v1', 'stdlib', 'source-a', 'b'*64,
        ('arm/drive',), ('rad',), 'joint_bias', ('N*m',), 'joint-axis',
        'evaluation_boundary', .01, 0., 'pure_no_physics_step', 'controller-a',
        'none', 'required')
    model = AffineJointBiasModelV1('affine-joint-bias-model-v1', requirement,
                                   (0.5,), (2.,), (3.,))
    profile = LinearEffortProfileV1('linear-effort-profile-v1', 'controller-a',
        ('action',), ('arm/drive',), ((4.,),), requirement)
    controller = LinearEffortControllerV1(profile, plan.binding, model)
    from task_env.runtime.sessions.physical_control import PhysicalControlExecutionV1
    execution = PhysicalControlExecutionV1(plan, (controller,), plan.scene, {}, {},
        StateRequirements('state-requirements-v1', 'controller', 'controller-a', ()), 1)
    execution.validate_source(scene=plan.scene, artifact_sha256='a'*64,
                              source_id='source-a', source_closure_sha256='b'*64)
    assert execution.action_space().shape == (1,)
    with pytest.raises(ValueError, match='Scene, Artifact, or source'):
        execution.validate_source(scene=plan.scene, artifact_sha256='a'*64,
                                  source_id='foreign', source_closure_sha256='b'*64)
    from types import SimpleNamespace
    source = SimpleNamespace(joints={'arm/drive': 'native'}, free_joints={}, bodies={}, frames={})
    with pytest.raises(ValueError, match='exactly cover selected source names'):
        execution.validate_source(scene=plan.scene, artifact_sha256='a'*64,
            source_id='source-a', source_closure_sha256='b'*64, source=source)
    joint = TypedJointStateValue('typed-joint-state-v1', 'arm', 'drive', 'revolute',
        'radian', (.1,), 'radian_per_second', (.2,))
    state = CanonicalStateViewV2('canonical-state-v2', 'SI_right_handed_z_up_wxyz',
        context.boundary, context.clock, (joint,), (), ())
    batch = controller.compute((.25,), state, context)
    # 4*.25 + (.5 + 2*.1 + 3*.2) = 2.3 N*m.
    assert batch.joint_efforts[0].value == pytest.approx(2.3, abs=1e-12)
    resolved = prepare_physical_command_batch(plan, batch, expected_context=context,
                                               assessment=assessment('joint_effort'), joint_build_receipt=_joint_receipt(plan,context))
    assert resolved.joints[0].value == pytest.approx(2.3, abs=1e-12)
    with pytest.raises(ValueError, match='state is stale'):
        controller.compute((.25,), state, replace(context, boundary=replace(context.boundary, state_revision=1)))
    with pytest.raises(ValueError, match='model cadence'):
        controller.compute((.25,), state, replace(context, cadence_s=.02))

def test_reconstructed_invalid_binding_cannot_bypass_scene_resolution():
    from task_env.runtime.sessions.physical_control import CompiledPhysicalBindingV1
    plan, context, effort, assessment = _case()
    invalid_channel = replace(plan.binding.channels[0], component_path=('robot','not-a-joint'))
    invalid = replace(plan.binding, channels=(invalid_channel,))
    forged = CompiledPhysicalBindingV1(invalid, plan.scene, plan.root, plan.children)
    batch = PhysicalCommandBatchV1('physical-command-batch-v1',context,(effort('force-a',1),),(),())
    with pytest.raises(ValueError, match='does not resolve'):
        prepare_physical_command_batch(forged,batch,expected_context=context,assessment=assessment('joint_effort'))

def test_numpy_gym_actions_accept_real_values_and_reject_invalid_dtype():
    import numpy as np
    from task_env.artifacts.state import CanonicalStateViewV2, TypedJointStateValue
    from task_env.controllers.canonical.model import ControllerModelRequirementV1, AffineJointBiasModelV1
    from task_env.controllers.canonical.physical_controller import LinearEffortProfileV1, LinearEffortControllerV1
    plan, context, _, _ = _case()
    requirement = ControllerModelRequirementV1('controller-model-requirement-v1','affine-example',
        'geochora','v1','stdlib','source-a','b'*64,('arm/drive',),('rad',),'joint_bias',
        ('N*m',),'joint-axis','evaluation_boundary',.01,0.,'pure_no_physics_step',
        'controller-a','none','required')
    model = AffineJointBiasModelV1('affine-joint-bias-model-v1',requirement,(0.,),(0.,),(0.,))
    profile = LinearEffortProfileV1('linear-effort-profile-v1','controller-a',('action',),
                                     ('arm/drive',),((1.,),),requirement)
    controller = LinearEffortControllerV1(profile,plan.binding,model)
    joint = TypedJointStateValue('typed-joint-state-v1','arm','drive','revolute','radian',(0.,),
                                  'radian_per_second',(0.,))
    state = CanonicalStateViewV2('canonical-state-v2','SI_right_handed_z_up_wxyz',
                                 context.boundary,context.clock,(joint,),(),())
    assert controller.compute(np.array([0.25],dtype=np.float32),state,context).joint_efforts[0].value == .25
    for invalid in (np.array([True]), np.array(['1']), np.array([float('nan')]), np.ones((1,1))):
        with pytest.raises(ValueError, match='shape or finite'):
            controller.compute(invalid,state,context)

def test_hold_extension_duplicate_and_measurement_fail_closed():
    from task_env.controllers.canonical.physical_commands import (BodyWrenchV1,
        PhysicalBufferPolicyV1, PhysicalMeasurementV1, PhysicalControlReceiptV1,
        TypedLoadExtensionV1, require_physical_measurement)
    plan, context, effort, assessment = _case()
    joint = effort('load-a',1.)
    held = replace(joint, contribution=replace(joint.contribution,persistence='hold_reapply'))
    batch = PhysicalCommandBatchV1('physical-command-batch-v1',context,(held,),(),())
    capability = assessment('joint_effort','sum','hold_reapply')
    with pytest.raises(ValueError, match='buffer policy|clear/add or replace'):
        prepare_physical_command_batch(plan,batch,expected_context=context,assessment=capability,
                                       joint_build_receipt=_joint_receipt(plan,context))
    safe = PhysicalBufferPolicyV1('physical-buffer-policy-v1',plan.binding.identity_hash,
                                  'material-a','clear_then_add','each_native_step','clear_before_new_episode')
    result = prepare_physical_command_batch(plan,batch,expected_context=context,assessment=capability,
                                            joint_build_receipt=_joint_receipt(plan,context),buffer_policy=safe)
    assert result.joints[0].value == 1.
    with pytest.raises(ValueError, match='stale or foreign'):
        prepare_physical_command_batch(plan,batch,expected_context=replace(context,generation=2),
            assessment=capability,joint_build_receipt=_joint_receipt(plan,context),buffer_policy=safe)
    with pytest.raises(ValueError, match='buffer operation'):
        replace(safe,operation='add')
    wrench = BodyWrenchV1('body-wrench-v1',context,
        replace(joint.contribution,contribution_id='wrench-a'), 'arm','body-a',
        FrameReference('arm','base'),(0,0,0),FrameReference('arm','base'),
        (0,0,0),FrameReference('arm','base'),(1,0,0),(0,0,0))
    with pytest.raises(ValueError, match='same physical effect'):
        PhysicalCommandBatchV1('physical-command-batch-v1',context,(joint,),(wrench,),())
    with pytest.raises((TypeError,ValueError)):
        replace(wrench,expressed_in=None)
    extension = TypedLoadExtensionV1('typed-load-extension-v1',context,
        replace(joint.contribution,contribution_id='ext-a',physical_effect_id='ext-effect'),
        'example','pressure-v1','required','arm','e'*64,'surface-a',(3,),
        'N',FrameReference('arm','base'),'f'*64)
    extbatch = PhysicalCommandBatchV1('physical-command-batch-v1',context,(),(),(extension,))
    extcap = assessment('load_extension:example/pressure-v1')
    with pytest.raises(ValueError, match='topology is stale'):
        prepare_physical_command_batch(plan,extbatch,expected_context=context,assessment=extcap,topology_sha256='0'*64)
    with pytest.raises(ValueError, match='unknown required'):
        prepare_physical_command_batch(plan,extbatch,expected_context=context,assessment=extcap,topology_sha256='e'*64)
    unavailable = PhysicalMeasurementV1('physical-measurement-v1',context,'load-a','sensor-a',
        'unavailable',(),'N*m',context.clock,'sensor missing')
    assert require_physical_measurement(unavailable,context=context,contribution_id='load-a',required=False).reason == 'sensor missing'
    with pytest.raises(ValueError, match='required physical measurement unavailable'):
        require_physical_measurement(unavailable,context=context,contribution_id='load-a',required=True)
    ack = PhysicalControlReceiptV1('physical-control-receipt-v1',context,'a'*64,'native_write_ack',('load-a',),'adapter','N*m')
    with pytest.raises(ValueError, match='receipt stage'):
        replace(ack,stage='measured')
    with pytest.raises(TypeError, match='typed measurement'):
        require_physical_measurement(ack,context=context,contribution_id='load-a',required=True)
    estimate = replace(unavailable,kind='estimated',value=(1.,),reason=None)
    with pytest.raises(ValueError, match='distinct feedback kinds'):
        require_physical_measurement(estimate,context=context,contribution_id='load-a',required=True)

def test_disjoint_named_controllers_can_form_one_interval():
    from task_env.artifacts import JointReference
    from task_env.artifacts.state import CanonicalStateViewV2, TypedJointStateValue
    from task_env.controllers.canonical.model import ControllerModelRequirementV1, AffineJointBiasModelV1
    from task_env.controllers.canonical.physical_controller import LinearEffortProfileV1, LinearEffortControllerV1
    from task_env.diagnostics.tasks.physical_contract_fixtures import _assembly, _sub, _entity_member
    scene = _scene_v3()
    root = _assembly(scene,'two-controller-root',(
        _entity_member('arm'),_entity_member('hand'),
        _sub(('arm','joint'),JointReference('arm','drive'),'joint'),
        _sub(('hand','joint'),JointReference('hand','drive'),'joint')))
    channels = tuple(PhysicalJointChannelV1('physical-joint-channel-v1',(entity,'joint'),(f'{entity}-controller',),
        entity,'drive','dof0','revolute',(0,0,1),FrameReference(entity,'base'),1,'N*m',(-5,5),
        f'{entity}-actuator',f'{entity}-transmission',1.,(-5,5),'disabled') for entity in ('arm','hand'))
    binding = PhysicalControlBindingV1('physical-control-binding-v1',scene.identity_hash,
        'a'*64,'source-a','b'*64,root.logical_content_sha256,channels)
    plan = compile_physical_control_binding(scene,root,{},binding)
    boundary = StateBoundaryIdentity('state-boundary-identity-v1','episode-a','reset-'+'d'*64,
        scene.identity_hash,'instance-a','material-a',0,0)
    clock = StateSampleClock('state-sample-clock-v1','evaluation_boundary',0,0.)
    context = PhysicalCommandContextV1('physical-command-context-v1','source-a','b'*64,'a'*64,
                                       boundary,clock,0,1,.01,.01)
    state = CanonicalStateViewV2('canonical-state-v2','SI_right_handed_z_up_wxyz',boundary,clock,
        tuple(TypedJointStateValue('typed-joint-state-v1',e,'drive','revolute','radian',(0.,),
                                  'radian_per_second',(0.,)) for e in ('arm','hand')),(),())
    parts = []
    for entity,value in (('arm',1.5),('hand',-2.)):
        owner = f'{entity}-controller'; joint = f'{entity}/drive'
        requirement = ControllerModelRequirementV1('controller-model-requirement-v1','affine-example',
            'geochora','v1','stdlib','source-a','b'*64,(joint,),('rad',),'joint_bias',('N*m',),
            'joint-axis','evaluation_boundary',.01,0.,'pure_no_physics_step',owner,'none','required')
        model = AffineJointBiasModelV1('affine-joint-bias-model-v1',requirement,(0.,),(0.,),(0.,))
        profile = LinearEffortProfileV1('linear-effort-profile-v1',owner,('action',),(joint,),((1.,),),requirement)
        parts.append(LinearEffortControllerV1(profile,binding,model).compute((value,),state,context))
    batch = PhysicalCommandBatchV1('physical-command-batch-v1',context,
        tuple(x for part in parts for x in part.joint_efforts),(),())
    caps = ('joint_effort','transmission','native_drive_state')
    assessment = CapabilityAssessmentV1('capability-assessment-v1',binding.identity_hash,'static_preflight',
        tuple(CapabilityAssessmentRowV1('capability-assessment-row-v1',name,f'binding:{binding.identity_hash}',
        'required','supported','implemented','available','none','static_preflight','synthetic declaration',None,None) for name in caps))
    result = prepare_physical_command_batch(plan,batch,expected_context=context,assessment=assessment,
                                             joint_build_receipt=_joint_receipt(plan,context))
    assert {(x.entity_id,x.value) for x in result.joints} == {('arm',1.5),('hand',-2.)}


@pytest.mark.parametrize('bad_ack', [False, True])
def test_selected_env_production_step_uses_single_fake_session_write(bad_ack):
    """Exercise the real selected step owner; fake I/O never advances physics."""
    from types import SimpleNamespace
    from task_env.artifacts.state import (CanonicalStateViewV2, CanonicalStatePublicationV2,
        StateViewLifetime, StateRequirements, TypedJointStateValue)
    from task_env.controllers.canonical.model import ControllerModelRequirementV1, AffineJointBiasModelV1
    from task_env.controllers.canonical.physical_commands import PhysicalControlReceiptV1
    from task_env.controllers.canonical.physical_controller import LinearEffortProfileV1, LinearEffortControllerV1
    from task_env.environment.reference_env import SelectedReferenceEnv
    from task_env.runtime.sessions.physical_control import PhysicalControlExecutionV1
    plan, context, _, assessment = _case()
    requirement = ControllerModelRequirementV1('controller-model-requirement-v1','affine-example',
        'geochora','v1','stdlib','source-a','b'*64,('arm/drive',),('rad',),'joint_bias',
        ('N*m',),'joint-axis','evaluation_boundary',.01,0.,'pure_no_physics_step',
        'controller-a','none','required')
    model = AffineJointBiasModelV1('affine-joint-bias-model-v1',requirement,(.5,),(2.,),(3.,))
    profile = LinearEffortProfileV1('linear-effort-profile-v1','controller-a',('action',),
                                     ('arm/drive',),((4.,),),requirement)
    controller = LinearEffortControllerV1(profile,plan.binding,model)
    original_compute = controller.compute
    controller.preflight_compute_calls = 0
    def stateful_compute(action, view, context):
        controller.preflight_compute_calls += 1
        return original_compute(action, view, context)
    controller.compute = stateful_compute
    scene = _scene_v3()
    requirements = StateRequirements('state-requirements-v1','controller','controller-a',())
    execution = PhysicalControlExecutionV1(plan,(controller,),scene,{}, {},requirements,1)
    joint = TypedJointStateValue('typed-joint-state-v1','arm','drive','revolute','radian',(.1,),
                                  'radian_per_second',(.2,))
    view = CanonicalStateViewV2('canonical-state-v2','SI_right_handed_z_up_wxyz',
                                context.boundary,context.clock,(joint,),(),())
    lifetime = StateViewLifetime('state-view-lifetime-v1','material-a',context.boundary,0,
                                 'owned_snapshot','retained')
    publication = CanonicalStatePublicationV2('canonical-state-publication-v2',view,lifetime)
    class FakeSession:
        physical_control_generation = 1
        writes = 0
        advances = 0
        aborts = 0
        provenance = 'synthetic_fixture'
        assessment_phase = 'static_preflight'
        def snapshot_v2(self, **kwargs): return publication
        def state_boundary_identity(self): return context.boundary
        def assess_physical_control(self, binding):
            value = assessment('joint_effort')
            return replace(value, phase=self.assessment_phase,
                           rows=tuple(replace(row, phase=self.assessment_phase) for row in value.rows))
        def physical_joint_build_receipt(self, binding):
            return replace(_joint_receipt(plan,context), provenance=self.provenance)
        def apply_physical_command_batch(self, resolved):
            self.writes += 1
            assert resolved.joints[0].value == pytest.approx(2.3, abs=1e-12)
            return PhysicalControlReceiptV1('physical-control-receipt-v1',context,
                '0'*64 if bad_ack else resolved.input_batch.identity_hash,'native_write_ack',
                resolved.accepted_receipt.contribution_ids,'fake-terminal','per-channel')
        def abort_physical_control(self):
            self.aborts += 1
        def step(self):
            self.advances += 1
            return SimpleNamespace(control_step=1, simulation_time=.01)
    env = object.__new__(SelectedReferenceEnv)
    env._uses_component_assembly = False
    env._episode_mode = None
    env.binding = SimpleNamespace(external_solution_actions=False,external_actions=True,
        physical_control_profile=lambda _env:execution,
        observation_projection=lambda _env,_state: ({'x':1.}, {}, SimpleNamespace(failure=False,reward=.5)))
    env.artifact = SimpleNamespace(identity_hash='a'*64,timebase=SimpleNamespace(control_dt=.01,control_substeps=1))
    env.value = {'source':SimpleNamespace(source_id='source-a',source_closure_digest='b'*64),
                 'physical_execution':execution}
    # This fake has no declared subjects and makes no post-step state claim.
    env.typed_state = publication
    env.state = SimpleNamespace(control_step=0,simulation_time=0.)
    env.session = FakeSession()
    env.session._physical_controller_versions = execution.controller_versions()
    env.recorder = None
    env.horizon = 3
    env.mixed_control_profile = False
    with pytest.raises(ValueError, match='native-build or runtime capability assessment'):
        env.step((.25,))
    assert (env.session.writes, env.session.advances) == (0, 0)
    env.session.assessment_phase = 'native_build'
    with pytest.raises(ValueError, match='synthetic mapping cannot authorize'):
        env.step((.25,))
    assert (env.session.writes, env.session.advances) == (0, 0)
    assert controller.preflight_compute_calls == 1
    # Controller calculation has already run. No general rollback exists,
    # even though the physical clock has not advanced.
    with pytest.raises(RuntimeError, match=r'faulted; reset\(\) is required'):
        env.step((.25,))
    assert controller.preflight_compute_calls == 1
    # The following ACK cases use a separate fixture/episode; this does not
    # claim that clearing a fault alone constitutes a real runtime reset.
    previous = env
    env = object.__new__(SelectedReferenceEnv)
    env.__dict__.update({key: value for key, value in previous.__dict__.items()
                         if key != '_episode_state'})
    env.session = FakeSession()
    env.session.assessment_phase = 'native_build'
    fresh_controller = LinearEffortControllerV1(profile,plan.binding,model)
    fresh_execution = replace(execution, controllers=(fresh_controller,))
    env.session._physical_controller_versions = fresh_execution.controller_versions()
    env.value = {**env.value, 'physical_execution': fresh_execution}
    # This remains synthetic I/O: supply the bound execution and timebase so
    # the real scene preflight is exercised rather than bypassed. The receipt
    # provenance below was already an explicit fake, not native-build proof.
    env.session._physical_port = SimpleNamespace(execution=fresh_execution)
    env.session._artifact = SimpleNamespace(identity_hash='a'*64,
        timebase=SimpleNamespace(control_dt=.01, physics_dt=.01, control_substeps=1))
    env.binding = replace_binding = SimpleNamespace(**vars(previous.binding))
    replace_binding.physical_control_profile = lambda _env: fresh_execution
    # Explicit mock of the downstream native receipt: this is not build evidence.
    env.session.provenance = 'native_build'
    if bad_ack:
        with pytest.raises(ValueError, match='invalid write acknowledgement'):
            env.step((.25,))
        assert (env.session.writes, env.session.advances, env.session.aborts) == (1, 0, 1)
        return
    result = env.step((.25,))
    assert result[:4] == ({'x':1.},.5,False,False)
    assert result[4]['physical_control_v1']['native_write_ack']['stage'] == 'native_write_ack'
    assert (env.session.writes, env.session.advances) == (1,1)
    # Re-present the same pre-advance boundary to test duplicate submission.
    env.state = SimpleNamespace(control_step=0, simulation_time=0.)
    with pytest.raises(ValueError, match='already submitted'):
        env.step((.25,))
    assert (env.session.writes, env.session.advances) == (1,1)


def test_selected_env_composes_independent_effort_and_wrench_once():
    """Real selected step with two pure Controllers, synthetic session, no physics."""
    import numpy as np
    from types import SimpleNamespace
    from task_env.artifacts.contracts import PoseWorld
    from task_env.artifacts.state import (CanonicalStateViewV2, CanonicalStatePublicationV2,
        StateViewLifetime, StateRequirements, TypedJointStateValue, TypedFrameStateValue)
    from task_env.controllers.canonical.model import ControllerModelRequirementV1, AffineJointBiasModelV1
    from task_env.controllers.canonical.physical_commands import PhysicalControlReceiptV1, PhysicalBodyBindingV1, PhysicalBodyBuildReceiptV1
    from task_env.controllers.canonical.physical_controller import (LinearEffortProfileV1, LinearEffortControllerV1,
        WrenchControlProfileV1, WrenchControllerV1)
    from task_env.environment.reference_env import SelectedReferenceEnv
    from task_env.runtime.sessions.physical_control import PhysicalControlExecutionV1
    original, context, _, _ = _case()
    body = PhysicalBodyBindingV1('physical-body-binding-v1','arm','body-a',FrameReference('arm','base'),'native-body',('external-force',))
    binding = replace(original.binding,bodies=(body,))
    plan = compile_physical_control_binding(original.scene, original.root, original.children,binding)
    requirement = ControllerModelRequirementV1('controller-model-requirement-v1','affine-example',
        'geochora','v1','stdlib','source-a','b'*64,('arm/drive',),('rad',),'joint_bias',
        ('N*m',),'joint-axis','evaluation_boundary',.01,0.,'pure_no_physics_step','controller-a','none','required')
    model = AffineJointBiasModelV1('affine-joint-bias-model-v1',requirement,(0.,),(0.,),(0.,))
    profile = LinearEffortProfileV1('linear-effort-profile-v1','controller-a',('action',),('arm/drive',),((1.,),),requirement)
    arm = LinearEffortControllerV1(profile,binding,model)
    wp = WrenchControlProfileV1('wrench-control-profile-v1','external-force','arm','body-a',
        FrameReference('arm','base'),(0.,0.,0.),FrameReference('arm','base'),
        (0.,0.,0.),FrameReference('arm','base'),'exclusive')
    wrench = WrenchControllerV1(wp,binding)
    arm.generation, wrench.generation = 1, 7
    execution = PhysicalControlExecutionV1(plan,(arm,wrench),original.scene,{}, {},
        StateRequirements('state-requirements-v1','controller','controller-a',()),1)
    joint = TypedJointStateValue('typed-joint-state-v1','arm','drive','revolute','radian',(0.,),
                                  'radian_per_second',(0.,))
    frame = TypedFrameStateValue('typed-frame-state-v1',FrameReference('arm','base'),PoseWorld((0,0,0),(1,0,0,0)))
    view = CanonicalStateViewV2('canonical-state-v2','SI_right_handed_z_up_wxyz',context.boundary,context.clock,(joint,),(frame,),())
    lifetime = StateViewLifetime('state-view-lifetime-v1','material-a',context.boundary,0,'owned_snapshot','retained')
    publication = CanonicalStatePublicationV2('canonical-state-publication-v2',view,lifetime)
    caps = ('joint_effort','transmission','native_drive_state','body_force','body_torque','body_frame','body_offset_point')
    assessment = CapabilityAssessmentV1('capability-assessment-v1',binding.identity_hash,'native_build',
        tuple(CapabilityAssessmentRowV1('capability-assessment-row-v1',c,f'binding:{binding.identity_hash}',
        'required','supported','implemented','available','none','native_build','synthetic terminal',None,None) for c in caps))
    class FakeSession:
        physical_control_generation = 1
        writes = 0
        def snapshot_v2(self, **kwargs): return publication
        def state_boundary_identity(self): return context.boundary
        def assess_physical_control(self, b): return assessment
        def physical_joint_build_receipt(self, b):
            return replace(_joint_receipt(plan,context), provenance='native_build')
        def physical_body_build_receipt(self, b):
            return PhysicalBodyBuildReceiptV1('physical-body-build-receipt-v1',binding.identity_hash,'b'*64,
                                               'material-a',(body,),'native_build')  # mocked, not a native build
        def apply_physical_command_batch(self, result):
            self.writes += 1
            assert result.joints[0].value == 2.
            assert result.body_wrenches[0].force_world_N == pytest.approx((1.,0.,0.),abs=1e-12)
            return PhysicalControlReceiptV1('physical-control-receipt-v1',context,result.input_batch.identity_hash,
                'native_write_ack',result.accepted_receipt.contribution_ids,'fake-terminal','per-channel')
        def step(self): return SimpleNamespace(control_step=1,simulation_time=.01)
    env = object.__new__(SelectedReferenceEnv)
    env._uses_component_assembly = False
    env._episode_mode = None
    env.binding = SimpleNamespace(external_solution_actions=False,external_actions=True,
        physical_control_profile=lambda _env:execution,
        observation_projection=lambda _env,_state: ({}, {}, SimpleNamespace(failure=False,reward=0.)))
    env.artifact = SimpleNamespace(identity_hash='a'*64,timebase=SimpleNamespace(control_dt=.01,control_substeps=1,physics_dt=.01))
    env.value = {'source':SimpleNamespace(source_id='source-a',source_closure_digest='b'*64),
                 'physical_execution':execution}
    # This fake has no declared subjects and makes no post-step state claim.
    env.typed_state = publication
    env.state = SimpleNamespace(control_step=0,simulation_time=0.)
    env.session = FakeSession()
    env.session._artifact = env.artifact
    env.session._physical_port = SimpleNamespace(execution=execution)
    env.session._physical_controller_versions = execution.controller_versions()
    env.recorder = None
    env.horizon = 3
    env.mixed_control_profile = False
    wrench.generation = 8
    with pytest.raises(ValueError, match='versions differ from materialization'):
        env.step({arm.identity:np.array([2.],dtype=np.float32), wrench.identity:np.array([1.,0.,0.,0.,0.,0.])})
    assert env.session.writes == 0
    wrench.generation = 7
    result = env.step({arm.identity:np.array([2.],dtype=np.float32), wrench.identity:np.array([1.,0.,0.,0.,0.,0.])})
    assert env.session.writes == 1
    assert len(result[4]['physical_control_v1']['submitted_batch']['joint_efforts']) == 1
    assert len(result[4]['physical_control_v1']['submitted_batch']['body_wrenches']) == 1
    outer = env.session._last_scene_control_submission
    assert outer['inner_submission_id'] == env.session._last_control_submission['submission_id']
    assert {item['command_kind'] for item in outer['interval']['contributions']} == {'joint-effort', 'body-wrench'}
    assert {item['writer_id']: item['controller_generation'] for item in outer['interval']['contributions']} == {
        'controller-a': 1, 'external-force': 7}
    assert outer['interval']['row'] == 0


def test_eight_actions_map_to_seven_torques_and_constrained_finger_pair():
    """Synthetic source declarations only; coefficients are not Panda native evidence."""
    import json
    from pathlib import Path
    from task_env.artifacts import (SceneDefinition, JointReference, LogicalAssemblyV1,
        LogicalAssemblyScenePinV1, LogicalAssemblyEntityMemberV1,
        LogicalAssemblyNestedMemberV1, LogicalAssemblySubcomponentReferenceV1)
    from task_env.artifacts.state import CanonicalStateViewV2, TypedJointStateValue
    from task_env.controllers.canonical.model import ControllerModelRequirementV1, AffineJointBiasModelV1
    from task_env.controllers.canonical.physical_controller import LinearEffortProfileV1, LinearEffortControllerV1
    fixture = Path(__file__).with_name('fixtures')/'synthetic_panda_scene_v3.json'
    scene = SceneDefinition.from_mapping(json.loads(fixture.read_text()))
    pin = LogicalAssemblyScenePinV1('logical-assembly-scene-pin-v1', scene.scene_id,
                                     scene.schema_version, scene.identity_hash)
    names = tuple(f'joint{i}' for i in range(1,8)) + ('finger_joint1', 'finger_joint2')
    refs = tuple(LogicalAssemblySubcomponentReferenceV1('existing_entity_subcomponent_ref',
        (name,), 'joint', JointReference('panda-main', name)) for name in names)
    child = LogicalAssemblyV1('logical-assembly-v1', 'panda-subtree', 'r1', pin, refs)
    root = LogicalAssemblyV1('logical-assembly-v1', 'panda-root', 'r1', pin, (
        LogicalAssemblyEntityMemberV1('entity_member', ('owner',), 'panda-main',
                                      'panda-v1', 'mujoco-menagerie-panda'),
        LogicalAssemblyNestedMemberV1('nested_assembly', ('robot',), child.assembly_id,
                                      child.revision, child.logical_content_sha256)))
    definitions = {j.joint_id:j for a in scene.articulations for j in a.joints}
    # Fixture joint-frame axes independently rotated into their parent frames.
    parent_axes = ((0,0,1),(0,1,0),(0,-1,0),(0,-1,0),(0,1,0),
                   (0,-1,0),(0,-1,0),(0,1,0),(0,-1,0))
    channels = tuple(PhysicalJointChannelV1('physical-joint-channel-v1', ('robot', name),
        ('panda-controller',), 'panda-main', name, 'dof0', definitions[name].kind,
        parent_axes[i], definitions[name].parent_frame, 1,
        'N*m' if i < 7 else 'N', (-10,10), f'actuator-{i}' if i < 7 else 'tendon',
        f'direct-{i}' if i < 7 else 'paired-fingers', 1., (-10,10), 'disabled')
        for i, name in enumerate(names))
    binding = PhysicalControlBindingV1('physical-control-binding-v1', scene.identity_hash,
        'a'*64, 'synthetic-source', 'b'*64, root.logical_content_sha256, channels)
    plan = compile_physical_control_binding(scene, root, {(child.assembly_id, child.revision):child}, binding)
    boundary = StateBoundaryIdentity('state-boundary-identity-v1', 'episode-a', 'reset-'+'d'*64,
        scene.identity_hash, 'instance-a', 'material-a', 0, 0)
    clock = StateSampleClock('state-sample-clock-v1', 'evaluation_boundary', 0, 0.)
    context = PhysicalCommandContextV1('physical-command-context-v1', 'synthetic-source',
        'b'*64, 'a'*64, boundary, clock, 0, 1, .01, .01)
    keys = tuple(f'panda-main/{name}' for name in names)
    requirement = ControllerModelRequirementV1('controller-model-requirement-v1', 'affine-example',
        'geochora','v1','stdlib','synthetic-source','b'*64,keys,('rad',)*7+('m',)*2,
        'joint_bias',('N*m',)*7+('N',)*2,'joint-axis','evaluation_boundary',.01,0.,
        'pure_no_physics_step','panda-controller','none','required')
    model = AffineJointBiasModelV1('affine-joint-bias-model-v1', requirement, (0.,)*9, (0.,)*9, (0.,)*9)
    matrix = tuple(tuple(1. if col == (row if row < 7 else 7) else 0.
                         for col in range(8)) for row in range(9))
    profile = LinearEffortProfileV1('linear-effort-profile-v1','panda-controller',
        tuple(f'input-{i}' for i in range(8)),keys,matrix,requirement)
    controller = LinearEffortControllerV1(profile,binding,model)
    state_joints = tuple(TypedJointStateValue('typed-joint-state-v1','panda-main',name,
        definitions[name].kind, 'radian' if i < 7 else 'meter', (0.,),
        'radian_per_second' if i < 7 else 'meter_per_second', (0.,)) for i,name in enumerate(names))
    state = CanonicalStateViewV2('canonical-state-v2','SI_right_handed_z_up_wxyz',boundary,clock,state_joints,(),())
    action = (1.,2.,3.,4.,5.,6.,7.,8.)
    batch = controller.compute(action,state,context)
    caps = ('joint_effort','transmission','native_drive_state')
    assessment = CapabilityAssessmentV1('capability-assessment-v1',binding.identity_hash,
        'static_preflight',tuple(CapabilityAssessmentRowV1('capability-assessment-row-v1',c,
        f'binding:{binding.identity_hash}','required','supported','implemented','available',
        'none','static_preflight','synthetic fixture only',None,None) for c in caps))
    result = prepare_physical_command_batch(plan,batch,expected_context=context,assessment=assessment, joint_build_receipt=_joint_receipt(plan,context))
    by_name = {item.joint_id:item.value for item in result.joints}
    assert tuple(by_name[name] for name in names) == (*action[:7],8.,8.)
    bad = replace(batch, joint_efforts=(*batch.joint_efforts[:-1], replace(batch.joint_efforts[-1], value=7.)))
    with pytest.raises(ValueError, match='not representable'):
        prepare_physical_command_batch(plan,bad,expected_context=context,assessment=assessment, joint_build_receipt=_joint_receipt(plan,context))
