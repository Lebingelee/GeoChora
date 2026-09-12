"""Gym-compatible public-API-only transition recording wrapper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gymnasium import Wrapper

from .contracts import RecordState, RecorderConfig
from .flatten import TreeCodec
from .recorder import TransitionRecorder
from .trajectory import FrozenTrajectory, copy_tree


class TransitionRecordWrapper(Wrapper):
    def __init__(self, env, config: RecorderConfig | None = None) -> None:
        super().__init__(env)
        self.config = config or RecorderConfig()
        self._codec = TreeCodec(env.observation_space, env.action_space, self.config)
        self.observation_space = self._codec.observation_space
        self.action_space = self._codec.action_space
        self.recorder = TransitionRecorder(self.config)
        self._state = RecordState.UNRESET
        self._current_obs: Any = None
        self._current_reset_info: dict[str, Any] = {}

    @property
    def record_state(self) -> RecordState: return self._state

    def start_record(self) -> None:
        if self._state is RecordState.RECORDING: raise RuntimeError("recording is already active")
        if self._state in (RecordState.STOPPED_TERMINAL,) : raise RuntimeError("terminal recording requires reset before restart")
        if self._state is RecordState.UNRESET:
            self._state = RecordState.ARMED
            return
        self.recorder.begin_episode(self._current_obs, self._current_reset_info, self.env.get_record_metadata())
        self._state = RecordState.RECORDING

    def reset(self, **kwargs):
        observation, info = self.env.reset(**kwargs)
        self._current_obs, self._current_reset_info = copy_tree(observation), copy_tree(info)
        if self._state is RecordState.ARMED:
            self.recorder.begin_episode(self._current_obs, self._current_reset_info, self.env.get_record_metadata())
            self._state = RecordState.RECORDING
        elif self._state is not RecordState.RECORDING:
            self._state = RecordState.READY
        return self._codec.encode_obs(observation), info

    def step(self, action):
        base_action = self._codec.decode_action(action)
        observation, reward, terminated, truncated, info = self.env.step(base_action)
        if self._state is RecordState.RECORDING:
            self.recorder.append_transition(
                info["external_action"],
                info["universal_action"],
                observation,
                reward,
                info["is_success"],
                terminated,
                truncated,
                info,
            )
            if terminated or truncated:
                self.recorder.end_episode("terminated" if terminated else "truncated")
                self._state = RecordState.STOPPED_TERMINAL
        self._current_obs = copy_tree(observation)
        return self._codec.encode_obs(observation), reward, terminated, truncated, info

    def end_record(self) -> FrozenTrajectory:
        if self._state is not RecordState.RECORDING: raise RuntimeError("no active recording to end")
        result = self.recorder.end_episode("manual")
        self._state = RecordState.STOPPED_MANUAL
        return result

    def save_h5(self, path: Path | str | None = None, name: str | None = None) -> Path:
        return self.recorder.save_h5(path=path, name=name)


__all__ = ["TransitionRecordWrapper"]
