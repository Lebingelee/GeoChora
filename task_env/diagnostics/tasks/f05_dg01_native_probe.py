"""Explicit DG01 N0/N1 MuJoCo diagnostics through the frozen Core candidate."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path


def _utc_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _write_once(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def run_n0(output: Path):
    from task_env.runtime.sessions.api import materialize
    from task_env.tasks.position_candidate.builder import build_f05_dg01_mujoco_candidate

    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    started = _utc_now()
    candidate = build_f05_dg01_mujoco_candidate(output / 'candidate-build', horizon=300)
    session = None
    try:
        session = materialize(
            candidate.artifact, candidate.execution,
            source=candidate.source,
            _f05_dg01_mujoco_input=candidate.candidate_input,
        )
        model_receipt = getattr(session, '_f05_dg01_model_receipt', None)
        if not isinstance(model_receipt, dict):
            raise RuntimeError('DG01 Core Materialize returned without a public model receipt')
        if (getattr(session, '_native_steps', None) != 0
                or float(session._data.time) != 0.0
                or getattr(session, '_reset_done', None)):
            raise RuntimeError('N0 must end after model compile with zero reset, forward or physics steps')
        payload = {
            'schema_version': 'f05-dg01-n0-core-model-receipt-v1',
            'run_id': output.name,
            'started_utc': started,
            'finished_utc': _utc_now(),
            'native_invocations': 1,
            'physics_steps': 0,
            'physics_time_s': float(session._data.time),
            'reset_performed': False,
            'forward_calls': 0,
            'task_source_identity_sha256': candidate.task_source.identity_hash,
            'task_artifact_identity_sha256': candidate.artifact.identity_hash,
            'scene_identity_sha256': candidate.scene.identity_hash,
            'execution_identity_sha256': candidate.execution.identity_hash,
            'panda_source_closure_sha256': candidate.panda_closure_digest,
            'panda_source_file_count': candidate.panda_file_count,
            'derived_source_xml_sha256': candidate.derived_source_sha256,
            'runtime_source_closure_sha256': candidate.source_closure_digest,
            'task_scene_recipe_sha256': candidate.recipe_sha256,
            'model_receipt': model_receipt,
            'model_receipt_identity_sha256': model_receipt['identity_sha256'],
            'closed_at_zero_steps': False,
        }
    finally:
        if session is not None:
            session.close()
            if getattr(session, '_closed', False) is not True:
                raise RuntimeError('N0 RuntimeSession did not close')
        candidate.env.close()
    payload['closed_at_zero_steps'] = True
    _write_once(output / 'n0_model_receipt.json', payload)
    _write_once(output / 'n0_close_receipt.json', {
        'schema_version': 'f05-dg01-n0-close-receipt-v1',
        'run_id': output.name,
        'native_steps': 0,
        'physics_time_s': 0.0,
        'session_closed': True,
        'model_receipt_identity_sha256': payload['model_receipt_identity_sha256'],
    })
    return payload


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('n0',), required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    if args.mode == 'n0':
        result = run_n0(args.output)
        print(json.dumps({
            'mode': args.mode,
            'native_invocations': result['native_invocations'],
            'physics_steps': result['physics_steps'],
            'model_receipt_identity_sha256': result['model_receipt_identity_sha256'],
        }, sort_keys=True))


if __name__ == '__main__':
    main()
