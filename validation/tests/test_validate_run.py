"""End-to-end routing for user-supplied tasks; no simulator or online account required."""
import json
from dataclasses import asdict
from pathlib import Path
import shutil

import pytest

from validation import validate_run
from validation.artifact_io import digest, read_json
from validation.tests.fixtures.source_reviews import PROFILE, verification
from validation.tests.test_task_inputs import task as sample_task
from validation.tests.test_goals import MANIFEST, state
from validation.terminal.dispatch import make_terminal_result
from validation.terminal.source_run import execute_source_run


EXAMPLE = Path(__file__).resolve().parents[2] / 'examples/validation/external-fixture'
VOCAB = Path(__file__).resolve().parents[1] / 'goals/vocabularies/scene-predicates-v1.yaml'


def write(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')


def invoke(task, bundle, output, *options):
    return validate_run.main(['--task', str(task), '--evidence-bundle', str(bundle),
                              '--output', str(output), *options])


def test_custom_text_task_offline_and_tampered_evidence(tmp_path):
    fixture = tmp_path / 'input'
    shutil.copytree(EXAMPLE, fixture)
    task, bundle = fixture / 'task.txt', fixture / 'bundle.json'
    output = tmp_path / 'offline'
    assert invoke(task, bundle, output) == 0
    assert read_json(output / 'result.json')['reason'] == 'no_authored_goal'
    with pytest.raises(FileExistsError):
        invoke(task, bundle, output)
    (fixture / 'indicator.json').write_text('{}', encoding='utf-8')
    output = tmp_path / 'changed'
    assert invoke(task, bundle, output) == 1
    assert 'hash mismatch' in read_json(output / 'result.json')['reason']


def test_foreign_endpoint_fails_before_offline_decision(tmp_path):
    packet = read_json(EXAMPLE / 'bundle.json')
    packet['evidence'][0]['episode_id'] = 'different-run'
    path = tmp_path / 'bundle.json'
    write(path, packet)
    out = tmp_path / 'output'
    assert invoke(EXAMPLE / 'task.txt', path, out, '--artifact-root', str(EXAMPLE)) == 1
    assert 'another episode' in read_json(out / 'result.json')['reason']


def test_invalid_endpoint_is_unknown_even_if_model_was_enabled(tmp_path, monkeypatch):
    packet = read_json(EXAMPLE / 'bundle.json')
    packet['endpoint']['valid'] = False
    path = tmp_path / 'bundle.json'
    write(path, packet)
    monkeypatch.setattr(validate_run, '_review', lambda *args: pytest.fail('unexpected model review'))
    out = tmp_path / 'output'
    assert invoke(EXAMPLE / 'task.txt', path, out, '--artifact-root', str(EXAMPLE),
                  '--review-on-unknown', '--judge-profile', 'unused', '--verifier-profile', 'unused',
                  '--host-script', 'unused') == 0
    assert read_json(out / 'result.json')['reason'] == 'invalid_endpoint'


@pytest.mark.parametrize('opening, settled, outcome', [(0.2, True, True), (0.0, True, False),
                                                        (0.2, None, None)])
def test_custom_goal_uses_bound_state_without_task_catalog(tmp_path, opening, settled, outcome):
    task = sample_task()
    task.update(task_id='custom-open', schema_version='low-detail-task/1.2.0', resources=[
        {'id': 'objects', 'type': 'object_manifest', 'path': 'objects.json'},
        {'id': 'vocab', 'type': 'predicate_vocabulary', 'path': 'vocab.yaml'}])
    task['truth'].update(group='A', goal={'pred': 'Open', 'args': ['drawer_1']})
    write(tmp_path / 'task.json', task)
    write(tmp_path / 'objects.json', MANIFEST)
    shutil.copyfile(VOCAB, tmp_path / 'vocab.yaml')
    def capture(t, distance):
        s = state(openings={'drawer_1': distance}, time=t)
        s.settled = settled
        return json.loads(json.dumps(asdict(s), default=lambda a: a.tolist()))

    packet = read_json(EXAMPLE / 'bundle.json')
    payload = {'schema_version': 'goal-states/1', 'endpoint': packet['endpoint'],
               'initial': capture(0., 0.), 'terminal': capture(1., opening)}
    path = tmp_path / 'state.json'
    write(path, payload)
    packet['evidence'][0].update(id='goal_state', path=path.name, sha256=digest(path))
    packet['task_id'] = task['task_id']
    write(tmp_path / 'bundle.json', packet)
    out = tmp_path / 'evaluation'
    assert invoke(tmp_path / 'task.json', tmp_path / 'bundle.json', out) == 0
    result = read_json(out / 'result.json')
    assert result['terminal'] is outcome
    assert result['status'] == ('unknown' if outcome is None else 'determinate')
    goal = read_json(out / 'goal-result.json')
    assert goal['goal'] is outcome and goal['success'] is outcome
    if settled is None:
        assert goal['goal_if_settled'] is True
        assert goal['goal_reason'] == result['reason'] == 'settled_terminal_unverified'


def test_opt_in_file_review_for_plain_text_task(tmp_path, monkeypatch):
    """Exercise actual file preparation, admission and verification with authored replies."""
    profile = tmp_path / 'profile.json'
    write(profile, PROFILE)
    roles = []
    def host(directory, script, *, agent_dir):
        def respond(input_path, output_path):
            job = read_json(input_path)['job']
            roles.append(job['kind'])
            req = job['request']
            if job['kind'] == 'terminal-source-review':
                response = {'schema_version': 'terminal-source-review-response/0.1',
                    'request_sha256': req['request_sha256'], 'terminal': True, 'reason': 'Green at endpoint.',
                    'requirements': [{'id': 'color', 'source_pointers': ['/task/prompt'],
                        'scope': 'terminal', 'text': req['source']['task']['prompt'], 'value': True,
                        'reason': 'Instrument readback green.', 'evidence_ids': ['indicator_readback']}]}
            else:
                response = verification(req)
            write(output_path, make_terminal_result(job, json.dumps(response), dispatch_id=job['job_id']+'/call',
                  context_id=job['context_id'], model_profile=req['model_profile'], image_receipts=[]))
        return execute_source_run(directory, respond)
    monkeypatch.setattr(validate_run.source_run, 'run_file_host', host)
    out = tmp_path / 'reviewed'
    assert invoke(EXAMPLE/'task.txt', EXAMPLE/'bundle.json', out, '--review-on-unknown',
                  '--judge-profile', str(profile), '--verifier-profile', str(profile), '--host-script', 'fixture') == 0
    result = read_json(out / 'result.json')
    assert roles == ['terminal-source-review', 'terminal-source-verification']
    assert result['terminal'] is True
    assert result['judge_requirements'][0]['id'] == 'color'
