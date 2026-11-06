"""SDK-free session tests for a held spatial wrench on a moving body."""
import math
from types import SimpleNamespace

import numpy as np
import pytest

from task_env.artifacts import FrameReference
from task_env.controllers.canonical.physical_commands import BodyWrenchV1, ContributionPolicyV1
from task_env.artifacts.contracts import PoseWorld
from task_env.diagnostics.tasks.test_v211_physical_control_contract import _case
from task_env.runtime.sessions.mujoco import _MuJoCoSession
from task_env.runtime.sessions.mujoco_physical import MuJoCoPhysicalPort
from task_env.runtime.sessions.physical_control import resolve_body_wrench_at_poses


@pytest.mark.parametrize('force_frame,reference,expected', [
    ('world', 'point', (1.3, .3)),
    ('body', 'point', (1.3, 1.3)),
    ('site', 'point', (1.3, 1.3)),
    ('world', 'origin', (.3, .3)),
])
def test_actual_session_reprojects_held_wrench_at_each_configuration(force_frame, reference, expected):
    """A unit lever and unit force have analytical torque cos(q) or 1 N*m."""
    _, context, _, _ = _case()
    world, body = FrameReference('scene', 'world'), FrameReference('arm', 'tool')
    site = FrameReference('arm', 'tip')
    policy = ContributionPolicyV1('physical-contribution-policy-v1', 'wrench-a', 'effect-a',
                                  'writer-a', 'exclusive', 'reject_outside', 'hold_reapply')
    wrench = BodyWrenchV1('body-wrench-v1', context, policy, 'arm', 'tool',
        {'world': world, 'body': body, 'site': site}[force_frame], (1., 0., 0.), body,
        (1., 0., 0.) if reference == 'point' else (0., 0., 0.), body,
        (0., 1., 0.), (0., 0., 0.))
    data = SimpleNamespace(q=0., qfrc_applied=np.array([expected[0]]), xfrc_applied=np.zeros((2,6)),
        xpos=np.zeros((2,3)), xquat=np.array([[1.,0.,0.,0.],[1.,0.,0.,0.]]),
        site_xpos=np.zeros((1,3)), site_xmat=np.array([np.eye(3)]))
    observed, refreshes = [], []
    def kinematics(_model, d):
        d.xquat[1] = (math.cos(d.q/2), 0., 0., math.sin(d.q/2))
        c, s = math.cos(d.q), math.sin(d.q)
        d.site_xmat[0] = ((c,-s,0.),(s,c,0.),(0.,0.,1.))
        refreshes.append(d.q)
    def apply_ft(_model, _data, force, torque, point, body_id, target):
        assert body_id == 1
        target[0] += torque[2] + np.cross(point, force)[2]
    def step(_model, d):
        observed.append(float(d.qfrc_applied[0])); d.q = math.pi/2
    def mat2quat(out, matrix):
        out[:] = (math.cos(data.q/2), 0., 0., math.sin(data.q/2))
    mj = SimpleNamespace(mjtIntegrator=SimpleNamespace(mjINT_IMPLICITFAST=3), mju_mat2Quat=mat2quat,
                         mj_kinematics=kinematics, mj_comPos=lambda *_: None,
                         mj_applyFT=apply_ft, mj_step=step, mj_forward=lambda *_: None)
    session = object.__new__(_MuJoCoSession)
    session._require_reset = lambda: None
    session._artifact = SimpleNamespace(timebase=SimpleNamespace(control_substeps=2))
    session._model, session._data, session._mj = SimpleNamespace(opt=SimpleNamespace(integrator=3)), data, mj
    session._native_steps = session._control_step = session._state_revision = 0
    session.snapshot = lambda: None
    port = object.__new__(MuJoCoPhysicalPort)
    port.session, port.pending, port.pending_values = session, 'boundary', np.array([expected[0]])
    port.pending_joints = np.array([.3])
    port.pending_wrenches = (wrench,)
    port.kinematics_refreshes = 0
    port.frame_handles = {world: ('body', 0), body: ('body', 1), site: ('site', 0)}
    port.body_frames = {('arm','tool'): body}
    port.bodies = {('arm','tool'): 1}
    session._physical_port = port
    session.step()
    assert observed == pytest.approx(expected, abs=1e-12)
    assert refreshes == pytest.approx((0., math.pi/2), abs=1e-12)
    assert data.qfrc_applied[0] == 0 and not np.any(data.xfrc_applied)
    assert port.pending is None


