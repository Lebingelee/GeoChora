"""Public declaration route for existing Panda/table/free-box CPU assets.

The task supplies its immutable declaration and evaluation hook. Core owns the
Artifact, source bindings, controller and selected runtime lifecycle.
"""
from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

import numpy as np

from ..artifacts import PoseWorld
from ..artifacts.execution import ResetSample
from ..assembly.compiler import reference_task_identity_fields
from ..assembly.panda_box import (
    PandaBoxDeclaration,
    compile_panda_box_artifact,
    compile_panda_box_source,
    compile_panda_box_task,
)
from ..controllers.canonical import ProductionCanonicalPandaController
from ..controllers.canonical.contracts import digest
from ..environment.configuration import resolve_env_config
from ..environment.config import ResolvedSelectedConfig
from .reference_env import ReferenceTaskBinding, SelectedReferenceEnv


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
    from ..assembly.compiler import ReferenceTaskDeclarationV1, compile_reference_source
    from ..environment.task_source import TaskArtifactDeclarationV1
    from ..objects.pick_cube import PickCubeSceneComposer
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


class DeclaredPandaBoxEnv(SelectedReferenceEnv):
    """Subclass with a declaration and evaluator; register it with `register_env`."""

    uses_selected_public_config = True
    selected_controller_profiles = frozenset()
    selected_parameter_limits = {}
    selected_supports_isaac = False

    @classmethod
    def declaration(cls) -> PandaBoxDeclaration:
        raise NotImplementedError

    @staticmethod
    def evaluate_task(state, semantics):
        raise NotImplementedError

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
