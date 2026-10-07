"""Requested Flow horizons preserve length through the temporal U-Net."""
import torch

from task_env.alg.agent_factory.modules.actors.diffusion_module.conditional_unet1d import (
    ConditionalUnet1D,
)


def _small_unet():
    return ConditionalUnet1D(
        input_dim=8,
        global_cond_dim=12,
        diffusion_step_embed_dim=16,
        down_dims=[16, 32, 64],
        kernel_size=3,
        n_groups=8,
    )


def test_h50_flow_velocity_shape_and_gradients_are_finite():
    model = _small_unet()
    actions = torch.randn(2, 50, 8, requires_grad=True)
    condition = torch.randn(2, 12)
    times = torch.tensor([1, 7], dtype=torch.long)
    output = model(actions, times, condition)
    assert output.shape == (2, 50, 8)
    output.square().mean().backward()
    assert torch.isfinite(output).all()
    assert actions.grad is not None and torch.isfinite(actions.grad).all()


def test_h16_divisible_historical_horizon_keeps_requested_shape():
    model = _small_unet()
    output = model(torch.randn(2, 16, 8), torch.tensor([1, 7]), torch.randn(2, 12))
    assert output.shape == (2, 16, 8)
