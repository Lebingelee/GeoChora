"""Gym-boundary driver: publish one raw observation, then step once per reply."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import uuid4
from typing import Any

import numpy as np

from .contracts import (
    ActionReply,
    ObservationPacket,
    ReporterProtocolError,
    ReporterTransport,
    canonical_env_meta_hash,
)


class ReporterSession:
    """Owns ordering only; it never invents, chunks, or safety-fills actions."""

    def __init__(self, env: Any, transport: ReporterTransport) -> None:
        self.env = env
        self.transport = transport
        self._episode_id: str | None = None
        self._transition_id = -1
        self._latest_packet: ObservationPacket | None = None
        self._env_meta = self._public_env_meta()
        self._env_meta_hash = canonical_env_meta_hash(self._env_meta)

    @property
    def latest_packet(self) -> ObservationPacket | None:
        return self._latest_packet

    def reset(self, *, seed: int | None = None, options: dict[str, Any] | None = None):
        observation, info = self.env.reset(seed=seed, options=options)
        self._episode_id = uuid4().hex
        self._transition_id = 0
        self._publish("reset", observation, {"info": info})
        return observation, info

    def step_if_action(self, timeout_s: float | None = None):
        """Consume at most one reply.  ``None`` means no ``env.step`` occurred."""
        if self._latest_packet is None:
            raise RuntimeError("reset() must publish an observation before receiving actions")
        reply = self.transport.receive(timeout_s)
        if reply is None:
            return None
        action = self._validate_reply(reply)
        observation, reward, terminated, truncated, info = self.env.step(action)
        self._transition_id += 1
        self._publish(
            "step",
            observation,
            {
                "info": info,
                "reward": float(reward),
                "terminated": bool(terminated),
                "truncated": bool(truncated),
            },
        )
        return observation, reward, terminated, truncated, info

    def republish_latest(self) -> ObservationPacket:
        """Send the retained reset/step result after an explicit transport reconnect.

        This does not change the transition identity and, critically, does not
        call ``env.step``.  The reconnecting peer must reply to this same
        packet before the simulation can advance.
        """
        if self._latest_packet is None:
            raise RuntimeError("reset() must publish an observation before it can be republished")
        self.transport.publish(self._latest_packet)
        return self._latest_packet

    def close(self) -> None:
        self.transport.close()

    def _public_env_meta(self) -> Mapping[str, Any]:
        metadata = getattr(self.env, "metadata", None)
        if not isinstance(metadata, Mapping):
            raise TypeError("reporter environment must expose mapping metadata")
        return dict(metadata)

    def _publish(self, kind: str, observation: Any, context: Mapping[str, Any]) -> None:
        if self._episode_id is None:
            raise RuntimeError("reporter episode is not initialized")
        packet = ObservationPacket(
            episode_id=self._episode_id,
            transition_id=self._transition_id,
            kind=kind,
            env_meta=self._env_meta,
            env_meta_hash=self._env_meta_hash,
            observation=observation,
            transition_context=dict(context),
        )
        self.transport.publish(packet)
        self._latest_packet = packet

    def _validate_reply(self, reply: ActionReply) -> np.ndarray:
        packet = self._latest_packet
        assert packet is not None
        if reply.schema_id != packet.schema_id or reply.schema_version != packet.schema_version:
            raise ReporterProtocolError("action reply packet schema does not match")
        if reply.episode_id != packet.episode_id or reply.transition_id != packet.transition_id:
            raise ReporterProtocolError("action reply is stale or belongs to another episode")
        if reply.env_meta_hash != packet.env_meta_hash:
            raise ReporterProtocolError("action reply env_meta_hash does not match")
        action_schema = self._env_meta.get("action_schema", {})
        if isinstance(action_schema, Mapping):
            if reply.action_schema_id != action_schema.get("schema_id") or reply.action_schema_version != action_schema.get("schema_version"):
                raise ReporterProtocolError("action reply action schema does not match")
        action_space = getattr(self.env, "action_space", None)
        if action_space is None:
            raise ReporterProtocolError("reporter environment must expose action_space")
        expected_shape = getattr(action_space, "shape", None)
        expected_dtype = getattr(action_space, "dtype", None)
        if expected_shape is None or expected_dtype is None:
            raise ReporterProtocolError("reporter action_space must declare shape and dtype")
        expected_dtype = np.dtype(expected_dtype)
        if isinstance(reply.action, np.ndarray):
            if np.dtype(reply.action.dtype) != expected_dtype:
                raise ReporterProtocolError("action reply dtype does not match env.action_space")
            action = reply.action
        else:
            try:
                action = np.asarray(reply.action, dtype=expected_dtype)
            except (TypeError, ValueError) as exc:
                raise ReporterProtocolError("action reply is not a numeric vector") from exc
        if action.shape != tuple(expected_shape):
            raise ReporterProtocolError("action reply shape does not match env.action_space")
        if not np.isfinite(action).all():
            raise ReporterProtocolError("action reply must contain finite values")
        if not action_space.contains(action):
            raise ReporterProtocolError("action reply is outside env.action_space")
        return action


__all__ = ["ReporterSession"]
