"""Synthetic tests for the generic BDDL -> goal converter (LIBERO/BEHAVIOR-style fixtures written inline)."""
import hashlib
import json

import pytest

from validation.goals.converters import CONVERTER_VERSION, BDDLError, convert_bddl_file, convert_bddl_text, parse_sexprs

VOCAB = 'libero-predicates/test-rev'

LIBERO_BOWL = """\
; synthetic, modelled on LIBERO public BDDL style
(define (problem LIBERO_Kitchen_Tabletop_Manipulation)
  (:domain robosuite)
  (:language put the black bowl on the plate)
  (:regions
    (plate_init_region
        (:target kitchen_table)
        (:ranges ((-0.01 -0.25 0.01 -0.23)))
        (:yaw_rotation ((0.0 0.0)))
    )
  )
  (:fixtures
    kitchen_table - kitchen_table
    wooden_cabinet_1 - wooden_cabinet
  )
  (:objects
    akita_black_bowl_1 - akita_black_bowl
    plate_1 - plate
  )
  (:obj_of_interest
    akita_black_bowl_1
    plate_1
  )
  (:init
    (On akita_black_bowl_1 kitchen_table_akita_black_bowl_init_region)  ; trailing comment
    (On plate_1 kitchen_table_plate_init_region)
    (Open wooden_cabinet_1_top_region)
  )
  (:goal
    (And (On akita_black_bowl_1 plate_1))
  )
)
"""


def conv(text, **kw):
    kw.setdefault('vocabulary', VOCAB)
    return convert_bddl_text(text, **kw)


def wrap(goal, objects='a_1 - a b_1 - b', extra=''):
    return f'(define (problem p) (:domain robosuite) (:objects {objects}) {extra} (:goal {goal}))'


def test_libero_style_full_document():
    out = conv(LIBERO_BOWL, source_path='libero/put_bowl.bddl')
    assert out['goal'] == {'all': [{'pred': 'On', 'args': ['akita_black_bowl_1', 'plate_1']}]}
    assert out['problem'] == 'LIBERO_Kitchen_Tabletop_Manipulation'
    assert out['domain'] == 'robosuite'
    assert out['language'] == 'put the black bowl on the plate'
    assert out['objects'] == {'akita_black_bowl_1': 'akita_black_bowl', 'plate_1': 'plate'}
    assert out['fixtures'] == {'kitchen_table': 'kitchen_table', 'wooden_cabinet_1': 'wooden_cabinet'}
    assert out['obj_of_interest'] == ['akita_black_bowl_1', 'plate_1']
    assert out['init'] is None
    assert out['vocabulary'] == VOCAB
    assert out['basis'] == 'native_converted'
    assert out['provenance'] == {'source_path': 'libero/put_bowl.bddl',
                                 'sha256': hashlib.sha256(LIBERO_BOWL.encode()).hexdigest(),
                                 'converter': CONVERTER_VERSION}


def test_init_converted_separately():
    out = conv(LIBERO_BOWL, include_init=True)
    assert out['init'] == [
        {'pred': 'On', 'args': ['akita_black_bowl_1', 'kitchen_table_akita_black_bowl_init_region']},
        {'pred': 'On', 'args': ['plate_1', 'kitchen_table_plate_init_region']},
        {'pred': 'Open', 'args': ['wooden_cabinet_1_top_region']},
    ]


def test_init_negated_literal_and_bad_init():
    assert conv(wrap('(On a_1 b_1)', extra='(:init (not (Open c_1)))'), include_init=True)['init'] == [
        {'not': {'pred': 'Open', 'args': ['c_1']}}]
    with pytest.raises(BDDLError, match='init entries must be literals'):
        conv(wrap('(On a_1 b_1)', extra='(:init (and (Open c_1)))'), include_init=True)


