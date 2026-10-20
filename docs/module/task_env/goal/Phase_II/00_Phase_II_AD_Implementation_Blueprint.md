# GeoChora Phase II — A–D 实施蓝图（架构审阅修订版）

> **状态：PROPOSED / READY FOR SECOND REVIEW；本次授权仅修订、提交和推送规划，不启动代码实施。**
> **修订日期：2026-10-20；源码审阅基准 `develop@f292df149f41520b484ff27cf2ff78a584903013`。**
> **发布基线：v1.1.0（`7ed9e78a60d407fa1150c99209e06c70bfa0ed87`）。**
> **阅读顺序：本文件 → [审阅决策与执行顺序](05_Architecture_Review_and_Execution_Order.md) → A/B/C/D 阶段文档。**
> **原始五份草案在提交 `a299d8b` 原样保存；修订不代替 canonical docs、源代码、Evidence 或实现批准。**

## 0. 使用与事实来源

1. 本组规划保存在 `docs/module/task_env/goal/Phase_II/`。`00` 定义范围，`01–04` 定义各 Goal 契约，`05` 是实施切片顺序、决策和审阅事实的唯一入口；不是新的 canonical capability matrix。
2. **每次执行 Goal 之前重新读取目标分支最新源代码、文档、调用者与测试**；此文固定于上述审阅基准，不假定未来 `develop` 仍与 `main` 相同。
3. 仓库事实优先级：**当前源码与可复现实证 > 当前 canonical docs > tests/qualification > 本草案和历史讨论**。遇到冲突要报告，不得静默“按草案修正”既有行为。
4. 基础引用：[`AGENTS.md`](../../../../../AGENTS.md)、[`docs/global/architecture.md`](../../../../global/architecture.md)、[`docs/global/ownership.md`](../../../../global/ownership.md)、[`docs/module/task_env/public-api.md`](../../public-api.md)、[`docs/module/task_env/qualification.md`](../../qualification.md)、[`docs/roadmap/README.md`](../../../../roadmap/README.md)。
5. 状态用语：**IMPLEMENTED**（源码存在）、**TESTED_BOUNDED**（限定真实交集验证）、**QUALIFIED**（独立 Decision 与充分 Evidence）、**PROPOSED**（本文设计）、**DEFERRED**（明确推迟）。编译通过/注册成功 ≠ 可运行 ≠ 合格。

## 1. Phase II 本轮范围决议

**规划取舍**：维护者于 2026-10-20 授权按架构审阅建议调整 A–D 规划并推送 `develop`，供后续二审。保留 A–D 优先、E 延后的候选工程方向；现有 canonical Roadmap 的 LIBERO + Panda + MuJoCo bounded Oracle 研究方向保持原记录，可为未来需求提供反例。此文档提交不启动 benchmark adapter、Harness 或代码实施；进入工程时再按批准范围同步 canonical Roadmap。

**后续工程范围限 A–D；E 延后。首个实现基线采取固定拓扑、精确既有时间配方、单 Robot 真实主线、双 Robot 静态契约，以及一个真实独立 Physics × Renderer 目标交集。** 多 Robot 动力学须另有实际 S2 才可声明；拓扑变体不隐式改变 spaces。新任务 Stage-1 validation/randomized feasibility/Human Judge 不随 Harness 延后。

| 阶段 | 必须产出 | 不在本轮要求 |
| --- | --- | --- |
| A Core Object Model | Asset Definition、Entity Instance、Component/Articulation/Frame、Scene、Registry 的唯一身份与所有权 | 通用 ECS、所有资产格式、全面 OpenUSD Scene IR |
| B Task Representation | 可声明、可解析、可验证的任务/角色/初始化/时序语义，版本化既有 Task Artifact | 自动任务创作 Agent、完整 Task Harness、通用训练流水线 |
| C Execution API | Single Env 公共契约、按 Entity/Control Group 的 Controller、`reset/step/stop`、Observation、Solution 解耦 | Phase III 通用 Batch/Vectorized 改造、任意设备训练、通用 Policy Runner |
| D Physics/Rendering | 一份 Canonical Scene，独立物理/视觉实例化，Canonical State、Camera 与可验证 Pairing | 自研通用求解器、全部 Physics × Renderer 组合的 Qualification、所有软体/流体与高级光学实现 |

