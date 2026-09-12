"""Environment-free recorder core; wrapper owns all env interaction."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .contracts import RecorderConfig
from .trajectory import FrozenTrajectory, copy_tree, tree_nbytes


def _recording_copy(value: Any, *, in_rgb_branch: bool = False) -> Any:
    """复制观测，并将 RGB 叶子压缩为适合数据集存储的 ``uint8``。"""

    if isinstance(value, Mapping):
        return {
            str(key): _recording_copy(item, in_rgb_branch=in_rgb_branch or str(key) == "rgb")
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [_recording_copy(item, in_rgb_branch=in_rgb_branch) for item in value]
    if isinstance(value, np.ndarray):
        if in_rgb_branch:
            return _quantize_rgb(value)
        return np.asarray(value).copy()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _quantize_rgb(value: np.ndarray) -> np.ndarray:
    """将 RGB 图像量化为数据集统一使用的 ``CHW uint8`` 副本。"""

    image = np.asarray(value)
    if image.ndim != 3 or (image.shape[0] != 3 and image.shape[-1] != 3):
        raise ValueError("recorded RGB leaf must be a CHW or HWC image with three channels")
    if not np.issubdtype(image.dtype, np.number):
        raise ValueError("recorded RGB leaf must use a numeric dtype")
    if image.dtype == np.uint8:
        result = image.copy()
        return result if result.shape[0] == 3 else np.transpose(result, (2, 0, 1)).copy()
    values = np.asarray(image, dtype=np.float32)
    if not np.isfinite(values).all():
        raise ValueError("recorded RGB leaf must contain finite values")
    if np.all((values >= 0.0) & (values <= 1.0)):
        values = values * 255.0
    elif not np.all((values >= 0.0) & (values <= 255.0)):
        raise ValueError("recorded RGB leaf values must be in [0, 1] or [0, 255]")
    result = np.rint(values).astype(np.uint8)
    return result if result.shape[0] == 3 else np.transpose(result, (2, 0, 1)).copy()


class TransitionRecorder:
    def __init__(self, config: RecorderConfig | None = None) -> None:
        self.config = config or RecorderConfig()
        self._active = False
        self._frozen: FrozenTrajectory | None = None
        self._bytes = 0
        self._observations: list[Any] = []
        self._actions: list[np.ndarray] = []
        self._universal_actions: list[np.ndarray] = []
        self._rewards: list[float] = []
        self._successes: list[bool] = []
        self._terminated: list[bool] = []
        self._truncated: list[bool] = []
        self._infos: list[dict[str, Any]] = []
        self._reset_info: dict[str, Any] = {}
        self._record_metadata: dict[str, Any] = {}
        self._save_index = 0

    @property
    def active(self) -> bool:
        return self._active

    @property
    def frozen(self) -> FrozenTrajectory | None:
        return self._frozen

    def begin_episode(self, initial_obs: Any, reset_info: dict[str, Any], record_metadata: dict[str, Any]) -> None:
        if self._active:
            raise RuntimeError("recording is already active")
        self._active = True
        self._frozen = None
        self._bytes = 0
        self._observations = []
        self._actions = []
        self._universal_actions = []
        self._rewards, self._successes, self._terminated, self._truncated, self._infos = [], [], [], [], []
        self._reset_info, self._record_metadata = copy_tree(reset_info), copy_tree(record_metadata)
        self._append_observation(initial_obs)

    def _append_observation(self, observation: Any) -> None:
        copied = _recording_copy(observation)
        self._reserve(tree_nbytes(copied))
        self._observations.append(copied)

    def _reserve(self, count: int) -> None:
        if self._bytes + count > self.config.max_buffer_bytes:
            raise MemoryError("recording buffer exceeds max_buffer_bytes")
        self._bytes += count

    def append_transition(
        self,
        action: Any,
        universal_action: Any,
        next_obs: Any,
        reward: float,
        success: bool,
        terminated: bool,
        truncated: bool,
        info: dict[str, Any],
    ) -> None:
        if not self._active:
            raise RuntimeError("begin_episode() must be called before append_transition()")
        if len(self._actions) >= self.config.max_transitions:
            raise OverflowError("recording exceeds max_transitions")
        action_value = np.asarray(action, dtype=np.float32).copy()
        universal_value = np.asarray(universal_action, dtype=np.float32).copy()
        if universal_value.ndim != 1 or not np.isfinite(universal_value).all():
            raise ValueError("universal_action must be a finite 1D vector")
        schema = self._record_metadata.get("universal_action_schema", {})
        if not schema:
            env_metadata = self._record_metadata.get("env_metadata", {})
            schema = env_metadata.get("universal_action_schema", {})
        if isinstance(schema, dict) and schema.get("dimension") is not None:
            expected_dimension = int(schema["dimension"])
            if universal_value.shape != (expected_dimension,):
                raise ValueError(
                    "universal_action shape does not match its schema: "
                    f"got {universal_value.shape}, expected {(expected_dimension,)}"
                )
        self._reserve(
            action_value.nbytes
            + universal_value.nbytes
        )
        self._actions.append(action_value)
        self._universal_actions.append(universal_value)
        self._rewards.append(float(reward))
        self._successes.append(bool(success))
        self._terminated.append(bool(terminated))
        self._truncated.append(bool(truncated))
        self._infos.append(copy_tree(info))
        self._append_observation(next_obs)

    def end_episode(self, reason: str) -> FrozenTrajectory:
        if not self._active:
            raise RuntimeError("no active recording to end")
        self._active = False
        trajectory = FrozenTrajectory(
            tuple(self._observations),
            tuple(self._actions),
            tuple(self._universal_actions),
            tuple(self._rewards),
            tuple(self._successes),
            tuple(self._terminated),
            tuple(self._truncated),
            tuple(self._infos),
            self._reset_info,
            self._record_metadata,
            str(reason),
        )
        trajectory.validate()
        self._frozen = trajectory
        return trajectory

    def save_h5(self, path: Path | str | None = None, name: str | None = None) -> Path:
        if self._frozen is None:
            raise RuntimeError("save_h5() requires a frozen trajectory")
        from .h5 import save_trajectory_h5
        output = save_trajectory_h5(self._frozen, self.config, path=path, name=name, index=self._save_index)
        self._save_index += 1
        return output


__all__ = ["TransitionRecorder"]
