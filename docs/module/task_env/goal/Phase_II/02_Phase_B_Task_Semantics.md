# Phase B — Task Representation & Semantics：架构、代码实施与验收（Codex 草案）

> **PROPOSED / 需 Codex Audit 与维护者确认；不等于新的 Task Artifact 已实现。**  
> 编制基准：2026-10-19，`main` HEAD `f292df149f41520b484ff27cf2ff78a584903013`，v1.1.0。  
> 相关文件：[`00_Phase_II_AD_Implementation_Blueprint.md`](00_Phase_II_AD_Implementation_Blueprint.md)、[`01_Phase_A_Core_Object_Model.md`](01_Phase_A_Core_Object_Model.md)。

## B.0 阶段目标与四条已达成的设计决议

**目标**：允许用户基于 A 的 Scene/Entity/Frame，以 **YAML 为主要声明格式 + 有约束的 Python Hooks** 定义 Task Roles、Reset Distribution、Success/Failure/Reward、时序语义和 Action/Observation Requirements，最后将稳定的语义内容汇入**现有** TaskArtifact，供 C/D Execution 使用。

**不做**：自然语言 Task 自动创作、Task Harness、自动审批冻结、通用 Policy Runner、自动将任何 benchmark 无损转换为 Task。Python Hook 约束不是恶意代码安全沙箱。

本轮沿用此前 B-R1–B-R4：

- **B-R1 Role / Sampling**：Task Role 的 selection rule/cardinality/randomization 进入冻结声明；每 Episode 在 Core reset 时解析成不可变 Role Binding，并记录 provenance。
- **B-R2 Stateful Semantics**：时序评估器写成 `(semantic_memory_next, evaluation) = F(canonical_state, semantic_memory, frozen_params)`；明确 sequence/dwell/rising_edge；缺失 State 是 unavailable/error 而不是 `False`。
- **B-R3 YAML + Restricted Hooks**：声明式为主；Python Hooks 仅做已声明的 Authoring/Initialization/Semantic 扩展，确定性要求、State/Capability Dependencies、版本/内容 hash 必须显式。
- **B-R4 Frozen Artifact / Experiment 分离**：任务定义与 Evaluation Contract 归 Artifact；Provider/Policy/样本次数/训练预算/rollout/record 配置归 Experiment/Execution；不新建第二个 Artifact 系统。Task 的时间需求与原生 Physics `dt` 的拆分需保护旧 `Timebase` v0 身份。

## B.1 当前代码真实状态与演进风险

