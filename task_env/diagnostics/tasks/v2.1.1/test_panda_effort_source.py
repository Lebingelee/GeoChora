"""Pure admission checks for the Panda transmission used by formal PickCube."""

import xml.etree.ElementTree as ET

import pytest

from task_env.runtime.sessions.mujoco_composition import panda_effort_source_limits
from task_env.runtime.sessions.source import source_resource_receipt


def test_formal_position_and_effort_share_task_binding_factory(monkeypatch):
    from task_env import make_env
    from task_env.tasks.pick_cube import specialization

    calls = []
    factory = specialization.make_reference_binding
    def capture(**kwargs):
        calls.append(kwargs.get('physical_kind'))
        return factory(**kwargs)
    monkeypatch.setattr(specialization, 'make_reference_binding', capture)
    for profile in ('r3_continuous_v1', 'panda-joint-effort-reference-v1'):
        env = make_env('pick-cube-p16-reference-v1', config={
            'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process'},
            'controller': {'profile_id': profile},
        })
        env.close()
    assert calls == [None, 'joint']


def test_effort_intent_precedes_scene_import_and_controls_writer_ownership(monkeypatch):
    from dataclasses import replace
    from task_env import make_env
    from task_env.robots.panda import PandaAgent
    from task_env.runtime.sessions import source_composition_adapters, source_scene_import

    events = []
    prepare = source_composition_adapters.prepare_robot_source_intent
    declare = source_scene_import.declare_panda_scene
    def capture_intent(source, **kwargs):
        assert source.scene_definition is None
        result = prepare(source, **kwargs)
        events.append('intent')
        return result
    def capture_scene(*args, **kwargs):
        assert events == ['intent']
        events.append('scene')
        return declare(*args, **kwargs)
    monkeypatch.setattr(source_composition_adapters, 'prepare_robot_source_intent', capture_intent)
    monkeypatch.setattr(source_scene_import, 'declare_panda_scene', capture_scene)
    config = {'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process'},
              'controller': {'profile_id': 'panda-direct-effort-v1'}}
    env = make_env('pick-cube-p16-reference-v1', config=config)
    try:
        assert events == ['intent', 'scene']
        assert len(env.value['resolved_configuration']['source_composition_intent_v1_sha256']) == 64
    finally:
        env.close()

    original_recipe = PandaAgent.source_recipe_for_profile
    def foreign_writer(robot, profile):
        recipe = original_recipe(robot, profile)
        return replace(recipe, resource_writers=tuple((entity, actuator, 'foreign-writer')
                                                       for entity, actuator, _ in recipe.resource_writers))
    monkeypatch.setattr(PandaAgent, 'source_recipe_for_profile', foreign_writer)
    events.clear()
    with pytest.raises(ValueError, match='writer resources differ'):
        make_env('pick-cube-p16-reference-v1', config=config)


def test_position_freezes_input_intent_before_scene_import(monkeypatch):
    from task_env import make_env
    from task_env.runtime.sessions import source_composition_adapters, source_scene_import

    inputs = []
    prepare = source_composition_adapters.prepare_robot_source_intent
    declare = source_scene_import.declare_panda_scene
    def capture_intent(source, **kwargs):
        result = prepare(source, **kwargs)
        inputs.append((source.scene_definition, result[0].identity_hash))
        return result
    def capture_scene(*args, **kwargs):
        assert inputs and inputs[0][0] is None
        return declare(*args, **kwargs)
    monkeypatch.setattr(source_composition_adapters, 'prepare_robot_source_intent', capture_intent)
    monkeypatch.setattr(source_scene_import, 'declare_panda_scene', capture_scene)
    env = make_env('pick-cube-p16-reference-v1', config={
        'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process'},
        'controller': {'profile_id': 'r3_continuous_v1'},
    })
    try:
        assert env.value['resolved_configuration']['input_source_composition_intent_v1_sha256'] == inputs[0][1]
    finally:
        env.close()


@pytest.mark.parametrize('profile', ('panda-direct-effort-v1', 'panda-joint-effort-reference-v1'))
def test_effort_without_solution_does_not_prepare_position_readiness(monkeypatch, profile):
    from task_env import make_env
    from task_env.tasks.pick_cube import specialization

    def unexpected_readiness(**_kwargs):
        raise AssertionError('effort construction selected a Position Solution')

    monkeypatch.setattr(specialization, '_prepare_reference_source', unexpected_readiness)
    env = make_env('pick-cube-p16-reference-v1', config={
        'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process'},
        'controller': {'profile_id': profile},
    })
    try:
        assert env.value['physical_execution'].controllers == env.robot.controllers
        assert env.value['solution'] is None
    finally:
        env.close()


