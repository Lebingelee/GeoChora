from enum import Enum
from types import SimpleNamespace

import numpy as np
import pytest

from task_env.runtime.sessions.mujoco import _MuJoCoSession


class _JointType(Enum):
    FREE = 0
    BALL = 1
    SLIDE = 2
    HINGE = 3

    def __int__(self):
        return self.value


class _Model:
    def __init__(self, joint_type):
        self.jnt_type = np.asarray([joint_type], dtype=np.int32)
        self.jnt_qposadr = np.asarray([7], dtype=np.int32)
        self.jnt_dofadr = np.asarray([6], dtype=np.int32)

    @staticmethod
    def joint(name):
        assert name == "joint-v1/native"
        return SimpleNamespace(id=0)


def _session(joint_type):
    session = object.__new__(_MuJoCoSession)
    session._model = _Model(joint_type)
    session._mj = SimpleNamespace(mjtJoint=SimpleNamespace(
        mjJNT_FREE=_JointType.FREE,
        mjJNT_BALL=_JointType.BALL,
        mjJNT_SLIDE=_JointType.SLIDE,
        mjJNT_HINGE=_JointType.HINGE,
    ))
    return session


@pytest.mark.parametrize("joint_type", (_JointType.HINGE, _JointType.SLIDE))
def test_addresses_normalize_numpy_scalar_before_scalar_enum_membership(joint_type):
    session = _session(int(joint_type))

    assert session._addresses("joint-v1/native", free=False) == (7, 6)


def test_addresses_normalize_numpy_scalar_before_free_enum_membership():
    session = _session(int(_JointType.FREE))

    assert session._addresses("joint-v1/native", free=True) == (7, 6)


@pytest.mark.parametrize(
    ("joint_type", "free"),
    ((_JointType.BALL, False), (_JointType.HINGE, True)),
)
def test_addresses_still_rejects_incompatible_joint_representation(joint_type, free):
    session = _session(int(joint_type))

    with pytest.raises(ValueError, match="unsupported source joint representation"):
        session._addresses("joint-v1/native", free=free)
