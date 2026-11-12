"""Pure admission checks for the Panda transmission used by formal PickCube."""

import xml.etree.ElementTree as ET

import pytest

from task_env.runtime.sessions.mujoco_composition import panda_effort_source_limits


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


def test_canonical_source_owns_and_validates_input_snapshot():
    from dataclasses import replace
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.runtime.sessions.source import source_resource_receipt
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu'},
        'controller': {'profile_id': 'panda-joint-effort-reference-v1'},
        'episode': {'horizon': 8},
    })
    binding = PickCubeReferenceEnv.selected_binding(config)
    try:
        source = binding.build_for_request('mujoco', 'cpu', 31, 8)['source']
        receipt = source_resource_receipt(source)
        assert receipt is source.source_snapshot_receipt
        assert source.execution_source_receipt is None
        assert receipt.snapshot_root.is_dir()
        receipt.validate_snapshot()
        with pytest.raises(ValueError, match='snapshot differs'):
            replace(source, scene_source=replace(source.scene_source, xml=source.scene_source.xml + ' '))
        snapshot = receipt.snapshot_root
    finally:
        binding.close_task_resources()
    assert not snapshot.exists()


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
