"""Project selected Position reset and transitions into the existing recorder schema."""

import hashlib
from dataclasses import asdict

import numpy as np
from ..environment.reference_binding import position_input_kind


def position_episode_end_payload(*, state, boundary, source_closure_digest,
                                 controller=None,
                                 position_profiles=None, switch_fault_receipt=None,
                                 pending_switch=None, execution_fault=None,
                                 last_transition=None, runtime_step=None, payload=None):
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
    if switch_fault_receipt is not None:
        details['controller_switch_fault_receipt'] = dict(switch_fault_receipt)
    if pending_switch is not None:
        details['pending_controller_switch_application'] = pending_controller_switch_receipt(
            pending_switch, published_step=state.control_step,
            execution_fault=execution_fault, last_transition=last_transition,
            runtime_step=runtime_step,
        )
    details.update(dict(payload or {}))
    return details


def position_control_binding_provenance(binding, selector):
    """Snapshot the materialized Position binding and selector file for this recording."""
    from .reference_provenance import callable_source_snapshot
    return {
        'binding': asdict(binding),
        'selector_source_sha256': callable_source_snapshot(selector),
    }


def _switch_controller_payload(controller, *, requested=False):
    prefix = 'requested_' if requested else ''
    return {
        f'{prefix}profile_id': controller.profile_id,
        f'{prefix}writer_id': controller.writer_id,
        f'{prefix}controller_identity': controller.identity,
        'action_config': asdict(controller.config),
    }


def position_switch_event(*, switch_id, boundary, clock, transition_count, sequence,
                          current, candidate, binding_identity, source_closure):
    """Build the recorded switch event without changing runtime or recorder state."""
    from ..trajectory.canonical.episode import BoundaryEventV1

    return BoundaryEventV1(
        'boundary-event-v1', boundary.episode_id, transition_count, sequence,
        f'controller-switch-{switch_id}', 'controller_instance_switch',
        'task_env.selected_reference.position_servo_v1',
        {
            'switch_id': switch_id,
            'request': {'operation': 'replace_position_controller_instance',
                        **_switch_controller_payload(candidate, requested=True)},
            'previous_controller': _switch_controller_payload(current),
            'effective_controller': _switch_controller_payload(candidate),
            'result': {'preparation': 'validated', 'switch': 'effective',
                       'first_control_application': 'pending_next_step'},
            'effective_boundary': {**boundary.to_mapping(), 'boundary_id': boundary.boundary_id},
            'effective_clock': clock.to_mapping(),
            'binding_identity_hash': binding_identity,
            'source_closure_digest': source_closure,
        },
    )


def position_switch_fault_receipt(*, switch_id, boundary, clock, current, candidate,
                                  active_controller_identity, fault):
    """Describe a committed switch whose effective event could not be recorded."""
    return {
        'switch_id': switch_id,
        'result': 'committed_but_effective_event_record_failed',
        'request': {'operation': 'replace_position_controller_instance',
                    **_switch_controller_payload(candidate, requested=True)},
        'previous_controller': _switch_controller_payload(current),
        'effective_controller': _switch_controller_payload(candidate),
        'previous_controller_identity': current.identity,
        'active_controller_identity': active_controller_identity,
        'effective_boundary': {**boundary.to_mapping(), 'boundary_id': boundary.boundary_id},
        'effective_clock': clock.to_mapping(),
        'preparation_succeeded': True,
        'switch_effective': True,
        'effective_event_recorded': False,
        'first_control_application': 'not_attempted',
        'execution_fault': fault.to_mapping(),
    }


def pending_controller_switch_receipt(pending, *, published_step, execution_fault,
                                      last_transition, runtime_step):
    """Project a pending switch without treating an unrecorded ack as a transition."""
    receipt = dict(pending)
    receipt['status'] = (
        'not_attempted_before_episode_end'
        if execution_fault is None and int(published_step) == pending['effective_control_step']
        else 'not_confirmed_in_complete_transition'
    )
    if (isinstance(last_transition, tuple) and len(last_transition) == 3
            and getattr(last_transition[1], 'controller_identity', None)
            == pending['controller_identity']
            and getattr(last_transition[1].source_boundary, 'boundary_id', None)
            == pending['effective_boundary_id']
            and getattr(last_transition[2], 'target_hash', None)
            == last_transition[1].target.identity_hash):
        receipt.update({
            'status': 'target_ack_observed_but_transition_not_recorded',
            'target_identity_hash': last_transition[1].target.identity_hash,
            'applied_target_hash': last_transition[2].target_hash,
            'observed_runtime_boundary': int(runtime_step()),
        })
    return receipt


