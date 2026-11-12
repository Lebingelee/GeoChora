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
    from task_env.controllers.canonical import execution
    from task_env.controllers.canonical.execution import ReferenceExecutionController, StableArmTargetHold
    from task_env.tasks.pick_cube import specialization as pickcube
    from task_env.tasks.nut_assembly import specialization as nut

    original = execution.build_reference_position_controller
    constructed = []
    profiles = []
    profile = ReferenceExecutionController.identity_profile
    def capture_profile(controller):
        result = profile(controller)
        profiles.append((controller, result))
        return result
    monkeypatch.setattr(ReferenceExecutionController, 'identity_profile', capture_profile)
    def capture(artifact, source, **kwargs):
        controller = original(artifact, source, **kwargs)
        constructed.append((controller, artifact, source, kwargs['profile_id']))
        return controller
    monkeypatch.setattr(execution, 'build_reference_position_controller', capture)
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
        assert len(profiles) == 1 and profiles[0][0] is controller
        assert value['resolved_configuration']['gripper_control_hz'] == profiles[0][1]['gripper_control_hz']
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
    original_source = specialization._compile_task_source
    original_scene = source_scene_import.declare_panda_scene
    from task_env.runtime.sessions import source_composition_adapters
    original_control = source_composition_adapters.build_panda_direct_effort_execution

    def source(*args, **kwargs):
        value = original_source(*args, **kwargs)
        built.append(value[2].agents[0])
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
    monkeypatch.setattr(specialization, '_compile_task_source', source)
    monkeypatch.setattr(source_scene_import, 'declare_panda_scene', scene)
    monkeypatch.setattr(source_composition_adapters, 'build_panda_direct_effort_execution', control)
    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'mujoco'},
        'controller': {'profile_id': 'panda-direct-effort-v1'},
    })
    binding = PickCubeReferenceEnv.selected_binding(config)
    try:
        value = binding.build_for_request('mujoco', 'cpu', 31, 8)
        assert len(built) == len(declared) == len(bound) == 1
        assert built[0] is declared[0] is bound[0]
    finally:
        from task_env.runtime.sessions.source import source_resource_receipt
        source_resource_receipt(value['source']).close()


@pytest.mark.parametrize('physical', [False, True])
def test_usd_build_failure_does_not_create_mjcf_source(physical, monkeypatch):
    from task_env.runtime.sessions import source as source_module
    from task_env.tasks.pick_cube import specialization

    failure = RuntimeError('USD source preparation failed')
    def unexpected(*args, **kwargs):
        pytest.fail('USD readiness must not allocate an MJCF snapshot')
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(source_module, 'snapshot_legacy_mjcf_source', unexpected)
    monkeypatch.setattr(specialization, 'compile_panda_box_task', unexpected)
    monkeypatch.setattr(specialization, 'build_pickcube_isaac_runtime_input_v1', fail)
    with pytest.raises(RuntimeError) as raised:
        specialization.build_isaac_reference(
            delivery_manifest='unused', include_solution=False,
            physical_kind='direct' if physical else None,
            physical_drive='disabled' if physical else None,
        )
    assert raised.value is failure


def test_usd_readiness_failure_prevents_delivery_construction(monkeypatch):
    from task_env.tasks.pick_cube import specialization
    from task_env.tasks.pick_cube.solution import PickCubeReadinessConfig

    failure = RuntimeError('readiness failed')
    def fail(*args, **kwargs):
        raise failure
    def unexpected(*args, **kwargs):
        pytest.fail('delivery must not be built after failed readiness')
    monkeypatch.setattr(PickCubeReadinessConfig, 'from_resolved_config', fail)
    monkeypatch.setattr(specialization, 'build_pickcube_isaac_runtime_input_v1', unexpected)
    with pytest.raises(RuntimeError) as raised:
        specialization.build_isaac_reference(delivery_manifest='unused', include_solution=False)
    assert raised.value is failure


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


@pytest.mark.parametrize('profile', ['r3_continuous_v1', 'panda-direct-effort-v1'])
def test_source_composition_failure_releases_source_before_controller(profile, monkeypatch):
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.runtime.sessions import source as source_module, source_composition_adapters
    from task_env.tasks.pick_cube.task import PickCubeReferenceEnv

    receipts = []
    snapshot = source_module.snapshot_legacy_mjcf_source
    failure = RuntimeError('Robot composition failed')
    def capture(*args, **kwargs):
        source = snapshot(*args, **kwargs)
        receipts.append(source_resource_receipt(source))
        return source
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(source_module, 'snapshot_legacy_mjcf_source', capture)
    monkeypatch.setattr(source_composition_adapters, 'prepare_robot_source_intent', fail)
    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'mujoco'}, 'controller': {'profile_id': profile}})
    with pytest.raises(RuntimeError) as raised:
        PickCubeReferenceEnv.selected_binding(config).build_for_request('mujoco', 'cpu', 31, 8)
    assert raised.value is failure
    assert len(receipts) == 1 and not receipts[0].snapshot_root.exists()


