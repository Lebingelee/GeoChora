"""Register a marker task using the existing Panda/table/box assembly."""
from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

import numpy as np

from task_env.artifacts import PoseWorld, SemanticDefinition, Timebase
from task_env.artifacts.execution import ResetSample
from task_env.assembly.compiler import reference_task_identity_fields
from task_env.assembly.panda_box import (
    PandaBoxDeclaration, compile_panda_box_artifact, compile_panda_box_source,
    compile_panda_box_task,
)
from task_env.controllers.canonical import ProductionCanonicalPandaController
from task_env.controllers.canonical.contracts import digest
from task_env.environment import TaskEvaluation
from task_env.environment.configuration import resolve_env_config
from task_env.environment.config import ResolvedSelectedConfig
from task_env.environment.reference_binding import ReferenceTaskBinding
from task_env.environment.reference_env import SelectedReferenceEnv
from task_env.registry import register_env


def _sample_box_reset(declaration, artifact, seed):
    if type(seed) is not int or seed < 0:
        raise ValueError('task_seed must be a nonnegative integer')
    expected = compile_panda_box_artifact(declaration)
    if artifact.identity_hash != expected.identity_hash:
        raise ValueError('reset Artifact does not match the task declaration')
    rng = np.random.Generator(np.random.PCG64(seed))
    initial = artifact.initialization
    position = list(initial.poses_world[declaration.object_id].position)
    for index, dimension in enumerate(initial.randomization):
        position[index] = float(rng.uniform(*dimension.training_bounds))
    pose = PoseWorld(tuple(position), initial.poses_world[declaration.object_id].quaternion_wxyz)
    return ResetSample.create(
        schema_version='reset-sample-v0', task_artifact_hash=artifact.identity_hash,
        sampler_id=f'{declaration.task_id}/uniform_xy', sampler_version='pcg64-v0', task_seed=seed,
        joint_position=dict(initial.joint_position), poses_world={declaration.object_id: pose},
        velocity_policy='zero_named_joint_and_entity_velocities',
        control_policy='arm_targets_at_initial_joints_gripper_open', settle_steps=0,
    )


def _compile_value(declaration, config, evaluator):
    compiled = compile_panda_box_task(declaration, config=config)
    artifact, source = compiled.artifact, compiled.source
    controller = ProductionCanonicalPandaController.from_source(artifact, source)
    construction_identity = reference_task_identity_fields(artifact, source, controller)
    from task_env.assembly.compiler import ReferenceTaskDeclarationV1, compile_reference_source
    from task_env.environment.task_source import TaskArtifactDeclarationV1
    from task_env.objects.pick_cube import PickCubeSceneComposer
    owners = (type(declaration), evaluator, compile_panda_box_artifact, compile_panda_box_source,
              compile_panda_box_task, ReferenceTaskDeclarationV1, compile_reference_source,
              TaskArtifactDeclarationV1, reference_task_identity_fields, PickCubeSceneComposer,
              ProductionCanonicalPandaController)
    paths = {Path(__file__).resolve(), *(Path(inspect.getsourcefile(owner)).resolve() for owner in owners)}
    root = Path(__file__).resolve().parents[2]
    source_hashes = {(path.relative_to(root).as_posix() if path.is_relative_to(root)
                      else f'external:{path.name}'): hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in sorted(paths)}
    resolved = {
        'schema_version': 'declared-panda-box-construction-v1',
        'task_id': declaration.task_id, 'object_id': declaration.object_id,
        **construction_identity,
        'source_sha256': source_hashes,
        'solution': 'not_declared', 'qualification': 'NOT_REQUALIFIED',
    }
    return {'construction_id': 'declared-panda-box-construction-v1', 'artifact': artifact,
            'source': source, 'controller': controller, 'solution': None,
            'solution_identity': digest({'schema': 'no-task-solution-v1', 'task_id': declaration.task_id}),
            'recipe_identity': digest(resolved), 'resolved_configuration': resolved,
            'source_sha256': source_hashes}


@register_env()
class MarkerHeightEnv(SelectedReferenceEnv):
    """Observe a movable marker and report whether it reaches a height."""

    uses_selected_public_config = True
    selected_controller_profiles = frozenset()
    selected_parameter_limits = {}
    selected_supports_isaac = False

    @classmethod
    def selected_default_config(cls):
        d = cls.declaration()
        return resolve_env_config(
            task_uid=d.task_id, scene_uid='tabletop-v1', agent_uids=('panda-v1',),
            object_uids=('cube-v1',), success_definition=d.success_definition,
            runtime={'backend': 'cpu', 'physics_dt': d.timebase.physics_dt,
                     'control_substeps': d.timebase.control_substeps, 'prewarm': False},
            robot={'controller': {'kind': 'absolute_pose', 'reference': 'world',
                                  'rotation_representation': 'quaternion_wxyz'}},
            observation={'schema_version': 'task-env-state-v2', 'include_privileged_state': True},
            render={'camera_obs': False}, episode={'horizon': 6000},
        )

    @staticmethod
    def selected_default_controller_profile():
        return None

    @classmethod
    def from_resolved_config(cls, config, *, render_mode=None, **kwargs):
        if type(config) is not ResolvedSelectedConfig or config.task_uid != cls.uid:
            raise TypeError('declared task requires its resolved selected configuration')
        if render_mode is not None or kwargs:
            raise ValueError('declared Panda box route is state-only')
        declaration = cls.declaration()
        if declaration.task_id != cls.uid:
            raise ValueError('registered UID and declared task identity differ')
        def build(_provider):
            return _compile_value(declaration, config.environment, cls.evaluate_task)
        binding = ReferenceTaskBinding(
            build=build, reset_sample=lambda artifact, seed: _sample_box_reset(declaration, artifact, seed),
            evaluate=cls.evaluate_task, object_poses=((declaration.object_id, declaration.object_id.replace('-', '_')),),
            external_actions=True, interval_mode='grouped', recorder_mode='canonical',
        )
        env = cls(provider=config.physics_provider, backend=config.environment.runtime.backend,
                  horizon=config.environment.episode.horizon, _binding=binding)
        env.resolved_public_config = config
        return env

    uid = 'marker-height-example-v1'

    @classmethod
    def declaration(cls):
        semantics = SemanticDefinition(
            'semantics-v0', 'marker-height-v1', ('marker-v1', 'panda-v1/ee'), (),
            {'height_m': 0.60}, 'marker_above_height_v1',
        )
        return PandaBoxDeclaration(
            task_id=cls.uid, artifact_id='marker-height-example-v1/initial', version='v1',
            object_id='marker-v1', success_definition='marker_above_height_v1',
            table_half_size=(.28, .20, .01), table_top_z=.462, table_center_xy=(.5545, 0.),
            source_box_position=(.50, 0., .488), source_box_quaternion_wxyz=(1., 0., 0., 0.),
            reset_center_xy=(.5545, 0.), reset_half_extent_m=.05, semantics=semantics,
            timebase=Timebase(.002, 5, .01),
        )

    @staticmethod
    def evaluate_task(state, semantics):
        semantics.require_state(state)
        height = state.pose_world['marker-v1'].position[2]
        success = height >= semantics.parameters_si['height_m']
        return TaskEvaluation(float(success), success, False,
                              {'marker_height_m': height, 'task_success': success},
                              {'height': float(success)})
