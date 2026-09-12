"""Length-prefixed TCP adapter for the reporter port contract.

The wire representation is JSON plus base64 ndarray payloads.  It is intended
as the stable interoperability adapter, not as a high-throughput image stream.
"""

from __future__ import annotations

import base64
import json
import socket
import struct
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from typing import Any

import numpy as np

from .contracts import ActionReply, ObservationPacket, ReporterDisconnected


def _wire_value(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return {"__ndarray__": True, "dtype": str(value.dtype), "shape": list(value.shape), "data": base64.b64encode(np.ascontiguousarray(value).tobytes()).decode("ascii")}
    if isinstance(value, np.generic):
        return value.item()
    if is_dataclass(value):
        # ``asdict()`` 会深拷贝非容器字段；真实 TaskEnv 的 transition
        # context 刻意包含不可 pickle/deep-copy 的只读 ``mappingproxy``。
        # 这里递归投影字段，保持 JSON wire conversion 只读。
        return {
            field.name: _wire_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _wire_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_wire_value(item) for item in value]
    return value


def _from_wire(value: Any) -> Any:
    if isinstance(value, dict) and value.get("__ndarray__"):
        raw = base64.b64decode(value["data"])
        return np.frombuffer(raw, dtype=np.dtype(value["dtype"])).reshape(tuple(value["shape"])).copy()
    if isinstance(value, dict):
        return {key: _from_wire(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_from_wire(item) for item in value]
    return value


def _send(sock: socket.socket, payload: Mapping[str, Any]) -> None:
    body = json.dumps(_wire_value(payload), separators=(",", ":")).encode("utf-8")
    try:
        sock.sendall(struct.pack("!I", len(body)) + body)
    except OSError as exc:
        raise ReporterDisconnected("reporter TCP peer disconnected while sending") from exc


def _recv_exact(sock: socket.socket, count: int) -> bytes | None:
    chunks: list[bytes] = []
    while count:
        try:
            data = sock.recv(count)
        except socket.timeout:
            return None
        except OSError as exc:
            raise ReporterDisconnected("reporter TCP peer disconnected while receiving") from exc
        if not data:
            raise ReporterDisconnected("reporter TCP peer closed connection")
        chunks.append(data)
        count -= len(data)
    return b"".join(chunks)


def _recv(sock: socket.socket, timeout_s: float | None) -> dict[str, Any] | None:
    previous = sock.gettimeout()
    sock.settimeout(timeout_s)
    try:
        header = _recv_exact(sock, 4)
        if header is None:
            return None
        body = _recv_exact(sock, struct.unpack("!I", header)[0])
        return None if body is None else _from_wire(json.loads(body.decode("utf-8")))
    finally:
        sock.settimeout(previous)


class TcpReporterTransport:
    """Server-side transport.  Accept once, then use it as a ReporterTransport."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind((host, port))
        self._listener.listen(1)
        self._connection: socket.socket | None = None

    @property
    def address(self) -> tuple[str, int]:
        return self._listener.getsockname()[:2]

    def accept(self, timeout_s: float | None = None) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        self._listener.settimeout(timeout_s)
        try:
            connection, _ = self._listener.accept()
        except socket.timeout as exc:
            raise TimeoutError("timed out waiting for reporter TCP client") from exc
        finally:
            self._listener.settimeout(None)
        self._connection = connection

    def publish(self, packet: ObservationPacket) -> None:
        if self._connection is None:
            raise ReporterDisconnected("reporter TCP client has not connected")
        _send(self._connection, {"kind": "observation", "packet": _wire_value(packet)})

    def receive(self, timeout_s: float | None = None) -> ActionReply | None:
        if self._connection is None:
            raise ReporterDisconnected("reporter TCP client has not connected")
        message = _recv(self._connection, timeout_s)
        if message is None:
            return None
        if message.get("kind") != "action":
            raise ValueError("reporter TCP expected an action message")
        return ActionReply(**message["reply"])

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        self._listener.close()


class TcpReporterClient:
    """Small reference peer for remote reporter integration and smoke tests."""

    def __init__(self, host: str, port: int, *, timeout_s: float | None = 10.0) -> None:
        self._connection = socket.create_connection((host, port), timeout=timeout_s)

    def receive_observation(self, timeout_s: float | None = None) -> ObservationPacket | None:
        message = _recv(self._connection, timeout_s)
        if message is None:
            return None
        if message.get("kind") != "observation":
            raise ValueError("reporter TCP expected an observation message")
        return ObservationPacket(**message["packet"])

    def send_action(self, reply: ActionReply) -> None:
        _send(self._connection, {"kind": "action", "reply": _wire_value(reply)})

    def close(self) -> None:
        self._connection.close()


__all__ = ["TcpReporterClient", "TcpReporterTransport"]
