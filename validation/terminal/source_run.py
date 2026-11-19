"""Local paired source review using the existing immutable external-file transport.

Preparation is offline. Execution invokes a caller-selected file host once per
stage, without automatic retries. No SDK or task/provider implementation lives here.
"""
import argparse
import json
from pathlib import Path
import subprocess
import uuid

from validation.terminal import reviews as terminal_reviews
from validation.protocol import InvalidGenerationProtocol, _profile
from validation import protocol
from validation.terminal import dispatch
from validation import json_codec as _terminal_json
from validation.json_codec import ENCODING
from validation.terminal import evidence_views as views
from validation.artifact_io import checked_ref, digest, read_json


def _save(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def _ref(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': digest(path)}


def _check(reference):
    if _ref(reference['path']) != reference:
        raise ValueError('frozen run file changed: ' + reference['path'])


def prepare_source_run(request, artifact_root, output_directory, *, verification_model_profile,
                       review_unknown=False, evidence_encoding=ENCODING,
                       max_text_characters=None, max_images=None, evidence_mode='full'):
    """Prepare offline; full preserves legacy behavior, adaptive allows one expansion.

    catalogued_full is the controlled full-data baseline for adaptive experiments.
    Both use protocol 0.2 and the same hash-bound asset receipt. No SDK is invoked.
    """
    request = terminal_reviews._prepared_source(request)
    if request['schema_version'] not in ('terminal-source-review-request/0.1', 'terminal-source-review-request/0.2'):
        raise InvalidGenerationProtocol('paired run must start with a source judgment request')
    if evidence_mode not in ('full', 'adaptive', 'catalogued_full'):
        raise InvalidGenerationProtocol('unsupported source evidence mode')
    if type(review_unknown) is not bool:
        raise InvalidGenerationProtocol('review_unknown must be boolean')
    profile = _profile(verification_model_profile)
    identity = 'source-run-' + uuid.uuid4().hex
    directory = Path(output_directory).resolve()
    if directory.exists():
        raise FileExistsError('paired source run requires a fresh output directory')
    original_request = request
    view_ref = None
    if evidence_mode != 'full':
        if evidence_mode == 'adaptive' and max_text_characters is None:
            max_text_characters = 250000
        view = views.prepare_evidence_views(artifact_root, request['evidence'], request['endpoint'],
            directory / 'evidence-initial', mode='boundary' if evidence_mode == 'adaptive' else 'full',
            max_characters=max_text_characters or 250000, asset_cache=directory / 'asset-checks')
        view_ref = _ref(directory / 'evidence-initial/index.json')
        original_request = terminal_reviews.prepare_source_review(request['source'],request['endpoint'],
            required_source_pointers=request['required_source_pointers'],model_profile=request['model_profile'],evidence=view['original_evidence'])
        request = terminal_reviews.prepare_source_review(request['source'], request['endpoint'],
            required_source_pointers=request['required_source_pointers'], model_profile=request['model_profile'],
            evidence=view['evidence'], evidence_catalogue=view['catalogue'])
    job = dispatch.prepare_terminal_job(request, job_id=identity + '/judge', transport='external_file',
        context_id=identity + '/judge-context', artifact_root=artifact_root, evidence_encoding=evidence_encoding)
    # The dispatcher checks budgets before creating any output or calling a host.
    dispatch.write_terminal_job(job, directory / 'judge', max_text_characters=max_text_characters, max_images=max_images)
    plan = {'schema_version': 'terminal-source-run/0.1', 'identity': identity,
        'artifact_root': str(Path(artifact_root).resolve()), 'verification_model_profile': profile,
        'review_unknown': review_unknown, 'evidence_encoding': evidence_encoding,
        'evidence_mode': evidence_mode, 'evidence_view': view_ref,
        'original_request': original_request,
        'max_text_characters': max_text_characters, 'max_images': max_images,
        'judge_job': _ref(directory / 'judge/job.json'),
        'implementation': [_ref(path) for path in (Path(__file__), Path(dispatch.__file__),
            Path(_terminal_json.__file__), Path(terminal_reviews.__file__), Path(views.__file__), Path(protocol.__file__))],
        'task_success': None}
    _save(directory / 'run.json', plan)
    return plan


def _expansion(directory, plan, first):
    """Compose a fresh judgment with selected raw observations, never the old answer."""
    index_path = directory / 'evidence-expanded/index.json'
    queries = first['admission']['evidence_requests']
    original = plan['original_request']
    if index_path.exists():
        view = read_json(index_path)
        if (view['original_evidence'] != original['evidence'] or view['endpoint'] != original['endpoint']
                or [item['request'] for item in view['outcomes']] != queries
                or view['projector_sha256'] != _ref(Path(views.__file__))['sha256']):
            raise ValueError('saved expansion differs from frozen source/query')
        for item in view['evidence']:
            checked_ref(Path(plan['artifact_root']), item)
    else:
        view = views.prepare_evidence_views(plan['artifact_root'], original['evidence'], original['endpoint'],
            directory / 'evidence-expanded', mode='expanded', queries=queries,
            max_characters=plan['max_text_characters'] or 250000, asset_cache=directory / 'asset-checks')
    if not view['evidence']:
        return None, view['outcomes']
    boundary = read_json(directory / 'judge/job.json')['request']
    # IDs are unique in the closed protocol. Expanded files retain original IDs
    # in their bodies; the delivery descriptors get distinct citation IDs.
    evidence = [*boundary['evidence'], *[{**item, 'id':item['id'] + '/expanded-' + str(i)}
                                        for i,item in enumerate(view['evidence'])]]
    request = terminal_reviews.prepare_source_review(original['source'], original['endpoint'],
        required_source_pointers=original['required_source_pointers'], model_profile=original['model_profile'],
        evidence=evidence, evidence_catalogue=view['catalogue'], evidence_round=1)
    job = dispatch.prepare_terminal_job(request, job_id=plan['identity'] + '/judge-expanded',
        context_id=plan['identity'] + '/expanded-context', artifact_root=plan['artifact_root'],
        transport='external_file', evidence_encoding=plan['evidence_encoding'])
    target = directory / 'judge-expanded'
    if not target.exists():
        dispatch.write_terminal_job(job, target, max_text_characters=plan['max_text_characters'], max_images=plan['max_images'])
    elif read_json(target / 'job.json') != job:
        raise ValueError('saved expanded judgment job changed')
    return target, view['outcomes']


def _completed(directory, job):
    """Recheck retained receipt/response bindings before reusing a completed call."""
    receipt = read_json(directory / 'completion.json')
    if receipt['status'] != 'completed':
        raise ValueError('previous admission failed; use a fresh run after fixing the cause')
    for field in ('raw_response_ref', 'response_ref', 'result_ref'):
        reference = receipt[field]
        if _ref(directory / reference['path'])['sha256'] != reference['sha256']:
            raise ValueError('saved call response changed')
    result = read_json(directory / 'result.json')
    if (any(result[key] != job[key] or receipt[key] != job[key] for key in dispatch._BINDING)
            or result['context_id'] != job['context_id'] or result['model_profile'] != job['model_profile']
            or receipt['dispatch']['dispatch_id'] != result['dispatch_id']):
        raise ValueError('saved call belongs to a different job/context')
    dispatch._read_receipts(job, result['image_receipts'])
    response = read_json(directory / 'response.json')
    if json.loads(result['raw_response']) != response:
        raise ValueError('saved model response changed')
    status, admission = dispatch._admit(job, response, receipt['dispatch'])
    if status != receipt['admission_status'] or admission != receipt['admission']:
        raise ValueError('saved admission changed')
    return receipt


def _prepared_job(directory):
    job = dispatch._job(read_json(directory / 'job.json'))
    prepared = read_json(directory / 'prepared.json')
    for field in ('job', 'input'):
        if _ref(directory / prepared[field]['path'])['sha256'] != prepared[field]['sha256']:
            raise ValueError('prepared call bytes changed')
    if read_json(directory / 'input.json') != dispatch._payload(job):
        raise ValueError('prepared call content changed')
    return job


def _call(directory, invoke):
    job = _prepared_job(directory)
    if (directory / 'completion.json').exists():
        return _completed(directory, job)
    output = directory / 'host-result.json'
    if not output.exists():
        if (directory / 'physpi-model-call.claim').exists():
            raise ValueError('previous host attempt is incomplete; no automatic retry')
        invoke(directory / 'input.json', output)
    result = read_json(output)
    if result.get('schema_version') != 'terminal-model-result/0.1':
        raise ValueError('host execution failed; inspect retained host result and usage sidecar')
    return dispatch.complete_terminal_job(directory, result)


def execute_source_run(output_directory, invoke):
    """Execute/resume saved stages; invoke(input_path, output_path) owns the host.

    Valid completed stages are reused without new calls. A failed/interrupted
    attempted stage is preserved and never silently retried. Protocol and host
    errors are execution_failed, distinct from a valid null judgment.
    """
    directory = Path(output_directory).resolve()
    plan = read_json(directory / 'run.json')
    for reference in [plan['judge_job'], *plan['implementation']]:
        _check(reference)
    if plan.get('evidence_view'):
        _check(plan['evidence_view'])
        for item in [*plan['original_request']['evidence'],*read_json(plan['evidence_view']['path'])['input_evidence']]:
            checked_ref(Path(plan['artifact_root']), item)
    result_path = directory / 'run-result.json'
    if result_path.exists():
        saved = read_json(result_path)
        for reference in saved.get('retained', []):
            _check(reference)
        for stage in ('judge', 'judge-expanded', 'verify'):
            call_directory = directory / stage
            if (call_directory / 'prepared.json').is_file():
                job = _prepared_job(call_directory)
                completion = call_directory / 'completion.json'
                if completion.is_file() and read_json(completion)['status'] == 'completed':
                    _completed(call_directory, job)
        return saved
    # Exclusive claim prevents two local executors from paying for the same run.
    claim = directory / 'execution.claim'
    with claim.open('x', encoding='utf-8') as stream:
        stream.write('one paired execution window\n')
    result = {'schema_version': 'terminal-source-run-result/0.1', 'terminal': None,
        'candidate_terminal': None, 'review_performed': False, 'review_status': 'not_started',
        'task_success': None, 'retained': [_ref(directory / 'run.json')]}
    if plan.get('evidence_view'):
        asset_ref = read_json(plan['evidence_view']['path'])['asset_checks']
        asset_receipt = read_json(Path(plan['artifact_root']) / asset_ref['path'])
        result['asset_checks'] = asset_ref
        result['asset_comparison_summary'] = asset_receipt.get('comparison_summary')
    stage = 'judgment'
    try:
        first = _call(directory / 'judge', invoke)
        result['retained'].append(_ref(directory / 'judge/completion.json'))
        judgment_directory = directory / 'judge'
        queries = first['admission'].get('evidence_requests', [])
        if plan.get('evidence_mode') == 'adaptive' and queries:
            stage = 'evidence_expansion'
            target, outcomes = _expansion(directory, plan, first)
            result['evidence_expansion'] = outcomes
            if target is not None:
                stage = 'expanded_judgment'
                first = _call(target, invoke)
                judgment_directory = target
                result['retained'].append(_ref(target / 'completion.json'))
        result['candidate_terminal'] = first['admission']['candidate_terminal']
        result['requirements'] = first['admission']['requirements']
        result['requirement_summary'] = first['admission']['requirement_summary']
        stage = 'verification_preparation'
        request = terminal_reviews.prepare_source_verification(
            read_json(judgment_directory / 'job.json')['request'], read_json(judgment_directory / 'response.json'),
            judgment_dispatch=first['dispatch'], model_profile=plan['verification_model_profile'],
            review_unknown=plan['review_unknown'])
        if request is None:
            result.update(status='judgment_unknown', review_status='unknown_not_reviewed')
        else:
            job = dispatch.prepare_terminal_job(request, job_id=plan['identity'] + '/verify',
                context_id=plan['identity'] + '/verify-context', artifact_root=plan['artifact_root'],
                transport='external_file', evidence_encoding=plan['evidence_encoding'])
            review_dir = directory / 'verify'
            if not review_dir.exists():
                dispatch.write_terminal_job(job, review_dir, max_text_characters=plan['max_text_characters'],
                                            max_images=plan['max_images'])
            elif read_json(review_dir / 'job.json') != job:
                raise ValueError('saved verification job changed')
            stage = 'verification'
            result['review_performed'] = True
            final = _call(review_dir, invoke)
            result['retained'].append(_ref(review_dir / 'completion.json'))
            result.update(status='completed', terminal=final['admission']['terminal'],
                          review_status=final['admission']['review_status'])
    except Exception as error:
        result.update(status='execution_failed', failure_stage=stage, error_type=type(error).__name__,
                      reason=str(error))
    # Bind all saved stage artifacts, including failed responses/usage and input
    # sizes, so a repeated read cannot silently trust changed retained bytes.
    retained_paths = {reference['path'] for reference in result['retained']}
    for stage in ('judge', 'judge-expanded', 'verify', 'evidence-initial', 'evidence-expanded', 'asset-checks'):
        for path in sorted((directory / stage).glob('*')):
            if path.is_file() and str(path.resolve()) not in retained_paths:
                result['retained'].append(_ref(path))
    _save(result_path, result)
    # Remove only this exact disposable lock after a retained result. An abrupt
    # process interruption leaves it for explicit inspection, never auto retry.
    claim.unlink()
    return result


def run_file_host(output_directory, host_script, *, agent_dir=None, node="node"):
    """Execute a prepared review using the PhysPi-compatible file host."""
    script = Path(host_script).resolve(strict=True)

    def invoke(input_path, output_path):
        command = [node, str(script), '--input', str(input_path), '--output', str(output_path)]
        if agent_dir:
            command.extend(['--agent-dir', str(agent_dir)])
        completed = subprocess.run(command, capture_output=True, timeout=360, check=False)
        _save(input_path.parent / 'host-execution.json', {'return_code': completed.returncode})
        if completed.returncode != 0:
            raise RuntimeError('external terminal host failed; inspect saved host output')

    return execute_source_run(output_directory, invoke)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='stage', required=True)
    prepare = sub.add_parser('prepare', help='offline input construction and size preflight')
    prepare.add_argument('--request', type=Path, required=True)
    prepare.add_argument('--root', type=Path, required=True)
    prepare.add_argument('--output', type=Path, required=True)
    prepare.add_argument('--verification-profile', type=Path, required=True)
    prepare.add_argument('--review-unknown', action='store_true', help='diagnostic: review null candidates too')
    prepare.add_argument('--raw-evidence', action='store_true')
    prepare.add_argument('--max-text-characters', type=int)
    prepare.add_argument('--max-images', type=int)
    prepare.add_argument('--evidence-mode', choices=('full', 'adaptive', 'catalogued_full'), default='full',
                         help='adaptive: initial/final observations, one requested expansion; full: legacy')
    run = sub.add_parser('run', help='explicitly call the selected external file host')
    run.add_argument('--output', type=Path, required=True)
    run.add_argument('--host-script', type=Path, required=True)
    run.add_argument('--node', default='node')
    run.add_argument('--agent-dir', type=Path)
    args = parser.parse_args()
    if args.stage == 'prepare':
        prepare_source_run(read_json(args.request), args.root, args.output,
            verification_model_profile=read_json(args.verification_profile), review_unknown=args.review_unknown,
            evidence_encoding=None if args.raw_evidence else ENCODING,
            max_text_characters=args.max_text_characters, max_images=args.max_images, evidence_mode=args.evidence_mode)
        print(json.dumps({'status': 'prepared_no_model_call',
            'input': read_json(args.output / 'judge/input-summary.json')}))
        return
    result = run_file_host(args.output, args.host_script, agent_dir=args.agent_dir, node=args.node)
    print(json.dumps(result, ensure_ascii=False))
    if result['status'] == 'execution_failed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
