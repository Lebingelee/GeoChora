"""In-process port implementation used by protocol smoke tests and integrations."""

from __future__ import annotations

from collections import deque

from .contracts import ActionReply, ObservationPacket


class LoopbackReporterTransport:
    """A deliberately non-stepping transport with explicit client-side queues."""

    def __init__(self) -> None:
        self._published: deque[ObservationPacket] = deque()
        self._replies: deque[ActionReply] = deque()
        self._closed = False

    def publish(self, packet: ObservationPacket) -> None:
        if self._closed:
            raise ConnectionError("loopback reporter transport is closed")
        self._published.append(packet)

    def receive(self, timeout_s: float | None = None) -> ActionReply | None:
        del timeout_s
        if self._closed:
            raise ConnectionError("loopback reporter transport is closed")
        return self._replies.popleft() if self._replies else None

    def take_observation(self) -> ObservationPacket | None:
        return self._published.popleft() if self._published else None

    def submit_action(self, reply: ActionReply) -> None:
        if self._closed:
            raise ConnectionError("loopback reporter transport is closed")
        self._replies.append(reply)

    def close(self) -> None:
        self._closed = True
        self._published.clear()
        self._replies.clear()


__all__ = ["LoopbackReporterTransport"]
