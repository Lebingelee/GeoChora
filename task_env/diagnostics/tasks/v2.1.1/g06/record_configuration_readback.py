"""Check solver provenance in actual H5 metadata without opening an Env."""
import argparse
import json
from pathlib import Path

import h5py
import yaml


def find_facts(value):
    if isinstance(value, dict):
        if 'solver_iterations_requested' in value:
            yield value
        for child in value.values():
            yield from find_facts(child)
    elif isinstance(value, list):
        for child in value:
            yield from find_facts(child)


def read(directory, *, iterations):
    files = sorted(Path(directory).glob('trajectory_slot_*.h5'))
    if not files:
        raise ValueError('no H5 trajectories')
    results = []
    for path in files:
        with h5py.File(path, 'r') as file:
            metadata = yaml.safe_load(file['meta/env_meta'][()].decode())
            candidates = list(find_facts(metadata))
            if not candidates:
                raise ValueError(f'{path.name}: no recorded solver facts')
            for facts in candidates:
                if (facts['solver_iterations_requested'] != iterations
                        or facts['solver_iterations_resolved']['contact'] != iterations
                        or facts['solver_iterations_resolved']['coupled_constraints'] < iterations
                        or facts['contact_mode_resolved'] != 'discrete'):
                    raise ValueError(f'{path.name}: solver provenance differs')
            leaves = []
            file['obs'].visit(lambda name: leaves.append(name))
            if any('boundary_identity_sha256' in name for name in leaves):
                raise ValueError(f'{path.name}: observation contains removed boundary digest')
            results.append({'file': path.name, 'facts': candidates[0]})
    return {'status': 'PASS', 'scope': 'recorded batch solver provenance and observation schema',
            'files': results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', required=True)
    parser.add_argument('--iterations', required=True, type=int)
    args = parser.parse_args()
    print(json.dumps(read(args.directory, iterations=args.iterations), indent=2))
