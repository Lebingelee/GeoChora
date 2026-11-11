"""Summarize a failed feasibility report and write fixed-pose diagnostic specs.

Reads one ``feasibility_probe`` CheckReport and the exact candidate spec it
ran. Writes ``summary.json`` (non-solved seeds grouped by outcome, each seed's
reset offset, and which findings a ledger revision may cite) plus one
``fixed-pose-seed<N>.spec.json`` per selected non-solved seed. Each diagnostic
spec pins the reset to that seed's recorded object pose with zero extent, so a
separate probe can isolate the pose from the sampling distribution.

This tool is descriptive. It runs no physics, imports no Core module, makes no
revision decision and never establishes infeasibility. Diagnostic specs are
evidence inputs, not candidates. The output directory must be new.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from completion_facts import CLASSIFICATIONS
from harness_spec_schema import CandidateSpec, CheckReport, save_json

SUMMARY_SCHEMA = 'harness-diagnostic-summary-v1'
REVISABLE_LOCALITIES = ('task_local', 'unknown')


class DiagnosisInputError(ValueError):
    """The report/spec pair cannot be diagnosed as supplied."""


def _require(condition, message):
    if not condition:
        raise DiagnosisInputError(message)


def _read_once(path):
    """Return ``(parsed, sha256)`` from one read, so the cited hash is the analyzed snapshot.

    A probe report is rewritten at every seed checkpoint; hashing a second read
    could cite bytes this diagnosis never parsed.
    """
    data = Path(path).read_bytes()
    if Path(path).suffix.lower() in ('.yaml', '.yml'):
        import yaml
        value = yaml.safe_load(data)
    else:
        value = json.loads(data)
    return value, hashlib.sha256(data).hexdigest()


def _object_key(rows, requested):
    keys = set()
    for row in rows:
        if isinstance(row.get('start_pose'), dict):
            keys.update(row['start_pose'])
    if requested is not None:
        _require(not keys or requested in keys,
                 f'--object-key {requested!r} is absent from recorded start poses: {sorted(keys)}')
        return requested
    _require(len(keys) <= 1, f'several entities have start poses; choose one with --object-key: {sorted(keys)}')
    return next(iter(keys), None)


def _object_xy(row, key):
    pose = row.get('start_pose')
    if key is None or not isinstance(pose, dict) or key not in pose:
        return None
    position = pose[key].get('position')
    _require(isinstance(position, list) and len(position) == 3, f"seed {row.get('seed')} start pose is malformed")
    return [float(position[0]), float(position[1])]


def _bounds(offsets):
    if not offsets:
        return None
    return {'min': [min(o[i] for o in offsets) for i in range(2)],
            'max': [max(o[i] for o in offsets) for i in range(2)]}


def _finding_rows(report):
    result = []
    for index, finding in enumerate(report.findings):
        revisable = finding.locality in REVISABLE_LOCALITIES and finding.category != 'execution_fault'
        result.append({
            'finding_index': index, 'check': finding.check, 'category': finding.category,
            'locality': finding.locality, 'seed': finding.evidence.get('seed'),
            'row_index': finding.evidence.get('row_index'),
            # Mirrors construction_ledger.begin: owner localities and execution
            # faults are escalated, and unknown attribution needs diagnostics.
            'spec_revision_allowed': revisable,
            'diagnostics_required': revisable and finding.locality == 'unknown',
        })
    return result


def diagnose(report_path, spec_path, *, seeds=None, object_key=None):
    """Return ``(summary, {filename: CandidateSpec})`` without touching the filesystem."""
    report_path, spec_path = Path(report_path).resolve(), Path(spec_path).resolve()
    spec_value, spec_file_sha256 = _read_once(spec_path)
    report_value, report_sha256 = _read_once(report_path)
    spec = CandidateSpec.from_dict(spec_value)
    report = CheckReport.from_dict(report_value)
    _require(report.tool == 'feasibility_probe', f'expected a feasibility_probe report, got {report.tool!r}')
    _require(report.spec_sha256 == spec.spec_sha256(), 'report was produced for a different spec')
    rows = report.details.get('rows')
    _require(isinstance(rows, list) and rows,
             'report has no episode rows (compile rejection or tool error); read its findings directly')
    for row in rows:
        _require(isinstance(row, dict) and type(row.get('seed')) is int
                 and row.get('classification') in CLASSIFICATIONS, 'report row lacks a seed or known classification')
    row_seeds = [row['seed'] for row in rows]
    _require(len(set(row_seeds)) == len(row_seeds), 'report rows repeat a seed')
    if seeds is not None:
        _require(len(set(seeds)) == len(seeds), '--seeds repeats a seed')
        by_seed = {row['seed']: row for row in rows}
        for seed in seeds:
            _require(seed in by_seed, f'seed {seed} is not in the report')
            _require(by_seed[seed]['classification'] != 'solved',
                     f'seed {seed} solved; a fixed-pose diagnostic targets non-solved seeds')

    key = _object_key(rows, object_key)
    center = spec.object_config['initial_pos_xy']
    half_extent = spec.object_config['reset_half_extent_m']
    findings = _finding_rows(report)
    totals = {name: sum(row['classification'] == name for row in rows) for name in CLASSIFICATIONS}

    seed_rows, groups, offsets = [], {}, {'solved': [], 'non_solved': []}
    for index, row in enumerate(rows):
        xy = _object_xy(row, key)
        offset = None if xy is None else [xy[i] - center[i] for i in range(2)]
        solved = row['classification'] == 'solved'
        if offset is not None:
            offsets['solved' if solved else 'non_solved'].append(offset)
        seed_rows.append({
            'seed': row['seed'], 'row_index': index, 'classification': row['classification'],
            'phase': row.get('phase'), 'stage': row.get('stage'), 'reason': row.get('reason'),
            'steps': row.get('steps'), 'object_xy': xy, 'offset_from_reset_center_xy': offset,
            'offset_fraction_of_half_extent': (None if offset is None or not half_extent
                                               else [value / half_extent for value in offset]),
            'finding_indices': [f['finding_index'] for f in findings if f['seed'] == row['seed']],
        })
        if not solved:
            group_key = (row['classification'], row.get('phase'), row.get('stage'), row.get('reason'))
            groups.setdefault(group_key, []).append(row['seed'])

    solved_bounds = _bounds(offsets['solved'])
    outside = None
    if solved_bounds is not None:
        outside = [item['seed'] for item in seed_rows
                   if item['classification'] != 'solved' and item['offset_from_reset_center_xy'] is not None
                   and any(not solved_bounds['min'][i] <= item['offset_from_reset_center_xy'][i] <= solved_bounds['max'][i]
                           for i in range(2))]

    selected = seeds if seeds is not None else [item['seed'] for item in seed_rows if item['classification'] != 'solved']
    by_seed = {item['seed']: item for item in seed_rows}
    specs, diagnostics, seen = {}, [], {}
    for seed in selected:
        item = by_seed[seed]
        entry = {'seed': seed, 'spec': None, 'spec_sha256': None, 'skipped': None}
        if item['object_xy'] is None:
            entry['skipped'] = 'start pose was not recorded for this seed'
        elif not half_extent:
            # Decided from reset semantics, not the spec hash: a provider may
            # record the same pose rounded (Isaac casts the center to float32),
            # which would change the hash without changing the reset.
            entry['skipped'] = 'candidate reset already has zero extent; not an independent diagnostic'
        else:
            value = spec.to_dict()
            value['object_config'] = {**value['object_config'], 'initial_pos_xy': item['object_xy'],
                                      'reset_half_extent_m': 0.0}
            fixed = CandidateSpec.from_dict(value)
            digest = fixed.spec_sha256()
            if digest == spec.spec_sha256():
                # The ledger rejects a diagnostic whose spec equals the cited candidate.
                entry['skipped'] = 'candidate already resets to exactly this pose; not an independent diagnostic'
            elif digest in seen:
                entry['skipped'] = f'same pose as seed {seen[digest]}'
            else:
                name = f'fixed-pose-seed{seed}.spec.json'
                seen[digest] = seed
                specs[name] = fixed
                entry.update(spec=name, spec_sha256=digest,
                             changed={'object_config.initial_pos_xy': item['object_xy'],
                                      'object_config.reset_half_extent_m': 0.0})
        diagnostics.append(entry)

    summary = {
        'schema_version': SUMMARY_SCHEMA,
        'scope': ('Descriptive regrouping of recorded probe rows. Not a new probe, not evidence of '
                  'infeasibility, and not a revision decision. Fixed-pose specs are diagnostic inputs only.'),
        'source': {
            'report': str(report_path), 'report_sha256': report_sha256,
            'spec': str(spec_path), 'spec_file_sha256': spec_file_sha256, 'spec_sha256': spec.spec_sha256(),
            'artifact_hash': report.artifact_hash, 'core_commit': report.core_commit,
            'provider': report.details.get('provider'), 'horizon': report.details.get('horizon'),
            'report_status': report.status, 'complete': report.details.get('complete'),
        },
        'totals': totals,
        'declared_totals_match': report.details.get('totals') == totals,
        'reset': {'object_key': key, 'center_xy': center, 'half_extent_m': half_extent},
        'non_solved_groups': sorted(
            ({'classification': k[0], 'phase': k[1], 'stage': k[2], 'reason': k[3],
              'count': len(v), 'seeds': v} for k, v in groups.items()),
            key=lambda group: (-group['count'], group['seeds'][0])),
        'offset_bounds': {'solved': solved_bounds, 'non_solved': _bounds(offsets['non_solved']),
                          'non_solved_seeds_outside_solved_bounds': outside},
        'seeds': seed_rows,
        'findings': findings,
        'fixed_pose_diagnostics': diagnostics,
    }
    return summary, specs


def write(summary, specs, output_dir):
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=False)
    for name, spec in specs.items():
        spec.save(root / name)
    for entry in summary['fixed_pose_diagnostics']:
        if entry['spec'] is not None:
            entry['spec'] = str(root / entry['spec'])
    save_json(summary, root / 'summary.json')
    return root / 'summary.json'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--report', type=Path, required=True, help='feasibility_probe CheckReport to regroup')
    parser.add_argument('--spec', type=Path, required=True, help='the exact candidate spec that report ran')
    parser.add_argument('--output-dir', type=Path, required=True, help='new directory for summary.json and specs')
    parser.add_argument('--seeds', type=int, nargs='+',
                        help='non-solved seeds to write fixed-pose specs for (default: all non-solved)')
    parser.add_argument('--object-key', help='entity whose start pose defines the reset (needed if several)')
    args = parser.parse_args(argv)
    try:
        summary, specs = diagnose(args.report, args.spec, seeds=args.seeds, object_key=args.object_key)
        path = write(summary, specs, args.output_dir)
    except (ValueError, TypeError, KeyError, OSError) as error:
        print(json.dumps({'status': 'error', 'error': f'{type(error).__name__}: {error}'}))
        return 2
    print(json.dumps({'status': 'written', 'summary': str(path), 'totals': summary['totals'],
                      'non_solved_groups': len(summary['non_solved_groups']),
                      'fixed_pose_specs': [e['spec'] for e in summary['fixed_pose_diagnostics'] if e['spec']]}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
