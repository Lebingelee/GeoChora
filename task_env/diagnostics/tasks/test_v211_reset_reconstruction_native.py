"""Narrow MuJoCo checks of affected seeded and mixed reset owners."""
import numpy as np


def test_seeded_public_route_rebuilds_then_steps_with_one_session(monkeypatch):
    import mujoco
    from task_env import make_env

    native_step = mujoco.mj_step
    attempts = []
    def bounded(*args, **kwargs):
        if len(attempts) >= 5:
            raise RuntimeError('seeded test physics reservation exhausted')
        attempts.append(True)
        return native_step(*args, **kwargs)
    monkeypatch.setattr(mujoco, 'mj_step', bounded)
    env = make_env('pick-cube-p16-reference-v1', config={
        'robot': {'uid': 'panda-v1'}, 'task': {'controller_profile': 'r1'},
        'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu', 'physics_device': 'cpu'},
        'episode': {'horizon': 8},
    })
    try:
        initial = env.value
        env.reset(seed=31)
        first = env.value
        assert first is not initial
        env.reset(seed=31)
        assert env.value is not first and env.state.control_step == 0
        pose = env.state.pose_world['panda-v1/ee']
        action = np.asarray((pose.position[0] + .02, *pose.position[1:], *pose.quaternion_wxyz, -.5))
        env.step(action)
        assert len(attempts) == 5 and env.state.control_step == 1
        assert env.session._last_scene_control_submission['status'] == 'acknowledged'
    finally:
        env.close()


def test_mixed_owner_reuses_first_value_and_rebuilds_for_second_real_reset(monkeypatch):
    from task_env.diagnostics.tasks import test_r07c_libero_core_env_s1 as fixture
    fixture._FAKE_WORLD = fixture._World()
    env = fixture._synthetic_mixed_candidate(monkeypatch, horizon=4, install_fake_sdk=False)
    try:
        initial = env.value
        env.reset(seed=51)
        assert env.value is initial and env.state.control_step == 0
        env.reset(seed=51)
        assert env.value is not initial and env.state.control_step == 0
    finally:
        env.close()
