"""Provider-free checks for the bounded shared direct-effort Controller."""
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import pytest

from task_env.controllers.canonical.physical_controller import DirectJointEffortControllerV1
from task_env.diagnostics.tasks.test_v211_physical_control_contract import _case
from task_env.runtime.sessions.physical_control import PhysicalControlExecutionV1


def test_direct_effort_action_tree_episode_and_bounds():
    plan, context, _, _ = _case()
    controller = DirectJointEffortControllerV1(plan.binding, controller_id='controller-a',
        channel_keys=('arm/drive',))
    state = SimpleNamespace(boundary=context.boundary, sample_clock=context.clock)
    with pytest.raises(ValueError, match='reset'):
        controller.compute({'torque': np.array([1.], np.float32)}, state, context)
    controller.reset_from_realized_state(state)
    batch = controller.compute({'torque': np.array([1.], np.float32)}, state, context)
    assert batch.joint_efforts[0].value == 1.
    assert batch.joint_efforts[0].target_key == ('arm', 'drive', 'dof0')
    assert controller.compute([0.], state, context).joint_efforts[0].value == 0.
    for invalid in ([6.], [float('nan')], [1., 2.], [True]):
        with pytest.raises(ValueError):
            controller.compute(invalid, state, context)
    with pytest.raises(ValueError, match='source'):
        controller.compute([1.], state, replace(context, source_id='foreign'))
    other = replace(context.boundary, episode_id='other')
    with pytest.raises(ValueError, match='episode'):
        controller.compute([1.], SimpleNamespace(boundary=other, sample_clock=context.clock),
                           replace(context, boundary=other))
    assert not PhysicalControlExecutionV1._controller_action_space(controller).contains(
        {'torque': np.array([6.], np.float32)})


def test_direct_effort_reset_state_and_action_rejection_are_pre_effect():
    plan, context, _, _ = _case()
    controller = DirectJointEffortControllerV1(plan.binding, controller_id='controller-a',
        channel_keys=('arm/drive',))
    state = SimpleNamespace(boundary=context.boundary, sample_clock=context.clock)
    controller.reset_from_realized_state(state)
    controller.compute({'torque': np.array([2.], np.float64)}, state, context)
    last = controller.last_action.copy()
    with pytest.raises(ValueError):
        controller.compute({'torque': np.array([6.], np.float32)}, state, context)
    assert np.array_equal(controller.last_action, last)
    with pytest.raises(ValueError, match='Scene'):
        controller.reset_from_realized_state(SimpleNamespace(
            boundary=replace(context.boundary, scene_identity_hash='c'*64)))
    with pytest.raises(ValueError, match='declared writer'):
        DirectJointEffortControllerV1(plan.binding, controller_id='foreign', channel_keys=('arm/drive',))


def test_source_bound_physical_reset_keeps_nonzero_joint_velocity_and_rejects_free_bodies():
    from task_env.artifacts.execution import ResetSampleV1, ResetPlanV1
    from task_env.artifacts import PoseWorld
    args = dict(schema_version='reset-sample-v1', task_artifact_hash='a'*64,
        source_id='source-a', source_closure_digest='b'*64, sampler_id='test', sampler_version='v1',
        task_seed=37, init_row_index=0, init_row_sha256='c'*64,
        joint_position={'arm/drive': 1.}, joint_velocity={'arm/drive': .3},
        sampled_poses_world={}, poses_world={}, free_joint_velocity={},
        free_joint_velocity_frame='mujoco_world_linear_local_angular_v1', fixture_pose_world={},
        simulation_time_s=0., velocity_policy='named_qvel_and_free_joint_qvel_v1',
        control_policy='named_physical_effort_by_source_v1', initialization_order=(
            'sample_source_properties', 'native_preprocess', 'sample_task_placements',
            'restore_source_bound_state', 'forward_derived_state'), settle_steps=0)
    sample = ResetSampleV1.create(**args)
    plan = ResetPlanV1('reset-plan-v1', sample, 'task_episode')
    plan.validate()
    assert plan.reset_sample.joint_velocity['arm/drive'] == .3
    pose = PoseWorld((0.,0.,0.), (1.,0.,0.,0.))
    args.update(sampled_poses_world={'free': pose}, poses_world={'free': pose},
                free_joint_velocity={'free': (0.,)*6})
    with pytest.raises(ValueError, match='scalar source state'):
        ResetSampleV1.create(**args)
