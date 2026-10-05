"""Task-owned deterministic reset sampling. No provider imports or RNG calls there."""
import numpy as np

from ...artifacts import PoseWorld, TaskArtifact
from ...artifacts.execution import ResetSample
from .candidate import build_candidate


def sample_reset(artifact: TaskArtifact, task_seed: int) -> ResetSample:
    if artifact.identity_hash != build_candidate().identity_hash:
        raise ValueError('unsupported PickCube Artifact for this bounded sampler')
    if type(task_seed) is not int or task_seed < 0:
        raise ValueError('task_seed must be a nonnegative integer')
    rng = np.random.Generator(np.random.PCG64(task_seed))
    initial = artifact.initialization
    position = list(initial.poses_world['cube-v1'].position)
    for index, dim in enumerate(initial.randomization):
        # Order and algorithm are sampler-v0 provenance, not provider randomness.
        position[index] = float(rng.uniform(*dim.training_bounds))
    poses = {'cube-v1': PoseWorld(tuple(position), initial.poses_world['cube-v1'].quaternion_wxyz)}
    return ResetSample.create(
        schema_version='reset-sample-v0', task_artifact_hash=artifact.identity_hash,
        sampler_id='pick-cube-v1/uniform_xy', sampler_version='pcg64-v0',
        task_seed=task_seed, joint_position=dict(initial.joint_position), poses_world=poses,
        velocity_policy='zero_named_joint_and_entity_velocities',
        control_policy='arm_targets_at_initial_joints_gripper_open',
        settle_steps=initial.settle_steps,
    )
