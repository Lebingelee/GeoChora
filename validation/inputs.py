"""Versioned task inputs and source loading for external recorded experiments."""
from functools import lru_cache
import json
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator

from validation.protocol import _json


TASK_SCHEMA_VERSION = 'low-detail-task/1.1.0'
_SCHEMA_FILES = {
    TASK_SCHEMA_VERSION: 'low-detail-task-1.1.0.schema.json',
    'low-detail-task/1.2.0': 'low-detail-task-1.2.0.schema.json',
}
TASK_SCHEMA_VERSIONS = tuple(_SCHEMA_FILES)


class TaskInputError(ValueError):
    """Invalid task structure or unavailable/ambiguous source dependencies."""


@lru_cache(maxsize=None)
def _validator(version):
    path = Path(__file__).with_name('schemas') / _SCHEMA_FILES[version]
    schema = json.loads(path.read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_task(task, *, label='task'):
    """Return an unchanged JSON copy accepted by the declared task schema.

    This checks the input contract, not task success or evidence sufficiency.
    Unrecognized versions are rejected explicitly; no implicit migration occurs.
    """
    try:
        task = _json(task)
    except ValueError as error:
        raise TaskInputError(f'{label}: finite JSON task required') from error
    version = task.get('schema_version') if isinstance(task, dict) else None
    if not isinstance(version, str) or version not in _SCHEMA_FILES:
        supported = ', '.join(TASK_SCHEMA_VERSIONS)
        raise TaskInputError(f'{label}/schema_version: supported versions are {supported}')
    errors = sorted(_validator(version).iter_errors(task), key=lambda e: (tuple(map(str, e.absolute_path)), e.message))
    if errors:
        messages = []
        for error in errors:
            parts = list(error.absolute_path)
            if error.validator == 'required' and isinstance(error.instance, dict):
                locations = [(parts + [key], 'required field is missing')
                             for key in error.validator_value if key not in error.instance]
            else:
                locations = [(parts, error.message)]
            for location, message in locations:
                pointer = '/' + '/'.join(str(p).replace('~', '~0').replace('/', '~1') for p in location)
                messages.append(f'{label}{pointer}: {message}')
        raise TaskInputError('\n'.join(dict.fromkeys(messages)))
    return task


def load_task(path):
    """Read one original task JSON; report input errors before model execution."""
    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as error:
        raise TaskInputError(f'{path}: task JSON cannot be read: {error}') from error
    return validate_task(document, label=str(path))


def load_task_source(path, *, resource_root=None):
    """Load original task and declared JSON contracts without executing assets.

    Every declared resource must resolve inside resource_root (default: task's
    directory). Only task_contract and initial_state JSON are embedded as source
    dependencies. Callers retain file-byte identities with their evidence.
    """
    path = Path(path)
    task = load_task(path)
    root = Path(resource_root if resource_root is not None else path.parent).resolve()
    dependencies, ids = {}, set()
    for resource in task.get('resources', []):
        identity = resource['id']
        if identity in ids:
            raise TaskInputError(f'{path}/resources: duplicate resource ID {identity!r}')
        ids.add(identity)
        relative = PurePosixPath(resource['path'].replace('\\', '/'))
        target = (root / str(relative)).resolve()
        if (relative.is_absolute() or '..' in relative.parts or ':' in str(relative)
                or not target.is_relative_to(root) or not target.is_file()):
            raise TaskInputError(f'{path}/resources/{identity}: resource is missing or outside resource_root')
        if resource.get('type') in {'task_contract', 'initial_state'}:
            try:
                dependencies[identity] = _json(json.loads(target.read_text(encoding='utf-8-sig')))
            except (OSError, ValueError) as error:
                raise TaskInputError(f'{path}/resources/{identity}: invalid JSON dependency') from error
    return {'task': task, 'dependencies': dependencies}
