# Task environment

**Import path**：`task_env.BaseTaskEnv`、`task_env.tasks.BaseTaskEnv`
**任务域**：Task Semantics
**稳定性**：单环境生命周期源码和无引擎契约已有限接收，后续维护变更待复审；provider 能力以实际验证范围为准。
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

env = make_env("pendulum-v1", config={"runtime": {"backend": "cpu"}})
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

## 3a 执行选择与预检（待独立复审）

selected 的 `execution` 可指定 provider/backend/device、host/engine、solver family/algorithm、coupler、`batch_layout`、`deployment`、`interpreter` 与 `native_dt`。`get_execution_receipt()` 返回请求、解析结果、预检及尚未读取的 native effective 状态；预检失败的异常提供 `reason`、`phase`、`request_identity` 和 JSON-compatible `receipt`。这些字段不证明原生执行或资格。

预检中的 `assessment` 按实际来源及控制声明记录对象、必需性和检查阶段；需要构建确认的项目在静态阶段保持 `pending_native_build`。已连接该检查的 adapter 完成构建后，`build_checks` 将实际具名映射与同一请求绑定，查询、reset info 及记录元数据共享该回执；这不把 `native_effective` 升为已读取，也不证明物性或任务成功。预检拒绝的回执标记 `rejected` 并记录 `failure_reason`。这些接线仍待 Sol 按 3a 完整范围复审，特别是 Isaac F06 的离线入口与 versioned Controller 的完整生产入口。

当前实现只接受 scalar、state-only 和与 task cadence 相同的 native dt。GeoPhys 默认从 `GEOCHORA_GEOPHYS_PYTHON`、Isaac 从 `ISAAC_SIM_PYTHON` 选择隔离解释器；MuJoCo 默认当前解释器，可用 `GEOCHORA_CORE_PYTHON` 显式选择。必须满足对应依赖与当前源码 origin，缺失或冲突会在关闭已有 session 前拒绝。

普通 PickCube／Nut 的 MJCF 会捕获其实际引用的 Panda 资源，并把原始 XML 和导入快照绑定到同一来源回执；MuJoCo 使用回执中的相同资源字节。attempt002 的 PickCube seed31、Nut seed19 已分别完成真实 MuJoCo CPU reset 和 10 步有界检查，已由Sol有界接收核心恢复，3a整体仍待收口；不推及其他后端、任务成功或资格。F06 的精确 USD 来源约束仍适用。

## 当前 selected 路线

`task_env.environment.reference_env.SelectedReferenceEnv` 是 selected 环境的当前实现 owner；`task_env.tasks.reference_env.SelectedReferenceEnv` 为兼容导入。PickCube、Nut、Empty、Pendulum 和 TwoWheel 通过各自任务配置和同一环境 owner 构造；动作、观测及运行时接线仍由具体任务决定。普通 selected `reset()` 不传 seed 时使用 19；显式 `seed=None` 与省略并不等价。Position 候选的 seed 受固定 reset plan 约束，mixed 候选有独立明确的 reset-plan 检查。普通 selected 非空 options 不支持。

规范 Env 的方向是外部 Solution 根据 observation 产生 action，调用方使用 `step(action)`；`step_expert()` 不是标准 Env API。selected 保留的 `step_expert()` 是受限兼容入口，`reset_for_solution()` / `step_with_solution()` 也仍由 Env 调用 Solution。NutAssembly 与 scalar CPU PickCube 均支持调用方 `act → step(action) → observe`。Nut action 包含来源边界、Solution身份与控制请求，Env 返回五样本 native receipt，裸数组仍拒绝；PickCube调用方动作同样携带声明的Solution身份及动作前边界。两条路线均在推进前核对身份和边界。在 `5a04140a`，PickCube seed31 与 NutAssembly seed19 的 MuJoCo CPU 调用方路径及同次独立读回通过[有界物理回归](../../../../docs/module/task_env/v2.1.1/maintenance/reviews/20261105_pre_stage3_resumed_physical_checks.md)，不推及其他组合。冻结的 R05b GeoPhys 原生反馈 profile 的 runtime 物化不要求 Solution 实例；普通 reset 不持有 Solution，调用方可直接提交任务 Solution 的动作；Nut task binding 在显式接收 Solution 时校验其类型、配置和来源，物理准入及反馈约束仍保留。当前 R05b 调用方路线及无 Solution 物化证据仅为无引擎测试，详见[Solution 接口](../planning/task_owned_solutions.md)。各执行模式不能在同一 episode 混用。相关 step 调用返回 observation、reward、terminated、truncated、info。执行 fault 后必须 reset；`close()` 释放环境持有的 session，重复 close 幂等。selected 普通 public 配置当前 state-only，不接受 `render_mode`。Action/observation、termination 与 success 以实际任务和其 spaces、metadata、评估为准；不将 Panda 的输入维数套到 classic-control。本次统一已获[Sol源码与无引擎契约有限接收](../../../../docs/module/task_env/v2.1.1/maintenance/reviews/20261105_lifecycle_unification_sol_review.md)；合成测试不能替代真实 provider 或物理验证。