def test_formal_position_and_effort_share_task_and_robot_scene():
    from task_env import make_env

    declarations = []
    for profile in ('r3_continuous_v1', 'panda-joint-effort-reference-v1'):
        env = make_env('pick-cube-p16-reference-v1', config={
            'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process'},
            'controller': {'profile_id': profile},
        })
        try:
            source = env.value['source']
            declarations.append((env.robot.uid, env.value['artifact'].identity_hash,
                source.scene_definition.identity_hash, dict(source.bodies), dict(source.frames)))
        finally:
            env.close()
    assert declarations[0] == declarations[1]


def test_public_solution_factory_releases_its_preparation_source(monkeypatch):
    from task_env.runtime.sessions import source as source_module
    from task_env.tasks.pick_cube import build_readiness_solution

    captured = []
    snapshot = source_module.snapshot_legacy_mjcf_source
    def capture(source):
        result = snapshot(source)
        captured.append(result.execution_source_receipt.snapshot_root)
        return result
    monkeypatch.setattr(source_module, 'snapshot_legacy_mjcf_source', capture)
    solution = build_readiness_solution(controller_profile='r3_continuous_v1')
    assert solution.identity
    assert len(captured) == 1 and not captured[0].exists()


def test_formal_env_releases_its_source_once(monkeypatch):
    from task_env import make_env
    from task_env.runtime.sessions.source import ExecutionSourceReceiptV1

    env = make_env('pick-cube-p16-reference-v1', config={
        'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process'},
        'controller': {'profile_id': 'panda-direct-effort-v1'},
    })
    receipt = source_resource_receipt(env.value['source'])
    snapshot = receipt.snapshot_root
    calls = []
    original = ExecutionSourceReceiptV1.close
    def close(self):
        calls.append(self)
        return original(self)
    monkeypatch.setattr(ExecutionSourceReceiptV1, 'close', close)
    env.close()
    env.close()
    assert calls == [receipt]
    assert not snapshot.exists()


def test_panda_source_preserves_paired_transmission_and_signed_limits():
    actuators = ''.join(
        f'<general name="actuator{i}" class="panda" joint="joint{i}" '
        'gainprm="1" biasprm="0 -1 0"/>' for i in range(1, 8)
    ) + ('<general name="actuator8" class="panda" tendon="split" '
         'gainprm="1" biasprm="0 -1 0"/>')
    root = ET.fromstring(
        '<mujoco><default><default class="panda"><general biastype="affine" '
        'forcerange="-5 5"/></default></default>'
        '<tendon><fixed name="split"><joint joint="finger_joint1" coef="0.5"/>'
        '<joint joint="finger_joint2" coef="0.5"/></fixed></tendon>'
        '<equality><joint joint1="finger_joint1" joint2="finger_joint2"/></equality>'
        f'<actuator>{actuators}</actuator></mujoco>'
    )
    assert panda_effort_source_limits(root) == [(-5., 5.)] * 8
    root.find('./tendon/fixed/joint').set('coef', '1')
    with pytest.raises(ValueError, match='tendon/equality'):
        panda_effort_source_limits(root)


def test_canonical_source_owns_and_validates_input_snapshot(monkeypatch):
    from dataclasses import replace
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.runtime.sessions.source import source_resource_receipt
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv
    from task_env.runtime.sessions import source_composition_adapters

    calls = []
    build = source_composition_adapters.prepare_panda_source_effort_factory
    def record(*args, **kwargs):
        calls.append(args[3])
        return build(*args, **kwargs)
    monkeypatch.setattr(source_composition_adapters, 'prepare_panda_source_effort_factory', record)

    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu'},
        'controller': {'profile_id': 'panda-joint-effort-reference-v1'},
        'episode': {'horizon': 8},
    })
    binding = PickCubeReferenceEnv.selected_binding(config)
    try:
        value = binding.build_for_request('mujoco', 'cpu', 31, 8)
        source = value['source']
        assert calls == [source]
        receipt = source_resource_receipt(source)
        assert receipt is source.source_snapshot_receipt
        assert value['source_sha256']['original_closure'] == receipt.source_closure_digest
        assert value['resolved_configuration']['original_closure'] == receipt.source_closure_digest
        assert source.execution_source_receipt is None
        assert receipt.snapshot_root.is_dir()
        receipt.validate_snapshot()
        with pytest.raises(ValueError, match='snapshot differs'):
            replace(source, scene_source=replace(source.scene_source, xml=source.scene_source.xml + ' '))
        snapshot = receipt.snapshot_root
    finally:
        source_resource_receipt(value['source']).close()
    assert not snapshot.exists()


