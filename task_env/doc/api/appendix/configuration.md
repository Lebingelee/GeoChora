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
| integrator | implicitfast | 默认积分器；rigid_batch_v1 要求 euler |
| broadphase | n2 | 场景 broadphase |
| prewarm | true | 是否预热运行 kernel |
| batch_physics_layout | merged_scene | merged_scene 或 static_template |
| enable_ground_contact | null | 是否启用地面接触 |
| enable_domain_boundary_contact | false | 是否启用边界接触 |

batch_physics_layout 与 make_parallel_env 的 execution 参数相互独立：前者选择并行物理布局，后者选择当前进程 local 或独立 worker remote。single make_env 不接受 batch layout。

## StaticTemplateRuntimeConfig

静态模板配置位于 runtime.static_template：

| 字段 | 可用值/默认值 | 说明 |
| --- | --- | --- |
| profile | auto | 静态模板 capability |
| kinematics_backend | torch | torch 或 taichi |
| contact_precision | f64 | f64 或 f32 |
| cuda_graph | false | 显式启用 CUDA Graph |
| contact.response_backend | auto | auto 或 active_slot_cholesky_f32_v1 |
| contact.fixed_topology_child_schur | false | 固定 topology child Schur |
| contact.root_factor_6x6 | false | 有界 root 6×6 factor；依赖 child Schur |

profile 当前包括：

~~~text
auto
hinge_or_slide_no_contact_v1
articulated_fused_no_contact_v1
articulated_fused_ground_contact_v1
articulated_ground_contact_v1
rigid_batch_v1
~~~

profile 由 compiled topology 和接触 capability 共同决定。不能使用 ground/domain contact 的 profile 会明确拒绝不兼容配置，不会静默退回 merged_scene。

rigid_batch_v1 在同一 static-template factory/lifecycle 中调用 src/solvers/rigid/batch 的 BatchedRigidSolver；当前要求 integrator=euler，不提供 TaskEnv ground/domain contact，也不声明 zero-copy device transition，state exchange 保持显式 host/NumPy boundary。其它静态 profile 的 implementation、execution、state/workspace 和 transfer capability 通过 resource_summary 与 record metadata 暴露。

## Action、observation 和 render

- action 由 task/robot 的 public action contract 决定；actuator ctrl 是 runtime 细节。
- observation 通过 Gymnasium observation_space 和 versioned metadata 暴露；privileged observation 只能在 learner contract 明确允许时使用。
- render 配置只控制展示 backend、尺寸、相机和 selected parallel worlds，不改变 physics、reset、reward 或 done。
- YAML 中的 render.training 和 render.parallel 分别服务训练渲染提交与并行展示布局。

## 解析与复现

推荐在运行前固定任务 UID、YAML、backend、seed、num_env、execution 和输出目录，并保存 env.get_record_metadata()。resolved config 中会记录 runtime layout、profile、device transition 和 reset policy，便于判断实际是否走到了目标 runtime。
