# Passive objects

**Import path**：`task_env.objects`  
**任务域**：Task Composition  
**稳定性**：Extension API（基类）/ Public API（内置物体）  
**职责**：声明被动物体资产和稳定引用。  
**调用者/消费者**：object registry、`TaskReferences.objects`。  
**源码**：`task_env/objects/base.py`、`nut_assembly.py`

## `task_env.objects.BaseTaskObject`

**Kind**：class；**Stability**：Extension API；**Defined in**：`objects/base.py`

`BaseTaskObject` 是 `TaskObjectComponent` 的别名。实现者提供 `asset_manifest() -> AssetManifest` 和 `reference_spec() -> ReferenceSpec`；不得保存 solver 地址或直接推进物理。

## Built-in objects

**Kind**：class；**Stability**：Public API；**Defined in**：`objects/nut_assembly.py`

`CubeObject`、`SquareNutObject`、`SquarePegObject`、`RoundPegObject` 可由 UID 参与组合；`NUT_ASSET_ROOT` 是资产根路径常量。几何细节以编译结果为准，源码未将其作为通用 object API 字段公开。

资产定义描述几何、碰撞、质量或来源；Task 的 entity instance 决定具体语义 ID、放置和 reset。静态 peg 与可动 nut 的自由关节行为不同，不能仅因实体可动就推断 BodyWrench writer 已获准入。source lowerer 负责把已验证声明编成 provider 可消费的资源；引用缺失、单位不匹配或 source closure 不完整应在构造阶段暴露。

```python
from task_env.objects.nut_assembly import SquareNutObject

nut = SquareNutObject()
manifest = nut.asset_manifest()
references = nut.reference_spec()
print(manifest.owner_uid, manifest.source_reference)
print(references.body_names, references.joint_names, references.site_names)
```

这里读取资产声明，不物化资源或证明接触／抓取成功。改变资产来源后需重新构建 source 和匹配 Controller，不能复用旧 episode 的引用；[资产导入指南](../../资产导入与二次开发指南.md)解释实例与绑定的完整路径。[7b 接收记录](../../../../docs/module/task_env/v2.1.1/maintenance/reviews/20261117_g07b_final_acceptance.md)限定了具体 body/source 的载荷支持。上例已在本轮受监督的无物理步骤脚本中执行。
