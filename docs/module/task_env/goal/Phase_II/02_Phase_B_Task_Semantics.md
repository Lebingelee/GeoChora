# Phase B — Task Representation & Semantics：架构、实施切片与验收

> **PROPOSED / READY FOR SECOND REVIEW；仅修订规划，不等于新的 Task Artifact 已实现或已批准冻结。**
> 修订于 2026-10-20；源码基准 `develop@f292df149f41520b484ff27cf2ff78a584903013`，v1.1.0。
> 相关文件：[`00_Phase_II_AD_Implementation_Blueprint.md`](00_Phase_II_AD_Implementation_Blueprint.md)、[`01_Phase_A_Core_Object_Model.md`](01_Phase_A_Core_Object_Model.md)。

## B.0 阶段目标与四条已达成的设计决议

**目标**：允许用户基于 A 的 Scene/Entity/Frame，以 **YAML 为主要声明格式 + 有约束的 Python Hooks** 定义 Task Roles、Reset Distribution、Success/Failure/Reward、时序语义和 Action/Observation Requirements，最后将稳定的语义内容汇入**现有** TaskArtifact，供 C/D Execution 使用。

**不做**：自然语言 Task 自动创作、Task Harness、自动审批冻结、通用 Policy Runner、自动将任何 benchmark 无损转换为 Task。Python Hook 约束不是恶意代码安全沙箱。

本轮沿用此前 B-R1–B-R4：

- **B-R1 Role / Sampling**：Task Role 的 selection rule/cardinality/randomization 进入冻结声明；每 Episode 在 Core reset 时解析成不可变 Role Binding，并记录 provenance。
- **B-R2 Stateful Semantics**：`(memory_next, evaluation) = F(evaluation_context, memory, frozen_params)`；
  context 显式含前后 canonical state、所声明的 action 层与 measured interval。按 sampling contract 一次提交；
  只读 observation/diagnostics 不推进记忆。缺失 State 是 unavailable/error，而不是 `False`。
- **B-R3 YAML + Restricted Hooks**：声明式为主；Python Hooks 仅做已声明的 Authoring/Initialization/Semantic 扩展，确定性要求、State/Capability Dependencies、版本/内容 hash 必须显式。
- **B-R4 Frozen Artifact / Experiment 分离**：任务定义与 Evaluation Contract 归 Artifact；Provider/Policy/样本次数/训练预算/rollout/record 配置归 Experiment/Execution；不新建第二个 Artifact 系统。Task 的时间需求与原生 Physics `dt` 的拆分需保护旧 `Timebase` v0 身份。

## B.1 当前代码真实状态与演进风险

| owner / 路径 | IMPLEMENTED（当前事实） | 计划差距 |
| --- | --- | --- |
| [`task_env/artifacts/contracts.py`](../../../../../task_env/artifacts/contracts.py) | `TaskArtifact(task-artifact-v0)`，`WorldDefinition`、`InitializationContract`、`SemanticDefinition`、`Timebase`、`RequiredCapabilitySet`，strict hashing | Frozen Roles/Temporal Semantics/Hook Identity/Requirements 需**版本迁移**，不能静默扩 v0 bytes |
| [`task_env/artifacts/execution.py`](../../../../../task_env/artifacts/execution.py) | `ResetSample(reset-sample-v0)`、`RealizedInitialState` | Scene Variant/Role Binding 的 per-episode identity/provenance 尚非通用契约 |
| [`task_env/tasks/pick_cube/`](../../../../../task_env/tasks/pick_cube) | task.py/solution.py/config.yaml，lift-only success 及任务随机化 | 语义及 reset recipe 适配新声明系统，不改历史 task identity |
| [`task_env/tasks/nut_assembly/`](../../../../../task_env/tasks/nut_assembly) | Task Semantics、11-stage Solution、Guard、Outcome Completion V1 | 分开 Task Success 与 Expert Completion；不通过 B 更改 Guard Controller |
| [`task_env/environment/task_definition.py`](../../../../../task_env/environment/task_definition.py) | 既有 TaskDefinition/TaskStateView/evaluation 路线 | 归一化 Semantic Evaluator 输入与反馈；不能绕开已有 TaskDefinition |
| [`task_env/environment/lifecycle.py`](../../../../../task_env/environment/lifecycle.py) | TaskLifecycleAdapter reset/evaluate/obs normalization | B 仅提供 Evaluation Contract，终止策略执行归 C |
| [`task_env/environment/configuration.py`](../../../../../task_env/environment/configuration.py) | YAML loader/strict config 合并等 | 复用现有 loader；明确 new source schema 与 frozen compiled artifact |

**特别风险**：目前先进路径把 `physics_dt × control_substeps` 纳入 `TaskArtifact.timebase`。以前讨论希望任务只声明所需控制/评价时间需求，但若在 B 直接删除 physics_dt，就会破坏已发布 hash 与 Provider Source Admission。必须版本化并同时保护旧 decode/execution。

### B.1.1 审阅补充：已有语义与待实现契约

