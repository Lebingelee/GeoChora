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
