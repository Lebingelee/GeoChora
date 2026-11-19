"""Synthetic tests for the deterministic goal evaluator (no SimDataKit data required)."""
import json
import math
import re
from pathlib import Path

import numpy as np
import pytest

from validation.goals import SceneState, Trace, evaluate_task
from validation.goals import predicates as P
from validation.goals.predicates import Scene
from validation.inputs import TaskInputError, validate_task

TABLE = 0.75
VOCAB = {'version': 'scene-predicates/1.0.0', 'predicates': {}, 'process_predicates': {}}
CAVITY = {'x': [-0.153, 0.153], 'y': [0.052, 0.308], 'floor_z': 0.78, 'rim_z': 0.866}


def ball(name, color='red', d=0.04):
    return {'name': name, 'kind': 'ball', 'color': color, 'size_m': [d, d, d], 'initially_on': 'table',
            'initial_orientation': 'n/a'}


def brick(name, size, color='red', cls=None, initial='upright'):
    cls = cls or ('long' if max(size[:2]) >= 0.06 else 'mid' if max(size[:2]) >= 0.045 else 'small')
    return {'name': name, 'kind': 'brick', 'color': color, 'size_m': list(size) + [0.0228], 'size_class': cls,
            'initially_on': 'table', 'initial_orientation': initial}


MANIFEST = {
    'objects': [ball('b1'), ball('b2', 'blue'), ball('b3', 'green'),
                brick('long1', (0.068, 0.042), 'yellow'), brick('long2', (0.068, 0.042), 'yellow'),
                brick('long3', (0.068, 0.042), 'purple'), brick('sq1', (0.035, 0.035), 'red'),
                brick('mid1', (0.052, 0.039), 'red')],
    'drawers': [{'name': 'drawer_1', 'cavity_when_closed': CAVITY}],
}


def rot(axis, deg):
    h = math.radians(deg) / 2
    v = {'x': (1, 0, 0), 'y': (0, 1, 0), 'z': (0, 0, 1)}[axis]
    return [math.cos(h)] + [math.sin(h) * c for c in v]


def qmul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return [w1*w2 - x1*x2 - y1*y2 - z1*z2, w1*x2 + x1*w2 + y1*z2 - z1*y2,
            w1*y2 - x1*z2 + y1*w2 + z1*x2, w1*z2 + x1*y2 - y1*x2 + z1*w2]


def state(poses=None, openings=None, fingers=None, contacts=None, time=None):
    """poses: name -> (xyz, quat|None). Defaults: everything far away on the table."""
    pos, quat = {}, {}
    for i, o in enumerate(MANIFEST['objects']):
        z = TABLE + (0.02 if o['kind'] == 'ball' else 0.0)
        pos[o['name']] = [-0.4 + 0.1 * i, -0.4, z]
        if o['kind'] == 'brick':
            quat[o['name']] = [1, 0, 0, 0]
    for k, (p, q) in (poses or {}).items():
        pos[k] = p
        if q is not None:
            quat[k] = q
    return SceneState(positions=pos, orientations_wxyz=quat, drawer_openings=openings or {'drawer_1': 0.0},
                      finger_positions=fingers if fingers is not None else {'finger_left': [5, 5, 5], 'finger_right': [5, 5, 6]},
                      contacts=contacts, contacts_available=contacts is not None, time=time)


def scene(poses=None, initial=None, **kw):
    return Scene(MANIFEST, state(poses, **kw), initial)


def v(fn, s, *args):
    return fn(s, *args).value


def bz(x, y, z=TABLE, q=None):  # brick pose
    return ([x, y, z], q or [1, 0, 0, 0])


def bl(x, y, z=TABLE + 0.02):  # ball pose
    return ([x, y, z], None)


# ------------------------------------------------------------------ containers
@pytest.mark.parametrize('opening,open_v,closed_v', [
    (0.18, True, False), (0.14, True, False), (0.12, None, False), (0.10, False, False),
    (0.05, False, False), (0.03, False, False), (0.02, False, None), (0.01, False, True), (0.0, False, True)])