def test_nesting_and_keyword_case_insensitivity():
    goal = '(AND (or (In a_1 wooden_cabinet_1_middle_region) (NOT (Open wooden_cabinet_1_top_region))) (TurnOn flat_stove_1) (Up a_1))'
    out = conv(wrap(goal))
    assert out['goal'] == {'all': [
        {'any': [{'pred': 'In', 'args': ['a_1', 'wooden_cabinet_1_middle_region']},
                 {'not': {'pred': 'Open', 'args': ['wooden_cabinet_1_top_region']}}]},
        {'pred': 'TurnOn', 'args': ['flat_stove_1']},
        {'pred': 'Up', 'args': ['a_1']},
    ]}
    upper = '(DEFINE (PROBLEM p) (:DOMAIN d) (:OBJECTS a_1 - a) (:GOAL (And (Close a_1))))'
    assert conv(upper)['goal'] == {'all': [{'pred': 'Close', 'args': ['a_1']}]}


def test_predicate_case_rule():
    out = conv(wrap('(And (TurnOff a_1) (On a_1 b_1))'), predicate_case='lower')
    assert [n['pred'] for n in out['goal']['all']] == ['turnoff', 'on']
    assert out['goal']['all'][1]['args'] == ['a_1', 'b_1']  # names never normalised
    with pytest.raises(BDDLError, match='predicate_case'):
        conv(wrap('(On a_1 b_1)'), predicate_case='upper')


def test_object_names_verbatim_and_behavior_style_types():
    text = """(define (problem cleaning_bowls_0) (:domain igibson)
      (:objects bowl.n.01_1 bowl.n.01_2 - bowl.n.01 Sink_1 - sink.n.01 loose_thing)
      (:init (ontop bowl.n.01_1 Sink_1))
      (:goal (and (inside bowl.n.01_1 Sink_1) (not (ontop bowl.n.01_2 Sink_1)))))"""
    out = conv(text, include_init=True)
    assert out['objects'] == {'bowl.n.01_1': 'bowl.n.01', 'bowl.n.01_2': 'bowl.n.01', 'Sink_1': 'sink.n.01',
                              'loose_thing': None}
    assert out['goal'] == {'all': [{'pred': 'inside', 'args': ['bowl.n.01_1', 'Sink_1']},
                                   {'not': {'pred': 'ontop', 'args': ['bowl.n.01_2', 'Sink_1']}}]}
    assert out['init'] == [{'pred': 'ontop', 'args': ['bowl.n.01_1', 'Sink_1']}]


def test_comments_everywhere_and_crlf_bom():
    text = '﻿; header\r\n(define ; c1\r\n (problem p) ;c2\r\n (:objects a_1 - a) ; c3 (not a form\r\n (:goal (On a_1 ; mid-atom comment\r\n b_1)))\r\n; tail'
    assert conv(text.encode('utf-8'))['goal'] == {'pred': 'On', 'args': ['a_1', 'b_1']}


def test_allowlist_accepts_and_rejects():
    allow = {'On': 2, 'Open': 1, 'In': [2]}
    assert conv(wrap('(And (On a_1 b_1) (Open c_1))'), allowlist=allow)['goal']['all'][1]['pred'] == 'Open'
    with pytest.raises(BDDLError, match="unknown predicate 'TurnOn'"):
        conv(wrap('(And (On a_1 b_1) (TurnOn c_1))'), allowlist=allow)
    with pytest.raises(BDDLError, match="'On' has arity 3"):
        conv(wrap('(On a_1 b_1 c_1)'), allowlist=allow)
    with pytest.raises(BDDLError, match="unknown predicate 'on'"):  # exact after case rule
        conv(wrap('(on a_1 b_1)'), allowlist=allow)
    assert conv(wrap('(ON a_1 b_1)'), allowlist={'on': 2}, predicate_case='lower')['goal']['pred'] == 'on'


def test_allowlist_applies_to_init():
    with pytest.raises(BDDLError, match=':init: unknown predicate'):
        conv(wrap('(On a_1 b_1)', extra='(:init (Weird a_1))'), allowlist={'On': 2}, include_init=True)


