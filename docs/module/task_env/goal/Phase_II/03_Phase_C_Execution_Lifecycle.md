# Phase C — Execution API & Runtime Lifecycle：架构、实施切片与验收

> **Phase C remaining design: PROPOSED.** C02a/C05a/C03a/C03b/C04 have bounded implementation receipts below;
> C02b remains BLOCKED, C02c and unified Environment migration remain incomplete.
> **2026-10-21 恢复规划修订**：位置控制候选与旧 force-aware 路线分流；之后维护者分别授权 C02b-P/E 与 C03b 有界实现。
> 当前 33 切片顺序与旧序号映射见 [05](05_Architecture_Review_and_Execution_Order.md#3-切片依赖与推荐执行顺序)，
> Recovery Review 及后续 E-S1/S2 进展见 [Recovery Review](C02b_Recovery_Architecture_Review.md)、[C02b-P Review](C02b_P_Position_Based_Profile_Review.md)、[C02b-E S1](C02b_E_Position_Profile_S1_Acceptance.md)、[C02b-E S2/H5](C02b_E_Position_Profile_S2_Acceptance.md) 与 [dual Entity Position receipt](C02b_Dual_Entity_Position_Acceptance.md)。C02b 仍 BLOCKED；历史收据不改写。
> 修订于 2026-10-20；源码基准 `develop@f292df149f41520b484ff27cf2ff78a584903013`，发布 v1.1.0。
> 总体与依赖：[`00_Phase_II_AD_Implementation_Blueprint.md`](00_Phase_II_AD_Implementation_Blueprint.md)；输入：[`01_Phase_A_Core_Object_Model.md`](01_Phase_A_Core_Object_Model.md)、[`02_Phase_B_Task_Semantics.md`](02_Phase_B_Task_Semantics.md)。

## C.0 设计目标 / Phase II 有效范围

**目标**：将 B 的 Task Artifact、A 的 Scene/Robot/Control Groups、D 的 Provider Runtime 组合成**单个**规范化 Environment，向用户提供稳定的 `reset()/step()/close()` 和明确的终止、Observation、Controller、Recorder 行为；Solution 在 Environment **之外**产生 Action。

**不做**：统一通用 Batch/Vectorization（Phase III）；通用 Agent Runner/Task Harness（E 延后）；强制所有 Controller 通过同一个硬编码 Panda 8D Action；执行时 Provider 热切换；旧 Selected Expert 路线未验证前直接删除。

用户已认可的 C 边界：

1. 先统一 scalar 公共行为和 lifecycle policy；通过既有 RuntimeBoundary/RuntimeSession 的适配保留薄 facade。
   不要求 selected 立即继承当前 `BaseTaskEnv`，不强制统一 storage/solver ABI，复用现有 Lifecycle Adapter。
2. `step_expert()` 不作为新标准 Env API：**Task/Environment 接收 Action、返回 Observation；外部 Solution 使用 obs/privileged state 推理动作**。PickCube/NutAssembly 旧方法在真实迁移前保留受限兼容。
3. Phase II 只设计 Single Environment；一个 Scene 内可以有多个 Robot，并非多个 Environment。
4. `obs` 可以同时包含 `state/privileged_state/rgb/depth/...`；`info` 放 Task/Execution Facts 与可选 Diagnostics。不因暂不做安全控制就混淆 Observation 语义。
5. 任务、Solution 分别有自己的 stage/completion 状态；`Task Success ≠ Solution Completion ≠ Episode Termination`。Environment 可不设 Success Evaluator。
6. Controller 配置应由 YAML 按 **Entity × Control Group** 指定默认；支持运行时安全修改 Controller，**不**支持 Provider 热切换。
7. 用户通过同一 Execution Configuration 简化/高级选择 Provider/Controller/Renderer；必须经过 Capability Admission。
8. Controller 内部必要 feedback 不等于用户可选 Diagnostics；慢速 LLM 推理不暗中推进模拟物理时间。

## C.1 当前真实执行路径与迁移风险

| 模块 | IMPLEMENTED | Phase II 拟修改的行为 |
| --- | --- | --- |
| [`task_env/registry.py`](../../../../../task_env/registry.py) | `make_env(uid, config, ...)`；selected 和 generic 两分支 | 一个配置解析/准入入口，不暗改旧 UID |
| [`task_env/environment/env.py`](../../../../../task_env/environment/env.py) | `BaseTaskEnv` 组合 Scene/Robot/Task/Runtime/Observations | 统一公共行为，允许薄 facade 过渡；避免巨大 God Object |
| [`task_env/environment/lifecycle.py`](../../../../../task_env/environment/lifecycle.py) | `TaskLifecycleAdapter` 共用语义，`SingleTaskLifecycleAdapter` 有 reset/step；success/failure 可终止 | 策略化 termination、stop/metadata，不另建 manager |
| [`task_env/tasks/reference_env.py`](../../../../../task_env/tasks/reference_env.py) | `SelectedReferenceEnv` own `step_expert()`/`_step()`/recording | 外部 Solution 接管 expert lifecycle，公用 `env.step(action)`；回归验证后退休兼容方法 |
| [`task_env/environment/config.py`](../../../../../task_env/environment/config.py) | 当前 `RobotControllerConfig` 基本是单 Robot controller | 扩展为 Entity/ControlGroup→Controller Binding，含 YAML 默认 |
| [`task_env/runtime/sessions/api.py`](../../../../../task_env/runtime/sessions/api.py) | advanced `RuntimeSession(reset/snapshot/step/close)`、Provider admission | 构造规划/Session reuse；无 native ABI 强制统一 |
| [`task_env/environment/protocols.py`](../../../../../task_env/environment/protocols.py) | 通用 `RuntimeBoundary` 与 advanced Session 是不同的集成协议 | 适配而非强行把两套接口“合并为一个 solver” |
| [`task_env/controllers/`](../../../../../task_env/controllers) | Panda pose/joint/gripper 控制、Canonical Feedback | Group Binding、控制状态所有权、切换 safepoint |
| [`task_env/observations/state.py`](../../../../../task_env/observations/state.py) | State/Privileged/Private/Vision field builders 和 schema | 保留现有 obs 分组，对不同 robot 扩展 typed schemas |
| [`task_env/recorders/`](../../../../../task_env/recorders) | `TransitionRecordWrapper`、H5 v2、T/T+1 规则 | Stop/Controller switch/Solution metadata 使用版本化事件，不能伪造物理 step |

**关键回归风险**：当前 NutAssembly 禁止 external action，并依赖旧 `step_expert()` 获取真实 Native-rate Guard Evidence、Readiness、11-stage Solution 所需反馈；如果仅把 `solution.act()` 移到外部却删除底层必要测量，属于功能破坏。旧 selected route 的成功后继续执行、录制和 terminal 不同于 Generic Gym Success Stop，不能一律改成 `terminated=success`。

### C.1.1 审阅建立的额外耦合

- [BaseTaskEnv](../../../../../task_env/environment/env.py#L113-L159) 直接 bootstrap GeoPhys，且拒绝多个
  resolved robots；[ControlledRuntimeSession](../../../../../task_env/runtime/sessions/control.py#L18-L35)
  限定七 arm targets 和一个 0.08 m gripper binding。统一继承不是接口适配的替代。
- NutAssembly [构造](../../../../../task_env/tasks/nut_assembly/task.py#L300-L371) 共享 arm_hold；
  Solution 修改 locked，ReferenceArmSchedule 读 `_lift_released` 决定 native ramp，
  controller identity 还包含 Solution identity。外置 Solution 必须迁移这些施控契约，不能只迁移 act/observe。
- [TransitionRecorder](../../../../../task_env/recorders/recorder.py#L104-L145) 将 action 转成 NumPy vector，
  [H5 writer](../../../../../task_env/recorders/h5.py#L150-L157) 按固定 components 堆叠。
  当前并不支持本页 proposed action tree；C05a 的存储工作必须前移。
- [scalar lifecycle](../../../../../task_env/environment/lifecycle.py#L468-L501) 在物理推进后仍可能于
  evaluation/capture 出错；新公共行为必须明确 fault/reset/close，不能在未知施控状态继续下一动作。

## C.2 分层代码架构

```text
Task Artifact (B) + Canonical Scene (A)
               +
Execution Configuration (Physics + Renderer + per-Group Controllers)
               │
               ▼
Config Resolution & Capability Admission
               │
               ▼
Execution Plan (resolved bindings, timebase, owner identities)
               │
               ▼
Existing thin Scalar Facade(s) / shared public behavior
 ├─ Scalar Lifecycle Adapter (reuse existing)
 ├─ Physics Runtime Adapter / RuntimeSession
 ├─ Controller Bindings (zero or more per Robot)
 ├─ Task Semantic Evaluator (B-owned memory)
 ├─ Observation/Sensor Pipeline
 └─ Episode Status + optional Recorder integration
               ▲
               │ Action / Lifecycle Command
External Solution / Human / Script / Future Experiment
```

**边界说明**：`Execution Plan` 可作为当前配置解析的不可变结果；不代表必须新增一个长期存在的 PlanManager。`BaseTaskEnv` 不持有 Solution 规划状态。外部 Solution 接收 public/privileged observations、optional normalized execution facts，产生 Control Action 或 Stop Decision。

### C.2.1 状态所有权表

| State | 唯一 Owner | Env 能做什么 | Recorder 记录什么 |
| --- | --- | --- | --- |
| 物理坐标/速度/接触/native solver | Physics Provider | 合法控制与 canonical read | measured canonical data + source ids |
| Entity/Frame/Scene 静态拓扑 | A Scene Definition/Materialization Map | 只读查询 refs | Scene/Asset hashes |
| Controller 增益积分项/上一 target/gripper memory | 对应 Controller 实例 | reset/step/switch lifecycle | config + target/applied + switch events |
| Temporal Predicate Memory | B Evaluator | reset/evaluate/snapshot when supported | semantic facts/identity |
| Episode status/horizon/stop reason | C Single Lifecycle | API 决定是否可 step | terminated/truncated/outcome |
| Solution stage/policy memory/readiness logic | 外部 Solution | 接收外部动作，不自行写阶段 | 外部执行协调者关联 source + diagnostics |
| Renderer cache / camera pending frame | D Renderer/Sensor | 请求 capture/close | capture identities/timestamps |
| Recorder buffer/H5 index | 已有 Recorder | public API/wrapper 控制启停 | T/T+1 与独立 events |

完整 snapshot/restore 需要同时覆盖以上所有相应 owner；本轮不得因 `RuntimeSnapshot` 或 selected H5 receipt 存在就声称 D0 可靠重构。

## C.3 配置：每个 Robot 的每个 Control Group 都可指定 Controller

### C.3.1 YAML 默认配置（**示意**）

```yaml
# PROPOSED; exact parsing/schema to be approved in C01/C02
execution:
  physics: {provider: geophys, backend: cpu}
  renderer:
    default: {provider: geophys, backend: rasterizer, profile: declared_rgb}
  controllers:
    robot_left:
      arm: {type: cartesian_pose, reference_frame: robot_left/base}
      hand: {type: joint_position}
    robot_right:
      arm: {type: absolute_joint}
      hand: {type: gripper_position}
  episode:
    horizon_steps: 6000
    stop_on_success: false
    stop_on_failure: true
    allow_external_stop: true
```

`robot_left` 等来自 A 的 Entity Instance，`arm/hand` 来自其 Control Groups。Asset 不应硬编码任务实例默认 Controller；Task 可以声明允许的 Action/Controller Requirements，具体 Binding 属 Execution Configuration。多 Controller 如果写同一组 Actuator，需显式 coordinator/arbitration，否则 Admission 拒绝。

首个基线默认拒绝 multi-writer，不建设通用 arbitration framework。Renderer provider 与 backend 是不同维度，
示例 profile 为待准入值，不代表当前已注册。固定拓扑内 Entity/Group 和 spaces 在 Env 生命周期内稳定；
新增拓扑 variant 或不同 action schema 需要重新构造 Env/wrapper。

### C.3.2 简洁/高级构造必须共用一个 Normalize Path

```python
# PROPOSED; not actual current API
make_env("pick_cube", physics_provider="geophys")  # 使用 YAML 中 controllers default
make_env("pick_cube", execution={"physics": {"provider": "mujoco"},
                                 "controllers": {"robot_left": {"arm": {"type": "absolute_joint"}}})
```

解析次序：Frozen Task Requirements → Scene/Robot Binding Defaults → Execution YAML → 用户明确 override → Single Normalized Execution Config → Static Admission → Materialization Validation → Environment。不允许两个 Factory 分别理解 `provider`/`controller`。User override 在 benchmark 下必须尊重冻结的合法范围。

## C.4 Structured Action、运行时 Controller Switch

**普通动作**通过 Entity/Control Group 命名空间：

```python
# Candidate structured action; old Panda vector can remain adapter input
{
  "robot_left":  {"arm": left_ee_target, "hand": left_finger_targets},
  "robot_right": {"arm": right_joint_targets, "hand": right_finger_targets}
}
```

动作维数/单位/参考 frame 由绑定的 Controller Action Contract 定义。单机械臂可有兼容向量入口；不能强制所有任务有 8D Panda Action。

Action Contract 还需声明所有 enabled groups 的必填/可选规则：默认缺失即拒绝；只有冻结 schema
显式允许时才 hold-last，并携带 target epoch/有效性。先校验全部 group 的 key、shape、finite、frame、
资源与 capability，再改变任一 controller memory 或施控。C05a 保留 raw action tree 与 schema identity，
不能通过 learner flatten 伪装存储兼容；target/applied 各自记录。

**建议 runtime controller replacement**（暂不冻结函数签名）：

- **兼容切换**：同一 Control Group、同一外部 Action Schema/Unit/Reference/Timing/Actuator Ownership，在完整 Control Interval 边界提交；验证新 Controller required feedback，初始化新 Controller State，避免遗留 target/force。
- **非兼容切换**：Cartesian Target ↔ Joint Position 等 schema 变化，重新构造 Env 及依赖 spaces 的
  wrapper/learner；本基线不提供仅 reset 后更换 shape 的捷径。旧 Env 不在 Episode 中偷换输入形状。
- **记录**：Controller identity、参数 hash、effective boundary、旧/新 binding、switch reason、readiness 与任何 discontinuity warning；不可默默影响 Frozen Experiment 比较。
- **失败原子性**：Admission 失败不得先丢弃旧有效 Controller；切换应用失败必须 fail-closed 标记 Episode/Runtime 状态，不能继续未知施控。
- **Provider hot-swap**：Phase II 明确不做；通过重新 `make_env()` 构造新 Runtime。

## C.5 Single Environment Lifecycle / Terminal 语义

### C.5.1 标准执行与唯一物理推进路径

```text
CREATED → PREPARED/ADMITTED → READY (after reset)
                                      │ step(action)
                                      ▼
                         Validate Action & Episode State
                                      │
                                Convert/Control
                                      │
                    Apply + N Native Physics Substeps
                                      │
                          Read Canonical Boundary State
                                      │
              B Semantic Evaluation + Observation/Sensor Capture
                                      │
                Episode Termination Policy + Recorder Transition
                                      │
                       READY or ENDED → reset or close
```

不得 step-before-reset、step-after-ended。执行异常（solver NaN/Capability missing/Controller crash）不算真实 Task Failure Episode；需单独 Execution Error，并提供异常后可否 reset/close 的显式规则。

失败原子性按实际完成边界报告：action validation 失败不改 owner memory/clock；control 已应用或部分 native
substeps 已完成后发生异常，进入 FAULTED，禁止再 step，不补造完整 transition。仅 owner 明确提供受验证
恢复路线时允许 reset，否则 close/recreate；记录最后完整 boundary、已知 native application receipts 与错误阶段。
多资源构造失败按已取得资源逐一 rollback；close 幂等且保持 exactly-once teardown，不引入第二个 lifecycle manager。

### C.5.2 Task Success / Solution Complete / Episode End 严格区分

| 事件 | 负责判断 | 是否天然触发 `terminated` | 说明 |
| --- | --- | --- | --- |
| `task_success_current` | B Task Evaluator（可选） | **否**，看合法 Termination Policy | 未设置 Evaluator ≠ 永远评估为失败 |
| `task_success_ever` | B 评估过程记录 | 否 | Post-success 后可发生回退 |
| `solution_completed` | 外部 Solution | 否 | 可能放弃或只完成规划，不等于物理成功 |
| `task_failure` | B Task Evaluator | 看策略 | 特定任务失败条件可定义正常终止 |
| `external_stop` | Env Lifecycle 收到授权 Stop Command | 按 Termination Policy | 一般任务外部提前截断；若任务将 Stop 定义为正常终止，才计 terminated |
| `horizon_reached` | Env Lifecycle | 通常 `truncated=True` | 保留 Gymnasium 语义 |
| `execution_error` | Runtime/Controller/Renderer | 不伪造 Task success/failure | 异常/独立 Episode Outcome |

例如 success 后继续夹爪松开/后退可以 `stop_on_success=false`，直到 external Stop 或 Horizon；Frozen Benchmark 的允许策略归 Task Evaluation Contract，具体选择记录 Execution/Experiment Identity。Stop 不得悄悄把 success 改为 True。

### C.5.3 Stop Command 采用独立 Lifecycle Entry

此前讨论最终倾向于**不**把立即停止塞进连续机器人 Action 向量或 `env.step(StopRequest)` 冒充物理 transition。

```python
# Conceptual API only
outcome = env.stop(reason="solution_completed")
```

外部 Solution 可以返回 `StopRequest` Decision，由用户 loop 路由至 `env.stop()`。Stop 操作：检查 Episode 在执行 → 不推进 Physics → 结束/截断 policy 结算 → 保存 Stop Event/Final Outcome，不额外编造 transition。终止标志按 Gymnasium 定义，常规外部提前停止通常为 truncated；具体 Task Definition 若将显式 Stop 视为目标终止事件，可版本化选择 `terminated`。必须处理 `stop()` 重复调用、已经结束、并发 Step、Reset 前 Stop 的异常/幂等性规则，Codex 审阅并冻结。

**Recorder T/T+1**：不因 Stop 生成零时间伪 Action/Transition；现有记录仅有真实 `step` 增量。`stop()` 对调用者返回 Episode Outcome 的具体类型待实现审议，避免强制伪造 Gymnasium 五元组。

**本轮选择**：Stop 产生独立、版本化 Boundary Event 与 EpisodeOutcome，绑定 episode/boundary/event sequence，
保留此前已返回 transition 的原 flags；不回写消费者已经读到的数据。常规 external stop 的 outcome 标记
truncation，loader/learner 必须按冻结 policy 从 final outcome 得到 end/bootstrap mask，不能只看最后 transition。
C05a 要让此解释在 raw file、reader、training conversion 中一致，并显式拒绝旧 reader 无法表达的新格式。
S1 包含 T=0、重复 Stop、reset 前/terminal 后 Stop、Stop 后 finalize/reset、切换与 capture 同 boundary 排序。
本基线为同步单调用路径；重入/并发 step-stop 请求明确拒绝，不暗示线程安全。

## C.6 Observation / Feedback / Wall Clock

- 标准：`reset(seed,options) → obs,info`；`step(action) → obs,reward,terminated,truncated,info`。
- **obs**：schema 统一的 `state`, `privileged_state`, optional `rgb`, `depth`, `segmentation`；保留现有 `private_state` 含义，不能未经迁移视为 privileged 的别名。
- **info**：基本 `task_metrics`, success/termination facts, elapsed clocks；高级 `execution_feedback` 与 diagnostics **可选**。Controller 内部必需反馈不得因用户关闭 Diagnostics 而消失。
- `Provider Native State` ≠ `Canonical State` ≠ `Public/Privileged Observation`；Task Success 可依赖真实 Canonical State 而不要求 Policy 也能看到该状态。
- 无 evaluator、unavailable、已评价 False 分开表示；v0 bool 字段经显式兼容投影保留，不以缺测为失败样本。
- Observation Schema 对每个 field 声明 shape/dtype/unit/frame/sampling/required capabilities；必需字段缺失 fail-closed，不被静默省略；Session/Capture 的时间边界按 D2/D3。
- 内层真实 Feedback：Panda gripper force / native Guard samples 必须与实际完成的物理区间对齐；不能用 Outer Snapshot 插值假装 500Hz 实测。
- LLM/slow Solution 推理等待时一般 **`simulation_time` 不推进**；wall-clock latency 分开记录；若某 Experiment 需要实时 Deadline，则独立声明、归上层执行协调者。

## C.7 Solution 解耦与既有 NutAssembly Guard 兼容

```text
External Solution (planner/RL/VLA/LLM/privileged policy)
   ├─ reads declared obs/info / normalized execution evidence
   ├─ owns Solution Stage, budgets, readiness/guard decisions
   └─ emits Control Action OR Stop Decision
                │
                ▼
           env.step(action)
                │
           Controller → Native interval(s)
                │
         Canonical state + truthful evidence
                │
                ▼
             obs/info  → External Solution.observe(...)
```

要求：

1. `step_expert` **不进入 vNext 标准 public API**，但旧 `SelectedReferenceEnv` 过渡期保留至所有生产调用迁移/相应回归通过。
2. 为 NutAssembly 独立 Solution 保留 Native Guard Samples、 Readiness/Warn/Stage 事实；不要让 Env 自行推断 Solution Completion。
3. Task success（物理谓词）、Solution completion（11-stage/retreat）、env terminated/truncated 分别记录；不可把 strict failure 重写成 pass。
4. NutAssembly 当前 external action 被拒，迁移必须**先完成可安全受控的 Control Action Admission**，必要时通过受限 Solution Control Plan 对外暴露，而不是删除 `external_action_error` 直接解禁所有输入。
5. 典型用户 loop 归用户脚本/未来 Experiment Runner；本轮可以更新 `examples/` 演示，不新增通用 `Runner(env,policy).run()`。
6. Solution 不再持有 Controller 的共享可变 hold 对象；在既有 action/control contract 内表达受限、
   版本化的 hold/release/ramp profile 请求，由 Controller 在 admitted boundary 应用并返回 acknowledgement。
   具体字段由 C05c 先 audit；Provider 不认识任务 stage，不能把私有 `_lift_released` 作为跨边界接口。
7. Native measurement producer 按声明需求提供原始 state/force/clock/validity；
   task-owned Solution 将它们组成 Guard 条件。必要采样与用户 diagnostics 开关无关，
   Controller/Runtime 不回调 Solution 来决定是否采样，测量本身不推进 Task semantic memory。
8. 新 controller/solution/execution identity 各自记录，不追求旧字符串相等；等价声明保护实际算法、sample、
   时钟、应用层、readiness warning/strict failure 和 task outcome，历史 H5 不改写。

## C.8 五个 Implementation Goals

### C01 — Resolved Execution Config / Admission Plan（a/b）

- **切片**：C01a 在 A02/B04a/D02a 后明确 normalize precedence、静态 plan 和 resource ownership；
  C01b 在 B05/B04b/D02b 后接入实际 requirements、actual manifests 与动态 realization。两切片均扩展现有 factory/config owner。
- **任务**：YAML defaults/override 共用 normalize；静态 admission→materialization→reset realization 分层。
  固定拓扑 variant 在 reset 解析；拓扑变化明确拒绝。D01a 可先用 v0 compatibility bridge，C01b 不要求新增 runtime。
- **验收**：同源配置得到同一 resolved identity；legacy selected/generic configs 仍清晰 fail-closed；不支持的 controller/provider/renderer 前置拒绝；没有构造一半 Runtime 就泄漏资源；支持切换 Provider 实例而不修改 Frozen Artifact。
- **Codex AUDIT**：对比 registry 的 `from_reference_config` 分流与 `resolve_env_config`，提出不复制 factory 的迁移方案。

#### C01b bounded dynamic admission receipt（2026-10-20）

C01b 复用现有 [`RuntimeSession.materialize()`](../../../../../task_env/runtime/sessions/api.py#L51-L73) 和
[`provider_manifest()`](../../../../../task_env/runtime/sessions/api.py#L36-L48)：Runtime admission 读取实际 selected
TaskArtifact 的 `required_capabilities`，按 `ExecutionSpec.physics_provider` 解析 manifest，并在任何 native
materializer 调用之前完成 capability、ExecutionSpec、source timebase/backend、Artifact identity 与 bindings 检查。
Manifest 的 provider version 由
[`provider_build_identity()`](../../../../../task_env/runtime/sessions/provenance.py#L8-L47) 绑定当前 GeoPhys checkout 或
MuJoCo package identity；它的 evidence 仍标为 `implementation_only_no_qualification`，不是 provider qualification。

当前实现已具备该 admission 路径，因此本切片不增加生产 API、Provider manifest registry、第二套 Runtime/TaskEnv 或
config-to-runtime factory；新增 `test_phase_ii_c01b_dynamic_admission.py` 锁定跨 owner 行为。PickCube 与 NutAssembly
真实 selected v0 Artifact 的七项 requirements 分别通过当前 GeoPhys 与 MuJoCo manifest admission（同一 Artifact
requirements 不因 provider 选择改变）。负向检查证明：将 `contact_detection` 加入实际 Task requirements，即使调用者
提供扩大后的 manifest，当前 provider manifest 仍拒绝；调用者的 restrictive manifest 可拒绝 `frame_pose_query`；
CUDA backend 与当前 CPU manifest 不匹配，以及非 `none` renderer 均在 native materializer 之前明确拒绝。

C01b、C01a、selected reference construction/consumer 定向回归组合 **59 passed, 0 failed, 0 errors**；当前受测实现为
`006801074052c51db9845ccf64be1d21fc08609c`，GeoPhys pin 为 `4436787e9cb85ce519506a2a9af86d1eeec9de2d`，MuJoCo
package version 为 `3.8.1`。PickCube / NutAssembly v0 Artifact identities 分别为
`fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4` /
`99e374bd870c70f0dd427e34c47c6e6820aaa7067365133181a001a38239b9fe`；GeoPhys / MuJoCo manifest identity hashes 为
`f3b70b029a1514e0aeedd2a61125387f8a6b0c64c25eed0d13f5de479b7f9ab6` /
`af5368b98f1b28101ab989e3334032599e0d0d8d1ccbeecf3d0e88e60a48760f`。完整 argv、environment、测试源码 SHA-256、
stdout/stderr hashes 和完整 Provider build identities 见本地
`workspace/maintenance/phase_ii_c01b_20261020_001/run_metadata.json`。C01a 的静态 `ExecutionPlan` 和旧
`ResolvedEnvConfig` 路由保持原样；SelectedReferenceEnv 仍经原有 task factory。序号 18 的验证只证明 v0 Artifact 的
动态 admission 与兼容路径，不证明 TaskArtifact v1 native materialization、D01b、SAPIEN/Genesis、完整 rollout 或
Qualification；这些仍须各自满足后续 Goal 的真实 provider gates。

### C02 — Controller Binding / Atomic Execution / Safe Switch（a/b/c）

- **切片**：C02a 在 A03/C01b/D02b 后确定 bindings、完整 action/feedback schema；
  C02b 在 C02a/C03a/C04/C05a2/D01b 后开放实际原子执行；内部先 P（Profile 审计与进入条件）、后 E（执行与证据）。
  C02c 在 C02b/C03b/C05a2 后做受限同 schema 安全切换，不要求等待完整 C05c；具名任务未经验证的切换仍拒绝。
- **验收**：arm+hand 有真实受限 S2；双臂先静态，实际支持另需 D01b 双 Robot binding/S2。
  缺 Group/extra key/NaN 必须在任何 owner mutation 前拒绝；重叠 writer 拒绝；
  同 schema switch 的 initialization、effective boundary、applied acknowledgement、failure atomicity 可测。
  非兼容 schema 必须新 Env/wrapper。旧 Panda 输出保护，未测 multi-robot 不宣称执行支持。
- **Codex AUDIT**：精确追踪已有 `RobotControllerHandle`, `ProductionCanonicalPandaController` 以及 `ControlledRuntimeSession` 的 owner/feedback 状态，不复制控制代码。

#### C02b-P / C02b-E recovery contract（2026-10-22，Position 单/双 Entity 有界切片通过；完整 C02b 未完成）

**状态**：C02b 仍为 BLOCKED。单 Panda Position candidate 与最小双 Entity Position candidate 已分别完成其声明范围的 S1、GeoPhys/MuJoCo CPU native S2 与 Generic H5 v3 真写读；force-aware `production-r1` 与完整 C02b 交集仍未完成。双 Entity 是两个独立 Scene root，不构成 Assembly。它与现有
`panda-main/production-r1` 保留不同的 writer/profile/binding identity；R1 raw `actuator_force` requirement 未删除、未改 optional、未填零，force-aware reset freshness 缺陷不因位置路线通过而关闭。

C02b-P 源码审阅与 C02b-E S1/S2/H5 验收分别见 [Position-based Profile Review](C02b_P_Position_Based_Profile_Review.md)、[C02b-E S1 Acceptance](C02b_E_Position_Profile_S1_Acceptance.md) 和 [C02b-E S2/H5 Acceptance](C02b_E_Position_Profile_S2_Acceptance.md)。A05 hand-origin TCP 勘误和 S1/S2/H5 分层退出标准以这些记录为准。
本次 P00/P99 最小双 Entity position-only 证据见 [C02b 双 Entity Position Acceptance](C02b_Dual_Entity_Position_Acceptance.md)。

**C02b-P — Profile 与完整消费链**：已复用 `CanonicalPandaController` 的 DLS/position servo，
或在现有 Controller owner 中组合已有位置型 gripper；不重写控制算法。首条候选为同一 Panda Entity、arm/gripper
两个 Group、一个既有 writer、CPU、100 Hz 外层/五个 2 ms native steps。真实 required state 包括 arm/finger
joint positions 和 EE world pose；绑定 source/kinematic model、frame、unit、clock 与 reset 有效性，
不以静态 writer 字符串代替实际 Controller instance/config/identity 校验。

须明确解决以下现有调用耦合，不能只替换 Controller 类：

- `SelectedReferenceEnv.reset/_step` 无条件读取 `control_feedback()`，并使用 R1 reset/compute/readiness 接口。
  新位置路线不能直接复用这些调用；在既有执行 owner 内明确 Profile 所需的接口和受限适配，不新建 Env/Runtime。
- GeoPhys `snapshot()` 默认不请求力，但 `control_feedback()` 请求 raw force；MuJoCo reset 和 controlled step
  还会复制 `actuator_force` 缓存。新 Profile 全链不得进行此测量查询/复制；legacy 默认路径保持兼容。
  Provider 内部正常计算执行器力属于物理求解，和 Core/Controller 读取该信号是不同操作。
- 旧 canonical `BoundaryRecord` 强制包含 force feedback/readiness，不能用零值冒充位置路线数据。
  首条候选优先使用现有 `CanonicalStatePublicationV1`/state 与 generic H5 v3 structured controls/events/outcome，
  明确记录测得的位置、请求、target/applied 和边界。旧 canonical/execution bytes 与 readers 保持；
  若未来需要其支持 position-only boundary，须在原 owner 内另审版本化扩展。

`force_limit_N` 仍可作为 position servo 配置及 physical actuator cap 下发；这不意味着查询 measured force。
新 Profile 必须显式记录其限幅/servo 参数，不冒称与 R1 的 30 N 闭环、readiness 或任务行为等价。
Composite preset/leaf override 在未来展开为一个不可变 Effective Plan，父 preset 不增加 writer；
递归 Robot Assembly、跨 Entity attachment、whole-body IK 不属于本检查点。

**C02b-E — 实际执行**：Position candidate 通过 `SelectedReferenceEnv.from_position_candidate()` 显式进入既有 `ReferenceTaskBinding`/SelectedReferenceEnv lifecycle；没有新增默认 registry。沿用 `compile_control_binding_plan()`/`prepare_structured_action()` 全组预检、source-bound target/boundary identity、现有 `RuntimeSession.step()`、typed publication 与 C03a fault latch。固定 ResetPlan 的 omitted seed 使用绑定 seed；不匹配的显式 seed 在修改 live Position session 前拒绝。既有单 writer Position 路径保持；新增的精确双 Entity candidate 仅准入 `panda-main` 与 `panda-secondary` 两个独立 writer、各自完整 arm/gripper Groups 和互不重叠的 16 个 actuator resources。所有 Entity/Group/action/target/ack/state 均保留 Entity-qualified 身份；两 writer 的动作和 source boundary 全组预检后才 compute/apply。
GeoPhys/MuJoCo CPU 两个独立进程用相同 hash-bound candidate/sample 完成 64 个真实 outer controls 和每区间五个 2 ms 的 native-clock evidence。Generic H5 v3 记录 reset observation、64 个 structured controls、65 个 boundary observations 与 outcome；结构化 reader、training projection 和磁盘 joint/hand/boundary identity leaves 均回读通过。clock 的五步数由公开 native-time delta 推断，不冒称 RuntimeSession 提供独立 native completion counter。apply、post-step、record fault injection 均复用 C03a fault latch；record failure 不留半条 transition。

最终定向回归覆盖 Position profile/execution/H5、C02b admission、C02a controller bindings、C03a fault lifecycle、C05a structured recording、D02b typed runtime state 与 selected consumers：**92 passed**，一条上游 `taichi_forge` `locale.getdefaultlocale` 弃用告警。未运行完整仓库回归。

**验收层次**：单/双 Entity Position 的声明范围内，S1 身份与资源冲突/拒绝边界、target freshness、双 writer 完整预检，及 S2 双 Provider 真执行、状态与 H5 v3 回读通过。双 Entity partial-apply 注入显示首 writer 已 ack、第二 writer apply 被拒、native clock 未推进、C03a fault latch 生效且没有伪 transition；不声称跨 Entity 物理回滚。被动 Entity 的关节可能因物理响应漂移，隔离判断依据是实际资源目标、Entity-local target/ack 与单独的命令关节运动。receipt 不覆盖 obstructed/force-hold、force-aware R1、NutAssembly Guard 或 full Expert。S3/其他真实 task 主线与完整 C02b qualification 尚未通过；S2/H5 是 E 的后层退出标准，不是开工前置。

**完成边界**：C02b-P/E 不增加正式切片数。单/双 Entity position-profile S2 只关闭各自的声明交集；P00/P99 的最小双 Entity position-only 独立施控子项已有真实 D01/C02 Evidence，但不代表任意多 Entity/writer、其他 Provider 或 Assembly 支持，也不能将完整 C02b 标为完成。
未覆盖必需交集时明确 partial，P99 不得标 complete。C05b/C05c 的旧 Solution/readiness/Native Guard 保真另验；
需要 force 的 consumer 仍受 freshness gate 约束。

**C02c 契约**：同外部 action schema/frame/unit/timebase/actuator ownership 的实例切换只在最后一个完整、
非 terminal 的公开控制边界生效。切换前验证现有 Profile 类型、构造 identity/config、required state、source closure、
source/resource binding、Scene/Artifact、Action schema、Frame/TCP 与 ControlBindingPlan；拒绝路径不得改变 active
Profile/session admission 或其 memory。切换要求活动 Generic H5 v3 Recorder，以既有 BoundaryEventV1 记录请求、
切换前后 identity、参数、结果、effective boundary 与 clock。新 Profile 的 mid-episode memory 只在最终 RuntimeSession
提交点以该 boundary 初始化，不调用 reset()；reset() 仍只接受 step 0/time 0。切换本身不 compute、不 apply、不 step、
不追加 transition；T boundary 的切换事件之后，T→T+1 的首个普通 step 才记录新 Profile target 和对应 applied ack。
旧 identity target 在切换后拒绝。一个 switch 的首个完整 step/ack 记录前禁止再次 switch；该 transition 通过同一
switch ID 关联 event、source boundary、target 和 applied acknowledgement。episode 在首个 step 前结束时，EpisodeEnd 明确记录
“effective, not applied”。Recorder Event 在实际提交后写入失败时，复用 C03a fault latch、禁止续步，并把提交已生效、
Event 缺失及首个控制未尝试的 receipt 写入 EpisodeEnd；不承诺 Provider 原生回滚。非兼容 schema/frame/unit/timebase/
ownership、新 Env terminal/faulted/stopped/closed/horizon 状态和无效 boundary 均拒绝。父 preset 状态仍由有效配置推导，
不增加第二个 authority；未验证 NutAssembly、R1/force-aware、双 Entity 切换仍拒绝。

#### C02c bounded single-Panda Position receipt（2026-10-22）

本轮只在已验证的单 Panda Position C02b 交集实现实例替换：复用
`PandaPositionServoProfileV1`、`ControlBindingPlanV1`、`SelectedReferenceEnv` lifecycle、既有 RuntimeSession 和
Generic H5 v3 Recorder，没有新增 Runtime、TaskEnv、Recorder、Provider 或切换 registry。只允许 `panda-main` 单 writer、
GeoPhys CPU/MuJoCo CPU、A05 Scene-v3 固定 ResetPlan 的显式 Position candidate；需先启动 v3 recording，且当前状态、
typed publication、public clock 与 Recorder T/T+1 对齐。替换 Profile 的 ActionConfig 必须与当前实例不同，identity 也必须不同；
action schema、Scene/Artifact/source closure、required state、hand-origin TCP/frame、100 Hz/五个 2 ms timebase、joint 与
actuator 资源映射和 writer ownership 必须完全一致。切换仅在当前 episode 有效，reset 按原 candidate builder 重建基线 Profile。

切换准备是无副作用校验，候选 memory 在 RuntimeSession 最终提交前保持 fresh；提交初始化 memory cursor 为 T，并同步 session、
SelectedReferenceEnv 当前 Profile 指针。当前 `CanonicalPandaController` 对 Position candidate 是 stateless 的；Profile memory
仅含 plan identity、episode/reset identity、next control step 和 activation boundary，不继承或复制旧实例的 memory。
BoundaryEventV1 在 T 记录 request、old/new identity 与 ActionConfig、validated/effective
状态和确切 StateBoundary/clock。首个 T→T+1 真实控制记录新 identity 的 source-bound target、匹配 ack 和 switch ID；在这条完整
transition 前再次切换被拒绝。旧 Profile 即使为同一 T 边界生成 shadow target，也在 Provider apply 前因 identity 不符而拒绝。
episode 若在首步之前结束，end Event 标记 effective/not-applied。提交后的 Recorder 写入故障用 C03a latch 锁住当前环境；
EpisodeEnd event 保留 request、两侧 Profile/config、boundary/clock 和 failure receipt，零 transition 不会伪增。

S1：`test_phase_ii_c02c_position_switch.py` **16 passed**，覆盖 step-0 reset 合同、合法中途切换、无 dispatch/物理/transition、
旧 target、schema/frame/required-state/source/resource/timebase/identity/config 拒绝、无 active recorder 与错位 boundary、
closed/faulted/stopped/horizon guard 和提交后 Event 写入故障。S2：GeoPhys CPU 与 MuJoCo CPU 各由独立进程完成真实
step→切换→step；参数 `ik_position_gain` 从 0.9 改为 0.45，同一请求下实际 arm target 不同，切换时 compute/apply/step 均为 0，
下一步各为 1，公开时钟从 T=1/0.010 s 到 T+1=2/0.020 s 并对应五个 2 ms 子步。H5 v3 读回 2 transitions/3 observations、
切换 Event、switch ID→target/ack 关联与 boundary、关节/hand/boundary identity 三组 state leaves。最终版忽略 Evidence receipts
位于 `workspace/maintenance/c02c_single_position_switch_20261022-r3/{geophys,mujoco}/`，定向回归 stdout 位于
`workspace/maintenance/c02c_single_position_switch_20261022-r3/test-results/targeted-regressions.log`。

此 receipt 只关闭 C02c 的单 Panda Position/GeoPhys CPU/MuJoCo CPU bounded slice；完整 C02c 仍未完成。未覆盖 dual Entity
同时切换、R1/force-aware 切换、NutAssembly Guard、Assembly、Camera observation、其他 Profile/provider/backend 或一般 Controller
arbitration。完整 C02b 仍 BLOCKED，Phase II 未完成。

#### C02a bounded implementation receipt（2026-10-21）

`task_env/runtime/sessions/control.py` 现在提供 Scene-v3 validated `ControlBindingPlanV1` 编译及纯
`prepare_structured_action()` 预检：每个 Entity×ControlGroup 恰有一个现有 Controller writer，每个 writer 的
现有 `ActionModeSpec` components 被各组精确分区，actuator resource 唯一归属；反馈声明复用已有
`StateRequirements`，并验证其引用落在声明的 Scene Entity/Joint/Frame/Actuator。绑定 identity 同时覆盖
Scene、action schema、feedback requirements 和 writer/group 映射。完整请求必须匹配 Scene 与 binding identity，
并提供所有 group 一次且仅一次；schema、维数、finite 值和 quaternion 均预检后，才返回按现有 writer 组合的
`RequestedAction`。非法请求不调用或改写 Controller/Runtime。

回归命令 `PYTHONPATH=GeoPhys/src:. /home/lly/miniconda3/envs/geochora/bin/python -m pytest -q
task_env/diagnostics/tasks/test_phase_ii_c02a_controller_bindings.py` 为 **11 passed**；含 A05 Panda arm+gripper
由同一个现有生产 Controller 接收的绑定、拒绝路径，以及 legacy 8D action/feedback/output 在 GeoPhys CPU 和
MuJoCo CPU 上各执行一步。与 C01a/C01b、D01a/D01b、D02b、D05a、A04/A05、B04b、selected consumer 的定向
交叉回归为 **87 passed**；`git diff --check` 通过。仅有 Taichi 上游 `locale.getdefaultlocale` deprecation warning。

该结果只关闭 C02a 静态绑定与 action preflight gate：没有 dispatch 多个 group、没有实现 C02b 原子多组执行，
没有证明双机器人控制，也未扩展 provider manifest。现有 `StateRequirements` 可以表达 actuator-force feedback，
但当前 provider `CAPABILITIES` 尚未声明 `actuator_force_query`；该 feedback 在相关 provider 上仍需 admission
拒绝或由后续 provider capability 切片补齐。实现和测试位于
[`control.py`](../../../../../task_env/runtime/sessions/control.py) 与
[`test_phase_ii_c02a_controller_bindings.py`](../../../../../task_env/diagnostics/tasks/test_phase_ii_c02a_controller_bindings.py)。

### C03 — Scalar Execution / Fault Policy / Stop（a/b）

- **切片**：C03a 在 C02a/D01b/C05a2 后以现有 ports/adapter 接入 reset/step/fault，
  先保留单 controller 兼容执行；C03b 在 C03a/C04/C05a2 后于现有 lifecycle/Recorder/Environment owners 加入 termination policy 和 Stop（bounded receipt 在本节下方）。
- **任务**：先统一公共行为，允许两薄 facade 过渡，不强制 selected 继承旧 BaseTaskEnv；
  保留 generic ignore_done、selected success 后动作及默认 horizon 的既有语义。
- **验收**：Gymnasium 5-tuple、reset-before-step、post-terminal guard、success-post-success、no-success、stop-early/horizon 的 flags 和 clock；Stop 不产生物理 step/伪 transition；旧 UID 按兼容路由保持行为至 C05 迁移。
- **补充 Gate**：故障后禁止续步；partial interval 不保存为成功 transition；Stop outcome/loader bootstrap 一致；
  共享 TaskLifecycleAdapter 修改需 Pendulum scalar/batch targeted regression，不因 Phase III 延后而豁免。
- **Codex AUDIT**：指出 `SingleTaskLifecycleAdapter.resolve_scalar_done` 与 Selected `_step` 的主要差异；不能用一次强制成功终止破坏 NutAssembly。

#### C03b bounded Stop/Outcome receipt（2026-10-21）

在本地 C02b 检查点 `d99941c` 之上，只扩展现有 `SingleTaskLifecycleAdapter`、`BaseTaskEnv`、显式 Position candidate、
`TransitionRecorder`、`TransitionRecordWrapper` 与 Generic H5 v3 reader；未新增 Lifecycle Manager、Environment、Recorder 或
Provider 抽象。`EpisodeTerminationPolicyV1` 由既有 `TaskDefinitionBase` 提供：default success/failure terminal，external Stop
truncated/bootstrap allowed，horizon truncated/bootstrap allowed；terminated outcome 禁止 bootstrap。step 仍返回旧 Gymnasium
flags；当 terminal 与 horizon 同时为真时，Outcome 选 task terminal，但不改写 step flags。Selected Position candidate
保留 success 后继续控制；旧 selected `production-r1` 的行为/identity/required force feedback 不变，Stop 显式拒绝。

`env.stop(reason)` 返回 `EpisodeEndV1`（有序 `episode_ended` BoundaryEvent 与 EpisodeOutcome），只引用最后完整公开边界，不调用
Controller、不施控、不推进物理。T=0 Stop、重复 Stop、terminal/horizon 后 Stop、reset 前 Stop、fault 后 Stop、close 后 Stop 均有
确定行为。generic reset 在结束当前 active episode 后创建新 episode，并在新 reset info 返回 `previous_episode_end_v1`；close
在 teardown 前结束 active lifecycle。Generic Step 的公开结果构造失败时，先撤销未返回 step 的 finalizer boundary，再锁存
execution fault；fault Event 保留真实 after-clock，而 Stop 与 Outcome 留在前一条可见边界。Position candidate 以同样的 published
boundary 区分物理 after-clock 与成功提交的 transition。

Recorder `end_episode(..., end_event=...)` 在一次性提交前校验 T/T+1、outcome/event identity、boundary 与 sequence；重复 finalize
拒绝。`TransitionRecordWrapper` 保留 v2 路径，active v2 Stop/close 明确拒绝；v3 仅接受显式声明每步发布 typed
`StructuredControlTransitionV1` 的环境，external Stop/自然结束都用 Event/Outcome finalization，active reset/manual v3 end
拒绝。当前没有 generic TaskEnv 被声明支持该 wrapper v3 route；Position candidate 通过其现有 direct Generic H5 v3 route
写入。Vector wrapper、legacy R1 Stop 和无 structured control 的 Pendulum v3 wrapper 明确拒绝。

`load_structured_training_episode_h5()` 在既有 exact one-writer action projection 上组合读取 raw transition terminated/truncated、
final outcome 和 bootstrap policy；external Stop 不回写先前 `step()` flags，返回的 per-transition effective bootstrap 单独使用
final Outcome 覆盖最后一个 transition decision。

缺陷敏感 S1：`test_phase_ii_c03b_stop_outcome.py` 覆盖 T=0/idempotent Stop、reset/close/fault、terminal+horizon 同时 flags、reset
自动 end、v2 Stop 拒绝前无 mutation、v3 wrapper typed-control gate、Event/Outcome atomic finalizer、H5 outcome/action/flag/bootstrap
consumer。结合 Position close 的 active v3 recording exactly-once 回归、C03a fault lifecycle、C05a structured recording、C02b Position H5 和 selected consumers，定向组合 **78 passed**；
仅有上游 Taichi `locale.getdefaultlocale` 弃用告警。真实 S2 脚本为
[`c03b_stop_s2_probe.py`](../../../../../task_env/diagnostics/tasks/c03b_stop_s2_probe.py)，GeoPhys 与 MuJoCo 由独立进程运行，输出位于
ignored `workspace/maintenance/c03b_stop_20261021/final_run/{geophys,mujoco}/c03b-stop-s2-report.json`。

S2 两 Provider 的 C02b Position candidate 均通过 T=0 与 T=1 Stop：Stop 前后 Controller compute、apply、native step 计数为零；
T/T+1 与 Event/Outcome 在 Generic H5 v3 真写读一致；外部 Stop 后 transition flags 仍为 false/false，最终 Outcome 是
`truncated=true, bootstrap_allowed=true`，training loader 保留两类语义。成功 task predicate 继续执行且在 external Stop Outcome 中
保留 `task_success=true`。另外在每 Provider 注入一次真实物理 step 后的 Recorder append 故障：Runtime clock 已到 1/10 ms，Stop
final boundary 仍为已发布的 0，fault 为 `advanced/transition_status=rejected`，H5 为 T=0/T+1=1，无伪 transition，fault Outcome
禁止 bootstrap。

Pendulum 仅通过现有 GeoPhys CPU scalar `BaseTaskEnv` 路径测试 T=0/T=1 Stop 的 clock 不变、reset 后携带上一 EpisodeEnd、重复
Stop 与 Stop 后 step 拒绝；Gym v2 活跃录制 Stop 在调用 Env 前明确拒绝。通用 `ExecutionPlan` 固定声明 GeoPhys provider，因此
MuJoCo Pendulum 为 `NOT_ADMITTED`，不是失败或支持结论。structured v3 wrapper 正常写读只用显式 contract fixture 验证；当前没有
真实 generic Env 声明该能力。未运行 learner 全算法迁移、vectorized Stop、NutAssembly R3 Guard、双 Entity、Assembly、R1 force
refresh、完整 C02b 或 Phase II qualification。C02b 仍 **BLOCKED**；本 receipt 不将其或 Phase II 标为完成。

### C04 — Unified Observation & Optional Diagnostics

- **依赖**：C03a、D02b；Camera 先消费 D05a 的 metadata/selection 契约，D04 后补真实模态实现。
- **任务**：统一 public+privileged obs schema 与 `info`；标准执行事实、必要 feedback、用户可选 Diagnostics 分开；Renderer Camera metadata 的位置/引用契约明确。
- **验收**：`observation_space.contains(obs)`、字段必需缺失失败、Reset/Step 同 Schema、frame/time 符合 S1；打开/关闭 diagnostics 不改变 Controller 物理结果；已有 `private_state` 行为保护。
- **Codex AUDIT**：现有 `StateObservationBuilder` 是否足以扩展，不要造第二个大型 Obs Pipeline。

### C05 — Storage Compatibility / External Solutions（a1/a2/a3/b/c）

- **C05a1**：依赖 C02a/C01b/D05a；structured request、target/applied、Boundary Event、EpisodeOutcome 的
  版本/值语义和 Stop finalizer 合同。已有共用值契约直接复用；实际 Stop/finalizer 行为在 C03b 验收。
- **C05a2**：依赖 C05a1；在既有 generic H5 owner 提供 vNext、reader/最低训练 loader、T/T+1 和
  end/bootstrap 准入。已有 H5 v3/单 writer 投影证据复用，non-arm 和 outcome 消费缺口逐项补证，不默认全通过。
- **C05a3**：依赖 C05a1/C05a2；既有 canonical/execution 格式适配、未知版本拒绝和各自 legacy detector。
  已有 outer v1/stream v3 实现复用，不重复建设 Recorder 或改历史 bytes。
- **状态映射**：原 C05a 完成收据保持原样；它是 bounded storage evidence，不自动等于新三切片的全部 P00 退出条件。
  [05 的映射表](05_Architecture_Review_and_Execution_Order.md#32-c05a-既有证据与三切片映射)逐项列明已有/未证实范围，
  不因拆分撤销 C03a/C04 已有受限验收，也不把未证实的 consumer gate 记为通过。
- **C05b**：依赖 C02b/C03b/C04/C05a3，迁移 PickCube external Solution，证明 action→step→record 路线。
- **C05c**：依赖 C05b/D02b，先审定 native feedback/hold/ramp 契约再迁移 NutAssembly；
  分别证明 measured 500 Hz、Guard、arm schedule、Outcome V1 与 strict warning/failure 保真。
  无法证明时保留旧 step_expert，不能仅删除 external_action_error。
- **验收**：同 frozen sample/config 在 GeoPhys/MuJoCo 已实现的受限 selected route 上，success/current-success/expert outcome/Guard/clock/recording 与旧基线有据可查；记录 T/T+1、Stop Events；不宣称完整 checkpoint replay；S2/S3 未跑标记缺口；兼容方法在所有 caller 迁移前不能删除。
- **完整 C05 Gate**：C05a1/a2/a3/b/c 分别有退出证据映射或 receipt，真实采集/读取及适用的 replay validity 独立报告；
  旧方法退休另需 production callers/examples/tests/docs 迁移及非回归，不与“新接口已存在”绑定。
  精确依赖及顺序见 [执行表](05_Architecture_Review_and_Execution_Order.md#3-切片依赖与推荐执行顺序)。
- **Codex AUDIT**：提供旧 `step_expert → solution.act → _step → controller → feedback → solution.observe → recorder` 的完整调用图，逐步证明等价。

#### C05a bounded storage receipt（2026-10-21）

三个既有格式 owner 均采用 additive version dispatch：generic `task-env-h5/v3`、canonical outer
`canonical-trajectory-v1`、execution `canonical-execution-trajectory-v3`。共享的
`BoundaryEventV1` / `EpisodeOutcomeV1` / `StructuredControlTransitionV1` 是 value contracts，不新增 Recorder。
每种 writer/reader 都保留自己的旧 layout，旧 H5/JSON fixtures 没有迁写；generic H5 的现有 Training
projection 只接受 one-writer 且 Action schema id/component order 精确一致，并要求投影值逐项等于现有 action
dataset；canonical/execution 的专用 converter 同样拒绝多 writer。新的 stored outcome 与先前返回的
transition flags 分离；终止后禁止 bootstrap，截断 bootstrap 显式决定。Events 只能在 0..T boundary 排序；T=0
仅含 outcome/event 是有效存储，没有伪 transition；execution pending interval 一律禁止 freeze。

专项 `test_phase_ii_c05a_structured_recording.py` 为 **7 passed**，覆盖三种真实 H5 write/read、streaming exact
roundtrip、T=0、outcome/bootstrap、单 writer conversion 与不匹配 action dataset 拒绝、partial interval 和旧 schema
版本界定。最终定向组合包含 C05a、record CLI、selected consumers 与 execution streaming，结果为 **82 passed、2
deselected**；两项 deselected runner 依赖已退休的 `task_env.tasks.nut_assembly.assets`。此前未排除它们的较小组合为
**52 passed、2 failed**，失败均发生在导入该历史 integration runner 时，不涉及本次执行路径。这些结果证明存储/reader
契约和 legacy route 回归，不是 selected v3 真实采集、D0 replay 或正式 Qualification。现有
`validate_trajectory()` transcode 仍只接受 v2，已对 v3 给出明确拒绝；selected reference replay 也不把 canonical
outer v1 当 replay 输入。

#### C03a bounded scalar lifecycle and fault receipt（2026-10-21）

在 `codex/phase-ii-c` 的受测提交基线 `7139eba31a979e062043cbfa3a20316258f31dd4` 上，C03a 仅扩展现有
`SingleTaskLifecycleAdapter`、`BaseTaskEnv` 与 `SelectedReferenceEnv`，未引入第二套 Runtime、Lifecycle Manager、
具体 Env 基类或 Provider 抽象。Generic route 继续使用 `RuntimeBoundary`；selected route 继续使用现有
`RuntimeSession` / interval callback，保留单个现有 Controller 的执行方式。

新增 `ExecutionFaultV1` 作为 owner-local、可序列化的失败 receipt，并由 `task_env.environment` 导出。已构造 Env
在 lifecycle 失败后可读 `env.execution_fault`；construction 失败保留原异常类型并附带 `exception.execution_fault`。
receipt 记录失败 phase、原异常类型/消息、可读到的前后控制步和 simulation clock、native substeps 计数及
readback error。`physical_progress` 只表达**当前控制区间**的可观测进展：`not_advanced`、`partially_advanced`、
`advanced` 或 `unknown`；不表示物理回滚能力。Generic Runtime 与 selected route 都以可信 public snapshot 的
前后 simulation clock、预期 control dt 为进度依据；interval 是否返回、control-step 边界及 observer/Recorder
计数仅作交叉验证。receipt 分别记录 `observer_confirmed_substeps`、`recorder_confirmed_substeps` 和
`native_substeps_expected`，绝不把 callback 数直接当成精确物理完成数。时钟不可读、时钟与执行证据冲突、
或不足以判断区间进度时均为 `unknown`。

两条 route 在 reset/step 构造或后处理失败后均 fail-closed：保留触发时异常类型，设置 fault，后续 step 必须先
成功 reset。Generic action conversion 发生在任何施控前；selected expert proposal/内部 action 校验失败也会闭锁，
而既有 selected 外部/Expert 模式边界保持兼容。Reset 成功才清除故障。控制区间只要未完整返回，就不会生成有效
transition：generic wrapper 仅在 env step 成功后 append；selected execution Recorder 保留 pending interval，
其既有 `freeze()` 明确拒绝 `incomplete effective interval`。receipt 的 `transition_status` 独立标注 owner 是否
评估（`not_assessed`）、没有录制（`not_recorded`）、`incomplete`、`rejected` 或已确认的 `valid`；物理区间即使完整推进，
只要 Recorder 证据未形成完整 transition，仍保留 pending 并拒绝 freeze。该 pending recording 也会阻止 reset；当前 route 需 close/recreate，
C03a 不新增丢弃 API。代码不会回滚 provider 已推进的物理状态。

正常 gate 由真实 Pendulum GeoPhys CPU `reset → 两次 step → close` 覆盖：返回 5-tuple、声明 timebase clock、horizon
`truncated=True`、terminal 后禁止续步；真实 A05 Panda arm+hand legacy action/feedback 在 GeoPhys CPU 与 MuJoCo CPU 的
C02a 定向执行回归为 **11 passed**。Fault/compatibility 定向组合为 **62 passed**，含 construction、control apply、
physics 前置失败、partial substep、readback/evaluation 故障、闭锁/reset 恢复、selected pending recorder 拒绝，及
selected Task success 后 Expert 继续至 Expert 自己完成；Pendulum B03a/B03b scalar/batch semantics 回归包含其中。
C05a/record CLI/selected consumers/streaming 组合为 **85 passed、2 deselected**；两项仍因 historical runner 导入已退休
`task_env.tasks.nut_assembly.assets` 而 deselect。日志留在本地 ignored
`workspace/maintenance/phase_ii_c03a_20261021/`，命令和输出文件清单见 `run_metadata.json`。
TaskEnv module Skill 已按现有 failure behavior 刷新；`check_module_skill.py` 静态校验通过。

证据仅覆盖现有 generic Pendulum scalar CPU 与 A05 Panda selected legacy compatibility 交集，以及合成故障注入的
生命周期边界；它不是新 Provider qualification、partial-state recovery、全 selected source S2、C03b Stop policy
或 C02b group dispatch 的证据。C04 与 C02b 各自有独立 receipt。该段记录 C03a receipt 当时未覆盖 C03b；后续 C03b
有界验收见 [C03b Stop/Outcome receipt](C03b_Stop_Outcome_Receipt_2026-10-21.md)。

#### C03a fault-receipt correction（2026-10-21）

在 `codex/phase-ii-c` 上对 C03a receipt 做受限修正，没有进入 C04，也未改变 Runtime、Controller、Provider、
Recorder 的所有权。receipt 分开报告 public clock 推断的 `physical_progress`、native observer 的
`observer_confirmed_substeps`、Recorder pending/transition 内确认的 `recorder_confirmed_substeps`，以及
`transition_status`。回调/Recorder 计数是独立执行证据，不充当物理完成数量；仅有回调或 `interval_completed`
而缺少可信前后时钟时标 `unknown`。时钟进度与成功回调的最低进度不符、完整返回却 clock 未完整、或 Recorder
计数与 observer 顺序证据冲突时也标 `unknown`。

定向故障注入新增：最后子步物理推进后抛错、中途推进后抛错、故障边界 public clock 不可读、回调与边界时钟冲突、
以及完整物理推进后最终 Recorder receipt 缺失。最后一种情况必须保留 `physical_progress=advanced` 与不相等的
observer/Recorder 计数，同时 `transition_status=incomplete`、不追加 transition、既有 `freeze()` 继续拒绝；Env
仍 faulted 并禁止续步。receipt 更新不清除 pending，也不提供物理恢复或 rollback 语义。

修正后定向组合 `test_phase_ii_c03a_fault_lifecycle.py`、`test_selected_consumers.py`、Pendulum B03a/B03b 为
**70 passed**（一个上游 Taichi locale deprecation warning）。其中真实 GeoPhys CPU Pendulum 覆盖 scalar
reset/step/horizon/terminal 与后处理故障；selected 最后子步、中途子步、不可读边界、clock/observer 冲突及
Recorder receipt 缺失用现有 FakeSession 与公开快照面注入。它不构成 selected Provider fault qualification。
日志保存在 ignored `workspace/maintenance/phase_ii_c03a_20261021/c03a_fault_receipt_correction.log`。

TaskEnv module Skill refresh receipt（2026-10-21）：module=`task_env`，mode=`refresh`；从 `9bec437` 的
`ExecutionFaultV1`、`SingleTaskLifecycleAdapter`、`SelectedReferenceEnv`、`ExecutionRecorder`、当前 C03a/C05a
测试和 public API contract 对照原有 fault 路由，确认差异是 callback 被误作物理步数、receipt 未区分 Recorder
确认量和 transition 完整性。修复归类为 `FIX_EXISTING`：沿用现有 lifecycle receipt 与 Recorder pending/append owner，
没有新 Runtime/Recorder/recovery API。冷启动按 AGENTS + TaskEnv Skill 路由到现有 `execution_fault` 和 selected
recording owner，并能找到“clock 决定进度、两种计数仅作证据、pending 阻止 freeze、close/recreate”的处理；
`check_module_skill.py .agents/skills/geochora-task-env` 静态检查通过。该 Skill 描述更新不升级 provider 能力或 qualification。

#### C03a Recorder completeness fence follow-up (2026-10-21)

复核发现，原 selected native 录制检查只校验 observer 回调序列；若 `ExecutionRecorder.applied_substep()` 静默漏记一行，
物理区间和 observer 都完整时，旧路径仍可能把含不完整 pending interval 的 transition 追加到 Recorder。现有
`SelectedReferenceEnv._record_interval()` 在 append 前再核对 Recorder pending 的起始 control step、physics dt、预期
substep 数、计数器与实际 rows 的一致性、完整有序的 index/native-step index，以及每行的 state/feedback/target/applied
字段。Recorder 计数器与实际 rows 冲突时，receipt 的 `recorder_confirmed_substeps` 为 `None`；缺行或字段不全时在
append 前拒绝 transition。此修正只使用现有 selected Env 与 ExecutionRecorder owners，不清除 pending、不新增 recovery
或 discard API，也不改变 C04、Controller、Runtime、Provider 或 Recorder 所有权。

新增负例覆盖“物理区间完整但 Recorder 静默漏掉最终子步”和“Recorder 计数器与实际 rows 冲突”。两者均证明公开 clock
可确认 `physical_progress=advanced`，而 transition 不追加、`transition_status=rejected`、pending 保留且 Env 继续 faulted；
冲突计数不会被当成 Recorder 确认数量。C03a contract 另新增 public clock 小于 observer 已确认最小进度时标 `unknown` 的
冲突用例。末子步推进后抛错、中途推进后抛错、边界不可读和已有回调/时钟冲突用例继续通过。

定向命令 `PYTHONPATH=GeoPhys/src:. /home/lly/miniconda3/envs/geochora/bin/python -m pytest -q`
覆盖 `test_phase_ii_c03a_fault_lifecycle.py`、`test_selected_consumers.py`、C05a structured Recorder、B03a/B03b；
结果 **80 passed**，仅一个上游 Taichi `locale.getdefaultlocale` deprecation warning。真实 GeoPhys CPU Pendulum scalar
reset/step/horizon/terminal 测试在集合内；selected fault injection 使用既有 FakeSession 与公开快照面，不构成 Provider
fault qualification。完整输出保存在 ignored `workspace/maintenance/phase_ii_c03a_20261021/c03a_fault_receipt_final_20261021.log`；
`check_module_skill.py .agents/skills/geochora-task-env` 结果为 PASS，`git diff --check` 通过。

TaskEnv Skill refresh receipt（2026-10-21 follow-up）：module=`task_env`，mode=`refresh`；在 clean 基线
`a447e49` 上检查 `SelectedReferenceEnv` 的 native interval/append caller、`ExecutionRecorder` pending 行、相关 public
failure receipt、C03a/C05a/B03a/B03b tests 与现有 Skill。漂移为 selected append gate 未核对实际 Recorder rows，且计数器不一致
仍会被当成子步数；修复沿用现有 owners，分类为 `FIX_EXISTING`。Skill 已补充 pending payload/计数器一致性、clock 物理进度与
transition 有效性分离；冷启动沿现有 `make_env` → `reset` → selected `start_recording`/`step_expert` 和 `execution_fault`
路径可定位，无新 API/示例需迁移。`check_module_skill.py` 对 frontmatter、markdown links 和 source paths 静态检查通过；
冷启动不是 Provider qualification。没有运行真实 Panda Provider fault campaign；无 public API、Provider capability 或 qualification 声明变更，maintainer review
按常规提交审阅处理。

#### C03a append commit boundary follow-up（2026-10-21）

本次限定修正继续复用 `SelectedReferenceEnv` 与现有 `ExecutionRecorder`。复核发现，Recorder 原先先写 transition 并清空
pending，再构造下一条 boundary；若 boundary owner/序列化失败，receipt 会拒绝 transition，但 Recorder 内存里仍留有孤立
transition row。现在 append 先准备 transition、pending interval 的 owned copy、structured control、post-boundary 和
content blobs；这些准备全部成功后才提交 transition/boundary 并清空 pending。任何准备失败都保持 transition/boundary 对齐、
保留 pending，并令 fault receipt 的 `transition_status=rejected`。没有新增 Runtime、Recorder、恢复/discard API，也不清除
pending，不代表物理状态可回滚。

新增 selected integration 负例使用 FakeSession 与可读 public clock 完成全部物理区间及两类子步 receipt，然后注入 post-boundary
序列化失败。验收要求且实测为 `physical_progress=advanced`、observer/Recorder 数量独立完整、transition row 数仍为零、pending
保留、`transition_status=rejected`、faulted 后禁止续步且 freeze 拒绝。复跑末子步推进后抛错、中途推进后抛错、故障边界不可读、
observer/Recorder 证据冲突及完整物理推进但 Recorder 缺行/计数冲突用例。

定向命令覆盖 `test_phase_ii_c03a_fault_lifecycle.py`、`test_selected_consumers.py`、C05a structured Recorder、Pendulum B03a/B03b，
结果 **81 passed**，仅一项上游 Taichi locale deprecation warning。真实 GeoPhys CPU Pendulum scalar reset/step/horizon/terminal
回归在集合内；selected failure injection 走 FakeSession/public snapshot seam，不构成 Panda Provider fault qualification。完整输出位于
ignored `workspace/maintenance/phase_ii_c03a_20261021/c03a_atomic_append_followup.log`。TaskEnv module Skill refresh 按当前
`ExecutionRecorder.append` owner 更新原 Skill；Skill checker 与 `git diff --check` 结果见本次提交验证，不涉及 C04。

#### C03a fault-evidence semantics re-audit（2026-10-21）

在 `codex/phase-ii-c`、基线 `9e4fc3e` 上复核故障 receipt 契约。`ExecutionFaultV1`、selected interval observer、现有
`ExecutionRecorder` pending/append gate 及本节前述故障注入已实现所需分离，因此本次没有重复实现 lifecycle、Runtime 或
Recorder 行为。公开前后 simulation clock 与预期 control dt、interval/control-step 证据决定可观测 `physical_progress`；
observer 和 Recorder 只分别报告已确认的子步 receipt。时钟不可读，或时钟与已完成区间、控制边界、最小已确认推进证据矛盾时，
物理进度为 `unknown`。若可信 clock 已显示完整推进而 Recorder 缺失/冲突，仅保留可校验的 Recorder 数量（无法校验时为
unknown），现有 interval/append validation 仍将该 transition 留为不完整或拒绝；不得用完整物理推进推导录制完整，也不得
清除 pending 或解锁 faulted Env。

复跑最后子步推进后抛错、中途推进后抛错、故障边界不可读、clock/执行证据冲突、完整物理推进但 Recorder 缺项/计数冲突及
原子 append 失败用例；并覆盖 selected consumers、C05a structured Recorder、B03a/B03b 与真实 GeoPhys CPU Pendulum
scalar reset/step/horizon/terminal 回归。命令覆盖 `test_phase_ii_c03a_fault_lifecycle.py`、`test_selected_consumers.py`、
`test_phase_ii_c05a_structured_recording.py`、`test_phase_ii_b03a_predicates.py`、`test_phase_ii_b03b_temporal_commit.py`，
结果 **81 passed**，仅一项上游 Taichi `locale.getdefaultlocale` deprecation warning。selected fault injection 使用既有
FakeSession 和公开 snapshot seam，不构成 Provider fault qualification。完整输出保存在 ignored
`workspace/maintenance/phase_ii_c03a_20261021/c03a_fault_receipt_reaudit_20261021.log`。

TaskEnv Skill 同步澄清：Recorder evidence 不完整不反向抹去可信 public clock 已确认的物理进度，但仍使 transition 无效；
物理边界证据不可读或互相矛盾时才将 `physical_progress` 标为 `unknown`。本次未进入 C04，也未修改/清除既有的 C02b
工作区内容；未使用 Provider 私有状态、物理回滚或新的恢复接口。

#### C04 bounded observation and info receipt (2026-10-21)

C04 扩展现有 `ObservationFieldSpec` / `ObservationSchema` / `StateObservationBuilder` 和 task-owned Pendulum、TwoWheel
builders，没有新增 observation pipeline。`metadata["observation_schema"]` 逐 leaf 发布 path、shape、dtype、unit、frame、
reset/step boundary time reference、requiredness 与 visibility；`state`、`privileged_state`、`private_state` 的语义分开，
并保留 `private_state.robot_base_pose_world` 原名、shape 和 world pose 内容。Task info 的声明复用 `environment.metadata`
owner，以 `info_schema` 标明 reset/step execution facts、required feedback、optional diagnostics、每字段 shape/dtype/
unit/frame/time/requiredness；同一 owner 的 `validate_task_info()` 对必需字段和 finite simulation clock 做 fail-closed 校验。

通用 `BaseTaskEnv` reset/step 的 `simulation_time_s` 来自返回 observation 所用的 RuntimeSnapshot。缺失或无效 clock 会让
结果格式化失败，继续由现有 lifecycle fault 闭锁。新增 `ObservationConfig.include_diagnostics` 默认 `True`，旧 clipping
诊断键默认保持；设为 `False` 只省略 action/ctrl clipping 标记，所有 task evaluation 和 requested/external action、
controller target、requested/applied control、universal action 与时钟保持可用。相机 metadata 只从现有
`SensorObservation.camera_metadata` 透出到可选 `info["camera_capture"]`，引用同一 elapsed step 和 simulation time；不实现
新 image/depth modality。RGB/depth observation 叶仍由现有 renderer/Camera owners 构建；depth 单位与 frame 标为 provider
passthrough，TaskEnv 不伪称重解释。

新增 `test_phase_ii_c04_observation_contract.py`。真实 Pendulum GeoPhys CPU route 覆盖
reset/step schema、`observation_space.contains`、有限且对齐的时钟、同 seed/action 下 diagnostics 开关前后的 observation、
reward/task metrics、控制反馈相等。Panda synthetic builder 覆盖现有 private-state 路径、space membership、required body/site
来源缺失失败及 schema 缺字段失败；controller-call/feedback probe 覆盖 diagnostics 开关不改变传给既有 Controller 的
RuntimeSnapshot 且不删除必需 target/applied 字段。Camera 检查沿 Env fallback 保存已有 `SensorObservation` metadata，
核对来源与同一 boundary reference。组合 `test_phase_ii_c04_observation_contract.py`、C03a lifecycle、B03a/B03b、C02a
Controller bindings、C05a recording 为 **57 passed**，有一个上游 Taichi `locale.getdefaultlocale` deprecation warning；日志见
ignored `workspace/maintenance/phase_ii_c04_20261021/c04_regression.log`。

证据边界：当前 generic Panda `BaseTaskEnv` 真实 runtime 构造在 Stage 1 `compile_task_scene` 处以
`NotImplementedError: no Stage 1 scene composition adapter` 失败，因此没有报告真实 Panda Controller/physics A/B 验收或
Panda GeoPhys/MuJoCo S2。Panda 的本轮证据限合成 RuntimeSnapshot builder、controller-call 与 info-packaging probes；实际
物理 A/B 由现有非 Panda Pendulum CPU 路径验证。Camera 只测 metadata carrier/reference，不构成 D04 动态图像、深度语义或
Provider pairing 验收。C04 不合并 selected-reference Env 类型，不改其独立兼容路线。

TaskEnv module Skill refresh receipt（2026-10-21）：module=`task_env`，mode=`refresh`；对照当前 BaseTaskEnv/
ObservationBuilder、Pendulum/TwoWheel builder、RuntimeSnapshot、Camera metadata carrier、C04 定向测试及 public API contract，
刷新了 schema/info/diagnostics/camera 使用说明。复用归类为 `EXTEND_EXISTING`：沿用 metadata、field spec、builder 与已有
`SensorObservation` owner；未新建 InfoSchema 类、Recorder、Controller 或 camera runtime。Skill 静态校验及示例/源码链接校验
记录在 `workspace/maintenance/phase_ii_c04_20261021/`。该 receipt 不升级 Panda、camera、Provider 或 qualification claims。

#### C04 acceptance re-audit for C02b gate (2026-10-21)

在当前 `codex/phase-ii-c` / C03a append-completeness 修正后重新核验 C04→C02b 两条 gate。补强的 Panda builder
测试现用一个 object body，保护 `privileged_state.cube_v1_body_pose` 的 `(1,7)` / `float32`、`m + unit_quaternion`、
`world` frame、同一 reset/step boundary、required/privileged visibility 及 group semantics；缺少 body pose 明确失败。
既有测试继续保护 public Pendulum field、`private_state.robot_base_pose_world` 的独立 legacy private 含义、缺 site/body
源失败、schema 键缺失失败，并新增 required step `applied_ctrl` 缺失失败。

真实 GeoPhys CPU Pendulum 用相同 seed/action 对比 diagnostics 开/关：reset/step observation、`observation_space.contains`、
时钟、reward/termination flags、task metrics/evaluation 以及 requested/target/requested/applied/universal feedback 一致；
关闭后只省略 clipping diagnostics。Camera 仍只验证 `SensorObservation.camera_metadata` 的来源与同 boundary 引用，不实现
图像/深度新模态。generic Panda 真实 TaskEnv 的 Stage 1 composition adapter 缺口保持原状；selected pending recording 的
close/recreate 限制仍由 C03a 记录。Skill checker 只验证 frontmatter、本地 Markdown links 和显式 source paths，不是行为或
Provider validator；本轮未扩展 checker、恢复框架或相关治理规则。

新增 C04 direct contract 集合为 **6 passed**。交叉 gate 执行 C04、C03a lifecycle/selected consumers、B03a/B03b、C02a、
C05a 与 D01b 定向测试，结果 **103 passed**，一个上游 Taichi `locale.getdefaultlocale` deprecation warning；完整日志见
ignored `workspace/maintenance/phase_ii_c04_20261021/c04_gate_after_c03a_20261021.log`。观测契约 gate 与 feedback-independence
gate 均通过；因此 C04 放行 C02b。该 S1/bounded 证据不声称真实 Panda TaskEnv、D04 camera 或新的 Provider qualification。

#### C02b admission gate receipt（2026-10-21）

C04 两条放行准则保持通过。本轮复核 A05 `ControlBindingPlanV1` 的真实 provider admission：所需
`StateRequirements` 包含必需 `actuator_force`，对应 consumer requirement ID `actuator_force_query`。当前 GeoPhys 与 MuJoCo
`provider_manifest()` 均只声明 `rigid_body`、`free_body`、`articulated_robot`、`joint_position_actuation`、
`joint_state_query`、`body_pose_query` 和 `frame_pose_query`；Core capability schema 也不含 `actuator_force_query`。
D02a 已明确 requirement ID 不是 Provider claim，admission 必须 fail-closed。GeoPhys 的 `read_actuator_force()` 源码注释
限定为诊断/测试；`geophys.api_registry.query_public_api()` 对该 bare symbol 和 fully-qualified implementation symbol
均返回 `unknown-symbol`。这证明了裸底层 symbol 没有独立公开路由；当时据此写出的“没有可接入的 GeoPhys public API route”超出了查询范围。
本 receipt 的 admission 结论仍成立，API route 结论由下方 2026-10-21 勘误和真实 Probe 记录更正。

沿现有 `task_env.runtime.sessions.control.materialize_control()` 增加可选 plan-bound admission：先核对 RuntimeSource 与
Scene identity，再将每项必需 feedback capability 与实际 Provider manifest 及可选限制 manifest 求交，缺项在调用现有
`materialize()` 前抛 `CapabilityAdmissionError`。旧调用者不传 plan 时保持原有兼容路线。新测试对 GeoPhys/MuJoCo 两份实际
manifest 验证 `actuator_force_query` 缺失时 Runtime materialization 调用数为零；另验证不传 plan 的旧调用仍通过既有
admission 并绑定原 `ControlBinding`。C02a 已有测试继续保护完整 Group request 预检失败时无 Controller/Runtime 局部施控。

本轮执行 `test_phase_ii_c04_observation_contract.py`、C02a binding、C02b admission 与 D02a state contract，**26 passed**；
随后追加 legacy-call compatibility case 后，C02a/C02b 专项为 **14 passed**。两次均只有 Taichi 上游
`locale.getdefaultlocale` deprecation warning。日志分别保存在 ignored
`workspace/maintenance/phase_ii_c02b_20261021/c04_c02a_admission_gate_20261021.log` 和
`workspace/maintenance/phase_ii_c02b_20261021/c02b_admission_compat_20261021.log`。

**当前状态：BLOCKED（序号 24／C02b）。** 这不是实现或测试失败，而是计划绑定的 Runtime admission 所需
`actuator_force_query` 没有当前可用的公开 Provider 能力：GeoPhys 与 MuJoCo manifest 均未声明该能力，GeoPhys
`read_actuator_force()` 仅限诊断/测试且 API registry 不公开该符号。现有 fail-closed 测试证明 Runtime 在施控前拒绝构造；
不能用 fake manifest、Provider-private 状态、静默填零或删除 required feedback 绕过边界。

**阻塞影响与解除条件：** C02b 的 Group dispatch、applied acknowledgement、分组执行区间、C05a 真实录制读取及真实 arm+hand
S2 均未开始/验收，因此序号 24 不得标为完成，也不能宣称双 Robot 支持。继续前需由维护者与 Provider/API owner 确认并提供
可验证的解法：公开并定义 actuator-force feedback（语义、单位、采样边界及 GeoPhys/MuJoCo manifest admission），或基于
公开且充分的执行证据正式调整 A05/C02b 的 required-feedback 契约。完成该决策和能力证据后，才可继续 dispatch、真实执行和录制验收。
本 receipt 仅证明 admission 失败边界，不代表物理能力已支持；在阻塞解除前不进入依赖 C02b 的后续目标。

#### C02b feedback source & sampling audit（2026-10-21）

**勘误：**上一段 public API 结论只查了裸/底层 `read_actuator_force` symbol；没有可据此推出“GeoPhys 完全没有公开 force-read route”。同一 GeoPhys pin 的 official registry 将 `control.robot_arm.RobotArmObservationReader` 和 `control.robot_arm.RobotArmObservationConfig` 标为 exact、stable、documented。公开 Reader 的 `read_cpu_snapshot()` 支持 `actuator_force=True`，适用于低频评估/agent 外层读取；不应用于每个 physics substep。本勘误保留上一 receipt 的 registry 原始结果和 admission 判断，不把发现的 Reader 路线等同于 capability admission。

本轮在 PickCube 实际 GeoPhys CPU source 上经 Provider bootstrap/boundary adapter 使用公开 Reader。初次 reset 首样为 `0 N`；一次 `100 Hz` 外层 interval 精确推进五个 `2 ms` native steps 后，actuator8 raw signed force 为 `−30 N`；之后 reset 到 seed 73 与重复 reset 到 seed 31，两个新 boundary 的时间均为 `0 s`、reset 无新增物理步，但 Reader 都仍返回 `−30 N`。连续 Reader readback 未改变 Provider-measured state/time 或 ctrl；两次完整运行的稳态 CPU readback median 分别约 `99.6 μs` 与 `267.1 μs`，不设性能阈值。Probe 无 R1 `.compute()`；若经现有 `feedback_value()` 投影，旧值会成为 `+30 N` closing magnitude，超过当前 R1 3 N force-mode 激活阈值，此为源码推断而非行为已触发。

**结论仍为 BLOCKED，且阻塞原因进一步精确为 PROVIDER CONTRACT GAP。** 公开 Reader 提供可组合的外层 raw snapshot，但不携带 validity/freshness、reset identity、native sample index/time 或 phase；GeoPhys restore/reset 后未刷新 actuator force，首样可以是上一 episode 的旧值。Reader route 本身不需要 Core 私有穿透；但 Provider 必须先由现有 rigid state/reset lifecycle 与 observation owner 定义 reset force refresh（不加物理步）或显式 invalid、样本 identity/clock/phase/freshness。若继续保留 raw `actuator_force` typed requirement，Core 还须版本化现有 `snapshot_v1` typed-state owner 发布真实 raw N 值，不能只增 manifest capability。required feedback 保持不变。

前置有效性失败后，R1 compute、打开/闭合/受阻闭合/force hold/重开、MuJoCo native comparison、完整双 Provider 反馈、真实 `panda-main/production-r1` dispatch、ack、录制读取均 blocked/not run。C02b structured dispatch 与真实 arm+hand S2 仍未验收，不将此 Probe 记作完成。

完整 source/config/identities、数据表、采样语义、CPU 计时、Provider owner 合同和下一步进入准则见 [C02b Feedback Source & Sampling Audit](C02b_Feedback_Source_and_Sampling_Audit.md)。诊断脚本与原始输出保存在 ignored `workspace/maintenance/c02b_feedback_source_sampling_audit_20261021_001/`。

#### C02b-E Position Profile 第一轮验收（2026-10-21）

维护者后续授权 Position Profile 第一轮实现与 S2/H5 继续工作。S1 后的窄修正将 RuntimeSource/ResetSample/Provider target 统一到 `panda-main/joint*`，并在复用的 legacy DLS 输出边界显式适配；旧 `production-r1` 不变。双 Provider 各自 64 transitions、65 H5 observations、FK/Jacobian、motion、read-only sampling、clock、fault latch 和磁盘 leaf 回读通过。专项测试 **88 passed**；之后对最后新增的 live fixed-seed guard 单独复核，完整受影响专项结果见 S2 acceptance 与本轮执行记录。Generic recorder append capacity failure atomicity 与 selected consumer 兼容通过。

**当前仍为 BLOCKED**：单 Panda Position S2/H5 不提供 required raw actuator force，也不关闭 GeoPhys reset-force freshness，因此 C02b/R1 保持 BLOCKED。未实施 C02c、Assembly 或 GeoPhys force refresh；NutAssembly 500 Hz Guard 与 Phase II 未被此 bounded result 覆盖。

## C.9 质量门与直接可测问题

| 检测 | 预期行为 | 证据等级 |
| --- | --- | --- |
| Scalar reset/step/terminal | 正确 Gymnasium flags/time/horizon | S1 |
| controller schema/switch | 非法 binding/资源争用拒绝；合法 switch 到点生效 | S1；真实控制效果需 S2 |
| requested/canonical/target/applied | 四层独立、有原始命令来源 | S1/S2 |
| NutAssembly guard/native servo | 真实 native interval evidence；不可用时拒绝 | S2/S3 |
| Success 后继续、外部 Stop | 不自动把 task success 变成 solution completion | S1/S3 |
| Recorder event integrity | T/T+1 与 Stop/Switch/Capture provenance | S1 + 适用 S3 |
| Slow Solution | 不调用 env 时 sim time 不推进 | S1；walltime 记录可为 synthetic |
| Legacy support | 现有 selected UIDs、generic Pendulum 行为 | 相关 S2/S3 |

**严禁**：因为 C05 只完成 API 整合，就声明所有现有任务已支持外部动作或通用 RL/VLA policy。支持能力必须精确指向 Task×Provider×Controller×State/Render 的已测试交集。

## C.10 参考项目与借鉴界限

| 项目 | 参考重点 | 不照搬 |
| --- | --- | --- |
| [Gymnasium](https://github.com/Farama-Foundation/Gymnasium) | `reset/step`、terminated/truncated、Space、Wrapper 语义 | 不把 Solution Completion 直接当成 Environment success |
| [Isaac Lab](https://github.com/isaac-sim/IsaacLab) | Task/Controller/Action 配置与分层 Execution/Backend 选择 | 大型 manager stack、Batch API 迁入 Phase II |
| [ManiSkill](https://github.com/mani-skill/ManiSkill) | 单任务 Observation/Reward/Robot Action/Controller 配置与强校验 | SAPIEN 原生 wrapper/Pointer 作为 GeoChora Core |
| [robosuite](https://github.com/ARISE-Initiative/robosuite) | 机械臂 Controller 与 Task/Environment 单独组合 | 专用 MuJoCo 8D Action 假设 |
| [Genesis](https://github.com/Genesis-Embodied-AI/genesis-world) | 交互式场景的控制模式便利接口 | Solver-native Controller state 泄漏到任务层 |

## C.11 Codex 审阅重点与出口

1. `SelectedReferenceEnv` 不继承 `BaseTaskEnv` 的具体障碍是什么？共用 adapter 与 facade 哪种改变最小？
2. 仅有 `env.stop()` 是否满足终止事件所有权？重复 stop/recording 的异常结果如何定义？
3. 多 Robot Group Controller 的 YAML 默认应该由 Scene Instance 的 Config 还是 Task-level default 指定；覆盖规则是否明确、是否可重放？
4. `private_state`/`privileged_state` 在现有 schema 的准确差异是什么，如何在不改旧 H5 的情况下迁移？
5. 外部 Solution 的 Guard 所需真正反馈如何提供，而不要求普通用户开启昂贵的 diagnostics？
6. 旧 H5 v2 Reader/Writer 如何记录 Stop/ControllerSwitch；需不需要新事件 schema？不能用随意 `info` 字段假装兼容。
7. 控制边界是否可能因 Error 产生已施控但未成功返回的区间？如何防止下一 Action 在未知状态继续执行？

**C 阶段出口**：冻结/可复现 Task 可在单 Environment 中通过规范化 Action 执行，用户可按 Control Group 配置 Controller 并进行受限安全切换；外部 Solution 与 Environment 分离，现有 Selected Reference 能力不回归。E 的统一 Runner、自动编排和 Phase III 批量环境不属于本阶段结束条件。
