"""Check that tabletop Artifacts and sources share one declared Robot."""
from types import SimpleNamespace

import pytest

from task_env.assembly.compiler import compile_reference_source
from task_env.environment.types import TaskCompositionSpec
from task_env.robots.panda import PandaAgent
from task_env.runtime.sessions.source import source_resource_receipt


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
        source_resource_receipt(source).close()


def test_pickcube_reference_compiles_the_selected_robot_instance(monkeypatch):
    from task_env.tasks.pick_cube import specialization

    create = specialization.make_agent
    selected = []
    def capture(uid):
        robot = create(uid)
        selected.append(robot)
        return robot
    monkeypatch.setattr(specialization, 'make_agent', capture)
    value = specialization.build_reference(backend='cpu', include_solution=False)
    try:
        assert len(selected) == 1
        assert value['source'].agents == (selected[0],)
        assert value['source'].scene_definition.robots[0].entity_id == selected[0].uid
    finally:
        source_resource_receipt(value['source']).close()


@pytest.mark.parametrize('task_name', ['pickcube', 'nut'])
def test_reference_source_composition_reuses_the_task_robot(task_name, monkeypatch):
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.runtime.sessions import mujoco_composition
    from task_env.runtime.sessions.source_composition_adapters import declared_robot_source_composer
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv, build_reference as build_pickcube
    from task_env.tasks.nut_assembly.specialization import NutAssemblyReferenceEnv, build_reference as build_nut

    cls = PickCubeReferenceEnv if task_name == 'pickcube' else NutAssemblyReferenceEnv
    config = resolve_task_env_config(cls, {'execution': {'physics_provider': 'mujoco',
        'physics_backend': 'cpu', 'physics_device': 'cpu'}})
    value = (build_pickcube(backend='cpu', include_solution=False, controller_profile=config.controller_profile)
             if task_name == 'pickcube' else build_nut(provider='mujoco', include_solution=False))
    original = mujoco_composition.compose_robot_source
    seen = []
    def capture(source, *, robot, **kwargs):
        seen.append((source.agents[0], robot))
        return original(source, robot=robot, **kwargs)
    monkeypatch.setattr(mujoco_composition, 'compose_robot_source', capture)
    try:
        compose = declared_robot_source_composer(config, robot_uid=config.robot_uid,
            existing_robot_entity=cls.default_robot_source_uid, task_body_names=cls.robot_source_roots,
            task_site_transfers=cls.robot_source_site_transfers)
        adapted = compose(value['source'], artifact=value['artifact'], controller=value['controller'])
        assert len(seen) == 1 and seen[0][0] is seen[0][1]
        assert adapted.agents[0] is seen[0][1]
        if adapted.scene_definition is not None:
            assert adapted.position_subject_binding.plan.scene_identity_hash == adapted.scene_definition.identity_hash
    finally:
        source_resource_receipt(value['source']).close()


def test_source_rejects_robot_outside_task_composition():
    artifact = SimpleNamespace(initialization=SimpleNamespace(joint_position={}), identity_hash='a' * 64)
    composition = TaskCompositionSpec('task-test', 'tabletop-v1', ('panda-v1',), ())
    with pytest.raises(ValueError, match='supplied Robots differ'):
        compile_reference_source(artifact=artifact, scene_source=None, composition=composition, config=None,
            bodies={}, frames={}, free_joints={}, joint_targets={}, open_actuators=(),
            agents=(SimpleNamespace(uid='foreign-robot'),))


