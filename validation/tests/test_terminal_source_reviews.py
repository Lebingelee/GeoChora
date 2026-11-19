"""Provider-free source-review contract and real file/callback transport checks.

Authored candidate/reviewer responses test provenance, missing evidence and
release behavior. They do not measure model accuracy or simulate physics.
"""

from validation.tests.fixtures.source_reviews import PROFILE, inputs, candidate, dispatch, verification
import base64
from copy import deepcopy
import hashlib
import json

import pytest

from validation.protocol import InvalidGenerationProtocol
from validation.terminal.reviews import admit_source_review, admit_source_verification, prepare_source_review, prepare_source_verification
from validation.protocol import _digest
from validation.terminal.dispatch import TerminalDispatchError, complete_terminal_job, execute_terminal_job, make_terminal_result, prepare_terminal_job, write_terminal_job
from validation.tests.fixtures.source_reviews import PNG


@pytest.mark.parametrize('value', [True, False, None])
@pytest.mark.parametrize('status', ['confirmed', 'disputed', 'unresolved'])
def test_original_source_without_vocabulary_releases_only_independently_confirmed_candidate(value, status):
    request = inputs()
    response = candidate(request, value)
    before = deepcopy((request, response))
    first = admit_source_review(request, response, dispatch=dispatch(request, response))
    assert first['candidate_terminal'] is value and first['terminal'] is None
    assert first['reason'] == 'independent_review_required'
    review = prepare_source_verification(request, response, judgment_dispatch=first['dispatch'], model_profile=PROFILE)
    answer = verification(review, status)
    result = admit_source_verification(review, answer, dispatch=dispatch(review, answer, 'reviewer', 'review-call'))
    assert result['terminal'] is (value if status == 'confirmed' else None)
    assert result['task_success'] is None and result['process'] == 'not_evaluated'
    assert result['requirements'][1]['scope'] == 'delivery' and result['requirements'][1]['value'] is None
    assert review['source'] == request['source'] and 'specification' not in review
    assert 'vocabulary' not in request and 'atoms' not in request
    result['requirements'][0]['text'] = 'consumer mutation'
    assert (request, response) == before


@pytest.mark.parametrize('field', ['context_id', 'dispatch_id'])
def test_verifier_cannot_reuse_judgment_context_or_dispatch(field):
    request = inputs()
    response = candidate(request)
    first = dispatch(request, response)
    review = prepare_source_verification(request, response, judgment_dispatch=first, model_profile=PROFILE)
    answer = verification(review)
    receipt = dispatch(review, answer, 'reviewer', 'review-call')
    receipt[field] = first[field]
    with pytest.raises(InvalidGenerationProtocol, match='independent'):
        admit_source_verification(review, answer, dispatch=receipt)


@pytest.mark.parametrize('mutation', ['omission', 'false_summary', 'unknown_summary', 'delivery_pass',
                                    'foreign_citation', 'no_observation', 'duplicate', 'foreign_source_pointer'])
def test_malformed_or_unsupported_candidates_do_not_become_unknown_opinions(mutation):
    request = inputs()
    response = candidate(request)
    if mutation == 'omission':
        response['requirements'].pop()
    elif mutation == 'false_summary':
        response['terminal'] = False
    elif mutation == 'unknown_summary':
        response['requirements'][0]['value'] = None
    elif mutation == 'delivery_pass':
        response['requirements'][1]['value'] = True
    elif mutation == 'foreign_citation':
        response['requirements'][0]['evidence_ids'] = ['other-run']
    elif mutation == 'no_observation':
        response['requirements'][0]['evidence_ids'] = []
    elif mutation == 'duplicate':
        response['requirements'].append(deepcopy(response['requirements'][0]))
    else:
        response['requirements'][0]['source_pointers'] = ['/missing']
    with pytest.raises((InvalidGenerationProtocol, ValueError)):
        admit_source_review(request, response, dispatch=dispatch(request, response))


@pytest.mark.parametrize('value', [True, False])
def test_auxiliary_numeric_measurements_alone_cannot_authorize_a_physical_result(value):
    request = inputs(kinds=('measurement',))
    response = candidate(request, value)
    with pytest.raises(InvalidGenerationProtocol, match='native endpoint observations'):
        admit_source_review(request, response, dispatch=dispatch(request, response))
    response = candidate(request, None)
    assert admit_source_review(request, response, dispatch=dispatch(request, response))['candidate_terminal'] is None


