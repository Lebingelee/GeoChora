# RuntimeSession 路线统一与 LIBERO 诊断交接

日期：2026-10-30（Asia/Shanghai）。这是临时诊断对话的交接记录，保存已确认事实、维护者决定与待实施计划；不是实现完成、native授权或资格声明。新窗口先读本文并核对实时HEAD/写入者，再继续讨论；不要自动执行历史prompt。

## 1. 本窗口结束时的仓库状态

| checkout | branch | 观察到的HEAD | 文档写入前状态 |
| --- | --- | --- | --- |
| 主checkout | develop-full | `875954f101033568a3e1f5e439ed86be3cf29cc2` | M .agents/skills/geochora-task-env/SKILL.md;  M docs/module/task_env/README.md;  M docs/module/task_env/goal/Phase_II_01/07_Execution_Order_and_Acceptance.md;  M docs/module/task_env/goal/Phase_II_01/README.md;  M docs/module/task_env/public-api.md |
| camera工作树 | codex/phase-ii-01-camera | `b34d88a668d50e5a59f93e9613a110e6face3e2c` | clean |

本窗口没有修改Core/benchmark实现、运行pytest/native、创建或调用subagent、切换分支、merge/push或删除实现文件。修改范围只有项目Skill规则；交接时这些Skill变更已经出现在主checkout最新提交中（`875954f101033568a3e1f5e439ed86be3cf29cc2`，`docs: record diagnostic workflow and runtime migration direction`），不应重复覆盖或回退该提交。本交接文档及ignored快照为本次新增文件。

机器本地工作树绝对路径、Skill字节副本/hash与观察状态记录在 `workspace/maintenance/runtime_route_diagnostic_handoff_20261030_001/snapshot.json`。该目录还保存两份Skill副本与SHA-256清单；存在未提交Skill差异时另存patch。该快照只用于恢复上下文，不能据它reset实时checkout。

## 2. 维护者已确定的方向

1. 任务执行统一为 `SelectedReferenceEnv → RuntimeSession → provider adapter`；新benchmark不能另走BaseTaskEnv的GeoPhys专用执行分支。
2. `bench_deploy/<benchmark>/`可以新增benchmark专用控制器；其输出消费Core控制/状态合同。物理执行、reset/step/fault/close、记录仍由现Core/adapter负责，不建第二Runtime/Recorder。
3. 整体迁移BaseTaskEnv调用方。最终保留的`BaseTaskEnv`导入名直接指向`SelectedReferenceEnv`，接口与后者一致，不保留第二套reset/step或静默回退旧路径。
4. BaseTaskEnv名称在2.x保留，弃用/删除放到3.0.0规划。先迁调用方，不能先改别名导致任务失效。
5. 常规子阶段仍以三次attempt为限；维护者明确指定的诊断工作，attempt不设固定次数上限。保留常规与诊断历史，各run分别记录；无限次数不代表无限时间、资源或native授权。
6. 非常不鼓励反复开启诊断对话：会消耗用户精力和额度。每次诊断attempt必须产出具体修复或可验证增量，不能循环交同一份调查，也不能要求用户为普通修复不断开新窗口。