def test_pickcube_task_definition_uses_frozen_artifact_semantics(monkeypatch):
    from dataclasses import replace
    from task_env.artifacts import CanonicalStateView, PoseWorld
    from task_env.environment.task_definition import TaskEvaluationContextV1
    from task_env.tasks.pick_cube import task
    from task_env.tasks.pick_cube.specialization import build_artifact

    artifact = build_artifact(lift_height_m=.17)
    monkeypatch.setattr(task, '_recipe', lambda: pytest.fail('Task definition reloaded the recipe'))
    definition = task.PickCubeTaskDefinition.from_artifact(artifact)
    rest = artifact.semantics.parameters_si['rest_height']
    fingers = {'panda-v1/finger_joint1': .01, 'panda-v1/finger_joint2': .01}
    def state(height):
        return CanonicalStateView('canonical-state-v0', 'SI_right_handed_z_up_wxyz', 0, 0.,
            fingers, {key: 0. for key in fingers}, {
                'cube-v1': PoseWorld((0., 0., rest + height), (1., 0., 0., 0.)),
                'panda-v1/ee': PoseWorld((0., 0., rest + height), (1., 0., 0., 0.))})
    assert not definition.reset(state(.16)).success
    assert definition.evaluate(state=state(.18)).success
    result = definition.evaluate_predicates(TaskEvaluationContextV1(state(.18)))
    assert result.predicates['cube_lifted'].value is True
    with pytest.raises(ValueError, match='unsupported PickCube success definition'):
        task.PickCubeTaskDefinition(replace(artifact.semantics, success_definition='other'))


@pytest.mark.parametrize('task_name', ['pickcube', 'nut'])
def test_r3_execution_controller_owns_hold_and_gripper(task_name, monkeypatch):
    from task_env.controllers.canonical.execution import ReferenceExecutionController, StableArmTargetHold
    from task_env.tasks.pick_cube import specialization as pickcube
    from task_env.tasks.nut_assembly import specialization as nut

    module = pickcube if task_name == 'pickcube' else nut
    original = module.build_reference_position_controller
    constructed = []
    def capture(artifact, source, **kwargs):
        controller = original(artifact, source, **kwargs)
        constructed.append((controller, artifact, source, kwargs['profile_id']))
        return controller
    monkeypatch.setattr(module, 'build_reference_position_controller', capture)
    value = (pickcube.build_reference(backend='cpu', include_solution=False, controller_profile='r3_continuous_v1')
             if task_name == 'pickcube' else nut.build_reference(provider='mujoco', include_solution=False))
    try:
        controller = value['controller']
        assert constructed == [(controller, value['artifact'], value['source'], 'r3_continuous_v1')]
        assert isinstance(controller, ReferenceExecutionController)
        assert isinstance(controller.hold, StableArmTargetHold)
        assert controller.inner.controller is controller.hold.controller
        assert controller.gripper_rate_hz == 500
        assert controller.gripper_config.force_limit_N == 10.0
        assert controller.control_dt == value['artifact'].timebase.control_dt
    finally:
        source_resource_receipt(value['source']).close()


@pytest.mark.parametrize('task_name', ['pickcube', 'nut'])
def test_both_tabletop_controllers_use_the_same_hold_ramp_contract(task_name):
    from task_env.controllers.canonical.contracts import CanonicalControlTarget, GripperControlTarget
    from task_env.controllers.canonical.execution import ARM_HOLD_RAMP_PROFILE, ArmTargetExecutionRequestV1
    from task_env.tasks.pick_cube.specialization import build_reference as build_pickcube
    from task_env.tasks.nut_assembly.specialization import build_reference as build_nut

    value = (build_pickcube(backend='cpu', include_solution=False, controller_profile='r3_continuous_v1')
             if task_name == 'pickcube' else build_nut(provider='mujoco', include_solution=False))
    try:
        controller = value['controller']
        arm = tuple(f'panda-v1/joint{i}' for i in range(1, 8))
        target = CanonicalControlTarget('canonical-control-v0', value['artifact'].identity_hash,
            controller.identity, arm, {k: .4 for k in arm}, {k: .4 for k in arm},
            GripperControlTarget('panda-v1/gripper', .08, 10., .08))
        request = lambda mode: ArmTargetExecutionRequestV1(
            'arm-target-execution-request-v1', ARM_HOLD_RAMP_PROFILE, mode)
        with pytest.raises(ValueError, match='preceding applied'):
            controller.validate_arm_execution_request(request('hold_last_applied'))
        controller.applied(SimpleNamespace(arm_servo_position={k: .1 for k in arm}))
        controller.request_arm_execution(request('hold_last_applied'))
        assert controller.target(target, 0, 5).arm_servo_position == {k: .1 for k in arm}
        controller.request_arm_execution(request('ramp_from_last_applied'))
        controller.begin(target)
        for i in range(5):
            applied = controller.target(target, i, 5)
            assert applied.arm_servo_position == {k: .1 + (i + 1) / 5 * (.4 - .1) for k in arm}
            assert applied.gripper == target.gripper
            controller.applied(SimpleNamespace(arm_servo_position=applied.arm_servo_position))
        controller.request_arm_execution(request('track'))
        assert controller.target(target, 0, 5) is target
        with pytest.raises(ValueError, match='unsupported arm target execution'):
            controller.request_arm_execution(request('unsupported'))
    finally:
        source_resource_receipt(value['source']).close()


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
        first_receipt = source_resource_receipt(first.value['source'])
        second_receipt = source_resource_receipt(second.value['source'])
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
        binding.build_for_request('mujoco', 'cpu', 31, 8)
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
        receipts.append(source_resource_receipt(source))
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
        receipts.append(source_resource_receipt(source))
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
        receipts.append(source_resource_receipt(source))
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
        receipts.append(source_resource_receipt(source))
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