def test_terminal_counterexample_remains_false_with_other_unknown_requirements():
    request = inputs()
    response = candidate(request, False)
    other = deepcopy(response['requirements'][0])
    other.update(id='unresolved-detail', value=None, evidence_ids=[], reason='Necessary condition lacks evidence.')
    response['requirements'].append(other)
    assert admit_source_review(request, response, dispatch=dispatch(request, response))['candidate_terminal'] is False


@pytest.mark.parametrize('goal,asset,overall', [(True, None, None), (False, None, False), (True, True, True)])
def test_category_report_keeps_original_conjunction_and_unverified_authority(goal, asset, overall):
    original = inputs()
    source = deepcopy(original['source'])
    source['requirements'].append('Preserve the original collision geometry at the endpoint.')
    request = prepare_source_review(source, original['endpoint'], required_source_pointers=['/requirements'],
                                    model_profile=PROFILE, evidence=original['evidence'])
    response = candidate(request, goal)
    response['requirements'][0]['category'] = 'goal'
    response['requirements'][1]['category'] = None
    asset_row = deepcopy(response['requirements'][0])
    asset_row.update(id='preserved-assets', category='asset_integrity', source_pointers=['/requirements/2'],
                     text=source['requirements'][2], value=asset)
    response['requirements'].append(asset_row)
    response['terminal'] = overall
    result = admit_source_review(request, response, dispatch=dispatch(request, response))
    summary = result['requirement_summary']
    assert result['candidate_terminal'] is overall and result['terminal'] is None
    assert summary['terminal_categories']['goal']['candidate_value'] is goal
    assert summary['terminal_categories']['asset_integrity']['candidate_value'] is asset
    assert summary['terminal_categories']['asset_integrity']['unknown_ids'] == (['preserved-assets'] if asset is None else [])
    assert summary['deferred']['delivery'] == [response['requirements'][1]['id']]
    review = prepare_source_verification(request, response, judgment_dispatch=dispatch(request, response), model_profile=PROFILE)
    answer = verification(review, 'disputed')
    final = admit_source_verification(review, answer, dispatch=dispatch(review, answer, 'reviewer', 'review-call'))
    assert final['terminal'] is None and final['requirement_summary'] == summary
    assert summary['authority'] == 'candidate_checklist_not_independent_verification'


def test_legacy_rows_remain_unclassified_instead_of_guessing_from_names():
    request = inputs()
    response = candidate(request)
    response['requirements'][0]['id'] = 'asset-looking-name'
    result = admit_source_review(request, response, dispatch=dispatch(request, response))
    categories = result['requirement_summary']['terminal_categories']
    assert categories['unclassified']['requirement_ids'] == ['asset-looking-name']
    assert categories['goal']['requirement_ids'] == categories['asset_integrity']['requirement_ids'] == []


@pytest.mark.parametrize('index,category', [(0, None), (0, 'skip'), (1, 'goal')])
def test_invalid_requirement_categories_are_protocol_errors(index, category):
    request = inputs()
    response = candidate(request)
    response['requirements'][index]['category'] = category
    with pytest.raises(InvalidGenerationProtocol, match='category'):
        admit_source_review(request, response, dispatch=dispatch(request, response))


@pytest.mark.parametrize('status', ['confirmed', 'disputed', 'unresolved'])
def test_counterexample_verification_with_unrelated_semantic_omission_uses_existing_file_gate(tmp_path, status):
    original = inputs(tmp_path)
    source = deepcopy(original['source'])
    source['requirements'].append('The assembly must also rest on the pedestal.')
    request = prepare_source_review(source, original['endpoint'], required_source_pointers=['/requirements'],
                                    model_profile=PROFILE, evidence=original['evidence'])
    # Structural pointer coverage does not imply that the checklist includes every requirement.
    response = candidate(request, False)
    review = prepare_source_verification(request, response, judgment_dispatch=dispatch(request, response),
                                         model_profile=PROFILE)
    answer = verification(review, status)
    answer['reason'] = ('The raw observation independently shows neither enclosure surrounds the same assembly; '
                        '/requirements/0 is a necessary condition. The omitted pedestal condition at '
                        '/requirements/2 does not change that counterexample or its applicability.'
                        if status == 'confirmed' else 'The counterexample or its applicability is not independently confirmed.')
    job = prepare_terminal_job(review, job_id='counterexample', transport='external_file',
                               context_id='independent-reviewer', artifact_root=tmp_path)
    directory = tmp_path / 'verification'
    write_terminal_job(job, directory)
    result = make_terminal_result(job, json.dumps(answer), dispatch_id='independent-review-call',
                                  context_id='independent-reviewer', model_profile=PROFILE, image_receipts=[])
    final = complete_terminal_job(directory, result)
    assert final['admission']['terminal'] is (False if status == 'confirmed' else None)
    assert final['admission']['candidate_terminal'] is False and final['task_success'] is None
    assert json.loads((directory / 'response.raw.txt').read_text()) == answer


