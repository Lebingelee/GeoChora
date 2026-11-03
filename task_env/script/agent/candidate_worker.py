"""One strict-candidate episode inside the frozen Isaac Python.

Launched only by ``native_candidate_runner``. The worker opens the one headless
Isaac App before compiling the candidate the parent already admitted, then
runs either the feasibility ``run_seed`` loop (mode ``probe``)
or the Oracle recording body (mode ``oracle``) through the unchanged Core
PickCube owners, writes its raw facts, and leaves through the controlled Kit
exit boundary. It never classifies on behalf of the parent.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import time
import traceback

_CORE_ROOT = Path(__file__).resolve().parents[3]
if str(_CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(_CORE_ROOT))
_GEOPHYS_SOURCE = _CORE_ROOT / 'GeoPhys' / 'src'
if _GEOPHYS_SOURCE.is_dir() and str(_GEOPHYS_SOURCE) not in sys.path:
    sys.path.insert(1, str(_GEOPHYS_SOURCE))
_CORE_SITE = os.environ.get('GEOCHORA_CORE_SITE')
if _CORE_SITE and Path(_CORE_SITE).is_dir() and _CORE_SITE not in sys.path:
    # Keep Isaac's native packages first; the frozen Core environment only
    # supplies Python dependencies the Isaac distribution does not ship.
    sys.path.append(_CORE_SITE)

if __package__:
    from .builtin_example_worker import _terminate_isaac_worker
    from .catalog_query import core_context
    from .harness_compiler import CompilationRejected, compile_candidate
    from .harness_spec_schema import CandidateSpec
    from .provider_routes import requires_native_worker
else:
    from builtin_example_worker import _terminate_isaac_worker
    from catalog_query import core_context
    from harness_compiler import CompilationRejected, compile_candidate
    from harness_spec_schema import CandidateSpec
    from provider_routes import requires_native_worker

RECEIPT_SCHEMA = 'harness-candidate-worker-receipt-v1'


def _write(path: Path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False, default=str) + '\n')
    temporary.replace(path)


def run_worker(*, mode, spec, catalog, provider, seed, horizon, output, h5=None, time_limit_s=None):
    output = Path(output).resolve()
    receipt = {'schema_version': RECEIPT_SCHEMA, 'mode': mode, 'provider': provider, 'seed': seed,
               'horizon': horizon, 'worker_python': sys.executable, 'errors': [], 'app': None,
               'compiled': None, 'core_commit': None, 'core_dirty': None, 'facts': None,
               'row_written': False}
    app_owner = None
    row = None
    exit_code = 1
    phase = 'setup'
    try:
        if not requires_native_worker(provider):
            raise ValueError(f'{provider} does not use the native candidate worker')
        if horizon != spec.horizon:
            raise ValueError('worker horizon differs from the candidate spec')
        context = core_context(catalog['core_repo'])
        receipt.update(core_commit=context['core_commit'], core_dirty=context['core_dirty'])
        from task_env.runtime.sessions.isaac_native_io import (
            F06_ISAAC_APP_LAUNCH_PROFILE_V1, _process_app_owner,
        )
        app_owner = _process_app_owner(launch_profile_id=F06_ISAAC_APP_LAUNCH_PROFILE_V1)
        # Kit must register its USD libraries and schemas before source construction.
        phase = 'app_open'
        app_owner.open()
        receipt['app'] = {'launch_profile': app_owner.launch_profile_receipt()}
        phase = 'compile'
        compiled = compile_candidate(spec, catalog, provider=provider)
        initial = compiled.initial_value or {}
        receipt['compiled'] = {
            'spec_sha256': compiled.spec_sha256, 'artifact_hash': compiled.artifact_hash,
            'backend': compiled.backend, 'device': compiled.device, 'source_kind': compiled.source_kind,
            'source_closure_sha256': compiled.source_xml_sha256,
            'source_revision': initial.get('source_revision'),
            'source_sha256': dict(initial.get('source_sha256') or {}),
            'solution_identity': initial.get('solution_identity'),
            'controller_identity': getattr(initial.get('controller'), 'identity', None),
            'route': compiled.route,
        }
        phase = 'episode'
        if mode == 'probe':
            if __package__:
                from .feasibility_probe import run_seed
            else:
                from feasibility_probe import run_seed
            row = run_seed(compiled.env_class(), provider, seed, horizon)
            _write(output / 'row.json', row)
            receipt['row_written'] = True
            receipt['facts'] = {'classification': row['classification'], 'reason': row['reason']}
        elif mode == 'oracle':
            if __package__:
                from .oracle_candidate import alarm, record_episode
            else:
                from oracle_candidate import alarm, record_episode
            if h5 is None or time_limit_s is None:
                raise ValueError('oracle mode requires --h5 and --time-limit-s')
            deadline = time.perf_counter() + float(time_limit_s)
            with alarm(float(time_limit_s)):
                receipt['facts'] = record_episode(compiled, spec, provider=provider, seed=seed,
                                                  h5=Path(h5), deadline=deadline)
        else:
            raise ValueError(f'unknown worker mode: {mode}')
        exit_code = 0
    except CompilationRejected as error:
        receipt['errors'].append({'phase': phase, 'type': 'CompilationRejected', 'message': str(error),
                                  'report': asdict(error.report)})
        exit_code = 1
    except BaseException as error:
        receipt['errors'].append({'phase': phase, 'type': type(error).__name__, 'message': str(error),
                                  'traceback': ''.join(traceback.format_exception(type(error), error, error.__traceback__))})
        exit_code = 1
    finally:
        if app_owner is not None:
            try:
                app_owner.close()
            except BaseException as error:
                receipt['errors'].append({'phase': 'isaac_app_close', 'type': type(error).__name__,
                                          'message': str(error)})
            try:
                receipt.setdefault('app', {})
                receipt['app'] = {**(receipt['app'] or {}), 'close_receipt': app_owner.close_receipt()}
            except BaseException as error:
                receipt['errors'].append({'phase': 'isaac_app_close_receipt', 'type': type(error).__name__,
                                          'message': str(error)})
        if receipt['errors']:
            exit_code = 1
            if row is not None:
                first = receipt['errors'][0]
                row.update(classification='invalid', phase='close', error_phase='close',
                           error_type=first['type'], error_message=first['message'],
                           error_traceback=json.dumps(receipt['errors'], sort_keys=True),
                           cleanup_error=first['message'], close_succeeded=False,
                           reason='native App cleanup failed')
                _write(output / 'row.json', row)
        receipt['exit_code'] = exit_code
        _write(output / 'worker_receipt.json', receipt)
    return receipt, exit_code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('probe', 'oracle'), required=True)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--provider', required=True)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--horizon', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--h5', type=Path, help='oracle mode: canonical/v3 H5 output path')
    parser.add_argument('--time-limit-s', type=int, help='oracle mode: wall-clock budget')
    args = parser.parse_args(argv)
    spec = CandidateSpec.load(args.spec)
    catalog = json.loads(args.catalog.read_text())
    receipt, exit_code = run_worker(mode=args.mode, spec=spec, catalog=catalog, provider=args.provider,
                                    seed=args.seed, horizon=args.horizon, output=args.output,
                                    h5=args.h5, time_limit_s=args.time_limit_s)
    print(json.dumps({'mode': args.mode, 'seed': args.seed, 'provider': args.provider,
                      'exit_code': exit_code, 'errors': receipt['errors']}, sort_keys=True, default=str),
          flush=True)
    _terminate_isaac_worker(exit_code)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
