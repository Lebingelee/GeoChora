# Geochora 系统架构基准

> 状态：canonical 架构基准，v0.2
> 日期：2026-10-01
> 范围：定义其他 Geochora 文档必须遵循的稳定系统级概念、所有权边界和生命周期。

## 1. Geochora 是什么

Geochora 是一个长期演进、与 provider 无关的 API 与工具中枢，面向具身任务构造、多仿真器执行、多渲染器展示、评估和 Evidence 采集。

它的首要目标是可靠性：一套统一的任务与生命周期 contract 应当能够跨仿真器和渲染器 provider 工作，同时不把 provider 内部实现泄漏到任务定义中。人、脚本、CI 和其他 Agent 都可以直接使用 Geochora；PhysPi 是预期的上层 Agent 消费者，但使用 Geochora 并不要求必须存在 PhysPi。

各组成部分可简要定位为：

- PhysPi：基于 pi 的 Agent 与 LLM 编排项目，负责推理、经验、记忆、Skills、工具选择和重试策略。
- Geochora：为具身任务的构造、运行、渲染、记录、评估和资格验证提供稳定的可执行 API 与工具。
- Simulator / solver provider：决定物理世界如何演化。
- Renderer / presentation provider：产生视觉观测和面向 UI 的展示数据。
- Controller / planner / expert route：生成可执行行为或参考轨迹。
- Policy / learner：学习如何根据观测采取动作。
- Task Artifact：声明一个可复现任务。
- Experiment Evidence：记录执行了什么、使用了什么配置，以及得到什么结果。

Geochora 不是 Agent，也不是自治式自我改进系统，更不会替代仿真器、渲染器、控制器、规划器或 learner 的实现。

## 2. Canonical 架构

~~~text
用户需求
        |
        v
PhysPi Agent / 人 / 其他客户端
        |
        | Geochora 公共 API 与工具
        v
Geochora Core
   |-- Task Artifact 加载与验证
   |-- 任务/runtime 生命周期
   |-- observation、action 与 controller contract
   |-- Experiment、记录、回放、评估与 Evidence
   |-- 统一 render 与 UI presentation contract
   |
   +-- physics/runtime provider --> 当前为 GeoPhys；未来包括 MuJoCo、SAPIEN 等
   +-- render provider          --> 当前为 GeoPhys；Flora 等在资格验证后接入
   +-- asset resolver           --> 任务局部和可复用资产库
   +-- planner/controller       --> provider-neutral 集成
   +-- learner/policy           --> agent_factory 或其他已资格化集成
   +-- 可选交换层               --> OpenUSD 候选方案；尚未成为确定依赖
~~~

图片 docs/figures/整体架构.png 展示了更广泛的产品上下文。其中的 Agent 和 Part B 属于 PhysPi 或其他外部消费方，而不属于 Geochora Core。如果旧图片与本文冲突，以本 v0.2 架构基准为准。

## 3. PhysPi 边界

PhysPi 可以利用积累的经验选择 Geochora 工具、组合 Task Artifact、诊断失败、安全重试并解释 Evidence。依赖方向是单向的：

~~~text
PhysPi -> Geochora 公共 API -> 已资格化 provider
~~~

Geochora 不得导入 PhysPi 内部实现，也不得依赖特定的记忆、prompt、模型或 Skill 实现。通过这一边界，较强模型建立的已验证流程可以经由受审查的 PhysPi 经验和稳定的 Geochora 接口，帮助较弱模型达到可比的验收质量。

即使以后将 Geochora 放在 PhysPi 项目路径之下，这种打包位置也不会把 Geochora Core contract 的所有权转移给 PhysPi。

## 4. Geochora Core 能力

Core 负责跨任务复用所需的 contract 和生命周期：