**现有** Batch、RSL/SB3、Recorder、Renderer、selected reference 及诊断源码不得因不在当前实施重点而删除。Phase III 才新增/重构通用并行环境设计；现有已声明的有界路径应保持非回归。

### 1.1 不可跨越的所有权

```text
Human / Script / Future PhysPi
       │
       ▼
GeoChora Core (task_env/)
 ├─ A: Asset/Entity/Frame/Scene identities & composition
 ├─ B: Task declaration, role binding, semantic evaluator, artifact
 ├─ C: Execution planning, controller/action, scalar lifecycle, observation
 └─ D: Provider-neutral physics/render materialization, state projection
       │                    │
       ▼                    ▼
Physics Provider        Rendering Provider
(native solver owner)    (native renderer owner)
```

- **GeoChora `task_env/` 是唯一 Core TaskEnv owner**；`GeoPhys` 是外部 Gitlink；`asset/external/mujoco_menagerie` 是外部资产 Gitlink。不能复制 GeoPhys solver 或私读 provider storage。
- **不新建**第二个 TaskEnv、Runtime/Session 框架、Artifact 框架、Recorder、Controller 基础体系、UniversalSolver、Agent Orchestrator。
- Task/Env/Solution/Experiment/Evidence/Judge 各有边界。Experiment/Harness 的统一编排归未来 E；本轮通过脚本/已有工具形成受限验收即可。
- Provider 的 native state 是唯一物理权威；Renderer 可有 cache，不得拥有第二套演化中的物理状态。
- Frozen Task Artifact 不随 Provider 或 Render Profile 改写任务语义；行为兼容性变更必须版本化。

## 2. 需要保护的当前基线（Codex 不可自行扩权）

| 当前事实（2026-10-19 核查） | Phase II 的处理 |
| --- | --- |
| `task_env/registry.py` 已有 `make_env/make_agent/make_object/make_scene` 和注册器 | **扩展/迁移，不平行新建 factory**；`make_agent` 命名未来应避免与 RL Agent 混淆，保留迁移计划 |
| 通用 `BaseTaskEnv` 与 `SelectedReferenceEnv` 是两条 scalar 构造路径 | C 阶段统一公共契约和协调行为，迁移有界任务；过渡期保留兼容路由 |
| `TaskLifecycleAdapter`、`SingleTaskLifecycleAdapter` 已存在 | 不新增同义 lifecycle manager |
| 高级 `RuntimeSession`、通用 `RuntimeBoundary` **接口不同** | 仅在明确 Adapter 需求时打通；不强制统一 provider ABI |
| `TaskArtifact` 现为 `task-artifact-v0`，`Timebase` 含 `physics_dt` | B 阶段只能通过有版本迁移引入新的任务时间需求表达；不可静默改写 v0 bytes/hash |
| Advanced `CanonicalStateView` 目前使用标量 joint map | D 阶段扩展 Typed Joint/Frame & Extensions，同时保留适配/旧路由 |
| `CameraGeometry`、`CanonicalCameraObservation` 目前偏 RGB/Depth | D 阶段规范化并扩展 Segmentation，保留原 Camera/Depth 语义 |
| Selected NutAssembly 目前只能 `step_expert()`，且依赖 native-rate Guard Evidence | C 阶段先证明独立 Solution + external action 仍有等价 evidence，再退役旧 API |
| PickCube/NutAssembly GeoPhys/MuJoCo CPU 特定任务/seed 为 TESTED_BOUNDED | 不以新的 import/smoke 冒充完整正式 QUALIFIED |
| `task_env/recorders` H5 v2 与 T/T+1 对齐已有约束 | Stop Event、Controller Switch 与 Capture Meta 必须版本化记录，不能造假 transition |
| 仓库无根 `pyproject.toml/setup.py` | 不默认使用 `pip install -e .`；按当前依赖与 `PYTHONPATH=GeoPhys/src:.` 执行 |