def test_open_closed_bands(opening, open_v, closed_v):
    s = scene(openings={'drawer_1': opening})
    assert v(P.Open, s, 'drawer_1') is open_v and v(P.Closed, s, 'drawer_1') is closed_v


def test_drawer_opening_missing_is_unknown():
    s = scene(openings={})
    s.state.drawer_openings.clear()
    assert P.Open(s, 'drawer_1').reason.startswith('drawer_opening_missing')


def test_in_geometric_bands_and_cavity_translation():
    inside = {'b1': bl(0.0, 0.18, 0.80)}
    assert v(P.In, scene(inside, openings={'drawer_1': 0.0}), 'b1', 'drawer_1') is True
    # cavity moves with the opening: same ball is outside when the drawer is opened 0.18
    assert v(P.In, scene(inside, openings={'drawer_1': 0.18}), 'b1', 'drawer_1') is False
    assert v(P.In, scene({'b1': bl(0.0, 0.0, 0.80)}, openings={'drawer_1': 0.18}), 'b1', 'drawer_1') is True
    # margin: x edge at 0.153; ball radius 0.02
    assert v(P.In, scene({'b1': bl(0.153 - 0.02 + 0.004, 0.18, 0.80)}), 'b1', 'drawer_1') is None
    assert v(P.In, scene({'b1': bl(0.153 - 0.02 + 0.007, 0.18, 0.80)}), 'b1', 'drawer_1') is False
    assert v(P.In, scene({'b1': bl(0.153 - 0.02 + 0.0015, 0.18, 0.80)}), 'b1', 'drawer_1') is True  # resting on wall
    assert v(P.In, scene({'b1': bl(0.153 - 0.02, 0.18, 0.80)}), 'b1', 'drawer_1') is True
    # height outside the rim band, or floating above the floor
    assert v(P.In, scene({'b1': bl(0.0, 0.18, 0.95)}), 'b1', 'drawer_1') is False
    assert v(P.In, scene({'b1': bl(0.0, 0.18, 0.84)}), 'b1', 'drawer_1') is False  # no load path


def test_in_basis_and_stacking_on_object_in_drawer():
    r = P.In(scene({'b1': bl(0.0, 0.18, 0.80)}), 'b1', 'drawer_1')
    assert r.basis == 'geometric'
    s = scene({'long1': bz(0.0, 0.18, 0.78), 'sq1': bz(0.0, 0.18, 0.78 + 0.0196)})
    assert v(P.In, s, 'sq1', 'drawer_1') is True   # rests on long1 which rests on the floor


def test_in_contact_path_excludes_robot():
    pose = {'b1': bl(0.0, 0.18, 0.80)}
    c = {frozenset(('b1', 'drawer_1'))}
    assert P.In(scene(pose, contacts=c), 'b1', 'drawer_1').value is True
    assert P.In(scene(pose, contacts=c), 'b1', 'drawer_1').basis == 'contact'
    assert v(P.In, scene(pose, contacts={frozenset(('b1', 'finger_left'))}), 'b1', 'drawer_1') is False
    chain = {frozenset(('b1', 'sq1')), frozenset(('sq1', 'drawer_1'))}
    assert v(P.In, scene({**pose, 'sq1': bz(0.0, 0.1, 0.78)}, contacts=chain), 'b1', 'drawer_1') is True


# ------------------------------------------------------------------ support
def test_on_table_geometric_and_contact():
    assert v(P.OnTable, scene({'b1': bl(0, 0)}), 'b1') is True
    assert v(P.OnTable, scene({'b1': bl(0, 0, 0.77 + 0.004)}), 'b1') is None
    assert v(P.OnTable, scene({'b1': bl(0, 0, 0.77 + 0.02)}), 'b1') is False
    assert P.OnTable(scene({'b1': bl(0, 0)}), 'b1').basis == 'geometric'
    assert v(P.OnTable, scene({'b1': bl(0, 0)}, contacts={frozenset(('b1', 'table'))}), 'b1') is True
    assert v(P.OnTable, scene({'b1': bl(0, 0)}, contacts=set()), 'b1') is False


