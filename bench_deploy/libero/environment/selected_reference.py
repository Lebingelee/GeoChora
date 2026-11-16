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
    ActionIntent, EntityDefinition, InitializationContract,
    SemanticDefinition, TaskArtifact, Timebase,
)
from task_env.assembly.compiler import (
    ReferenceTaskDeclarationV1,
    reference_task_identity_fields,
)
from task_env.assembly.source import TaskSceneSource
from task_env.controllers.canonical.contracts import (
    ControlGroupActionV1, MixedActuatorChannelV1, MixedActuatorPlanV1,
    StructuredActionRequestV1, digest,
)
from task_env.environment.configuration import resolve_env_config
from task_env.environment.task_source import TaskArtifactDeclarationV1
from task_env.runtime.sessions.source import (
    ExecutionSourceReceiptV1, RuntimeSource, source_asset_bytes,
)
from task_env.environment.types import ReferenceSpec, TaskCompositionSpec
from task_env.environment.reference_binding import ReferenceTaskBinding
from task_env.environment.reference_env import SelectedReferenceEnv

from bench_deploy.libero.controllers.osc import LiberoMixedControllerV6, LiberoMixedControllerV7
from bench_deploy.libero.tasks.predicates import (
    evaluate_on_bowl_plate_v1, evaluate_open_middle_drawer_v1,
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


def _libero_entity(name, kind, asset, *, frames=(), joints=(), source='source-authored-mesh'):
    return EntityDefinition(
        name, kind, f'asset:libero-{asset}-v1', frames, joints, source,
        'source-authored-collision', {},
    )


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
@dataclass(frozen=True)
class _TaskProfile:
    semantic_id: str
    semantic_entities: tuple[str, ...]
    semantic_parameters: tuple[tuple[str, float], ...]
    success_rule: str
    static_instances: tuple[str, ...]
    observer: Callable
    evaluator: Callable
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
        lambda evidence: evaluate_on_bowl_plate_v1(
            evidence, expected_source_manifest_sha256=PILOT_SOURCE_MANIFEST_SHA256,
        ),
        (('akita_black_bowl_1', 'bowl'), ('plate_1', 'plate')),
    ),
    TASK_2: _TaskProfile(
        'libero_open_middle_drawer_source_predicate_v1',
        ('panda-v1/ee', 'wooden_cabinet_1', 'main_table'),
        (('middle_drawer_open_threshold_m', -0.14),),
        'libero_open_middle_drawer_joint_position_lt_minus_0_14m_v1',
        ('wine_rack_1',),
        observe_task23_reference_v1,
        lambda evidence: evaluate_open_middle_drawer_v1(
            evidence, expected_boundary=getattr(evidence, 'boundary', None),
        ),
    ),
    TASK_3: _TaskProfile(
        'libero_plate_front_of_stove_source_predicate_v1',
        ('panda-v1/ee', 'main_table', 'plate_1', 'flat_stove_1'),
        (('stove_front_xy_half_extent_m', 0.01),),
        'libero_site_object_under_plate_and_stove_front_v1',
        ('wine_rack_1',),
        observe_task23_reference_v1,
        lambda evidence: evaluate_stove_front_region_v1(
            evidence, expected_boundary=getattr(evidence, 'boundary', None),
        ),
    ),
}


class _LiberoMJCFReferenceScene:
    """Task-local names required to compile the already-authored LIBERO MJCF."""

    uid = 'libero-spatial-bowl-to-plate-source-mjcf-v1'

    def __init__(self, reference_spec: ReferenceSpec):
        self._reference_spec = reference_spec

    def reference_spec(self):
        return self._reference_spec


def _geophys_importer_site_projection_v1(
    xml_bytes: bytes, *, task_uid: str = TASK_1, source_model_id: str | None = None,
):
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
    project_fluid_options = (
        task_uid in {TASK_2, TASK_3}
        or (
            task_uid == TASK_1
            and source_model_id == 'libero-official-runtime-source-profile-v4'
        )
    )
    if project_fluid_options:
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
                    **({
                        'row0_static_fluid_force_N': 0.0,
                        'maximum_force_fraction_of_object_weight_at_0_3m_s_translation_and_0_5rad_s_rotation': 0.0062,
                        'evidence': 'workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/libero_a123_closeout_20261101_001/fluid_effect_check_retry003_resource_receipt.json',
                    } if task_uid in {TASK_2, TASK_3} else {
                        'status': 'NOT_MEASURED_FOR_TASK1',
                        'reason': 'the frozen fluid-effect probe covers task2/task3 source rows only',
                    }),
                },
            })
            fluid_projection = removed
    ET.fromstring(projected_xml)
    return projected_xml, {
        'schema_version': (
            'libero-geophys-importer-projection-v3'
            if fluid_projection is not None and task_uid == TASK_1 else
            'libero-geophys-importer-projection-v2' if fluid_projection is not None
            else 'libero-geophys-importer-site-projection-v1'
        ),
        'task_uid': task_uid,
        'transformations': transformations,
    }


