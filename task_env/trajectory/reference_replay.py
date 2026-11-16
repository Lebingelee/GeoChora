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


def inspect_selected_replay(path):
    """Inspect the outer format without constructing an Env or importing a physics SDK.

    Format support is not proof of source identity or successful re-execution.
    """
    with h5py.File(path, 'r') as handle:
        schema = handle.attrs.get('schema')
        if isinstance(schema, bytes):
            schema = schema.decode('utf-8')
        generic_schema = handle.attrs.get('schema_id')
    supported = {'task-env-canonical-trajectory-v0', 'task-env-canonical-execution-v1',
                 'task-env-canonical-execution-v2'}
    if schema == 'task-env-canonical-trajectory-v1':
        reason = ('canonical trajectory v1 stores structured controls/events/outcome; selected reference replay '
                  'does not yet reproduce that execution contract')
    elif schema == 'task-env-canonical-execution-v3':
        reason = ('execution trajectory v3 stores structured controls/events/outcome; selected reference replay '
                  'does not yet compare that contract')
    elif schema not in supported:
        reason = 'unsupported selected reference replay format'
    else:
        reason = None
    return {'schema': schema, 'generic_schema': generic_schema,
            'format_supported_for_reexecution': reason is None, 'reason': reason,
            'source_identity_checked': False}


def reexecute_selected(path, *, output):
    inspected = inspect_selected_replay(path)
    if not inspected['format_supported_for_reexecution']:
        raise ValueError(inspected['reason'])
    outer = inspected['schema'] == 'task-env-canonical-trajectory-v0'
    from task_env.environment.reference_env import __file__ as adapter_file
    from task_env.tasks.pick_cube.task import REFERENCE_ENV_ID as PC
    from task_env.tasks.nut_assembly.task import REFERENCE_ENV_ID as NA
    SELECTED_ENV_IDS = (PC, NA)
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
    if (configuration['env_id'] == NA and frozen['transitions']
            and 'arm_execution_request_v1' not in frozen['transitions'][0]['record'].get('expert_diagnostics', {})):
        raise ValueError('legacy Nut expert recording cannot be compared using the external Solution execution contract')
    from task_env.runtime.sessions import common as session_common
    if metadata['source_provenance']['interval_source'] != hashlib.sha256(Path(session_common.__file__).read_bytes()).hexdigest():
        raise ValueError('runtime interval source identity mismatch')
    if metadata['source_provenance']['adapter'] != hashlib.sha256(Path(adapter_file).read_bytes()).hexdigest():
        raise ValueError('adapter source identity mismatch; no historical identity substitution')
    from task_env.recorders import reference_provenance
    coordinator_source = metadata['source_provenance'].get('coordinator_source')
    if coordinator_source is not None and coordinator_source != reference_provenance.source_snapshot(reference_provenance.__file__):
        raise ValueError('coordinator source identity mismatch; no historical identity substitution')
    from task_env import make_env
    env = make_env(configuration['env_id'], config={k:v for k,v in configuration.items() if k!='env_id'})
    try:
        binding_sources = {
            'observation_source': env.binding.observation_projection,
            'observation_space_source': env.binding.observation_space_factory,
            'action_source': env.binding.prepare_action,
            'action_space_source': env.binding.action_space_factory,
        }
        recorded_sources = metadata['source_provenance']
        recorded_task_sources = {
            name.removeprefix('source_sha256:'): value
            for name, value in recorded_sources.items()
            if name.startswith('source_sha256:')
        }
        if recorded_task_sources and recorded_task_sources != env.value.get('source_sha256', {}):
            raise ValueError('task source inventory identity mismatch; no historical identity substitution')
        for name, callback in binding_sources.items():
            expected_source = recorded_sources.get(name)
            if expected_source is not None and expected_source != reference_provenance.callable_source_snapshot(callback):
                raise ValueError(f'{name} identity mismatch; no historical identity substitution')
        if digest(env.value['resolved_configuration']) != digest(recipe['resolved_configuration']):
            raise ValueError('construction source/configuration identity mismatch')
        if (env.controller.identity != metadata['controller_identity'] or
                env.value['solution_identity'] != metadata['expert_identity']):
            raise ValueError('controller/solution identity mismatch')
        observation, info = env.reset(seed=metadata['task_seed'])
        if env.sample.to_mapping() != metadata['reset_sample']:
            raise ValueError('reset identity mismatch')
        env.start_recording(output)
        solution = env.value['solution_factory']()
        if solution.identity != env.value['solution_identity']:
            raise ValueError('constructed Solution identity differs from selected task')
        solution.reset(observation, info, env.metadata)
        for index, expected in enumerate(frozen['transitions']):
            action = solution.act(observation, info)
            observation, reward, terminated, truncated, info = env.step(action)
            solution.observe(observation, reward, terminated, truncated, info)
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