- Task Artifact schema、loader 与 validation；
- 与仿真器无关的任务和 runtime 生命周期；
- provider 准入、发现和 capability reporting；
- observation、action、controller、planner 与 expert-route 接口；
- recorder、replay、runner 与 environment-policy execution；
- learner 集成及训练/评估编排；
- 确定性配置、seed 和 provenance 采集；
- Experiment 与 Experiment Evidence contract；
- render frame、camera、viewport、overlay 和面向 UI 的 presentation contract；
- 支撑公共能力声明的资格验证与回归 Evidence。

provider 特定代码必须留在 adapter 后方。任务可以请求某项 capability，但不得访问 provider 私有的 scene、physics 或 renderer 状态。

## 5. Rendering、UI 与 OpenUSD

Geochora 负责 provider-neutral 的 presentation contract，而不是某个强制的桌面或 Web 应用。Render provider 产生经过资格验证的 frame 和 metadata；UI client 以一致方式消费这些 contract。

OpenUSD 是未来用于 scene interchange、composition 和 visualization 的候选层。它尚未成为已采用的 canonical representation；如果没有独立设计决策和资格验证计划，不得将其变成首个 milestone 的必选依赖。

## 6. Assets

Asset Library 回答“有哪些机器人和物体资源可用”。其中可以包含 URDF、MJCF、XML、mesh、texture、metadata 和 conversion recipe。

简单的任务局部资产可以放在 Task Artifact 内。可复用或复杂资产应通过明确的 asset interface 解析。资产格式不定义 Core scene API。

## 7. Task Artifact

Task Artifact 是对一个任务进行冻结、可复现的声明。它负责任务局部的 scene composition、成功与失败条件、初始化、action/observation 选择、允许的 controller route、评估配置和本地资产。

参考任务是 Core 与 provider 的资格验证载体。它们用于展示 contract 和回归覆盖，不定义完整产品边界。

## 8. Experiment 与 Evidence 生命周期

Canonical 生命周期如下：

~~~text
需求
  -> 构造 Task Artifact
  -> 验证 schema 和请求的 capability
  -> 实例化已资格化 provider
  -> 执行 controller、planner、expert 或 policy route
  -> 记录 observation、action、event、metric 与 provenance
  -> 根据验收标准进行 Judge
  -> 冻结 Experiment Evidence
~~~

Evidence 必须区分 implemented、tested、qualified、planned 和 aspirational。一个参考任务通过，并不能证明某个 provider、机器人、scene format 或真实世界迁移路线已经获得通用支持。

## 9. 受治理的演进，而非当前 RSI

Evidence 经审查后可以沉淀为：

- 改进后的 PhysPi 经验、记忆和 Skills；
- 更清晰的 Task Artifact template；
- 更多 provider 资格验证案例；
- 经过审查的 Geochora API 或实现修改。

这些属于受治理的软件和知识更新。自治式递归自我改进不是当前 Geochora 的目标，Experiment Evidence 本身也绝不授权修改 Core 源码。

因此，图片 docs/figures/改进方案.png 应理解为长期、带审查门槛的反馈闭环，而不是已实现的 RSI 机制。

## 10. Roadmap 优先级

当前优先级：

1. 为多仿真器执行和多渲染器展示建立可靠的公共 contract；
2. 对 GeoPhys 路线和参考任务进行端到端资格验证；
3. 使 Evidence 与 capability claim 可复现；
4. 维持严格的 provider 边界，以便接纳更多 backend。

后续优先事项包括更多 simulator/render provider、更完善的 UI client、更丰富的资产、learning integration，以及对 OpenUSD 作出决策。

长期目标包括更快速的任务构造，以及完整或部分的 real -> sim -> policy -> real 验收工作流。在相应接口和 Evidence 路线完成实现与资格验证前，这些只代表方向。

## 11. 权威顺序与冲突处理

架构声明按以下顺序判断：

1. 当前实现和可复现 Evidence；
2. 本 canonical 架构基准与仓库所有权 contract；
3. module 文档；
4. README 摘要与图片；
5. 历史迁移说明。

出现冲突时，应更新较低权威层级的材料，或明确将其标记为历史内容。
