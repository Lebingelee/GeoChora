"""Reward-variant metadata for staged Go2 Codex experiments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RewardVariant:
    """A named reward control/variant with auditable experiment metadata."""

    variant_id: str
    stage: str
    algebra: str
    changed_terms: tuple[str, ...]
    host_device_parity: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "variant_id": self.variant_id,
            "stage": self.stage,
            "algebra": self.algebra,
            "changed_terms": list(self.changed_terms),
            "host_device_parity": self.host_device_parity,
        }


C0_REWARD_VARIANT = RewardVariant(
    variant_id="C0",
    stage="control",
    algebra="frozen-go2-walk-deploy-height-v1",
    changed_terms=(),
    host_device_parity="inherited-and-covered-by-deploy-height-contract",
)

# C1/C2 remain declarations for later variants.  Each must be introduced one
# variant at a time and covered by matching host/device tests first.
C1_REWARD_VARIANT = RewardVariant(
    variant_id="C1",
    stage="legacy-control",
    algebra="mujoco-warp-old-probe-13-term-control",
    changed_terms=("legacy_reward_algebra",),
    host_device_parity="required-before-activation",
)
C2_REWARD_VARIANT = RewardVariant(
    variant_id="C2",
    stage="forward-stable",
    algebra="axis-wise-forward-stable-shaping",
    changed_terms=(
        "tracking_lin_vel_x",
        "tracking_lin_vel_y",
        "tracking_ang_vel",
        "lin_vel_z",
        "base_height",
        "projected_gravity_xy",
        "roll_pitch",
    ),
    host_device_parity="required-before-activation",
)

C2A_REWARD_VARIANT = RewardVariant(
    variant_id="C2A",
    stage="forward-stable-axis-tracking",
    algebra="axis-wise-forward-tracking-v1",
    changed_terms=("tracking_lin_vel_x", "tracking_lin_vel_y"),
    host_device_parity="shared-formula-and-covered-by-codex-parity-test",
)
C2B_REWARD_VARIANT = RewardVariant(
    variant_id="C2B",
    stage="forward-stable-axis-and-posture",
    algebra="axis-wise-forward-tracking-plus-stability-v1",
    changed_terms=(
        "tracking_lin_vel_x",
        "tracking_lin_vel_y",
        "lin_vel_z_stability",
        "nominal_height",
        "projected_gravity_xy",
        "roll_pitch",
    ),
    host_device_parity="shared-formula-and-covered-by-codex-parity-test",
)

REWARD_VARIANTS = {
    item.variant_id: item
    for item in (
        C0_REWARD_VARIANT,
        C1_REWARD_VARIANT,
        C2_REWARD_VARIANT,
        C2A_REWARD_VARIANT,
        C2B_REWARD_VARIANT,
    )
}

C2A_TRACKING_LIN_VEL_X_SCALE = 1.5
C2A_TRACKING_LIN_VEL_Y_SCALE = 0.5
C2B_LIN_VEL_Z_SCALE = -2.0
C2B_NOMINAL_HEIGHT_SCALE = -5.0
C2B_PROJECTED_GRAVITY_XY_SCALE = -0.5
C2B_ROLL_SCALE = -0.25
C2B_PITCH_SCALE = -0.125


def c2a_tracking_terms_host(
    *,
    lin,
    commands,
    tracking_multiplier,
    dt,
):
    """Return the C2a axis-wise tracking terms using NumPy arithmetic."""

    import numpy as np

    values = np.asarray(lin, dtype=np.float32)
    command_value = np.asarray(commands, dtype=np.float32)
    multiplier = np.asarray(tracking_multiplier, dtype=np.float32)
    policy_dt = np.float32(dt)
    return {
        "tracking_lin_vel_x": np.exp(
            -np.square(command_value[..., 0] - values[..., 0]) / 0.25
        ) * np.float32(C2A_TRACKING_LIN_VEL_X_SCALE) * multiplier * policy_dt,
        "tracking_lin_vel_y": np.exp(
            -np.square(command_value[..., 1] - values[..., 1]) / 0.25
        ) * np.float32(C2A_TRACKING_LIN_VEL_Y_SCALE) * multiplier * policy_dt,
    }


def c2a_tracking_terms_device(*, lin, commands, tracking_multiplier, dt):
    """Return the C2a axis-wise tracking terms using Torch tensors."""

    import torch

    return {
        "tracking_lin_vel_x": torch.exp(
            -torch.square(commands[..., 0] - lin[..., 0]) / 0.25
        ) * C2A_TRACKING_LIN_VEL_X_SCALE * tracking_multiplier * dt,
        "tracking_lin_vel_y": torch.exp(
            -torch.square(commands[..., 1] - lin[..., 1]) / 0.25
        ) * C2A_TRACKING_LIN_VEL_Y_SCALE * tracking_multiplier * dt,
    }


def c2b_stability_terms_host(
    *,
    lin,
    projected_gravity,
    base_height,
    roll,
    pitch,
    dt,
):
    """Return C2b stability terms using NumPy arithmetic."""

    import numpy as np

    lin_value = np.asarray(lin, dtype=np.float32)
    gravity_value = np.asarray(projected_gravity, dtype=np.float32)
    height_value = np.asarray(base_height, dtype=np.float32)
    roll_value = np.asarray(roll, dtype=np.float32)
    pitch_value = np.asarray(pitch, dtype=np.float32)
    policy_dt = np.float32(dt)
    return {
        "lin_vel_z_stability": (
            np.square(lin_value[..., 2])
            * np.float32(C2B_LIN_VEL_Z_SCALE)
            * policy_dt
        ),
        "nominal_height": (
            np.square(height_value - np.float32(0.34))
            * np.float32(C2B_NOMINAL_HEIGHT_SCALE)
            * policy_dt
        ),
        "projected_gravity_xy": (
            np.sum(np.square(gravity_value[..., :2]), axis=-1)
            * np.float32(C2B_PROJECTED_GRAVITY_XY_SCALE)
            * policy_dt
        ),
        "roll_pitch": (
            (
                np.square(roll_value) * np.float32(C2B_ROLL_SCALE)
                + np.square(pitch_value) * np.float32(C2B_PITCH_SCALE)
            )
            * policy_dt
        ),
    }


def c2b_stability_terms_device(
    *,
    lin,
    projected_gravity,
    base_height,
    roll,
    pitch,
    dt,
):
    """Return C2b stability terms using Torch arithmetic."""

    import torch

    return {
        "lin_vel_z_stability": (
            lin[..., 2].square() * C2B_LIN_VEL_Z_SCALE * dt
        ),
        "nominal_height": (
            (base_height - 0.34).square() * C2B_NOMINAL_HEIGHT_SCALE * dt
        ),
        "projected_gravity_xy": (
            torch.sum(projected_gravity[..., :2].square(), dim=-1)
            * C2B_PROJECTED_GRAVITY_XY_SCALE
            * dt
        ),
        "roll_pitch": (
            (
                roll.square() * C2B_ROLL_SCALE
                + pitch.square() * C2B_PITCH_SCALE
            )
            * dt
        ),
    }


def get_reward_variant(variant_id: str = "C0") -> RewardVariant:
    """Return an explicitly named variant or fail before training starts."""

    try:
        return REWARD_VARIANTS[str(variant_id).upper()]
    except KeyError as exc:
        valid = ", ".join(sorted(REWARD_VARIANTS))
        raise ValueError(
            f"unknown Go2 Codex reward variant {variant_id!r}; expected {valid}"
        ) from exc


__all__ = [
    "C0_REWARD_VARIANT",
    "C1_REWARD_VARIANT",
    "C2_REWARD_VARIANT",
    "C2A_REWARD_VARIANT",
    "C2B_REWARD_VARIANT",
    "C2A_TRACKING_LIN_VEL_X_SCALE",
    "C2A_TRACKING_LIN_VEL_Y_SCALE",
    "C2B_LIN_VEL_Z_SCALE",
    "C2B_NOMINAL_HEIGHT_SCALE",
    "C2B_PROJECTED_GRAVITY_XY_SCALE",
    "C2B_ROLL_SCALE",
    "C2B_PITCH_SCALE",
    "REWARD_VARIANTS",
    "RewardVariant",
    "c2a_tracking_terms_device",
    "c2a_tracking_terms_host",
    "c2b_stability_terms_device",
    "c2b_stability_terms_host",
    "get_reward_variant",
]
