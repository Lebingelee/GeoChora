# Worlds

**Import path**：`task_env.tasks.worlds`
**任务域**：Task Composition  
**稳定性**：Extension API（`BaseSceneBuilder`）/ Public API（`TabletopSceneBuilder`）  
**职责**：提供可复用背景的资产与名称需求。  
**调用者/消费者**：registry、场景编译。  
**源码**：`task_env/tasks/worlds/base.py`、`tabletop.py`

## `task_env.tasks.worlds.BaseSceneBuilder`

**Kind**：class；**Defined in**：`worlds/base.py`

`BaseSceneBuilder` 是 `SceneBuilderComponent` 的别名。实现者必须提供 `asset_manifest() -> AssetManifest` 与 `reference_spec() -> ReferenceSpec`，不拥有 runtime 状态、不推进 episode。

## `task_env.tasks.worlds.TabletopSceneBuilder`

**Kind**：class；**Defined in**：`worlds/tabletop.py`

内置桌面背景组件。其资产和引用由上述方法的返回值定义；环境创建示例统一见
[`doc/api/examples/index.md`](../examples/index.md)，具体由 `make_env` 组合后再交给 public TaskEnv lifecycle。

桌面是场景静态结构，Task 另行声明任务对象、reset 和成功条件。资产定义可以被多个实例引用，但实例的语义名称、初态与运行身份属于具体 Task。世界坐标和重力由 source／执行配置共同限定；renderer 由环境的渲染配置选择，不由桌面 builder 推进或自动启动。

以下只读取声明，不加载仿真器：

```python
from task_env.tasks.worlds.tabletop import TabletopSceneBuilder

world = TabletopSceneBuilder()
manifest = world.asset_manifest()
references = world.reference_spec()
print(manifest.owner_uid, manifest.asset_kind)
print(references.body_names, references.geom_names)
```

声明 `grasp_table` 需要在 source 编译后解析成实际引用；缺失名称会在构造时拒绝。`build_scene_source(composition, agents)` 属于扩展路线，核对 Robot UID，与 component source 的多 Robot 情形会明确拒绝；不要通过它绕过 `make_env` 的 Task 选择。上例已在本轮受监督的无物理步骤脚本中执行；实际 scene 与 provider 支持以[构造入口](../appendix/environment_creation.md)和版本矩阵为准。

[World declarations](../../../tasks/worlds) own the scene declarations; [assembly](../../../assembly) resolves their composition.
