"""Provider-free cost controls: exact round-trip, call counts and admission gates.

Authored responses and real file transport exercise the reusable local runner.
These checks measure representation/call savings, never physics or model accuracy.
"""

from copy import deepcopy
import hashlib
import json

import pytest

from validation.json_codec import _encode, _text, decode, present, ENCODING
from validation.terminal.dispatch import prepare_terminal_job, write_terminal_job, complete_terminal_job, make_terminal_result
from validation.terminal.source_run import prepare_source_run, execute_source_run
from validation.tests.fixtures.source_reviews import inputs, candidate, verification, dispatch, PROFILE
from validation.protocol import InvalidGenerationProtocol
from validation.terminal.reviews import prepare_source_verification, prepare_source_review


@pytest.mark.parametrize('value', [
    {'mixed': [1, 1., True, None, -0., '1'], 'empty': [[], {}, '', 0]},
    {'$constant': {'count': 3, 'value': 7}, '$literal': {'$records': []}},
    [{'step': i, 'time_s': i * .01, 'pose': [1., 0., -0.], 'velocity': [0., 0., i * .1],
      'contact': None if i % 3 else {'normal_impulse': .003}} for i in range(101)],
    [{'a': None}, {'a': 3}, {'other': 7}],
    [[[], []], [[], []]], [{}, {}, {}],
])
def test_lossless_roundtrip_preserves_types_nulls_velocities_and_order(value):
    before = deepcopy(value)
    assert _text(decode(_encode(value))) == _text(value)
    assert _text(value) == _text(before)


def test_columnar_constants_shrink_repeated_native_rows_without_changing_tiny_or_non_json_inputs():
    value = [{'step': i, 'time_s': i * .01, 'solvers': {'2': {'positions': [[0., 1., 2.]] * 12,
        'orientations': [[1., 0., 0., 0.]] * 12, 'velocity': [i / 1000, None]}}} for i in range(101)]
    raw = _text(value)
    compact = present(raw)
    assert len(compact) < len(raw) * .3
    assert _text(decode(json.loads(compact.split('\n', 1)[1]))) == raw
    for body in ('{"small":1}', '<xml source="unchanged"/>', '{"x":1,"x":2}', '[NaN,Infinity]'):
        assert present(body) == body


def test_opt_in_dispatch_deduplicates_only_same_bytes_and_binding_and_keeps_legacy_exact(tmp_path):
    request = inputs(tmp_path)
    original = request['evidence'][0]
    data = _text([{'step': i, 'name': 'the_same_recorded_body', 'position_m': [0., 0., 1.]} for i in range(101)]).encode()
    (tmp_path / original['path']).write_bytes(data)
    original['sha256'] = hashlib.sha256(data).hexdigest()
    evidence = [original, {**original, 'id': 'exact-alias'}, {**original, 'id': 'other-kind', 'kind': 'measurement'}]
    request = prepare_source_review(request['source'], request['endpoint'], model_profile=PROFILE,
        required_source_pointers=request['required_source_pointers'], evidence=evidence)
    jobs = []
    for encoding, name in ((None, 'raw'), (ENCODING, 'packed')):
        job = prepare_terminal_job(request, job_id=name, transport='external_file', context_id=name,
                                   artifact_root=tmp_path, evidence_encoding=encoding)
        write_terminal_job(job, tmp_path / name)
        payload = json.loads((tmp_path / name / 'input.json').read_text(encoding='utf-8'))
        jobs.append((job, payload))
    assert 'evidence_encoding' not in jobs[0][0]
    assert all(part['text'].endswith(data.decode()) for part in jobs[0][1]['content'][1:])
    bodies = jobs[1][1]['content'][1:]
    assert len(bodies) == 3 and 'Frozen evidence alias' in bodies[1]['text']
    assert 'Lossless JSON presentation' in bodies[0]['text'] and 'Lossless JSON presentation' in bodies[2]['text']
    assert sum(len(p['text']) for p in bodies) < sum(len(p['text']) for p in jobs[0][1]['content'][1:]) * .5
    answer = candidate(request)
    result = make_terminal_result(jobs[1][0], json.dumps(answer), dispatch_id='packed-call', context_id='packed',
                                 model_profile=PROFILE, image_receipts=[])
    assert complete_terminal_job(tmp_path / 'packed', result)['admission']['candidate_terminal'] is True


def test_budget_exceeded_before_output_or_host_and_no_silent_truncation(tmp_path):
    request = inputs(tmp_path, image=True)
    job = prepare_terminal_job(request, job_id='budget', transport='external_file', context_id='budget', artifact_root=tmp_path)
    for limit in ({'max_text_characters': 1}, {'max_images': 0}):
        with pytest.raises(InvalidGenerationProtocol, match='budget exceeded'):
            write_terminal_job(job, tmp_path / 'never', **limit)
        assert not (tmp_path / 'never').exists()


def test_skip_unknown_requires_valid_protocol_and_explicit_opt_in():
    request = inputs()
    response = candidate(request, None)
    kwargs = dict(judgment_dispatch=dispatch(request, response), model_profile=PROFILE)
    assert prepare_source_verification(request, response, **kwargs) is not None
    assert prepare_source_verification(request, response, review_unknown=False, **kwargs) is None
    response['requirements'].pop()
    kwargs['judgment_dispatch'] = dispatch(request, response)
    with pytest.raises(InvalidGenerationProtocol, match='coverage'):
        prepare_source_verification(request, response, review_unknown=False, **kwargs)


