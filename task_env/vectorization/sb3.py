"""Generic SB3 protocol adapter for a homogeneous TaskEnv vector.

This module deliberately contains no concrete TaskEnv import.  In particular,
it must remain safe to import from the learner process before the Taichi
simulator worker is started.
"""

from __future__ import annotations

from typing import Any, Protocol

import gymnasium as gym
import numpy as np
from stable_baselines3.common.vec_env import VecEnv

from ..utils.tree import tree_copy, tree_index, tree_set_index, validate_batched_tree


class HomogeneousVectorTaskEnvProtocol(Protocol):
    """Minimal five-tuple vector contract consumed by the SB3 bridge."""

    num_envs: int
    single_action_space: gym.spaces.Space
    single_observation_space: gym.spaces.Space

    def reset(self, *, seed=None, options=None, mask=None): ...

    def step(self, actions): ...

    def close(self) -> None: ...


class TaskEnvSB3VecAdapter(VecEnv):
    """Translate Gymnasium five-tuples to the SB3 four-tuple VecEnv API."""

    def __init__(self, env: HomogeneousVectorTaskEnvProtocol) -> None:
        self.env = env
        if not hasattr(self.env, "render_mode"):
            self.env.render_mode = None
        super().__init__(env.num_envs, env.single_observation_space, env.single_action_space)
        # Preserve the framework metadata on the local SB3 boundary just as
        # RemoteBatchVecEnv does.  This includes static-template execution mode,
        # exact-B resource ownership, device and provenance fields.
        self.metadata = dict(getattr(env, "metadata", {}))
        self._pending_actions: Any = None
        self._last_observation: Any = None

    def reset(self) -> Any:
        if self._seeds and any(seed is not None for seed in self._seeds):
            seed: int | list[int] | None = [seed for seed in self._seeds]
        else:
            seed = None
        observation, infos = self.env.reset(seed=seed)
        self.reset_infos = infos
        self._reset_seeds()
        self._reset_options()
        self._last_observation = observation
        return observation

    def step_async(self, actions: Any) -> None:
        if isinstance(self.action_space, (gym.spaces.Dict, gym.spaces.Tuple)):
            validate_batched_tree(actions, self.action_space, self.num_envs)
            self._pending_actions = tree_copy(actions)
        else:
            action_value = np.asarray(actions, dtype=self.action_space.dtype)
            expected_shape = (self.num_envs, *self.action_space.shape)
            if action_value.shape != expected_shape:
                raise ValueError(f"SB3 actions must have shape {expected_shape}")
            self._pending_actions = action_value.copy()

    def step_wait(self):
        if self._pending_actions is None:
            raise RuntimeError("step_async() must be called before step_wait()")
        observation, reward, terminated, truncated, infos = self.env.step(self._pending_actions)
        dones = np.logical_or(terminated, truncated)
        for slot, done in enumerate(dones):
            infos[slot]["TimeLimit.truncated"] = bool(truncated[slot] and not terminated[slot])
            if done:
                infos[slot]["terminal_observation"] = tree_index(observation, slot)
        if np.any(dones):
            reset_observation, reset_infos = self.env.reset(mask=dones)
            for slot, done in enumerate(dones):
                if done:
                    infos[slot]["reset_info"] = reset_infos[slot]
                    tree_set_index(observation, slot, tree_index(reset_observation, slot))
        self._pending_actions = None
        self._last_observation = observation
        return observation, reward, dones, infos

    def close(self) -> None:
        self.env.close()

    @property
    def observation_noise_level(self) -> float:
        return float(getattr(self.env, "observation_noise_level", 1.0))

    def configure_observation_noise_curriculum(
        self, *, total_policy_ticks: int, start_policy_tick: int = 0
    ) -> None:
        configure = getattr(self.env, "configure_observation_noise_curriculum", None)
        if callable(configure):
            configure(
                total_policy_ticks=total_policy_ticks,
                start_policy_tick=start_policy_tick,
            )

    def configure_domain_randomization_curriculum(
        self, *, total_policy_ticks: int, start_policy_tick: int = 0
    ) -> None:
        configure = getattr(self.env, "configure_domain_randomization_curriculum", None)
        if callable(configure):
            configure(
                total_policy_ticks=total_policy_ticks,
                start_policy_tick=start_policy_tick,
            )

    def set_parallel_render_num(self, count: int) -> None:
        self.env.set_parallel_render_num(count)

    def set_parallel_render_hard(self, enabled: bool) -> None:
        self.env.set_parallel_render_hard(enabled)

    def set_parallel_render_budget_bypass(self, enabled: bool) -> None:
        self.env.set_parallel_render_budget_bypass(enabled)

    def set_parallel_render_layout(self, **kwargs: Any) -> None:
        self.env.set_parallel_render_layout(**kwargs)

    def render(self, mode: str | None = None):
        return self.env.render(mode=mode)

    def set_render_control_keys(self, *, toggle: str, disable: str) -> None:
        self.env.set_render_control_keys(toggle=toggle, disable=disable)

    def poll_render_events(self):
        return self.env.poll_render_events()

    def consume_render_events(self):
        return self.env.consume_render_events()

    def close_render(self) -> None:
        self.env.close_render()

    @property
    def device_field_plan(self):
        """保留 local SB3 边界上的 device provenance。"""

        return getattr(self.env, "device_field_plan", None)

    def read_device_state(self, names):
        reader = getattr(self.env, "read_device_state", None)
        if not callable(reader):
            raise RuntimeError("SB3-wrapped environment has no read_device_state capability")
        return reader(names)

    def step_device(self, actions):
        stepper = getattr(self.env, "step_device", None)
        if not callable(stepper):
            raise RuntimeError("SB3-wrapped environment has no step_device capability")
        return stepper(actions)

    @property
    def has_privileged_observation(self) -> bool:
        return bool(getattr(self.env, "has_privileged_observation", False))

    def privileged_observation_manifest(self):
        provider = getattr(self.env, "privileged_observation_manifest", None)
        return provider() if callable(provider) else None

    def get_privileged_observation(self):
        provider = getattr(self.env, "get_privileged_observation", None)
        if not callable(provider):
            raise RuntimeError("SB3-wrapped environment has no privileged observation capability")
        return provider()

    def get_privileged_observation_device(self):
        provider = getattr(self.env, "get_privileged_observation_device", None)
        if not callable(provider):
            raise RuntimeError("SB3-wrapped environment has no device privileged observation capability")
        return provider()

    def prepare_device_reset_selection(self, mask):
        preparer = getattr(self.env, "prepare_device_reset_selection", None)
        if not callable(preparer):
            raise RuntimeError("SB3-wrapped environment has no device reset selection capability")
        return preparer(mask)

    def reset_device(self, state, mask, *, selection=None):
        resetter = getattr(self.env, "reset_device", None)
        if not callable(resetter):
            raise RuntimeError("SB3-wrapped environment has no reset_device capability")
        if selection is None:
            return resetter(state, mask)
        return resetter(state, mask, selection=selection)

    def reset_device_from_mask(self, mask, *, selection=None):
        resetter = getattr(self.env, "reset_device_from_mask", None)
        if not callable(resetter):
            raise RuntimeError("SB3-wrapped environment has no device autoreset capability")
        if selection is None:
            return resetter(mask)
        return resetter(mask, selection=selection)

    def resource_summary(self):
        getter = getattr(self.env, "resource_summary", None)
        if not callable(getter):
            return dict(self.metadata.get("runtime_resource_summary", {}))
        return dict(getter())

    def get_record_metadata(self) -> dict[str, Any]:
        getter = getattr(self.env, "get_record_metadata", None)
        if getter is None:
            raise AttributeError("wrapped homogeneous environment has no record metadata")
        return getter()

    def get_attr(self, attr_name: str, indices=None) -> list[Any]:
        values = [getattr(self.env, attr_name)]
        if indices is None:
            return values * self.num_envs
        selected = self._indices(indices)
        return [values[0] for _ in selected]

    def set_attr(self, attr_name: str, value: Any, indices=None) -> None:
        if indices is not None and len(self._indices(indices)) != self.num_envs:
            raise AttributeError("TaskEnv batch attributes are shared and cannot be partially assigned")
        setattr(self.env, attr_name, value)

    def env_method(self, method_name: str, *method_args, indices=None, **method_kwargs) -> list[Any]:
        method = getattr(self.env, method_name)
        result = method(*method_args, **method_kwargs)
        selected = self._indices(indices) if indices is not None else range(self.num_envs)
        return [result for _ in selected]

    def env_is_wrapped(self, wrapper_class: type[gym.Wrapper], indices=None) -> list[bool]:
        del wrapper_class
        selected = self._indices(indices) if indices is not None else range(self.num_envs)
        return [False for _ in selected]

    def get_images(self):
        if getattr(self.env, "render_mode", None) is None:
            return [None for _ in range(self.num_envs)]
        render = getattr(self.env, "render", None)
        if not callable(render):
            return [None for _ in range(self.num_envs)]
        return [render(mode="rgb_array")]

    @staticmethod
    def _indices(indices):
        if indices is None:
            raise ValueError("indices=None must be handled by the caller")
        if isinstance(indices, (int, np.integer)):
            return [int(indices)]
        return [int(index) for index in indices]


LocalBatchVecEnv = TaskEnvSB3VecAdapter


__all__ = [
    "HomogeneousVectorTaskEnvProtocol",
    "LocalBatchVecEnv",
    "TaskEnvSB3VecAdapter",
]
