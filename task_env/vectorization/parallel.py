"""Generic local and process-isolated TaskEnv vector wrappers.

The communication in this module is deliberately limited to Python
``multiprocessing`` connections.  It is not a reporter transport: this
module does not import ``task_env.reporter``, does not bind a TCP port, and
does not exchange reporter observation/action packets.

The simulator worker owns the concrete Taichi environment.  The learner only
sees the SB3 ``VecEnv`` protocol and receives NumPy arrays over the local IPC
connection.  A task registers a deferred factory for its existing homogeneous runtime;
the lifecycle, SB3 bridge, and process isolation remain shared by all tasks.

This module is the implementation behind the lazy public
``task_env.make_parallel_env`` facade. Registration is intentionally kept in
``task_env.vectorization.registry`` and single-environment construction stays
in ``task_env.registry``; keeping these layers separate avoids importing SB3
or multiprocessing machinery for ordinary component creation.
"""

from __future__ import annotations

from collections.abc import Mapping
import multiprocessing as mp
import traceback
from typing import Any

import gymnasium as gym
import numpy as np
from stable_baselines3.common.vec_env import VecEnv

from .homogeneous import HomogeneousVectorTaskEnv
from .registry import PARALLEL_ENV_REGISTRY, register_parallel_env
from ..utils.tree import tree_copy, tree_index, tree_set_index, validate_batched_tree


def register_vector_env(
    uid: str,
    factory=None,
    *,
    override: bool = False,
):
    """Backward-compatible alias for ``register_parallel_env``."""

    return register_parallel_env(uid, factory, override=override)


def make_homogeneous_env(
    uid: str,
    env_config: Mapping[str, Any] | None,
    num_env: int,
    backend: str,
    execution: str = "local",
    transfer_mode: str = "device",
    **env_kwargs: Any,
) -> HomogeneousVectorTaskEnv:
    """Resolve a task factory and wrap it in the generic lifecycle."""

    # Spawned workers start with a fresh interpreter.  Importing the package's
    # task modules here replays the explicit @register_parallel_env() entries
    # while leaving concrete runtime imports inside the framework factory.
    import importlib

    importlib.import_module("task_env.tasks")
    if not PARALLEL_ENV_REGISTRY.contains(uid):
        raise KeyError(
            f"task uid has no homogeneous parallel backend: {str(uid).strip()}"
        )
    factory = PARALLEL_ENV_REGISTRY.get(uid)
    factory_kwargs: dict[str, Any] = {
        "num_env": int(num_env),
        "env_config": env_config,
        "backend": str(backend),
    }
    if PARALLEL_ENV_REGISTRY.is_framework(uid):
        factory_kwargs.update(
            {
                "execution": str(execution),
                "transfer_mode": str(transfer_mode),
            }
        )
    task_spec = factory(
        **factory_kwargs,
        **env_kwargs,
    )
    if isinstance(task_spec, HomogeneousVectorTaskEnv):
        return task_spec
    return HomogeneousVectorTaskEnv(task_spec)


def _send_worker_error(conn, phase: str, exc: BaseException) -> None:
    try:
        conn.send(
            (
                "error",
                str(phase),
                type(exc).__name__,
                str(exc),
                traceback.format_exc(),
            )
        )
    except (BrokenPipeError, EOFError, OSError):
        pass


def _step_and_autoreset(
    env: HomogeneousVectorTaskEnv,
    actions: Any,
) -> tuple[Any, np.ndarray, np.ndarray, list[dict[str, Any]]]:
    """Convert the TaskEnv five-tuple to the SB3 four-tuple in the worker."""

    observation, reward, terminated, truncated, infos = env.step(actions)
    dones = np.logical_or(terminated, truncated)
    for slot, done in enumerate(dones):
        infos[slot]["TimeLimit.truncated"] = bool(
            truncated[slot] and not terminated[slot]
        )
        if done:
            infos[slot]["terminal_observation"] = tree_index(observation, slot)

    if np.any(dones):
        reset_observation, reset_infos = env.reset(mask=dones)
        for slot, done in enumerate(dones):
            if done:
                infos[slot]["reset_info"] = reset_infos[slot]
                tree_set_index(observation, slot, tree_index(reset_observation, slot))
    return observation, reward, dones, infos