def test_assembled_position_builds_controller_from_selected_source(monkeypatch):
    from task_env.controllers.canonical import execution
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    seen = []
    original = execution.build_reference_position_controller
    def capture(artifact, source, **options):
        seen.append((artifact, source))
        return original(artifact, source, **options)
    monkeypatch.setattr(execution, 'build_reference_position_controller', capture)
    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'mujoco'},
        'robot': {'uid': 'panda-arm-hand-v1'}, 'controller': {'profile_id': 'r1_split'}})
    binding = PickCubeReferenceEnv._build_selected_binding(config)
    value = binding.build_for_request('mujoco', 'cpu', 31, 8)
    try:
        assert len(seen) == 1 and seen[0][0] is value['artifact']
        assert value['source'].source_composition_request.robot_uid == binding.robot.uid
        assert seen[0][1].source_id == value['source'].source_id
        assert value['controller'].arm.writer_id != value['controller'].hand.writer_id
        assert value['resolved_configuration']['controller_profile'] == 'r1_split'
    finally:
        source_resource_receipt(value['source']).close()


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
                                              physical_kind='direct', physical_drive='disabled')
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
        PickCubeReferenceEnv.selected_binding(config).build_for_request('mujoco', 'cpu', 31, 8)
    assert raised.value is failure
    assert len(receipts) == 1 and not receipts[0].snapshot_root.exists()


def test_mujoco_source_lowering_applies_declared_options_and_rejects_missing_option():
    import xml.etree.ElementTree as ET
    from task_env.runtime.sessions.mujoco_composition import apply_mjcf_option_overrides

    source = '<mujoco><option timestep="0.002"/><worldbody/></mujoco>'
    lowered = ET.fromstring(apply_mjcf_option_overrides(source, {'noslip_iterations': 2}))
    assert lowered.find('option').attrib == {'timestep': '0.002', 'noslip_iterations': '2'}
    with pytest.raises(ValueError, match='no option element'):
        apply_mjcf_option_overrides('<mujoco/>', {'noslip_iterations': 2})


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
        from task_env.runtime.sessions.source import source_resource_receipt
        source_resource_receipt(value['source']).close()


def test_assembled_robot_rejects_foreign_task_joint_mapping_and_releases_source(monkeypatch):
    from dataclasses import replace
    from task_env import make_env
    from task_env.tasks.pick_cube import specialization

    prepare = specialization._prepare_reference_source
    receipts = []
    def altered(*args, **kwargs):
        prepared = prepare(*args, **kwargs)
        receipts.append(source_resource_receipt(prepared.source))
        joints = dict(prepared.source.joints)
        joints['panda-v1/joint1'] = 'foreign_joint'
        return prepared._replace(source=replace(prepared.source, joints=joints))
    monkeypatch.setattr(specialization, '_prepare_reference_source', altered)
    with pytest.raises(ValueError, match='Task joint binding differs from the declared Robot source'):
        make_env('pick-cube-p16-reference-v1', config={
            'execution': {'physics_provider': 'mujoco'},
            'robot': {'uid': 'panda-arm-hand-v1'},
            'controller': {'profile_id': 'r1_split'},
        })
    assert receipts and all(not receipt.snapshot_root.exists() for receipt in receipts)


@pytest.mark.parametrize('uid', ['pick-cube-p16-reference-v1', 'nut-assembly-outcome-reference-v1'])
def test_tabletop_build_uses_selected_robot_source_root(uid, tmp_path, monkeypatch):
    from dataclasses import replace
    from shutil import copytree
    from task_env import make_env

    original = PandaAgent.asset_manifest
    manifest = original(PandaAgent())
    root = tmp_path / 'robot'
    copytree(manifest.asset_roots[0], root)
    relocated = replace(manifest, asset_roots=(root,), mjcf_sources=(root / 'panda.xml',))
    monkeypatch.setattr(PandaAgent, 'asset_manifest', lambda self: relocated)
    env = make_env(uid, config={'execution': {'physics_provider': 'mujoco'}})
    try:
        source = env.value['source']
        assert source.agents[0] is env.binding.robot
        receipt = source_resource_receipt(source)
        receipt.validate_snapshot()
        import xml.etree.ElementTree as ET
        compiler = ET.fromstring(receipt.closure_files['canonical-source.xml']).find('compiler')
        assert compiler.get('meshdir') == str(root / 'assets')
        assert receipt.snapshot_root.is_dir()
    finally:
        env.close()


