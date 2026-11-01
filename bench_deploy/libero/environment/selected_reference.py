"""Task-local construction recipe for the R07c LIBERO mixed diagnostic.

The candidate owns only the fixed Artifact/source/Controller/reset binding.
SelectedReferenceEnv and RuntimeSession retain lifecycle, admission, native
control, observation, and recording ownership.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from collections.abc import Callable, Mapping
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import numpy as np
from gymnasium.spaces import Box, Dict

from task_env.artifacts import (
    ActionIntent, EntityDefinition, InitializationContract, RequiredCapabilitySet,
    SemanticDefinition, TaskArtifact, Timebase, WorldDefinition,
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
from task_env.environment.types import ReferenceSpec
from task_env.tasks.reference_env import ReferenceTaskBinding, SelectedReferenceEnv

from bench_deploy.libero.controllers.osc import LiberoMixedControllerV6, LiberoMixedControllerV7
from bench_deploy.libero.tasks.predicates import (
    PILOT_TASK_UID, evaluate_on_bowl_plate_v1, evaluate_open_middle_drawer_v1,
    evaluate_stove_front_region_v1, observe_selected_reference_v1,
    observe_task23_reference_v1,
)
from bench_deploy.libero.environment.init_state import (
    PILOT_SOURCE_MANIFEST_SHA256, decode_pruned_init_bytes,
    init_layout_v1, sample_libero_normal_reset_v1,
)
from bench_deploy.libero.artifacts.contracts import TASK_1, TASK_2, TASK_3, task_source_contract_v1
from bench_deploy.libero.assembly.model_profile import (
    normalize_libero_robosuite_model_xml_v3,
    validate_libero_official_source_plan_v1,
)


PANDA_GRIPPER_DELTA_REPLAY_PROFILE_ID = 'robosuite-panda-gripper-delta-v1'
PANDA_GRIPPER_ENDPOINT_GUARD_PROFILE_ID = 'robosuite-panda-gripper-delta-endpoint-guard-v2'
PANDA_GRIPPER_DELTA_PROFILE_IDS = frozenset({
    PANDA_GRIPPER_DELTA_REPLAY_PROFILE_ID,
    PANDA_GRIPPER_ENDPOINT_GUARD_PROFILE_ID,
})
PANDA_GRIPPER_DELTA_ACTION_SCHEMA_ID = 'libero-world-pose-wxyz-panda-gripper-delta-v1'
_PANDA_GRIPPER_DELTA_PER_SUBSTEP = 0.01
_PANDA_GRIPPER_ENDPOINT_MARGIN_M = 5.0e-4


def _a_upstream_pose_replay_joint_limit_tolerances(
    provider: str, task_uid: str, upstream_pose_replay: bool,
) -> dict[str, float]:
    """Return the bounded physical-monitor allowances for task2/3 A replay."""
    if type(upstream_pose_replay) is not bool:
        raise TypeError('upstream pose replay selector must be bool')
    if not upstream_pose_replay or provider != 'mujoco' or task_uid not in {TASK_2, TASK_3}:
        return {}
    finger_tolerance = 500.0e-6 if task_uid == TASK_3 else 50.0e-6
    return {
        **{f'joint{i}': 4.0e-3 for i in range(1, 8)},
        'finger_joint1': finger_tolerance,
        'finger_joint2': finger_tolerance,
        'wooden_cabinet_1.top_level': 50.0e-6,
        'wooden_cabinet_1.middle_level': 50.0e-6,
        'wooden_cabinet_1.bottom_level': 50.0e-6,
    }


def _make_candidate_controller(
    *, execution_profile: str, task_uid: str,
    arm_resolver_identity: str | None,
    nullspace_reference_joint_position_rad=None,
):
    """Select the final optional V8 or accepted A-reference controller."""
    if execution_profile == 'v8':
        return LiberoMixedControllerV7(arm_resolver_identity=arm_resolver_identity)
    if execution_profile == 'a-reference':
        return LiberoMixedControllerV6(
            arm_resolver_identity=arm_resolver_identity,
            allow_unconverged_arm_resolution=(task_uid == TASK_3),
            nullspace_reference_joint_position_rad=nullspace_reference_joint_position_rad,
        )
    raise ValueError('LIBERO candidate requires execution_profile="a-reference" or "v8"')


def _panda_gripper_action_after_substep(current_action: float, action: float) -> float:
    """Mirror pinned robosuite PandaGripper.format_action for one physics substep."""
    current_action = float(current_action)
    action = float(action)
    if (not np.isfinite(current_action) or not -1.0 <= current_action <= 1.0
            or not np.isfinite(action) or not -1.0 <= action <= 1.0):
        raise ValueError('PandaGripper replay state and normalized action must lie in [-1,1]')
    return float(np.clip(
        current_action - _PANDA_GRIPPER_DELTA_PER_SUBSTEP * np.sign(action), -1.0, 1.0,
    ))


def _panda_gripper_aggregate_opening_m(
    current_action: float,
    profile_id: str = PANDA_GRIPPER_DELTA_REPLAY_PROFILE_ID,
) -> float:
    """Map robosuite PandaGripper state to its versioned opening profile."""
    current_action = float(current_action)
    if not np.isfinite(current_action) or not -1.0 <= current_action <= 1.0:
        raise ValueError('PandaGripper current_action must lie in [-1,1]')
    if profile_id not in PANDA_GRIPPER_DELTA_PROFILE_IDS:
        raise ValueError('unsupported PandaGripper delta replay profile')
    opening = 0.04 * (1.0 + current_action)
    margin = (_PANDA_GRIPPER_ENDPOINT_MARGIN_M
              if profile_id == PANDA_GRIPPER_ENDPOINT_GUARD_PROFILE_ID else 0.0)
    return float(np.clip(
        opening, margin, 0.08 - margin,
    ))


def _compiled_physics_fingerprint_diff_v1(actual, expected):
    """Return bounded field-level differences for a failed model readback."""
    result = {}
    for field in ('model_dimensions', 'object_names', 'numeric_array_fields'):
        left, right = actual.get(field, {}), expected.get(field, {})
        keys = sorted(set(left) | set(right))
        changed = [key for key in keys if left.get(key) != right.get(key)]
        result[field] = {
            'mismatch_count': len(changed),
            'first_mismatches': [
                {'name': key, 'actual': left.get(key), 'expected': right.get(key)}
                for key in changed[:12]
            ],
        }
    return result


ARTIFACT_ID = 'libero-spatial-bowl-to-plate-v1/mixed-v1'
SCENE_ID = 'libero-spatial-bowl-to-plate-composed-mjcf-v1'
SOURCE_MANIFEST_PATH = Path(__file__).resolve().parents[3] / 'asset/benchmarks/libero/source_manifest.json'
DEFAULT_INSTALL_ROOT = Path(
    '/home/lly/Program_Files/Geochora/workspace/maintenance/'
    'phase_ii_01_sol_luna_handoff_20261023_001/r07b_pilot_001_install/final_001'
)
INIT_RELATIVE_PATH = (
    'upstream/libero/libero/libero/init_files/libero_spatial/'
    'pick_up_the_black_bowl_between_the_plate_and_the_ramekin_and_place_it_on_the_plate.pruned_init'
)
TASK_ID = PILOT_TASK_UID


@dataclass(frozen=True)
class _TaskProfile:
    semantic_id: str
    semantic_entities: tuple[str, ...]
    semantic_parameters: tuple[tuple[str, float], ...]
    success_rule: str
    static_instances: tuple[str, ...]
    observer: Callable
    object_poses: tuple[tuple[str, str], ...] | None = None

    @property
    def fixture_bodies(self):
        return ('wooden_cabinet_1', 'flat_stove_1', *self.static_instances)


_TASK_PROFILES = {
    TASK_1: _TaskProfile(
        'libero_on_bowl_plate_v1',
        ('panda-v1/ee', 'main_table', 'akita_black_bowl_1', 'plate_1'),
        (('xy_threshold_m', 0.03),),
        'libero_on_bowl_plate_geom_contact_and_xy_lt_0_03m_v1',
        (),
        observe_selected_reference_v1,
        (('akita_black_bowl_1', 'bowl'), ('plate_1', 'plate')),
    ),
    TASK_2: _TaskProfile(
        'libero_open_middle_drawer_source_predicate_v1',
        ('panda-v1/ee', 'wooden_cabinet_1', 'main_table'),
        (('middle_drawer_open_threshold_m', -0.14),),
        'libero_open_middle_drawer_joint_position_lt_minus_0_14m_v1',
        ('wine_rack_1',),
        observe_task23_reference_v1,
    ),
    TASK_3: _TaskProfile(
        'libero_plate_front_of_stove_source_predicate_v1',
        ('panda-v1/ee', 'main_table', 'plate_1', 'flat_stove_1'),
        (('stove_front_xy_half_extent_m', 0.01),),
        'libero_site_object_under_plate_and_stove_front_v1',
        ('wine_rack_1',),
        observe_task23_reference_v1,
    ),
}


class _LiberoMJCFReferenceScene:
    """Task-local names required to compile the already-authored LIBERO MJCF."""

    uid = 'libero-spatial-bowl-to-plate-source-mjcf-v1'

    def __init__(self, reference_spec: ReferenceSpec):
        self._reference_spec = reference_spec

    def reference_spec(self):
        return self._reference_spec


def _geophys_importer_site_projection_v1(xml_bytes: bytes, *, task_uid: str = TASK_1):
    """Apply explicit importer-only compatibility projections for the selected LIBERO task."""
    if type(xml_bytes) is not bytes:
        raise TypeError('GeoPhys LIBERO importer projection requires immutable MJCF bytes')
    root = ET.fromstring(xml_bytes)
    matches = tuple(re.finditer(rb'<site\b[^>]*>', xml_bytes))
    sites = tuple(root.iter('site'))
    if len(matches) != len(sites):
        raise ValueError('GeoPhys LIBERO site projection could not map source XML tags exactly')
    widths = {'sphere': 1, 'capsule': 2, 'cylinder': 2, 'box': 3, 'ellipsoid': 3}
    replacements = []
    projected_xml = xml_bytes
    for match, site in reversed(tuple(zip(matches, sites, strict=True))):
        shape = site.get('type', 'sphere')
        if shape not in widths:
            raise ValueError(f'GeoPhys LIBERO importer does not support MJCF Site type {shape!r}')
        raw_size = site.get('size')
        if raw_size is None:
            continue
        values = raw_size.split()
        if len(values) == widths[shape]:
            continue
        if (shape != 'sphere' or len(values) != 3
                or not np.allclose(
                    tuple(float(value) for value in values),
                    (float(values[0]),) * 3, rtol=0.0, atol=0.0,
                )):
            name = site.get('name', '<unnamed>')
            raise ValueError(
                f'GeoPhys LIBERO importer found unsupported padded Site dimensions: '
                f'{name} ({shape}, {raw_size})'
            )
        tag = match.group(0)
        size_attr = re.search(rb'(\bsize\s*=\s*)(["\'])(.*?)(\2)', tag)
        if size_attr is None:
            raise ValueError('GeoPhys LIBERO Site projection could not locate the size attribute')
        projected_tag = (
            tag[:size_attr.start(3)] + values[0].encode('ascii') + tag[size_attr.end(3):]
        )
        replacements.append({
            'site_name': site.get('name', ''),
            'shape': shape,
            'size_before': list(values),
            'size_after': [values[0]],
            'reason': 'MuJoCo sphere Site uses the first size component; trailing repeated marker dimensions are nonphysical',
        })
        # Rebuild only this start tag; descending order preserves earlier offsets.
        projected_xml = (
            projected_xml[:match.start()] + projected_tag + projected_xml[match.end():]
        )
    ET.fromstring(projected_xml)
    transformations = list(reversed(replacements))
    fluid_projection = None
    if task_uid in {TASK_2, TASK_3}:
        projected_root = ET.fromstring(projected_xml)
        option_elements = tuple(projected_root.iter('option'))
        option_matches = tuple(re.finditer(rb'<option\b[^>]*>', projected_xml))
        if len(option_elements) != len(option_matches) or len(option_elements) != 1:
            raise ValueError('GeoPhys LIBERO fluid projection requires one mappable MJCF option element')
        option = option_elements[0]
        option_match = option_matches[0]
        option_tag = option_match.group(0)
        removed = {}
        for attribute in ('density', 'viscosity'):
            source_value = option.get(attribute)
            if source_value is None:
                continue
            try:
                numeric_value = float(source_value)
            except ValueError as error:
                raise ValueError(
                    f'GeoPhys LIBERO fluid projection found invalid {attribute}={source_value!r}'
                ) from error
            if not np.isfinite(numeric_value) or numeric_value < 0.0:
                raise ValueError(
                    f'GeoPhys LIBERO fluid projection found invalid {attribute}={source_value!r}'
                )
            attribute_pattern = re.compile(
                rb'\s+' + attribute.encode('ascii') + rb'\s*=\s*(["\'])(.*?)\1'
            )
            attribute_match = attribute_pattern.search(option_tag)
            if attribute_match is None:
                raise ValueError(
                    f'GeoPhys LIBERO fluid projection could not map the {attribute} attribute'
                )
            removed[attribute] = source_value
            option_tag = (
                option_tag[:attribute_match.start()]
                + option_tag[attribute_match.end():]
            )
        if removed:
            projected_xml = (
                projected_xml[:option_match.start()]
                + option_tag
                + projected_xml[option_match.end():]
            )
            transformations.append({
                'kind': 'omit_unsupported_inertia_based_fluid_forces',
                'source_option_attributes': removed,
                'importer_option_attributes': {},
                'reason': 'GeoPhys MJCF importer has no density/viscosity fluid-force support; original MuJoCo source and compiled-model evidence remain unchanged',
                'measured_impact': {
                    'row0_static_fluid_force_N': 0.0,
                    'maximum_force_fraction_of_object_weight_at_0_3m_s_translation_and_0_5rad_s_rotation': 0.0062,
                    'evidence': 'workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/libero_a123_closeout_20261101_001/fluid_effect_check_retry003_resource_receipt.json',
                },
            })
            fluid_projection = removed
    ET.fromstring(projected_xml)
    return projected_xml, {
        'schema_version': (
            'libero-geophys-importer-projection-v2' if fluid_projection is not None
            else 'libero-geophys-importer-site-projection-v1'
        ),
        'task_uid': task_uid,
        'transformations': transformations,
    }


def _artifact(init_bytes: bytes, *, execution_profile: str,
              provider: str = 'mujoco', task_uid: str = TASK_1) -> TaskArtifact:
    solution_profile = execution_profile == 'v8'
    contract = task_source_contract_v1(task_uid)
    profile = _TASK_PROFILES[task_uid]
    decoded = decode_pruned_init_bytes(init_bytes, task_uid=task_uid)
    layout = init_layout_v1(task_uid)
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
    shared_entities = [
        EntityDefinition(
            'panda-v1', 'embodiment', 'asset:libero-mounted-panda-v1',
            ('panda-v1/ee',), joints[:9], 'pinned_mounted_panda_mjcf',
            'source-authored-collision', {},
        ),
        EntityDefinition('main_table', 'scene', 'asset:libero-tabletop-v1', (), (),
                         'source-authored-tabletop', 'source-authored-collision', {}),
    ]
    for instance in contract.movable_instances:
        asset_slug = instance.rsplit('_', 1)[0]
        shared_entities.append(EntityDefinition(
            instance, 'movable', f'asset:libero-{asset_slug}-v1', (), (),
            'source-authored-mesh', 'source-authored-collision', {},
        ))
    shared_entities.extend((
        EntityDefinition('wooden_cabinet_1', 'static', 'asset:libero-wooden-cabinet-v1', (),
                         joints[9:12], 'source-authored-articulated-fixture',
                         'source-authored-collision', {}),
        EntityDefinition('flat_stove_1', 'static', 'asset:libero-flat-stove-v1', (),
                         (joints[12],), 'source-authored-articulated-fixture',
                         'source-authored-collision', {}),
    ))
    for instance in profile.static_instances:
        asset_slug = instance.rsplit('_', 1)[0].replace('_', '-')
        shared_entities.append(EntityDefinition(
            instance, 'static', f'asset:libero-{asset_slug}-v1', (), (),
            'source-authored-static-fixture', 'source-authored-collision', {},
        ))
    entities = tuple(shared_entities)
    from task_env.runtime.sessions.api import CAPABILITIES

    required_capabilities = (
        tuple(CAPABILITIES) + ('joint_torque_actuation',)
        if provider == 'geophys'
        else tuple(CAPABILITIES) + ('contact_detection',)
    )
    artifact = TaskArtifact(
        'task-artifact-v0',
        (ARTIFACT_ID if task_uid == TASK_1 else f'libero/{task_uid.rsplit("/", 1)[-1]}/mixed-v1')
        if not solution_profile else
        (ARTIFACT_ID + '/solution-v8' if task_uid == TASK_1 else
         f'libero/{task_uid.rsplit("/", 1)[-1]}/solution-v8'),
        task_uid, 'diagnostic-v1' if not solution_profile else 'diagnostic-solution-v8',
        WorldDefinition(
            'world-v0', 'SI_right_handed_z_up_wxyz', entities,
            ActionIntent('absolute_pose', 'world', 'quaternion_wxyz', 'arm_joint_position_and_gripper'),
            ('canonical-state-v0', 'task-contact-summary-v2'), (),
        ),
        InitializationContract(
            'initialization-v0', {}, {name: float(qpos[name]) for name in joints}, (),
            'restore_source_named_pruned_init_row', 'pinned_libero_normal_reset_v1', 0,
        ),
        SemanticDefinition(
            'semantics-v0', profile.semantic_id, profile.semantic_entities, joints,
            dict(profile.semantic_parameters), profile.success_rule,
        ),
        Timebase(0.002, 25, 0.05),
        RequiredCapabilitySet(required_capabilities),
    )
    artifact.validate()
    if tuple(artifact.initialization.joint_position) != tuple(joints):
        raise ValueError('LIBERO initialization field order differs from the source row projection')
    return artifact


def _build_fixed_source(*, xml_path: Path, xml_bytes_override: bytes | None,
                        install_root: Path, composition_plan_path: Path,
                        init_path: Path, horizon: int, execution_profile: str,
                        provider: str = 'mujoco', task_uid: str = TASK_1,
                        gripper_action_profile: str | None = None,
                        official_nullspace_reference_joint_position_rad=None,
                        official_compiled_mujoco_profile_v1=None):
    solution_profile = execution_profile == 'v8'
    upstream_pose_replay = execution_profile == 'a-reference' and task_uid in {TASK_2, TASK_3}
    a_reference_profile = execution_profile == 'a-reference'
    contract = task_source_contract_v1(task_uid)
    profile = _TASK_PROFILES[task_uid]
    panda_gripper_delta_replay = gripper_action_profile is not None
    official_nullspace_reference = None
    if official_nullspace_reference_joint_position_rad is not None:
        official_nullspace_reference = np.asarray(
            official_nullspace_reference_joint_position_rad, dtype=np.float64,
        )
        if (official_nullspace_reference.shape != (7,)
                or not np.isfinite(official_nullspace_reference).all()):
            raise ValueError('official robosuite nullspace reference must contain seven finite joint values')
        official_nullspace_reference = tuple(float(x) for x in official_nullspace_reference)
    official_compiled_mujoco_profile = None
    if official_compiled_mujoco_profile_v1 is not None:
        if not isinstance(official_compiled_mujoco_profile_v1, Mapping):
            raise TypeError('public candidate must provide a mapping for compiled MuJoCo options')
        official_compiled_mujoco_profile = json.loads(json.dumps(
            official_compiled_mujoco_profile_v1, allow_nan=False,
        ))
        if set(official_compiled_mujoco_profile) != {
                'mujoco_runtime', 'options', 'model_sizes',
                'compiled_model_binary_sha256',
                'compiled_model_physics_fingerprint_v1'}:
            raise ValueError('official compiled MuJoCo profile has an unsupported shape')
    raw_xml_bytes = Path(xml_path).read_bytes() if xml_bytes_override is None else bytes(xml_bytes_override)
    plan_bytes = Path(composition_plan_path).read_bytes()
    plan = json.loads(plan_bytes)
    if plan.get('output', {}).get('status') != 'SOURCE_MJCF_COMPOSED_NOT_NATIVE_COMPILED':
        raise ValueError('R07c source plan must remain explicitly source-composed and not precompiled')
    expected_xml_sha = plan['output']['composed_mjcf_sha256']
    source_model_id = plan.get('identity', {}).get('source_model_id')
    compile_first_official_model = source_model_id == 'libero-official-model-builder-v1'
    if compile_first_official_model:
        validate_libero_official_source_plan_v1(plan_bytes, raw_xml_bytes)
    if hashlib.sha256(raw_xml_bytes).hexdigest() != expected_xml_sha:
        raise ValueError('candidate MJCF differs from its frozen composition plan')
    runtime_model_xml_bytes = raw_xml_bytes
    model_profile_receipt = None
    model_profile_bytes = None
    if solution_profile:
        if not compile_first_official_model:
            raise ValueError('optional V8 requires the pinned official compile-first LIBERO model')
        runtime_model_xml_bytes, model_profile_receipt = normalize_libero_robosuite_model_xml_v3(raw_xml_bytes)
        model_profile_bytes = json.dumps(
            model_profile_receipt, sort_keys=True, separators=(',', ':'), allow_nan=False,
        ).encode('utf-8')
    runtime_model_xml_sha = hashlib.sha256(runtime_model_xml_bytes).hexdigest()
    model_profile_sha = (
        None if model_profile_bytes is None else hashlib.sha256(model_profile_bytes).hexdigest()
    )
    install_root = Path(install_root).resolve(strict=True)
    init_path = Path(init_path).resolve(strict=True)
    init_bytes = init_path.read_bytes()
    if hashlib.sha256(init_bytes).hexdigest() != contract.init_sha256:
        raise ValueError('candidate .pruned_init differs from the frozen task source bytes')
    if task_uid == TASK_1:
        manifest_bytes = SOURCE_MANIFEST_PATH.read_bytes()
        if hashlib.sha256(manifest_bytes).hexdigest() != PILOT_SOURCE_MANIFEST_SHA256:
            raise ValueError('tracked LIBERO source manifest differs from the frozen pilot identity')
        source_manifest = json.loads(manifest_bytes)
        source_manifest_sha256 = PILOT_SOURCE_MANIFEST_SHA256
    else:
        source_manifest = {
            'schema_version': 'libero-task-source-identity-v1',
            'task_uid': task_uid,
            'libero_revision': '8f1084e3132a39270c3a13ebe37270a43ece2a01',
            'robosuite_revision': 'fbee5844ff5632f5b5698e204ec5357ca50be0df',
            'bddl_path': contract.bddl_path,
            'bddl_sha256': contract.bddl_sha256,
            'init_path': contract.init_path,
            'init_sha256': contract.init_sha256,
            'source_model_id': plan.get('identity', {}).get('source_model_id'),
            'source_model_xml_sha256': expected_xml_sha,
        }
        manifest_bytes = json.dumps(
            source_manifest, sort_keys=True, separators=(',', ':'), allow_nan=False,
        ).encode('utf-8')
        source_manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    artifact = _artifact(
        init_bytes, execution_profile=execution_profile, provider=provider, task_uid=task_uid,
    )

    importer_xml = runtime_model_xml_bytes
    importer_projection = {
        'schema_version': 'libero-geophys-importer-site-projection-v1',
        'task_uid': task_uid,
        'transformations': [],
    }
    if provider == 'geophys':
        importer_xml, importer_projection = _geophys_importer_site_projection_v1(
            runtime_model_xml_bytes, task_uid=task_uid,
        )
    external_assets = source_asset_bytes(install_root, importer_xml.decode('utf-8'))
    closure = {'canonical-source.xml': runtime_model_xml_bytes, **external_assets}
    source_id = (
        f'libero-spatial-official-model-profile-v3:{expected_xml_sha}:{model_profile_sha}:{runtime_model_xml_sha}'
        if solution_profile else
        f'libero-spatial-pilot-v1:{expected_xml_sha}' if task_uid == TASK_1 else
        f'libero-task-a-v1:{task_uid}:{expected_xml_sha}'
    )
    source_receipt = ExecutionSourceReceiptV1.create(
        source_id=source_id,
        canonical_xml=runtime_model_xml_bytes, importer_xml=importer_xml, closure_files=closure,
        expected_canonical_xml_sha256=runtime_model_xml_sha,
    )
    scene_source = TaskSceneSource(
        xml=runtime_model_xml_bytes.decode('utf-8'), base_dir=source_receipt.snapshot_root,
        source_id=source_receipt.source_id,
        diagnostics=(
            ('A-stage immutable LIBERO source; GeoPhys importer-only fluid-parameter projection is recorded in provider_import_projection',)
            if provider == 'geophys' and task_uid in {TASK_2, TASK_3} else
            ('A123 reference replay source; physical attributes preserved from the frozen model',)
            if not solution_profile else
            ('R07 v2.1.0 task #1 immutable importer snapshot; physical attributes preserved from composed MJCF',)
        ),
    )
    semantic_bodies = dict(plan['semantic_to_compiled_body_names'])
    expected_bodies = {
        'main_table': 'table' if compile_first_official_model or task_uid != TASK_1 else 'main_table',
        **{name: f'{name}_main' for name in (*contract.movable_instances, *profile.static_instances)},
        'wooden_cabinet_1': 'wooden_cabinet_1_main',
        'flat_stove_1': 'flat_stove_1_main',
    }
    if semantic_bodies != expected_bodies:
        source_receipt.close()
        raise ValueError('composition plan semantic body map differs from the fixed pilot allowlist')
    bound_bodies = dict(semantic_bodies)
    groups = plan['composition_receipt']['contact_geom_name_transform']['groups']
    contact_geom_groups = {key: tuple(value) for key, value in groups.items()}
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
        task_uid=task_uid, scene_uid=(SCENE_ID if task_uid == TASK_1 else f'libero-{task_uid.rsplit("/", 1)[-1]}-upstream-scene-v1'),
        runtime={
            'backend': 'cpu', 'physics_dt': 0.002, 'control_substeps': 25,
            'integrator': 'euler', 'prewarm': False,
        },
        render={'camera_obs': False}, episode={'horizon': horizon, 'ignore_done': False},
        success_definition=(
            'A-stage replay; task success is not claimed' if a_reference_profile else
            'pinned LIBERO On(akita_black_bowl_1,plate_1) task success and caller-owned Solution completion'
        ),
    )
    from task_env.controllers.canonical import CanonicalPandaController, PandaKinematics
    from task_env.controllers.canonical.kinematics import derive_panda_tcp_profile_v2
    tcp_profile = derive_panda_tcp_profile_v2(
        runtime_model_xml_bytes, tcp_id='libero-mounted-panda-v1/gripper0-grip-site-v1',
        hand_frame_id='robot0_right_hand', site_name='gripper0_grip_site',
    )
    arm_kinematics = PandaKinematics(
        runtime_model_xml_bytes, tcp_profile=tcp_profile, native_prefix='robot0_',
        base_body_id='robot0_link0',
    )
    resolver_action_config = (
        replace(
            config.action,
            ik_position_deadband=0.0005,
            ik_rotation_deadband=0.0025,
        ) if solution_profile else config.action
    )
    arm_resolver = CanonicalPandaController(
        arm_kinematics, artifact_hash=artifact.identity_hash,
        config=resolver_action_config,
    )
    arm_resolver_position_tolerance_m = 0.001 if solution_profile else 0.006
    arm_resolver_max_iterations = 64
    arm_resolver_orientation_tolerance_rad = (
        0.04 if panda_gripper_delta_replay else 0.005 if solution_profile else 0.03
    )
    arm_resolver_identity = (
        None if arm_resolver is None else arm_resolver.iterative_resolution_identity_v1(
            max_iterations=arm_resolver_max_iterations,
            position_tolerance_m=arm_resolver_position_tolerance_m,
            orientation_tolerance_rad=arm_resolver_orientation_tolerance_rad,
        )
    )
    controller = _make_candidate_controller(
        execution_profile=execution_profile,
        task_uid=task_uid,
        arm_resolver_identity=arm_resolver_identity,
        nullspace_reference_joint_position_rad=official_nullspace_reference,
    )
    expected_controller_profile = (
        LiberoMixedControllerV7.profile_id if solution_profile else
        LiberoMixedControllerV6.OFFICIAL_REFERENCE_PROFILE_ID
        if official_nullspace_reference is not None else LiberoMixedControllerV6.profile_id
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
    frames = {'panda-v1/ee': 'gripper0_grip_site'}
    free_joints = {name: f'{name}_joint0' for name in contract.movable_instances}
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
    provider_reference_scene = None
    provider_agents = ()
    provider_objects = tuple(key for key in expected_bodies if key != 'main_table')
    if provider == 'geophys':
        source_root = ET.fromstring(runtime_model_xml_bytes)
        provider_reference_scene = _LiberoMJCFReferenceScene(ReferenceSpec(
            body_names=tuple(bound_bodies.values()),
            joint_names=tuple((*joints.values(), *free_joints.values())),
            site_names=tuple(frames.values()),
            geom_names=tuple(
                name for geom in source_root.iter('geom')
                if (name := geom.get('name'))
            ),
            actuator_names=tuple(channel.actuator_name for channel in mixed_plan.channels),
        ))
        # The exact immutable importer source owns these assets and bodies.
        # The ordinary MuJoCo adapter consumes the separate semantic object list;
        # GeoPhys resolves the imported MJCF through the task-local name contract.
        provider_objects = ()
    source = RuntimeSource(
        task_artifact_hash=artifact.identity_hash,
        scene_source=scene_source,
        joints=joints,
        bodies=bound_bodies,
        frames=frames,
        free_joints=free_joints,
        joint_targets={}, open_actuators=(),
        composition=plan['composition_receipt'], config=config, scene=provider_reference_scene,
        agents=provider_agents, objects=provider_objects,
        source_closure_digest=source_receipt.source_closure_digest,
        execution_source_receipt=source_receipt,
        torque_actuators=torque_bindings,
        position_actuators=position_bindings,
        actuator_units={
            **{f'robot0_torq_j{i}': 'N*m' for i in range(1, 8)},
            'gripper0_gripper_finger_joint1': 'm',
            'gripper0_gripper_finger_joint2': 'm',
        },
        fixture_bodies=profile.fixture_bodies,
        contact_geom_groups=(contact_geom_groups if provider == 'mujoco' else {}),
        mixed_actuator_plan=mixed_plan,
        task_local_joint_limit_tolerance_overrides=(
            _a_upstream_pose_replay_joint_limit_tolerances(
                provider, task_uid, upstream_pose_replay,
            )
        ),
    )
    solution_identity = None
    if solution_profile:
        from bench_deploy.libero.tasks.solution import solution_identity_v8

        solution_identity = solution_identity_v8(
            runtime_model_xml_sha, source_receipt.source_closure_digest,
            arm_resolver_identity=arm_resolver_identity,
        )
    if panda_gripper_delta_replay:
        # This opt-in profile replays frozen upstream actions directly; it is
        # not the V5 task Solution lifecycle or identity.
        solution_identity = None
    return {
        'artifact': artifact, 'source': source, 'controller': controller,
        'selected_controller_kind': 'mixed_actuator_v1', 'solution': None,
        'source_manifest_sha256': source_manifest_sha256,
        'source_revision': 'LIBERO:8f1084e3132a39270c3a13ebe37270a43ece2a01;'
                           'robosuite:fbee5844ff5632f5b5698e204ec5357ca50be0df',
        'source_sha256': {
            'composed_candidate_xml': expected_xml_sha,
            'runtime_model_xml': runtime_model_xml_sha,
            'model_profile_receipt': model_profile_sha,
            'model_profile_id': (
                None if model_profile_receipt is None else model_profile_receipt['profile_id']
            ),
            'source_model_id': source_model_id,
            'composition_plan': hashlib.sha256(plan_bytes).hexdigest(),
            'source_manifest': hashlib.sha256(manifest_bytes).hexdigest(),
            'pruned_init': hashlib.sha256(init_bytes).hexdigest(),
            'importer_xml': hashlib.sha256(importer_xml).hexdigest(),
            'importer_projection': hashlib.sha256(json.dumps(
                importer_projection, sort_keys=True, separators=(',', ':'),
                allow_nan=False,
            ).encode('utf-8')).hexdigest(),
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
        'arm_resolver_identity': arm_resolver_identity,
        'arm_resolver_max_iterations': arm_resolver_max_iterations,
        'arm_resolver_position_tolerance_m': arm_resolver_position_tolerance_m,
        'arm_resolver_orientation_tolerance_rad': arm_resolver_orientation_tolerance_rad,
        'official_nullspace_reference_joint_position_rad': official_nullspace_reference,
        'official_compiled_mujoco_profile_v1': official_compiled_mujoco_profile,
        'source_xml_bytes': raw_xml_bytes,
        'runtime_model_xml_bytes': runtime_model_xml_bytes,
        'model_profile_bytes': model_profile_bytes,
        'model_profile_receipt': model_profile_receipt,
        'provider_import_projection': importer_projection,
        'solution_profile': bool(solution_profile),
        'resolved_configuration': asdict(config),
        'reset_realizations': {},
        'init_bytes': init_bytes,
        'source_manifest': source_manifest,
        'install_root': install_root,
    }


def build_libero_selected_candidate(
    *, xml_path: Path | None = None,
    xml: str | bytes | None = None,
    composition_plan_path: Path | None = None,
    install_root: Path = DEFAULT_INSTALL_ROOT,
    init_path: Path | None = None,
    horizon: int = 64,
    provider: str = 'mujoco',
    task_uid: str = TASK_1,
    _execution_profile: str = 'a-reference',
    _gripper_action_profile: str | None = None,
    _official_nullspace_reference_joint_position_rad=None,
    _official_compiled_mujoco_profile_v1=None,
):
    """Construct the fixed LIBERO candidate through the existing Core route.

    The default selects the accepted A-reference controller. The task-owned
    solution wrapper selects optional V8 explicitly.
    """
    if type(_execution_profile) is not str or _execution_profile not in {'a-reference', 'v8'}:
        raise TypeError('LIBERO execution profile must be the named A-reference or V8 profile')
    solution_profile = _execution_profile == 'v8'
    if solution_profile and task_uid != TASK_1:
        raise ValueError('optional V8 Solution is defined only for LIBERO task1')
    contract = task_source_contract_v1(task_uid)
    profile = _TASK_PROFILES[task_uid]
    if _gripper_action_profile is not None and _gripper_action_profile not in PANDA_GRIPPER_DELTA_PROFILE_IDS:
        raise ValueError('unsupported PandaGripper delta replay profile')
    panda_gripper_delta_replay = _gripper_action_profile is not None
    if (_official_nullspace_reference_joint_position_rad is not None
            and not panda_gripper_delta_replay):
        raise ValueError('official robosuite nullspace reference is restricted to the frozen PandaGripper replay profile')
    if (_official_compiled_mujoco_profile_v1 is not None
            and not panda_gripper_delta_replay):
        raise ValueError('official compiled MuJoCo options are restricted to the frozen PandaGripper replay profile')
    maximum_horizon = 1000
    if type(horizon) is not int or not 1 <= horizon <= maximum_horizon:
        raise ValueError(f'LIBERO candidate horizon must be in [1,{maximum_horizon}]')
    if composition_plan_path is None:
        raise ValueError('LIBERO candidate requires an explicit source composition plan')
    if xml is None and xml_path is None:
        raise ValueError('LIBERO candidate requires source XML bytes or an explicit XML path')
    xml_path = Path(xml_path) if xml_path is not None else Path(composition_plan_path).with_name('composed_candidate.xml')
    if provider not in {'mujoco', 'geophys'}:
        raise ValueError('LIBERO candidate supports MuJoCo or GeoPhys CPU')
    install_root = Path(install_root).resolve(strict=True)
    if init_path is None:
        if task_uid != TASK_1:
            raise ValueError('task2/3 LIBERO candidate requires the exact task-specific .pruned_init path')
        init_path = install_root / INIT_RELATIVE_PATH
    value_cache = {}
    reset_receipts = {}
    source_gravity_model_ref = {'model': None}
    source_gravity_model_resources = []
    source_resource_close_state = {'attempted': False, 'receipt': None, 'error': None}
    env_holder = {}

    def value_for_artifact(artifact):
        matches = [value for value in value_cache.values()
                   if value['artifact'].identity_hash == artifact.identity_hash]
        if len(matches) != 1:
            raise RuntimeError('LIBERO provider candidate cache does not contain this TaskArtifact')
        return matches[0]

    def bind_source_gravity_model(model):
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
        live_env = env_holder.get('env')
        source = value_cache.get(getattr(live_env, 'provider', None))
        if not isinstance(source, dict):
            raise RuntimeError('task Solution source identity must be built before binding gravity feed-forward')
        model_profile_receipt = source.get('model_profile_receipt')
        expected_model_profile_id = (
            None if model_profile_receipt is None else model_profile_receipt.get('profile_id')
        )
        if (getattr(model, 'profile_id', None) != 'libero-source-mjcf-gravity-bias-v1'
                or getattr(model, 'source_xml_sha256', None)
                != source['source_sha256']['runtime_model_xml']
                or getattr(model, 'source_closure_digest', None)
                != source['source_sha256']['source_closure_digest']
                or getattr(model, 'model_profile_id', None) != expected_model_profile_id
                or getattr(model, 'model_profile_receipt_sha256', None)
                != source['source_sha256']['model_profile_receipt']
                or not callable(getattr(model, 'operational_space_state_v2', None))):
            raise ValueError('task Solution gravity model differs from its selected source identity')
        live_env = env_holder.get('env')
        if live_env is not None and live_env.controller.gravity_bias_model is None:
            live_env.controller.set_source_gravity_model(
                model,
                source_xml_sha256=source['source_sha256']['runtime_model_xml'],
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
                if getattr(model, 'closed', False):
                    receipt = getattr(model, 'close_receipt', None)
                    if not isinstance(receipt, Mapping):
                        raise RuntimeError('closed task source helper omitted its own close receipt')
                elif controller is not None and getattr(controller, 'gravity_bias_model', None) is model:
                    receipt = controller.close_resources()
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
        if provider not in value_cache:
            xml_bytes = None if xml is None else (xml.encode('utf-8') if isinstance(xml, str) else bytes(xml))
            value = _build_fixed_source(
                xml_path=Path(xml_path), xml_bytes_override=xml_bytes, install_root=install_root,
                composition_plan_path=Path(composition_plan_path),
                init_path=Path(init_path), horizon=horizon,
                execution_profile=_execution_profile,
                provider=provider,
                task_uid=task_uid,
                gripper_action_profile=_gripper_action_profile,
                official_nullspace_reference_joint_position_rad=(
                    _official_nullspace_reference_joint_position_rad
                ),
                official_compiled_mujoco_profile_v1=(
                    _official_compiled_mujoco_profile_v1
                ),
            )
            value_cache[provider] = value
        else:
            value = dict(value_cache[provider])
            value['controller'] = _make_candidate_controller(
                execution_profile=_execution_profile,
                task_uid=task_uid,
                arm_resolver_identity=value['arm_resolver_identity'],
                nullspace_reference_joint_position_rad=(
                    value['official_nullspace_reference_joint_position_rad']
                ),
            )
        value['controller'].plan_identity_hash = value['source'].mixed_actuator_plan.identity_hash
        value['reset_realizations'] = reset_receipts
        value['bind_source_gravity_model'] = bind_source_gravity_model
        value['close_task_resources'] = close_task_resources
        model = source_gravity_model_ref['model']
        if model is not None:
            value['controller'].set_source_gravity_model(
                model,
                source_xml_sha256=value['source_sha256']['runtime_model_xml'],
                source_closure_digest=value['source_sha256']['source_closure_digest'],
            )
        value['panda_gripper_delta_replay_profile_id'] = _gripper_action_profile
        if panda_gripper_delta_replay:
            value['panda_gripper_delta_replay_state'] = {
                'current_action': 0.0, 'committed_control_step': 0, 'pending': None,
            }
        components = (
            'world_x_m', 'world_y_m', 'world_z_m',
            'world_qw', 'world_qx', 'world_qy', 'world_qz',
            'gripper_action_normalized_delta' if panda_gripper_delta_replay else 'gripper_normalized',
        )
        value['action_schema'] = {
            'schema_id': PANDA_GRIPPER_DELTA_ACTION_SCHEMA_ID if panda_gripper_delta_replay
            else 'libero-world-pose-wxyz-absolute-v1',
            'schema_version': 1,
            'controller_kind': 'absolute_pose_with_robosuite_panda_gripper_delta'
            if panda_gripper_delta_replay else 'absolute_pose',
            'reference': 'world', 'rotation_representation': 'quaternion_wxyz',
            'dimension': len(components), 'components': components,
            'gripper_profile_id': _gripper_action_profile,
            'gripper_endpoint_margin_m': (
                _PANDA_GRIPPER_ENDPOINT_MARGIN_M
                if _gripper_action_profile == PANDA_GRIPPER_ENDPOINT_GUARD_PROFILE_ID else 0.0
            ) if panda_gripper_delta_replay else None,
            'arm_resolver_orientation_tolerance_rad': value['arm_resolver_orientation_tolerance_rad'],
        }
        object_names = contract.movable_instances
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
        cached_value = value_for_artifact(artifact)
        if task_uid != TASK_1:
            from task_env.artifacts import ResetSampleV1

            if set(options) != {'task_reset_sample_v1'}:
                raise ValueError('task2/3 A-stage reset requires only its source-captured ResetSampleV1')
            reset_sample = options['task_reset_sample_v1']
            if type(reset_sample) is not ResetSampleV1:
                raise TypeError('task2/3 A-stage reset requires the public ResetSampleV1 value')
            reset_sample.validate()
            if (reset_sample.task_seed != seed
                    or reset_sample.task_artifact_hash != artifact.identity_hash
                    or reset_sample.source_id != source.scene_source.source_id
                    or reset_sample.source_closure_digest != source.source_closure_digest
                    or reset_sample.init_row_index != 0
                    or reset_sample.init_row_sha256 != decode_pruned_init_bytes(
                        cached_value['init_bytes'], task_uid=task_uid,
                    ).row_sha256[0]):
                raise ValueError('task2/3 reset sample differs from the pinned source row or candidate identity')
            receipt = {
                'schema_version': 'libero-upstream-reset-row-realization-v1',
                'task_uid': task_uid, 'task_seed': seed,
                'init_row_index': reset_sample.init_row_index,
                'init_row_sha256': reset_sample.init_row_sha256,
                'sampler_id': reset_sample.sampler_id,
                'sampler_version': reset_sample.sampler_version,
                'source_manifest_sha256': cached_value['source_manifest_sha256'],
                'reset_sample_id': reset_sample.sample_id,
                'reset_source': 'pinned ControlEnv.reset then ControlEnv.set_init_state(row0)',
            }
            reset_receipts[reset_sample.sample_id] = receipt
            return reset_sample
        reset_sample, receipt = sample_libero_normal_reset_v1(
            init_bytes=cached_value['init_bytes'],
            install_root=install_root,
            source_manifest=cached_value['source_manifest'],
            task_artifact_hash=artifact.identity_hash,
            source_id=source.scene_source.source_id,
            source_closure_digest=source.source_closure_digest,
            task_seed=seed,
            init_row_index=options.get('init_row_index', 0),
        )
        reset_receipts[reset_sample.sample_id] = receipt
        return reset_sample

    def evaluate(evidence, _semantics):
        if task_uid == TASK_1:
            return evaluate_on_bowl_plate_v1(
                evidence, expected_source_manifest_sha256=PILOT_SOURCE_MANIFEST_SHA256,
            )
        if task_uid == TASK_2:
            return evaluate_open_middle_drawer_v1(
                evidence, expected_boundary=getattr(evidence, 'boundary', None),
            )
        return evaluate_stove_front_region_v1(
            evidence, expected_boundary=getattr(evidence, 'boundary', None),
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
        action_schema_id = env.value['action_schema']['schema_id']
        aggregate_opening_m = None
        pose_action_schema_ids = {
            'libero-world-pose-wxyz-absolute-v1',
            PANDA_GRIPPER_DELTA_ACTION_SCHEMA_ID,
        }
        panda_gripper_delta_replay = (
            action_schema_id == PANDA_GRIPPER_DELTA_ACTION_SCHEMA_ID
        )
        if action_schema_id not in pose_action_schema_ids:
            raise ValueError('unsupported LIBERO selected task action schema')
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
            max_iterations=env.value['arm_resolver_max_iterations'],
            position_tolerance_m=env.value['arm_resolver_position_tolerance_m'],
            model_position_tolerance_m=0.003,
            orientation_tolerance_rad=env.value['arm_resolver_orientation_tolerance_rad'],
            model_orientation_tolerance_rad=0.03,
        )
        if type(arm_resolution) is not CanonicalArmResolutionV1:
            raise TypeError('canonical arm resolver returned an untyped iterative result')
        arm_target = arm_resolution.target
        normalized_opening = float(values_tuple[7])
        if panda_gripper_delta_replay:
            gripper_profile_id = env.value.get('panda_gripper_delta_replay_profile_id')
            if gripper_profile_id not in PANDA_GRIPPER_DELTA_PROFILE_IDS:
                raise RuntimeError('PandaGripper delta action schema has no matching task adapter')
            gripper_state = env.value.get('panda_gripper_delta_replay_state')
            if (not isinstance(gripper_state, dict)
                    or gripper_state.get('committed_control_step') != state.control_step
                    or gripper_state.get('pending') is not None):
                raise RuntimeError('PandaGripper replay state is stale or has an uncommitted action')
            current_gripper_action = float(gripper_state['current_action'])
            first_gripper_action = _panda_gripper_action_after_substep(
                current_gripper_action, normalized_opening,
            )
            final_gripper_action = current_gripper_action
            action_trace = [current_gripper_action]
            opening_trace = []
            for _ in range(env.artifact.timebase.control_substeps):
                final_gripper_action = _panda_gripper_action_after_substep(
                    final_gripper_action, normalized_opening,
                )
                action_trace.append(final_gripper_action)
                opening_trace.append(
                    _panda_gripper_aggregate_opening_m(
                        final_gripper_action, gripper_profile_id,
                    )
                )
            aggregate_opening_m = opening_trace[0]
            panda_gripper_context = {
                'profile_id': gripper_profile_id,
                'action_scalar': normalized_opening,
                'current_action_before': current_gripper_action,
                'action_trace_after_substeps': tuple(action_trace[1:]),
                'opening_trace_m': tuple(opening_trace),
                'current_action_after': final_gripper_action,
            }
            canonical_gripper_fields = {
                'gripper_profile_id': gripper_profile_id,
                'gripper_action_scalar': normalized_opening,
                'gripper_current_action_before': current_gripper_action,
                'gripper_current_action_after_first_substep': first_gripper_action,
                'gripper_current_action_after_outer_step': final_gripper_action,
                'gripper_current_action_trace_after_each_substep': list(action_trace[1:]),
                'gripper_aggregate_opening_trace_m': opening_trace,
                'gripper_format_calls_per_outer_step': env.artifact.timebase.control_substeps,
            }
        else:
            aggregate_opening_m = 0.04 * (normalized_opening + 1.0)
            if not 0.0 <= aggregate_opening_m <= 0.08:
                raise ValueError('normalized planner gripper is outside the aggregate opening range')
            panda_gripper_context = None
            canonical_gripper_fields = {
                'normalized_gripper_scalar': normalized_opening,
                'aggregate_opening_m': aggregate_opening_m,
                'finger_position_mapping_m': [aggregate_opening_m / 2.0, -aggregate_opening_m / 2.0],
            }
        ordered_q = env.controller.map_arm_target_to_control_order(arm_target)
        named_servo = dict(zip(arm_target.arm_joint_order, arm_target.servo_position_rad, strict=True))
        ordered_servo = tuple(
            float(named_servo[f'panda-v1/{name}']) for name in env.controller.control_joint_order
        )
        substep_context = {
            'arm_resolution': arm_resolution,
            'aggregate_opening_m': aggregate_opening_m,
            'panda_gripper_delta_replay': panda_gripper_context,
        }
        canonical_action = {
            'schema_version': 'libero-world-pose-canonical-v1',
            'interpreted_values': values_tuple,
            'controller_identity': env.controller.identity,
            'hold_policy': env.controller.operational_config.hold_policy,
            'arm_target_schema_version': arm_target.schema_version,
            'arm_target_source_xml_sha256': arm_target.source_xml_sha256,
            'arm_target_controller_identity': arm_target.controller_identity,
            'arm_resolution_diagnostics': arm_resolution.diagnostics.to_mapping(),
            'qdesired_rad': list(ordered_q),
            'qdesired_joint_order': list(env.controller.control_joint_order),
            'arm_joint_order': list(arm_target.arm_joint_order),
            'arm_servo_position_rad': list(ordered_servo),
            **canonical_gripper_fields,
        }
        target_kwargs = {
            'task_artifact_hash': env.artifact.identity_hash,
            'source_id': source.scene_source.source_id,
            'source_closure_digest': source.source_closure_digest,
            'provider_materialization_id': env.session.provider_materialization_id,
            'episode_id': env.session.episode_id,
            'reset_sample_id': env.sample.sample_id,
            'state_revision': env.session.state_revision,
        }
        target = env.controller.compute_pose_target(
            arm_resolution, aggregate_opening_m, state, **target_kwargs,
        )
        canonical_action['controller_receipt'] = env.controller.last_control_receipt
        if panda_gripper_delta_replay:
            first_action = panda_gripper_context['action_trace_after_substeps'][0]
            canonical_action['controller_receipt'] = {
                **dict(canonical_action['controller_receipt']),
                'panda_gripper_action_v1': {
                    'profile_id': panda_gripper_context['profile_id'],
                    'substep_index': 0,
                    'current_action': first_action,
                    'aggregate_opening_m': aggregate_opening_m,
                }
            }
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
                    'unit': ('world_xyz_m_quaternion_wxyz_plus_panda_gripper_delta'
                             if panda_gripper_delta_replay else
                             'world_xyz_m_quaternion_wxyz_plus_absolute_normalized_gripper'),
                },
                'canonical_action': canonical_action,
            },
        }
        prepared['substep_context'] = substep_context
        if panda_gripper_delta_replay:
            env.value['panda_gripper_delta_replay_state']['pending'] = {
                'control_step': int(state.control_step) + 1,
                'current_action': final_gripper_action,
            }
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
        panda_gripper_context = context.get('panda_gripper_delta_replay')
        if panda_gripper_context is not None:
            current_action = panda_gripper_context['action_trace_after_substeps'][substep_index]
            opening_m = panda_gripper_context['opening_trace_m'][substep_index]
        else:
            current_action = None
            opening_m = context['aggregate_opening_m']
        if substep_index == 0:
            target = prepared['target']
            receipt = prepared['writer_control']['canonical_action'].get('controller_receipt')
        else:
            source = env.value['source']
            target = env.controller.compute_pose_target(
                context['arm_resolution'], opening_m, state,
                task_artifact_hash=env.artifact.identity_hash,
                source_id=source.scene_source.source_id,
                source_closure_digest=source.source_closure_digest,
                provider_materialization_id=env.session.provider_materialization_id,
                episode_id=env.session.episode_id,
                reset_sample_id=env.sample.sample_id,
                state_revision=state_revision,
            )
            receipt = env.controller.last_control_receipt
        if panda_gripper_context is not None:
            receipt = {
                **dict(receipt),
                'panda_gripper_action_v1': {
                    'profile_id': panda_gripper_context['profile_id'],
                    'substep_index': substep_index,
                    'current_action': current_action,
                    'aggregate_opening_m': opening_m,
                },
            }
        if not isinstance(receipt, Mapping):
            raise TypeError('physics-rate OSC callback omitted its recomputation receipt')
        return {'target': target, 'controller_receipt': dict(receipt)}

    def observe_mixed_control(env, state):
        result = profile.observer(env, state)
        if env.value.get('panda_gripper_delta_replay_profile_id') in PANDA_GRIPPER_DELTA_PROFILE_IDS:
            gripper_state = env.value['panda_gripper_delta_replay_state']
            if state.control_step == 0:
                gripper_state.update({
                    'current_action': 0.0,
                    'committed_control_step': 0,
                    'pending': None,
                })
            else:
                pending = gripper_state.get('pending')
                if (not isinstance(pending, Mapping)
                        or pending.get('control_step') != state.control_step):
                    raise RuntimeError('PandaGripper replay action did not complete at its outer boundary')
                gripper_state.update({
                    'current_action': float(pending['current_action']),
                    'committed_control_step': int(state.control_step),
                    'pending': None,
                })
        return result

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
                             if not solution_profile else
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
                    'units': ['meter'] * 3 + ['unit_quaternion_wxyz'] * 4 + [
                        'normalized_panda_gripper_increment'
                        if env.value['action_schema']['schema_id'] == PANDA_GRIPPER_DELTA_ACTION_SCHEMA_ID
                        else 'normalized_absolute_gripper_target'
                    ],
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
                'hold_policy': env.controller.operational_config.hold_policy,
            },
            'control_plan': env.controller.identity_mapping(),
            'panda_gripper_action_profile': env.value.get('panda_gripper_delta_replay_profile_id'),
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
        }

    def validate_compiled_session(session, value):
        receipt = session.compiled_layout_receipt
        provider = receipt.get("provider")
        if provider == "geophys":
            return {
                "schema_version": "libero-pre-reset-layout-validation-v1",
                "provider": provider, "compiled_layout": receipt,
                "reset_not_yet_applied": True,
            }

        contract = task_source_contract_v1(value["artifact"].task_id)
        dimensions = receipt["dimensions"]
        expected_dimensions = (
            9 + 7 * len(contract.movable_instances) + len(contract.fixture_joint_names),
            9 + 6 * len(contract.movable_instances) + len(contract.fixture_joint_names),
            0, 9,
        )
        if (dimensions.get("nq"), dimensions.get("nv"), dimensions.get("na"), dimensions.get("nu")) != expected_dimensions:
            raise ValueError("compiled LIBERO dimensions differ from the locked source layout")
        scalar_qpos_start = 9 + 7 * len(contract.movable_instances)
        scalar_dof_start = 9 + 6 * len(contract.movable_instances)
        expected_scalar_addresses = {
            **{f"joint{i}": [i - 1, i - 1] for i in range(1, 8)},
            "finger_joint1": [7, 7], "finger_joint2": [8, 8],
            **{name: [scalar_qpos_start + index, scalar_dof_start + index]
               for index, name in enumerate(contract.fixture_joint_names)},
        }
        expected_free_addresses = {
            name: [9 + 7 * index, 9 + 6 * index]
            for index, name in enumerate(contract.movable_instances)
        }
        if (receipt["named_joint_addresses"] != expected_scalar_addresses
                or receipt["named_free_joint_addresses"] != expected_free_addresses):
            raise ValueError("compiled scalar joint order differs from the fixed source init layout")

        compiled_options = getattr(session, "compiled_model_options_receipt_v1", None)
        expected_profile = value.get("official_compiled_mujoco_profile_v1")
        if value.get("panda_gripper_delta_replay_profile_id") in PANDA_GRIPPER_DELTA_PROFILE_IDS:
            if not isinstance(compiled_options, Mapping):
                raise ValueError("PandaGripper replay requires the public compiled MuJoCo options receipt")
            if (compiled_options.get("schema_version") != "compiled-model-options-v1"
                    or compiled_options.get("provider") != "mujoco"
                    or compiled_options.get("backend") != "cpu"
                    or compiled_options.get("source_id") != receipt["source_id"]
                    or compiled_options.get("source_closure_digest") != receipt["source_closure_digest"]
                    or compiled_options.get("canonical_xml_sha256") != receipt["canonical_xml_sha256"]):
                raise ValueError("compiled MuJoCo options receipt is not bound to the admitted runtime source")
            if not isinstance(expected_profile, Mapping):
                raise ValueError("PandaGripper replay requires the frozen official compiled-model comparison profile")
            actual = tuple(compiled_options.get(key) for key in (
                "mujoco_runtime", "options", "model_sizes",
            ))
            expected = tuple(expected_profile.get(key) for key in (
                "mujoco_runtime", "options", "model_sizes",
            ))
            if any(not isinstance(row, Mapping) for row in (*actual, *expected)):
                raise ValueError("compiled MuJoCo options receipt or expected profile is incomplete")
            for section, actual_section, expected_section in zip(
                    ("mujoco_runtime", "options", "model_sizes"), actual, expected, strict=True):
                for key, expected_value in expected_section.items():
                    measured = actual_section.get(key)
                    equal = (
                        tuple(measured) == tuple(expected_value)
                        if isinstance(expected_value, list) else measured == expected_value
                    )
                    if not equal:
                        raise ValueError(f"compiled MuJoCo {section}.{key} differs from the pinned official model")
            options = compiled_options["options"]
            if (options.get("integrator_name") != "euler"
                    or options.get("solver_name") != "newton"
                    or options.get("cone_name") != "elliptic"):
                raise ValueError("compiled MuJoCo option enum names differ from the pinned LIBERO profile")
        return {
            "schema_version": "libero-pre-reset-compiled-validation-v1",
            "runtime_identity": session.runtime_identity,
            "compiled_layout": receipt,
            "compiled_model_options_v1": compiled_options,
            "compiled_model_physics_fingerprint_stage": "post_reset_before_first_physics_step",
            "reset_not_yet_applied": True,
        }

    def validate_post_reset_compiled_session(session, value):
        if value.get('panda_gripper_delta_replay_profile_id') not in PANDA_GRIPPER_DELTA_PROFILE_IDS:
            return None
        if session.compiled_layout_receipt.get('provider') == 'geophys':
            return {
                'schema_version': 'libero-cross-provider-compiled-fingerprint-status-v1',
                'provider': 'geophys',
                'status': 'MUJOCO_COMPILED_FINGERPRINT_NOT_APPLICABLE',
                'source_id': value['source'].scene_source.source_id,
                'source_closure_digest': value['source'].source_closure_digest,
            }
        expected_profile = value.get('official_compiled_mujoco_profile_v1')
        expected = (
            None if not isinstance(expected_profile, Mapping)
            else expected_profile.get('compiled_model_physics_fingerprint_v1')
        )
        actual = getattr(session, 'compiled_model_physics_fingerprint_v1', None)
        if (not isinstance(actual, Mapping) or not isinstance(expected, Mapping)
                or actual.get('schema_version') != 'compiled-model-physics-fingerprint-v1'
                or expected.get('schema_version') != 'compiled-model-physics-fingerprint-v1'):
            raise ValueError('post-reset LIBERO replay requires source-bound physical-model fingerprints')

        bookkeeping_dimensions = {'nbuffer', 'npaths'}
        render_only_arrays = {'site_rgba', 'geom_rgba'}
        actual_dimensions = actual.get('model_dimensions')
        expected_dimensions = expected.get('model_dimensions')
        actual_names = actual.get('object_names')
        expected_names = expected.get('object_names')
        actual_arrays = actual.get('numeric_array_fields')
        expected_arrays = expected.get('numeric_array_fields')
        if not all(isinstance(row, Mapping) for row in (
                actual_dimensions, expected_dimensions, actual_names, expected_names,
                actual_arrays, expected_arrays)):
            raise ValueError('post-reset LIBERO model fingerprint omitted dimensions, names or arrays')

        physical_dimensions_actual = {
            key: val for key, val in actual_dimensions.items()
            if key not in bookkeeping_dimensions
        }
        physical_dimensions_expected = {
            key: val for key, val in expected_dimensions.items()
            if key not in bookkeeping_dimensions
        }
        if physical_dimensions_actual != physical_dimensions_expected:
            raise ValueError('post-reset LIBERO physical model dimensions differ from the official compile')
        if actual_names != expected_names:
            raise ValueError(
                'post-reset LIBERO object names/order differ from the official compile: '
                + json.dumps(_compiled_physics_fingerprint_diff_v1(actual, expected),
                             sort_keys=True, separators=(',', ':'))
            )
        physical_array_differences = {
            key: {'actual': actual_arrays.get(key), 'expected': expected_arrays.get(key)}
            for key in sorted(set(actual_arrays) | set(expected_arrays))
            if key not in render_only_arrays and actual_arrays.get(key) != expected_arrays.get(key)
        }
        if physical_array_differences:
            reset_readback = getattr(session, 'reset_readback_v1', None)
            fixture_readback = (
                None if reset_readback is None else {
                    name: {
                        'position': list(pose.position),
                        'quaternion_wxyz': list(pose.quaternion_wxyz),
                    }
                    for name, pose in reset_readback.fixture_pose_world.items()
                }
            )
            raise ValueError(
                'post-reset LIBERO physical model arrays differ from the official compile: '
                + json.dumps({
                    'array_differences': physical_array_differences,
                    'fixture_readback_world': fixture_readback,
                }, sort_keys=True, separators=(',', ':'))
            )
        return {
            'schema_version': 'libero-post-reset-compiled-validation-v1',
            'boundary': 'after_nonintegrating_reset_before_first_physics_step',
            'native_physics_steps_at_validation': 0,
            'runtime_identity': session.runtime_identity,
            'compiled_model_physics_fingerprint_v1': actual,
            'official_compiled_model_binary_sha256': expected.get('compiled_model_binary_sha256'),
            'candidate_compiled_model_binary_sha256': actual.get('compiled_model_binary_sha256'),
            'bookkeeping_dimension_differences': {
                key: {'actual': actual_dimensions.get(key), 'expected': expected_dimensions.get(key)}
                for key in sorted(bookkeeping_dimensions)
                if actual_dimensions.get(key) != expected_dimensions.get(key)
            },
            'render_only_array_differences': {
                key: {'actual': actual_arrays.get(key), 'expected': expected_arrays.get(key)}
                for key in sorted(render_only_arrays)
                if actual_arrays.get(key) != expected_arrays.get(key)
            },
            'physical_dimensions_equal': True,
            'object_names_and_order_equal': True,
            'physical_array_fields_equal': True,
            'reset_not_integrated': True,
        }

    def validate_external_solution(value, solution):
        from bench_deploy.libero.tasks.solution import (
            LiberoPickPlaceSolutionV8, solution_identity_v8,
        )
        if not isinstance(solution, LiberoPickPlaceSolutionV8):
            raise TypeError('LIBERO task #1 external lifecycle requires the final V8 Solution')
        expected_source = value['source_sha256']['runtime_model_xml']
        expected_closure = value['source_sha256']['source_closure_digest']
        expected_resolver_identity = value['arm_resolver_identity']
        if (solution.task_uid != value['artifact'].task_id
                or solution.source_xml_sha256 != expected_source
                or solution.source_closure_digest != expected_closure
                or solution.identity != value.get('solution_identity')
                or solution.arm_resolver_identity
                   != expected_resolver_identity
                or solution.identity != solution_identity_v8(
                    expected_source, expected_closure,
                    arm_resolver_identity=expected_resolver_identity,
                )):
            raise ValueError('external LIBERO Solution does not match the selected task/source/profile')

    binding = ReferenceTaskBinding(
        build=lambda provider: build_value(provider, 'cpu'),
        reset_sample=lambda artifact, seed: reset_with_options(
            artifact, seed, {'init_row_index': 0}, value_for_artifact(artifact)['source'],
        ),
        evaluate=evaluate,
        object_poses=(profile.object_poses or
                      tuple((name, name) for name in contract.movable_instances)),
        external_actions=True, interval_mode='grouped', recorder_mode='canonical',
        reset_seed=lambda seed: seed,
        runtime_episode_identity=True,
        build_mixed_control_profile=build_value,
        build_external=(lambda provider: build_value(provider, 'cpu'))
        if solution_profile and not panda_gripper_delta_replay else None,
        validate_external_solution=validate_external_solution
        if solution_profile and not panda_gripper_delta_replay else None,
        reset_sample_with_options=reset_with_options,
        prepare_mixed_control=prepare_mixed_control,
        prepare_mixed_control_substep=prepare_mixed_control_substep,
        observe_mixed_control=observe_mixed_control,
        mixed_record_metadata=mixed_record_metadata,
        pre_reset_session_validator=validate_compiled_session,
        post_reset_session_validator=validate_post_reset_compiled_session,
        close_task_resources=close_task_resources,
    )
    env = SelectedReferenceEnv.from_mixed_control_candidate(
        binding, provider=provider, backend='cpu', horizon=horizon,
    )
    env_holder['env'] = env
    if solution_profile:
        env.metadata.update({
            'provider': provider, 'backend': 'cpu',
            'solution_identity': env.value['solution_identity'],
            'source_xml_sha256': env.value['source_sha256']['runtime_model_xml'],
            'source_closure_digest': env.value['source_sha256']['source_closure_digest'],
            'provider_import_projection': env.value['provider_import_projection'],
        })
    # The shared sample owner retains reset and source facts for the public
    # reset receipt; it is private recipe state, not a second runtime owner.
    env.value['reset_realizations'] = reset_receipts
    return env


__all__ = ['build_libero_selected_candidate']
