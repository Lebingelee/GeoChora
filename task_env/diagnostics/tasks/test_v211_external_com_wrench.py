"""Pure admission and ownership tests; no physics SDK is loaded here."""
from types import SimpleNamespace

import numpy as np
import pytest

from task_env.controllers.canonical.physical_commands import ExternalComWrenchV1
from task_env.runtime.sessions.mujoco_external_wrench import MuJoCoExternalComPort


def _session():
    points = []
    model = SimpleNamespace(nv=2, opt=SimpleNamespace(integrator=3),
        body=lambda name: SimpleNamespace(id={'object-native': 1}[name]),
        body_mass=np.array([0., 2.]), body_parentid=np.array([0, 0]), body_dofnum=np.array([0, 6]))
    data = SimpleNamespace(qfrc_applied=np.zeros(2), xfrc_applied=np.zeros((2, 6)),
                           xipos=np.array([[0., 0., 0.], [1., 2., 3.]]))
    def apply(_model, _data, force, torque, point, body, target):
        points.append(tuple(point))
        target[:] += (force[1], torque[2])
    mj = SimpleNamespace(__version__='3.8.1', mjtIntegrator=SimpleNamespace(mjINT_IMPLICITFAST=3),
        mj_kinematics=lambda *_: None, mj_comPos=lambda *_: None, mj_applyFT=apply)
    boundary = object()
    session = SimpleNamespace(_provider='mujoco', _physical_port=None, _mixed_actuator_plan=None,
        _model=model, _data=data, _mj=mj, _require_reset=lambda: None,
        _source=SimpleNamespace(bodies={'object': 'object-native'}, source_id='task',
                                source_closure_digest='a' * 64),
        _artifact=SimpleNamespace(identity_hash='b' * 64,
                                  timebase=SimpleNamespace(control_substeps=5)),
        state_boundary_identity=lambda: boundary)
    return session, boundary, points


def _request(effect='effect', body='object'):
    return ExternalComWrenchV1('external-com-wrench-v1', effect, body, (0., 2., 0.), (0., 0., 1.))


def test_com_refresh_reads_current_com_and_preserves_foreign_writes():
    s, boundary, points = _session()
    port = MuJoCoExternalComPort(s, (_request(),))
    s._external_com_port = port
    interval = SimpleNamespace(boundary=boundary, source_id='task', source_closure_sha256='a' * 64,
                               artifact_sha256='b' * 64, substeps=5)
    port.verify(interval)
    s._source.bodies.clear()
    with pytest.raises(ValueError, match='body binding changed'):
        port.verify(interval)
    s._source.bodies['object'] = 'object-native'
    with pytest.raises(RuntimeError, match='submission owner'):
        port.refresh_substep()
    port.authorized = True
    port.refresh_substep()
    s._data.xipos[1] = (4., 5., 6.)
    port.refresh_substep()
    assert points == [(1., 2., 3.), (4., 5., 6.)]
    assert s._data.qfrc_applied.tolist() == [2., 1.]
    s._data.qfrc_applied[1] = 7.
    with pytest.raises(RuntimeError, match='foreign force buffer'):
        port.preflight_reset()
    with pytest.raises(RuntimeError, match='changed during interval'):
        port.refresh_substep()
    port.finish()
    assert s._data.qfrc_applied.tolist() == [0., 7.]
    assert s._external_com_port is None


def test_com_stage_rejects_unbound_alias_duplicate_and_occupied_buffers():
    s, _, _ = _session()
    with pytest.raises(ValueError, match='not bound'):
        MuJoCoExternalComPort(s, (_request(body='foreign'),))
    with pytest.raises(ValueError, match='unique'):
        MuJoCoExternalComPort(s, (_request(), _request(effect='another')))
    s._data.xfrc_applied[1, 0] = 4.
    with pytest.raises(ValueError, match='occupied'):
        MuJoCoExternalComPort(s, (_request(),))
    assert s._data.xfrc_applied[1, 0] == 4.


def test_active_recorder_rejects_unrecorded_caller_force_before_staging():
    from task_env.environment.reference_env import SelectedReferenceEnv
    from task_env.environment.types import StageUnavailableError
    env = object.__new__(SelectedReferenceEnv)
    env._require_execution_healthy = lambda: None
    env.recorder = SimpleNamespace(active=True)
    with pytest.raises(StageUnavailableError, match='not represented by the active Recorder'):
        env.step(object(), external_com_wrenches=(_request(),))
