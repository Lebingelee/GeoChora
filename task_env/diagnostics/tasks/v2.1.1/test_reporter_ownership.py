"""Reporter transport never advances an environment without a matching reply."""
import gymnasium as gym
import numpy as np
import pytest

from task_env.reporter import ActionReply, ReporterProtocolError, ReporterSession
from task_env.reporter.loopback import LoopbackReporterTransport


def test_reporter_reconnect_and_stale_reply_cannot_step():
    class Env:
        metadata = {'action_schema': {'schema_id': 'action', 'schema_version': 'v1'}}
        action_space = gym.spaces.Box(-1, 1, shape=(1,), dtype=np.float32)
        steps = 0

        def reset(self, **kwargs):
            return np.zeros(1, dtype=np.float32), {}

        def step(self, action):
            self.steps += 1
            return action, 0., False, False, {}

    env = Env()
    transport = LoopbackReporterTransport()
    reporter = ReporterSession(env, transport)
    reporter.reset(seed=4)
    packet = transport.take_observation()
    reporter.republish_latest()
    assert transport.take_observation() is packet
    assert reporter.step_if_action() is None and env.steps == 0
    reply = ActionReply(packet.episode_id, packet.transition_id - 1, packet.env_meta_hash,
                        'action', 'v1', np.zeros(1, dtype=np.float32))
    transport.submit_action(reply)
    with pytest.raises(ReporterProtocolError, match='stale'):
        reporter.step_if_action()
    assert env.steps == 0
    transport.submit_action(ActionReply(packet.episode_id, packet.transition_id, packet.env_meta_hash,
                                        'action', 'v1', np.zeros(1, dtype=np.float32)))
    reporter.step_if_action()
    assert env.steps == 1 and transport.take_observation().transition_id == 1
    reporter.close()
