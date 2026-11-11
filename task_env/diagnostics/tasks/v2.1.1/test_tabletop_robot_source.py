"""Check that tabletop Artifacts and sources share one declared Robot."""
from types import SimpleNamespace

import pytest

from task_env.assembly.compiler import compile_reference_source
from task_env.environment.types import TaskCompositionSpec
from task_env.robots.panda import PandaAgent


@pytest.mark.parametrize('task_name', ['pickcube', 'nut'])
def test_artifact_and_runtime_source_share_robot(task_name, monkeypatch):
    from task_env.tasks.pick_cube.specialization import build_reference as build_pickcube
    from task_env.tasks.nut_assembly.specialization import build_reference as build_nut

    original = PandaAgent.artifact_entity
    used = []
    def capture(robot, *args, **kwargs):
        used.append(robot)
        return original(robot, *args, **kwargs)
    monkeypatch.setattr(PandaAgent, 'artifact_entity', capture)
    value = (build_pickcube(backend='cpu', include_solution=False)
             if task_name == 'pickcube' else build_nut(provider='mujoco', include_solution=False))
    source = value['source']
    try:
        assert used and all(robot is source.agents[0] for robot in used)
        assert source.agents[0].uid == 'panda-v1'
    finally:
        source.execution_source_receipt.close()


def test_source_rejects_robot_outside_task_composition():
    artifact = SimpleNamespace(initialization=SimpleNamespace(joint_position={}), identity_hash='a' * 64)
    composition = TaskCompositionSpec('task-test', 'tabletop-v1', ('panda-v1',), ())
    with pytest.raises(ValueError, match='supplied Robots differ'):
        compile_reference_source(artifact=artifact, scene_source=None, composition=composition, config=None,
            bodies={}, frames={}, free_joints={}, joint_targets={}, open_actuators=(),
            agents=(SimpleNamespace(uid='foreign-robot'),))


@pytest.mark.parametrize('task_name', ['pickcube', 'nut'])
def test_r3_execution_controller_owns_hold_and_gripper(task_name):
    from task_env.controllers.canonical.execution import ReferenceExecutionController, StableArmTargetHold
    from task_env.tasks.pick_cube.specialization import build_reference as build_pickcube
    from task_env.tasks.nut_assembly.specialization import build_reference as build_nut

    value = (build_pickcube(backend='cpu', include_solution=False, controller_profile='r3_continuous_v1')
             if task_name == 'pickcube' else build_nut(provider='mujoco', include_solution=False))
    try:
        controller = value['controller']
        assert isinstance(controller, ReferenceExecutionController)
        assert isinstance(controller.hold, StableArmTargetHold)
        assert controller.inner.controller is controller.hold.controller
        assert controller.gripper_rate_hz == 500
        assert controller.gripper_config.force_limit_N == 10.0
        assert controller.control_dt == value['artifact'].timebase.control_dt
    finally:
        value['source'].execution_source_receipt.close()


@pytest.mark.parametrize('uid', ['pick-cube-p16-reference-v1', 'nut-assembly-outcome-reference-v1'])
def test_each_public_environment_owns_its_binding_and_source(uid):
    import sys
    from task_env import make_env

    config = {'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu',
                            'physics_device': 'cpu', 'deployment': 'in_process',
                            'interpreter': sys.executable}, 'episode': {'horizon': 8}}
    first = make_env(uid, config=config)
    second = None
    try:
        second = make_env(uid, config=config)
        assert first.binding is not second.binding
        assert first.controller is not second.controller
        first_receipt = first.value['source'].execution_source_receipt
        second_receipt = second.value['source'].execution_source_receipt
        assert first_receipt is not second_receipt
        first.close()
        assert not first_receipt.snapshot_root.exists()
        assert second_receipt.snapshot_root.exists()
    finally:
        first.close()
        if second is not None:
            second.close()


def test_usd_task_scene_uses_the_supplied_robot(monkeypatch):
    from task_env.runtime.sessions import source_scene_import
    from task_env.tasks.pick_cube.specialization import _configuration, build_pickcube_isaac_scene

    robot = PandaAgent()
    original = source_scene_import.declare_panda_scene
    used = []

    def capture(subject, **kwargs):
        used.append(subject)
        return original(subject, **kwargs)

    monkeypatch.setattr(source_scene_import, 'declare_panda_scene', capture)
    scene = build_pickcube_isaac_scene(_configuration(), robot=robot)
    assert used == [robot]
    assert scene.robots[0].entity_id == 'panda-v1'


