"""Source-independent checks for two-wheel shared-route semantics."""
import numpy as np

from task_env.tasks.two_wheel_physical import sample_reset
from task_env.tasks.two_wheel_balance import TwoWheelBalanceTaskDefinition
from task_env.environment.types import RuntimeSnapshot


def test_reset_sampling_preserves_order_and_seed_sequence():
    rng = np.random.default_rng(37)
    actual = sample_reset(rng)
    expected_rng = np.random.default_rng(37)
    expected = tuple(expected_rng.uniform(low, high) for low, high in (
        (-.08, .08), (-.20, .20), (-.02, .02), (-.02, .02), (-.30, .30), (-.30, .30)))
    assert actual == expected
    assert sample_reset(rng) != actual


def test_reward_preserves_two_distinct_wheel_rates_and_action_cost():
    definition = TwoWheelBalanceTaskDefinition(0, 0, 1, 1, 2, 2)
    state = RuntimeSnapshot(qpos=np.array([0., 0., 0.], np.float32),
                            qvel=np.array([0., 2., -3.], np.float32))
    definition.reset(state=state)
    evaluation = definition.evaluate(state=state, action=np.array([.9, -.4], np.float32), elapsed_steps=1)
    assert np.isclose(evaluation.reward, 1. - .002 * (4. + 9.) - .0005 * (.9**2 + .4**2))
    assert not evaluation.failure
