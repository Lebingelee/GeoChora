"""Small contract tests for opt-in Flow normalization, independent of simulator/training."""
from types import SimpleNamespace

import torch
from omegaconf import OmegaConf

import task_env.alg.agent_factory
from agent_factory.data.normalization import MeanStdNormalizer, QuantileNormalizer
from agent_factory.agents.mixins.actor.flow_matching import FlowMatchingActorMixin


class _FlowObservationHarness(FlowMatchingActorMixin):
    device = torch.device('cpu')

    def __init__(self, normalization_type):
        self.cfg = SimpleNamespace(actor=OmegaConf.create({
            'obs_norm': {'type': normalization_type, 'params': {}}
        }), env=SimpleNamespace(proprio_dim=2))
        self._init_obs_normalizer()

    def _preprocess_obs(self, obs):
        return {'state': torch.as_tensor(obs['state'], dtype=torch.float32)}


def test_q01_q99_maps_and_clips_per_dimension():
    data = torch.tensor([[-100.0, -2.0], [-1.0, -1.0], [0.0, 0.0],
                         [1.0, 1.0], [100.0, 2.0]])
    normalizer = QuantileNormalizer(2, q_low=0.25, q_high=0.75, clip=True)
    normalizer.fit(data)
    bounds = torch.stack((normalizer.low_val, normalizer.high_val))
    assert torch.equal(bounds, torch.tensor([[-1.0, -1.0], [1.0, 1.0]]))
    scaled = normalizer.normalize(torch.tensor([[-100.0, -2.0], [0.0, 0.0], [100.0, 2.0]]))
    assert torch.equal(scaled, torch.tensor([[-1.0, -1.0], [0.0, 0.0], [1.0, 1.0]]))
    restored = normalizer.denormalize(scaled)
    assert torch.equal(restored, torch.tensor([[-1.0, -1.0], [0.0, 0.0], [1.0, 1.0]]))


def test_legacy_quantile_default_remains_unclipped():
    normalizer = QuantileNormalizer(1, q_low=0.25, q_high=0.75)
    normalizer.fit(torch.tensor([[-1.0], [0.0], [1.0]]))
    assert normalizer.normalize(torch.tensor([[3.0]])).item() > 1.0


def test_flow_observation_zscore_is_used_for_training_and_inference():
    policy = _FlowObservationHarness('mean_std')
    assert isinstance(policy.obs_normalizer, MeanStdNormalizer)
    samples = torch.tensor([[1.0, 10.0], [3.0, 14.0], [5.0, 18.0]])
    policy.fit_obs_normalizer(samples)
    actual = policy._prepare_flow_observation({'state': samples})['state']
    expected = (samples - samples.mean(0)) / (samples.std(0) + 1e-8)
    assert torch.allclose(actual, expected)
    assert torch.allclose(actual.mean(0), torch.zeros(2), atol=1e-6)


def test_flow_default_observation_path_remains_raw():
    policy = _FlowObservationHarness(None)
    samples = torch.tensor([[1.0, 10.0], [3.0, 14.0]])
    assert policy.obs_normalizer is None
    assert torch.equal(policy._prepare_flow_observation({'state': samples})['state'], samples)
