# Geochora Core API 与能力范围

> 状态：canonical Core 范围，v0.3
> 日期：2026-10-04

## 1. Core 使命

即使缺少以下组成部分，Geochora/task_env 也必须提供最小但完整的具身 Experiment 能力：

- PhysPi 或其他 Agent 编排；
- 外部记忆、经验或 Agent Skills；
- 外部 Asset Library。

人类开发者或 Codex 必须能够通过有文档说明的 Core API，手动完成两个阶段。

Core 的首要使命是成为可靠、provider-neutral 的多仿真器执行与多渲染器/UI 展示中枢。LLM 推理和积累的经验属于 PhysPi 或其他外部消费方。

### Required capability 与当前 implementation

本文的“必须支持”及概念 API 定义 required canonical capability，不是 implemented/tested/qualified 声明。能力词义以 [仓库 Capability 与 Evidence 治理](../../global/01-repository-ownership-and-boundaries.md#5-capability-与-evidence-治理) 为准。

经人工审查的 P1.0-A baseline（起始 HEAD `9b4a55e8f944daa45a5d4d811ba6a02af4c1cfdc`）确认：

- Scalar production materialization 仍绑定 GeoPhys。
- Batch factory 的 `merged_scene`/`static` 是内部 runtime/layout route，不是 GeoPhys/MuJoCo/SAPIEN/Genesis selector。
- MuJoCo 只有独立 oracle/probe 等路径，尚非统一 Task Artifact 的 production provider；multi-provider materialization 是 planned。
- Task Artifact/Experiment/Evidence 的规范存在。P1.1 新增 `task_env.artifacts` 的 strict TaskArtifact v0 mapping contract skeleton（见 [06](06-phase-1-contracts-and-provider-boundaries.md#14-p11-additive-contract-route)）；production provider materialization、完整 Validator、Runner 与 Experiment/Evidence loader 仍未形成完整统一实现。
- RSL/SB3 learner adapter 和部分 IL script 入口存在；统一 learner integration 及 manipulation IL acceptance 不能据此称为 qualified。
- PickCube/NutAssembly 尚无完整 current-HEAD manipulation qualification；Go2 CUDA/static/RSL 是历史 Evidence 最强的 regression route，current-HEAD qualification 待 P1.0 baseline smoke 确认。

## 2. 最小独立能力

### Stage 1 — 任务构造与物理/可行性验证

Core 必须支持：

~~~text
本地/默认资产或显式资产路径
   -> 机器人/scene 构造
   -> task semantics
   -> observation/action contract
   -> controller/action mode
   -> reset/randomization contract
   -> Automatic Validator
   -> expert route
   -> 随机化可行性探测
   -> report
   -> Judge decision
   -> 冻结的 Task Artifact
~~~

首条 manipulation 参考路线可复用现有 Cartesian primitive planning、controller 内在线 IK 与 action conversion；通用 trajectory optimizer pipeline 及完整 feasibility acceptance 仍需独立实现/证据。

Expert abstraction 不得固化为 manipulator 特定的 IK 语义；未来 locomotion expert route 可以使用不同的 solver、controller 或 policy。

### Stage 2 — 数据、学习与仿真评估

Core 必须支持：

~~~text
冻结的 Task Artifact
   -> expert dataset 生成
   -> recorder/replay/data check
   -> baseline learner 集成
   -> runner(env, policy)
   -> closed-loop 仿真评估
   -> evaluation report
   -> Judge decision
   -> Experiment Evidence
~~~

## 3. 公共 API 能力组

具体 Python class/function 名称可以演进，以下能力组属于规范要求。

### 3.1 构造 API

- 创建/加载 robot embodiment；
- 创建/导入 task-local asset；
- 组合 scene/environment；
- 定义 task semantics；
- 定义 reset/randomization contract；
- 选择 runtime/provider profile；
- 定义 observation 与 action。

### 3.2 Task semantics API

- success/failure；
- reward/metric；
- termination/truncation；
- reset parameter；
- task-level evaluation contract；
- state/privileged-state/camera observation requirement。

### 3.3 Controller/action API

Manipulation 已有如下 action/control conversion：

- world/base frame 下的 absolute_pose；
- EE/world frame 下的 delta_pose；
- absolute_joint；
- trajectory conversion 与 replay validation。

规则：

- 公共/默认 robot controller 可以注册在 Core；
- 不受支持的 robot-specific controller 可以先作为 Task Artifact 私有实现；
- 通过验证的可复用 controller 之后可以提升到 Core；
- locomotion 不强制经过 manipulation controller conversion。

### 3.4 Planning / expert-route API

Core 为 expert-route execution 与 provenance 提供有文档的入口。

当前 manipulation 实现入口：

~~~text
Cartesian primitive planning -> controller/action conversion（含在线 IK）-> executable rollout
~~~

Core 必须区分：

- task feasibility Evidence；
- 当前 expert solver 的成功或失败。

Solver 失败不能自动标记为任务不可行。

此执行入口不证明 expert qualification；trajectory optimizer 集成属于待验证的规范目标。

### 3.5 Validator API

Automatic validation 至少包括：

- config/schema 有效性；
- asset/reference 有效性；
- runtime/provider capability admission；
- reset/initial-state 有效性；
- controller/action 兼容性；
- observation contract 有效性；
- expert rollout 前所需的 finite/sanity check。

上述是统一 Validator 的规范要求。当前校验分散在 config、asset、runtime admission、controller 和 observation 路径中，不能将它们称为已完成并资格化的统一 Validator。

### 3.6 Recorder / replay API

应复用并稳定现有 recording infrastructure，而不是替换它。

Core 必须支持：

- transition/trajectory recording；
- 适用时记录 vector provenance；
- H5 或等效的 canonical dataset representation；
- replay；
- action/observation metadata；
- Evidence 所需的 trajectory/video reference。

每个主要参考任务最终都必须具备 collection -> save -> load -> replay oracle。

### 3.7 Learning 集成

Baseline imitation-learning 计划通过外部 agent_factory 库集成；当前已有部分 script 调用入口，不构成完整 learner route 的资格证明。

Core 负责：

- learner integration/adapter；
- training configuration binding；
- dataset/policy provenance；
- evaluation invocation；
- Experiment 集成。

Core 不需要复制 agent_factory 的算法实现。

首条 manipulation learning route：

1. oracle/state route：state + privileged_state；
2. visuomotor route：RGB + proprioception。

Diffusion Policy 是 planned 初始主要 IL 路线；Flow Matching 可以通过 agent_factory 作为另一条参考路线。两者仍需 dataset、learner 和 closed-loop evaluation Evidence。

Locomotion 仍是 RL 路线，可以使用现有 Go2/RSL 参考路径。

### 3.8 Runner API

runner(env, policy) 是 required 公共 rollout executor；统一实现尚未形成。

概念用法（不是当前可直接调用的已资格化 API）：

~~~python
runner = Runner(env=env, policy=policy, ...)
result = runner.run()
~~~

Runner 统一的是 closed-loop rollout execution，而不是 learning algorithm。

当前 `alg/runner.py` 选择 PPO training route，script 中另有 rollout loop；它们不等于上述通用 Runner 已实现。

Runner 必须依赖稳定的 environment 与 policy contract，不得依赖 GeoPhys/Taichi/robot-SDK 内部实现。

长期目标：

~~~text
SimulationEnv -> GeoPhys/MuJoCo/... provider
RealRobotEnv  -> robot SDK

二者都满足 Runner 使用的 Geochora environment contract。
~~~

Phase I 不要求 real-robot deployment。

### 3.9 Evaluation 与 reporting API

Core 负责结构化 evaluation execution 与 report production。

Core 产生事实；Judge 产生验收决策。

必须分离：

~~~text
evaluation_report.json / report.md   # 事实与 metric
judge_decision.yaml                  # approve/reject + 原因 + 必需修改
~~~

### 3.10 Rendering 与 UI presentation API

Core 负责以下 provider-neutral contract：

- camera 与 render request；
- frame 与 presentation metadata；
- viewport 与 overlay；
- UI client 所需的 interaction event；
- renderer capability reporting 与 fail-closed admission。

Core 不要求特定桌面 toolkit、browser stack 或 renderer。OpenUSD 是未来 interchange/composition 层候选方案，尚不是确定的 canonical format。

## 4. Experiment Evidence 构造 Skill 文档

除公共 API 文档之外，task_env 还必须包含一份内部 Skill/how-to 文档，明确教会 Agent 或 Codex：

- 在何处创建 Task Artifact；
- 在何处创建 Experiment；
- 如何引用冻结的 Task Artifact；
- 如何记录 trajectory 与 video；
- 如何保存外部 dataset/checkpoint reference；
- 如何创建 evaluation_report.json 和 report.md；
- 如何创建/消费 judge_decision.yaml；
- 如何完成 evidence.json；
- 哪些 artifact 可以 cleanup/archive；
- PhysPi 等外部消费方需要保留哪些事实，才能形成持久经验。

这是一份使用 Core 的操作 Skill，不是 PhysPi 的经验或 Skill-distillation 实现。

## 5. Provider 范围

### 当前实现与 Phase-I 目标

- current/default physics implementation：GeoPhys；具体 qualification 绑定具名 intersection；
- primary Phase-I providers：GeoPhys、MuJoCo；
- boundary-validation providers：SAPIEN、Genesis；
- Linux renderer：GeoPhys 默认 renderer；
- Flora：平台条件允许时再进行 provider 集成；
- OpenUSD：scene interchange/composition 候选集成，不是必选项。

不得创建 UniversalSolver abstraction。应维持 Runtime Port/provider 边界与 capability admission。

Phase-I provider 角色是 planned 实施范围，不代表已 supported。安装 MuJoCo package、存在独立 oracle 或采纳 [05–08 实施文档](05-phase-1-multi-simulator-blueprint.md)，均不能证明统一 provider 已 implemented、tested 或 qualified。Physics provider 与 render provider 保持独立选择与资格边界。

## 6. 参考路径

### 主要资格验证路线

Manipulation / IL：

~~~text
PickCube -> NutAssembly -> Agent 生成的相似但未见过的 manipulation task
~~~

### Regression/reference 路线

Locomotion / RL：

~~~text
Go2 walk / RSL
~~~

这些参考路径用于验证 Core contract 和 provider，不定义 Geochora 的完整产品边界。Core 在扩展 manipulation capability 时，必须保留 Go2 CUDA/static/RSL 的历史 regression route，并以 current-HEAD Evidence 确认其状态。

## 7. Phase I 的明确非目标

- PhysPi memory、experience 或 Skill 实现；
- 在 Geochora 内自动提炼 Skill；
- 自动生成 Core patch 或递归自我改进；
- 强制采用 OpenUSD；
- soft-body task；
- phone-video-to-digital-twin；
- 3DGS real-to-sim-to-real；
- 大规模 VLA/WAM 训练；
- 强制 real-robot deployment；
- 在已声明 Phase-I acceptance envelope 外宣称 MuJoCo/SAPIEN/Genesis 的完整支持；
- 在 SAPIEN/Genesis 上进行完整 policy training，或强制 Flora 集成；
- 对完整 real -> sim -> policy -> real 支持作出仓库级声明。