def test_reference_point_and_rotated_body_are_distinct_physical_wrenches():
    _, context, _, _ = _case()
    world, body = FrameReference('scene', 'world'), FrameReference('arm', 'tool')
    policy = ContributionPolicyV1('physical-contribution-policy-v1', 'wrench-a', 'effect-a',
                                  'writer-a', 'exclusive', 'reject_outside', 'one_interval')
    base = BodyWrenchV1('body-wrench-v1', context, policy, 'arm', 'tool', world,
        (.01,0.,0.), body, (.01,0.,0.), body, (0.,0.,1.), (0.,0.,0.))
    identity = PoseWorld((0.,0.,0.), (1.,0.,0.,0.))
    poses = {world: identity, body: identity}
    _, force, moment = resolve_body_wrench_at_poses(base, body, poses)
    assert force == pytest.approx((0.,0.,1.))
    assert moment == pytest.approx((0.,-.01,0.))
    from dataclasses import replace
    _, _, origin_moment = resolve_body_wrench_at_poses(replace(base, moment_reference=(0.,0.,0.)), body, poses)
    assert origin_moment == pytest.approx((0.,0.,0.))
    q = math.sqrt(.5)
    poses[body] = PoseWorld((0.,0.,0.), (q,q,0.,0.))
    body_force = replace(base, expressed_in=body)
    _, rotated_force, rotated_moment = resolve_body_wrench_at_poses(body_force, body, poses)
    assert rotated_force == pytest.approx((0.,-1.,0.), abs=1e-12)
    assert rotated_moment == pytest.approx((0.,0.,-.01), abs=1e-12)
    couple = replace(body_force, force_N=(0.,0.,0.), torque_Nm=(0.,0.,2.))
    _, _, pure_moment = resolve_body_wrench_at_poses(couple, body, poses)
    assert pure_moment == pytest.approx((0.,-2.,0.), abs=1e-12)


@pytest.mark.parametrize('foreign_kind', ['generalized', 'body'])
def test_foreign_force_conflict_faults_without_overwriting_foreign_buffer(foreign_kind):
    data = SimpleNamespace(qfrc_applied=np.array([.3]), xfrc_applied=np.zeros((2,6)))
    def step(_model, d):
        if foreign_kind == 'generalized':
            d.qfrc_applied[0] = 7.
        else:
            d.xfrc_applied[1,0] = 7.
    session = object.__new__(_MuJoCoSession)
    session._require_reset = lambda: None
    session._artifact = SimpleNamespace(timebase=SimpleNamespace(control_substeps=2))
    session._model, session._data = object(), data
    session._mj = SimpleNamespace(mj_step=step)
    session._native_steps = 0
    port = object.__new__(MuJoCoPhysicalPort)
    port.session, port.pending, port.pending_values = session, 'boundary', np.array([.3])
    port.pending_joints, port.pending_wrenches = np.array([.3]), ()
    session._physical_port = port
    with pytest.raises(RuntimeError, match='buffer changed'):
        session.step()
    assert port.pending is None
    if foreign_kind == 'generalized':
        assert data.qfrc_applied[0] == 7.
    else:
        assert data.xfrc_applied[1,0] == 7. and data.qfrc_applied[0] == 0.


def test_reset_and_close_clear_owned_force_without_erasing_foreign_force():
    from task_env.artifacts.execution import ResetSample
    data = SimpleNamespace(qfrc_applied=np.array([.3]), xfrc_applied=np.zeros((2,6)))
    session = object.__new__(_MuJoCoSession)
    session._mixed_actuator_plan = None
    session._validate_sample = lambda sample: None
    def stop_after_clear():
        raise RuntimeError('stop after pre-reset cleanup')
    session._begin_reset = stop_after_clear
    session._data, session._model = data, object()
    port = object.__new__(MuJoCoPhysicalPort)
    port.session, port.pending, port.pending_values = session, 'boundary', np.array([.3])
    port.pending_joints, port.pending_wrenches = np.array([.3]), ()
    session._physical_port = port
    sample = object.__new__(ResetSample)
    data.xfrc_applied[1,0] = 7.
    with pytest.raises(RuntimeError, match='foreign force buffer'):
        session.reset(sample)
    assert data.qfrc_applied[0] == .3 and data.xfrc_applied[1,0] == 7.
    data.xfrc_applied[:] = 0.
    with pytest.raises(RuntimeError, match='stop after pre-reset cleanup'):
        session.reset(sample)
    assert data.qfrc_applied[0] == 0. and port.pending is None
    port.pending, port.pending_values = 'boundary-2', np.array([.4])
    data.qfrc_applied[0] = .4
    session._closed, session._source = False, SimpleNamespace(fixed_attachment_plan=None)
    session.close()
    assert data.qfrc_applied[0] == 0. and port.pending is None and session._closed


