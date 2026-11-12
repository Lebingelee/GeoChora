"""Strict R02c/R03c historical experiment judge; independent of Core H5 decoding.

Run with an old H5 path to verify the original fixed experiment gates.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
import hashlib
import json
import math

import numpy as np

from task_env.recorders.h5 import load_structured_control_records_h5
from task_env.trajectory.metadata import plain_metadata


def load_leaf_control_records_h5(path: Path | str) -> dict[str, Any]:
    """Independently validate R02c leaf Target/command/Ack against v3 metadata and observations."""
    from task_env.artifacts.state import StateBoundaryIdentity, StateSampleClock
    from task_env.controllers.canonical.leaf_profiles import decode_leaf_application_ack, decode_leaf_target
    from task_env.runtime.sessions.leaf_control import LeafPreparedCommandV1

    generic = load_structured_control_records_h5(path)
    profile = generic['env_meta'].get('reference_profile')
    if isinstance(profile, Mapping) and profile.get('profile_id') == 'r03c-attached-entity-position-leaves-v1':
        return _load_attached_leaf_control_records_h5(Path(path), generic, profile)
    required_profile = {
        'schema_version', 'profile_id', 'task_artifact_identity_hash',
        'task_source_identity_sha256', 'scene_identity_hash', 'source_id',
        'source_closure_digest', 'effective_leaf_plan_identity_sha256',
        'preset_identity_sha256', 'reset_plan_identity_hash', 'reset_sample_id',
        'provider', 'provider_version', 'provider_build_sha256', 'backend',
        'physics_dt_s', 'control_substeps', 'control_dt_s',
        'materialization_identity_sha256', 'configuration_revision', 'writers',
    }
    if (not isinstance(profile, Mapping) or set(profile) != required_profile
            or profile.get('schema_version') != 'leaf-position-recording-profile-v1'
            or profile.get('profile_id') != 'r02c-independent-position-leaves-v1'):
        raise ValueError('task-env-h5/v3 does not contain the exact R02c leaf recording profile')
    writers = profile['writers']
    if not isinstance(writers, list) or len(writers) != 2:
        raise ValueError('R02c H5 metadata must identify exactly two leaf writers')
    writer_by_id = {}
    for writer in writers:
        if not isinstance(writer, Mapping) or set(writer) != {
            'writer_id', 'profile_kind', 'action_schema_id', 'binding_identity_sha256',
            'effective_configuration_identity_sha256', 'member_path', 'entity_id',
            'control_group_id', 'joint_order', 'actuator_order',
        }:
            raise ValueError('R02c H5 writer binding metadata has unknown or missing fields')
        if writer['writer_id'] in writer_by_id:
            raise ValueError('R02c H5 writer identity is duplicated')
        writer_by_id[writer['writer_id']] = writer
    if {item.get('profile_kind') for item in writers} != {'arm_position', 'hand_position'}:
        raise ValueError('R02c H5 must bind one Arm and one Position Hand leaf')
    if (profile['provider'], profile['provider_version'], profile['backend'],
            profile['physics_dt_s'], profile['control_substeps'], profile['control_dt_s']) != (
            'mujoco', '3.8.1', 'cpu', 0.002, 5, 0.01):
        raise ValueError('R02c H5 Provider/timebase metadata differs from the admitted source route')
    transition_count = generic['transition_count']
    observation_count = generic['observation_count']
    if transition_count != 64 or observation_count != 65:
        raise ValueError('R02c H5 requires exactly 64 transitions and 65 observations')
    with __import__('h5py').File(Path(path), 'r') as root:
        if 'obs/state/boundary_identity_sha256' not in root:
            raise ValueError('R02c H5 lacks the independent stored state-boundary observation')
        state_boundary_digests = np.asarray(root['obs/state/boundary_identity_sha256'][...])
    if state_boundary_digests.shape != (65, 32) or state_boundary_digests.dtype != np.uint8:
        raise ValueError('R02c H5 state-boundary observation has the wrong shape or dtype')
    controls = generic['structured_controls']
    for index, control in enumerate(controls):
        if (control is None or control.request.scene_identity_hash != profile['scene_identity_hash']
                or control.request.binding_identity_hash != profile['effective_leaf_plan_identity_sha256']):
            raise ValueError(f'R02c transition {index} is not bound to the H5 Scene/plan')
        if len(control.writer_controls) != 2:
            raise ValueError(f'R02c transition {index} must record exactly two leaf writers')
        records = {item['writer_id']: item for item in control.writer_controls}
        if set(records) != set(writer_by_id):
            raise ValueError(f'R02c transition {index} omits or duplicates a leaf writer')
        seen_slots = set()
        for writer_id, writer_meta in writer_by_id.items():
            row = records[writer_id]
            canonical = row['canonical_action']
            if not isinstance(canonical, Mapping) or canonical.get('schema_version') != 'leaf-canonical-action-v1':
                raise ValueError(f'R02c transition {index}/{writer_id} lacks a versioned canonical command')
            for key, expected in (
                ('source_closure_sha256', profile['source_closure_digest']),
                ('effective_plan_identity_sha256', profile['effective_leaf_plan_identity_sha256']),
                ('materialization_identity_sha256', profile['materialization_identity_sha256']),
                ('configuration_identity_sha256', writer_meta['effective_configuration_identity_sha256']),
            ):
                if canonical.get(key) != expected:
                    raise ValueError(f'R02c transition {index}/{writer_id} has mismatched {key}')
            target = decode_leaf_target(row['controller_target']['payload'])
            if (target.identity_hash != row['controller_target']['identity_hash']
                    or target.writer_id != writer_id
                    or target.binding_identity_hash != writer_meta['binding_identity_sha256']
                    or target.scene_identity_hash != profile['scene_identity_hash']
                    or target.source_closure_sha256 != profile['source_closure_digest']
                    or target.action_schema_id != writer_meta['action_schema_id']
                    or tuple(ref.joint_id for ref in target.joint_order) != tuple(writer_meta['joint_order'])
                    or tuple(ref.actuator_id for ref in target.actuator_order) != tuple(writer_meta['actuator_order'])
                    or any(ref.entity_id != writer_meta['entity_id']
                           for ref in (*target.joint_order, *target.actuator_order))
                    or canonical.get('target_identity_sha256') != target.identity_hash):
                raise ValueError(f'R02c transition {index}/{writer_id} Target identity/source mismatch')
            if json.dumps(plain_metadata(row['requested_action'].get('payload')), sort_keys=True, separators=(',', ':'),
                          allow_nan=False) != json.dumps(target.action.to_mapping(), sort_keys=True,
                                                       separators=(',', ':'), allow_nan=False):
                raise ValueError(f'R02c transition {index}/{writer_id} requested Action differs from the Target')
            command = LeafPreparedCommandV1.from_mapping(canonical['prepared_command'])
            if (command.command_identity_sha256 != canonical.get('command_identity_sha256')
                    or command.target != target or command.writer_id != writer_id
                    or command.effective_plan_identity_sha256 != profile['effective_leaf_plan_identity_sha256']
                    or command.binding_identity_sha256 != writer_meta['binding_identity_sha256']
                    or command.effective_configuration_identity_sha256
                    != writer_meta['effective_configuration_identity_sha256']
                    or command.materialization_identity_sha256 != profile['materialization_identity_sha256']
                    or command.state_boundary != target.source_boundary
                    or command.state_configuration_revision != profile['configuration_revision']):
                raise ValueError(f'R02c transition {index}/{writer_id} prepared command identity mismatch')
            ack = decode_leaf_application_ack(canonical['application_ack'])
            applied = row['applied_control']
            applied_payload = applied['payload']
            applied_ack = decode_leaf_application_ack(applied_payload['ack'])
            if (ack != applied_ack or applied['target_hash'] != target.identity_hash
                    or ack.target_identity_hash != target.identity_hash
                    or applied_payload.get('writer_id') != writer_id
                    or applied_payload.get('command_identity_sha256') != command.command_identity_sha256
                    or applied_payload.get('materialization_identity_sha256') != profile['materialization_identity_sha256']
                    or ack.writer_id != writer_id
                    or ack.binding_identity_hash != writer_meta['binding_identity_sha256']
                    or ack.source_closure_sha256 != profile['source_closure_digest']
                    or ack.scene_identity_hash != profile['scene_identity_hash']
                    or ack.joint_order != target.joint_order
                    or ack.actuator_order != target.actuator_order
                    or ack.source_boundary != target.source_boundary
                    or ack.source_sample_clock != target.sample_clock
                    or ack.application_sample_clock != target.sample_clock):
                raise ValueError(f'R02c transition {index}/{writer_id} application Ack/command mismatch')
            slots = tuple(item.ctrl_slot for item in command.slot_values)
            if (tuple(applied_payload.get('applied_slots', ())) != slots
                    or seen_slots.intersection(slots)):
                raise ValueError(f'R02c transition {index}/{writer_id} duplicate/mismatched native ctrl slots')
            seen_slots.update(slots)
            source = target.source_boundary
            next_boundary = StateBoundaryIdentity.from_mapping(canonical['next_boundary'])
            if (source.control_step != index or next_boundary.control_step != index + 1
                    or ack.source_boundary != source
                    or ack.application_boundary.control_step != index
                    or (source.episode_id, source.reset_sample_id, source.scene_identity_hash,
                        source.provider_materialization_id) != (
                        next_boundary.episode_id, next_boundary.reset_sample_id,
                        next_boundary.scene_identity_hash, next_boundary.provider_materialization_id)
                    or target.sample_clock.sample_index != index
                    or not math.isclose(
                        target.sample_clock.simulation_time_s,
                        index * profile['control_dt_s'], rel_tol=0.0, abs_tol=1e-12,
                    )
                    or ack.application_sample_clock != target.sample_clock):
                raise ValueError(f'R02c transition {index}/{writer_id} boundary/clock sequence mismatch')
            if (canonical.get('source_boundary') != source.to_mapping()
                    or canonical.get('application_boundary') != ack.application_boundary.to_mapping()):
                raise ValueError(f'R02c transition {index}/{writer_id} Target/Ack boundaries disagree')
            for boundary_index, boundary in ((index, source), (index + 1, next_boundary)):
                digest = bytes(state_boundary_digests[boundary_index]).hex()
                if digest != boundary.boundary_id.removeprefix('state-boundary-'):
                    raise ValueError(f'R02c transition {index}/{writer_id} boundary differs from stored observation')
    generic['leaf_profile'] = profile
    generic['leaf_writer_ids'] = tuple(sorted(writer_by_id))
    return generic


def _load_attached_leaf_control_records_h5(path: Path, generic: dict[str, Any], profile: Mapping) -> dict[str, Any]:
    """Strict offline reader for the R03c fixed Attachment + two Entity leaf receipt chain."""
    from task_env.artifacts.state import StateBoundaryIdentity
    from task_env.controllers.canonical.leaf_profiles import decode_leaf_application_ack, decode_leaf_target
    from task_env.runtime.sessions.leaf_control import LeafPreparedCommandV1

    required = {
        'schema_version', 'profile_id', 'task_artifact_identity_hash', 'task_source_identity_sha256',
        'scene_identity_hash', 'source_id', 'source_closure_digest',
        'effective_leaf_plan_identity_sha256', 'preset_identity_sha256', 'reset_plan_identity_hash',
        'reset_sample_id', 'provider', 'provider_version', 'provider_build_sha256', 'backend',
        'physics_dt_s', 'control_substeps', 'control_dt_s', 'materialization_identity_sha256',
        'configuration_revision', 'attachment_plan_identity_sha256', 'assembly_identity_sha256',
        'attachment_receipt', 'attachment_receipt_identity_sha256', 'leaf_materialization_receipt',
        'leaf_materialization_receipt_identity_sha256', 'provider_materialization_id', 'episode_id',
        'arm_active', 'hand_active', 'writers',
    }
    if set(profile) != required or profile.get('schema_version') != 'leaf-position-recording-profile-v1':
        raise ValueError('R03c H5 metadata does not match the exact attached-leaf profile schema')
    if (profile['provider'], profile['provider_version'], profile['backend'],
            profile['physics_dt_s'], profile['control_substeps'], profile['control_dt_s']) != (
            'mujoco', '3.8.1', 'cpu', 0.002, 5, 0.01):
        raise ValueError('R03c H5 Provider/timebase differs from the bounded native contract')
    if (type(profile['arm_active']) is not bool or type(profile['hand_active']) is not bool
            or profile['episode_id'] not in {'E1', 'E2', 'E3', 'E4'}):
        raise ValueError('R03c H5 episode identity/activity metadata is invalid')
    if (generic['transition_count'], generic['observation_count']) != (64, 65):
        raise ValueError('R03c H5 requires exactly 64 transitions and 65 observations')

    attachment = profile['attachment_receipt']
    if not isinstance(attachment, Mapping):
        raise ValueError('R03c H5 lacks its same-Env fixed Attachment model receipt')
    receipt_payload = dict(attachment)
    receipt_hash = receipt_payload.pop('receipt_identity_sha256', None)
    calculated_receipt_hash = hashlib.sha256(json.dumps(
        receipt_payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False,
    ).encode()).hexdigest()
    if (receipt_hash != calculated_receipt_hash
            or receipt_hash != profile['attachment_receipt_identity_sha256']
            or attachment.get('schema_version') != 'fixed-attachment-model-receipt-v1'
            or attachment.get('provider') != 'mujoco' or attachment.get('backend') != 'cpu'
            or attachment.get('provider_materialization_id') != profile['provider_materialization_id']
            or attachment.get('task_artifact_sha256') != profile['task_artifact_identity_hash']
            or attachment.get('scene_identity_sha256') != profile['scene_identity_hash']
            or attachment.get('assembly_identity_sha256') != profile['assembly_identity_sha256']
            or attachment.get('attachment_plan_sha256') != profile['attachment_plan_identity_sha256']
            or attachment.get('source_closure_sha256') != profile['source_closure_digest']):
        raise ValueError('R03c Attachment receipt identity/source/Runtime binding mismatch')
    dimensions = attachment.get('dimensions', {})
    if tuple(dimensions.get(key) for key in ('nq', 'nv', 'nu', 'njnt', 'neq', 'ntendon')) != (9, 9, 8, 9, 1, 1):
        raise ValueError('R03c Attachment receipt dimensions differ from the exact fixed tree')
    fixed_root = attachment.get('fixed_root', {})
    if (fixed_root.get('parent_entity_id'), fixed_root.get('child_entity_id'),
            fixed_root.get('parent_mount'), fixed_root.get('child_mount'), fixed_root.get('root_policy')) != (
            'panda-arm', 'panda-hand', 'panda-arm/attachment_site', 'panda-hand/hand',
            'fixed_child_root_under_parent_mount_no_free_joint'):
        raise ValueError('R03c fixed Attachment root receipt is not the selected two-Entity mount')

    canonical_native = {
        'joints': {
            **{f'panda-arm/joint{i}': f'joint{i}' for i in range(1, 8)},
            'panda-hand/finger_joint1': 'probe_hand_finger_joint1',
            'panda-hand/finger_joint2': 'probe_hand_finger_joint2',
        },
        'actuators': {**{f'panda-arm/actuator{i}': f'actuator{i}' for i in range(1, 8)},
                      'panda-hand/actuator8': 'probe_hand_actuator8'},
        'bodies': {'panda-arm/link7': 'link7', 'panda-hand/hand': 'probe_hand_hand'},
        'tendons': {'panda-hand/split': 'probe_hand_split'},
    }
    for receipt_key, section_key in (('native_joint_mappings', 'joints'),
                                     ('native_actuator_mappings', 'actuators'),
                                     ('native_body_mappings', 'bodies'),
                                     ('native_tendon_mappings', 'tendons')):
        mappings = attachment.get(receipt_key)
        if not isinstance(mappings, Mapping):
            raise ValueError(f'R03c Attachment receipt omits {receipt_key}')
        for canonical, native_name in canonical_native[section_key].items():
            if mappings.get(canonical, {}).get('native_name') != native_name:
                raise ValueError(f'R03c Attachment native map mismatch for {canonical}')

    leaf_receipt = profile['leaf_materialization_receipt']
    if not isinstance(leaf_receipt, Mapping):
        raise ValueError('R03c H5 lacks its leaf materialization receipt')
    leaf_identity_payload = {
        'schema_version': leaf_receipt['schema_version'],
        'provenance_kind': leaf_receipt['provenance_kind'],
        'scene_identity_sha256': leaf_receipt['scene_identity_sha256'],
        'source_closure_sha256': leaf_receipt['source_closure_sha256'],
        'effective_plan_identity_sha256': leaf_receipt['effective_plan_identity_sha256'],
        'provider_name': leaf_receipt['provider_name'], 'provider_version': leaf_receipt['provider_version'],
        'provider_build_sha256': leaf_receipt['provider_build_sha256'], 'backend': leaf_receipt['backend'],
        'materialization_id': leaf_receipt['materialization_id'],
        'configuration_revision': leaf_receipt['configuration_revision'],
        'dimensions': tuple(leaf_receipt[name] for name in ('nq', 'nv', 'nu', 'njnt', 'nbody', 'neq', 'ntendon')),
        'joints': leaf_receipt['joints'], 'actuators': leaf_receipt['actuators'],
        'frames': leaf_receipt['frames'], 'tendons': leaf_receipt['tendons'],
        'equality_identities': leaf_receipt['equality_identities'],
    }
    if leaf_receipt.get('fixed_attachment_receipt_identity_sha256') is not None:
        leaf_identity_payload['fixed_attachment_receipt_identity_sha256'] = (
            leaf_receipt['fixed_attachment_receipt_identity_sha256']
        )
    leaf_hash = hashlib.sha256(json.dumps(
        leaf_identity_payload, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False,
    ).encode()).hexdigest()
    if (leaf_hash != profile['leaf_materialization_receipt_identity_sha256']
            or leaf_hash != profile['materialization_identity_sha256']
            or leaf_receipt.get('fixed_attachment_receipt_identity_sha256') != receipt_hash
            or leaf_receipt.get('materialization_id') != profile['provider_materialization_id']
            or leaf_receipt.get('effective_plan_identity_sha256') != profile['effective_leaf_plan_identity_sha256']
            or leaf_receipt.get('scene_identity_sha256') != profile['scene_identity_hash']
            or leaf_receipt.get('source_closure_sha256') != profile['source_closure_digest']
            or leaf_receipt.get('provider_name') != profile['provider']
            or leaf_receipt.get('provider_version') != profile['provider_version']
            or leaf_receipt.get('provider_build_sha256') != profile['provider_build_sha256']
            or leaf_receipt.get('backend') != profile['backend']
            or leaf_receipt.get('configuration_revision') != profile['configuration_revision']):
        raise ValueError('R03c leaf receipt is not bound to the same Attachment Runtime/plan')

    writers = profile['writers']
    if not isinstance(writers, list) or len(writers) != 2:
        raise ValueError('R03c H5 must bind exactly two Entity leaf writers')
    expected_writer_fields = {
        'writer_id', 'profile_kind', 'action_schema_id', 'binding_identity_sha256',
        'effective_configuration_identity_sha256', 'member_path', 'entity_id',
        'control_group_id', 'joint_order', 'actuator_order', 'tcp_frame',
    }
    writer_by_id = {}
    for writer in writers:
        if not isinstance(writer, Mapping) or set(writer) != expected_writer_fields:
            raise ValueError('R03c writer metadata has an unknown or missing bound field')
        if writer['writer_id'] in writer_by_id:
            raise ValueError('R03c writer identity is duplicated')
        writer_by_id[writer['writer_id']] = writer
    expected_owner = {
        'panda-arm/arm-position-leaf': ('arm_position', 'panda-arm', 'arm-position', ['arm']),
        'panda-hand/hand-position-leaf': ('hand_position', 'panda-hand', 'hand-position', ['hand']),
    }
    for writer_id, (kind, entity, group, path_members) in expected_owner.items():
        writer = writer_by_id.get(writer_id)
        if (writer is None or writer['profile_kind'] != kind or writer['entity_id'] != entity
                or writer['control_group_id'] != group or writer['member_path'] != path_members):
            raise ValueError(f'R03c writer {writer_id} is not bound to its exact Assembly Entity/Group')
    leaf_joints = {item['canonical_joint']['entity_id'] + '/' + item['canonical_joint']['joint_id']: item
                   for item in leaf_receipt['joints']}
    leaf_actuators = {item['canonical_actuator']['entity_id'] + '/' + item['canonical_actuator']['actuator_id']: item
                      for item in leaf_receipt['actuators']}
    leaf_frames = {item['canonical_frame']['entity_id'] + '/' + item['canonical_frame']['frame_id']: item
                   for item in leaf_receipt['frames']}
    for writer_id, writer in writer_by_id.items():
        for entity, joint in writer['joint_order']:
            key = f'{entity}/{joint}'
            mapped = leaf_joints.get(key)
            if mapped is None or mapped['native_name'] != canonical_native['joints'][key]:
                raise ValueError(f'R03c leaf Joint native receipt mismatch: {key}')
        for entity, actuator in writer['actuator_order']:
            key = f'{entity}/{actuator}'
            mapped = leaf_actuators.get(key)
            if mapped is None or mapped['native_name'] != canonical_native['actuators'][key]:
                raise ValueError(f'R03c leaf Actuator native receipt mismatch: {key}')
            attachment_actuator = attachment['native_actuator_mappings'][key]
            if (mapped['ctrl_slot'] != attachment_actuator['ctrl_slot']
                    or mapped['native_actuator_id'] != attachment_actuator['actuator_id']):
                raise ValueError(f'R03c leaf Actuator slot differs from Attachment receipt: {key}')
        entity, frame = writer['tcp_frame']
        key = f'{entity}/{frame}'
        mapped = leaf_frames.get(key)
        if mapped is None or mapped['native_name'] != canonical_native['bodies'][key]:
            raise ValueError(f'R03c leaf TCP native receipt mismatch: {key}')

    with __import__('h5py').File(path, 'r') as root:
        required_arrays = {
            'obs/state/boundary_identity_sha256': ((65, 32), np.dtype(np.uint8)),
            'obs/state/entities/panda-arm/joint_position': ((65, 7), np.dtype(np.float32)),
            'obs/state/entities/panda-hand/joint_position': ((65, 2), np.dtype(np.float32)),
            'obs/state/entities/panda-arm/hand_pose': ((65, 7), np.dtype(np.float32)),
            'obs/state/entities/panda-hand/hand_pose': ((65, 7), np.dtype(np.float32)),
        }
        arrays = {}
        for dataset_path, (shape, dtype) in required_arrays.items():
            if dataset_path not in root:
                raise ValueError(f'R03c H5 lacks stored typed observation {dataset_path}')
            array = np.asarray(root[dataset_path][...])
            if array.shape != shape or array.dtype != dtype or not np.isfinite(array).all():
                raise ValueError(f'R03c H5 stored observation shape/dtype/finite mismatch: {dataset_path}')
            arrays[dataset_path] = array
        arm = arrays['obs/state/entities/panda-arm/joint_position']
        fingers = arrays['obs/state/entities/panda-hand/joint_position']
        opening = fingers.sum(axis=1)
        home = np.asarray((0.0, 0.0, 0.0, -1.57079, 0.0, 1.57079, -0.7853), dtype=np.float64)
        if np.max(np.abs(arm[-1].astype(np.float64) - home)) > 0.02:
            raise ValueError('R03c stored Arm final state is outside the home-return gate')
        if profile['arm_active'] and np.max(np.abs(arm[:, 0].astype(np.float64) - home[0])) < 0.08:
            raise ValueError('R03c stored Arm motion does not reach the required joint1 excursion')
        if float(opening[-1]) < 0.06:
            raise ValueError('R03c stored Hand opening does not return to the final open gate')
        if profile['hand_active'] and (
                float(np.min(opening[16:33])) > 0.02
                or float(np.max(opening) - np.min(opening)) < 0.04
                or np.max(np.abs(fingers[:, 0] - fingers[:, 1])) > 1e-4):
            raise ValueError('R03c stored Hand motion/equality differs from its closed-phase gate')
        hand_pose = arrays['obs/state/entities/panda-hand/hand_pose'][:, 3:7].astype(np.float64)
        norms = np.linalg.norm(hand_pose, axis=1, keepdims=True)
        if np.any(norms <= 1e-12):
            raise ValueError('R03c stored Hand rotation contains a zero quaternion')
        quats = hand_pose / norms
        dots = np.clip(np.abs(quats @ quats[0]), 0.0, 1.0)
        rotation_excursion = float(np.max(2.0 * np.arccos(dots)))
        if profile['arm_active'] and rotation_excursion < 0.05:
            raise ValueError('R03c stored attached Hand root did not follow active Arm rotation')
        state_boundary_digests = arrays['obs/state/boundary_identity_sha256']

    controls = generic['structured_controls']
    for index, control in enumerate(controls):
        if (control is None or control.request.scene_identity_hash != profile['scene_identity_hash']
                or control.request.binding_identity_hash != profile['effective_leaf_plan_identity_sha256']):
            raise ValueError(f'R03c transition {index} is not bound to the H5 Scene/plan')
        if len(control.writer_controls) != 2:
            raise ValueError(f'R03c transition {index} must record exactly two writers')
        records = {item['writer_id']: item for item in control.writer_controls}
        if set(records) != set(writer_by_id):
            raise ValueError(f'R03c transition {index} omits or duplicates an Entity writer')
        seen_slots = set()
        for writer_id, writer_meta in writer_by_id.items():
            row = records[writer_id]
            canonical = row['canonical_action']
            for key, expected_value in (
                ('source_closure_sha256', profile['source_closure_digest']),
                ('effective_plan_identity_sha256', profile['effective_leaf_plan_identity_sha256']),
                ('materialization_identity_sha256', profile['materialization_identity_sha256']),
                ('configuration_identity_sha256', writer_meta['effective_configuration_identity_sha256']),
            ):
                if canonical.get(key) != expected_value:
                    raise ValueError(f'R03c transition {index}/{writer_id} mismatched {key}')
            target = decode_leaf_target(row['controller_target']['payload'])
            expected_joints = tuple((entity, joint) for entity, joint in writer_meta['joint_order'])
            expected_actuators = tuple((entity, actuator) for entity, actuator in writer_meta['actuator_order'])
            if (target.identity_hash != row['controller_target']['identity_hash']
                    or target.writer_id != writer_id
                    or target.binding_identity_hash != writer_meta['binding_identity_sha256']
                    or target.scene_identity_hash != profile['scene_identity_hash']
                    or target.source_closure_sha256 != profile['source_closure_digest']
                    or target.action_schema_id != writer_meta['action_schema_id']
                    or tuple((ref.entity_id, ref.joint_id) for ref in target.joint_order) != expected_joints
                    or tuple((ref.entity_id, ref.actuator_id) for ref in target.actuator_order) != expected_actuators):
                raise ValueError(f'R03c transition {index}/{writer_id} Target binding mismatch')
            if json.dumps(plain_metadata(row['requested_action'].get('payload')), sort_keys=True,
                          separators=(',', ':'), allow_nan=False) != json.dumps(
                    target.action.to_mapping(), sort_keys=True, separators=(',', ':'), allow_nan=False):
                raise ValueError(f'R03c transition {index}/{writer_id} Action differs from typed Target')
            command = LeafPreparedCommandV1.from_mapping(canonical['prepared_command'])
            if (command.command_identity_sha256 != canonical.get('command_identity_sha256')
                    or command.target != target or command.writer_id != writer_id
                    or command.effective_plan_identity_sha256 != profile['effective_leaf_plan_identity_sha256']
                    or command.binding_identity_sha256 != writer_meta['binding_identity_sha256']
                    or command.effective_configuration_identity_sha256
                    != writer_meta['effective_configuration_identity_sha256']
                    or command.materialization_identity_sha256 != profile['materialization_identity_sha256']
                    or command.state_boundary != target.source_boundary
                    or command.state_configuration_revision != profile['configuration_revision']):
                raise ValueError(f'R03c transition {index}/{writer_id} prepared command mismatch')
            ack = decode_leaf_application_ack(canonical['application_ack'])
            applied = row['applied_control']
            payload = applied['payload']
            applied_ack = decode_leaf_application_ack(payload['ack'])
            slots = tuple(item.ctrl_slot for item in command.slot_values)
            if (ack != applied_ack or ack.target_identity_hash != target.identity_hash
                    or ack.writer_id != writer_id
                    or ack.binding_identity_hash != writer_meta['binding_identity_sha256']
                    or ack.source_closure_sha256 != profile['source_closure_digest']
                    or ack.scene_identity_hash != profile['scene_identity_hash']
                    or ack.joint_order != target.joint_order or ack.actuator_order != target.actuator_order
                    or ack.source_boundary != target.source_boundary
                    or ack.source_sample_clock != target.sample_clock
                    or ack.application_sample_clock != target.sample_clock
                    or payload.get('writer_id') != writer_id
                    or payload.get('materialization_identity_sha256') != profile['materialization_identity_sha256']
                    or tuple(payload.get('applied_slots', ())) != slots
                    or applied.get('target_hash') != target.identity_hash
                    or seen_slots.intersection(slots)):
                raise ValueError(f'R03c transition {index}/{writer_id} Ack/slot evidence mismatch')
            seen_slots.update(slots)
            if any(not 0 <= item.ctrl_slot < dimensions['nu'] for item in command.slot_values):
                raise ValueError(f'R03c transition {index}/{writer_id} slot exceeds fixed model dimensions')
            for item in command.slot_values:
                key = f'{item.actuator.entity_id}/{item.actuator.actuator_id}'
                mapped = leaf_actuators.get(key)
                if mapped is None or item.ctrl_slot != mapped['ctrl_slot']:
                    raise ValueError(f'R03c transition {index}/{writer_id} command slot differs from its Actuator receipt')
            source = target.source_boundary
            next_boundary = StateBoundaryIdentity.from_mapping(canonical['next_boundary'])
            if (source.control_step != index or next_boundary.control_step != index + 1
                    or source.reset_sample_id != profile['reset_sample_id']
                    or source.provider_materialization_id != profile['provider_materialization_id']
                    or (source.episode_id, source.reset_sample_id, source.scene_identity_hash,
                        source.scene_instance_id, source.provider_materialization_id)
                    != (next_boundary.episode_id, next_boundary.reset_sample_id, next_boundary.scene_identity_hash,
                        next_boundary.scene_instance_id, next_boundary.provider_materialization_id)
                    or (ack.application_boundary.episode_id, ack.application_boundary.reset_sample_id,
                        ack.application_boundary.scene_identity_hash, ack.application_boundary.scene_instance_id,
                        ack.application_boundary.provider_materialization_id, ack.application_boundary.control_step)
                    != (source.episode_id, source.reset_sample_id, source.scene_identity_hash,
                        source.scene_instance_id, source.provider_materialization_id, source.control_step)
                    or target.sample_clock.sample_index != index
                    or not math.isclose(target.sample_clock.simulation_time_s,
                                        index * profile['control_dt_s'], rel_tol=0.0, abs_tol=1e-12)
                    or canonical.get('source_boundary') != source.to_mapping()
                    or canonical.get('application_boundary') != ack.application_boundary.to_mapping()):
                raise ValueError(f'R03c transition {index}/{writer_id} boundary/clock sequence mismatch')
            for boundary_index, boundary in ((index, source), (index + 1, next_boundary)):
                if bytes(state_boundary_digests[boundary_index]).hex() != boundary.boundary_id.removeprefix('state-boundary-'):
                    raise ValueError(f'R03c transition {index}/{writer_id} boundary differs from stored observation')
        if seen_slots != set(range(dimensions['nu'])):
            raise ValueError(f'R03c transition {index} does not bind the exact disjoint 7+1 slots')
    generic['leaf_profile'] = profile
    generic['leaf_writer_ids'] = tuple(sorted(writer_by_id))
    generic['attachment_receipt_identity_sha256'] = receipt_hash
    generic['stored_motion_oracle'] = {
        'arm_peak_joint1_rad': float(np.max(np.abs(arm[:, 0].astype(np.float64)))),
        'hand_final_opening_m': float(opening[-1]),
        'hand_rotation_excursion_rad': rotation_excursion,
    }
    return generic



if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    args = parser.parse_args()
    result = load_leaf_control_records_h5(args.path)
    print(json.dumps({'profile': result['leaf_profile']['profile_id'],
                      'transition_count': result['transition_count'],
                      'observation_count': result['observation_count'],
                      'strict_historical_judge': 'pass'}, sort_keys=True))
