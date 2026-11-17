# Configuration

用户通常将 mapping、YAML 路径或该路线接受的 resolved config 交给 `task_env.make_env(uid, *, config=None, render_mode=None, **kwargs)`。`task_env.resolve_env_config` 是关键字构造函数，必填 `task_uid`、`scene_uid`，并可传 `agent_uids`、`object_uids`、`success_definition` 及各 section；它不是接受任意字典的统一解析器。factory 内部 `resolve_task_env_config(environment_type, config)` 按实际 task 选择解析路径。未知字段、错误类型和不满足 capability 的组合会在相应构造／准入阶段报错。

## Selected 配置

四个正式任务使用`execution`、`episode`、`task`、`controller`、`robot`、`runtime`及`render`。例如：

```python
from task_env import make_env
env = make_env("pick-cube-p16-reference-v1", config={
    "execution": {"physics_provider": "mujoco", "physics_backend": "cpu"},
    "episode": {"horizon": 1000},
    "controller": {"profile_id": "r3_continuous_v1"},
})
print(env.resolved_public_config)
env.close()
```

该片段本维护版本未单独运行。解析顺序是Core → task class → task YAML → caller；旧顶层provider/backend/horizon/controller等alias已退休，不能继续用于正式配置。`task`可用字段由任务声明。`execution.render_default`当前仍限none/cpu/none/null，但这不禁止独立的observer与task RGB。scalar与device batch均接受顶层`render`及resolved往返；实际native observer backend、显式CameraSpec、CPU uint8导出和未支持sensor字段见[当前渲染合同](../../../../docs/module/task_env/v2.1.1/api/README.md#render-contract)。精确类型和准入以[`configuration.py`](../../../environment/configuration.py)为准。

## 配置层次

ResolvedEnvConfig 由以下 public section 组成：

~~~
asset
scene
agents
objects
runtime
robot
action
observation
render
task
episode
~~~

对 legacy classic-control 路线，任务 YAML 可以覆盖这些 section，调用方叠加在其上并经过 dataclass/configuration 校验。此结构与上面的 selected 输入不同。G06 的 canonical device batch 使用 selected 配置的 `make_parallel_env(..., execution='device')`；旧 classic/component 并行入口仍按其独立合同保留，不能把两者混成同一适配结论。

## RuntimeConfig

常用 runtime 字段：

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| physics_dt | 0.002 | 物理时间步 |
| control_substeps | 1 | 一个 control tick 的物理子步数 |
| backend | cpu | cpu、vulkan 或 cuda |
| integrator | implicitfast | GeoPhys runtime 积分器；MuJoCo strict CPU mixed-actuator source 可用其源 MJCF 声明的 `implicitfast` 或 `euler` |
| broadphase | n2 | 场景 broadphase |
| prewarm | true | 是否预热运行 kernel |
| batch_physics_layout | merged_scene | 当前只支持 merged_scene |
| enable_ground_contact | null | 是否启用地面接触 |
| enable_domain_boundary_contact | false | 是否启用边界接触 |

batch_physics_layout 与 make_parallel_env 的 execution 参数相互独立：当前并行物理布局只支持 `merged_scene`，旧 component 并行入口的 execution 选择当前进程 local 或独立 worker remote；声明式 device 路线使用明确的 `execution="device"`，其 provider 和 Task 适用范围另行限定。scalar 与 device batch 的布局须按各自已声明路线验证，不能仅由该字段推断批量支持。请求已退休的 `static_template` 会明确失败，不会改走其他布局。

## 已退休的 static-template runtime 配置

S4 已集成到 public `develop`（`0ff2d846a36c7014d2b40a530f52d99e64266ff9`），并移除了 GeoChora-owned static-template physics factory、profile selector 和兼容模块。`runtime.batch_physics_layout: static_template` 会 fail closed。现有 `RuntimeConfig` 保留 static-template 默认配置对象，以免无关 scalar Task 的 resolved-config identity 改变；public YAML/mapping 中显式出现 `runtime.static_template.*`，或直接传入非默认静态 profile 时都会 fail closed。错误信息指引使用 `merged_scene`，但不会自动转换用户配置。`StaticTemplate*Config` 不再从 `task_env.environment` package root 导出。

GeoPhys-owned `GeoPhysRigidBatchRuntime` adapter 与通用 Batch/Device contracts 保留；该 adapter 的 import 不代表它已注册为 `make_parallel_env` 的 runtime route，也不扩展其既有 capability envelope。旧静态 solver 实现从 `v1.0.0` 或 S4 retirement manifest 记录的 S3 baseline commit 恢复。

## Action、observation 和 render

- action 由 task/robot 的 public action contract 决定；actuator ctrl 是 runtime 细节。
- observation 通过 Gymnasium observation_space 和 versioned metadata 暴露；privileged observation 只能在 learner contract 明确允许时使用。
- render 配置只控制展示 backend、尺寸、相机和 selected parallel worlds，不改变 physics、reset、reward 或 done。
- YAML 中的 render.training 和 render.parallel 分别服务训练渲染提交与并行展示布局。

## 解析与复现

推荐在运行前固定任务 UID、YAML、backend、seed、num_env、execution 和输出目录，并保存 env.get_record_metadata()。resolved config 中会记录 runtime layout、device transition 和 reset policy，便于判断实际是否走到了目标 runtime。

## 七个 selected 输入域

| 输入 section | 负责内容 | 注意 |
| --- | --- | --- |
| `execution` | provider/backend/device、部署和解释器 | worker 解释器及依赖须与实际 provider 匹配 |
| `episode` | horizon、seed 和终止策略 | reset 显式 seed 与省略值按 Task 合同处理 |
| `task` | Task 声明的有限参数 | 不是任意修改 predicate 的入口 |
| `controller` | profile、参数及适用补偿 | 明确选择不会被默认 Controller 覆盖 |
| `robot` | Robot UID 和声明的 drive 选择 | 必须与 Task/source 和 Controller 匹配 |
| `runtime` | dt、子步及路线准入的物理配置 | 时间单位为秒，不能推断其他 provider 同义 |
| `render` | backend、尺寸与观察配置 | UI、task sensor、device camera 的数据合同不同 |

YAML 路径和 mapping 均走相同 task parser；实际 resolved config 与 `get_execution_receipt()` 可用于核对请求与解析，但 preflight 不等于 native 读取。旧顶层 alias、未知字段、不可用的解释器和不支持组合应拒绝，不静默回退。安装只按[唯一安装指南](../../../../docs/module/task_env/v2.1.1/guides/installation-and-start.md)，不要将本机路径写成所有部署的默认值。
