"""Task-local construction recipe for the R07c LIBERO mixed diagnostic.

The candidate owns only the fixed Artifact/source/Controller/reset binding.
SelectedReferenceEnv and RuntimeSession retain lifecycle, admission, native
control, observation, and recording ownership.
"""
from __future__ import annotations

from dataclasses import asdict
from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
import numpy as np
from gymnasium.spaces import Box, Dict

from task_env.artifacts import (
    ActionIntent, EntityDefinition, InitializationContract, RequiredCapabilitySet,
    SemanticDefinition, TaskArtifact, Timebase, UniformDimension, WorldDefinition,
)
from task_env.assembly.source import TaskSceneSource
from task_env.controllers.canonical.contracts import (
    ControlGroupActionV1, MixedActuatorChannelV1, MixedActuatorPlanV1,
    StructuredActionRequestV1, digest,
)
from task_env.environment.configuration import resolve_env_config
from task_env.runtime.sessions.source import (
    ExecutionSourceReceiptV1, RuntimeSource, source_asset_bytes,
)
from task_env.tasks.reference_env import ReferenceTaskBinding, SelectedReferenceEnv

from .controller import (
    LiberoMixedControllerV1, LiberoMixedControllerV2, LiberoMixedControllerV3,
    LiberoMixedControllerV4,
)
from .evaluation import (
    PILOT_TASK_UID, evaluate_on_bowl_plate_v1, observe_selected_reference_v1,
)
from .init_state import (
    INIT_SHA256, PILOT_SOURCE_MANIFEST_SHA256, decode_pruned_init_bytes,
    init_layout_v1, sample_libero_normal_reset_v1,
)


PROFILE_ID = 'libero-spatial-bowl-to-plate-mixed-v1'
CONTROLLER_PROFILE_ID = 'libero-spatial-bowl-to-plate-joint-space-pd-v6'


def _controller_hold_policy(controller):
    operational = getattr(controller, 'operational_config', None)
    if operational is not None:
        return operational.hold_policy
    return controller.config.hold_policy
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


