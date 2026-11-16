"""No SDK is imported: test isolation admission against a small model substitute."""
from types import SimpleNamespace as NS
import numpy as np
import pytest

from task_env.runtime.sessions.mujoco_physical import validate_physical_joint_mapping


def fixture():
    joint_ids = {'arm-joint': 0, 'finger-joint': 1}
    actuator_ids = {'arm-motor': 0, 'finger-position': 1}
    model = NS(
        body=lambda name: NS(id={'base': 1}[name]),
        joint=lambda name: NS(id=joint_ids[name]), actuator=lambda name: NS(id=actuator_ids[name]),
        body_parentid=[0, 0], body_jntnum=[0, 0], jnt_type=[1, 2],
        jnt_axis=np.array([[0., 0., 1.], [0., 1., 0.]]), jnt_dofadr=[0, 1],
        actuator_trntype=[0, 0], actuator_trnid=np.array([[0, 0], [1, 0]]),
        actuator_biastype=[0, 1], actuator_gaintype=[0, 0], actuator_dyntype=[0, 0],
        actuator_gainprm=np.array([[1., 0.], [1000., 0.]]),
        actuator_biasprm=np.array([[0., 0., 0.], [0., -1000., 0.]]),
        actuator_forcelimited=[0, 1], actuator_ctrllimited=[1, 1],
        actuator_ctrlrange=np.array([[-12., 12.], [-.04, .04]]),
        actuator_gear=np.array([[1., 0, 0, 0, 0, 0], [1., 0, 0, 0, 0, 0]]),
        nu=2, opt=NS(disableflags=0))
    mj = NS(mjtJoint=NS(mjJNT_HINGE=1, mjJNT_SLIDE=2),
            mjtBias=NS(mjBIAS_NONE=0, mjBIAS_AFFINE=1), mjtGain=NS(mjGAIN_FIXED=0),
            mjtDyn=NS(mjDYN_NONE=0), mjtTrn=NS(mjTRN_JOINT=0, mjTRN_TENDON=1),
            mjtDisableBit=NS(mjDSBL_ACTUATION=1024))
    channel = NS(entity_id='robot', joint_id='arm', native_drive='disabled',
        native_actuator='arm-motor', transmission_id='motor', kind='revolute', dof_id='dof0',
        target_key=('robot', 'arm', 'dof0'), native_range=(-12., 12.), transmission_coefficient=1.)
    return model, mj, NS(channels=(channel,))


def check(model, mj, binding, *, target='finger-joint'):
    return validate_physical_joint_mapping(model, mj, binding,
        {('robot', 'arm'): NS(axis=(0., 0., 1.))},
        source_joints={'robot/arm': 'arm-joint', 'robot/finger': target},
        torque_actuators={'robot/arm': 'arm-motor'},
        position_actuators={'robot/finger': 'finger-position'},
        joint_targets={'robot/finger': 'finger-position'}, open_actuators=(),
        gripper_force_limit=None, fixed_roots=('base',), build_layout_facts={})


def test_disjoint_position_hold_keeps_its_drive_and_isolates_arm():
    model, mj, binding = fixture()
    dofs, _ = check(model, mj, binding)
    assert dofs[('robot', 'arm', 'dof0')] == 0
    assert model.actuator_gainprm[:, 0].tolist() == [0., 1000.]
    assert model.opt.disableflags == 0


def test_position_hold_cannot_share_a_controlled_dof():
    model, mj, binding = fixture()
    with pytest.raises(ValueError, match='overlaps or differs'):
        check(model, mj, binding, target='arm-joint')
    assert model.actuator_gainprm[:, 0].tolist() == [1., 1000.]


def test_unrecognized_actuator_prevents_any_motor_mutation():
    model, mj, binding = fixture()
    model.nu = 3
    with pytest.raises(ValueError, match='every actuator'):
        check(model, mj, binding)
    assert model.actuator_gainprm[:, 0].tolist() == [1., 1000.]
