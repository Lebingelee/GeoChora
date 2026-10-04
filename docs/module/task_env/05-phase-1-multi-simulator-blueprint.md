# Geochora Phase I 多仿真器实施蓝图

> 状态：active Phase-I 实施蓝图，v0.2
> 日期：2026-10-04
> 范围：定义 Phase I 多仿真器资格验证的实施顺序、阶段 gate、Evidence 位置和完成标准。
> 权威关系：作为 Phase-I 实施计划采纳，从属于 [系统架构基准](../../global/00-system-architecture-anchor.md)、[仓库所有权](../../global/01-repository-ownership-and-boundaries.md) 与 canonical TaskEnv contract。active 表示文档用于指导实施，不表示 capability 已实现、测试通过、qualified 或任何子阶段已获准。

## 1. 目的

Phase I 将 Geochora 的 provider-neutral 架构变成可执行、有 Evidence 支撑的多仿真器路线。

Phase I 目标：

~~~text
一个 Task Artifact
    -> 一个 provider-neutral task definition
    -> 一份由 Geochora 生成的 randomization / ResetSample
    -> 多个 provider materialization
    -> 一套 canonical state / control / trajectory contract
    -> 成对 provider 的 expert 与 replay qualification
    -> 一条 dataset / learner route
    -> 在主要 provider 间评估同一 policy checkpoint
    -> machine-readable qualification Evidence
~~~

Phase I 实施目标（provider 角色为 planned，不是当前 capability claim）：

- 主要 physics provider：GeoPhys 与 MuJoCo。
- 边界验证 physics provider：SAPIEN 与 Genesis。
- 主要 manipulation task：PickCube。
- 精密/contact regression task：NutAssemblySquare。
- 必须保护的 regression route：Go2 CUDA/static/RSL 历史路线；current-HEAD qualification 在 P1.0 baseline 中重新确认。

Phase I 不要求 PhysPi。人类开发者或 Codex 必须能够通过 Geochora 公共 API、已记录的 Skills、Task Artifact、Experiment 与 Evidence 执行该路线。

## 2. 固定架构决策

Phase I 采用以下所有权规则：

~~~text
Geochora 负责：
- task semantics；
- task randomization 与实际 ResetSample 生成；
- public action semantics；
- 存在公共 controller 时的 canonical controller computation；
- canonical state / observation contract；
- evaluation semantics 与 qualification tolerance；
- trajectory、Experiment、report 与 Evidence contract。

Provider 负责：
- provider-specific world/materialization；
- actuator realization；
- 数值物理演化；
- provider-native cache、kernel、solver internals 与性能工程。

Render provider 与 physics provider 始终是不同边界。
~~~

任务构造模型保持为：

~~~text
A. World Definition
   - 存在哪些对象；
   - 可控制的 embodiment；
   - control contract；
   - observation contract；
   - randomization contract；
   - 不调用 simulator API。

B. Runtime Materialization
   - 选择 ExecutionSpec；
   - 执行 capability admission；
   - 生成/应用 ResetSample；
   - 编译/materialize provider runtime；
   - 暴露 canonical runtime state。

C. Semantic Evaluation
   - 只消费 canonical current/history state；
   - 产生 metric、predicate、event、task outcome 与 trajectory-level evaluation；
   - 绝不读取 provider-private state。
~~~

Provider 选择是 Execution 属性，不属于 Task Artifact identity。当所需 capability set 获准时，同一 frozen Task Artifact 必须能够在 GeoPhys、MuJoCo、SAPIEN 和 Genesis 中复用。

## 3. Phase I 完成定义

只有满足以下全部条件，Phase I 才算完成。

### 3.1 主要 provider 完成标准

GeoPhys 与 MuJoCo 都必须通过：

1. frozen PickCube Task Artifact 的 provider capability admission；
2. provider-neutral asset/embodiment materialization；
3. canonical frame、state、timebase、reset 与 camera-geometry conformance；
4. canonical controller-target realization；
5. open-loop replay qualification；
6. closed-loop expert qualification；
7. canonical dataset record/load/replay 检查；
8. state-policy 单 provider 训练和同一 checkpoint 跨 provider 评估；
9. camera/render observation 获得资格验证后的 visuomotor-policy route；
10. Experiment Evidence 与 phase qualification report。

