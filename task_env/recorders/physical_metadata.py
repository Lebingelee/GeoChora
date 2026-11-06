"""Generic H5 v3 metadata and transition projection for selected physical control."""
from __future__ import annotations

import numpy as np


def physical_record_metadata(env, metadata):
    """Replace Position action identity with the actually selected physical input."""
    spec = env.physical_action_spec()
    kind = spec['kind']
    components = (('x', 'y', 'z', 'qw', 'qx', 'qy', 'qz', 'gripper') if kind == 'r3-pose'
                  else tuple(f'joint{i}' for i in range(1, 8)) + ('opening',))
    result = dict(metadata)
    env_meta = dict(result['env_metadata'])
    env_meta['env_name'] = 'SelectedReferenceEnv.PhysicalControlV1'
    env_meta['action_schema'] = {'schema_id': 'physical-' + spec['spec_id'], 'schema_version': 'physical-reset-action-spec-v1',
                                  'controller_kind': kind, 'components': components}
    observation_schema = dict(env_meta['observation_schema'])
    observation_schema['leaf_specs'] = [
        ({**field, 'semantic': 'source-bound PickCube end-effector site pose'}
         if field.get('path') == 'state.ee_pose' else field)
        for field in observation_schema['leaf_specs']]
    env_meta['observation_schema'] = observation_schema
    env_meta['reference_profile'] = {
        'schema_version': 'physical-control-recording-profile-v1',
        'physical_action_spec_v1': spec,
        'task_artifact_identity_hash': env.artifact.identity_hash,
        'scene_identity_hash': env.position_scene.identity_hash,
        'source_closure_digest': env.value['source'].source_closure_digest,
        'reset_plan_identity_hash': env.value['reset_plan'].identity_hash,
        'reset_sample_id': env.value['reset_plan'].reset_sample.sample_id,
        'provider': env.provider, 'backend': env.backend,
        'solution_identity': env.value.get('solution_identity'),
        'physical_binding_sha256': env._physical_reset_selection.current.execution.compiled.binding.identity_hash,
        'feedback': 'independent force measurement unavailable',
    }
    result['env_metadata'] = env_meta
    result['universal_action_schema'] = {'version': 'physical-reset-action-v1', 'dimension': 8,
                                         'components': components}
    result['resolved_config'] = {**result['resolved_config'], 'physical_action_spec_v1': spec}
    return result


def record_physical_transition(env, action, batch, resolved, ack, *, terminated, truncated):
    """Persist requested input, submitted typed batch and native ACK without inventing measurement."""
    from ..controllers.canonical.contracts import ControlGroupActionV1, StructuredActionRequestV1, digest
    from ..trajectory.canonical.episode import StructuredControlTransitionV1
    from dataclasses import asdict
    spec = env.physical_action_spec()
    values = tuple(float(x) for x in np.asarray(action, dtype=np.float64))
    if len(values) != 8:
        raise ValueError('physical recording requires the declared eight-value action')
    components = (('x', 'y', 'z', 'qw', 'qx', 'qy', 'qz', 'gripper') if spec['kind'] == 'r3-pose'
                  else tuple(f'joint{i}' for i in range(1, 8)) + ('opening',))
    entity = batch.joint_efforts[0].entity_id
    schema_id = 'physical-' + spec['spec_id']
    groups = (ControlGroupActionV1('control-group-action-v1', entity, 'arm', schema_id, values[:7]),
              ControlGroupActionV1('control-group-action-v1', entity, 'gripper', schema_id, values[7:]))
    request = StructuredActionRequestV1('structured-action-request-v1', batch.context.boundary.scene_identity_hash,
                                        env._physical_reset_selection.current.execution.compiled.binding.identity_hash,
                                        groups)
    payload = batch.to_mapping()
    target_hash = digest(payload)
    if target_hash != batch.identity_hash or ack.batch_sha256 != target_hash:
        raise ValueError('physical record batch and acknowledgement identities differ')
    control = StructuredControlTransitionV1('structured-control-transition-v1', request, ({
        'writer_id': env._physical_reset_selection.current.execution.controllers[0].writer_id,
        'action_schema_id': schema_id, 'components': components,
        'groups': ({'entity_id': entity, 'group_id': 'arm', 'action_components': components[:7]},
                   {'entity_id': entity, 'group_id': 'gripper', 'action_components': components[7:]}),
        'requested_action': {'values': values, 'physical_action_spec_v1': spec},
        'canonical_action': {'schema_version': 'physical-input-record-v1', 'interpreted_values': values,
                             'meaning': 'requested input; internal target interpretation unavailable'},
        'controller_target': {'schema_version': batch.schema_version, 'payload': payload, 'identity_hash': target_hash},
        'applied_control': {'schema_version': ack.schema_version,
                            'payload': {'native_write_ack': ack.to_mapping(),
                                        'accepted': resolved.accepted_receipt.to_mapping(),
                                        'admitted_joint_efforts': [asdict(item) for item in resolved.joints],
                                        'independent_measurement': 'unavailable'}, 'target_hash': target_hash},
    },))
    control.validate()
    env.recorder.append_transition(np.asarray(values, dtype=np.float32), np.asarray(values, dtype=np.float32),
        env.obs, float(env.evaluation.reward), bool(env.evaluation.success), bool(terminated), bool(truncated),
        env.info, structured_control=control)
