"""Gym-compatible public-API-only transition recording wrapper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gymnasium import Wrapper

from .contracts import RecordState, RecorderConfig
from .flatten import TreeCodec
from .recorder import TransitionRecorder
from .trajectory import FrozenTrajectory, copy_tree
from task_env.environment.types import StageUnavailableError
from task_env.trajectory.canonical.episode import EpisodeEndV1, StructuredControlTransitionV1


class TransitionRecordWrapper(Wrapper):
    def __init__(self, env, config: RecorderConfig | None = None) -> None:
        super().__init__(env)
        self.config = config or RecorderConfig()
        if self.config.schema_version == "v3" and getattr(
            env, "supports_structured_control_recording", False
        ) is not True:
            raise StageUnavailableError(
                "task-env-h5/v3 wrapper requires an environment that explicitly "
                "publishes StructuredControlTransitionV1 for every step"
            )
        self._codec = TreeCodec(env.observation_space, env.action_space, self.config)
        self.observation_space = self._codec.observation_space
        self.action_space = self._codec.action_space
        self.recorder = TransitionRecorder(self.config)
        self._state = RecordState.UNRESET
        self._current_obs: Any = None
        self._current_reset_info: dict[str, Any] = {}
        self._last_stop: EpisodeEndV1 | None = None
        self._closed = False

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
        if self._closed:
            raise RuntimeError("recording wrapper is closed")
        if self._state is RecordState.RECORDING:
            raise RuntimeError("finalize the active recording before reset")
        observation, info = self.env.reset(**kwargs)
        self._last_stop = None
        self._current_obs, self._current_reset_info = copy_tree(observation), copy_tree(info)
        if self._state is RecordState.ARMED:
            self.recorder.begin_episode(self._current_obs, self._current_reset_info, self.env.get_record_metadata())
            self._state = RecordState.RECORDING
        elif self._state is not RecordState.RECORDING:
            self._state = RecordState.READY
        return self._codec.encode_obs(observation), info

    def step(self, action):
        if self._closed:
            raise RuntimeError("recording wrapper is closed")
        base_action = self._codec.decode_action(action)
        observation, reward, terminated, truncated, info = self.env.step(base_action)
        if self._state is RecordState.RECORDING:
            structured_control = None
            episode_end = None
            record_info = dict(info)
            if self.config.schema_version == "v3":
                structured_control = info.get("structured_control_transition")
                if not isinstance(structured_control, StructuredControlTransitionV1):
                    raise StageUnavailableError(
                        "declared v3 environment omitted typed structured control for a step"
                    )
                structured_control.validate()
                record_info.pop("structured_control_transition", None)
                if terminated or truncated:
                    raw_end = info.get("episode_end_v1")
                    episode_end = (
                        raw_end if isinstance(raw_end, EpisodeEndV1)
                        else EpisodeEndV1.from_mapping(raw_end)
                    )
            self.recorder.append_transition(
                info["external_action"],
                info["universal_action"],
                observation,
                reward,
                info["is_success"],
                terminated,
                truncated,
                record_info,
                structured_control=structured_control,
            )
            if terminated or truncated:
                if self.config.schema_version == "v3":
                    assert episode_end is not None
                    self._finish_structured_episode(episode_end)
                else:
                    self.recorder.end_episode("terminated" if terminated else "truncated")
                self._state = RecordState.STOPPED_TERMINAL
                self._last_stop = episode_end
        self._current_obs = copy_tree(observation)
        return self._codec.encode_obs(observation), reward, terminated, truncated, info

    def stop(self, reason: str = "external_stop") -> EpisodeEndV1:
        """Forward the public environment Stop and finalize supported v3 data."""

        if self._closed:
            raise RuntimeError("recording wrapper is closed")
        if self._state in (RecordState.UNRESET, RecordState.ARMED):
            raise RuntimeError("reset must complete before Stop")
        if self._last_stop is not None:
            return self._last_stop
        stop = getattr(self.env, "stop", None)
        if not callable(stop):
            raise StageUnavailableError("wrapped environment does not expose Stop/Outcome")
        if self._state is RecordState.RECORDING and self.config.schema_version != "v3":
            raise StageUnavailableError(
                "Stop during v2 recording is unsupported because v2 cannot persist "
                "BoundaryEvent, EpisodeOutcome, or bootstrap policy"
            )
        result = stop(reason)
        episode_end = result if isinstance(result, EpisodeEndV1) else EpisodeEndV1.from_mapping(result)
        if self._state is RecordState.RECORDING:
            self._finish_structured_episode(episode_end)
        self._last_stop = episode_end
        self._state = RecordState.STOPPED_TERMINAL
        return episode_end

    def _finish_structured_episode(self, episode_end: EpisodeEndV1) -> FrozenTrajectory:
        outcome = episode_end.outcome
        if self.recorder.transition_count != outcome.final_boundary:
            raise RuntimeError(
                "recorded T does not match Stop final boundary; refusing to add a transition"
            )
        if self.recorder.observation_count != self.recorder.transition_count + 1:
            raise RuntimeError("recorded observations do not satisfy T+1")
        return self.recorder.end_episode(
            outcome.end_reason,
            outcome=outcome,
            end_event=episode_end.boundary_event,
        )

    def end_record(self) -> FrozenTrajectory:
        if self._state is not RecordState.RECORDING: raise RuntimeError("no active recording to end")
        if self.config.schema_version == "v3":
            raise StageUnavailableError(
                "task-env-h5/v3 episodes require Stop/Outcome; manual end_record is unsupported"
            )
        result = self.recorder.end_episode("manual")
        self._state = RecordState.STOPPED_MANUAL
        return result

    def save_h5(self, path: Path | str | None = None, name: str | None = None) -> Path:
        return self.recorder.save_h5(path=path, name=name)

    def close(self) -> None:
        if self._closed:
            return
        if self._state is RecordState.RECORDING:
            if self.config.schema_version != "v3":
                raise StageUnavailableError(
                    "finalize the v2 recording before close; v2 cannot persist Stop/Outcome"
                )
            self.stop("environment_close")
        self._closed = True
        self.env.close()


__all__ = ["TransitionRecordWrapper"]
