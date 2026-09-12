# Assembly and references

**Import path**：`task_env.assembly`  
**任务域**：Task Composition  
**稳定性**：Extension API（source/compiler）/ Public API（references）  
**职责**：组合组件、编译场景并生成稳定引用。  
**调用者/消费者**：runtime assembly、action、observation、task definition。  
**源码**：`task_env/assembly/`

## `task_env.assembly.TaskSceneSource`

**Kind**：frozen dataclass；**Stability**：Extension API；**Defined in**：`source.py`

签名：`TaskSceneSource(xml: str, base_dir: Path, source_id: str, diagnostics: tuple[str, ...] = ())`。这是装配期场景 source，不是 tick API。

## `compile_task_scene` / `CompiledTaskScene`

**Kind**：function / dataclass；**Stability**：Extension API；**Defined in**：`compiler.py`

编译 `TaskCompositionSpec` 与组件。它属于构造流程，不可在 task solution 中替代 `env.step()`。

## `SceneNameTable`、`AgentReferences`、`ObjectReferences`、`TaskReferences`

**Kind**：frozen dataclass；**Stability**：Public API；**Defined in**：`references.py`

`SceneNameTable` 记录 body/joint/site/geom/actuator 名称到 ID 的映射；`TaskReferences(names, agents, objects)` 汇总 agent/object 引用。映射与 ID 数组均被冻结或 readonly。`resolve_task_references(...)` 在编译期核验 `ReferenceSpec`，未解析名称会抛出 `KeyError`。
