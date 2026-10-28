# GeoChora 所有权与变更边界

Canonical repository：[Lebingelee/GeoChora](https://github.com/Lebingelee/GeoChora)。
当前发布 v1.1.0；日常集成分支为 `develop`。源码、真实调用者与可复现 Evidence
决定当前行为；canonical contract 描述规范，历史计划不能建立当前能力。

2026-10-23 的 [Phase II Maintainer Scope Decision](../maintenance/phase_ii_scope_freeze_20261023/maintainer_scope_decision.yaml) 已接受 20 父 Goal/33 切片/P00/P99 的声明交集及明确延期、诊断例外。现有 owners 与依赖方向不变；后续候选仅在 Roadmap 登记，工程 freeze 不授权新阶段实现、main/tag/Release 或 Qualification。

## 模块与公共 API owner

| 范围 | Canonical owner | 消费方式 |
| --- | --- | --- |
| 公共 task/environment facade、registries | `task_env/__init__.py`、`task_env/registry.py` | `make_env` 等 public API；注册不是资格证明 |
| scalar/task semantics、config、reset/done | `task_env/environment/` | task definition、lifecycle、metadata 与 snapshot contracts |
| selected task 配方、谓词、expert | `task_env/tasks/pick_cube/`、`task_env/tasks/nut_assembly/` | `make_env` 具名 UID；不复制候选任务层级 |
| runtime/admission/state mapping | `task_env/runtime/`、`task_env/artifacts/` | 公共 provider API；不泄漏 solver storage |
| controller/planner | `task_env/controllers/`、`task_env/planners/` | action → canonical target；task solution 拥有 stage |
| batch/parallel | `task_env/vectorization/`、`task_env/runtime/` | 显式 homogeneous registration；不 fallback 为多个 scalar |
| trajectory 与数据 | `task_env/recorders/`、`task_env/trajectory/` | 既有 schema、reader/writer、版本化转换 |
| learner 接入 | `task_env/alg/` | 复用现有 SB3/RSL/算法组件；不复制算法实现 |
| camera/presentation | `task_env/observations/`、`task_env/render/` | 独立 renderer admission；UI 消费 frame metadata |
| 可复用资产 | `asset/` | reference/hash；Menagerie 是外部依赖 |
| solver/kernel/原生 renderer | GeoPhys 等 provider 项目 | provider 自有公共边界后的实现 |
| Agent 编排、记忆、经验、Skill 演进 | 外部 PhysPi | 单向消费 GeoChora API/Evidence |
| 仓库/模块操作与治理 Skill | `.agents/skills/`，现有 Evidence Skill 在 `task_env/.agents/skills/` | 描述当前能力；不承担 runtime 或 PhysPi 自治实现 |

Task-local defect 留在 Task Artifact；跨任务 contract defect 归 Core；provider defect 归
provider/adapter；Agent retry/经验问题归 PhysPi。物理目录位置不转移所有权。

## 复用 gate 与跨模块变更

实现前先确认 canonical owner，检查 public API，搜索既有实现，追踪 production callers，
查看 tests，复现或建立 limitation，再评估修复/扩展。提案分类为 `FIX_EXISTING`、
`EXTEND_EXISTING`、`COMPOSE_EXISTING` 或 `NEW_IMPLEMENTATION`；最后一类必须解释既有 owner
为何无法支持需求。不得重复 Runtime、Recorder、Controller、task factory、provider abstraction
或 Skill，不得以私有 provider 访问补缺口。跨模块修改须同时审查调用方向、生命周期状态 owner、
API、schema、失败路径和相应 Evidence，必要时更新 canonical 文档及 module Skill。

## Agent 与 Skill 职责

仓库治理 Skill 定义变更约束，module Skill 提供当前操作路线；Experiment/Evidence Skill
管理任务/实验/事实分离。Skill 不是 API 的替代实现，也不能根据源码变动自动认定其更新正确。
[AGENTS.md](../../AGENTS.md)记录自然语言 activation convention；API/qualification 敏感更新
保留 Human review。PhysPi 经验提炼和自主 Skill evolution 不在 Core 内实现。

2026-10-25维护者明确的[阶段分支与Sol/Luna工作流](../../AGENTS.md#phase-branch-workflow)优先于旧规划/Prompt中的冲突流程：先按phase/stage规划少量分支，多个sub-stage/Goal复用同一分支；每个有界产出关联本地提交。Sol按阶段执行表发单slice包，Luna执行/验证/提交并交回报告，Sol复核后再发下一包。恢复或独立方案比较/整合需要时再评估额外branch/worktree，讨论本身不触发新建。单writer、ignored原始Evidence、独立范围/Qualification及发布授权边界保持不变。

## 能力与发布治理

精确状态定义复用[唯一 v1.1 矩阵](../module/task_env/capability_matrix_v1_1_0_candidate.json)。
`IMPLEMENTED`、`TESTED_BOUNDED`、`QUALIFIED`、`PLANNED`、`RETIRED`、`NOT_IMPLEMENTED`
不可混用。缺少 provenance 的历史结果不得追补虚构 identity 或升级为 current qualification。
事实由 Evaluator 输出，approve/reject 由独立 Judge 输出。

冻结 v1.0.0/v1.1.0 tag、历史 Judge decisions 和原始 Evidence 不可改写。
生成 workspace 默认不提交；清理前必须保护本地 bytes、hash、decisions、relocation mappings
以及被提升知识引用的 Evidence。本次文档 topic branch 在维护者审阅批准前不 push/merge；
后续集成须 fetch/check 后正常进入 develop，再按批准流程进入 main，绝不改 frozen refs。
