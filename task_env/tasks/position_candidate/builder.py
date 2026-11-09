"""Task-owned construction for the bounded C02b Position candidate."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
import hashlib

from task_env.artifacts import Timebase
from task_env.controllers.canonical.contracts import (digest, REFERENCE_POSE_ACTION_SCHEMA,
    reference_pose_action, reference_pose_action_space)
from task_env.observations.selected_reference import build_selected_observation, selected_reference_observation_spaces
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
from task_env.runtime.sessions.position_admission import (
    F05NativePositionCandidateInputV1, F05Dg02GeoPhysUsdCandidateInputV1,
    F05Dg04IsaacNativeCandidateInputV1, _F05IsaacUsdSourcePreparationV1,
    F05_DG04_ISAAC_NATIVE_PROFILE, F05_DG02_GEOPHYS_PROFILE,
    F05_DG02_USD_ASSET_VERSION, F05_DG02_USD_RECIPE_SHA256,
    _F05_ISAAC_USD_ASSET_ID, _F05_ISAAC_USD_ASSET_VERSION,
    _F05_ISAAC_USD_DELIVERY_IDENTITY_SHA256, _F05_ISAAC_USD_DELIVERY_CLOSURE_SHA256,
    _F05_ISAAC_USD_DELIVERY_MANIFEST_SHA256, _F05_ISAAC_USD_RECIPE_SHA256,
    _F05_ISAAC_USD_REPORT_SHA256, _f05_dg02_usd_source_bindings,
    _f05_isaac_usd_source_bindings,
)
from task_env.runtime.sessions.source import (
    RuntimeSource, UsdRuntimeSourceV1, validate_usd_task_reset_identities,
)
from task_env.runtime.sessions.leaf_control import (
    GeoPhysHostModelProducerIdentityV1,
    GeoPhysUsdPositionDriveReceiptV1, GeoPhysUsdSourceActuationReceiptV2,
    IsaacNamedPositionDriveReceiptV1,
)
from task_env.runtime.sessions.control import ControlBinding, compile_control_binding_plan
from task_env.environment.reference_binding import ReferenceTaskBinding, legacy_position_physical_observation_binding
from task_env.environment.reference_env import SelectedReferenceEnv


POSITION_CANDIDATE_TASK_ID = 'phase-ii-c02b-position-servo'
POSITION_CANDIDATE_VERSION = 'candidate-v1'
POSITION_CANDIDATE_SEED = 31


def _dg02_r3_arm_profile():
    """Resolve the shared R3 profile from its controller owner."""
    from task_env.controllers.canonical.production_r3 import (
        R3_PROFILE_PATH, load_r3_dynamic_profile,
    )

    profile = load_r3_dynamic_profile()
    return {**profile, 'profile_source_sha256': hashlib.sha256(R3_PROFILE_PATH.read_bytes()).hexdigest()}


def _validate_f05_native_position_action_config(controller_config):
    from task_env.environment.config import ActionConfig

    if type(controller_config) is not ActionConfig:
        raise TypeError('F05 native candidate requires its frozen Position ActionConfig')
    if controller_config != ActionConfig(
            joint_position_correction_gain=1.0,
            gripper_default_force_N=100.0):
        raise ValueError('F05 native ActionConfig differs from the accepted DG01 control semantics')


# The DG02 Core route tracks source-FK pose targets whose Panda solution is
# redundant. The bounded probes found a tradeoff: gain 0.0 reduced target error
# and speed versus 1.0, while increasing joint jitter. Use the midpoint for a
# short source-bound response diagnostic; this is not a qualified controller
# setting. Other Position routes are unchanged. Recompute each increment from
# achieved state so delayed physical response cannot wind up an accumulated
# joint target.
F05_DG02_NULLSPACE_REFERENCE_GAIN = 0.5
F05_DG02_POSE_TARGET_METHOD = 'achieved_state_dls_v1'






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










def build_f05_dg04_isaac_native_candidate(
    delivery_manifest, *, task_seed=POSITION_CANDIDATE_SEED, horizon=300,
    environment_type=SelectedReferenceEnv,
):
    """Build the DG04 native-mimic candidate from its private frozen source preparation."""
    from task_env.environment.config import ActionConfig

    source_prep = _prepare_f05_isaac_usd_source(
        delivery_manifest, task_seed=task_seed,
    )
    execution = ExecutionSpecV1(
        'execution-spec-v1', 'isaacsim', 'cuda', F05_DG04_ISAAC_NATIVE_PROFILE,
        0, 'best_effort', RendererSelectionV1(
            'renderer-selection-v1', 'none', 'cpu', 'none', None,
        ), 'cuda:0', (),
    )
    input_v1 = F05Dg04IsaacNativeCandidateInputV1(
        'f05-dg04-isaac-native-candidate-input-v1', source_prep.task_source,
        source_prep.artifact, source_prep.runtime_source, execution, source_prep.reset_plan,
        source_prep.kinematics_source_xml, source_prep.kinematics_source_sha256,
        source_prep.task_scene_recipe_sha256,
        ActionConfig(joint_position_correction_gain=1.0, gripper_default_force_N=100.0),
    )
    input_v1.validate()
    candidate = build_versioned_position_candidate(
        input_v1, horizon=horizon, environment_type=environment_type,
    )
    return input_v1, candidate


def _prepare_f05_isaac_usd_source(delivery_manifest, *, task_seed=POSITION_CANDIDATE_SEED):
    """Prepare the exact frozen Isaac/USD source consumed by the DG04 builder."""
    from dataclasses import replace as dataclass_replace
    from task_env.assembly.source import UsdTaskSceneSourceV1
    from task_env.assembly.usd_delivery import (
        _canonical_hash, load_usd_asset_delivery, resolve_provider_representation,
    )
    from task_env.artifacts import TaskArtifact, ExecutionSpecV1, RendererSelectionV1
    from task_env.environment import compile_task_artifact_v1, sample_episode_reset_plan
    from task_env.environment.config import ActionConfig

    loaded = load_usd_asset_delivery(Path(delivery_manifest).resolve(strict=True))
    if (not loaded.locally_validated or loaded.source_verified
            or loaded.manifest_bytes_sha256 != _F05_ISAAC_USD_DELIVERY_MANIFEST_SHA256
            or loaded.delivery_sha256 != _F05_ISAAC_USD_DELIVERY_IDENTITY_SHA256
            or loaded.closure_sha256 != _F05_ISAAC_USD_DELIVERY_CLOSURE_SHA256):
        raise ValueError('DG04 source preparation requires the exact locally validated delivery bytes')
    scene = _f05_dg01_scene()
    legacy_artifact, _ = _f05_dg01_artifact_and_sample(scene)
    task_source = _f05_dg01_task_source(scene)
    panda_asset = loaded.delivery.asset_definition
    old_assets = [asset for asset in scene.assets if asset.asset_id == 'panda-v1']
    if len(old_assets) != 1:
        raise ValueError('F05 Isaac preparation could not locate the exact DG01 Panda asset owner')
    scene = dataclass_replace(
        scene,
        assets=tuple(panda_asset if asset == old_assets[0] else asset for asset in scene.assets),
        entities=tuple(
            dataclass_replace(entity, asset_id=panda_asset.asset_id,
                              asset_version=panda_asset.asset_version)
            if entity.entity_id == 'panda-main' else entity
            for entity in scene.entities
        ),
    )
    scene.validate()
    legacy_mapping = legacy_artifact.to_mapping()
    for entity in legacy_mapping['world']['entities']:
        if entity['semantic_id'] == 'panda-main':
            entity['asset_reference'] = f'{panda_asset.source_reference}@{panda_asset.asset_version}'
    legacy_artifact = TaskArtifact.from_mapping(legacy_mapping)
    artifact = compile_task_artifact_v1(task_source, scene, legacy_artifact)
    reset_plan = sample_episode_reset_plan(task_source, scene, artifact, task_seed=int(task_seed))
    bodies, frames, joints = _f05_isaac_usd_source_bindings()
    options = {
        'f05_goal': 'DG04',
        'lowering': 'isaacsim-6.2-physx-native-mimic-leader-drive-v1',
        'delivery_manifest_sha256': _F05_ISAAC_USD_DELIVERY_MANIFEST_SHA256,
        'task_scene_recipe_sha256': F05_DG01_RECIPE_SHA256,
    }
    representation = resolve_provider_representation(
        loaded, provider='isaacsim', provider_build_identity='isaacsim-6.2.0.0',
        options=options,
    )
    if representation.options_sha256 != _canonical_hash(options):
        raise ValueError('DG04 provider selection did not bind its native-mimic source options')
    task_scene_source = UsdTaskSceneSourceV1(
        'usd-task-scene-source-v1', loaded, representation,
        task_source.identity_hash, scene.identity_hash,
    )
    source = UsdRuntimeSourceV1(
        'usd-runtime-source-v1', artifact, scene, task_scene_source,
        joints, bodies, frames, {'free-cube/free_cube': '/F05Scene/free_cube/rootJoint'}, joints,
    )
    original_xml = loaded.source_input_bytes.get(loaded.delivery.source_entry_file)
    if type(original_xml) is not bytes:
        raise ValueError('DG04 source preparation lacks the exact Menagerie source XML bytes')
    source_xml = original_xml.decode('utf-8')
    source_prep = _F05IsaacUsdSourcePreparationV1(
        'f05-isaac-usd-source-preparation-v1', task_source, artifact, source,
        reset_plan, source_xml, hashlib.sha256(original_xml).hexdigest(),
        F05_DG01_RECIPE_SHA256,
        ActionConfig(joint_position_correction_gain=1.0, gripper_default_force_N=100.0),
    )
    source_prep.validate()
    return source_prep
def _versioned_position_candidate_kind(input_v1):
    if input_v1 is None:
        return None
    kinds = {
        F04PositionCandidateInputV1: 'f04',
        F05NativePositionCandidateInputV1: 'f05_native',
        F05Dg02GeoPhysUsdCandidateInputV1: 'dg02_geophys',
        F05Dg04IsaacNativeCandidateInputV1: 'dg04_isaac_native',
    }
    try:
        return kinds[type(input_v1)]
    except KeyError as error:
        raise TypeError('versioned Position value requires an exact supported candidate input') from error


def build_versioned_position_candidate(input_v1: F04PositionCandidateInputV1 | F05NativePositionCandidateInputV1 | F05Dg02GeoPhysUsdCandidateInputV1 | F05Dg04IsaacNativeCandidateInputV1, *, horizon=8,
                                       environment_type=SelectedReferenceEnv,
                                       camera_observation_config=None,
                                       controller_config=None, physical_execution=None):
    """Build through the existing binding and SelectedReferenceEnv owners."""
    if type(input_v1) not in (F04PositionCandidateInputV1,
                              F05NativePositionCandidateInputV1,
                              F05Dg02GeoPhysUsdCandidateInputV1,
                              F05Dg04IsaacNativeCandidateInputV1):
        raise TypeError('versioned Position candidate requires an exact F04/F05-native/DG02/DG04 input contract')
    input_v1.validate()
    if type(input_v1) is F05NativePositionCandidateInputV1:
        _validate_f05_native_position_action_config(controller_config)
    elif type(input_v1) is F05Dg02GeoPhysUsdCandidateInputV1:
        if controller_config is not None and controller_config != input_v1.action_config:
            raise ValueError('DG02 controller override differs from its frozen ActionConfig')
    elif type(input_v1) is F05Dg04IsaacNativeCandidateInputV1:
        if controller_config is not None and controller_config != input_v1.action_config:
            raise ValueError('DG04 controller override differs from its frozen ActionConfig')
    elif controller_config is not None:
        raise ValueError('explicit Position ActionConfig is supported only by exact F05 native, DG02, or DG04 candidates')
    source = input_v1.runtime_source
    artifact = input_v1.artifact
    scene = source.scene_definition
    if physical_execution is not None:
        from task_env.runtime.sessions.physical_control import PhysicalControlExecutionV1
        if type(physical_execution) is not PhysicalControlExecutionV1:
            raise TypeError('physical_execution must be the exact physical control execution contract')
        physical_execution.validate_source(scene=scene, artifact_sha256=artifact.identity_hash,
            source_id=source.source_id, source_closure_sha256=source.source_closure_digest,
            source=source)
    native_drive_receipt = getattr(input_v1, 'native_drive_receipt', None)
    position_config = input_v1.action_config if type(input_v1) in (
        F05Dg02GeoPhysUsdCandidateInputV1, F05Dg04IsaacNativeCandidateInputV1,
    ) else controller_config
    nullspace_reference_gain = (
        F05_DG02_NULLSPACE_REFERENCE_GAIN
        if type(input_v1) in (F05Dg02GeoPhysUsdCandidateInputV1, F05Dg04IsaacNativeCandidateInputV1)
        else 0.0
    )
    arm_tracking_method = (
        'production_r3_continuous_v1'
        if type(input_v1) in (F05Dg02GeoPhysUsdCandidateInputV1, F05Dg04IsaacNativeCandidateInputV1)
        else 'canonical_position_v1'
    )
    arm_tracking_profile = (
        _dg02_r3_arm_profile()
        if arm_tracking_method == 'production_r3_continuous_v1'
        else None
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
                if type(input_v1) in (F05Dg02GeoPhysUsdCandidateInputV1, F05Dg04IsaacNativeCandidateInputV1)
                else 'achieved_state_dls_v1'
            ),
            arm_tracking_method=arm_tracking_method,
            arm_tracking_profile=arm_tracking_profile,
        )
    else:
        profile = PandaPositionServoProfileV1.from_source(
            artifact, source, config=controller_config,
            nullspace_reference_gain=nullspace_reference_gain,
        )
    plan = compile_control_binding_plan(scene, (profile.controller_binding(),))
    if input_v1.reset_plan.reset_sample.task_seed < 0:
        raise ValueError('Position candidate reset seed must be nonnegative')

    def build(_provider):
        return {
            'artifact': artifact, 'task_source': input_v1.task_source,
            'solution': None, 'controller': profile, 'source': source,
            'reset_plan': input_v1.reset_plan,
            'controller_binding_plan': plan,
            'execution_spec_v1': input_v1.execution,
            'versioned_position_input': input_v1,
            'session_admission_input': input_v1 if type(input_v1) in (
                F05NativePositionCandidateInputV1, F05Dg02GeoPhysUsdCandidateInputV1,
                F05Dg04IsaacNativeCandidateInputV1,
            ) else None,
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
                **({'physical_binding': physical_execution.compiled.binding.identity_hash,
                    'physical_controllers': [item.identity for item in physical_execution.controllers]}
                   if physical_execution is not None else {}),
                'kinematics_source_sha256': input_v1.kinematics_source_sha256,
            }),
            'resolved_configuration': {
                'provider': input_v1.execution.physics_provider,
                'backend': input_v1.execution.physics_backend,
                'device': input_v1.execution.physics_device,
                'profile_id': profile.profile_id,
                'execution_identity_sha256': input_v1.execution.identity_hash,
                'arm_tracking_method': arm_tracking_method,
            },
            'source_revision': {
                F04PositionCandidateInputV1: 'F04-versioned-usd-native-candidate-v1',
                F05NativePositionCandidateInputV1: 'F05-versioned-geophys-usd-native-v1',
                F05Dg02GeoPhysUsdCandidateInputV1: 'F05-DG02-source-preserving-geophys-usd-core-v1',
                F05Dg04IsaacNativeCandidateInputV1: 'F05-DG04-native-physx-mimic-core-v1',
            }[type(input_v1)],
            'source_sha256': {
                'source_closure': source.source_closure_digest,
                'kinematics_source': input_v1.kinematics_source_sha256,
                **({'arm_tracking_profile_source': arm_tracking_profile['profile_source_sha256']}
                   if arm_tracking_profile is not None else {}),
            },
        }

    def fixed_seed(seed):
        if type(seed) is not int or seed != input_v1.reset_plan.reset_sample.task_seed:
            raise ValueError('Position reset seed must match its fixed EpisodeResetPlan')
        return seed

    def evaluate(state, semantics):
        if type(input_v1) not in (
                F05Dg02GeoPhysUsdCandidateInputV1,
                F05Dg04IsaacNativeCandidateInputV1):
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

    action_schema = REFERENCE_POSE_ACTION_SCHEMA
    action_space_factory = reference_pose_action_space
    if physical_execution is not None:
        action_schema = {'schema_version': 'physical-control-actions-v1',
                         'controllers': [{'identity': item.identity,
                                          'shape': list(item.action_shape)}
                                         for item in physical_execution.controllers]}
        action_space_factory = physical_execution.action_space
    binding = ReferenceTaskBinding(
        position_control_binding=lambda _value: ControlBinding("panda-main/gripper", 0.08),
        build=build,
        classify_position_input=_versioned_position_candidate_kind,
        action_schema=action_schema, action_space_factory=action_space_factory,
        prepare_action=reference_pose_action,
        observation_space_factory=selected_reference_observation_spaces, observation_projection=build_selected_observation,
        reset_sample=lambda _artifact, _seed: input_v1.reset_plan.reset_sample,
        evaluate=evaluate,
        object_poses=tuple(
            (name, 'target') for name in sorted(input_v1.artifact.initialization.poses_world)
        ),
        external_actions=True, interval_mode='grouped', recorder_mode='execution',
        reset_seed=fixed_seed,
        physical_control_profile=(None if physical_execution is None else lambda _env: physical_execution),
        physical_observation_binding=(None if physical_execution is None else legacy_position_physical_observation_binding),
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
        versioned_position_input=input_v1,
    )


def build_position_candidate(workspace: Path | str, *, provider: str, horizon: int = 6000,
                             environment_type=SelectedReferenceEnv,
                             camera_observation_config=None, physical_profile=None,
                             task_probe_force_y_N=None):
    """Build one source-identified candidate through SelectedReferenceEnv's existing binding."""
    import importlib
    if task_probe_force_y_N is not None:
        import math
        if (physical_profile != 'panda-free-body-wrench-only-v1' or provider != 'mujoco'
                or type(task_probe_force_y_N) not in (int, float)
                or not math.isfinite(task_probe_force_y_N) or not -30. <= task_probe_force_y_N <= 30.):
            raise ValueError('probe Task force requires the MuJoCo body-only profile and finite [-30, 30] N')

    root = Path(workspace).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if physical_profile in ('panda-free-body-point-wrench-v1', 'panda-free-body-wrench-only-v1'):
        from task_env.artifacts import PoseWorld
        from .free_body_fixture import fixture_scene
        scene = fixture_scene()
    else:
        scene = _a05_scene()
    legacy, _ = _artifact_and_sample(scene)
    legacy = replace(
        legacy,
        artifact_id='phase-ii-c02b-position-servo-v1',
        task_id=POSITION_CANDIDATE_TASK_ID,
        artifact_version=POSITION_CANDIDATE_VERSION,
        timebase=Timebase(0.002, 5, 0.01),
    )
    if physical_profile in ('panda-fixed-frame-point-wrench-v1', 'panda-free-body-point-wrench-v1',
                            'panda-free-body-wrench-only-v1', 'panda-direct-effort-home-v1'):
        # A distinct Artifact makes the home reset explicit; it does not alter
        # the original A05 candidate or its source constraints and drives.
        home = (0.0, 0.0, 0.0, -1.57079, 0.0, 1.57079, -0.7853)
        positions = dict(legacy.initialization.joint_position)
        positions.update({f'panda-main/joint{i}': value for i, value in enumerate(home, 1)})
        positions.update({'panda-main/finger_joint1': 0.038, 'panda-main/finger_joint2': 0.038})
        legacy = replace(legacy, artifact_id='panda-fixed-frame-point-wrench-home-v1',
                         task_id='panda-fixed-frame-point-wrench-home', artifact_version='v1',
                         initialization=replace(legacy.initialization, joint_position=positions))
        if physical_profile == 'panda-direct-effort-home-v1':
            legacy = replace(legacy, artifact_id='panda-direct-effort-home-v1',
                             task_id='panda-direct-effort-home', artifact_version='v1')
    if physical_profile in ('panda-free-body-point-wrench-v1', 'panda-free-body-wrench-only-v1'):
        entities = tuple(replace(entity, kind='movable', geometry='source_asset',
                                 parameters_si={'mass_kg': 0.08})
                         if entity.semantic_id == 'probe' else entity for entity in legacy.world.entities)
        legacy = replace(legacy, artifact_id='panda-free-body-point-wrench-v1',
                         task_id='panda-free-body-point-wrench', artifact_version='v1',
                         world=replace(legacy.world, entities=entities),
                         initialization=replace(legacy.initialization,
                             poses_world={'probe/probe_body': PoseWorld((0., 0., 1.), (1., 0., 0., 0.))}),
                         semantics=replace(legacy.semantics, required_poses=tuple(
                             name for name in legacy.semantics.required_poses if name != 'probe/world')))
    task_source = replace(
        _task_source(scene), task_id=legacy.task_id, version=legacy.artifact_version,
    )
    artifact = compile_task_artifact_v1(task_source, scene, legacy)
    reset_plan = sample_episode_reset_plan(
        task_source, scene, artifact, task_seed=POSITION_CANDIDATE_SEED,
    )
    if physical_profile is None:
        source, imported, closure_digest, panda_digest, panda_file_count = _source_input(
            importlib.import_module('scene'), root / 'source-closure', scene, legacy,
        )
        if imported is None:
            raise ValueError('Position candidate source import evidence is incomplete')
    elif physical_profile in ('panda-direct-effort-v1', 'panda-direct-effort-wrench-v1',
                              'panda-direct-effort-object-wrench-v1', 'panda-split-direct-effort-v1',
                              'panda-fixed-frame-point-wrench-v1', 'panda-free-body-point-wrench-v1',
                              'panda-free-body-wrench-only-v1', 'panda-direct-effort-home-v1'):
        from .source import _physical_source_input
        mutator = None
        if physical_profile in ('panda-free-body-point-wrench-v1', 'panda-free-body-wrench-only-v1'):
            from .free_body_fixture import compose_fixture_xml
            mutator = compose_fixture_xml
        source, closure_digest, panda_digest, panda_file_count = _physical_source_input(
            root / 'source-closure', scene, legacy, xml_mutator=mutator)
    else:
        raise ValueError('unsupported physical control profile')
    if len(closure_digest) != 64 or len(panda_digest) != 64:
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
    physical_execution = None
    if physical_profile is not None:
        from .physical_profile import build_panda_direct_effort_execution
        target = {'panda-direct-effort-v1': None, 'panda-direct-effort-wrench-v1': 'hand',
                  'panda-direct-effort-object-wrench-v1': 'object', 'panda-split-direct-effort-v1': None,
                  'panda-fixed-frame-point-wrench-v1': 'hand',
                  'panda-free-body-point-wrench-v1': 'probe',
                  'panda-free-body-wrench-only-v1': 'probe',
                  'panda-direct-effort-home-v1': None}[physical_profile]
        physical_execution = build_panda_direct_effort_execution(
            scene, artifact, source, wrench_target=target, split=physical_profile == 'panda-split-direct-effort-v1',
            fixed_frame_point=physical_profile in ('panda-fixed-frame-point-wrench-v1',
                                                  'panda-free-body-point-wrench-v1',
                                                  'panda-free-body-wrench-only-v1'))
        if physical_profile == 'panda-free-body-wrench-only-v1':
            # This fixture exposes the already source-bound free probe wrench
            # without claiming Panda actuator channels.  Its distinct control
            # identity is recorded below with the other physical profiles.
            from task_env.runtime.sessions.physical_control import (
                PhysicalControlExecutionV1, compile_physical_control_binding,
            )
            from task_env.controllers.canonical.physical_controller import WrenchControllerV1
            binding = replace(physical_execution.compiled.binding, channels=())
            compiled = compile_physical_control_binding(scene, physical_execution.compiled.root,
                physical_execution.compiled.children, binding)
            controller = WrenchControllerV1(
                replace(physical_execution.controllers[-1].profile, composition='sum'), binding)
            physical_execution = PhysicalControlExecutionV1(compiled, (controller,), scene,
                physical_execution.joint_bindings, physical_execution.frame_bindings,
                physical_execution.requirements, physical_execution.generation)

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
                **({'position_physical_action': 'position-physical-action-v1'}
                   if physical_profile == 'panda-free-body-wrench-only-v1' else {}),
                **({'task_probe_force_y_N': task_probe_force_y_N} if task_probe_force_y_N is not None else {}),
                **({'physical_binding': physical_execution.compiled.binding.identity_hash,
                    'physical_controllers': [item.identity for item in physical_execution.controllers]}
                   if physical_execution is not None else {}),
            }),
            'resolved_configuration': {
                'provider': _provider, 'backend': 'cpu', 'profile_id': profile.profile_id,
                **({'task_probe_force_y_N': task_probe_force_y_N} if task_probe_force_y_N is not None else {}),
                **({'physical_profile': physical_profile,
                    'physical_binding': physical_execution.compiled.binding.identity_hash,
                    'physical_controllers': [item.identity for item in physical_execution.controllers]}
                   if physical_execution is not None else {}),
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

    action_schema = REFERENCE_POSE_ACTION_SCHEMA
    action_space_factory = reference_pose_action_space
    if physical_execution is not None:
        action_schema = {'schema_version': 'physical-control-actions-v1',
                         'controllers': [{'identity': item.identity, 'shape': list(item.action_shape)}
                                         for item in physical_execution.controllers]}
        action_space_factory = physical_execution.action_space
    if physical_profile == 'panda-free-body-wrench-only-v1':
        action_schema['position_physical_action'] = 'position-physical-action-v1'

    def task_probe_force(env):
        from task_env.controllers.canonical.physical_commands import ExternalComWrenchSumSegmentV1
        return (ExternalComWrenchSumSegmentV1('external-com-wrench-sum-segment-v1',
            'candidate-task-probe-writer-v1', 'candidate-task-probe-force-v1', 'probe/probe_body',
            0, env.artifact.timebase.control_substeps, (0., float(task_probe_force_y_N), 0.), (0., 0., 0.)),)

    binding = ReferenceTaskBinding(
        position_physical_mixed=physical_profile == 'panda-free-body-wrench-only-v1',
        task_com_wrench_factory=task_probe_force if task_probe_force_y_N is not None else None,
        position_control_binding=lambda _value: ControlBinding("panda-main/gripper", 0.08),
        build=build,
        action_schema=action_schema, action_space_factory=action_space_factory,
        prepare_action=reference_pose_action,
        observation_space_factory=selected_reference_observation_spaces, observation_projection=build_selected_observation,
        reset_sample=lambda _artifact, _seed: reset_plan.reset_sample,
        evaluate=lambda _state, _semantics: SimpleNamespace(
            reward=0.0, success=False, failure=False, metrics={},
        ),
        object_poses=(('square-peg-instance/peg1', 'target'),),
        external_actions=True,
        interval_mode='grouped',
        recorder_mode='execution',
        reset_seed=fixed_seed,
        physical_control_profile=(None if physical_execution is None else lambda _env: physical_execution),
        physical_observation_binding=(None if physical_execution is None else legacy_position_physical_observation_binding),
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
    'F04PositionCandidateInputV1',
    'F05NativePositionCandidateInputV1',
    'POSITION_CANDIDATE_SEED',
    'POSITION_CANDIDATE_TASK_ID', 'POSITION_CANDIDATE_VERSION',
    'build_position_candidate',
    'build_versioned_position_candidate',
]
