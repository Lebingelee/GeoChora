# Geochora 仓库所有权与边界

> 状态：canonical 所有权 contract，v0.3
> 日期：2026-10-04

## 1. 仓库意图

本仓库是 Geochora 的 canonical owner。Geochora 是可复用的多仿真器、多渲染器具身任务 API 与工具中枢。

Canonical repository 为 [Lebingelee/GeoChora](https://github.com/Lebingelee/GeoChora)，canonical branch 为 `main`。P1.0-A 审查的起始 HEAD 为 `9b4a55e8f944daa45a5d4d811ba6a02af4c1cfdc`；本地 checkout 的工作分支名不定义 canonical branch。

历史任务环境代码和文档可能起源于其他项目的分支。它们只构成迁移背景，不再具有持续的架构权威。Geochora Core 或 task_env 不得存在两份同时主动维护的 canonical 副本。

PhysPi 是独立的、基于 pi 的 Agent 项目，也是 Geochora 的预期消费方。Geochora 以后可以检出或引用在 PhysPi 项目路径下，但目录位置不会合并所有权：PhysPi 负责 Agent 行为和经验；Geochora 负责可执行的仿真、渲染、任务、Experiment 与 Evidence contract。

## 2. 目标仓库结构

~~~text
Geochora/
|-- task_env/              # Geochora Core 实现
|-- asset/                 # 可复用资产导入/解析接口
|   +-- external/mujoco_menagerie/  # 外部资产链接/子模块
|-- GeoPhys/               # 开发用 provider 链接/子模块
|-- docs/                  # canonical 与 module 文档
|-- .agents/skills/        # 仓库工作流与治理 Skills
+-- workspace/             # 生成的 Task Artifact/Experiment；不提交
~~~

外部 provider 始终是外部依赖。其源码通过链接、安装或解析获得；不能仅为了让公开审查分支自包含，就把源码 vendoring 到 Geochora。

## 3. Canonical 所有权

### 3.1 Geochora Core 与 task_env

Geochora 负责：

- 公共 environment 与 task API；
- task/runtime 生命周期；
- simulator 和 renderer provider 边界；
- provider 发现、capability reporting 与 admission；
- observation、action、controller 和 planner contract；
- recorder、replay、runner 与 environment-policy execution；
- learner 集成及训练/评估编排；
- Task Artifact、Experiment 与 Experiment Evidence contract；
- provider-neutral 的 render 与 UI presentation contract；
- Core 和 provider 的资格验证与回归。

task_env 中的参考任务作为资格验证路线维护。任务局部实现属于对应 Task Artifact，除非它已证明可跨任务复用，并经过明确流程提升到 Core。

### 3.2 PhysPi

PhysPi 负责：

- Agent 与 LLM 编排；
- prompt 和模型策略；
- 工具选择、顺序安排、恢复与重试行为；
- 持久化经验、记忆、检索与知识提炼；
- 可复用 Agent Skills 及其验证/提升流程；
- 对 Geochora Evidence 进行推理。

Geochora 为 PhysPi 暴露稳定 API、工具、capability metadata 和 Evidence。Geochora 不得导入 PhysPi 内部实现，也不得要求特定 PhysPi 模型、memory store 或 Skill 格式。

预期依赖方向为：

~~~text
PhysPi -> Geochora 公共 API -> provider 公共 API
~~~

### 3.3 Assets 与 OpenUSD

Geochora 负责可复用的 asset resolution interface。简单资产可以属于 Task Artifact；可复用的机器人和物体资源应通过该接口解析。

OpenUSD 以后可能用于 scene interchange、composition 或 visualization。在设计被接受之前，它只是候选集成方案，不是 canonical 仓库格式或必选依赖。

### 3.4 Providers

GeoPhys 是当前/default implementation physics/runtime provider，并提供默认 rendering 路径。Qualification 必须绑定到有 Evidence 的 provider × backend/profile × task × lifecycle intersection，不能对整个 provider 作无范围的资格声明。

Go2 CUDA/static/RSL 是历史 Evidence 最强的具名 regression route；其 current-HEAD qualification 仍需在 P1.0 baseline smoke 中重新确认，不能外推到 PickCube、NutAssembly 或其他 GeoPhys 路线。

Phase-I primary target 为 GeoPhys/MuJoCo，boundary-validation target 为 SAPIEN/Genesis。这些目标不构成实现或资格证明；MuJoCo 当前独立 oracle/probe 也不等于统一 production provider。其他 simulator/render provider（包括 Flora）须经明确 adapter、capability declaration 和具名 acceptance route 接入。Physics 与 render provider 始终是不同边界。

Core 和 task 代码可以依赖 provider 公共 API，但不得依赖 provider 私有内部实现、可变 singleton state 或未声明的 backend 特定行为。

Provider 仓库和大型外部资产集应保持为链接、submodule 或安装依赖。Geochora 公开分支应发布引用与安装 contract，而不是复制其源码。

### 3.5 Rendering 与 UI

Geochora 负责 render frame、camera、viewport、overlay、interaction event 和 presentation metadata 的 provider-neutral 边界。Render backend 和 UI client 分别实现或消费这一边界。

任何特定 renderer、桌面 toolkit、browser stack 或未来 OpenUSD 集成都不拥有 Core presentation contract。

### 3.6 agent_factory 与 learning library

现有算法库可以提供 baseline imitation-learning 或 policy 实现。Geochora 通过明确的 learner/policy 边界集成它们，而不重复实现其算法。

## 4. 变更分类

实施前必须将每项拟议变更分类：

1. Task-local：只属于一个 Task Artifact，不改变共享 contract。
2. PhysPi experience 或 Skill：改变 Agent 选择或组合现有 Geochora 能力的方式。
3. Geochora Core：增加或改变可复用 API、生命周期、schema、provider 边界、UI/render contract 或 Evidence 语义。
4. Provider：在既有边界后方改变 backend 特定的仿真或渲染行为。

不能因为某个 workaround 解决了一个任务，就把它提升到 Core。不能把 Agent 推理或积累的经验编码进 Geochora API。不能通过未记录的 provider 私有访问来弥补 Core capability 缺失。

## 5. Capability 与 Evidence 治理

Capability claim 必须准确标记：

- implemented：代码已存在；
- tested：有测试执行 Evidence；仅有测试代码不构成 tested；
- qualified：通过已声明 acceptance route，并且 Evidence/provenance 足够；
- planned：Phase-I 计划目标，但尚未实现或资格化；
- unsupported/unknown：当前无足够支持或证据；已确认不支持与尚未确认须分别记录；
- aspirational：尚无确定接口的长期目标。

real -> sim -> policy -> real 支持可以按部分路线逐步获得资格验证，但目前不能作为仓库级完整能力声明。

Experiment Evidence 可以推动 PhysPi Skill 更新、新增 regression，或形成受审查的 Core proposal；它不能直接改写 Core 或绕过审查。递归自我改进不是当前 Geochora 的职责。

## 6. 依赖与公开审查规则

针对公开审查仓库：

- 可以发布 Geochora 自有的源码、文档、测试和 Skills；
- GeoPhys、mujoco_menagerie、PhysPi 及其他外部项目保持为引用或链接，除非其自身发布政策明确允许其他方式；
- 生成的 workspace、Experiment、cache、credential 和大型本地产物保持未跟踪；
- README 安装说明必须指出每条已资格化路线需要哪些外部依赖。

## 7. 冲突处理

权威顺序依次为：当前实现与可复现 Evidence、docs/global、module 文档、README 摘要、历史说明。如果打包方式、旧图片或过去的分支历史暗示了不同所有权，在有意修订前以本 contract 为准。