- [PendulumTaskDefinition](../../../../../task_env/tasks/pendulum.py#L316-L333) 已有 scalar/batch 语义记忆；
  [torque cost](../../../../../task_env/tasks/pendulum.py#L169-L189) 依赖 action。
  B03 复用 TaskDefinition 的 action/previous_state/elapsed_steps 路线，不仅用瞬时 pose 重写全部评价。
- selected [observation()](../../../../../task_env/tasks/reference_env.py#L157-L169) 内直接 evaluate，
  [native Guard callback](../../../../../task_env/tasks/reference_env.py#L203-L225) 还会再次调用它。
  无状态实现可这样读取；stateful evaluator 不可直接替换，否则每个 outer step 多次提交 memory。
- [ResetSample](../../../../../task_env/artifacts/execution.py#L19-L62) 的 v0 control/velocity policy
  带机械臂约束，CanonicalStateView 仅标量 joint map；version plan 必须覆盖 nested codecs/readers，
  不仅 TaskArtifact 外层字符串。RealizedInitialState 容器也不等于已执行 tolerance gate。
- 新版声明可以是可解析 candidate。frozen 状态仍按
  [现有 Stage-1 contract](../../task-artifact.md#任务-contract-与冻结) 产生 validation、
  randomized feasibility 和 Human Judge。Harness 延后不豁免这些要求。

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
Reset(seed + admitted episode identity) → Core selection/Role Binding → ResetSample
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

**首个基线决定**：只执行固定拓扑的 Role/pose randomization。候选集合排序、各随机量的 RNG stream/domain、
sampler/version 和 sample 内容进入 provenance，不让新增 role 改变无关采样序列。拓扑变化保留为显式
unsupported/deferred；以后需要它时，新建 Env/SceneInstance 并重建依赖 spaces 的 wrapper，或独立设计有界 mask。
不能在 reset 中静默改变 action/observation shape；原声明不得因此被自动标为 supported。

## B.4 Temporal Semantics：有状态但不依赖 Solution

推荐 Formal Contract：

\[
(m_{t+1}, e_t) = F(c_t^{\text{evaluation}}, m_t, \theta_{\text{frozen}}),
\quad e_t=(r_t,\text{success}_t,\text{failure}_t,\text{metrics}_t).
\]

Semantic Memory 的 Owner 是 Task Semantic Evaluator，不是 Controller、Solution、Recorder。独立 Solution 可以有完全不同的规划 Stage。

Evaluation Context 包含已声明的前后 state、requested/canonical/applied action 层、有效 measured interval、
episode/boundary/sample identity；字段缺失不得隐式补零。选择哪一 action 层计算 effort/reward 属冻结语义。
Evaluator 每个合法 semantic sample 只提交一次；重复/乱序提交需幂等读取或明确拒绝，不能再累计 dwell。
Native Guard 的只读物理判据与 outer Task Evaluation 分开；渲染、observation、诊断不得改变 memory。
无 evaluator、unavailable 和已评价为 False 是三个状态，vNext 要有明确有效性表示及 v0 compatibility projection。

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

Hook 变更涉及语义时须新 Artifact Identity；记录可恢复的 source reference、所需文件/资源的内容 hash、
依赖版本和参数，而不是只记函数名或单个文件 hash。Authoring hook 编译结果也进入规范化身份。
源码/依赖闭包无法恢复时，标记不可复现/不准正式 benchmark；不新建包管理器或声称 Python 安全沙箱。

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

**本轮 Timebase 决议**：首个 vNext 基线保留既有 exact Timebase，包含 native dt/substeps/sampling。
将 task demand 与 native dt 完全拆分仍是后续有版本的扩展，需独立 Guard/control/recorder Evidence；
不得把相同 control_dt 当作跨 native dt 等价。以下为未来扩展边界，不是本次实现的自由选择：

- **兼容保留**：v0 保留 exact `physics_dt × substeps`；vNext 把 task-level required `control_dt` 与 Provider native dt/profile 区分，vNext 通过 C/D admission 检查兼容性。
- **边界策略**：若暂不能证明新时间模型与现有 Guard/Recorder 兼容，vNext 先保留现有 Timebase 并标注后续迁移，不得提前承诺跨 dt 同一任务等价。

Experiment、Provider、Controller 的具体实例参数、Policy/Training Budget、Rollout Count 不应暗改 Frozen Task Identity；如果某 Controller/Terminal Policy 直接改变 benchmark 评估条件，则其合法范围需在 Artifact 或正式 Evaluation Contract 声明，并在 Execution Provenance 记录具体选择。

## B.7 五个 Implementation Goals

父编号不变；B03/B04 的后缀切片及跨阶段顺序见 [执行表](05_Architecture_Review_and_Execution_Order.md#3-切片依赖与推荐执行顺序)。

### B01 — YAML Task Source / Hook Declaration

- **依赖**：A05、B04a，以及 D01a/D02b 的最小真实闭环；不是要求完整 D 阶段先完成。
- **任务**：复用 `load_yaml_mapping` 与现有 TaskDefinition Source 路线，引入严格 Task Source Schema；无未知字段静默接受；定义 hooks 的允许位置/依赖声明。
- **验收**：相同 YAML 解析结果确定；未知 key/type/role、重复 mapping key fail-closed；
  无 native Provider import；当前 PickCube 可通过兼容适配加载，不改 v0。保留既有 loader/merge owner，
  明确新 Task Source 与 Execution Config 的字段边界，不把 safe_load 当完整 strict semantic parser。
- **风险**：YAML Schema 与 `ResolvedEnvConfig` 重复，或把 executable hooks 当成通用 Python 包机制。
- **Codex AUDIT Prompt**：列出当前任务 config 中 `recipe`/`environment` 与新 task-source 字段的映射差异，提出可增量迁移的最小 schema。

#### B01 bounded source and hook declaration slice (2026-10-20)

在 `task_env.environment` owner 中新增 provider-free `TaskSourceV1`、严格 loader 和 hook metadata contract；
这是 authoring input，不是新 TaskDefinition runtime、TaskArtifact 或 config resolver。首版只收
`identity`、Canonical Scene ref、Role declarations 与 Hook declarations；初始化/语义/交互/time requirements
仍由后续 B02/B03 slices 扩展。未知字段和 schema/version/type/cardinality/role/hook placement 不匹配均拒绝。

为贴合当前 A Scene owner，Role selector 只接受显式 Entity-ID 候选列表；不接受 tags，因为 canonical
`EntityInstance` 尚无 tags/selector metadata owner。B02 可直接在这些候选上实现确定性 reset selection，候选必须
在 A Scene 中解析；不得为此另建 tags registry。当前 parser 的 cardinality 限于 `exactly_one`；更广 cardinality
仅在 B02 的实际需求和 oracle 明确后加入。`entity_type` 是 Task Source selector 的受限提示，B02 必须用 A03
`RobotInstance`/Entity refs 验证候选，不构造第二份 Scene taxonomy。

Hook declarations 仅记录 kind、稳定 ID/version/code hash、输入、capability dependencies、determinism、phase
及 pure/stateful 标记。authoring/initialization/semantic 分别绑定 source_compile/reset_sample/evaluation_boundary；
seeded hook 必须声明 `task_seed`，前两类必须 pure。任何 Hook 都不动态 import 或执行；其可恢复源码闭包和最终
TaskArtifact identity 归 B04b 收敛。

既有 `environment.configuration.load_yaml_mapping()` 继续是公共 YAML loader；现增加 SafeLoader duplicate-key
拒绝，并保留 YAML merge-key 的本地覆盖语义。当前 PickCube legacy adapter 只投影 recipe 中的 task/version/Scene
和固定 agent/object IDs，`environment` 仍留给原 config resolver，且不重写 TaskArtifact v0。
定向验证：`task_env/diagnostics/tasks/test_phase_ii_b01_task_source.py` 6 passed；与 B04a legacy fixtures、C01a
config/execution-plan、reference construction 合计 **35 passed**。子进程 import probe 未加载 GeoPhys/MuJoCo/SAPIEN/
Genesis/Taichi；尚未执行任意 Hook、Role resolution、Artifact compilation 或 native runtime。

### B02 — Role Binding / Scene Variant / Deterministic Reset

- **依赖**：B01、B04a、D01a、D02b；A 的 Entity Identity/Frame。
- **任务**：Role Cardinality/Selector 与 per-reset immutable RoleBinding；初始化参数 hard bounds、sampler/version；Sample/realized provenance。沿用现有 `ResetSample` v0 与 `RuntimeSession`，只增 plan wrapper 和 rollout gate。
- **验收**：同 seed/version/Scene 得到相同 Role/Sample；候选重排与独立 RNG domain 可测；
  非法 cardinality/资源/overlap 失败；Provider 不替换 sample；requested/realized tolerance 在 rollout 前核验。
  `RuntimeSource` Scene hash 不匹配、Artifact 声明 topology 缺失或 reset realization 超 tolerance 必须 fail closed；
  缺 D01a realization 证据不得将完整 B02 标完成；拓扑变化必须明确拒绝。
- **Codex AUDIT Prompt**：对比现有 `ResetSample`、`RealizedInitialState`、PickCube `sample_reset` 与 NutAssembly `NA-S0`，确定需新增的最少字段和 version strategy。

#### B02 bounded Role/reset-plan slice (2026-10-20)

此切片只扩展现有 `task_env.environment.TaskSourceV1` 与 `task_env.artifacts.execution`：增加可选的
`TaskInitializationV1`、`RoleBindingV1` 和 `EpisodeResetPlanV1`。B01 未含 initialization 的 YAML 仍可读取；
只有构造 reset plan 时才要求初始化声明。Role selector 仍限显式 Entity IDs 和 `exactly_one`；按规范化候选
与 per-role `SHA-256 → PCG64` domain 选取，增加无关 disjoint role 不改变既有 binding。

Role resolution 要求显式传入精确 task/version 对应的 TaskArtifact v0 和 Scene ref；全部 Artifact Entity 及其声明的
Frame/Joint 子拓扑都必须在 structured A Scene 中找到，即使某实体不是本轮 Role 候选也不能漏掉。`robot` 候选必须
是 A03 `RobotInstance` 且 Artifact kind 为 `embodiment`；`rigid_body` 候选只接受 Artifact `static`/`movable` kind。
Scene identity hash 绑定完整结构及 Scene variant。
此处不把 A AssetDeclaration identity 与旧 Artifact `asset_reference` 混成一个身份 owner；A04/D01a 继续负责源资产
映射和 importer evidence。随机化只读取现有 `InitializationContract.randomization`/`UniformDimension`：`pcg64-v0`
复用 PickCube 的顺序 PCG64 draw、`pcg64-domain-v1` 为每个 dimension 独立派生 RNG、`frozen-authored-v0`
只接受空随机化集；其余版本显式拒绝。现支持位置 x/y/z 与已声明 semantic/role joint position，其他 dimension
语义保持 unsupported，不猜测映射。

`EpisodeResetPlanV1.to_provider_sample()` 返回原有同一 `ResetSample` v0；不改旧 Artifact、sample hash 或 Provider reset ABI。
现有 `RuntimeSession.reset_plan()` 先确认 materialized source ID 与 plan 所绑 Scene hash 相同，再调用原 `reset(sample)`；
只有既有 `validate_reset_realization()` 的 requested/measured tolerance 通过，session 才开放后续 snapshot/step。
传统 `reset(sample)` 入口仍可用，显式走 B02 的调用方应使用 `reset_plan()`。

定向验收：`test_phase_ii_b01_task_source.py` 与 `test_phase_ii_b02_reset_plan.py` **13 passed**，覆盖
候选重排、RNG domain 隔离、包括非 Role Artifact Entity 在内的 Scene/Artifact topology 缺口、rigid_body/Robot 类型错配、
resolver 缺失 TaskArtifact 的拒绝、overlap、hard bounds、reset plan identity、Scene hash gate，
以及 GeoPhys/MuJoCo CPU 三自由刚体 reset；并逐字段确认现有 PickCube PCG64-v0 和 NutAssembly NA-S0
factory sample 与 plan 中的 ResetSample v0 完全相等。`test_b02_plan_consumes_the_exact_a05_v3_scene_identity`
在 D01a 已验证的 A05 v3 Scene/source-closure 路径上另通过 GeoPhys reset-plan gate；这个集成 probe 使用固定
authored initialization，不代表 A04 importer 已验证任意 free-body topology。三自由刚体随机化 probe 使用直接构造的
bounded MJCF source 与 Scene-v2 identity，不代替真实 Asset import/closure 证据。新增 reset-plan gate rejection 使 session 在 rollout 前锁定；
合并重跑 B01/B02/D01a/D02b 四个定向文件的最终命令 **20 passed**；B04a/C01a/reference construction 回归
**29 passed**。GeoPhys 用例有 Taichi 上游 `locale.getdefaultlocale` 弃用警告。证据仅覆盖 candidate Artifact、
固定 topology、CPU 和两个已实测 Provider；
不代表 freeze/Judge、完整 PickCube/NutAssembly rollout、通用 importer free-joint projection 或 SAPIEN/Genesis 支持。

### B03 — Typed Predicate / Temporal Evaluator

- **切片**：B03a 扩展既有 TaskDefinition 的只读 typed predicates/action context；B03b 增加受限 temporal memory/提交规则。依赖 B02/D02b，B03b 另需 B03a。
- **验收**：除 sequence/dwell/rising-edge trace 外，必须保护 Pendulum action cost 和已有窗口；
  reset 清 memory；重复 observation/diagnostics 不推进语义；同 boundary 重复/乱序 commit 拒绝或幂等；
  native Guard 读取不当作 outer sample；missing/no-evaluator/False 可区分，PickCube lift-only 不变。
- **Codex AUDIT Prompt**：先比较 `TaskLifecycleAdapter` 与 `task_env/tasks/guarded_transition.py`，只复用可复用语义，不把 Expert Guard 偷换成一般 Task Predicate。

<a id="b03a-read-only-predicate-action-interval-context"></a>

#### B03a — 只读 Predicate 与 Action/Interval Context（2026-10-20）

在现有 `TaskDefinitionBase` 与 `TaskLifecycleAdapter` 上增加显式只读入口，没有新增 predicate engine 或第二套 evaluator：
`TaskEvaluationContextV1` 包含当前/前一 `TaskStateView`、typed requested action/schema、既有 `AppliedControl`、elapsed step、
已有 `Timebase` 和可选 `NativeIntervalEvidence`；action payload 为复制后的只读值。声明 cadence 与 measured interval 分开，
未提供 interval evidence 时不从配置或 sample 数推导“实测”时间。`TaskLifecycleAdapter.evaluate_predicates()` 必须由调用方显式调用，
step、observation 和 diagnostics 路径不会暗中触发，也不提交 task memory。

`TaskPredicateEvaluationV1.resolve()` 返回 `available` + bool value（False 不是缺测）、`unavailable`（含明确原因）、
`no_evaluator` 三类可区分结果；已声明 evaluator 未产出某名字时为 `unavailable/predicate_not_produced`。
PickCube `cube_lifted` 逐项复用 `_evaluate_values()`，成功仍仅由 lift 决定。Pendulum 只读暴露瞬时 `upright`；
纯读取不会推断其依赖窗口的 `task_success`，B03b 可在单独 temporal commit 中给出该结果。
旧 `TaskDefinition.evaluate()`、Pendulum torque-cost、scalar/batch 五步窗口、PickCube reward/metrics 和 selected-reference
native Guard 回调不变。Expert Guard 仍归 task solution，不成为通用 Predicate API。

定向验收 `test_phase_ii_b03a_predicates.py` 覆盖 requested/applied action 区分所依托的既有值类型、action 只读复制、声明/实测
interval、false/missing/no-evaluator 区分、PickCube lift-only oracle 和 Pendulum scalar/batch 重复只读调用不推进窗口，且核对
torque cost 与第五步 success。与 `test_reference_construction.py`、`test_selected_consumers.py` 一起 **50 passed**；
另与 B01/B02/D01a/D02b 四份依赖切片一起 **25 passed**（含一条 Taichi 上游 deprecation warning）。本切片不构成新 task/provider qualification。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=GeoPhys/src:. python -m pytest -q -p no:cacheprovider \
  task_env/diagnostics/tasks/test_phase_ii_b03a_predicates.py \
  task_env/diagnostics/tasks/test_reference_construction.py \
  task_env/diagnostics/tasks/test_selected_consumers.py
```

<a id="b03b-bounded-temporal-memory-boundary-commit"></a>

#### B03b — 有界 Temporal Memory 与显式边界提交（2026-10-20）

继续扩展 `TaskDefinitionBase` 与 `TaskLifecycleAdapter`，不改变任何 provider/runtime 或 reward evaluator：TaskDefinition
只声明 `TemporalPredicateRuleV1`（`rising_edge`、连续 outer-sample `dwell`、有序 rising-edge `sequence`）；可变进度和
last-commit identity 由其现有 `TaskLifecycleAdapter` 持有，并随 `reset_task()` 清除。暂不扩展成 Artifact DSL、
continuous-time guard 或新的 state manager。`commit_temporal_predicates()` 是唯一推进点，必须提供既有
`StateBoundaryIdentity` 与 evaluation-boundary `StateSampleClock`；单纯 `evaluate_predicates()`、observation、诊断读取、
Runtime native substeps 均不推进 temporal memory。

精确相同 boundary/input 重复 commit 幂等回传同一结果；同 boundary 的状态/action/interval/predicate 变化拒绝，乱序拒绝。
control-step gap、missing/unavailable source 与 reset 清除相关连续进度；identity 更换未经过 reset 也拒绝。Dwell 的
`required_samples` 明确为 evaluation-boundary 数，非物理秒/native substep；sequence 以不同 boundary 上的 rising edge 顺序匹配，
baseline 缺失、同时 edge 或缺测不伪造成功。Temporal commit 当前限 scalar evaluation boundary，batch 只保留 B03a 的只读
predicate array；在没有 per-environment boundary identity 前 fail closed。

Pendulum 声明 `upright` 的五-sample dwell 输出 `task_success`，只在 explicit commit 结果中可见；既有
`PendulumTaskDefinition.evaluate()` 仍是 reward/success 的当前 owner，`torque_cost` 与 scalar/batch `_upright_steps`
窗口原样保留。对同一输入 trace，定向测试逐步比较 temporal `task_success` 与旧 reward oracle；测试还覆盖 dwell/sequence/edge、
25 个重复 predicate reads 后仅一次 commit、重复 commit、冲突 boundary、乱序/gap/missing/reset、native interval 内
25 个 substeps 只计一个 outer sample。selected Expert Guard 与 native callback 不接入此提交点。

`test_phase_ii_b03b_temporal_commit.py` **15 passed**；覆盖全部公开 `RuntimeSnapshot` 字段的重复 boundary 指纹，
以及 action/applied-control/Timebase/NativeInterval/predicate 输入冲突和 no-evaluator 清进度。与 B03a、reference
construction 和 selected consumers 合计 **65 passed**。B01/B02/D01a/D02b 与 B03a/B03b 六份定向文件合计
**40 passed**，含一条 Taichi 上游
`locale.getdefaultlocale` 弃用警告。当前仅是 scalar boundary 的 S1 语义契约/旧 consumer 回归，不代表有真实 provider
输出 NativeIntervalEvidence、batch temporal commit、TaskArtifact 序列化、selected native callback 集成或 qualification。
下文 B04b/B05 的 aggregate 数字记录各自先前运行；本次 B03b follow-up 未重跑那两组更宽的组合。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=GeoPhys/src:. python -m pytest -q -p no:cacheprovider \
  task_env/diagnostics/tasks/test_phase_ii_b03a_predicates.py \
  task_env/diagnostics/tasks/test_phase_ii_b03b_temporal_commit.py \
  task_env/diagnostics/tasks/test_reference_construction.py \
  task_env/diagnostics/tasks/test_selected_consumers.py
```

### B04 — Existing TaskArtifact vNext / Identity Migration

- **切片**：B04a 在 A02 后先交付 schema/version/read-write/migration 矩阵与 legacy fixtures 策略；
  B04b 在 B01/B02/B03b 后实现声明编译、codec/hash，沿用 TaskArtifact owner。
- **覆盖范围**：World/Scene、ResetSample/Role、RealizedInitialState、State、ExecutionSpec、
  Timebase、CapabilityManifest、Camera 以及三类 trajectory metadata/readers 的嵌套引用。
  ExecutionSpec 当前无 schema discriminator；新版本路由必须有明确识别，不靠猜 key 静默转换。
- **验收**：旧 Frozen Artifact 反序列化前后内容/Hash 与发布基线相同；vNext roundtrip/hash deterministic；ExecutionSpec 的 provider 替换不改变 Task Semantic Identity；试图覆盖 Frozen 字段必须新版本或拒绝；compatibility behavior documented。
- **补充 Gate**：存储原文件 bytes 保持只读；codec 比较规范化 mapping/hash，不能误把 YAML 格式化后字节视为原文件。
  Legacy decode/new write/explicit migration/reject 的组合逐项可测；新增 segmentation 等 capability 不扩权旧 manifest。
- **Codex AUDIT Prompt**：评审 timebase v0 拆分方案是否会影响 `materialize()` 精确 dt gate；缺真实兼容证据可选择 defer，仅输出有限的新版 Artifact。

#### B04a — 当前版本/读写/迁移矩阵（基线，不是 vNext 实现）

本切片仅冻结当前事实与下一版路由规则；当前生产 schema 不改，不为没有消费者的字段添加 discriminator，也不建立第二套 Artifact/Recorder owner。

| Contract / data family | 当前版本与身份 | 当前读写者/真实调用 | B04a 兼容规则与后续版本策略 |
| --- | --- | --- | --- |
| TaskArtifact / World | `task-artifact-v0`；嵌套 `world-v0`、`initialization-v0`、`semantics-v0`；`identity_hash` 是完整 `to_mapping()` 的 sorted compact JSON SHA-256 | `TaskArtifact.from_mapping()` strict decode；PickCube/NutAssembly `build_artifact()` 构造；没有统一 artifact 文件 writer/reader | v0 codec、mapping、identity 原样保留；`from_mapping()` 不自动升级。单一 artifacts-owner dispatcher 按精确 `schema_version` 选择 v0 或未来 decoder，缺失/未知版本拒绝。显式 v0→v1 migration 只产生新 Artifact/新 identity，并回报每字段去向；不得覆盖原 bytes 或自动标为 frozen。 |
| Scene / World mapping | A owner 的 `scene-definition-v1/v2/v3` 与 B Artifact 的 `world-v0` 是不同 contract；SceneDefinition 每个版本有独立 strict field set | `SceneDefinition.from_mapping()` 按 `schema_version` 验证；Artifact `WorldDefinition` 仍存其自身的 entity mapping | 不把 `world-v0` 伪装为 `scene-definition-v3`。vNext TaskArtifact 应显式引用 Scene identity/version；迁移不能复制第二份 Scene owner。 |
| Reset / Role | `reset-sample-v0`；sample ID 由除 `sample_id` 外的 canonical mapping 得出，含 frozen Artifact hash；通用 RoleBinding/SceneVariant 尚未实现 | `ResetSample.create()` 归一化后计算 identity；`from_mapping()` strict decode；PickCube/NA-S0 `sample_reset()` 是实际 caller | v0 的采样语义和 hash 不改；新 RoleBinding/Variant 使用有版本的独立值，不能把字段 append 到 v0 或从字段形状猜测版本。旧 sample 仅按 v0 解码；migration 显式记录源 Artifact/sample identity。 |
| Realized state / canonical state | `realized-initial-state-v0` 嵌入 `canonical-state-v0`；state 是标量 joint position/velocity 与 `pose_world` map | `RealizedInitialState.from_mapping()`、P1.2 runtime receipt、canonical trajectory reader | v0 保持 strict 且不 reinterpret 为 typed multi-DOF state；vNext 如改变 state representation 必须新 discriminator，并由其 Episode/trajectory parent 明确选择。 |
| ExecutionSpec / Timebase | ExecutionSpec 没有自身 discriminator；Timebase 也没有。TaskArtifact Timebase 固定 `physics_dt × control_substeps == control_dt`（容许 1 ULP），并显式记录 action/sampling policy | 两者是 strict `Contract.from_mapping()` 子对象；EpisodeMetadata v0 嵌入 ExecutionSpec/Timebase；TaskArtifact v0 嵌入 Timebase。ExecutionSpec 不在 TaskArtifact identity 内 | 旧映射缺少版本字段是合法 v0 事实，不得回填字段以“补齐”版本。未来新形状经明确的 parent v1 codec 路由，或采用单独 versioned child；不得根据 key 集合猜测。Provider 替换只改变 Execution provenance，不改变 Task Semantic Identity；Timebase native `dt/substeps` 在证明 Guard/materialize 兼容前不得拆除。 |
| Capability manifest | `provider-capability-v0`；CapabilityClaim 本身无版本，能力名称由固定集合校验 | `ProviderCapabilityManifest.from_mapping()` strict decode；`admit_capabilities()` 使用其声明 | 未知能力（含新 segmentation 等）在 v0 失败；不得扩展旧 manifest 的解释范围。新能力集合/字段由明确新 manifest version 承载，不授予既有 Evidence 新资格。 |
| Camera | `camera-observation-v0` 的 `CameraGeometry` 链接 TaskArtifact hash；`ResolvedCameraMetadata` 无 discriminator | `CameraGeometry.from_mapping()` strict decode；canonical camera resolve/project/back-project 使用者读其值 | 已冻结的 RGB/Depth convention 保持不变；新增 modality、capture timing 或 metadata 语义必须通过明确版本/parent route 读取，旧 camera 不能因 decoder 忽略未知字段而扩权。 |
| 通用 H5 trajectory | 默认写 `task-env-h5/v2`；另有显式 `geophys-transition-h5/v1` 兼容 config/写出分支。env metadata 新写 YAML，`load_metadata()` 仍接受历史 JSON 文档 | `save_trajectory_h5()`、collection writer、`inspect_trajectory_h5()`、replay/transcode/collection readers；`env_meta` 是普通 mapping，非 TaskArtifact codec | 不改变既有 H5 v1/v2 bytes/dataset。只在 container layout 或 reader semantics 改变时升级 H5 outer version；embedded mapping 的 YAML/JSON 原文件 bytes、normalized mapping 和 Artifact identity 分别记录。`inspect_trajectory_h5()` 当前是 summary reader，不等价于全语义 validator。 |
| Canonical trajectory | Logical `canonical-trajectory-v0` + `canonical-trajectory-metadata-v0`；H5 outer `task-env-canonical-trajectory-v0`，含 logical JSON 与核对用 numeric projection | `task_env.trajectory.canonical.h5.save/load()`；`CanonicalTrajectory.identity_hash` 覆盖 logical mapping | v0 outer/logical bytes 与 hash保持；nested metadata/state 改变必须有新 logical/outer 路由和 reader oracle，不得同名覆盖旧 file schema。 |
| Canonical execution stream | `canonical-execution-trajectory-v1` 为旧读版本；当前 writer 为 `canonical-execution-trajectory-v2`，H5 file 分别为 `task-env-canonical-execution-v1/v2`；v2 增加 versioned clock validation | resident 与 streaming save/load/validate 共用 logical mapping 和 semantic validators；当前 tracked `execution_prefix_fixture.json.gz` 是 v2 | 保留 v1 read path、v2 当前读写语义；未来 nested contract 改变需要新的 logical/file discriminator 和显式 reader dispatch。当前测试把 v2 fixture 的 schema 字段改成 v1 做 smoke，**不是原始 v1 bytes fixture**；B04b 前须取得真正历史 v1 bytes/hash，或把其 reader migration 标记 DEFERRED。 |

Scene/Task/Execution/Recorder 是不同版本域，`v1` 不代表全局兼容。新 TaskArtifact 由 exact top-level discriminator 选择 decoder；nested typed contracts 验证自己的 discriminator，未独立版本化的 child 由显式 parent codec 解释。未知版本/字段一律拒绝，不做“尽力读取”或默认回填。迁移 API 只能在调用点明确命名目标版本，并返回 `{source_schema, source_identity, target_schema, target_identity, field_dispositions}`；`SOURCE_RETAINED`、`APPROXIMATE`、`UNSUPPORTED` 必须可见，必需字段无安全投影时停止迁移。

#### B04a — Legacy fixtures 与本切片边界（2026-10-20）

新增 `task_env/diagnostics/tasks/fixtures/phase_ii_b04a/` 两份当前 PickCube/NutAssembly `task-artifact-v0` mapping fixture。测试分别 pin fixture 原文件 SHA-256、解码/重编码后的 mapping、canonical identity 和当前 builder 输出；另以不同 YAML bytes 解出同一 mapping，证明“原文件 bytes”不等同于 Artifact identity。现有 `reference_construction_baseline.json` 中 PickCube reset seed 11 继续作为 `reset-sample-v0` fixture。

已知 fixture 缺口需保留为明确 gate：仓库没有已发现的 `geophys-transition-h5/v1` 文件 fixture，也没有 `canonical-trajectory-v0` outer H5 golden file；canonical execution 的当前压缩 fixture 是 v2，现有 v1 测试通过改写其 schema 字段生成。B04b 若触及这些 reader，先从历史已保存的原始 bytes/已批准归档获取并 pin SHA-256；拿不到真实 v1 bytes 时只可保留/defer 旧 reader，不可把合成 v2 样本宣称为历史 v1 兼容证据。TaskArtifact v0 fixture 是 mapping fixture，不声称对应某个先前落盘文件。

B04a 只增加上述基线夹具与 strict compatibility tests，不改 production schema、TaskDefinition、Recorder writer/reader，不编译 Task Source，不迁移 Artifact。A04/A05 复测留待后续开发完善后执行；本切片的测试不替代它们。

#### B04a — source-bound Evidence 重建（2026-10-20，cmd-0001）

**状态：SELF_CHECKED_PENDING_REVIEW。** 在 `codex/phase-ii-b` 的受测实现 `f9543b8725d2990966743f49cebf9d68493b6b06`（tree
`ffd78e99f96f75c5c338fa9a297a7032a6d786c6`）上，仅重跑现有 provider-free S1 detector；GeoPhys pin 为
`4436787e9cb85ce519506a2a9af86d1eeec9de2d`，Menagerie pin 为
`b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。未改实现、测试或 fixture。测试命令：

```text
/home/lly/miniconda3/envs/geochora/bin/python -m pytest -q -p no:cacheprovider --basetemp=workspace/phase_ii_coordination/evidence/cmd-0001/worker/pytest-temp task_env/diagnostics/tasks/test_phase_ii_b04a_legacy_matrix.py
```

结果为 **6 passed, 0 failed, 0 errors**，exit 0、未 timeout；环境覆盖为 `PYTHONDONTWRITEBYTECODE=1`、
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`、`OMP_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1`、`MKL_NUM_THREADS=1`、
`NUMEXPR_NUM_THREADS=1`、`PYTHONPATH=GeoPhys/src:.`，预算为 wall 120s、单进程 CPU 90s、address space 8 GiB，
process-tree RSS 未设限。该检测覆盖两份 v0 fixture 的原 bytes/mapping/hash、canonical identity 和当前 builder 一致性、
nested contract roundtrip、未知版本/字段拒绝及独立 reader version routing；不能证明 provider/runtime 行为。

源码与原始结果引用如下（均为仓库相对路径）：

| Evidence | SHA-256 |
| --- | --- |
| 原始 stdout：`workspace/phase_ii_coordination/evidence/cmd-0001/worker/stdout.log` | `d23ba7a7244a561a7e47aaba2d7106faf62d830b682490b5adf75890ec6c60a8` |
| 原始 stderr：`workspace/phase_ii_coordination/evidence/cmd-0001/worker/stderr.log` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| 命令、环境、受测身份和计时：`workspace/phase_ii_coordination/evidence/cmd-0001/worker/run_metadata.json` | `7dd71a134e4878ee891d245f7bcb32464eb15e5cef213c279e14fe7f5fd4d788` |
| detector：`task_env/diagnostics/tasks/test_phase_ii_b04a_legacy_matrix.py` | `0550d3a66193f82c7ac8d455b711c8d0461cf9ae9f21e23aa918db9ebcfa4c62` |
| baseline：`task_env/diagnostics/tasks/reference_construction_baseline.json` | `96aad056c1a71c6448e43c3366304988e1d676099b7f215557304717f2cf962e` |
| PickCube fixture：`task_env/diagnostics/tasks/fixtures/phase_ii_b04a/pick_cube_task_artifact_v0.json` | `5ce44d4deaa30071fee0de3cb98aee17878c566e9f32b9216bd48b3e6934b135` |
| NutAssembly fixture：`task_env/diagnostics/tasks/fixtures/phase_ii_b04a/nut_assembly_task_artifact_v0.json` | `e25bb363bd9e6e59b41c0dd6b14316f2e840913c714cd0f4646df05e6374ea09` |
| 已验收静态前置：`workspace/maintenance/phase_ii_a_20261020_A02_004/a02_receipt.json` | `ced0dd3e610086bd722edb89f9a9968039dc769cadec1bad551d7e91739ef054` |

旧 aggregate `workspace/maintenance/phase_ii_next_gate_review_20261020_001/pytest.log`（SHA-256
`94c8336c73d87898fe7f00fc34ec0816311d4c75b5f748863eff0feddc87481c`，91 passed）及其
`review_receipt.json`（SHA-256 `b37aff9e14041cdb4e7c8955b9f568c970944b613bad129024021a9ddd38f8df`）绑定
`b24cd9707f27b70d09d28565125dd48f65444dd2`，没有当前全部 owner hashes，故不作为 `f9543b8` 的本轮验收证据。
`geophys-transition-h5/v1` 原始文件及 canonical trajectory outer H5 golden bytes 仍缺；synthetic H5 不作为历史兼容
证据，缺口继续 DEFERRED。此次仅恢复 B04a 的 source-bound S1 证据；B04a 工程验收、B 阶段收口、C01b 开放以及
Human Judge/Qualification 均待独立审查或原有 gate，不由本次自检替代。

<a id="b04b-taskartifact-v1"></a>

#### B04b — bounded Source → TaskArtifact v1 compiler/codec (2026-10-20)

在既有 `task_env.artifacts` owner 增加 `TaskArtifactV1` 和 `decode_task_artifact()`；原
`TaskArtifact.from_mapping()` 仍只接受 `task-artifact-v0`，不通过字段形状猜版本，也不自动升级。新
`compile_task_artifact_v1()` 位于现有 Task Source owner，必须显式接收 strict `TaskSourceV1`、结构化 A Scene
与对应的 legacy v0 semantic bridge。它复用 B02 的 role-candidate 静态验证，不抽样、不创建 RoleBinding 或
ResetSample；要求 source/task/scene identity 一致，旧 Artifact Entity 必须精确存在于 Scene，旧 Frame/Joint 必须
精确匹配或由调用方提供类型化、逐项显式的 `FrameReference`/`JointReference` 绑定。编译结果保存解析后的绑定，绑定参与
TaskArtifact v1 identity；不按字符串推测别名。Scene 只以 `schema_version + scene_id + identity_hash` 引用，不拷贝
Scene 或旧 World entity topology。

v1 精确保留现有 ActionIntent、world convention、Observation requirements、InitializationContract、
SemanticDefinition、Timebase 和 RequiredCapabilitySet。旧 v0 Entity 的 `kind`、`asset_reference`、`geometry`、
`collision_intent`、`parameters_si` 暂不能在 Canonical Scene 中精确表达；v1 记录 legacy v0 Artifact identity
和逐字段 `source_retained_v0_fields` 指针，数据仍由原 v0 source 保有。没有近似映射；任何 Entity/Frame/Joint
目标不匹配均拒绝。ExecutionSpec/Provider identity 不进入 Task Semantic Identity，Timebase 原 `physics_dt ×
control_substeps == control_dt` gate 不变。

这是 bounded candidate codec，不是 selected Task 的新默认 Artifact，也没有接入 `RuntimeSession`、Recorder、Camera、
D01b 或 Task freeze。`TaskSourceV1` 当前不声明完整 predicate/Reward/Action requirements，因此该 candidate 仍从
现有 v0 semantic bridge 取得相应字段；B03b temporal rules 尚未落盘。Capability manifest、ResetSample、State、Camera
和三类 trajectory/H5 codec/readers 保持各自 owner。历史 H5/canonical-execution-v1 golden bytes 仍缺时，这些 reader
不改并继续 DEFERRED；B04b 不把合成样本描述成旧文件兼容证据。完整 Stage-1/新主线由 B05 与后续 D01b/P99 gate 验证。

B04b 新增 `test_phase_ii_b04b_task_artifact.py`，覆盖 Source/Scene/v0 编译链接、v1 roundtrip/hash、精确版本路由、
嵌套未知字段/identity 拒绝、topology mismatch、v0 `scene` Entity 不能绑定 rigid_body Role，以及完整 source-retained
World Entity field pointers；与 B04a codec 基线合计 **12 passed**。再与 B01/B02/B03a/B03b、D01a/D02b、
reference construction、selected consumers 定向回归合计 **97 passed**，仅一条 Taichi 上游
`locale.getdefaultlocale` 弃用警告。该结果仅是 bounded candidate codec 与旧 consumer/provider regressions，不证明新 v1
进入现有执行链。

### B05 — Reference Task Semantics Migration / Gate

- **依赖**：B04b。
- **任务**：迁移或桥接 PickCube 与 NutAssembly 的 Task Semantics、Role/Reset，而不抢先把 Solution/Controller/Guard 合并进新 Task 定义；保留 task.py/solution.py 的职责区分。
- **验收**：相同冻结 Sample 下 success/reward/metrics 与受保护 baseline 等价；NutAssembly success ≠ 11-stage Expert Completion；旧 reference env 仍可调用，任何 physical behavior drift 有归因。新增 `TaskArtifact` 不继承旧 identity（除非旧 bytes 完全不变）。
- **Gate 分工**：本切片完成语义差分与 legacy 路由保护；vNext 新执行主链在 D01b/P99 验证。
  没有完整 Stage-1 证据的新版本继续为 candidate，不能因 B05 通过自动 freeze。
- **Codex AUDIT Prompt**：提供“旧 predicate/参数 → 新 predicate/参数”的逐字段对照及 sample trace；未证明的近似必须标明。

#### B05 bounded execution receipt (2026-10-20)

B05 的语义桥接检查复用 A04/A05 现有 source-backed receipts，并只扩展 TaskArtifact candidate/测试路径：NutAssembly
投影使用真实 Panda MJCF、procedural square peg 和 legacy factory evidence 组合的 A05 `scene-definition-v3`；对
`panda-v1/base → panda-v1/link0` 等非同名结构引用要求显式 Frame/Joint 映射。PickCube candidate 使用 A04 真实
Panda imported structure，table/cube 的几何与接触参数仍通过 v0 source Artifact identity 显式保留。两条路径都调用
现有 v0 evaluator，对相同固定 `CanonicalStateView` 比较旧 Artifact 与 v1 candidate 的 success、reward、metrics；
PickCube 还固定核对已接受边界的距离与 reward 数值。旧 SelectedReferenceEnv、ResetSample、NutAssembly Outcome/Expert
分离路径仍由原有 reference/selected-consumer/outcome regression 覆盖，没有把 Task success 升格为 Expert completion。

B05 专项 `test_phase_ii_b05_reference_semantics.py` **2 passed**；NutAssembly outcome、reference construction 与
selected consumer 定向回归 **80 passed**。这里的 `CanonicalStateView` 是确定性语义 fixture，比较的是同一状态输入下
旧 v0 evaluator 与从 candidate 携带的语义；它不构成 v1 Runtime/Recorder 主链、实际 trajectory replay、Stage-1
randomized feasibility、Stage-1 Judge、物理漂移归因或 Provider qualification。新 v1 仍为 candidate；TaskArtifact v0
identity 和 legacy execution routes 均未变。

## B.8 验收 Oracle 与质量标准

| 维度 | 优先 Oracle | 最小证据 |
| --- | --- | --- |
| YAML/Hook Contract | strict schema、CODE hash | S0/S1 单元测试、坏字段拒绝 |
| Role Binding | 固定 seed + 冻结 Scene identity | 重放选择与 cardinality |
| Initialization | Frozen ResetSample + Realization tolerance | S1 sampler；适用时 S2 provider microprobe |
| Temporal Semantics | 手写确定性 timeline（含缺失点） | S1 time/edge/dwell/sequence 对照 |
| v0→vNext Artifact | 原发布字节/Hash + strict codec | legacy fixtures + new codec roundtrip |
| PickCube/NutAssembly | 既有有界评估 route 与对应 Evaluation Outcome | 定位准确的 S2/S3，未跑不算 pass |

**禁止以 Expert 失败直接判定 Task 不可行，也不能以一次成功证明全 Reset Distribution 可行。**
E 只延后统一编排，不延后新任务首次 Stage-1 release 的 randomized reset probe 和 Human Judge；
通过已有脚本、task-local validation 即可形成证据。若本轮只做 legacy 适配，有界回归足以支持相应工程结论；
若声明新 frozen task，则必须先完成现有冻结要求，范围和样本/分布准确记录。

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
