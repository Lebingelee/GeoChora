"""Selected open-loop physical sequence using existing batch admission."""
from dataclasses import asdict

from ...artifacts.state import CanonicalStatePublicationV1, CanonicalStatePublicationV2
from ...controllers.canonical.model import AffineJointBiasModelV1
from ...controllers.canonical.physical_controller import LinearEffortControllerV1
from ...controllers.canonical.contracts import digest
from ...controllers.canonical.physical_commands import PhysicalControlReceiptV1
from ...environment.types import StageUnavailableError
from .control_submission import submit_control_command
from .physical_control import (PhysicalSequenceAcknowledgementV1, ResolvedPhysicalSequenceV1,
                               prepare_physical_command_batch)


def describe_physical_sequence_capability(env, profile):
    """Describe the exact live capability without computing or advancing physics."""
    if (env.provider, env.backend) != ('mujoco', 'cpu'):
        raise StageUnavailableError('physical sequences require the MuJoCo CPU port')
    if (getattr(env.binding, 'physical_direct_effort_feedback', False)
            or (getattr(env.binding, 'physical_observation_binding', None) is None
                and getattr(env.binding, 'physical_sequence_v2_observation', False) is not True)
            or not getattr(env.binding, 'external_actions', False)
            or getattr(env, '_physical_reset_selection', None) is not None
            or getattr(env, '_episode_mode', None) in {'expert', 'external_solution'}):
        raise StageUnavailableError('physical sequences require a bound observation without direct feedback')
    if (getattr(env, '_task_rgb_config', None) is not None
            or getattr(env, '_legacy_camera_observations', False)
            or getattr(env, '_legacy_observer_requested', False)
            or (env.recorder is not None and not getattr(
                env.recorder, 'frozen', getattr(env.recorder, '_frozen', False)))):
        raise StageUnavailableError('physical sequences do not admit RGB/observer or active Recorder')
    port = getattr(env.session, '_physical_port', None)
    if (port is None or getattr(port, 'execution', None) is not profile
            or not callable(getattr(env.session, 'apply_physical_command_sequence', None))):
        raise StageUnavailableError('RuntimeSession has no bound physical sequence port')
    if (getattr(env.session, 'physical_control_generation', None) != profile.generation
            or getattr(env.session, '_physical_controller_versions', None) != profile.controller_versions()):
        raise ValueError('physical Controller versions differ from materialization')
    if any(type(controller) is not LinearEffortControllerV1
           or type(controller.model) is not AffineJointBiasModelV1
           or 'compute' in vars(controller) for controller in profile.controllers):
        raise StageUnavailableError('physical sequence requires the admitted pure effort/model Controllers')
    for controller in profile.controllers:
        controller.profile.validate()
        controller.model.validate()
        if (controller.model.requirement != controller.profile.model_requirement
                or controller.identity != digest({'profile': controller.profile.identity_hash,
                    'binding': controller.binding.identity_hash, 'model': controller.model.identity_hash})):
            raise ValueError('physical sequence Controller profile or model differs from its identity')
    channels = {f'{item.entity_id}/{item.joint_id}': item for item in profile.compiled.binding.channels}
    return {
        'schema_version': 'physical-action-sequence-spec-v1',
        'boundary': env.session.state_boundary_identity().to_mapping(),
        'physics_dt_s': env.artifact.timebase.physics_dt,
        'control_substeps': env.artifact.timebase.control_substeps,
        'controllers': tuple({'identity': controller.identity, 'writer_id': controller.writer_id,
                              'generation': getattr(controller, 'generation', None),
                              'action_shape': controller.action_shape,
                              'action_names': controller.profile.action_names,
                              'action_to_effort': controller.profile.action_to_effort,
                              'model_identity': controller.model.identity_hash,
                              'outputs': tuple({'channel': key, 'unit': channels[key].unit,
                                                'range': channels[key].effort_range}
                                               for key in controller.profile.channel_keys)}
                             for controller in profile.controllers),
    }


