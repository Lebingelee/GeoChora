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

## Source 与 Robot 的共同构建

正式 Task 将 `TaskBuildRequest` 交给既有 builder；Task 声明所需的实体、初态、时基及 body 映射，source compiler 生成实际 snapshot 与 closure。Robot recipe 声明组件、frame、joint、transmission 和 writer；公共 source composer 验证并组合它们，再将 Controller 与最终 source 的具名资源匹配。`RobotRuntime` 是已绑定主体的运行视图，不能用类注册或单独构造 Controller 来代替这条链。原 Panda 与受支持的 arm/hand 装配沿相同 owner；各自的名称、TCP 和参数仍由 Robot/source 声明。

source snapshot 和 session 具有资源寿命：构造中失败要关闭已获得的 source，正常调用由环境 `close` 释放；重建后不要缓存旧 native ID 或旧 bound Controller。native 索引只在其 source/materialization 内有效，Task 和调用者应使用具名引用或公开状态，而不是保存 provider 私有地址。

下面经正式注册和配置构造已验证的 marker，展示共同链的使用，而不是手工创建 source lease：

```python
import numpy as np
import examples.tasks.declared_marker
from task_env import make_env

env = make_env('marker-height-example-v1', config={
    'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu', 'deployment': 'in_process'},
    'episode': {'horizon': 10},
})
try:
    obs, info = env.reset(seed=19)
    pose = env.state.pose_world['panda-v1/ee']
    action = np.asarray([*pose.position, *pose.quaternion_wxyz, 1.], dtype=np.float64)
    action[0] += .001
    obs, reward, terminated, truncated, info = env.step(action)
    print(info['task_metrics']['marker_height_m'])
finally:
    env.close()
```

7c002 的 marker-005 对应 MuJoCo CPU 真实非零 step、重新 reset、同运行 H5 读回与 close；不证明任意 provider 或 source。缺失 subject binding、source closure 或名称冲突应由共同构造拒绝，不手填伪 closure，也不取消 guard。[自定义任务指南](../../自定义任务构建指南.md)描述 Task author 的各个声明位置。