def position_record_metadata(self):
    from dataclasses import asdict


    versioned_position_input = self.value.get('versioned_position_input')
    versioned_input_kind = position_input_kind(self.binding, versioned_position_input)
    f04_input = versioned_position_input if versioned_input_kind == 'f04' else None
    f05_native_input = versioned_position_input if versioned_input_kind == 'f05_native' else None
    f05_dg02_input = versioned_position_input if versioned_input_kind == 'dg02_geophys' else None
    f05_dg04_input = versioned_position_input if versioned_input_kind == 'dg04_isaac_native' else None
    f05_native_route = f05_native_input is not None
    f05_dg02_route = f05_dg02_input is not None
    f05_dg04_route = f05_dg04_input is not None
    f05_native_core_route = f05_native_route or f05_dg02_route or f05_dg04_route
    f05_route = f05_native_core_route
    f05_host_model_route = f05_route and not f05_dg04_route
    if f04_input is not None or f05_route:
        f04_route = f04_input is not None
        versioned_input = (
            f05_dg04_input if f05_dg04_route else
            f05_dg02_input if f05_dg02_route else
            f05_native_input if f05_native_route else f04_input
        )
        source = self.value['source']
        source_scene = source.scene_source
        loaded = source_scene.loaded_delivery
        delivery = loaded.delivery
        representation = source_scene.representation
        drive_receipt = getattr(self.session, '_drive_receipt', None)
        native_metadata = self.session._native_io_metadata
        reset_receipt = self.session._reset_write_receipt
        if reset_receipt is None:
            raise RuntimeError('versioned USD recording requires the successful Core reset write receipt')
        f04_native = bool(f04_route and drive_receipt is not None
                          and drive_receipt.provenance_kind == 'native_runtime')
        f05_native = bool(f05_native_core_route and drive_receipt is not None
                          and drive_receipt.provenance_kind == 'native_runtime')
        expected_provenance = 'native_runtime' if f04_native or f05_native else 'synthetic_fixture'
        if (drive_receipt is None or drive_receipt.provenance_kind != expected_provenance):
            raise RuntimeError('versioned USD recording receipt provenance differs from its execution route')
        if f04_native:
            if not (source.scene_source.source_verified or source.scene_source.locally_validated):
                raise RuntimeError('F04 recording requires a loader-verified upstream or fixed local production delivery')
            bootstrap = self.session._native_io.bootstrap_receipt()
        elif f05_native:
            bootstrap = self.session._native_io.bootstrap_receipt()
        else:
            bootstrap = None
        action_schema = self.controller.controller_binding().action_schema
        profile = {
            'schema_version': (
                'f04-isaac-core-position-recording-profile-v1' if f04_native else
                'f05-dg04-isaac-native-core-position-profile-v1' if f05_dg04_route else
                'f05-dg02-geophys-usd-core-position-native-profile-v1' if f05_dg02_route else
                'f05-geophys-core-position-native-profile-v1' if f05_native else
                'f04-core-position-synthetic-io-s1-profile-v1'
            ),
            'profile_id': (
                'f04-isaac-panda-position-native-v1' if f04_native else
                'f05-dg04-isaac-native-mimic-v1' if f05_dg04_route else
                'geophys-usd-position-f05-dg02-core-v1' if f05_dg02_route else
                'geophys-usd-position-f05-native-v1' if f05_native else
                'f04-local-source-synthetic-io-s1-v1'
            ),
            'provenance_kind': 'native_runtime' if f04_native or f05_native else 'synthetic_fixture',
            'runtime_admitted': bool(f04_native or f05_native),
            'source_verified': bool(source_scene.source_verified),
            'source_validation_provenance_kind': delivery.provenance_kind,
            'task_source_identity_sha256': versioned_input.task_source.identity_hash,
            'task_artifact_identity_sha256': self.artifact.identity_hash,
            'scene_identity_sha256': self.position_scene.identity_hash,
            'source_id': source.source_id,
            'source_closure_sha256': source.source_closure_digest,
            'usd_delivery': {
                'asset_identity_sha256': delivery.asset_identity_hash,
                'delivery_sha256': loaded.delivery_sha256,
                'closure_sha256': loaded.closure_sha256,
                'provenance_kind': delivery.provenance_kind,
                'source_revision': delivery.source_revision,
                'entry_file': delivery.entry_file,
                'entry_prim': delivery.entry_prim,
                'variant_selections': dict(delivery.variant_selections),
                'validation_report_path': delivery.validation_report_path,
                'validation_report_sha256': delivery.validation_report_sha256,
                'validation_report_payload_sha256': hashlib.sha256(loaded.report_bytes).hexdigest(),
                'validation_report_id': loaded.report.report_id,
                'validation_report_passed': loaded.report.passed,
                'validation_report_provenance_kind': loaded.report.provenance_kind,
                'locally_validated': bool(getattr(loaded, 'locally_validated', False)),
                **({
                    'source_closure_sha256': delivery.source_closure_sha256,
                    'source_manifest_sha256': delivery.source_manifest_sha256,
                    'source_variant_selections': dict(delivery.source_variant_selections),
                    'source_variant_selection_sha256': delivery.source_variant_selection_sha256,
                    'recipe_sha256': delivery.recipe_sha256,
                    'checker_sha256': delivery.checker_sha256,
                } if getattr(loaded, 'locally_validated', False) else {}),
            },
            'representation': {
                'identity_sha256': representation.identity_hash,
                'provider': representation.provider,
                'provider_build_identity': representation.provider_build_identity,
                'requested_target_build_identity': representation.provider_build_identity,
                **({'actual_execution_build_identity': native_metadata.provider_build_identity}
                   if f05_native else {}),
                'decision': representation.decision,
                'runtime_admitted': representation.runtime_admitted,
                'source_verified': representation.source_verified,
            },
            'execution_spec_v1': self.execution.to_mapping(),
            'execution_identity_sha256': self.execution.identity_hash,
            'device': self.execution.physics_device,
            'backend': self.execution.physics_backend,
            'provider_build_identity': native_metadata.provider_build_identity,
            **({
                'requested_target_build_identity': versioned_input.host_model_producer_identity.requested_target_build_identity,
                'actual_provider_build_identity': versioned_input.host_model_producer_identity.actual_provider_build_identity,
                'host_model_producer_identity_sha256': versioned_input.host_model_producer_identity.identity_sha256,
                'host_model_producer_identity': versioned_input.host_model_producer_identity.to_mapping(),
            } if f05_host_model_route else {}),
            'timebase': {
                'physics_dt_s': self.artifact.timebase.physics_dt,
                'control_substeps': self.artifact.timebase.control_substeps,
                'control_dt_s': self.artifact.timebase.control_dt,
                'clock_domain': 'evaluation_boundary',
            },
            'reset_plan_identity_sha256': self.value['reset_plan'].identity_hash,
            'reset_sample_id': self.value['reset_plan'].reset_sample.sample_id,
            'reset_write_receipt': reset_receipt.to_mapping(),
            'controller_identity_sha256': self.controller.identity,
            'control_binding_plan_identity_sha256': self.position_plan.identity_hash,
            'native_position_drive_receipt_identity_sha256': drive_receipt.identity_sha256,
            'native_position_drive_receipt': (
                drive_receipt.to_mapping() if f05_dg04_route else asdict(drive_receipt)
            ),
            **({'public_model_identity_sha256': drive_receipt.public_model_identity_sha256}
               if f05_host_model_route else {}),
            'native_runtime_io_metadata': native_metadata.to_mapping(),
            **({'native_public_bootstrap_receipt': bootstrap} if f04_native or f05_native else {}),
            'native_source_mappings': {
                'joints': dict(source.joints), 'bodies': dict(source.bodies),
                'frames': dict(source.frames), 'free_joints': dict(source.free_joints),
                'joint_targets': dict(source.joint_targets),
            },
            ('source_calibrated_kinematics_source_sha256' if f04_route or f05_route
             else 'static_kinematics_source_sha256'): versioned_input.kinematics_source_sha256,
            'reset_sample_clock': self.typed_state.view.sample_clock.to_mapping(),
            **({'typed_state_h5_witness_schema_version': 'f05-public-typed-state-witness-v1'}
               if f05_route else {}),
            'recording_scope': (
                'F04 exact Isaac 6.2.0.0 cuda:0 GPU PhysX Position execution'
                if f04_native else
                'F05 DG04 source-bound Menagerie USD / Isaac 6.2.0.0 GPU PhysX native-mimic Core Position diagnostic'
                if f05_dg04_route and f05_native else
                'F05 DG04 synthetic lowest NativeRuntimeIO Core Position S1; no native physics admission'
                if f05_dg04_route else
                'F05 DG02 source-preserving Menagerie USD / GeoPhys CPU Core Position cell'
                if f05_dg02_route else
                'F05 frozen Menagerie USD / GeoPhys CPU native Core Position cell'
                if f05_native else
                'F05 public GeoPhys host-model synthetic S1; no provider solver or physics admission'
                if f05_route else 'Core synthetic S1 conformance; no provider physics or native admission'
            ),
        }
        action_components = tuple(action_schema.components)
        return {
            'env_metadata': {
                'env_name': (
                    'SelectedReferenceEnv.F04IsaacPandaPosition' if f04_native else
                    'SelectedReferenceEnv.F05Dg04IsaacNativePosition' if f05_dg04_route else
                    'SelectedReferenceEnv.F05Dg02GeoPhysUsdCorePosition' if f05_dg02_route else
                    'SelectedReferenceEnv.F05MenagerieGeoPhysCpuNativePosition' if f05_native else
                    'SelectedReferenceEnv.F04LocalSourceSyntheticIOS1' if f04_route else
                    'SelectedReferenceEnv.F05GeoPhysUsdSyntheticIOS1' if f05_route else
                    'SelectedReferenceEnv.VersionedPositionCandidate'
                ),
                'task_name': self.artifact.task_id,
                'task_version': self.artifact.artifact_version,
                'scene_uid': self.position_scene.scene_id,
                'agent_uids': ('panda-main',),
                'physics_dt': self.artifact.timebase.physics_dt,
                'control_substeps': self.artifact.timebase.control_substeps,
                'control_frequency': 1.0 / self.artifact.timebase.control_dt,
                'action_schema': asdict(action_schema),
                'observation_schema': {'leaf_specs': (
                    {'path': 'state.ee_pose', 'semantic': 'hand_origin_tcp_pose_world'},
                    {'path': 'state.joint_position', 'semantic': 'named_arm_then_finger_joint_positions'},
                    {'path': 'state.hand_pose', 'semantic': 'measured_hand_frame_pose_world'},
                    {'path': 'state.boundary_identity_sha256', 'semantic': 'state_boundary_identity_sha256'},
                    {'path': 'privileged_state.target_body_pose', 'semantic': 'floating_target_body_pose_world'},
                )},
                'reference_profile': profile,
            },
            'universal_action_schema': {
                'version': ('f04-isaac-core-position-action-v1'
                            if f04_route else 'f05-dg02-geophys-usd-core-position-action-v1'
                            if f05_dg02_route else 'f05-dg04-isaac-native-mimic-position-action-v1'
                            if f05_dg04_route else 'f05-geophys-native-position-action-v1'
                            if f05_native else 'f05-geophys-usd-position-synthetic-s1-action-v1'),
                'dimension': len(action_components), 'components': action_components,
            },
            'resolved_config': {
                'provider': self.provider, 'backend': self.backend,
                'device': self.execution.physics_device, 'horizon': self.horizon,
                'controller_profile': self.controller.profile_id,
                'execution_identity_sha256': self.execution.identity_hash,
            },
            'candidate_identity': {
                'task_artifact_identity_hash': self.artifact.identity_hash,
                'task_source_identity_sha256': versioned_input.task_source.identity_hash,
                'scene_identity_hash': self.position_scene.identity_hash,
                'source_id': source.source_id,
                'source_closure_digest': source.source_closure_digest,
                'reset_plan_identity_hash': self.value['reset_plan'].identity_hash,
                'execution_identity_sha256': self.execution.identity_hash,
                'controller_identity_sha256': self.controller.identity,
                'native_position_drive_receipt_identity_sha256': drive_receipt.identity_sha256,
                **({'host_model_producer_identity_sha256': versioned_input.host_model_producer_identity.identity_sha256}
                   if f05_host_model_route else {}),
            },
        }

    profile = self.controller
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
    if self.value.get('f06_pickcube_isaac_input') is not None:
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
    if self.camera_observation_config is not None:
        from ..observations.state import camera_observation_field_specs

        observation_leaf_specs.extend({
            'path': field.name,
            'shape': field.shape,
            'dtype': field.dtype,
            'semantic': field.semantic,
            'unit': field.unit,
            'frame': field.frame,
            'time_reference': field.time_reference,
        } for field in camera_observation_field_specs(self.camera_observation_config))
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
    f06_input = self.value.get('f06_pickcube_isaac_input')
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
            **({'camera_observation': self.camera_observation_config.to_mapping()}
               if self.camera_observation_config is not None else {}),
        },
        'candidate_identity': {
            'task_artifact_identity_hash': self.artifact.identity_hash,
            'source_closure_digest': self.value['source'].source_closure_digest,
            'reset_plan_identity_hash': self.value['reset_plan'].identity_hash,
        },
        **({
            'camera_observation_contract_v1': self.camera_observation_config.to_mapping(),
        } if self.camera_observation_config is not None else {}),
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

    schema = self.controller.controller_binding().action_schema
    groups = {(group.entity_id, group.group_id): group for group in request.groups}
    entity_id = self.controller.entity_id
    arm = groups[(entity_id, 'arm')]
    gripper = groups[(entity_id, 'gripper')]
    action_values = np.asarray((*arm.values, *gripper.values), dtype=np.float32)
    target_payload = target.target.to_mapping()
    target_hash = target.target.identity_hash
    applied_payload = applied.to_mapping()
    if 'gravity_compensation_v1' in self.info:
        applied_payload['gravity_compensation_v1'] = self.info['gravity_compensation_v1']
    versioned_position_input = self.value.get('versioned_position_input')
    versioned_input_kind = position_input_kind(self.binding, versioned_position_input)
    f04_input = versioned_position_input if versioned_input_kind == 'f04' else None
    f05_dg02_input = versioned_position_input if versioned_input_kind == 'dg02_geophys' else None
    if (f04_input is not None or versioned_input_kind == 'f05_native'
            or f05_dg02_input is not None
            or versioned_input_kind == 'dg04_isaac_native'
            or self.value.get('f06_pickcube_isaac_input') is not None):
        evidence = self.session.native_interval_evidence
        native_ack = evidence['position_ack']
        native_advances = evidence['advances']
        advance_attempts = evidence['advance_attempts']
        if native_ack is None or len(native_advances) != self.artifact.timebase.control_substeps:
            raise ValueError('versioned USD recording requires a complete native Position Ack and interval receipts')
        applied_payload['native_position_write_ack_v1'] = native_ack
        applied_payload['native_interval_advance_receipts_v1'] = list(native_advances)
        applied_payload['native_interval_advance_attempts'] = advance_attempts
        if (f04_input is not None or versioned_input_kind == 'f05_native'
                or f05_dg02_input is not None
                or versioned_input_kind == 'dg04_isaac_native'
                or self.value.get('f06_pickcube_isaac_input') is not None):
            provenance = evidence['provenance_kind']
            if provenance == 'native_runtime':
                execution_class = 'native_runtime_accepted_physics'
            elif provenance == 'synthetic_fixture':
                execution_class = 'synthetic_fixture_no_physics'
            else:
                raise ValueError(
                    'F04 Position recording requires an explicit native-I/O execution provenance'
                )
        else:
            execution_class = 'synthetic_fixture_no_physics'
        applied_payload['native_io_execution_class'] = execution_class
    canonical_action = {
        **canonical.to_mapping(),
        'position_target_v1': target.to_mapping(),
        'position_target_identity_hash': target.identity_hash,
    }
    pending_switch = self._pending_position_switch
    if pending_switch is not None:
        if (target.controller_identity != pending_switch['controller_identity']
                or target.source_boundary.boundary_id != pending_switch['effective_boundary_id']):
            raise ValueError('first post-switch target does not match the committed Controller/boundary')
        canonical_action['controller_switch_application'] = {
            'switch_id': pending_switch['switch_id'],
            'status': 'target_and_applied_ack_recorded',
            'controller_identity': target.controller_identity,
            'effective_boundary_id': pending_switch['effective_boundary_id'],
            'target_identity_hash': target.target.identity_hash,
            'applied_target_hash': applied.target_hash,
        }
    control = StructuredControlTransitionV1(
        'structured-control-transition-v1', request, ({
            'writer_id': self.controller.writer_id,
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
    if pending_switch is not None:
        self._pending_position_switch = None

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
        } if position_input_kind(
            self.binding, self.value.get('versioned_position_input'),
        ) in ('f05', 'f05_native', 'dg02_geophys', 'dg04_isaac_native')
          or self.value.get('f06_pickcube_isaac_input') is not None else {}),
        **({
            'camera_observation_v1': self.info['camera_observation_v1'],
        } if self.camera_observation_config is not None else {}),
    }
    return info