def test_source_snapshot_rejects_assets_outside_component_roots(tmp_path, monkeypatch):
    from dataclasses import replace
    from task_env.assembly.panda_box import compile_panda_box_task
    from task_env.runtime.sessions.source import snapshot_legacy_mjcf_source
    from task_env.tasks.pick_cube.specialization import _declaration, _environment_config

    robot = PandaAgent()
    source = compile_panda_box_task(_declaration(), config=_environment_config(), robot=robot).source
    manifest = robot.asset_manifest()
    monkeypatch.setattr(PandaAgent, 'asset_manifest',
                        lambda self: replace(manifest, asset_roots=(tmp_path,)))
    with pytest.raises(ValueError, match='outside declared component asset roots'):
        snapshot_legacy_mjcf_source(source)


def test_assembled_robot_composer_uses_declared_asset_root(tmp_path, monkeypatch):
    from dataclasses import replace
    from task_env import make_env
    from task_env.robots.assembled_panda import AssembledPandaAgent
    from task_env.runtime.sessions.source import source_asset_bytes

    original = AssembledPandaAgent.asset_manifest
    manifest = original(AssembledPandaAgent())
    root = tmp_path / 'declared-robot'
    root.mkdir()
    for source in manifest.mjcf_sources:
        (root / source.name).write_bytes(source.read_bytes())
        for relative, content in source_asset_bytes(manifest.asset_roots[0], source.read_text()).items():
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
    (root / 'LICENSE').write_bytes((manifest.asset_roots[0] / 'LICENSE').read_bytes())
    relocated = replace(manifest, asset_roots=(root,),
        mjcf_sources=tuple(root / source.name for source in manifest.mjcf_sources))
    monkeypatch.setattr(AssembledPandaAgent, 'asset_manifest', lambda _self: relocated)
    env = make_env('pick-cube-p16-reference-v1', config={
        'execution': {'physics_provider': 'mujoco'},
        'robot': {'uid': 'panda-arm-hand-v1'},
        'controller': {'profile_id': 'r1_split'},
    })
    try:
        declaration = env.value['source'].composition_runtime_input.fixed_declaration
        assert declaration.parent_source.base_dir == root.resolve()
        assert all(source.base_dir == root.resolve() for source in declaration.source_by_entity.values())
    finally:
        env.close()


def test_assembled_robot_rejects_foreign_asset_manifest(monkeypatch):
    from dataclasses import replace
    from task_env import make_env
    from task_env.robots.assembled_panda import AssembledPandaAgent

    original = AssembledPandaAgent.asset_manifest
    monkeypatch.setattr(AssembledPandaAgent, 'asset_manifest',
        lambda self: replace(original(self), owner_uid='foreign-robot'))
    with pytest.raises(ValueError, match='Robot source manifest differs from the selected source recipe'):
        make_env('pick-cube-p16-reference-v1', config={
            'execution': {'physics_provider': 'mujoco'},
            'robot': {'uid': 'panda-arm-hand-v1'},
            'controller': {'profile_id': 'r1_split'},
        })


@pytest.mark.parametrize('uid', [
    'pick-cube-p16-reference-v1', 'nut-assembly-outcome-reference-v1',
    'pendulum-v1', 'two-wheel-balance-v1',
])
def test_formal_construction_uses_one_selected_robot_declaration(uid):
    from task_env import make_env

    env = make_env(uid, config={'execution': {'physics_provider': 'mujoco'}})
    try:
        selected = env.binding.robot
        assert selected.uid == env.resolved_public_config.robot_uid
        assert env.value['source'].agents == (selected,)
        assert env.value['source'].composition.agent_uids == (selected.uid,)
        assert env.robot.declaration is selected
        assert env.robot.controllers and env.robot.subjects
        assert env._task_definition is not None
        assert env._task_lifecycle.task_definition is env._task_definition
    finally:
        env.close()


