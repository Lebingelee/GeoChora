"""Explicit parallel-capability registry.

The registry may contain either a legacy module-level task factory or a
TaskEnv class registered with ``@register_parallel_env()``.  Class entries are
resolved to the framework factory at creation time; task modules therefore do
not need to own a batch runtime or a second batch lifecycle implementation.

This is a capability registry, not the component registry in
``task_env.registry``. It deliberately does not construct environments or
own the local/remote SB3 lifecycle; those responsibilities belong to
``task_env.vectorization.parallel``.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from functools import partial
from collections.abc import Callable

from .contracts import ParallelTaskSpecProtocol


ParallelTaskFactory = Callable[..., ParallelTaskSpecProtocol]


@dataclass(frozen=True)
class ParallelRegistration:
    uid: str
    factory: ParallelTaskFactory | None = None
    environment_type: type | None = None

    @property
    def uses_framework_factory(self) -> bool:
        return self.factory is None and self.environment_type is not None


class ParallelEnvRegistry:
    """保存显式并行能力，不保存 runtime、field 或 CUDA 对象。"""

    def __init__(self) -> None:
        self._entries: dict[str, ParallelRegistration] = {}

    def register(
        self,
        uid: str | None = None,
        factory: ParallelTaskFactory | None = None,
        *,
        override: bool = False,
    ):
        if uid is not None and not str(uid).strip():
            raise ValueError("parallel environment uid cannot be empty")

        def _register(candidate: ParallelTaskFactory) -> ParallelTaskFactory:
            candidate_uid = getattr(candidate, "uid", None)
            normalized_uid = str(uid if uid is not None else candidate_uid or "").strip()
            if not normalized_uid:
                raise ValueError(
                    "parallel environment registration without uid requires class.uid"
                )
            if inspect.isclass(candidate):
                if not all(
                    callable(getattr(candidate, name, None))
                    for name in (
                        "create_scene_composer",
                        "create_reset_sampler",
                        "create_task_definition",
                    )
                ):
                    raise TypeError(
                        "parallel class registration requires the three TaskEnv factories"
                    )
                declared_uid = str(getattr(candidate, "uid", "")).strip()
                if declared_uid != normalized_uid:
                    raise ValueError(
                        f"parallel environment uid mismatch: key={normalized_uid!r}, "
                        f"class={declared_uid!r}"
                    )
                entry = ParallelRegistration(
                    uid=normalized_uid,
                    environment_type=candidate,
                )
            else:
                if not callable(candidate):
                    raise TypeError(
                        "parallel environment registration requires a factory or TaskEnv class"
                    )
                if inspect.isfunction(candidate) and (
                    candidate.__closure__ is not None
                    or "<locals>" in candidate.__qualname__
                ):
                    raise TypeError(
                        "parallel environment factory must be a module-level callable; "
                        "closures are not pickleable for remote workers"
                    )
                entry = ParallelRegistration(uid=normalized_uid, factory=candidate)
            if normalized_uid in self._entries and not override:
                raise KeyError(f"duplicate parallel environment uid: {normalized_uid}")
            self._entries[normalized_uid] = entry
            return candidate

        return _register(factory) if factory is not None else _register

    def get(self, uid: str) -> ParallelTaskFactory:
        normalized_uid = str(uid).strip()
        try:
            entry = self._entries[normalized_uid]
        except KeyError as exc:
            raise KeyError(
                f"task uid has no homogeneous parallel backend: {normalized_uid}"
            ) from exc
        if entry.factory is not None:
            return entry.factory
        from .factory import make_framework_parallel_spec

        return partial(make_framework_parallel_spec, uid=normalized_uid)

    def is_framework(self, uid: str) -> bool:
        normalized_uid = str(uid).strip()
        entry = self._entries.get(normalized_uid)
        return bool(entry is not None and entry.uses_framework_factory)

    def contains(self, uid: str) -> bool:
        return str(uid).strip() in self._entries

    def uids(self) -> tuple[str, ...]:
        return tuple(sorted(self._entries))


PARALLEL_ENV_REGISTRY = ParallelEnvRegistry()
register_parallel_env = PARALLEL_ENV_REGISTRY.register


__all__ = [
    "PARALLEL_ENV_REGISTRY",
    "ParallelRegistration",
    "ParallelEnvRegistry",
    "ParallelTaskFactory",
    "register_parallel_env",
]