def test_on_geometric_and_contact():
    top = {'long1': bz(0, 0), 'sq1': bz(0.005, 0.0, TABLE + 0.0196)}
    assert v(P.On, scene(top), 'sq1', 'long1') is True
    assert v(P.On, scene({'long1': bz(0, 0), 'sq1': bz(0.2, 0, TABLE + 0.0196)}), 'sq1', 'long1') is False
    assert v(P.On, scene({'long1': bz(0, 0), 'sq1': bz(0.0, 0, TABLE)}), 'sq1', 'long1') is False  # on table
    assert v(P.On, scene({'long1': bz(0, 0), 'sq1': bz(0.0, 0, TABLE + 0.0196)}, contacts={frozenset(('sq1', 'long1'))}),
             'sq1', 'long1') is True
    both = {frozenset(('sq1', 'long1')), frozenset(('sq1', 'table'))}
    assert v(P.On, scene(top, contacts=both), 'sq1', 'long1') is False


def test_released_bands_and_basis():
    pose = {'b1': bl(0, 0)}
    far = {'finger_left': [0.1, 0, 0.8], 'finger_right': [0.1, 0.01, 0.8]}
    assert v(P.Released, scene(pose, fingers=far), 'b1') is True
    assert v(P.Released, scene(pose, fingers={'finger_left': [0.035, 0, 0.77]}), 'b1') is None
    assert v(P.Released, scene(pose, fingers={'finger_left': [0.025, 0, 0.77]}), 'b1') is False
    assert v(P.Released, scene(pose, fingers={}), 'b1') is None
    assert v(P.Released, scene(pose, fingers=far, contacts={frozenset(('b1', 'finger_left'))}), 'b1') is False
    assert P.Released(scene(pose, fingers=far, contacts=set()), 'b1').basis.startswith('contact')
    assert v(P.AllReleased, scene(pose, fingers=far)) is True
    assert v(P.AllReleased, scene(pose, fingers={'finger_left': [0.025, 0, 0.77]})) is False


# ------------------------------------------------------------------ orientation
@pytest.mark.parametrize('deg,up,inv,side', [
    (0, True, False, False), (15, True, False, False), (20, None, False, False), (25, False, False, False),
    (90, False, False, True), (80, False, False, True), (70, False, False, None), (60, False, False, False),
    (180, False, True, False), (166, False, True, False), (160, False, None, False)])
def test_orientation_bands(deg, up, inv, side):
    s = scene({'long1': bz(0, 0, TABLE + 0.05, rot('x', deg))})
    assert (v(P.Upright, s, 'long1'), v(P.Inverted, s, 'long1'), v(P.OnSide, s, 'long1')) == (up, inv, side)


def test_orientation_requires_brick():
    assert P.Upright(scene(), 'b1').reason.startswith('not_a_brick')


# ------------------------------------------------------------------ planar relations
def test_near_apart_gap_bands_for_bricks_and_balls():
    # long1 half-length along x = 0.034; sq1 half = 0.0175 -> gap = dx - 0.0515
    for gap, near, apart in [(0.0, True, False), (0.002, True, False), (0.005, True, None), (0.03, True, True),
                             (0.045, None, True), (0.07, False, True)]:
        s = scene({'long1': bz(0, 0), 'sq1': bz(0.0515 + gap, 0)})
        assert (v(P.Near, s, 'long1', 'sq1'), v(P.Apart, s, 'long1', 'sq1')) == (near, apart), gap
    s = scene({'b1': bl(0, 0), 'b2': bl(0.04 + 0.05, 0)})
    assert v(P.Near, s, 'b1', 'b2') is None and v(P.Apart, s, 'b1', 'b2') is True
    s = scene({'b1': bl(0, 0), 'long1': bz(0.02 + 0.034 + 0.02, 0)})
    assert P.Near(s, 'b1', 'long1').measurements['gap_m']['measure'] == pytest.approx(0.02)


def test_near_uses_rotated_footprint():
    s = scene({'long1': bz(0, 0, q=rot('z', 90)), 'sq1': bz(0.021 + 0.0175 + 0.001, 0)})
    # rotated long1 extends only 0.021 along x
    assert P.Near(s, 'long1', 'sq1').measurements['gap_m']['measure'] == pytest.approx(0.001, abs=1e-6)


