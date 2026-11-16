"""Strict versioned F05/F06 witness codecs for historical H5 payloads."""
from collections.abc import Mapping
import numpy as np

from .trajectory import FrozenTrajectory


def _validate_f06_typed_state_witness(witness, profile, observation_count, observations=None):
    """Validate actual public state values and request-bound T+1 identities."""
    from task_env.artifacts.state import CanonicalStateViewV1
    schema = 'f06-public-typed-state-witness-v1'
    if not isinstance(witness, Mapping) or witness.get('schema_version') != schema:
        raise ValueError('F06 typed state witness schema missing or invalid')
    rows = witness.get('rows')
    if not isinstance(rows, list) or len(rows) != observation_count or witness.get('observation_count') != observation_count:
        raise ValueError('F06 typed state witness must contain every T+1 boundary')
    expected = tuple([f'joint{i}' for i in range(1, 8)] + ['finger_joint1', 'finger_joint2'])
    if witness.get('joint_order') != list(expected):
        raise ValueError('F06 witness joint order is incomplete')
    if (witness.get('source_closure_digest') != profile.get('source_closure_digest')
            or witness.get('request_identity_sha256') != profile.get('request_identity_sha256')
            or witness.get('materialization_identity') != profile.get('materialization_identity')):
        raise ValueError('F06 witness source/request/materialization differs from profile')
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping) or row.get('boundary_index') != index:
            raise ValueError('F06 typed state witness boundary order mismatch')
        view = CanonicalStateViewV1.from_mapping(row['canonical_state_view_v1'])
        if (view.boundary.control_step != index or view.sample_clock.sample_index != index
                or view.boundary.provider_materialization_id != profile['materialization_identity']
                or view.boundary.reset_sample_id != profile['reset_sample_id']
                or view.boundary.scene_identity_hash != profile['scene_identity_hash']):
            raise ValueError('F06 typed state witness identity or clock mismatch')
        values = {v.joint_id: v for v in view.joints if v.entity_id == 'panda-v1'}
        if set(values) != set(expected):
            raise ValueError('F06 typed state witness requires all nine named joint velocities')
        for name in expected:
            value = values[name]
            unit = 'radian_per_second' if name.startswith('joint') else 'meter_per_second'
            if value.velocity_representation != unit or len(value.velocity) != 1:
                raise ValueError(f'F06 typed state witness has invalid velocity or unit for {name}')
        if not any(v.frame.entity_id == 'panda-v1' and v.frame.frame_id == 'ee' for v in view.frames):
            raise ValueError('F06 typed state witness requires the declared ee frame')
        if observations is not None:
            ee = next(v.pose_world for v in view.frames
                      if v.frame.entity_id == 'panda-v1' and v.frame.frame_id == 'ee')
            expected_pose = np.asarray((*ee.position, *ee.quaternion_wxyz), dtype=np.float32)
            expected_q = np.asarray([values[name].position[0] for name in expected], dtype=np.float32)
            if (not np.array_equal(observations['joint_position'][index], expected_q)
                    or not np.array_equal(observations['ee_pose'][index], expected_pose)
                    or not np.array_equal(observations['hand_pose'][index], expected_pose)
                    or bytes(observations['boundary_identity_sha256'][index]).hex()
                    != view.boundary.boundary_id.removeprefix('state-boundary-')):
                raise ValueError('F06 typed state witness differs from recorded observation or frame')
    return witness


def _f06_typed_state_extension(trajectory):
    metadata = trajectory.record_metadata.get('env_metadata', {})
    profile = metadata.get('reference_profile', {}) if isinstance(metadata, Mapping) else {}
    if not isinstance(profile, Mapping) or profile.get('typed_state_h5_witness_schema_version') != 'f06-public-typed-state-witness-v1':
        return None
    infos = [trajectory.reset_info, *trajectory.infos]
    rows = []
    for index, info in enumerate(infos):
        if not isinstance(info, Mapping) or not isinstance(info.get('canonical_state_view_v1'), Mapping):
            raise ValueError(f'F06 public typed state missing at boundary {index}')
        state = info['canonical_state_view_v1']
        if state.get('boundary') != info.get('state_boundary_identity') or state.get('sample_clock') != info.get('state_sample_clock'):
            raise ValueError(f'F06 typed state boundary or clock disagrees at boundary {index}')
        rows.append({'boundary_index': index, 'canonical_state_view_v1': dict(info['canonical_state_view_v1'])})
    witness = {'schema_version': 'f06-public-typed-state-witness-v1',
               'source': 'public canonical state at evaluation boundary',
               'observation_count': len(trajectory.observations),
               'joint_order': [f'joint{i}' for i in range(1, 8)] + ['finger_joint1', 'finger_joint2'],
               'source_closure_digest': profile['source_closure_digest'],
               'request_identity_sha256': profile['request_identity_sha256'],
               'materialization_identity': profile['materialization_identity'], 'rows': rows}
    return _validate_f06_typed_state_witness(witness, profile, len(trajectory.observations))


def _f05_typed_state_extension(trajectory: FrozenTrajectory):
    """Persist the public T+1 typed-state snapshots for the bounded F05 profile only."""
    metadata = trajectory.record_metadata.get("env_metadata", {})
    profile = metadata.get("reference_profile", {}) if isinstance(metadata, Mapping) else {}
    if not isinstance(profile, Mapping) or profile.get("profile_id") not in {
            "geophys-usd-position-f05-native-v1",
            "geophys-usd-position-f05-dg02-core-v1",
            "f05-dg04-isaac-native-mimic-v1",
    }:
        return None
    if profile.get("typed_state_h5_witness_schema_version") != "f05-public-typed-state-witness-v1":
        raise ValueError("F05 recording metadata does not declare the typed T+1 H5 witness")
    public_infos = [trajectory.reset_info, *trajectory.infos]
    if len(public_infos) != len(trajectory.observations):
        raise ValueError("F05 typed-state witness requires one public reset/step info per T+1 observation")
    rows = []
    for index, info in enumerate(public_infos):
        if not isinstance(info, Mapping):
            raise TypeError("F05 public reset/step info must be a mapping")
        state = info.get("canonical_state_view_v1")
        boundary = info.get("state_boundary_identity")
        clock = info.get("state_sample_clock")
        if not isinstance(state, Mapping) or not isinstance(boundary, Mapping) or not isinstance(clock, Mapping):
            raise ValueError(f"F05 public reset/step info {index} lacks typed state, boundary or clock")
        if state.get("boundary") != boundary or state.get("sample_clock") != clock:
            raise ValueError(f"F05 public typed state {index} differs from its public boundary/clock")
        rows.append({
            "boundary_index": index,
            "state_boundary_identity": dict(boundary),
            "state_sample_clock": dict(clock),
            "canonical_state_view_v1": dict(state),
        })
    return {
        "schema_version": "f05-public-typed-state-witness-v1",
        "source": "SelectedReferenceEnv public reset/step info captured by Generic H5 v3 Recorder",
        "observation_count": len(trajectory.observations),
        "rows": rows,
    }
