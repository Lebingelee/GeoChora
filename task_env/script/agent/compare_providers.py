"""Compare episode outcomes of one candidate across providers, seed by seed.

Reads two or more ``feasibility_probe`` CheckReports, one per provider, and
writes a single JSON comparison: per-seed classification, steps, stage and
reason for each provider; which seeds agree; and how far the recorded start
poses differ.

This compares recorded outcomes only. Agreement is not per-step physical
equivalence, replay validity or Qualification, and disagreement does not say
which provider is right. The tool runs no physics and imports no Core module.
Reports are read once and identified by the hash of those bytes. Each report's
rows are checked against the current completion contract; a report that fails
is still shown, marked unverified, so historical reports remain comparable
without being promoted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from completion_facts import CLASSIFICATIONS, COMPLETION_CONTRACT, validate_probe_report
from harness_spec_schema import CheckReport, save_json

COMPARISON_SCHEMA = 'harness-provider-comparison-v1'


class ComparisonInputError(ValueError):
    """The supplied reports cannot be compared."""


def _require(condition, message):
    if not condition:
        raise ComparisonInputError(message)


def _load(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    report = CheckReport.from_dict(json.loads(data))
    _require(report.tool == 'feasibility_probe', f'{path.name}: expected a feasibility_probe report, got {report.tool!r}')
    provider = report.details.get('provider')
    _require(isinstance(provider, str) and provider, f'{path.name}: report does not declare a provider')
    rows = report.details.get('rows')
    _require(isinstance(rows, list) and rows, f'{path.name}: report has no episode rows')
    by_seed = {}
    for row in rows:
        _require(isinstance(row, dict) and type(row.get('seed')) is int
                 and row.get('classification') in CLASSIFICATIONS,
                 f'{path.name}: row lacks a seed or known classification')
        _require(row['seed'] not in by_seed, f'{path.name}: rows repeat seed {row["seed"]}')
        by_seed[row['seed']] = row
    try:
        # The validator requires the contract marker only of passing reports;
        # "verified" here must mean the current contract for any status.
        if report.details.get('completion_contract') != COMPLETION_CONTRACT:
            raise ValueError('report does not declare the current completion contract')
        validate_probe_report(report)
        contract_error = None
    except ValueError as error:
        contract_error = str(error)
    return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(), 'report': report,
            'provider': provider, 'rows': by_seed, 'contract_error': contract_error}


def _position(pose, key):
    entity = pose.get(key) if isinstance(pose, dict) else None
    position = entity.get('position') if isinstance(entity, dict) else None
    if isinstance(position, list) and len(position) == 3 and all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in position):
        return position
    return None


def _pose_spread(poses, expected):
    """Largest per-axis position difference, per entity, only where every provider recorded it.

    Returns None unless all ``expected`` providers have a row for the seed: a
    spread over a subset would read as agreement between all of them.
    """
    if len(poses) < expected or expected < 2:
        return None
    keys = set().union(*(set(pose) for pose in poses if isinstance(pose, dict)))
    result = {}
    for key in sorted(keys):
        positions = [_position(pose, key) for pose in poses]
        if all(p is not None for p in positions):
            result[key] = max(max(p[i] for p in positions) - min(p[i] for p in positions) for i in range(3))
    return result or None


def compare(report_paths, *, allow_spec_mismatch=False):
    loaded = [_load(path) for path in report_paths]
    _require(len(loaded) >= 2, 'at least two reports are required')
    providers = [item['provider'] for item in loaded]
    _require(len(set(providers)) == len(providers), f'each provider may appear once; got {providers}')
    spec_hashes = {item['report'].spec_sha256 for item in loaded}
    same_spec = len(spec_hashes) == 1 and None not in spec_hashes
    _require(same_spec or allow_spec_mismatch,
             'reports do not share one identified spec; pass --allow-spec-mismatch to compare them anyway')

    seeds = sorted(set().union(*(item['rows'] for item in loaded)))
    seed_rows, agree, disagree, partial = [], [], [], []
    for seed in seeds:
        outcomes, classes, poses = {}, [], []
        for item in loaded:
            row = item['rows'].get(seed)
            if row is None:
                outcomes[item['provider']] = None
                continue
            outcomes[item['provider']] = {key: row.get(key) for key in
                                          ('classification', 'steps', 'phase', 'stage', 'reason')}
            classes.append(row['classification'])
            poses.append(row.get('start_pose'))
        if len(classes) < len(loaded):
            status = 'not_in_all_reports'
            partial.append(seed)
        elif len(set(classes)) == 1:
            status = 'agree'
            agree.append(seed)
        else:
            status = 'disagree'
            disagree.append(seed)
        seed_rows.append({'seed': seed, 'comparison': status, 'outcomes': outcomes,
                          'start_position_max_difference_m': _pose_spread(poses, len(loaded))})

    def describe(item):
        report = item['report']
        totals = {name: sum(row['classification'] == name for row in item['rows'].values())
                  for name in CLASSIFICATIONS}
        return {'report': item['path'], 'report_sha256': item['sha256'],
                'spec_sha256': report.spec_sha256, 'artifact_hash': report.artifact_hash,
                'core_commit': report.core_commit, 'core_dirty': report.core_dirty,
                'report_status': report.status, 'complete': report.details.get('complete'),
                'horizon': report.details.get('horizon'), 'seed_count': len(item['rows']), 'totals': totals,
                'completion_contract_verified': item['contract_error'] is None,
                'completion_contract_error': item['contract_error']}

    described = {item['provider']: describe(item) for item in loaded}
    return {
        'schema_version': COMPARISON_SCHEMA,
        'scope': ('Recorded episode outcomes only. Agreement is not per-step physical equivalence, replay '
                  'validity or Qualification; disagreement does not identify which provider is correct.'),
        'providers': described,
        'same_spec': same_spec,
        'same_core_commit': len({d['core_commit'] for d in described.values()}) == 1,
        'same_horizon': len({d['horizon'] for d in described.values()}) == 1,
        'all_reports_contract_verified': all(d['completion_contract_verified'] for d in described.values()),
        'summary': {'seeds_compared': len(agree) + len(disagree), 'agree': len(agree), 'disagree': len(disagree),
                    'disagreeing_seeds': disagree, 'seeds_not_in_all_reports': partial},
        'seeds': seed_rows,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--reports', type=Path, nargs='+', required=True,
                        help='feasibility_probe reports, one per provider')
    parser.add_argument('--output', type=Path, required=True, help='new JSON file; never overwritten')
    parser.add_argument('--allow-spec-mismatch', action='store_true',
                        help='compare reports of different specs; the mismatch is recorded')
    args = parser.parse_args(argv)
    try:
        result = compare(args.reports, allow_spec_mismatch=args.allow_spec_mismatch)
        save_json(result, args.output)
    except (ValueError, TypeError, KeyError, OSError) as error:
        print(json.dumps({'status': 'error', 'error': f'{type(error).__name__}: {error}'}))
        return 2
    print(json.dumps({'status': 'written', 'output': str(args.output), 'same_spec': result['same_spec'],
                      **result['summary']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
