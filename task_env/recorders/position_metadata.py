"""Project selected Position reset and transitions into the existing recorder schema."""

import hashlib
from dataclasses import asdict

import numpy as np


def position_episode_end_payload(*, state, boundary, source_closure_digest,
                                 controller=None,
                                 position_profiles=None, payload=None):
    """Project the last published Position boundary and control facts for recording."""
    details = {
        'control_step': int(state.control_step),
        'simulation_time_s': float(state.simulation_time),
        'state_boundary_id': boundary.boundary_id,
        'source_closure_digest': source_closure_digest,
    }
    details.update({'controller_identity': controller.identity,
                    'profile_id': controller.profile_id})
    if position_profiles is not None:
        details['position_writers'] = tuple({
            'entity_id': profile.entity_id,
            'writer_id': profile.writer_id,
            'controller_identity': profile.identity,
        } for profile in position_profiles)
    details.update(dict(payload or {}))
    return details


def position_control_binding_provenance(binding, selector):
    """Snapshot the materialized Position binding and selector file for this recording."""
    from .reference_provenance import callable_source_snapshot
    return {
        'binding': asdict(binding),
        'selector_source_sha256': callable_source_snapshot(selector),
    }


def position_record_metadata(self):
    from dataclasses import asdict


    profile = self.position_profiles[0]
    action_schema = profile.controller_binding().action_schema
    action_contract = asdict(action_schema)
    position_profiles = self.position_profiles
    if self.dual_entity_position:
        action_components = tuple(
            f'{writer_profile.entity_id}/{component}'
            for writer_profile in position_profiles
            for component in writer_profile.controller_binding().action_schema.components
        )
        action_contract.update({
            'schema_id': 'panda-position-dual-entity-action-v1',
            'schema_version': 'structured-action-schema-v1',
            'components': action_components,
        })
    observation_leaf_specs = [
        {'path': 'state.ee_pose', 'semantic': 'hand_origin_tcp_pose'},
        {'path': 'state.joint_position', 'semantic': 'required_panda_joint_position'},
        {'path': 'state.hand_pose', 'semantic': 'provider_measured_panda_hand_pose'},
        {'path': 'state.boundary_identity_sha256', 'semantic': 'state_boundary_identity_sha256'},
    ]
    if self.value.get('session_admission_input') is not None:
        # F06's position profile binds its historical hand_pose field to the
        # source ee frame; it is not the physical hand-origin frame.
        for field in observation_leaf_specs:
            if field['path'] in ('state.ee_pose', 'state.hand_pose'):
                field.update(semantic='provider_measured_pickcube_ee_pose', frame='panda-v1/ee')
    if self.dual_entity_position:
        for writer_profile in position_profiles:
            observation_leaf_specs.extend((
                {'path': f'state.entities.{writer_profile.entity_id}.joint_position',
                 'semantic': 'entity_qualified_required_joint_position'},
                {'path': f'state.entities.{writer_profile.entity_id}.hand_pose',
                 'semantic': 'entity_qualified_provider_measured_hand_pose'},
            ))
    observation_leaf_specs.extend(
        {'path': f'privileged_state.{key}_body_pose', 'semantic': 'scene_body_pose'}
        for _, key in self.binding.object_poses
    )
    env_metadata = {
        'env_name': 'SelectedReferenceEnv.PositionServoV1',
        'task_name': self.artifact.task_id,
        'task_version': self.artifact.artifact_version,
        'scene_uid': self.position_scene.scene_id,
        'agent_uids': tuple(item.entity_id for item in position_profiles),
        'physics_dt': self.artifact.timebase.physics_dt,
        'control_substeps': self.artifact.timebase.control_substeps,
        'control_frequency': 1.0 / self.artifact.timebase.control_dt,
        'action_schema': action_contract,
        'observation_schema': {'leaf_specs': observation_leaf_specs},
        'reference_profile': {
            'profile_id': profile.profile_id,
            'writer_id': profile.writer_id,
            'controller_identity': profile.identity,
            'control_binding_plan_identity_hash': self.position_plan.identity_hash,
            'task_artifact_identity_hash': self.artifact.identity_hash,
            'scene_identity_hash': self.position_scene.identity_hash,
            'reset_plan_identity_hash': self.value['reset_plan'].identity_hash,
            'reset_sample_id': self.value['reset_plan'].reset_sample.sample_id,
            'source_closure_digest': self.value['source'].source_closure_digest,
            'tcp_profile': profile.tcp_profile.to_mapping(),
            'force_feedback': 'not_consumed',
        },
    }
    f06_input = self.value.get('session_admission_input')
    if f06_input is not None:
        native_facts = self.session.build_layout_facts
        native_metadata = native_facts['native_runtime_metadata']
        bootstrap = dict(native_facts['native_public_bootstrap_receipt'])
        deployment = self.get_execution_receipt()
        env_metadata['reference_profile'].update({
            'provider': 'isaacsim', 'provider_version': native_metadata['provider_build_identity'],
            'provider_build_identity': native_metadata['provider_build_identity'],
            'backend': 'cuda', 'device': 'cuda:0',
            'determinism_mode': 'best_effort',
            'execution_identity_sha256': f06_input.execution.identity_hash,
            'source_id': self.value['source'].source_id,
            'delivery_manifest_sha256': f06_input.delivery_manifest_sha256,
            'native_public_bootstrap_receipt': bootstrap,
            'request_identity_sha256': deployment['request_identity'],
            'worker_request_identity_sha256': deployment.get('worker_request_identity'),
            'materialization_identity': self.session.provider_materialization_id,
            'native_build_layout_facts': native_facts,
            'reset_plan_evidence': self.session.reset_plan_evidence,
            'requested_reset_sample': self.value['reset_plan'].to_provider_sample().to_mapping(),
            'measured_reset_state': self.realized.measured_state.to_mapping(),
            'typed_state_h5_witness_schema_version': 'f06-public-typed-state-witness-v1',
            'solution_identity': self._active_solution_identity(),
            'tcp_semantic_frame': 'panda-v1/ee',
            'hand_pose_semantic_frame': 'panda-v1/ee',
        })
    universal_components = tuple(action_schema.components)
    if self.dual_entity_position:
        universal_components = action_components
    universal_schema = {
        'version': 'panda-position-servo-universal-action-v1',
        'dimension': len(universal_components),
        'components': universal_components,
    }
    return {
        'env_metadata': env_metadata,
        'universal_action_schema': universal_schema,
        'resolved_config': {
            'provider': self.provider, 'backend': self.backend, 'horizon': self.horizon,
            'controller_profile': profile.profile_id,
        },
        'candidate_identity': {
            'task_artifact_identity_hash': self.artifact.identity_hash,
            'source_closure_digest': self.value['source'].source_closure_digest,
            'reset_plan_identity_hash': self.value['reset_plan'].identity_hash,
        },
    }
    if self.dual_entity_position:
        env_metadata['candidate_identity']['scene_identity_hash'] = self.position_scene.identity_hash
        env_metadata['reference_profile']['writers'] = tuple({
            'entity_id': item.entity_id,
            'profile_id': item.profile_id,
            'writer_id': item.writer_id,
            'controller_identity': item.identity,
            'required_state': item.requirements.to_mapping(),
        } for item in position_profiles)
        env_metadata['resolved_config']['controller_profiles'] = tuple(
            item.profile_id for item in position_profiles
        )


