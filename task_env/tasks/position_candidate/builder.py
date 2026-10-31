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
    _f05_dg01_scene,
    _f05_dg01_artifact_and_sample,
    _f05_dg01_task_source,
    _copy_panda_snapshot,
    _compose_f05_dg01_scene_source,
    _f05_dg01_runtime_source,
    F05_DG01_SCENE_ID,
    F05_DG01_TASK_ID,
    F05_DG01_TASK_VERSION,
    F05_DG01_RECIPE_SHA256,
)
from .source import _task_source
from task_env.environment import compile_task_artifact_v1, sample_episode_reset_plan
from task_env.environment.task_source import TaskSourceV1
from task_env.artifacts import ExecutionSpecV1, TaskArtifactV1, RendererSelectionV1
from task_env.artifacts.execution import EpisodeResetPlanV1
from task_env.runtime.sessions.source import RuntimeSource, UsdRuntimeSourceV1
from task_env.runtime.sessions.leaf_control import (
    GeoPhysHostModelProducerIdentityV1,
    GeoPhysUsdPositionDriveReceiptV1, GeoPhysUsdSourceActuationReceiptV2,
    IsaacNamedPositionDriveReceiptV1,
)
from task_env.runtime.sessions.control import compile_control_binding_plan
from task_env.tasks.reference_env import ReferenceTaskBinding, SelectedReferenceEnv


POSITION_CANDIDATE_TASK_ID = 'phase-ii-c02b-position-servo'
POSITION_CANDIDATE_VERSION = 'candidate-v1'
POSITION_CANDIDATE_SEED = 31
F05_DG01_MUJOCO_PROFILE = 'mujoco-mjcf-f05-dg01-core-v1'


def _validate_f05_native_position_action_config(controller_config):
    from task_env.environment.config import ActionConfig

    if type(controller_config) is not ActionConfig:
        raise TypeError('F05 native candidate requires its frozen Position ActionConfig')
    if controller_config != ActionConfig(
            joint_position_correction_gain=1.0,
            gripper_default_force_N=100.0):
        raise ValueError('F05 native ActionConfig differs from the accepted DG01 control semantics')


F05_DG02_GEOPHYS_PROFILE = 'geophys-usd-position-f05-dg02-core-v1'
F05_DG02_USD_ASSET_VERSION = 'f05-dg02-usd-v2'
F05_DG02_USD_RECIPE_SHA256 = '003238fb99d5b2574e5550918b6902518d7bc09cd0d6f4ad02049ccc408bb0fd'
# The DG02 Core route tracks source-FK pose targets whose Panda solution is
# redundant. Keep the achieved-state DLS increment free of a second posture
# objective: the bounded native probe showed that full reset-posture feedback
# still produced oscillatory point-hold joint motion. Other Position routes are
# unchanged. Recompute each increment from achieved state so delayed physical
# response cannot wind up an accumulated joint target.
F05_DG02_NULLSPACE_REFERENCE_GAIN = 0.0
F05_DG02_POSE_TARGET_METHOD = 'achieved_state_dls_v1'


def _f05_dg02_usd_source_bindings():
    """Return the exact canonical-to-prim map authored by the DG02 USD stage."""
    body_paths = {}
    path = '/panda/Geometry'
    for index in range(8):
        path = f'{path}/link{index}'
        body_paths[f'panda-main/link{index}'] = path
    hand = f'{path}/hand'
    body_paths.update({
        'panda-main/hand': hand,
        'panda-main/left_finger': f'{hand}/left_finger',
        'panda-main/right_finger': f'{hand}/right_finger',
        'free-cube/free_cube': '/F04Scene/free_cube',
        'free-cube/world': '/F04Scene/free_cube',
        'support/support': '/F04Scene/support',
    })
    joints = {
        **{f'panda-main/joint{index}': f'joint{index}' for index in range(1, 8)},
        'panda-main/finger_joint1': 'finger_joint1',
        'panda-main/finger_joint2': 'finger_joint2',
    }
    return body_paths, joints


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


