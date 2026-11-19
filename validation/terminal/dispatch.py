"""Opt-in file/callback transport for the existing terminal model protocols.

This diagnostic adapter does not own an Agent loop or a model SDK. A Codex host
uses its actual collaboration/view_image tools, or an external caller consumes
the same JSON job and PhysPi-shaped text/image content blocks. The caller supplies
actual execution metadata and per-image context-read attestations. Those records
attest delivery/tool use, not model identity, attention, perception or truth.

Use prepare_terminal_job -> execute_terminal_job(callback), or
prepare_terminal_job -> write_terminal_job -> complete_terminal_job. A directory
has exactly one completion attempt; failed jobs require a fresh job/directory.
Original-task judgment and independent verification protocols own admission.
"""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from validation.protocol import InvalidGenerationProtocol, _json, _keys, _profile, _text, _hash, _digest
from validation.terminal.reviews import _prepared_source, admit_source_review, admit_source_verification
from validation.json_codec import ENCODING, present


_JOB = 'terminal-model-job/0.1'
_INPUT = 'terminal-model-input/0.1'
_RESULT = 'terminal-model-result/0.1'
_COMPLETION = 'terminal-model-completion/0.1'
_TRANSPORTS = ('codex_session', 'external_callback', 'external_file')
_ATTESTATION = 'caller_attested_context_delivery_or_tool_read_not_model_attention_or_visual_accuracy'
_BINDING = ('job_id', 'job_sha256', 'kind', 'mode', 'transport', 'request_sha256',
            'source_sha256', 'endpoint')


class TerminalDispatchError(ValueError):
    """A failed transport/input/admission attempt, distinct from unknown opinions."""

    def __init__(self, stage, reason, receipt=None):
        super().__init__(stage + ': ' + reason)
        self.stage = stage
        self.receipt = deepcopy(receipt)


def _bytes_hash(data):
    return hashlib.sha256(data).hexdigest()


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def _write(path, data):
    with path.open('xb') as stream:
        stream.write(data)
    return {'path': path.name, 'sha256': _bytes_hash(data)}


def _request(request):
    request = _json(request)
    version = request.get('schema_version') if isinstance(request, dict) else None
    if version in ('terminal-source-review-request/0.1', 'terminal-source-verification-request/0.1',
                   'terminal-source-review-request/0.2', 'terminal-source-verification-request/0.2'):
        request = _prepared_source(request)
        kind = 'terminal-source-review' if version.startswith('terminal-source-review-request/') else 'terminal-source-verification'
        return request, kind, request['mode'], request['source'], request['endpoint']
    raise InvalidGenerationProtocol('unsupported terminal model request')


def _file(root, ref):
    _text(ref.get('path'), 'artifact path')
    _hash(ref.get('sha256'), 'artifact hash')
    path = (root / ref['path']).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise InvalidGenerationProtocol('artifact is missing or outside artifact_root: ' + ref['path'])
    data = path.read_bytes()
    if _bytes_hash(data) != ref['sha256']:
        raise InvalidGenerationProtocol('artifact bytes differ from their frozen hash: ' + ref['path'])
    return data