### 3.2 边界 provider 完成标准

SAPIEN 与 Genesis 至少必须通过：

- provider admission；
- world/asset materialization；
- ResetSample realization；
- canonical state/frame/timebase；
- camera geometry；
- canonical control realization；
- conformance probe；
- PickCube closed-loop expert execution。

Phase I 不要求在 SAPIEN 或 Genesis 上进行完整 policy training。可将可选的 zero-shot policy evaluation 记录为附加 Evidence。

### 3.3 精密/contact regression

NutAssemblySquare 必须验证这些 contract 并非只适用于 PickCube。GeoPhys 与 MuJoCo 至少都必须执行同一 frozen task contract，并通过已声明的 expert/trajectory semantic acceptance route。

## 4. Phase I 对象流

~~~text
文本需求 / 现有参考任务
                |
                v
        Draft Task Artifact
                |
                v
      RequiredCapabilitySet
                |
                v
       Capability Admission
                |
                v
    Geochora Random Sampler
                |
                v
           ResetSample
                |
          +-----+-----+
          |           |
          v           v
     ExecutionSpec  EvaluationSampleSet
          |
          v
 Provider Materialization
          |
          v
  RealizedInitialState
          |
          v
    CanonicalStateView
          |
   +------+------+
   |             |
   v             v
Controller   Semantic Evaluation
   |             |
   v             |
CanonicalControl |
   |             |
   +------rollout+
          |
          v
 Canonical Trajectory
          |
     +----+----+
     |         |
     v         v
  Dataset    Replay/Expert report
     |
     v
   Policy
     |
     v
多 provider Evaluation
     |
     v
Experiment Evidence + Phase Qualification
~~~

## 5. 实施子阶段

Phase I 的正式 architecture/implementation subphase 为 P1.0–P1.8，共九个。每个子阶段都应独立审查，并在下一阶段成为权威工作前留下自己的 acceptance package。

### P1.0 — 冻结 baseline 并采纳计划

目标：在改变 provider 边界前冻结当前仓库与 Evidence baseline。

推荐 operator workflow：audit → documentation adoption → baseline smoke → evidence freeze。P1.0-A/B/C/D 仅是这一流程的执行 checkpoint，不新增正式 architecture subphase；文档采纳不能替代 baseline smoke 或授权进入 P1.1。

工作：

- 记录起始 Git commit、历史 Evidence 路线与待重新确认的 current-HEAD qualification；
- 记录 PickCube/NutAssembly 当前实现状态；
- 记录不得破坏的 Go2/RSL regression route；
- 采纳 Phase I 文档；
- 更新与本蓝图冲突的 canonical provider-scope 表述；
- 建立 machine-readable Phase I capability matrix 骨架。

必需 smoke：

- repository import/bootstrap smoke；
- 当前最强 Go2/RSL 或同等现有受治理 regression smoke；
- 当前 TaskEnv contract test subset；
- 文档 relative-link 检查。

验收：

- 不把不受支持的 capability 重新标记为已资格化；
- baseline failure 必须记录，不能静默归因于 Phase I change；
- 在 baseline report 中冻结 HEAD、dependency/provider revision 与已知 unsupported intersection。

Evidence：workspace/qualification/phase1/p1_0_baseline/

### P1.1 — Contract 骨架与 provider-neutral task 边界

目标：实现让单个 task definition 保持 provider-neutral 所需的最小 contract。

工作：

- 定义 Phase I 所需的 Task Artifact v0 field；
- 定义 WorldDefinition、InitializationContract、SemanticDefinition 与 Timebase；
- 定义 ExecutionSpec；
- 定义 RequiredCapabilitySet 与 ProviderCapabilityManifest；
- 定义最小 CanonicalStateView；
- 确保 task file 不导入 simulator API；
- 提升现有 provider-neutral scene-source seam，不在 task definition 中嵌入 GeoPhys scene construction。

必需 smoke：

- schema load/roundtrip；
- 拒绝未知/无效 field；
- fail-closed capability admission；
- 不依赖 provider 的 task definition import；
- 不构造 simulator 的 semantic fixture evaluation。

验收：

- PickCube candidate Task Artifact 可在不导入四个 provider 的情况下加载；
- 切换 provider 不需要创建第二个 Task Artifact；
- semantic evaluation 只接受 canonical state/history data。

