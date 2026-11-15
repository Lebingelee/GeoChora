"""Task-agnostic raw homogeneous vector lifecycle."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium.spaces.utils import flatten_space, unflatten

from ..render.base.contracts import (
    RenderMode,
    RenderUnavailableError,
    normalize_render_mode,
)
from .contracts import ParallelTaskSpecProtocol
from ..utils.tree import tree_copy, tree_stack, validate_batched_tree


def _copy_selected_device_tree(value, mask):
    """Retain terminal rows in a fixed batch-shaped owned tree."""
    import torch

    if isinstance(value, Mapping):
        return {key: _copy_selected_device_tree(item, mask) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_copy_selected_device_tree(item, mask) for item in value)
    result = torch.zeros_like(value)
    result[mask] = value[mask]
    return result


def _copy_device_info(value):
    """Retain task evidence before a reset can mutate task-owned buffers."""
    import torch

    if isinstance(value, Mapping):
        return {key: _copy_device_info(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_copy_device_info(item) for item in value)
    if isinstance(value, list):
        return [_copy_device_info(item) for item in value]
    return value.clone() if isinstance(value, torch.Tensor) else value


def _scalar_device_tree(value, *, add_batch_axis):
    """Adapt one device row without copying or owning task lifecycle state."""
    import torch

    if isinstance(value, Mapping):
        return {key: _scalar_device_tree(item, add_batch_axis=add_batch_axis)
                for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_scalar_device_tree(item, add_batch_axis=add_batch_axis) for item in value)
    if isinstance(value, list):
        return [_scalar_device_tree(item, add_batch_axis=add_batch_axis) for item in value]
    if isinstance(value, torch.Tensor):
        if add_batch_axis:
            return value.unsqueeze(0)
        if value.ndim and value.shape[0] == 1:
            return value[0]
    return value


class HomogeneousVectorTaskEnv:
    """Generic batch contract over one task-owned ParallelTaskSpec.

    Task reward, reset sampling, observation construction and topology are
    intentionally delegated to ``task_spec``.  This class only owns lifecycle,
    batch shape validation and terminal-slot guards.
    """

    def __init__(self, task_spec: ParallelTaskSpecProtocol, *, execution_mode='host', scalar_device=False) -> None:
        if execution_mode not in {'host', 'device'}:
            raise ValueError('homogeneous execution mode must be host or device')
        self._execution_mode = execution_mode
        self._closed = False
        self._close_complete = False
        self._task_spec = task_spec
        self.num_envs = int(task_spec.num_envs)
        if self.num_envs < 1:
            raise ValueError("num_envs must be positive")
        if scalar_device and (execution_mode != 'device' or self.num_envs != 1):
            raise ValueError('scalar device execution requires one device world')
        self._scalar_device = bool(scalar_device)
        self.single_action_space = task_spec.single_action_space
        self.single_observation_space = task_spec.single_observation_space
        if execution_mode == 'device' and not self._scalar_device:
            from gymnasium.vector.utils import batch_space
            self.action_space = batch_space(self.single_action_space, self.num_envs)
            self.observation_space = batch_space(self.single_observation_space, self.num_envs)
        else:
            self.action_space = self.single_action_space
            self.observation_space = self.single_observation_space
        self.metadata = tree_copy(task_spec.metadata)
        if self._scalar_device:
            self.metadata['execution'] = 'device_scalar_worker'
        self._parallel_render_provider = getattr(
            task_spec,
            "parallel_render_provider",
            None,
        )
        self.render_mode = (
            task_spec.metadata.get('render_mode', RenderMode.HUMAN.value)
            if self._parallel_render_provider is not None
            else None
        )
        self._terminal = (None if execution_mode == 'device'
                          else np.zeros(self.num_envs, dtype=np.bool_))
        self._has_reset = False

    @property
    def task_uid(self) -> str:
        return str(self._task_spec.uid)

    @property
    def device_field_plan(self):
        """返回 task 声明的不可变公共 device capability plan（如果存在）。"""

        return getattr(self._task_spec, "device_field_plan", None)

    def get_record_metadata(self) -> dict[str, Any]:
        resolved_config = getattr(self._task_spec, "resolved_config", None)
        if resolved_config is None:
            resolved_config = {
                "task_uid": self.task_uid,
                "num_envs": self.num_envs,
                "backend": self.metadata.get("backend", "unknown"),
            }
        return {
            "env_metadata": tree_copy(self.metadata),
            "resolved_config": tree_copy(resolved_config),
            "universal_action_schema": tree_copy(
                self.metadata.get("universal_action_schema", {})
            ),
        }

    @property
    def observation_noise_level(self) -> float:
        return float(getattr(self._task_spec, "observation_noise_level", 1.0))

    def configure_observation_noise_curriculum(
        self, *, total_policy_ticks: int, start_policy_tick: int = 0
    ) -> None:
        configure = getattr(
            self._task_spec, "configure_observation_noise_curriculum", None
        )
        if callable(configure):
            configure(
                total_policy_ticks=total_policy_ticks,
                start_policy_tick=start_policy_tick,
            )

    def configure_domain_randomization_curriculum(
        self, *, total_policy_ticks: int, start_policy_tick: int = 0
    ) -> None:
        configure = getattr(
            self._task_spec, "configure_domain_randomization_curriculum", None
        )
        if callable(configure):
            configure(
                total_policy_ticks=total_policy_ticks,
                start_policy_tick=start_policy_tick,
            )

    def reset(
        self,
        *,
        seed: int | list[int] | tuple[int | None, ...] | None = None,
        options: dict[str, Any] | None = None,
        mask: np.ndarray | None = None,
    ):
        if self._execution_mode == 'device':
            if self._closed:
                raise RuntimeError('vector environment is closed')
            if options:
                raise ValueError('device reset does not support reset options')
            if self._scalar_device and mask is not None:
                raise ValueError('scalar device reset does not accept a batch mask')
            result = self._task_spec.reset_sampled_device(seed=seed, mask=mask)
            self._has_reset = True
            if self._scalar_device:
                return (_scalar_device_tree(result.observation, add_batch_axis=False),
                        _scalar_device_tree(result.infos, add_batch_axis=False))
            return result.observation, result.infos
        if mask is not None:
            mask_value = np.asarray(mask, dtype=np.bool_)
            if mask_value.shape != (self.num_envs,):
                raise ValueError("reset mask must have shape (B,)")
        result = self._task_spec.reset(seed=seed, options=options, mask=mask)
        self._validate_observation(result.observation)
        if len(result.infos) != self.num_envs:
            raise ValueError("task reset must return one info mapping per slot")
        if mask is None:
            self._terminal.fill(False)
        else:
            self._terminal[np.asarray(mask, dtype=np.bool_)] = False
        self._has_reset = True
        return tree_copy(result.observation), tree_copy(result.infos)

    def step(self, actions: Any):
        if self._execution_mode == 'device':
            if self._scalar_device:
                actions = _scalar_device_tree(actions, add_batch_axis=True)
                result = self._step_device_with_autoreset(actions)
                return _scalar_device_tree(result, add_batch_axis=False)
            return self._step_device_with_autoreset(actions)
        if not self._has_reset:
            raise RuntimeError("reset() must be called before vector step()")
        if np.any(self._terminal):
            raise RuntimeError("terminal vector slots must be masked-reset before step()")
        normalized_actions = self._normalize_action(actions)
        self._validate_action(normalized_actions)
        result = self._task_spec.step(normalized_actions)
        self._validate_observation(result.observation)
        reward = np.asarray(result.reward, dtype=np.float32)
        terminated = np.asarray(result.terminated, dtype=np.bool_)
        truncated = np.asarray(result.truncated, dtype=np.bool_)
        if reward.shape != (self.num_envs,):
            raise ValueError("task reward must have shape (B,)")
        if terminated.shape != (self.num_envs,) or truncated.shape != (self.num_envs,):
            raise ValueError("task terminal arrays must have shape (B,)")
        if len(result.infos) != self.num_envs:
            raise ValueError("task step must return one info mapping per slot")
        self._terminal = np.logical_or(terminated, truncated)
        return (
            tree_copy(result.observation),
            reward.copy(),
            terminated.copy(),
            truncated.copy(),
            tree_copy(result.infos),
        )

    def _step_device_with_autoreset(self, actions):
        if self._closed:
            raise RuntimeError('vector environment is closed')
        if not self._has_reset:
            raise RuntimeError('reset() must be called before vector step()')
        transition = self._task_spec.step_device(actions)
        try:
            return self._finish_device_autoreset(transition)
        except BaseException as error:
            self._task_spec.latch_device_fault(error)
            raise

    def _finish_device_autoreset(self, transition):
        import torch

        for name, value, dtype in (('reward', transition.reward, torch.float32),
                                   ('terminated', transition.terminated, torch.bool),
                                   ('truncated', transition.truncated, torch.bool)):
            if (not isinstance(value, torch.Tensor) or value.dtype != dtype
                    or str(value.device) != transition.device or tuple(value.shape) != (self.num_envs,)):
                raise ValueError(f'device {name} must have shape (B,) and the declared dtype/device')
        done = torch.logical_or(transition.terminated, transition.truncated)
        selection = self._task_spec.prepare_device_reset_selection(done)
        old_episode = self._task_spec.device_episode_ids
        old_step = self._task_spec.device_episode_steps
        env_id = torch.arange(self.num_envs, dtype=torch.int64, device=transition.device)
        task_info = {} if transition.infos is None else transition.infos
        if not isinstance(task_info, Mapping):
            raise TypeError('device transition task infos must be a mapping')
        reserved = {'env_id', 'episode_id', 'episode_step', 'boundary', 'final_observation',
                    '_final_observation', 'final_mask', 'final_info', '_final_info',
                    'reset_info', '_reset_info', 'final_episode_id', 'final_episode_step'}
        if reserved.intersection(task_info):
            raise ValueError('task infos conflict with lifecycle metadata')
        valid = done.clone()
        retained_task_info = _copy_device_info(task_info)
        final_info = {'env_id': env_id, 'episode_id': old_episode, 'episode_step': old_step,
                      'boundary': transition.boundary, 'task': retained_task_info}
        infos = dict(retained_task_info)
        infos.update({'env_id': env_id, 'episode_id': old_episode, 'episode_step': old_step,
                      'boundary': transition.boundary,
                      'final_observation': _copy_selected_device_tree(transition.observation, done),
                      '_final_observation': valid, 'final_mask': valid,
                      'final_info': final_info, '_final_info': valid,
                      'reset_info': {}, '_reset_info': valid,
                      'final_episode_id': old_episode.clone(), 'final_episode_step': old_step.clone()})
        observation = transition.observation
        if selection.selected_count:
            reset = self._task_spec.reset_sampled_device(mask=done, selection=selection)
            observation = reset.observation
            infos['episode_id'] = reset.infos['episode_id']
            infos['episode_step'] = self._task_spec.device_episode_steps
            infos['boundary'] = getattr(getattr(reset, 'state', None), 'identity', None)
            infos['reset_info'] = {'env_id': env_id, 'episode_id': infos['episode_id'],
                                   'episode_step': infos['episode_step'],
                                   'boundary': infos['boundary'], 'task': dict(reset.infos)}
        return observation, transition.reward, transition.terminated, transition.truncated, infos

    def _validate_action(self, actions: Any) -> None:
        if isinstance(self.single_action_space, (gym.spaces.Dict, gym.spaces.Tuple)):
            validate_batched_tree(actions, self.single_action_space, self.num_envs)
            return
        value = np.asarray(actions, dtype=self.single_action_space.dtype)
        expected = (self.num_envs, *self.single_action_space.shape)
        if value.shape != expected:
            raise ValueError(f"vector actions must have shape {expected}")
        if not np.isfinite(value).all() or not self.single_action_space.contains(value[0]):
            raise ValueError("vector actions must be finite and within the action space")

    def _normalize_action(self, actions: Any) -> Any:
        """Accept the raw tree and the legacy flat `(B, flatdim)` input."""

        if not isinstance(self.single_action_space, (gym.spaces.Dict, gym.spaces.Tuple)):
            return actions
        if isinstance(actions, Mapping):
            return actions
        value = np.asarray(actions, dtype=np.float32)
        expected = (self.num_envs, int(np.prod(flatten_space(self.single_action_space).shape)))
        if value.shape != expected:
            raise ValueError(f"flat vector actions must have shape {expected}")
        return tree_stack(
            [unflatten(self.single_action_space, value[slot]) for slot in range(self.num_envs)]
        )

    def _validate_observation(self, observation: Any) -> None:
        validate_batched_tree(
            observation,
            self.single_observation_space,
            self.num_envs,
        )

    def resource_summary(self) -> dict[str, Any]:
        return dict(self._task_spec.resource_summary())

    def set_parallel_render_num(self, count: int) -> None:
        provider = self._require_parallel_render_provider()
        provider.set_parallel_render_num(count)

    def set_parallel_render_hard(self, enabled: bool) -> None:
        provider = self._require_parallel_render_provider()
        provider.set_parallel_render_hard(enabled)

    def set_parallel_render_budget_bypass(self, enabled: bool) -> None:
        provider = self._require_parallel_render_provider()
        provider.set_parallel_render_budget_bypass(enabled)

    def set_parallel_render_layout(self, **kwargs: Any) -> None:
        provider = self._require_parallel_render_provider()
        provider.set_parallel_render_layout(**kwargs)

    def render(self, mode: RenderMode | str | None = None):
        provider = self._require_parallel_render_provider()
        requested = self.render_mode if mode is None else mode
        normalized = normalize_render_mode(requested or RenderMode.HUMAN)
        self.render_mode = normalized.value
        snapshot = getattr(self._task_spec, "_last_state", None)
        return provider.render(mode=normalized, snapshot=snapshot)

    def set_render_control_keys(self, *, toggle: str, disable: str) -> None:
        provider = self._require_parallel_render_provider()
        provider.set_render_control_keys(toggle=toggle, disable=disable)

    def poll_render_events(self):
        provider = self._require_parallel_render_provider()
        return provider.poll_render_events()

    def consume_render_events(self):
        provider = self._require_parallel_render_provider()
        return provider.consume_render_events()

    def close_render(self) -> None:
        provider = self._parallel_render_provider
        if provider is not None:
            provider.close_render()

    def _require_parallel_render_provider(self):
        provider = self._parallel_render_provider
        if provider is None:
            raise RenderUnavailableError(
                "parallel TaskEnv has no attached static-template/merged-scene render source"
            )
        return provider

    def read_device_state(self, names: tuple[str, ...]):
        """Optional named device-state forwarding at the vector boundary."""

        reader = getattr(self._task_spec, "read_device_state", None)
        if not callable(reader):
            raise RuntimeError("homogeneous task has no read_device_state capability")
        return reader(names)

    def step_device(self, actions: Any):
        """Optional device transition forwarding; NumPy path is unchanged."""

        if self._execution_mode == 'device':
            raise RuntimeError('use step() for the coordinated device lifecycle')

        stepper = getattr(self._task_spec, "step_device", None)
        if not callable(stepper):
            raise RuntimeError("homogeneous task has no step_device capability")
        return stepper(actions)

    @property
    def has_privileged_observation(self) -> bool:
        return bool(getattr(self._task_spec, "has_privileged_observation", False))

    def privileged_observation_manifest(self):
        provider = getattr(self._task_spec, "privileged_observation_manifest", None)
        return provider() if callable(provider) else None

    def get_privileged_observation(self):
        provider = getattr(self._task_spec, "get_privileged_observation", None)
        if not callable(provider):
            raise RuntimeError("homogeneous task has no privileged observation capability")
        return provider()

    def get_privileged_observation_device(self):
        provider = getattr(self._task_spec, "get_privileged_observation_device", None)
        if not callable(provider):
            raise RuntimeError("homogeneous task has no device privileged observation capability")
        return provider()

    def prepare_device_reset_selection(self, mask: Any):
        preparer = getattr(self._task_spec, "prepare_device_reset_selection", None)
        if not callable(preparer):
            raise RuntimeError("homogeneous task has no device reset selection capability")
        return preparer(mask)

    def reset_device(self, state: Mapping[str, Any], mask: Any, *, selection=None):
        if self._execution_mode == 'device':
            raise RuntimeError('use reset() for the coordinated device lifecycle')
        resetter = getattr(self._task_spec, "reset_device", None)
        if not callable(resetter):
            raise RuntimeError("homogeneous task has no reset_device capability")
        if selection is None:
            return resetter(state, mask)
        return resetter(state, mask, selection=selection)

    def reset_device_from_mask(self, mask: Any, *, selection=None):
        if self._execution_mode == 'device':
            raise RuntimeError('use reset() for the coordinated device lifecycle')
        resetter = getattr(self._task_spec, "reset_device_from_mask", None)
        if not callable(resetter):
            raise RuntimeError("homogeneous task has no device autoreset capability")
        if selection is None:
            return resetter(mask)
        return resetter(mask, selection=selection)

    def close(self) -> None:
        if self._execution_mode == 'device':
            if self._close_complete:
                return
            self._closed = True
            self._task_spec.close()
            self._close_complete = True
            return
        try:
            self.close_render()
        except BaseException as error:
            try:
                self._task_spec.close()
            except BaseException as cleanup_error:
                error.add_note(f"task cleanup also failed: {cleanup_error!r}")
            raise
        self._task_spec.close()


__all__ = ["HomogeneousVectorTaskEnv"]
