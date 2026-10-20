# GeoChora Phase II — A–D 代码实施总蓝图（Codex 审阅草案）

> **状态：PROPOSED / REVIEW REQUIRED；非已批准开发排期，非现有能力声明。**  
> **编制基准：2026-10-19；GitHub `main` HEAD `f292df149f41520b484ff27cf2ff78a584903013`；`develop` 在本次核对时同 SHA。**  
> **发布基线：v1.1.0（`7ed9e78a60d407fa1150c99209e06c70bfa0ed87`）。**  
> **阅读顺序：本文件 → `01_Phase_A_Core_Object_Model.md` → `02_Phase_B_Task_Semantics.md` → `03_Phase_C_Execution_Lifecycle.md` → `04_Phase_D_Physics_Rendering.md`。**  
> **作用：供 Codex 首轮代码调查、架构审阅、逐 Goal 实施及维护者验收；不代替仓库 canonical docs、源代码或 Evidence。**

## 0. 使用与事实来源

1. 将本文件与另外四个 Markdown **放在同一个目录**，建议临时放入 `docs/plans/phase_ii_ad/` 的 topic branch；路径仅为提交建议，是否归档至该目录由维护者决定。相互引用使用同目录文件名。
2. **每次执行 Goal 之前重新读取目标分支最新源代码、文档、调用者与测试**；此文固定于上述审阅基准，不假定未来 `develop` 仍与 `main` 相同。
3. 仓库事实优先级：**当前源码与可复现实证 > 当前 canonical docs > tests/qualification > 本草案和历史讨论**。遇到冲突要报告，不得静默“按草案修正”既有行为。
4. 基础引用：[`AGENTS.md`](https://github.com/Lebingelee/GeoChora/blob/main/AGENTS.md)、[`docs/global/architecture.md`](https://github.com/Lebingelee/GeoChora/blob/main/docs/global/architecture.md)、[`docs/global/ownership.md`](https://github.com/Lebingelee/GeoChora/blob/main/docs/global/ownership.md)、[`docs/module/task_env/public-api.md`](https://github.com/Lebingelee/GeoChora/blob/main/docs/module/task_env/public-api.md)、[`docs/module/task_env/qualification.md`](https://github.com/Lebingelee/GeoChora/blob/main/docs/module/task_env/qualification.md)、[`docs/roadmap/README.md`](https://github.com/Lebingelee/GeoChora/blob/main/docs/roadmap/README.md)。
5. 状态用语：**IMPLEMENTED**（源码存在）、**TESTED_BOUNDED**（限定真实交集验证）、**QUALIFIED**（独立 Decision 与充分 Evidence）、**PROPOSED**（本文设计）、**DEFERRED**（明确推迟）。编译通过/注册成功 ≠ 可运行 ≠ 合格。

## 1. Phase II 本轮范围决议

**与当前仓库 Roadmap 的优先级差异（明确待维护者决议）**：现有 `docs/roadmap/README.md` 将 LIBERO + Panda + MuJoCo 的 bounded benchmark/Oracle 对照列为近期首选，且强调先完成评审后再建设 Task Harness。**用户本轮提出新的实施顺序：先开发 A–D，待新版本形成后再设计 E。** 本草案以用户最新规划组织 *proposal*，但**不会静默改写当前 canonical Roadmap**；Codex 首轮审阅必须提交 Roadmap 取舍与影响说明，待维护者批准后再同步正式文档。

**只开发 A–D，E 延后至 A–D 新版本发布/形成稳定实施基线后。**

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

## 3. 20 个 Implementation Goals — 推荐拆分

**含义：20 个目标是可独立审查的工作单元，并非 20 次必定可独立合并的单提交。** 每个 Goal 先 Audit/Design Review，维护者认可后才 Implement；允许提出 `SPLIT`、`ACCEPTED-DEFERRED`。

| 顺序 | Goal | 核心结果 | 依赖 | 主权责 | 必须通过的代表性 Gate |
| ---: | --- | --- | --- | --- | --- |
| 01 | **A01** 定义与实例身份 | Asset Definition / Entity Instance / 资源引用 / 版本身份 | P00 | Core + `asset/` 边界 | 相同 Asset 多实例唯一 ID；codec/非法引用 |
| 02 | **A02** Components & Frames | Rigid/Collision/Joint/Frame 与轻量组件契约 | A01 | Core | Frame 图无环、单位/坐标规范、非法引用拒绝 |
| 03 | **A03** Robot & Scene Composition | Robot 特化、Articulation、Control Group、Scene 组合 | A02 | Core | 多 Robot 名字隔离、资源无冲突、Scene 可复现 |
| 04 | **A04** Asset/Registry Public Path | import→canonical→factory→Scene，复用现有 registry | A01–A03 | `asset/` 引用、`task_env/registry.py` | 旧 UID 行为保护、unknown/duplicate fail-closed |
| 05 | **A05** A 集成与迁移 Gate | 静态单/双 Robot + 空/简单任务场景 smoke | A01–A04 | assembly/diagnostics | PickCube/NutAssembly 资产/身份非回归、无并行化承诺 |
| 06 | **B01** Task Declarative Source | YAML 主体 + 受约束 Python Hook 解析与版本 | A05 | task/tasks/artifacts | strict parsing、Hook 依赖声明、roundtrip |
| 07 | **B02** Roles & Init | Role Binding、Scene Variant、ResetSample 确定性解析 | B01 | Core sampler | seed 重现、cardinality、无隐式 provider 重采样 |
| 08 | **B03** Semantic Evaluator | typed predicates、时间逻辑、显式 semantic memory | B02 | Task Semantics | sequence/dwell/rising-edge，missing≠False |
| 09 | **B04** Artifact Identity Evolution | 复用 TaskArtifact，冻结完整语义/Hook/time requirements | B01–B03 | artifacts | 新旧版本各自 strict roundtrip/hash，不重写 v0 |
| 10 | **B05** B Reference Regression | 将现有两 selected task 的“语义”迁移或适配 | B01–B04 | tasks | 成功判定/ResetSample 与基线对照；不抢先重构 expert loop |
| 11 | **C01** Execution Config & Plan | YAML 默认 + Override 归一；Admission 分层 | A/B | environment/runtime | Provider/Controller/Renderer 错配前置拒绝 |
| 12 | **C02** Multi-controller Bindings | Entity×Control Group 绑定、structured actions、safepoint 切换 | A03、C01 | controllers/environment | 同实体臂+手配置、不同 robot 绑定、资源冲突拒绝 |
| 13 | **C03** Unified Scalar Lifecycle | `BaseTaskEnv` thin facade、reset/step/stop、termination policy | B05、C01–C02 | lifecycle/environment | success/stop/horizon 正确 flags；无伪物理 Step |
| 14 | **C04** Observation & Diagnostics | public/privileged obs schema、控制 feedback 可选、时钟对齐 | C03 | observations/controllers | obs shape/time、诊断关不影响算法、missing 拒绝 |
| 15 | **C05** Solution & Recorder Migration | external Solution 统一 step，NutAssembly Guard 保真；事件录制 | C03–C04 | selected tasks/recorders | 两 provider selected regression、T/T+1、旧 API 安全退役 |
| 16 | **D01** Physics Materialization | Canonical Scene → GeoPhys/MuJoCo 受限实例化与映射 | A05、B04、C01 | assembly/runtime adapters | Scene/Frame identity、失配拒绝、real microprobe |
| 17 | **D02** Canonical State vNext | typed joint/frame/state requirements、只读投影 | D01、C04 | runtime/artifacts | 多自由度、单位/Frame、consumer 时钟一致 |
| 18 | **D03** Render State Synchronization | visual materialization、transform/geometry versions、按需 sync | D02 | render/observations | 两消费者版本独立，reset/同 step 修改可见 |
| 19 | **D04** Camera & Modalities | camera model、RGB/Depth/Segmentation/metadata 的扩展 | D03 | observations/render | 投影+反投影、seg ID、capture provenance |
| 20 | **D05** Renderer Composition Gate | physics/renderer 组合准入 + **受限真实交集**验证 | D03–D04、C01 | render/runtime/diagnostics | 至少可声明的独立 pairing；失败路径；资格不虚报 |

**注意几个跨阶段依赖：** C01 可以先依靠既有 Advanced RuntimeSession 做受限 Admission，D01 后才完成更通用的 Scene Materialization；C05 迁移不得等待所有 D 阶段高保真 Renderer；D02 进一步丰富的 State/Frame 将按版本回灌 C 的 observation/feedback，而不是修改过去已经冻结的任务语义。A05/B05/C05/D05 是阶段验收 Goal，不等于发布全部功能已合格。

## 4. 依赖分层与阶段边界

```text
P00: Baseline Audit / public-contract inventory / regression fixtures
  │
  ├─ A01 → A02 → A03 → A04 → A05
  │                          │
  │                          ▼
  └──────────────────────── B01 → B02 → B03 → B04 → B05
                                       │             │
                                       └─────────────┴── C01 → C02 → C03 → C04 → C05
                                                               │                 │
                                                               └──── D01 → D02 → D03 → D04 → D05
                                                                                           │
                                                                                           ▼
                                                              P99: Integrated A–D Gate / docs/skills review
```

此图是**建议的主干顺序**，不是禁止多个独立 audit 在不同分支并行。具体代码提交按受影响的 owner 和数据契约安排；避免同时大幅改 `TaskArtifact`、RuntimeSession、Recorder H5 和 Renderer API，导致无法定位回归。

## 5. P00：启动前 Baseline / Compatibility Gate（不算实施 Goal）

Codex 在第一次动手前必须交付：

- 当前 branch/HEAD/dirty/untracked/submodule revision 与本计划 SHA 对比；若有差异，标注设计是否过时。
- Owner + public symbol + 生产调用者 + 测试分布图；重点扫描 `task_env/registry.py`、`environment/`、`tasks/reference_env.py`、`artifacts/`、`runtime/sessions/`、`observations/`、`controllers/`、`render/`、`recorders/`。
- 真实运行基线：`examples/tasks/pick_cube.py`、`examples/tasks/nut_assembly.py`，适用的 Pendulum 与 Native Camera bounded cases；报告硬件/依赖是否满足，**不得捏造 PASS**。
- 确定可使用的 `tests`/diagnostics 命令、最小 provider test 成本、resource constraints/超时及重跑条件；已有 `task_env/diagnostics/` 不能被静默丢弃。
- 当前已知缺陷（如 `single_inline` 等）和历史未通过 gates 单独列出；不将其误认成本阶段新引入回归，也不能在迁移中掩盖。
- **Human review：**签署受保护的 golden-path/contract fixtures 列表后进入 A01。

## 6. Goal 级工作模式：Audit → Approve → Implement → Evidence → Integrate

**用户计划让 Codex 在每个 Goal 执行 Goal 模式，建议固定以下交互协议，而不绑定某一客户端的私有命令：**

1. **AUDIT_ONLY**：读取当前代码，映射 owner/调用链/测试；指出本文与源码冲突，列出 1–3 种方案和需维护者决策的问题；不修改代码。输出 `APPROVE / REVISE / DEFER / SPLIT` 建议。
2. **APPROVED_IMPLEMENTATION**：收到明确批准和限定范围后，实施**一个** Goal；不以“顺手”理由提前实施下一个 Goal。
3. **EVIDENCE**：先 S0/S1，按需要 S2/S3；报告每条命令真实结果、修改前/后的差异、未测部分、可复现失败。
4. **REVIEW**：维护者/二审通过才能合入 `develop`；评估是否同步 canonical docs/module skill/public exports；不得自动更改已冻结 Decision/Capability Matrix。
5. **NEXT_GOAL**：下一 Goal 从最新 `develop` 重新 audit，而不是假定前一 Goal 的临时工作树即事实。

### 建议提交给 Codex 的单 Goal 模板

```text
$geochora-architecture-refactor
Project: GeoChora Phase II A–D
Goal: <A01 ... D05>
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
4. Timebase 的 `physics_dt` 在当前 v0 Artifact 内；未来拆出 native physics step 是**带 identity 影响的版本迁移**，不可当成自由配置覆盖。
5. 动态 Controller 更改：同 Action Schema/控制资源兼容时只在安全 Control Boundary 切换；不兼容时 Reset 边界重绑定，版本化 event。Provider 不热切换。
6. 当前 UI Renderer 与 Camera Observation 路由不同；D 不得通过 UI Frame 假冒 Camera 契约或使用 fake Flora 证明 native pairing。

## 9. P99：A–D 结束条件（不算实施 Goal）

- A–D 四份阶段文档所列各 Goal 有明确 `implemented / accepted_deferred / blocked` 结果和 review receipt；不能以尚有 blocked 时默认“已完成 Phase II”。
- 至少一条**受限真实**主干能从声明的 Scene/Task 经 `make_env → reset → step → observation → record` 跑通；selected PickCube/NutAssembly 的适用行为回归清晰，未通过者如实列残余。
- 新旧 Artifact/Config/Observation/H5 兼容策略与拒绝行为均经过保护性测试；核心身份、时间、状态、终止语义有证据。
- 至少有一个物理场景和相机组合的实际 GeoPhys 或 MuJoCo Runtime Evidence；**不要求在没有设备/依赖时造出多个合格 Renderer**，但对应 Goal 须标明 accepted-deferred/blocked，不能虚报 completion。
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

**提交 Codex 审阅时，要求它先提供一份独立的 REVIEW 文档/PR 评论**：明确哪些 Goal 可复用现有代码、哪些必须拆分、是否存在严重遗漏、实际调用方与测试证据、建议先开发的最小闭环，以及每条意见对应的源文件和 commit；在维护者批准前，不擅自把这五份草案标成 canonical architecture。