@pytest.mark.parametrize('deg,par,perp', [(0, True, False), (10, True, False), (15, None, False),
                                         (25, False, False), (45, False, False), (70, False, None),
                                         (80, False, True), (90, False, True), (180, True, False)])
def test_parallel_perpendicular_bands(deg, par, perp):
    s = scene({'long1': bz(0, 0), 'long2': bz(0.1, 0, q=rot('z', deg))})
    assert (v(P.Parallel, s, 'long1', 'long2'), v(P.Perpendicular, s, 'long1', 'long2')) == (par, perp)


def test_perpendicular_to_drawer_front_and_square_bricks():
    s = scene({'long1': bz(0, 0, q=rot('z', 90)), 'sq1': bz(0.1, 0)})
    assert v(P.Perpendicular, s, 'long1', 'drawer_front') is True
    assert v(P.Perpendicular, scene({'long1': bz(0, 0)}), 'long1', 'drawer_front') is False
    assert v(P.Parallel, s, 'long1', 'sq1') is False   # square brick: no long edge
    assert 'not_elongated' in P.Parallel(s, 'long1', 'sq1').measurements['applies_to']


def row_scene(ys, names=('long1', 'long2', 'long3'), q=None):
    return scene({n: bz(0.0, y, q=q or rot('z', 90)) for n, y in zip(names, ys)})


def test_row_bands_order_and_touching():
    # rotated long bricks: footprint 0.042 wide in x, 0.068 along y; narrowest width 0.042
    names = ['long1', 'long2', 'long3']
    ok = scene({'long1': bz(0.0, 0.0), 'long2': bz(0.0, 0.1), 'long3': bz(0.0, 0.2)})
    assert v(P.Row, ok, names) is True
    assert v(P.Row, ok, names[::-1]) is True          # either direction
    assert v(P.Row, ok, ['long2', 'long1', 'long3']) is False   # order violated
    off = lambda dx: scene({'long1': bz(0, 0), 'long2': bz(dx, 0.1), 'long3': bz(0, 0.2)})
    assert v(P.Row, off(0.0), names) is True
    assert v(P.Row, off(0.03), names) is None         # residual between 0.25 and 0.75 widths
    assert v(P.Row, off(0.2), names) is False
    touching = scene({'long1': bz(0.0, 0.0), 'long2': bz(0.0, 0.04), 'long3': bz(0.0, 0.2)})
    assert v(P.Row, touching, names) is False
    assert P.Row(ok, names).measurements['order_holds'] is True


def test_between_bands():
    def at(x, y):
        return scene({'b1': bl(x, y), 'long1': bz(-0.1, 0), 'long2': bz(0.1, 0)})
    assert v(P.Between, at(0.0, 0.0), 'b1', 'long1', 'long2') is True
    assert v(P.Between, at(0.0, 0.02), 'b1', 'long1', 'long2') is True
    assert v(P.Between, at(0.0, 0.045), 'b1', 'long1', 'long2') is None
    assert v(P.Between, at(0.0, 0.07), 'b1', 'long1', 'long2') is False
    assert v(P.Between, at(-0.095, 0.0), 'b1', 'long1', 'long2') is None   # t=0.025 -> between bands
    assert v(P.Between, at(-0.15, 0.0), 'b1', 'long1', 'long2') is False   # t<0
    assert v(P.Between, at(0.15, 0.0), 'b1', 'long1', 'long2') is False