def _mime(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if data.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP':
        return 'image/webp'
    raise InvalidGenerationProtocol('required image has unsupported or missing image bytes')


def prepare_terminal_job(request, *, job_id, transport, context_id, artifact_root,
                         required_image_ids=None, selection_ref=None, evidence_encoding=None):
    """Freeze a transport job and verify selected image/selection-file bytes.

    Images default to all capture_verified evidence. An explicit subset is a
    caller-owned selection: no response may cite an image outside that subset.
    This verifies files, not native capture provenance or selection sufficiency.
    Source hashes are canonical frozen source-record hashes, not file hashes.
    """
    request, kind, mode, source, endpoint = _request(request)
    for value, label in ((job_id, 'job ID'), (context_id, 'context ID')):
        _text(value, label)
    if transport not in _TRANSPORTS:
        raise InvalidGenerationProtocol('unsupported terminal transport')
    if evidence_encoding not in (None, ENCODING):
        raise InvalidGenerationProtocol('unsupported evidence encoding')
    root = Path(artifact_root).resolve()
    if not root.is_dir():
        raise InvalidGenerationProtocol('artifact_root must be an existing directory')
    images = {item['id']: item for item in request.get('evidence', [])
              if item.get('capture_verified') is True}
    ids = list(images) if required_image_ids is None else _json(required_image_ids)
    if (not isinstance(ids, list) or any(not isinstance(item, str) for item in ids)
            or len(set(ids)) != len(ids) or set(ids) - set(images)):
        raise InvalidGenerationProtocol('required image IDs must be a unique subset of native image evidence')
    if set(ids) != set(images):
        raise InvalidGenerationProtocol('source review requires delivery of every listed native image')
    required = []
    for identity in ids:
        item = images[identity]
        data = _file(root, item)
        required.append({'evidence_id': identity, 'path': item['path'], 'sha256': item['sha256'],
                         'mime_type': _mime(data), 'byte_count': len(data)})
    for item in request.get('evidence', []):
        if item.get('capture_verified') is not True:
            _file(root, item)
    selection_ref = _json(selection_ref)
    if selection_ref is not None:
        _keys(selection_ref, ('path', 'sha256'), 'image selection reference')
        _file(root, selection_ref)
    job = {'schema_version': _JOB, 'job_id': job_id, 'kind': kind, 'mode': mode,
           'transport': transport, 'context_id': context_id, 'model_profile': request['model_profile'],
           'request_sha256': request['request_sha256'], 'source_sha256': _digest(source),
           'endpoint': endpoint, 'request': request, 'artifact_root': str(root),
           'required_images': required, 'selection_ref': selection_ref,
           'attestation_scope': _ATTESTATION}
    if evidence_encoding is not None:
        job['evidence_encoding'] = evidence_encoding
    return {**job, 'job_sha256': _digest(job)}


def _job(job):
    job = _json(job)
    encoding = ('evidence_encoding',) if isinstance(job, dict) and 'evidence_encoding' in job else ()
    _keys(job, ('schema_version', 'job_id', 'kind', 'mode', 'transport', 'context_id',
               'model_profile', 'request_sha256', 'source_sha256', 'endpoint', 'request',
               'artifact_root', 'required_images', 'selection_ref', 'attestation_scope',
               'job_sha256') + encoding, 'terminal job')
    if not isinstance(job['required_images'], list):
        raise InvalidGenerationProtocol('required image descriptors must be a list')
    for image in job['required_images']:
        _keys(image, ('evidence_id', 'path', 'sha256', 'mime_type', 'byte_count'), 'required image')
    expected = prepare_terminal_job(job['request'], job_id=job['job_id'], transport=job['transport'],
        context_id=job['context_id'], artifact_root=job['artifact_root'],
        required_image_ids=[item['evidence_id'] for item in job['required_images']],
        selection_ref=job['selection_ref'], evidence_encoding=job.get('evidence_encoding'))
    if job != expected:
        raise InvalidGenerationProtocol('terminal job differs from its frozen request, images or identity')
    return job


def _payload(job):
    content = [{'type': 'text', 'text': _encoded(job).decode('utf-8')}]
    root = Path(job['artifact_root'])
    binary_files = []
    seen = {}
    for item in job['request'].get('evidence', []):
        if item.get('capture_verified') is not True:
            data = _file(root, item)
            try:
                body = data.decode('utf-8')
            except UnicodeDecodeError:
                binary_files.append({'evidence_id': item['id'], 'path': item['path'],
                    'sha256': item['sha256'], 'data': base64.b64encode(data).decode('ascii')})
                body = 'Exact binary bytes are attached in binary_files; no asset decoding or execution was performed.'
            if job.get('evidence_encoding') == ENCODING:
                # Only identical bytes AND matching semantic bindings may share
                # a body. Keep each descriptor/ID/hash as a citeable alias.
                binding = _encoded({key: value for key, value in item.items() if key not in ('id', 'path')})
                if binding in seen:
                    content.append({'type': 'text', 'text': 'Frozen evidence alias: '
                        + _encoded(item).decode('utf-8') + '\nExact same body and semantic binding as evidence '
                        + seen[binding] + '; this ID remains independently citeable.'})
                    continue
                seen[binding] = item['id']
                body = present(body)
            content.append({'type': 'text', 'text': 'Frozen evidence: ' + _encoded(item).decode('utf-8')
                            + '\n' + body})
    for item in job['required_images']:
        data = _file(root, item)
        content.extend([{'type': 'text', 'text': 'Required native image: ' + _encoded(item).decode('utf-8')},
                        {'type': 'image', 'data': base64.b64encode(data).decode('ascii'),
                         'mimeType': item['mime_type']}])
    return {'schema_version': _INPUT, 'job': job, 'content': content, 'binary_files': binary_files}


def input_summary(payload):
    """Exact input sizes, not tokenizer estimates, quotas or billing."""
    text = [part['text'] for part in payload['content'] if part['type'] == 'text']
    images = [part for part in payload['content'] if part['type'] == 'image']
    return {'schema_version': 'terminal-input-size/0.1',
        'text_characters': sum(map(len, text)), 'text_utf8_bytes': sum(len(item.encode('utf-8')) for item in text),
        'image_count': len(images), 'image_bytes': sum(len(base64.b64decode(item['data'])) for item in images),
        'binary_file_count': len(payload['binary_files']), 'scope': 'input_sizes_not_token_usage'}


def write_terminal_job(job, output_dir, *, max_text_characters=None, max_images=None):
    """Write a fresh job and executable external input; never call Codex tools.

    input.json content uses the shape consumed by PhysPi Agent tools:
    {type:'text',text:...} and {type:'image',data:<base64>,mimeType:...}.
    Non-UTF8 evidence bytes (for example source archives) are in binary_files;
    the external host owns their resource tooling, never automatic execution.
    A Codex host instead views each required_images path with its actual image
    tool and records the returned tool-call reference in its result. The host
    must enforce a fresh context and the requested model/reasoning configuration.
    """
    job = _job(job)
    payload = _payload(job)
    summary = input_summary(payload)
    for value, field in ((max_text_characters, 'text_characters'), (max_images, 'image_count')):
        if value is not None and (type(value) is not int or value < 0):
            raise InvalidGenerationProtocol('input size limits must be nonnegative integers')
        if value is not None and summary[field] > value:
            raise InvalidGenerationProtocol('terminal input budget exceeded: ' + field)
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=False)
    refs = {'job': _write(directory / 'job.json', _encoded(job)),
            'input': _write(directory / 'input.json', _encoded(payload))}
    _write(directory / 'prepared.json', _encoded({'job_sha256': job['job_sha256'], **refs}))
    _write(directory / 'input-summary.json', _encoded(summary))
    return {'job_path': str(directory / 'job.json'), 'input_path': str(directory / 'input.json')}