当前源码还包括 GeoPhys 公开 `ImportedScene.ir/capability_report/build_render_scene_desc()`，
以及 Core 的三类录制格式。A04/D01/D03 先评估这些 owner 的组合；C05a 先处理 action 存储兼容，
不能把 generic H5 v2、canonical outer 和 execution stream 统称为一个可自由扩展的 H5。

## 3. 20 个 Implementation Goals — 推荐拆分

**20 个编号保持稳定，表示父目标，不表示提交顺序或 20 个小提交。** 大目标拆成有退出条件的后缀切片，
每次授权一个有界切片。下表只索引目标；精确前置依赖和建议执行顺序以 [`05`](05_Architecture_Review_and_Execution_Order.md#3-切片依赖与推荐执行顺序) 为准。

| 编号 | Goal | 核心结果 | 切片/主要输入 | 主权责 | 必须通过的代表性 Gate |
| ---: | --- | --- | --- | --- | --- |
| 01 | **A01** 定义与实例身份 | Asset Definition / Entity Instance / 资源引用 / 版本身份 | P00 | Core + `asset/` 边界 | 相同 Asset 多实例唯一 ID；codec/非法引用 |
| 02 | **A02** Components & Frames | Rigid/Collision/Joint/Frame 与轻量组件契约 | A01 | Core | Frame 图无环、单位/坐标规范、非法引用拒绝 |
| 03 | **A03** Robot & Scene Composition | Robot 特化、Articulation、Control Group、Scene 组合 | A02 | Core | 多 Robot 名字隔离、资源无冲突、Scene 可复现 |
| 04 | **A04** Asset/Registry Public Path | Registry + public importer 组合，保留源语义 | A01–A03 | registry/assembly/provider public importer | source/hash、映射报告、旧 UID 行为 |
| 05 | **A05** A 集成与迁移 Gate | 静态单/双 Robot + 空/简单任务场景 smoke | A01–A04 | assembly/diagnostics | PickCube/NutAssembly 资产/身份非回归、无并行化承诺 |
| 06 | **B01** Task Declarative Source | YAML 主体 + 受约束 Python Hook 解析与版本 | A05/B04a/D01a/D02b | task/tasks/artifacts | strict parsing、Hook 依赖声明、roundtrip |
| 07 | **B02** Roles & Init | 固定拓扑 Role/ResetSample 与 realization | B01/B04a/D01a/D02b | Core sampler/runtime | RNG/version、cardinality、realization gate |
| 08 | **B03** Semantic Evaluator | B03a 只读谓词；B03b 时序提交与 action context | B02/D02b | TaskDefinition/Evaluator | exactly-once、action reward、missing≠False |
| 09 | **B04** Artifact Identity Evolution | B04a 提前确定嵌套版本；B04b 编译/codec | A02；B04b 另需 B03b | artifacts/现有 readers | v0 及嵌套 schema/identity 全链保护 |
| 10 | **B05** B Reference Regression | 将现有两 selected task 的“语义”迁移或适配 | B04b | tasks | 成功判定/ResetSample 与基线对照；不抢先重构 expert loop |
| 11 | **C01** Execution Config & Plan | C01a 静态计划；C01b 实际 requirements/admission | A02/B04a/D02a；C01b 另需 B05 | environment/runtime | actual manifest 不扩权、动态失败回收 |
| 12 | **C02** Multi-controller Bindings | C02a schema；C02b 原子执行；C02c 兼容切换 | A03/C01b；执行另需 C05a/C04/D01b | controllers/environment | 全动作先校验、唯一 writer、memory/space 一致 |
| 13 | **C03** Scalar Lifecycle | C03a 现有 ports/fault policy；C03b Stop/termination | C02a/D01b/C05a；Stop 另需 C04 | 现有 lifecycle/environment | fault 禁止续步、flags、零时间 Stop |
| 14 | **C04** Observation & Diagnostics | public/privileged/private schema、必要反馈与可选诊断 | C03a/D02b | observations/controllers | 同 boundary、非 Panda、重复读取不改语义 |
| 15 | **C05** Recorder & Solution Migration | C05a 存储前移；C05b PickCube；C05c NutAssembly | 存储需 C02a；Solution 需 C02b/C03b/C04 | 既有 recorder/tasks/controllers | action tree/events、hold/ramp/native Guard 保真 |
| 16 | **D01** Physics Materialization | D01a 提前真实桥接；D01b vNext 完整接入 | A05/C01a/B04a；D01b 另需 B04b/C01b | assembly/runtime adapters | 新表示真实被消费、realization、两 provider |
| 17 | **D02** Canonical State vNext | D02a 契约提前；D02b runtime projection | A02；D02b 另需 D01a | runtime/artifacts | 真实多 DOF、Frame/Twist、alias lifetime |
| 18 | **D03** Render State Synchronization | visual materialization、transform/geometry versions、按需 sync | D01b/D02b/D05a | render/observations | 两消费者版本独立，reset/同 step 修改可见 |
| 19 | **D04** Camera & Modalities | camera model、RGB/Depth/Segmentation/metadata 的扩展 | D03/C04/C05a | observations/render | 投影+反投影、seg ID、capture provenance |
| 20 | **D05** Renderer Composition Gate | D05a selection/manifest；D05b 真实 pairing | C01a/A02；集成另需 D04/C01b | render/runtime/diagnostics | provider/backend 分层、真实同步、资格不虚报 |

**前移的是契约和最小真实闭环，不是同时重写所有 subsystem。** D01a 使用 v0 schema 新 candidate microfixture
或经证明等价的只读 projection，不改变旧 frozen Artifact/hash；
D01b 才接入完整 vNext。B05 先保护语义，D01b/P99 再验证新版端到端，不能提前宣称新版 frozen。
C05a 必须早于 structured action 的开放；C05c 不等待高保真 Renderer。A05/B05/D05 是 gate，不另建运行时。

## 4. 依赖分层与阶段边界

```text
P00 → A01/A02 → B04a/D02a/C01a/D05a contracts
    → A03/A04/A05 → D01a/D02b real microprobe
    → B01/B02/B03a/B03b/B04b/B05
    → C01b/D01b/C02a/C05a storage
    → C03a/C04/C02b/C03b
    → C05b/C05c; C02c after the selected regression gate
    → D03/D04/D05b → P99
```

这是导航图，斜杠不表示相互独立或可同时合并；逐切片前置条件在 `05` 的有序依赖表中定义。
每个父 Goal 需全部必需切片完成才能标记 implemented；deferred 明示范围缩减，blocked 不可计完成。

## 5. P00：启动前 Baseline / Compatibility Gate（不算实施 Goal）

Codex 在第一次动手前必须交付：

- 当前 branch/HEAD/dirty/untracked/submodule revision 与本计划 SHA 对比；若有差异，标注设计是否过时。
- Owner + public symbol + 生产调用者 + 测试分布图；重点扫描 `task_env/registry.py`、`environment/`、`tasks/reference_env.py`、`artifacts/`、`runtime/sessions/`、`observations/`、`controllers/`、`render/`、`recorders/`。
- 真实运行基线：`examples/tasks/pick_cube.py`、`examples/tasks/nut_assembly.py`，适用的 Pendulum 与 Native Camera bounded cases；报告硬件/依赖是否满足，**不得捏造 PASS**。
- 确定可使用的 `tests`/diagnostics 命令、最小 provider test 成本、resource constraints/超时及重跑条件；已有 `task_env/diagnostics/` 不能被静默丢弃。
- 当前已知缺陷（如 `single_inline` 等）和历史未通过 gates 单独列出；不将其误认成本阶段新引入回归，也不能在迁移中掩盖。
- 2026-10-20 审阅发现部分 P1.1/P1.4/lifecycle/Guard detector 引用退休模块；逐条判断其保护义务，迁移或补回有效检测需单独批准，不能以跳过/删断言制造全绿。已有运行事实见 `05`，不作为未来提交的复验结果。
- **Human review：**签署受保护的 golden-path/contract fixtures 列表后进入 A01。

## 6. Goal 级工作模式：Audit → Approve → Implement → Evidence → Integrate

**用户计划让 Codex 在每个 Goal 执行 Goal 模式，建议固定以下交互协议，而不绑定某一客户端的私有命令：**

1. **AUDIT_ONLY**：读取当前代码，映射 owner/调用链/测试；指出本文与源码冲突，列出 1–3 种方案和需维护者决策的问题；不修改代码。输出 `APPROVE / REVISE / DEFER / SPLIT` 建议。
2. **APPROVED_IMPLEMENTATION**：收到明确批准和限定范围后，实施**一个**有界切片；父 Goal 有多个切片时，
   批准范围须指明后缀，不以“顺手”理由启动下一切片。
3. **EVIDENCE**：先 S0/S1，按需要 S2/S3；报告每条命令真实结果、修改前/后的差异、未测部分、可复现失败。
4. **REVIEW**：维护者/二审通过才能合入 `develop`；评估是否同步 canonical docs/module skill/public exports；不得自动更改已冻结 Decision/Capability Matrix。
5. **NEXT_GOAL**：下一 Goal 从最新 `develop` 重新 audit，而不是假定前一 Goal 的临时工作树即事实。

### 建议提交给 Codex 的单 Goal 模板

```text
$geochora-architecture-refactor
Project: GeoChora Phase II A–D
Goal: <parent A01 ... D05>
Slice: <e.g. B04a / C05c; unsplit Goal repeats its parent ID>
Mode: AUDIT_ONLY    # 维护者批准后改为 APPROVED_IMPLEMENTATION

Read first:
  AGENTS.md
  docs/global/{architecture,ownership}.md
  docs/module/task_env/{public-api,qualification,runtime-and-providers,task-artifact}.md
  <本阶段 Markdown> 与 00_Phase_II_AD_Implementation_Blueprint.md

Task:
  1. Verify branch, HEAD, dirty tree, gitlinks, real production callers and test entrypoints.
  2. Inspect current canonical owner; classify FIX_EXISTING / EXTEND_EXISTING /
     COMPOSE_EXISTING / NEW_IMPLEMENTATION; reject duplicate owners.
  3. Compare design proposal against current source; propose minimal changed files,
     API/version strategy, migration & rollback path.
  4. Specify defect-sensitive tests and exact support envelope.
  5. Output unresolved questions; STOP and request approval before implementation.

Constraints:
  - No new Task Harness, broad batch rewrite, solver internals, or fabricated qualification.
  - Keep old selected reference routes until their actual callers are migrated and tested.
  - Do not change provider/renderer backend internals without a separate owner-reviewed proposal.
```

执行后交付的 **Goal Completion Receipt**（建议文件可留在 Codex 输出/PR 描述，不强制新建工作流系统）：

```yaml
# 概念模板，非运行时契约
phase_goal: C03
slice: C03a
base_commit: <SHA>
result_commit: <SHA or uncommitted>
disposition: implemented | accepted_deferred | blocked
classification: EXTEND_EXISTING
owners_changed: [<module>]
public_contract_delta: [<API/version/failure behavior>]
source_and_provider_identity: {core: <SHA>, geophys: <SHA-or-not-used>}
tests:
  - {command: <exact command>, result: pass|fail|timeout|not_run, reason: <why>}
regressions_checked: [<named reference routes>]
evidence_paths: [<path/hash>]
known_unsupported: [<precise intersection>]
review_required: true
```

## 7. 统一验收策略（不得让 20 Goal 变成 20 次全仓昂贵 campaign）

复用当前 `docs/module/task_env/qualification.md` 的 Layer A/B/C 和 S0–S4：

- **S0**：static/import/schema/negative-path；只能证明 wiring。
- **S1**：Contract/codec/identity/time/schema/lifecycle，具有稳定 Oracle 的独立单元测试。
- **S2**：最小真实 Provider Microprobe，按当前物理环境/依赖满足程度选择。
- **S3**：短 `reset→step→record→read` 与适用的 task golden path（NutAssembly Guard 必须保持真实测量语义）。
- **S4**：独立声明范围、Frozen Artifact/样本、维护者或 Human Judge 的 Qualification Campaign；**不会因为 Phase II 工程 Goal 完成自动触发或自动通过**。

默认每 Goal 先跑 S0/S1，并在确有物理/时间/场景/相机变化时执行 S2；涉及生产执行主链迁移则 S3。整阶段 Gate 执行有限的相关交叉验证而非全 Provider 笛卡尔积。超时、环境缺依赖、跳过只能标记为 `not_run/incomplete`。

### 7.1 最小横向回归集

| 风险 | 应有检测 |
| --- | --- |
| Registry/API 回归 | 旧 UID、无运行时导入、duplicate/unknown fail-closed |
| Artifact 回归 | v0 bytes/hash strict roundtrip + 新版 codec，冻结样本只读 |
| Scene/Frame | 资产多实例身份、多 Robot Frame、循环/悬挂引用拒绝 |
| Reset/semantics | Deterministic roles/samples，`missing` 与 `False` 区分，Temporal Memory reset |
| Controller | Action Schema、targets/applied 分层、ownership overlap reject、switch safepoint |
| Lifecycle | step-before-reset、step-after-terminal、success/failure/stop/horizon、零物理时间 Stop |
| Solution | 外部 Action Producer 的 NutAssembly 原 Guard/Stage 证据，不伪造 native samples |
| Recorder | T transitions/T+1 observations，Stop/Switch/Capture Event 对齐，旧 H5 Reader 可识别旧版 |
| State | SI、wxyz、Z-up、Typed DOF、time boundary、一致只读 snapshots |
| Render | Camera projection/depth、Scene Sync version、invalid segmentation、Pairing fail-closed |
| Eligibility | IMPLEMENTED/TESTED_BOUNDED/QUALIFIED 严格区分，未测组合不可扩权 |

## 8. 兼容/迁移策略

1. **Add → Adapt → Migrate Callers → Deprecate/Retire**：A 的 `make_agent`、B 的 `task-artifact-v0`、C 的 `step_expert`、D 的 static Camera route 均先证明迁移，再决定是否退役。
2. 不让一个 Goal 同时破坏旧 API、旧 Artifact 和旧 H5；如确需突破，由维护者批准 Version/Adapter 和测例。
3. 当前 selected NutAssembly 需要 Native Guard 证据；外部 Solution 必须能够消费标准化、真实采样的必要 feedback，不能因为“去耦合”将 Guard 悄悄降级成 outer 100 Hz。
4. 首个 vNext 基线保留当前精确 Timebase；task demand/native dt 的进一步拆分需独立证据和版本迁移，不承诺跨 dt 等价。
5. 同 Action Schema/资源/单位/时序的 Controller 只在安全 Boundary 切换；schema 改变则重新构造 Env 及依赖其 spaces 的 wrapper/learner，不以 reset 偷换 spaces。Provider 不热切换。
6. 当前 UI Renderer 与 Camera Observation 路由不同；D 不得通过 UI Frame 假冒 Camera 契约或使用 fake Flora 证明 native pairing。

## 9. P99：A–D 结束条件（不算实施 Goal）

- A–D 四份阶段文档所列各 Goal 有明确 `implemented / accepted_deferred / blocked` 结果和 review receipt；不能以尚有 blocked 时默认“已完成 Phase II”。
- 至少一条**受限真实**主干能从声明的 Scene/Task 经 `make_env → reset → step → observation → record` 跑通；selected PickCube/NutAssembly 的适用行为回归清晰，未通过者如实列残余。
- 新旧 Artifact/Config/Observation/H5 兼容策略与拒绝行为均经过保护性测试；核心身份、时间、状态、终止语义有证据。
- 对新 Task 的发布冻结，必须完成现有 Stage-1 validation、randomized feasibility 和独立 Human Judge；脚本即可执行，不依赖 E。未达 gate 的新版只能是 candidate。
- 以 GeoPhys CPU physics × MuJoCo native renderer × rigid calibration RGB/Depth 为首选工程目标，提供动态同步的真实独立 pairing；此为待实现目标，当前 admission 会拒绝。若仅同名 pairing 通过，不能将 D05b 或完整 independence 标完成；必须明确缩减范围/延期。
- 公共 API 导航、canonical docs、`task_env/.agents` 与仓库 module skills 根据真实变更同步；缺少实际证据的能力保留为 PLANNED/TESTED_BOUNDED。
- 变更经过维护者/独立审阅，进入 `develop` 后进行新的代码二审；**不得自动合并 main、改写 frozen v1.1.0、扩大资格矩阵**。
- E 阶段由新版本事实再启动；不得把暂留的 E1–E5 抽象偷偷并入 Core 实现。

## 10. 风险、决策门与回退

| 风险 | 预防与决策门 | 回退/延期条件 |
| --- | --- | --- |
| 重复 Core Owner 或全面重写 | Audit 既有类/生产调用者；一个 Goal 改一个所有权边界 | 需要新平行 manager 时 `SPLIT/REVISE` |
| v0 Artifact/历史 H5 identity 破坏 | 新 schema version + roundtrip fixtures | 旧 bytes/hash 改变立即回退 |
| 多 Controller 动态切换时状态跳变 | safepoint、realized measured state、Action Schema gate | 不满足兼容声明则只允许 reset 后切换 |
| Phys/Render 耦合与 GPU resource 泄漏 | Core 只持有规范化 map；显式 release/worker teardown | 无法证明安全释放则 bounded worker isolation |
| 同步视觉 observation 过期 | capture identity + precise timestamp + reset invalidation | 不满足 fresh requirement 时拒绝 |
| 测试环境稀缺导致误报 | S0–S3 分层，标注依赖/未跑/超时 | accepted-deferred 而非伪绿 |
| Scope Creep 至 E、Phase III | Goal 出入界验收、Human review | 先留 extension slot，不新增 Runner/Parallel Harness |

## 11. 参考资料与审阅交接

**外部架构参考（来源均为公开活跃/有实际研究采用的项目，但对应能力需要按所引用 revision 核实）：**

- A： [Isaac Lab](https://github.com/isaac-sim/IsaacLab)、[SAPIEN](https://github.com/haosulab/SAPIEN)、[MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie)、[Gazebo Sim](https://github.com/gazebosim/gz-sim)。
- B： [robosuite](https://github.com/ARISE-Initiative/robosuite)、[RoboCasa](https://github.com/robocasa/robocasa)、[ManiSkill](https://github.com/mani-skill/ManiSkill)、[LIBERO](https://github.com/Lifelong-Robot-Learning/LIBERO)。
- C： [Gymnasium](https://github.com/Farama-Foundation/Gymnasium)、[Isaac Lab](https://github.com/isaac-sim/IsaacLab)、[ManiSkill](https://github.com/mani-skill/ManiSkill)。
- D： [Isaac Lab multi-backend `develop`](https://github.com/isaac-sim/IsaacLab/tree/develop)、[Gazebo Rendering](https://github.com/gazebosim/gz-rendering)、[Genesis](https://github.com/Genesis-Embodied-AI/genesis-world)、[SAPIEN](https://github.com/haosulab/SAPIEN)、[robosuite USD workflow](https://github.com/ARISE-Initiative/robosuite)。

**二审入口为 [05](05_Architecture_Review_and_Execution_Order.md)**：复核复用/拆分、源码与测试依据、
切片依赖和最小真实闭环；每条新增意见绑定 source/commit。规划被提交或推送不自动成为 canonical
architecture，不授权后续实施，也不创建新的 Qualification Decision。