def test_grouped_bands():
    # group 1: balls b1,b2 (d=0.04) with gap w_gap between them; group 2: two bricks 0.0175 apart edge to edge
    def g(between, w_gap=0.0):
        x2 = 0.04 + w_gap
        x3 = x2 + 0.02 + between + 0.034          # long1 centre; its half length is 0.034
        return scene({'b1': bl(0, 0), 'b2': bl(x2, 0), 'long1': bz(x3, 0),
                      'sq1': bz(x3 + 0.034 + 0.0175 + 0.0, 0)})
    args = (['b1', 'b2'], ['long1', 'sq1'])
    assert v(P.Grouped, g(0.1), *args) is True                     # g=0.1 >= 2w (w=0) and >= 0.05
    assert v(P.Grouped, g(0.03), *args) is None                    # 0.02 < g < 0.05
    assert v(P.Grouped, g(0.015), *args) is False                  # g <= 0.02
    assert v(P.Grouped, g(0.2, w_gap=0.04), *args) is True         # w=0.04 (<=0.06), g=0.2 >= 2w
    assert v(P.Grouped, g(0.07, w_gap=0.04), *args) is None        # g < 2w
    assert v(P.Grouped, g(0.04, w_gap=0.05), *args) is False       # g <= w
    assert v(P.Grouped, g(0.5, w_gap=0.07), *args) is None         # w in (0.06, 0.10)
    assert v(P.Grouped, g(0.5, w_gap=0.12), *args) is False        # w >= 0.10 even though g is large
    # MST: a chain whose largest edge is w counts, not the end-to-end span
    chain = scene({'b1': bl(0, 0), 'b2': bl(0.06, 0), 'b3': bl(0.12, 0), 'long1': bz(0.6, 0)})
    assert v(P.Grouped, chain, ['b1', 'b2', 'b3'], ['long1']) is True
    # singleton groups have w = 0
    assert v(P.Grouped, scene({'b1': bl(0, 0), 'b2': bl(0.2, 0)}), ['b1'], ['b2']) is True


# ------------------------------------------------------------------ displacement
def test_unmoved_and_at_initial_position():
    init = state({'long1': bz(0, 0), 'long2': bz(0.3, 0)})
    for dx, rot_deg, expect in [(0, 0, True), (0.01, 0, True), (0.015, 0, None), (0.02, 0, False),
                                (0, 10, True), (0, 15, None), (0, 22, False)]:
        s = Scene(MANIFEST, state({'long1': bz(dx, 0, q=rot('z', rot_deg))}), init)
        assert v(P.Unmoved, s, 'long1') is expect, (dx, rot_deg)
    assert P.Unmoved(Scene(MANIFEST, state(), None), 'long1').reason == 'initial_state_missing'
    for dist, expect in [(0.0, True), (0.03, True), (0.04, None), (0.055, False)]:
        s = Scene(MANIFEST, state({'long1': bz(0.3 + dist, 0)}), init)
        assert v(P.AtInitialPositionOf, s, 'long1', 'long2') is expect, dist


# ------------------------------------------------------------------ evaluation: bind, quantifiers
def task(goal, bind=None, process=None):
    t = {'goal': goal}
    if bind:
        t['bind'] = bind
    if process:
        t['process'] = process
    return {'task_id': 'x', 'truth': t}


def A(pred, *args):
    return {'pred': pred, 'args': list(args)}


def evaluate(row, final, initial=None, trace=None):
    return evaluate_task(row, MANIFEST, VOCAB, final, initial or state(), trace)


FAR = {'finger_left': [5, 5, 5], 'finger_right': [5, 5, 6]}


def test_existential_bind_true_false_unknown():
    bind = {'?b': {'kind': 'ball'}}
    goal = {'all': [A('In', '?b', 'drawer_1')]}
    final = state({'b2': bl(0, 0.18, 0.80)})
    r = evaluate(task(goal, bind), final)
    assert r['goal'] is True and r['assignment'] == {'?b': 'b2'}
    assert evaluate(task(goal, bind), state())['goal'] is False
    # unknown: b1 margin is in the unresolved band, others fail
    r = evaluate(task(goal, bind), state({'b1': bl(0.153 - 0.02 + 0.004, 0.18, 0.80)}))
    assert r['goal'] is None