def make_terminal_result(job, raw_response, *, dispatch_id, context_id, model_profile,
                         image_receipts):
    """Format caller-supplied execution facts; this function does not attest them.

    Each image receipt is {evidence_id, sha256, method, reference}. method is
    codex_view_image for a real Codex tool read, or external_image_content for
    the external adapter's actual context delivery. reference identifies that
    tool call/message, not a model's assertion that it looked at the image.
    """
    return {'schema_version': _RESULT, **{key: deepcopy(job[key]) for key in _BINDING},
            'dispatch_id': dispatch_id, 'context_id': context_id,
            'model_profile': deepcopy(model_profile), 'raw_response': raw_response,
            'image_receipts': deepcopy(image_receipts)}


def _read_receipts(job, receipts):
    expected = {item['evidence_id']: item for item in job['required_images']}
    if not isinstance(receipts, list):
        raise InvalidGenerationProtocol('per-image context read receipts must be a list')
    seen = set()
    method = 'codex_view_image' if job['transport'] == 'codex_session' else 'external_image_content'
    for receipt in receipts:
        _keys(receipt, ('evidence_id', 'sha256', 'method', 'reference'), 'image read receipt')
        identity = receipt['evidence_id']
        if not isinstance(identity, str) or identity in seen or identity not in expected:
            raise InvalidGenerationProtocol('duplicate or foreign image read receipt')
        seen.add(identity)
        if receipt['sha256'] != expected[identity]['sha256'] or receipt['method'] != method:
            raise InvalidGenerationProtocol('image read hash or transport method mismatch')
        _text(receipt['reference'], 'actual image tool/message reference')
    if seen != set(expected):
        raise InvalidGenerationProtocol('missing mandatory image context read receipt')


def _admit(job, response, dispatch):
    request = job['request']
    if job['kind'] == 'terminal-source-review':
        admitted = admit_source_review(request, response, dispatch=dispatch)
        rows = response['requirements']
    elif job['kind'] == 'terminal-source-verification':
        admitted = admit_source_verification(request, response, dispatch=dispatch)
        rows = [response]
    else:
        raise InvalidGenerationProtocol('unsupported terminal model job')
    # The protocol whitelist can contain unselected pictures. Their citations
    # cannot become determinate/unknown findings without a context-read record.
    unread = {item['id'] for item in request['evidence'] if item.get('capture_verified') is True}
    unread -= {item['evidence_id'] for item in job['required_images']}
    if any(unread.intersection(row['evidence_ids']) for row in rows):
        raise InvalidGenerationProtocol('response cites an image that was not selected and context-read')
    return 'valid', admitted


def _claim(directory):
    try:
        _write(directory / 'completion.claim', b'one completion attempt\n')
    except FileExistsError as error:
        raise TerminalDispatchError('duplicate_completion', 'job already has a completion attempt') from error


