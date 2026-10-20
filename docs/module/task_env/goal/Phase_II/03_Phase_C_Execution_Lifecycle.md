# Phase C — Execution API & Runtime Lifecycle：架构、实施切片与验收

> **PROPOSED / READY FOR SECOND REVIEW；本次仅修订规划，不启动统一 API 实施。**
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
  C02b 在 C03a/C04/C05a/D01b 后开放实际原子执行；C02c 在 selected C05b/C05c 回归后做同 schema 安全切换。
- **验收**：arm+hand 有真实受限 S2；双臂先静态，实际支持另需 D01b 双 Robot binding/S2。
  缺 Group/extra key/NaN 必须在任何 owner mutation 前拒绝；重叠 writer 拒绝；
  同 schema switch 的 initialization、effective boundary、applied acknowledgement、failure atomicity 可测。
  非兼容 schema 必须新 Env/wrapper。旧 Panda 输出保护，未测 multi-robot 不宣称执行支持。
- **Codex AUDIT**：精确追踪已有 `RobotControllerHandle`, `ProductionCanonicalPandaController` 以及 `ControlledRuntimeSession` 的 owner/feedback 状态，不复制控制代码。

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

- **切片**：C03a 在 C02a/D01b/C05a 后以现有 ports/adapter 接入 reset/step/fault，
  先保留单 controller 兼容执行；C03b 在 C03a/C04/C05a 后加入 termination policy 和 Stop。
- **任务**：先统一公共行为，允许两薄 facade 过渡，不强制 selected 继承旧 BaseTaskEnv；
  保留 generic ignore_done、selected success 后动作及默认 horizon 的既有语义。
- **验收**：Gymnasium 5-tuple、reset-before-step、post-terminal guard、success-post-success、no-success、stop-early/horizon 的 flags 和 clock；Stop 不产生物理 step/伪 transition；旧 UID 按兼容路由保持行为至 C05 迁移。
- **补充 Gate**：故障后禁止续步；partial interval 不保存为成功 transition；Stop outcome/loader bootstrap 一致；
  共享 TaskLifecycleAdapter 修改需 Pendulum scalar/batch targeted regression，不因 Phase III 延后而豁免。
- **Codex AUDIT**：指出 `SingleTaskLifecycleAdapter.resolve_scalar_done` 与 Selected `_step` 的主要差异；不能用一次强制成功终止破坏 NutAssembly。

### C04 — Unified Observation & Optional Diagnostics

- **依赖**：C03a、D02b；Camera 先消费 D05a 的 metadata/selection 契约，D04 后补真实模态实现。
- **任务**：统一 public+privileged obs schema 与 `info`；标准执行事实、必要 feedback、用户可选 Diagnostics 分开；Renderer Camera metadata 的位置/引用契约明确。
- **验收**：`observation_space.contains(obs)`、字段必需缺失失败、Reset/Step 同 Schema、frame/time 符合 S1；打开/关闭 diagnostics 不改变 Controller 物理结果；已有 `private_state` 行为保护。
- **Codex AUDIT**：现有 `StateObservationBuilder` 是否足以扩展，不要造第二个大型 Obs Pipeline。

### C05 — Storage Compatibility / External Solutions（a/b/c）

- **C05a**：依赖 C02a/C01b/D05a，在 C03a/C02b 前完成 structured request、target/applied、
  Boundary Event、EpisodeOutcome 的版本化存储/reader 及训练转换规则。扩展三类已有格式的实际 owner，
  不新建 Recorder。旧 vector H5 和旧 canonical/execution fixtures 只读保护。
- **C05b**：依赖 C02b/C03b/C04，先迁移 PickCube 的 external Solution，证明 action→step→record 路线。
- **C05c**：依赖 C05b/D02b，先审定 native feedback/hold/ramp 契约再迁移 NutAssembly；
  分别证明 measured 500 Hz、Guard、arm schedule、Outcome V1 与 strict warning/failure 保真。
  无法证明时保留旧 step_expert，不能仅删除 external_action_error。
- **验收**：同 frozen sample/config 在 GeoPhys/MuJoCo 已实现的受限 selected route 上，success/current-success/expert outcome/Guard/clock/recording 与旧基线有据可查；记录 T/T+1、Stop Events；不宣称完整 checkpoint replay；S2/S3 未跑标记缺口；兼容方法在所有 caller 迁移前不能删除。
- **完整 C05 Gate**：C05a/b/c 分别有 receipt，真实采集/读取及适用的 replay validity 独立报告；
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
