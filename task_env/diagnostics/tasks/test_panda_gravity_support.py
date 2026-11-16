"""Source-bound gravity math; these tests do not claim actuator support."""
import numpy as np
import pytest

from task_env.controllers.canonical.kinematics import PandaKinematics


def _source():
    # Only link1 has an offset COM. All later mass centers sit at the shared
    # pivot, giving an independently calculable single-pendulum result.
    links = ''
    for i in range(7, 0, -1):
        axis = '0 1 0' if i == 1 else '0 0 1'
        com = '1 0 0' if i == 1 else '0 0 0'
        tail = links if i < 7 else (
            '<body name="hand"><inertial mass="1" pos="0 0 0"/>'
            '<site name="nutassembly_ee_site"/>'
            '<body name="left_finger"><joint name="finger_joint1" class="finger"/>'
            '<inertial mass="1" pos="0 0 0"/></body>'
            '<body name="right_finger"><joint name="finger_joint2" class="finger"/>'
            '<inertial mass="1" pos="0 0 0"/></body></body>')
        links = (f'<body name="link{i}"><joint name="joint{i}" axis="{axis}"/>'
                 f'<inertial mass="1" pos="{com}"/>{tail}</body>')
    return ('<mujoco><compiler angle="radian"/><default><default class="panda">'
            '<joint range="-3.14 3.14"/><default class="finger">'
            '<joint type="slide" axis="0 1 0"/></default></default></default>'
            f'<worldbody><body name="link0">{links}</body></worldbody></mujoco>')


def test_gravity_support_analytical_pendulum_and_world_base_rotation():
    model = PandaKinematics(_source())
    q = np.zeros(7)
    tau = model.gravity_support(q, (0., 0.), (0., 0., -9.81), np.eye(3))
    np.testing.assert_allclose(tau, (-9.81, 0, 0, 0, 0, 0, 0), atol=1e-12)
    q[0] = np.pi / 2
    np.testing.assert_allclose(model.gravity_support(q, (0, 0), (0, 0, -9.81), np.eye(3)), 0, atol=1e-12)
    q[0] = 0
    rx = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], dtype=float)
    np.testing.assert_allclose(model.gravity_support(q, (0, 0), (0, 0, -9.81), rx), 0, atol=1e-12)
    # World/base representations must produce the same local gravitational vector.
    np.testing.assert_allclose(model.gravity_support(q, (0, 0), rx @ np.array([0, 0, -9.81]), rx), tau, atol=1e-12)
    np.testing.assert_array_equal(model.gravity_support(q, (0, 0), (0, 0, 0), rx), np.zeros(7))


def test_gravity_support_refuses_invalid_rotation_or_unbound_payload():
    model = PandaKinematics(_source())
    with pytest.raises(ValueError, match='rotation'):
        model.gravity_support(np.zeros(7), (0, 0), (0, 0, -9.81), np.zeros((3, 3)))
    with pytest.raises(ValueError, match='finite'):
        model.gravity_support([float('nan')]*7, (0, 0), (0, 0, -9.81), np.eye(3))
    xml = _source().replace('<site name="nutassembly_ee_site"/>', '<site name="nutassembly_ee_site"/><body name="payload"/>')
    with pytest.raises(ValueError, match='unsupported'):
        PandaKinematics(xml).gravity_support(np.zeros(7), (0, 0), (0, 0, -9.81), np.eye(3))


def test_gravity_support_exposes_each_finger_self_weight():
    model = PandaKinematics(_source())
    arm, fingers = model.gravity_support(np.zeros(7), (0, 0), (0, -9.81, 0), np.eye(3),
                                         include_fingers=True)
    np.testing.assert_allclose(arm, 0, atol=1e-12)
    np.testing.assert_allclose(fingers, [9.81, 9.81], atol=1e-12)


def test_selected_gravity_switch_defaults_and_unsupported_routes():
    import sys
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv
    base = {'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu',
                          'deployment': 'in_process', 'interpreter': sys.executable}}
    default = resolve_task_env_config(PickCubeReferenceEnv, base)
    explicit_off = resolve_task_env_config(PickCubeReferenceEnv, {**base, 'controller': {'gravity_compensation': False}})
    enabled = resolve_task_env_config(PickCubeReferenceEnv, {**base, 'controller': {'gravity_compensation': True}})
    assert default == explicit_off and not default.gravity_compensation and enabled.gravity_compensation
    assert resolve_task_env_config(PickCubeReferenceEnv, enabled) == enabled
    with pytest.raises(TypeError, match='boolean'):
        resolve_task_env_config(PickCubeReferenceEnv, {**base, 'controller': {'gravity_compensation': 1}})
    with pytest.raises(ValueError, match='MuJoCo CPU'):
        resolve_task_env_config(PickCubeReferenceEnv, {'execution': {'physics_provider': 'geophys'},
                                                       'controller': {'gravity_compensation': True}})
    with pytest.raises(ValueError, match='MuJoCo CPU'):
        resolve_task_env_config(PickCubeReferenceEnv, {'execution': {'physics_provider': 'mujoco',
            'physics_backend': 'cpu', 'deployment': 'isolated_worker', 'interpreter': sys.executable},
            'controller': {'gravity_compensation': True}})


