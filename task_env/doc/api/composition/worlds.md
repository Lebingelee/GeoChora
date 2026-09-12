# Worlds

**Import path**：`task_env.worlds`  
**任务域**：Task Composition  
**稳定性**：Extension API（`BaseSceneBuilder`）/ Public API（`TabletopSceneBuilder`）  
**职责**：提供可复用背景的资产与名称需求。  
**调用者/消费者**：registry、场景编译。  
**源码**：`task_env/worlds/base.py`、`tabletop.py`

## `task_env.worlds.BaseSceneBuilder`

**Kind**：class；**Defined in**：`worlds/base.py`

继承 `SceneBuilderComponent`。实现者必须提供 `asset_manifest() -> AssetManifest` 与 `reference_spec() -> ReferenceSpec`，不拥有 runtime 状态、不推进 episode。

## `task_env.worlds.TabletopSceneBuilder`

**Kind**：class；**Defined in**：`worlds/tabletop.py`

内置桌面背景组件。其资产和引用由上述方法的返回值定义；环境创建示例统一见
[`doc/api/examples/index.md`](../examples/index.md)，具体由 `make_env` 组合后再交给 public TaskEnv lifecycle。
