"""Independent primitive conformance worker, using unchanged P1.3 oracles."""
import argparse
import hashlib
import json
from pathlib import Path
import traceback
import yaml
from ..conformance.evaluate import evaluate
from ..conformance.lock import verify


def run(provider, oracle, probe, output):
    output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError('refusing prerequisite Evidence overwrite')
    specification = verify(oracle)[0]['probes'][probe]
    report = {'provider': provider, 'probe': probe, 'fixture_hash': specification['fixture_hash'],
        'oracle_sha256': hashlib.sha256(Path(oracle).read_bytes()).hexdigest(), 'status': 'error', 'series': []}
    adapter = None
    try:
        if provider == 'sapien':
            from .sapien_probe import SapienProbe
            adapter = SapienProbe(specification)
        elif provider == 'genesis':
            from .genesis_probe import GenesisProbe
            adapter = GenesisProbe(specification, output.parent)
        else:
            raise ValueError('unsupported prerequisite provider')
        report['facts'] = adapter.facts(); report['series'].append(adapter.read())
        for _ in range(specification['recipe']['timebase']['steps']):
            adapter.step(); report['series'].append(adapter.read())
        report.update(evaluate(specification, report['series'], report['facts']))
    except Exception as error:
        report.update(error=str(error), traceback=traceback.format_exc())
    finally:
        if adapter is not None:
            try: adapter.close(); report['closed'] = True
            except Exception as error: report.update(status='error', close_error=str(error))
        verify(oracle)
        with output.open('x') as handle:
            handle.write(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--provider', choices=['sapien', 'genesis'], required=True)
    p.add_argument('--oracle', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--probe', choices=['asset_frame', 'free_fall', 'joint_tracking', 'contact'], required=True)
    a = p.parse_args(); r = run(a.provider, a.oracle, a.probe, a.output)
    print(a.provider, a.probe, r['status'], r.get('error', ''))
    raise SystemExit(0 if r['status'] == 'pass' else 1)


if __name__ == '__main__': main()
