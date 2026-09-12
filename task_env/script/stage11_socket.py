"""Stage 11 socket-v2 server and Flow Matching policy client.

The server owns only a GeoPhys environment.  The client owns only policy
inference and evaluation bookkeeping; the socket protocol performs descriptor,
session, episode and transition validation.
"""

from __future__ import annotations

import argparse
from collections import deque
import json
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
import math
from pathlib import Path
import sys
from typing import Any

import h5py
import numpy as np

if __package__ in (None, ""):
    from _bootstrap import configure_imports
else:
    from ._bootstrap import configure_imports

configure_imports()

from task_env import make_env
from task_env.script.recorder import _pick_cube_config


def _socket_imports():
    from agent_infra.socket_env.Env.v2 import SocketEnvV2
    from agent_infra.socket_env.Report.server import EnvReporter

    return SocketEnvV2, EnvReporter


def _descriptor_value(value: Any) -> Any:
    """Convert GeoPhys metadata into strict finite descriptor JSON values."""

    if is_dataclass(value):
        return _descriptor_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _descriptor_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_descriptor_value(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_descriptor_value(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _descriptor_value(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _descriptor_metadata(env) -> dict[str, Any]:
    return _descriptor_value(dict(env.metadata))


class _ReporterEnv:
    """Keep GeoPhys stepping intact while making protocol info JSON-safe."""

    def __init__(self, env):
        self._env = env
        self.observation_space = env.observation_space
        self.action_space = env.action_space
        self.metadata = env.metadata

    def reset(self, **kwargs):
        observation, info = self._env.reset(**kwargs)
        return observation, _descriptor_value(info)

    def step(self, action):
        observation, reward, terminated, truncated, info = self._env.step(action)
        return observation, reward, terminated, truncated, _descriptor_value(info)

    def close(self):
        self._env.close()


def run_server(args: argparse.Namespace) -> None:
    _, EnvReporter = _socket_imports()
    config = _pick_cube_config(
        args.backend,
        120,
        camera_obs=True,
        camera_size=args.camera_size,
    )
    env = make_env("pick-cube-v1", config=config)
    reporter_env = _ReporterEnv(env)
    reporter = EnvReporter(
        reporter_env,
        bind_host=args.host,
        port=args.port,
        metadata_provider=_descriptor_metadata,
    )
    host, port = reporter.address
    print(json.dumps({"host": host, "port": port}, sort_keys=True), flush=True)
    try:
        reporter.serve_once(timeout_s=args.accept_timeout)
    finally:
        reporter.close()


def _h5_layout(path: Path) -> tuple[list[str], list[str]]:
    with h5py.File(path, "r") as root:
        group = root["traj_000"] if "traj_000" in root else root
        return list(group["obs/state"].keys()), list(group["obs/rgb"].keys())


def _state_frame(observation: dict[str, Any], order: list[str]) -> np.ndarray:
    state = observation.get("state")
    if not isinstance(state, dict):
        raise ValueError("socket observation has no state mapping")
    return np.concatenate(
        [np.asarray(state[key], dtype=np.float32).reshape(-1) for key in order], axis=0
    ).astype(np.float32)


def _rgb_frame(observation: dict[str, Any], order: list[str]) -> np.ndarray:
    rgb = observation.get("rgb")
    if not isinstance(rgb, dict):
        raise ValueError("socket observation has no rgb mapping")
    images = []
    for key in order:
        image = np.asarray(rgb[key])
        if image.ndim != 3 or (image.shape[0] != 3 and image.shape[-1] != 3):
            raise ValueError(f"socket RGB leaf {key!r} is not a 3-channel image")
        if image.shape[0] != 3:
            image = np.transpose(image, (2, 0, 1))
        if image.dtype != np.uint8:
            values = image.astype(np.float32)
            if np.all((values >= 0.0) & (values <= 1.0)):
                values = values * 255.0
            image = np.rint(values).clip(0.0, 255.0).astype(np.uint8)
        images.append(image)
    return np.concatenate(images, axis=0)


def _agent_observation(
    state_history: deque[np.ndarray],
    rgb_history: deque[np.ndarray],
):
    import torch

    return {
        "state": torch.from_numpy(np.stack(tuple(state_history), axis=0)[None]).float(),
        "rgb": torch.from_numpy(np.stack(tuple(rgb_history), axis=0)[None]).to(torch.uint8),
    }


def _load_policy(config_path: Path, checkpoint: Path):
    from agent_factory.agents.registry import make_agent
    from agent_factory.config.resolution import general_resolve
    from omegaconf import OmegaConf

    cfg = OmegaConf.load(config_path)
    resolved = general_resolve(file_config=cfg, override_config={})[0]
    agent = make_agent(str(resolved.agent_type), resolved)
    agent.load(str(checkpoint))
    agent.to(str(getattr(resolved, "device", "cuda:0")))
    agent.eval()
    return agent


def _policy_action(agent, observation) -> np.ndarray:
    import torch

    with torch.no_grad():
        output = agent.sample_action(observation)
    if isinstance(output, torch.Tensor):
        output = output.detach().cpu().numpy()
    action = np.asarray(output, dtype=np.float32)
    if action.ndim == 3:
        action = action[0]
    if action.ndim == 2:
        action = action[0]
    if action.shape != (8,) or not np.isfinite(action).all():
        raise ValueError(f"policy action must be finite shape (8,), got {action.shape}")
    return action


def run_client(args: argparse.Namespace) -> None:
    SocketEnvV2, _ = _socket_imports()
    state_order, rgb_order = _h5_layout(args.data)
    agent = _load_policy(args.config, args.checkpoint)
    env = SocketEnvV2(
        args.host,
        args.port,
        connect_timeout_s=args.timeout,
        request_timeout_s=args.timeout,
        auto_connect=True,
    )
    rows: list[dict[str, Any]] = []
    try:
        for seed in range(1000, 1050):
            state_history: deque[np.ndarray] = deque(maxlen=2)
            rgb_history: deque[np.ndarray] = deque(maxlen=2)
            steps = 0
            failure: str | None = None
            final_info: dict[str, Any] = {}
            try:
                observation, info = env.reset(seed=seed)
                state = _state_frame(observation, state_order)
                rgb = _rgb_frame(observation, rgb_order)
                for _ in range(2):
                    state_history.append(state.copy())
                    rgb_history.append(rgb.copy())
                while steps < 120:
                    action = _policy_action(agent, _agent_observation(state_history, rgb_history))
                    if not env.action_space.contains(action):
                        raise ValueError("INVALID_ACTION: action is outside advertised action_space")
                    observation, _, terminated, truncated, info = env.step(action)
                    final_info = dict(info)
                    steps += 1
                    state_history.append(_state_frame(observation, state_order))
                    rgb_history.append(_rgb_frame(observation, rgb_order))
                    if terminated or truncated:
                        break
            except TimeoutError:
                failure = "socket_timeout"
            except (ConnectionError, OSError) as exc:
                failure = f"socket_timeout:{type(exc).__name__}"
            except ValueError as exc:
                text = str(exc)
                failure = "schema_mismatch" if "schema" in text.lower() else "invalid_action"
            except Exception as exc:  # protocol, model shape, and remote errors are failures
                text = str(exc)
                failure = "schema_mismatch" if "descriptor" in text.lower() or "protocol" in text.lower() else f"client_error:{type(exc).__name__}"
            metrics = final_info.get("task_metrics", {})
            metrics = dict(metrics) if isinstance(metrics, dict) else {}
            success = bool(final_info.get("is_success", False)) and float(metrics.get("cube_lift", 0.0)) >= 0.10
            if failure is None and not success:
                failure = "task_not_successful" if steps < 120 else "horizon_exhausted"
            rows.append({
                "seed": seed,
                "success": bool(success and failure is None),
                "final_lift": float(metrics.get("cube_lift", 0.0)),
                "steps": steps,
                "failure_reason": failure,
            })
    finally:
        env.close()
    successes = sum(bool(row["success"]) for row in rows)
    output = {
        "protocol": "socket_env_v2",
        "seed_range": [1000, 1049],
        "episodes": rows,
        "success_count": successes,
        "success_rate": successes / 50.0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2), encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    server = sub.add_parser("server")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=0)
    server.add_argument("--backend", choices=("cpu", "cuda"), default="cuda")
    server.add_argument("--camera-size", type=int, default=64)
    server.add_argument("--accept-timeout", type=float, default=None)
    server.set_defaults(handler=run_server)
    client = sub.add_parser("client")
    client.add_argument("--host", default="127.0.0.1")
    client.add_argument("--port", type=int, required=True)
    client.add_argument("--config", type=Path, required=True)
    client.add_argument("--checkpoint", type=Path, required=True)
    client.add_argument("--data", type=Path, required=True)
    client.add_argument("--output", type=Path, required=True)
    client.add_argument("--timeout", type=float, default=10.0)
    client.set_defaults(handler=run_client)
    return parser


if __name__ == "__main__":
    parsed = _parser().parse_args()
    parsed.handler(parsed)
