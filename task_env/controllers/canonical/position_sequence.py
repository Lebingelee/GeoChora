"""Open-loop absolute-joint actions for one source-bound Position interval."""
from dataclasses import dataclass
import math

from .contracts import RequestedAction, digest


@dataclass(frozen=True)
class PositionActionSliceV1:
    start_substep: int
    end_substep: int
    request: RequestedAction


@dataclass(frozen=True)
class PositionActionSequenceV1:
    slices: tuple[PositionActionSliceV1, ...]
    schema_version: str = 'position-action-sequence-v1'

    def validate(self, *, substeps):
        if self.schema_version != 'position-action-sequence-v1':
            raise ValueError('unsupported Position sequence schema')
        if type(substeps) is not int or substeps <= 0:
            raise ValueError('Position sequence requires an integral positive timebase')
        if type(self.slices) is not tuple or not self.slices:
            raise ValueError('Position sequence requires immutable nonempty slices')
        cursor = 0
        for item in self.slices:
            if (type(item) is not PositionActionSliceV1
                    or type(item.start_substep) is not int or type(item.end_substep) is not int
                    or item.start_substep != cursor or not cursor < item.end_substep <= substeps):
                raise ValueError('Position slices must cover the interval without gaps or overlaps')
            if type(item.request) is not RequestedAction or item.request.mode != 'absolute_joint':
                raise ValueError('Position sequence requires absolute-joint requests')
            item.request.validate()
            if (type(item.request.values) is not tuple
                    or any(type(value) not in (int, float) or not math.isfinite(value)
                           for value in item.request.values)):
                raise ValueError('Position sequence requires immutable finite numeric actions')
            cursor = item.end_substep
        if cursor != substeps:
            raise ValueError('Position slices must cover the complete interval')

    @property
    def identity_hash(self):
        return digest({'schema_version': self.schema_version, 'slices': tuple(
            {'start_substep': item.start_substep, 'end_substep': item.end_substep,
             'request': item.request.to_mapping()} for item in self.slices)})