def test_gravity_source_refuses_missing_mass_and_bad_tree():
    invalid = _source().replace('<inertial mass="1" pos="1 0 0"/>', '<inertial pos="1 0 0"/>')
    with pytest.raises(ValueError, match='mass and COM'):
        PandaKinematics(invalid).gravity_support(np.zeros(7), (0, 0), (0, 0, -9.81), np.eye(3))
    invalid = _source().replace('<body name="link2">', '<body name="link3">', 1)
    with pytest.raises(ValueError, match='Panda chain'):
        PandaKinematics(invalid)


def test_gravity_contribution_reports_clamping_and_rejects_extra_effort():
    from types import SimpleNamespace
    from task_env.runtime.sessions.mujoco import _MuJoCoSession
    class Gravity:
        source_sha256 = 'a' * 64
        _gravity_bodies = [('link1',)]
        def gravity_support(self, q, fingers, gravity, rotation, *, include_fingers=False):
            assert include_fingers
            return np.full(7, 100.0), np.zeros(2)
    addresses = {f'panda-v1/joint{i}': (i - 1, i - 1) for i in range(1, 8)}
    addresses.update({f'panda-v1/finger_joint{i}': (6 + i, 6 + i) for i in (1, 2)})
    data = SimpleNamespace(qfrc_applied=np.zeros(9), xfrc_applied=np.zeros((1, 6)),
                           qpos=np.zeros(9), xmat=np.eye(3).reshape(1, 9),
                           actuator_force=np.full(7, 5.0))
    native = SimpleNamespace(opt=SimpleNamespace(gravity=np.array([0., 0., -9.81])),
                             actuator_ctrlrange=np.tile([-0.01, 0.01], (7, 1)),
                             actuator_forcerange=np.tile([-5., 5.], (7, 1)))
    actuators = [(f'panda-v1/joint{i}', i - 1, 1000., 1.) for i in range(1, 8)]
    session = SimpleNamespace(_data=data, _model=native, _gravity_model=Gravity(),
        _gravity_base_body=0, _joint_addresses=addresses, _gravity_actuators=actuators,
        _gravity_interval_receipts=[], _control_step=0, _native_steps=0,
        _source=SimpleNamespace(source_closure_digest='b'*64),
        provider_materialization_id='materialization', _episode_id='episode', _reset_sample_id='reset')
    target = SimpleNamespace(arm_servo_position={name: 0. for name, *_ in actuators}, identity_hash='c'*64)
    adjusted = _MuJoCoSession._gravity_adjusted_targets(session, target)
    assert all(value == 0.01 for value in adjusted.values())
    assert all(row['position_target_clamped'] for row in session._gravity_interval_receipts[0]['joints'])
    _MuJoCoSession._record_gravity_force_sample(session)
    assert all(row['force_limit_reached'] for row in session._gravity_interval_receipts[0]['actual_actuator_force_samples'][0]['values'])
    data.qfrc_applied[0] = 1.
    with pytest.raises(ValueError, match='unaccounted applied force'):
        _MuJoCoSession._gravity_adjusted_targets(session, target)
    assert len(session._gravity_interval_receipts) == 1
    data.qfrc_applied[0] = 0.
    class Unbalanced(Gravity):
        def gravity_support(self, q, fingers, gravity, rotation, *, include_fingers=False):
            return np.zeros(7), np.array([1., 0.])
    session._gravity_model = Unbalanced()
    with pytest.raises(ValueError, match='net coupled finger gravity'):
        _MuJoCoSession._gravity_adjusted_targets(session, target)
    assert len(session._gravity_interval_receipts) == 1


def test_gravity_support_matches_independent_potential_derivative_for_rotated_bases():
    model = PandaKinematics(_source())
    rng = np.random.default_rng(20261106)
    eps = 1e-6
    for _ in range(50):
        rotation, _ = np.linalg.qr(rng.normal(size=(3, 3)))
        if np.linalg.det(rotation) < 0:
            rotation[:, 0] *= -1
        world_gravity = rng.normal(size=3) * 9.81
        q = np.zeros(7); q[0] = rng.uniform(-2, 2)
        gravity_base = rotation.T @ world_gravity
        def potential(angle):
            center = np.array([np.cos(angle), 0., -np.sin(angle)])
            return -float(np.dot(gravity_base, center))
        expected = (potential(q[0] + eps) - potential(q[0] - eps)) / (2 * eps)
        result = model.gravity_support(q, (0, 0), world_gravity, rotation)
        assert result[0] == pytest.approx(expected, abs=1e-8, rel=1e-8)
        np.testing.assert_allclose(result[1:], 0, atol=1e-12)


def test_gravity_support_ignores_other_world_objects():
    clean = _source()
    extra = clean.replace('</worldbody>', '<body name="external_object"><inertial mass="999" pos="1 2 3"/></body></worldbody>')
    q = np.array([.2, -.1, .3, -.4, .2, .1, -.2])
    a = PandaKinematics(clean).gravity_support(q, (.01, .02), (0, 0, -9.81), np.eye(3))
    b = PandaKinematics(extra).gravity_support(q, (.01, .02), (0, 0, -9.81), np.eye(3))
    np.testing.assert_array_equal(a, b)
