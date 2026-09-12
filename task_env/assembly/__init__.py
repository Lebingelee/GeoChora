"""TaskEnv 场景描述基础设施。"""

from .assets import AssetManifest
from .references import ReferenceSpec
from .source import TaskSceneSource

__all__ = ["AssetManifest", "ReferenceSpec", "TaskSceneSource"]
from .compiler import CompiledTaskScene, compile_task_scene
from .references import (
    AgentReferences,
    ObjectReferences,
    SceneNameTable,
    TaskReferences,
    resolve_task_references,
)

__all__ = [
    "AgentReferences",
    "CompiledTaskScene",
    "ObjectReferences",
    "SceneNameTable",
    "TaskReferences",
    "compile_task_scene",
    "resolve_task_references",
]
