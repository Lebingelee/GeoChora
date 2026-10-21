"""Explicit diagnostic construction for the bounded C02b Position candidate."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from task_env.artifacts import Timebase
from task_env.controllers.canonical.contracts import digest
from task_env.controllers.canonical.position_profile import PandaPositionServoProfileV1
from task_env.diagnostics.tasks.test_phase_ii_d01a_scene_materialization import (
    _a05_scene,
    _artifact_and_sample,
    _source_input,
)
from task_env.diagnostics.tasks.test_phase_ii_d01b_vnext_materialization import _task_source
from task_env.environment import compile_task_artifact_v1, sample_episode_reset_plan
from task_env.runtime.sessions.control import compile_control_binding_plan
from task_env.tasks.reference_env import ReferenceTaskBinding, SelectedReferenceEnv


POSITION_CANDIDATE_TASK_ID = 'phase-ii-c02b-position-servo'
POSITION_CANDIDATE_VERSION = 'candidate-v1'
POSITION_CANDIDATE_SEED = 31


def build_position_candidate(workspace: Path | str, *, provider: str, horizon: int = 6000):
    """Build one source-identified candidate through SelectedReferenceEnv's existing binding."""
    import importlib

    root = Path(workspace).resolve()
    root.mkdir(parents=True, exist_ok=True)
    scene = _a05_scene()
    legacy, _ = _artifact_and_sample(scene)
    legacy = replace(
        legacy,
        artifact_id='phase-ii-c02b-position-servo-v1',
        task_id=POSITION_CANDIDATE_TASK_ID,
        artifact_version=POSITION_CANDIDATE_VERSION,
        timebase=Timebase(0.002, 5, 0.01),
    )
    task_source = replace(
        _task_source(scene), task_id=legacy.task_id, version=legacy.artifact_version,
    )
    artifact = compile_task_artifact_v1(task_source, scene, legacy)
    reset_plan = sample_episode_reset_plan(
        task_source, scene, artifact, task_seed=POSITION_CANDIDATE_SEED,
    )
    source, imported, closure_digest, panda_digest, panda_file_count = _source_input(
        importlib.import_module('scene'), root / 'source-closure', scene, legacy,
    )
    if imported is None or len(closure_digest) != 64 or len(panda_digest) != 64:
        raise ValueError('Position candidate source import/closure evidence is incomplete')
    source_config = replace(
        source.config,
        runtime=replace(source.config.runtime, control_substeps=5),
    )
    source = replace(
        source,
        task_artifact_hash=artifact.identity_hash,
        joint_targets={f'panda-main/joint{i}': f'actuator{i}' for i in range(1, 8)},
        open_actuators=('actuator8',),
        config=source_config,
        source_closure_digest=closure_digest,
    )
    if source.bodies.get('square-peg-instance/peg1') != 'peg1':
        raise ValueError('Position candidate A05 source lacks its declared target body')
    plan = compile_control_binding_plan(scene, (
        PandaPositionServoProfileV1.from_source(artifact, source).controller_binding(),
    ))

    def build(_provider):
        profile = PandaPositionServoProfileV1.from_source(artifact, source)
        return {
            'artifact': artifact,
            'solution': None,
            'controller': profile,
            'source': source,
            'reset_plan': reset_plan,
            'controller_binding_plan': plan,
            'construction_id': digest({
                'artifact': artifact.identity_hash,
                'source_closure': source.source_closure_digest,
                'profile': profile.identity,
                'plan': plan.identity_hash,
            }),
            'resolved_configuration': {
                'provider': _provider, 'backend': 'cpu', 'profile_id': profile.profile_id,
            },
            'source_revision': 'C02b-E-diagnostic-candidate-v1',
            'source_sha256': {'source_closure': source.source_closure_digest},
        }

    def fixed_seed(seed):
        if type(seed) is not int or seed != reset_plan.reset_sample.task_seed:
            raise ValueError(
                'Position candidate uses a fixed ResetPlan; reset seed must equal '
                f'{reset_plan.reset_sample.task_seed}'
            )
        return seed

    binding = ReferenceTaskBinding(
        build=build,
        reset_sample=lambda _artifact, _seed: reset_plan.reset_sample,
        evaluate=lambda _state, _semantics: SimpleNamespace(
            reward=0.0, success=False, failure=False, metrics={},
        ),
        object_poses=(('square-peg-instance/peg1', 'target'),),
        external_actions=True,
        interval_mode='grouped',
        recorder_mode='execution',
        reset_seed=fixed_seed,
    )
    env = SelectedReferenceEnv.from_position_candidate(
        binding, provider=provider, backend='cpu', horizon=horizon,
    )
    return SimpleNamespace(
        env=env, scene=scene, task_source=task_source, artifact=artifact,
        reset_plan=reset_plan, source=source, controller_binding_plan=plan,
        panda_closure_digest=panda_digest, panda_file_count=panda_file_count,
        provider=provider,
    )


__all__ = [
    'POSITION_CANDIDATE_SEED', 'POSITION_CANDIDATE_TASK_ID',
    'POSITION_CANDIDATE_VERSION', 'build_position_candidate',
]
