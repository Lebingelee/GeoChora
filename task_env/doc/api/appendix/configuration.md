# Configuration

用户通常将 mapping、YAML 路径或该路线接受的 resolved config 交给 `task_env.make_env(uid, *, config=None, render_mode=None, **kwargs)`。`task_env.resolve_env_config` 是关键字构造函数，必填 `task_uid`、`scene_uid`，并可传 `agent_uids`、`object_uids`、`success_definition` 及各 section；它不是接受任意字典的统一解析器。factory 内部 `resolve_task_env_config(environment_type, config)` 按实际 task 选择解析路径。未知字段、错误类型和不满足 capability 的组合会在相应构造／准入阶段报错。

## Selected 配置

PickCube 和 Nut 使用 `execution`、`episode`、`task`。例如：

```python
from task_env import make_env
env = make_env("pick-cube-p16-reference-v1", config={
    "execution": {"physics_provider": "mujoco", "physics_backend": "cpu"},
    "episode": {"horizon": 1000},
    "task": {"controller_profile": "r3_continuous_v1"},
})
print(env.resolved_public_config)
env.close()
```

该片段本维护版本未运行。解析顺序是 Core → task class → task YAML → caller；允许的顶层兼容 alias 为 `provider`、`backend`、`horizon`、`controller_profile`、`source_delivery_manifest`，与其嵌套等价项同时指定会报冲突。`task` 可用字段由任务声明，不可任意叠加。当前 selected CPU 接受 GeoPhys 或 MuJoCo；Isaac 仅限明确的 PickCube/R3/CUDA 和 delivery manifest 准入。`execution.render_default` 当前只接受 none/cpu/none/null 的 state-only 组合，`render_mode` 非空也会被拒绝。精确类型、缺失值和错误以 [`configuration.py`](../../../environment/configuration.py) 为准。

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

对 legacy classic-control 路线，任务 YAML 可以覆盖这些 section，调用方叠加在其上并经过 dataclass/configuration 校验。此结构与上面的 selected 输入不同；统一 Env 并行尚未适配。

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

batch_physics_layout 与 make_parallel_env 的 execution 参数相互独立：当前并行物理布局只支持 `merged_scene`，execution 选择当前进程 local 或独立 worker remote。single make_env 不接受 batch layout。请求已退休的 `static_template` 会明确失败，不会改走其他布局。

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
