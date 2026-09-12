# Passive objects

**Import path**：`task_env.objects`  
**任务域**：Task Composition  
**稳定性**：Extension API（基类）/ Public API（内置物体）  
**职责**：声明被动物体资产和稳定引用。  
**调用者/消费者**：object registry、`TaskReferences.objects`。  
**源码**：`task_env/objects/base.py`、`nut_assembly.py`

## `task_env.objects.BaseTaskObject`

**Kind**：class；**Stability**：Extension API；**Defined in**：`objects/base.py`

继承 `TaskObjectComponent`。子类实现 `asset_manifest() -> AssetManifest` 和 `reference_spec() -> ReferenceSpec`；不得保存 solver 地址或直接推进物理。

## Built-in objects

**Kind**：class；**Stability**：Public API；**Defined in**：`objects/nut_assembly.py`

`CubeObject`、`SquareNutObject`、`SquarePegObject`、`RoundPegObject` 可由 UID 参与组合；`NUT_ASSET_ROOT` 是资产根路径常量。几何细节以编译结果为准，源码未将其作为通用 object API 字段公开。
