"""GeoPhys TaskEnv public entry points.

Registration modules are imported eagerly because they are lightweight
descriptors (they do not initialize Taichi/solvers); runtime-heavy assembly
remains deferred to ``make_env``/``make_parallel_env``.  This preserves the
historical registry contents while keeping learner-only imports safe.
"""

from importlib import import_module

from .environment.configuration import resolve_env_config
from .registry import (
    AGENT_REGISTRY,
    ENV_REGISTRY,
    OBJECT_REGISTRY,
    SCENE_REGISTRY,
    make_agent,
    make_env,
    make_object,
    make_scene,
)

# Populate the public registries without constructing any simulator.  The
# modules intentionally contain only task/asset descriptors and factories;
# concrete runtime imports stay inside explicit construction boundaries.
from . import objects as _registered_objects  # noqa: F401,E402
from . import robots as _registered_robots  # noqa: F401,E402
from . import tasks as _registered_tasks  # noqa: F401,E402


def make_parallel_env(*args, **kwargs):
    """Lazily create an optional homogeneous parallel TaskEnv.

    The public facade lives here, while the capability registry and the
    local/remote SB3 implementation remain under ``vectorization`` so
    ``make_env`` does not acquire parallel-only dependencies.
    """

    from .vectorization.parallel import make_parallel_env as _make_parallel_env

    return _make_parallel_env(*args, **kwargs)


def register_parallel_env(*args, **kwargs):
    """Lazily register a task-owned homogeneous parallel factory."""

    from .vectorization.registry import register_parallel_env as _register

    return _register(*args, **kwargs)


def _get_parallel_registry():
    from .vectorization.registry import PARALLEL_ENV_REGISTRY

    return PARALLEL_ENV_REGISTRY


_LAZY_EXPORTS = {
    "PandaAgent": ("task_env.robots", "PandaAgent"),
    "ActionConfig": ("task_env.environment", "ActionConfig"),
    "CameraSpec": ("task_env.environment", "CameraSpec"),
    "ExternalActionContract": ("task_env.environment", "ExternalActionContract"),
    "ObservationConfig": ("task_env.environment", "ObservationConfig"),
    "ParallelRenderConfig": ("task_env.environment", "ParallelRenderConfig"),
    "RenderConfig": ("task_env.environment", "RenderConfig"),
    "ResolvedEnvConfig": ("task_env.environment", "ResolvedEnvConfig"),
    "RuntimeBoundary": ("task_env.environment", "RuntimeBoundary"),
    "StageUnavailableError": ("task_env.environment", "StageUnavailableError"),
    "TaskCompositionSpec": ("task_env.environment", "TaskCompositionSpec"),
    "TaskEnvMetadata": ("task_env.environment", "TaskEnvMetadata"),
    "TaskEvaluation": ("task_env.environment", "TaskEvaluation"),
    "TrainingRenderConfig": ("task_env.environment", "TrainingRenderConfig"),
    "CubeObject": ("task_env.objects", "CubeObject"),
    "RoundPegObject": ("task_env.objects", "RoundPegObject"),
    "SquareNutObject": ("task_env.objects", "SquareNutObject"),
    "SquarePegObject": ("task_env.objects", "SquarePegObject"),
    "ExpertAction": ("task_env.planners", "ExpertAction"),
    "TaskExpertSolver": ("task_env.planners", "TaskExpertSolver"),
    "RenderMode": ("task_env.render", "RenderMode"),
    "RenderUnavailableError": ("task_env.render", "RenderUnavailableError"),
    "BaseTaskEnv": ("task_env.tasks", "BaseTaskEnv"),
    "Go2WalkEnv": ("task_env.tasks", "Go2WalkEnv"),
    "EmptyTaskEnv": ("task_env.tasks", "EmptyTaskEnv"),
    "NutAssemblyEnv": ("task_env.tasks", "NutAssemblyEnv"),
    "PendulumEnv": ("task_env.tasks", "PendulumEnv"),
    "PickCubeEnv": ("task_env.tasks", "PickCubeEnv"),
    "TabletopSceneBuilder": ("task_env.tasks", "TabletopSceneBuilder"),
    "TwoWheelBalanceEnv": ("task_env.tasks", "TwoWheelBalanceEnv"),
}


def __getattr__(name: str):
    if name == "PARALLEL_ENV_REGISTRY":
        value = _get_parallel_registry()
        globals()[name] = value
        return value
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute = target
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value

__all__ = [
    "AGENT_REGISTRY",
    "ActionConfig",
    "ENV_REGISTRY",
    "OBJECT_REGISTRY",
    "PARALLEL_ENV_REGISTRY",
    "SCENE_REGISTRY",
    "BaseTaskEnv",
    "CameraSpec",
    "CubeObject",
    "EmptyTaskEnv",
    "ExpertAction",
    "ExternalActionContract",
    "Go2WalkEnv",
    "NutAssemblyEnv",
    "PendulumEnv",
    "ObservationConfig",
    "ParallelRenderConfig",
    "PandaAgent",
    "PickCubeEnv",
    "RenderConfig",
    "RenderMode",
    "RenderUnavailableError",
    "ResolvedEnvConfig",
    "RoundPegObject",
    "RuntimeBoundary",
    "SquareNutObject",
    "SquarePegObject",
    "StageUnavailableError",
    "TabletopSceneBuilder",
    "TaskCompositionSpec",
    "TaskEnvMetadata",
    "TaskEvaluation",
    "TrainingRenderConfig",
    "TaskExpertSolver",
    "TwoWheelBalanceEnv",
    "make_agent",
    "make_env",
    "make_parallel_env",
    "make_object",
    "make_scene",
    "register_parallel_env",
    "resolve_env_config",
]
