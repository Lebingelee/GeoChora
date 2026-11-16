"""Generic H5 v3 metadata and transition projection for selected physical control."""
from __future__ import annotations

import numpy as np


def physical_record_metadata(env):
    """Describe the committed physical Controller and its source-bound state."""
    from ..observations.selected_reference import selected_reference_observation_schema

    selection_owner = getattr(env, '_physical_reset_selection', None)
    execution = env._physical_execution()
    spec = env.physical_action_spec() if selection_owner is not None else None
    kind = spec['kind'] if spec is not None else env.binding.action_schema['mode']
    components = ((('x', 'y', 'z', 'qw', 'qx', 'qy', 'qz', 'gripper') if kind == 'r3-pose'
                   else tuple(f'joint{i}' for i in range(1, 8)) + ('opening',))
                  if spec is not None else tuple(env.binding.action_schema['components']))
    schema = selected_reference_observation_schema(env, env.obs,
        base_schema=getattr(env.binding, 'task_observation_schema', None))
    leaf_specs = [dict(path=item.name, shape=item.shape, dtype=item.dtype,
                       semantic=item.semantic, unit=item.unit, frame=item.frame,
                       time_reference=item.time_reference) for item in schema.fields]
    source = env.value['source']
    reset_plan = env.value['reset_plan']
    artifact = env.artifact
    env_metadata = {
        'env_name': 'SelectedReferenceEnv.PhysicalControlV1',
        'task_name': artifact.task_id, 'task_version': artifact.artifact_version,
        'scene_uid': execution.scene.scene_id,
        'agent_uids': tuple(subject.entity_id for subject in execution.subjects),
        'physics_dt': artifact.timebase.physics_dt,
        'control_substeps': artifact.timebase.control_substeps,
        'control_frequency': 1.0 / artifact.timebase.control_dt,
        'action_schema': {'schema_id': ('physical-' + spec['spec_id'] if spec is not None
                                         else env.binding.action_schema['schema_id']),
                          'schema_version': ('physical-reset-action-spec-v1' if spec is not None
                                             else env.binding.action_schema['schema_version']),
                          'controller_kind': kind, 'components': components},
        'observation_schema': {'leaf_specs': leaf_specs},
        'reference_profile': {
            'schema_version': 'physical-control-recording-profile-v1',
            'physical_action_spec_v1': spec,
            'task_artifact_identity_hash': artifact.identity_hash,
            'scene_identity_hash': execution.scene.identity_hash,
            'source_closure_digest': source.source_closure_digest,
            'reset_plan_identity_hash': reset_plan.identity_hash,
            'reset_sample_id': reset_plan.reset_sample.sample_id,
            'provider': env.provider, 'backend': env.backend,
            'solution_identity': env.value.get('solution_identity'),
            'physical_binding_sha256': execution.compiled.binding.identity_hash,
            'feedback': 'independent force measurement unavailable',
        },
    }
    return {
        'env_metadata': env_metadata,
        'universal_action_schema': {'version': 'physical-reset-action-v1',
                                    'components': components, 'dimension': len(components)},
        'resolved_config': {'provider': env.provider, 'backend': env.backend,
                            'horizon': env.horizon, 'physical_action_spec_v1': spec},
        'candidate_identity': {'task_artifact_identity_hash': artifact.identity_hash,
                               'source_closure_digest': source.source_closure_digest,
                               'reset_plan_identity_hash': reset_plan.identity_hash},
        'execution_configuration_v1': env.get_execution_receipt(),
    }


def record_physical_transition(env, action, batch, resolved, ack, *, terminated, truncated):
    """Persist requested input, submitted typed batch and native ACK without inventing measurement."""
    from ..controllers.canonical.contracts import ControlGroupActionV1, StructuredActionRequestV1, digest
    from ..trajectory.canonical.episode import StructuredControlTransitionV1
    from dataclasses import asdict
    selection = getattr(env, '_physical_reset_selection', None)
    execution = env._physical_execution()
    spec = env.physical_action_spec() if selection is not None else None
    raw_action = action if spec is not None else action['torque']
    values = tuple(float(x) for x in np.asarray(raw_action, dtype=np.float64))
    entity = batch.joint_efforts[0].entity_id
    if spec is not None:
        if len(values) != 8:
            raise ValueError('physical recording requires the declared eight-value action')
        components = (('x', 'y', 'z', 'qw', 'qx', 'qy', 'qz', 'gripper') if spec['kind'] == 'r3-pose'
                      else tuple(f'joint{i}' for i in range(1, 8)) + ('opening',))
        schema_id = 'physical-' + spec['spec_id']
        projections = (('arm', components[:7], values[:7]), ('gripper', components[7:], values[7:]))
    else:
        components = tuple(env.binding.action_schema['components'])
        if len(values) != len(components):
            raise ValueError('physical action does not match the declared component count')
        available = tuple(group for group in execution.scene.control_groups if group.entity_id == entity)
        if len(available) != 1:
            raise ValueError('physical recording requires one declared group for the action')
        schema_id = env.binding.action_schema['schema_id']
        projections = ((available[0].group_id, components, values),)
    groups = tuple(ControlGroupActionV1('control-group-action-v1', entity, group, schema_id, part)
                   for group, _names, part in projections)
    request = StructuredActionRequestV1('structured-action-request-v1', batch.context.boundary.scene_identity_hash,
                                        execution.compiled.binding.identity_hash, groups)
    payload = batch.to_mapping()
    target_hash = digest(payload)
    if target_hash != batch.identity_hash or ack.batch_sha256 != target_hash:
        raise ValueError('physical record batch and acknowledgement identities differ')
    control = StructuredControlTransitionV1('structured-control-transition-v1', request, ({
        'writer_id': execution.controllers[0].writer_id,
        'action_schema_id': schema_id, 'components': components,
        'groups': tuple({'entity_id': entity, 'group_id': group, 'action_components': names}
                        for group, names, _part in projections),
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
    info = physical_boundary_info(env, env.info)
    env.recorder.append_transition(np.asarray(values, dtype=np.float32), np.asarray(values, dtype=np.float32),
        env.obs, float(env.evaluation.reward), bool(env.evaluation.success), bool(terminated), bool(truncated),
        info, structured_control=control)


def physical_boundary_info(env, info):
    """Attach the real published state clock and, when present, task camera receipt."""
    view = env.typed_state.view
    boundary = view.boundary.to_mapping()
    context = {'schema_version': 'physical-record-boundary-v1',
               'state_boundary_identity': boundary,
               'state_sample_clock': view.sample_clock.to_mapping()}
    camera = info.get('task_rgb_v1')
    if camera is not None:
        from ..render.camera.source import CameraCaptureIdentityV1
        identity = CameraCaptureIdentityV1.from_mapping(camera['capture_identity'])
        if (identity.state_boundary != view.boundary or identity.sample_clock != view.sample_clock
                or identity.identity_hash != camera['capture_identity_sha256']):
            raise ValueError('task camera does not belong to the recorded state boundary and clock')
        context['task_rgb_v1'] = camera
    return {**info, 'boundary_context_v1': context}
