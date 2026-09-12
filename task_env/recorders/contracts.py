"""Public, task-agnostic contracts for Stage 9 transition recording."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RecordState(str, Enum):
    UNRESET = "unreset"
    ARMED = "armed"
    READY = "ready"
    RECORDING = "recording"
    STOPPED_TERMINAL = "stopped_terminal"
    STOPPED_MANUAL = "stopped_manual"


@dataclass(frozen=True)
class RecorderConfig:
    """Fixed per-trajectory layout and bounded in-memory recording policy."""

    schema_id: str = "task-env-h5"
    schema_version: str = "v2"
    flatten_observation_paths: tuple[str, ...] = ()
    flatten_action: bool = False
    max_transitions: int = 1000
    max_buffer_bytes: int = 512 * 1024 * 1024
    h5_compression: str = "gzip"
    h5_compression_level: int = 4
    # Stage 11 recorder outputs carry reset/replay context in env_meta and
    # therefore omit the historical episode_meta sidecar.  The default stays
    # False so existing v2 fixtures remain byte/schema compatible.
    meta_only: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.meta_only, bool):
            raise ValueError("meta_only must be bool")
        paths = tuple(str(path).strip(".") for path in self.flatten_observation_paths)
        if any(not path for path in paths) or len(set(paths)) != len(paths):
            raise ValueError("flatten_observation_paths must be unique non-empty paths")
        if self.max_transitions < 1 or self.max_buffer_bytes < 1:
            raise ValueError("recording capacity limits must be positive")
        supported = {
            ("task-env-h5", "v2"),
            # Kept solely for reading/regression fixtures written before 10.5.
            ("geophys-transition-h5", "v1"),
        }
        if (self.schema_id, self.schema_version) not in supported:
            raise ValueError("unsupported TaskEnv H5 schema")
        if self.h5_compression != "gzip" or not 0 <= self.h5_compression_level <= 9:
            raise ValueError("H5 supports gzip compression levels 0 through 9 only")
        if self.schema_version == "v2" and (paths or self.flatten_action):
            raise ValueError("task-env-h5 v2 records raw observations and actions without flattening")
        object.__setattr__(self, "flatten_observation_paths", paths)


__all__ = ["RecorderConfig", "RecordState"]
