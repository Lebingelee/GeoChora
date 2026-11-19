"""One function per scene-predicates/1.0.0 predicate, returning a three-valued Tri.

Thresholds in `Bands` are the vocabulary's pass/fail numbers. `Fallbacks` holds the few
numbers the vocabulary leaves open for geometric (non-contact) evidence; they are reported
in every result's `basis` and are NOT vocabulary values.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
import math

import numpy as np

from validation.goals.tri import Tri, _clean, k_and, k_not, k_or, unknown  # noqa: F401  (re-exported)
from validation.goals.shapes import (
    Body, MissingEvidence, footprint_clearance_in_rect, footprint_gap, point_footprint_margin)

VOCABULARY_VERSION = 'scene-predicates/1.0.0'
ROBOT_BODIES = frozenset({'robot', 'hand', 'finger_left', 'finger_right'})


@dataclass(frozen=True)
class Bands:
    """(pass, fail) pairs copied from scene-predicates-v1.yaml."""
    open_opening: tuple = (0.14, 0.10)           # >= pass, <= fail
    closed_opening: tuple = (0.01, 0.03)         # <= pass, >= fail
    in_margin: tuple = (-0.002, -0.006)           # >= pass, <= fail
    released_clearance: tuple = (0.001, 0.0)     # >= pass; fail = finger contact
    orient_angle_deg: tuple = (15.0, 25.0)       # <= pass, >= fail
    near_gap: tuple = (0.03, 0.06)               # <= pass, >= fail
    apart_gap: tuple = (0.01, 0.003)             # >= pass, <= fail
    parallel_deg: tuple = (10.0, 20.0)           # <= pass, >= fail (also Perpendicular)
    parallel_min_ratio: float = 1.25
    row_residual_widths: tuple = (0.25, 0.75)    # <= pass, >= fail
    between_t: tuple = (0.15, 0.85)              # pass interval; fail t<=0 or t>=1
    between_d: tuple = (0.03, 0.06)              # <= pass, >= fail
    grouped_ratio: float = 2.0                   # pass g >= ratio*w, fail g <= w
    grouped_gap: tuple = (0.05, 0.02)            # pass g >= 0.05, fail g <= 0.02
    grouped_w: tuple = (0.06, 0.10)              # pass w <= 0.06, fail w >= 0.10
    unmoved_translation: tuple = (0.01, 0.02)    # <= pass, >= fail
    unmoved_rotation_deg: tuple = (10.0, 20.0)   # <= pass, >= fail
    at_initial: tuple = (0.03, 0.05)             # <= pass, >= fail
    support_within_m: float = 0.003              # vocabulary: lowest point within 0.003 above surface


@dataclass(frozen=True)
class Fallbacks:
    """Choices for geometric evidence where the vocabulary is silent (reported as basis)."""
    table_top_z: float = 0.750
    support_fail_above_m: float = 0.006       # lowest point this far above the surface: not supported
    support_max_penetration_m: float = 0.006  # allows stud interlock/settling; deeper is unknown
    centre_on_surface_fail_m: float = 0.003   # centre this far outside the support footprint: fails
    finger_envelope_pass_m: float = 0.020     # finger link-origin clearance treated as released
    finger_envelope_fail_m: float = 0.010     # at or inside this the finger origin counts as touching
    grasp_pass_m: float = 0.015               # both finger origins within -> geometric 'grasped'
    grasp_fail_m: float = 0.030               # a finger origin beyond -> not grasped
    allow_geometric_grasp: bool = True


def _band(x, good, bad, mode, unit=None):
    """mode 'le': pass x<=good, fail x>=bad.  mode 'ge': pass x>=good, fail x<=bad."""
    if x is None or not math.isfinite(x):
        return None, {'measure': None}
    if mode == 'le':
        value = True if x <= good else False if x >= bad else None
    else:
        value = True if x >= good else False if x <= bad else None
    span = abs(good - bad) or 1.0
    info = {'measure': float(x), 'pass': good, 'fail': bad, 'mode': mode,
            'norm_margin': min(abs(x - good), abs(x - bad)) / span}
    if unit:
        info['unit'] = unit
    return value, info


def _tri_band(x, good, bad, mode, unit=None, key='value', basis=None):
    value, info = _band(x, good, bad, mode, unit)
    return Tri(value, 'between_pass_and_fail_bands' if value is None else None, {key: info}, basis)


class Scene:
    """Evaluation view over one SceneState (+ initial state) with cached bodies/results."""

    def __init__(self, manifest, state, initial=None, bands=Bands(), fallbacks=Fallbacks()):
        self.manifest, self.state, self.initial = manifest, state, initial
        self.bands, self.fb = bands, fallbacks
        self.objects = {o['name']: o for o in manifest['objects']}
        self.drawers = {d['name']: d for d in manifest['drawers']}
        self._bodies, self.memo = {}, {}

    def body(self, name, initial=False):
        state = self.initial if initial else self.state
        if state is None:
            raise MissingEvidence('initial_state_missing')
        key = (name, initial)
        if key not in self._bodies:
            if name not in self.objects:
                raise MissingEvidence(f'unknown_object:{name}')
            pos = state.positions.get(name)
            if pos is None:
                raise MissingEvidence(f'pose_missing:{name}')
            self._bodies[key] = Body(self.objects[name], pos, state.orientations_wxyz.get(name))
        return self._bodies[key]

    def opening(self, drawer):
        if drawer not in self.drawers:
            raise MissingEvidence(f'unknown_drawer:{drawer}')
        value = self.state.drawer_openings.get(drawer)
        if value is None:
            raise MissingEvidence(f'drawer_opening_missing:{drawer}')
        return value

    @property
    def contacts(self):
        return self.state.contacts if self.state.contacts_available else None

    def touching(self, a, b):
        return frozenset((a, b)) in self.state.contacts


def _guard(fn):
    def wrapped(scene, *args):
        try:
            return fn(scene, *args)
        except MissingEvidence as error:
            return unknown(str(error))
    wrapped.__name__ = fn.__name__
    wrapped.__doc__ = fn.__doc__
    return wrapped


# ----------------------------------------------------------------------------- containers
@_guard
def Open(s, drawer):
    return _tri_band(s.opening(drawer), *s.bands.open_opening, 'ge', 'm', 'opening_m')


@_guard
def Closed(s, drawer):
    return _tri_band(s.opening(drawer), *s.bands.closed_opening, 'le', 'm', 'opening_m')


def _gap_support(s, lowest_z, surface_z, what):
    """Geometric support tri: lowest point within `support_within_m` above the surface."""
    gap = float(lowest_z - surface_z)
    fb = s.fb
    if -fb.support_max_penetration_m <= gap <= s.bands.support_within_m:
        value, reason = True, None
    elif gap >= fb.support_fail_above_m:
        value, reason = False, None
    else:
        value, reason = None, 'support_gap_unresolved'
    return Tri(value, reason, {'gap_above_surface_m': gap, 'surface': what}, 'geometric')


def _support_by_object(s, a, b):
    """Geometric: a's lowest point sits on b's top and a's centre projects onto b's footprint."""
    z = _gap_support(s, a.lowest_z, b.top_z, b.name)
    margin = point_footprint_margin(a.center[:2], b.footprint)
    fail = -s.fb.centre_on_surface_fail_m
    value = True if margin >= 0 else False if margin <= fail else None
    proj = Tri(value, None if value is not None else 'centre_projection_unresolved',
               {'centre_margin_m': margin}, 'geometric')
    out = k_and([z, proj])
    return Tri(out.value, out.reason, {**z.measurements, **proj.measurements}, 'geometric')


def _table_support(s, name):
    if s.contacts is not None:
        hit = s.touching(name, 'table')
        return Tri(hit, None, {'contact_with_table': hit}, 'contact')
    return _gap_support(s, s.body(name).lowest_z, s.fb.table_top_z, 'table')


def _load_path_to_drawer(s, name, drawer):
    """Contact load path object -> (objects) -> drawer, never through robot bodies or the table."""
    seen, frontier = {name}, [name]
    while frontier:
        node = frontier.pop()
        for pair in s.state.contacts:
            if node not in pair:
                continue
            other = next(iter(pair - {node}), None)
            if other is None or other in ROBOT_BODIES or other == 'table' or other in seen:
                continue
            if other == drawer:
                return True
            if other in s.objects:
                seen.add(other)
                frontier.append(other)
    return False


def _geometric_load_path(s, name, drawer, floor_z, visited=()):
    """Support by the cavity floor, or by an object that itself rests on the floor (recursive)."""
    a = s.body(name)
    floor = _gap_support(s, a.lowest_z, floor_z, f'{drawer}_floor')
    if floor.value is True:
        return floor
    options = [floor]
    for other in s.objects:
        if other == name or other in visited or other not in s.state.positions:
            continue
        b = s.body(other)
        if b.top_z > a.lowest_z + s.fb.support_fail_above_m:
            continue
        lower = _support_by_object(s, a, b)
        if lower.value is False:
            continue
        below = _geometric_load_path(s, other, drawer, floor_z, visited + (name,))
        options.append(k_and([lower, below]))
    return k_or(options)


@_guard
def In(s, name, drawer):
    if drawer not in s.drawers:
        raise MissingEvidence(f'unknown_drawer:{drawer}')
    cav = s.drawers[drawer]['cavity_when_closed']
    opening = s.opening(drawer)
    obj = s.body(name)
    y_range = (cav['y'][0] - opening, cav['y'][1] - opening)
    margin = footprint_clearance_in_rect(obj.footprint, cav['x'], y_range)
    m_tri = _tri_band(margin, *s.bands.in_margin, 'ge', 'm', 'footprint_margin_m')
    z = float(obj.center[2])
    b_tri = Tri(cav['floor_z'] <= z <= cav['rim_z'], None,
                {'center_z': z, 'floor_z': cav['floor_z'], 'rim_z': cav['rim_z'], 'opening_m': opening})
    if s.contacts is not None:
        c_tri = Tri(_load_path_to_drawer(s, name, drawer), None, {}, 'contact')
    else:
        c_tri = _geometric_load_path(s, name, drawer, cav['floor_z'])
    out = k_and([m_tri, b_tri, c_tri])
    return Tri(out.value, out.reason, {**m_tri.measurements, **b_tri.measurements, **c_tri.measurements,
                                       'load_path': c_tri.value}, c_tri.basis)


# ----------------------------------------------------------------------------- support
@_guard
def OnTable(s, name):
    s.body(name)
    return _table_support(s, name)


@_guard
def On(s, upper, lower):
    a, b = s.body(upper), s.body(lower)
    table = _table_support(s, upper)
    if s.contacts is not None:
        hit = s.touching(upper, lower)
        direct = Tri(hit, None, {'contact_with_lower': hit}, 'contact')
    else:
        direct = _support_by_object(s, a, b)
    out = k_and([direct, k_not(table)])
    return Tri(out.value, out.reason, {**direct.measurements, 'direct_table_support': table.value,
                                       **{f'table_{k}': v for k, v in table.measurements.items()
                                          if k == 'gap_above_surface_m'}}, direct.basis)


@_guard
def Released(s, name):
    body = s.body(name)
    contact = None
    if s.contacts is not None:
        contact = any(s.touching(name, f) for f in ('finger_left', 'finger_right'))
        if contact:
            return Tri(False, None, {'finger_contact': True}, 'contact')
    fingers = [s.state.finger_positions.get(f) for f in ('finger_left', 'finger_right')]
    fingers = [f for f in fingers if f is not None]
    if not fingers:
        if contact is False:
            return Tri(True, None, {'finger_contact': False},
                       'contact (finger clearance not separately measured)')
        return unknown('finger_evidence_missing')
    clearance = min(body.local_box_distance(f) for f in fingers)
    if contact is False:
        value, info = _band(clearance, *s.bands.released_clearance, 'ge', 'm')
        return Tri(value, 'between_pass_and_fail_bands' if value is None else None,
                   {'finger_contact': False, 'finger_clearance': info}, 'contact+finger_origin_clearance')
    value, info = _band(clearance, s.fb.finger_envelope_pass_m, s.fb.finger_envelope_fail_m, 'ge', 'm')
    return Tri(value, 'between_pass_and_fail_bands' if value is None else None,
               {'finger_clearance': info},
               'geometric (finger link origins as points; envelope not in vocabulary)')


@_guard
def AllReleased(s):
    results = {n: Released(s, n) for n in s.objects}
    out = k_and(list(results.values()))
    clearances = [r.measurements['finger_clearance']['measure'] for r in results.values()
                  if r.measurements.get('finger_clearance', {}).get('measure') is not None]
    basis = next((r.basis for r in results.values() if r.basis), None)
    return Tri(out.value, out.reason,
               {'min_finger_clearance_m': min(clearances, default=None),
                'unknown_objects': [n for n, r in results.items() if r.value is None],
                'held_objects': [n for n, r in results.items() if r.value is False]}, basis)


# ----------------------------------------------------------------------------- orientation
def _brick(s, name):
    b = s.body(name)
    if b.kind != 'brick':
        raise MissingEvidence(f'not_a_brick:{name}')
    return b


def _angle_deg(cos):
    return math.degrees(math.acos(float(np.clip(cos, -1, 1))))


@_guard
def Upright(s, name):
    b = _brick(s, name)
    return _tri_band(_angle_deg(b.z_axis[2]), *s.bands.orient_angle_deg, 'le', 'deg', 'angle_to_world_up_deg')


@_guard
def Inverted(s, name):
    b = _brick(s, name)
    return _tri_band(_angle_deg(-b.z_axis[2]), *s.bands.orient_angle_deg, 'le', 'deg', 'angle_to_world_down_deg')


@_guard
def OnSide(s, name):
    b = _brick(s, name)
    angle = math.degrees(math.asin(float(np.clip(abs(b.z_axis[2]), 0, 1))))
    return _tri_band(angle, *s.bands.orient_angle_deg, 'le', 'deg', 'stud_axis_to_horizontal_deg')


# ----------------------------------------------------------------------------- planar
@_guard
def Near(s, a, b):
    return _tri_band(footprint_gap(s.body(a), s.body(b)), *s.bands.near_gap, 'le', 'm', 'gap_m')


@_guard
def Apart(s, a, b):
    return _tri_band(footprint_gap(s.body(a), s.body(b)), *s.bands.apart_gap, 'ge', 'm', 'gap_m')


def _long_axis(s, name):
    if name == 'drawer_front':
        return np.array([1.0, 0.0]), None
    b = _brick(s, name)
    if b.long_ratio < s.bands.parallel_min_ratio:
        return None, f'not_elongated:{name}:ratio={b.long_ratio:.3f}'
    if b.long_axis_horizontal < 0.5:
        raise MissingEvidence(f'long_axis_not_horizontal:{name}')
    v = b.long_axis_xy
    return v / np.linalg.norm(v), None


def _folded_angle(s, a, b):
    va, ra = _long_axis(s, a)
    vb, rb = _long_axis(s, b)
    if va is None or vb is None:
        return None, ra or rb
    return math.degrees(math.acos(float(np.clip(abs(va @ vb), 0, 1)))), None


@_guard
def Parallel(s, a, b):
    ang, why = _folded_angle(s, a, b)
    if ang is None:
        return Tri(False, None, {'applies_to': why})
    return _tri_band(ang, *s.bands.parallel_deg, 'le', 'deg', 'folded_axis_angle_deg')


@_guard
def Perpendicular(s, a, b):
    ang, why = _folded_angle(s, a, b)
    if ang is None:
        return Tri(False, None, {'applies_to': why})
    return _tri_band(90.0 - ang, *s.bands.parallel_deg, 'le', 'deg', 'perpendicular_error_deg')


def _flat(args):
    out = []
    for a in args:
        out.extend(_flat(a) if isinstance(a, (list, tuple)) else [a])
    return out


@_guard
def Row(s, *args):
    names = _flat(args)
    if len(names) < 2:
        raise MissingEvidence('row_needs_two_objects')
    bodies = [s.body(n) for n in names]
    pts = np.array([b.center[:2] for b in bodies])
    mean = pts.mean(0)
    _, _, vt = np.linalg.svd(pts - mean)
    d = vt[0]
    n = np.array([-d[1], d[0]])
    residual = float(np.abs((pts - mean) @ n).max())
    r = residual / min(b.min_width() for b in bodies)
    r_tri = _tri_band(r, *s.bands.row_residual_widths, 'le', 'widths', 'residual_widths')
    order = [int(i) for i in np.argsort((pts - mean) @ d)]
    expected = list(range(len(names)))
    order_ok = order == expected or order == expected[::-1]
    apart = [Apart(s, a, b) for a, b in zip(names, names[1:])]
    out = k_and([r_tri, Tri(order_ok)] + apart)
    return Tri(out.value, out.reason,
               {**r_tri.measurements, 'order_holds': order_ok, 'projection_order': [names[i] for i in order],
                'adjacent_gaps_m': [a.measurements.get('gap_m', {}).get('measure') for a in apart]})


@_guard
def Between(s, a, b, c):
    pa, pb, pc = (s.body(n).center[:2] for n in (a, b, c))
    seg = pc - pb
    length2 = float(seg @ seg)
    if length2 < 1e-12:
        raise MissingEvidence('degenerate_segment')
    t = float((pa - pb) @ seg / length2)
    d = float(np.linalg.norm(pa - (pb + np.clip(t, 0, 1) * seg)))
    lo, hi = s.bands.between_t
    value = True if lo <= t <= hi else False if (t <= 0 or t >= 1) else None
    t_tri = Tri(value, None if value is not None else 'between_pass_and_fail_bands',
                {'t': {'measure': t, 'pass': [lo, hi], 'fail': 't<=0 or t>=1',
                       'norm_margin': min(abs(t - lo), abs(t - hi), abs(t), abs(t - 1)) / 0.15}})
    d_tri = _tri_band(d, *s.bands.between_d, 'le', 'm', 'distance_to_segment_m')
    out = k_and([t_tri, d_tri])
    return Tri(out.value, out.reason, {**t_tri.measurements, **d_tri.measurements})


def _mst_max_edge(names, gaps):
    """Largest edge of the minimum spanning tree over pairwise gaps (0 for a single object)."""
    if len(names) < 2:
        return 0.0
    in_tree, worst = {names[0]}, 0.0
    while len(in_tree) < len(names):
        w, n = min((gaps[frozenset((a, b))], b) for a in in_tree for b in names if b not in in_tree)
        in_tree.add(n)
        worst = max(worst, w)
    return worst


@_guard
def Grouped(s, g1, g2):
    groups = [_flat([g1]), _flat([g2])]
    bodies = {n: s.body(n) for g in groups for n in g}
    gaps = {frozenset((a, b)): footprint_gap(bodies[a], bodies[b]) for a, b in combinations(bodies, 2)}
    w = max(_mst_max_edge(g, gaps) for g in groups)
    g = min(gaps[frozenset((a, b))] for a in groups[0] for b in groups[1])
    b = s.bands
    if g >= b.grouped_ratio * w and g >= b.grouped_gap[0] and w <= b.grouped_w[0]:
        value = True
    elif g <= w or g <= b.grouped_gap[1] or w >= b.grouped_w[1]:
        value = False
    else:
        value = None
    return Tri(value, 'between_pass_and_fail_bands' if value is None else None,
               {'within_group_w_m': {'measure': float(w), 'pass': b.grouped_w[0], 'fail': b.grouped_w[1]},
                'between_group_gap_m': {
                    'measure': float(g), 'pass': f'>= max({b.grouped_ratio}*w, {b.grouped_gap[0]})',
                    'fail': f'<= max(w, {b.grouped_gap[1]})',
                    'norm_margin': float(min(abs(g - max(b.grouped_ratio * w, b.grouped_gap[0])),
                                             abs(g - max(w, b.grouped_gap[1]))) / b.grouped_gap[0])}})


# ----------------------------------------------------------------------------- displacement
@_guard
def Unmoved(s, name):
    a, b = s.body(name, initial=True), s.body(name)
    if a.kind == 'brick':
        translation = float(np.linalg.norm(b.pos - a.pos))
        qa, qb = s.initial.orientations_wxyz[name], s.state.orientations_wxyz[name]
        dot = abs(float(qa @ qb) / (np.linalg.norm(qa) * np.linalg.norm(qb)))
        rotation = math.degrees(2 * math.acos(min(1.0, dot)))
    else:
        translation, rotation = float(np.linalg.norm(b.center - a.center)), 0.0  # sphere: rotation moot
    t_tri = _tri_band(translation, *s.bands.unmoved_translation, 'le', 'm', 'translation_m')
    r_tri = _tri_band(rotation, *s.bands.unmoved_rotation_deg, 'le', 'deg', 'rotation_deg')
    out = k_and([t_tri, r_tri])
    return Tri(out.value, out.reason, {**t_tri.measurements, **r_tri.measurements})


@_guard
def AtInitialPositionOf(s, a, b):
    d = float(np.linalg.norm(s.body(a).center[:2] - s.body(b, initial=True).center[:2]))
    return _tri_band(d, *s.bands.at_initial, 'le', 'm', 'horizontal_distance_m')


TERMINAL_PREDICATES = {
    'Open': (Open, 1), 'Closed': (Closed, 1), 'In': (In, 2), 'OnTable': (OnTable, 1), 'On': (On, 2),
    'Released': (Released, 1), 'AllReleased': (AllReleased, 0), 'Upright': (Upright, 1),
    'Inverted': (Inverted, 1), 'OnSide': (OnSide, 1), 'Near': (Near, 2), 'Apart': (Apart, 2),
    'Parallel': (Parallel, 2), 'Perpendicular': (Perpendicular, 2), 'Row': (Row, None),
    'Between': (Between, 3), 'Grouped': (Grouped, 2), 'Unmoved': (Unmoved, 1),
    'AtInitialPositionOf': (AtInitialPositionOf, 2),
}


# ----------------------------------------------------------------------------- process helpers
def grasped(s, name, fb):
    """Both-finger grasp evidence for one sample: contact when available, else finger proximity."""
    if s.contacts is not None:
        both = s.touching(name, 'finger_left') and s.touching(name, 'finger_right')
        return Tri(both, None, {}, 'contact')
    if not fb.allow_geometric_grasp:
        return unknown('contacts_unavailable')
    try:
        body = s.body(name)
    except MissingEvidence as error:
        return unknown(str(error))
    fingers = [s.state.finger_positions.get(f) for f in ('finger_left', 'finger_right')]
    if any(f is None for f in fingers):
        return unknown('finger_evidence_missing')
    c = [body.local_box_distance(f) for f in fingers]
    near = _band(max(c), fb.grasp_pass_m, fb.grasp_fail_m, 'le')[0]
    return Tri(near, None if near is not None else 'grasp_unresolved', {'finger_clearances_m': c},
               'geometric (finger link origins; not in vocabulary)')


def robot_contact(s, name):
    if s.contacts is None:
        return unknown('contacts_unavailable')
    hit = any(name in pair and any(o in ROBOT_BODIES or str(o).startswith(('robot', 'link', 'panda'))
                                   for o in pair - {name}) for pair in s.state.contacts)
    return Tri(hit, None, {}, 'contact')