def record_position_transition(self, request, canonical, target, applied, *, terminated, truncated):
    from ..trajectory.canonical.episode import StructuredControlTransitionV1

    schema = self.position_profiles[0].controller_binding().action_schema
    groups = {(group.entity_id, group.group_id): group for group in request.groups}
    entity_id = self.position_profiles[0].entity_id
    arm = groups[(entity_id, 'arm')]
    gripper = groups[(entity_id, 'gripper')]
    action_values = np.asarray((*arm.values, *gripper.values), dtype=np.float32)
    target_payload = target.target.to_mapping()
    target_hash = target.target.identity_hash
    applied_payload = applied.to_mapping()
    if 'gravity_compensation_v1' in self.info:
        applied_payload['gravity_compensation_v1'] = self.info['gravity_compensation_v1']
    if self.value.get('session_admission_input') is not None:
        evidence = self.session.native_interval_evidence
        native_ack = evidence['position_ack']
        native_advances = evidence['advances']
        advance_attempts = evidence['advance_attempts']
        if native_ack is None or len(native_advances) != self.artifact.timebase.control_substeps:
            raise ValueError('USD recording requires a complete native Position Ack and interval receipts')
        applied_payload['native_position_write_ack_v1'] = native_ack
        applied_payload['native_interval_advance_receipts_v1'] = list(native_advances)
        applied_payload['native_interval_advance_attempts'] = advance_attempts
        provenance = evidence['provenance_kind']
        if provenance == 'native_runtime':
            execution_class = 'native_runtime_accepted_physics'
        elif provenance == 'synthetic_fixture':
            execution_class = 'synthetic_fixture_no_physics'
        else:
            raise ValueError('Position recording requires explicit native-I/O execution provenance')
        applied_payload['native_io_execution_class'] = execution_class
    canonical_action = {
        **canonical.to_mapping(),
        'position_target_v1': target.to_mapping(),
        'position_target_identity_hash': target.identity_hash,
    }
    control = StructuredControlTransitionV1(
        'structured-control-transition-v1', request, ({
            'writer_id': self.position_profiles[0].writer_id,
            'action_schema_id': schema.schema_id,
            'components': tuple(schema.components),
            'groups': (
                {'entity_id': entity_id, 'group_id': 'arm',
                 'action_components': tuple(schema.components[:7])},
                {'entity_id': entity_id, 'group_id': 'gripper',
                 'action_components': (schema.components[7],)},
            ),
            'requested_action': canonical.requested.to_mapping(),
            'canonical_action': canonical_action,
            'controller_target': {
                'schema_version': target.target.schema_version,
                'payload': target_payload, 'identity_hash': target_hash,
            },
            'applied_control': {
                'schema_version': applied.schema_version,
                'payload': applied_payload, 'target_hash': applied.target_hash,
            },
        },),
    )
    control.validate()
    self.recorder.append_transition(
        action_values, action_values, self.obs, float(self.evaluation.reward),
        bool(self.evaluation.success), bool(terminated), bool(truncated), self.info,
        structured_control=control,
    )