def test_variables_distinct_from_each_other_and_from_named_objects():
    bind = {'?a': {'kind': 'brick', 'size_class': 'long', 'color': 'yellow'},
            '?b': {'kind': 'brick', 'size_class': 'long', 'color': 'yellow'}}
    goal = {'all': [A('Near', '?a', '?b')]}
    r = evaluate(task(goal, bind), state({'long1': bz(0, 0), 'long2': bz(0.3, 0)}))
    assert r['assignments']['evaluated'] == 2 and r['goal'] is False   # (long1,long2),(long2,long1) only
    # a variable may not alias a named object: long1 is named, so ?a can only be long2
    goal = {'all': [A('OnTable', 'long1'), A('OnTable', '?a')]}
    r = evaluate(task(goal, {'?a': {'kind': 'brick', 'color': 'yellow'}}), state())
    assert r['assignments']['evaluated'] == 1 and r['assignment'] == {'?a': 'long2'}
    r = evaluate(task({'all': [A('Near', 'long1', '?a')]}, {'?a': {'kind': 'brick', 'color': 'yellow'}}),
                 state({'long1': bz(0, 0), 'long2': bz(0.0, 0.0)}))   # alias would be Near; distinctness blocks it
    assert r['assignments']['evaluated'] == 1


def test_distinct_variables_cannot_reuse_one_object():
    bind = {'?a': {'kind': 'ball', 'color': 'red'}, '?b': {'kind': 'ball', 'color': 'red'}}
    r = evaluate(task({'all': [A('OnTable', '?a'), A('OnTable', '?b')]}, bind), state())
    assert r['goal'] is None and r['goal_reason'] == 'no_candidate_assignment'


def test_kleene_combinators_and_implicit_all_released():
    final = state({'b1': bl(0, 0)})
    assert evaluate(task({'any': [A('OnTable', 'b2'), A('Closed', 'drawer_1')]}), final)['goal'] is True
    assert evaluate(task({'not': A('Closed', 'drawer_1')}), final)['goal'] is False
    unk = state(openings={'drawer_1': 0.02})
    assert evaluate(task({'all': [A('Closed', 'drawer_1'), A('OnTable', 'b1')]}), unk)['goal'] is None
    assert evaluate(task({'all': [A('Open', 'drawer_1'), A('Closed', 'drawer_1')]}), unk)['goal'] is False
    held = state({'b1': bl(0, 0)}, fingers={'finger_left': [0.025, 0, 0.77], 'finger_right': [0.0, -0.025, 0.77]})
    r = evaluate(task({'all': [A('OnTable', 'b1')]}), held)
    assert r['goal'] is False and r['all_released']['value'] is False
    assert evaluate(task({'all': [A('OnTable', 'b1')]}), state({'b1': bl(0, 0)}, fingers={}))['goal'] is None


def test_unknown_predicate_and_vocabulary_version_rejected():
    with pytest.raises(ValueError, match='unknown predicate'):
        evaluate(task({'all': [A('Teleported', 'b1')]}), state())
    with pytest.raises(ValueError, match='unsupported vocabulary'):
        evaluate_task(task({'all': []}), MANIFEST, {'version': 'other/1'}, state(), state())


def test_process_requires_trace():
    row = task({'all': [A('OnTable', 'b1')]}, process=[{'pred': 'Never', 'args': ['b2']}])
    r = evaluate(row, state({'b1': bl(0, 0)}))
    assert r['goal'] is True and r['success'] is None
    assert r['process'][0]['value'] is None and r['process'][0]['reason'] == 'trace_required'
    r = evaluate(task({'all': [A('Closed', 'drawer_1'), A('Open', 'drawer_1')]}, process=row['truth']['process']), state())
    assert r['success'] is False   # false goal wins over unknown process


# ------------------------------------------------------------------ traces
def trace_of(states, complete=True, dt=0.1):
    for i, s in enumerate(states):
        s.time = round(i * dt, 6)
    return Trace(states, recording_complete=complete)


def steady(n=12, **kw):
    return [state(**kw) for _ in range(n)]