@dataclass(frozen=True)
class F05PositionCandidateInputV1:
    """Explicit F05 source/control S1 input bound to public GeoPhys host metadata."""

    schema_version: str
    task_source: TaskSourceV1
    artifact: TaskArtifactV1
    runtime_source: UsdRuntimeSourceV1
    execution: ExecutionSpecV1
    reset_plan: EpisodeResetPlanV1
    kinematics_source_xml: str
    kinematics_source_sha256: str
    host_model_producer_identity: GeoPhysHostModelProducerIdentityV1
    native_drive_receipt: GeoPhysUsdPositionDriveReceiptV1

    def validate(self):
        if self.schema_version != 'f05-position-candidate-input-v1':
            raise ValueError('unsupported F05 Position candidate input schema')
        if (type(self.task_source) is not TaskSourceV1
                or type(self.artifact) is not TaskArtifactV1
                or type(self.runtime_source) is not UsdRuntimeSourceV1
                or type(self.execution) is not ExecutionSpecV1
                or type(self.reset_plan) is not EpisodeResetPlanV1
                or type(self.host_model_producer_identity) is not GeoPhysHostModelProducerIdentityV1
                or type(self.native_drive_receipt) is not GeoPhysUsdPositionDriveReceiptV1):
            raise TypeError('F05 Position input requires exact versioned Core/source/drive contracts')
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
            raise ValueError('F05 source/TaskSource/Artifact/reset identities disagree')
        if (self.execution.physics_provider, self.execution.physics_backend,
                self.execution.physics_device, self.execution.physics_profile,
                self.execution.determinism_mode) != (
                'geophys', 'cpu', 'cpu', 'geophys-usd-position-f05-s1-v1', 'best_effort'):
            raise ValueError('F05 S1 requires the exact provider-free GeoPhys CPU execution identity')
        renderer = self.execution.render_default
        if (renderer.provider, renderer.backend, renderer.profile, renderer.device,
                self.execution.camera_overrides) != ('none', 'cpu', 'none', None, ()):
            raise ValueError('F05 S1 is state-only and does not admit renderer or camera overrides')
        representation = self.runtime_source.scene_source.representation
        delivery = self.runtime_source.scene_source.loaded_delivery.delivery
        if (representation.provider, representation.provider_build_identity,
                representation.representation_format, representation.runtime_admitted,
                self.runtime_source.scene_source.source_verified,
                self.runtime_source.scene_source.locally_validated,
                delivery.provenance_kind) != (
                'geophys', self.host_model_producer_identity.requested_target_build_identity,
                'usd', False, False, True, 'local-validated'):
            raise ValueError('F05 S1 source is outside the frozen locally validated GeoPhys USD input')
        producer = self.host_model_producer_identity
        producer.validate_current_tree()
        from task_env.assembly.usd_delivery import resolve_provider_representation
        expected_representation = resolve_provider_representation(
            self.runtime_source.scene_source.loaded_delivery,
            provider='geophys',
            provider_build_identity=producer.requested_target_build_identity,
            options={
                'f05_attempt': '002',
                'lowering': 'public-host-model-s1-v1',
                'host_model_producer_identity_sha256': producer.identity_sha256,
            },
        )
        if expected_representation.identity_hash != representation.identity_hash:
            raise ValueError('F05 representation options do not bind the actual host-model producer identity')
        receipt = self.native_drive_receipt
        if (receipt.provenance_kind, receipt.scene_identity_sha256,
                receipt.source_closure_sha256, receipt.execution_identity_sha256,
                receipt.provider_build_identity, receipt.physics_profile,
                receipt.backend, receipt.device, receipt.determinism_mode,
                receipt.host_model_producer_identity_sha256,
                receipt.writer_id) != (
                'synthetic_fixture', self.runtime_source.scene_definition.identity_hash,
                self.runtime_source.source_closure_digest, self.execution.identity_hash,
                representation.provider_build_identity, self.execution.physics_profile,
                self.execution.physics_backend, self.execution.physics_device,
                self.execution.determinism_mode, producer.identity_sha256,
                'panda-main/position-servo-v1'):
            raise ValueError('F05 model-bound drive receipt does not bind exact source/execution/control identity')
        if not self.kinematics_source_xml or type(self.kinematics_source_xml) is not str:
            raise ValueError('F05 Position S1 requires source-calibrated kinematics bytes')
        if hashlib.sha256(self.kinematics_source_xml.encode()).hexdigest() != self.kinematics_source_sha256:
            raise ValueError('F05 source-calibrated kinematics hash mismatch')