def _mapping_differences(
    actual, expected, *, exclude=(), keys=None, sequence_values=False,
    missing_is_difference=True,
):
    compared = set(expected) if keys is None else set(keys)
    if keys is None:
        compared |= set(actual)
    differences = {}
    for key in sorted(compared - set(exclude)):
        actual_value, expected_value = actual.get(key), expected.get(key)
        equal = (
            tuple(actual_value) == tuple(expected_value)
            if sequence_values and isinstance(expected_value, list)
            else actual_value == expected_value
        )
        if ((missing_is_difference and (key not in actual or key not in expected))
                or not equal):
            differences[key] = {'actual': actual_value, 'expected': expected_value}
    return differences


def _artifact_declaration(init_bytes: bytes, *, execution_profile: str,
                          provider: str = 'mujoco', task_uid: str = TASK_1) -> TaskArtifactDeclarationV1:
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
        _libero_entity(
            'panda-v1', 'embodiment', 'mounted-panda', frames=('panda-v1/ee',),
            joints=joints[:9], source='pinned_mounted_panda_mjcf',
        ),
        _libero_entity('main_table', 'scene', 'tabletop', source='source-authored-tabletop'),
    ]
    for instance in contract.movable_instances:
        shared_entities.append(_libero_entity(instance, 'movable', instance.rsplit('_', 1)[0]))
    shared_entities.extend((
        _libero_entity('wooden_cabinet_1', 'static', 'wooden-cabinet',
                       joints=joints[9:12], source='source-authored-articulated-fixture'),
        _libero_entity('flat_stove_1', 'static', 'flat-stove',
                       joints=(joints[12],), source='source-authored-articulated-fixture'),
    ))
    for instance in profile.static_instances:
        asset_slug = instance.rsplit('_', 1)[0].replace('_', '-')
        shared_entities.append(_libero_entity(
            instance, 'static', asset_slug, source='source-authored-static-fixture',
        ))
    entities = tuple(shared_entities)
    from task_env.runtime.sessions.api import CAPABILITIES

    required_capabilities = (
        tuple(CAPABILITIES) + ('joint_torque_actuation',)
        if provider == 'geophys'
        else tuple(CAPABILITIES) + ('contact_detection',)
    )
    return TaskArtifactDeclarationV1(
        artifact_id=(ARTIFACT_ID if task_uid == TASK_1 else f'libero/{task_uid.rsplit("/", 1)[-1]}/mixed-v1')
            if not solution_profile else
            (ARTIFACT_ID + '/solution-v8' if task_uid == TASK_1 else
             f'libero/{task_uid.rsplit("/", 1)[-1]}/solution-v8'),
        task_id=task_uid, version='diagnostic-v1' if not solution_profile else 'diagnostic-solution-v8',
        entities=entities,
        action=ActionIntent('absolute_pose', 'world', 'quaternion_wxyz', 'arm_joint_position_and_gripper'),
        observations=('canonical-state-v0', 'task-contact-summary-v2'),
        initialization=InitializationContract(
            'initialization-v0', {}, {name: float(qpos[name]) for name in joints}, (),
            'restore_source_named_pruned_init_row', 'pinned_libero_normal_reset_v1', 0,
        ),
        semantics=SemanticDefinition(
            'semantics-v0', profile.semantic_id, profile.semantic_entities, joints,
            dict(profile.semantic_parameters), profile.success_rule,
        ),
        timebase=Timebase(0.002, 25, 0.05), capabilities=required_capabilities,
    )


def _compile_artifact_declaration(declaration: TaskArtifactDeclarationV1) -> TaskArtifact:
    artifact = declaration.compile()
    if tuple(artifact.initialization.joint_position) != tuple(artifact.semantics.required_joints):
        raise ValueError('LIBERO initialization field order differs from the source row projection')
    return artifact


def _artifact(init_bytes: bytes, *, execution_profile: str,
              provider: str = 'mujoco', task_uid: str = TASK_1) -> TaskArtifact:
    return _compile_artifact_declaration(_artifact_declaration(
        init_bytes, execution_profile=execution_profile, provider=provider, task_uid=task_uid,
    ))
    if tuple(artifact.initialization.joint_position) != tuple(joints):
        raise ValueError('LIBERO initialization field order differs from the source row projection')
    return artifact


