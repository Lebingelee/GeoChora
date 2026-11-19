"""Independent source_reviews factories; no reference labels or model calls."""
import base64
import hashlib
from validation.terminal.reviews import prepare_source_review
from validation.protocol import _digest
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j6xkAAAAASUVORK5CYII=')


PROFILE = {'name': 'synthetic-source-review-fixture', 'reasoning_effort': 'none'}


def inputs(tmp_path=None, *, image=False, kinds=('raw_state',)):
    source = {'task_id': 'unregistered-synthetic-source', 'requirements': [
        'Either enclosure A or enclosure B must surround the same marked assembly and remain upright.',
        'Deliver two readable images of the result.']}
    endpoint = {'episode_id': 'fixture-run', 'endpoint_id': 'actual-end',
                'asset_family': 'unregistered-lattice-assembly', 'valid': True, 'time_s': 3.}
    evidence = []
    for index, kind in enumerate(kinds):
        data = b'{"synthetic":true,"observed_position_m":[0,0,1]}'
        path = f'observation-{index}.json'
        if tmp_path is not None:
            (tmp_path / path).write_bytes(data)
        evidence.append({'id': f'observation-{index}', 'kind': kind, 'path': path,
            'sha256': hashlib.sha256(data).hexdigest(), 'episode_id': 'fixture-run', 'endpoint_id': 'actual-end'})
    if image:
        if tmp_path is not None:
            (tmp_path / 'final.png').write_bytes(PNG)
        evidence.append({'id': 'final-image', 'kind': 'native_image', 'path': 'final.png',
            'sha256': hashlib.sha256(PNG).hexdigest(), 'episode_id': 'fixture-run', 'endpoint_id': 'actual-end',
            'capture_verified': True, 'time_s': 3., 'view_id': 'front'})
    return prepare_source_review(source, endpoint, model_profile=PROFILE, evidence=evidence,
                                 required_source_pointers=['/requirements/0', '/requirements/1'])


def candidate(request, value=True):
    return {'schema_version': 'terminal-source-review-response/0.1',
        'request_sha256': request['request_sha256'], 'terminal': value, 'reason': 'Synthetic bounded candidate.',
        'requirements': [
            {'id': 'placement', 'source_pointers': ['/requirements/0'], 'scope': 'terminal',
             'text': request['source']['requirements'][0], 'value': value,
             'reason': 'Authored fixture premise preserves the same object and either/or relation.',
             'evidence_ids': [item['id'] for item in request['evidence']] if value is not None else []},
            {'id': 'pictures', 'source_pointers': ['/requirements/1'], 'scope': 'delivery',
             'text': request['source']['requirements'][1], 'value': None,
             'reason': 'Delivery remains separately unevaluated.', 'evidence_ids': []}]}


def dispatch(request, response, context='judge', identity='judge-call'):
    return {'schema_version': 'terminal-spec-model-dispatch/0.1', 'dispatch_id': identity,
        'context_id': context, 'model_profile': request['model_profile'],
        'request_sha256': request['request_sha256'], 'response_sha256': _digest(response)}


def verification(request, status='confirmed'):
    return {'schema_version': 'terminal-source-verification-response/0.1',
        'request_sha256': request['request_sha256'], 'status': status,
        'reason': 'Authored independent check against /requirements/0 and the raw observations.',
        'evidence_ids': [item['id'] for item in request['evidence']]}