def _artifact(init_bytes: bytes, *, solution_profile: bool = False) -> TaskArtifact:
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
        'task-artifact-v0',
        ARTIFACT_ID if not solution_profile else ARTIFACT_ID + '/solution-v4',
        TASK_ID, 'diagnostic-v1' if not solution_profile else 'diagnostic-solution-v4',
        WorldDefinition(
            'world-v0', 'SI_right_handed_z_up_wxyz', entities,
            ActionIntent(
                'absolute_pose' if solution_profile else 'absolute_joint',
                'world' if solution_profile else None,
                'quaternion_wxyz' if solution_profile else 'none',
                'arm_joint_position_and_gripper',
            ),
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
                        init_path: Path, horizon: int, solution_profile: bool = False):
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
    artifact = _artifact(init_bytes, solution_profile=solution_profile)

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
        diagnostics=(
            ('R07c D01 immutable importer snapshot; physical attributes preserved from composed MJCF',)
            if not solution_profile else
            ('R07 v2.1.0 task #1 immutable importer snapshot; physical attributes preserved from composed MJCF',)
        ),
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
    bound_bodies = dict(semantic_bodies)
    groups = plan['composition_receipt']['contact_geom_name_transform']['groups']
    contact_geom_groups = {key: tuple(value) for key, value in groups.items()}
    if solution_profile:
        # Keep the public finger groups aligned with all source-authored
        # collidable parts of each finger. Counting only the pads misses valid
        # rim contacts made by the Panda finger collision meshes.
        bound_bodies.update({
            'panda-v1/finger-left': 'gripper0_leftfinger',
            'panda-v1/finger-right': 'gripper0_rightfinger',
        })
        contact_geom_groups.update({
            'panda-v1/finger-left': (
                'gripper0_finger1_collision', 'gripper0_finger1_pad_collision',
            ),
            'panda-v1/finger-right': (
                'gripper0_finger2_collision', 'gripper0_finger2_pad_collision',
            ),
        })
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
        success_definition=(
            'diagnostic LIBERO On(bowl,plate) source predicate'
            if not solution_profile else
            'pinned LIBERO On(akita_black_bowl_1,plate_1) task success and caller-owned Solution completion'
        ),
    )
    arm_resolver = None
    if solution_profile:
        from task_env.controllers.canonical import CanonicalPandaController, PandaKinematics
        from task_env.controllers.canonical.kinematics import derive_panda_tcp_profile_v2
        tcp_profile = derive_panda_tcp_profile_v2(
            xml_bytes, tcp_id='libero-mounted-panda-v1/gripper0-grip-site-v1',
            hand_frame_id='robot0_right_hand', site_name='gripper0_grip_site',
        )
        arm_kinematics = PandaKinematics(
            xml_bytes, tcp_profile=tcp_profile, native_prefix='robot0_',
            base_body_id='robot0_link0',
        )
        arm_resolver = CanonicalPandaController(
            arm_kinematics, artifact_hash=artifact.identity_hash, config=config.action,
        )
    controller = (
        LiberoMixedControllerV4(
            arm_resolver_identity=arm_resolver.iterative_resolution_identity_v1(),
        )
        if solution_profile else LiberoMixedControllerV1()
    )
    expected_controller_profile = (
        LiberoMixedControllerV4.profile_id if solution_profile else CONTROLLER_PROFILE_ID
    )
    if controller.profile_id != expected_controller_profile:
        raise ValueError('LIBERO task-local controller profile changed')
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
    torque_bindings = {f'joint{i}': f'robot0_torq_j{i}' for i in range(1, 8)}
    position_bindings = {
        'finger_joint1': 'gripper0_gripper_finger_joint1',
        'finger_joint2': 'gripper0_gripper_finger_joint2',
    }
    controller_limits = controller.identity_mapping()['torque_limits_Nm']
    mixed_plan = MixedActuatorPlanV1(
        'mixed-actuator-plan-v1', artifact.identity_hash, scene_source.source_id,
        source_receipt.source_closure_digest, controller.identity,
        tuple([
            MixedActuatorChannelV1(
                semantic, actuator, joints[semantic], 'joint_torque', 'N*m',
                (-float(controller_limits[semantic]), float(controller_limits[semantic])),
            ) for semantic, actuator in torque_bindings.items()
        ] + [
            MixedActuatorChannelV1(
                'finger_joint1', position_bindings['finger_joint1'], joints['finger_joint1'],
                'joint_position', 'm', (0.0, 0.04),
            ),
            MixedActuatorChannelV1(
                'finger_joint2', position_bindings['finger_joint2'], joints['finger_joint2'],
                'joint_position', 'm', (-0.04, 0.0),
            ),
        ]),
    )
    source = RuntimeSource(
        task_artifact_hash=artifact.identity_hash,
        scene_source=scene_source,
        joints=joints,
        bodies=bound_bodies,
        frames={'panda-v1/ee': 'gripper0_grip_site'},
        free_joints=free_joints,
        joint_targets={}, open_actuators=(),
        composition=plan['composition_receipt'], config=config, scene=None,
        agents=(), objects=tuple(key for key in expected_bodies if key != 'main_table'),
        source_closure_digest=source_receipt.source_closure_digest,
        execution_source_receipt=source_receipt,
        torque_actuators=torque_bindings,
        position_actuators=position_bindings,
        actuator_units={
            **{f'robot0_torq_j{i}': 'N*m' for i in range(1, 8)},
            'gripper0_gripper_finger_joint1': 'm',
            'gripper0_gripper_finger_joint2': 'm',
        },
        fixture_bodies=('wooden_cabinet_1', 'flat_stove_1'),
        contact_geom_groups=contact_geom_groups,
        mixed_actuator_plan=mixed_plan,
    )
    controller.plan_identity_hash = mixed_plan.identity_hash
    solution_identity = None
    if solution_profile:
        from .solution import solution_identity_v5
        solution_identity = solution_identity_v5(
            expected_xml_sha, source_receipt.source_closure_digest,
            arm_resolver_identity=arm_resolver.iterative_resolution_identity_v1(),
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
        'solution_identity': solution_identity,
        'arm_resolver': arm_resolver,
        'source_xml_bytes': xml_bytes,
        'solution_profile': bool(solution_profile),
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
    _solution_profile: bool = False,
):
    """Construct the fixed LIBERO candidate through the existing Core route.

    The default retains the frozen D01 diagnostic envelope. The task-owned
    solution wrapper below selects the separately versioned full Solution
    profile and its bounded horizon.
    """
    if type(_solution_profile) is not bool:
        raise TypeError('internal LIBERO Solution profile selector must be bool')
    maximum_horizon = 1000 if _solution_profile else 64
    if type(horizon) is not int or not 1 <= horizon <= maximum_horizon:
        raise ValueError(f'LIBERO candidate horizon must be in [1,{maximum_horizon}]')
    install_root = Path(install_root).resolve(strict=True)
    if init_path is None:
        init_path = install_root / INIT_RELATIVE_PATH
    value_cache = {}
    reset_receipts = {}
    source_gravity_model_ref = {'model': None}
    source_gravity_model_resources = []
    source_resource_close_state = {'attempted': False, 'receipt': None, 'error': None}
    env_holder = {}

    def bind_source_gravity_model(model):
        if not _solution_profile:
            raise RuntimeError('source gravity feed-forward is available only on the task Solution profile')
        # Register ownership before validating/binding. If a caller supplies a
        # source-mismatched model, the binding error remains primary while the
        # ordinary Env.close() path can still release the newly created helper.
        if not callable(getattr(model, 'close', None)):
            raise TypeError('task Solution source model must expose a close operation')
        if all(existing is not model for existing in source_gravity_model_resources):
            source_gravity_model_resources.append(model)
        existing = source_gravity_model_ref['model']
        if existing is None:
            source_gravity_model_ref['model'] = model
        elif existing is not model:
            raise RuntimeError('task Solution source gravity model may be bound only once')
        source = value_cache.get('value')
        if not isinstance(source, dict):
            raise RuntimeError('task Solution source identity must be built before binding gravity feed-forward')
        if (getattr(model, 'profile_id', None) != 'libero-source-mjcf-gravity-bias-v1'
                or getattr(model, 'source_xml_sha256', None)
                != source['source_sha256']['composed_candidate_xml']
                or getattr(model, 'source_closure_digest', None)
                != source['source_sha256']['source_closure_digest']
                or not callable(getattr(model, 'gravity_torque', None))
                or (_solution_profile
                    and not callable(getattr(model, 'operational_space_state_v1', None)))):
            raise ValueError('task Solution gravity model differs from its selected source identity')
        live_env = env_holder.get('env')
        if live_env is not None and live_env.controller.gravity_bias_model is None:
            live_env.controller.set_source_gravity_model(
                model,
                source_xml_sha256=source['source_sha256']['composed_candidate_xml'],
                source_closure_digest=source['source_sha256']['source_closure_digest'],
            )
        elif (live_env is not None
              and live_env.controller.gravity_bias_model is not model):
            raise RuntimeError('task Solution mixed Controller already owns another gravity model')

    def close_task_resources():
        """Release candidate-owned source helpers once through the Env lifecycle."""
        state = source_resource_close_state
        if state['attempted']:
            if state['error'] is not None:
                raise state['error']
            return dict(state['receipt'])
        state['attempted'] = True
        live_env = env_holder.get('env')
        controller = None if live_env is None else live_env.controller
        receipts = []
        first_error = None
        for model in source_gravity_model_resources:
            try:
                if controller is not None and getattr(controller, 'gravity_bias_model', None) is model:
                    receipt = controller.close_resources()
                elif getattr(model, 'closed', False):
                    # A task-local caller may have explicitly closed the
                    # helper already; do not invoke its single-use close twice.
                    receipt = {
                        'schema_version': 'libero-source-gravity-model-close-v1',
                        'profile_id': getattr(model, 'profile_id', None),
                        'model_identity_sha256': getattr(model, 'model_identity_sha256', None),
                        'source_xml_sha256': getattr(model, 'source_xml_sha256', None),
                        'source_closure_digest': getattr(model, 'source_closure_digest', None),
                        'model_created': True, 'closed': True,
                        'model_released': True, 'data_released': True,
                        'close_receipt_recovered': False,
                    }
                else:
                    receipt = model.close()
                receipts.append(receipt)
            except BaseException as error:
                if first_error is None:
                    first_error = error
                else:
                    first_error.add_note(
                        f'another task source helper close failed: {type(error).__name__}: {error}'
                    )
        source_gravity_model_ref['model'] = None
        if first_error is not None:
            state['error'] = first_error
            raise first_error
        if len(receipts) == 1:
            state['receipt'] = receipts[0]
        else:
            state['receipt'] = {
                'schema_version': 'selected-task-resources-close-v1',
                'closed': True,
                'resource_count': len(receipts),
                'resources': receipts,
            }
        return dict(state['receipt'])

    def build_value(provider, backend):
        if (provider, backend) != ('mujoco', 'cpu'):
            route = 'R07 v2.1.0 task #1 Solution candidate' if _solution_profile else 'R07c D01 candidate'
            raise ValueError(f'{route} is limited to MuJoCo CPU')
        if 'value' not in value_cache:
            xml_bytes = None if xml is None else (xml.encode('utf-8') if isinstance(xml, str) else bytes(xml))
            value_cache['value'] = _build_fixed_source(
                xml_path=Path(xml_path), xml_bytes_override=xml_bytes, install_root=install_root,
                composition_plan_path=Path(composition_plan_path),
                init_path=Path(init_path), horizon=horizon,
                solution_profile=_solution_profile,
            )
            if (composed_mjcf_sha256 is not None
                    and value_cache['value']['source_sha256']['composed_candidate_xml'] != composed_mjcf_sha256):
                value_cache['value']['source'].execution_source_receipt.close()
                value_cache.clear()
                raise ValueError('caller composed MJCF SHA differs from the frozen composition plan')
        value = dict(value_cache['value'])
        value['controller'] = (
            LiberoMixedControllerV4(
                arm_resolver_identity=value['arm_resolver'].iterative_resolution_identity_v1(),
            ) if _solution_profile else LiberoMixedControllerV1()
        )
        value['controller'].plan_identity_hash = value['source'].mixed_actuator_plan.identity_hash
        value['reset_realizations'] = reset_receipts
        if _solution_profile:
            value['bind_source_gravity_model'] = bind_source_gravity_model
            value['close_task_resources'] = close_task_resources
            model = source_gravity_model_ref['model']
            if model is not None:
                value['controller'].set_source_gravity_model(
                    model,
                    source_xml_sha256=value['source_sha256']['composed_candidate_xml'],
                    source_closure_digest=value['source_sha256']['source_closure_digest'],
                )
        if _solution_profile:
            components = (
                'world_x_m', 'world_y_m', 'world_z_m',
                'world_qw', 'world_qx', 'world_qy', 'world_qz', 'gripper_normalized',
            )
            value['action_schema'] = {
                'schema_id': 'libero-world-pose-wxyz-absolute-v1', 'schema_version': 1,
                'controller_kind': 'absolute_pose', 'reference': 'world',
                'rotation_representation': 'quaternion_wxyz',
                'dimension': len(components), 'components': components,
            }
        else:
            components = tuple([*(f'joint{i}' for i in range(1, 8)), 'aggregate_opening_m'])
            value['action_schema'] = {
                'schema_id': 'libero-joint-space-absolute-v1', 'schema_version': 1,
                'controller_kind': 'absolute_joint', 'reference': 'joint_coordinates',
                'dimension': len(components), 'components': components,
            }
        object_names = ('akita_black_bowl_1', 'plate_1')
        value['action_space'] = Box(-np.inf, np.inf, (len(components),), dtype=np.float64)
        value['observation_space'] = Dict({
            'state': Dict({
                'ee_pose': Box(-np.inf, np.inf, (7,), dtype=np.float32),
                'joint_position': Box(-np.inf, np.inf, (9,), dtype=np.float32),
                'boundary_identity_sha256': Box(0, 255, (32,), dtype=np.uint8),
            }),
            'privileged_state': Dict({
                name + '_body_pose': Box(-np.inf, np.inf, (1, 7), dtype=np.float32)
                for name in object_names
            }),
        })
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

    def prepare_mixed_control(env, action, state):
        values = np.asarray(action, dtype=np.float64)
        components = tuple(env.value['action_schema']['components'])
        if values.shape != (len(components),) or not np.isfinite(values).all():
            raise ValueError('task action must be a finite vector matching its declared action schema')
        values_tuple = tuple(float(item) for item in values)
        source = env.value['source']
        plan = source.mixed_actuator_plan
        request = StructuredActionRequestV1(
            'structured-action-request-v1',
            source.execution_source_receipt.canonical_xml_sha256,
            plan.identity_hash,
            (ControlGroupActionV1(
                'control-group-action-v1', 'panda-v1', 'mixed-actuation',
                env.value['action_schema']['schema_id'], values_tuple,
            ),),
        )
        request.validate()
        action_schema_id = env.value['action_schema']['schema_id']
        controller_values = values_tuple
        arm_resolution = None
        aggregate_opening_m = None
        substep_context = None
        canonical_action = {
            'schema_version': 'libero-joint-space-canonical-v1',
            'interpreted_values': values_tuple,
            'controller_identity': env.controller.identity,
            'hold_policy': _controller_hold_policy(env.controller),
        }
        if action_schema_id == 'libero-world-pose-wxyz-absolute-v1':
            if (env.value.get('arm_resolver') is None
                    or not hasattr(env.controller, 'last_control_receipt')):
                raise RuntimeError('world-pose task route has no shared arm resolver or feed-forward mixed Controller')
            from task_env.controllers.canonical.contracts import CanonicalArmResolutionV1
            arm_resolution = env.value['arm_resolver'].resolve_world_pose_target_iterative_v1(
                current_joint_position_rad=tuple(
                    float(state.joint_position[f'joint{index}']) for index in range(1, 8)
                ),
                current_pose_world=state.pose_world['panda-v1/ee'],
                target_pose_world=values_tuple[:7],
                gripper_scalar=values_tuple[7],
                model_position_tolerance_m=0.003,
                model_orientation_tolerance_rad=0.03,
            )
            if type(arm_resolution) is not CanonicalArmResolutionV1:
                raise TypeError('canonical arm resolver returned an untyped iterative result')
            if not arm_resolution.diagnostics.converged:
                raise ValueError('shared canonical arm resolver did not meet its FK residual gates')
            arm_target = arm_resolution.target
            normalized_opening = float(values_tuple[7])
            aggregate_opening_m = 0.04 * (normalized_opening + 1.0)
            if not 0.0 <= aggregate_opening_m <= 0.08:
                raise ValueError('normalized planner gripper is outside the aggregate opening range')
            ordered_q = env.controller.map_arm_target_to_control_order(arm_target)
            named_servo = dict(zip(arm_target.arm_joint_order, arm_target.servo_position_rad, strict=True))
            ordered_servo = tuple(
                float(named_servo[f'panda-v1/{name}']) for name in env.controller.control_joint_order
            )
            controller_values = (*ordered_q, aggregate_opening_m)
            substep_context = {
                'arm_resolution': arm_resolution,
                'aggregate_opening_m': aggregate_opening_m,
            }
            canonical_action = {
                'schema_version': 'libero-world-pose-canonical-v1',
                'interpreted_values': values_tuple,
                'controller_identity': env.controller.identity,
                'hold_policy': _controller_hold_policy(env.controller),
                'arm_target_schema_version': arm_target.schema_version,
                'arm_target_source_xml_sha256': arm_target.source_xml_sha256,
                'arm_target_controller_identity': arm_target.controller_identity,
                'arm_resolution_diagnostics': arm_resolution.diagnostics.to_mapping(),
                'qdesired_rad': list(ordered_q),
                'qdesired_joint_order': list(env.controller.control_joint_order),
                'arm_joint_order': list(arm_target.arm_joint_order),
                'arm_servo_position_rad': list(ordered_servo),
                'normalized_gripper_scalar': normalized_opening,
                'aggregate_opening_m': aggregate_opening_m,
                'finger_position_mapping_m': [aggregate_opening_m / 2.0, -aggregate_opening_m / 2.0],
            }
        elif action_schema_id != 'libero-joint-space-absolute-v1':
            raise ValueError('unsupported LIBERO selected task action schema')
        target_kwargs = {
            'task_artifact_hash': env.artifact.identity_hash,
            'source_id': source.scene_source.source_id,
            'source_closure_digest': source.source_closure_digest,
            'provider_materialization_id': env.session.provider_materialization_id,
            'episode_id': env.session.episode_id,
            'reset_sample_id': env.sample.sample_id,
            'state_revision': env.session.state_revision,
        }
        if arm_resolution is None:
            target = env.controller.compute_target(controller_values, state, **target_kwargs)
        else:
            target = env.controller.compute_pose_target(
                arm_resolution, aggregate_opening_m, state, **target_kwargs,
            )
        if action_schema_id == 'libero-world-pose-wxyz-absolute-v1':
            canonical_action['controller_receipt'] = env.controller.last_control_receipt
        prepared = {
            'action_values': values_tuple,
            'universal_action': values_tuple,
            'request': request,
            'target': target,
            'writer_control': {
                'writer_id': 'libero-spatial-mixed-controller-v1',
                'action_schema_id': env.value['action_schema']['schema_id'],
                'components': components,
                'groups': ({
                    'entity_id': 'panda-v1', 'group_id': 'mixed-actuation',
                    'action_components': components,
                },),
                'requested_action': {
                    'schema_version': env.value['action_schema']['schema_id'],
                    'values': values_tuple,
                    'unit': ('world_xyz_m_quaternion_wxyz_plus_normalized_gripper'
                             if action_schema_id == 'libero-world-pose-wxyz-absolute-v1'
                             else 'rad_x7_plus_aggregate_opening_m'),
                },
                'canonical_action': canonical_action,
            },
        }
        if _solution_profile:
            prepared['substep_context'] = substep_context
        return prepared

    def prepare_mixed_control_substep(env, prepared, state, substep_index,
                                      substep_count, state_revision):
        """Recompute task OSC from each fresh native state and the same pose goal."""
        if (type(substep_index) is not int or type(substep_count) is not int
                or not 0 <= substep_index < substep_count
                or substep_count != env.artifact.timebase.control_substeps
                or type(state_revision) is not int or state_revision < 0):
            raise ValueError('physics-rate OSC callback received an invalid substep boundary')
        context = prepared.get('substep_context')
        if not isinstance(context, Mapping):
            raise TypeError('physics-rate OSC callback requires its typed outer pose-resolution context')
        if substep_index == 0:
            target = prepared['target']
            receipt = prepared['writer_control']['canonical_action'].get('controller_receipt')
        else:
            source = env.value['source']
            target = env.controller.compute_pose_target(
                context['arm_resolution'], context['aggregate_opening_m'], state,
                task_artifact_hash=env.artifact.identity_hash,
                source_id=source.scene_source.source_id,
                source_closure_digest=source.source_closure_digest,
                provider_materialization_id=env.session.provider_materialization_id,
                episode_id=env.session.episode_id,
                reset_sample_id=env.sample.sample_id,
                state_revision=state_revision,
            )
            receipt = env.controller.last_control_receipt
        if not isinstance(receipt, Mapping):
            raise TypeError('physics-rate OSC callback omitted its recomputation receipt')
        return {'target': target, 'controller_receipt': dict(receipt)}

    def observe_mixed_control(env, state):
        return observe_selected_reference_v1(env, state)

    def mixed_record_metadata(env):
        source = env.value['source']
        receipt = source.execution_source_receipt
        reset_context = env.info
        if not isinstance(reset_context, dict):
            raise RuntimeError('task recording metadata has no reset context')
        reset_sample = reset_context.get('reset_sample_v1')
        reset_realization = reset_context.get('reset_realization_v1')
        reset_readback = reset_context.get('reset_readback_v1')
        if not all(isinstance(item, dict) for item in (reset_realization, reset_readback)):
            raise RuntimeError('task recording metadata requires reset realization/readback receipts')
        components = list(env.value['action_schema']['components'])
        return {
            'env_metadata': {
                'env_name': ('SelectedReferenceEnv.LiberoMixedDiagnosticV1'
                             if not _solution_profile else
                'SelectedReferenceEnv.LiberoMixedSolutionV4'),
                'task_name': env.artifact.task_id,
                'task_version': env.artifact.artifact_version,
                'physics_dt': env.artifact.timebase.physics_dt,
                'control_substeps': env.artifact.timebase.control_substeps,
                'control_frequency': 1.0 / env.artifact.timebase.control_dt,
                'action_schema': {
                    'schema_id': env.value['action_schema']['schema_id'],
                    'components': components,
                    'controller_kind': env.value['action_schema']['controller_kind'],
                    'reference': env.value['action_schema']['reference'],
                    'rotation_representation': env.value['action_schema'].get('rotation_representation'),
                    'units': (
                        ['meter'] * 3 + ['unit_quaternion_wxyz'] * 4 + ['normalized_minus1_to1']
                        if env.value['action_schema']['schema_id'] == 'libero-world-pose-wxyz-absolute-v1'
                        else ['radian'] * 7 + ['meter_total_opening']
                    ),
                },
                'observation_schema': {
                    'state.ee_pose': 'world_position_m_quaternion_wxyz',
                    'state.joint_position': 'seven_arm_then_two_signed_finger_positions_rad_m',
                    'state.boundary_identity_sha256': 'selected RuntimeSession boundary identity SHA-256',
                    'privileged_state.*_body_pose': 'world_body_center_m_quaternion_wxyz',
                },
                'provider': env.provider, 'backend': env.backend,
                'evidence_class': 'diagnostic_candidate',
            },
            'universal_action_schema': {
                'version': env.value['action_schema']['schema_id'],
                'dimension': len(components), 'components': components,
            },
            'resolved_config': {
                'provider': env.provider, 'backend': env.backend, 'horizon': env.horizon,
                'physics_dt': env.artifact.timebase.physics_dt,
                'control_substeps': env.artifact.timebase.control_substeps,
                'control_dt': env.artifact.timebase.control_dt,
                'integrator': source.config.runtime.integrator,
                'controller_profile_id': env.controller.profile_id,
                'controller_identity': env.controller.identity,
                    'hold_policy': _controller_hold_policy(env.controller),
            },
            'control_plan': env.controller.identity_mapping(),
            'task_context': {
                'schema_version': 'libero-episode-context-v1',
                'task_artifact_identity_hash': env.artifact.identity_hash,
                'source_id': source.scene_source.source_id,
                'source_xml_sha256': receipt.canonical_xml_sha256,
                'source_closure_digest': source.source_closure_digest,
                'source_manifest_sha256': env.value['source_manifest_sha256'],
                'solution_identity': env.value.get('solution_identity'),
                'controller_identity': env.controller.identity,
                'provider_materialization_id': env.session.provider_materialization_id,
                'episode_id': env.session.episode_id,
                'init_row_index': env.sample.init_row_index,
                'init_row_sha256': env.sample.init_row_sha256,
                'reset_sample_id': env.sample.sample_id,
                'simulation_time_s': env.sample.simulation_time_s,
                'reset_sample_v1': reset_sample,
                'reset_realization_v1': reset_realization,
                'reset_readback_v1': reset_readback,
            },
            'candidate_identity': {
                'task_artifact_identity_hash': env.artifact.identity_hash,
                'source_id': source.scene_source.source_id,
                'source_xml_sha256': receipt.canonical_xml_sha256,
                'source_closure_digest': source.source_closure_digest,
                'provider_materialization_id': env.session.provider_materialization_id,
                'controller_identity': env.controller.identity,
                'source_manifest_sha256': env.value['source_manifest_sha256'],
                'solution_identity': env.value.get('solution_identity'),
            },
        }

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
        expected_scalar_addresses = {
            **{f'joint{i}': [i - 1, i - 1] for i in range(1, 8)},
            'finger_joint1': [7, 7], 'finger_joint2': [8, 8],
            'wooden_cabinet_1.top_level': [44, 39],
            'wooden_cabinet_1.middle_level': [45, 40],
            'wooden_cabinet_1.bottom_level': [46, 41],
            'flat_stove_1.button': [47, 42],
        }
        expected_free_addresses = {
            name: [9 + 7 * index, 9 + 6 * index]
            for index, name in enumerate((
                'akita_black_bowl_1', 'akita_black_bowl_2', 'cookies_1',
                'glazed_rim_porcelain_ramekin_1', 'plate_1',
            ))
        }
        if (receipt['named_joint_addresses'] != expected_scalar_addresses
                or receipt['named_free_joint_addresses'] != expected_free_addresses):
            raise ValueError('compiled scalar joint order differs from the fixed source init layout')
        expected_channels = {
            channel.semantic_id: channel for channel in value['source'].mixed_actuator_plan.channels
        }
        compiled_channels = receipt.get('named_actuator_channels')
        if not isinstance(compiled_channels, dict) or set(compiled_channels) != set(expected_channels):
            raise ValueError('compiled named actuator channels differ from the fixed source plan')
        for semantic, channel in expected_channels.items():
            record = compiled_channels[semantic]
            if (record.get('actuator_name') != channel.actuator_name
                    or record.get('joint_name') != channel.joint_name
                    or record.get('drive_mode') != channel.drive_mode
                    or record.get('unit') != channel.unit
                    or record.get('control_range') != list(channel.control_range)
                    or record.get('control_limited') is not True):
                raise ValueError(f'compiled actuator differs from the fixed source channel: {semantic}')
        if (receipt['source_id'] != value['source'].scene_source.source_id
                or receipt['source_closure_digest'] != value['source'].source_closure_digest):
            raise ValueError('compiled LIBERO layout receipt is not source-bound')
        return {
            'schema_version': 'r07c-d01-pre-reset-compiled-validation-v1',
            'runtime_identity': session.runtime_identity,
            'compiled_layout': receipt,
            'reset_not_yet_applied': True,
        }

    def validate_external_solution(value, solution):
        from .solution import LiberoPickPlaceSolutionV5, solution_identity_v5

        if not isinstance(solution, LiberoPickPlaceSolutionV5):
            raise TypeError('LIBERO task #1 external lifecycle requires LiberoPickPlaceSolutionV5')
        expected_source = value['source_sha256']['composed_candidate_xml']
        expected_closure = value['source_sha256']['source_closure_digest']
        if (solution.task_uid != value['artifact'].task_id
                or solution.source_xml_sha256 != expected_source
                or solution.source_closure_digest != expected_closure
                or solution.identity != value.get('solution_identity')
                or solution.arm_resolver_identity
                   != value['arm_resolver'].iterative_resolution_identity_v1()
                or solution.identity != solution_identity_v5(
                    expected_source, expected_closure,
                    arm_resolver_identity=value['arm_resolver'].iterative_resolution_identity_v1(),
                )):
            raise ValueError('external LIBERO Solution does not match the selected task/source/profile')

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
        build_mixed_control_profile=build_value,
        build_external=(lambda provider: build_value(provider, 'cpu')) if _solution_profile else None,
        validate_external_solution=validate_external_solution if _solution_profile else None,
        reset_sample_with_options=reset_with_options,
        prepare_mixed_control=prepare_mixed_control,
        prepare_mixed_control_substep=(
            prepare_mixed_control_substep if _solution_profile else None
        ),
        observe_mixed_control=observe_mixed_control,
        mixed_record_metadata=mixed_record_metadata,
        pre_reset_session_validator=validate_compiled_session,
        close_task_resources=close_task_resources if _solution_profile else None,
    )
    env = SelectedReferenceEnv.from_mixed_control_candidate(
        binding, provider='mujoco', backend='cpu', horizon=horizon,
    )
    env_holder['env'] = env
    if _solution_profile:
        env.metadata.update({
            'provider': 'mujoco', 'backend': 'cpu',
            'solution_identity': env.value['solution_identity'],
            'source_xml_sha256': env.value['source_sha256']['composed_candidate_xml'],
            'source_closure_digest': env.value['source_sha256']['source_closure_digest'],
        })
    # The shared sample owner retains reset and source facts for the public
    # reset receipt; it is private recipe state, not a second runtime owner.
    env.value['reset_realizations'] = reset_receipts
    return env


def build_libero_solution_candidate(
    *, xml_path: Path = DEFAULT_OUTPUT_ROOT / 'source/composed_candidate.xml',
    xml: str | bytes | None = None,
    composed_mjcf_sha256: str | None = None,
    composition_plan_path: Path = DEFAULT_OUTPUT_ROOT / 'source/composition_plan.json',
    install_root: Path = DEFAULT_INSTALL_ROOT,
    init_path: Path | None = None,
    horizon: int = 1000,
):
    """Construct the versioned task #1 Solution through existing Core owners."""
    if type(horizon) is not int or not 1 <= horizon <= 1000:
        raise ValueError('LIBERO task Solution horizon must be in [1,1000]')
    return build_libero_selected_candidate(
        xml_path=xml_path, xml=xml, composed_mjcf_sha256=composed_mjcf_sha256,
        composition_plan_path=composition_plan_path, install_root=install_root,
        init_path=init_path, horizon=horizon, _solution_profile=True,
    )


__all__ = ['build_libero_selected_candidate', 'build_libero_solution_candidate']
