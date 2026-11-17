# Task environment

**Import path**：`task_env.BaseTaskEnv`、`task_env.tasks.BaseTaskEnv`
**任务域**：Task Semantics
**稳定性**：同一环境 owner 已有有界接收；provider、渲染和批量能力按版本矩阵的受测交集判断。
**职责**：描述统一环境的组件组装与任务生命周期。
**调用者/消费者**：用户、wrapper、内置 task。
**源码**：`task_env/environment/reference_env.py`、`task_env/environment/lifecycle.py`

## `task_env.tasks.BaseTaskEnv`

**Kind**：class；**Defined in**：`environment/reference_env.py`。`BaseTaskEnv` 是 `SelectedReferenceEnv` 的同对象兼容导出；`environment/env.py` 与 `tasks/base.py` 不再拥有独立环境类。

### Signature

`BaseTaskEnv(config: ResolvedEnvConfig | None = None, *, render_mode=None, build_runtime: bool = True)`

`reset(*, seed: int | None = None, options: dict[str, Any] | None = None)` 返回 `(observation, info)`；会应用初态、归零 elapsed steps、reset action/render/task definition。`step(action)` 返回 Gym 五元组 `(observation, reward, terminated, truncated, info)`：terminal 后再次 step 在 reset 前抛 `RuntimeError`。

### Lifecycle and extension hooks

`default_config()` 是 classmethod；`placement_notes()`、`create_scene_composer()`、`create_reset_sampler()`、`create_task_definition(compiled_scene)` 是供子类覆写的 Extension API。`composition_spec`、`get_env_metadata()`、`task_references` 是读取入口；未构造 runtime 时访问 runtime 相关成员抛 `StageUnavailableError`。`get_record_metadata()` 返回 recorder 使用的 JSON-compatible public projection。

### Example

```python
from task_env import make_env

env = make_env("pendulum-v1", config={"execution": {"physics_provider": "mujoco", "physics_backend": "cpu", "deployment": "in_process"}})
try:
    obs, info = env.reset(seed=73)
    obs, reward, terminated, truncated, info = env.step(env.action_space.sample())
finally:
    env.close()
```

