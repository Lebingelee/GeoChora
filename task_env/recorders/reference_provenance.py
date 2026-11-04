"""Recording-time source snapshot and per-boundary coordinator receipt."""
from hashlib import sha256
from pathlib import Path

from ..controllers.canonical.contracts import digest


def source_snapshot(path):
    """Identify the file bytes at the start of one recording."""
    return sha256(Path(path).read_bytes()).hexdigest()


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
