# 阶段3前维护：职责与当前文档处置清单

本清单核对源码 `80904684`，供后续实施和 Sol 复审使用；不是接收决定，也不是阶段3授权。它记录真实调用和剩余问题，不把文件移动或目录形态当作职责验收。验证结果及其源码身份以[续作检查点](20261105_pre_stage3_continuation.md)和[验收门草稿](20261105_pre_stage3_gate_audit.md)为准。

## 原功能到当前 owner

| 原功能／输入 | 当前通用 owner | 任务、诊断和真实调用者 | 尚需复核的边界 |
| --- | --- | --- | --- |
| `tasks/guarded_transition.py`：样本间隔与连续性 | `task_env/planners/completion.py::measured_interval_timing` 校验时间、采样间隔与缺口 | `nut_assembly/solution.py::GuardedTransitionEvaluator` 调用；阶段、优先级、关爪与抓取条件和任务阈值留在Nut Solution及配置 | 不能把缺采样视为连续；五样本反馈是正式执行契约，不是可删除的展示数据。相关离线测试在 `diagnostics/phase1/integration/test_guarded_transition.py` 与 `diagnostics/tasks/test_selected_consumers.py` |
| `tasks/canonical_solution_lifecycle.py`：完成／失败和恢复 | `task_env/planners/completion.py::CanonicalSolutionLifecycle` 与 `SolutionCompletionPolicy` | `nut_assembly/solution.py::NutAssemblySolutionLifecycle` 负责Nut终段事件与完成策略；`diagnostics/phase1/integration/test_solution_lifecycle.py` 检查恢复 | Solution完成不等于任务success；Env episode/fault/close属于 `environment/lifecycle.py`，不能再造第二套Env状态机 |
| `tasks/declarative_reference.py`：声明编译、reset、评价和旧中间模板 | `assembly/compiler.py::ReferenceTaskDeclarationV1`、`reference_construction_value` 与 `assembly/panda_box.py` 承接已用的编译／来源能力；规范Env的 `from_resolved_config` 接公共factory | `examples/tasks/declared_marker.py` 保留声明、reset、评价与正常注册；`task_env.make_env` 构造。旧 `DeclaredPandaBoxEnv` 与 `make_marker_env` 已移除 | Marker仍显式创建binding及resolved配置，构造来源不证明闭包所有间接依赖；R2尚待继续整理及Sol复审，不能称为最短开发路线已验收 |
| PickCube `tasks/pick_cube/isaac.py`：USD投影和准入 | `runtime/sessions/source.py::UsdRuntimeInputV1`、`runtime/sessions/api.py` 和现有USD delivery owner保存类型、来源／provider准入；`isaac_native_io.py` 消费该输入 | PickCube具体source／Scene投影、固定映射和任务声明在 `pick_cube/specialization.py`；真实构造与合成拒绝检查在 `diagnostics/tasks/test_pickcube_isaac_projection.py` 等 | runtime依受信声明摘要及原delivery／执行约束严格核验；真实Isaac未运行。F05 Session分类仍反向导入任务候选类型，不能宣称全部runtime依赖方向已归位 |
| Nut trusted source manifest | `assembly/r05b_trusted_execution_source_manifest.json` 保存原始字节 | `runtime/sessions/api.py` 准入、`nut_assembly/specialization.py` 来源清单及 `diagnostics/tasks/r05b_native_feedback_independent_reader.py` 消费新位置 | 以原输入 `4bdf4d5f` 的旧路径与现文件对比，SHA-256均为 `0895a65980b97650bcc91ed9ee8a536958a15b0bc8d5703f5eab5ffdebd5c7d6`；历史raw和原路径解释不改写 |
| 单环境构造／生命周期 | `environment/reference_env.py::SelectedReferenceEnv`；`environment/lifecycle.py::EpisodeExecutionState` 是共同episode执行协调owner | Empty、Pendulum、TwoWheel经公共factory；selected任务经各自binding。`BaseTaskEnv`各兼容出口与规范类同对象 | R1在 `48401525` 获Sol有限接收；组件RuntimeBoundary和selected RuntimeSession仍各有接线与投影。当前类仍较大，未完成整体职责整理；并行留G06 |
| 控制反馈／记录／重执行 | `controllers/canonical/feedback.py` 校验并投影selected applied ack；`recorders/reference_provenance.py` 处理selected来源与transition；`recorders/position_metadata.py` 投影Position记录 | PickCube／Nut示例及selected重执行使用调用方 `act → env.step(action) → observe`；正式native反馈与故障数据由任务／runtime契约提供，展示与对照在diagnostics | `step_expert()`仍为受限兼容。旧Nut专家录制与新调用方记录契约不同，当前重执行明确拒绝；Position v3重执行不支持。合成H5读回不是物理成功证明 |
| 历史replay构造 | `environment/_historical.py::make_replay_env` 提供受限历史入口；`trajectory/replay.py` 使用它 | `diagnostics/historical_tasks.py` 是兼容调用者；`diagnostics/tasks/test_pre_stage3_boundaries.py` 检查历史拒绝 | 不恢复已退役任务，也不把旧H5或冻结源码结果重标为当前实现 |

