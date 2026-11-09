"""Bounded open-loop action fragments for one physical control interval."""
from dataclasses import dataclass
import math

from .contracts import digest


@dataclass(frozen=True)
class PhysicalActionSliceV1:
    """One half-open range of actions keyed by actual Controller identity."""
    start_substep: int
    end_substep: int
    actions: tuple[tuple[str, tuple[float, ...]], ...]

    def validate(self, substeps):
        if (type(self.start_substep) is not int or type(self.end_substep) is not int
                or not 0 <= self.start_substep < self.end_substep <= substeps):
            raise ValueError('physical action slice requires a half-open substep range')
        if type(self.actions) is not tuple or not self.actions:
            raise TypeError('physical action slice requires immutable Controller actions')
        identities = []
        for row in self.actions:
            if type(row) is not tuple or len(row) != 2:
                raise TypeError('physical slice actions must be identity/action pairs')
            identity, values = row
            if (type(identity) is not str or len(identity) != 64
                    or any(c not in '0123456789abcdef' for c in identity)
                    or type(values) is not tuple or not values
                    or any(type(x) not in (int, float) or not math.isfinite(x) for x in values)):
                raise ValueError('physical slice requires exact identities and finite numeric tuples')
            identities.append(identity)
        if len(identities) != len(set(identities)):
            raise ValueError('physical action slice repeats a Controller')


@dataclass(frozen=True)
class PhysicalActionSequenceV1:
    """One action with precomputed inputs covering a complete outer interval."""
    slices: tuple[PhysicalActionSliceV1, ...]
    schema_version: str = 'physical-action-sequence-v1'

    def validate(self, *, substeps, controller_identities):
        if self.schema_version != 'physical-action-sequence-v1':
            raise ValueError('unsupported physical action sequence schema')
        if type(substeps) is not int or substeps <= 0:
            raise ValueError('physical sequence requires an integral positive timebase')
        if type(self.slices) is not tuple or not self.slices:
            raise TypeError('physical sequence requires immutable slices')
        cursor = 0
        for item in self.slices:
            if type(item) is not PhysicalActionSliceV1:
                raise TypeError('physical sequence contains an untyped slice')
            item.validate(substeps)
            if item.start_substep != cursor:
                raise ValueError('physical action slices must cover the interval without gaps or overlaps')
            if {identity for identity, _ in item.actions} != set(controller_identities):
                raise ValueError('each physical action slice must cover the bound Controllers')
            cursor = item.end_substep
        if cursor != substeps:
            raise ValueError('physical action slices must cover the complete interval')

    @property
    def identity_hash(self):
        return digest({'schema_version': self.schema_version,
            'slices': tuple({'start_substep': x.start_substep, 'end_substep': x.end_substep,
                             'actions': x.actions} for x in self.slices)})
