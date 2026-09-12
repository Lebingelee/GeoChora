"""Generic RSL-RL learner-action profiles.

Action semantics belong at the learner boundary, not in a task-specific
runner.  A profile declares the policy-side clip, the task/native clip and an
optional affine transform.  The default profile is an identity transform
which falls back to the wrapped environment's public action space, so adding
the Go2 reference profile does not alter other tasks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Mapping
from typing import Any

import numpy as np


_PROFILE_ROOT = Path(__file__).with_name("profiles")


def _optional_scalar(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    result = float(value)
    if not np.isfinite(result):
        raise ValueError(f"{field_name} must be finite when specified")
    return result


@dataclass(frozen=True)
class RslActionTransformSpec:
    """Serializable action transform applied once per policy tick."""

    profile_id: str = "default"
    policy_low: float | None = None
    policy_high: float | None = None
    native_low: float | None = None
    native_high: float | None = None
    scale: float = 1.0
    bias: float = 0.0

    def __post_init__(self) -> None:
        profile_id = str(self.profile_id).strip()
        if not profile_id:
            raise ValueError("RSL action profile_id cannot be empty")
        object.__setattr__(self, "profile_id", profile_id)
        for name in ("policy_low", "policy_high", "native_low", "native_high"):
            object.__setattr__(self, name, _optional_scalar(getattr(self, name), name))
        scale = float(self.scale)
        bias = float(self.bias)
        if not np.isfinite(scale) or scale == 0.0:
            raise ValueError("RSL action transform scale must be finite and non-zero")
        if not np.isfinite(bias):
            raise ValueError("RSL action transform bias must be finite")
        object.__setattr__(self, "scale", scale)
        object.__setattr__(self, "bias", bias)
        for low_name, high_name in (
            ("policy_low", "policy_high"),
            ("native_low", "native_high"),
        ):
            low = getattr(self, low_name)
            high = getattr(self, high_name)
            if (low is None) != (high is None):
                raise ValueError(f"{low_name} and {high_name} must be specified together")
            if low is not None and low >= high:
                raise ValueError(f"{low_name} must be smaller than {high_name}")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RslActionTransformSpec":
        allowed = {
            "profile_id",
            "policy_low",
            "policy_high",
            "native_low",
            "native_high",
            "scale",
            "bias",
        }
        unknown = sorted(set(value).difference(allowed))
        if unknown:
            raise ValueError(f"unknown RSL action profile fields: {unknown}")
        return cls(**{str(key): item for key, item in value.items()})

    def apply_numpy(
        self,
        action: Any,
        *,
        fallback_low: Any = None,
        fallback_high: Any = None,
    ) -> np.ndarray:
        """Clip/transform a flat or batched action at the NumPy boundary."""

        value = np.asarray(action)
        if not np.isfinite(value).all():
            raise ValueError("RSL policy action must be finite")
        policy_low = self.policy_low if self.policy_low is not None else fallback_low
        policy_high = self.policy_high if self.policy_high is not None else fallback_high
        if policy_low is not None and policy_high is not None:
            value = np.clip(value, policy_low, policy_high)
        value = value * self.scale + self.bias
        native_low = self.native_low if self.native_low is not None else fallback_low
        native_high = self.native_high if self.native_high is not None else fallback_high
        if native_low is not None and native_high is not None:
            value = np.clip(value, native_low, native_high)
        return value

    def apply_torch(
        self,
        action: Any,
        *,
        fallback_low: Any = None,
        fallback_high: Any = None,
    ) -> Any:
        """Clip/transform a Torch action without a host round-trip."""

        torch = _torch()
        value = action
        # Do not materialize a GPU scalar here: the downstream learner/task
        # contract performs finite validation at an explicit boundary, while
        # the device hot path must remain free of host synchronizations.

        def _clamp(current: Any, low: Any, high: Any) -> Any:
            if low is None or high is None:
                return current
            return torch.clamp(current, min=low, max=high)

        policy_low = self.policy_low if self.policy_low is not None else fallback_low
        policy_high = self.policy_high if self.policy_high is not None else fallback_high
        value = _clamp(value, policy_low, policy_high)
        if self.scale != 1.0 or self.bias != 0.0:
            value = value * self.scale + self.bias
        native_low = self.native_low if self.native_low is not None else fallback_low
        native_high = self.native_high if self.native_high is not None else fallback_high
        # The Go2 reference declares the same policy/native bounds and an
        # identity affine transform.  In that common device hot path the first
        # clamp already establishes the native contract; launching an identical
        # second clamp only adds scheduler work to every rollout tick.
        if (
            self.scale == 1.0
            and self.bias == 0.0
            and self.policy_low is not None
            and self.native_low == self.policy_low
            and self.native_high == self.policy_high
        ):
            return value
        return _clamp(value, native_low, native_high)

    def manifest(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "policy_clip": None
            if self.policy_low is None
            else {"low": self.policy_low, "high": self.policy_high},
            "native_clip": None
            if self.native_low is None
            else {"low": self.native_low, "high": self.native_high},
            "scale": self.scale,
            "bias": self.bias,
            "semantics": "clip_policy_then_affine_then_clip_native",
        }


@dataclass(frozen=True)
class RslObservationProfile:
    """Profile-owned actor/critic observation-group declaration.

    The profile describes learner groups, while the environment supplies the
    actual tensors.  This keeps deployable actor fields and simulator-only
    critic fields explicit without adding task-id conditionals to the runner.
    """

    actor_groups: tuple[str, ...] = ("policy",)
    critic_groups: tuple[str, ...] = ("policy",)
    groups: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any] | "RslObservationProfile" | None,
    ) -> "RslObservationProfile":
        if isinstance(value, cls):
            return value
        if value is None:
            return cls()
        allowed = {"actor_groups", "critic_groups", "groups"}
        unknown = sorted(set(value).difference(allowed))
        if unknown:
            raise ValueError(f"unknown RSL observation profile fields: {unknown}")

        def _groups(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
            raw = value.get(name, default)
            if not isinstance(raw, (list, tuple)) or not raw:
                raise ValueError(f"RSL observation profile {name} must be a non-empty list")
            result = tuple(str(item).strip() for item in raw)
            if any(not item for item in result) or len(result) != len(set(result)):
                raise ValueError(f"RSL observation profile {name} must contain unique names")
            return result

        raw_groups = value.get("groups", {})
        if not isinstance(raw_groups, Mapping):
            raise ValueError("RSL observation profile groups must be a mapping")
        groups: dict[str, Mapping[str, Any]] = {}
        allowed_group_fields = {
            "fields",
            "source",
            "privileged",
            "dimension",
            "deployable",
        }
        for group_name, group_value in raw_groups.items():
            name = str(group_name).strip()
            if not name or not isinstance(group_value, Mapping):
                raise ValueError("RSL observation group names and values must be valid mappings")
            unknown_group = sorted(set(group_value).difference(allowed_group_fields))
            if unknown_group:
                raise ValueError(
                    f"unknown RSL observation group fields for {name!r}: {unknown_group}"
                )
            fields_value = group_value.get("fields", [])
            if not isinstance(fields_value, (list, tuple)):
                raise ValueError(f"RSL observation group {name!r} fields must be a list")
            fields: list[dict[str, Any]] = []
            cursor = 0
            for field_value in fields_value:
                if not isinstance(field_value, Mapping) or not str(field_value.get("name", "")).strip():
                    raise ValueError(
                        f"RSL observation group {name!r} fields require a non-empty name"
                    )
                allowed_field_fields = {
                    "name",
                    "source",
                    "offset",
                    "shape",
                    "scale",
                    "deployable",
                    "description",
                }
                unknown_field = sorted(set(field_value).difference(allowed_field_fields))
                if unknown_field:
                    raise ValueError(
                        f"unknown RSL observation field fields for {name!r}: {unknown_field}"
                    )
                shape = field_value.get("shape")
                if not isinstance(shape, (list, tuple)) or not shape:
                    raise ValueError(
                        f"RSL observation group {name!r} fields require a non-empty shape"
                    )
                shape_values = tuple(int(item) for item in shape)
                if any(item <= 0 for item in shape_values):
                    raise ValueError(
                        f"RSL observation group {name!r} field shapes must be positive"
                    )
                offset = int(field_value.get("offset", cursor))
                if offset != cursor:
                    raise ValueError(
                        f"RSL observation group {name!r} fields must be contiguous: "
                        f"expected offset {cursor}, got {offset}"
                    )
                normalized = {str(key): item for key, item in field_value.items()}
                normalized["shape"] = list(shape_values)
                normalized["offset"] = offset
                fields.append(normalized)
                width = int(np.prod(shape_values, dtype=np.int64))
                cursor += width
            dimension = group_value.get("dimension")
            if dimension is not None:
                dimension = int(dimension)
                if dimension <= 0 or (fields and cursor != dimension):
                    raise ValueError(
                        f"RSL observation group {name!r} dimension does not match fields"
                    )
            groups[name] = {
                "fields": tuple(fields),
                "source": group_value.get("source"),
                "privileged": bool(group_value.get("privileged", False)),
                "dimension": dimension,
                "deployable": bool(group_value.get("deployable", False)),
            }
        actor_groups = _groups("actor_groups", ("policy",))
        critic_groups = _groups("critic_groups", ("policy",))
        for group_name in (*actor_groups, *critic_groups):
            if group_name != "policy" and group_name not in groups:
                raise ValueError(
                    f"RSL observation group {group_name!r} is referenced but not declared"
                )
        return cls(
            actor_groups=actor_groups,
            critic_groups=critic_groups,
            groups=groups,
        )

    @property
    def privileged_groups(self) -> tuple[str, ...]:
        return tuple(
            group
            for group in self.critic_groups
            if bool(self.groups.get(group, {}).get("privileged", False))
        )

    def manifest(self) -> dict[str, Any]:
        return {
            "actor_groups": list(self.actor_groups),
            "critic_groups": list(self.critic_groups),
            "groups": {
                str(name): {
                    "fields": [dict(item) for item in spec.get("fields", ())],
                    "source": spec.get("source"),
                    "privileged": bool(spec.get("privileged", False)),
                    "dimension": spec.get("dimension"),
                    "deployable": bool(spec.get("deployable", False)),
                }
                for name, spec in self.groups.items()
            },
        }


@dataclass(frozen=True)
class RslLearnerProfile:
    """Combined action and observation declaration loaded from one YAML file."""

    action: RslActionTransformSpec
    observation: RslObservationProfile

    @property
    def profile_id(self) -> str:
        return self.action.profile_id

    def manifest(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "action": self.action.manifest(),
            "observation": self.observation.manifest(),
        }


def _torch():
    try:
        import torch
    except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("RSL action transforms require PyTorch") from exc
    return torch


def _load_yaml(path: Path) -> Mapping[str, Any]:
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - task_env base install
        raise RuntimeError("RSL action profiles require PyYAML") from exc
    with path.open("r", encoding="utf-8") as stream:
        value = yaml.safe_load(stream) or {}
    if not isinstance(value, Mapping):
        raise ValueError(f"RSL action profile must contain a mapping: {path}")
    return value


def _profile_mapping(
    profile: str | Path | Mapping[str, Any] | RslActionTransformSpec | RslLearnerProfile | None,
) -> Mapping[str, Any]:
    """Resolve a built-in YAML profile, explicit path, or mapping."""

    if profile is None:
        profile = "default"
    if isinstance(profile, RslLearnerProfile):
        return profile.action.manifest()
    if isinstance(profile, RslActionTransformSpec):
        return {
            "profile_id": profile.profile_id,
            "policy_low": profile.policy_low,
            "policy_high": profile.policy_high,
            "native_low": profile.native_low,
            "native_high": profile.native_high,
            "scale": profile.scale,
            "bias": profile.bias,
        }
    if isinstance(profile, Mapping):
        return profile
    requested = Path(str(profile))
    if requested.suffix in {".yaml", ".yml"}:
        path = requested if requested.is_file() else _PROFILE_ROOT / requested.name
    else:
        path = _PROFILE_ROOT / f"{requested.name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"unknown RSL action profile: {profile}")
    values = dict(_load_yaml(path))
    values.setdefault("profile_id", requested.stem if requested.suffix else str(profile))
    return values


def resolve_learner_profile(
    profile: str | Path | Mapping[str, Any] | RslActionTransformSpec | RslLearnerProfile | None,
) -> RslLearnerProfile:
    """Resolve one profile containing action and observation declarations."""

    if isinstance(profile, RslLearnerProfile):
        return profile
    values = dict(_profile_mapping(profile))
    profile_id = str(values.get("profile_id", "default"))
    action_values = values.get("action", values)
    if not isinstance(action_values, Mapping):
        raise ValueError("RSL learner profile action must be a mapping")
    action_payload = {str(key): item for key, item in action_values.items()}
    action_payload.setdefault("profile_id", profile_id)
    observation_values = values.get("observation", {})
    if not isinstance(observation_values, Mapping):
        raise ValueError("RSL learner profile observation must be a mapping")
    return RslLearnerProfile(
        action=RslActionTransformSpec.from_mapping(action_payload),
        observation=RslObservationProfile.from_mapping(observation_values),
    )


def resolve_action_profile(
    profile: str | Path | Mapping[str, Any] | RslActionTransformSpec | RslLearnerProfile | None,
) -> RslActionTransformSpec:
    """Resolve only the action part of a combined learner profile."""

    if isinstance(profile, RslLearnerProfile):
        return profile.action
    return resolve_learner_profile(profile).action


def resolve_task_action_profile(
    task_uid: str,
    *,
    config: Mapping[str, Any] | None = None,
) -> str | Mapping[str, Any] | None:
    """Resolve the learner action profile from task-owned public YAML.

    The training CLI intentionally has no action-profile switch.  A task may
    declare ``action.rsl_action_profile`` in its default YAML and a complete
    public YAML override may replace that declaration before environment
    construction.  Tasks without a declaration retain the generic action
    space-derived profile.
    """

    def _read(mapping: Mapping[str, Any] | None) -> str | Mapping[str, Any] | None:
        if not isinstance(mapping, Mapping):
            return None
        action = mapping.get("action")
        if not isinstance(action, Mapping):
            return None
        value = action.get("rsl_action_profile")
        return value if isinstance(value, (str, Mapping)) else None

    override = _read(config)
    if override is not None:
        return override

    candidate_paths: list[Path] = []
    try:
        from ...registry import ENV_REGISTRY

        environment_type = ENV_REGISTRY.get(str(task_uid))
        default_path_getter = getattr(environment_type, "default_config_path", None)
        if callable(default_path_getter):
            default_path = default_path_getter()
            if default_path is not None:
                candidate_paths.append(Path(default_path))
    except (KeyError, OSError, TypeError, ValueError):
        # Keep the resolver usable by a lightweight third-party registration.
        pass

    task_name = str(task_uid).rsplit("-v", 1)[0].replace("-", "_")
    candidate_paths.append(
        Path(__file__).resolve().parents[2] / "tasks" / task_name / "default.yaml"
    )
    for task_path in candidate_paths:
        if not task_path.is_file():
            continue
        try:
            value = _read(_load_yaml(task_path))
        except (OSError, ValueError):
            continue
        if value is not None:
            return value

    # The resolved task class is the owner of its default learner profile.
    # This fallback keeps a shared package YAML from overwriting the distinct
    # 45D and 46D class defaults, without introducing task-id conditionals in
    # the learner adapter.
    try:
        from ...registry import ENV_REGISTRY

        environment_type = ENV_REGISTRY.get(str(task_uid))
        default_config = environment_type.default_config()
        action_config = getattr(default_config, "action", None)
        value = getattr(action_config, "rsl_action_profile", None)
        if isinstance(value, (str, Mapping)):
            return value
    except (KeyError, OSError, TypeError, ValueError):
        pass
    return None


__all__ = [
    "RslActionTransformSpec",
    "RslObservationProfile",
    "RslLearnerProfile",
    "resolve_action_profile",
    "resolve_learner_profile",
    "resolve_task_action_profile",
]
