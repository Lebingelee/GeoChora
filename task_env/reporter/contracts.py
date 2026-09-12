"""Public, transport-neutral protocol for remote TaskEnv inference."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

import numpy as np


PACKET_SCHEMA_ID = "task-env-reporter"
PACKET_SCHEMA_VERSION = "v1"


def canonical_env_meta_hash(env_meta: Mapping[str, Any]) -> str:
    """Hash metadata identity without imposing a serialization on observations."""

    encoded = json.dumps(env_meta, sort_keys=True, separators=(",", ":"), default=_json_default)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"cannot serialize reporter metadata value {type(value)!r}")


@dataclass(frozen=True)
class ObservationPacket:
    episode_id: str
    transition_id: int
    kind: str
    env_meta: Mapping[str, Any]
    env_meta_hash: str
    observation: Any
    transition_context: Mapping[str, Any]
    schema_id: str = PACKET_SCHEMA_ID
    schema_version: str = PACKET_SCHEMA_VERSION


@dataclass(frozen=True)
class ActionReply:
    episode_id: str
    transition_id: int
    env_meta_hash: str
    action_schema_id: str | None
    action_schema_version: str | None
    action: Any
    schema_id: str = PACKET_SCHEMA_ID
    schema_version: str = PACKET_SCHEMA_VERSION


class ReporterTransport(Protocol):
    def publish(self, packet: ObservationPacket) -> None: ...

    def receive(self, timeout_s: float | None = None) -> ActionReply | None: ...

    def close(self) -> None: ...


class ReporterProtocolError(ValueError):
    """Reply identity or action validity does not match the latest packet."""


class ReporterDisconnected(ConnectionError):
    """The configured reporter transport cannot exchange its next message."""


__all__ = [
    "ActionReply", "ObservationPacket", "PACKET_SCHEMA_ID", "PACKET_SCHEMA_VERSION",
    "ReporterDisconnected", "ReporterProtocolError", "ReporterTransport", "canonical_env_meta_hash",
]
