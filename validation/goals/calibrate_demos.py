"""Calibration: evaluate the 19 franka-scene-50 1.0.0 demo traces with the goal evaluator.

Reports agreement/disagreement only; no threshold is tuned. Run from the GeoChora root:

    python -m validation.goals.calibrate_demos [--simdatakit PATH]

For each demo task folder two evaluations are made:
  (a) the v2 (`low-detail-task/1.2.0`) task selected by the `v1` field of tools/task_specs.py;
  (b) a goal written below that follows the 1.0.0 prompt, with named objects replaced by bind
      variables of the same kind (so any object the demo happened to use can satisfy it).
Outputs evidence/demo-calibration.json and .md in the v2 workspace.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import runpy

from validation.goals import evaluate_task, load_vocabulary
from validation.goals.adapters.simdatakit_trace import read_trace

ROOT = Path(__file__).resolve().parents[3]


def A(pred, *args):
    return {'pred': pred, 'args': list(args)}


def ALL(*nodes):
    return {'all': list(nodes)}


def ANY(*nodes):
    return {'any': list(nodes)}


def FLAT(x):
    return ANY(A('Upright', x), A('Inverted', x))


def seq(*stages):
    return {'pred': 'Sequence', 'args': [ALL(*s) for s in stages]}


BRICK, BALL = {'kind': 'brick'}, {'kind': 'ball'}
LONG = {'kind': 'brick', 'size_class': 'long'}
ON_TABLE_BRICK = {'kind': 'brick', 'initially_on': 'table'}

# task_id -> (review outcome from the batch README/review, explicit (b) truth or None)
ONE_BALL = ALL(A('In', '?b', 'drawer_2'))
EXPLICIT = {
    'fsc-ball-drawer': {'bind': {'?b': BALL}, 'goal': ONE_BALL},
    'fsc-close-open-middle': {'goal': ALL(A('Closed', 'drawer_2'))},
    'fsc-layout-t': {  # two elongated bricks flat on the table in a T; any brick class, because Perpendicular
        # itself requires long/short ratio >= 1.25 (the demo used a long and a mid brick)
        'bind': {'?a': BRICK, '?b': BRICK},
        'goal': ALL(A('Perpendicular', '?a', '?b'), A('Near', '?a', '?b'), A('OnTable', '?a'), A('OnTable', '?b'),
                    FLAT('?a'), FLAT('?b'))},
    'fsc-unstack-existing': {  # the upper brick of an original stack goes to the table, the lower one stays
        'bind': {'?t1': {'kind': 'brick', 'initially_on': 'red_long_brick'},
                 '?t2': {'kind': 'brick', 'initially_on': 'yellow_mid_brick'}},
        'goal': ANY(ALL(A('OnTable', '?t1'), A('Unmoved', 'red_long_brick')),
                    ALL(A('OnTable', '?t2'), A('Unmoved', 'yellow_mid_brick')))},
    'fsc-align-drawer-edge': {
        'bind': {'?a': LONG},
        'goal': ALL(A('Perpendicular', '?a', 'drawer_front'), A('OnTable', '?a'), FLAT('?a'))},
    'fsc-open-drawer': {'goal': ALL(A('Open', 'drawer_2'))},
    'fsc-parallel-row': {
        'bind': {'?a': LONG, '?b': LONG, '?c': LONG},
        'goal': ALL(A('Row', ['?a', '?b', '?c']), A('Parallel', '?a', '?b'), A('Parallel', '?b', '?c'),
                    A('Parallel', '?a', '?c'), A('OnTable', '?a'), A('OnTable', '?b'), A('OnTable', '?c'))},
    'fsc-stack-two': {  # two originally separate bricks stacked, lower one on the table
        'bind': {'?u': ON_TABLE_BRICK, '?l': ON_TABLE_BRICK},
        'goal': ALL(A('On', '?u', '?l'), A('OnTable', '?l'))},
    'fsc-swap-places': {
        'bind': {'?a': ON_TABLE_BRICK, '?b': ON_TABLE_BRICK},
        'goal': ALL(A('AtInitialPositionOf', '?a', '?b'), A('AtInitialPositionOf', '?b', '?a'),
                    A('OnTable', '?a'), A('OnTable', '?b'))},
    'fsc-flip-brick': {
        'bind': {'?a': {'kind': 'brick', 'initial_orientation': 'inverted'}},
        'goal': ALL(A('Upright', '?a'), A('OnTable', '?a'))},
    'fsc-group-types': {
        'bind': {'?b1': BALL, '?b2': BALL, '?k1': BRICK, '?k2': BRICK},
        'goal': ALL(A('Grouped', ['?b1', '?b2'], ['?k1', '?k2']), A('OnTable', '?b1'), A('OnTable', '?b2'),
                    A('OnTable', '?k1'), A('OnTable', '?k2'))},
    'fsc-stand-brick': {  # an originally flat long brick stood on a side face
        'bind': {'?a': {'kind': 'brick', 'size_class': 'long', 'initial_orientation': 'upright'}},
        'goal': ALL(A('OnSide', '?a'), A('OnTable', '?a'))},
    'fsc-store-close': {'bind': {'?b': BALL}, 'goal': ALL(A('In', '?b', 'drawer_2'), A('Closed', 'drawer_2'))},
    'fsc-store-retrieve': {  # ball into the open middle drawer, released, then taken out onto the table
        'bind': {'?b': BALL},
        'goal': ALL(A('OnTable', '?b')),
        'process': [seq([A('In', '?b', 'drawer_2'), A('Released', '?b')], [A('OnTable', '?b')])]},
    'fsc-between-drawers': {  # a brick into the open lowest drawer, released, then moved into the middle drawer
        'bind': {'?k': ON_TABLE_BRICK},
        'goal': ALL(A('In', '?k', 'drawer_2')),
        'process': [seq([A('In', '?k', 'drawer_1'), A('Released', '?k')], [A('In', '?k', 'drawer_2')])]},
    'fsc-enclose-ball': {  # APPROXIMATION: the vocabulary has no enclosure predicate
        'bind': {'?ball': BALL, '?k1': BRICK, '?k2': BRICK, '?k3': BRICK},
        'goal': ALL(A('Between', '?ball', '?k1', '?k2'), A('Parallel', '?k1', '?k2'),
                    A('Near', '?ball', '?k1'), A('Near', '?ball', '?k2'), A('Near', '?ball', '?k3'),
                    A('OnTable', '?ball'), A('OnTable', '?k1'), A('OnTable', '?k2'), A('OnTable', '?k3')),
        'approximate': True},
    'fsc-invert-brick': {
        'bind': {'?a': {'kind': 'brick', 'initial_orientation': 'upright'}},
        'goal': ALL(A('Inverted', '?a'), A('OnTable', '?a'))},
    'fsc-selective-retrieval': {  # ball and brick into the open lowest drawer; only the ball comes back out
        'bind': {'?b': {'kind': 'ball'}, '?k': ON_TABLE_BRICK},
        'goal': ALL(A('OnTable', '?b'), A('In', '?k', 'drawer_1')),
        'process': [seq([A('In', '?b', 'drawer_1'), A('In', '?k', 'drawer_1'), A('Released', '?b'),
                         A('Released', '?k')], [A('OnTable', '?b'), A('In', '?k', 'drawer_1')])]},
    'fsc-sort-drawers': {  # the 1.0.0 prompt does not ask to close the drawers
        'bind': {'?b1': BALL, '?b2': BALL, '?k1': BRICK, '?k2': BRICK},
        'goal': ALL(A('In', '?b1', 'drawer_1'), A('In', '?b2', 'drawer_1'),
                    A('In', '?k1', 'drawer_2'), A('In', '?k2', 'drawer_2'))},
}

# AI-review outcome per demo: README of the batch (and review.json / final-demo-review.json)
REVIEW = {tid: 'success' for tid in EXPLICIT}
REVIEW['fsc-unstack-existing'] = 'partial'
REVIEW_SOURCE = ('batch README.md + review.json (goal_observed); sample4 batch: '
                 'datasets/archive/releases/franka-scene-50/1.0.0/evidence/final-demo-review.json '
                 '(unstack-existing: partial_result_original_lower_position_not_confirmed)')


def _compact(result):
    if result is None:
        return None
    return {k: result.get(k) for k in ('success', 'success_reason', 'goal', 'goal_reason', 'goal_if_settled')}


def _walk_margins(atoms):
    """(norm_margin, pred, args, key, info) for every banded measurement of the chosen assignment."""
    found = []
    for atom in atoms:
        for key, info in (atom.get('measurements') or {}).items():
            if isinstance(info, dict) and 'norm_margin' in info and info.get('measure') is not None:
                found.append((info['norm_margin'], atom['pred'], atom.get('resolved'), key, info))
    for atom in atoms:  # support relations: geometric gap of the lowest point above the surface (vocabulary 0.003 m)
        gap = (atom.get('measurements') or {}).get('gap_above_surface_m')
        if gap is not None and atom['pred'] in ('On', 'OnTable'):
            found.append((abs(gap - 0.003) / 0.003, atom['pred'], atom.get('resolved'), 'gap_above_surface_m',
                          {'measure': gap, 'pass': '[-0.006, 0.003] (fallback lower bound)', 'fail': '>= 0.006 (fallback)'}))
    return sorted(found, key=lambda t: t[0])


def summarise(result):
    atoms = result['atoms']
    unknowns = [{'pred': a['pred'], 'resolved': a.get('resolved'), 'reason': a.get('reason')}
                for a in atoms if a['value'] is None]
    unknowns += [{'process': p['pred'], 'reason': p.get('reason')} for p in result['process']
                 if p['value'] is None and p.get('reason') != 'skipped_goal_false']
    if result['all_released']['value'] is None:
        unknowns.append({'pred': 'AllReleased', 'reason': result['all_released'].get('reason'),
                         'unknown_objects': result['all_released']['measurements'].get('unknown_objects')})
    if result.get('goal_reason'):
        unknowns.append({'goal': result['goal_reason']})
    nearest = [{'pred': p, 'args': a, 'measure_key': k, 'measure': i['measure'], 'pass': i['pass'],
                'fail': i['fail'], 'normalised_distance_to_nearest_band_edge': round(m, 4)}
               for m, p, a, k, i in _walk_margins(atoms)[:3]]
    false_atoms = [{'pred': a['pred'], 'resolved': a.get('resolved')} for a in atoms if a['value'] is False]
    return {'result': _compact(result), 'assignment': result['assignment'],
            'assignments': result['assignments'], 'settle': result['settle'],
            'false_atoms': false_atoms, 'unknown': unknowns, 'nearest_to_thresholds': nearest,
            'all_released': {'value': result['all_released']['value'],
                             'min_finger_clearance_m': result['all_released']['measurements'].get('min_finger_clearance_m'),
                             'basis': result['all_released'].get('basis')},
            'process': [{k: p.get(k) for k in ('pred', 'value', 'reason', 'measurements')} for p in result['process']],
            'basis': result['basis']}


def run(simdatakit):
    sdk = Path(simdatakit)
    v2dir = sdk / 'workspace/franka-scene-50-v2'
    manifest = json.loads((v2dir / 'resources/object-manifest.json').read_text(encoding='utf-8'))
    vocab_path = sdk / 'catalog/profiles/vocabularies/scene-predicates-v1.yaml'
    vocabulary = load_vocabulary(vocab_path)
    v1_rows = [json.loads(line) for line in (sdk / 'datasets/archive/releases/franka-scene-50/1.0.0/tasks.jsonl')
               .read_text(encoding='utf-8').splitlines()]
    v2_rows = {json.loads(line)['task_id']: json.loads(line)
               for line in (v2dir / 'tasks.jsonl').read_text(encoding='utf-8').splitlines()}
    specs = runpy.run_path(str(v2dir / 'tools/task_specs.py'))['SPECS']
    v2_by_v1 = {}
    for spec in specs:
        if spec['v1'] is not None:
            v2_by_v1.setdefault(spec['v1'], []).append(spec['id'])
    out = []
    for folder in sorted((sdk / 'results/franka-scene-50/1.0.0').glob('*/tasks/*')):
        tid = folder.name
        v1_index = 1 + next(i for i, r in enumerate(v1_rows) if r['task_id'] == tid)
        summary = json.loads((folder / 'run-summary.json').read_text(encoding='utf-8'))
        trace = read_trace(folder / 'trace.json', manifest, recording_complete=bool(summary.get('full_execution')))
        initial, final = trace.samples[0], trace.samples[-1]
        entry = {'task_id': tid, 'batch': folder.parents[1].name, 'v1_index': v1_index,
                 'review_outcome': REVIEW[tid], 'trace_samples': len(trace.samples),
                 'duration_s': float(trace.times[-1]), 'recording_complete': trace.recording_complete,
                 'prompt_1_0_0': v1_rows[v1_index - 1]['prompt'].splitlines()[0], 'a': [], 'b': None}
        for v2id in v2_by_v1.get(v1_index, []):
            row = v2_rows[v2id]
            entry['a'].append({'v2_task_id': v2id, 'prompt': row['prompt'].splitlines()[0],
                               **summarise(evaluate_task(row, manifest, vocabulary, final, initial, trace))})
        truth = EXPLICIT[tid]
        row = {'task_id': f'{tid}:explicit', 'truth': {k: truth[k] for k in ('goal', 'bind', 'process') if k in truth}}
        entry['b'] = {'goal': truth['goal'], 'bind': truth.get('bind'), 'process': truth.get('process'),
                      'approximate': bool(truth.get('approximate')),
                      **summarise(evaluate_task(row, manifest, vocabulary, final, initial, trace))}
        out.append(entry)
    return {'schema': 'goal-demo-calibration/1', 'vocabulary': vocabulary['version'],
            'vocabulary_sha256': hashlib.sha256(vocab_path.read_bytes()).hexdigest(),
            'diagnostic_count': len(out),
            'review_source': REVIEW_SOURCE,
            'note': 'Agreement report only; thresholds are the vocabulary values and were not tuned. '
                    'Geometric support/release evidence (the traces have no contact records).',
            'demos': out}


def _cell(r):
    if r is None:
        return 'n/a'
    s = r['result']
    word = {True: 'TRUE', False: 'FALSE', None: 'unknown'}[s['success']]
    if s['goal'] != s['success'] and s['goal'] is not None:
        word += f" (goal {s['goal']})"
    return word


def _key(summary):
    near = summary['nearest_to_thresholds']
    bits = []
    if near:
        n = near[0]
        bits.append(f"{n['pred']} {n['measure_key']}={n['measure']:.4g} (pass {n['pass']}, fail {n['fail']})")
    if summary['false_atoms'] and summary['result']['success'] is False:
        bits.append('false: ' + ', '.join(f"{a['pred']}{a['resolved']}" for a in summary['false_atoms'][:2]))
    return '; '.join(bits)


def markdown(report):
    lines = ['# Goal evaluator calibration on the 19 franka-scene-50 1.0.0 demos', '',
             f"Vocabulary {report['vocabulary']} (sha256 {report['vocabulary_sha256']}); "
             f"{report['diagnostic_count']} demos. {report['note']}", '',
             f"Review outcome source: {report['review_source']}.", '',
             '(a) = v2 task mapped by `v1`; (b) = goal written from the 1.0.0 prompt with bind variables. '
             'Cell = evaluator success (goal AND process).', '',
             '| demo | v1 | review | (a) | (b) | unknown reasons | key measurement (b) |',
             '| --- | --- | --- | --- | --- | --- | --- |']
    for d in report['demos']:
        a = '<br>'.join(f"{x['v2_task_id'].replace('fsc2-', '')}: {_cell(x)}" for x in d['a']) or 'no v2 task'
        unk = [u for x in d['a'] + [d['b']] for u in x['unknown']]
        reasons = sorted({str(u.get('reason') or u.get('goal')) for u in unk})
        lines.append(f"| {d['task_id']} | {d['v1_index']} | {d['review_outcome']} | {a} | {_cell(d['b'])}"
                     f"{' (approx.)' if d['b']['approximate'] else ''} | {'; '.join(reasons)} | {_key(d['b'])} |")
    lines += ['', '## Per demo detail', '']
    for d in report['demos']:
        lines += [f"### {d['task_id']} (v1 #{d['v1_index']}, {d['batch']}, {d['duration_s']:.1f} s, {d['trace_samples']} samples)",
                  f"1.0.0 prompt: {d['prompt_1_0_0']}", f"review: {d['review_outcome']}"]
        for label, s in [(f"(a) {x['v2_task_id']}", x) for x in d['a']] + [('(b)', d['b'])]:
            lines.append(f"- {label}: {_cell(s)}; assignment {s['assignment']}; settle {s['settle'].get('settled')} "
                         f"({s['settle'].get('max_speed_mps', s['settle'].get('reason'))})")
            if s['false_atoms']:
                lines.append(f"  - false atoms: {s['false_atoms']}")
            for u in s['unknown']:
                lines.append(f"  - unknown: {u}")
            for n in s['nearest_to_thresholds']:
                lines.append(f"  - nearest: {n['pred']}{n['args']} {n['measure_key']}={n['measure']:.5g} "
                             f"pass {n['pass']} fail {n['fail']}")
            lines.append(f"  - AllReleased {s['all_released']}")
        lines.append('')
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simdatakit', default=str(ROOT / 'SimDataKit'))
    parser.add_argument('--out', default=None,
                        help='output folder (default: the SimDataKit v2 workspace evidence folder)')
    args = parser.parse_args(argv)
    report = run(args.simdatakit)
    evidence = Path(args.out) if args.out else Path(args.simdatakit) / 'workspace/franka-scene-50-v2/evidence'
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / 'demo-calibration.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1, default=str) + '\n', encoding='utf-8')
    (evidence / 'demo-calibration.md').write_text(markdown(report), encoding='utf-8')
    for d in report['demos']:
        print(d['task_id'], d['review_outcome'], [(x['v2_task_id'], x['result']['success']) for x in d['a']],
              d['b']['result']['success'])


if __name__ == '__main__':
    main()
