"""Goal engine / vocabulary plugin boundary (validation.goals.vocabulary)."""
from dataclasses import dataclass

import pytest

from validation.goals import GOAL_BASES, VocabularyPlugin, WhenOutcome, evaluate_task, register, registered
from validation.goals.tri import Tri

MANIFEST = {'objects': [{'name': 'a', 'kind': 'k'}, {'name': 'b', 'kind': 'k'}]}


@dataclass(frozen=True)
class _Policy:
    max_assignments: int = 100
    max_sample_gap_s: float = 0.1


TOY = register(VocabularyPlugin(
    version='toy-predicates/0.0.1',
    predicates={'Lit': (lambda state, name: Tri(state.get(name)), 1)},
    when='final_state',
    evaluate_when=lambda trace, final, objects, policy: WhenOutcome({'settled': None, 'reason': 'not_applicable'}),
    state_adapter=lambda manifest, state, initial, policy: state,
    default_policy=_Policy,
    bind_fields=('kind',),
))


def _row(goal, bind=None):
    return {'task_id': 't', 'truth': {'goal': goal, **({'bind': bind} if bind else {})}}


def test_engine_runs_a_non_scene_vocabulary_without_implicit_terms():
    goal = {'all': [{'pred': 'Lit', 'args': ['?x']}]}
    r = evaluate_task(_row(goal, {'?x': {'kind': 'k'}}), MANIFEST, {'version': TOY.version},
                      {'a': False, 'b': True}, {})
    assert r['vocabulary'] == TOY.version and r['goal_basis'] == 'dataset_goal'
    assert r['success'] is True and r['assignment'] == {'?x': 'b'}
    assert 'all_released' not in r and r['settle'] == {'settled': None, 'reason': 'not_applicable'}
    r = evaluate_task(_row(goal, {'?x': {'kind': 'k'}}), MANIFEST, {'version': TOY.version},
                      {'a': None, 'b': False}, {}, basis='native_converted')
    assert r['success'] is None and r['goal_basis'] == 'native_converted'


def test_engine_refuses_undeclared_or_unregistered_vocabulary_and_unknown_basis():
    row = _row({'pred': 'Lit', 'args': ['a']})
    for declared in (None, {}, {'version': 'toy-predicates/9.9.9'}):
        with pytest.raises(ValueError, match='unsupported vocabulary'):
            evaluate_task(row, MANIFEST, declared, {'a': True}, {})
    with pytest.raises(ValueError, match='not implemented'):
        evaluate_task(row, MANIFEST, {'version': TOY.version, 'predicates': {'Other': {}}}, {'a': True}, {})
    with pytest.raises(ValueError, match='unknown goal basis'):
        evaluate_task(row, MANIFEST, {'version': TOY.version}, {'a': True}, {}, basis='guess')
    with pytest.raises(ValueError, match='process predicate Sequence'):
        evaluate_task(_row({'pred': 'Sequence', 'args': []}), MANIFEST, {'version': TOY.version}, {}, {})


def test_registry_and_bases():
    assert {'scene-predicates/1.0.0', TOY.version} <= set(registered())
    assert GOAL_BASES == ('dataset_goal', 'native_converted', 'llm_drafted_reviewed', 'terminal_review')
    with pytest.raises(ValueError, match='already registered'):
        register(VocabularyPlugin(version=TOY.version, predicates={}, when='x', evaluate_when=None,
                                  state_adapter=None, default_policy=_Policy))
