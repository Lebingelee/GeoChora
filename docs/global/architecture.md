# GeoChora 系统架构

基线：2026-10-18 已发布的 v1.1.0，source `7ed9e78a60d407fa1150c99209e06c70bfa0ed87`。
当前能力取自[发布记录](../releases/v1.1/README.md)及其原始矩阵；架构方向本身不构成实现或资格证明。

2026-10-23，维护者已接受并冻结 [Phase II 声明交集的有界工程范围](../maintenance/phase_ii_scope_freeze_20261023/maintainer_scope_decision.yaml)，源码基线 `90071ace…`。这是开发基线的 Scoped Engineering Acceptance；已发布 v1.1.0 的资格矩阵不变，v2.0.0 尚须独立 Release Gate，不代表所有设计广度或新 Formal Qualification。

## 定位与依赖方向

GeoChora 是面向具身任务的多仿真器、多渲染器 API 与工具中枢。
人、脚本、CI 或 Agent 可以独立使用 Core；PhysPi 是外部消费方，负责 Agent/LLM
编排、工具选择、重试、记忆、经验及 Skill 演进。Geochora 不依赖 PhysPi 内部实现。

```text
PhysPi / 人 / 脚本 -> GeoChora 公共 API -> provider 公共/runtime-facing API
                                            ├─ physics/runtime
                                            └─ renderer
```

`task_env/` 是 Core 唯一 canonical 实现。GeoPhys 是默认 physics/runtime provider，
通过 Gitlink 引用，不依赖 Geochora 内部模块。不得建立第二份 TaskEnv、UniversalSolver
或统一 provider storage ABI。具体 owner 见[ownership](ownership.md)。

## Core 与 provider

Core 拥有任务构造、配置与 admission、reset/step、语义评估、controller/action 与
observation contract、录制、数据转换、learner 接入和 presentation contract。
Provider 拥有物理积分、原生状态存储、kernel、cache、数值求解和渲染实现。
Core/task/planner/recorder 消费命名 canonical state 或公开 snapshot，不读取私有 solver/renderer
状态来补偿缺失能力。任务专属 stage、成功条件和资产配方留在任务模块或 Task Artifact。

当前 scalar selected references 为 PickCube 和 NutAssembly，具名 GeoPhys/MuJoCo CPU
执行交集有 bounded acceptance。SAPIEN/Genesis session adapter 的存在不授予 selected-task
支持。一般 `BaseTaskEnv` 与 selected-reference adapter 是不同构造分支，不能互换配置。
[模块入口](../module/task_env/README.md)说明当前可用流程及精确限制。

## Physics 与 Renderer

Physics 决定状态演化；Renderer 产生 camera observations 或 UI presentation frames，
两者独立准入。Camera 的几何、RGB/depth metadata 不等同于交互式 UI；render 配置不改变
reset、reward、done 或物理状态。当前 native RGB smoke 只覆盖 Pendulum × GeoPhys CPU ×
scalar/merged_scene batch × rasterizer。Flora registry/fake-endpoint tests 不证明 native Flora，
也不证明 manipulation × Flora 或一般 Physics × Renderer interoperability。

## Assets

`asset/` 拥有可复用资产解析；Menagerie 保持外部 Gitlink。任务局部小型 XML/URDF/geometry
可以随 Task Artifact 保存；复杂资产记录稳定 reference/version/hash。
Evidence 记录使用了什么资产，不取得资产所有权；资产格式也不定义 Core scene API。

## Task Artifact、Experiment、Evidence 与 Judge

```text
需求 -> task candidate -> config/asset/admission/reset/controller/observation checks
     -> expert 与 randomized feasibility -> Human Judge -> frozen Task Artifact
     -> 多个 Experiment -> 采集/数据验证/适用的学习与闭环评估
     -> evaluation facts -> 独立 Judge decision -> canonical Evidence package
```

这是受治理的工作流 contract；不是一个已完成并资格化的统一 Validator/Experiment Engine。
校验当前分散在配置、资产、admission、controller 和 observation 路径；通用
`Runner(env, policy).run()` 仍非当前公共 API。冻结语义和评估分布不得在实验中静默改变。
详见[Task Artifact contract](../module/task_env/task-artifact.md)。
Evidence 只记录发生的事实与 provenance，不能自动批准任务、更新 Core 或产生可信 Skill。

## 实现与未来

v1.1.0 完成了 selected task authoring、工作流整合及 Go2/static-template retirement，
保留 generic RL、Batch/Device/Vectorization 和 Renderer contracts；没有新增正式 qualification。
历史 v1.0 bounded decisions 不转移到新 source。统一 Validator、通用 rollout Runner、完整
Policy Harness、real-robot deployment、OpenUSD canonical interchange 和 RSI 均不能作为当前能力。
[post-v1.1 roadmap](../roadmap/README.md)优先规划 benchmark 对照、Oracle 验证和训练可用数据；
Task Harness 与 Asset Harness 分属不同职责。OpenUSD、real → sim → policy → real 属长期方向。