def prepare_selected_physical_sequence(env, action, *, profile, view, context, assessment,
                                       proposal, observer_solution, clock_tolerance):
    """Precompute all admitted slices before a single session write and advance."""
    describe_physical_sequence_capability(env, profile)
    if (proposal is not None or observer_solution is not None
            or getattr(env, '_task_rgb_config', None) is not None):
        raise StageUnavailableError('physical sequences require a bound observation and do not admit Solution, RGB or direct feedback')
    if env.recorder is not None and not getattr(env.recorder, 'frozen', getattr(env.recorder, '_frozen', False)):
        raise StageUnavailableError('physical sequences are not represented by the active Recorder')
    write = getattr(env.session, 'apply_physical_command_sequence', None)
    if not callable(write):
        raise StageUnavailableError('RuntimeSession has no physical sequence port')
    if getattr(env.session, '_prepared_physical_sequence', None) is not None:
        env._physical_controller_preparation_started = True
        raise RuntimeError('a prepared physical sequence is already pending; reset is required')
    count = env.artifact.timebase.control_substeps
    identities = tuple(controller.identity for controller in profile.controllers)
    action.validate(substeps=count, controller_identities=identities)
    get_receipt = getattr(env.session, 'physical_joint_build_receipt', None)
    if not callable(get_receipt):
        raise StageUnavailableError('physical sequence requires a native joint mapping receipt')
    joint_receipt = get_receipt(profile.compiled.binding)
    if getattr(joint_receipt, 'provenance', None) != 'native_build':
        raise ValueError('synthetic mapping cannot authorize a physical sequence')

    # Each Controller may change internal state while computing, even though
    # this bounded capability currently admits only known pure implementations.
    # Any later failure is therefore fault-latched by the common lifecycle.
    env._physical_controller_preparation_started = True
    slices = []
    submitted = []
    for item in action.slices:
        batch = profile.controller_batch(dict(item.actions), view, context)
        if batch.body_wrenches or batch.extensions:
            raise ValueError('physical sequence admits joint effort batches only')
        submitted.append(PhysicalControlReceiptV1('physical-control-receipt-v1', context,
            batch.identity_hash, 'submitted', tuple(value.contribution.contribution_id
                for value in batch.joint_efforts), 'core-selected', 'per-channel'))
        resolved = prepare_physical_command_batch(profile.compiled, batch,
            expected_context=context, assessment=assessment, state=view,
            joint_build_receipt=joint_receipt)
        slices.append((item.start_substep, item.end_substep, resolved))
    sequence = ResolvedPhysicalSequenceV1(action, tuple(slices))
    env.session._prepared_physical_sequence = sequence
    before = env.state
    attempted = False
    completed = False
    ack = None

    def apply_control():
        nonlocal attempted, ack
        attempted = True
        writers = tuple(sorted({item.contribution.owner_id for _, _, resolved in slices
                                for item in resolved.input_batch.joint_efforts}))
        resources = tuple(sorted({f'{item.entity_id}/{item.joint_id}' for _, _, resolved in slices
                                  for item in resolved.joints}))
        units = tuple(sorted({item.unit for _, _, resolved in slices for item in resolved.joints}))
        progress = {'attempted_writer_ids': [], 'completed_writer_ids': []}
        expected_hashes = tuple(item.input_batch.identity_hash for _, _, item in slices)
        def stage_sequence():
            progress['attempted_writer_ids'].extend(writers)
            result = write(sequence)
            if (type(result) is not PhysicalSequenceAcknowledgementV1
                    or result.sequence_sha256 != sequence.identity_hash
                    or result.batch_sha256s != expected_hashes
                    or result.producer_id != 'mujoco-qfrc-applied'):
                raise ValueError('physical sequence returned an invalid native acknowledgement')
            progress['completed_writer_ids'].extend(writers)
            return result
        ack = submit_control_command(env.session, sequence, command_kind='physical-effort-sequence',
            command_sha256=sequence.identity_hash, source_id=context.source_id,
            source_closure_sha256=context.source_closure_sha256, artifact_sha256=context.artifact_sha256,
            boundary=context.boundary, sample_clock=context.clock, controller_generation=profile.generation,
            controller_identities=identities, writer_ids=writers, resource_ids=resources, units=units,
            lowering=f'{type(env.session).__module__}.{type(env.session).__qualname__}.apply_physical_command_sequence',
            lower=stage_sequence, submission_progress=progress)
        return ack

    def advance(_ack):
        nonlocal completed
        env.state = env.session.step()
        completed = True
        publication = env.session.snapshot_v2(scene=profile.scene, joint_bindings=profile.joint_bindings,
            frame_bindings=profile.frame_bindings, requirements=profile.requirements)
        if (type(publication) is not CanonicalStatePublicationV2 or not publication.lifetime.may_be_retained
                or publication.view.boundary != env.session.state_boundary_identity()
                or publication.view.boundary.control_step != env.state.control_step
                or abs(publication.view.sample_clock.simulation_time_s - float(env.state.simulation_time)) > clock_tolerance):
            raise ValueError('physical sequence post-step state is stale or foreign')
        publication.view.validate_against_scene(profile.scene)
        publication.view.validate_requirements(profile.requirements)
        env.typed_state = publication
        observation_binding = getattr(env.binding, 'physical_observation_binding', None)
        if observation_binding is not None:
            scene, joints, frames, requirements = observation_binding(env)
            projected = env.session.snapshot_v1(scene=scene, joint_bindings=joints,
                frame_bindings=frames, requirements=requirements)
            if (type(projected) is not CanonicalStatePublicationV1 or not projected.lifetime.may_be_retained
                    or projected.view.boundary != env.session.state_boundary_identity()
                    or projected.view.boundary.control_step != env.state.control_step
                    or abs(projected.view.sample_clock.simulation_time_s - float(env.state.simulation_time)) > clock_tolerance):
                raise ValueError('physical sequence observation state is stale or foreign')
            projected.view.validate_against_scene(scene)
            projected.view.validate_requirements(requirements)
            env.typed_state = projected

    def evaluate(_state):
        env.obs, env.info, env.evaluation = env.observation(env.state)
        env.info = dict(env.info)
        env.info['physical_control_sequence_v1'] = {
            'sequence_sha256': sequence.identity_hash,
            'slices': [{'start_substep': start, 'end_substep': end,
                        'submitted_batch': item.input_batch.to_mapping(),
                        'submitted': receipt.to_mapping(), 'accepted': item.accepted_receipt.to_mapping()}
                       for (start, end, item), receipt in zip(slices, submitted, strict=True)],
            'native_write_ack': asdict(ack),
        }
        return env.evaluation

    def publish(_control, _state, _evaluation, _observation):
        terminated, truncated = env._episode_execution_state().step_outcome(
            task_terminated=bool(env.evaluation.failure or
                (getattr(env.binding, 'physical_terminate_on_success', False) and env.evaluation.success)),
            task_truncated=False, control_step=env.state.control_step, horizon=env.horizon,
            ignore_done=getattr(env.binding, 'physical_ignore_done', False))
        env._episode_mode = 'external'
        env._episode_execution_state().finish_step(terminated=terminated, truncated=truncated)
        if env.value.get('physical_execution') is not None:
            env._physical_published_state = env.state
            env._physical_published_typed_state = env.typed_state
            env._physical_published_evaluation = env.evaluation
        if getattr(env.binding, 'physical_observation_binding', None) is not None:
            env._last_position_terminated, env._last_position_truncated = terminated, truncated
            env._publish_position_boundary(env.state, env.typed_state, env.evaluation)
        return env.obs, float(env.evaluation.reward), terminated, truncated, env.info

    def on_failure(phase, error):
        if getattr(env.session, '_prepared_physical_sequence', None) is sequence:
            env.session._prepared_physical_sequence = None
        abort = getattr(env.session, 'abort_physical_control', None)
        if attempted and callable(abort):
            try:
                abort()
            except BaseException as cleanup_error:
                error.add_note(f'physical sequence cleanup also failed: {cleanup_error!r}')
        after_state = env.state if completed else None
        readback_error = None
        if attempted and not completed:
            try:
                after_state = env.session.snapshot()
                env.state = after_state
            except BaseException as snapshot_error:
                readback_error = f'{type(snapshot_error).__name__}: {snapshot_error}'
        env._latch_fault(phase, error, before_state=before, after_state=after_state,
            interval_attempted=attempted, interval_completed=completed,
            native_substeps_expected=env.artifact.timebase.control_substeps,
            readback_error=readback_error, transition_status='not_assessed')

    return dict(apply_control=apply_control, advance=advance, read_state=lambda: env.state,
                evaluate=evaluate, observe=lambda _state: env.obs, publish=publish, on_failure=on_failure)