@dataclass(frozen=True)
class F05NativePositionCandidateInputV1:
    """One exact F05 Menagerie/GeoPhys native cell with deferred model receipt."""

    schema_version: str
    task_source: TaskSourceV1
    artifact: TaskArtifactV1
    runtime_source: UsdRuntimeSourceV1
    execution: ExecutionSpecV1
    reset_plan: EpisodeResetPlanV1
    kinematics_source_xml: str
    kinematics_source_sha256: str
    host_model_producer_identity: GeoPhysHostModelProducerIdentityV1

    def validate(self):
        if self.schema_version != 'f05-native-position-candidate-input-v1':
            raise ValueError('unsupported F05 native Position candidate input schema')
        if (type(self.task_source) is not TaskSourceV1
                or type(self.artifact) is not TaskArtifactV1
                or type(self.runtime_source) is not UsdRuntimeSourceV1
                or type(self.execution) is not ExecutionSpecV1
                or type(self.reset_plan) is not EpisodeResetPlanV1
                or type(self.host_model_producer_identity) is not GeoPhysHostModelProducerIdentityV1):
            raise TypeError('F05 native input requires exact versioned Core/source/producer contracts')
        source, artifact, execution = self.runtime_source, self.artifact, self.execution
        source.validate()
        artifact.validate()
        execution.validate()
        self.reset_plan.validate()
        if (source.task_artifact.identity_hash != artifact.identity_hash
                or source.scene_definition.identity_hash != artifact.scene_identity_hash
                or source.scene_source.task_source_identity_sha256 != self.task_source.identity_hash
                or source.scene_source.scene_identity_sha256 != source.scene_definition.identity_hash
                or self.task_source.scene_ref != source.scene_definition.scene_id
                or self.task_source.task_id != artifact.task_id
                or self.task_source.version != artifact.artifact_version
                or self.reset_plan.role_binding.task_source_identity_hash != self.task_source.identity_hash
                or self.reset_plan.role_binding.scene_identity_hash != source.scene_definition.identity_hash
                or self.reset_plan.reset_sample.task_artifact_hash != artifact.identity_hash):
            raise ValueError('F05 native source/TaskSource/Artifact/reset identities disagree')
        if (execution.physics_provider, execution.physics_backend, execution.physics_device,
                execution.physics_profile, execution.determinism_mode) != (
                'geophys', 'cpu', 'cpu', 'geophys-usd-position-f05-native-v1', 'best_effort'):
            raise ValueError('F05 native input requires the exact GeoPhys CPU native execution identity')
        if (artifact.timebase.physics_dt, artifact.timebase.control_substeps,
                artifact.timebase.control_dt) != (0.002, 5, 0.01):
            raise ValueError('F05 native input requires 100 Hz / five 2 ms physics steps')
        from ...runtime.sessions.api import CAPABILITIES
        if not set(artifact.required_capabilities.names) <= set(CAPABILITIES):
            raise ValueError('F05 native input requests unsupported TaskArtifact capabilities')
        renderer = execution.render_default
        if ((renderer.provider, renderer.backend, renderer.profile, renderer.device,
                execution.camera_overrides) != ('none', 'cpu', 'none', None, ())):
            raise ValueError('F05 native cell is state-only and does not admit a renderer or camera overrides')
        representation = source.scene_source.representation
        delivery = source.scene_source.loaded_delivery.delivery
        if (representation.provider, representation.provider_build_identity,
                representation.representation_format, representation.runtime_admitted,
                source.scene_source.source_verified, source.scene_source.locally_validated,
                delivery.provenance_kind, delivery.asset_definition.source_reference,
                delivery.source_revision, delivery.source_closure_sha256) != (
                'geophys', self.host_model_producer_identity.requested_target_build_identity,
                'usd', False, False, True, 'local-validated',
                'mujoco-menagerie://franka_emika_panda/panda.xml',
                'b846dd12bc459d776cccb3dee0b1d02acbf7a9c7',
                'a59a66d0b176cb6b2634d54cd20744752742b425e5524db1b865dda0eb3adf2a'):
            raise ValueError('F05 native input is outside the frozen locally validated Menagerie USD source')
        if (self.host_model_producer_identity.requested_target_build_identity
                != representation.provider_build_identity):
            raise ValueError('F05 requested target representation differs from the producer identity')
        self.host_model_producer_identity.validate_current_tree()
        expected_joints = {
            **{f'panda-main/joint{i}': f'joint{i}' for i in range(1, 8)},
            'panda-main/finger_joint1': 'finger_joint1',
            'panda-main/finger_joint2': 'finger_joint2',
        }
        if (dict(source.joints) != expected_joints
                or dict(source.joint_targets) != expected_joints
                or dict(source.free_joints) != {'square-peg-instance/peg1': '/F04Scene/free_cube/rootJoint'}
                or source.frames):
            raise ValueError('F05 native source mapping differs from the frozen Menagerie Panda/free-body binding')
        if (not self.kinematics_source_xml or type(self.kinematics_source_xml) is not str
                or hashlib.sha256(self.kinematics_source_xml.encode()).hexdigest()
                != self.kinematics_source_sha256):
            raise ValueError('F05 native source-calibrated kinematics bytes/hash mismatch')