def test_foreign_write_during_projection_is_not_overwritten():
    data = SimpleNamespace(qfrc_applied=np.array([.3]), xfrc_applied=np.zeros((2,6)))
    session = object.__new__(_MuJoCoSession)
    session._require_reset = lambda: None
    session._artifact = SimpleNamespace(timebase=SimpleNamespace(control_substeps=1))
    session._model, session._data, session._mj = object(), data, SimpleNamespace()
    port = object.__new__(MuJoCoPhysicalPort)
    port.session, port.pending, port.pending_values = session, 'boundary', np.array([.3])
    port.pending_joints, port.pending_wrenches = np.array([.3]), ()
    def foreign_during_projection(*args):
        data.qfrc_applied[0] = 7.
        return np.array([.3])
    port._project_current = foreign_during_projection
    session._physical_port = port
    with pytest.raises(RuntimeError, match='changed during projection'):
        session.step()
    assert data.qfrc_applied[0] == 7. and port.pending is None


def test_projection_exception_clears_only_owned_pending_force():
    data = SimpleNamespace(qfrc_applied=np.array([.3]), xfrc_applied=np.zeros((2,6)))
    session = object.__new__(_MuJoCoSession)
    session._require_reset = lambda: None
    session._artifact = SimpleNamespace(timebase=SimpleNamespace(control_substeps=1))
    session._model, session._data, session._mj = object(), data, SimpleNamespace()
    port = object.__new__(MuJoCoPhysicalPort)
    port.session, port.pending, port.pending_values = session, 'boundary', np.array([.3])
    port.pending_joints, port.pending_wrenches = np.array([.3]), ()
    def fail_projection(*args):
        raise RuntimeError('projection failed')
    port._project_current = fail_projection
    session._physical_port = port
    with pytest.raises(RuntimeError, match='projection failed'):
        session.step()
    assert data.qfrc_applied[0] == 0. and port.pending is None


def test_reapplying_spatial_load_across_intervals_does_not_accumulate():
    _, context, _, _ = _case()
    world, body = FrameReference('scene', 'world'), FrameReference('arm', 'tool')
    policy = ContributionPolicyV1('physical-contribution-policy-v1', 'wrench-a', 'effect-a',
                                  'writer-a', 'exclusive', 'reject_outside', 'hold_reapply')
    wrench = BodyWrenchV1('body-wrench-v1', context, policy, 'arm', 'tool', world,
        (1.,0.,0.), body, (1.,0.,0.), body, (0.,1.,0.), (0.,0.,0.))
    data = SimpleNamespace(qfrc_applied=np.zeros(1), xfrc_applied=np.zeros((2,6)),
        xpos=np.zeros((2,3)), xquat=np.array([[1.,0.,0.,0.],[1.,0.,0.,0.]]))
    samples = []
    def project(_model, _data, force, torque, point, body_id, target):
        target[0] += torque[2]
    session = object.__new__(_MuJoCoSession)
    session._require_reset = lambda: None
    session._artifact = SimpleNamespace(timebase=SimpleNamespace(control_substeps=2))
    session._model, session._data = SimpleNamespace(opt=SimpleNamespace(integrator=3)), data
    session._mj = SimpleNamespace(mjtIntegrator=SimpleNamespace(mjINT_IMPLICITFAST=3),
        mj_kinematics=lambda *_: None, mj_comPos=lambda *_: None, mj_applyFT=project,
        mj_step=lambda _model,d: samples.append(float(d.qfrc_applied[0])), mj_forward=lambda *_: None)
    session._native_steps = session._control_step = session._state_revision = 0
    session.snapshot = lambda: None
    port = object.__new__(MuJoCoPhysicalPort)
    port.session, port.frame_handles = session, {world: ('body',0), body: ('body',1)}
    port.body_frames, port.bodies, port.kinematics_refreshes = {('arm','tool'): body}, {('arm','tool'):1}, 0
    session._physical_port = port
    for interval in range(2):
        port.pending, port.pending_values = f'boundary-{interval}', np.array([1.3])
        port.pending_joints, port.pending_wrenches = np.array([.3]), (wrench,)
        data.qfrc_applied[:] = 1.3
        session.step()
        assert data.qfrc_applied[0] == 0. and port.pending is None
    assert samples == pytest.approx((1.3,1.3,1.3,1.3), abs=1e-12)