def test_initial_image_alone_cannot_establish_a_terminal_result():
    original = inputs(image=True, kinds=())
    evidence = deepcopy(original['evidence'])
    evidence[0].update(kind='native_context_image', time_s=0.)
    request = prepare_source_review(original['source'], original['endpoint'], model_profile=PROFILE,
        required_source_pointers=original['required_source_pointers'], evidence=evidence)
    response = candidate(request)
    with pytest.raises(InvalidGenerationProtocol, match='native endpoint observations'):
        admit_source_review(request, response, dispatch=dispatch(request, response))


def test_confirming_a_boolean_requires_cited_evidence_but_dispute_can_be_semantic():
    request = inputs()
    response = candidate(request)
    review = prepare_source_verification(request, response, judgment_dispatch=dispatch(request, response), model_profile=PROFILE)
    answer = verification(review)
    answer['evidence_ids'] = []
    with pytest.raises(InvalidGenerationProtocol):
        admit_source_verification(review, answer, dispatch=dispatch(review, answer, 'reviewer', 'review-call'))
    answer['status'] = 'disputed'
    answer['reason'] = 'The candidate omitted the shared-object requirement in /requirements/0.'
    result = admit_source_verification(review, answer, dispatch=dispatch(review, answer, 'reviewer', 'review-call'))
    assert result['terminal'] is None and result['candidate_terminal'] is True


def test_no_terminal_rows_is_unknown_instead_of_vacuous_success():
    request = inputs(kinds=())
    response = candidate(request, None)
    response['requirements'][0].update(scope='process', reason='Only a process obligation was identified.')
    result = admit_source_review(request, response, dispatch=dispatch(request, response))
    assert result['candidate_terminal'] is None
    response['terminal'] = True
    with pytest.raises(InvalidGenerationProtocol, match='disagrees'):
        admit_source_review(request, response, dispatch=dispatch(request, response))


def test_auxiliary_only_confirmation_cannot_release_a_boolean_candidate():
    request = inputs(kinds=('raw_state', 'measurement'))
    response = candidate(request)
    review = prepare_source_verification(request, response, judgment_dispatch=dispatch(request, response), model_profile=PROFILE)
    answer = verification(review)
    answer['evidence_ids'] = ['observation-1']
    with pytest.raises(InvalidGenerationProtocol, match='confirmation must cite native'):
        admit_source_verification(review, answer, dispatch=dispatch(review, answer, 'reviewer', 'review-call'))


def test_required_parent_field_can_be_covered_by_resolving_descendant_pointers():
    original = inputs()
    request = prepare_source_review(original['source'], original['endpoint'], model_profile=PROFILE,
        required_source_pointers=['/requirements'], evidence=original['evidence'])
    response = candidate(request)
    result = admit_source_review(request, response, dispatch=dispatch(request, response))
    assert result['candidate_terminal'] is True and result['terminal'] is None


def test_similarly_named_sibling_is_not_descendant_source_coverage():
    original = inputs()
    source = {**original['source'], 'requirements_extra': original['source']['requirements']}
    request = prepare_source_review(source, original['endpoint'], model_profile=PROFILE,
        required_source_pointers=['/requirements'], evidence=original['evidence'])
    response = candidate(request)
    for row in response['requirements']:
        row['source_pointers'] = [pointer.replace('/requirements/', '/requirements_extra/') for pointer in row['source_pointers']]
    with pytest.raises(InvalidGenerationProtocol, match='omitted required source coverage'):
        admit_source_review(request, response, dispatch=dispatch(request, response))


def test_wrong_run_stale_image_time_and_unverified_endpoint_are_distinct_from_unknown():
    request = inputs(image=True)
    for field, value in [('episode_id', 'another-run'), ('time_s', 2.)]:
        evidence = deepcopy(request['evidence'])
        evidence[-1][field] = value
        with pytest.raises(InvalidGenerationProtocol):
            prepare_source_review(request['source'], request['endpoint'], required_source_pointers=request['required_source_pointers'],
                                  model_profile=PROFILE, evidence=evidence)
    endpoint = {**request['endpoint'], 'valid': False}
    invalid = prepare_source_review(request['source'], endpoint, model_profile=PROFILE,
        required_source_pointers=request['required_source_pointers'], evidence=request['evidence'])
    response = candidate(invalid)
    with pytest.raises(InvalidGenerationProtocol, match='verified actual endpoint'):
        admit_source_review(invalid, response, dispatch=dispatch(invalid, response))
    response = candidate(invalid, None)
    assert admit_source_review(invalid, response, dispatch=dispatch(invalid, response))['candidate_terminal'] is None