PickCube和Nut任务目录当前各保留四个业务文件 `task.py`、`specialization.py`、`solution.py`、`config.yaml` 及必要 `__init__.py`。`task.py` 承担任务评价、reset及必要反馈投影；`specialization.py` 连接声明、source、Controller和执行配置；`solution.py` 负责各自规划、阶段和完成策略；`config.yaml` 保存配置。实际职责还须结合源码逐项复审，不能以数量代替检查。

静态扫描中活跃非测试Python未调用 `step_expert()`，只保留方法定义；兼容／故障测试仍有调用。旧三个模块、旧Marker包装／模板及 `tasks.pick_cube.isaac` 没有活跃源码导入；扫描中旧 `declarative_reference.py` 名称只用于测试断言其不在新来源清单。该扫描不等同真实provider验证。

## 当前文档处置

| 活跃入口 | 当前处置及依据 | 未完成或限制 |
| --- | --- | --- |
| `task_env/README.md`、`task_env/doc/index.md`、`task_env/doc/api/index.md` | 保留当前公共 `make_env` 和单环境导航；规范数据流与示例对照 `task_env/registry.py`、`examples/tasks/` | 不宣称全provider、并行或新协议可用；后续接口改动时再核对 |
| `task_env/doc/自定义任务构建指南.md`、`task_env/doc/新手使用训练与采集.md` | 按Marker声明和公共factory说明任务开发、采集及Solution方向 | Marker仍存在内部binding接线，新手原生闭环未对最终源码完成，不能宣称简化目标验收 |
| `task_env/doc/api/planning/task_owned_solutions.md`、`task_env/doc/api/semantics/task_environment.md` | 说明外部Solution、动作边界与身份、Nut反馈及兼容入口 | 身份是内容一致性检查，不是调用者认证；Nut当前源码完整物理成功未验证 |
| `task_env/doc/api/recording/trajectory_cli.md` | 区分历史replay、selected同源重执行和H5离线检查；说明已记录源码清单与旧Nut拒绝 | Position v3重执行不支持；缺少历史源码清单不能证明完整同源；reader不等同物理回归 |
| `docs/module/task_env/v2.1.1/guides/installation-and-start.md`、`examples/start.py` | 保留新安装／复用现有路径和显式解释器、GeoPhys路径的路线；记录依赖约束 | 本次 `3ed14c08` 物理单步直接运行 `examples/tasks/scalar_step.py`，未运行上游 `examples/start.py`；不要重标 |
| `task_env/doc/api/appendix/migration.md`、`environment/_historical.py` | 保留并标识旧接口的历史和受限兼容意义 | 不以旧文本作为新标准API；v2.1.0及更早冻结文档不改写 |
| 本版 `planning/pre-stage3-environment-refactor.md`、`maintenance/recovery.md`、续作与验收门记录 | 保留规划、来源提交和未完成门，按检查点追加，而非改写历史复审 | 本清单不是最终报告；最终源码、验证、窗口释放和Sol决定仍需补充 |

两份保护untracked及GeoPhys、Menagerie pin须继续保持原状。不得修改旧raw、历史manifest、旧review或阶段编排来使当前门看起来通过。
