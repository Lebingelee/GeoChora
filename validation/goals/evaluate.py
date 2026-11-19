"""Vocabulary-agnostic goal engine for `low-detail-task/1.2.0`-style goal nodes.

The engine owns the goal grammar (all/any/not, predicate atoms, ?variables), Kleene combination,
existential bind semantics (pairwise distinct variables, also distinct from explicitly named
objects), the generic `Sequence` process combinator, best-assignment choice and result assembly.
Predicate meaning, the evaluation-time rule, implicit goal terms and the state adapter come from the
vocabulary plugin the goal declares (`validation.goals.vocabulary`); scene-predicates/1.0.0 is
`validation.goals.vocabularies.scene_predicates`.
"""
from __future__ import annotations

from itertools import chain
from pathlib import Path

from validation.goals.tri import Tri, k_and, k_not, k_or, unknown
from validation.goals.vocabulary import ENGINE_PROCESS_PREDICATES, resolve
from validation.goals.vocabularies.scene_predicates import BIND_FIELDS, EvalPolicy  # noqa: F401  (compat re-export)
from validation.sampling import MeasurementPolicy, ordered_witness

# Judgement basis of a result (reported separately in statistics, never pooled).
GOAL_BASES = ('dataset_goal', 'native_converted', 'llm_drafted_reviewed', 'terminal_review')


def load_vocabulary(path):
    import yaml
    return yaml.safe_load(Path(path).read_text(encoding='utf-8'))


def _names_in(node, objects, out):
    if isinstance(node, dict):
        if 'pred' in node:
            for arg in node.get('args', []):
                _names_in(arg, objects, out)
        else:
            for child in (node.get('all') or node.get('any') or ([node['not']] if 'not' in node else [])):
                _names_in(child, objects, out)
    elif isinstance(node, list):
        for item in node:
            _names_in(item, objects, out)
    elif isinstance(node, str) and node in objects:
        out.add(node)


def assignments(bind, manifest, explicit, limit, fields=BIND_FIELDS):
    """All pairwise-distinct assignments, none using an explicitly named object."""
    names = list(bind)
    candidates = []
    for var in names:
        flt = bind[var]
        unknown_keys = set(flt) - set(fields)
        if unknown_keys:
            raise ValueError(f'unsupported bind filter keys for {var}: {sorted(unknown_keys)}')
        candidates.append([o['name'] for o in manifest['objects']
                           if o['name'] not in explicit and all(o.get(k) == v for k, v in flt.items())])
    result, current = [], []

    def extend(i):
        if len(result) > limit:
            raise ValueError('too many bind assignments')
        if i == len(names):
            result.append(dict(zip(names, current)))
            return
        for c in candidates[i]:
            if c not in current:
                current.append(c)
                extend(i + 1)
                current.pop()
    extend(0)
    return result


def _resolve(arg, assignment):
    if isinstance(arg, list):
        return [_resolve(a, assignment) for a in arg]
    if isinstance(arg, str) and arg.startswith('?'):
        if arg not in assignment:
            raise ValueError(f'unbound variable {arg}')
        return assignment[arg]
    return arg


def _freeze(x):
    return tuple(_freeze(i) for i in x) if isinstance(x, list) else x


class _Frame:
    """One adapted state (vocabulary state view) plus the engine's per-state atom memo."""

    def __init__(self, vocab, state):
        self.vocab, self.state, self.memo = vocab, state, {}


def _atom(frame, node, assignment):
    pred, raw = node['pred'], node.get('args', [])
    vocab = frame.vocab
    if pred in ENGINE_PROCESS_PREDICATES or pred in vocab.process_predicates:
        raise ValueError(f'process predicate {pred} cannot appear inside a goal node')
    if pred not in vocab.predicates:
        raise ValueError(f'unknown predicate {pred!r}')
    fn, arity = vocab.predicates[pred]
    args = _resolve(raw, assignment)
    if arity is not None and len(args) != arity:
        raise ValueError(f'{pred} expects {arity} arguments, got {len(args)}')
    key = (pred, _freeze(args))
    if key not in frame.memo:
        frame.memo[key] = fn(frame.state, *args)
    return frame.memo[key], args