def _failed(directory, job, stage, error):
    job = job if isinstance(job, dict) else {}
    response_refs = {}
    for field, filename in (('raw_response_ref', 'response.raw.txt'), ('response_ref', 'response.json'),
                            ('result_ref', 'result.json')):
        path = directory / filename
        response_refs[field] = {'path': filename, 'sha256': _bytes_hash(path.read_bytes())} if path.is_file() else None
    receipt = {'schema_version': _COMPLETION, 'status': 'failed',
               **{key: deepcopy(job.get(key)) for key in (*_BINDING, 'model_profile', 'context_id')},
               **response_refs, 'failure': {'stage': stage,
                   'type': type(error).__name__, 'reason': str(error)},
               'task_success': None, 'attestation_scope': _ATTESTATION}
    _write(directory / 'completion.json', _encoded(receipt))
    return TerminalDispatchError(stage, str(error), receipt)


def complete_terminal_job(output_dir, result):
    """Admit one result with exact binding and all mandatory read attestations.

    Raw response UTF-8 bytes are retained even when JSON/protocol admission
    fails. Valid unknown judgments and unresolved verifications remain protocol
    results; missing read receipts are failed delivery, never physical unknown.
    """
    directory = Path(output_dir)
    _claim(directory)
    job, stage = {}, 'prepared_input'
    try:
        raw = result.get('raw_response') if isinstance(result, dict) else None
        raw_ref = _write(directory / 'response.raw.txt', raw.encode('utf-8')) if isinstance(raw, str) else None
        job_bytes = (directory / 'job.json').read_bytes()
        input_bytes = (directory / 'input.json').read_bytes()
        prepared = json.loads((directory / 'prepared.json').read_text(encoding='utf-8'))
        job = json.loads(job_bytes)
        if (prepared['job']['sha256'] != _bytes_hash(job_bytes)
                or prepared['input']['sha256'] != _bytes_hash(input_bytes)
                or prepared['job_sha256'] != job['job_sha256']):
            raise InvalidGenerationProtocol('prepared job/input bytes changed after dispatch')
        job = _job(job)
        if json.loads(input_bytes) != _payload(job):
            raise InvalidGenerationProtocol('input content differs from the frozen job and evidence bytes')
        stage = 'result_binding'
        result = _json(result)
        result_ref = _write(directory / 'result.json', _encoded(result))
        _keys(result, ('schema_version', *_BINDING, 'dispatch_id', 'context_id', 'model_profile',
                       'raw_response', 'image_receipts'), 'terminal model result')
        if result['schema_version'] != _RESULT or any(result[key] != job[key] for key in _BINDING):
            raise InvalidGenerationProtocol('result belongs to a foreign job, source, endpoint, mode or transport')
        _text(result['dispatch_id'], 'actual dispatch ID')
        if result['context_id'] != job['context_id'] or _profile(result['model_profile']) != job['model_profile']:
            raise InvalidGenerationProtocol('actual context/model differs from requested execution')
        stage = 'image_context_read'
        _read_receipts(job, result['image_receipts'])
        stage = 'response_protocol'
        _text(raw, 'raw response')
        response = _json(json.loads(raw))
        response_ref = _write(directory / 'response.json', _encoded(response))
        dispatch = {'schema_version': 'terminal-spec-model-dispatch/0.1',
                    'dispatch_id': result['dispatch_id'], 'context_id': result['context_id'],
                    'model_profile': result['model_profile'], 'request_sha256': job['request_sha256'],
                    'response_sha256': _digest(response)}
        stage = 'admission'
        admission_status, admission = _admit(job, response, dispatch)
        receipt = {'schema_version': _COMPLETION, 'status': 'completed',
            **{key: deepcopy(job[key]) for key in _BINDING},
            'dispatch': dispatch, 'image_receipts': result['image_receipts'],
            'selection_ref': job['selection_ref'], 'admission_status': admission_status,
            'admission': admission, 'raw_response_ref': raw_ref, 'response_ref': response_ref,
            'result_ref': result_ref, 'attestation_scope': _ATTESTATION, 'task_success': None}
        _write(directory / 'completion.json', _encoded(receipt))
        return receipt
    except Exception as error:
        raise _failed(directory, job, stage, error) from error


def execute_terminal_job(job, callback, output_dir):
    """Call one host-owned callable with real text/image content, then admit it.

    The callable may invoke a configured PhysPi session, another external model
    host, or a command through stdin JSON. No SDK, provider registry, retry or
    collaboration implementation is supplied here. Callback exceptions are
    archived as transport failures and never converted to unknown opinions.
    """
    if job.get('transport') != 'external_callback' or not callable(callback):
        raise InvalidGenerationProtocol('execute requires external_callback and a callable')
    paths = write_terminal_job(job, output_dir)
    try:
        result = callback(json.loads(Path(paths['input_path']).read_text(encoding='utf-8')))
    except Exception as error:
        directory = Path(output_dir)
        _claim(directory)
        raise _failed(directory, job, 'transport', error) from error
    return complete_terminal_job(output_dir, result)
