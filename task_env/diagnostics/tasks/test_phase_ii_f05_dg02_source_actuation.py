from __future__ import annotations

import pytest

from task_env.artifacts import JointReference
from task_env.runtime.sessions.leaf_control import (
    GeoPhysUsdPositionDriveV1,
    GeoPhysUsdSourceActuationReceiptV2,
)


def _receipt():
    rows = []
    arm = (
        (-2.8973, 2.8973, 4500.0, 450.0, (-2.8973, 2.8973), (-87.0, 87.0)),
        (-1.7628, 1.7628, 4500.0, 450.0, (-1.7628, 1.7628), (-87.0, 87.0)),
        (-2.8973, 2.8973, 3500.0, 350.0, (-2.8973, 2.8973), (-87.0, 87.0)),
        (-3.0718, -0.0698, 3500.0, 350.0, (-3.0718, -0.0698), (-87.0, 87.0)),
        (-2.8973, 2.8973, 2000.0, 200.0, (-2.8973, 2.8973), (-12.0, 12.0)),
        (-0.0175, 3.7525, 2000.0, 200.0, (-0.0175, 3.7525), (-12.0, 12.0)),
        (-2.8973, 2.8973, 2000.0, 200.0, (-2.8973, 2.8973), (-12.0, 12.0)),
    )
    for index, (lo, hi, stiffness, damping, ctrl_range, force_range) in enumerate(arm, 1):
        rows.append(GeoPhysUsdPositionDriveV1(
            'geophys-usd-position-drive-v1', JointReference('panda-main', f'joint{index}'),
            f'joint{index}', index - 1, f'actuator{index}', index - 1, 'radian',
            lo, hi, stiffness, 0.0, stiffness, damping, 0.0, 0.0, 0.0,
            True, *ctrl_range, True, *force_range,
        ))
    for index, name in enumerate(('finger_joint1', 'finger_joint2'), 7):
        rows.append(GeoPhysUsdPositionDriveV1(
            'geophys-usd-position-drive-v1', JointReference('panda-main', name),
            name, index, 'actuator8', 7, 'meter', 0.0, 0.04, 0.01568627451,
            0.0, 100.0, 10.0, 0.0, 0.0, 0.0,
            True, 0.0, 255.0, True, -100.0, 100.0,
        ))
    return GeoPhysUsdSourceActuationReceiptV2(
        'geophys-usd-source-actuation-receipt-v2', 'synthetic_fixture',
        '1' * 64, '2' * 64, '3' * 64, '4' * 64, 'geophys-test',
        'geophys-usd-position-f05-native-v1', 'cpu', 'cpu', 'best_effort',
        0.002, 5, 'panda-main/dg02-source-actuation-v2', 9, tuple(rows),
        'split', ('finger_joint1', 'finger_joint2'), (0.5, 0.5),
        'finger_joint1_finger_joint2', (0.005, 1.0), (0.95, 0.99, 0.001), '5' * 64,
    )


def test_source_actuation_receipt_maps_nine_targets_to_eight_public_actuators():
    receipt = _receipt()
    arm = {
        'panda-main/joint1': 0.012,
        'panda-main/joint2': -0.568,
        'panda-main/joint3': 0.0,
        'panda-main/joint4': -2.811,
        'panda-main/joint5': 0.0,
        'panda-main/joint6': 3.037,
        'panda-main/joint7': 0.741,
    }
    targets = receipt.commands(arm, 0.08)
    controls = receipt.control_inputs(targets)
    assert len(targets) == 9
    assert len(controls) == 8
    assert len({index for index, _name, _value in controls}) == 8
    by_name = {name: value for _index, name, value in controls}
    assert by_name['actuator8'] == pytest.approx(255.0, abs=2e-5)
    assert by_name['actuator4'] == pytest.approx(-2.811)
    assert receipt.equality_solref == (0.005, 1.0)
    assert receipt.equality_solimp == (0.95, 0.99, 0.001)


def test_source_actuation_receipt_rejects_independent_finger_targets():
    receipt = _receipt()
    targets = list(receipt.commands({
        f'panda-main/joint{index}': value for index, value in enumerate(
            (0.012, -0.568, 0.0, -2.811, 0.0, 3.037, 0.741), 1,
        )
    }, 0.04))
    targets[-1] = (targets[-1][0], targets[-1][1], targets[-1][2] - 0.01)
    with pytest.raises(ValueError, match='equal source finger targets'):
        receipt.control_inputs(tuple(targets))


def test_f05_native_candidate_requires_the_frozen_dg01_action_config():
    from task_env.environment.config import ActionConfig
    from task_env.tasks.position_candidate.builder import _validate_f05_native_position_action_config

    expected = ActionConfig(
        joint_position_correction_gain=1.0,
        gripper_default_force_N=100.0,
    )
    assert _validate_f05_native_position_action_config(expected) is None
    with pytest.raises(ValueError, match='accepted DG01 control semantics'):
        _validate_f05_native_position_action_config(ActionConfig())
