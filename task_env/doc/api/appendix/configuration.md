# Configuration

配置入口是 task_env.resolve_env_config 和各 task 的 default.yaml。配置对象在解析后冻结；未知字段、错误类型和不满足 capability 的组合会在构造阶段报错。

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

任务 YAML 可以覆盖这些 section；用户覆盖值会经过同一套 dataclass/configuration 校验。单环境和并行环境共享任务、动作、观测和 episode 配置。

## RuntimeConfig

常用 runtime 字段：

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| physics_dt | 0.002 | 物理时间步 |
| control_substeps | 1 | 一个 control tick 的物理子步数 |
| backend | cpu | cpu、vulkan 或 cuda |
| integrator | implicitfast | GeoPhys runtime 积分器 |
| broadphase | n2 | 场景 broadphase |
| prewarm | true | 是否预热运行 kernel |
| batch_physics_layout | merged_scene | 当前只支持 merged_scene |
| enable_ground_contact | null | 是否启用地面接触 |
| enable_domain_boundary_contact | false | 是否启用边界接触 |

batch_physics_layout 与 make_parallel_env 的 execution 参数相互独立：当前并行物理布局只支持 `merged_scene`，execution 选择当前进程 local 或独立 worker remote。single make_env 不接受 batch layout。请求已退休的 `static_template` 会明确失败，不会改走其他布局。

## 已退休的 static-template runtime 配置

S4 本地 candidate 移除了 GeoChora-owned static-template physics factory、profile selector 和兼容模块；该 candidate 尚未集成到 public `develop`。`runtime.batch_physics_layout: static_template` 会 fail closed。现有 `RuntimeConfig` 保留 static-template 默认配置对象，以免无关 scalar Task 的 resolved-config identity 改变；public YAML/mapping 中显式出现 `runtime.static_template.*`，或直接传入非默认静态 profile 时都会 fail closed。错误信息指引使用 `merged_scene`，但不会自动转换用户配置。`StaticTemplate*Config` 不再从 `task_env.environment` package root 导出。

GeoPhys-owned `GeoPhysRigidBatchRuntime` adapter 与通用 Batch/Device contracts 保留；该 adapter 的 import 不代表它已注册为 `make_parallel_env` 的 runtime route，也不扩展其既有 capability envelope。旧静态 solver 实现从 `v1.0.0` 或 S4 retirement manifest 记录的 S3 baseline commit 恢复。

## Action、observation 和 render

- action 由 task/robot 的 public action contract 决定；actuator ctrl 是 runtime 细节。
- observation 通过 Gymnasium observation_space 和 versioned metadata 暴露；privileged observation 只能在 learner contract 明确允许时使用。
- render 配置只控制展示 backend、尺寸、相机和 selected parallel worlds，不改变 physics、reset、reward 或 done。
- YAML 中的 render.training 和 render.parallel 分别服务训练渲染提交与并行展示布局。

## 解析与复现

推荐在运行前固定任务 UID、YAML、backend、seed、num_env、execution 和输出目录，并保存 env.get_record_metadata()。resolved config 中会记录 runtime layout、device transition 和 reset policy，便于判断实际是否走到了目标 runtime。