规则已写入[项目Skill](../../.agents/skills/geochora/SKILL.md)的“Runtime route consolidation direction”和[goal orchestration](../../.agents/skills/geochora/references/goal-orchestration.md#post-limit-diagnostic-conversation)。Skill quick validator与git diff --check已通过；没有通过这些检查声称实现完成。

## 3. 已确认：两条旧入口实际并列，并无BaseTaskEnv→SelectedReferenceEnv委托

当前实现：

```text
TaskEnvironmentComponent
├─ SelectedReferenceEnv → RuntimeSession → provider adapters
└─ BaseTaskEnv → bootstrap_task_runtime → GeoPhys专用构造
```

`BaseTaskEnv`和`SelectedReferenceEnv`是同一抽象组件下的并列类，不是前者自动连接后者。`task_env/registry.py::make_env`对具备`from_reference_config`的类走selected构造；普通BaseTaskEnv任务走另一配置路径。

关键owner：

- `task_env/tasks/reference_env.py::SelectedReferenceEnv/ReferenceTaskBinding`：现selected生命周期/内部配方seam。
- `task_env/environment/env.py::BaseTaskEnv._build_runtime_with_rollback`：直接调用旧bootstrap。
- `task_env/runtime/bootstrap.py::bootstrap_task_runtime`：直接构造GeoPhys。
- `task_env/runtime/sessions/geophys.py::_GeoPhysSession`：**统一RuntimeSession路线内部仍复用该bootstrap**。

因此错误是R07c候选绕过统一入口，不能把所有GeoPhys bootstrap/helper都当成无用代码删除。provider内部仍使用的部分可保留；待删除的是第二条对外任务执行分支及其无用专用接线。

旧BaseTaskEnv调用方至少包括`EmptyTaskEnv`、`PendulumEnv`、`TwoWheelBalanceEnv`和相关渲染/并行/配置消费者。selected入口当前有Panda/position/tendon的具体假设，迁移前需做真实能力与调用方盘点，不是机械改继承就完成。

## 4. 已确认：develop-full的Isaac Core路线正确

实际F04 worker及源码链：

```text
F04 worker
 → make_env("panda-position-servo-candidate-v1", versioned_input=...)
 → PositionCandidateEnv（继承SelectedReferenceEnv）
 → build_versioned_position_candidate
 → SelectedReferenceEnv.from_position_candidate
 → RuntimeSession materialize
 → UsdCoreRuntimeSession + Isaac native IO
```

核对位置：

- `task_env/tasks/position_candidate/__init__.py::PositionCandidateEnv`
- `task_env/tasks/position_candidate/builder.py::F04PositionCandidateInputV1/build_versioned_position_candidate`
- `task_env/runtime/sessions/api.py::materialize`的USD/Isaac分支
- `task_env/runtime/sessions/native_io.py`与`isaac_native_io.py`
- 实际保存worker：`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f04_004/evidence/f04_native_core_worker.py::run_family`，其调用make_env，未经过BaseTaskEnv。

这证明F04 Core任务路由；不能据此宣布任意Isaac source/provider资格，亦不意味着F01独立安装/原生诊断脚本必须经过任务Env。后续统一改动要保护F线已有接线和证据，不在camera旧版本上覆盖F线增量。

## 5. LIBERO资产、位姿和历史恢复：本窗口纠正的结论

### 5.1 上游有资产，也有环境构造与位姿采样代码

LIBERO物体/fixture资产、robosuite机器人、BDDL任务声明与Python构造代码共同生成场景。上游reset将动态物体位置写入free-joint qpos，将固定根fixture位置写入model.body_pos/body_quat；资产模板本身不必保存最终世界位姿。

当前camera单pilot来源manifest含103项payload，其中89项资产，包含XML/mesh/texture/BDDL/.pruned_init，**不包含demo HDF5**。这只说明本轮交付范围，不能说明上游没有完整场景信息或全机没有dataset。

### 5.2 上游demo生成流程保存model XML

锁定LIBERO revision `8f1084e3132a39270c3a13ebe37270a43ece2a01`：

- [collect_demonstration.py](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/scripts/collect_demonstration.py#L154)：demo保存`model_file` XML及states。
- [create_dataset.py](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/scripts/create_dataset.py#L120)：先恢复对应XML，再恢复state；输出仍保存model_file和init_state。

所以“flat state不含fixture pose”不能泛化为“LIBERO没有精确场景信息”。对应demo XML值得继续核查；但50条.pruned_init rows与demo的对应关系尚未核实，不能默认一一对应。本窗口未下载demo HDF5。

### 5.3 一般评估不要求找回某次历史fixture realization

[官方metric.py](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/lifelong/metric.py#L94)按`env.reset()`→`env.set_init_state(指定row)`→执行；[env_wrapper.py](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/env_wrapper.py#L129)载入flat state并forward。

**正常部署/评估语义与精确重放某次demo应分别验收。** 把“恢复每条init row当年关联的fixture精确位姿”作为一般部署的强制前置，是此前额外加上的门。不能据此反复要求资产团队补一个正常评估未要求的历史sample。应先按上游reset+init-state语义定义部署；若另做历史demo重放，再绑定对应model XML与state。

这个结论是当前诊断修正，尚未改写camera旧prompt/报告。旧冻结证据保持；后续工作包应明确替代了哪些要求，不能偷偷把未过的旧合同记为PASS。

## 6. R07c已有成果与错误接线的处置

常规pilot attempts001/002/003已返回；attempt003最终为`R07C_PILOT_PARTIAL_G1_G2_BLOCKED_PENDING_SOL_REVIEW`，Sol复核维持partial。18/22不变；未产生此pilot native证据，R07五任务/P99/Qualification未关闭。

| 内容 | 后续处置 |
| --- | --- |
| 来源manifest、install/verify、notice/provenance | 保留 |
| 修复后5个动态free roots、fixture内部关节、source组合 | 保留，继续核对上游规则 |
| 固定格式.pruned_init安全decoder与原rows/hash | 保留，原生compiled layout另验 |
| 成本reader独立Git/缺项拒绝门 | 保留，未知usage/费用仍null，旧INVALID不升级 |
| `bench_deploy/libero/core_candidate.py`的BaseTaskEnv继承/GeoPhys接线 | 替换为SelectedReferenceEnv配方；迁后删除错误活跃入口 |
| `task.py::create_action_adapter`旧hook | 改接统一Core controller合同 |
| `task_env/controllers/mounted_panda_mixed.py`中的LIBERO专有策略 | 移入benchmark controller；通用控制合同/可复用算法留Core |
| `core_candidate_worker.py`读取Env私有状态 | 改用公开lifecycle/outcome/recording接口 |
| 只验证旧GeoPhys fake路线的测试 | 换成真实选定RuntimeSession路线，保留故障/收尾覆盖 |
| 冻结历史报告、失败记录、Git提交、raw H5 | 保留，不删除或改写 |

当前一般MuJoCo控制入口仍带position+tendon假设；LIBERO需7 arm torque＋2 signed finger position。reset旧实现会清qvel，contact公开查询/coverage/freshness未接通。这些是Core复用/adapter接线缺口，不能全部归给bench资产，也不应在benchmark内另写solver循环补偿。

## 7. 建议的诊断实施批次（暂定，不是已派发prompt）

| 批次 | 工作与出口 |
| --- | --- |
| D01 修正LIBERO路线 | 在现SelectedReferenceEnv/RuntimeSession owner内补所需扩展，接benchmark controller/reset/semantics；移除旧candidate执行接线。完整同路线synthetic叶S1与fault/Recorder链通过，不再用GeoPhys fake证明MuJoCo支持 |
| D02 迁移旧BaseTaskEnv调用方 | 覆盖Empty/Pendulum/TwoWheelBalance及观察/渲染/并行消费者；selected消除无关Panda专属假设，每任务提供正确配方；保留数值/生命周期语义 |
| D03 兼容名收敛与删除 | 调用方迁完后，让BaseTaskEnv保留导入名直接alias SelectedReferenceEnv；清理重复reset/step、旧构造分支/文档与无用测试入口；保留provider仍用helper |
| D04 集成验收 | 按受影响的已支持交集验证MuJoCo/GeoPhys/Isaac，核公开路径、state/control/outcome、同H5和收尾；不是自动要求所有任务×所有provider都支持 |

能合并的批次不为凑次数拆开。D01与D02都可能修改SelectedReferenceEnv/RuntimeSession，实施前须明确版本集成和单writer；不从camera旧文件覆盖develop-full的F线代码。不要把两个checkpoint强行reset到同HEAD或未经授权merge。

每个执行窗口需冻结实际HEAD/输入、允许改动、动作/状态/失败门、时间和资源预算；先same-route S1，再按明确授权做native。旧attempt003 native条件合同已结束，不能直接复用其“额度未消耗”启动新运行。

## 8. 新窗口的第一步与未完成事项

先做：

1. 读取本文、当前项目Skill、两工作树实时HEAD/status；确认F线/原线程没有正在持有同文件写入窗口。
2. 确认统一路线的最小Core扩展与全体BaseTaskEnv调用方迁移矩阵；落实控制、reset、观测/渲染/并行、错误和Recorder方法，不再仅写高层执行顺序。
3. 按本窗口查到的上游reset/evaluation代码修正LIBERO验收合同；精确demo重放是否另做列清楚，不默认新增门。
4. 选择一个可交付诊断实施窗口，明确冻结输入和资源；届时再准备完整prompt，由维护者按原约定转发。不要自动给Luna发送消息。

未完成：没有实际统一Selected能力、没有迁移BaseTaskEnv、没有改别名/删除旧代码、没有实现MuJoCo mixed/reset/contact、没有下载/检查demo HDF5、没有新native或新诊断attempt。

## 9. 证据索引与简短续接说明

本机ignored维护根：`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/`。

- `r07c_pilot_001/`、`r07c_pilot_002/`、`r07c_pilot_003/`：常规执行报告与原件。
- `sol_review_r07c_pilot_001/`至`003/`：原Sol复核；fixture缺件结论须结合本文修正其适用范围。
- `r07b_pilot_001_install/final_001/`：只读103项来源安装。
- `f04_004/evidence/f04_native_core_worker.py`：实际Isaac构造路径，保留证据只读。
- camera规划：`docs/module/task_env/goal/Phase_II_01/07_Execution_Order_and_Acceptance.md`、`09_R07_Benchmark_Deployment_and_Agent_Cost.md`；尚未合入本窗口完整路线修正。

可给新窗口的首条消息：

> 请先读取 docs/maintenance/20261030_runtime_route_diagnostic_handoff.md 与当前项目Skill，核对develop-full和camera实时状态，然后继续讨论统一SelectedReferenceEnv→RuntimeSession、BaseTaskEnv迁移及LIBERO错误接线清理的实施方案。保留本诊断交接的事实与维护者决定，不自动运行旧attempt003工作包，不动其他writer的F/Isaac代码。

### 保存期间的并发状态观察

本交接开始观察时主checkout为clean；保存期间其他开发窗口又产生以下未提交文档变化，本窗口没有编辑、暂存或覆盖它们。恢复时以实时status为准，不因初始快照clean就认定写入窗口空闲：

```text
M .agents/skills/geochora-task-env/SKILL.md
 M docs/module/task_env/README.md
 M docs/module/task_env/goal/Phase_II_01/07_Execution_Order_and_Acceptance.md
 M docs/module/task_env/goal/Phase_II_01/README.md
 M docs/module/task_env/public-api.md
```
