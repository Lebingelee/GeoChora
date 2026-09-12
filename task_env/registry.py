"""无 import-time runtime 副作用的类型安全组件 registry。

本模块只负责 component registry 与 single-environment factory
(``make_env``/``make_agent``/``make_object``/``make_scene``)。并行能力的
登记位于 ``task_env.vectorization.registry``，并行 wrapper/factory 位于
``task_env.vectorization.parallel``；后两者不在这里混入，以保持 SB3、进程
隔离和 batch lifecycle 的依赖边界。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Iterator, TypeVar

from .environment.protocols import (
    AgentComponent,
    SceneBuilderComponent,
    TaskEnvironmentComponent,
    TaskObjectComponent,
)


T = TypeVar("T")


@dataclass(frozen=True)
class Registration(Generic[T]):
    uid: str
    component_type: type[T]


class ComponentRegistry(Generic[T]):
    """只保存 class，不在注册或 import 时构造组件。"""

    def __init__(self, kind: str, expected_base: type[T]) -> None:
        self.kind = str(kind)
        self.expected_base = expected_base
        self._entries: dict[str, Registration[T]] = {}

    def register(
        self,
        uid: str,
        component_type: type[T],
        *,
        override: bool = False,
    ) -> type[T]:
        normalized_uid = str(uid).strip()
        if not normalized_uid:
            raise ValueError(f"{self.kind} uid cannot be empty")
        if not isinstance(component_type, type) or not issubclass(
            component_type,
            self.expected_base,
        ):
            raise TypeError(
                f"{self.kind} registration requires a "
                f"{self.expected_base.__name__} subclass"
            )
        declared_uid = str(getattr(component_type, "uid", "")).strip()
        if declared_uid != normalized_uid:
            raise ValueError(
                f"{self.kind} uid mismatch: key={normalized_uid!r}, "
                f"class={declared_uid!r}"
            )
        if normalized_uid in self._entries and not override:
            raise KeyError(f"duplicate {self.kind} uid: {normalized_uid}")
        self._entries[normalized_uid] = Registration(
            uid=normalized_uid,
            component_type=component_type,
        )
        return component_type

    def decorator(self, uid: str | None = None, *, override: bool = False):
        """Return a decorator accepting either an explicit or class UID.

        Both ``@register_env("pendulum-v1")`` and the less repetitive
        ``@register_env()`` (which reads ``component_type.uid``) are public
        forms.  The latter is useful when the same class is also registered
        with the parallel capability registry.
        """

        def _register(component_type: type[T]) -> type[T]:
            resolved_uid = uid if uid is not None else getattr(component_type, "uid", None)
            if resolved_uid is None:
                raise ValueError(
                    f"{self.kind} registration without uid requires class.uid"
                )
            return self.register(str(resolved_uid), component_type, override=override)

        return _register

    def get(self, uid: str) -> type[T]:
        normalized_uid = str(uid).strip()
        try:
            return self._entries[normalized_uid].component_type
        except KeyError as exc:
            raise KeyError(f"unknown {self.kind} uid: {normalized_uid}") from exc

    def create(self, uid: str, **kwargs) -> T:
        return self.get(uid)(**kwargs)

    def uids(self) -> tuple[str, ...]:
        return tuple(sorted(self._entries))

    def registrations(self) -> Iterator[Registration[T]]:
        for uid in self.uids():
            yield self._entries[uid]


ENV_REGISTRY = ComponentRegistry("environment", TaskEnvironmentComponent)
AGENT_REGISTRY = ComponentRegistry("agent", AgentComponent)
OBJECT_REGISTRY = ComponentRegistry("object", TaskObjectComponent)
SCENE_REGISTRY = ComponentRegistry("scene", SceneBuilderComponent)


register_env = ENV_REGISTRY.decorator
register_agent = AGENT_REGISTRY.decorator
register_object = OBJECT_REGISTRY.decorator
register_scene = SCENE_REGISTRY.decorator


def make_env(
    uid: str,
    *,
    config=None,
    render_mode=None,
    **kwargs,
) -> TaskEnvironmentComponent:
    """Construct a task env from task defaults plus a public config overlay."""

    # Registration modules are loaded at the actual construction boundary so
    # learner-only imports do not initialize Taichi or concrete task assets.
    import importlib

    importlib.import_module("task_env.tasks")
    environment_type = ENV_REGISTRY.get(uid)
    from .environment.configuration import resolve_task_env_config

    resolved_config = resolve_task_env_config(environment_type, config)
    if resolved_config.runtime.batch_physics_layout != "merged_scene":
        from .environment.types import StageUnavailableError

        raise StageUnavailableError(
            "batch_physics_layout is only valid for make_parallel_env(); "
            "single TaskEnv construction requires merged_scene"
        )
    return environment_type(
        config=resolved_config,
        render_mode=render_mode,
        **kwargs,
    )


def make_agent(uid: str, **kwargs) -> AgentComponent:
    import importlib

    importlib.import_module("task_env.robots")
    return AGENT_REGISTRY.create(uid, **kwargs)


def make_object(uid: str, **kwargs) -> TaskObjectComponent:
    import importlib

    importlib.import_module("task_env.objects")
    return OBJECT_REGISTRY.create(uid, **kwargs)


def make_scene(uid: str, **kwargs) -> SceneBuilderComponent:
    import importlib

    importlib.import_module("task_env.tasks.worlds")
    return SCENE_REGISTRY.create(uid, **kwargs)
