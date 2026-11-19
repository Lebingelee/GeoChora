"""External task contracts reject malformed input before model execution."""
import json

import pytest

from validation.inputs import TaskInputError, load_task, load_task_source, validate_task


def task():
    prompt = 'Place the supplied object inside the container, then release it.'
    return {'schema_version': 'low-detail-task/1.1.0', 'task_id': 'external-placement',
        'language': 'en', 'domain': 'articulated_control', 'prompt': prompt,
        'truth': {'required_capabilities': ['rigid.contact.resolve'],
            'difficulty': {'level': 'L1', 'scores': dict.fromkeys([
                'scene_composition', 'temporal_evolution', 'physical_interaction',
                'api_composition', 'resource_and_control', 'visual_verification'], 1)},
            'acceptance': {'policy': 'low_detail_lenient',
                'behaviors': [{'id': 'placement', 'description': prompt, 'public_basis': prompt,
                    'criteria': {'kind': 'inside_container_and_released'}}],
                'open_choices': ['Any suitable object and grasp strategy.'],
                'evidence': {'process': 'Use recorded motion when relevant.',
                    'completion': 'Inspect the actual final placement.',
                    'insufficient_evidence': 'unverified',
                    'execution_budget_exhausted': 'execution_limit_not_proven_task_failure'}},
            'source': {'kind': 'authored', 'source_id': 'external-contract-fixture', 'parent_task_ids': []}}}


def test_supported_task_is_preserved_and_not_aliased():
    original = task()
    accepted = validate_task(original)
    assert accepted == original
    accepted['truth']['acceptance']['behaviors'].clear()
    assert original['truth']['acceptance']['behaviors']


def test_1_2_task_passes_file_and_source_loading(tmp_path):
    original = task()
    original['schema_version'] = 'low-detail-task/1.2.0'
    original['truth'].update(group='A',
        goal={'vocab': 'scene-predicates/1.0.0', 'all': [['In', '?object', 'container']]},
        bind={'?object': {'kind': 'brick'}}, process=[])
    path = tmp_path / 'task.json'
    path.write_text(json.dumps(original), encoding='utf-8')

    assert load_task(path) == original
    assert load_task_source(path) == {'task': original, 'dependencies': {}}

    original['schema_version'] = 'low-detail-task/1.1.0'
    with pytest.raises(TaskInputError, match='/truth:'):
        validate_task(original)


def test_1_2_rejects_missing_version_specific_fields():
    data = task()
    data['schema_version'] = 'low-detail-task/1.2.0'
    with pytest.raises(TaskInputError) as caught:
        validate_task(data)
    assert set(str(caught.value).splitlines()) == {
        'task/truth/group: required field is missing',
        'task/truth/goal: required field is missing',
    }


@pytest.mark.parametrize('field', ['task_id', 'prompt', 'truth'])
def test_missing_task_fields_report_their_location(field):
    data = task(); del data[field]
    with pytest.raises(TaskInputError, match='/' + field):
        validate_task(data, label='external/task.json')


def test_multiple_missing_fields_are_reported_at_distinct_locations():
    data = task(); del data['task_id']; del data['prompt']
    with pytest.raises(TaskInputError) as caught:
        validate_task(data, label='input.json')
    assert set(str(caught.value).splitlines()) == {
        'input.json/task_id: required field is missing',
        'input.json/prompt: required field is missing',
    }


@pytest.mark.parametrize('version', [None, '2.0.0', 'low-detail-task/1.0.0', 'unknown', [], {}])
def test_unknown_versions_are_not_silently_migrated(version):
    data = task(); data['schema_version'] = version
    with pytest.raises(TaskInputError, match='/schema_version'):
        validate_task(data)


def test_nested_invalid_acceptance_and_nonfinite_values_are_input_errors():
    data = task(); data['truth']['acceptance']['behaviors'][0]['criteria'] = {}
    with pytest.raises(TaskInputError, match='/truth/acceptance/behaviors/0/criteria'):
        validate_task(data)
    data = task(); data['truth']['acceptance']['behaviors'][0]['criteria']['limit'] = float('nan')
    with pytest.raises(TaskInputError, match='finite JSON'):
        validate_task(data)


def write_task(tmp_path, resources):
    data = task(); data['resources'] = resources
    path = tmp_path / 'task.json'; path.write_text(json.dumps(data), encoding='utf-8')
    return path


def test_external_source_embeds_original_json_contracts_and_checks_resources(tmp_path):
    (tmp_path / 'scene.bin').write_bytes(b'synthetic asset, never executed')
    (tmp_path / 'contract.json').write_text('{"allowed_objects": ["any suitable object"]}', encoding='utf-8')
    path = write_task(tmp_path, [{'id': 'scene', 'path': 'scene.bin', 'type': 'scene'},
        {'id': 'contract', 'path': 'contract.json', 'type': 'task_contract'}])
    source = load_task_source(path)
    assert source['task'] == load_task(path)
    assert source['dependencies'] == {'contract': {'allowed_objects': ['any suitable object']}}
    (tmp_path / 'scene.bin').unlink()
    with pytest.raises(TaskInputError, match='resource is missing'):
        load_task_source(path)


@pytest.mark.parametrize('relative', ['../outside.json', '/outside.json', 'C:/outside.json'])
def test_resource_paths_cannot_escape_the_supplied_root(tmp_path, relative):
    path = write_task(tmp_path, [{'id': 'scene', 'path': relative}])
    with pytest.raises(TaskInputError, match='outside resource_root'):
        load_task_source(path)


def test_duplicate_resource_identity_is_rejected(tmp_path):
    (tmp_path / 'asset').write_bytes(b'asset')
    path = write_task(tmp_path, [{'id': 'scene', 'path': 'asset'}, {'id': 'scene', 'path': 'asset'}])
    with pytest.raises(TaskInputError, match='duplicate resource ID'):
        load_task_source(path)
