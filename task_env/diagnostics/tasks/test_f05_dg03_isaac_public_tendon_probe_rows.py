"""Offline regression coverage for the DG03 N1 readback adapter.

This protects only the probe's scalar-row normalization. It does not exercise
Isaac Sim, PhysX, USD consumption, or any physical capability.
"""

from array import array

import pytest

from task_env.diagnostics.tasks.f05_dg03_isaac_public_tendon_probe import (
    _remove_source_equality_for_ablation,
    _source_equality_probe_outcome,
    _rows,
)


class _ListConvertible:
    def tolist(self):
        return [array("d", [1.25, 2.5]), [3.75]]


class _SequenceOnly:
    """Models native array wrappers that expose indexing but no __iter__."""

    def __init__(self, values):
        self._values = values

    def __getitem__(self, index):
        return self._values[index]


class _NumpyConvertible:
    """Models Warp public array readback without importing the Isaac runtime."""

    def numpy(self):
        return array("d", [1.0, 2.0, 3.0])


@pytest.mark.parametrize(
    "value",
    [
        array("d", [1.0, 2.0, 3.0]),
        [array("d", [1.0, 2.0]), [3.0]],
        _ListConvertible(),
        _SequenceOnly([1.0, 2.0, 3.0]),
        _NumpyConvertible(),
    ],
)
def test_rows_flattens_iterable_and_list_convertible_arrays(value):
    expected = [1.25, 2.5, 3.75] if isinstance(value, _ListConvertible) else [1.0, 2.0, 3.0]

    assert _rows(value, 3) == expected


def test_rows_rejects_wrong_width_and_nonfinite_values():
    with pytest.raises(ValueError, match="invalid width"):
        _rows(array("d", [1.0, 2.0]), 3)

    with pytest.raises(ValueError, match="nonfinite"):
        _rows([1.0, float("nan"), 3.0], 3)


def test_source_equality_probe_uses_asymmetric_relation_error_for_positive_and_ablation():
    assert _source_equality_probe_outcome(
        equality_removed=False,
        initial_difference_m=0.016,
        final_difference_m=0.001,
        leader_motion_m=0.004,
    )
    assert _source_equality_probe_outcome(
        equality_removed=True,
        initial_difference_m=0.016,
        final_difference_m=0.015,
        leader_motion_m=0.004,
    )
    assert not _source_equality_probe_outcome(
        equality_removed=True,
        initial_difference_m=0.016,
        final_difference_m=0.001,
        leader_motion_m=0.004,
    )
    assert not _source_equality_probe_outcome(
        equality_removed=False,
        initial_difference_m=0.016,
        final_difference_m=0.015,
        leader_motion_m=0.004,
    )
    assert not _source_equality_probe_outcome(
        equality_removed=True,
        initial_difference_m=0.0,
        final_difference_m=0.015,
        leader_motion_m=0.004,
    )


def test_mimic_ablation_removes_all_encodings_of_one_equality_only():
    from pxr import Sdf, Usd

    stage = Usd.Stage.CreateInMemory()
    leader = stage.DefinePrim("/leader")
    follower = stage.DefinePrim("/follower")
    api_schemas = Sdf.TokenListOp()
    api_schemas.prependedItems = ["PhysxMimicJointAPI:transX"]
    follower.SetMetadata("apiSchemas", api_schemas)
    follower.CreateRelationship("physxMimicJoint:transX:referenceJoint")
    for name in (
        "gearing", "offset", "naturalFrequency", "dampingRatio",
    ):
        follower.CreateAttribute(
            f"physxMimicJoint:transX:{name}", Sdf.ValueTypeNames.Float,
        ).Set(1.0)
    leader_schemas = Sdf.TokenListOp()
    leader_schemas.prependedItems = [
        "NewtonJointAPI", "MjcJointAPI", "NewtonMimicAPI", "MjcEqualityJointAPI",
    ]
    leader.SetMetadata("apiSchemas", leader_schemas)
    leader.CreateRelationship("newton:mimicJoint").SetTargets([follower.GetPath()])
    leader.CreateAttribute("mjc:solref", Sdf.ValueTypeNames.DoubleArray).Set([0.005, 1.0])
    leader.CreateAttribute("mjc:solimp", Sdf.ValueTypeNames.DoubleArray).Set(
        [0.95, 0.99, 0.001, 0.5, 2.0],
    )
    leader.CreateAttribute("mjc:damping", Sdf.ValueTypeNames.Double).Set(1.0)

    removed = _remove_source_equality_for_ablation(leader, follower)

    assert "PhysxMimicJointAPI:transX" not in follower.GetMetadata("apiSchemas").GetAppliedItems()
    assert not ({"NewtonMimicAPI", "MjcEqualityJointAPI"}
                & set(leader.GetMetadata("apiSchemas").GetAppliedItems()))
    assert {"NewtonJointAPI", "MjcJointAPI"}.issubset(
        set(leader.GetMetadata("apiSchemas").GetAppliedItems()),
    )
    assert len(removed["removed_schema_tokens"]) == 3
    assert len(removed["removed_properties"]) == 8
    assert follower.GetRelationship("physxMimicJoint:transX:referenceJoint").GetTargets() == []
    for name in removed["removed_properties"][1:5]:
        assert follower.GetAttribute(name).Get() is None
    assert leader.GetRelationship("newton:mimicJoint").GetTargets() == []
    for name in removed["removed_properties"][6:]:
        assert leader.GetAttribute(name).Get() is None
    assert leader.GetAttribute("mjc:damping").Get() == 1.0
