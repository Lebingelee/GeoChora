"""Real file/callback transport checks with synthetic terminal model responses.

The oracle is exact delivered bytes, request identity and rejection of missing
read attestations. A real stdin subprocess consumes PhysPi-shaped image content.
No fixture asserts that a model ran, attended to images or judged physics well.
"""

from validation.tests.fixtures.source_reviews import PNG
import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from validation.terminal.dispatch import TerminalDispatchError, complete_terminal_job, execute_terminal_job, make_terminal_result, prepare_terminal_job, write_terminal_job


from validation.tests.fixtures.source_reviews import inputs as source_inputs, candidate as response_for
from validation.protocol import InvalidGenerationProtocol
from validation.terminal.reviews import prepare_source_review

PROFILE = {'name': 'synthetic-transport-contract-fixture', 'reasoning_effort': 'none'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def request_files(tmp_path, mode='visual', count=2):
    original = source_inputs(tmp_path)
    evidence = []
    for index in range(count if mode == 'visual' else 1):
        data = PNG if mode == 'visual' else b'{"position":[0,0,1],"scope":"synthetic-test"}'
        path = tmp_path / (f'image-{index}.png' if mode == 'visual' else 'state.json')
        path.write_bytes(data)
        item = {**deepcopy(original['evidence'][0]), 'id': f'observation-{index}',
                'path': path.name, 'sha256': sha(data)}
        if mode == 'visual':
            item.update(kind='native_image', capture_verified=True, time_s=original['endpoint']['time_s'], view_id=str(index))
        evidence.append(item)
    return prepare_source_review(original['source'], original['endpoint'], model_profile=PROFILE,
        evidence=evidence, required_source_pointers=original['required_source_pointers'])


def job_for(tmp_path, request=None, transport='external_callback', **kwargs):
    return prepare_terminal_job(request or request_files(tmp_path), job_id='fixture-job',
        transport=transport, context_id='fixture-isolated-context', artifact_root=tmp_path, **kwargs)


def result_for(job, response=None):
    if response is None:
        response = response_for(job['request'], None)
    method = 'codex_view_image' if job['transport'] == 'codex_session' else 'external_image_content'
    return make_terminal_result(job, json.dumps(response, ensure_ascii=False),
        dispatch_id='synthetic-execution-' + job['job_id'], context_id=job['context_id'],
        model_profile=job['model_profile'], image_receipts=[{
            'evidence_id': item['evidence_id'], 'sha256': item['sha256'],
            'method': method, 'reference': f'synthetic-context-input:{index}',
        } for index, item in enumerate(job['required_images'])])


@pytest.mark.parametrize('transport', ['codex_session', 'external_callback', 'external_file'])
def test_all_transports_share_exact_job_result_and_keep_unknown_distinct_from_failure(tmp_path, transport):
    job = job_for(tmp_path, transport=transport)
    directory = tmp_path / 'dispatch'
    calls = []

    def caller(payload):
        calls.append(payload)
        images = [item for item in payload['content'] if item['type'] == 'image']
        assert len(images) == 2
        assert all(set(item) == {'type', 'data', 'mimeType'} and item['mimeType'] == 'image/png'
                   and base64.b64decode(item['data'], validate=True) == PNG for item in images)
        assert json.loads(payload['content'][0]['text']) == job
        return result_for(payload['job'])

    if transport == 'external_callback':
        completed = execute_terminal_job(job, caller, directory)
        assert len(calls) == 1
    else:
        paths = write_terminal_job(job, directory)
        completed = complete_terminal_job(directory, caller(json.loads(Path(paths['input_path']).read_text(encoding='utf-8'))))
    assert completed['status'] == 'completed' and completed['admission_status'] == 'valid'
    assert completed['admission']['candidate_terminal'] is None
    assert completed['task_success'] is None
    assert 'not_model_attention' in completed['attestation_scope']
    raw = (directory / 'response.raw.txt').read_bytes()
    assert completed['raw_response_ref']['sha256'] == sha(raw)
    assert json.loads(raw) == response_for(job['request'], None)
    assert json.loads((directory / 'completion.json').read_text()) == completed


def test_structured_callback_receives_verified_evidence_text_not_just_local_paths(tmp_path):
    request = request_files(tmp_path, 'structured')
    job = job_for(tmp_path, request)

    def caller(payload):
        assert len(payload['content']) == 2
        assert all(item['type'] == 'text' for item in payload['content'])
        assert '"position":[0,0,1]' in payload['content'][1]['text']
        return result_for(payload['job'], response_for(request, True))

    completed = execute_terminal_job(job, caller, tmp_path / 'dispatch')
    assert completed['admission']['candidate_terminal'] is True
    assert completed['image_receipts'] == []


def test_binary_source_assets_reach_external_caller_without_being_decoded_or_executed(tmp_path):
    request = request_files(tmp_path, 'structured')
    archive_bytes = b'PK\x03\x04\xff\x80synthetic-archive'
    (tmp_path / 'asset.zip').write_bytes(archive_bytes)
    item = {**deepcopy(request['evidence'][0]), 'id': 'source-archive', 'kind': 'source_geometry',
            'path': 'asset.zip', 'sha256': sha(archive_bytes)}
    request = prepare_source_review(request['source'], request['endpoint'], model_profile=PROFILE,
        evidence=[*request['evidence'], item], required_source_pointers=request['required_source_pointers'])
    job = job_for(tmp_path, request)

    def caller(payload):
        assert len(payload['binary_files']) == 1
        binary = payload['binary_files'][0]
        assert binary['evidence_id'] == 'source-archive'
        assert base64.b64decode(binary['data'], validate=True) == archive_bytes
        assert binary['sha256'] == sha(archive_bytes)
        assert all(part['type'] == 'text' for part in payload['content'])
        return result_for(payload['job'])

    assert execute_terminal_job(job, caller, tmp_path / 'dispatch')['status'] == 'completed'


@pytest.mark.parametrize('mutation,stage', [
    ('missing_image', 'image_context_read'), ('duplicate_image', 'image_context_read'),
    ('foreign_image', 'image_context_read'), ('foreign_image_hash', 'image_context_read'),
    ('wrong_read_method', 'image_context_read'), ('no_tool_reference', 'image_context_read'),
    ('foreign_job', 'result_binding'), ('foreign_endpoint', 'result_binding'),
    ('foreign_source', 'result_binding'), ('wrong_mode', 'result_binding'),
    ('wrong_transport', 'result_binding'), ('wrong_context', 'result_binding'),
    ('wrong_model', 'result_binding'), ('bad_json', 'response_protocol'),
    ('omitted_atom', 'admission'), ('foreign_response', 'admission'),
])
def test_invalid_result_is_archived_failed_and_cannot_be_unknown_or_retried(tmp_path, mutation, stage):
    job = job_for(tmp_path)
    directory = tmp_path / 'dispatch'
    write_terminal_job(job, directory)
    result = result_for(job)
    if mutation == 'missing_image':
        result['image_receipts'].pop()
    elif mutation == 'duplicate_image':
        result['image_receipts'].append(deepcopy(result['image_receipts'][0]))
    elif mutation == 'foreign_image':
        result['image_receipts'][0]['evidence_id'] = 'some-other-run'
    elif mutation == 'foreign_image_hash':
        result['image_receipts'][0]['sha256'] = '0' * 64
    elif mutation == 'wrong_read_method':
        result['image_receipts'][0]['method'] = 'codex_view_image'
    elif mutation == 'no_tool_reference':
        result['image_receipts'][0]['reference'] = ''
    elif mutation == 'foreign_job':
        result['job_id'] = 'some-other-job'
    elif mutation == 'foreign_endpoint':
        result['endpoint']['endpoint_id'] = 'some-other-endpoint'
    elif mutation == 'foreign_source':
        result['source_sha256'] = '0' * 64
    elif mutation == 'wrong_mode':
        result['mode'] = 'structured'
    elif mutation == 'wrong_transport':
        result['transport'] = 'codex_session'
    elif mutation == 'wrong_context':
        result['context_id'] = 'another-context'
    elif mutation == 'wrong_model':
        result['model_profile']['reasoning_effort'] = 'wrong-effort'
    elif mutation == 'bad_json':
        result['raw_response'] = 'I claim I read all the images.'
    else:
        response = json.loads(result['raw_response'])
        if mutation == 'omitted_atom':
            response['requirements'].pop(0)
        else:
            response['request_sha256'] = '0' * 64
        result['raw_response'] = json.dumps(response)
    with pytest.raises(TerminalDispatchError) as error:
        complete_terminal_job(directory, result)
    assert error.value.stage == stage
    stored = (directory / 'completion.json').read_bytes()
    assert json.loads(stored)['status'] == 'failed'
    assert (directory / 'response.raw.txt').read_text() == result['raw_response']
    assert json.loads(stored)['raw_response_ref']['sha256'] == sha(result['raw_response'].encode('utf-8'))
    with pytest.raises(TerminalDispatchError, match='duplicate_completion'):
        complete_terminal_job(directory, result_for(job))
    assert (directory / 'completion.json').read_bytes() == stored


def test_successful_callback_cannot_be_completed_twice_or_overwritten(tmp_path):
    job = job_for(tmp_path)
    directory = tmp_path / 'dispatch'
    execute_terminal_job(job, lambda payload: result_for(payload['job']), directory)
    completed = (directory / 'completion.json').read_bytes()
    with pytest.raises(TerminalDispatchError, match='duplicate_completion'):
        complete_terminal_job(directory, result_for(job))
    calls = []
    with pytest.raises(FileExistsError):
        execute_terminal_job(job, lambda payload: calls.append(payload), directory)
    assert calls == [] and (directory / 'completion.json').read_bytes() == completed


def test_transport_exception_is_a_failed_call_and_callback_runs_once(tmp_path):
    job = job_for(tmp_path)
    calls = []

    def broken(payload):
        calls.append(payload['job']['job_id'])
        raise TimeoutError('bounded fixture transport timeout')

    directory = tmp_path / 'dispatch'
    with pytest.raises(TerminalDispatchError) as error:
        execute_terminal_job(job, broken, directory)
    assert calls == [job['job_id']] and error.value.stage == 'transport'
    assert json.loads((directory / 'completion.json').read_text())['failure']['type'] == 'TimeoutError'
    assert not (directory / 'response.raw.txt').exists()


@pytest.mark.parametrize('mutation', ['image_bytes', 'job_identity', 'selection_bytes', 'text_evidence'])
def test_changed_input_is_rejected_before_callback(tmp_path, mutation):
    selection = tmp_path / 'selection.json'
    selection.write_bytes(b'{"scope":"caller-selected-test-images"}')
    request = request_files(tmp_path, 'structured' if mutation == 'text_evidence' else 'visual')
    job = job_for(tmp_path, request, selection_ref={'path': selection.name, 'sha256': sha(selection.read_bytes())})
    if mutation == 'image_bytes':
        (tmp_path / 'image-0.png').write_bytes(PNG + b'changed')
    elif mutation == 'job_identity':
        job['mode'] = 'structured'
    elif mutation == 'selection_bytes':
        selection.write_bytes(b'changed')
    else:
        (tmp_path / 'state.json').write_bytes(b'{"invented":true}')
    calls = []
    with pytest.raises(InvalidGenerationProtocol):
        execute_terminal_job(job, lambda payload: calls.append(payload), tmp_path / 'dispatch')
    assert calls == [] and not (tmp_path / 'dispatch').exists()


def test_a_rehashed_input_file_cannot_substitute_foreign_image_content(tmp_path):
    job = job_for(tmp_path)
    directory = tmp_path / 'dispatch'
    write_terminal_job(job, directory)
    payload = json.loads((directory / 'input.json').read_text(encoding='utf-8'))
    payload['content'][-1]['data'] = base64.b64encode(b'foreign-pixels').decode('ascii')
    data = json.dumps(payload).encode('utf-8')
    (directory / 'input.json').write_bytes(data)
    prepared = json.loads((directory / 'prepared.json').read_text())
    prepared['input']['sha256'] = sha(data)
    (directory / 'prepared.json').write_text(json.dumps(prepared))
    with pytest.raises(TerminalDispatchError, match='input content differs') as error:
        complete_terminal_job(directory, result_for(job))
    assert error.value.stage == 'prepared_input'
    assert (directory / 'response.raw.txt').is_file()


def test_source_review_requires_every_listed_image_to_be_delivered(tmp_path):
    request = request_files(tmp_path)
    with pytest.raises(InvalidGenerationProtocol):
        job_for(tmp_path, request, required_image_ids=['observation-1'])





@pytest.mark.parametrize('mutation', ['duplicate', 'foreign', 'empty', 'outside_root'])
def test_invalid_image_requirements_cannot_be_written(tmp_path, mutation):
    request = request_files(tmp_path)
    ids = ['observation-0']
    if mutation == 'duplicate':
        ids *= 2
    elif mutation == 'foreign':
        ids = ['foreign']
    elif mutation == 'empty':
        ids = []
    else:
        outside = tmp_path.parent / (tmp_path.name + '-outside.png')
        outside.write_bytes(PNG)
        request['evidence'][0]['path'] = '../' + outside.name
        request = prepare_source_review(request['source'], request['endpoint'], model_profile=PROFILE,
            evidence=request['evidence'], required_source_pointers=request['required_source_pointers'])
    with pytest.raises(InvalidGenerationProtocol):
        job_for(tmp_path, request, required_image_ids=ids)








# Standalone external caller fixture: stdlib only, no GeoChora/PhysPi import and
# no provider SDK. This is an actual subprocess/stdio boundary, not a model run.
STDIN_CALLER = r'''import base64, hashlib, json, sys
payload = json.loads(sys.stdin.buffer.read().decode('utf-8'))
job = payload['job']
assert payload['schema_version'] == 'terminal-model-input/0.1'
assert job['model_profile']['name'] == 'synthetic-transport-contract-fixture'
images = [part for part in payload['content'] if part['type'] == 'image']
assert len(images) == len(job['required_images'])
receipts = []
for index, (image, expected) in enumerate(zip(images, job['required_images'])):
    assert set(image) == {'type', 'data', 'mimeType'}
    data = base64.b64decode(image['data'], validate=True)
    assert hashlib.sha256(data).hexdigest() == expected['sha256']
    assert len(data) == expected['byte_count'] and image['mimeType'] == expected['mime_type']
    receipts.append({'evidence_id': expected['evidence_id'], 'sha256': expected['sha256'],
        'method': 'external_image_content', 'reference': 'fixture-stdin-decoded-image:' + str(index)})
response = {'schema_version': 'terminal-source-review-response/0.1',
    'request_sha256': job['request_sha256'], 'terminal': None,
    'reason': 'Transport fixture: no model or physics judgment executed.',
    'requirements': [
        {'id': 'placement', 'source_pointers': ['/requirements/0'], 'scope': 'terminal',
         'text': job['request']['source']['requirements'][0], 'value': None,
         'reason': 'Transport fixture: no model or physics judgment executed.', 'evidence_ids': []},
        {'id': 'pictures', 'source_pointers': ['/requirements/1'], 'scope': 'delivery',
         'text': job['request']['source']['requirements'][1], 'value': None,
         'reason': 'Transport fixture: no model or physics judgment executed.', 'evidence_ids': []}]}
result = {'schema_version': 'terminal-model-result/0.1', **{key: job[key] for key in
    ('job_id', 'job_sha256', 'kind', 'mode', 'transport', 'request_sha256', 'source_sha256', 'endpoint')},
    'dispatch_id': 'stdlib-stdin-fixture', 'context_id': job['context_id'],
    'model_profile': job['model_profile'], 'image_receipts': receipts, 'raw_response': json.dumps(response)}
sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
'''


def test_external_stdin_caller_consumes_actual_physpi_shaped_image_content(tmp_path):
    job = prepare_terminal_job(request_files(tmp_path), job_id='外部字节', transport='external_callback',
        context_id='跨进程上下文', artifact_root=tmp_path)
    caller_path = tmp_path / 'external_caller.py'
    caller_path.write_text(STDIN_CALLER, encoding='utf-8')

    def external(payload):
        process = subprocess.run([sys.executable, str(caller_path)], input=json.dumps(payload, ensure_ascii=False),
            text=True, encoding='utf-8', capture_output=True, check=True, timeout=15,
            env={**os.environ, 'PYTHONIOENCODING': 'cp1252'})
        return json.loads(process.stdout)

    completed = execute_terminal_job(job, external, tmp_path / 'dispatch')
    assert completed['status'] == 'completed'
    assert completed['dispatch']['dispatch_id'] == 'stdlib-stdin-fixture'
    assert len(completed['image_receipts']) == 2
    assert all('no model' in row['reason'] for row in completed['admission']['requirements'])
