"""Per-slot recording for raw structured TaskEnv vector environments.

This module deliberately has no Stable-Baselines3 dependency.  The recorder
uses the small ``reset``/``step_async``/``step_wait`` protocol already exposed
by ``make_parallel_env`` and can therefore sit below any learner adapter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium.spaces.utils import flatten

from ..utils.tree import tree_copy, tree_index
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
    ) -> None:
        self.raw_observation_space = venv.observation_space
        self.raw_action_space = venv.action_space
        self.venv = venv
        self.num_envs = int(venv.num_envs)
        self.observation_space = venv.observation_space
        self.action_space = venv.action_space
        self.metadata = dict(getattr(venv, "metadata", {}))
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

        if self.record_enabled:
            return
        self.record_enabled = True
        if self._current_observation is not None:
            self._new_recorders(self._current_observation, self.reset_infos)

    def reset(self):
        if self.record_enabled and self._recorders:
            for slot in range(self.num_envs):
                self._finish_slot(slot, "manual", save=True)
        observation = self.venv.reset()
        self.reset_infos = list(self.venv.reset_infos)
        self._current_observation = tree_copy(observation)
        if self.record_enabled:
            self._new_recorders(observation, self.reset_infos)
        return observation

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
        for slot in range(self.num_envs):
            self._finish_slot(slot, "manual", save=True)
        self.record_enabled = False

    def close(self) -> None:
        try:
            if self.record_enabled and self._recorders:
                for slot in range(self.num_envs):
                    self._finish_slot(slot, "manual", save=True)
        finally:
            self.venv.close()


VectorTransitionRecordWrapper = VectorTransitionRecorder


__all__ = ["VectorTransitionRecorder", "VectorTransitionRecordWrapper"]
