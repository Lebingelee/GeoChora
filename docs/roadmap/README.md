# Post-v1.1.0 Phase II Roadmap

更新于 2026-10-18。v1.1.0 已发布，工程整合完成；本页不重开 Phase 2.0 implementation。
[Release](../releases/v1.1/README.md)和[唯一能力矩阵](../module/task_env/capability_matrix_v1_1_0_candidate.json)
定义当前实现/证据；下列研究和工程方向不构成已实现或已获资格的能力。

## 当前基线

Current IMPLEMENTED：selected task authoring、scalar GeoPhys/MuJoCo route、generic batch/learner/
renderer contracts、既有 recorder/trajectory APIs。TESTED_BOUNDED：具名 PickCube/NutAssembly
CPU/100 Hz/seed 和 Pendulum smoke。没有新增 formal Qualification，P1.7 visuomotor 仍 deferred。
历史 decisions 与 failed/diagnostic receipts 保留在冻结 refs，不将工程 closure 写成原 Phase I 蓝图全完成。

## 近期研究

首个候选是 **LIBERO + Panda + MuJoCo**；先对比一条 native benchmark workflow 与对应 canonical
TaskEnv route，形成有界 Oracle、质量报告与 training-ready data。其他候选包括 RoboCasa、RoboTwin、
RoboDojo，未作接入/支持承诺。选择具体任务/benchmark revision 后才冻结实验配方与样本。

```text
External Benchmark -> Canonical TaskArtifact -> TaskEnv Execution
                   -> Trajectory / Evidence Validation -> Task Harness
                   -> Future PhysPi Integration
```

研究清单与预期交付：

| 议题 | 需要建立的 Evidence/决策 |
| --- | --- |
| 环境隔离 | native benchmark 独立依赖环境、Python/library revisions、许可证与资源边界；避免污染 Core 环境 |
| Task/semantic mapping | scene/asset IDs、reset distributions、success/failure/reward、timebase、native 与 canonical 语义差异 |
| provider/runtime adaptation | 复用当前 owner 与 public API；列出缺口，禁止 private solver shortcuts |
| observation/action/controller | shape/dtype/frame/unit、normalization、action hold、target/applied layer 与控制频率映射 |
| 双向 trajectory conversion | native → canonical 与 canonical → native，版本化 schema、T/T+1、roundtrip 与信息损失报告 |
| provenance | benchmark source/version、task/assets/data/checkpoint hashes、Core/provider/config/seed、转换 lineage |
| validation/oracles | reset realization、semantic equivalence、bounded replay/execution、paired samples、predeclared tolerance |
| training-ready data | coverage、invalid transitions、terminal correctness、quality/safety、train/eval split、loader compatibility 报告 |

优先 analytical/Artifact/独立 semantic Oracle；native benchmark 是对照，不天然为唯一 ground truth。
不要用视觉相似、import、一次 demo 或数据格式转换成功证明行为等价。

## 计划工程

在上述对照与 Human review 后，形成 bounded Task Harness：编排任务准入、execution/trajectory
Oracle、质量报告和训练数据产出。Task Harness 拥有任务执行/验证工作流；Asset Harness 拥有资产
来源、解析/转换和一致性；两者不能合成新的 task/runtime owner。先复用 TaskEnv 的 runtime、
controller、recorders、factories、provider abstractions 和 Evidence contracts。

完整 Policy Harness 延后；通用 Validator、通用 environment-policy Runner 和更广 provider/renderer
资格仍按实际需求与独立 Evidence 分别推进。学习进展报告 software portability 与 task outcome，
不把一次 update 当收敛。新增 task 要 Stage-1 randomized feasibility、新 frozen version 与 Human Judge。
本次文档工作不实现 benchmark adapters、Harness 或 RSI。

## 长期方向

PhysPi 拥有 Agent orchestration、memory、experience、Skill evolution，通过 GeoChora 公共 API
消费 Evidence。自动 Core patch/自治 RSI 不是当前 Core 能力。更多 simulator/render providers、UI、
OpenUSD interchange、real → sim → policy → real 与真实机器人部署均需后续设计、依赖准入及资格。
软体、手机视频数字孪生、3DGS、大规模 VLA/WAM 不作为当前已支持目标。