def eval_node(frame, node, assignment, tree=False):
    """-> (Tri, tree|None, number of true atoms)."""
    if 'pred' in node:
        tri, args = _atom(frame, node, assignment)
        t = {'pred': node['pred'], 'args': node.get('args', []), 'resolved': args, **tri.to_dict()} if tree else None
        return tri, t, int(tri.value is True)
    op = next(k for k in ('all', 'any', 'not') if k in node)
    kids = [node['not']] if op == 'not' else node[op]
    parts = [eval_node(frame, k, assignment, tree) for k in kids]
    tris = [p[0] for p in parts]
    out = k_and(tris) if op == 'all' else k_or(tris) if op == 'any' else k_not(tris[0])
    t = None
    if tree:
        t = {'op': op, 'value': out.value, 'children': [p[1] for p in parts]}
        if out.reason:
            t['reason'] = out.reason
    return Tri(out.value, out.reason), t, sum(p[2] for p in parts)


class _TraceView:
    """Per-sample adapted-state cache for process evaluation (the `view` given to process predicates)."""

    def __init__(self, vocab, trace, manifest, initial, policy):
        self.vocab, self.trace, self.manifest, self.initial, self.policy = vocab, trace, manifest, initial, policy
        self.times = trace.times
        self._frames = {}

    def frame(self, i):
        if i not in self._frames:
            self._frames[i] = _Frame(self.vocab, self.vocab.state_adapter(
                self.manifest, self.trace.samples[i], self.initial, self.policy))
        return self._frames[i]

    def state(self, i):
        return self.frame(i).state

    def __len__(self):
        return len(self.trace.samples)


def _process_atom(atom, view, final_scene, assignment, policy):
    pred, raw = atom['pred'], atom.get('args', [])
    args = _resolve(raw, assignment)
    if pred == 'Sequence':
        return _sequence(raw, view, final_scene, assignment, policy)
    if pred in view.vocab.process_predicates:
        return view.vocab.process_predicates[pred](view, args, policy)
    raise ValueError(f'unknown process predicate {pred!r}')


def _from_witness(result):
    return Tri(result.value if result.status == 'available' else None,
               result.reason if result.status != 'available' else None)


def _sequence(stages, view, final_scene, assignment, policy):
    if not stages:
        raise ValueError('Sequence needs at least one stage')
    if len(view) == 0:
        return unknown('trace_empty')
    names = [f'stage{k}' for k in range(len(stages))]
    series = {n: [eval_node(view.frame(i), st, assignment)[0].value for i in range(len(view))]
              for n, st in zip(names, stages)}
    try:
        witness, indexes = ordered_witness(view.times, series, names,
                                           policy=MeasurementPolicy(max_sample_gap_s=policy.max_sample_gap_s),
                                           recording_complete=view.trace.recording_complete)
    except ValueError as error:
        return unknown(f'trace_invalid:{error}')
    witness = _from_witness(witness)
    last, _, _ = eval_node(final_scene, stages[-1], assignment)
    out = k_and([witness, last])
    return Tri(out.value, out.reason,
               {'witness_times_s': [float(view.times[i]) for i in indexes] if indexes else [],
                'stages': len(stages), 'last_stage_on_terminal_state': last.value}, 'trace')


def _rank(tri):
    return 2 if tri.value is True else 1 if tri.value is None else 0


