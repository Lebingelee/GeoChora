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
from .logical_source import (
    LogicalAssemblySourceProjectionV1,
    ProjectedEntitySourceV1,
    ProjectedLeafSourceV1,
    SourceReceiptLinkV1,
    project_logical_assembly_source,
)
from .fixed_attachment import (
    LoweredFixedAttachmentSourceV1,
    lower_fixed_attachment_sources,
    validate_fixed_attachment_scene,
)

__all__ = [
    "AgentReferences",
    "CompiledTaskScene",
    "ObjectReferences",
    "SceneNameTable",
    "TaskReferences",
    "compile_task_scene",
    "resolve_task_references",
    "LogicalAssemblySourceProjectionV1",
    "ProjectedEntitySourceV1",
    "ProjectedLeafSourceV1",
    "SourceReceiptLinkV1",
    "project_logical_assembly_source",
    "LoweredFixedAttachmentSourceV1",
    "lower_fixed_attachment_sources",
    "validate_fixed_attachment_scene",
]
