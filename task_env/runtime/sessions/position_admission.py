"""Source-bound F05 runtime admission inputs and frozen source declarations.

Task Scene construction remains with its task owner. These exact types and
validators are shared by the runtime admission path and task-side builders.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from ...artifacts import ExecutionSpecV1, TaskArtifactV1
from ...artifacts.execution import EpisodeResetPlanV1
from ...environment.task_source import TaskSourceV1
from .source import UsdRuntimeSourceV1, validate_usd_task_reset_identities
from .leaf_control import GeoPhysHostModelProducerIdentityV1, GeoPhysUsdSourceActuationReceiptV2

F05_DG01_SCENE_ID = "f05-dg01-menagerie-panda-cube-support"


F05_DG01_TASK_ID = "phase-ii-f05-dg01-panda-cube"


F05_DG01_TASK_VERSION = "candidate-v1"


F05_DG01_RECIPE_SHA256 = "6a705816e619681e948a1b243e0588dd1db2f667ecfb085bd2e55b1c3fd8b89d"


F05_DG04_ISAAC_NATIVE_PROFILE = 'isaac-gpu-physx-f05-dg04-native-mimic-v1'


F05_DG02_GEOPHYS_PROFILE = 'geophys-usd-position-f05-dg02-core-v1'


F05_DG02_USD_ASSET_VERSION = 'f05-dg02-usd-v2'


F05_DG02_USD_RECIPE_SHA256 = '003238fb99d5b2574e5550918b6902518d7bc09cd0d6f4ad02049ccc408bb0fd'


_F05_ISAAC_USD_ASSET_ID = 'f05-dg03-menagerie-panda-source-preserving-isaac-usd'


_F05_ISAAC_USD_ASSET_VERSION = 'f05-dg03-isaac-usd-v4'


_F05_ISAAC_USD_DELIVERY_IDENTITY_SHA256 = '1db5fd51add419ec4bca461ceed5552a8578cd77adac41f153993746a4d07194'


_F05_ISAAC_USD_DELIVERY_CLOSURE_SHA256 = '84c76220531db6688962a9544e33ab950e0de300eac6b7dc475e2469f89d9c8e'


_F05_ISAAC_USD_DELIVERY_MANIFEST_SHA256 = '06958dd05d901408f74f8e71cefdd73f6e5e28df0451457ea3b616c95ab0ad58'


_F05_ISAAC_USD_RECIPE_SHA256 = '6fa56c502337a0feee5243c74e6d55845e5cf733873eab9c70319c916be8641b'


_F05_ISAAC_USD_REPORT_SHA256 = 'f331be05fabe8fb019f009d44b0eb1ee13de058320bc60cecd3e06327158c710'


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


def _f05_isaac_usd_source_bindings():
    """Return the frozen Isaac/USD body and static-frame maps used by DG04."""
    body_paths, joints = _f05_dg02_usd_source_bindings()
    body_paths = dict(body_paths)
    body_paths['free-cube/free_cube'] = '/F05Scene/free_cube'
    body_paths['free-cube/world'] = '/F05Scene/free_cube'
    # The local F05 overlay authors a static collision Xform for the support.
    # Preserve it as a RuntimeSource Frame so Isaac's existing public XformPrim
    # route reads it without claiming that it is a dynamic rigid body.
    body_paths.pop('support/support')
    frame_paths = {'support/support': '/F05Scene/support'}
    return body_paths, frame_paths, joints


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
        if (self.task_source.scene_ref != source.scene_definition.scene_id
                or self.task_source.task_id != artifact.task_id
                or self.task_source.version != artifact.artifact_version):
            raise ValueError('F05 native source/TaskSource/Artifact/reset identities disagree')
        validate_usd_task_reset_identities(
            self.task_source, artifact, source, self.reset_plan,
            error_message='F05 native source/TaskSource/Artifact/reset identities disagree',
        )
        if (execution.physics_provider, execution.physics_backend, execution.physics_device,
                execution.physics_profile, execution.determinism_mode) != (
                'geophys', 'cpu', 'cpu', 'geophys-usd-position-f05-native-v1', 'best_effort'):
            raise ValueError('F05 native input requires the exact GeoPhys CPU native execution identity')
        if (artifact.timebase.physics_dt, artifact.timebase.control_substeps,
                artifact.timebase.control_dt) != (0.002, 5, 0.01):
            raise ValueError('F05 native input requires 100 Hz / five 2 ms physics steps')
        from .api import CAPABILITIES
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
        validate_usd_task_reset_identities(
            self.task_source, artifact, source, self.reset_plan,
            error_message='DG02 Task/Scene/Artifact/reset identities disagree',
        )
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
class _F05IsaacUsdSourcePreparationV1:
    """Private frozen source preparation consumed by the DG04 candidate builder."""

    schema_version: str
    task_source: TaskSourceV1
    artifact: TaskArtifactV1
    runtime_source: UsdRuntimeSourceV1
    reset_plan: EpisodeResetPlanV1
    kinematics_source_xml: str
    kinematics_source_sha256: str
    task_scene_recipe_sha256: str
    action_config: object

    def validate(self):
        if self.schema_version != 'f05-isaac-usd-source-preparation-v1':
            raise ValueError('unsupported private F05 Isaac/USD source-preparation schema')
        if (type(self.task_source) is not TaskSourceV1
                or type(self.artifact) is not TaskArtifactV1
                or type(self.runtime_source) is not UsdRuntimeSourceV1
                or type(self.reset_plan) is not EpisodeResetPlanV1):
            raise TypeError('F05 Isaac source preparation requires exact TaskSource/Artifact/USD/reset contracts')
        from task_env.environment.config import ActionConfig

        if type(self.action_config) is not ActionConfig or self.action_config != ActionConfig(
                joint_position_correction_gain=1.0,
                gripper_default_force_N=100.0):
            raise ValueError('F05 Isaac source preparation differs from accepted DG01 Position semantics')
        source, artifact = self.runtime_source, self.artifact
        source.validate()
        artifact.validate()
        self.reset_plan.validate()
        scene = source.scene_definition
        if (self.task_source.task_id, self.task_source.version, self.task_source.scene_ref,
                artifact.task_id, artifact.artifact_version, scene.scene_id) != (
                F05_DG01_TASK_ID, F05_DG01_TASK_VERSION, F05_DG01_SCENE_ID,
                F05_DG01_TASK_ID, F05_DG01_TASK_VERSION, F05_DG01_SCENE_ID):
            raise ValueError('F05 Isaac source preparation differs from the frozen DG01 task')
        validate_usd_task_reset_identities(
            self.task_source, artifact, source, self.reset_plan,
            error_message='F05 Isaac source-preparation Task/Scene/Artifact/reset identities disagree',
        )
        delivery = source.scene_source.loaded_delivery
        representation = source.scene_source.representation
        d = delivery.delivery
        if (delivery.source_verified, delivery.locally_validated,
                d.provenance_kind, delivery.manifest_bytes_sha256,
                delivery.delivery_sha256, delivery.closure_sha256,
                d.recipe_sha256, d.asset_definition.asset_id,
                d.asset_definition.asset_version, d.asset_definition.source_reference,
                d.asset_definition.source_revision, d.source_closure_sha256,
                d.source_entry_sha256, representation.provider,
                representation.provider_build_identity, representation.representation_format,
                representation.runtime_admitted) != (
                False, True, 'local-validated', _F05_ISAAC_USD_DELIVERY_MANIFEST_SHA256,
                _F05_ISAAC_USD_DELIVERY_IDENTITY_SHA256, _F05_ISAAC_USD_DELIVERY_CLOSURE_SHA256,
                _F05_ISAAC_USD_RECIPE_SHA256, _F05_ISAAC_USD_ASSET_ID,
                _F05_ISAAC_USD_ASSET_VERSION,
                'mujoco-menagerie://franka_emika_panda/panda.xml',
                'b846dd12bc459d776cccb3dee0b1d02acbf7a9c7',
                'a59a66d0b176cb6b2634d54cd20744752742b425e5524db1b865dda0eb3adf2a',
                '96ad67da03710f17f798c9478fd9e9efdf24a3bf8359f05e456dd9fb158ea273',
                'isaacsim', 'isaacsim-6.2.0.0', 'usd', False):
            raise ValueError('F05 Isaac source preparation is outside the exact local Menagerie delivery')
        if (d.recipe_path, d.validation_report_path, d.validation_report_sha256) != (
                'metadata/f05_dg03_isaac_usd_recipe_v4.json',
                'metadata/f05_dg03_local_validation_report_v4.json',
                _F05_ISAAC_USD_REPORT_SHA256):
            raise ValueError('F05 Isaac source preparation differs from its frozen local delivery')
        from task_env.assembly.usd_delivery import _canonical_hash

        expected_options = {
            'f05_goal': 'DG04',
            'lowering': 'isaacsim-6.2-physx-native-mimic-leader-drive-v1',
            'delivery_manifest_sha256': _F05_ISAAC_USD_DELIVERY_MANIFEST_SHA256,
            'task_scene_recipe_sha256': F05_DG01_RECIPE_SHA256,
        }
        if (representation.options_sha256 != _canonical_hash(expected_options)
                or representation.source_verified is not False
                or delivery.manifest_bytes_sha256 != _F05_ISAAC_USD_DELIVERY_MANIFEST_SHA256):
            raise ValueError('F05 Isaac source preparation does not bind the exact DG04 delivery/options')
        expected_bodies, expected_frames, expected_joints = _f05_isaac_usd_source_bindings()
        if (dict(source.joints) != expected_joints
                or dict(source.joint_targets) != expected_joints
                or dict(source.bodies) != expected_bodies
                or dict(source.frames) != expected_frames
                or dict(source.free_joints) != {
                    'free-cube/free_cube': '/F05Scene/free_cube/rootJoint',
                }):
            raise ValueError('F05 Isaac source preparation differs from the exact Panda/free-cube bindings')
        expected_runtime_frames = {
            f'{frame.entity_id}/{frame.frame_id}'
            for frame in scene.frames or () if frame.frame_kind == 'runtime'
        }
        if set(expected_bodies) | set(expected_frames) != expected_runtime_frames:
            raise ValueError('F05 Isaac source bindings do not cover canonical runtime Frames')
        if (artifact.initialization.poses_world != self.reset_plan.reset_sample.poses_world
                or set(artifact.initialization.poses_world) != {'free-cube/free_cube'}
                or artifact.initialization.poses_world['free-cube/free_cube'].position != (1.0, 0.5, 0.9)
                or artifact.initialization.poses_world['free-cube/free_cube'].quaternion_wxyz
                    != (1.0, 0.0, 0.0, 0.0)
                or dict(artifact.initialization.joint_position)
                    != dict(self.reset_plan.reset_sample.joint_position)):
            raise ValueError('F05 Isaac reset differs from the frozen DG01 home/free-cube reset')
        if self.task_scene_recipe_sha256 != F05_DG01_RECIPE_SHA256:
            raise ValueError('F05 Isaac task scene recipe differs from the frozen DG01 recipe')
        if (not self.kinematics_source_xml or type(self.kinematics_source_xml) is not str
                or hashlib.sha256(self.kinematics_source_xml.encode()).hexdigest()
                    != self.kinematics_source_sha256
                or self.kinematics_source_sha256
                    != '96ad67da03710f17f798c9478fd9e9efdf24a3bf8359f05e456dd9fb158ea273'):
            raise ValueError('F05 Isaac source-calibrated kinematics bytes/hash mismatch')


@dataclass(frozen=True)
class F05Dg04IsaacNativeCandidateInputV1:
    """DG04 source-bound Isaac profile with one native mimic-driven finger."""

    schema_version: str
    task_source: TaskSourceV1
    artifact: TaskArtifactV1
    runtime_source: UsdRuntimeSourceV1
    execution: ExecutionSpecV1
    reset_plan: EpisodeResetPlanV1
    kinematics_source_xml: str
    kinematics_source_sha256: str
    task_scene_recipe_sha256: str
    action_config: object

    def validate(self):
        if self.schema_version != 'f05-dg04-isaac-native-candidate-input-v1':
            raise ValueError('unsupported F05 DG04 Isaac native candidate input schema')
        if (type(self.task_source) is not TaskSourceV1
                or type(self.artifact) is not TaskArtifactV1
                or type(self.runtime_source) is not UsdRuntimeSourceV1
                or type(self.execution) is not ExecutionSpecV1
                or type(self.reset_plan) is not EpisodeResetPlanV1):
            raise TypeError('DG04 requires exact TaskSource/Artifact/USD/Execution/reset contracts')
        from task_env.environment.config import ActionConfig
        if type(self.action_config) is not ActionConfig or self.action_config != ActionConfig(
                joint_position_correction_gain=1.0,
                gripper_default_force_N=100.0):
            raise ValueError('DG04 ActionConfig differs from accepted DG01 Position semantics')

        _F05IsaacUsdSourcePreparationV1(
            'f05-isaac-usd-source-preparation-v1', self.task_source, self.artifact,
            self.runtime_source, self.reset_plan, self.kinematics_source_xml,
            self.kinematics_source_sha256, self.task_scene_recipe_sha256,
            self.action_config,
        ).validate()
        self.execution.validate()
        if (self.execution.physics_provider, self.execution.physics_backend,
                self.execution.physics_device, self.execution.physics_profile,
                self.execution.determinism_mode) != (
                'isaacsim', 'cuda', 'cuda:0', F05_DG04_ISAAC_NATIVE_PROFILE, 'best_effort'):
            raise ValueError('DG04 requires its exact versioned Isaac CUDA/native-mimic profile')