def test_sequence_ordered_witness():
    seq = {'pred': 'Sequence', 'args': [{'all': [A('Open', 'drawer_1')]}, {'all': [A('Closed', 'drawer_1')]}]}
    row = task({'all': [A('Closed', 'drawer_1')]}, process=[seq])
    states = [state(openings={'drawer_1': o}) for o in [0, 0, 0.1, 0.18, 0.18, 0.1, 0.0, 0.0] + [0.0] * 8]
    tr = trace_of(states)
    r = evaluate(row, states[-1], states[0], tr)
    assert r['process'][0]['value'] is True and r['success'] is True
    assert len(r['process'][0]['measurements']['witness_times_s']) == 2
    # wrong order: closed first then opened never closes again -> false on complete record
    states2 = [state(openings={'drawer_1': o}) for o in [0.0] * 6 + [0.18] * 6]
    r = evaluate(task({'all': [A('Open', 'drawer_1')]}, process=[seq]), states2[-1], states2[0], trace_of(states2))
    assert r['goal'] is True and r['process'][0]['value'] is False and r['success'] is False
    # terminal-state check of the last stage: Open->Closed cannot hold when the record ends open
    assert r['process'][0]['measurements']['last_stage_on_terminal_state'] is False
    # never opened, ends closed: complete record -> false; incomplete record cannot confirm absence
    states3 = [state(openings={'drawer_1': 0.0}) for _ in range(12)]
    row3 = task({'all': [A('Closed', 'drawer_1')]}, process=[seq])
    r = evaluate(row3, states3[-1], states3[0], trace_of(states3))
    assert r['process'][0]['value'] is False
    r = evaluate(row3, states3[-1], states3[0], trace_of(states3, complete=False))
    assert r['process'][0]['value'] is None and r['process'][0]['reason'] == 'recording_incomplete'


def test_sequence_gap_and_unknown_samples():
    seq = {'pred': 'Sequence', 'args': [{'all': [A('Open', 'drawer_1')]}, {'all': [A('Closed', 'drawer_1')]}]}
    states = [state(openings={'drawer_1': o}) for o in [0.0, 0.18, 0.0]]
    tr = trace_of(states, dt=1.0)   # gaps larger than the sample-gap limit
    r = evaluate(task({'all': [A('Closed', 'drawer_1')]}, process=[seq]), states[-1], states[0], tr)
    assert r['process'][0]['value'] is None and r['process'][0]['reason'] == 'sample_gap'


def test_never_needs_contacts():
    row = task({'all': [A('Closed', 'drawer_1')]}, process=[{'pred': 'Never', 'args': ['b2']}])
    clean = steady(contacts=set())
    r = evaluate(row, clean[-1], clean[0], trace_of(clean))
    assert r['process'][0]['value'] is True
    dirty = steady(contacts=set())
    dirty[4] = state(contacts={frozenset(('b2', 'finger_left'))})
    r = evaluate(row, dirty[-1], dirty[0], trace_of(dirty))
    assert r['process'][0]['value'] is False and r['process'][0]['measurements']['first_contact_time_s'] == pytest.approx(0.4)
    nocontact = steady()
    r = evaluate(row, nocontact[-1], nocontact[0], trace_of(nocontact))
    assert r['process'][0]['value'] is None and r['process'][0]['reason'] == 'contacts_unavailable'
    r = evaluate(row, clean[-1], clean[0], trace_of(clean, complete=False))
    assert r['process'][0]['value'] is None


def test_while_grasped_contact_basis():
    both = {frozenset(('b1', 'finger_left')), frozenset(('b1', 'finger_right'))}
    row = task({'all': []}, process=[{'pred': 'WhileGrasped', 'args': ['long1', 'Inverted']}])
    both = {frozenset(('long1', 'finger_left')), frozenset(('long1', 'finger_right'))}
    inv = {'long1': bz(0, 0, TABLE + 0.1, rot('x', 180))}
    up = {'long1': bz(0, 0, TABLE + 0.1)}
    good = [state(inv, contacts=set())] + [state(inv, contacts=both) for _ in range(5)] + [state(up, contacts=set()) for _ in range(4)]
    r = evaluate(row, good[-1], good[0], trace_of(good))
    assert r['process'][0]['value'] is True      # upright only while not grasped
    bad = [state(inv, contacts=both) for _ in range(3)] + [state(up, contacts=both)] + [state(up, contacts=set()) for _ in range(4)]
    assert evaluate(row, bad[-1], bad[0], trace_of(bad))['process'][0]['value'] is False
    never = [state(up, contacts=set()) for _ in range(6)]
    r = evaluate(row, never[-1], never[0], trace_of(never))
    assert r['process'][0]['value'] is False and r['process'][0]['reason'] == 'never_grasped'
    r = evaluate(row, never[-1], never[0], trace_of(never, complete=False))
    assert r['process'][0]['value'] is None


