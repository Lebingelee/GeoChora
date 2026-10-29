"""Raw R06b H5 witness; intentionally imports no TaskEnv or physics provider."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_h5(path: Path, case: dict) -> dict[str, object]:
    import h5py
    import numpy as np
    import yaml

    with h5py.File(path, 'r') as root:
        if (str(root.attrs.get('schema_id', '')) != 'task-env-h5'
                or str(root.attrs.get('schema_version', '')) != 'v3'
                or not bool(root.attrs.get('episode_complete', False))
                or int(root.attrs.get('transition_count', 0)) != 64
                or int(root.attrs.get('observation_count', 0)) != 65):
            raise ValueError(f'{case["episode_id"]} raw H5 schema, close or T/T+1 counts are invalid')
        raw_meta = root['meta/env_meta'][()]
        if isinstance(raw_meta, bytes):
            raw_meta = raw_meta.decode('utf-8')
        metadata = yaml.safe_load(str(raw_meta))
        raw_controls = root['meta/structured_controls_v1_json'][()]
        if isinstance(raw_controls, bytes):
            raw_controls = raw_controls.decode('utf-8')
        controls = json.loads(str(raw_controls))
        raw_outcome = root['meta/episode_outcome_v1_json'][()]
        if isinstance(raw_outcome, bytes):
            raw_outcome = raw_outcome.decode('utf-8')
        outcome = json.loads(str(raw_outcome))
        stop_reason = str(root.attrs.get('stop_reason', ''))
        boundary = root['obs/state/boundary_identity_sha256'][...]
        full_joint_state = root['obs/state/joint_position'][...]
        arm_joint_state = root['obs/state/entities/panda-arm/joint_position'][...]
        hand_joint_state = root['obs/state/entities/panda-hand/joint_position'][...]
    profile = metadata.get('reference_profile')
    if not isinstance(profile, dict) or profile.get('profile_id') != 'r03c-attached-entity-position-leaves-v1':
        raise ValueError(f'{case["episode_id"]} raw H5 has no strict attached-leaf profile')
    expected = case['candidate']
    joins = {
        'task_source_identity_sha256': expected['task_source_identity_sha256'],
        'task_artifact_identity_hash': expected['task_artifact_identity_sha256'],
        'scene_identity_hash': expected['scene_identity_sha256'],
        'assembly_identity_sha256': expected['assembly_identity_sha256'],
        'attachment_plan_identity_sha256': expected['attachment_plan_identity_sha256'],
        'effective_leaf_plan_identity_sha256': expected['leaf_plan_identity_sha256'],
        'reset_plan_identity_hash': expected['reset_plan_identity_sha256'],
        'reset_sample_id': expected['reset_sample_id'],
        'source_closure_digest': expected['source_closure_sha256'],
        'episode_id': case['episode_id'],
    }
    for key, value in joins.items():
        if profile.get(key) != value:
            raise ValueError(f'{case["episode_id"]} raw H5/profile join mismatch at {key}')
    receipt = profile.get('attachment_receipt')
    if not isinstance(receipt, dict):
        raise ValueError(f'{case["episode_id"]} raw H5 has no fixed Attachment receipt')
    receipt_hash = receipt.get('receipt_identity_sha256')
    receipt_payload = dict(receipt)
    receipt_payload.pop('receipt_identity_sha256', None)
    calculated = hashlib.sha256(json.dumps(
        receipt_payload, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False,
    ).encode()).hexdigest()
    if receipt_hash != calculated or receipt_hash != profile.get('attachment_receipt_identity_sha256'):
        raise ValueError(f'{case["episode_id"]} raw Attachment receipt self-hash mismatch')
    native_expected = case['native_expected']
    for field in ('native_body_order', 'native_joint_order', 'native_actuator_order'):
        if receipt.get(field) != native_expected[field]:
            raise ValueError(f'{case["episode_id"]} raw receipt has wrong {field}')
    actuator_maps = receipt.get('native_actuator_mappings')
    if not isinstance(actuator_maps, dict):
        raise ValueError(f'{case["episode_id"]} raw receipt has no named actuator map')
    slot_map = {key: row['ctrl_slot'] for key, row in actuator_maps.items()}
    if slot_map != native_expected['actuator_slots']:
        raise ValueError(f'{case["episode_id"]} raw receipt does not bind names to actual ctrl slots')
    leaf_receipt = profile.get('leaf_materialization_receipt')
    if (not isinstance(leaf_receipt, dict)
            or leaf_receipt.get('materialization_id') != profile.get('provider_materialization_id')
            or leaf_receipt.get('scene_identity_sha256') != expected['scene_identity_sha256']
            or leaf_receipt.get('source_closure_sha256') != expected['source_closure_sha256']
            or leaf_receipt.get('fixed_attachment_receipt_identity_sha256') != receipt_hash):
        raise ValueError(f'{case["episode_id"]} raw leaf/fixed receipts do not join to the same run')
    if (len(controls) != 64 or boundary.shape != (65, 32) or boundary.dtype.name != 'uint8'
            or full_joint_state.shape != (65, 9) or arm_joint_state.shape != (65, 7)
            or hand_joint_state.shape != (65, 2)
            or not np.isfinite(full_joint_state).all()
            or not np.array_equal(full_joint_state, np.concatenate((arm_joint_state, hand_joint_state), axis=1))
            or outcome.get('end_reason') != stop_reason):
        raise ValueError(f'{case["episode_id"]} raw H5 boundary/state-order/control/outcome arrays are invalid')
    profile_writers = profile.get('writers')
    if not isinstance(profile_writers, list) or len(profile_writers) != 2:
        raise ValueError(f'{case["episode_id"]} raw H5 profile does not declare both canonical writers')
    profile_writer_by_id = {writer.get('writer_id'): writer for writer in profile_writers
                            if isinstance(writer, dict)}
    if len(profile_writer_by_id) != 2:
        raise ValueError(f'{case["episode_id"]} raw H5 profile writer identities are duplicated')
    seen_slots = set()
    checked_writer_slots = {'arm': 0, 'hand': 0}
    for index, control in enumerate(controls):
        if not isinstance(control, dict) or not isinstance(control.get('writer_controls'), list):
            raise ValueError(f'{case["episode_id"]}/{index} raw structured control row is malformed')
        writers = control['writer_controls']
        if len(writers) != 2:
            raise ValueError(f'{case["episode_id"]}/{index} does not contain both leaf writers')
        writer_ids = set()
        next_boundaries = []
        for writer in writers:
            writer_id = writer.get('writer_id')
            if writer_id not in {'panda-arm/arm-position-leaf', 'panda-hand/hand-position-leaf'}:
                raise ValueError(f'{case["episode_id"]}/{index} has an unknown leaf writer')
            if writer_id in writer_ids:
                raise ValueError(f'{case["episode_id"]}/{index} duplicates a leaf writer')
            writer_ids.add(writer_id)
            canonical = writer['canonical_action']
            target = writer.get('controller_target')
            target_payload = target.get('payload') if isinstance(target, dict) else None
            target_hash = target.get('identity_hash') if isinstance(target, dict) else None
            calculated_target_hash = hashlib.sha256(json.dumps(
                target_payload, sort_keys=True, separators=(',', ':'),
                ensure_ascii=False, allow_nan=False,
            ).encode()).hexdigest() if isinstance(target_payload, dict) else None
            profile_writer = profile_writer_by_id.get(writer_id)
            target_action = target_payload.get('action') if isinstance(target_payload, dict) else None
            target_joint_order = target_payload.get('joint_order') if isinstance(target_payload, dict) else None
            target_actuator_order = target_payload.get('actuator_order') if isinstance(target_payload, dict) else None
            expected_joint_order = [
                {'entity_id': entity, 'joint_id': joint}
                for entity, joint in profile_writer.get('joint_order', ())
            ] if isinstance(profile_writer, dict) else None
            expected_actuator_order = [
                {'entity_id': entity, 'actuator_id': actuator}
                for entity, actuator in profile_writer.get('actuator_order', ())
            ] if isinstance(profile_writer, dict) else None
            ack = canonical.get('application_ack')
            applied_payload = writer.get('applied_control', {}).get('payload', {})
            applied_ack = applied_payload.get('ack')
            source_boundary = canonical.get('source_boundary')
            next_boundary = canonical.get('next_boundary')
            source_clock = ack.get('source_sample_clock') if isinstance(ack, dict) else None
            if (not isinstance(target_payload, dict) or not isinstance(target_action, dict)
                    or target_hash != calculated_target_hash
                    or canonical.get('target_identity_sha256') != target_hash
                    or target_payload.get('writer_id') != writer_id
                    or target_payload.get('scene_identity_hash') != expected['scene_identity_sha256']
                    or target_payload.get('source_closure_sha256') != expected['source_closure_sha256']
                    or target_joint_order != expected_joint_order
                    or target_actuator_order != expected_actuator_order
                    or profile_writer is None
                    or (profile_writer.get('action_schema_id') == 'arm-position-action-v1'
                        and target_action.get('joint_order') != expected_joint_order)
                    or profile_writer.get('writer_id') != writer_id):
                raise ValueError(f'{case["episode_id"]}/{index}/{writer_id} Target identity/order/source mismatch')
            if (not isinstance(ack, dict) or ack != applied_ack
                    or ack.get('writer_id') != writer_id
                    or ack.get('target_identity_hash') != target_hash
                    or ack.get('scene_identity_hash') != expected['scene_identity_sha256']
                    or ack.get('source_closure_sha256') != expected['source_closure_sha256']
                    or ack.get('joint_order') != expected_joint_order
                    or ack.get('actuator_order') != expected_actuator_order
                    or not isinstance(source_boundary, dict)
                    or source_boundary.get('control_step') != index
                    or not isinstance(next_boundary, dict)
                    or next_boundary.get('control_step') != index + 1
                    or ack.get('source_boundary') != source_boundary
                    or ack.get('application_boundary', {}).get('control_step') != index
                    or not isinstance(source_clock, dict)
                    or source_clock.get('sample_index') != index
                    or abs(float(source_clock.get('simulation_time_s', -1.0)) - index * 0.01) > 1e-12
                    or ack.get('application_sample_clock') != source_clock):
                raise ValueError(f'{case["episode_id"]}/{index}/{writer_id} Ack/boundary/clock mismatch')
            next_boundaries.append(next_boundary)
            command = canonical['prepared_command']
            slot_values = command.get('slot_values')
            if not isinstance(slot_values, list) or not slot_values:
                raise ValueError(f'{case["episode_id"]}/{index}/{writer_id} lacks prepared native slots')
            local_slots = []
            for slot in slot_values:
                actuator = slot['actuator']
                key = f"{actuator['entity_id']}/{actuator['actuator_id']}"
                if slot['ctrl_slot'] != native_expected['actuator_slots'].get(key):
                    raise ValueError(f'{case["episode_id"]}/{index} command slot does not match named actuator {key}')
                local_slots.append(slot['ctrl_slot'])
            payload = writer['applied_control']['payload']
            if tuple(payload.get('applied_slots', ())) != tuple(local_slots):
                raise ValueError(f'{case["episode_id"]}/{index}/{writer_id} applied slots differ from prepared command')
            if seen_slots.intersection(local_slots):
                raise ValueError(f'{case["episode_id"]}/{index} writers alias a native ctrl slot')
            seen_slots.update(local_slots)
            checked_writer_slots['arm' if writer_id.startswith('panda-arm/') else 'hand'] += len(local_slots)
        # Slots are unique within one boundary and must cover all eight native
        # controls after both writers have been applied.
        if writer_ids != {'panda-arm/arm-position-leaf', 'panda-hand/hand-position-leaf'} or seen_slots != set(range(8)):
            raise ValueError(f'{case["episode_id"]}/{index} accepted slots do not cover all eight controls')
        if next_boundaries[0] != next_boundaries[1]:
            raise ValueError(f'{case["episode_id"]}/{index} writer next-boundary publications diverge')
        seen_slots.clear()
    if not all(checked_writer_slots.values()):
        raise ValueError(f'{case["episode_id"]} one or more writers recorded no native ctrl slots')
    imported_forbidden = [name for name in sys.modules
                          if name == 'task_env' or name.startswith('task_env.')
                          or name == 'mujoco' or name.startswith('mujoco.')]
    if imported_forbidden:
        raise RuntimeError(f'raw witness imported a forbidden Core/provider module: {imported_forbidden[:5]}')
    return {
        'episode_id': case['episode_id'], 'path': str(path), 'sha256': _sha(path),
        'bytes': path.stat().st_size, 'transition_count': 64, 'observation_count': 65,
        'task_artifact_identity_sha256': expected['task_artifact_identity_sha256'],
        'scene_identity_sha256': expected['scene_identity_sha256'],
        'source_closure_sha256': expected['source_closure_sha256'],
        'attachment_receipt_identity_sha256': receipt_hash,
        'provider_materialization_id': profile['provider_materialization_id'],
        'native_body_order': receipt['native_body_order'],
        'native_joint_order': receipt['native_joint_order'],
        'native_actuator_order': receipt['native_actuator_order'],
        'named_actuator_slots': slot_map,
        'checked_writer_slot_values': checked_writer_slots,
        'outcome': outcome,
        'forbidden_imports_seen': imported_forbidden,
    }


def run_readback(contract_path: Path, native_result_path: Path) -> dict[str, object]:
    contract = json.loads(contract_path.read_text())
    result = json.loads(native_result_path.read_text())
    if result.get('status') != 'R06B_NATIVE_WORKER_PASS_PENDING_READBACK':
        raise ValueError('raw H5 witness requires one completed same-worker native receipt')
    if result.get('contract_sha256') != contract.get('contract_sha256'):
        raise ValueError('native worker result is not bound to the frozen R06b contract')
    cases = []
    for case in contract['cases']:
        path = Path(contract['output_dir']) / 'cases' / case['episode_id'] / f"{case['episode_id']}.h5"
        if not path.is_file():
            raise FileNotFoundError(path)
        cases.append(_read_h5(path, case))
    if (len(cases) != 2 or cases[0]['provider_materialization_id'] == cases[1]['provider_materialization_id']
            or cases[0]['scene_identity_sha256'] == cases[1]['scene_identity_sha256']
            or cases[0]['source_closure_sha256'] == cases[1]['source_closure_sha256']):
        raise ValueError('raw H5 cases do not preserve distinct same-worker Run/Scene/source identities')
    forbidden = [name for name in sys.modules
                 if name == 'task_env' or name.startswith('task_env.')
                 or name == 'mujoco' or name.startswith('mujoco.')]
    if forbidden:
        raise RuntimeError(f'raw reader process imported a forbidden Core/provider module: {forbidden[:5]}')
    receipt = {
        'status': 'INDEPENDENT_RAW_H5_READBACK_PASS',
        'reader': 'stdlib+h5py+PyYAML; no TaskEnv/provider imports',
        'cases': cases,
        'materialization_ids_distinct': True,
        'source_scene_closure_ids_distinct': True,
        'forbidden_imports_seen': forbidden,
    }
    output = Path(contract['output_dir']) / 'raw_readback.json'
    output.write_text(json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + '\n')
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--native-result', type=Path, required=True)
    args = parser.parse_args(argv)
    receipt = run_readback(args.contract, args.native_result)
    print(json.dumps({'status': receipt['status'], 'cases': len(receipt['cases'])}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
