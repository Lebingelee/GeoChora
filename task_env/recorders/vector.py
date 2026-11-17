"""Per-slot recording for raw structured TaskEnv vector environments.

This module deliberately has no Stable-Baselines3 dependency.  The recorder
uses the small ``reset``/``step_async``/``step_wait`` protocol already exposed
by ``make_parallel_env`` and can therefore sit below any learner adapter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass

import gymnasium as gym
import numpy as np
from gymnasium.spaces.utils import flatten

from ..utils.tree import tree_copy, tree_index
from ..environment.types import StageUnavailableError
from .contracts import RecorderConfig
from .recorder import TransitionRecorder


class VectorTransitionRecorder:
    """Record each vector slot with one :class:`TransitionRecorder` per slot.

    The class is a lightweight protocol wrapper, not an SB3 ``VecEnv``.  It
    keeps the raw environment's tree spaces and delegates all non-recording
    vector methods to that environment.  An SB3 wrapper can still be placed
    outside it because the required vector methods are intentionally duck
    typed.
    """

    def __init__(
        self,
        venv,
        *,
        path: Path | str | None = None,
        name_prefix: str = "trajectory",
        config: RecorderConfig | None = None,
        record: bool = True,
        env_ids: tuple[int, ...] | None = None,
        observation_paths: tuple[str, ...] | None = None,
    ) -> None:
        self.raw_observation_space = venv.observation_space
        self.raw_action_space = venv.action_space
        self.venv = venv
        self.num_envs = int(venv.num_envs)
        self.observation_space = venv.observation_space
        self.action_space = venv.action_space
        self.metadata = dict(getattr(venv, "metadata", {}))
        if self.metadata.get('execution') == 'device_scalar_worker':
            raise ValueError('VectorTransitionRecorder requires batched device observations')
        self._device_mode = self.metadata.get('execution') == 'device_worker'
        if not self._device_mode and (env_ids is not None or observation_paths is not None):
            raise ValueError('selective vector recording requires a device batch')
        self._device_slots = tuple(range(self.num_envs)) if env_ids is None else tuple(env_ids)
        if (not self._device_slots or len(set(self._device_slots)) != len(self._device_slots)
                or any(type(slot) is not int or not 0 <= slot < self.num_envs for slot in self._device_slots)):
            raise ValueError('recorded env_ids must be unique valid batch rows')
        self._observation_paths = None if observation_paths is None else tuple(observation_paths)
        if self._observation_paths is not None and (
                not self._observation_paths or len(set(self._observation_paths)) != len(self._observation_paths)
                or any(not isinstance(path, str) or not path or any(not part for part in path.split('.'))
                       for path in self._observation_paths)):
            raise ValueError('observation_paths must be unique nonempty dotted paths')
        self.render_mode = getattr(venv, "render_mode", None)
        self.output_path = None if path is None else Path(path)
        self.name_prefix = str(name_prefix)
        if not self.name_prefix:
            raise ValueError("name_prefix must not be empty")
        self.config = config or RecorderConfig()
        self.record_enabled = bool(record)
        self._current_observation: Any = None
        self._pending_actions: Any = None
        self._recorders: list[TransitionRecorder] = []
        self._episode_numbers = [0 for _ in range(self.num_envs)]
        self._saved_paths: list[Path] = []
        self._metadata = self._get_record_metadata()
        self._device_recorders = {}
        self._device_last_info = None
        self._device_recording_fault = None
        if self._device_mode:
            if self.config.schema_version != 'v2':
                raise ValueError('device vector recording currently requires the existing H5 v2 codec')
            components = self._metadata['env_metadata']['action_schema'].get('components')
            if not components:
                raise ValueError('device vector recording requires declared action components')
            if not self._metadata.get('universal_action_schema'):
                self._metadata['universal_action_schema'] = {
                    'version': 'direct-device-action-v1', 'dimension': len(components),
                    'components': list(components)}

    def __getattr__(self, name: str) -> Any:
        """Delegate optional VecEnv/runtime methods without importing SB3."""

        venv = self.__dict__.get("venv")
        if venv is None:
            raise AttributeError(name)
        return getattr(venv, name)

    def get_attr(self, attr_name: str, indices=None) -> list[Any]:
        return self.venv.get_attr(attr_name, indices=indices)

    def set_attr(self, attr_name: str, value: Any, indices=None) -> None:
        return self.venv.set_attr(attr_name, value, indices=indices)

    def env_method(self, method_name: str, *args, indices=None, **kwargs) -> list[Any]:
        return self.venv.env_method(
            method_name, *args, indices=indices, **kwargs
        )

    def env_is_wrapped(self, wrapper_class: type, indices=None) -> list[bool]:
        return self.venv.env_is_wrapped(wrapper_class, indices=indices)

    @property
    def saved_paths(self) -> tuple[Path, ...]:
        return tuple(self._saved_paths)

    def _get_record_metadata(self) -> dict[str, Any]:
        getter = getattr(self.venv, "get_record_metadata", None)
        if getter is None:
            raise AttributeError(
                "VectorTransitionRecorder requires raw vector record metadata"
            )
        metadata = getter()
        if not isinstance(metadata, dict):
            raise TypeError("raw VecEnv record metadata must be a dictionary")
        return tree_copy(metadata)

    def _refresh_record_metadata(self) -> None:
        """Pick up a new provider/generation before opening the next rows."""

        metadata = self._get_record_metadata()
        if self._device_mode and not metadata.get("universal_action_schema"):
            components = (
                metadata.get("env_metadata", {})
                .get("action_schema", {})
                .get("components")
            )
            if components:
                metadata["universal_action_schema"] = {
                    "version": "direct-device-action-v1",
                    "dimension": len(components),
                    "components": list(components),
                }
        self._metadata = metadata
        self.metadata = dict(getattr(self.venv, "metadata", self.metadata))

    def _new_recorders(self, observation: Any, reset_infos: list[dict[str, Any]]) -> None:
        self._recorders = [TransitionRecorder(self.config) for _ in range(self.num_envs)]
        for slot, recorder in enumerate(self._recorders):
            recorder.begin_episode(
                tree_index(observation, slot),
                tree_copy(reset_infos[slot]),
                self._slot_record_metadata(slot),
            )

    def _slot_record_metadata(self, slot: int) -> dict[str, Any]:
        """Attach immutable batch/layout provenance to each slot trajectory."""

        metadata = tree_copy(self._metadata)
        env_metadata = metadata.setdefault("env_metadata", {})
        summary = env_metadata.get("runtime_resource_summary", {})
        provenance = {
            "slot": int(slot),
            "num_envs": int(self.num_envs),
            "backend": str(env_metadata.get("backend", "unknown")),
            "layout": str(env_metadata.get("batch_physics_layout", "unknown")),
            "capability_profile": summary.get("capability_profile"),
            "capacity_policy": summary.get("capacity_policy"),
        }
        metadata["batch_provenance"] = provenance
        resolved_config = metadata.setdefault("resolved_config", {})
        if isinstance(resolved_config, dict):
            resolved_config["batch_provenance"] = provenance
        return metadata

    def _finish_slot(self, slot: int, reason: str, *, save: bool) -> None:
        recorder = self._recorders[slot]
        if not recorder.active:
            return
        trajectory = recorder.end_episode(reason)
        if not save or trajectory.transition_count == 0:
            return
        episode = self._episode_numbers[slot]
        filename = f"{self.name_prefix}_slot_{slot:03d}_episode_{episode:06d}.h5"
        self._saved_paths.append(recorder.save_h5(path=self.output_path, name=filename))
        self._episode_numbers[slot] += 1

    def _restart_slot(self, slot: int, observation: Any, reset_info: dict[str, Any]) -> None:
        self._recorders[slot] = TransitionRecorder(self.config)
        self._recorders[slot].begin_episode(
            tree_index(observation, slot),
            tree_copy(reset_info),
            self._slot_record_metadata(slot),
        )

    def start_record(self) -> None:
        """Arm recording; a reset starts one episode per vector slot."""

        if self._device_mode:
            self._require_device_recording_ready()
        if self.record_enabled:
            return
        self.record_enabled = True
        if self._device_mode:
            try:
                if self._current_observation is not None:
                    self._begin_device_rows(self._device_slots, self._current_observation, self._device_last_info)
            except BaseException as error:
                self._device_recording_fault = error
                raise
            return
        if self._current_observation is not None:
            self._new_recorders(self._current_observation, self.reset_infos)

    def reset(self, **kwargs):
        if self._device_mode:
            return self._reset_device(**kwargs)
        if kwargs:
            raise TypeError('legacy vector recorder reset takes no keyword arguments')
        if self.record_enabled and self._recorders:
            for slot in range(self.num_envs):
                self._finish_slot(slot, "manual", save=True)
        observation = self.venv.reset()
        self.reset_infos = list(self.venv.reset_infos)
        self._current_observation = tree_copy(observation)
        if self.record_enabled:
            self._new_recorders(observation, self.reset_infos)
        return observation

    def stop(self, reason: str = "external_stop"):
        del reason
        raise StageUnavailableError(
            "vector Stop/Outcome is unsupported; no per-slot synchronized Stop contract is declared"
        )

    def step_async(self, actions: Any) -> None:
        if self._pending_actions is not None:
            raise RuntimeError("step_async() called while a vector step is pending")
        self._pending_actions = tree_copy(actions)
        self.venv.step_async(actions)

    def _flat_action(self, action: Any) -> np.ndarray:
        if isinstance(self.raw_action_space, (gym.spaces.Dict, gym.spaces.Tuple)):
            value = flatten(self.raw_action_space, action)
        else:
            value = np.asarray(action, dtype=np.float32)
        value = np.asarray(value, dtype=np.float32).reshape(-1)
        if not np.isfinite(value).all():
            raise ValueError("recorded action must contain only finite values")
        return value

    def _flat_universal_action(self, value: Any, fallback: np.ndarray) -> np.ndarray:
        if value is None:
            return fallback.copy()
        if isinstance(value, (dict, tuple, list)):
            # Native non-arm actions currently use one ``torque`` leaf.  If a
            # future task exposes a different action tree, its raw action
            # space remains the authoritative flattening schema.
            value = flatten(self.raw_action_space, value)
        array = np.asarray(value, dtype=np.float32).reshape(-1)
        if not np.isfinite(array).all():
            raise ValueError("recorded universal_action must be finite")
        return array

    def step_wait(self):
        if self._pending_actions is None:
            raise RuntimeError("step_async() must be called before step_wait()")
        actions = self._pending_actions
        self._pending_actions = None
        observation, rewards, dones, infos = self.venv.step_wait()
        if self.record_enabled:
            for slot, done in enumerate(np.asarray(dones, dtype=np.bool_)):
                slot_action = self._flat_action(tree_index(actions, slot))
                info = infos[slot]
                external_action = self._flat_universal_action(
                    info.get("external_action"), slot_action
                )
                universal_action = self._flat_universal_action(
                    info.get("universal_action"), external_action
                )
                time_limit = bool(info.get("TimeLimit.truncated", False))
                terminated = bool(done and not time_limit)
                truncated = bool(done and time_limit)
                next_observation = (
                    info.get("terminal_observation")
                    if done
                    else tree_index(observation, slot)
                )
                if next_observation is None:
                    raise RuntimeError(
                        "completed vector slot lacks terminal_observation"
                    )
                self._recorders[slot].append_transition(
                    external_action,
                    universal_action,
                    next_observation,
                    float(rewards[slot]),
                    bool(info.get("is_success", False)),
                    terminated,
                    truncated,
                    info,
                )
                if done:
                    self._finish_slot(
                        slot,
                        "truncated" if truncated else "terminated",
                        save=True,
                    )
                    reset_info = info.get("reset_info", {})
                    self._restart_slot(slot, observation, reset_info)
        self._current_observation = tree_copy(observation)
        return observation, rewards, dones, infos

    def end_record(self) -> None:
        if not self.record_enabled:
            return
        if self._device_mode:
            error = None
            for slot in tuple(self._device_recorders):
                try:
                    self._finish_device_row(slot, 'manual')
                except BaseException as caught:
                    if error is None:
                        error = caught
                    else:
                        error.add_note(f'recording row {slot} cleanup also failed: {caught!r}')
            if error is not None:
                if self._device_recording_fault is None:
                    self._device_recording_fault = error
                elif self._device_recording_fault is not error:
                    self._device_recording_fault.add_note(f'recording cleanup retry failed: {error!r}')
                raise self._device_recording_fault
            self.record_enabled = False
            self._device_recording_fault = None
            return
        for slot in range(self.num_envs):
            self._finish_slot(slot, "manual", save=True)
        self.record_enabled = False

    def close(self) -> None:
        if self._device_mode:
            error = None
            try:
                self.end_record()
            except BaseException as caught:
                error = caught
            try:
                self.venv.close()
            except BaseException as caught:
                if error is None:
                    error = caught
                else:
                    error.add_note(f'vector environment cleanup also failed: {caught!r}')
            if error is not None:
                raise error
            return
        try:
            if self.record_enabled and self._recorders:
                for slot in range(self.num_envs):
                    self._finish_slot(slot, "manual", save=True)
        finally:
            self.venv.close()

    def _device_row(self, value, slot):
        """Copy only an explicitly recorded row from a device tree to host."""
        import torch

        if isinstance(value, Mapping):
            return {key: self._device_row(item, slot) for key, item in value.items()}
        if isinstance(value, torch.Tensor):
            selected = value[slot] if value.ndim and value.shape[0] == self.num_envs else value
            result = selected.detach().clone().cpu().numpy()
            return result.item() if result.ndim == 0 else result
        if is_dataclass(value) and not isinstance(value, type):
            return asdict(value)
        return value

    def _require_device_recording_ready(self):
        if self._device_recording_fault is not None:
            raise RuntimeError('device recording is faulted; finalize or close before continuing') from self._device_recording_fault

    def _device_observation_row(self, observation, slot):
        if self._observation_paths is None:
            return self._device_row(observation, slot)
        selected = {}
        for path in self._observation_paths:
            source, target = observation, selected
            parts = path.split('.')
            for part in parts[:-1]:
                source = source[part]
                target = target.setdefault(part, {})
            target[parts[-1]] = self._device_row(source[parts[-1]], slot)
        return selected

    def _device_boundary(self, info, slot):
        if not isinstance(info, Mapping) or info.get('boundary') is None:
            raise ValueError('device recording requires public boundary identity')
        boundary = self._device_row(info['boundary'], slot)
        if not isinstance(boundary, Mapping):
            raise TypeError('device recording boundary must be a typed identity')
        result = {'schema_version': 'device-batch-boundary-v1', 'env_id': slot,
                  'episode_id': int(self._device_row(info['episode_id'], slot)),
                  'episode_step': int(self._device_row(info['episode_step'], slot)),
                  **boundary}
        if 'native_world_time' in info:
            result['native_world_time_s'] = float(self._device_row(info['native_world_time'], slot))
        return result

    def _begin_device_rows(self, slots, observation, info):
        for slot in slots:
            recorder = TransitionRecorder(self.config)
            boundary = self._device_boundary(info, slot)
            recorder.begin_episode(self._device_observation_row(observation, slot),
                                   {'boundary_context_v1': boundary}, self._slot_record_metadata(slot))
            self._device_recorders[slot] = recorder

    def _finish_device_row(self, slot, reason):
        recorder = self._device_recorders[slot]
        trajectory = recorder.end_episode(reason) if recorder.active else recorder.frozen
        if trajectory is None:
            raise RuntimeError('device recording has no active or frozen episode')
        if trajectory.transition_count:
            episode = self._episode_numbers[slot]
            name = f'{self.name_prefix}_slot_{slot:03d}_episode_{episode:06d}.h5'
            self._saved_paths.append(recorder.save_h5(path=self.output_path, name=name))
            self._episode_numbers[slot] += 1
        del self._device_recorders[slot]

    def _reset_device(self, **kwargs):
        self._require_device_recording_ready()
        mask = kwargs.get('mask')
        observation, info = self.venv.reset(**kwargs)
        # The environment has already committed reset, even if saving a prior
        # episode fails. A later start_record must use this new boundary.
        self._current_observation, self._device_last_info = observation, info
        try:
            self._refresh_record_metadata()
            if self.record_enabled and self._device_recorders:
                selected = (self._device_slots if mask is None else
                            tuple(slot for slot in self._device_slots if bool(mask[slot].item())))
                save_error = None
                for slot in selected:
                    if slot in self._device_recorders:
                        try:
                            self._finish_device_row(slot, 'manual')
                        except BaseException as error:
                            if save_error is None:
                                save_error = error
                            elif save_error is not error:
                                save_error.add_note(f'recording row {slot} cleanup also failed: {error!r}')
                if save_error is not None:
                    raise save_error
            else:
                selected = self._device_slots
            if self.record_enabled:
                self._begin_device_rows(selected, observation, info)
        except BaseException as error:
            self._device_recording_fault = error
            raise
        return observation, info

    def step(self, actions, *, scene_body_wrenches=()):
        if not self._device_mode:
            if scene_body_wrenches:
                raise ValueError('scene body wrenches require the device batch route')
            self.step_async(actions)
            return self.step_wait()
        self._require_device_recording_ready()
        observation, reward, terminated, truncated, info = (
            self.venv.step(actions, scene_body_wrenches=scene_body_wrenches)
            if scene_body_wrenches else self.venv.step(actions))
        self._current_observation, self._device_last_info = observation, info
        if not self.record_enabled:
            return observation, reward, terminated, truncated, info
        try:
            self._record_device_transition(actions, observation, reward, terminated, truncated, info)
        except BaseException as error:
            self._device_recording_fault = error
            raise
        return observation, reward, terminated, truncated, info

    def _record_device_transition(self, actions, observation, reward, terminated, truncated, info):
        """Append the completed public transition without advancing the environment."""
        done = terminated | truncated
        first_error = None
        for slot in self._device_slots:
            try:
                ended = bool(done[slot].item())
                previous = info['final_info'] if ended else info
                boundary = self._device_boundary(previous, slot)
                next_observation = info['final_observation'] if ended else observation
                action = self._device_row(actions, slot)
                flat = np.asarray(flatten(self.venv.single_action_space, action), dtype=np.float32).reshape(-1)
                metrics = self._device_row(info.get('metrics', {}), slot)
                terms = self._device_row(info.get('reward_terms', {}), slot)
                scene = previous.get('task', {}).get('scene_physical_v1', ()) if ended else info.get('scene_physical_v1', ())
                scene_rows = [{key: self._device_row(value, slot) for key, value in entry.items()}
                              for entry in scene]
                if scene_rows:
                    from ..trajectory.metadata import plain_metadata
                    boundary = {**boundary, 'scene_physical_v1': plain_metadata(scene_rows)}
                self._device_recorders[slot].append_transition(flat, flat,
                    self._device_observation_row(next_observation, slot),
                    float(reward[slot].item()), False, bool(terminated[slot].item()),
                    bool(truncated[slot].item()), {'boundary_context_v1': boundary,
                    'task_metrics': metrics, 'reward_terms': terms,
                    'scene_physical_v1': scene_rows})
                if ended:
                    reason = 'terminated' if bool(terminated[slot].item()) else 'truncated'
                    self._finish_device_row(slot, reason)
                    self._begin_device_rows((slot,), observation, info['reset_info'])
            except BaseException as error:
                if first_error is None:
                    first_error = error
                elif first_error is not error:
                    first_error.add_note(f'recording row {slot} also failed: {error!r}')
        if first_error is not None:
            raise first_error


VectorTransitionRecordWrapper = VectorTransitionRecorder


__all__ = ["VectorTransitionRecorder", "VectorTransitionRecordWrapper"]
