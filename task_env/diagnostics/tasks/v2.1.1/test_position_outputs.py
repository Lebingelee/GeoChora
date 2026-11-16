"""Common multi-writer Position output ownership is independent of Robot names."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from task_env.controllers.canonical.position_outputs import PositionOutputBundleV1, PositionWriterOutputV1


def test_position_outputs_match_actual_writer_identities_and_target():
    target = SimpleNamespace(identity_hash='target', controller_identity='combined')
    plan = SimpleNamespace(controller_bindings=(
        SimpleNamespace(writer_id='left', controller_identity='left-controller'),
        SimpleNamespace(writer_id='right', controller_identity='right-controller'),
    ))
    first = PositionWriterOutputV1('left', 'left-controller', 'left-output', 'joint-position', ('rad',))
    second = PositionWriterOutputV1('right', 'right-controller', 'right-output', 'joint-position', ('rad',))
    bundle = PositionOutputBundleV1('target', 'combined', (first, second))
    bundle.validate_target(target, plan)
    with pytest.raises(ValueError, match='writers'):
        replace(bundle, outputs=(first, replace(second, controller_identity='foreign'))).validate_target(target, plan)
    with pytest.raises(ValueError, match='writers'):
        replace(bundle, outputs=(first, first)).validate_target(target, plan)
    with pytest.raises(ValueError, match='canonical target'):
        bundle.validate_target(SimpleNamespace(identity_hash='stale', controller_identity='combined'), plan)
