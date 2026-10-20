"""Current selected-expert re-execution comparison, explicitly not D0 restoration.

Recorded requests are checked against requests newly emitted by the selected
expert. Neither frozen controls nor a diagnostic shadow are injected.
"""
import hashlib
import json
import h5py
from pathlib import Path
from task_env.controllers.canonical.contracts import digest
from task_env.trajectory.canonical.streaming import load_streaming


def reexecute_selected(path, *, output):
    from task_env import make_env
    from task_env.tasks.reference_env import __file__ as adapter_file
    from task_env.tasks.pick_cube.task import REFERENCE_ENV_ID as PC
    from task_env.tasks.nut_assembly.task import REFERENCE_ENV_ID as NA
    SELECTED_ENV_IDS = (PC, NA)
    with h5py.File(path, 'r') as handle:
        outer_schema = handle.attrs.get('schema')
        if outer_schema == 'task-env-canonical-trajectory-v1':
            raise ValueError('canonical trajectory v1 stores structured controls/events/outcome; selected reference replay does not yet reproduce that execution contract')
        if outer_schema == 'task-env-canonical-execution-v3':
            raise ValueError('execution trajectory v3 stores structured controls/events/outcome; selected reference replay does not yet compare that contract')
        outer = outer_schema == 'task-env-canonical-trajectory-v0'
    if outer:
        from task_env.trajectory.canonical.h5 import load
        value = load(path).to_mapping()
        provenance = value['metadata']['source_provenance']
        frozen = {'metadata': value['metadata'],
            'recipe': {'execution_configuration': json.loads(provenance['execution_configuration_json']),
                       'resolved_configuration': json.loads(provenance['resolved_configuration_json'])},
            'transitions': [{'record': t} for t in value['transitions']],
            'boundaries': [{'record': b} for b in value['boundaries']]}
    else:
        frozen = load_streaming(path)
    metadata, recipe = frozen['metadata'], frozen['recipe']
    configuration = recipe['execution_configuration']
    if configuration['env_id'] not in SELECTED_ENV_IDS:
        raise ValueError('not a selected reference execution')
    from task_env.runtime.sessions import common as session_common
    if metadata['source_provenance']['interval_source'] != hashlib.sha256(Path(session_common.__file__).read_bytes()).hexdigest():
        raise ValueError('runtime interval source identity mismatch')
    if metadata['source_provenance']['adapter'] != hashlib.sha256(Path(adapter_file).read_bytes()).hexdigest():
        raise ValueError('adapter source identity mismatch; no historical identity substitution')
    env = make_env(configuration['env_id'], config={k:v for k,v in configuration.items() if k!='env_id'})
    try:
        if digest(env.value['resolved_configuration']) != digest(recipe['resolved_configuration']):
            raise ValueError('construction source/configuration identity mismatch')
        if (env.controller.identity != metadata['controller_identity'] or
                env.solution.identity != metadata['expert_identity']):
            raise ValueError('controller/solution identity mismatch')
        env.reset(seed=metadata['task_seed'])
        if env.sample.to_mapping() != metadata['reset_sample']:
            raise ValueError('reset identity mismatch')
        env.start_recording(output)
        for index, expected in enumerate(frozen['transitions']):
            env.step_expert()
            if outer:
                actual = {'record': env.recorder.transitions[-1].to_mapping()}
                boundary = {'record': env.recorder.boundaries[-1].to_mapping()}
            else:
                actual = env.recorder.value['transitions'][-1]
                boundary = env.recorder.value['boundaries'][-1]
            if actual['record'] != expected['record'] or boundary['record'] != frozen['boundaries'][index+1]['record']:
                raise ValueError(f'current selected re-execution divergence at transition {index}')
        result = env.finish_recording('selected-expert-reexecution-comparison')
        return {'status':'PASS', 'scope':'same-source selected-expert reexecution',
                'transitions':len(frozen['transitions']), 'recording':result,
                'D0':'NOT_ASSESSED', 'historical_qualification':'NOT_ASSESSED'}
    finally:
        env.close()