def test_mjcf_effort_reuses_robot_from_task_source(monkeypatch):
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.runtime.sessions import source_scene_import
    from task_env.tasks.pick_cube import specialization
    from task_env.controllers.canonical.execution import ReferenceExecutionController
    from task_env.tasks.pick_cube.task import PickCubeReferenceEnv

    built, declared, bound = [], [], []
    original_reference = specialization._prepare_reference_source
    original_scene = source_scene_import.declare_panda_scene
    original_control = PandaAgent.build_direct_effort_execution

    def reference(*args, **kwargs):
        value = original_reference(*args, **kwargs)
        built.append(value.source.agents[0])
        return value

    def scene(robot, **kwargs):
        declared.append(robot)
        return original_scene(robot, **kwargs)

    def control(robot, *args, **kwargs):
        bound.append(robot)
        return original_control(robot, *args, **kwargs)

    def reject_reference(*args, **kwargs):
        raise AssertionError('effort source preparation must not construct a reference Controller')

    monkeypatch.setattr(ReferenceExecutionController, 'from_source', reject_reference)
    monkeypatch.setattr(specialization, '_prepare_reference_source', reference)
    monkeypatch.setattr(source_scene_import, 'declare_panda_scene', scene)
    monkeypatch.setattr(PandaAgent, 'build_direct_effort_execution', control)
    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'mujoco'},
        'controller': {'profile_id': 'panda-direct-effort-v1'},
    })
    binding = PickCubeReferenceEnv.selected_binding(config)
    try:
        binding.build('mujoco')
        assert len(built) == len(declared) == len(bound) == 1
        assert built[0] is declared[0] is bound[0]
    finally:
        binding.close_task_resources()


@pytest.mark.parametrize('physical', [False, True])
def test_usd_build_failure_releases_prepared_task_source(physical, monkeypatch):
    from task_env.runtime.sessions import source as source_module
    from task_env.tasks.pick_cube import specialization

    receipts = []
    original = source_module.snapshot_legacy_mjcf_source
    failure = RuntimeError('USD source preparation failed')

    def capture(*args, **kwargs):
        source = original(*args, **kwargs)
        receipts.append(source.execution_source_receipt)
        return source

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(source_module, 'snapshot_legacy_mjcf_source', capture)
    monkeypatch.setattr(specialization, 'build_pickcube_isaac_runtime_input_v1', fail)
    with pytest.raises(RuntimeError) as raised:
        specialization.build_isaac_reference(
            delivery_manifest='unused', include_solution=False,
            controller_builder=(lambda *args: None) if physical else None,
        )
    assert raised.value is failure
    assert len(receipts) == 1
    assert not receipts[0].snapshot_root.exists()


def test_usd_build_failure_preserves_error_when_source_cleanup_fails(monkeypatch):
    from task_env.runtime.sessions.source import ExecutionSourceReceiptV1
    from task_env.tasks.pick_cube import specialization

    original_close = ExecutionSourceReceiptV1.close
    failure = RuntimeError('USD source failed')

    def fail_build(*args, **kwargs):
        raise failure

    def fail_close(receipt):
        original_close(receipt)
        raise OSError('cleanup failed')

    monkeypatch.setattr(specialization, 'build_pickcube_isaac_runtime_input_v1', fail_build)
    monkeypatch.setattr(ExecutionSourceReceiptV1, 'close', fail_close)
    with pytest.raises(RuntimeError) as raised:
        specialization.build_isaac_reference(delivery_manifest='unused', include_solution=False)
    assert raised.value is failure
    assert any('cleanup failed' in note for note in raised.value.__notes__)


def test_readiness_failure_does_not_create_a_source_snapshot(monkeypatch):
    from task_env.runtime.sessions import source as source_module
    from task_env.tasks.pick_cube import specialization
    from task_env.tasks.pick_cube.solution import PickCubeReadinessConfig

    failure = RuntimeError('readiness failed')
    def fail_readiness(*args, **kwargs):
        raise failure
    def unexpected_snapshot(*args, **kwargs):
        raise AssertionError('snapshot must not be created before readiness succeeds')
    monkeypatch.setattr(PickCubeReadinessConfig, 'from_source', fail_readiness)
    monkeypatch.setattr(source_module, 'snapshot_legacy_mjcf_source', unexpected_snapshot)
    with pytest.raises(RuntimeError) as raised:
        specialization._prepare_reference_source(controller_profile='r3_continuous_v1')
    assert raised.value is failure