| owner / 路径 | IMPLEMENTED（当前事实） | 计划差距 |
| --- | --- | --- |
| [`task_env/artifacts/contracts.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/artifacts/contracts.py) | `TaskArtifact(task-artifact-v0)`，`WorldDefinition`、`InitializationContract`、`SemanticDefinition`、`Timebase`、`RequiredCapabilitySet`，strict hashing | Frozen Roles/Temporal Semantics/Hook Identity/Requirements 需**版本迁移**，不能静默扩 v0 bytes |
| [`task_env/artifacts/execution.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/artifacts/execution.py) | `ResetSample(reset-sample-v0)`、`RealizedInitialState` | Scene Variant/Role Binding 的 per-episode identity/provenance 尚非通用契约 |
| [`task_env/tasks/pick_cube/`](https://github.com/Lebingelee/GeoChora/tree/main/task_env/tasks/pick_cube) | task.py/solution.py/config.yaml，lift-only success 及任务随机化 | 语义及 reset recipe 适配新声明系统，不改历史 task identity |
| [`task_env/tasks/nut_assembly/`](https://github.com/Lebingelee/GeoChora/tree/main/task_env/tasks/nut_assembly) | Task Semantics、11-stage Solution、Guard、Outcome Completion V1 | 分开 Task Success 与 Expert Completion；不通过 B 更改 Guard Controller |
| [`task_env/environment/task_definition.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/environment/task_definition.py) | 既有 TaskDefinition/TaskStateView/evaluation 路线 | 归一化 Semantic Evaluator 输入与反馈；不能绕开已有 TaskDefinition |
| [`task_env/environment/lifecycle.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/environment/lifecycle.py) | TaskLifecycleAdapter reset/evaluate/obs normalization | B 仅提供 Evaluation Contract，终止策略执行归 C |
| [`task_env/environment/configuration.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/environment/configuration.py) | YAML loader/strict config 合并等 | 复用现有 loader；明确 new source schema 与 frozen compiled artifact |

**特别风险**：目前先进路径把 `physics_dt × control_substeps` 纳入 `TaskArtifact.timebase`。以前讨论希望任务只声明所需控制/评价时间需求，但若在 B 直接删除 physics_dt，就会破坏已发布 hash 与 Provider Source Admission。必须版本化并同时保护旧 decode/execution。

## B.2 推荐数据流与 owner 划分

```text
Task Authoring Source (YAML + declared Hook references)
 ├─ Scene Ref / Entity Roles / Cardinalities
 ├─ Initialization / Randomization / Allowed Variants
 ├─ Predicates / Temporal Rules / Reward / Metrics
 ├─ Action/Observation/Interaction Requirements
 └─ Evaluation Contract + task-time requirements
                  │ strict load + semantic validation
                  ▼
          Task Definition IR (not separate artifact authority)
                  │ compile against Canonical Scene & A identities
                  ▼
         Existing TaskArtifact (vNext, versioned)
                  │
           C: Execution Planning
                  │
                  ▼
Reset(time + seed) → Core selection/Role Binding → ResetSample
                  │ apply to one Provider (D)
                  ▼
       Canonical State + Semantic Memory
                  │
                  ▼
           Task Evaluation
      success / failure / reward / metrics
```

**注意**：`Task Definition IR` 只表示编译阶段的临时中间值；如果源码已有合适的 TaskDefinition/Contract，就直接扩展。不得创造一个与 `TaskArtifact` 同义的持久版本框架。

### B.2.1 任务声明建议分块

| 区块 | 用途 | 归属 |
| --- | --- | --- |
| `identity/scene` | task id、version、A Scene 引用 | Task Source → Artifact |
| `roles` | Entity/Group Selector、cardinality、类型条件与选择策略 | Task Artifact，reset 时实例化 |
| `initialization` | sampled dimensions/distribution、hard bounds、validity、显式 settle | Task Artifact → Core sampler |
| `semantics` | typed predicates、时间组合、success/failure、reward/metrics | Task Artifact |
| `interaction` | action modes、state dependencies、observation requirements | Task Artifact，C/D admission |
| `time_requirements` | control interval / semantic observation rates / horizons 的 task intent | Task Artifact vNext，原生 physics_dt 兼容版本另论 |
| `hooks` | 名称、阶段、declared inputs、code hash/version | Task Artifact provenance |
| `solution_reference` | 可选独立 Solution provenance | 不绑定 Env 生命周期，严禁 Expert Completion 定义 Task Success |

### B.2.2 YAML 示例（**设计示意**，非可直接执行 Schema）

```yaml
schema_version: task-source-proposal-v1
identity: {task_id: place_red_block, version: v1}
scene: {ref: scenes/tabletop_dual_arm@v1}
roles:
  manipulator: {entity_type: robot, selection: {ids: [robot_left]}, cardinality: exactly_one}
  target_block: {entity_type: rigid_body, tags: [red_block], cardinality: exactly_one}
  target_region: {entity_type: region, tags: [drop_zone], cardinality: exactly_one}
initialization:
  seed_domain: task_seed
  randomization:
    - {field: target_block.pose_xy, distribution: uniform, hard_bounds: [[0.40, 0.55], [-0.1, 0.1]]}
  settle: {policy: none}
semantics:
  predicates:
    block_in_region: {type: pose_in_region, object_role: target_block, region_role: target_region}
    arm_clear: {type: frame_distance_gt, robot_role: manipulator, threshold_m: 0.12}
  success: {type: sequence, stages: [block_in_region, arm_clear]}
  failure: {type: never}      # 示例，不代表所有任务可以缺省 Failure
  reward: {type: sparse_success}
interaction:
  required_state: [target_block.pose_world, manipulator.ee.pose_world]
  action_requirements: [cartesian_pose]
  observation_requirements: [state, privileged_state]
hooks: []
```

Task/Scene Role 的引用必须在编译阶段检查合法性；不能把 Provider 整数 Object ID 写入声明。该示例具体 predicate names、selectors、hook signature 均待 Codex 结合现有代码提出小而可测的正式 Schema。

## B.3 Role / Scene Variant / Initialization

### B.3.1 Role Selector 是冻结规则，Role Binding 是每 Episode 结果

例如某场景有 `cube_red_01`、`cube_red_02`，Task 声明 `target_block = any red_cube`，且 cardinality `exactly_one`。

- **Compile**：确认 selector 合法、资源上界和可选候选集合存在；如场景允许动态添加，则声明迟绑定条件与失败行为。
- **Reset**：Core sampler 使用 `task_seed` 和冻结的 selection policy 选出真实 `entity_id`。
- **Execute**：Task Evaluator、Solution、Recorder 使用已解析的不可变 Role Binding，不能每 Step 重新抽一个目标。
- **Record**：保存选择规则身份、选中 Entity、Seed、Scene Variant 和 Sample ID，便于跨 Provider paired comparison。

对数量关系建议显式：`exactly_one`、`one_or_more`、`exactly_n` 或界定范围；同时禁止多个独占 Role 意外绑定同一 Entity，除非声明允许共享。

### B.3.2 初始化是请求+实现核验，不是 Provider 随机采样

```text
Frozen Initialization Contract + Task Seed
            │ deterministic Core sampler
            ▼
         ResetSample
            │ D provider applies exactly this sample
            ▼
       RealizedInitialState
            │ realization gate / tolerance
            ▼
       Accepted Episode State
```

禁止隐式 settle / native resampling / 运行时篡改 hard bounds。Sample 需有 stable identity；同一整数 seed 跨 Provider 不保证同一实际物理初态，因此跨 Provider 对照应**复用冻结 Sample 内容，并检查 Realized State**。

### B.3.3 Scene Variant 不应暗改 Task 定义

Task 可声明合法 Scene Variant 分布，但必须冻结其 selection envelope（允许对象数、资产类别、位置边界等）。Episode 内若仅选择已有实体的初始位姿，不一定需要 native scene recreate；若实体拓扑变化，C/D 必须选择合法的 materialization/reset path，并在记录中体现 scene-instance ID。

## B.4 Temporal Semantics：有状态但不依赖 Solution

推荐 Formal Contract：

\[
(m_{t+1}, e_t) = F(s_t^{\text{canonical}}, m_t, \theta_{\text{frozen}}),
\quad e_t=(r_t,\text{success}_t,\text{failure}_t,\text{metrics}_t).
\]

Semantic Memory 的 Owner 是 Task Semantic Evaluator，不是 Controller、Solution、Recorder。独立 Solution 可以有完全不同的规划 Stage。

| Predicate 类型 | 必需行为 | 需要保护的边界 |
| --- | --- | --- |
| Scalar/geometric | pose distance、position in region、joint threshold | SI、Frame 方向、比较等号与容差版本 |
| Event | rising_edge / falling_edge | 必须保存上一采样的布尔状态 |
| Temporal | dwell/hold(duration, predicate) | 连续时间采样、gap/reset、clock provenance |
| Ordered | sequence(stage1, stage2) | 必须保存完成阶段并确定 reset 行为 |
| Logical | AND/OR/NOT 或显式组合 | short-circuit 是否会漏状态更新必须确定 |
| Reward/Metric | step reward、dense potential、completion status | Reward 与 Success 可以相关但不是同一个事实 |

- Missing required state ⇒ **Unavailable**（或明确执行契约错误），不能假装 predicate=False。
- Native 500 Hz Guard Evidence（例如 NutAssembly）不可由 100 Hz Outer Snapshot 内插伪造；它属于 Solution/Controller 的高频执行需求，由 C 消费，B 的 Temporal Evaluator 只依赖实际声明的 Sampling Contract。
- `success_current` 与 `success_ever` 可以同时记录；是否触发 Episode Termination **归 C 的 Termination Policy**，不是 Task Predicate 直接关闭 Runtime。
- Semantic Memory 的 Snapshot/Restore 语义需明确；但完整 Provider/Controller/Solution Checkpoint 属 C/D 的更广工作，不得因 B Memory 可序列化声称 D0 Replay。

## B.5 Python Hook 契约

只允许**有界扩展位置**：

1. `authoring_hook`：基于规范化 Scene/Task Source 生成/验证声明；不直接控制仿真。
2. `initialization_hook`：在冻结 Envelope 下产生 Role/Reset 的确定性派生，不能任意访问 Provider Native API。
3. `semantic_hook`：接受已声明的 canonical state、semantic memory 和 frozen params，返回 Evaluation/Memory。

每个 Hook 至少声明 `hook_id`、`version/code_hash`、`inputs`、`required_capabilities`、`determinism`、`evaluation_phase`、`pure_or_stateful`，构造时 strict validation。禁止 hook 在 runtime 悄悄依赖系统时间、随机全局状态或私有 solver array 来改变 Frozen Evaluation Contract。**这是可审计/可复现性约束，不是安全沙箱。**

Hook 变更涉及语义时须新 Artifact Identity；源码无法保证复现时，标记不可复现/不准正式 benchmark，而不是只记函数名。

## B.6 Task Artifact 版本、身份和时间要求

**明确避免“两个 Artifact”问题**：沿用 `task_env/artifacts/contracts.py::TaskArtifact`，使用 `task-artifact-vNext` 或显式新类型版本；旧 `task-artifact-v0` Decode/Hash 必须维持不变。

vNext 候选冻结范围：

- World/Scene/Entity+Role Rules 与 Asset References；
- Initialization/Sampling/Variant/realization requirements；
- Success/Failure/Reward/Temporal memory policy/metrics；
- Action/Observation/State Capabilities；
- Hook identities/versions；
- Evaluation protocol + Stop/Termination permitted policies（终止执行归 C）；
- Task-owned control/semantic time requirements。

**Timebase 迁移**：当前 v0 冻结了 `physics_dt`；不能在 B 阶段让 `physics_dt` 任意变动却保持同一 hash。可选策略由 Codex 审阅：

- **兼容保留**：v0 保留 exact `physics_dt × substeps`；vNext 把 task-level required `control_dt` 与 Provider native dt/profile 区分，vNext 通过 C/D admission 检查兼容性。
- **边界策略**：若暂不能证明新时间模型与现有 Guard/Recorder 兼容，vNext 先保留现有 Timebase 并标注后续迁移，不得提前承诺跨 dt 同一任务等价。

Experiment、Provider、Controller 的具体实例参数、Policy/Training Budget、Rollout Count 不应暗改 Frozen Task Identity；如果某 Controller/Terminal Policy 直接改变 benchmark 评估条件，则其合法范围需在 Artifact 或正式 Evaluation Contract 声明，并在 Execution Provenance 记录具体选择。

## B.7 五个 Implementation Goals

### B01 — YAML Task Source / Hook Declaration

- **依赖**：A05。
- **任务**：复用 `load_yaml_mapping` 与现有 TaskDefinition Source 路线，引入严格 Task Source Schema；无未知字段静默接受；定义 hooks 的允许位置/依赖声明。
- **验收**：相同 YAML 解析结果确定；未知 key/type/role fail-closed；无 Provider import；当前 PickCube 样例可**通过兼容适配**加载，不改变其冻结 v0 Artifacts。
- **风险**：YAML Schema 与 `ResolvedEnvConfig` 重复，或把 executable hooks 当成通用 Python 包机制。
- **Codex AUDIT Prompt**：列出当前任务 config 中 `recipe`/`environment` 与新 task-source 字段的映射差异，提出可增量迁移的最小 schema。

### B02 — Role Binding / Scene Variant / Deterministic Reset

- **依赖**：B01；A 的 Entity Identity/Frame。
- **任务**：Role Cardinality/Selector 与 per-reset immutable RoleBinding；初始化参数 hard bounds、sampler/version；Sample/realized provenance。
- **验收**：同 Task Seed 生成相同 Role/Sample；非法 cardinality/不存在资源/overlap policy 失败；Provider 不替换 sample；记录 Role IDs；无隐式 settle。需要 native 实现时先保留 D materialization TODO，不伪称已实测。
- **Codex AUDIT Prompt**：对比现有 `ResetSample`、`RealizedInitialState`、PickCube `sample_reset` 与 NutAssembly `NA-S0`，确定需新增的最少字段和 version strategy。

### B03 — Typed Predicate / Temporal Evaluator

- **依赖**：B02。
- **任务**：统一 Task Evaluation pure/stateful 规范、Predicate evaluator、Temporal Memory、`unavailable` 处理；不直接决定 `terminated/truncated`。
- **验收**：sequence/dwell/rising-edge 合成 trace 的 exact state transitions；Reset 清除 Memory；缺测/clock gap 失败或清连续性；zero/invalid state 不被当 Success；现有 PickCube lift-only 成功条件不改变。
- **Codex AUDIT Prompt**：先比较 `TaskLifecycleAdapter` 与 `task_env/tasks/guarded_transition.py`，只复用可复用语义，不把 Expert Guard 偷换成一般 Task Predicate。

### B04 — Existing TaskArtifact vNext / Identity Migration

- **依赖**：B01–B03。
- **任务**：将声明语义版本化保存至现有 Artifact；含 role/sampling/hook/time/evaluation 身份；严格 codec/hash；保护 v0 source hashes 与 data readers。
- **验收**：旧 Frozen Artifact 反序列化前后内容/Hash 与发布基线相同；vNext roundtrip/hash deterministic；ExecutionSpec 的 provider 替换不改变 Task Semantic Identity；试图覆盖 Frozen 字段必须新版本或拒绝；compatibility behavior documented。
- **Codex AUDIT Prompt**：评审 timebase v0 拆分方案是否会影响 `materialize()` 精确 dt gate；缺真实兼容证据可选择 defer，仅输出有限的新版 Artifact。

### B05 — Reference Task Semantics Migration / Gate

- **依赖**：B04。
- **任务**：迁移或桥接 PickCube 与 NutAssembly 的 Task Semantics、Role/Reset，而不抢先把 Solution/Controller/Guard 合并进新 Task 定义；保留 task.py/solution.py 的职责区分。
- **验收**：相同冻结 Sample 下 success/reward/metrics 与受保护 baseline 等价；NutAssembly success ≠ 11-stage Expert Completion；旧 reference env 仍可调用，任何 physical behavior drift 有归因。新增 `TaskArtifact` 不继承旧 identity（除非旧 bytes 完全不变）。
- **Codex AUDIT Prompt**：提供“旧 predicate/参数 → 新 predicate/参数”的逐字段对照及 sample trace；未证明的近似必须标明。

## B.8 验收 Oracle 与质量标准

| 维度 | 优先 Oracle | 最小证据 |
| --- | --- | --- |
| YAML/Hook Contract | strict schema、CODE hash | S0/S1 单元测试、坏字段拒绝 |
| Role Binding | 固定 seed + 冻结 Scene identity | 重放选择与 cardinality |
| Initialization | Frozen ResetSample + Realization tolerance | S1 sampler；适用时 S2 provider microprobe |
| Temporal Semantics | 手写确定性 timeline（含缺失点） | S1 time/edge/dwell/sequence 对照 |
| v0→vNext Artifact | 原发布字节/Hash + strict codec | legacy fixtures + new codec roundtrip |
| PickCube/NutAssembly | 既有有界评估 route 与对应 Evaluation Outcome | 定位准确的 S2/S3，未跑不算 pass |

**禁止以 Expert 执行失败直接判定 Task 不可行**；同样不能以一次 Expert 成功证明全 Reset Distribution 可行。完整 randomized feasibility 与冻结审批归 E，因此本轮 B05 仅做足以保护核心语义的有界回归。

## B.9 参考项目

| 项目 | 对 B 有效的借鉴 | 限制 |
| --- | --- | --- |
| [robosuite](https://github.com/ARISE-Initiative/robosuite) | Task+Arena+Object+Robot 模块化组合、Success/Reward 的清晰位置 | 不直接把 MuJoCo Model/Observable 写进 Canonical Task Artifact |
| [RoboCasa](https://github.com/robocasa/robocasa) | 大规模家居任务的 Scene Variant、对象选择和参数化生成 | 完整生成系统属于未来 Task Harness，不进入 B 的核心 Runtime |
| [ManiSkill](https://github.com/mani-skill/ManiSkill) | 清晰的 task initialize/evaluate/obs 与注册定义 | GPU batch lifecycle 不代表本轮必须实现 |
| [Isaac Lab](https://github.com/isaac-sim/IsaacLab) | Config-driven task specification、可组合检测/评价 terms | 不照搬其 Manager/Config 大型继承层级与物理耦合 |
| [LIBERO](https://github.com/Lifelong-Robot-Learning/LIBERO) | BDDL/语言目标和具名物体条件的任务声明思想 | 不把自然语言语义作为自动可执行的精确成功 Oracle |

参考优先级：**ManiSkill 的 Task 分层 + RoboCasa 的对象选择/变体 + LIBERO 的具名目标表达**；适配以 GeoChora Frozen Artifact/Predicate 定义为准，不以外部 benchmark 原生 reward 作为唯一 Oracle。

## B.10 Codex 审阅问题与出口

1. 现有 `SemanticDefinition` 是否可安全承载时序规则，还是需要有版本的 typed predicate node？如何避免重复 Evaluator？
2. Role Binding 应附着在 ResetSample、Episode Metadata 还是二者中仅留哈希引用？如何避免两个 Owner 写入？
3. Hook 源代码版本变化对 Frozen Artifact 的 hashing 和 source recovery 怎样明确记录？
4. `task-artifact-v0` 如何做到全量、字节级兼容；迁移路径何时需要显式版本升级？
5. `Timebase` 区分 Task Demand / Physics Execution 是否本阶段具备真实验证，哪些必须 defer？
6. 双机器人/复杂 Scene 的 Role Selector 何处解析？不能让 Task 每次依据 Provider object id 直接查询。

**B 阶段出口**：一个声明式 Task 能经 A 的 Scene 解析出冻结语义、per-episode ResetSample/Role Binding，并对 D 规范化 State 做 Task Evaluation；**并不**要求完成统一任务作者工作流、自动 Judge 或跨 Provider 正式 Qualification。