def test_while_grasped_geometric_fallback_basis():
    row = task({'all': []}, process=[{'pred': 'WhileGrasped', 'args': ['long1', 'Upright']}])
    held = {'finger_left': [-0.01, -0.01, TABLE + 0.05], 'finger_right': [0.01, -0.01, TABLE + 0.05]}
    states = [state({'long1': bz(0, 0)}, fingers=FAR) for _ in range(3)] + \
             [state({'long1': bz(0, 0, TABLE + 0.05, rot('x', 90))}, fingers=held) for _ in range(2)] + \
             [state({'long1': bz(0, 0)}, fingers=FAR) for _ in range(3)]
    r = evaluate(row, states[-1], states[0], trace_of(states))
    assert r['process'][0]['value'] is False                       # tilted while both fingers hold it
    assert 'geometric' in r['process'][0]['basis']


def test_not_settled_makes_terminal_goal_unknown():
    row = task({'all': [A('OnTable', 'b1')]})
    moving = [state({'b1': bl(0.01 * i, 0)}) for i in range(12)]
    r = evaluate(row, moving[-1], moving[0], trace_of(moving))
    assert r['goal'] is None and r['goal_reason'] == 'not_settled' and r['goal_if_settled'] is True
    rest = steady()
    r = evaluate(row, rest[-1], rest[0], trace_of(rest, dt=0.1))
    assert r['goal'] is True and r['settle']['settled'] is True


# ------------------------------------------------------------------ inputs and vocabulary pins
def v11():
    from validation.tests.test_task_inputs import task as fixture
    return fixture()


def test_inputs_accept_1_1_0_unchanged_and_reject_unknown():
    t = v11()
    assert t['schema_version'] == 'low-detail-task/1.1.0'
    assert validate_task(t) == t
    t['schema_version'] = 'low-detail-task/1.3.0'
    with pytest.raises(TaskInputError, match='/schema_version'):
        validate_task(t)


SIMDATAKIT = Path(__file__).resolve().parents[3] / 'SimDataKit'


@pytest.mark.skipif(not (SIMDATAKIT / 'workspace/franka-scene-50-v2/tasks.jsonl').exists(), reason='SimDataKit not checked out')
def test_real_1_2_0_rows_validate():
    rows = [json.loads(line) for line in (SIMDATAKIT / 'workspace/franka-scene-50-v2/tasks.jsonl').read_text(encoding='utf-8').splitlines()]
    assert rows and all(r['schema_version'] == 'low-detail-task/1.2.0' for r in rows)
    for r in rows:
        assert validate_task(r)['truth']['goal']


@pytest.mark.skipif(not (SIMDATAKIT / 'catalog/profiles/vocabularies/scene-predicates-v1.yaml').exists(), reason='vocabulary absent')
def test_thresholds_match_vocabulary_file():
    text = (SIMDATAKIT / 'catalog/profiles/vocabularies/scene-predicates-v1.yaml').read_text(encoding='utf-8')
    numbers = {float(x) for x in re.findall(r'(?<![\w.])-?\d+(?:\.\d+)?', text)}
    bands = P.Bands()
    for name, value in vars(bands).items():
        for x in (value if isinstance(value, tuple) else (value,)):
            assert any(abs(x - n) < 1e-12 for n in numbers), (name, x)
    from validation.goals.evaluate import load_vocabulary
    vocab = load_vocabulary(SIMDATAKIT / 'catalog/profiles/vocabularies/scene-predicates-v1.yaml')
    assert vocab['version'] == P.VOCABULARY_VERSION
    assert set(vocab['predicates']) <= set(P.TERMINAL_PREDICATES)
