"""Task-owned construction for the bounded C02b Position candidate."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
import hashlib
import yaml

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
from task_env.environment.reference_binding import ReferenceTaskBinding
from task_env.environment.reference_env import SelectedReferenceEnv


POSITION_CANDIDATE_TASK_ID = 'phase-ii-c02b-position-servo'
POSITION_CANDIDATE_VERSION = 'candidate-v1'
POSITION_CANDIDATE_SEED = 31


def _dg02_r3_arm_profile():
    """Read the existing NutAssembly R3 profile as configuration, not task logic."""
    path = Path(__file__).resolve().parents[1] / 'nut_assembly' / 'config.yaml'
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    controller = data.get('recipe', {}).get('controller', {})
    if controller.get('implementation') != 'ProductionCanonicalPandaControllerR3':
        raise ValueError('DG02 R3 profile source no longer selects the production R3 owner')
    profile = controller.get('dynamic_profile')
    if not isinstance(profile, dict):
        raise ValueError('DG02 requires the existing NutAssembly R3 dynamic profile')
    return {**profile, 'profile_source_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


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
                                       controller_config=None):
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

    binding = ReferenceTaskBinding(
        position_control_binding=lambda _value: ControlBinding("panda-main/gripper", 0.08),
        build=build,
        classify_position_input=_versioned_position_candidate_kind,
        action_schema=REFERENCE_POSE_ACTION_SCHEMA, action_space_factory=reference_pose_action_space,
        prepare_action=reference_pose_action,
        observation_space_factory=selected_reference_observation_spaces, observation_projection=build_selected_observation,
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
        versioned_position_input=input_v1,
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
        position_control_binding=lambda _value: ControlBinding("panda-main/gripper", 0.08),
        build=build,
        action_schema=REFERENCE_POSE_ACTION_SCHEMA, action_space_factory=reference_pose_action_space,
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
