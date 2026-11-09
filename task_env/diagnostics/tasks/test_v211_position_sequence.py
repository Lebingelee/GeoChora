"""Pure contract checks for bounded Position sequences."""
from dataclasses import replace
import pytest
from task_env.controllers.canonical.contracts import RequestedAction
from task_env.controllers.canonical.position_sequence import PositionActionSequenceV1, PositionActionSliceV1


def test_position_slices_are_immutable_contiguous_absolute_joint_requests():
    action = RequestedAction('absolute_joint', None, 'none', (0., -.2, 0., -1.5, 0., 1.5, -.7, .5))
    first = PositionActionSliceV1(0, 2, action)
    second = PositionActionSliceV1(2, 5, action)
    sequence = PositionActionSequenceV1((first, second))
    sequence.validate(substeps=5)
    assert sequence.identity_hash != replace(sequence, slices=(first, replace(second, end_substep=4))).identity_hash
    for start in (1, 3, 2.0):
        with pytest.raises(ValueError):
            replace(sequence, slices=(first, replace(second, start_substep=start))).validate(substeps=5)
    with pytest.raises(ValueError, match='complete'):
        replace(sequence, slices=(first, replace(second, end_substep=4))).validate(substeps=5)
    pose = RequestedAction('absolute_pose', 'world', 'quaternion_wxyz', (0., 0., 0., 1., 0., 0., 0., 0.))
    with pytest.raises(ValueError, match='absolute-joint'):
        replace(sequence, slices=(first, replace(second, request=pose))).validate(substeps=5)


def test_position_sequence_rejects_mutable_or_boolean_action_values():
    request = RequestedAction('absolute_joint', None, 'none', (0., 0., 0., -1., 0., 1., 0., 0.))
    sequence = PositionActionSequenceV1((PositionActionSliceV1(0, 5, request),))
    for values in (list(request.values), (True, *request.values[1:])):
        tampered = replace(request)
        object.__setattr__(tampered, 'values', values)
        with pytest.raises(ValueError, match='immutable finite'):
            replace(sequence, slices=(replace(sequence.slices[0], request=tampered),)).validate(substeps=5)
