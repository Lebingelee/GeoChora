# Phase C — Execution API & Runtime Lifecycle：架构、代码实施与验收（Codex 草案）

> **PROPOSED / 需 Codex Audit 与维护者确认；不是目前的统一 API 实现。**  
> 基准：2026-10-19，`main` HEAD `f292df149f41520b484ff27cf2ff78a584903013`，发布 v1.1.0。  
> 总体与依赖：[`00_Phase_II_AD_Implementation_Blueprint.md`](00_Phase_II_AD_Implementation_Blueprint.md)；输入：[`01_Phase_A_Core_Object_Model.md`](01_Phase_A_Core_Object_Model.md)、[`02_Phase_B_Task_Semantics.md`](02_Phase_B_Task_Semantics.md)。

## C.0 设计目标 / Phase II 有效范围

**目标**：将 B 的 Task Artifact、A 的 Scene/Robot/Control Groups、D 的 Provider Runtime 组合成**单个**规范化 Environment，向用户提供稳定的 `reset()/step()/close()` 和明确的终止、Observation、Controller、Recorder 行为；Solution 在 Environment **之外**产生 Action。

**不做**：统一通用 Batch/Vectorization（Phase III）；通用 Agent Runner/Task Harness（E 延后）；强制所有 Controller 通过同一个硬编码 Panda 8D Action；执行时 Provider 热切换；旧 Selected Expert 路线未验证前直接删除。

用户已认可的 C 边界：

