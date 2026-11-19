"""Validate a task against one existing run. Model review is explicitly opt-in."""
import argparse
import json
import os
from pathlib import Path
import sys

from validation.adapters import physpi
from validation.adapters.recorded import validate_terminal_evidence
from validation.artifact_io import checked_ref, digest, read_json
from validation.goals import EvalPolicy, SceneState, evaluate_task, load_vocabulary, registered
from validation.inputs import load_task_source
from validation.terminal import reviews, source_run


def _save(path, data):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False, allow_nan=False)


def _ref(root, path):
    return {'path': path.resolve().relative_to(root).as_posix(), 'sha256': digest(path)}


def _input_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def _source(args):
    if args.task.suffix.lower() in {'.txt', '.md'}:
        prompt = args.task.read_text(encoding='utf-8-sig').strip()
        if not prompt:
            raise ValueError('task prompt is empty')
        return {'task': {'prompt': prompt}, 'dependencies': {}}, [], {}
    resource_root = args.resource_root or args.task.parent
    source = load_task_source(args.task, resource_root=resource_root)
    paths, goal_resources = [], {}
    for item in source['task'].get('resources', []):
        path = resource_root / item['path']
        paths.append(path)
        kind = item.get('type')
        if kind in {'object_manifest', 'predicate_vocabulary'}:
            if kind in goal_resources:
                raise ValueError(f'ambiguous {kind} resource')
            goal_resources[kind] = path
            source['dependencies'][item['id']] = (read_json(path) if kind == 'object_manifest'
                                                  else path.read_text(encoding='utf-8-sig'))
    return source, paths, goal_resources


def _collect(args, root, refs, goal_resources):
    run, out = args.physpi_run.resolve(), args.output
    runtime = args.runtime_python
    if runtime is None:
        exe = 'Scripts/python.exe' if os.name == 'nt' else 'bin/python'
        runtime = args.physpi_root / '.venv' / exe
    index = read_json(run / ('timeline/timeline.json' if args.branch else 'manifest.json'))
    views = index.get('boundary_views') if args.branch else index.get('artifacts', {}).get('boundary_views')
    window = read_json(args.window) if args.window else None
    vocabulary = goal_resources.get('predicate_vocabulary')
    if window is None and vocabulary and digest(vocabulary) == digest(
            Path(__file__).parent / 'goals/vocabularies/scene-predicates-v1.yaml'):
        window = {'source_ref': _ref(root, vocabulary), 'pointer': '/evaluation/terminal_state',
                  'seconds': EvalPolicy().settle_window_s}
    state = physpi.collect_evidence(run, runtime.resolve(), root, out / 'state.json',
                                    branch=args.branch, window=window, source_refs=refs)
    state_ref = _ref(root, out / 'state.json')
    native = None
    metadata = physpi._runtime_source(run, args.branch)
    if state['endpoint']['valid'] and metadata['measurements_path'].is_file():
        physpi.collect_native_evidence(run, runtime.resolve(), root, out / 'native',
                                      base_evidence_ref=state_ref,
                                      branch=args.branch, source_refs=refs)
        native = _ref(root, out / 'native/native-evidence.json')
    return physpi.prepare_source_evidence(root, state_ref, out / 'source', native_evidence_ref=native,
        boundary_views_ref=_ref(root, run / views) if views else None)


