"""TaskEnv 场景描述基础设施。"""

from .assets import AssetManifest
from .references import ReferenceSpec
from .source import TaskSceneSource

__all__ = ["AssetManifest", "ReferenceSpec", "TaskSceneSource"]
from .compiler import (
    CompiledReferenceTaskV1,
    CompiledTaskScene,
    ReferenceTaskDeclarationV1,
    compile_task_scene,
    reference_task_identity_fields,
)
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
from .usd_delivery import (
    LoadedUsdDeliveryV1,
    load_usd_asset_delivery,
    resolve_provider_representation,
)
from .asset_scene import LoadedAssetScenePreparationV1, load_asset_scene_preparation
from .asset_scene_structure import validate_asset_scene_structure

__all__ = [
    "AgentReferences",
    "CompiledTaskScene",
    "CompiledReferenceTaskV1",
    "ObjectReferences",
    "SceneNameTable",
    "TaskReferences",
    "compile_task_scene",
    "ReferenceTaskDeclarationV1",
    "reference_task_identity_fields",
    "resolve_task_references",
    "LogicalAssemblySourceProjectionV1",
    "ProjectedEntitySourceV1",
    "ProjectedLeafSourceV1",
    "SourceReceiptLinkV1",
    "project_logical_assembly_source",
    "LoweredFixedAttachmentSourceV1",
    "lower_fixed_attachment_sources",
    "validate_fixed_attachment_scene",
    "LoadedUsdDeliveryV1",
    "load_usd_asset_delivery",
    "resolve_provider_representation",
    "LoadedAssetScenePreparationV1", "load_asset_scene_preparation",
    "validate_asset_scene_structure",
]
