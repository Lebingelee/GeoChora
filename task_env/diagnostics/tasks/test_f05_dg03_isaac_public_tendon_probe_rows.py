"""Offline regression coverage for the DG03 N1 readback adapter.

This protects only the probe's scalar-row normalization. It does not exercise
Isaac Sim, PhysX, USD consumption, or any physical capability.
"""

from array import array

import pytest

from task_env.diagnostics.tasks.f05_dg03_isaac_public_tendon_probe import _rows


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
