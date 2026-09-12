"""Schema-validated RSL-RL checkpoint inspection and tensor conversion.

The bridge is intentionally limited to the non-recurrent actor/critic MLP
shape used by the Go2 policy. It prevents unsafe/ambiguous loads and only
copies tensor weights after the caller supplies a matching architecture
manifest.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import numpy as np


class CheckpointCompatibilityError(ValueError):
    pass


@dataclass(frozen=True)
class PolicyArchitecture:
    """The small, framework-neutral policy shape needed for a safe bridge.

    RSL-RL 1.x stores one ``ActorCritic`` module while 5.x stores separate
    actor/critic ``MLPModel`` modules.  Names can therefore be translated,
    but only when this manifest proves that the actual linear layers and
    action-noise parameterization are the same.  A converter never guesses
    hidden widths from a checkpoint.
    """

    observation_dim: int
    action_dim: int
    actor_hidden_dims: tuple[int, ...]
    critic_hidden_dims: tuple[int, ...]
    activation: str = "elu"
    std_parameterization: str = "scalar"
    normalization: str = "none"
    action_scale: float = 1.0

    def __post_init__(self) -> None:
        if int(self.observation_dim) <= 0 or int(self.action_dim) <= 0:
            raise ValueError("policy dimensions must be positive")
        if any(int(width) <= 0 for width in (*self.actor_hidden_dims, *self.critic_hidden_dims)):
            raise ValueError("policy hidden dimensions must be positive")
        if self.std_parameterization not in {"scalar", "log"}:
            raise ValueError("std_parameterization must be 'scalar' or 'log'")
        if self.normalization not in {"none", "declared_external"}:
            raise ValueError("normalization must be none or declared_external")
        if not np.isfinite(float(self.action_scale)) or float(self.action_scale) <= 0.0:
            raise ValueError("action_scale must be finite and positive")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PolicyArchitecture":
        required = {
            "observation_dim",
            "action_dim",
            "actor_hidden_dims",
            "critic_hidden_dims",
        }
        missing = sorted(required.difference(value))
        if missing:
            raise CheckpointCompatibilityError(
                f"architecture manifest is missing required fields: {missing}"
            )
        return cls(
            observation_dim=int(value["observation_dim"]),
            action_dim=int(value["action_dim"]),
            actor_hidden_dims=tuple(int(item) for item in value["actor_hidden_dims"]),
            critic_hidden_dims=tuple(int(item) for item in value["critic_hidden_dims"]),
            activation=str(value.get("activation", "elu")),
            std_parameterization=str(value.get("std_parameterization", "scalar")),
            normalization=str(value.get("normalization", "none")),
            action_scale=float(value.get("action_scale", 1.0)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "observation_dim": int(self.observation_dim),
            "action_dim": int(self.action_dim),
            "actor_hidden_dims": list(self.actor_hidden_dims),
            "critic_hidden_dims": list(self.critic_hidden_dims),
            "activation": self.activation,
            "std_parameterization": self.std_parameterization,
            "normalization": self.normalization,
            "action_scale": float(self.action_scale),
        }


def load_tensor_checkpoint(path: str | Path, *, map_location: str = "cpu") -> Mapping[str, Any]:
    try:
        import torch
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError("checkpoint inspection requires PyTorch") from exc
    try:
        payload = torch.load(Path(path), map_location=map_location, weights_only=True)
    except TypeError as exc:  # old torch has no safe weights_only mode
        raise CheckpointCompatibilityError(
            "this PyTorch version cannot safely load tensor-only checkpoints"
        ) from exc
    if not isinstance(payload, Mapping):
        raise CheckpointCompatibilityError("checkpoint root must be a mapping")
    return payload


def model_state_dict(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    state = payload.get("model_state_dict")
    if not isinstance(state, Mapping):
        raise CheckpointCompatibilityError(
            "checkpoint must contain a tensor-only model_state_dict mapping"
        )
    for name, value in state.items():
        if not isinstance(name, str) or not hasattr(value, "shape"):
            raise CheckpointCompatibilityError(
                "model_state_dict contains a non-tensor or non-string entry"
            )
    return state


def state_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("model_state_dict"), Mapping):
        state = model_state_dict(payload)
    elif isinstance(payload.get("actor_state_dict"), Mapping) and isinstance(
        payload.get("critic_state_dict"), Mapping
    ):
        actor = _state_mapping(payload["actor_state_dict"], label="current actor_state_dict")
        critic = _state_mapping(payload["critic_state_dict"], label="current critic_state_dict")
        state = {
            **{"actor." + name: value for name, value in actor.items()},
            **{"critic." + name: value for name, value in critic.items()},
        }
    else:
        raise CheckpointCompatibilityError(
            "checkpoint must contain either model_state_dict or actor_state_dict/critic_state_dict"
        )
    return {
        "keys": sorted(str(name) for name in state),
        "shapes": {str(name): list(value.shape) for name, value in state.items()},
        "checkpoint_schema": payload.get("checkpoint_schema", "legacy_unspecified"),
        "observation_schema": payload.get("observation_schema"),
        "action_schema": payload.get("action_schema"),
        "architecture": payload.get("architecture"),
        "source_api": payload.get("source_api"),
        "target_api": payload.get("target_api"),
    }


def require_contract_match(
    source: Mapping[str, Any],
    target: Mapping[str, Any],
    *,
    fields: tuple[str, ...] = (
        "observation_schema",
        "action_schema",
    ),
) -> None:
    for field in fields:
        if source.get(field) != target.get(field):
            raise CheckpointCompatibilityError(
                f"checkpoint {field} mismatch: {source.get(field)!r} != {target.get(field)!r}"
            )


def _state_mapping(value: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    result = dict(value)
    for name, tensor in result.items():
        if not isinstance(name, str) or not hasattr(tensor, "shape"):
            raise CheckpointCompatibilityError(f"{label} contains a non-tensor entry: {name!r}")
    return result


def _linear_shapes(state: Mapping[str, Any], prefix: str) -> list[tuple[int, int]]:
    layers: list[tuple[int, tuple[int, ...], tuple[int, ...]]] = []
    for name, value in state.items():
        match = re.match(rf"^{re.escape(prefix)}\.(\d+)\.weight$", name)
        if match is None:
            continue
        weight_shape = tuple(int(item) for item in value.shape)
        bias = state.get(f"{prefix}.{match.group(1)}.bias")
        if bias is None or tuple(int(item) for item in bias.shape) != (weight_shape[0],):
            raise CheckpointCompatibilityError(
                f"{prefix} layer {match.group(1)} must contain matching weight and bias tensors"
            )
        layers.append((int(match.group(1)), weight_shape, tuple(int(item) for item in bias.shape)))
    if not layers:
        raise CheckpointCompatibilityError(f"checkpoint has no linear layers under {prefix!r}")
    layers.sort(key=lambda item: item[0])
    return [(shape[0], shape[1]) for _, shape, _ in layers]


def _expected_layers(architecture: PolicyArchitecture, *, role: str) -> list[tuple[int, int]]:
    hidden = architecture.actor_hidden_dims if role == "actor" else architecture.critic_hidden_dims
    output = architecture.action_dim if role == "actor" else 1
    dims = [architecture.observation_dim, *hidden, output]
    return list(zip(dims[1:], dims[:-1]))


def _copy_with_prefix(
    state: Mapping[str, Any], *, source_prefix: str, target_prefix: str
) -> dict[str, Any]:
    converted: dict[str, Any] = {}
    for name, value in state.items():
        if name.startswith(source_prefix + "."):
            converted[target_prefix + name[len(source_prefix) :]] = value
        else:
            converted[name] = value
    return converted


def _require_architecture(
    source: Mapping[str, Any], target: PolicyArchitecture | Mapping[str, Any]
) -> PolicyArchitecture:
    architecture = target if isinstance(target, PolicyArchitecture) else PolicyArchitecture.from_mapping(target)
    embedded = source.get("architecture")
    if embedded is not None:
        source_architecture = PolicyArchitecture.from_mapping(embedded)
        if source_architecture != architecture:
            raise CheckpointCompatibilityError(
                "checkpoint architecture manifest differs from the requested target architecture"
            )
    return architecture


def convert_legacy_to_current(
    payload: Mapping[str, Any],
    architecture: PolicyArchitecture | Mapping[str, Any],
    *,
    target_observation_schema: Any = None,
    target_action_schema: Any = None,
) -> dict[str, Any]:
    """Convert an RSL-RL 1.x ActorCritic checkpoint to the 5.x split form.

    The operation is tensor-only and intentionally rejects recurrent policies,
    observation normalizers, unknown state entries, or shape mismatches.
    """

    state = _state_mapping(model_state_dict(payload), label="legacy model_state_dict")
    architecture = _require_architecture(payload, architecture)
    actor = {name: value for name, value in state.items() if name.startswith("actor.")}
    critic = {name: value for name, value in state.items() if name.startswith("critic.")}
    if not actor or not critic:
        raise CheckpointCompatibilityError("legacy checkpoint must contain actor.* and critic.* keys")
    unsupported = sorted(set(state) - set(actor) - set(critic) - {"std", "log_std"})
    if unsupported:
        raise CheckpointCompatibilityError(f"legacy checkpoint contains unsupported state entries: {unsupported}")
    if architecture.std_parameterization == "scalar":
        std = state.get("std")
        if std is None or tuple(int(item) for item in std.shape) != (architecture.action_dim,):
            raise CheckpointCompatibilityError("legacy scalar std must have shape (action_dim,)")
        actor["actor.distribution.std_param"] = std
    else:
        log_std = state.get("log_std")
        if log_std is None or tuple(int(item) for item in log_std.shape) != (architecture.action_dim,):
            raise CheckpointCompatibilityError("legacy log_std must have shape (action_dim,)")
        actor["actor.distribution.log_std_param"] = log_std
    actor_layers = {
        "mlp." + name[len("actor.") :]: value
        for name, value in actor.items()
        if name.startswith("actor.") and not name.startswith("actor.distribution.")
    }
    if architecture.std_parameterization == "scalar":
        actor_layers["distribution.std_param"] = actor["actor.distribution.std_param"]
    else:
        actor_layers["distribution.log_std_param"] = actor["actor.distribution.log_std_param"]
    critic = _copy_with_prefix(critic, source_prefix="critic", target_prefix="mlp")
    actor = actor_layers
    if _linear_shapes(actor, "mlp") != _expected_layers(architecture, role="actor"):
        raise CheckpointCompatibilityError("legacy actor linear layer shapes do not match architecture")
    if _linear_shapes(critic, "mlp") != _expected_layers(architecture, role="critic"):
        raise CheckpointCompatibilityError("legacy critic linear layer shapes do not match architecture")
    return {
        "checkpoint_schema": "task_env_rsl_rl_bridge_v1",
        "source_api": "legacy_1",
        "target_api": "current_5",
        "architecture": architecture.as_dict(),
        "observation_schema": target_observation_schema if target_observation_schema is not None else payload.get("observation_schema"),
        "action_schema": target_action_schema if target_action_schema is not None else payload.get("action_schema"),
        "actor_state_dict": actor,
        "critic_state_dict": critic,
        "iter": 0,
        "infos": {},
    }


def convert_current_to_legacy(
    payload: Mapping[str, Any],
    architecture: PolicyArchitecture | Mapping[str, Any],
    *,
    target_observation_schema: Any = None,
    target_action_schema: Any = None,
) -> dict[str, Any]:
    """Convert a current RSL-RL split checkpoint to the legacy form."""

    actor = _state_mapping(payload.get("actor_state_dict", {}), label="current actor_state_dict")
    critic = _state_mapping(payload.get("critic_state_dict", {}), label="current critic_state_dict")
    if not actor or not critic:
        raise CheckpointCompatibilityError("current checkpoint must contain actor_state_dict and critic_state_dict")
    architecture = _require_architecture(payload, architecture)
    if _linear_shapes(actor, "mlp") != _expected_layers(architecture, role="actor"):
        raise CheckpointCompatibilityError("current actor linear layer shapes do not match architecture")
    if _linear_shapes(critic, "mlp") != _expected_layers(architecture, role="critic"):
        raise CheckpointCompatibilityError("current critic linear layer shapes do not match architecture")
    unsupported_actor = sorted(name for name in actor if not name.startswith("mlp.") and name not in {"distribution.std_param", "distribution.log_std_param"})
    if unsupported_actor:
        raise CheckpointCompatibilityError(f"current actor contains unsupported state entries: {unsupported_actor}")
    unsupported_critic = sorted(name for name in critic if not name.startswith("mlp."))
    if unsupported_critic:
        raise CheckpointCompatibilityError(f"current critic contains unsupported state entries: {unsupported_critic}")
    if architecture.std_parameterization == "scalar":
        std = actor.get("distribution.std_param")
        if std is None or tuple(int(item) for item in std.shape) != (architecture.action_dim,):
            raise CheckpointCompatibilityError("current checkpoint is missing distribution.std_param")
        noise = {"std": std}
    else:
        log_std = actor.get("distribution.log_std_param")
        if log_std is None or tuple(int(item) for item in log_std.shape) != (architecture.action_dim,):
            raise CheckpointCompatibilityError("current checkpoint is missing distribution.log_std_param")
        noise = {"log_std": log_std}
    legacy_actor = {"actor." + name[len("mlp.") :]: value for name, value in actor.items() if name.startswith("mlp.")}
    legacy_critic = {"critic." + name[len("mlp.") :]: value for name, value in critic.items() if name.startswith("mlp.")}
    legacy_actor.update(noise)
    legacy_actor.update(legacy_critic)
    return {
        "checkpoint_schema": "task_env_rsl_rl_bridge_v1",
        "source_api": "current_5",
        "target_api": "legacy_1",
        "architecture": architecture.as_dict(),
        "observation_schema": target_observation_schema if target_observation_schema is not None else payload.get("observation_schema"),
        "action_schema": target_action_schema if target_action_schema is not None else payload.get("action_schema"),
        "model_state_dict": legacy_actor,
        "iter": 0,
        "infos": {},
    }


__all__ = [
    "CheckpointCompatibilityError",
    "PolicyArchitecture",
    "convert_current_to_legacy",
    "convert_legacy_to_current",
    "load_tensor_checkpoint",
    "model_state_dict",
    "require_contract_match",
    "state_manifest",
]
