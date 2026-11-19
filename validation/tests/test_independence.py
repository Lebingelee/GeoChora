"""An external data consumer can validate without importing the runtime stack."""
import os
from pathlib import Path
import subprocess
import sys


def test_recorded_validation_and_review_run_without_task_env(tmp_path):
    script = r'''
import importlib.abc
import json
from pathlib import Path
import pkgutil
import sys

class NoRuntimeImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'task_env', 'geophys', 'taichi', 'gymnasium', 'mujoco', 'physpi_runtime'}:
            raise AssertionError('offline validation imported a runtime: ' + fullname)

sys.meta_path.insert(0, NoRuntimeImports())
import validation
for module in pkgutil.walk_packages(validation.__path__, validation.__name__ + '.'):
    if '.tests' not in module.name:
        __import__(module.name)

from validation.adapters.recorded import adapt_recorded_poses, validate_recorded_evidence
from validation.terminal.numeric import measure_source_requests
from validation.terminal.reviews import prepare_source_review
from validation.terminal.source_run import prepare_source_run, execute_source_run
from validation.terminal.dispatch import make_terminal_result
from validation.tests.fixtures.source_reviews import inputs, candidate, verification, PROFILE

code = {'path': 'input/recorder.py', 'sha256': '1' * 64}
trace = {'path': 'input/trace.json', 'sha256': '2' * 64}
claim_ref = {'path': 'input/completion.json', 'sha256': '3' * 64}
source_ref = {'path': 'input/task.json', 'sha256': '4' * 64}
frames = [{'time': time, 'positions': {'gear': [0., 0., 0.]},
           'orientations': {'gear': [1., 0., 0., 0.]}} for time in [0., 1.]]
completion = {'trace_ref': trace, 'run_id': 'external-experiment', 'code_ref': code,
    'bodies': ['gear'], 'frame_count': 2, 'last_recorded_time_s': 1.,
    'last_recorded_step': 20, 'actual_final_time_s': 1., 'actual_final_step': 20,
    'complete': True, 'first_step': 0}
record = adapt_recorded_poses(frames, run_id='external-experiment', bodies=['gear'],
    code_ref=code, trace_ref=trace, completion_ref=claim_ref, completion=completion,
    pose_schema={'frame': 'world', 'position_unit': 'm', 'time_unit': 's', 'orientation_order': 'wxyz'},
    source_refs=[source_ref])
assert validate_recorded_evidence(record) == record
measurements = measure_source_requests({'prompt': 'The orientation must remain unchanged.'},
    source_ref=source_ref, evidence=record, evidence_refs=[source_ref],
    requests=[{'request_id': 'orientation', 'method': 'orientation_unchanged/v1',
        'arguments': [record['identities']['gear']], 'params': {'maximum_angle_deg': 0.},
        'source_basis': [{'path': source_ref['path'], 'pointer': '/prompt'}]}])
assert measurements['measurements'][0]['value'] is True
request = inputs(Path(sys.argv[1]))
directory = Path(sys.argv[1]) / 'paired'
prepare_source_run(request, sys.argv[1], directory, verification_model_profile=PROFILE)
def invoke(input_path, output_path):
    job = json.loads(input_path.read_text(encoding='utf-8'))['job']
    response = candidate(job['request']) if job['kind'] == 'terminal-source-review' else verification(job['request'])
    result = make_terminal_result(job, json.dumps(response), dispatch_id=job['job_id'] + '/synthetic',
        context_id=job['context_id'], model_profile=job['request']['model_profile'],
        image_receipts=[])
    output_path.write_text(json.dumps(result), encoding='utf-8')
result = execute_source_run(directory, invoke)
assert result['terminal'] is True
assert not any(name == 'task_env' or name.startswith('task_env.') for name in sys.modules)
print('standalone recorded measurement and independently verified review passed')
'''
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path))
    result = subprocess.run([sys.executable, '-X', 'utf8', '-B', '-c', script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[2], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