@pytest.mark.parametrize('uid', [
    'pick-cube-p16-reference-v1', 'nut-assembly-outcome-reference-v1',
])
def test_tabletop_source_uses_selected_robot_actuation_declaration(uid, monkeypatch):
    from task_env import make_env
    from task_env.robots.panda import PandaAgent

    calls = []
    original = PandaAgent.reference_source_actuation
    def capture(robot):
        calls.append(robot)
        return original(robot)
    monkeypatch.setattr(PandaAgent, 'reference_source_actuation', capture)
    env = make_env(uid, config={'execution': {'physics_provider': 'mujoco'}})
    try:
        assert any(robot is env.binding.robot for robot in calls)
        targets, opening = original(env.binding.robot)
        assert env.value['source'].joint_targets == targets
        assert env.value['source'].open_actuators == opening
    finally:
        env.close()


def test_assembled_composition_uses_the_robot_selected_by_the_common_entry(monkeypatch):
    from task_env import make_env
    from task_env.robots.assembled_panda import AssembledPandaAgent

    original = AssembledPandaAgent.position_subject_layout
    compiled = []
    def capture(robot, *args, **kwargs):
        compiled.append(robot)
        return original(robot, *args, **kwargs)
    monkeypatch.setattr(AssembledPandaAgent, 'position_subject_layout', capture)
    env = make_env('pick-cube-p16-reference-v1', config={
        'execution': {'physics_provider': 'mujoco'},
        'robot': {'uid': 'panda-arm-hand-v1'},
        'controller': {'profile_id': 'r1_split'},
    })
    try:
        assert compiled == [env.binding.robot]
        request = env.value['source'].source_composition_request
        assert request.robot_uid == env.binding.robot.uid
        edge = request.attachments[0]
        assert (edge.parent_entity_id, edge.parent_frame_id, edge.child_entity_id,
                edge.child_frame_id, edge.rule_id) == env.binding.robot.source_recipe_for_profile('r1_split').component_edges[0]
        assert {'task_env/runtime/sessions/mujoco_composition.py',
                'task_env/assembly/panda_source_profiles.py',
                'task_env/assembly/fixed_attachment.py'} <= set(env.value['source_sha256'])
    finally:
        env.close()


def test_assembled_composition_rejects_robot_attachment_mismatch(monkeypatch):
    from dataclasses import replace
    from task_env import make_env
    from task_env.robots.assembled_panda import AssembledPandaAgent

    original = AssembledPandaAgent.source_recipe

    def foreign_attachment(robot):
        recipe = original(robot)
        parent, _frame, child, child_frame, rule = recipe.component_edges[0]
        return replace(recipe, component_edges=((parent, 'foreign_site', child, child_frame, rule),))

    monkeypatch.setattr(AssembledPandaAgent, 'source_recipe', foreign_attachment)
    with pytest.raises(ValueError, match='attachment differs from the admitted fixed source'):
        make_env('pick-cube-p16-reference-v1', config={
            'execution': {'physics_provider': 'mujoco'},
            'robot': {'uid': 'panda-arm-hand-v1'},
            'controller': {'profile_id': 'r1_split'},
        })


@pytest.mark.parametrize(('robot_uid', 'profile', 'component_count'), [
    ('panda-v1', 'r3_continuous_v1', 1),
    ('panda-arm-hand-v1', 'r1_split', 2),
])
def test_robot_position_layout_is_compiled_by_runtime(robot_uid, profile, component_count, monkeypatch):
    from task_env import make_env
    from task_env.runtime.sessions import position_subject_binding
    from task_env.robots.source_recipe import PositionSubjectLayoutV1

    calls = []
    compile_subjects = position_subject_binding.compile_position_subjects
    def capture(**kwargs):
        calls.append(kwargs['layout'])
        return compile_subjects(**kwargs)
    monkeypatch.setattr(position_subject_binding, 'compile_position_subjects', capture)
    env = make_env('pick-cube-p16-reference-v1', config={
        'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process'},
        'robot': {'uid': robot_uid}, 'controller': {'profile_id': profile},
    })
    try:
        assert len(calls) == 1 and type(calls[0]) is PositionSubjectLayoutV1
        assert len(calls[0].components) == component_count
        assert len(env.robot.subjects) == component_count
    finally:
        env.close()


def test_nut_mujoco_source_records_provider_lowerer_identity():
    import xml.etree.ElementTree as ET
    from task_env.tasks.nut_assembly.specialization import build_reference

    value = build_reference(provider='mujoco', include_solution=False)
    try:
        assert ET.fromstring(value['source'].scene_source.xml).find('option').get('noslip_iterations') == '2'
        assert value['_contact_profile']['model_option_overrides'] == {'noslip_iterations': 2}
        assert 'task_env/runtime/sessions/mujoco_composition.py' in value['source_sha256']
    finally:
        source_resource_receipt(value['source']).close()
