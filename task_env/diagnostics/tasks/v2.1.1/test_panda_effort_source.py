"""Pure admission checks for the Panda transmission used by formal PickCube."""

import xml.etree.ElementTree as ET

import pytest

from task_env.runtime.sessions.mujoco_composition import panda_effort_source_limits


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
    build = source_composition_adapters.build_panda_source_effort_profile
    def record(*args, **kwargs):
        calls.append(args[3])
        return build(*args, **kwargs)
    monkeypatch.setattr(source_composition_adapters, 'build_panda_source_effort_profile', record)

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
        binding.close_task_resources()
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
        binding.close_task_resources()


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
    try:
        value = binding.build_for_request('mujoco', 'cpu', 31, 8)
        snapshot = value['source'].source_snapshot_receipt.snapshot_root
        def fail(*args, **kwargs):
            raise ValueError('composition rejected')
        strategy = replace(binding, compose_robot_source=fail).reset_reconstruction_strategy('mujoco', 'cpu', 8)
        with pytest.raises(ValueError, match='composition rejected'):
            strategy._compose(value)
        assert not snapshot.exists()
    finally:
        binding.close_task_resources()


@pytest.mark.parametrize('cleanup_failure', [False, True])
def test_failed_robot_source_composer_releases_prepared_task_source(monkeypatch, cleanup_failure):
    from dataclasses import replace
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu'},
        'controller': {'profile_id': 'panda-joint-effort-reference-v1'},
        'episode': {'horizon': 8},
    })
    selected_binding = PickCubeReferenceEnv.selected_binding
    snapshots = []

    def prepare(cls, config, *, robot):
        binding = selected_binding(config, robot=robot)
        source = binding.build_for_request('mujoco', 'cpu', 31, 8)['source']
        snapshots.append(source.source_snapshot_receipt.snapshot_root)
        assert snapshots[-1].is_dir()
        if cleanup_failure:
            close = binding.close_task_resources
            def fail_after_close():
                close()
                raise RuntimeError('cleanup failed')
            binding = replace(binding, close_task_resources=fail_after_close)
        return binding

    def reject(cls, binding, config):
        raise ValueError('source composition rejected')

    monkeypatch.setattr(PickCubeReferenceEnv, 'selected_binding', classmethod(prepare))
    monkeypatch.setattr(PickCubeReferenceEnv, '_bind_robot_source_composer', classmethod(reject))
    with pytest.raises(ValueError, match='source composition rejected') as caught:
        PickCubeReferenceEnv._build_selected_binding(config)
    if cleanup_failure:
        assert any('cleanup failed' in note for note in caught.value.__notes__)
    assert len(snapshots) == 1
    assert not snapshots[0].exists()