## 历史与后续 gate

[原 Phase I follow-ups](https://github.com/Lebingelee/GeoChora/blob/v1.1.0/docs/roadmap/phase1_followups.md)
和[原 Phase II 计划](https://github.com/Lebingelee/GeoChora/blob/v1.1.0/docs/roadmap/phase2_plan.md)
用于历史 rationale；本页为当前方向唯一入口。每次新工程提案先通过 owner/API/implementation/
callers/tests/limitation/extendability 的复用 gate，随后冻结边界和 Oracle，再执行最小证据路线，
最后由维护者决定是否 promote。文档采纳不产生 capability admission 或正式 qualification。


<a id="phase-ii-01-candidate-handoff"></a>

## Phase II 有界基线冻结与 Phase II-01 候选交接

2026-10-23，维护者已接受 [Phase II 有界工程范围](../maintenance/phase_ii_scope_freeze_20261023/maintainer_scope_decision.yaml)，
当前入口仍为 [05](../module/task_env/goal/Phase_II/05_Architecture_Review_and_Execution_Order.md)。
`v2.0.0` 是 Phase II 预期冻结版本，尚须独立 Release Gate；`v2.0.1` 仅为后续 Phase II-01 规划目标。
以下六项是继承既有实现的候选主题，不是最终 Goal 数量、实施切片、DAG、开发承诺或本轮授权；不新建下一阶段 Goal 文件。

| 候选主题 | 后续需另定的范围 | 现有基础/owner 定位 |
| --- | --- | --- |
| Logical Robot Assembly | 多 Entity 成员关系、递归嵌套、身份/引用；不得回写旧 Scene mapping/hash | `task_env/artifacts/contracts.py` 与 [A 契约](../module/task_env/goal/Phase_II/01_Phase_A_Core_Object_Model.md)；版本化扩展须先核对实际 owner |
| Composite Control Profiles | 整机快捷/子组件独立模式、局部 override、唯一执行器 writer；不假定已有通用仲裁 | `task_env/controllers/canonical/`、`task_env/runtime/sessions/control.py` 与 [C02](../module/task_env/goal/Phase_II/C_Development_Record.md#c02a) |
| Physical Attachment | 按维护者指定，将 Isaac Sim Robot Assembler 的 Mount Frame、Fixed Joint、Articulation Root、Collision Filtering 作为待研究参考；受限真实装配须另行验证 | 既有 Scene/source 与 `task_env/assembly/` / RuntimeSession materialization；不新建 solver/Runtime |
| Dynamic Camera Consumer Integration | 将动态 RGB/Depth/Mask 及同 boundary capture identity 接入 policy observation/TransitionRecorder | `task_env/observations/`、`task_env/render/camera/`、`task_env/recorders/`；[D consumer 边界](../module/task_env/goal/Phase_II/D_Development_Record.md#consumer-边界与未准入范围) |
| GeoPhys Native-rate Feedback Contract | 在现有 Provider observation owner 定义高频 value/phase/freshness/invalidations/cadence，再由 Core 绑定 episode/reset | `GeoPhys/src/control/robot_arm_observation.py`、`task_env/runtime/sessions/`；[C05c 诊断例外](../module/task_env/goal/Phase_II/C_Development_Record.md#c05c) |
| Compatibility / Regression Governance | 历史 H5 原件恢复或 reader retirement 的独立决定、当前 pin 跨场景回归与受限兼容 | 三 recorder reader owners、[B04a](../module/task_env/goal/Phase_II/B_Development_Record.md#b04a)、[Evidence 索引](../maintenance/phase_ii_scope_freeze_20261023/evidence_index.json) |

Robot Assembly 应优先考虑独立版本化 Contract 与现有 Materialization owner 扩展；不得自行改变已冻结 Scene v1/v2/v3 mapping/hash。
这些候选不回写为 Phase II 已接受范围的强制阻塞，也不扩大现有 Provider Capability 或授予新 Qualification。