@dataclass(frozen=True)
class F05Dg02GeoPhysUsdCandidateInputV1:
    """Exact DG02 Menagerie USD/Core route with its model-bound V2 receipt."""

    schema_version: str
    task_source: TaskSourceV1
    artifact: TaskArtifactV1
    runtime_source: UsdRuntimeSourceV1
    execution: ExecutionSpecV1
    reset_plan: EpisodeResetPlanV1
    kinematics_source_xml: str
    kinematics_source_sha256: str
    host_model_producer_identity: GeoPhysHostModelProducerIdentityV1
    native_drive_receipt: GeoPhysUsdSourceActuationReceiptV2
    action_config: object

    def validate(self):
        if self.schema_version != 'f05-dg02-geophys-usd-candidate-input-v1':
            raise ValueError('unsupported F05 DG02 GeoPhys/USD candidate input schema')
        if (type(self.task_source) is not TaskSourceV1
                or type(self.artifact) is not TaskArtifactV1
                or type(self.runtime_source) is not UsdRuntimeSourceV1
                or type(self.execution) is not ExecutionSpecV1
                or type(self.reset_plan) is not EpisodeResetPlanV1
                or type(self.host_model_producer_identity) is not GeoPhysHostModelProducerIdentityV1
                or type(self.native_drive_receipt) is not GeoPhysUsdSourceActuationReceiptV2):
            raise TypeError('DG02 requires exact TaskSource/Artifact/USD/Execution/reset/producer/V2 receipt contracts')
        from task_env.environment.config import ActionConfig

        expected_action = ActionConfig(
            joint_position_correction_gain=1.0,
            gripper_default_force_N=100.0,
        )
        if type(self.action_config) is not ActionConfig or self.action_config != expected_action:
            raise ValueError('DG02 ActionConfig differs from the accepted DG01 Position semantics')
        source, artifact, execution = self.runtime_source, self.artifact, self.execution
        source.validate()
        artifact.validate()
        execution.validate()
        self.reset_plan.validate()
        scene = source.scene_definition
        if (self.task_source.task_id, self.task_source.version, self.task_source.scene_ref,
                artifact.task_id, artifact.artifact_version, scene.scene_id) != (
                F05_DG01_TASK_ID, F05_DG01_TASK_VERSION, F05_DG01_SCENE_ID,
                F05_DG01_TASK_ID, F05_DG01_TASK_VERSION, F05_DG01_SCENE_ID):
            raise ValueError('DG02 TaskSource/Artifact identity differs from accepted DG01 task semantics')
        if (source.task_artifact.identity_hash != artifact.identity_hash
                or artifact.scene_identity_hash != scene.identity_hash
                or source.scene_source.task_source_identity_sha256 != self.task_source.identity_hash
                or source.scene_source.scene_identity_sha256 != scene.identity_hash
                or self.reset_plan.role_binding.task_source_identity_hash != self.task_source.identity_hash
                or self.reset_plan.role_binding.scene_identity_hash != scene.identity_hash
                or self.reset_plan.reset_sample.task_artifact_hash != artifact.identity_hash):
            raise ValueError('DG02 Task/Scene/Artifact/reset identities disagree')
        if (execution.physics_provider, execution.physics_backend, execution.physics_device,
                execution.physics_profile, execution.determinism_mode) != (
                'geophys', 'cpu', 'cpu', F05_DG02_GEOPHYS_PROFILE, 'best_effort'):
            raise ValueError('DG02 requires its exact GeoPhys CPU USD execution profile')
        if (artifact.timebase.physics_dt, artifact.timebase.control_substeps,
                artifact.timebase.control_dt) != (0.002, 5, 0.01):
            raise ValueError('DG02 requires 100 Hz control with five 2 ms physics steps')
        if (execution.render_default.provider, execution.render_default.backend,
                execution.render_default.profile, execution.render_default.device,
                execution.camera_overrides) != ('none', 'cpu', 'none', None, ()):
            raise ValueError('DG02 state-only cell does not admit renderer or camera overrides')
        delivery = source.scene_source.loaded_delivery.delivery
        representation = source.scene_source.representation
        if (delivery.provenance_kind, delivery.recipe_path, delivery.recipe_sha256,
                delivery.entry_prim, delivery.entry_file,
                delivery.asset_definition.asset_id, delivery.asset_definition.asset_version,
                delivery.asset_definition.source_reference, delivery.source_revision,
                delivery.source_closure_sha256,
                representation.provider, representation.provider_build_identity,
                representation.representation_format, representation.runtime_admitted,
                source.scene_source.source_verified, source.scene_source.locally_validated) != (
                'local-validated', 'metadata/f05_dg02_usd_recipe.json', F05_DG02_USD_RECIPE_SHA256,
                '/panda', 'derived/panda.usda',
                'f05-dg02-menagerie-panda-source-preserving-usd', F05_DG02_USD_ASSET_VERSION,
                'mujoco-menagerie://franka_emika_panda/panda.xml',
                'b846dd12bc459d776cccb3dee0b1d02acbf7a9c7',
                'a59a66d0b176cb6b2634d54cd20744752742b425e5524db1b865dda0eb3adf2a',
                'geophys', self.host_model_producer_identity.requested_target_build_identity,
                'usd', False, False, True):
            raise ValueError('DG02 candidate is outside the frozen source-preserving local USD delivery')
        self.host_model_producer_identity.validate_current_tree()
        expected_bodies, expected_joints = _f05_dg02_usd_source_bindings()
        if (dict(source.joints) != expected_joints
                or dict(source.joint_targets) != expected_joints
                or dict(source.bodies) != expected_bodies
                or dict(source.frames)
                or dict(source.free_joints) != {
                    'free-cube/free_cube': '/F04Scene/free_cube/rootJoint',
                }):
            raise ValueError('DG02 USD mappings differ from the exact nine-DOF/free-cube source contract')
        expected_runtime_frames = {
            f'{frame.entity_id}/{frame.frame_id}'
            for frame in scene.frames or () if frame.frame_kind == 'runtime'
        }
        if set(expected_bodies) != expected_runtime_frames:
            raise ValueError('DG02 USD body bindings do not cover the exact canonical runtime Frames')
        if (artifact.initialization.poses_world != self.reset_plan.reset_sample.poses_world
                or set(artifact.initialization.poses_world) != {'free-cube/free_cube'}
                or artifact.initialization.poses_world['free-cube/free_cube'].position != (1.0, 0.5, 0.9)
                or artifact.initialization.poses_world['free-cube/free_cube'].quaternion_wxyz
                    != (1.0, 0.0, 0.0, 0.0)
                or dict(artifact.initialization.joint_position)
                    != dict(self.reset_plan.reset_sample.joint_position)):
            raise ValueError('DG02 reset differs from the frozen DG01 home/free-cube reset')
        if (self.native_drive_receipt.provenance_kind != 'native_runtime'
                or self.native_drive_receipt.scene_identity_sha256 != scene.identity_hash
                or self.native_drive_receipt.source_closure_sha256 != source.source_closure_digest
                or self.native_drive_receipt.execution_identity_sha256 != execution.identity_hash
                or self.native_drive_receipt.provider_build_identity
                    != self.host_model_producer_identity.actual_provider_build_identity
                or self.native_drive_receipt.host_model_producer_identity_sha256
                    != self.host_model_producer_identity.identity_sha256
                or self.native_drive_receipt.physics_profile != F05_DG02_GEOPHYS_PROFILE
                or self.native_drive_receipt.tendon_name != 'split'
                or self.native_drive_receipt.equality_name != 'finger_joint1_finger_joint2'
                or self.native_drive_receipt.equality_solref != (0.005, 1.0)
                or self.native_drive_receipt.equality_solimp != (0.95, 0.99, 0.001)):
            raise ValueError('DG02 model receipt does not bind the actual source/Scene/Execution/producer')
        receipt_targets = {
            f'{row.canonical_joint.entity_id}/{row.canonical_joint.joint_id}': row.native_dof_name
            for row in self.native_drive_receipt.drives
        }
        if receipt_targets != expected_joints:
            raise ValueError('DG02 model receipt does not cover all nine exact scalar DOF targets')
        if (not self.kinematics_source_xml or type(self.kinematics_source_xml) is not str
                or hashlib.sha256(self.kinematics_source_xml.encode()).hexdigest()
                != self.kinematics_source_sha256):
            raise ValueError('DG02 source-calibrated kinematics bytes/hash mismatch')