1. `BaseTaskEnv` 最终统一 scalar 公共契约，但保持**薄 Environment Facade**；复用已有 `TaskLifecycleAdapter`/`SingleTaskLifecycleAdapter`，不创建第二套 Lifecycle Manager。
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
| [`task_env/registry.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/registry.py) | `make_env(uid, config, ...)`；selected 和 generic 两分支 | 一个配置解析/准入入口，不暗改旧 UID |
| [`task_env/environment/env.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/environment/env.py) | `BaseTaskEnv` 组合 Scene/Robot/Task/Runtime/Observations | 统一 facade；迁移多 Controller/B 语义，避免巨大 God Object |
| [`task_env/environment/lifecycle.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/environment/lifecycle.py) | `TaskLifecycleAdapter` 共用语义，`SingleTaskLifecycleAdapter` 有 reset/step；success/failure 可终止 | 策略化 termination、stop/metadata，不另建 manager |
| [`task_env/tasks/reference_env.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/tasks/reference_env.py) | `SelectedReferenceEnv` own `step_expert()`/`_step()`/recording | 外部 Solution 接管 expert lifecycle，公用 `env.step(action)`；回归验证后退休兼容方法 |
| [`task_env/environment/config.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/environment/config.py) | 当前 `RobotControllerConfig` 基本是单 Robot controller | 扩展为 Entity/ControlGroup→Controller Binding，含 YAML 默认 |
| [`task_env/runtime/sessions/api.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/runtime/sessions/api.py) | advanced `RuntimeSession(reset/snapshot/step/close)`、Provider admission | 构造规划/Session reuse；无 native ABI 强制统一 |
| [`task_env/environment/protocols.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/environment/protocols.py) | 通用 `RuntimeBoundary` 与 advanced Session 是不同的集成协议 | 适配而非强行把两套接口“合并为一个 solver” |
| [`task_env/controllers/`](https://github.com/Lebingelee/GeoChora/tree/main/task_env/controllers) | Panda pose/joint/gripper 控制、Canonical Feedback | Group Binding、控制状态所有权、切换 safepoint |
| [`task_env/observations/state.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/observations/state.py) | State/Privileged/Private/Vision field builders 和 schema | 保留现有 obs 分组，对不同 robot 扩展 typed schemas |
| [`task_env/recorders/`](https://github.com/Lebingelee/GeoChora/tree/main/task_env/recorders) | `TransitionRecordWrapper`、H5 v2、T/T+1 规则 | Stop/Controller switch/Solution metadata 使用版本化事件，不能伪造物理 step |

**关键回归风险**：当前 NutAssembly 禁止 external action，并依赖旧 `step_expert()` 获取真实 Native-rate Guard Evidence、Readiness、11-stage Solution 所需反馈；如果仅把 `solution.act()` 移到外部却删除底层必要测量，属于功能破坏。旧 selected route 的成功后继续执行、录制和 terminal 不同于 Generic Gym Success Stop，不能一律改成 `terminated=success`。

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
BaseTaskEnv / Single Environment Facade
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
  renderer: {default: rasterizer}
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
  "robot_right": {"arm": right_joint_targets}
}
```

动作维数/单位/参考 frame 由绑定的 Controller Action Contract 定义。单机械臂可有兼容向量入口；不能强制所有任务有 8D Panda Action。

**建议 runtime controller replacement**（暂不冻结函数签名）：

- **兼容切换**：同一 Control Group、同一外部 Action Schema/Unit/Reference/Timing/Actuator Ownership，在完整 Control Interval 边界提交；验证新 Controller required feedback，初始化新 Controller State，避免遗留 target/force。
- **非兼容切换**：例如 Cartesian Target ↔ Joint Position 更换 Action Schema，必须结束当前 Episode 或通过 Reset 边界重绑定，并向调用者明确提供更新后的 `action_space`/contract；**不**在已运行的 Episode 中悄悄改输入形状。
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

## C.6 Observation / Feedback / Wall Clock

- 标准：`reset(seed,options) → obs,info`；`step(action) → obs,reward,terminated,truncated,info`。
- **obs**：schema 统一的 `state`, `privileged_state`, optional `rgb`, `depth`, `segmentation`；保留现有 `private_state` 含义，不能未经迁移视为 privileged 的别名。
- **info**：基本 `task_metrics`, success/termination facts, elapsed clocks；高级 `execution_feedback` 与 diagnostics **可选**。Controller 内部必需反馈不得因用户关闭 Diagnostics 而消失。
- `Provider Native State` ≠ `Canonical State` ≠ `Public/Privileged Observation`；Task Success 可依赖真实 Canonical State 而不要求 Policy 也能看到该状态。
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

## C.8 五个 Implementation Goals

### C01 — Resolved Execution Config / Admission Plan

- **依赖**：A/B 的 identity 与 Task Requirements。
- **任务**：将用户 YAML defaults 和 `make_env` override 解析为同一个 immutable 结果；Provider、Controller、Renderer、Timebase 分层 admission；支持在 `reset()` 才需 dynamic Scene Variant materialize 的明确路径。
- **验收**：同源配置得到同一 resolved identity；legacy selected/generic configs 仍清晰 fail-closed；不支持的 controller/provider/renderer 前置拒绝；没有构造一半 Runtime 就泄漏资源；支持切换 Provider 实例而不修改 Frozen Artifact。
- **Codex AUDIT**：对比 registry 的 `from_reference_config` 分流与 `resolve_env_config`，提出不复制 factory 的迁移方案。

### C02 — Multi-Entity Controller Binding / Safe Switch

- **依赖**：A03、C01。
- **任务**：建立 Entity×ControlGroup→ControllerBinding，声明 typed Action Schema/feedback needs，controller memory owner；设计运行时 safepoint switch 并显式记录事件。
- **验收**：arm+hand/双臂可静态配置，资源重叠且无 arbitration 拒绝；同 schema 安全切换、不同 schema Reset-boundary 切换/拒绝；旧 Panda pose/joint/gripper 输出不改变；失败原子性。物理多机器人未验证不得称已支持。
- **Codex AUDIT**：精确追踪已有 `RobotControllerHandle`, `ProductionCanonicalPandaController` 以及 `ControlledRuntimeSession` 的 owner/feedback 状态，不复制控制代码。

### C03 — Unified Scalar BaseTaskEnv & Termination Policy

- **依赖**：B05、C01–C02。
- **任务**：复用现有 Lifecycle Adapter，统一两 scalar routes 的公共行为与 env metadata；可选 success evaluator、`stop_on_success`、failure、horizon、external_stop；明确异常/终态处理。
- **验收**：Gymnasium 5-tuple、reset-before-step、post-terminal guard、success-post-success、no-success、stop-early/horizon 的 flags 和 clock；Stop 不产生物理 step/伪 transition；旧 UID 按兼容路由保持行为至 C05 迁移。
- **Codex AUDIT**：指出 `SingleTaskLifecycleAdapter.resolve_scalar_done` 与 Selected `_step` 的主要差异；不能用一次强制成功终止破坏 NutAssembly。

### C04 — Unified Observation & Optional Diagnostics

- **依赖**：C03；D2/D3 更丰富状态尚可按版本后补。
- **任务**：统一 public+privileged obs schema 与 `info`；标准执行事实、必要 feedback、用户可选 Diagnostics 分开；Renderer Camera metadata 的位置/引用契约明确。
- **验收**：`observation_space.contains(obs)`、字段必需缺失失败、Reset/Step 同 Schema、frame/time 符合 S1；打开/关闭 diagnostics 不改变 Controller 物理结果；已有 `private_state` 行为保护。
- **Codex AUDIT**：现有 `StateObservationBuilder` 是否足以扩展，不要造第二个大型 Obs Pipeline。

### C05 — External Solution & Recorder Migration Gate

- **依赖**：C03–C04。
- **任务**：将 PickCube/NutAssembly expert loop 调用迁移到 Env 外部；统一 Action Transition；保护 Guard/Native Samples；Recorder 关联 Solution Identity、Controller Events、Stop Outcome；完整识别旧方法的生产调用方与退役次序。
- **验收**：同 frozen sample/config 在 GeoPhys/MuJoCo 已实现的受限 selected route 上，success/current-success/expert outcome/Guard/clock/recording 与旧基线有据可查；记录 T/T+1、Stop Events；不宣称完整 checkpoint replay；S2/S3 未跑标记缺口；兼容方法在所有 caller 迁移前不能删除。
- **Codex AUDIT**：提供旧 `step_expert → solution.act → _step → controller → feedback → solution.observe → recorder` 的完整调用图，逐步证明等价。

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