Evidence：workspace/qualification/phase1/p1_1_contracts/

### P1.2 — Runtime materialization、reset、state 与 timebase

目标：建立所有后续阶段共享的 provider runtime 边界。

工作：

- 定义 compile/materialize/reset/step/snapshot/close adapter 入口；
- 将 physics provider identity 与 GeoPhys 内部 layout/profile identity 分开；
- 实现 Geochora-owned ResetSample generation；
- 分别记录请求的 ResetSample 与 provider-realized initial state；
- 定义显式可选 settle behavior，默认 settle 为零；
- 在每个 control boundary 暴露 canonical time/state；
- 在 ExecutionSpec 中保持 physics_provider 与 render_provider 分离。

必需 smoke：

- deterministic mode 下对同一 provider 两次应用同一 ResetSample；
- GeoPhys 与 MuJoCo 接受同一 ResetSample；
- control-step 时间增量匹配 Task Artifact timebase；
- realized initial state 满足 reset tolerance；
- 不受支持 capability 在 rollout 前拒绝。

验收：

- GeoPhys 与 MuJoCo 都能 materialize 同一最小 PickCube world 并暴露 canonical initial state；
- provider randomization 不重新采样 task parameter；
- task semantics 中不泄漏 provider-private storage。

Evidence：workspace/qualification/phase1/p1_2_runtime/

### P1.3 — 主要 provider conformance probe

目标：在调试完整 manipulation task 前，先验证成本最低的物理 contract。

必需 probe：

1. Asset / frame probe。
2. Free-fall probe。
3. Joint-tracking probe。
4. Camera projection + depth probe。
5. Contact probe。

工作：

- 为每个 probe 定义显式 oracle 与 tolerance；
- 对相同输入运行 GeoPhys 和 MuJoCo；
- 将 field 分类为 exact semantic parameter、approximate mapping 或 provider-native parameter；
- 生成 pairwise comparison report。

验收：

- 两个主要 provider 通过所有 mandatory probe；
- 将失败归因到具名层级，而不是通过放宽 task-level threshold 隐藏；
- 存在 analytical invariant 或 provider-independent oracle 时，不把 MuJoCo 当作绝对真值。

Evidence：workspace/qualification/phase1/p1_3_conformance/

### P1.4 — Frame、camera 与 render-observation geometry

目标：在使用 RGB policy observation 前，使视觉几何保持 provider-neutral。

工作：

- 冻结 world/base/EE/object/camera mount/optical frame convention；
- 明确定义 T_world_from_camera 及逆变换命名；
- 定义 intrinsic matrix convention 与 vertical/horizontal FOV interpretation；
- 验证 dynamic camera parent transform；
- 验证 depth back-projection；
- 将 physics 与 render provider 保持为不同 capability dimension；
- 主要路线初期使用 provider native renderer。

必需 smoke：

- fixed landmark projection；
- robot motion 后的 dynamic attached-camera projection；
- depth pixel -> 3D -> world roundtrip；
- image layout/dtype/shape contract；
- post-control-step boundary 的 timestamp synchronization。

验收：

- GeoPhys 与 MuJoCo 的 camera geometry 通过声明的 pixel/depth tolerance；
- 不要求 RGB photometric equality；
- 记录 native renderer 差异，不通过 task-specific hack 补偿。

Evidence：workspace/qualification/phase1/p1_4_camera/

### P1.5 — Canonical control 与 expert trajectory qualification

目标：分离 controller、physics 和 task-feasibility Evidence。

工作：

- 冻结 Phase I canonical manipulation control target，初始为 joint-position target + gripper target；
- 保持 absolute/delta pose 为公共 Geochora action；
- 在 provider realization 前执行共享 Geochora controller computation；
- 实现两个独立 gate：
  - C1 open-loop replay；
  - C2 closed-loop expert execution；
- 记录 requested action、canonical action、controller target、applied control、canonical state 与 semantic trace。

必需 smoke：

- one-step action conversion；
- 短 free-space joint trajectory；
- gripper open/close transition；
- 短 open-loop PickCube segment；
- 短 closed-loop expert segment。

验收：

