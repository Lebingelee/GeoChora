"""Controller-declared outputs for a multi-writer Position target."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PositionWriterOutputV1:
    writer_id: str
    controller_identity: str
    output_hash: str
    kind: str
    units: tuple[str, ...]


@dataclass(frozen=True)
class PositionOutputBundleV1:
    """Bind component outputs to one canonical target and its Controller plan."""
    target_hash: str
    controller_identity: str
    outputs: tuple[PositionWriterOutputV1, ...]

    def validate_target(self, target, plan):
        if target.identity_hash != self.target_hash or target.controller_identity != self.controller_identity:
            raise ValueError('Position outputs differ from their canonical target')
        if (type(self.outputs) is not tuple or len(self.outputs) < 2
                or any(type(item) is not PositionWriterOutputV1 for item in self.outputs)):
            raise TypeError('Position outputs require immutable writer declarations')
        if any(any(type(value) is not str or not value for value in
                       (item.writer_id, item.controller_identity, item.output_hash, item.kind))
               or type(item.units) is not tuple or not item.units
               or any(type(unit) is not str or not unit for unit in item.units)
               for item in self.outputs):
            raise ValueError('Position writer output declaration is incomplete')
        actual = {item.writer_id: item.controller_identity for item in self.outputs}
        expected = {item.writer_id: item.controller_identity for item in plan.controller_bindings}
        if len(actual) != len(self.outputs) or actual != expected:
            raise ValueError('Position output writers differ from the source-bound plan')