def file_host(value, calls, *, status='confirmed', malformed=False):
    def invoke(input_path, output_path):
        job = json.loads(input_path.read_text(encoding='utf-8'))['job']
        calls.append(job)
        request = job['request']
        answer = candidate(request, value) if job['kind'] == 'terminal-source-review' else verification(request, status)
        if malformed:
            answer['requirements'].pop()
        result = make_terminal_result(job, json.dumps(answer), dispatch_id=job['job_id'] + '/actual',
            context_id=job['context_id'], model_profile=job['model_profile'], image_receipts=[{
                'evidence_id': item['evidence_id'], 'sha256': item['sha256'], 'method': 'external_image_content',
                'reference': job['job_id'] + '/image/' + str(i)} for i, item in enumerate(job['required_images'])])
        output_path.write_text(json.dumps(result), encoding='utf-8')
    return invoke


@pytest.mark.parametrize('value,diagnostic,review_status,call_count,final', [
    (None, False, 'confirmed', 1, None), (None, True, 'confirmed', 2, None),
    (True, False, 'confirmed', 2, True), (False, False, 'confirmed', 2, False),
    (True, False, 'disputed', 2, None), (False, False, 'unresolved', 2, None),
])
def test_local_pair_call_counts_and_independent_release(tmp_path, value, diagnostic, review_status, call_count, final):
    directory = tmp_path / 'run'
    prepare_source_run(inputs(tmp_path, image=True), tmp_path, directory, verification_model_profile=PROFILE,
                       review_unknown=diagnostic)
    calls = []
    result = execute_source_run(directory, file_host(value, calls, status=review_status))
    assert len(calls) == call_count and result['terminal'] is final
    assert result['status'] == ('judgment_unknown' if call_count == 1 else 'completed')
    assert result['review_status'] == ('unknown_not_reviewed' if call_count == 1 else review_status)
    assert result['review_performed'] is (call_count == 2) and result['task_success'] is None
    if call_count == 2:
        assert calls[0]['context_id'] != calls[1]['context_id']
    assert execute_source_run(directory, lambda *_: pytest.fail('saved result must never call host')) == result


def test_protocol_error_is_execution_failure_even_when_candidate_is_null(tmp_path):
    directory = tmp_path / 'invalid'
    prepare_source_run(inputs(tmp_path), tmp_path, directory, verification_model_profile=PROFILE)
    calls = []
    result = execute_source_run(directory, file_host(None, calls, malformed=True))
    assert len(calls) == 1 and result['status'] == 'execution_failed'
    assert result['review_status'] != 'unknown_not_reviewed'


def test_host_failure_preserves_unreported_cost_and_never_retries(tmp_path):
    directory = tmp_path / 'failure'
    prepare_source_run(inputs(tmp_path), tmp_path, directory, verification_model_profile=PROFILE)
    def fail(input_path, output_path):
        output_path.write_text('{"schema_version":"physpi-terminal-call-failure/0.1","code":"INCOMPLETE"}', encoding='utf-8')
        raise RuntimeError('host failed')
    result = execute_source_run(directory, fail)
    assert result['status'] == 'execution_failed' and result['review_performed'] is False
    assert execute_source_run(directory, lambda *_: pytest.fail('failed call must not retry')) == result


def test_interrupted_attempt_is_never_rebilled(tmp_path):
    directory = tmp_path / 'resume'
    prepare_source_run(inputs(tmp_path), tmp_path, directory, verification_model_profile=PROFILE)
    (directory / 'judge/physpi-model-call.claim').write_text('interrupted', encoding='utf-8')
    result = execute_source_run(directory, lambda *_: pytest.fail('interrupted call must not retry'))
    assert result['status'] == 'execution_failed' and 'no automatic retry' in result['reason']


def test_completed_judgment_stage_is_revalidated_and_reused_without_host_call(tmp_path):
    from validation.terminal.source_run import _call
    directory = tmp_path / 'resume-completed'
    prepare_source_run(inputs(tmp_path), tmp_path, directory, verification_model_profile=PROFILE)
    calls = []
    first = _call(directory / 'judge', file_host(True, calls))
    assert first['admission']['candidate_terminal'] is True and len(calls) == 1
    result = execute_source_run(directory, file_host(True, calls))
    assert result['terminal'] is True and len(calls) == 2
    assert calls[-1]['kind'] == 'terminal-source-verification'


def test_completion_tamper_stops_resume_before_any_new_host_call(tmp_path):
    from validation.terminal.source_run import _call
    directory = tmp_path / 'tamper'
    prepare_source_run(inputs(tmp_path), tmp_path, directory, verification_model_profile=PROFILE)
    _call(directory / 'judge', file_host(True, []))
    path = directory / 'judge/completion.json'
    receipt = json.loads(path.read_text(encoding='utf-8'))
    receipt['admission']['candidate_terminal'] = False
    path.write_text(json.dumps(receipt), encoding='utf-8')
    result = execute_source_run(directory, lambda *_: pytest.fail('tampered stage must not invoke host'))
    assert result['status'] == 'execution_failed' and 'admission changed' in result['reason']


@pytest.mark.parametrize('target', ['judge/input.json', 'observation-0.json', 'judge/response.json'])
def test_saved_final_result_rechecks_input_evidence_and_response_bytes(tmp_path, target):
    directory = tmp_path / 'final-tamper'
    prepare_source_run(inputs(tmp_path), tmp_path, directory, verification_model_profile=PROFILE)
    execute_source_run(directory, file_host(True, []))
    path = tmp_path / target if target == 'observation-0.json' else directory / target
    path.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError):
        execute_source_run(directory, lambda *_: pytest.fail('changed saved files cannot invoke host'))