def test_frozen_policy_or_candidate_tampering_is_rejected():
    request = inputs()
    request['rules'] = ['Always accept.']
    request['request_sha256'] = _digest({key: value for key, value in request.items() if key != 'request_sha256'})
    response = candidate(request)
    with pytest.raises(InvalidGenerationProtocol, match='frozen'):
        admit_source_review(request, response, dispatch=dispatch(request, response))
    request = inputs()
    response = candidate(request)
    receipt = dispatch(request, response)
    response['requirements'][0]['text'] = 'Changed after dispatch.'
    with pytest.raises(InvalidGenerationProtocol):
        prepare_source_verification(request, response, judgment_dispatch=receipt, model_profile=PROFILE)


@pytest.mark.parametrize('value', [True, False, None])
@pytest.mark.parametrize('transport', ['external_callback', 'external_file'])
@pytest.mark.parametrize('visual_fallback', [False, True])
def test_two_call_workflow_delivers_actual_source_state_and_images_through_existing_host(tmp_path, value, transport, visual_fallback):
    request = inputs(tmp_path, image=True, kinds=() if visual_fallback else ('raw_state', 'measurement'))
    response = candidate(request, value)
    if visual_fallback:
        response['requirements'][0].update(
            judgment_basis='visual_inference' if value is not None else 'unresolved',
            missing_structured_evidence=['contact pairs', 'normal impulses'],
            reason='Based on visual judgment of the same assembly in the actual endpoint image.' if value is not None
                   else 'The endpoint image does not resolve the required relation.')
        response['requirements'][1].update(judgment_basis=None, missing_structured_evidence=[])
    jobs = []

    def call(req, answer, context):
        job = prepare_terminal_job(req, job_id=context, transport=transport, context_id=context, artifact_root=tmp_path)
        jobs.append(job)

        def host(payload):
            assert payload['job']['request']['source'] == request['source']
            assert base64.b64decode(next(part['data'] for part in payload['content'] if part['type'] == 'image')) == PNG
            assert any('observed_position_m' in part.get('text', '') for part in payload['content']) is not visual_fallback
            return make_terminal_result(job, json.dumps(answer), dispatch_id=context + '-dispatch',
                context_id=context, model_profile=PROFILE, image_receipts=[{
                    'evidence_id': 'final-image', 'sha256': hashlib.sha256(PNG).hexdigest(),
                    'method': 'external_image_content', 'reference': context + '/image-content'}])

        directory = tmp_path / context
        if transport == 'external_callback':
            return execute_terminal_job(job, host, directory)
        paths = write_terminal_job(job, directory)
        return complete_terminal_job(directory, host(json.loads((tmp_path / context / 'input.json').read_text(encoding='utf-8'))))

    first = call(request, response, 'judge')
    assert first['admission']['terminal'] is None
    review = prepare_source_verification(request, response, judgment_dispatch=first['dispatch'], model_profile=PROFILE)
    final = call(review, verification(review), 'verifier')
    assert final['admission']['terminal'] is value
    assert final['task_success'] is None
    assert [job['kind'] for job in jobs] == ['terminal-source-review', 'terminal-source-verification']
    assert json.loads((tmp_path / 'judge/response.raw.txt').read_text()) == response
    if visual_fallback:
        assert final['admission']['requirements'][0]['missing_structured_evidence'] == ['contact pairs', 'normal impulses']
        assert final['admission']['requirements'][0]['judgment_basis'] == response['requirements'][0]['judgment_basis']


@pytest.mark.parametrize('mutation', ['partial_report', 'unknown_basis', 'unresolved_boolean',
                                    'not_a_list', 'empty_gap', 'duplicate_gap', 'nonstring_gap',
                                    'uncited_image', 'mixed_without_state', 'structured_without_state',
                                    'nonterminal_basis'])