def test_effort_construction_accepts_task_scene_without_historical_hash(monkeypatch):
    from copy import deepcopy
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    task_config = deepcopy(PickCubeReferenceEnv.selected_task_configuration())
    task_config['recipe']['scene']['table_half_size'][0] = .29
    monkeypatch.setattr(PickCubeReferenceEnv, 'selected_task_configuration', staticmethod(lambda: task_config))
    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process'},
        'controller': {'profile_id': 'panda-direct-effort-v1'},
        'episode': {'horizon': 8},
    })
    binding = PickCubeReferenceEnv._build_selected_binding(config)
    try:
        value = binding.build_for_request('mujoco', 'cpu', 31, 8)
        source = value['source']
        table = ET.fromstring(source.scene_source.xml).find(".//geom[@name='grasp_table_geom']")
        assert tuple(map(float, table.get('size').split())) == (.29, .2, .01)
        receipt = source.source_snapshot_receipt
        receipt.validate_snapshot()
        assert value['source_sha256']['original_closure'] == receipt.source_closure_digest
        assert value['physical_execution'].controllers
        with pytest.raises(ValueError, match='requested backend'):
            binding.build_for_request('mujoco', 'cuda', 31, 8)
    finally:
        source_resource_receipt(value['source']).close()


def test_effort_construction_accepts_multiple_declared_robot_roots(tmp_path, monkeypatch):
    from dataclasses import replace
    from task_env import make_env
    from task_env.robots.panda import PandaAgent

    original = PandaAgent.asset_manifest
    monkeypatch.setattr(PandaAgent, 'asset_manifest', lambda self: replace(
        original(self), asset_roots=(*original(self).asset_roots, tmp_path)))
    env = make_env('pick-cube-p16-reference-v1', config={
        'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process'},
        'controller': {'profile_id': 'panda-direct-effort-v1'},
    })
    try:
        source = env.value['source']
        source.source_snapshot_receipt.validate_snapshot()
        assert env.value['physical_execution'].controllers == env.robot.controllers
    finally:
        env.close()


def test_failed_robot_composition_releases_canonical_source_snapshot():
    from dataclasses import replace
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu'},
        'controller': {'profile_id': 'panda-joint-effort-reference-v1'},
        'episode': {'horizon': 8},
    })
    binding = PickCubeReferenceEnv.selected_binding(config)
    snapshots = []
    build = binding.build
    def capture(request):
        value = build(request)
        snapshots.append(value['source'].source_snapshot_receipt.snapshot_root)
        return value
    def fail(*args, **kwargs):
        raise ValueError('composition rejected')
    binding = replace(binding, build=capture, compose_robot_source=fail)
    with pytest.raises(ValueError, match='composition rejected'):
        binding.build_for_request('mujoco', 'cpu', 31, 8)
    assert len(snapshots) == 1 and not snapshots[0].exists()


def test_rejected_robot_composer_does_not_prepare_a_source(monkeypatch):
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.pick_cube import specialization

    config = resolve_task_env_config(specialization.PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu'},
        'controller': {'profile_id': 'panda-joint-effort-reference-v1'},
    })
    def unexpected_source(**_kwargs):
        pytest.fail('binding admission must not prepare a Task source')
    def reject(cls, binding, config):
        raise ValueError('source composition rejected')
    monkeypatch.setattr(specialization, '_prepare_reference_source', unexpected_source)
    monkeypatch.setattr(specialization.PickCubeReferenceEnv, '_bind_robot_source_composer', classmethod(reject))
    with pytest.raises(ValueError, match='source composition rejected'):
        specialization.PickCubeReferenceEnv._build_selected_binding(config)
