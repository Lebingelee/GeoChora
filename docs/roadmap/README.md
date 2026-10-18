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