公共 reset/step 示例可直接执行；v1.1.0 的 `single_inline` Pendulum step 有已复现的
`env.binding` AttributeError，详见[故障说明](../../../../docs/module/task_env/v2.0.0/guides/troubleshooting.md#已复现的-cli-缺陷)。完整参数矩阵见
[`doc/api/examples/index.md`](../examples/index.md)。当前 manipulation UIDs 与
expert/recording 入口见仓库根目录 `examples/README.md`；历史 `pick-cube-v1`
不会映射到新的 selected task。

## 执行选择与预检（3a 历史与当前边界）

selected 的 `execution` 可指定 provider/backend/device、host/engine、solver family/algorithm、coupler、`batch_layout`、`deployment`、`interpreter` 与 `native_dt`。`get_execution_receipt()` 返回请求、解析结果、预检及尚未读取的 native effective 状态；预检失败的异常提供 `reason`、`phase`、`request_identity` 和 JSON-compatible `receipt`。这些字段不证明原生执行或资格。

预检中的 `assessment` 按实际来源及控制声明记录对象、必需性和检查阶段；需要构建确认的项目在静态阶段保持 `pending_native_build`。已连接该检查的 adapter 完成构建后，`build_checks` 将实际具名映射与同一请求绑定，查询、reset info 及记录元数据共享该回执；这不把 `native_effective` 升为已读取，也不证明物性或任务成功。预检拒绝的回执标记 `rejected` 并记录 `failure_reason`。这些配置／准入／回执接线已由Sol按v2.1.1的3a范围接收；F06可准确在来源前拒绝不可用依赖，现有MuJoCo CPU Position／leaf生产入口已验证。该段“待 3b”只描述当时状态；后续三后端和 Isaac 的实际有界结果见[当前状态](../../../../docs/module/task_env/v2.1.1/maintenance/current-state.md)。

现有 MuJoCo CPU Position／leaf candidate 使用来源与既有执行声明解析共同 selection，并沿 selected preflight 发布同一请求回执；旧 ExecutionSpec 身份不变。F06 在解析 USD 来源前检查所选解释器依赖；若此时拒绝，回执明确标示来源尚未评估，不能当作来源完整性或原生构建结论。结构化 H5 metadata 保留同一执行回执。

3a 时的 scalar state-only 范围属于历史证据；当前 selected scalar 渲染和 device batch 已有后续有界接线，具体 dtype、生命周期及受测交集见[渲染说明](../appendix/observation_and_rendering.md)与[版本 API](../../../../docs/module/task_env/v2.1.1/api/README.md)。GeoPhys 默认从 `GEOCHORA_GEOPHYS_PYTHON`、Isaac 从 `ISAAC_SIM_PYTHON` 选择隔离解释器；MuJoCo 默认当前解释器，可用 `GEOCHORA_CORE_PYTHON` 显式选择。必须满足对应依赖与当前源码 origin，缺失或冲突会在关闭已有 session 前拒绝。

普通 PickCube／Nut 的 MJCF 会捕获其实际引用的 Panda 资源，并把原始 XML 和导入快照绑定到同一来源回执；MuJoCo 使用回执中的相同资源字节。attempt002 的 PickCube seed31、Nut seed19 已分别完成真实 MuJoCo CPU reset 和 10 步有界检查，已由Sol有界接收核心恢复，3a配置／准入／回执范围现已另经诊断001获Sol接收；不推及其他后端真实执行、任务成功或资格。F06 的精确 USD 来源约束仍适用。

## 当前 selected 路线

`task_env.environment.reference_env.SelectedReferenceEnv` 是 selected 环境的当前实现 owner；`task_env.tasks.reference_env.SelectedReferenceEnv` 为兼容导入。PickCube、Nut、Empty、Pendulum 和 TwoWheel 通过各自任务配置和同一环境 owner 构造；动作、观测及运行时接线仍由具体任务决定。selected `reset()` 省略 seed 时先使用已配置的 episode seed；显式 `seed=None` 与省略并不等价。Nut 的有界默认种子为 19。Position 候选的 seed 受固定 reset plan 约束，mixed 候选有独立明确的 reset-plan 检查。普通 selected 非空 options 不支持。

规范 Env 的方向是外部 Solution 根据 observation 产生 action，调用方使用 `step(action)`；`step_expert()` 不是标准 Env API。selected 保留的 `step_expert()` 是受限兼容入口，`reset_for_solution()` / `step_with_solution()` 也仍由 Env 调用 Solution。NutAssembly 与 scalar CPU PickCube 均支持调用方 `act → step(action) → observe`。Nut 的 Solution proposal 包含来源边界、Solution 身份与控制请求，Env 返回五样本 native receipt；普通 pose action 已在 7c002 接线并以 transition 来源区分普通动作和已校验 Solution proposal；声明的 expert identity 本身不证明专家执行，独立验收按对应回执范围判断；PickCube调用方动作同样携带声明的Solution身份及动作前边界。两条路线均在推进前核对身份和边界。在 `5a04140a`，PickCube seed31 与 NutAssembly seed19 的 MuJoCo CPU 调用方路径及同次独立读回通过[有界物理回归](../../../../docs/module/task_env/v2.1.1/maintenance/reviews/20261105_pre_stage3_resumed_physical_checks.md)，不推及其他组合。冻结的 R05b GeoPhys 原生反馈 profile 的 runtime 物化不要求 Solution 实例；普通 reset 不持有 Solution，调用方可直接提交任务 Solution 的动作；Nut task binding 在显式接收 Solution 时校验其类型、配置和来源，物理准入及反馈约束仍保留。R05b 当时的无引擎证据与后续实际 provider 验证分开保留，详见[Solution 接口](../planning/task_owned_solutions.md)及版本能力矩阵。各执行模式不能在同一 episode 混用。相关 step 调用返回 observation、reward、terminated、truncated、info。执行 fault 后必须 reset；`close()` 释放环境持有的 session，重复 close 幂等。selected 可使用已声明的渲染路线；UI `rgb_array`、task RGB 与 device camera 的 dtype 和生命周期不同，详见[渲染说明](../appendix/observation_and_rendering.md)。Action/observation、termination 与 success 以实际任务和其 spaces、metadata、评估为准；不将 Panda 的输入维数套到 classic-control。本次统一已获[Sol源码与无引擎契约有限接收](../../../../docs/module/task_env/v2.1.1/maintenance/reviews/20261105_lifecycle_unification_sol_review.md)；合成测试不能替代真实 provider 或物理验证。