@dataclass(frozen=True)
class F05Dg01MujocoCandidateInputV1:
    """Exact source-bound Menagerie MJCF → MuJoCo Core candidate for DG01."""

    schema_version: str
    task_source: TaskSourceV1
    artifact: TaskArtifactV1
    runtime_source: RuntimeSource
    execution: ExecutionSpecV1
    reset_plan: EpisodeResetPlanV1
    kinematics_source_xml: str
    kinematics_source_sha256: str
    recipe_sha256: str

    def validate(self):
        if self.schema_version != 'f05-dg01-mujoco-candidate-input-v1':
            raise ValueError('unsupported F05 DG01 MuJoCo candidate input schema')
        if (type(self.task_source) is not TaskSourceV1
                or type(self.artifact) is not TaskArtifactV1
                or type(self.runtime_source) is not RuntimeSource
                or type(self.execution) is not ExecutionSpecV1
                or type(self.reset_plan) is not EpisodeResetPlanV1):
            raise TypeError('F05 DG01 requires exact TaskSource/Artifact/RuntimeSource/Execution/ResetPlan contracts')
        self.execution.validate()
        self.artifact.validate()
        self.reset_plan.validate()
        source = self.runtime_source
        scene = source.scene_definition
        if scene is None:
            raise ValueError('F05 DG01 MuJoCo RuntimeSource requires its canonical SceneDefinition')
        self.artifact.validate_scene(scene)
        if (self.task_source.task_id, self.task_source.version, self.task_source.scene_ref,
                self.artifact.task_id, self.artifact.artifact_version, scene.scene_id) != (
                F05_DG01_TASK_ID, F05_DG01_TASK_VERSION, F05_DG01_SCENE_ID,
                F05_DG01_TASK_ID, F05_DG01_TASK_VERSION, F05_DG01_SCENE_ID):
            raise ValueError('F05 DG01 candidate task/source/Scene identity mismatch')
        if (source.task_artifact_hash != self.artifact.identity_hash
                or source.scene_source.source_id != f'scene-definition-v3:{scene.identity_hash}'
                or self.reset_plan.role_binding.task_source_identity_hash != self.task_source.identity_hash
                or self.reset_plan.role_binding.scene_identity_hash != scene.identity_hash
                or self.reset_plan.reset_sample.task_artifact_hash != self.artifact.identity_hash):
            raise ValueError('F05 DG01 candidate source/Artifact/reset identities disagree')
        if (self.execution.physics_provider, self.execution.physics_backend,
                self.execution.physics_device, self.execution.physics_profile,
                self.execution.determinism_mode) != (
                'mujoco', 'cpu', 'cpu', F05_DG01_MUJOCO_PROFILE, 'strict'):
            raise ValueError('F05 DG01 candidate requires the exact MuJoCo 3.8.1 CPU execution profile')
        if (self.execution.render_default.provider, self.execution.render_default.backend,
                self.execution.render_default.profile, self.execution.render_default.device,
                self.execution.camera_overrides) != ('none', 'cpu', 'none', None, ()):
            raise ValueError('F05 DG01 is state-only and does not admit a renderer or camera overrides')
        if (self.artifact.timebase.physics_dt, self.artifact.timebase.control_substeps,
                self.artifact.timebase.control_dt) != (0.002, 5, 0.01):
            raise ValueError('F05 DG01 requires 100 Hz control with five 2 ms physics steps')
        expected_scalar_joints = {
            **{f'panda-main/joint{i}': f'joint{i}' for i in range(1, 8)},
            'panda-main/finger_joint1': 'finger_joint1',
            'panda-main/finger_joint2': 'finger_joint2',
        }
        expected_targets = {f'panda-main/joint{i}': f'actuator{i}' for i in range(1, 8)}
        expected_free_joints = {'free-cube/free_cube': 'cube_freejoint'}
        expected_bodies = {
            f'{frame.entity_id}/{frame.frame_id}': frame.frame_id
            for frame in scene.frames or () if frame.frame_kind == 'runtime'
        }
        if (dict(source.joints) != expected_scalar_joints
                or dict(source.joint_targets) != expected_targets
                or dict(source.free_joints) != expected_free_joints
                or dict(source.bodies) != expected_bodies
                or dict(source.frames)
                or tuple(source.open_actuators) != ('actuator8',)):
            raise ValueError('F05 DG01 logical-to-native bindings differ from the frozen nine-joint/free-cube map')
        if (not source.source_closure_digest or len(source.source_closure_digest) != 64
                or self.recipe_sha256 != F05_DG01_RECIPE_SHA256):
            raise ValueError('F05 DG01 requires the exact task-recipe and composed-source closure hashes')
        expected_home = {
            'panda-main/joint1': 0.012, 'panda-main/joint2': -0.568,
            'panda-main/joint3': 0.0, 'panda-main/joint4': -2.811,
            'panda-main/joint5': 0.0, 'panda-main/joint6': 3.037,
            'panda-main/joint7': 0.741,
            'panda-main/finger_joint1': 0.03999999910593033,
            'panda-main/finger_joint2': 0.03999999910593033,
        }
        if (dict(self.artifact.initialization.joint_position) != expected_home
                or dict(self.reset_plan.reset_sample.joint_position) != expected_home
                or set(self.artifact.initialization.poses_world) != {'free-cube/free_cube'}
                or set(self.reset_plan.reset_sample.poses_world) != {'free-cube/free_cube'}):
            raise ValueError('F05 DG01 reset does not use the frozen original home and r009 free-cube pose')
        from task_env.runtime.sessions.api import _validate_f05_dg01_mujoco_source
        _validate_f05_dg01_mujoco_source(self.artifact, self.execution, source)
        if (not self.kinematics_source_xml or type(self.kinematics_source_xml) is not str
                or hashlib.sha256(self.kinematics_source_xml.encode()).hexdigest()
                != self.kinematics_source_sha256
                or self.kinematics_source_xml != source.scene_source.xml):
            raise ValueError('F05 DG01 source-calibrated kinematics bytes/hash mismatch')


