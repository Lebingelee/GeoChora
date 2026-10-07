"""Deterministic NA-S0; seed19 is provenance, not artificial reset diversity."""
from ...artifacts.execution import ResetSample
from .canonical_artifact import require_family


def sample_reset(artifact, task_seed=19):
    require_family(artifact)
    if type(task_seed) is not int or task_seed < 0:
        raise ValueError('nonnegative provenance seed required')
    return ResetSample.create(schema_version='reset-sample-v0', task_artifact_hash=artifact.identity_hash,
        sampler_id='nut-assembly-square-v1/NA-S0', sampler_version='frozen-authored-v0', task_seed=19,
        joint_position=artifact.initialization.joint_position, poses_world=artifact.initialization.poses_world,
        velocity_policy='zero_named_joint_and_entity_velocities',
        control_policy='arm_targets_at_initial_joints_gripper_open', settle_steps=0)