@pytest.mark.parametrize('task_name', ['pickcube', 'nut'])
def test_reference_controller_failure_releases_task_source(task_name, monkeypatch):
    from task_env.controllers.canonical.execution import ReferenceExecutionController
    from task_env.runtime.sessions import source as source_module
    from task_env.tasks.pick_cube import specialization as pickcube
    from task_env.tasks.nut_assembly import specialization as nut

    receipts = []
    original = source_module.snapshot_legacy_mjcf_source
    failure = RuntimeError('Controller construction failed')
    def capture(*args, **kwargs):
        source = original(*args, **kwargs)
        receipts.append(source.execution_source_receipt)
        return source
    def fail_controller(*args, **kwargs):
        raise failure
    monkeypatch.setattr(source_module, 'snapshot_legacy_mjcf_source', capture)
    monkeypatch.setattr(ReferenceExecutionController, 'from_source', fail_controller)
    with pytest.raises(RuntimeError) as raised:
        if task_name == 'pickcube':
            pickcube.build_reference(backend='cpu', include_solution=False, controller_profile='r3_continuous_v1')
        else:
            nut.build_reference(provider='mujoco', include_solution=False)
    assert raised.value is failure
    assert len(receipts) == 1 and not receipts[0].snapshot_root.exists()


def test_usd_source_identity_failure_releases_task_source(monkeypatch):
    from task_env.runtime.sessions import source as source_module
    from task_env.tasks.pick_cube import specialization

    receipts = []
    original = source_module.snapshot_legacy_mjcf_source
    failure = RuntimeError('source identity failed')
    def capture(*args, **kwargs):
        source = original(*args, **kwargs)
        receipts.append(source.execution_source_receipt)
        return source
    def fail_identity(*args, **kwargs):
        raise failure
    monkeypatch.setattr(source_module, 'snapshot_legacy_mjcf_source', capture)
    monkeypatch.setattr(specialization, '_source_identity_files', fail_identity)
    with pytest.raises(RuntimeError) as raised:
        specialization.build_isaac_reference(delivery_manifest='unused', include_solution=False,
                                              controller_builder=lambda *args: None)
    assert raised.value is failure
    assert len(receipts) == 1 and not receipts[0].snapshot_root.exists()


def test_failed_controller_cleanup_preserves_original_error(monkeypatch):
    from task_env.controllers.canonical.execution import ReferenceExecutionController
    from task_env.runtime.sessions.source import ExecutionSourceReceiptV1
    from task_env.tasks.pick_cube import specialization

    original_close = ExecutionSourceReceiptV1.close
    failure = RuntimeError('Controller construction failed')
    def fail_controller(*args, **kwargs):
        raise failure
    def fail_close(receipt):
        original_close(receipt)
        raise OSError('cleanup failed')
    monkeypatch.setattr(ReferenceExecutionController, 'from_source', fail_controller)
    monkeypatch.setattr(ExecutionSourceReceiptV1, 'close', fail_close)
    with pytest.raises(RuntimeError) as raised:
        specialization.build_reference(backend='cpu', include_solution=False,
                                       controller_profile='r3_continuous_v1')
    assert raised.value is failure
    assert any('cleanup failed' in note for note in raised.value.__notes__)


def test_physical_early_failure_releases_prepared_task_source(monkeypatch):
    import subprocess
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.runtime.sessions import source as source_module
    from task_env.tasks.pick_cube.task import PickCubeReferenceEnv

    receipts = []
    original = source_module.snapshot_legacy_mjcf_source
    failure = RuntimeError('revision lookup failed')
    def capture(*args, **kwargs):
        source = original(*args, **kwargs)
        receipts.append(source.execution_source_receipt)
        return source
    def fail_revision(*args, **kwargs):
        raise failure
    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'mujoco'},
        'controller': {'profile_id': 'panda-direct-effort-v1'},
    })
    monkeypatch.setattr(source_module, 'snapshot_legacy_mjcf_source', capture)
    monkeypatch.setattr(subprocess, 'check_output', fail_revision)
    with pytest.raises(RuntimeError) as raised:
        PickCubeReferenceEnv.selected_binding(config)
    assert raised.value is failure
    assert len(receipts) == 1 and not receipts[0].snapshot_root.exists()


def test_native_feedback_requires_source_owned_subject_before_materialization():
    from types import SimpleNamespace
    from task_env.runtime.sessions.control import materialize_control

    source = SimpleNamespace(position_subject_binding=None)
    with pytest.raises(ValueError, match='source-owned subject binding'):
        materialize_control(None, None, source=source, binding=None, selected_controller=object())
