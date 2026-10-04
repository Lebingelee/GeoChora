# Geochora Core API 与能力范围

> 状态：canonical Core 范围，v0.2
> 日期：2026-10-01

## 1. Core 使命

即使缺少以下组成部分，Geochora/task_env 也必须提供最小但完整的具身 Experiment 能力：

- PhysPi 或其他 Agent 编排；
- 外部记忆、经验或 Agent Skills；
- 外部 Asset Library。

人类开发者或 Codex 必须能够通过有文档说明的 Core API，手动完成两个阶段。

Core 的首要使命是成为可靠、provider-neutral 的多仿真器执行与多渲染器/UI 展示中枢。LLM 推理和积累的经验属于 PhysPi 或其他外部消费方。

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

首条 manipulation 参考路线可以使用现有的 IK + trajectory optimizer + controller/action conversion pipeline 生成 expert。

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

当前 manipulation 参考路线：

~~~text
IK -> trajectory optimizer -> controller/action conversion -> executable rollout
~~~

Core 必须区分：

- task feasibility Evidence；
- 当前 expert solver 的成功或失败。

Solver 失败不能自动标记为任务不可行。

### 3.5 Validator API

Automatic validation 至少包括：

- config/schema 有效性；
- asset/reference 有效性；
- runtime/provider capability admission；
- reset/initial-state 有效性；
- controller/action 兼容性；
- observation contract 有效性；
- expert rollout 前所需的 finite/sanity check。

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

Baseline imitation-learning algorithm 位于现有 agent_factory 库中。

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

Diffusion Policy 是初始主要 IL 路线；Flow Matching 可以通过 agent_factory 作为另一条参考路线。

Locomotion 仍是 RL 路线，可以使用现有 Go2/RSL 参考路径。

### 3.8 Runner API

runner(env, policy) 是公共 rollout executor。

概念用法：

~~~python
runner = Runner(env=env, policy=policy, ...)
result = runner.run()
~~~

Runner 统一的是 closed-loop rollout execution，而不是 learning algorithm。

Runner 必须依赖稳定的 environment 与 policy contract，不得依赖 GeoPhys/Taichi/robot-SDK 内部实现。

长期目标：

~~~text
SimulationEnv -> GeoPhys/MuJoCo/... provider
RealRobotEnv  -> robot SDK

二者都满足 Runner 使用的 Geochora environment contract。
~~~

首个 milestone 不要求 real-robot deployment。

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

### 首个 milestone

- physics：GeoPhys；
- Linux renderer：GeoPhys 默认 renderer；
- Flora：平台条件允许时再进行 provider 集成；
- MuJoCo/SAPIEN：未来 provider adapter；
- OpenUSD：scene interchange/composition 候选集成，不是必选项。

不得创建 UniversalSolver abstraction。应维持 Runtime Port/provider 边界与 capability admission。

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

这些参考路径用于验证 Core contract 和 provider，不定义 Geochora 的完整产品边界。Core 在扩展 manipulation capability 时，必须保留现有已资格化的 Go2 路线。

## 7. 首个 milestone 的明确非目标

- PhysPi memory、experience 或 Skill 实现；
- 在 Geochora 内自动提炼 Skill；
- 自动生成 Core patch 或递归自我改进；
- 强制采用 OpenUSD；
- soft-body task；
- phone-video-to-digital-twin；
- 3DGS real-to-sim-to-real；
- 大规模 VLA/WAM 训练；
- 强制 real-robot deployment；
- 立即完整支持 MuJoCo/SAPIEN/Flora；
- 对完整 real -> sim -> policy -> real 支持作出仓库级声明。