def record_dual_position_transition(self, request, position_records, *, terminated, truncated):
    """Store both Entity writers in the existing Generic H5 v3 transition."""
    from ..trajectory.canonical.episode import StructuredControlTransitionV1

    groups = {(group.entity_id, group.group_id): group for group in request.groups}
    expected_groups = {
        (profile.entity_id, group_id)
        for profile in self.position_profiles for group_id in ('arm', 'gripper')
    }
    if set(groups) != expected_groups or len(position_records) != 2:
        raise ValueError('dual Position recording requires both groups for both admitted Entities')
    action_values = np.asarray(tuple(
        value
        for group_key in sorted(groups)
        for value in groups[group_key].values
    ), dtype=np.float32)
    records_by_writer = {target.writer_id: (canonical, target, applied)
                         for canonical, target, applied in position_records}
    writer_controls = []
    for profile in self.position_profiles:
        canonical, bound_target, applied = records_by_writer[profile.writer_id]
        schema = profile.controller_binding().action_schema
        writer_controls.append({
            'writer_id': profile.writer_id,
            'action_schema_id': schema.schema_id,
            'components': tuple(schema.components),
            'groups': (
                {'entity_id': profile.entity_id, 'group_id': 'arm',
                 'action_components': tuple(schema.components[:7])},
                {'entity_id': profile.entity_id, 'group_id': 'gripper',
                 'action_components': (schema.components[7],)},
            ),
            'requested_action': canonical.requested.to_mapping(),
            'canonical_action': {
                **canonical.to_mapping(),
                'position_target_v1': bound_target.to_mapping(),
                'position_target_identity_hash': bound_target.identity_hash,
            },
            'controller_target': {
                'schema_version': bound_target.target.schema_version,
                'payload': bound_target.target.to_mapping(),
                'identity_hash': bound_target.target.identity_hash,
            },
            'applied_control': {
                'schema_version': applied.schema_version,
                'payload': applied.to_mapping(),
                'target_hash': applied.target_hash,
            },
        })
    control = StructuredControlTransitionV1(
        'structured-control-transition-v1', request, tuple(writer_controls),
    )
    control.validate()
    self.recorder.append_transition(
        action_values, action_values, self.obs, float(self.evaluation.reward),
        bool(self.evaluation.success), bool(terminated), bool(truncated), self.info,
        structured_control=control,
    )


def position_record_reset_info(self):
    plan = self.value['reset_plan']
    boundary = self.typed_state.view.boundary
    info = {
        'seed': int(plan.reset_sample.task_seed),
        'options': {},
        'reset_sample_id': plan.reset_sample.sample_id,
        'reset_plan_identity_hash': plan.identity_hash,
        'role_binding_identity_hash': plan.role_binding.identity_hash,
        'state_boundary_identity': boundary.to_mapping(),
        'state_boundary_id': boundary.boundary_id,
        'state_sample_clock': self.typed_state.view.sample_clock.to_mapping(),
        'source_closure_digest': self.value['source'].source_closure_digest,
        **({
            # Persist the public snapshot used to produce the reset
            # observation. Generic H5 v3 consumes this only for the
            # bounded versioned typed-state witness extension.
            'canonical_state_view_v1': self.info['canonical_state_view_v1'],
        } if self.value.get('session_admission_input') is not None else {}),
    }
    return info