def build_versioned_position_candidate(input_v1: F03PositionCandidateInputV1 | F04PositionCandidateInputV1 | F05PositionCandidateInputV1 | F05NativePositionCandidateInputV1 | F05Dg02GeoPhysUsdCandidateInputV1 | F05Dg01MujocoCandidateInputV1, *, horizon=8,
                                       environment_type=SelectedReferenceEnv,
                                       camera_observation_config=None,
                                       controller_config=None):
    """Build through the existing binding and SelectedReferenceEnv owners."""
    if type(input_v1) not in (F03PositionCandidateInputV1, F04PositionCandidateInputV1,
                              F05PositionCandidateInputV1, F05NativePositionCandidateInputV1,
                              F05Dg02GeoPhysUsdCandidateInputV1,
                              F05Dg01MujocoCandidateInputV1):
        raise TypeError('versioned Position candidate requires an exact F03/F04/F05/DG01/DG02 input contract')
    input_v1.validate()
    if type(input_v1) is F05NativePositionCandidateInputV1:
        _validate_f05_native_position_action_config(controller_config)
    elif type(input_v1) is F05Dg02GeoPhysUsdCandidateInputV1:
        if controller_config is not None and controller_config != input_v1.action_config:
            raise ValueError('DG02 controller override differs from its frozen ActionConfig')
    elif controller_config is not None and type(input_v1) is not F05Dg01MujocoCandidateInputV1:
        raise ValueError('explicit Position ActionConfig is supported only by exact F05 native, DG01, or DG02 candidates')
    source = input_v1.runtime_source
    artifact = input_v1.artifact
    scene = source.scene_definition
    native_drive_receipt = getattr(input_v1, 'native_drive_receipt', None)
    position_config = (
        input_v1.action_config
        if type(input_v1) is F05Dg02GeoPhysUsdCandidateInputV1
        else controller_config
    )
    nullspace_reference_gain = (
        F05_DG02_NULLSPACE_REFERENCE_GAIN
        if type(input_v1) is F05Dg02GeoPhysUsdCandidateInputV1
        else 0.0
    )
    if type(source) is UsdRuntimeSourceV1:
        profile = PandaPositionServoProfileV1.from_usd_source(
            artifact, source, execution=input_v1.execution,
            kinematics_source_xml=input_v1.kinematics_source_xml,
            native_drive_receipt=native_drive_receipt,
            config=position_config,
            nullspace_reference_gain=nullspace_reference_gain,
            pose_target_method=(
                F05_DG02_POSE_TARGET_METHOD
                if type(input_v1) is F05Dg02GeoPhysUsdCandidateInputV1
                else 'achieved_state_dls_v1'
            ),
        )
    else:
        profile = PandaPositionServoProfileV1.from_source(
            artifact, source, config=controller_config,
            nullspace_reference_gain=nullspace_reference_gain,
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
            'f05_position_input': input_v1 if type(input_v1) in (
                F05PositionCandidateInputV1, F05NativePositionCandidateInputV1,
            ) else None,
            'f05_native_position_input': input_v1 if type(input_v1) is F05NativePositionCandidateInputV1 else None,
            'f05_dg02_geophys_input': input_v1 if type(input_v1) is F05Dg02GeoPhysUsdCandidateInputV1 else None,
            'f05_dg01_mujoco_input': input_v1 if type(input_v1) is F05Dg01MujocoCandidateInputV1 else None,
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
                                else 'F04-versioned-usd-native-candidate-v1'
                                if type(input_v1) is F04PositionCandidateInputV1
                                else 'F05-versioned-geophys-usd-native-v1'
                                if type(input_v1) is F05NativePositionCandidateInputV1
                                else 'F05-DG01-versioned-menagerie-mjcf-mujoco-core-v1'
                                if type(input_v1) is F05Dg01MujocoCandidateInputV1
                                else 'F05-DG02-source-preserving-geophys-usd-core-v1'
                                if type(input_v1) is F05Dg02GeoPhysUsdCandidateInputV1
                                else 'F05-versioned-geophys-usd-synthetic-s1-v1'),
            'source_sha256': {
                'source_closure': source.source_closure_digest,
                'kinematics_source': input_v1.kinematics_source_sha256,
            },
        }

    def fixed_seed(seed):
        if type(seed) is not int or seed != input_v1.reset_plan.reset_sample.task_seed:
            raise ValueError('F03 reset seed must match its fixed EpisodeResetPlan')
        return seed

    def evaluate(state, semantics):
        if type(input_v1) not in (
                F05Dg01MujocoCandidateInputV1, F05Dg02GeoPhysUsdCandidateInputV1):
            return SimpleNamespace(reward=0.0, success=False, failure=False, metrics={})
        pose_name = 'free-cube/free_cube'
        cube_pose = state.pose_world.get(pose_name)
        if cube_pose is None:
            raise ValueError('F05 Task evaluator requires the measured free-cube Frame')
        threshold_m = float(semantics.parameters_si['lift_threshold_z_m'])
        center_z_m = float(cube_pose.position[2])
        raw_lift_predicate = center_z_m >= threshold_m
        return SimpleNamespace(
            reward=1.0 if raw_lift_predicate else 0.0,
            success=raw_lift_predicate,
            failure=False,
            metrics={
                'raw_lift_height_predicate': raw_lift_predicate,
                'free_cube_center_z_m': center_z_m,
                'lift_threshold_z_m': threshold_m,
                'reset_initial_height_already_satisfies_raw_predicate': (
                    float(input_v1.artifact.initialization.poses_world[pose_name].position[2])
                    >= threshold_m
                ),
                'lifecycle_terminated': False,
            },
        )

    binding = ReferenceTaskBinding(
        build=build,
        reset_sample=lambda _artifact, _seed: input_v1.reset_plan.reset_sample,
        evaluate=evaluate,
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
        f05_position_input=input_v1 if type(input_v1) is F05PositionCandidateInputV1 else None,
        f05_native_position_input=input_v1 if type(input_v1) is F05NativePositionCandidateInputV1 else None,
        f05_dg02_geophys_input=input_v1 if type(input_v1) is F05Dg02GeoPhysUsdCandidateInputV1 else None,
        f05_dg01_mujoco_input=input_v1 if type(input_v1) is F05Dg01MujocoCandidateInputV1 else None,
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


def build_f05_dg01_mujoco_candidate(workspace: Path | str, *, horizon: int = 300,
                                   environment_type=SelectedReferenceEnv,
                                   controller_config=None):
    """Construct DG01 from the frozen Menagerie source through the existing Core path."""
    import importlib

    from task_env.environment import compile_task_artifact_v1, sample_episode_reset_plan

    root = Path(workspace).resolve()
    root.mkdir(parents=True, exist_ok=True)
    scene = _f05_dg01_scene()
    legacy_artifact, _ = _f05_dg01_artifact_and_sample(scene)
    task_source = _f05_dg01_task_source(scene)
    artifact = compile_task_artifact_v1(task_source, scene, legacy_artifact)
    reset_plan = sample_episode_reset_plan(
        task_source, scene, artifact, task_seed=POSITION_CANDIDATE_SEED,
    )
    scene_module = importlib.import_module('scene')
    source_root, panda_files, panda_digest = _copy_panda_snapshot(
        scene_module, root / 'source-closure' / 'menagerie-panda', scene,
    )
    source_xml = _compose_f05_dg01_scene_source(
        scene, source_root, physics_dt=artifact.timebase.physics_dt,
    )
    source, imported, closure_digest = _f05_dg01_runtime_source(
        scene_module, scene, source_root, source_xml, artifact,
    )
    if imported is None or len(panda_digest) != 64 or len(closure_digest) != 64:
        raise ValueError('F05 DG01 Panda/task-scene source closure evidence is incomplete')
    execution = ExecutionSpecV1(
        schema_version='execution-spec-v1',
        physics_provider='mujoco',
        physics_backend='cpu',
        physics_profile=F05_DG01_MUJOCO_PROFILE,
        provider_seed=0,
        determinism_mode='strict',
        render_default=RendererSelectionV1(
            'renderer-selection-v1', 'none', 'cpu', 'none', None,
        ),
        physics_device='cpu',
        camera_overrides=(),
    )
    kinematics_xml = source.scene_source.xml
    candidate_input = F05Dg01MujocoCandidateInputV1(
        schema_version='f05-dg01-mujoco-candidate-input-v1',
        task_source=task_source,
        artifact=artifact,
        runtime_source=source,
        execution=execution,
        reset_plan=reset_plan,
        kinematics_source_xml=kinematics_xml,
        kinematics_source_sha256=hashlib.sha256(kinematics_xml.encode()).hexdigest(),
        recipe_sha256=F05_DG01_RECIPE_SHA256,
    )
    candidate_input.validate()
    built = build_versioned_position_candidate(
        candidate_input, horizon=horizon, environment_type=environment_type,
        controller_config=controller_config,
    )
    return SimpleNamespace(
        **vars(built),
        candidate_input=candidate_input,
        panda_closure_digest=panda_digest,
        panda_file_count=len(panda_files),
        derived_source_xml=source_xml,
        derived_source_sha256=hashlib.sha256(source_xml.encode()).hexdigest(),
        source_closure_digest=closure_digest,
        recipe_sha256=F05_DG01_RECIPE_SHA256,
        provider='mujoco',
    )


__all__ = [
    'F03PositionCandidateInputV1', 'F04PositionCandidateInputV1',
    'F05PositionCandidateInputV1', 'F05NativePositionCandidateInputV1',
    'F05Dg01MujocoCandidateInputV1', 'F05_DG01_MUJOCO_PROFILE',
    'POSITION_CANDIDATE_SEED',
    'POSITION_CANDIDATE_TASK_ID', 'POSITION_CANDIDATE_VERSION',
    'build_f05_dg01_mujoco_candidate', 'build_position_candidate',
    'build_versioned_position_candidate',
]