def _build_fixed_source(*, xml_path: Path, xml_bytes_override: bytes | None,
                        install_root: Path, composition_plan_path: Path,
                        init_path: Path, horizon: int, execution_profile: str,
                        provider: str = 'mujoco', task_uid: str = TASK_1,
                        gripper_action_profile: str | None = None,
                        official_nullspace_reference_joint_position_rad=None,
                        official_compiled_mujoco_profile_v1=None, source_only=False):
    if source_only and (provider != 'mujoco' or execution_profile != 'a-reference' or task_uid != TASK_1
                        or gripper_action_profile is not None):
        raise ValueError('source-only construction supports the declared MuJoCo task1 route')
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
    official_runtime_source_profile = (
        source_model_id == 'libero-official-runtime-source-profile-v4'
    )
    official_model_layout = compile_first_official_model or official_runtime_source_profile
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
    artifact_declaration = _artifact_declaration(
        init_bytes, execution_profile=execution_profile, provider=provider, task_uid=task_uid,
    )
    artifact = _compile_artifact_declaration(artifact_declaration)

    importer_xml = runtime_model_xml_bytes
    importer_projection = {
        'schema_version': 'libero-geophys-importer-site-projection-v1',
        'task_uid': task_uid,
        'transformations': [],
    }
    if provider == 'geophys':
        importer_xml, importer_projection = _geophys_importer_site_projection_v1(
            runtime_model_xml_bytes, task_uid=task_uid, source_model_id=source_model_id,
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
        'main_table': 'table' if official_model_layout or task_uid != TASK_1 else 'main_table',
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
    arm_resolver = arm_resolver_identity = controller = None
    arm_resolver_max_iterations = arm_resolver_position_tolerance_m = None
    arm_resolver_orientation_tolerance_rad = None
    if not source_only:
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
    mixed_plan = None
    if not source_only:
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
    reference_declaration = ReferenceTaskDeclarationV1(
        artifact=artifact_declaration,
        composition=TaskCompositionSpec(
            task_uid=task_uid, scene_uid=config.scene.scene_uid,
            success_definition=config.task.success_definition,
        ),
        bodies=bound_bodies,
        frames=frames,
        free_joints=free_joints,
        joint_targets={}, open_actuators=(),
        joints=joints,
    )
    source = reference_declaration.compile_source(
        artifact, scene_source=scene_source, config=config,
        scene=provider_reference_scene,
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
    construction_identity = reference_task_identity_fields(
        artifact, source, controller, include_runtime_config_sha256=False,
    )
    return {
        'artifact': artifact, 'source': source, 'controller': controller,
        'selected_controller_kind': 'mixed_actuator_v1', 'solution': None,
        'source_manifest_sha256': source_manifest_sha256,
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
            'artifact_identity_hash': construction_identity['artifact_sha256'],
            'source_id': source.scene_source.source_id,
            'source_closure_digest': source.source_closure_digest,
            'controller_identity': construction_identity['controller_identity'],
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
        'init_bytes': init_bytes,
        'source_manifest': source_manifest,
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
    controller_profile: str = 'direct_joint_effort_v1',
    _official_nullspace_reference_joint_position_rad=None,
    _official_compiled_mujoco_profile_v1=None,
):
    """Construct the fixed LIBERO candidate through the existing Core route.

    The migrated task1 MuJoCo route selects declared physical Controllers.
    Historical mixed-control callers remain explicitly unavailable.
    """
    if controller_profile not in {'direct_joint_effort_v1', 'source_osc_pose_v1'}:
        raise ValueError('unsupported mounted Panda Controller selection')
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
    if (provider != 'mujoco' or task_uid != TASK_1 or _execution_profile != 'a-reference'
            or _gripper_action_profile is not None):
        from task_env.environment.types import StageUnavailableError
        raise StageUnavailableError('this LIBERO route still requires retired mixed-control lifecycle; only MuJoCo task1 physical Controllers are migrated')
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
    from task_env.artifacts import ResetPlanV1, ResetSampleV1
    from task_env.assembly.compiler import CompiledReferenceTaskV1
    from task_env.environment.reference_binding import SourceBoundTaskBuilder
    from bench_deploy.libero.assembly.scene_declaration import bind_libero_default_source

    def compile_source(request):
        xml_bytes = None if xml is None else (xml.encode('utf-8') if isinstance(xml, str) else bytes(xml))
        legacy = _build_fixed_source(xml_path=Path(xml_path), xml_bytes_override=xml_bytes,
            install_root=install_root, composition_plan_path=Path(composition_plan_path),
            init_path=Path(init_path), horizon=request.horizon, execution_profile='a-reference',
            provider=request.provider, task_uid=task_uid, source_only=True)
        original = legacy['source']
        try:
            initial, _ = sample_libero_normal_reset_v1(init_bytes=legacy['init_bytes'],
                install_root=install_root, source_manifest=legacy['source_manifest'],
                task_artifact_hash=legacy['artifact'].identity_hash, source_id=original.source_id,
                source_closure_digest=original.source_closure_digest, task_seed=request.seed, init_row_index=0)
            task_source, artifact, source, robot, execution, intent, remap = bind_libero_default_source(
                source=original, legacy_artifact=legacy['artifact'], initial_poses=initial.poses_world,
                controller_profile=controller_profile)
        except BaseException as error:
            try:
                original.execution_source_receipt.close()
            except BaseException as cleanup_error:
                error.add_note(f'LIBERO source cleanup also failed: {cleanup_error!r}')
            raise
        return CompiledReferenceTaskV1(artifact, source, execution.controllers[0]), (
            legacy, task_source, robot, execution, intent, remap)

    def compile_control(compiled, context, _selection, _request):
        legacy, task_source, robot, physical, intent, remap = context
        controller = physical.controllers[0]
        identity = reference_task_identity_fields(compiled.artifact, compiled.source,
                                                   controller)
        return {**legacy, 'artifact': compiled.artifact, 'source': compiled.source,
            'controller': controller, 'physical_execution': physical,
            'selected_controller_kind': 'physical_effort_v1',
            'selected_controller_profile_id': controller_profile, 'solution': None,
            'task_source': task_source, 'composition_intent': intent,
            'reset_joint_remap': remap, 'legacy_reset_source_id': legacy['source'].source_id,
            'legacy_reset_closure': legacy['source'].source_closure_digest,
            'construction_id': digest(identity), 'resolved_configuration': identity,
            'solution_profile': False}

    def reset_plan(value, request):
        sample, _ = sample_libero_normal_reset_v1(init_bytes=value['init_bytes'],
            install_root=install_root, source_manifest=value['source_manifest'],
            task_artifact_hash=value['artifact'].identity_hash,
            source_id=value['legacy_reset_source_id'], source_closure_digest=value['legacy_reset_closure'],
            task_seed=request.seed, init_row_index=0)
        fields = sample.to_mapping()
        fields.pop('sample_id')
        fields.update(source_id=value['source'].source_id,
                      source_closure_digest=value['source'].source_closure_digest)
        for name in ('joint_position', 'joint_velocity'):
            fields[name] = {value['reset_joint_remap'][key]: item for key, item in fields[name].items()}
        return ResetPlanV1('reset-plan-v1', ResetSampleV1.create(**fields), 'task_episode')

    def observation_spaces(_env):
        return {'state': Dict({'ee_pose': Box(-np.inf, np.inf, (7,), dtype=np.float32),
            'joint_position': Box(-np.inf, np.inf, (9,), dtype=np.float32),
            'boundary_identity_sha256': Box(0, 255, (32,), dtype=np.uint8)}),
            'privileged_state': Dict({key + '_body_pose': Box(-np.inf, np.inf, (1, 7), dtype=np.float32)
                                      for _, key in profile.object_poses})}

    builder = SourceBoundTaskBuilder(compile_source, reset_plan, backend='cpu', reuse_source=True,
        allow_sampled_reset=False, compile_control=compile_control)
    binding = ReferenceTaskBinding(build=builder, reset_sample=lambda _artifact, _seed: None,
        evaluate=lambda evidence, _semantics: profile.evaluator(evidence), object_poses=profile.object_poses,
        external_actions=True, interval_mode='grouped', recorder_mode='execution',
        action_schema={'schema_version': 'physical-control-actions-v1',
            'schema_id': ('mounted-panda-joint-effort-v1' if controller_profile == 'direct_joint_effort_v1'
                          else 'mounted-panda-world-tcp-pose-v1'),
            'mode': 'joint_effort' if controller_profile == 'direct_joint_effort_v1' else 'absolute_pose',
            'components': (tuple(f'robot0_joint{i}' for i in range(1, 8))
                           if controller_profile == 'direct_joint_effort_v1'
                           else ('x', 'y', 'z', 'qw', 'qx', 'qy', 'qz'))},
        prepare_action=lambda action: action, observation_space_factory=observation_spaces,
        observation_projection=profile.observer)
    return SelectedReferenceEnv.from_task_binding(binding, provider=provider, backend='cpu', horizon=horizon)


__all__ = ['build_libero_selected_candidate']