@pytest.mark.parametrize('uid', ['pick-cube-p16-reference-v1', 'nut-assembly-outcome-reference-v1'])
def test_formal_construction_rejects_missing_robot_subject_and_cleans_source(uid, monkeypatch):
    import sys
    from task_env import make_env
    from task_env.registry import ENV_REGISTRY
    from task_env.runtime.sessions import source as source_module
    import task_env.tasks  # register the formal tasks

    receipts = []
    snapshot = source_module.snapshot_legacy_mjcf_source
    def capture(*args, **kwargs):
        result = snapshot(*args, **kwargs)
        receipts.append(source_resource_receipt(result))
        return result
    monkeypatch.setattr(source_module, 'snapshot_legacy_mjcf_source', capture)
    cls = ENV_REGISTRY.get(uid)
    monkeypatch.setattr(cls, '_bind_robot_source_composer',
                        classmethod(lambda cls, binding, config: binding))
    config = {'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process',
                            'interpreter': sys.executable}, 'episode': {'horizon': 8}}
    with pytest.raises(ValueError, match='source-owned Robot subject binding'):
        make_env(uid, config=config)
    assert receipts and all(not receipt.snapshot_root.exists() for receipt in receipts)


@pytest.mark.parametrize('split', [False, True])
def test_robot_rejects_controller_replaced_after_subject_compilation(split):
    from task_env import make_env
    from task_env.runtime.sessions.control import bind_selected_controller

    config = {'execution': {'physics_provider': 'mujoco'}, 'episode': {'horizon': 8}}
    if split:
        config.update(robot={'uid': 'panda-arm-hand-v1'}, controller={'profile_id': 'r1_split'})
    env = make_env('pick-cube-p16-reference-v1', config=config)
    try:
        if split:
            rows = list(env.controller.position_binding_requirements())
            first = rows[0]
            rows[0] = (SimpleNamespace(writer_id=first[0].writer_id, identity='f' * 64), *first[1:])
            foreign = SimpleNamespace(position_binding_requirements=lambda: tuple(rows))
        else:
            foreign = SimpleNamespace(identity='f' * 64)
        with pytest.raises(ValueError, match='Controllers differ from their source-owned binding'):
            bind_selected_controller({**env.value, 'controller': foreign}, binding=env.binding,
                                     provider=env.provider, backend=env.backend)
    finally:
        env.close()