def evaluate_task(task_row, manifest, vocabulary, final_state, initial_state, trace=None, policy=None,
                  basis='dataset_goal'):
    """Evaluate one task row. Returns a JSON-ready dict (see keys below).

    vocabulary  the declared vocabulary document ({'version': ...}); refused unless a plugin is registered.
    policy      vocabulary policy object (default: the plugin's default policy).
    basis       judgement basis, one of GOAL_BASES (reported as `goal_basis`).

    goal      True/False/None: implicit terms AND the existential goal on the terminal state chosen by
              the vocabulary's `when` rule (scene-predicates: AllReleased, settled final state).
    success   goal AND all process atoms (None propagates; a definite False wins).
    process   per-atom results for the chosen assignment (value None/'trace_required' without a trace).
    """
    vocab = resolve(vocabulary)
    if basis not in GOAL_BASES:
        raise ValueError(f'unknown goal basis {basis!r}; expected one of {list(GOAL_BASES)}')
    if policy is None:
        policy = vocab.default_policy()
    truth = task_row['truth']
    goal_node, bind = truth['goal'], truth.get('bind') or {}
    process_atoms = truth.get('process') or []
    objects = {o['name'] for o in manifest['objects']}
    explicit = set()
    _names_in(goal_node, objects, explicit)
    for atom in process_atoms:
        _names_in(atom, objects, explicit)
    asgs = assignments(bind, manifest, explicit, policy.max_assignments, vocab.bind_fields) if bind else [{}]

    final = _Frame(vocab, vocab.state_adapter(manifest, final_state, initial_state, policy))
    implicit = [(key, vocab.predicates[pred][0](final.state)) for key, pred in vocab.implicit_terms]
    view = _TraceView(vocab, trace, manifest, initial_state, policy) if trace is not None else None

    when = vocab.evaluate_when(trace, final_state, objects, policy)

    rows = []
    for asg in asgs:
        goal_tri, _, count = eval_node(final, goal_node, asg)
        rows.append({'asg': asg, 'goal': goal_tri, 'count': count, 'process': None})

    process_unknown = Tri(None, 'trace_required')
    for row in rows:
        if not process_atoms:
            row['process'], row['success'] = [], row['goal']
        elif view is None:
            row['process'] = [process_unknown] * len(process_atoms)
            row['success'] = k_and([row['goal']] + row['process'])
        elif row['goal'].value is False:
            row['success'] = row['goal']          # process cannot rescue a false goal; skipped for cost
        else:
            row['process'] = [_process_atom(a, view, final, row['asg'], policy) for a in process_atoms]
            row['success'] = k_and([row['goal']] + row['process'])

    def pick(key):
        return max(rows, key=lambda r: (_rank(r[key]), r['count']), default=None)

    def existential(key):
        if not rows:
            return Tri(None, 'no_candidate_assignment')
        vals = [r[key] for r in rows]
        return k_or(vals)

    best = pick('success')
    goal_exist = existential('goal')
    implicit_tris = [t for _, t in implicit]
    goal = k_and(implicit_tris + [goal_exist])
    success_exist = k_and(implicit_tris + [existential('success')])

    notes = list(when.notes)
    blocked = when.blocked_reason is not None
    result_goal, result_success = goal, success_exist
    if blocked:
        result_goal = Tri(None, when.blocked_reason)
        proc = [t for r in ([best] if best else []) for t in (r['process'] or [])]
        result_success = k_and([result_goal] + proc)

    out = {
        'schema': 'goal-evaluation/1',
        'vocabulary': vocab.version,
        'goal_basis': basis,
        'task_id': task_row.get('task_id'),
        'success': result_success.value,
        'success_reason': result_success.reason,
        'goal': result_goal.value,
        'goal_reason': result_goal.reason,
        'goal_if_settled': goal.value if blocked else None,
        **{key: t.to_dict() for key, t in implicit},
        'assignment': best['asg'] if best else None,
        'assignments': {'evaluated': len(rows),
                        'goal_true': sum(r['goal'].value is True for r in rows),
                        'goal_unknown': sum(r['goal'].value is None for r in rows)},
        'settle': when.report,
        'basis': {'notes': notes},
    }
    if best is not None:
        _, tree, _ = eval_node(final, goal_node, best['asg'], tree=True)
        out['goal_tree'] = tree
        out['atoms'] = list(_flatten(tree))
        procs = best['process']
        if procs is None:  # skipped because the goal was false for the chosen (best) assignment
            procs = [Tri(None, 'skipped_goal_false')] * len(process_atoms)
        out['process'] = [{'pred': a['pred'], 'args': a.get('args', []), **t.to_dict()}
                          for a, t in zip(process_atoms, procs)]
    else:
        out['goal_tree'], out['atoms'] = None, []
        out['process'] = [{'pred': a['pred'], 'args': a.get('args', []), 'value': None,
                           'reason': 'no_candidate_assignment'} for a in process_atoms]
    for item in chain(out['atoms'], out['process'], [out[key] for key, _ in implicit]):
        if item.get('basis'):
            out['basis'].setdefault('support_and_evidence', [])
            if item['basis'] not in out['basis']['support_and_evidence']:
                out['basis']['support_and_evidence'].append(item['basis'])
    if view is None and process_atoms:
        notes.append('process atoms need a trace (reason trace_required)')
    return out


def _flatten(tree):
    if tree is None:
        return
    if 'children' in tree:
        for c in tree['children']:
            yield from _flatten(c)
    else:
        yield tree
