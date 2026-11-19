"""The scene-predicates plugin must match the pinned SimDataKit vocabulary file.

SimDataKit owns the vocabulary (meaning and thresholds); GeoChora pins one copy per version and
implements it. A change on either side without a new vocabulary version fails here.
"""
import hashlib
import os
import re
from pathlib import Path

import pytest
import yaml

from validation.goals.predicates import TERMINAL_PREDICATES, Bands
from validation.goals.vocabularies.scene_predicates import EvalPolicy, PLUGIN

PINNED = Path(__file__).resolve().parents[1] / 'goals' / 'vocabularies' / 'scene-predicates-v1.yaml'
# Same bytes as SimDataKit catalog/profiles/vocabularies/scene-predicates-v1.yaml and the copy sealed in
# franka-scene-50 2.0.0 (resources/scene-predicates-v1.yaml).
PINNED_SHA256 = 'd0c915dfbaef65efd6b672e7772686938fde648d30673656aee22639e43c6890'
NUM = r'(-?\d+(?:\.\d+)?)'


def _vocab():
    return yaml.safe_load(PINNED.read_text(encoding='utf-8'))


def _nums(text):
    return [float(x) for x in re.findall(NUM, str(text))]


def test_pinned_copy_bytes():
    assert hashlib.sha256(PINNED.read_bytes()).hexdigest() == PINNED_SHA256


def test_version_and_predicate_names():
    v = _vocab()
    assert PLUGIN.version == v['version'] == 'scene-predicates/1.0.0'
    assert set(TERMINAL_PREDICATES) == set(v['predicates'])
    assert set(PLUGIN.process_predicates) | {'Sequence'} == set(v['process_predicates'])


def test_arities():
    v = _vocab()['predicates']
    for name, (_, arity) in TERMINAL_PREDICATES.items():
        args = v[name]['args']
        if '...' in args:
            assert arity is None, name
        else:
            assert arity == len(args), name


# (vocabulary predicate, Bands field): the band's (pass, fail) numbers as they appear in the YAML.
SIMPLE = {
    'Open': 'open_opening', 'Closed': 'closed_opening', 'Near': 'near_gap', 'Apart': 'apart_gap',
    'Parallel': 'parallel_deg', 'Perpendicular': 'parallel_deg', 'Upright': 'orient_angle_deg',
    'Inverted': 'orient_angle_deg', 'OnSide': 'orient_angle_deg', 'AtInitialPositionOf': 'at_initial',
}


@pytest.mark.parametrize('pred,field', sorted(SIMPLE.items()))
def test_simple_bands(pred, field):
    p = _vocab()['predicates'][pred]
    assert (_nums(p['pass'])[0], _nums(p['fail'])[0]) == getattr(Bands(), field)


def test_compound_bands():
    v, b = _vocab()['predicates'], Bands()
    assert _nums(v['In']['pass'])[0] == b.in_margin[0] and _nums(v['In']['fail'])[0] == b.in_margin[1]
    assert _nums(v['Released']['pass'])[0] == b.released_clearance[0]
    assert _nums(v['Parallel']['applies_to'])[0] == b.parallel_min_ratio
    row_p, row_f = _nums(v['Row']['pass']), _nums(v['Row']['fail'])
    assert (row_p[0], row_f[0]) == b.row_residual_widths
    bp, bf = _nums(v['Between']['pass']), _nums(v['Between']['fail'])
    assert (bp[0], bp[1]) == b.between_t and (bp[2], bf[2]) == b.between_d and bf[:2] == [0.0, 1.0]
    gp, gf = _nums(v['Grouped']['pass']), _nums(v['Grouped']['fail'])   # g>=2*w, g>=0.05, w<=0.06 | g<=0.02, w>=0.10
    assert gp == [b.grouped_ratio, b.grouped_gap[0], b.grouped_w[0]]
    assert gf == [b.grouped_gap[1], b.grouped_w[1]]
    up, uf = _nums(v['Unmoved']['pass']), _nums(v['Unmoved']['fail'])
    assert (up[0], uf[0]) == b.unmoved_translation and (up[1], uf[1]) == b.unmoved_rotation_deg


def test_evaluation_rules():
    ev = _vocab()['evaluation']
    policy = EvalPolicy()
    terminal = _nums(ev['terminal_state'])
    assert terminal[:2] == [policy.settle_speed_mps, policy.settle_window_s]
    assert _nums(ev['support_evidence'])[0] == Bands().support_within_m
    assert 'AllReleased' in ev['implicit_goal_terms']
    assert any(t[1] == 'AllReleased' or 'AllReleased' in str(t) for t in PLUGIN.implicit_terms)


def test_simdatakit_source_unchanged():
    """Optional cross-repo check: skipped when no SimDataKit checkout is found."""
    root = Path(os.environ.get('SIMDATAKIT_ROOT', Path(__file__).resolve().parents[3] / 'SimDataKit'))
    source = root / 'catalog' / 'profiles' / 'vocabularies' / 'scene-predicates-v1.yaml'
    if not source.exists():
        pytest.skip(f'SimDataKit vocabulary not found at {source}')
    assert hashlib.sha256(source.read_bytes()).hexdigest() == PINNED_SHA256, (
        'SimDataKit scene-predicates-v1.yaml changed in place; a vocabulary change needs a new version '
        '(new file + new GeoChora plugin), never an edit of v1')