- C1 在具名 tolerance 下报告 numerical/behavioral divergence；
- C2 证明同一 expert algorithm 能在所需 randomized feasibility set 上完成 GeoPhys 与 MuJoCo PickCube；
- solver/expert failure 不得重标为 task intrinsic infeasibility。

Task-local Stage-1 Evidence：workspace/tasks/<task_id>/artifacts/<version>/validation/

Phase-level cross-provider Evidence：workspace/qualification/phase1/p1_5_expert/

### P1.6 — Canonical trajectory 与 state-policy transfer

目标：证明 dataset 与 policy 边界可以跨主要 provider 移植。

工作：

- 完成 canonical trajectory schema；
- 保留 T+1 个 observation 与 T 个 transition；
- 按适用情况记录 ResetSample、RealizedInitialState、provider provenance、action/control layer、semantics 与 camera metadata；
- 每次从一个 provider 生成训练数据；
- 训练一个 state/proprioception policy；
- 在两个主要 provider 上评估完全相同的 checkpoint。

必需 Experiment：

~~~text
Train GeoPhys -> Eval GeoPhys
Train GeoPhys -> Eval MuJoCo
Train MuJoCo  -> Eval MuJoCo
Train MuJoCo  -> Eval GeoPhys
~~~

可以增加 mixed-provider training 作为次要 Experiment，但不能取代 transfer matrix。

必需 smoke：

- record/save/load/replay 一条 trajectory；
- dataset schema/shape 检查；
- 一个 minibatch/极短 learner smoke；
- 一次短 runner(env, policy) rollout；
- 在两个 provider 中加载 checkpoint。

验收：

- 一个 canonical dataset representation 可在没有 provider-specific learner code 时消费；
- 同一 checkpoint 无需 task-specific adapter patch 即可执行；
- performance result 使用同一 frozen EvaluationSampleSet。

Experiment 位于 workspace/tasks/<task_id>/experiments/<exp_id>/。

Phase-level transfer summary 位于 workspace/qualification/phase1/p1_6_state_policy/。

### P1.7 — Visuomotor policy qualification

目标：在 state-policy portability 建立后加入 native visual domain gap。

工作：

- 使用已资格化 camera contract 训练 RGB + proprioception policy；
- 主要路线保留 native renderer；
- 进行同一 checkpoint 跨 provider 评估；
- 与 state-policy baseline 对比，隔离 visual-domain degradation。

必需 smoke：

- 按训练 shape/dtype 采集 RGB observation；
- 一个 training minibatch；
- checkpoint save/load；
- 在两个 provider 上做短 closed-loop rollout。

验收：

- 完全相同的 visuomotor checkpoint 可在 GeoPhys 和 MuJoCo 执行；
- camera geometry 保持资格化；
- performance gap 与 state-policy portability 分开报告。

Evidence：workspace/qualification/phase1/p1_7_visuomotor/

### P1.8 — 边界 provider、NutAssembly regression 与 Phase I 收尾

目标：验证 abstraction 不只是 GeoPhys-MuJoCo 的成对 adapter。

工作：

- 只实现 SAPIEN 与 Genesis adapter 到声明的 Phase-I 边界；
- 运行 capability admission 和五项 conformance probe；
- 运行 PickCube closed-loop expert qualification；
- 在 GeoPhys 与 MuJoCo 上运行 NutAssemblySquare 作为 precision/contact regression；
- 可选运行 SAPIEN/Genesis zero-shot state-policy evaluation；
- 生成最终 provider/task capability matrix 与 Phase I decision。

验收：

- 支持的 capability intersection 不需要为 SAPIEN/Genesis 重写 Task Artifact；
- 不支持的 intersection fail closed；
- NutAssembly 在两个主要 provider 上验证同一 contract structure；
- 所有 Phase-I claim 都由 immutable Evidence reference 支撑。

Evidence：workspace/qualification/phase1/p1_8_closure/

## 6. Evidence 与 acceptance 文件

Phase-level implementation Evidence 不得提交到 docs/，而应放在 workspace/qualification/phase1/，并引用而非复制 task/experiment Evidence。

推荐布局（每个目录均有自己的 acceptance package）：

~~~text
workspace/qualification/phase1/
├── p1_0_baseline/
├── p1_1_contracts/
├── p1_2_runtime/
├── p1_3_conformance/
├── p1_4_camera/
├── p1_5_expert/
├── p1_6_state_policy/
├── p1_7_visuomotor/
└── p1_8_closure/

