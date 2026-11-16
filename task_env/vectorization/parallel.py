"""Shared parallel entry point and legacy SB3 worker functions.

Local and remote execution retain the NumPy/SB3 contract. Explicit device
execution selects the shared task builder and a device lifecycle without SB3.
"""

from __future__ import annotations

from collections.abc import Mapping
import traceback
from typing import Any

import numpy as np

from .homogeneous import HomogeneousVectorTaskEnv
from .registry import PARALLEL_ENV_REGISTRY, register_parallel_env
from ..utils.tree import tree_index, tree_set_index


def _require_parallel_registration(uid: str) -> None:
    """Reject known scalar-only tasks before creating a worker or Runtime."""
    if PARALLEL_ENV_REGISTRY.contains(uid):
        return
    from ..registry import ENV_REGISTRY
    from ..environment.types import StageUnavailableError

    normalized = str(uid).strip()
    if normalized in ENV_REGISTRY.uids() and getattr(
        ENV_REGISTRY.get(normalized), 'uses_selected_public_config', False
    ):
        raise StageUnavailableError(
            f"task {normalized!r} has no formal batch adapter; use scalar make_env"
        )
    raise KeyError(f"task uid has no homogeneous parallel backend: {normalized}")


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
    _require_parallel_registration(uid)
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
):
    """Create an SB3 vector environment or an explicit device batch by UID.

    ``execution="remote"`` is the native-SB3 path: the parent owns PPO and
    the child owns Taichi.  ``execution="local"`` is useful for contract
    checks and explicit-gradient tests, but it intentionally retains the
    same-process Taichi/PyTorch compatibility limitation.
    ``execution="device"`` returns the device five-tuple lifecycle.
    """

    normalized_execution = str(execution).strip().lower()
    if normalized_execution == 'device':
        from .factory import make_selected_device_spec

        if start_method != 'spawn' or compile_mode != 'fastest':
            raise ValueError('SB3 worker options do not apply to device execution')
        worker_directory = env_kwargs.pop('worker_directory', None)
        render_mode = env_kwargs.pop('render_mode', None)
        if env_kwargs:
            raise TypeError(f'unsupported device environment options: {sorted(env_kwargs)}')
        spec = make_selected_device_spec(uid=uid, num_env=num_env, env_config=env_config,
                                         backend=backend, worker_directory=worker_directory,
                                         render_mode=render_mode)
        try:
            return HomogeneousVectorTaskEnv(spec, execution_mode='device')
        except BaseException:
            spec.close()
            raise
    if normalized_execution == "remote":
        from .sb3_remote import RemoteBatchVecEnv

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
    raise ValueError("execution must be 'remote', 'local' or 'device'")


def __getattr__(name: str):
    if name == "RemoteBatchVecEnv":
        from .sb3_remote import RemoteBatchVecEnv

        return RemoteBatchVecEnv
    raise AttributeError(name)


__all__ = [
    "PARALLEL_ENV_REGISTRY",
    "RemoteBatchVecEnv",
    "make_homogeneous_env",
    "make_parallel_env",
    "register_parallel_env",
    "register_vector_env",
]