@pytest.mark.parametrize('goal, construct', [
    ('(exists (?x - bowl) (On ?x plate_1))', 'exists'),
    ('(ForAll (?x - bowl) (On ?x plate_1))', 'forall'),
    ('(forn (2) (?x - bowl) (On ?x plate_1))', 'forn'),
    ('(forpairs (?x - a) (?y - b) (On ?x ?y))', 'forpairs'),
    ('(imply (Open c_1) (On a_1 b_1))', 'imply'),
    ('(when (Open c_1) (On a_1 b_1))', 'when'),
    ('(> (temperature a_1) 5)', '>'),
    ('(= (count a_1) 2)', '='),
    ('(And (On a_1 b_1) (Not (exists (?x - a) (Open ?x))))', 'exists'),
])
def test_unsupported_constructs_error(goal, construct):
    with pytest.raises(BDDLError, match=f'unsupported construct {construct}'):
        conv(wrap(goal))


@pytest.mark.parametrize('goal, msg', [
    ('(On ?x b_1)', 'unbound variable'),
    ('(Height a_1 0.5)', 'numeric literal'),
    ('(On a_1 (f b_1))', 'nested expression'),
    ('(And)', 'empty'),
    ('(Or)', 'empty'),
    ('(not (On a_1 b_1) (On b_1 a_1))', 'exactly one operand'),
    ('()', 'empty expression'),
    ('On', 'expected a parenthesised'),
])
def test_malformed_goal_errors(goal, msg):
    with pytest.raises(BDDLError, match=msg):
        conv(wrap(goal))


@pytest.mark.parametrize('text, msg', [
    ('(define (problem p) (:objects a - b)', "unbalanced '\\('"),
    ('(define (problem p) (:goal (On a b))))', "unbalanced '\\)'"),
    ('(define (problem p) (:objects a - b))', 'missing \\(:goal'),
    ('(define (problem p) (:goal (On a b)) (:goal (On a b)))', 'duplicate section'),
    ('(define (problem p) (:constraints (On a b)) (:goal (On a b)))', 'unsupported section'),
    ('(define (problem p) (:goal (On a b) (On b a)))', 'exactly one expression'),
    ('(foo (problem p) (:goal (On a b)))', 'define'),
    ('(define (problem p) (:goal (On a b))) (define (problem q) (:goal (On a b)))', 'define'),
    ('(define (problem p) (:objects a - ) (:goal (On a b)))', 'dangling'),
    ('(define (problem p) (:objects a - x a - y) (:goal (On a b)))', 'duplicate name'),
    ('(define (problem p) (:objects a - x) (:fixtures a - y) (:goal (On a b)))', 'both as object and fixture'),
    ('(define (problem p) (:goal (On a "b)))', 'unterminated string'),
])
def test_malformed_document_errors(text, msg):
    with pytest.raises(BDDLError, match=msg):
        conv(text)


def test_vocabulary_required():
    with pytest.raises(BDDLError, match='vocabulary'):
        convert_bddl_text(LIBERO_BOWL, vocabulary='')


def test_sha256_check_and_file_entry(tmp_path):
    p = tmp_path / 'task.bddl'
    p.write_bytes(LIBERO_BOWL.encode())
    sha = hashlib.sha256(LIBERO_BOWL.encode()).hexdigest()
    out = convert_bddl_file(p, vocabulary=VOCAB, expected_sha256=sha.upper())
    assert out['provenance']['sha256'] == sha
    assert out['provenance']['source_path'] == p.as_posix()
    with pytest.raises(BDDLError, match='sha256 mismatch'):
        convert_bddl_file(p, vocabulary=VOCAB, expected_sha256='0' * 64)


def test_deterministic_and_json_serialisable():
    a = json.dumps(conv(LIBERO_BOWL, include_init=True), sort_keys=True)
    b = json.dumps(conv(LIBERO_BOWL, include_init=True), sort_keys=True)
    assert a == b


def test_parse_sexprs_strings_and_comments():
    assert parse_sexprs('(a "b ; c" d) ; e\n(f)') == [['a', 'b ; c', 'd'], ['f']]
