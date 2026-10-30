#!/usr/bin/env python3
"""Independent H5/T+1 validator for the bounded F05 GeoPhys S1 profile."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import h5py
import numpy as np

REPO = Path('/home/lly/Program_Files/Geochora')
BASE = REPO / 'workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001'
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from task_env.artifacts.state import StateBoundaryIdentity, decode_canonical_state_view
from task_env.controllers.canonical.contracts import digest
from task_env.recorders import load_structured_control_records_h5
from task_env.runtime.sessions.leaf_control import GeoPhysHostModelProducerIdentityV1


class ReaderReject(ValueError):
    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason = reason


def _seconds_match(actual, expected):
    if isinstance(actual, bool) or type(actual) not in (int, float):
        return False
    return math.isfinite(float(actual)) and math.isclose(
        float(actual), float(expected), rel_tol=0.0, abs_tol=1e-12,
    )


def _fingerprint_fields(fields):
    payload = json.dumps(fields, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest()


def _observation_fields(path: Path, index: int):
    fields = {}
    with h5py.File(path, 'r') as root:
        def visit(name, item):
            if not isinstance(item, h5py.Dataset):
                return
            value = np.asarray(item[index])
            fields[name] = {
                'dtype': value.dtype.str,
                'shape': list(value.shape),
                'bytes_sha256': hashlib.sha256(value.tobytes(order='C')).hexdigest(),
            }
        root['obs'].visititems(visit)
    return fields


def _as_mapping(value):
    if hasattr(value, 'to_mapping'):
        return value.to_mapping()
    if isinstance(value, dict):
        return value
    raise ReaderReject('typed_record_missing', f'expected typed mapping, got {type(value).__name__}')


def _float32_half_ulp_tolerance(values):
    source = np.asarray(values, dtype=np.float64)
    quantized = source.astype(np.float32)
    return np.maximum(np.abs(np.spacing(quantized).astype(np.float64)) * 0.5, 1e-12)


def _numeric_row(root, dataset_path, index, expected, *, reason, label, quaternion=False):
    if dataset_path not in root:
        raise ReaderReject(reason, f'H5 is missing canonical observation resource {dataset_path}')
    stored = np.asarray(root[dataset_path][index])
    expected = np.asarray(expected, dtype=np.float64)
    if stored.dtype != np.dtype('<f4') or stored.shape != expected.shape:
        raise ReaderReject(reason, f'{label} H5 layout/dtype differs from the canonical typed field')
    actual = stored.astype(np.float64)
    tolerance = _float32_half_ulp_tolerance(expected)
    if quaternion:
        if actual.shape[-1] != 7:
            raise ReaderReject(reason, f'{label} pose is not xyz plus wxyz')
        if not bool(np.all(np.abs(actual[..., :3] - expected[..., :3]) <= tolerance[..., :3])):
            raise ReaderReject(reason, f'{label} position differs beyond float32 storage quantization')
        plus = np.abs(actual[..., 3:] - expected[..., 3:]) <= tolerance[..., 3:]
        minus = np.abs(actual[..., 3:] + expected[..., 3:]) <= tolerance[..., 3:]
        if not (bool(np.all(plus)) or bool(np.all(minus))):
            raise ReaderReject(reason, f'{label} quaternion differs beyond float32 storage quantization')
    elif not bool(np.all(np.abs(actual - expected) <= tolerance)):
        raise ReaderReject(reason, f'{label} differs beyond float32 storage quantization')


def _producer_identity_from_contract(contract):
    mapping = contract.get('host_model_producer_identity')
    if not isinstance(mapping, dict):
        raise ReaderReject('producer_identity', 'F05 v2 input contract lacks actual host-model producer identity')
    try:
        identity = GeoPhysHostModelProducerIdentityV1(
            mapping['schema_version'], mapping['requested_target_build_identity'],
            mapping['repository_root'], mapping['origin_url'], mapping['commit_sha'],
            mapping['worktree_clean'], tuple(tuple(row) for row in mapping['module_sources']),
        )
        if mapping.get('identity_sha256') != identity.identity_sha256:
            raise ValueError('identity digest does not match its fields')
        identity.validate_current_tree()
    except Exception as error:
        raise ReaderReject('producer_identity', f'actual provider producer identity rejected: {error}') from error
    if contract.get('host_model_producer_identity_sha256') != identity.identity_sha256:
        raise ReaderReject('producer_identity', 'input contract producer identity hash differs from its full mapping')
    return identity


def _check_typed_numeric_observation(root, index, typed_raw, contract, receipt):
    joints = typed_raw.get('joints')
    if not isinstance(joints, list):
        raise ReaderReject('typed_joint_resources', f'boundary {index} has no typed joint resource list')
    joint_by_key = {}
    for row in joints:
        key = (row.get('entity_id'), row.get('joint_id')) if isinstance(row, dict) else None
        if key is None or key in joint_by_key:
            raise ReaderReject('typed_joint_resources', f'boundary {index} has missing/duplicate canonical Joint keys')
        joint_by_key[key] = row

    drives = receipt.get('drives')
    if not isinstance(drives, list) or len(drives) != 9:
        raise ReaderReject('receipt_dof_order', 'F05 receipt must contain nine named scalar drive rows')
    expected_names = [row.get('native_dof_name') for row in drives]
    if (expected_names != contract.get('native_dof_order')
            or any(type(name) is not str for name in expected_names)):
        raise ReaderReject('native_dof_order', 'contract DOF order differs from the ordered model-bound receipt')
    expected_keys = {
        (row['canonical_joint']['entity_id'], row['canonical_joint']['joint_id'])
        for row in drives
    }
    free_joint = contract.get('free_body_joint', {
        'entity_id': 'square-peg-instance', 'joint_id': 'floating_root',
    })
    if not isinstance(free_joint, dict) or set(free_joint) != {'entity_id', 'joint_id'}:
        raise ReaderReject('typed_joint_resources', 'F05 contract lacks an exact free-body Joint binding')
    free_key = (free_joint['entity_id'], free_joint['joint_id'])
    if set(joint_by_key) != expected_keys | {free_key}:
        raise ReaderReject('typed_joint_resources', f'boundary {index} canonical Joint resources differ from the bound source')

    by_name = {row['native_dof_name']: row for row in drives}
    positions = []
    for name in expected_names:
        drive = by_name[name]
        key = (drive['canonical_joint']['entity_id'], drive['canonical_joint']['joint_id'])
        state = joint_by_key[key]
        expected_position_unit = drive['position_unit']
        expected_velocity_unit = 'meter_per_second' if expected_position_unit == 'meter' else 'radian_per_second'
        if (state.get('schema_version'), state.get('position_representation'),
                state.get('velocity_representation'), len(state.get('position', ())),
                len(state.get('velocity', ()))) != (
                'typed-joint-state-v1', expected_position_unit, expected_velocity_unit, 1, 1):
            raise ReaderReject('typed_joint_unit', f'boundary {index} typed Joint unit/shape differs for {name}')
        values = (state['position'][0], state['velocity'][0])
        if any(type(value) not in (int, float) or isinstance(value, bool) or not math.isfinite(float(value))
               for value in values):
            raise ReaderReject('typed_joint_value', f'boundary {index} typed Joint values are non-finite for {name}')
        positions.append(float(values[0]))
    _numeric_row(root, 'obs/state/joint_position', index, positions,
                 reason='typed_joint_observation', label=f'boundary {index} named joint positions')

    frames = typed_raw.get('frames')
    if not isinstance(frames, list):
        raise ReaderReject('typed_frame_resources', f'boundary {index} has no typed frame resources')
    frame_by_key = {}
    for row in frames:
        raw = row.get('frame') if isinstance(row, dict) else None
        key = (raw.get('entity_id'), raw.get('frame_id')) if isinstance(raw, dict) else None
        if key is None or key in frame_by_key:
            raise ReaderReject('typed_frame_resources', f'boundary {index} has missing/duplicate canonical Frame keys')
        frame_by_key[key] = row
    frame_bindings = contract.get('typed_frame_bindings', {
        'hand': {'entity_id': 'panda-main', 'frame_id': 'hand'},
        'free_body': {'entity_id': 'square-peg-instance', 'frame_id': 'peg1'},
    })
    if not isinstance(frame_bindings, dict) or set(frame_bindings) != {'hand', 'free_body'}:
        raise ReaderReject('typed_frame_resources', 'F05 contract lacks hand/free-body Frame bindings')
    hand_key = (frame_bindings['hand'].get('entity_id'), frame_bindings['hand'].get('frame_id'))
    body_key = (frame_bindings['free_body'].get('entity_id'), frame_bindings['free_body'].get('frame_id'))
    if hand_key not in frame_by_key or body_key not in frame_by_key:
        raise ReaderReject('typed_frame_resources', f'boundary {index} is missing a recorded hand/free-body Frame')
    hand = frame_by_key[hand_key].get('pose_world', {})
    body = frame_by_key[body_key].get('pose_world', {})
    for label, pose in (('hand', hand), ('free body', body)):
        position, quaternion = pose.get('position'), pose.get('quaternion_wxyz')
        if (not isinstance(position, list) or len(position) != 3
                or not isinstance(quaternion, list) or len(quaternion) != 4
                or any(type(v) not in (int, float) or isinstance(v, bool) or not math.isfinite(float(v))
                       for v in (*position, *quaternion))):
            raise ReaderReject('typed_frame_value', f'boundary {index} {label} pose is invalid')
    _numeric_row(root, 'obs/state/hand_pose', index,
                 [*hand['position'], *hand['quaternion_wxyz']],
                 reason='typed_hand_pose', label=f'boundary {index} typed hand pose', quaternion=True)
    _numeric_row(root, 'obs/state/ee_pose', index,
                 [*hand['position'], *hand['quaternion_wxyz']],
                 reason='typed_hand_pose', label=f'boundary {index} typed hand/TCP pose', quaternion=True)
    body_dataset = 'obs/privileged_state/target_body_pose'
    if body_dataset not in root:
        raise ReaderReject('typed_free_body_pose', f'H5 is missing canonical free-body observation {body_dataset}')
    body_observation = np.asarray(root[body_dataset][index])
    if body_observation.shape != (1, 7) or body_observation.dtype != np.dtype('<f4'):
        raise ReaderReject('typed_free_body_pose', 'H5 free-body pose has wrong T+1 layout or storage dtype')
    _numeric_row(root, body_dataset, index, [
        [*body['position'], *body['quaternion_wxyz']],
    ], reason='typed_free_body_pose', label=f'boundary {index} typed free-body pose', quaternion=True)
    free_state = joint_by_key[free_key]
    if (free_state.get('position_representation') != 'xyz_meter_quaternion_wxyz'
            or free_state.get('velocity_representation') != 'linear_xyz_meter_per_second_angular_xyz_radian_per_second'
            or len(free_state.get('position', ())) != 7 or len(free_state.get('velocity', ())) != 6):
        raise ReaderReject('typed_free_body_unit', f'boundary {index} free-body Joint units/layout are invalid')
    if any(type(value) not in (int, float) or isinstance(value, bool) or not math.isfinite(float(value))
           for value in (*free_state['position'], *free_state['velocity'])):
        raise ReaderReject('typed_free_body_value', f'boundary {index} free-body pose/twist contains a non-finite value')
    if not np.allclose(np.asarray(free_state['position'], dtype=np.float64),
                       np.asarray([*body['position'], *body['quaternion_wxyz']], dtype=np.float64),
                       rtol=0.0, atol=1e-12):
        raise ReaderReject('typed_free_body_pose', f'boundary {index} free-body Joint and Frame poses differ')


def _validate_typed_unit_layout(typed_raw, contract, receipt, index):
    joints = typed_raw.get('joints')
    if not isinstance(joints, list):
        raise ReaderReject('typed_joint_resources', f'boundary {index} has no typed Joint list')
    by_key = {(row.get('entity_id'), row.get('joint_id')): row
              for row in joints if isinstance(row, dict)}
    for drive in receipt.get('drives', ()):
        key = (drive['canonical_joint']['entity_id'], drive['canonical_joint']['joint_id'])
        row = by_key.get(key)
        expected = drive['position_unit']
        expected_velocity = 'meter_per_second' if expected == 'meter' else 'radian_per_second'
        if row is None:
            raise ReaderReject('typed_joint_resources', f'boundary {index} is missing typed Joint {key}')
        if (row.get('position_representation'), row.get('velocity_representation')) != (
                expected, expected_velocity):
            raise ReaderReject('typed_joint_unit', f'boundary {index} typed Joint unit/layout differs for {key}')
    free = contract.get('free_body_joint', {
        'entity_id': 'square-peg-instance', 'joint_id': 'floating_root',
    })
    row = by_key.get((free.get('entity_id'), free.get('joint_id'))) if isinstance(free, dict) else None
    if row is None:
        raise ReaderReject('typed_joint_resources', f'boundary {index} is missing the free-body Joint')
    if (row.get('position_representation'), row.get('velocity_representation')) != (
            'xyz_meter_quaternion_wxyz',
            'linear_xyz_meter_per_second_angular_xyz_radian_per_second'):
        raise ReaderReject('typed_free_body_unit', f'boundary {index} free-body Joint units/layout are invalid')


def _read_typed_state_extension(root, observations, contract_schema):
    name = 'meta/f05_public_typed_state_witness_v1_json'
    if name not in root:
        if contract_schema == 'f05-s1-independent-input-contract-v2':
            raise ReaderReject('typed_state_h5_missing', 'F05 v2 H5 lacks the persisted public typed T+1 state extension')
        return None
    raw = root[name][()]
    try:
        extension = json.loads(raw.decode('utf-8') if isinstance(raw, bytes) else str(raw))
    except Exception as error:
        raise ReaderReject('typed_state_h5_decode', f'cannot decode F05 typed-state H5 extension: {error}') from error
    rows = extension.get('rows') if isinstance(extension, dict) else None
    if (extension.get('schema_version') != 'f05-public-typed-state-witness-v1'
            or extension.get('observation_count') != observations
            or not isinstance(rows, list) or len(rows) != observations):
        raise ReaderReject('typed_state_h5_layout', 'F05 typed-state H5 extension does not cover all T+1 observations')
    return rows


def validate_h5(path: Path, witness_path: Path, contract_path: Path):
    if not path.is_file():
        raise ReaderReject('h5_missing', 'H5 file is missing')
    witness = json.loads(witness_path.read_text(encoding='utf-8'))
    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    if witness.get('schema_version') != 'f05-public-boundary-witness-v1':
        raise ReaderReject('witness_schema', 'public witness schema is not F05')
    contract_schema = contract.get('schema_version')
    if contract_schema not in {
        'f05-s1-independent-input-contract-v1',
        'f05-s1-independent-input-contract-v2',
    }:
        raise ReaderReject('input_contract_schema', 'frozen input contract schema is not F05')
    producer_identity = None
    if contract_schema == 'f05-s1-independent-input-contract-v2':
        producer_identity = _producer_identity_from_contract(contract)
    actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if witness.get('h5_sha256') != actual_sha or Path(witness.get('h5_path', '')).resolve() != path.resolve():
        raise ReaderReject('witness_file_binding', 'public witness does not bind these exact closed H5 bytes')

    try:
        loaded = load_structured_control_records_h5(path)
    except Exception as error:
        detail = f'{type(error).__name__}: {error}'
        lowered = detail.lower()
        if 't/t+1' in lowered or 't+1' in lowered or 'observation count mismatch' in lowered:
            raise ReaderReject('t_plus_one_count', detail) from error
        if 'episodeoutcome' in lowered or 'episode identity mismatch' in lowered or 'boundaryevent' in lowered:
            raise ReaderReject('episode_outcome', detail) from error
        if 'ack' in lowered or 'target identity' in lowered or 'structured control' in lowered:
            raise ReaderReject('ack_identity', detail) from error
        raise ReaderReject('h5_decode', detail) from error
    transitions = loaded['transition_count']
    observations = loaded['observation_count']
    if transitions != 8 or observations != 9 or observations != transitions + 1:
        raise ReaderReject('t_plus_one_count', f'expected 8 transitions and 9 observations; got {transitions}/{observations}')
    if (witness.get('transition_count'), witness.get('observation_count')) != (transitions, observations):
        raise ReaderReject('witness_count', 'public witness counts differ from decoded H5 counts')
    public_rows = witness.get('public_boundaries')
    if not isinstance(public_rows, list) or len(public_rows) != observations:
        raise ReaderReject('t_plus_one_witness', 'public reset/step witness does not contain all T+1 boundaries')

    profile = loaded['env_meta'].get('reference_profile')
    if not isinstance(profile, dict):
        raise ReaderReject('profile_missing', 'F05 typed reference profile is absent')
    expected_profile = (
        'f05-geophys-usd-position-synthetic-io-s1-v1',
        'synthetic_fixture', False,
        'F05 public GeoPhys host-model synthetic S1; no provider solver or physics admission',
    )
    if (profile.get('profile_id'), profile.get('provenance_kind'), profile.get('runtime_admitted'),
            profile.get('recording_scope')) != expected_profile:
        raise ReaderReject('profile_classification', 'H5 profile is not the exact non-admitted synthetic F05 S1')
    if (contract_schema == 'f05-s1-independent-input-contract-v1'
            and any(profile.get(key) is not None for key in (
                'host_model_producer_identity', 'host_model_producer_identity_sha256',
                'typed_state_h5_witness_schema_version',
            ))):
        raise ReaderReject('input_contract_schema',
                           'F05 H5 with producer identity or typed-state extension requires a v2 contract')
    if (profile.get('source_validation_provenance_kind'), profile.get('source_verified')) != ('local-validated', False):
        raise ReaderReject('source_provenance', 'H5 source was upgraded from local validation or synthetic provenance')

    representation = profile.get('representation', {})
    if (representation.get('identity_sha256'), representation.get('provider'),
            representation.get('provider_build_identity'), representation.get('runtime_admitted'),
            representation.get('source_verified')) != (
            contract['representation']['identity_sha256'], 'geophys',
            contract['representation']['provider_build_identity'], False, False):
        raise ReaderReject('source_identity', 'H5 representation identity or admission state differs from frozen F05 input')
    if contract_schema == 'f05-s1-independent-input-contract-v2':
        producer_sha = producer_identity.identity_sha256
        if (representation.get('requested_target_build_identity'),
                profile.get('requested_target_build_identity'),
                profile.get('host_model_producer_identity_sha256'),
                profile.get('host_model_producer_identity'),
                profile.get('native_position_drive_receipt', {}).get('host_model_producer_identity_sha256')) != (
                producer_identity.requested_target_build_identity,
                producer_identity.requested_target_build_identity,
                producer_sha, producer_identity.to_mapping(), producer_sha):
            raise ReaderReject('producer_identity', 'H5 representation/host model/receipt do not bind the actual producer identity')
    if contract.get('family') != 'menagerie-panda':
        raise ReaderReject('source_family', 'this reader run is frozen to the Menagerie Panda S1 cell')

    source_expected = contract['delivery']
    delivery = profile.get('usd_delivery', {})
    frozen_bindings = json.loads((BASE / 'sol_f05_002/accepted_source_bindings.json').read_text())
    frozen_source = frozen_bindings['source_bindings']['menagerie-panda']
    from task_env.assembly.usd_delivery import load_usd_asset_delivery
    frozen_delivery_root = Path(frozen_source['delivery_root'])
    loaded_source = load_usd_asset_delivery(frozen_delivery_root / 'usd_delivery.json')
    frozen_delivery = loaded_source.delivery
    frozen_entry_sha = hashlib.sha256(loaded_source.file_bytes[frozen_delivery.entry_file]).hexdigest()
    frozen_report_sha = hashlib.sha256(loaded_source.report_bytes).hexdigest()
    frozen_values = {
        'source_reference': frozen_delivery.asset_definition.source_reference,
        'asset_identity_sha256': frozen_delivery.asset_identity_hash,
        'delivery_sha256': frozen_delivery.delivery_sha256,
        'closure_sha256': frozen_delivery.closure_sha256,
        'source_revision': frozen_delivery.source_revision,
        'entry_file': frozen_delivery.entry_file,
        'entry_sha256': frozen_entry_sha,
        'validation_report_sha256': frozen_report_sha,
    }


    if any(source_expected.get(key) != value for key, value in frozen_values.items()):
        raise ReaderReject('source_delivery', 'H5 input contract differs from independently loaded frozen delivery bytes')
    if any(frozen_source.get(key) != value for key, value in {
            'asset_identity_sha256': frozen_delivery.asset_identity_hash,
            'delivery_sha256': frozen_delivery.delivery_sha256,
            'delivery_closure_sha256': frozen_delivery.closure_sha256,
            'source_revision': frozen_delivery.source_revision,
            'entry_file': frozen_delivery.entry_file,
            'entry_sha256': frozen_entry_sha,
            'validation_report_sha256': frozen_report_sha,
    }.items()):
        raise ReaderReject('source_delivery', 'frozen F05 source binding no longer matches immutable delivery bytes')
    delivery_pairs = (
        ('asset_identity_sha256', source_expected['asset_identity_sha256']),
        ('delivery_sha256', source_expected['delivery_sha256']),
        ('closure_sha256', source_expected['closure_sha256']),
        ('source_revision', source_expected['source_revision']),
        ('entry_file', source_expected['entry_file']),
        ('validation_report_sha256', source_expected['validation_report_sha256']),
    )
    if any(delivery.get(key) != expected for key, expected in delivery_pairs):
        raise ReaderReject('source_delivery', 'H5 source delivery bytes/provenance differ from the input contract')

    receipt = profile.get('native_position_drive_receipt')
    if receipt != contract.get('native_position_drive_receipt'):
        raise ReaderReject('receipt_payload', 'H5 native-drive receipt payload differs from the independently frozen input contract')
    if profile.get('native_position_drive_receipt_identity_sha256') != contract['receipt_identity_sha256']:
        raise ReaderReject('receipt_identity', 'H5 native-drive receipt identity differs from the frozen F05 input')
    if profile.get('public_model_identity_sha256') != contract['public_model_identity_sha256']:
        raise ReaderReject('public_model_identity', 'H5 public-model identity differs from the frozen input')
    if contract_schema == 'f05-s1-independent-input-contract-v2':
        if (profile.get('native_runtime_io_metadata', {}).get('host_model_producer_identity_sha256')
                != producer_identity.identity_sha256):
            raise ReaderReject('producer_identity', 'NativeRuntimeIO metadata does not bind the actual host-model producer')
    if (profile.get('source_id'), profile.get('source_closure_sha256'),
            profile.get('task_source_identity_sha256'), profile.get('task_artifact_identity_sha256'),
            profile.get('scene_identity_sha256'), profile.get('execution_identity_sha256')) != (
            contract['source_id'], contract['source_closure_sha256'],
            contract['task_source_identity_sha256'], contract['task_artifact_identity_sha256'],
            contract['scene_identity_sha256'], contract['execution_identity_sha256']):
        raise ReaderReject('source_execution_identity', 'H5 source/TaskSource/Artifact/Scene/Execution bindings differ')

    execution = profile.get('execution_spec_v1', {})
    if (execution.get('schema_version'), execution.get('physics_provider'), execution.get('physics_backend'),
            execution.get('physics_profile'), execution.get('physics_device'),
            execution.get('determinism_mode')) != (
            'execution-spec-v1', 'geophys', 'cpu', 'geophys-usd-position-f05-s1-v1', 'cpu', 'best_effort'):
        raise ReaderReject('execution_profile', 'H5 ExecutionSpec does not identify the exact GeoPhys CPU F05 profile')

    metadata = profile.get('native_runtime_io_metadata', {})
    if (metadata.get('physics_provider'), metadata.get('provider_build_identity'), metadata.get('backend'),
            metadata.get('device'), metadata.get('execution_identity_sha256'),
            metadata.get('source_id'), metadata.get('source_closure_sha256'),
            metadata.get('scene_identity_sha256'), metadata.get('task_artifact_identity_sha256'),
            metadata.get('physics_dt_s'), metadata.get('control_substeps')) != (
            'geophys', contract['representation']['provider_build_identity'], 'cpu', 'cpu',
            contract['execution_identity_sha256'], contract['source_id'], contract['source_closure_sha256'],
            contract['scene_identity_sha256'], contract['task_artifact_identity_sha256'], 0.002, 5):
        raise ReaderReject('native_io_metadata', 'H5 native-I/O metadata differs from source or ExecutionSpec')
    expected_names = contract['native_dof_order']
    if metadata.get('native_dof_names') != expected_names:
        raise ReaderReject('native_dof_order', 'H5 named DOF metadata order differs from the model-bound receipt')

    with h5py.File(path, 'r') as root:
        attrs = root.attrs
        if int(attrs.get('transition_count', -1)) != transitions or int(attrs.get('observation_count', -1)) != observations:
            raise ReaderReject('h5_attributes', 'H5 v3 root counts disagree with independently decoded counts')
        stored = np.asarray(root['obs/state/boundary_identity_sha256'][...])
        if stored.shape != (observations, 32) or stored.dtype != np.uint8:
            raise ReaderReject('boundary_dataset_shape', 'T+1 boundary digest dataset has wrong shape or type')
        typed_extension_rows = _read_typed_state_extension(root, observations, contract_schema)

    boundaries = []
    for index, entry in enumerate(public_rows):
        try:
            boundary = StateBoundaryIdentity.from_mapping(entry.get('state_boundary_identity', {}))
            boundary.validate()
        except Exception as error:
            raise ReaderReject('boundary_identity', f'boundary {index} is invalid: {error}') from error
        if entry.get('state_boundary_id') != boundary.boundary_id:
            raise ReaderReject('boundary_identity', f'boundary {index} digest does not match its public fields')
        if (type(entry.get('control_step')) is not int or entry['control_step'] != index
                or boundary.control_step != index or boundary.state_revision != index
                or not _seconds_match(entry.get('simulation_time_s'), index * 0.01)):
            raise ReaderReject('boundary_clock', f'public boundary {index} has stale step/revision/clock')
        clock = entry.get('state_sample_clock')
        if (not isinstance(clock, dict) or (clock.get('schema_version'), clock.get('clock_domain'),
                clock.get('sample_index')) != ('state-sample-clock-v1', 'evaluation_boundary', index)
                or not _seconds_match(clock.get('simulation_time_s'), index * 0.01)):
            raise ReaderReject('boundary_clock', f'public boundary {index} has an invalid sample clock')
        if (boundary.reset_sample_id != profile.get('reset_sample_id')
                or boundary.scene_identity_hash != contract['scene_identity_sha256']):
            raise ReaderReject('boundary_source_identity', f'public boundary {index} reset/source identity mismatch')
        with h5py.File(path, 'r') as root:
            stored_digest = bytes(np.asarray(root['obs/state/boundary_identity_sha256'][index]))
        if stored_digest != bytes.fromhex(boundary.boundary_id.removeprefix('state-boundary-')):
            raise ReaderReject('boundary_digest', f'H5 boundary digest row {index} differs from public boundary')
        fields = _observation_fields(path, index)
        if fields != entry.get('observation_fields'):
            raise ReaderReject('observation_witness', f'H5 observation row {index} differs from public reset/step values')
        if entry.get('observation_identity_sha256') != _fingerprint_fields(fields):
            raise ReaderReject('observation_fingerprint', f'public observation row {index} fingerprint is invalid')
        typed_raw = entry.get('canonical_state_view_v1')
        if not isinstance(typed_raw, dict):
            raise ReaderReject('typed_state_missing', f'public boundary {index} has no typed state view')
        _validate_typed_unit_layout(typed_raw, contract, receipt, index)
        try:
            view = decode_canonical_state_view(typed_raw)
            view.validate()
        except Exception as error:
            detail = f'{type(error).__name__}: {error}'
            reason = 'typed_joint_unit' if 'joint representations disagree' in detail else 'typed_state_decode'
            raise ReaderReject(reason, f'public typed state row {index} is invalid: {detail}') from error
        if view.boundary.to_mapping() != boundary.to_mapping():
            raise ReaderReject('typed_state_boundary', f'typed state row {index} differs from its boundary')
        if view.sample_clock.to_mapping() != clock:
            raise ReaderReject('typed_state_clock', f'typed state row {index} differs from its public sample clock')
        if typed_extension_rows is not None:
            extension_row = typed_extension_rows[index]
            if (extension_row.get('boundary_index') != index
                    or extension_row.get('state_boundary_identity') != boundary.to_mapping()
                    or extension_row.get('state_sample_clock') != clock):
                raise ReaderReject('typed_state_h5_boundary', f'H5 typed-state extension row {index} has wrong boundary/clock')
            if extension_row.get('canonical_state_view_v1') != typed_raw:
                raise ReaderReject('typed_state_h5_mismatch', f'H5 typed-state extension row {index} differs from public witness')
        with h5py.File(path, 'r') as root:
            _check_typed_numeric_observation(root, index, typed_raw, contract, receipt)
        if index:
            previous = boundaries[-1]
            if (boundary.episode_id, boundary.reset_sample_id, boundary.scene_identity_hash,
                    boundary.scene_instance_id, boundary.provider_materialization_id) != (
                    previous.episode_id, previous.reset_sample_id, previous.scene_identity_hash,
                    previous.scene_instance_id, previous.provider_materialization_id):
                raise ReaderReject('episode_identity', f'boundary {index} crossed episode/reset/materialization identity')
            if boundary.state_revision != previous.state_revision + 1:
                raise ReaderReject('stale_boundary', f'boundary {index} revision did not advance exactly once')
        elif boundary.control_step != 0:
            raise ReaderReject('reset_boundary', 'first public boundary is not reset step 0')
        boundaries.append(boundary)

    if len({row.episode_id for row in boundaries}) != 1:
        raise ReaderReject('episode_identity', 'public boundary witness crosses episode identities')
    if len(loaded['structured_controls']) != transitions:
        raise ReaderReject('structured_transition_count', 'decoded structured controls do not equal T')
    drive_by_name = {row['native_dof_name']: row for row in receipt['drives']}
    if tuple(drive_by_name) != tuple(expected_names):
        raise ReaderReject('receipt_dof_order', 'F05 receipt is not in exact public model DOF order')

    verified_advances = 0
    for index, control in enumerate(loaded['structured_controls']):
        if control is None or control.request.scene_identity_hash != contract['scene_identity_sha256']:
            raise ReaderReject('transition_scene', f'transition {index} has an invalid request Scene identity')
        mapping = control.to_mapping()
        writers = mapping.get('writer_controls')
        if not isinstance(writers, list) or len(writers) != 1:
            raise ReaderReject('writer_count', f'transition {index} must have one Position writer')
        writer = writers[0]
        if writer.get('writer_id') != receipt.get('writer_id'):
            raise ReaderReject('writer_identity', f'transition {index} writer differs from the drive receipt')
        canonical = writer.get('canonical_action', {})
        target = canonical.get('position_target_v1')
        if not isinstance(target, dict):
            raise ReaderReject('position_target_missing', f'transition {index} lacks typed Position Target')
        boundary = StateBoundaryIdentity.from_mapping(target.get('source_boundary', {}))
        if boundary.to_mapping() != boundaries[index].to_mapping():
            raise ReaderReject('target_boundary', f'transition {index} Target is not bound to its source observation')
        if (target.get('binding_identity_hash') != profile.get('control_binding_plan_identity_sha256')
                or target.get('source_closure_digest') != contract['source_closure_sha256']
                or target.get('controller_identity') != profile.get('controller_identity_sha256')):
            raise ReaderReject('target_source_identity', f'transition {index} Target source/binding/controller differs')
        target_clock = target.get('sample_clock', {})
        if (target_clock.get('sample_index') != index
                or target_clock.get('clock_domain') != 'evaluation_boundary'
                or not _seconds_match(target_clock.get('simulation_time_s'), index * 0.01)):
            raise ReaderReject('target_clock', f'transition {index} Target clock is stale')
        if canonical.get('position_target_identity_hash') != digest(target):
            raise ReaderReject('target_identity_hash', f'transition {index} Position Target identity digest is invalid')
        if writer.get('controller_target', {}).get('payload') != target.get('target'):
            raise ReaderReject('target_payload', f'transition {index} controller Target differs from typed Target')

        normalized = None
        for group in control.request.groups:
            if group.group_id == 'gripper':
                if len(group.values) != 1:
                    raise ReaderReject('normalized_gripper', f'transition {index} has invalid normalized gripper shape')
                normalized = float(group.values[0])
                break
        gripper_target = target['target']['gripper']
        expected_opening = (normalized + 1.0) * 0.04 if normalized is not None else float('nan')
        if (normalized is None or not math.isfinite(normalized) or not -1.0 <= normalized <= 1.0
                or not math.isclose(float(gripper_target['opening_m']), expected_opening, rel_tol=0.0, abs_tol=1e-12)):
            raise ReaderReject('normalized_gripper', f'transition {index} normalized opening did not map to metres')

        applied = writer.get('applied_control', {}).get('payload', {})
        if (applied.get('native_io_execution_class') != 'synthetic_fixture_no_physics'
                or applied.get('native_interval_advance_attempts') != 5):
            raise ReaderReject('execution_class', f'transition {index} is not the exact no-physics S1 execution class')
        ack = applied.get('native_position_write_ack_v1')
        if not isinstance(ack, dict):
            raise ReaderReject('ack_missing', f'transition {index} has no native Position Ack')
        if (ack.get('schema_version'), ack.get('target_identity_sha256'), ack.get('partial'),
                ack.get('attempted_count'), tuple(ack.get('native_names', ()))) != (
                'native-position-write-ack-v1', digest(target['target']), False, 9, tuple(expected_names)):
            raise ReaderReject('ack_identity', f'transition {index} Ack identity/names/partial facts mismatch')
        arm = target['target']['arm_servo_position']
        finger_each = float(gripper_target['servo_opening_m']) / 2.0
        expected_values = {}
        for drive in receipt['drives']:
            joint = drive['canonical_joint']['joint_id']
            expected_values[drive['native_dof_name']] = (
                finger_each if joint.startswith('finger_joint')
                else float(arm[f"{drive['canonical_joint']['entity_id']}/{joint}"])
            )
        if len(ack.get('applied_values', ())) != 9:
            raise ReaderReject('ack_values', f'transition {index} Ack does not contain nine values')
        for name, value in zip(ack['native_names'], ack['applied_values'], strict=True):
            drive = drive_by_name[name]
            value = float(value)
            if (not math.isfinite(value)
                    or not math.isclose(value, expected_values[name], rel_tol=0.0, abs_tol=2e-9)
                    or not float(drive['lower_limit']) <= value <= float(drive['upper_limit'])):
                raise ReaderReject('ack_values', f'transition {index} Ack does not match target/limit for {name}')

        advances = applied.get('native_interval_advance_receipts_v1')
        if not isinstance(advances, list) or len(advances) != 5:
            raise ReaderReject('advance_count', f'transition {index} does not persist exactly five advances')
        for offset, advance in enumerate(advances, start=1):
            step = index * 5 + offset
            if (advance.get('schema_version'), advance.get('completed_count'), advance.get('native_step_index')) != (
                    'native-advance-receipt-v1', 1, step):
                raise ReaderReject('advance_clock', f'transition {index} native step index is invalid')
            if not _seconds_match(advance.get('simulation_time_s'), step * 0.002):
                raise ReaderReject('advance_clock', f'transition {index} native clock is invalid')
        verified_advances += len(advances)

    with h5py.File(path, 'r') as root:
        boundary_events = json.loads(root['meta/boundary_events_v1_json'][()].decode())
        outcome = json.loads(root['meta/episode_outcome_v1_json'][()].decode())
    if len(boundary_events) != 1:
        raise ReaderReject('episode_end_event', 'H5 must contain one final episode-ended event')
    final = boundaries[-1]
    end = boundary_events[0]
    payload = end.get('payload', {})
    last_writer = loaded['structured_controls'][-1].to_mapping()['writer_controls'][0]
    last_advances = last_writer['applied_control']['payload']['native_interval_advance_receipts_v1']
    last_advance = last_advances[-1]
    if (end.get('event_type'), end.get('episode_id'), end.get('boundary_index'),
            payload.get('control_step'), payload.get('state_boundary_id'),
            payload.get('source_closure_digest')) != (
            'episode_ended', final.episode_id, 8, 8, final.boundary_id, contract['source_closure_sha256']):
        raise ReaderReject('episode_end_event', 'episode-ended event does not bind the final public boundary')
    if (not _seconds_match(payload.get('simulation_time_s'), last_advance.get('simulation_time_s'))
            or not _seconds_match(public_rows[-1].get('simulation_time_s'), last_advance.get('simulation_time_s'))
            or not _seconds_match(public_rows[-1]['state_sample_clock'].get('simulation_time_s'), last_advance.get('simulation_time_s'))):
        raise ReaderReject('final_clock', 'final public publication differs from last successful advance clock')
    if (outcome.get('schema_version'), outcome.get('episode_id'), outcome.get('final_boundary'),
            outcome.get('end_reason'), outcome.get('terminated'), outcome.get('truncated')) != (
            'episode-outcome-v1', final.episode_id, 8, payload.get('end_reason'),
            payload.get('terminated'), payload.get('truncated')):
        raise ReaderReject('episode_outcome', 'H5 outcome identity differs from final boundary event')
    if witness.get('episode_ordinal') not in (0, 1):
        raise ReaderReject('episode_ordinal', 'witness episode ordinal is outside the two-run S1')
    return {
        'schema_version': 'f05-independent-h5-reader-result-v1',
        'accepted': True,
        'h5_sha256': actual_sha,
        'episode_id': final.episode_id,
        'verified_boundary_rows': len(boundaries),
        'verified_observation_rows': observations,
        'verified_typed_numeric_rows': observations,
        'verified_typed_joint_position_observation_rows': observations,
        'verified_typed_hand_pose_observation_rows': observations,
        'verified_typed_free_body_pose_observation_rows': observations,
        'verified_typed_state_h5_rows': 0 if typed_extension_rows is None else len(typed_extension_rows),
        'typed_velocity_persistence': (
            'public_reset_step_typed_state_h5_extension_bound_to_external_public_witness'
            if typed_extension_rows is not None else 'not_persisted_in_h5_unverified'
        ),
        'typed_velocity_observation_crosscheck': (
            'not_applicable_no_velocity_observation_leaf; finite/unit/shape checked and extension row matched to public witness'
            if typed_extension_rows is not None else 'unverified_not_persisted'
        ),
        'unverified_frame_states': ['all canonical frames except hand and free_body observation bindings'],
        'verified_transitions': transitions,
        'verified_synthetic_advances': verified_advances,
        'source_id': contract['source_id'],
        'source_closure_sha256': contract['source_closure_sha256'],
        'receipt_identity_sha256': contract['receipt_identity_sha256'],
        'runtime_admitted': False,
        'physics_steps': 0,
    }


def _native_physical_metrics(boundary_rows, contract, plan):
    """Recompute the frozen Panda/free-body gates from public typed T+1 rows."""
    from task_env.controllers.canonical.kinematics import (
        PANDA_HAND_ORIGIN_TCP_V1, PandaKinematics,
    )
    from task_env.runtime.sessions.free_joint_state import body_origin_local_twist_to_world_com

    thresholds = plan['physical_acceptance']['thresholds']
    home = plan['physical_acceptance']['home_joint_position_rad']
    reset_pose = plan['physical_acceptance']['reset_pose_world_m']
    kin_path = Path(contract['kinematics_source_path']).resolve()
    if not kin_path.is_file() or hashlib.sha256(kin_path.read_bytes()).hexdigest() != contract['kinematics_source_sha256']:
        raise ReaderReject('kinematics_source', 'source-calibrated Panda kinematics bytes differ from the frozen run contract')
    kinematics = PandaKinematics(kin_path.read_text(encoding='utf-8'), tcp_profile=PANDA_HAND_ORIGIN_TCP_V1)
    joint_rows, hand_rows, body_rows, twist_rows = [], [], [], []
    com_offset = np.asarray(contract['free_body_com_offset_body_m'], dtype=np.float64)
    if com_offset.shape != (3,) or not np.isfinite(com_offset).all():
        raise ReaderReject('com_binding', 'frozen free-body COM offset is invalid')
    for index, row in enumerate(boundary_rows):
        state = row['canonical_state_view_v1']
        joints = {(item['entity_id'], item['joint_id']): item for item in state['joints']}
        arm_names = [f'joint{i}' for i in range(1, 8)]
        try:
            q = [float(joints[('panda-main', name)]['position'][0]) for name in arm_names]
            hand = next(item for item in state['frames']
                        if item['frame'] == {'entity_id': 'panda-main', 'frame_id': 'hand'})['pose_world']
            free = joints[('square-peg-instance', 'floating_root')]
            body_frame = next(item for item in state['frames']
                              if item['frame'] == {'entity_id': 'square-peg-instance', 'frame_id': 'peg1'})['pose_world']
            p = [float(value) for value in free['position'][:3]]
            quat = [float(value) for value in free['position'][3:7]]
            local_twist = free['velocity']
            velocity_com, omega_world = body_origin_local_twist_to_world_com(
                position_world_m=p,
                orientation_world_from_body_wxyz=quat,
                com_offset_body_m=com_offset,
                linear_velocity_body_origin_local_m_s=local_twist[:3],
                angular_velocity_body_local_rad_s=local_twist[3:],
            )
        except Exception as error:
            raise ReaderReject('physical_state', f'public typed boundary {index} lacks native physical state: {error}') from error
        if not np.allclose(p, body_frame['position'], rtol=0.0, atol=1e-12):
            raise ReaderReject('physical_state', f'boundary {index} free Joint and public Body pose disagree')
        pose_hand = [*hand['position'], *hand['quaternion_wxyz']]
        joint_rows.append(q)
        hand_rows.append([float(value) for value in pose_hand])
        body_rows.append(p)
        twist_rows.append([*velocity_com, *omega_world])

    joints = np.asarray(joint_rows, dtype=np.float64)
    hand = np.asarray(hand_rows, dtype=np.float64)
    body = np.asarray(body_rows, dtype=np.float64)
    twist = np.asarray(twist_rows, dtype=np.float64)
    if (joints.shape != (101, 7) or hand.shape != (101, 7)
            or body.shape != (101, 3) or twist.shape != (101, 6)
            or not all(np.isfinite(value).all() for value in (joints, hand, body, twist))):
        raise ReaderReject('physical_state', 'public physical trajectory has invalid T+1 shape or non-finite values')
    if not np.allclose(body[0], reset_pose, rtol=0.0, atol=thresholds['reset_position_tolerance_m']):
        raise ReaderReject('physical_reset', 'free-body reset differs from frozen Menagerie USD reset pose')
    if float(np.max(np.abs(twist[0]))) > thresholds['reset_twist_max_abs']:
        raise ReaderReject('physical_reset', 'free-body reset twist exceeds the frozen zero-velocity tolerance')
    fk_position, fk_orientation = [], []
    for q, measured in zip(joints, hand, strict=True):
        predicted = kinematics.pose(q.tolist())
        fk_position.append(float(np.linalg.norm(np.asarray(predicted.position) - measured[:3])))
        q_pred = np.asarray(predicted.quaternion_wxyz, dtype=np.float64)
        q_measured = measured[3:7].copy()
        q_pred /= np.linalg.norm(q_pred)
        q_measured /= np.linalg.norm(q_measured)
        dot = min(1.0, max(0.0, abs(float(q_pred @ q_measured))))
        fk_orientation.append(float(2.0 * np.arccos(dot)))
    home_q1 = float(home['joint1'])
    arm_excursion = float(np.max(np.abs(joints[:, 0] - home_q1)))
    arm_return = float(abs(joints[-1, 0] - home_q1))
    # The two fingers are checked separately in the typed row; their opening is their sum.
    openings = np.asarray([
        float(next(item for item in row['canonical_state_view_v1']['joints']
                   if item['entity_id'] == 'panda-main' and item['joint_id'] == 'finger_joint1')['position'][0])
        + float(next(item for item in row['canonical_state_view_v1']['joints']
                     if item['entity_id'] == 'panda-main' and item['joint_id'] == 'finger_joint2')['position'][0])
        for row in boundary_rows
    ], dtype=np.float64)
    opening_delta = float(np.max(openings) - np.min(openings))
    final_opening = float(np.mean(openings[-10:]))
    drop = float(body[0, 2] - np.min(body[:, 2]))
    fall_end = max(1, int(np.argmin(body[:, 2])) + 1)
    downward = float(np.min(twist[:fall_end, 2]))
    late_z = body[-10:, 2]
    settled = float(np.mean(late_z))
    settled_dev = float(np.max(np.abs(late_z - settled)))
    settled_speed = float(np.max(np.abs(twist[-10:, 2])))
    checks = {
        'arm_joint1_excursion': arm_excursion >= thresholds['arm_joint1_excursion_min_rad'],
        'arm_joint1_return': arm_return <= thresholds['arm_joint1_return_max_error_rad'],
        'gripper_opening_change': opening_delta >= thresholds['gripper_opening_delta_min_m'],
        'gripper_open_after_return': final_opening >= thresholds['gripper_final_open_min_m'],
        'source_calibrated_fk_position': max(fk_position) <= thresholds['fk_position_error_max_m'],
        'source_calibrated_fk_orientation': max(fk_orientation) <= thresholds['fk_orientation_error_max_rad'],
        'free_body_drop': drop >= thresholds['free_body_drop_min_m'],
        'free_body_downward_motion': downward <= -thresholds['free_body_downward_speed_min_m_s'],
        'free_body_settled_height': thresholds['settled_center_min_m'] <= settled <= thresholds['settled_center_max_m'],
        'free_body_settled_stability': settled_dev <= thresholds['settled_center_max_deviation_m']
            and settled_speed <= thresholds['settled_vertical_speed_max_m_s'],
    }
    metrics = {
        'arm_joint1_excursion_rad': arm_excursion, 'arm_joint1_return_error_rad': arm_return,
        'gripper_opening_min_m': float(np.min(openings)), 'gripper_opening_max_m': float(np.max(openings)),
        'gripper_opening_delta_m': opening_delta, 'gripper_final_mean_opening_m': final_opening,
        'fk_position_error_max_m': max(fk_position), 'fk_orientation_error_max_rad': max(fk_orientation),
        'free_body_reset_position_m': body[0].tolist(), 'free_body_reset_twist_world_com': twist[0].tolist(),
        'free_body_min_center_z_m': float(np.min(body[:, 2])), 'free_body_drop_m': drop,
        'free_body_min_downward_speed_m_s': downward, 'free_body_late_center_z_mean_m': settled,
        'free_body_late_center_z_max_deviation_m': settled_dev,
        'free_body_late_vertical_speed_max_abs_m_s': settled_speed, 'checks': checks,
    }
    if not all(checks.values()):
        raise ReaderReject('physical_oracle', f'original F05 physical oracle failed: {[k for k,v in checks.items() if not v]}')
    return metrics


def validate_native_h5(path: Path, witness_path: Path, contract_path: Path, run_plan_path: Path):
    """Strict, separate F05 native profile; the legacy S1 reader remains unchanged."""
    if not path.is_file():
        raise ReaderReject('h5_missing', 'native H5 file is missing')
    witness = json.loads(witness_path.read_text(encoding='utf-8'))
    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    plan = json.loads(run_plan_path.read_text(encoding='utf-8'))
    if contract.get('schema_version') != 'f05-attempt003-native-reader-contract-v1':
        raise ReaderReject('contract_schema', 'native reader requires the exact F05 attempt003 contract')
    if (plan.get('schema_version') != 'f05-attempt003-native-run-plan-v1'
            or plan.get('reader_contract_sha256') != hashlib.sha256(contract_path.read_bytes()).hexdigest()):
        raise ReaderReject('run_plan_binding', 'native contract is not bound by the frozen run plan')
    plan_sha = hashlib.sha256(run_plan_path.read_bytes()).hexdigest()
    runtime_environment = contract.get('runtime_environment')
    runtime_environment_bytes = (
        json.dumps(runtime_environment, sort_keys=True, indent=2, allow_nan=False) + '\n'
    ).encode('utf-8') if isinstance(runtime_environment, dict) else b''
    runtime_environment_sha = hashlib.sha256(runtime_environment_bytes).hexdigest()
    if (contract.get('runtime_environment_sha256') != plan.get('runtime_environment_sha256')
            or contract.get('runtime_environment_sha256') != runtime_environment_sha
            or runtime_environment != plan.get('runtime_environment')
            or not isinstance(runtime_environment, dict)
            or runtime_environment.get('taichi_backend_alias') != 'taichi_forge'
            or runtime_environment.get('kit_or_isaacsim_imported') is not False
            or runtime_environment.get('environment', {}).get('GEOPHYS_TAICHI_ARCH') != 'cpu'
            or runtime_environment.get('environment', {}).get('CUDA_VISIBLE_DEVICES') != ''):
        raise ReaderReject('runtime_identity', 'frozen plan/contract does not bind the source-only CPU Forge/OpenUSD identity')
    if (witness.get('schema_version') != 'f05-native-public-boundary-witness-v1'
            or witness.get('witness_source') != 'SelectedReferenceEnv public reset/step observation and info return values'
            or witness.get('native_run_plan_sha256') != plan_sha):
        raise ReaderReject('witness_schema', 'native witness lacks exact public origin or run-plan binding')
    actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if (witness.get('h5_sha256') != actual_sha
            or Path(witness.get('h5_path', '')).resolve() != path.resolve()):
        raise ReaderReject('witness_file_binding', 'native public witness does not bind the closed H5 bytes')
    identity = _producer_identity_from_contract(contract)
    if (identity.actual_provider_build_identity != contract.get('actual_provider_build_identity')
            or identity.commit_sha != plan.get('provider_candidate_head')
            or plan.get('core_head') != contract.get('core_head')):
        raise ReaderReject('producer_identity', 'actual Core/provider HEAD differs from the run contract')
    try:
        loaded = load_structured_control_records_h5(path)
    except Exception as error:
        raise ReaderReject('h5_decode', f'{type(error).__name__}: {error}') from error
    transitions, observations = loaded['transition_count'], loaded['observation_count']
    if (transitions, observations) != (100, 101) or observations != transitions + 1:
        raise ReaderReject('t_plus_one_count', f'native H5 must contain 100 transitions/101 observations; got {transitions}/{observations}')
    public_rows = witness.get('public_boundaries')
    if (witness.get('transition_count'), witness.get('observation_count'),
            witness.get('episode_ordinal') in (0, 1), isinstance(public_rows, list),
            len(public_rows) if isinstance(public_rows, list) else -1) != (100, 101, True, True, 101):
        raise ReaderReject('witness_count', 'native public witness does not contain exact T+1 rows for one of two episodes')
    profile = loaded['env_meta'].get('reference_profile')
    expected_profile = (
        'f05-geophys-core-position-native-profile-v1',
        'geophys-usd-position-f05-native-v1', 'native_runtime', True,
        'F05 frozen Menagerie USD / GeoPhys CPU native Core Position cell',
    )
    if not isinstance(profile, dict) or (
            profile.get('schema_version'), profile.get('profile_id'), profile.get('provenance_kind'),
            profile.get('runtime_admitted'), profile.get('recording_scope')) != expected_profile:
        raise ReaderReject('profile_classification', 'H5 does not have the exact admitted F05 native cell profile')
    bootstrap = profile.get('native_public_bootstrap_receipt')
    if (not isinstance(bootstrap, dict)
            or bootstrap.get('native_run_id') != plan.get('native_run_id')
            or bootstrap.get('native_run_plan_sha256') != plan_sha
            or bootstrap.get('runtime_environment_sha256') != contract.get('runtime_environment_sha256')
            or bootstrap.get('actual_execution_build_identity') != identity.actual_provider_build_identity
            or bootstrap.get('public_native_step_counter') != 'actuator_force_sample_status.native_step_index'
            or bootstrap.get('native_step_counter_baseline') != 0
            or bootstrap.get('native_step_index_at_reset') != 0
            or bootstrap.get('execution', {}).get('cpu_max_num_threads') != 4):
        raise ReaderReject('runtime_identity', 'native H5 bootstrap receipt is not bound to the same run/plan/runtime identity')
    if (profile.get('source_verified'), profile.get('source_validation_provenance_kind')) != (False, 'local-validated'):
        raise ReaderReject('source_provenance', 'native cell must remain local-validated and source_verified=false')
    representation = profile.get('representation', {})
    if (representation.get('identity_sha256'), representation.get('provider'),
            representation.get('provider_build_identity'), representation.get('requested_target_build_identity'),
            representation.get('actual_execution_build_identity'), representation.get('runtime_admitted'),
            representation.get('source_verified')) != (
            contract['representation']['identity_sha256'], 'geophys',
            identity.requested_target_build_identity, identity.requested_target_build_identity,
            identity.actual_provider_build_identity, False, False):
        raise ReaderReject('source_identity', 'native representation does not distinguish requested target and actual producer')
    if (profile.get('host_model_producer_identity'), profile.get('host_model_producer_identity_sha256'),
            profile.get('actual_provider_build_identity')) != (
            identity.to_mapping(), identity.identity_sha256, identity.actual_provider_build_identity):
        raise ReaderReject('producer_identity', 'native H5 producer identity is not the exact committed candidate')
    if profile.get('native_position_drive_receipt') != contract.get('native_position_drive_receipt'):
        raise ReaderReject('receipt_identity', 'native H5 receipt payload differs from the pre-run public model receipt')
    receipt = contract['native_position_drive_receipt']
    if (receipt.get('provenance_kind'), receipt.get('provider_build_identity'),
            receipt.get('host_model_producer_identity_sha256'),
            profile.get('native_position_drive_receipt_identity_sha256')) != (
            'native_runtime', identity.actual_provider_build_identity, identity.identity_sha256,
            contract['receipt_identity_sha256']):
        raise ReaderReject('receipt_identity', 'native receipt class/build/producer identity mismatch')
    for key in ('source_id', 'source_closure_sha256', 'task_source_identity_sha256',
                'task_artifact_identity_sha256', 'scene_identity_sha256', 'execution_identity_sha256'):
        if profile.get(key) != contract.get(key):
            raise ReaderReject('source_execution_identity', f'native H5 {key} differs from frozen source contract')
    execution = profile.get('execution_spec_v1', {})
    if (execution.get('schema_version'), execution.get('physics_provider'), execution.get('physics_backend'),
            execution.get('physics_profile'), execution.get('physics_device'), execution.get('determinism_mode'),
            profile.get('execution_identity_sha256')) != (
            'execution-spec-v1', 'geophys', 'cpu', 'geophys-usd-position-f05-native-v1', 'cpu', 'best_effort',
            contract['execution_identity_sha256']):
        raise ReaderReject('execution_profile', 'native H5 ExecutionSpec does not match frozen CPU profile')
    metadata = profile.get('native_runtime_io_metadata', {})
    if (metadata.get('physics_provider'), metadata.get('provider_build_identity'), metadata.get('backend'),
            metadata.get('device'), metadata.get('determinism_mode'), metadata.get('execution_identity_sha256'),
            metadata.get('source_id'), metadata.get('source_closure_sha256'), metadata.get('scene_identity_sha256'),
            metadata.get('task_artifact_identity_sha256'), metadata.get('physics_dt_s'),
            metadata.get('control_substeps'), metadata.get('native_dof_names'),
            metadata.get('host_model_producer_identity_sha256')) != (
            'geophys', identity.actual_provider_build_identity, 'cpu', 'cpu', 'best_effort',
            contract['execution_identity_sha256'], contract['source_id'], contract['source_closure_sha256'],
            contract['scene_identity_sha256'], contract['task_artifact_identity_sha256'], 0.002, 5,
            contract['native_dof_order'], identity.identity_sha256):
        raise ReaderReject('native_io_metadata', 'native Runtime I/O metadata differs from the actual F05 provider/source')
    if (profile.get('native_source_mappings') != contract.get('native_source_mappings')
            or profile.get('public_model_identity_sha256') != contract.get('public_model_identity_sha256')):
        raise ReaderReject('public_model_identity', 'native canonical resource mapping/model identity differs from frozen model')
    delivery = profile.get('usd_delivery', {})
    if any(delivery.get(key) != contract['delivery'].get(key) for key in (
            'asset_identity_sha256', 'delivery_sha256', 'closure_sha256', 'source_revision',
            'entry_file', 'validation_report_sha256', 'recipe_sha256', 'checker_sha256')):
        raise ReaderReject('source_delivery', 'native H5 source delivery/report/recipe identity mismatch')
    frozen_bindings = json.loads((BASE / 'sol_f05_002/accepted_source_bindings.json').read_text())
    frozen_source = frozen_bindings['source_bindings']['menagerie-panda']
    from task_env.assembly.usd_delivery import load_usd_asset_delivery
    delivery_root = Path(frozen_source['delivery_root']).resolve()
    loaded_source = load_usd_asset_delivery(delivery_root / 'usd_delivery.json')
    frozen_delivery = loaded_source.delivery
    entry_sha = hashlib.sha256(loaded_source.file_bytes[frozen_delivery.entry_file]).hexdigest()
    report_sha = hashlib.sha256(loaded_source.report_bytes).hexdigest()
    source_facts = {
        'source_reference': frozen_delivery.asset_definition.source_reference,
        'asset_identity_sha256': frozen_delivery.asset_identity_hash,
        'delivery_sha256': loaded_source.delivery_sha256,
        'closure_sha256': loaded_source.closure_sha256,
        'source_revision': frozen_delivery.source_revision,
        'entry_file': frozen_delivery.entry_file,
        'entry_sha256': entry_sha,
        'validation_report_sha256': report_sha,
    }
    if (source_facts.get('source_reference') != 'mujoco-menagerie://franka_emika_panda/panda.xml'
            or any(contract['delivery'].get(key) != value for key, value in source_facts.items())
            or any(frozen_source.get(key) != value for key, value in {
                'asset_identity_sha256': source_facts['asset_identity_sha256'],
                'delivery_sha256': source_facts['delivery_sha256'],
                'delivery_closure_sha256': source_facts['closure_sha256'],
                'source_revision': source_facts['source_revision'],
                'entry_file': source_facts['entry_file'], 'entry_sha256': entry_sha,
                'validation_report_sha256': report_sha,
            }.items())):
        raise ReaderReject('source_delivery', 'native run contract is not bound to frozen Menagerie delivery/report bytes')
    report_path = (delivery_root / frozen_delivery.validation_report_path).resolve()
    if delivery_root not in report_path.parents or not report_path.is_file():
        raise ReaderReject('source_delivery', 'native validation report path escapes or is missing from frozen delivery')
    report_bytes = report_path.read_bytes()
    report = json.loads(report_bytes)
    if (hashlib.sha256(report_bytes).hexdigest() != source_facts['validation_report_sha256']
            or report.get('provenance_kind') != 'local-validated' or report.get('passed') is not True
            or report.get('output_closure_sha256') != frozen_delivery.closure_sha256
            or report.get('source_revision') != frozen_delivery.source_revision
            or report.get('recipe_sha256') != frozen_delivery.recipe_sha256
            or report.get('checker_sha256') != frozen_delivery.checker_sha256):
        raise ReaderReject('source_delivery', 'native source validation report bytes/content changed from frozen receipt')

    with h5py.File(path, 'r') as root:
        if (int(root.attrs.get('transition_count', -1)), int(root.attrs.get('observation_count', -1))) != (100, 101):
            raise ReaderReject('h5_attributes', 'native H5 attributes disagree with independent T/T+1 counts')
        stored = np.asarray(root['obs/state/boundary_identity_sha256'][...])
        if stored.shape != (101, 32) or stored.dtype != np.uint8:
            raise ReaderReject('boundary_dataset_shape', 'native boundary digest storage is not exact T+1')
        typed_rows = _read_typed_state_extension(root, 101, 'f05-s1-independent-input-contract-v2')
        events = json.loads(root['meta/boundary_events_v1_json'][()].decode())
        outcome = json.loads(root['meta/episode_outcome_v1_json'][()].decode())
    if len(loaded['structured_controls']) != 100:
        raise ReaderReject('structured_transition_count', 'native H5 lacks 100 structured controls')
    boundaries = []
    for index, entry in enumerate(public_rows):
        try:
            boundary = StateBoundaryIdentity.from_mapping(entry.get('state_boundary_identity', {}))
            boundary.validate()
            view = decode_canonical_state_view(entry.get('canonical_state_view_v1', {}))
            view.validate()
        except Exception as error:
            raise ReaderReject('boundary_identity', f'native public boundary {index} is invalid: {error}') from error
        if (entry.get('state_boundary_id') != boundary.boundary_id
                or view.boundary.to_mapping() != boundary.to_mapping()
                or view.sample_clock.to_mapping() != entry.get('state_sample_clock')):
            raise ReaderReject('typed_state_boundary', f'native boundary {index} typed identity/clock differs')
        clock = entry.get('state_sample_clock', {})
        if (entry.get('control_step') != index or boundary.control_step != index
                or boundary.state_revision != index or clock.get('sample_index') != index
                or clock.get('clock_domain') != 'evaluation_boundary'
                or not _seconds_match(entry.get('simulation_time_s'), index * .01)
                or not _seconds_match(clock.get('simulation_time_s'), index * .01)
                or boundary.scene_identity_hash != contract['scene_identity_sha256']
                or boundary.reset_sample_id != profile.get('reset_sample_id')):
            raise ReaderReject('boundary_clock', f'native public boundary {index} clock/source/reset identity mismatch')
        if bytes(np.asarray(stored[index])) != bytes.fromhex(boundary.boundary_id.removeprefix('state-boundary-')):
            raise ReaderReject('boundary_digest', f'native H5 boundary digest row {index} differs from public reset/step boundary')
        fields = _observation_fields(path, index)
        if fields != entry.get('observation_fields') or entry.get('observation_identity_sha256') != _fingerprint_fields(fields):
            raise ReaderReject('observation_witness', f'native H5 observation row {index} differs from public return values')
        typed = entry.get('canonical_state_view_v1')
        _validate_typed_unit_layout(typed, contract, receipt, index)
        _check_typed_numeric_observation(root, index, typed, contract, receipt)
        ext = typed_rows[index]
        if (ext.get('boundary_index') != index or ext.get('state_boundary_identity') != boundary.to_mapping()
                or ext.get('state_sample_clock') != clock
                or ext.get('canonical_state_view_v1') != typed):
            raise ReaderReject('typed_state_h5_mismatch', f'native H5 typed state extension row {index} differs from public witness')
        if index and (boundary.episode_id, boundary.reset_sample_id, boundary.scene_instance_id,
                      boundary.provider_materialization_id, boundary.scene_identity_hash) != (
                      boundaries[-1].episode_id, boundaries[-1].reset_sample_id, boundaries[-1].scene_instance_id,
                      boundaries[-1].provider_materialization_id, boundaries[-1].scene_identity_hash):
            raise ReaderReject('episode_identity', f'native T+1 row {index} crossed reset/materialization/episode identity')
        if index and boundary.state_revision != boundaries[-1].state_revision + 1:
            raise ReaderReject('stale_boundary', f'native boundary {index} revision is duplicated or stale')
        boundaries.append(boundary)
    if len({item.episode_id for item in boundaries}) != 1:
        raise ReaderReject('episode_identity', 'native H5 public boundaries span more than one episode')

    drive_by_name = {row['native_dof_name']: row for row in receipt['drives']}
    expected_names = contract['native_dof_order']
    if list(drive_by_name) != expected_names:
        raise ReaderReject('receipt_dof_order', 'native receipt DOF order differs from the frozen public actuator mapping')
    advances_total = 0
    schedule = plan['motion_schedule']
    home = plan['physical_acceptance']['home_joint_position_rad']
    for index, control in enumerate(loaded['structured_controls']):
        mapping = control.to_mapping()
        writers = mapping.get('writer_controls')
        if (control.request.scene_identity_hash != contract['scene_identity_sha256']
                or control.request.binding_identity_hash != profile.get('control_binding_plan_identity_sha256')
                or not isinstance(writers, list) or len(writers) != 1):
            raise ReaderReject('control_identity', f'native transition {index} request/writer identity mismatch')
        writer = writers[0]
        if writer.get('writer_id') != receipt.get('writer_id'):
            raise ReaderReject('writer_identity', f'native transition {index} writer is not the model-bound Position writer')
        canonical = writer.get('canonical_action', {})
        target = canonical.get('position_target_v1')
        if not isinstance(target, dict):
            raise ReaderReject('target_missing', f'native transition {index} lacks its typed Position Target')
        source_boundary = StateBoundaryIdentity.from_mapping(target.get('source_boundary', {}))
        if (source_boundary.to_mapping() != boundaries[index].to_mapping()
                or target.get('binding_identity_hash') != profile.get('control_binding_plan_identity_sha256')
                or target.get('controller_identity') != profile.get('controller_identity_sha256')
                or target.get('source_closure_digest') != contract['source_closure_sha256']
                or canonical.get('position_target_identity_hash') != digest(target)
                or writer.get('controller_target', {}).get('payload') != target.get('target')):
            raise ReaderReject('target_identity', f'native transition {index} Target is stale or source/controller-bound incorrectly')
        target_clock = target.get('sample_clock', {})
        if (target_clock.get('sample_index') != index or target_clock.get('clock_domain') != 'evaluation_boundary'
                or not _seconds_match(target_clock.get('simulation_time_s'), index * .01)):
            raise ReaderReject('target_clock', f'native transition {index} Position Target clock mismatch')
        phase = next(item for item in schedule if item['start_interval'] <= index < item['stop_interval_exclusive'])
        expected_arm = {f'panda-main/joint{j}': float(home[f'joint{j}']) + float(phase['arm_joint_offsets_rad'][j-1])
                        for j in range(1,8)}
        arm_target = target['target']['arm_servo_position']
        if any(not math.isclose(float(arm_target.get(name, float('nan'))), value, rel_tol=0.0, abs_tol=2e-7)
               for name, value in expected_arm.items()):
            raise ReaderReject('physical_target_schedule', f'native transition {index} arm Target differs from frozen motion schedule')
        group = next((item for item in control.request.groups if item.group_id == 'gripper'), None)
        gripper_target = target['target']['gripper']
        expected_opening = float(phase['gripper_opening_m'])
        if (group is None or len(group.values) != 1
                or not math.isclose((float(group.values[0]) + 1.0) * .04, expected_opening, rel_tol=0.0, abs_tol=1e-12)
                or not math.isclose(float(gripper_target['opening_m']), expected_opening, rel_tol=0.0, abs_tol=1e-12)):
            raise ReaderReject('normalized_gripper', f'native transition {index} normalized gripper does not match the frozen metre schedule')
        applied = writer.get('applied_control', {}).get('payload', {})
        if (applied.get('native_io_execution_class') != 'native_runtime_accepted_physics'
                or applied.get('native_interval_advance_attempts') != 5):
            raise ReaderReject('execution_class', f'native transition {index} was not accepted native physics')
        ack = applied.get('native_position_write_ack_v1')
        if (not isinstance(ack, dict) or ack.get('schema_version') != 'native-position-write-ack-v1'
                or ack.get('target_identity_sha256') != digest(target['target'])
                or ack.get('partial') is not False or ack.get('attempted_count') != 9
                or ack.get('native_names') != expected_names or len(ack.get('applied_values', ())) != 9):
            raise ReaderReject('ack_identity', f'native transition {index} Target/Ack names or partial-apply facts mismatch')
        fingers_each = float(gripper_target['servo_opening_m']) / 2.0
        for name, actual in zip(ack['native_names'], ack['applied_values'], strict=True):
            drive = drive_by_name[name]
            joint = drive['canonical_joint']['joint_id']
            expected = fingers_each if joint.startswith('finger_joint') else expected_arm[f"{drive['canonical_joint']['entity_id']}/{joint}"]
            if (not math.isfinite(float(actual)) or not math.isclose(float(actual), expected, rel_tol=0.0, abs_tol=2e-9)
                    or not float(drive['lower_limit']) <= float(actual) <= float(drive['upper_limit'])):
                raise ReaderReject('ack_values', f'native transition {index} Ack value differs from Target/limits for {name}')
        advances = applied.get('native_interval_advance_receipts_v1')
        if not isinstance(advances, list) or len(advances) != 5:
            raise ReaderReject('advance_count', f'native transition {index} must record five advances')
        for offset, item in enumerate(advances, start=1):
            step = index * 5 + offset
            if (item.get('schema_version'), item.get('completed_count'), item.get('native_step_index')) != (
                    'native-advance-receipt-v1', 1, step) or not _seconds_match(item.get('simulation_time_s'), step * .002):
                raise ReaderReject('advance_clock', f'native transition {index} advance count/index/clock mismatch')
        advances_total += 5
    if advances_total != 500:
        raise ReaderReject('advance_count', f'native H5 contains {advances_total} accepted advances instead of 500')
    if (len(events) != 1 or events[0].get('event_type') != 'episode_ended'
            or events[0].get('episode_id') != boundaries[-1].episode_id
            or events[0].get('boundary_index') != 100):
        raise ReaderReject('episode_end_event', 'native H5 lacks the exact final horizon boundary event')
    end_payload = events[0].get('payload', {})
    final_writer = loaded['structured_controls'][-1].to_mapping()['writer_controls'][0]
    final_advance = final_writer['applied_control']['payload']['native_interval_advance_receipts_v1'][-1]
    if (end_payload.get('control_step') != 100 or end_payload.get('state_boundary_id') != boundaries[-1].boundary_id
            or end_payload.get('source_closure_digest') != contract['source_closure_sha256']
            or not _seconds_match(end_payload.get('simulation_time_s'), 1.0)
            or not _seconds_match(final_advance.get('simulation_time_s'), 1.0)
            or not _seconds_match(public_rows[-1]['simulation_time_s'], 1.0)):
        raise ReaderReject('final_clock', 'native final event/publication does not match the final accepted advance')
    if (outcome.get('schema_version'), outcome.get('episode_id'), outcome.get('final_boundary'),
            outcome.get('end_reason'), outcome.get('terminated'), outcome.get('truncated')) != (
            'episode-outcome-v1', boundaries[-1].episode_id, 100,
            end_payload.get('end_reason'), end_payload.get('terminated'), end_payload.get('truncated')):
        raise ReaderReject('episode_outcome', 'native H5 outcome differs from its final Position horizon event')
    physical = _native_physical_metrics(public_rows, contract, plan)
    return {
        'schema_version': 'f05-independent-native-h5-reader-result-v1', 'accepted': True,
        'h5_sha256': actual_sha, 'episode_id': boundaries[-1].episode_id,
        'episode_ordinal': witness['episode_ordinal'], 'verified_boundary_rows': 101,
        'verified_observation_rows': 101, 'verified_typed_state_h5_rows': len(typed_rows),
        'verified_transitions': 100, 'verified_native_advances': advances_total,
        'runtime_admitted': True, 'provenance_kind': 'native_runtime',
        'actual_provider_build_identity': identity.actual_provider_build_identity,
        'source_closure_sha256': contract['source_closure_sha256'],
        'receipt_identity_sha256': contract['receipt_identity_sha256'], 'physical_metrics': physical,
    }
def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--h5', required=True, type=Path)
    parser.add_argument('--witness', required=True, type=Path)
    parser.add_argument('--contract', required=True, type=Path)
    parser.add_argument('--native-run-plan', type=Path,
                        help='selects the separate, strict attempt003 native profile contract')
    args = parser.parse_args(argv)
    try:
        result = (
            validate_native_h5(args.h5, args.witness, args.contract, args.native_run_plan)
            if args.native_run_plan is not None
            else validate_h5(args.h5, args.witness, args.contract)
        )
    except ReaderReject as error:
        print(json.dumps({'schema_version': 'f05-independent-h5-reader-result-v1',
                          'accepted': False, 'reason': error.reason, 'detail': str(error)},
                         sort_keys=True, allow_nan=False))
        return 2
    except Exception as error:
        print(json.dumps({'schema_version': 'f05-independent-h5-reader-result-v1',
                          'accepted': False, 'reason': 'reader_error',
                          'detail': f'{type(error).__name__}: {error}'},
                         sort_keys=True, allow_nan=False))
        return 3
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
