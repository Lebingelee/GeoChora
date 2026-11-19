"""Independent raw-record factories; no AST, model calls or reference labels."""
from copy import deepcopy
import hashlib
import json

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()

def evidence():
    refs = [{'path': 'native/manifest.json', 'sha256': '1' * 64},
            {'path': 'native/trace/states.parquet', 'sha256': '2' * 64},
            {'path': 'memory/task.json', 'sha256': '3' * 64}]
    run = {'run_id': 'independent-run', 'kind': 'batch', 'branch': None, 'code_sha256': '4' * 64}
    source_id = digest({'index': refs[0], 'code_sha256': run['code_sha256'], 'branch': None})
    episode = 'native-physpi::' + source_id + '::independent-run::batch'
    def sample(step):
        return {'step': step, 'time_s': step * .5, 'complete': True,
            'positions': {'a': [0., 0., 1.], 'b': [2., 0., 1.]},
            'orientations_wxyz': {'a': [1., 0., 0., 0.], 'b': [1., 0., 0., 0.]}}
    samples = [sample(index) for index in range(3)]
    return {'schema_version': 'terminal-evidence/0.1',
        'implementation': {'path': 'physpi_terminal.py', 'sha256': '5' * 64}, 'run': run,
        'endpoint': {'episode_id': episode, 'endpoint_id': digest({'episode': episode, 'step': 2, 'time_s': 1., 'trace': refs[1]['sha256']}),
                     'asset_family': 'native-physpi', 'valid': True, 'step': 2, 'time_s': 1., 'reasons': []},
        'identities': {name: episode + '::' + name for name in ('a', 'b')},
        'initial': {**deepcopy(samples[0]), 'scope': 'episode_initial', 'valid_for_task_initial': True},
        'terminal': deepcopy(samples[-1]),
        'terminal_window': {'requested': {'source_ref': refs[2], 'pointer': '/requirements/window_seconds', 'seconds': 1.,
                                        'sample_dt_pointer': '/requirements/sample_dt_seconds', 'sample_dt_seconds': .5},
            'start_time_s': 0., 'end_time_s': 1., 'sample_dt_seconds': .5, 'complete': True, 'reasons': [], 'samples': samples},
        'facts': {'terminal_window_pose_spread': {'a': {'available': True, 'maximum_pairwise_center_distance_m': 0.}}},
        'capture': {'owner': 'physpi_runtime.cli.cmd_query', 'scope': 'initial_terminal_and_source_requested_terminal_window_only'},
        'source_refs': refs, 'process': 'not_evaluated', 'task_success': None}

REFS = [{'path': 'native/evidence.json', 'sha256': '6' * 64}]
