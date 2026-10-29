"""Task-owned construction for the bounded C02b Position candidate."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
import hashlib

from task_env.artifacts import Timebase
from task_env.controllers.canonical.contracts import digest
from task_env.controllers.canonical.position_profile import PandaPositionServoProfileV1
from .source import (
    _a05_scene,
    _artifact_and_sample,
    _source_input,
)
from .source import _task_source
from task_env.environment import compile_task_artifact_v1, sample_episode_reset_plan
from task_env.environment.task_source import TaskSourceV1
from task_env.artifacts import ExecutionSpecV1, TaskArtifactV1
from task_env.artifacts.execution import EpisodeResetPlanV1
from task_env.runtime.sessions.source import UsdRuntimeSourceV1
from task_env.runtime.sessions.leaf_control import IsaacNamedPositionDriveReceiptV1
from task_env.runtime.sessions.control import compile_control_binding_plan
from task_env.tasks.reference_env import ReferenceTaskBinding, SelectedReferenceEnv


POSITION_CANDIDATE_TASK_ID = 'phase-ii-c02b-position-servo'
POSITION_CANDIDATE_VERSION = 'candidate-v1'
POSITION_CANDIDATE_SEED = 31


@dataclass(frozen=True)
class F03PositionCandidateInputV1:
    """Explicit versioned construction input for the F03 Core call-chain route."""

    schema_version: str
    task_source: TaskSourceV1
    artifact: TaskArtifactV1
    runtime_source: UsdRuntimeSourceV1
    execution: ExecutionSpecV1
    reset_plan: EpisodeResetPlanV1
    kinematics_source_xml: str
    kinematics_source_sha256: str
    native_drive_receipt: IsaacNamedPositionDriveReceiptV1

    def validate(self):
        if self.schema_version != 'f03-position-candidate-input-v1':
            raise ValueError('unsupported F03 Position candidate input schema')
        if (type(self.task_source) is not TaskSourceV1
                or type(self.artifact) is not TaskArtifactV1
                or type(self.runtime_source) is not UsdRuntimeSourceV1
                or type(self.execution) is not ExecutionSpecV1
                or type(self.reset_plan) is not EpisodeResetPlanV1
                or type(self.native_drive_receipt) is not IsaacNamedPositionDriveReceiptV1):
            raise TypeError('F03 Position input requires the exact versioned Core contracts')
        self.runtime_source.validate()
        self.artifact.validate()
        self.execution.validate()
        self.reset_plan.validate()
        if (self.runtime_source.task_artifact.identity_hash != self.artifact.identity_hash
                or self.runtime_source.scene_definition.identity_hash != self.artifact.scene_identity_hash
                or self.runtime_source.scene_source.task_source_identity_sha256 != self.task_source.identity_hash
                or self.runtime_source.scene_source.scene_identity_sha256 != self.runtime_source.scene_definition.identity_hash
                or self.task_source.scene_ref != self.runtime_source.scene_definition.scene_id
                or self.task_source.task_id != self.artifact.task_id
                or self.task_source.version != self.artifact.artifact_version
                or self.reset_plan.role_binding.task_source_identity_hash != self.task_source.identity_hash
                or self.reset_plan.role_binding.scene_identity_hash != self.runtime_source.scene_definition.identity_hash
                or self.reset_plan.reset_sample.task_artifact_hash != self.artifact.identity_hash):
            raise ValueError('F03 Position input source/TaskSource/Artifact/reset identities disagree')
        if (self.execution.physics_provider, self.execution.physics_backend,
                self.execution.physics_device, self.execution.determinism_mode,
                self.execution.provider_seed) != ('isaacsim', 'cuda', 'cuda:0', 'best_effort', 0):
            raise ValueError('F03 versioned Position candidate requires Isaac CUDA cuda:0 best_effort')
        renderer = self.execution.render_default
        if (renderer.provider, renderer.backend, renderer.profile, renderer.device,
                self.execution.camera_overrides) != ('none', 'cpu', 'none', None, ()):
            raise ValueError('F03 versioned Position candidate requires a no-renderer ExecutionSpecV1')
        if not self.kinematics_source_xml or type(self.kinematics_source_xml) is not str:
            raise ValueError('F03 synthetic S1 requires an explicit nonempty static kinematics source')
        actual_kinematics_hash = hashlib.sha256(self.kinematics_source_xml.encode('utf-8')).hexdigest()
        if self.kinematics_source_sha256 != actual_kinematics_hash:
            raise ValueError('F03 static kinematics source hash mismatch')
        if (self.native_drive_receipt.scene_identity_sha256,
                self.native_drive_receipt.source_closure_sha256,
                self.native_drive_receipt.execution_identity_sha256,
                self.native_drive_receipt.physics_profile,
                self.native_drive_receipt.writer_id) != (
                self.runtime_source.scene_definition.identity_hash,
                self.runtime_source.source_closure_digest,
                self.execution.identity_hash,
                self.execution.physics_profile,
                'panda-main/position-servo-v1'):
            raise ValueError('F03 named drive receipt does not bind the full versioned source/execution/control input')


@dataclass(frozen=True)
class F04PositionCandidateInputV1:
    """Production construction input whose named receipt is deferred to native metadata."""

    schema_version: str
    task_source: TaskSourceV1
    artifact: TaskArtifactV1
    runtime_source: UsdRuntimeSourceV1
    execution: ExecutionSpecV1
    reset_plan: EpisodeResetPlanV1
    kinematics_source_xml: str
    kinematics_source_sha256: str

    def validate(self):
        if self.schema_version != 'f04-position-candidate-input-v1':
            raise ValueError('unsupported F04 Position candidate input schema')
        if (type(self.task_source) is not TaskSourceV1
                or type(self.artifact) is not TaskArtifactV1
                or type(self.runtime_source) is not UsdRuntimeSourceV1
                or type(self.execution) is not ExecutionSpecV1
                or type(self.reset_plan) is not EpisodeResetPlanV1):
            raise TypeError('F04 Position input requires exact versioned Core contracts')
        self.runtime_source.validate()
        self.artifact.validate()
        self.execution.validate()
        self.reset_plan.validate()
        if (self.runtime_source.task_artifact.identity_hash != self.artifact.identity_hash
                or self.runtime_source.scene_definition.identity_hash != self.artifact.scene_identity_hash
                or self.runtime_source.scene_source.task_source_identity_sha256 != self.task_source.identity_hash
                or self.runtime_source.scene_source.scene_identity_sha256 != self.runtime_source.scene_definition.identity_hash
                or self.task_source.scene_ref != self.runtime_source.scene_definition.scene_id
                or self.task_source.task_id != self.artifact.task_id
                or self.task_source.version != self.artifact.artifact_version
                or self.reset_plan.role_binding.task_source_identity_hash != self.task_source.identity_hash
                or self.reset_plan.role_binding.scene_identity_hash != self.runtime_source.scene_definition.identity_hash
                or self.reset_plan.reset_sample.task_artifact_hash != self.artifact.identity_hash):
            raise ValueError('F04 Position input source/TaskSource/Artifact/reset identities disagree')
        from task_env.runtime.sessions.api import _validate_f04_isaac_position_source
        _validate_f04_isaac_position_source(self.artifact, self.execution, self.runtime_source)
        if not self.kinematics_source_xml or type(self.kinematics_source_xml) is not str:
            raise ValueError('F04 Position input requires source-calibrated kinematics bytes')
        actual_hash = hashlib.sha256(self.kinematics_source_xml.encode('utf-8')).hexdigest()
        if self.kinematics_source_sha256 != actual_hash:
            raise ValueError('F04 source-calibrated kinematics hash mismatch')


def build_versioned_position_candidate(input_v1: F03PositionCandidateInputV1 | F04PositionCandidateInputV1, *, horizon=8,
                                       environment_type=SelectedReferenceEnv,
                                       camera_observation_config=None):
    """Build through the existing binding and SelectedReferenceEnv owners."""
    if type(input_v1) not in (F03PositionCandidateInputV1, F04PositionCandidateInputV1):
        raise TypeError('versioned Position candidate requires an exact F03 or F04 input contract')
    input_v1.validate()
    source = input_v1.runtime_source
    artifact = input_v1.artifact
    scene = source.scene_definition
    native_drive_receipt = getattr(input_v1, 'native_drive_receipt', None)
    profile = PandaPositionServoProfileV1.from_usd_source(
        artifact, source, execution=input_v1.execution,
        kinematics_source_xml=input_v1.kinematics_source_xml,
        native_drive_receipt=native_drive_receipt,
    )
    plan = compile_control_binding_plan(scene, (profile.controller_binding(),))
    if input_v1.reset_plan.reset_sample.task_seed < 0:
        raise ValueError('F03 reset seed must be nonnegative')

    def build(_provider):
        return {
            'artifact': artifact, 'task_source': input_v1.task_source,
            'solution': None, 'controller': profile, 'source': source,
            'reset_plan': input_v1.reset_plan,
            'controller_binding_plan': plan,
            'execution_spec_v1': input_v1.execution,
            'f03_position_input': input_v1 if type(input_v1) is F03PositionCandidateInputV1 else None,
            'f04_position_input': input_v1 if type(input_v1) is F04PositionCandidateInputV1 else None,
            'native_drive_receipt': native_drive_receipt,
            'construction_id': digest({
                'artifact': artifact.identity_hash,
                'source': source.source_id,
                'closure': source.source_closure_digest,
                'task_source': input_v1.task_source.identity_hash,
                'reset_plan': input_v1.reset_plan.identity_hash,
                'execution': input_v1.execution.identity_hash,
                'controller': profile.identity,
                'drive_receipt': (None if native_drive_receipt is None
                                  else native_drive_receipt.identity_sha256),
                'kinematics_source_sha256': input_v1.kinematics_source_sha256,
            }),
            'resolved_configuration': {
                'provider': input_v1.execution.physics_provider,
                'backend': input_v1.execution.physics_backend,
                'device': input_v1.execution.physics_device,
                'profile_id': profile.profile_id,
                'execution_identity_sha256': input_v1.execution.identity_hash,
            },
            'source_revision': ('F03-versioned-usd-synthetic-s1-v1'
                                if type(input_v1) is F03PositionCandidateInputV1
                                else 'F04-versioned-usd-native-candidate-v1'),
            'source_sha256': {
                'source_closure': source.source_closure_digest,
                'kinematics_source': input_v1.kinematics_source_sha256,
            },
        }

    def fixed_seed(seed):
        if type(seed) is not int or seed != input_v1.reset_plan.reset_sample.task_seed:
            raise ValueError('F03 reset seed must match its fixed EpisodeResetPlan')
        return seed
    binding = ReferenceTaskBinding(
        build=build,
        reset_sample=lambda _artifact, _seed: input_v1.reset_plan.reset_sample,
        evaluate=lambda _state, _semantics: SimpleNamespace(
            reward=0.0, success=False, failure=False, metrics={},
        ),
        object_poses=tuple(
            (name, 'target') for name in sorted(input_v1.artifact.initialization.poses_world)
        ),
        external_actions=True, interval_mode='grouped', recorder_mode='execution',
        reset_seed=fixed_seed,
    )
    env = environment_type.from_position_candidate(
        binding, provider=input_v1.execution.physics_provider,
        backend=input_v1.execution.physics_backend, horizon=horizon,
        camera_observation_config=camera_observation_config,
        execution_spec=input_v1.execution,
    )
    return SimpleNamespace(
        env=env, scene=scene, task_source=input_v1.task_source,
        artifact=artifact, reset_plan=input_v1.reset_plan,
        source=source, controller_binding_plan=plan,
        execution=input_v1.execution,
        native_drive_receipt=native_drive_receipt,
        f03_position_input=input_v1 if type(input_v1) is F03PositionCandidateInputV1 else None,
        f04_position_input=input_v1 if type(input_v1) is F04PositionCandidateInputV1 else None,
    )


def build_position_candidate(workspace: Path | str, *, provider: str, horizon: int = 6000,
                             environment_type=SelectedReferenceEnv,
                             camera_observation_config=None):
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
            'task_source': task_source,
            'panda_closure_digest': panda_digest,
            'panda_file_count': panda_file_count,
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
    env = environment_type.from_position_candidate(
        binding, provider=provider, backend='cpu', horizon=horizon,
        camera_observation_config=camera_observation_config,
    )
    return SimpleNamespace(
        env=env, scene=scene, task_source=task_source, artifact=artifact,
        reset_plan=reset_plan, source=source, controller_binding_plan=plan,
        panda_closure_digest=panda_digest, panda_file_count=panda_file_count,
        provider=provider,
    )


__all__ = [
    'F03PositionCandidateInputV1', 'POSITION_CANDIDATE_SEED',
    'POSITION_CANDIDATE_TASK_ID', 'POSITION_CANDIDATE_VERSION',
    'build_position_candidate', 'build_versioned_position_candidate',
]