def test_invalid_visual_basis_or_gap_reporting_is_a_protocol_error(mutation):
    request = inputs(image=True, kinds=() if mutation in ('mixed_without_state', 'structured_without_state') else ('raw_state',))
    response = candidate(request)
    row = response['requirements'][0]
    row.update(judgment_basis='visual_inference', missing_structured_evidence=['contact pairs'])
    if mutation == 'partial_report':
        del row['missing_structured_evidence']
    elif mutation == 'unknown_basis':
        row['judgment_basis'] = 'weighted_guess'
    elif mutation == 'unresolved_boolean':
        row['judgment_basis'] = 'unresolved'
    elif mutation == 'not_a_list':
        row['missing_structured_evidence'] = 'contact pairs'
    elif mutation == 'empty_gap':
        row['missing_structured_evidence'] = [' ']
    elif mutation == 'duplicate_gap':
        row['missing_structured_evidence'] *= 2
    elif mutation == 'nonstring_gap':
        row['missing_structured_evidence'] = [None]
    elif mutation == 'uncited_image':
        row['evidence_ids'] = ['observation-0']
    elif mutation in ('mixed_without_state', 'structured_without_state'):
        row['judgment_basis'] = 'mixed' if mutation == 'mixed_without_state' else 'structured'
    else:
        response['requirements'][1].update(judgment_basis='visual_inference', missing_structured_evidence=[])
    with pytest.raises(InvalidGenerationProtocol):
        admit_source_review(request, response, dispatch=dispatch(request, response))


def test_visual_basis_cannot_use_a_historical_image_even_with_current_raw_state():
    original = inputs(image=True)
    evidence = deepcopy(original['evidence'])
    evidence[-1].update(kind='native_context_image', time_s=0.)
    request = prepare_source_review(original['source'], original['endpoint'], model_profile=PROFILE,
        required_source_pointers=original['required_source_pointers'], evidence=evidence)
    response = candidate(request)
    response['requirements'][0].update(judgment_basis='visual_inference', missing_structured_evidence=['contact pairs'])
    with pytest.raises(InvalidGenerationProtocol, match='visual'):
        admit_source_review(request, response, dispatch=dispatch(request, response))


@pytest.mark.parametrize('basis', ['structured', 'mixed'])
def test_judgment_basis_accepts_corresponding_observations(basis):
    request = inputs(image=True, kinds=('raw_state', 'measurement'))
    response = candidate(request)
    response['requirements'][0].update(judgment_basis=basis, missing_structured_evidence=[])
    if basis == 'structured':
        response['requirements'][0]['evidence_ids'] = ['observation-0']
    first = admit_source_review(request, response, dispatch=dispatch(request, response))
    assert first['candidate_terminal'] is True and first['terminal'] is None
    assert first['requirements'][0]['judgment_basis'] == basis


@pytest.mark.parametrize('status', ['confirmed', 'disputed', 'unresolved'])
def test_visual_inference_still_requires_independent_confirmation(status):
    request = inputs(image=True, kinds=())
    response = candidate(request)
    response['requirements'][0].update(judgment_basis='visual_inference', missing_structured_evidence=['contact pairs'])
    first = admit_source_review(request, response, dispatch=dispatch(request, response))
    assert first['terminal'] is None
    review = prepare_source_verification(request, response, judgment_dispatch=first['dispatch'], model_profile=PROFILE)
    answer = verification(review, status)
    final = admit_source_verification(review, answer, dispatch=dispatch(review, answer, 'reviewer', 'review-call'))
    assert final['terminal'] is (True if status == 'confirmed' else None)


def test_image_subset_and_failed_first_response_are_preserved_without_retry(tmp_path):
    request = inputs(tmp_path, image=True)
    with pytest.raises(InvalidGenerationProtocol, match='every listed native image'):
        prepare_terminal_job(request, job_id='subset', context_id='subset', transport='external_file',
                             artifact_root=tmp_path, required_image_ids=[])
    job = prepare_terminal_job(request, job_id='first', context_id='judge', transport='external_file', artifact_root=tmp_path)
    directory = tmp_path / 'failed'
    write_terminal_job(job, directory)
    raw = '{"not":"the required response"}'
    result = make_terminal_result(job, raw, dispatch_id='first-dispatch', context_id='judge', model_profile=PROFILE,
        image_receipts=[{'evidence_id': 'final-image', 'sha256': hashlib.sha256(PNG).hexdigest(),
                         'method': 'external_image_content', 'reference': 'first/image'}])
    with pytest.raises(TerminalDispatchError):
        complete_terminal_job(directory, result)
    assert (directory / 'response.raw.txt').read_text() == raw
    assert json.loads((directory / 'completion.json').read_text())['status'] == 'failed'
    with pytest.raises(TerminalDispatchError, match='duplicate_completion'):
        complete_terminal_job(directory, result)