def _states(packet, root):
    endpoint = packet['endpoint']
    for item in packet['evidence']:
        if item['kind'] != 'raw_state' or item['id'] not in {'observed_state', 'goal_state'}:
            continue
        data = read_json(checked_ref(root, item))
        schema = {'observed_state': 'terminal-evidence/0.1', 'goal_state': 'goal-states/1'}[item['id']]
        if not isinstance(data, dict) or data.get('schema_version') != schema:
            continue
        if any(data['endpoint'].get(k) != endpoint[k] for k in endpoint):
            raise ValueError('state payload belongs to a different endpoint')
        if item['id'] == 'observed_state':
            validate_terminal_evidence(data)
            return physpi.goal_states(data)
        for sample in (data['initial'], data['terminal']):
            if type(sample.get('contacts_available', False)) is not bool:
                raise ValueError('contacts_available must be boolean')
            if sample.get('contacts_available') and not isinstance(sample.get('contacts'), list):
                raise ValueError('observed contacts must be supplied as a list')
        first, last = SceneState(**data['initial']), SceneState(**data['terminal'])
        if type(last.time) not in (int, float) or last.time != endpoint.get('time_s'):
            raise ValueError('terminal state time must match endpoint.time_s')
        if last.settled is not None and type(last.settled) is not bool:
            raise ValueError('terminal settled flag must be boolean or null')
        return first, last, None
    return None


def _goal(source, resources, packet, root):
    task = source['task']
    if 'goal' not in task.get('truth', {}):
        return None, 'no_authored_goal'
    if set(resources) != {'object_manifest', 'predicate_vocabulary'}:
        return None, 'goal_resources_unavailable'
    vocabulary = load_vocabulary(resources['predicate_vocabulary'])
    if vocabulary['version'] not in registered():
        return None, 'unregistered_vocabulary'
    if vocabulary['version'] == 'scene-predicates/1.0.0':
        pinned = Path(__file__).parent / 'goals/vocabularies/scene-predicates-v1.yaml'
        if digest(resources['predicate_vocabulary']) != digest(pinned):
            raise ValueError('scene predicate vocabulary differs from its registered version')
    states = _states(packet, root)
    if states is None:
        return None, 'no_normalized_goal_states'
    first, last, trace = states
    manifest = read_json(resources['object_manifest'])
    # A terminal window can establish settling but cannot establish a whole-episode process.
    if trace is not None and task['truth'].get('process'):
        last.settled = trace.settle_report([o['name'] for o in manifest['objects']])['settled']
        trace = None
    return evaluate_task(task, manifest, vocabulary, last, first, trace), None


def _review(args, source, packet, root):
    task = source['task']
    pointers = ['/task/prompt']
    pointers += ['/task/truth/' + k for k in ('acceptance', 'goal', 'bind', 'process')
                 if k in task.get('truth', {})]
    pointers += ['/dependencies/' + k.replace('~', '~0').replace('/', '~1') for k in source['dependencies']]
    request = reviews.prepare_source_review(source, packet['endpoint'], required_source_pointers=pointers,
                    model_profile=_input_json(args.judge_profile), evidence=packet['evidence'])
    output = args.output / 'review'
    source_run.prepare_source_run(request, root, output, verification_model_profile=_input_json(args.verifier_profile),
                                  evidence_mode=args.evidence_mode, max_text_characters=args.max_text_characters)
    host = args.host_script or args.physpi_root / 'scripts/terminal-model.mjs'
    return source_run.run_file_host(output, host, agent_dir=args.agent_dir)


