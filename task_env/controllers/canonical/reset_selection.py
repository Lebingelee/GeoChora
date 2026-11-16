"""Reset-scoped identity for explicitly switchable physical Controllers."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
import numpy as np

from .contracts import digest
from ...runtime.sessions.physical_control import PhysicalControlExecutionV1


@dataclass(frozen=True)
class PhysicalResetCapability:
    """Controller-owned policy for reset-time selection and action semantics."""
    initial_kind: str
    allowed_kinds: tuple[str, ...]
    space_policy: str
    action_schema: object

    def __post_init__(self):
        if not callable(self.action_schema):
            raise TypeError('physical reset capability requires an action schema')

    def bind(self, value):
        return PhysicalResetSelection(value['_physical_controller_factory'],
            initial_kind=self.initial_kind, allowed_kinds=self.allowed_kinds,
            space_policy=self.space_policy, declaration=value['physical_execution'])

    def reconstruct(self, value, request):
        """Rebuild this declared choice without a second Controller lifecycle."""
        generation = request['generation']
        if type(generation) is not int or generation < 1:
            raise ValueError('reconstructed Controller generation must be positive')
        prepared = self.bind(value).prepare({'kind': request['kind'],
                                            'parameters': request['parameters']})
        return replace(prepared, execution=replace(
            prepared.execution, generation=generation)).bind_value(value)


@dataclass(frozen=True)
class PreparedPhysicalSelection:
    """An uncommitted controller selection, bound to its predecessor generation."""
    owner: object
    previous_generation: int
    kind: str
    parameters: tuple[tuple[str, float], ...]
    execution: PhysicalControlExecutionV1
    spec_id: str

    def reconstruction_request(self):
        """Value-only declaration consumed by the same binding in another process."""
        return {'kind': self.kind, 'parameters': dict(self.parameters),
                'generation': self.execution.generation}

    def bind_value(self, value):
        """Use the same prepared Controller for preflight and reconstruction."""
        return {**value, 'physical_execution': self.execution,
                'controller': self.execution.controllers[0],
                'selected_controller_profile_id': self.execution.selection_profile_id}


class PhysicalResetSelection:
    """Own the action identity and generation of one switchable scalar Env.

    The factory supplies fresh Controllers; preparation is side-effect free with
    respect to the live Env.  A fixed-space consumer may pin the *semantic*
    identity, not merely an array shape.  This class does not run physics.
    """
    def __init__(self, factory, *, initial_kind, allowed_kinds, space_policy='dynamic', declaration=None):
        if not callable(factory) or type(initial_kind) is not str or not initial_kind:
            raise ValueError('physical reset selection requires a factory and initial kind')
        if (type(allowed_kinds) is not tuple or not allowed_kinds
                or len(set(allowed_kinds)) != len(allowed_kinds)
                or any(type(x) is not str or not x for x in allowed_kinds)
                or initial_kind not in allowed_kinds):
            raise ValueError('physical reset selection requires distinct declared controller kinds')
        if space_policy not in {'dynamic', 'fixed_semantic'}:
            raise ValueError('unknown physical action-space policy')
        if declaration is not None and type(declaration) is not PhysicalControlExecutionV1:
            raise TypeError('physical selection declaration must be a physical execution')
        self.declaration = declaration
        self._factory, self._allowed = factory, allowed_kinds
        self._initial_kind, self._policy = initial_kind, space_policy
        self._generation, self._current = 0, None
        self._owner = object()

    def prepare(self, kind=None):
        parameters = {}
        if isinstance(kind, Mapping):
            if set(kind) != {'kind', 'parameters'} or not isinstance(kind['parameters'], Mapping):
                raise ValueError('physical controller selection requires kind and parameters')
            parameters = dict(kind['parameters'])
            if any(type(key) is not str for key in parameters):
                raise ValueError('physical controller parameter names must be strings')
            kind = kind['kind']
        elif kind is None and self._current is not None:
            parameters = dict(self._current.parameters)
        kind = self._initial_kind if kind is None and self._current is None else (
            self._current.kind if kind is None else kind)
        if type(kind) is not str or kind not in self._allowed:
            raise ValueError('unsupported physical controller reset selection')
        profile = self._factory(kind, **parameters)
        if type(profile) is not PhysicalControlExecutionV1 or len(profile.controllers) != 1:
            raise ValueError('switchable physical route requires one typed controller')
        controller = profile.controllers[0]
        shape = getattr(controller, 'action_shape', None)
        if type(shape) is not tuple or not shape or any(type(x) is not int or x < 1 for x in shape):
            raise ValueError('physical controller must declare one action layout')
        spec_id = digest({'schema': 'physical-reset-action-spec-v1', 'kind': kind,
                          'controller_identity': controller.identity, 'shape': list(shape)})
        if self._policy == 'fixed_semantic' and self._current is not None and spec_id != self._current.spec_id:
            raise ValueError('fixed semantic action space rejects a different controller spec')
        return PreparedPhysicalSelection(self._owner, self._generation, kind, tuple(sorted(parameters.items())),
            replace(profile, generation=self._generation + 1), spec_id)

    def commit(self, candidate):
        if (type(candidate) is not PreparedPhysicalSelection
                or candidate.owner is not self._owner
                or candidate.previous_generation != self._generation
                or candidate.execution.generation != self._generation + 1):
            raise ValueError('physical reset selection is stale or foreign')
        self._generation += 1
        self._current = candidate

    @property
    def committed(self):
        """Return the committed choice, or None before the first reset."""
        return self._current

    @property
    def current(self):
        if self._current is None:
            raise RuntimeError('physical controller selection requires reset')
        return self._current

    def describe(self):
        current = self.current
        controller = current.execution.controllers[0]
        return {'schema_version': 'physical-reset-action-spec-v1', 'kind': current.kind,
                'spec_id': current.spec_id, 'generation': current.execution.generation,
                'controller_identity': controller.identity, 'shape': list(controller.action_shape),
                'parameters': dict(current.parameters), 'space_policy': self._policy}

    def bind_action(self, values):
        spec = self.describe()
        return {'spec_id': spec['spec_id'], 'generation': spec['generation'], 'values': values}

    def action_space(self):
        """Expose a stable envelope; validate_action enforces the exact identity and generation."""
        from gymnasium.spaces import Dict, Discrete, Text
        spec = self.describe()
        return Dict({'spec_id': Text(min_length=64, max_length=64, charset='0123456789abcdef'),
                     'generation': Discrete(np.iinfo(np.int64).max - 1, start=1),
                     'values': self.current.execution.action_space()})

    def validate_action(self, action):
        if not isinstance(action, Mapping) or set(action) != {'spec_id', 'generation', 'values'}:
            raise ValueError('switchable physical action requires spec_id, generation and values')
        spec = self.describe()
        generation = action['generation']
        if (action['spec_id'] != spec['spec_id'] or isinstance(generation, (bool, np.bool_))
                or not isinstance(generation, (int, np.integer)) or int(generation) != spec['generation']):
            raise ValueError('physical action spec or generation is stale or foreign')
        raw = np.asarray(action['values'])
        if (raw.shape != tuple(spec['shape']) or raw.dtype.kind not in 'iuf'
                or not np.isfinite(raw).all()):
            raise ValueError('physical action values differ from the declared finite scalar layout')
        return raw.copy()
