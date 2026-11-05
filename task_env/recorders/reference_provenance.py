"""Recording-time source snapshot and per-boundary coordinator receipt."""
from hashlib import sha256
import json
from pathlib import Path

from ..controllers.canonical.contracts import digest
from ..utils._paths import callable_source_path


def source_snapshot(path):
    """Identify the file bytes at the start of one recording."""
    return sha256(Path(path).read_bytes()).hexdigest()


def _callable_source_path(callback):
    try:
        return callable_source_path(callback)
    except (TypeError, ValueError) as error:
        if not callable(callback):
            raise TypeError('recorded binding source must be callable') from error
        raise ValueError('recorded binding callable has no traceable source file') from error


def callable_source_snapshots(callbacks):
    """Hash each declaring file once per recording, without a persistent path cache."""
    paths = {name: _callable_source_path(callback) for name, callback in callbacks.items()}
    snapshots = {path: source_snapshot(path) for path in set(paths.values())}
    return {name: snapshots[path] for name, path in paths.items()}


def callable_source_snapshot(callback):
    """Identify the declaring file of one callable used for a recording."""
    return callable_source_snapshots({'source': callback})['source']


def recorded_execution_configuration(*, uid, provider, backend, horizon, resolved):
    """Project public execution inputs needed for same-source replay."""
    if resolved is None:
        return {'env_id': uid, 'provider': provider, 'backend': backend, 'horizon': horizon}
    execution = {'physics_provider': resolved.physics_provider,
                 'physics_backend': resolved.environment.runtime.backend,
                 'physics_device': resolved.physics_device,
                 'render_default': resolved.render_default.to_mapping()}
    if resolved.source_delivery_manifest is not None:
        execution['source_delivery_manifest'] = resolved.source_delivery_manifest
    task = dict(resolved.task_parameters)
    if resolved.controller_profile is not None:
        task['controller_profile'] = resolved.controller_profile
    return {'env_id': uid, 'execution': execution,
            'episode': {'horizon': resolved.environment.episode.horizon}, 'task': task}


def selected_source_provenance(*, adapter_path, binding, value, artifact,
                               controller_identity, solution_identity,
                               execution_configuration):
    """Snapshot recorder provenance once, before the first recorded boundary."""
    from ..runtime.sessions import common as session_common

    config = value['resolved_configuration']
    adapter_hash = source_snapshot(adapter_path)
    binding_sources = callable_source_snapshots({
        'observation_source': binding.observation_projection,
        'observation_space_source': binding.observation_space_factory,
        'action_source': binding.prepare_action,
        'action_space_source': binding.action_space_factory,
    })
    provenance = {
        'construction': digest(config), 'adapter': adapter_hash,
        'coordinator_source': source_snapshot(__file__), **binding_sources,
        'interval_source': source_snapshot(session_common.__file__),
        'resolved_configuration_json': json.dumps(config, sort_keys=True),
        'execution_configuration_json': json.dumps(execution_configuration, sort_keys=True),
    }
    if 'source_revision' in value:
        source = value['source']
        provenance.update({
            'geochora_revision': str(value['source_revision']),
            'artifact_identity': artifact.identity_hash,
            'controller_identity': controller_identity,
            'solution_identity': solution_identity,
            'runtime_source_id': source.scene_source.source_id,
            'runtime_source_xml_sha256': sha256(source.scene_source.xml.encode()).hexdigest(),
        })
        if source.source_closure_digest is not None:
            provenance['runtime_source_closure_digest'] = source.source_closure_digest
        provenance.update({f'source_sha256:{name}': item
                           for name, item in value.get('source_sha256', {}).items()})
        receipt = getattr(source, 'execution_source_receipt', None)
        if receipt is not None:
            provenance['runtime_execution_source_receipt_json'] = json.dumps(
                receipt.to_mapping(), sort_keys=True,
            )
    return adapter_hash, provenance


def selected_recording_metadata(*, artifact, sample, realized, execution, provider,
                                source_provenance, controller_identity,
                                solution_identity, action_schema, factory,
                                configuration, execution_configuration, owners):
    """Build canonical episode metadata and its existing replay recipe."""
    from ..runtime.sessions.provenance import provider_build_identity
    from ..trajectory.canonical.contracts import EpisodeMetadata

    metadata = EpisodeMetadata(
        'canonical-trajectory-metadata-v0', artifact.identity_hash,
        sample, realized, execution, {'build': str(provider_build_identity(provider))},
        source_provenance, artifact.timebase, controller_identity, solution_identity,
        digest({'readiness': solution_identity}),
        digest({'action_schema': dict(action_schema)}), sample.task_seed, 'regression',
    )
    recipe = {'factory': factory, 'artifact': artifact.to_mapping(),
              'resolved_configuration': configuration,
              'execution_configuration': execution_configuration,
              'stages': ['reference'], 'cadence': 'selected-native-stream-v1',
              'owner_schema': {key: {'version': item['version'],
                                     'source_sha256': item['source_sha256'],
                                     'fields': list(item['fields'])}
                               for key, item in owners['owners'].items()},
              'd0_reconstructible': False, 'qualification': 'NOT_REQUALIFIED',
              'owner_snapshot_scope': 'observation receipt; controller/expert restoration not implemented'}
    return metadata, recipe


def append_selected_transition(recorder, *, recorder_mode, record_native_substeps,
                               timebase, control_step, substeps, request, canonical,
                               target, applied, reward, terminated, truncated, stage,
                               diagnostics, boundary, owners, task_metrics):
    """Validate and append one completed selected interval to its recorder."""
    from ..trajectory.canonical.contracts import TransitionRecord

    count = timebase.control_substeps
    if record_native_substeps and (
            len(substeps) != count or [item[0] for item in substeps] != list(range(count))):
        raise ValueError('missing native application receipts')
    if record_native_substeps and recorder is not None and recorder_mode == 'execution':
        from ..trajectory.canonical.execution import validate_pending_native_interval
        validate_pending_native_interval(
            getattr(recorder, 'pending', None), control_step=control_step - 1,
            physics_dt=timebase.physics_dt, control_substeps=count,
        )
    wait = bool(diagnostics.get('readiness_hold', False))
    transition = TransitionRecord(
        request, canonical, target, applied, float(reward), terminated, truncated, stage,
        {key: json.dumps(value, sort_keys=True) for key, value in diagnostics.items()},
        not wait, wait,
    )
    if recorder_mode == 'canonical':
        recorder.append(transition, boundary())
        return
    recorder.append(transition, boundary(), owners(), 'reference',
                    {'observed_native_substeps': len(substeps), 'control_step': control_step},
                    task_metrics())


def coordinator_receipt(*, step, time, artifact_hash, controller_identity,
                        solution_identity, provider, execution_mode, task_outcome,
                        source_sha256):
    """Project current state into the existing non-restorable owner receipt."""
    fields = {'_stage_index': 0, 'execution_mode': execution_mode,
              'task_outcome': task_outcome}
    result = {'control_step': step, 'simulation_time': time,
              'artifact_hash': artifact_hash, 'controller_identity': controller_identity,
              'solution_identity': solution_identity, 'provider': provider,
              'owners': {'coordinator': {'version': 'selected-reference-observation-v1',
                  'source_sha256': source_sha256,
                  'fields': {key: {'present': True, 'value': value}
                             for key, value in fields.items()}}}}
    result['integrity_hash'] = digest(result)
    return result