def _run(args, result):
    source, resources, goal_resources = _source(args)
    task = source['task']
    result.update(task_id=task.get('task_id'), task_sha256=digest(args.task))
    if args.physpi_run:
        run = args.physpi_run.resolve()
        if run.parent.name == 'runs':
            original = run.parent.parent / 'input.json'
            if original.is_file() and read_json(original) != task:
                raise ValueError('task does not match PhysPi batch input.json')
        paths = [args.task, *resources, args.output, run]
        root = (args.artifact_root or Path(os.path.commonpath([p.resolve() for p in paths]))).resolve()
        packet = _collect(args, root, [_ref(root, p) for p in [args.task, *resources]], goal_resources)
    else:
        root = (args.artifact_root or args.evidence_bundle.parent).resolve()
        packet = _input_json(args.evidence_bundle)
    if 'task_id' in packet and task.get('task_id') and packet['task_id'] != task['task_id']:
        raise ValueError('bundle task_id differs from the supplied task')
    endpoint = packet['endpoint']
    reviews._source_endpoint(endpoint)
    reviews._evidence(packet['evidence'], endpoint, 'multimodal')
    for item in packet['evidence']:
        checked_ref(root, item)
        if 'source_video' in item:
            checked_ref(root, item['source_video'])
    result.update(endpoint=endpoint, artifact_root=str(root), evidence=packet['evidence'],
                  missing=list(packet.get('missing_structured_evidence', [])))
    if not endpoint['valid']:
        result.update(status='unknown', reason='invalid_endpoint')
        return
    goal, reason = _goal(source, goal_resources, packet, root)
    if goal is not None:
        _save(args.output / 'goal-result.json', goal)
        result.update(route='dataset_goal', requirements=goal['atoms'], goal_result='goal-result.json',
                      settle=goal['settle'], process=goal['process'])
        if 'all_released' in goal:
            result['requirements'] = [*goal['atoms'], {'pred': 'AllReleased', **goal['all_released']}]
        value = goal['goal']
        reason = goal['goal_reason']
        if value is not None:
            result.update(status='determinate', terminal=value, scope='authored_terminal_goal', reason=reason)
            return
    result.update(status='unknown', reason=reason)
    if args.review_on_unknown:
        result['route'] = 'model_review'
        result['fallback_reason'] = reason
        reviewed = _review(args, source, packet, root)
        result.update(status=reviewed['status'], terminal=reviewed['terminal'],
                      review_result='review/run-result.json', review_status=reviewed['review_status'])
        result['reason'] = reviewed.get('reason', reviewed['review_status'])
        for stage in ('judge-expanded', 'judge'):
            path = args.output / 'review' / stage / 'completion.json'
            if path.is_file():
                admission = read_json(path)['admission']
                result['judge_requirements'] = admission.get('requirements', [])
                result['judge_reason'] = admission.get('reason')
                break


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', required=True, type=Path, help='low-detail-task JSON or UTF-8 .txt/.md prompt')
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--physpi-run', type=Path)
    inputs.add_argument('--evidence-bundle', type=Path)
    for name in ('resource-root', 'artifact-root', 'physpi-root', 'runtime-python', 'window',
                 'judge-profile', 'verifier-profile', 'host-script', 'agent-dir'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--output', type=Path, required=True, help='fresh output directory')
    parser.add_argument('--branch', help='explicit branch of a sealed resident run')
    parser.add_argument('--review-on-unknown', action='store_true')
    parser.add_argument('--evidence-mode', choices=('full', 'adaptive', 'catalogued_full'), default='full')
    parser.add_argument('--max-text-characters', type=int)
    args = parser.parse_args(argv)
    if args.physpi_run and not args.physpi_root:
        candidates = [*args.physpi_run.resolve().parents, Path(__file__).resolve().parents[2] / 'PhysPi']
        args.physpi_root = next((p for p in candidates if (p / 'packages/runtime/physpi_runtime').is_dir()), None)
    if args.physpi_run and not (args.runtime_python or args.physpi_root):
        parser.error('--physpi-run requires --runtime-python or --physpi-root')
    if args.review_on_unknown and not (args.judge_profile and args.verifier_profile and (args.host_script or args.physpi_root)):
        parser.error('--review-on-unknown requires both profiles and --host-script or --physpi-root')
    args.output.mkdir(parents=True, exist_ok=False)
    result = {'status': 'execution_failed', 'terminal': None, 'route': 'offline'}
    try:
        _run(args, result)
    except Exception as exc:
        result.update(status='execution_failed', reason=str(exc), error_type=type(exc).__name__)
    _save(args.output / 'result.json', result)
    for item in result.get('judge_requirements', result.get('requirements', [])):
        print(json.dumps({k: item[k] for k in ('id', 'pred', 'args', 'value', 'reason') if k in item}))
    print(json.dumps({k: result.get(k) for k in ('status', 'terminal', 'reason')},
                     ensure_ascii=True), str(args.output / 'result.json'))
    return int(result['status'] == 'execution_failed')


if __name__ == '__main__':
    sys.exit(main())
