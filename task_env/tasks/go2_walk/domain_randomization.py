"""Private Go2 domain-randomization profile and reset-boundary sampler helpers.

The public runtime only sees :class:`WorldRandomizationBatch`.  This module
owns the Go2-specific ranges and reference profile names so the common
factory/runtime never branches on a robot or task UID.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite
from typing import Any, Mapping

import numpy as np


_CURRICULUM_PROFILE = "go2_episode_curriculum_randomization"
_CURRICULUM_MODES = {"start", "end", "curriculum"}


@dataclass(frozen=True)
class Go2DomainRandomizationConfig:
    """Validated Go2 reset-boundary randomization settings."""

    profile: str = "disabled"
    friction_enabled: bool = False
    friction_range: tuple[float, float] = (0.1, 1.25)
    friction_lifetime: str = "episode"
    push_enabled: bool = False
    push_interval_s: float = 5.0
    max_push_vel_xy: float = 1.5
    push_lifetime: str = "episode"
    push_on_reset_boundary: bool = False
    base_mass_enabled: bool = False
    added_mass_range: tuple[float, float] = (-1.0, 3.0)
    base_mass_lifetime: str = "episode"
    inertia_policy: str = "reference_mass_only"
    curriculum_start_fraction: float = 0.0
    curriculum_end_fraction: float = 1.0
    friction_mode: str = "curriculum"
    friction_nominal: float = 1.0
    push_mode: str = "end"
    base_mass_mode: str = "curriculum"
    base_mass_nominal: float = 0.0

    def __post_init__(self) -> None:
        profile = str(self.profile).strip()
        if not profile:
            raise ValueError("Go2 world_randomization profile cannot be empty")
        if profile not in {
            "disabled",
            "go2_episode_randomization_v1",
            "go2_reference_creation_v1",
            _CURRICULUM_PROFILE,
        }:
            raise ValueError(
                "unsupported Go2 world_randomization profile: " + profile
            )
        object.__setattr__(self, "profile", profile)
        for name in ("friction_lifetime", "push_lifetime", "base_mass_lifetime"):
            value = str(getattr(self, name)).strip().lower()
            if value not in {"construction", "episode"}:
                raise ValueError(f"{name} must be construction or episode")
            object.__setattr__(self, name, value)
        for name in ("friction_range", "added_mass_range"):
            values = tuple(float(item) for item in getattr(self, name))
            if len(values) != 2 or not all(isfinite(item) for item in values) or values[0] > values[1]:
                raise ValueError(f"{name} must be a finite ascending pair")
            object.__setattr__(self, name, values)
        if not isfinite(float(self.push_interval_s)) or float(self.push_interval_s) <= 0.0:
            raise ValueError("push_interval_s must be finite and positive")
        if not isfinite(float(self.max_push_vel_xy)) or float(self.max_push_vel_xy) < 0.0:
            raise ValueError("max_push_vel_xy must be finite and non-negative")
        start_fraction = float(self.curriculum_start_fraction)
        end_fraction = float(self.curriculum_end_fraction)
        if (
            not isfinite(start_fraction)
            or not isfinite(end_fraction)
            or not 0.0 <= start_fraction <= 1.0
            or not 0.0 <= end_fraction <= 1.0
            or start_fraction > end_fraction
        ):
            raise ValueError(
                "curriculum_start_fraction and curriculum_end_fraction must be finite "
                "fractions with 0 <= start <= end <= 1"
            )
        object.__setattr__(self, "curriculum_start_fraction", start_fraction)
        object.__setattr__(self, "curriculum_end_fraction", end_fraction)
        for name in ("friction_mode", "push_mode", "base_mass_mode"):
            value = str(getattr(self, name)).strip().lower()
            if value not in _CURRICULUM_MODES:
                raise ValueError(f"{name} must be start, end, or curriculum")
            object.__setattr__(self, name, value)
        friction_nominal = float(self.friction_nominal)
        base_mass_nominal = float(self.base_mass_nominal)
        if not isfinite(friction_nominal) or not isfinite(base_mass_nominal):
            raise ValueError("randomization nominal values must be finite")
        object.__setattr__(self, "friction_nominal", friction_nominal)
        object.__setattr__(self, "base_mass_nominal", base_mass_nominal)
        if profile == _CURRICULUM_PROFILE:
            if not self.friction_range[0] <= friction_nominal <= self.friction_range[1]:
                raise ValueError("friction_nominal must be inside friction_range")
            if not self.added_mass_range[0] <= base_mass_nominal <= self.added_mass_range[1]:
                raise ValueError("base_mass_nominal must be inside added_mass_range")
            has_continuous_curriculum = (
                (self.friction_enabled and self.friction_mode == "curriculum")
                or (self.push_enabled and self.push_mode == "curriculum")
                or (self.base_mass_enabled and self.base_mass_mode == "curriculum")
            )
            if has_continuous_curriculum:
                if start_fraction == end_fraction:
                    raise ValueError(
                        "curriculum mode requires curriculum_start_fraction < "
                        "curriculum_end_fraction"
                    )
        policy = str(self.inertia_policy).strip().lower()
        if policy not in {"reference_mass_only", "scale_inertia_with_mass"}:
            raise ValueError("inertia_policy is not supported")
        object.__setattr__(self, "inertia_policy", policy)
        if profile == "go2_reference_creation_v1":
            object.__setattr__(self, "friction_lifetime", "construction")
            object.__setattr__(self, "push_lifetime", "construction")
            object.__setattr__(self, "base_mass_lifetime", "construction")

    @classmethod
    def from_runtime_config(cls, runtime_config: object) -> "Go2DomainRandomizationConfig":
        values = getattr(runtime_config, "world_randomization", {}) or {}
        if not isinstance(values, Mapping):
            raise TypeError("runtime.world_randomization must be a mapping")
        profile = str(values.get("profile", "disabled"))
        if profile == "disabled":
            return cls(profile="disabled")
        friction = values.get("friction", {}) or {}
        push = values.get("push", {}) or {}
        mass = values.get("base_mass", values.get("mass", {})) or {}
        curriculum = values.get("curriculum", {}) or {}
        if not all(isinstance(item, Mapping) for item in (friction, push, mass)):
            raise TypeError("Go2 world_randomization sections must be mappings")
        if profile == _CURRICULUM_PROFILE and not isinstance(curriculum, Mapping):
            raise TypeError("world_randomization.curriculum must be a mapping")
        is_curriculum = profile == _CURRICULUM_PROFILE
        defaults_enabled = profile != "disabled"
        return cls(
            profile=profile,
            friction_enabled=bool(friction.get("enabled", defaults_enabled)),
            friction_range=tuple(friction.get("range", (0.1, 1.25))),
            friction_lifetime=str(friction.get("lifetime", "episode")),
            push_enabled=bool(push.get("enabled", defaults_enabled)),
            push_interval_s=float(push.get("interval_s", 5.0)),
            max_push_vel_xy=float(push.get("max_vel_xy", 1.5)),
            push_lifetime=str(push.get("lifetime", "episode")),
            push_on_reset_boundary=bool(push.get("on_reset_boundary", False)),
            base_mass_enabled=bool(mass.get("enabled", defaults_enabled)),
            added_mass_range=tuple(mass.get("range", (-1.0, 3.0))),
            base_mass_lifetime=str(mass.get("lifetime", "episode")),
            inertia_policy=str(mass.get("inertia_policy", values.get("inertia_policy", "reference_mass_only"))),
            curriculum_start_fraction=(
                float(curriculum.get("start_fraction", 0.0)) if is_curriculum else 0.0
            ),
            curriculum_end_fraction=(
                float(curriculum.get("end_fraction", 1.0)) if is_curriculum else 1.0
            ),
            friction_mode=(str(friction.get("mode", "curriculum")) if is_curriculum else "curriculum"),
            friction_nominal=(float(friction.get("nominal", 1.0)) if is_curriculum else 1.0),
            push_mode=(str(push.get("mode", "end")) if is_curriculum else "end"),
            base_mass_mode=(str(mass.get("mode", "curriculum")) if is_curriculum else "curriculum"),
            base_mass_nominal=(float(mass.get("nominal", 0.0)) if is_curriculum else 0.0),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.friction_enabled or self.push_enabled or self.base_mass_enabled)

    def as_dict(self) -> dict[str, Any]:
        result = {
            "profile": self.profile,
            "friction": {
                "enabled": self.friction_enabled,
                "range": list(self.friction_range),
                "lifetime": self.friction_lifetime,
            },
            "push": {
                "enabled": self.push_enabled,
                "interval_s": self.push_interval_s,
                "max_vel_xy": self.max_push_vel_xy,
                "lifetime": self.push_lifetime,
                "on_reset_boundary": self.push_on_reset_boundary,
            },
            "base_mass": {
                "enabled": self.base_mass_enabled,
                "range": list(self.added_mass_range),
                "lifetime": self.base_mass_lifetime,
                "inertia_policy": self.inertia_policy,
            },
        }
        if self.profile == _CURRICULUM_PROFILE:
            result["curriculum"] = {
                "start_fraction": self.curriculum_start_fraction,
                "end_fraction": self.curriculum_end_fraction,
            }
            result["friction"].update({
                "mode": self.friction_mode,
                "nominal": self.friction_nominal,
            })
            result["push"]["mode"] = self.push_mode
            result["base_mass"].update({
                "mode": self.base_mass_mode,
                "nominal": self.base_mass_nominal,
            })
        return result

    def _progress_fraction(self, progress: float | None) -> float:
        """Return normalized curriculum progress for the new profile only."""

        if self.profile != _CURRICULUM_PROFILE:
            return 1.0
        value = 0.0 if progress is None else float(progress)
        if not isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("curriculum progress must be a finite fraction in [0, 1]")
        return value

    def _component_level(self, mode: str, progress: float) -> float:
        """Map progress to one component's effective randomization level."""

        if self.profile != _CURRICULUM_PROFILE:
            return 1.0
        if mode == "start":
            return float(progress >= self.curriculum_start_fraction)
        if mode == "end":
            return float(progress >= self.curriculum_end_fraction)
        span = self.curriculum_end_fraction - self.curriculum_start_fraction
        if span <= 0.0:
            raise ValueError("curriculum mode requires a non-zero curriculum interval")
        return float(
            np.clip(
                (progress - self.curriculum_start_fraction) / span,
                0.0,
                1.0,
            )
        )

    @staticmethod
    def _effective_range(
        bounds: tuple[float, float], nominal: float, level: float
    ) -> tuple[float, float]:
        """Expand an interval from its explicit nominal value to full range."""

        return (
            nominal + level * (bounds[0] - nominal),
            nominal + level * (bounds[1] - nominal),
        )

    def sample_payload(
        self,
        *,
        rng: np.random.Generator,
        horizon: int,
        policy_dt: float,
        progress: float | None = None,
    ) -> dict[str, Any]:
        """Sample one world payload using only reset-boundary host RNG."""

        curriculum_progress = self._progress_fraction(progress)
        if not self.enabled:
            return {
                "schema_id": "task-env-world-randomization-v1",
                "reference_profile": self.profile,
                "lifetime": "episode",
            }
        payload: dict[str, Any] = {
            "schema_id": "task-env-go2-world-randomization-v1",
            "reference_profile": self.profile,
            "lifetime": "episode",
            "inertia_policy": self.inertia_policy,
            "push_on_reset_boundary": self.push_on_reset_boundary,
        }
        friction_bounds: tuple[float, float] | None = None
        mass_bounds: tuple[float, float] | None = None
        push_level = 0.0
        lifetimes = []
        if self.friction_enabled:
            if self.profile == _CURRICULUM_PROFILE:
                level = self._component_level(self.friction_mode, curriculum_progress)
                friction_bounds = self._effective_range(
                    self.friction_range, self.friction_nominal, level
                )
            else:
                friction_bounds = self.friction_range
            payload["friction_mu"] = float(rng.uniform(*friction_bounds))
            lifetimes.append(self.friction_lifetime)
        if self.base_mass_enabled:
            if self.profile == _CURRICULUM_PROFILE:
                level = self._component_level(self.base_mass_mode, curriculum_progress)
                mass_bounds = self._effective_range(
                    self.added_mass_range, self.base_mass_nominal, level
                )
            else:
                mass_bounds = self.added_mass_range
            payload["base_mass_delta_kg"] = float(rng.uniform(*mass_bounds))
            lifetimes.append(self.base_mass_lifetime)
        if self.push_enabled:
            push_level = self._component_level(self.push_mode, curriculum_progress)
            if push_level > 0.0:
                interval_steps = max(1, int(ceil(self.push_interval_s / float(policy_dt))))
                capacity = int(ceil(max(1, int(horizon)) / interval_steps))
                if self.push_on_reset_boundary:
                    capacity += 1
                event_steps = np.full((capacity,), -1, dtype=np.int32)
                start = 0 if self.push_on_reset_boundary else interval_steps
                event_steps[:capacity] = np.arange(
                    start,
                    start + capacity * interval_steps,
                    interval_steps,
                    dtype=np.int32,
                )
                max_push_vel_xy = self.max_push_vel_xy * push_level
                velocities = rng.uniform(
                    -max_push_vel_xy,
                    max_push_vel_xy,
                    size=(capacity, 2),
                ).astype(np.float32)
                payload["push_event_steps"] = event_steps.tolist()
                payload["push_velocity_xy"] = velocities.tolist()
                lifetimes.append(self.push_lifetime)
        if self.profile == _CURRICULUM_PROFILE:
            payload.update(
                {
                    "curriculum_progress": curriculum_progress,
                    "friction_effective_range": (
                        list(friction_bounds) if friction_bounds is not None else None
                    ),
                    "base_mass_effective_range": (
                        list(mass_bounds) if mass_bounds is not None else None
                    ),
                    "push_enabled": bool(push_level > 0.0),
                }
            )
        if lifetimes:
            if any(value != lifetimes[0] for value in lifetimes[1:]):
                raise ValueError("Go2 randomization sections must use one lifetime per reset payload")
            payload["lifetime"] = lifetimes[0]
        return payload


__all__ = ["Go2DomainRandomizationConfig"]
