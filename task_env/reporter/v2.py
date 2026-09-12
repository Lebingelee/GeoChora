"""与 agent_infra.socket_env 对齐的独立 remote-gym-env v2 producer。"""

from __future__ import annotations

import base64
import hashlib
import json
import socket
import struct
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from typing import Any
from uuid import uuid4

import numpy as np
from gymnasium import spaces


PROTOCOL_ID = "remote-gym-env"
PROTOCOL_VERSION = 2
MAX_MESSAGE_BYTES = 512 * 1024 * 1024
CAPABILITIES = ("describe", "reset", "step", "get_latest", "ping", "close")


class V2ProtocolError(ValueError):
    """v2 请求或本地环境返回值不满足固定协议。"""


def _encode(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        array = np.ascontiguousarray(value)
        return {
            "__ndarray__": True,
            "dtype": array.dtype.str,
            "shape": list(array.shape),
            "data": base64.b64encode(array.tobytes()).decode("ascii"),
        }
    if isinstance(value, np.generic):
        return value.item()
    if is_dataclass(value):
        # 真实 reset/step info 可包含冻结 schema；递归投影避免 deepcopy。
        return {field.name: _encode(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _encode(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_encode(item) for item in value]
    return value


def _decode(value: Any) -> Any:
    if isinstance(value, Mapping):
        if value.get("__ndarray__") is True:
            try:
                dtype = np.dtype(value["dtype"])
                shape = tuple(int(dim) for dim in value["shape"])
                raw = base64.b64decode(value["data"], validate=True)
            except (KeyError, TypeError, ValueError) as exc:
                raise V2ProtocolError("invalid ndarray payload") from exc
            if any(dim < 0 for dim in shape):
                raise V2ProtocolError("ndarray shape cannot contain negative dimensions")
            expected = int(np.prod(shape, dtype=np.int64)) * dtype.itemsize
            if len(raw) != expected:
                raise V2ProtocolError("ndarray byte length does not match dtype and shape")
            return np.frombuffer(raw, dtype=dtype).copy().reshape(shape)
        return {str(key): _decode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode(item) for item in value]
    return value


def _send(peer: socket.socket, message: Mapping[str, Any]) -> None:
    body = json.dumps(_encode(message), separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(body) > MAX_MESSAGE_BYTES:
        raise V2ProtocolError("message exceeds maximum size")
    peer.sendall(struct.pack("!I", len(body)) + body)


def _recv_exact(peer: socket.socket, count: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < count:
        data = peer.recv(count - len(chunks))
        if not data:
            raise ConnectionError("remote peer closed the connection")
        chunks.extend(data)
    return bytes(chunks)


def _recv(peer: socket.socket) -> dict[str, Any]:
    count = struct.unpack("!I", _recv_exact(peer, 4))[0]
    if count <= 0 or count > MAX_MESSAGE_BYTES:
        raise V2ProtocolError("invalid frame length")
    try:
        message = _decode(json.loads(_recv_exact(peer, count).decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise V2ProtocolError("invalid JSON frame") from exc
    if not isinstance(message, dict):
        raise V2ProtocolError("protocol message must be an object")
    return message


def _encode_space(space: spaces.Space) -> dict[str, Any]:
    if isinstance(space, spaces.Box):
        return {"type": "Box", "shape": list(space.shape), "dtype": np.dtype(space.dtype).str, "low": np.asarray(space.low), "high": np.asarray(space.high)}
    if isinstance(space, spaces.Dict):
        return {"type": "Dict", "keys": list(space.spaces), "spaces": {key: _encode_space(child) for key, child in space.spaces.items()}}
    if isinstance(space, spaces.Discrete):
        return {"type": "Discrete", "n": int(space.n), "start": int(space.start)}
    if isinstance(space, spaces.MultiDiscrete):
        return {"type": "MultiDiscrete", "nvec": np.asarray(space.nvec), "start": np.asarray(space.start)}
    if isinstance(space, spaces.MultiBinary):
        return {"type": "MultiBinary", "n": space.n}
    if isinstance(space, spaces.Tuple):
        return {"type": "Tuple", "spaces": [_encode_space(child) for child in space.spaces]}
    raise TypeError(f"unsupported Gym space {type(space).__name__}")


def _descriptor_hash(value: Mapping[str, Any]) -> str:
    body = json.dumps(_encode(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _strict_metadata(value: Any) -> Any:
    """投影为严格 JSON metadata，保留 portable space 作为 bounds 事实源。"""

    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_s = str(key)
            if key_s in {"low", "high"}:
                bounds = np.asarray(item)
                if np.issubdtype(bounds.dtype, np.number) and not np.isfinite(bounds).all():
                    continue
            result[key_s] = _strict_metadata(item)
        return result
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, (tuple, list)):
        return [_strict_metadata(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        raise V2ProtocolError("env_metadata must not contain non-finite scalar values")
    return value


def _meta_keys_from_observation_space(observation_space: spaces.Space) -> dict[str, dict[str, Any]]:
    """从已声明的 raw 空间构造 adapter 所需的 group/leaf/shape 表。"""

    if not isinstance(observation_space, spaces.Dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for group, group_space in observation_space.spaces.items():
        if not isinstance(group_space, spaces.Dict):
            continue
        leaves: dict[str, Any] = {}
        for leaf, leaf_space in group_space.spaces.items():
            shape = getattr(leaf_space, "shape", None)
            if shape is None:
                raise V2ProtocolError(f"observation leaf {group}.{leaf} has no declared shape")
            leaves[str(leaf)] = list(shape)
        result[str(group)] = leaves
    return result


def _project_model_observation_metadata(metadata: Mapping[str, Any], obs_meta_keys: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """补充 model-side layout 元数据，raw GeoPhys schema 与 observation 均不改写。"""

    projected = dict(metadata)
    schema = metadata.get("observation_schema")
    leaf_specs = schema.get("leaf_specs", ()) if isinstance(schema, Mapping) else ()
    cameras = {
        str(camera.get("name")): camera
        for camera in metadata.get("camera_specs", ())
        if isinstance(camera, Mapping) and isinstance(camera.get("name"), str)
    }
    groups: dict[str, dict[str, dict[str, Any]]] = {
        group: {} for group in obs_meta_keys
    }
    for spec in leaf_specs:
        if not isinstance(spec, Mapping) or not isinstance(spec.get("path"), str):
            continue
        group, separator, leaf = spec["path"].partition(".")
        if not separator or leaf not in obs_meta_keys.get(group, {}):
            continue
        leaf_metadata = {
            "shape": list(spec.get("shape", obs_meta_keys[group][leaf])),
            "dtype": str(spec.get("dtype", "")),
            "semantic": str(spec.get("semantic", "")),
        }
        if group == "rgb" and leaf in cameras:
            # CameraSpec 是 RGB layout/dtype 的唯一事实源；此处仅声明给模型层。
            leaf_metadata["layout"] = str(cameras[leaf].get("rgb_layout", ""))
            leaf_metadata["dtype"] = str(cameras[leaf].get("rgb_dtype", leaf_metadata["dtype"]))
            leaf_metadata["semantic"] = "rgb"
        groups[group][leaf] = leaf_metadata
    for group, leaves in obs_meta_keys.items():
        for leaf, shape in leaves.items():
            groups[group].setdefault(leaf, {"shape": list(shape), "dtype": "", "semantic": ""})
    projected["observation"] = {"groups": groups}
    projected["observation_group_order"] = list(obs_meta_keys)
    projected["observation_order"] = {group: list(leaves) for group, leaves in obs_meta_keys.items()}
    return projected


def _result(request_id: str, session_id: str, value: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {"kind": "result", "protocol_id": PROTOCOL_ID, "protocol_version": PROTOCOL_VERSION, "request_id": request_id, "session_id": session_id, "ok": True, "result": dict(value or {})}


def _error(request_id: str, session_id: str, code: str, message: str) -> dict[str, Any]:
    return {"kind": "result", "protocol_id": PROTOCOL_ID, "protocol_version": PROTOCOL_VERSION, "request_id": request_id, "session_id": session_id, "ok": False, "error": {"code": code, "message": message}}


class TaskEnvV2Reporter:
    """将真实 GeoPhys Gym TaskEnv 暴露为独立的 v2 command endpoint。"""

    def __init__(self, env: Any, host: str = "127.0.0.1", port: int = 0, *, request_cache_size: int = 128) -> None:
        self.env = env
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((host, port))
        self._server.listen(1)
        self._session_id = uuid4().hex
        self._episode_id: str | None = None
        self._transition_id: int | None = None
        self._latest_packet: dict[str, Any] | None = None
        self._cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._cache_size = int(request_cache_size)
        self._closed = False
        metadata = _strict_metadata(dict(getattr(env, "metadata", {})))
        observation_meta_keys = _meta_keys_from_observation_space(env.observation_space)
        metadata = _project_model_observation_metadata(metadata, observation_meta_keys)
        meta_keys = {"obs": observation_meta_keys, "action": {}}
        self._descriptor_body = {
            "protocol_id": PROTOCOL_ID,
            "protocol_version": PROTOCOL_VERSION,
            "session_id": self._session_id,
            "observation_space": _encode_space(env.observation_space),
            "action_space": _encode_space(env.action_space),
            "env_metadata": metadata,
            "meta_keys": meta_keys,
            "capabilities": list(CAPABILITIES),
        }
        self._descriptor_hash = _descriptor_hash(self._descriptor_body)

    @property
    def address(self) -> tuple[str, int]:
        return self._server.getsockname()[:2]

    def _descriptor(self) -> dict[str, Any]:
        return {**self._descriptor_body, "descriptor_hash": self._descriptor_hash}

    def _cache_response(self, request_id: str, response: dict[str, Any]) -> dict[str, Any]:
        self._cache[request_id] = response
        self._cache.move_to_end(request_id)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return response

    def _packet(self, kind: str, observation: Any, info: Mapping[str, Any], **transition: Any) -> dict[str, Any]:
        assert self._episode_id is not None and self._transition_id is not None
        return {"episode_id": self._episode_id, "transition_id": self._transition_id, "kind": kind, "descriptor_hash": self._descriptor_hash, "observation": observation, "info": _strict_metadata(info), **transition}

    def dispatch(self, message: Mapping[str, Any]) -> dict[str, Any]:
        request_id = str(message.get("request_id", ""))
        try:
            if message.get("kind") != "command" or message.get("protocol_id") != PROTOCOL_ID or int(message.get("protocol_version", -1)) != PROTOCOL_VERSION:
                raise V2ProtocolError("unsupported command envelope")
            if not request_id or not isinstance(message.get("op"), str) or not isinstance(message.get("payload", {}), Mapping):
                raise V2ProtocolError("invalid command fields")
            if request_id in self._cache:
                return self._cache[request_id]
            op, payload = message["op"].upper(), message.get("payload", {})
            if op == "DESCRIBE":
                response = _result(request_id, self._session_id, {"descriptor": self._descriptor()})
            else:
                if message.get("session_id") != self._session_id:
                    raise V2ProtocolError("session id mismatch")
                response = self._dispatch_session(request_id, op, payload)
            return self._cache_response(request_id, response)
        except V2ProtocolError as exc:
            return self._cache_response(request_id, _error(request_id, self._session_id, "INVALID_STATE", str(exc)))
        except Exception as exc:
            return self._cache_response(request_id, _error(request_id, self._session_id, "INTERNAL_ERROR", str(exc)))

    def _dispatch_session(self, request_id: str, op: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if op == "RESET":
            observation, info = self.env.reset(seed=payload.get("seed"), options=payload.get("options"))
            if not isinstance(info, Mapping):
                raise V2ProtocolError("env.reset info must be a mapping")
            self._episode_id, self._transition_id = uuid4().hex, 0
            self._latest_packet = self._packet("reset", observation, info)
            return _result(request_id, self._session_id, {"packet": self._latest_packet})
        if op == "STEP":
            if self._latest_packet is None:
                return _error(request_id, self._session_id, "NO_EPISODE", "RESET is required before STEP")
            if payload.get("episode_id") != self._episode_id or payload.get("transition_id") != self._transition_id:
                return _error(request_id, self._session_id, "STALE_TRANSITION", "episode or transition identity mismatch")
            if payload.get("descriptor_hash") != self._descriptor_hash:
                return _error(request_id, self._session_id, "SCHEMA_MISMATCH", "descriptor hash mismatch")
            action = payload.get("action")
            if not self.env.action_space.contains(action):
                return _error(request_id, self._session_id, "INVALID_ACTION", "action is not a member of action_space")
            observation, reward, terminated, truncated, info = self.env.step(action)
            if not isinstance(info, Mapping):
                raise V2ProtocolError("env.step info must be a mapping")
            self._transition_id += 1
            self._latest_packet = self._packet("step", observation, info, reward=float(reward), terminated=bool(terminated), truncated=bool(truncated))
            return _result(request_id, self._session_id, {"packet": self._latest_packet})
        if op == "GET_LATEST":
            if self._latest_packet is None:
                return _error(request_id, self._session_id, "NO_EPISODE", "no reset packet exists")
            return _result(request_id, self._session_id, {"packet": self._latest_packet})
        if op == "PING":
            return _result(request_id, self._session_id, {"nonce": payload.get("nonce"), "state": "ACTIVE" if self._latest_packet else "DESCRIBED"})
        if op == "CLOSE":
            if not self._closed:
                self.env.close()
                self._closed = True
            return _result(request_id, self._session_id, {"closed": True})
        return _error(request_id, self._session_id, "UNSUPPORTED", f"unsupported operation {op}")

    def serve_connection(self, peer: socket.socket) -> None:
        with peer:
            while not self._closed:
                try:
                    message = _recv(peer)
                except ConnectionError:
                    return
                _send(peer, self.dispatch(message))
                if self._closed:
                    return

    def serve_once(self, timeout_s: float | None = None) -> None:
        self._server.settimeout(timeout_s)
        peer, _ = self._server.accept()
        self.serve_connection(peer)

    def close(self) -> None:
        if not self._closed:
            self.env.close()
            self._closed = True
        self._server.close()


__all__ = ["CAPABILITIES", "MAX_MESSAGE_BYTES", "PROTOCOL_ID", "PROTOCOL_VERSION", "TaskEnvV2Reporter", "V2ProtocolError"]