def _remote_worker(conn, config: dict[str, Any]) -> None:
    """Own Taichi and one homogeneous batch in a spawned child process."""

    env: HomogeneousVectorTaskEnv | None = None
    try:
        # All Taichi imports and initialization stay on the simulator side of
        # the process boundary.  The learner never imports this path.
        import importlib

        ti = importlib.import_module("taichi")

        from task_env.utils.runtime_support import init_task_env_backend

        init_task_env_backend(
            config["backend"],
            compile_mode=config.get("compile_mode", "fastest"),
            default_fp=ti.f32,
        )
        env = make_homogeneous_env(
            config["uid"],
            config.get("env_config"),
            config["num_env"],
            config["backend"],
            execution="remote",
            transfer_mode="host_numpy",
        )
        conn.send(
            (
                "ready",
                env.single_observation_space,
                env.single_action_space,
                dict(getattr(env, "metadata", {})),
            )
        )

        while True:
            try:
                command, payload = conn.recv()
            except (EOFError, OSError):
                break

            try:
                if command == "reset":
                    observation, infos = env.reset(seed=payload)
                    conn.send(("reset_result", observation, infos))
                elif command == "step":
                    conn.send(("step_result", *_step_and_autoreset(env, payload)))
                elif command == "get_attr":
                    if payload == "render_mode":
                        value = getattr(env, "render_mode", None)
                    else:
                        value = getattr(env, payload)
                    conn.send(("value", value))
                elif command == "set_attr":
                    setattr(env, payload[0], payload[1])
                    conn.send(("ok",))
                elif command == "env_method":
                    result = getattr(env, payload[0])(*payload[1], **payload[2])
                    conn.send(("value", result))
                elif command == "is_wrapped":
                    conn.send(("value", False))
                elif command == "render":
                    render = getattr(env, "render", None)
                    conn.send(
                        (
                            "value",
                            render(mode=payload) if render is not None else None,
                        )
                    )
                elif command == "close":
                    env.close()
                    conn.send(("closed",))
                    break
                else:
                    raise NotImplementedError(f"unknown remote vector command: {command}")
            except BaseException as exc:  # report to the learner, then keep the worker alive
                _send_worker_error(conn, str(command), exc)
    except BaseException as exc:
        _send_worker_error(conn, "initialization", exc)
    finally:
        if env is not None:
            try:
                env.close()
            except BaseException:
                pass
        try:
            conn.close()
        except OSError:
            pass


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
        if not PARALLEL_ENV_REGISTRY.contains(self.uid):
            raise KeyError(
                f"unknown TaskEnv uid: {self.uid}"
            )
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


def make_parallel_env(
    uid: str,
    env_config: Mapping[str, Any] | None = None,
    num_env: int = 1,
    backend: str = "cuda",
    *,
    execution: str = "remote",
    start_method: str = "spawn",
    compile_mode: str = "fastest",
    **env_kwargs: Any,
) -> VecEnv:
    """Create a local or process-isolated SB3 vector environment by UID.

    ``execution="remote"`` is the native-SB3 path: the parent owns PPO and
    the child owns Taichi.  ``execution="local"`` is useful for contract
    checks and explicit-gradient tests, but it intentionally retains the
    same-process Taichi/PyTorch compatibility limitation.
    """

    normalized_execution = str(execution).strip().lower()
    if normalized_execution == "remote":
        return RemoteBatchVecEnv(
            uid,
            env_config,
            num_env,
            backend,
            start_method=start_method,
            compile_mode=compile_mode,
            **env_kwargs,
        )
    if normalized_execution == "local":
        from .sb3 import TaskEnvSB3VecAdapter

        env = make_homogeneous_env(
            uid,
            env_config,
            num_env,
            backend,
            execution="local",
            transfer_mode="device",
            **env_kwargs,
        )
        return TaskEnvSB3VecAdapter(env)
    raise ValueError("execution must be 'remote' or 'local'")


__all__ = [
    "PARALLEL_ENV_REGISTRY",
    "RemoteBatchVecEnv",
    "make_homogeneous_env",
    "make_parallel_env",
    "register_parallel_env",
    "register_vector_env",
]
