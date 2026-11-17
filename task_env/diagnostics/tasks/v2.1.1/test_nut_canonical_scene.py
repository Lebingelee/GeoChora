"""GeoPhys Nut Scene and reset remain bound to the frozen source."""
from dataclasses import replace

import pytest

from task_env.artifacts import TaskArtifactV1
from task_env.environment.task_source import adapt_legacy_recipe_task_source, sample_episode_reset_plan
from task_env.runtime.sessions.source import source_resource_receipt
from task_env.tasks.nut_assembly.specialization import _configuration, build_reference
from task_env.tasks.nut_assembly.task import NutAssemblyTaskDefinition, sample_reset


def test_geophys_nut_scene_and_reset_reject_foreign_identities():
    value = build_reference(provider='geophys', include_solution=False)
    artifact, source = value['artifact'], value['source']
    receipt = source_resource_receipt(source)
    try:
        assert isinstance(artifact, TaskArtifactV1)
        assert source.scene_definition.identity_hash == artifact.scene_identity_hash
        assert source.source_id == f'scene-definition-v3:{artifact.scene_identity_hash}'
        assert source.source_snapshot_receipt is receipt
        receipt.validate_snapshot()
        task = NutAssemblyTaskDefinition.from_artifact(artifact, _configuration()['recipe']['reset'])
        assert task.sample_reset(artifact, 19).task_artifact_hash == artifact.identity_hash
        with pytest.raises(ValueError):
            task.sample_reset(replace(artifact, artifact_id='foreign-artifact'), 19)
        with pytest.raises(ValueError):
            sample_reset(artifact, 19)
        config = _configuration()
        task_source = adapt_legacy_recipe_task_source(
            {'recipe': config['recipe'], 'environment': config['environment']})
        with pytest.raises(ValueError):
            sample_episode_reset_plan(task_source,
                replace(source.scene_definition, scene_id='foreign-scene'), artifact, task_seed=19)
    finally:
        receipt.close()
