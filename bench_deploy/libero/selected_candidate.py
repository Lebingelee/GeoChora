"""Task-local construction recipe for the R07c LIBERO mixed diagnostic.

The candidate owns only the fixed Artifact/source/Controller/reset binding.
SelectedReferenceEnv and RuntimeSession retain lifecycle, admission, native
control, observation, and recording ownership.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from task_env.artifacts import (
    ActionIntent, EntityDefinition, InitializationContract, RequiredCapabilitySet,
    SemanticDefinition, TaskArtifact, Timebase, UniformDimension, WorldDefinition,
)
from task_env.assembly.source import TaskSceneSource
from task_env.controllers.canonical.contracts import digest
from task_env.environment.configuration import resolve_env_config
from task_env.runtime.sessions.source import (
    ExecutionSourceReceiptV1, RuntimeSource, source_asset_bytes,
)
from task_env.tasks.reference_env import ReferenceTaskBinding, SelectedReferenceEnv

from .controller import LiberoMixedControllerV1
from .evaluation import PILOT_TASK_UID, evaluate_on_bowl_plate_v1
from .init_state import (
    INIT_SHA256, PILOT_SOURCE_MANIFEST_SHA256, decode_pruned_init_bytes,
    init_layout_v1, sample_libero_normal_reset_v1,
)


PROFILE_ID = 'libero-spatial-bowl-to-plate-mixed-v1'
CONTROLLER_PROFILE_ID = 'libero-spatial-bowl-to-plate-joint-space-pd-v1'
ARTIFACT_ID = 'libero-spatial-bowl-to-plate-v1/mixed-v1'
SCENE_ID = 'libero-spatial-bowl-to-plate-composed-mjcf-v1'
SOURCE_MANIFEST_PATH = Path(__file__).resolve().parents[2] / 'asset/benchmarks/libero/source_manifest.json'
DEFAULT_OUTPUT_ROOT = Path(
    '/home/lly/Program_Files/Geochora/workspace/maintenance/'
    'phase_ii_01_sol_luna_handoff_20261023_001/r07c_diag_d01_001'
)
DEFAULT_INSTALL_ROOT = Path(
    '/home/lly/Program_Files/Geochora/workspace/maintenance/'
    'phase_ii_01_sol_luna_handoff_20261023_001/r07b_pilot_001_install/final_001'
)
INIT_RELATIVE_PATH = (
    'upstream/libero/libero/libero/init_files/libero_spatial/'
    'pick_up_the_black_bowl_between_the_plate_and_the_ramekin_and_place_it_on_the_plate.pruned_init'
)
TASK_ID = PILOT_TASK_UID


def _artifact(init_bytes: bytes) -> TaskArtifact:
    decoded = decode_pruned_init_bytes(init_bytes)
    layout = init_layout_v1()
    qpos = dict(zip(
        layout['qpos_names'],
        decoded.row(0)[layout['qpos_slice'][0]:layout['qpos_slice'][1]],
        strict=True,
    ))
    joints = (
        *(f'joint{i}' for i in range(1, 8)), 'finger_joint1', 'finger_joint2',
        'wooden_cabinet_1.top_level', 'wooden_cabinet_1.middle_level',
        'wooden_cabinet_1.bottom_level', 'flat_stove_1.button',
    )
    entities = (
        EntityDefinition(
            'panda-v1', 'embodiment', 'asset:libero-mounted-panda-v1',
            ('panda-v1/ee',), joints[:9], 'pinned_mounted_panda_mjcf',
            'source-authored-collision', {},
        ),
        EntityDefinition('main_table', 'scene', 'asset:libero-tabletop-v1', (), (),
                         'source-authored-tabletop', 'source-authored-collision', {}),
        EntityDefinition('akita_black_bowl_1', 'movable', 'asset:libero-akita-black-bowl-v1',
                         (), (), 'source-authored-mesh', 'source-authored-collision', {}),
        EntityDefinition('akita_black_bowl_2', 'movable', 'asset:libero-akita-black-bowl-v1',
                         (), (), 'source-authored-mesh', 'source-authored-collision', {}),
        EntityDefinition('cookies_1', 'movable', 'asset:libero-cookies-v1', (), (),
                         'source-authored-mesh', 'source-authored-collision', {}),
        EntityDefinition('glazed_rim_porcelain_ramekin_1', 'movable',
                         'asset:libero-glazed-rim-porcelain-ramekin-v1', (), (),
                         'source-authored-mesh', 'source-authored-collision', {}),
        EntityDefinition('plate_1', 'movable', 'asset:libero-plate-v1', (), (),
                         'source-authored-mesh', 'source-authored-collision', {}),
        EntityDefinition('wooden_cabinet_1', 'static', 'asset:libero-wooden-cabinet-v1', (),
                         joints[9:12], 'source-authored-articulated-fixture',
                         'source-authored-collision', {}),
        EntityDefinition('flat_stove_1', 'static', 'asset:libero-flat-stove-v1', (),
                         (joints[12],), 'source-authored-articulated-fixture',
                         'source-authored-collision', {}),
    )
    from task_env.runtime.sessions.api import CAPABILITIES

    artifact = TaskArtifact(
        'task-artifact-v0', ARTIFACT_ID, TASK_ID, 'diagnostic-v1',
        WorldDefinition(
            'world-v0', 'SI_right_handed_z_up_wxyz', entities,
            ActionIntent('absolute_joint', None, 'none', 'arm_joint_position_and_gripper'),
            ('canonical-state-v0', 'task-contact-summary-v2'), (),
        ),
        InitializationContract(
            'initialization-v0', {}, {name: float(qpos[name]) for name in joints}, (),
            'restore_source_named_pruned_init_row', 'pinned_libero_normal_reset_v1', 0,
        ),
        SemanticDefinition(
            'semantics-v0', 'libero_on_bowl_plate_v1',
            ('panda-v1/ee', 'main_table', 'akita_black_bowl_1', 'plate_1'),
            joints, {'xy_threshold_m': 0.03},
            'libero_on_bowl_plate_geom_contact_and_xy_lt_0_03m_v1',
        ),
        Timebase(0.002, 25, 0.05),
        RequiredCapabilitySet(tuple(CAPABILITIES) + ('contact_detection',)),
    )
    artifact.validate()
    if tuple(artifact.initialization.joint_position) != tuple(joints):
        raise ValueError('LIBERO initialization field order differs from the source row projection')
    return artifact


def _build_fixed_source(*, xml_path: Path, xml_bytes_override: bytes | None,
                        install_root: Path, composition_plan_path: Path,
                        init_path: Path, horizon: int):
    xml_bytes = Path(xml_path).read_bytes() if xml_bytes_override is None else bytes(xml_bytes_override)
    plan_bytes = Path(composition_plan_path).read_bytes()
    plan = json.loads(plan_bytes)
    if plan.get('output', {}).get('status') != 'SOURCE_MJCF_COMPOSED_NOT_NATIVE_COMPILED':
        raise ValueError('R07c source plan must remain explicitly source-composed and not precompiled')
    expected_xml_sha = plan['output']['composed_mjcf_sha256']
    if hashlib.sha256(xml_bytes).hexdigest() != expected_xml_sha:
        raise ValueError('candidate MJCF differs from its frozen composition plan')
    install_root = Path(install_root).resolve(strict=True)
    init_path = Path(init_path).resolve(strict=True)
    init_bytes = init_path.read_bytes()
    if hashlib.sha256(init_bytes).hexdigest() != INIT_SHA256:
        raise ValueError('candidate .pruned_init differs from the frozen source bytes')
    manifest_bytes = SOURCE_MANIFEST_PATH.read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != PILOT_SOURCE_MANIFEST_SHA256:
        raise ValueError('tracked LIBERO source manifest differs from the frozen pilot identity')
    source_manifest = json.loads(manifest_bytes)
    artifact = _artifact(init_bytes)
    controller = LiberoMixedControllerV1()
    if controller.profile_id != CONTROLLER_PROFILE_ID:
        raise ValueError('LIBERO task-local controller profile changed')

    importer_xml = xml_bytes
    external_assets = source_asset_bytes(install_root, importer_xml.decode('utf-8'))
    closure = {'canonical-source.xml': xml_bytes, **external_assets}
    source_receipt = ExecutionSourceReceiptV1.create(
        source_id=f'libero-spatial-pilot-v1:{expected_xml_sha}',
        canonical_xml=xml_bytes, importer_xml=importer_xml, closure_files=closure,
        expected_canonical_xml_sha256=expected_xml_sha,
    )
    scene_source = TaskSceneSource(
        xml=importer_xml.decode('utf-8'), base_dir=source_receipt.snapshot_root,
        source_id=source_receipt.source_id,
        diagnostics=('R07c D01 immutable importer snapshot; physical attributes preserved from composed MJCF',),
    )
    semantic_bodies = dict(plan['semantic_to_compiled_body_names'])
    expected_bodies = {
        'main_table': 'main_table',
        'akita_black_bowl_1': 'akita_black_bowl_1_main',
        'akita_black_bowl_2': 'akita_black_bowl_2_main',
        'cookies_1': 'cookies_1_main',
        'glazed_rim_porcelain_ramekin_1': 'glazed_rim_porcelain_ramekin_1_main',
        'plate_1': 'plate_1_main',
        'wooden_cabinet_1': 'wooden_cabinet_1_main',
        'flat_stove_1': 'flat_stove_1_main',
    }
    if semantic_bodies != expected_bodies:
        source_receipt.close()
        raise ValueError('composition plan semantic body map differs from the fixed pilot allowlist')
    groups = plan['composition_receipt']['contact_geom_name_transform']['groups']
    expected_group_names = set(expected_bodies) - {'main_table'}
    if set(groups) != expected_group_names:
        source_receipt.close()
        raise ValueError('composition plan contact geom groups differ from the fixed pilot allowlist')
    config = resolve_env_config(
        task_uid=TASK_ID, scene_uid=SCENE_ID,
        runtime={
            'backend': 'cpu', 'physics_dt': 0.002, 'control_substeps': 25,
            'integrator': 'implicitfast', 'prewarm': False,
        },
        render={'camera_obs': False}, episode={'horizon': horizon, 'ignore_done': False},
        success_definition='diagnostic LIBERO On(bowl,plate) source predicate',
    )
    joints = {
        **{f'joint{i}': f'robot0_joint{i}' for i in range(1, 8)},
        'finger_joint1': 'gripper0_finger_joint1',
        'finger_joint2': 'gripper0_finger_joint2',
        'wooden_cabinet_1.top_level': 'wooden_cabinet_1_top_level',
        'wooden_cabinet_1.middle_level': 'wooden_cabinet_1_middle_level',
        'wooden_cabinet_1.bottom_level': 'wooden_cabinet_1_bottom_level',
        'flat_stove_1.button': 'flat_stove_1_button',
    }
    free_joints = {
        name: f'{name}_joint0' for name in (
            'akita_black_bowl_1', 'akita_black_bowl_2', 'cookies_1',
            'glazed_rim_porcelain_ramekin_1', 'plate_1',
        )
    }
    source = RuntimeSource(
        task_artifact_hash=artifact.identity_hash,
        scene_source=scene_source,
        joints=joints,
        bodies=semantic_bodies,
        frames={'panda-v1/ee': 'gripper0_grip_site'},
        free_joints=free_joints,
        joint_targets={}, open_actuators=(),
        composition=plan['composition_receipt'], config=config, scene=None,
        agents=(), objects=tuple(key for key in expected_bodies if key != 'main_table'),
        source_closure_digest=source_receipt.source_closure_digest,
        execution_source_receipt=source_receipt,
        torque_actuators={f'joint{i}': f'robot0_torq_j{i}' for i in range(1, 8)},
        position_actuators={
            'finger_joint1': 'gripper0_gripper_finger_joint1',
            'finger_joint2': 'gripper0_gripper_finger_joint2',
        },
        actuator_units={
            **{f'robot0_torq_j{i}': 'N*m' for i in range(1, 8)},
            'gripper0_gripper_finger_joint1': 'm',
            'gripper0_gripper_finger_joint2': 'm',
        },
        fixture_bodies=('wooden_cabinet_1', 'flat_stove_1'),
        contact_geom_groups={key: tuple(value) for key, value in groups.items()},
        mixed_controller_profile_id=controller.profile_id,
        mixed_controller_identity=controller.identity,
    )
    return {
        'artifact': artifact, 'source': source, 'controller': controller,
        'selected_controller_kind': 'mixed_actuator_v1', 'solution': None,
        'source_manifest_sha256': PILOT_SOURCE_MANIFEST_SHA256,
        'source_revision': 'LIBERO:8f1084e3132a39270c3a13ebe37270a43ece2a01;'
                           'robosuite:fbee5844ff5632f5b5698e204ec5357ca50be0df',
        'source_sha256': {
            'composed_candidate_xml': expected_xml_sha,
            'composition_plan': hashlib.sha256(plan_bytes).hexdigest(),
            'source_manifest': hashlib.sha256(manifest_bytes).hexdigest(),
            'pruned_init': hashlib.sha256(init_bytes).hexdigest(),
            'source_closure_digest': source_receipt.source_closure_digest,
        },
        'construction_id': digest({
            'schema_version': 'libero-selected-construction-v1',
            'artifact_identity_hash': artifact.identity_hash,
            'source_id': source.scene_source.source_id,
            'source_closure_digest': source.source_closure_digest,
            'controller_identity': controller.identity,
        }),
        'resolved_configuration': asdict(config),
        'reset_realizations': {},
        'init_bytes': init_bytes,
        'source_manifest': source_manifest,
        'install_root': install_root,
    }


def build_libero_selected_candidate(
    *, xml_path: Path = DEFAULT_OUTPUT_ROOT / 'source/composed_candidate.xml',
    xml: str | bytes | None = None,
    composed_mjcf_sha256: str | None = None,
    composition_plan_path: Path = DEFAULT_OUTPUT_ROOT / 'source/composition_plan.json',
    install_root: Path = DEFAULT_INSTALL_ROOT,
    init_path: Path | None = None,
    horizon: int = 64,
):
    """Construct the fixed internal SelectedReferenceEnv diagnostic candidate."""
    if type(horizon) is not int or not 1 <= horizon <= 64:
        raise ValueError('R07c D01 candidate horizon must be in [1,64]')
    install_root = Path(install_root).resolve(strict=True)
    if init_path is None:
        init_path = install_root / INIT_RELATIVE_PATH
    value_cache = {}
    reset_receipts = {}

    def build_value(provider, backend):
        if (provider, backend) != ('mujoco', 'cpu'):
            raise ValueError('R07c D01 candidate is limited to MuJoCo CPU')
        if 'value' not in value_cache:
            xml_bytes = None if xml is None else (xml.encode('utf-8') if isinstance(xml, str) else bytes(xml))
            value_cache['value'] = _build_fixed_source(
                xml_path=Path(xml_path), xml_bytes_override=xml_bytes, install_root=install_root,
                composition_plan_path=Path(composition_plan_path),
                init_path=Path(init_path), horizon=horizon,
            )
            if (composed_mjcf_sha256 is not None
                    and value_cache['value']['source_sha256']['composed_candidate_xml'] != composed_mjcf_sha256):
                value_cache['value']['source'].execution_source_receipt.close()
                value_cache.clear()
                raise ValueError('caller composed MJCF SHA differs from the frozen composition plan')
        value = dict(value_cache['value'])
        value['controller'] = LiberoMixedControllerV1()
        value['reset_realizations'] = reset_receipts
        return value

    def reset_with_options(artifact, seed, options, source):
        if artifact.identity_hash != value_cache['value']['artifact'].identity_hash:
            raise ValueError('LIBERO reset Artifact differs from its source candidate')
        reset_plan = options.get('reset_plan_v1')
        if reset_plan is not None:
            from task_env.artifacts import ResetPlanV1

            if type(reset_plan) is not ResetPlanV1:
                raise TypeError('LIBERO candidate reset requires the public ResetPlanV1 value')
            reset_plan.validate()
            reset_sample = reset_plan.reset_sample
            if (reset_plan.purpose != 'diagnostic_contact_endpoint'
                    or reset_sample.task_seed != seed
                    or reset_sample.task_artifact_hash != artifact.identity_hash
                    or reset_sample.source_id != source.scene_source.source_id
                    or reset_sample.source_closure_digest != source.source_closure_digest):
                raise ValueError('LIBERO ResetPlanV1 does not match this task, seed, or immutable source')
            receipt = {
                'schema_version': 'libero-diagnostic-reset-plan-realization-v1',
                'purpose': reset_plan.purpose,
                'reset_plan_identity_sha256': reset_plan.identity_hash,
                'init_row_index': reset_sample.init_row_index,
                'init_row_sha256': reset_sample.init_row_sha256,
                'sampler_id': reset_sample.sampler_id,
                'sampler_version': reset_sample.sampler_version,
                'task_seed': reset_sample.task_seed,
                'source_manifest_sha256': PILOT_SOURCE_MANIFEST_SHA256,
                'reset_sample_id': reset_sample.sample_id,
            }
            reset_receipts[reset_sample.sample_id] = receipt
            return reset_sample
        reset_sample, receipt = sample_libero_normal_reset_v1(
            init_bytes=value_cache['value']['init_bytes'],
            install_root=install_root,
            source_manifest=value_cache['value']['source_manifest'],
            task_artifact_hash=artifact.identity_hash,
            source_id=source.scene_source.source_id,
            source_closure_digest=source.source_closure_digest,
            task_seed=seed,
            init_row_index=options.get('init_row_index', 0),
        )
        reset_receipts[reset_sample.sample_id] = receipt
        return reset_sample

    def evaluate(evidence, _semantics):
        return evaluate_on_bowl_plate_v1(
            evidence, expected_source_manifest_sha256=PILOT_SOURCE_MANIFEST_SHA256,
        )

    def validate_compiled_session(session, value):
        receipt = session.compiled_layout_receipt
        dimensions = receipt['dimensions']
        if (dimensions.get('nq'), dimensions.get('nv'), dimensions.get('na'), dimensions.get('nu')) != (
                48, 43, 0, 9):
            raise ValueError('compiled LIBERO dimensions differ from the locked source layout')
        if set(receipt['named_joint_addresses']) != set(value['source'].joints):
            raise ValueError('compiled LIBERO named scalar joints differ from RuntimeSource')
        if set(receipt['named_free_joint_addresses']) != set(value['source'].free_joints):
            raise ValueError('compiled LIBERO named free joints differ from RuntimeSource')
        if set(receipt['named_torque_actuator_ids']) != set(value['source'].torque_actuators):
            raise ValueError('compiled LIBERO torque actuator map differs from RuntimeSource')
        if set(receipt['named_position_actuator_ids']) != set(value['source'].position_actuators):
            raise ValueError('compiled LIBERO finger actuator map differs from RuntimeSource')
        if (receipt['source_id'] != value['source'].scene_source.source_id
                or receipt['source_closure_digest'] != value['source'].source_closure_digest):
            raise ValueError('compiled LIBERO layout receipt is not source-bound')
        return {
            'schema_version': 'r07c-d01-pre-reset-compiled-validation-v1',
            'runtime_identity': session.runtime_identity,
            'compiled_layout': receipt,
            'reset_not_yet_applied': True,
        }

    binding = ReferenceTaskBinding(
        build=lambda provider: build_value(provider, 'cpu'),
        reset_sample=lambda artifact, seed: reset_with_options(
            artifact, seed, {'init_row_index': 0}, value_cache['value']['source'],
        ),
        evaluate=evaluate,
        object_poses=(('akita_black_bowl_1', 'bowl'), ('plate_1', 'plate')),
        external_actions=True, interval_mode='grouped', recorder_mode='canonical',
        reset_seed=lambda seed: seed,
        runtime_episode_identity=True,
        build_libero_mixed_profile=build_value,
        reset_sample_with_options=reset_with_options,
        mixed_control_profile_id=PROFILE_ID,
        pre_reset_session_validator=validate_compiled_session,
    )
    env = SelectedReferenceEnv.from_libero_diagnostic_candidate(
        binding, provider='mujoco', backend='cpu', horizon=horizon,
    )
    # The shared sample owner retains reset and source facts for the public
    # reset receipt; it is private recipe state, not a second runtime owner.
    env.value['reset_realizations'] = reset_receipts
    return env


__all__ = ['build_libero_selected_candidate']
