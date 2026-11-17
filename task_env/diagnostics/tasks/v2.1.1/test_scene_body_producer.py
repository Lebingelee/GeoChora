"""Source-bound independent physical producers keep Controller ownership intact."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from task_env.artifacts import FrameReference
from task_env.artifacts.state import StateRequirements
from task_env.controllers.canonical.physical_commands import (
    BodyWrenchV1, ContributionPolicyV1, PhysicalBodyBindingV1, PhysicalCommandBatchV1,
    PhysicalControlReceiptV1,
)
from task_env.diagnostics.tasks.physical_contract_fixtures import _case
from task_env.runtime.sessions.physical_control import (
    PhysicalControlExecutionV1, ResolvedPhysicalBatchV1, SceneBodyProducerV1,
    compile_physical_control_binding,
)
from task_env.runtime.sessions.control_submission import prepare_physical_scene_interval


def test_scene_body_writer_requires_declared_resource_and_current_interval():
    old, context, effort, _ = _case()
    body = PhysicalBodyBindingV1('physical-body-binding-v1', 'arm', 'body-a',
                                 FrameReference('arm', 'base'), 'native-body', ('caller-a',))
    binding = replace(old.binding, bodies=(body,))
    compiled = compile_physical_control_binding(old.scene, old.root, old.children, binding)
    controller = SimpleNamespace(binding=binding, identity='control-a', writer_id='controller-a',
        compute=lambda *_: None, action_shape=(1,))
    producer = SceneBodyProducerV1('caller-a', 'caller', (('arm', 'body-a'),))
    execution = PhysicalControlExecutionV1(compiled, (controller,), old.scene, {}, {},
        StateRequirements('state-requirements-v1', 'controller', 'controller-a', ()), 1,
        scene_body_producers=(producer,))
    policy = ContributionPolicyV1('physical-contribution-policy-v1', 'load-a', 'load-effect',
                                   'caller-a', 'exclusive', 'reject_outside', 'one_interval')
    frame = FrameReference('arm', 'base')
    wrench = BodyWrenchV1('body-wrench-v1', context, policy, 'arm', 'body-a', frame,
                           (0., 0., 0.), frame, (0., 0., 0.), frame, (1., 0., 0.), (0., 0., 0.))
    batch = PhysicalCommandBatchV1('physical-command-batch-v1', context, (effort('joint-a', 1.),), (), ())
    merged = execution.compose_scene_body_wrenches(batch, (wrench,))
    assert merged.joint_efforts == batch.joint_efforts and merged.body_wrenches == (wrench,)
    receipt = PhysicalControlReceiptV1('physical-control-receipt-v1', context, merged.identity_hash,
        'accepted', ('joint-a', 'load-a'), 'core-admission', 'per-channel')
    resolved = ResolvedPhysicalBatchV1(merged, binding.identity_hash, (object(),), (object(),), (),
                                       receipt, ('native_build', 'native_build'))
    session = SimpleNamespace(physical_control_execution=execution, physical_control_generation=1,
        _physical_controller_versions=execution.controller_versions(),
        _artifact=SimpleNamespace(timebase=SimpleNamespace(control_substeps=2, physics_dt=.005, control_dt=.01)))
    interval = prepare_physical_scene_interval(session=session, execution=execution, resolved=resolved)
    assert [(c.producer_kind, c.writer_id, c.controller_identity) for c in interval.contributions] == [
        ('robot-controller', 'controller-a', 'control-a'), ('caller', 'caller-a', None)]
    with pytest.raises(ValueError, match='not authorized'):
        execution.compose_scene_body_wrenches(batch, (replace(wrench, body_id='unknown'),))
    with pytest.raises(ValueError, match='share the exact interval'):
        execution.compose_scene_body_wrenches(batch, (replace(wrench, context=replace(context, row=1)),))
    with pytest.raises(ValueError, match='same physical effect'):
        execution.compose_scene_body_wrenches(batch, (replace(wrench, contribution=replace(policy,
            physical_effect_id='joint-a')),))
    with pytest.raises(ValueError, match='distinct'):
        replace(execution, scene_body_producers=(replace(producer, writer_id='controller-a'),))


def test_formal_pickcube_binds_declared_scene_body():
    from task_env import make_env
    env = make_env('pick-cube-p16-reference-v1', config={
        'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu', 'deployment': 'in_process'},
        'episode': {'horizon': 8}, 'controller': {'profile_id': 'panda-direct-effort-v1'},
        'scene_body_producers': [{'writer_id': 'caller-a', 'producer_kind': 'caller',
                                  'body_keys': [['cube-v1', 'PickCube']]}],
    })
    try:
        env.reset(seed=31)
        execution = env._physical_execution()
        assert execution.scene_body_producers[0].body_keys == (('cube-v1', 'PickCube'),)
        assert execution.compiled.binding.bodies[0].native_body == 'PickCube'
        assert execution.selection_profile_id == 'panda-direct-effort-v1'
        assert env.session.physical_body_build_receipt(execution.compiled.binding).provenance == 'native_build'
        context, bodies = env.physical_scene_context()
        frame = bodies[0].body_frame
        policy = ContributionPolicyV1('physical-contribution-policy-v1', 'load-a', 'effect-a',
                                      'caller-a', 'exclusive', 'reject_outside', 'one_interval')
        wrench = BodyWrenchV1('body-wrench-v1', context, policy, 'cube-v1', 'PickCube',
                              frame, (0., 0., 0.), frame, (0., 0., 0.), frame,
                              (0., 0., 1.), (0., 0., 0.))
        import numpy as np
        env.step(np.zeros(8, dtype=np.float32), scene_body_wrenches=(wrench,))
        native_steps = env.session._native_steps
        with pytest.raises(ValueError, match='interval|stale|boundary'):
            env.step(np.zeros(8, dtype=np.float32), scene_body_wrenches=(wrench,))
        assert env.session._native_steps == native_steps
    finally:
        env.close()


def test_mujoco_free_angular_armature_wrench_is_rejected_before_native_step():
    """The native implicitfast/free-armature mismatch must not be silently admitted."""
    import numpy as np
    from task_env import make_env
    env = make_env('pick-cube-p16-reference-v1', config={
        'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu', 'deployment': 'in_process'},
        'controller': {'profile_id': 'panda-direct-effort-v1'},
        'scene_body_producers': [{'writer_id': 'caller-a', 'producer_kind': 'caller',
                                  'body_keys': [['cube-v1', 'PickCube']]}],
    })
    try:
        env.reset(seed=31)
        context, bodies = env.physical_scene_context()
        frame = bodies[0].body_frame
        policy = ContributionPolicyV1('physical-contribution-policy-v1', 'load-a', 'effect-a',
                                      'caller-a', 'exclusive', 'reject_outside', 'one_interval')
        wrench = BodyWrenchV1('body-wrench-v1', context, policy, 'cube-v1', 'PickCube',
                              frame, (0., 0., 0.), frame, (0., 0., 0.), frame,
                              (0., 0., 0.), (0., 0., .01))
        before = env.session._native_steps
        with pytest.raises(ValueError, match='FREE body angular armature'):
            env.step(np.zeros(8, dtype=np.float32), scene_body_wrenches=(wrench,))
        assert env.session._native_steps == before
    finally:
        env.close()
