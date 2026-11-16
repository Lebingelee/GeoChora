"""Legacy SB3 remote proxy; loaded only when that bridge is requested."""

from __future__ import annotations

from collections.abc import Mapping
import multiprocessing as mp
from typing import Any

import gymnasium as gym
import numpy as np
from stable_baselines3.common.vec_env import VecEnv

from .parallel import _remote_worker, _require_parallel_registration
from ..utils.tree import tree_copy, validate_batched_tree


class RemoteBatchVecEnv(VecEnv):
    """SB3 VecEnv proxy for one spawned Taichi batch simulator process."""

    def __init__(
        self,
        uid: str,
        env_config: Mapping[str, Any] | None,
        num_env: int,
        backend: str,
        *,
        start_method: str = "spawn",
        compile_mode: str = "fastest",
        **env_kwargs: Any,
    ) -> None:
        if int(num_env) < 1:
            raise ValueError("num_env must be positive")
        if start_method == "fork":
            raise ValueError(
                "RemoteBatchVecEnv forbids fork; use spawn or forkserver to avoid inheriting Taichi/CUDA state"
            )

        self.uid = str(uid).strip()
        self.backend = str(backend)
        self.env_config = tree_copy(dict(env_config or {}))
        self.closed = False
        self.waiting = False
        if env_kwargs:
            unknown = ", ".join(sorted(str(key) for key in env_kwargs))
            raise TypeError(
                "RemoteBatchVecEnv accepts only resolved env_config; "
                f"unexpected kwargs: {unknown}"
            )
        # The task_env root is learner-safe and no longer eagerly imports
        # concrete task modules.  Resolve registrations at the explicit
        # parallel construction boundary instead.
        import importlib

        importlib.import_module("task_env.tasks")
        _require_parallel_registration(self.uid)
        context = mp.get_context(start_method)
        self._remote, work_remote = context.Pipe()
        config = {
            "uid": self.uid,
            "env_config": env_config,
            "num_env": int(num_env),
            "backend": self.backend,
            "compile_mode": str(compile_mode),
        }
        self.process = context.Process(
            target=_remote_worker,
            args=(work_remote, config),
            daemon=True,
        )
        self.process.start()
        work_remote.close()

        try:
            ready = self._recv()
        except BaseException:
            self.close()
            raise
        if ready[0] != "ready":
            self.close()
            raise RuntimeError(f"remote vector worker did not become ready: {ready!r}")
        _, observation_space, action_space, self.env_metadata = ready
        super().__init__(int(num_env), observation_space, action_space)
        self.metadata.update(self.env_metadata)
        self._pending_actions: Any = None

    @property
    def device_field_plan(self):
        """返回 worker 声明的不可变、可序列化 transfer provenance。"""

        return self.env_metadata.get("device_field_plan")

    def _recv(self):
        try:
            response = self._remote.recv()
        except (EOFError, OSError) as exc:
            raise ConnectionError(
                f"remote vector worker exited with code {self.process.exitcode}"
            ) from exc
        if response[0] == "error":
            _, phase, error_type, message, worker_traceback = response
            raise RuntimeError(
                f"remote vector worker failed during {phase}: "
                f"{error_type}: {message}\n{worker_traceback}"
            )
        return response

    def reset(self) -> Any:
        seed: int | list[int] | None
        if any(seed is not None for seed in self._seeds):
            seed = list(self._seeds)
        else:
            seed = None
        self._remote.send(("reset", seed))
        response = self._recv()
        if response[0] != "reset_result":
            raise RuntimeError(f"unexpected remote reset response: {response[0]}")
        _, observation, infos = response
        self.reset_infos = infos
        self._reset_seeds()
        self._reset_options()
        return observation

    def step_async(self, actions: Any) -> None:
        if self.waiting:
            raise RuntimeError("step_async() called while a remote step is pending")
        if isinstance(self.action_space, (gym.spaces.Dict, gym.spaces.Tuple)):
            validate_batched_tree(actions, self.action_space, self.num_envs)
            action_value = tree_copy(actions)
        else:
            action_value = np.asarray(actions, dtype=self.action_space.dtype)
            expected_shape = (self.num_envs, *self.action_space.shape)
            if action_value.shape != expected_shape:
                raise ValueError(f"SB3 actions must have shape {expected_shape}")
            action_value = action_value.copy()
        self._remote.send(("step", action_value))
        self._pending_actions = action_value
        self.waiting = True

    def step_wait(self):
        if not self.waiting:
            raise RuntimeError("step_wait() called without step_async()")
        try:
            response = self._recv()
        finally:
            self.waiting = False
            self._pending_actions = None
        if response[0] != "step_result":
            raise RuntimeError(f"unexpected remote step response: {response[0]}")
        return response[1:]

    def close(self) -> None:
        if self.closed:
            return
        try:
            if self.waiting:
                self._recv()
                self.waiting = False
            if self.process.is_alive():
                self._remote.send(("close", None))
                if self._remote.poll(5.0):
                    self._recv()
        except (ConnectionError, EOFError, OSError, RuntimeError):
            pass
        finally:
            self.process.join(timeout=5.0)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=5.0)
            self.closed = True
            try:
                self._remote.close()
            except OSError:
                pass

    def set_parallel_render_num(self, count: int) -> None:
        self.env_method("set_parallel_render_num", int(count))

    def set_parallel_render_layout(self, **kwargs: Any) -> None:
        self.env_method("set_parallel_render_layout", **kwargs)

    def render(self, mode: str | None = None):
        self._remote.send(("render", mode))
        response = self._recv()
        if response[0] != "value":
            raise RuntimeError(f"unexpected remote render response: {response[0]}")
        return response[1]

    def get_attr(self, attr_name: str, indices=None) -> list[Any]:
        self._remote.send(("get_attr", attr_name))
        response = self._recv()
        if response[0] != "value":
            raise RuntimeError(f"unexpected remote get_attr response: {response[0]}")
        selected = self._indices(indices)
        return [response[1] for _ in selected]

    def get_record_metadata(self) -> dict[str, Any]:
        resolved_config = {
            **self.env_config,
            "task_uid": self.uid,
            "num_envs": self.num_envs,
            "backend": self.backend,
        }
        resource_summary = self.env_metadata.get("runtime_resource_summary")
        if resource_summary is not None:
            resolved_config["runtime_resource_summary"] = tree_copy(resource_summary)
        return {
            "env_metadata": tree_copy(self.env_metadata),
            "resolved_config": resolved_config,
            "universal_action_schema": tree_copy(
                self.env_metadata.get("universal_action_schema", {})
            ),
        }

    def set_attr(self, attr_name: str, value: Any, indices=None) -> None:
        selected = self._indices(indices)
        if len(selected) != self.num_envs:
            raise AttributeError("batch attributes are shared and cannot be partially assigned")
        self._remote.send(("set_attr", (attr_name, value)))
        response = self._recv()
        if response[0] != "ok":
            raise RuntimeError(f"unexpected remote set_attr response: {response[0]}")

    def env_method(self, method_name: str, *method_args, indices=None, **method_kwargs) -> list[Any]:
        selected = self._indices(indices)
        self._remote.send(("env_method", (method_name, method_args, method_kwargs)))
        response = self._recv()
        if response[0] != "value":
            raise RuntimeError(f"unexpected remote env_method response: {response[0]}")
        return [response[1] for _ in selected]

    def env_is_wrapped(self, wrapper_class: type[gym.Wrapper], indices=None) -> list[bool]:
        del wrapper_class
        selected = self._indices(indices)
        self._remote.send(("is_wrapped", None))
        response = self._recv()
        if response[0] != "value":
            raise RuntimeError(f"unexpected remote is_wrapped response: {response[0]}")
        return [bool(response[1]) for _ in selected]

    def get_images(self):
        render_modes = self.get_attr("render_mode")
        if not render_modes or render_modes[0] is None:
            return [None for _ in range(self.num_envs)]
        selected = range(self.num_envs)
        self._remote.send(("render", "rgb_array"))
        response = self._recv()
        if response[0] != "value":
            raise RuntimeError(f"unexpected remote render response: {response[0]}")
        return [response[1] for _ in selected]

    def _indices(self, indices) -> list[int]:
        if indices is None:
            return list(range(self.num_envs))
        if isinstance(indices, (int, np.integer)):
            return [int(indices)]
        return [int(index) for index in indices]