每个 <subphase>/（p1_0_baseline 至 p1_8_closure）内部：
├── acceptance_report.md
├── acceptance.json
├── phase_decision.yaml
├── smoke/
├── qualification/
├── failures/
└── refs/
~~~

每个子阶段：

- acceptance_report.md：记录人可读事实、范围、命令、结果、不支持的 intersection 与剩余风险；
- acceptance.json：machine-readable result 与 Evidence index；
- phase_decision.yaml：显式 approve/reject/conditional authority decision；
- smoke/：smoke plan、report、log 与紧凑 artifact；
- qualification/：昂贵或端到端 qualification output；
- failures/：对设计产生实质影响的失败记录；
- refs/：Task Artifact、Experiment、dataset、checkpoint 与 provider Evidence 的稳定引用。

Task Artifact 与 Experiment Evidence 继续遵循 03-task-artifact-experiment-evidence-contract.md。

## 7. 子阶段 acceptance-report template

每个 acceptance_report.md 应包含：

~~~text
标题 / subphase ID
日期
仓库 commit
provider version
使用的 Task Artifact ID/hash
包含范围
明确排除范围
改变/保护的 contract
改变的实现路径
smoke summary
qualification summary
oracle/tolerance summary
已知 failure
不支持的 capability intersection
适用时的 performance/resource note
Evidence reference
残余风险
下一子阶段建议
~~~

Report 只记录事实，权威 decision 保留在 phase_decision.yaml。

~~~yaml
phase: p1_3_conformance
decision: approve
judge:
  type: human
basis:
  - asset_frame_probe passed on geophys and mujoco
  - free_fall_probe passed within declared tolerance
  - joint_tracking_probe passed
required_changes: []
unsupported:
  - sapien/contact_impulse
  - genesis/depth_camera
~~~

## 8. 变更纪律

Phase I 的每个 code change 必须指出：

- 改变或保护哪个 Phase-I contract；
- 执行哪个 provider/task path；
- 立即需要的最小 defect-sensitive smoke；
- 延后到哪个 subphase gate 的昂贵 qualification。

不要在每次修改后运行所有昂贵任务。不能为了降低成本而用 import-only coverage 替代 contract-sensitive smoke。

详细 smoke selection policy 见 07-phase-1-smoke-testing-and-acceptance.md。

## 9. 重复失败与恢复

重复失败不得引发无限期 localized patching。

当阶段触发 08-phase-1-debug-and-recovery-playbook.md 定义的 recovery trigger 时，Codex 或人必须：

- 停止基于同一 hypothesis patch；
- 编写 failure record；
- 重新分类 failing layer；
- 测试至少一个 upstream 和一个 downstream alternative hypothesis；
- 运行 common-sense invariant sweep；
- 与 known-good control path 对比；
- 如果公共边界错误则 rollback 或 redesign。

Provider-private workaround、静默放宽 tolerance 或隐藏的 task-specific branch 都不是可接受恢复方式。

## 10. 文档采纳与能力状态

本蓝图与 06–08 作为 active Phase-I 实施文档采纳；其要求是后续实施与验收目标，不是当前 capability Evidence。Canonical 00/01/02/04 已对齐目标范围、所有权、当前 implementation 和 qualification 边界。

权威分工：

- docs/global/00-system-architecture-anchor.md：
  - roadmap 定义 active multi-simulator 实施目标；
  - GeoPhys/MuJoCo 的主要角色和 SAPIEN/Genesis 的边界角色是 planned，不授予 capability status。
- docs/global/01-repository-ownership-and-boundaries.md：
  - 定义 capability 词义与具名 qualification intersection。
- docs/module/task_env/02-core-api-and-capability-scope.md：
  - 区分 required canonical capability 与当前 implementation；
  - 当前 scalar GeoPhys materialization、batch 内部 route 和 MuJoCo oracle/probe 不等于统一 multi-provider execution。
- docs/module/task_env/04-core-qualification-and-governance.md：
  - 定义 Phase-I qualification ladder、S0–S4 映射及历史/current-HEAD provenance 要求。

不得改写历史 Evidence 来暗示这些 capability 已存在。在某个子阶段通过前，应按实际情况标记为 planned 或 implemented/tested but not qualified。