def test_pickcube_scene_representations_share_task_artifact_compiler():
    from task_env.artifacts import FrameReference
    from task_env.robots.panda import PandaAgent
    from task_env.tasks.pick_cube import specialization as task

    config = task._configuration()
    legacy = task.build_artifact(lift_height_m=.17)
    robot = PandaAgent()
    mjcf_scene = task.build_pickcube_mjcf_scene(config, robot)
    mjcf_source, mjcf = task.compile_pickcube_task_artifact(config, mjcf_scene, legacy,
        frame_bindings={'panda-v1/base': FrameReference('panda-v1', 'link0'),
                        'panda-v1/ee': FrameReference('panda-v1', 'nutassembly_ee_site'),
                        'tabletop-v1/top': FrameReference('tabletop-v1', 'grasp_table')},
        cube_frame='PickCube')
    usd_source, usd_scene, usd = task.compile_pickcube_isaac_task_artifact(config, legacy, robot=robot)
    assert mjcf_source.identity_hash == usd_source.identity_hash
    assert mjcf.semantics == usd.semantics == legacy.semantics
    assert mjcf.initialization == usd.initialization == legacy.initialization
    assert mjcf.timebase == usd.timebase == legacy.timebase
    assert mjcf.scene_identity_hash == mjcf_scene.identity_hash
    assert usd.scene_identity_hash == usd_scene.identity_hash
    assert mjcf.legacy_frame_bindings['cube-v1'] == FrameReference('cube-v1', 'PickCube')
    assert usd.legacy_frame_bindings['cube-v1'] == FrameReference('cube-v1', 'cube')


@pytest.mark.parametrize('provider', ['mujoco', 'geophys'])
def test_position_robot_composes_checked_canonical_task_source(provider):
    import sys
    from dataclasses import replace
    from task_env.controllers.canonical.execution import build_reference_position_controller
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.runtime.sessions.source_composition_adapters import declared_robot_source_composer
    from task_env.tasks.pick_cube import specialization as task

    physical_config = resolve_task_env_config(task.PickCubeReferenceEnv, {
        'execution': {'physics_provider': provider, 'physics_backend': 'cpu', 'deployment': 'in_process', 'interpreter': sys.executable},
        'controller': {'profile_id': 'panda-joint-effort-reference-v1'},
        'episode': {'horizon': 8},
    })
    position_config = resolve_task_env_config(task.PickCubeReferenceEnv, {
        'execution': {'physics_provider': provider, 'physics_backend': 'cpu', 'deployment': 'in_process', 'interpreter': sys.executable},
        'controller': {'profile_id': 'r3_continuous_v1'}, 'episode': {'horizon': 8},
    })
    binding = task.PickCubeReferenceEnv.selected_binding(physical_config)
    try:
        value = binding.build_for_request(provider, 'cpu', 31, 8)
        source, artifact = value['source'], value['artifact']
        dynamic_profile, _ = task._r3_dynamic_profile()
        controller = build_reference_position_controller(artifact, source,
            profile_id='r3_continuous_v1', dynamic_profile=dynamic_profile,
            joint_velocity_limit_rad_s=task.PICKCUBE_R3_CONTINUOUS_PROFILE_V1['joint_velocity_limit_rad_s'])
        compose = declared_robot_source_composer(position_config, robot_uid=position_config.robot_uid,
            existing_robot_entity=task.PickCubeReferenceEnv.default_robot_source_uid,
            task_body_names=task.PickCubeReferenceEnv.robot_source_roots,
            task_site_transfers=task.PickCubeReferenceEnv.robot_source_site_transfers)
        adapted = compose(source, artifact=artifact, controller=controller)
        assert adapted.position_subject_binding.plan.artifact_identity_hash == artifact.identity_hash
        assert adapted.position_subject_binding.plan.source_closure_digest == source.source_closure_digest
        assert adapted.scene_definition is source.scene_definition
        xml = source.scene_source.xml
        assert '0 0 -9.81' in xml
        tampered = replace(source, source_snapshot_receipt=None,
            scene_source=replace(source.scene_source, xml=xml.replace('0 0 -9.81', '0 0 -9.8', 1)))
        with pytest.raises(ValueError, match='source closure digest mismatch'):
            compose(tampered, artifact=artifact, controller=controller)
    finally:
        binding.close_task_resources()
