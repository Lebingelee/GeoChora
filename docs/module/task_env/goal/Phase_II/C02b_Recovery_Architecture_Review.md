# C02b Recovery Architecture Review — Profile 分流与规划恢复

日期：2026-10-21。源码审阅基线：Core `cddee96ad1f74462f10d0dae8e6f8f7d4474c4c7`，
GeoPhys `4436787e9cb85ce519506a2a9af86d1eeec9de2d`。结论：**REVISE_PLAN → 本轮文档已按审阅意见修订；实施等待二审**。
维护者已批准本轮保全审计、整理规划并提交/推送 develop；不因此授权实施 Profile、Group dispatch 或 Robot Assembly。

当前顺序与状态唯一入口是 [05](05_Architecture_Review_and_Execution_Order.md#3-切片依赖与推荐执行顺序)；
本报告记录恢复决策的源码依据、风险、消费链和后续验收设计，不建立第二套 capability matrix。
本报告形成时 C02b-P/E 尚未实施；后续状态见下方补记。C02b 仍 BLOCKED，没有因改文档获得任何新 Qualification。

### 后续实施状态补记（2026-10-21）

上方结论与 §2/§6/§8 的“未实施/未运行”均是本报告形成时的历史状态（Core `cddee96`），现由后续
[C02b-P Review](C02b_P_Position_Based_Profile_Review.md)、[C02b-E S1 Acceptance](C02b_E_Position_Profile_S1_Acceptance.md)、
[Phase C](03_Phase_C_Execution_Lifecycle.md) 与 [执行顺序](05_Architecture_Review_and_Execution_Order.md) 更新。
维护者已另行授权 E 第一轮：Position Profile/source-state/force-free Core 接线与 S1 已完成；当时双 Provider native S2、
Generic H5 v3 真写读及 state-leaf 回读尚未完成。后续 C02b-E S2/H5 已对单 Panda Position candidate 完成 bounded
GeoPhys/MuJoCo CPU 实跑和磁盘回读，见 [S2/H5 Acceptance](C02b_E_Position_Profile_S2_Acceptance.md)。这些结果不关闭
force-aware `production-r1`、reset force freshness、其他任务或完整 C02b。A05 Panda hand 下没有 `nutassembly_ee_site`；
candidate 使用版本化 hand-origin TCP，未修改冻结 A05 fixture。S2/H5 是 E 的分层退出层，不是启动 E 的前置。

## 1. 来源、基线与受保护内容

审阅材料为维护者提供的 `Codex_Recovery_Prompt.md` 和 `GeoChora_PhaseII_C02b_Recovery.zip`。
独立 Prompt 与包内副本字节一致；ZIP CRC 检查通过。材料身份：

| 输入 | SHA-256 |
| --- | --- |
| Codex_Recovery_Prompt.md | `ee71aeb7028152f175e5fb476b7fde552f71e33912f82161520c01a27d9634a1` |
| GeoChora_PhaseII_C02b_Recovery.zip | `f272f0bfab7b753c3fee757f07c76b1a6a1310d5d5eea1cb233f1bcd9b9565e1` |

独立审阅时本地与远端 develop 均为 `cddee96`，main 为 `f292df149f41520b484ff27cf2ff78a584903013`；
GeoPhys checkout 与 gitlink 一致且无改动，本地冻结 phase-ii-b 为 `006801074052c51db9845ccf64be1d21fc08609c`。
审阅时工作区有 Phase C/05 的两项修改及新增 [反馈来源审计](C02b_Feedback_Source_and_Sampling_Audit.md)。
维护者授权发布后，三份原文及 diff/摘要先保存在 ignored maintenance workspace，并原样独立提交，再进行本规划修订。

受保护范围：TaskArtifact v0 与 Scene v1/v2/v3 mapping/hash、A05 source fixtures、两 selected tasks 的旧 Controller/UID、
已发布 H5/raw evidence、既有 A–D receipts、冻结 refs、GeoPhys/Menagerie gitlinks。
本轮不改生产源码、测试、canonical capability matrix 或 Skill 行为；当前 API 仍以 canonical docs 和源码为准。

## 2. 恢复方向与实际实现的区别

**接受方向**：C02b 的第一条真实执行候选可以是独立身份的 position-based Profile，不要求所有 Controller
消费 R1 的 raw force。force-aware Profile 的 required feedback 仍合法，不能从旧 binding 删除。
已有位置算法可 COMPOSE_EXISTING；现有执行、Profile admission 和存储接线需窄幅 EXTEND_EXISTING。
没有理由新增 Runtime、TaskEnv、Provider、Controller Manager 或 Recorder。

| 对象 | 当前事实 | 新规划，尚未实现 |
| --- | --- | --- |
| C02a | ControlBindingPlanV1 与 prepare_structured_action 完整静态预检 | 新 writer 与实际 Controller identity/requirements 的执行绑定 |
| CanonicalPandaController | stateless DLS/位置 servo，不读 measured force；标为 frozen-v0 compatibility | 原算法可复用，需新 Profile identity、明确配置与生命周期适配，不能直接替换 R1 |
| R1 | ProductionCanonicalPandaController 消费 closing_force_N、拥有 gripper memory/readiness | 保留 required raw force 和独立 freshness gate |
| Runtime | 现有 Panda position actuation/限幅/ack；GeoPhys 普通 state snapshot 默认不读力 | 按实际 Profile 选择反馈依赖，拒绝错误/跨 Profile target |
| 存储 | generic H5 v3 支持 structured control/event/outcome；canonical BoundaryRecord 强制 force/readiness | 首条位置路线优先使用 state + generic H5 v3；不伪造旧力字段 |
| Assembly | Scene v3 RobotInstance 和 Group 仍为同 Entity | 跨 Entity logical/physical assembly 只记 DEFERRED 候选 |

仅修改文档不消除 generic Panda TaskEnv 的 Stage 1 composition 缺口。
实现时必须确定既有 facade/lifecycle/session 的准确集成位置，不可用 native diagnostic 绕过 admission 或新建平行 Env 来求通过。

## 3. 完整 Controller/Runtime/Recorder 消费链

已有无测量力算法：

```text
CanonicalStateView (arm/finger joint positions + EE world pose)
  → CanonicalPandaController.compute(state, requested)
  → _compute_arm: source-bound FK/Jacobian + DLS → arm joint/servo positions
  → finger positions + configured opening/stiffness/force cap → servo opening
  → CanonicalControlTarget → existing Provider apply_control → native steps
```

源码：[controller.compute](../../../../../task_env/controllers/canonical/controller.py#L58)、
[位置 gripper servo](../../../../../task_env/robots/gripper.py#L127)、
[control admission/target validation](../../../../../task_env/runtime/sessions/control.py#L352)。
`force_limit_N` 用于 servo correction 和物理 hard cap，属于 command/config，不是测量力查询。
新 Profile 的具体 cap、opening step、stiffness、frame/timebase 都要明确，不混用 R1/NutAssembly 参数。

当前不能直接复用的外围路径：

```text
SelectedReferenceEnv.reset
  → materialize_control → session.reset → snapshot
  → session.control_feedback → GeoPhys raw read / MuJoCo force cache
  → R1 reset(state, feedback) → Solution/readiness

SelectedReferenceEnv._step
  → R1 compute(state, feedback, request)
  → grouped apply+step 或 native step_control_interval（每子步也读取 feedback）
  → control_feedback → readiness → canonical/execution BoundaryRecord
```

源码：[selected reset](../../../../../task_env/tasks/reference_env.py#L172)、
[selected execution](../../../../../task_env/tasks/reference_env.py#L323)、
[GeoPhys feedback](../../../../../task_env/runtime/sessions/geophys.py#L85)、
[MuJoCo reset](../../../../../task_env/runtime/sessions/mujoco.py#L160)、
[MuJoCo step/cache](../../../../../task_env/runtime/sessions/mujoco.py#L255)、
[canonical boundary](../../../../../task_env/trajectory/canonical/contracts.py#L44)。

R1 和兼容 Controller 的 compute/reset/readiness 接口不同。MuJoCo reset/controlled step 还会复制 actuator_force；
即使不消费也不能声称整条路径没有 query。位置路线需在既有 owner 内明确处理这些读取，保留 legacy 默认行为。
Provider 内部按物理规律计算 force 不受此禁止；要禁止的是新 consumer 对无合同测量的依赖/读取。

**建议接线**：新 Profile required Joint/Frame publication → 既有 binding/preflight → 现有位置算法 → apply/ack/step
→ 同边界 state → generic H5 v3，使用现有 StructuredControlTransitionV1/Event/Outcome owners。
不调用旧 force feedback，不构造零力 readiness。若以后要让 canonical/execution boundary 支持位置 Profile，
先在原 owner 审阅版本化表达；不能原地放松旧 schema，也不能新增另一套 Recorder。
这是候选设计，尚无 force-sentinel 全链或 native S2 通过结论。

## 4. Robot Assembly 边界

官方资料支持借鉴 mount alignment、fixed joint、root handling、collision filtering 和保存装配配置；
物理 fixed joint 的行为依赖 solver，装配后仍需稳定性测试。
参考：[Assembler API](https://docs.isaacsim.omniverse.nvidia.com/latest/py/source/extensions/isaacsim.robot_setup.assembler/docs/index.html)、
[6.2 教程](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/robot_setup/assemble_robots.html)、
[Isaac Lab Action Terms](https://isaac-sim.github.io/IsaacLab/develop/source/api/lab/isaaclab.envs.mdp.html)。
不把不同版本 API 的参数混用，也不由其存在推导本仓库已支持某种装配。

采用 Logical Assembly 与 Physical Attachment 分离：前者是成员/路径/配置关系，后者是 mount SE(3)、物理约束、
root/collision intent 与 Provider mapping。首期物理关系无环、唯一父级；logical reuse 不得重复物理实例或 actuator writer。
父 preset/leaf overrides 展开成一个不可变 effective plan，父级状态从配置推导，不拥有第二份 state。
跨 Entity fixed joint 需要新版本与 A03/D01 扩展证据，不修改现行 v3。

本轮不实现 Assembly、递归 preset、whole-body IK、topology hot swap 或 attach/detach。
P00/P99 最小双 Entity 隔离施控仍保留；它不需要物理装配，也不能因 Assembly 延后而删除。

## 5. 六文档补丁的修订与 DAG

| 文件 | 本轮实际修订 |
| --- | --- |
| [00](00_Phase_II_AD_Implementation_Blueprint.md) | 当前 33 切片基线、Profile 分流、导航与 C02c/C05/D04 依赖同步 |
| [01](01_Phase_A_Core_Object_Model.md) | A.9 仅设计候选；logical/physical 分离、实例/资源唯一、旧 A 验收保护 |
| [03](03_Phase_C_Execution_Lifecycle.md) | P/E 完整 gate、无力反馈/录制路线、实际 Profile identity、切换与 C05a1/a2/a3 |
| [04](04_Phase_D_Physics_Rendering.md) | D.13 现有 materialization 保护、未来 attachment gate、D04 storage 前置同步 |
| [05](05_Architecture_Review_and_Execution_Order.md) | 35 节点当前表、旧/新编号、C05a evidence crosswalk、当前状态及 RA-01–06 |
| [06](06_P00_Baseline_Caller_Compatibility_and_Feasibility_Audit.md) | 历史 P00 不变，追加当前恢复决议及双 Entity/P99 保护 |

包内原脚本不能直接用于当前 dirty tree：03/05 已因新审计改变 blob。没有使用 --force、清理审计内容或覆盖原文件。
只复用经审阅的表格转换；合并当前内容，并补上原补丁遗漏的正文状态、证据映射和范围说明。
33 实施切片 + P00/P99 的 DAG 已离线验证为 35 唯一节点、20 父 Goal，无缺失/前向前置和依赖环。
C02b-P/E 是内部检查点，不计入 33；P00 的 C02c←C02b/C03b/C05a2 等直接依赖保留。

原 C05a 收据可继承有据的 values/H5/codec/reader 结果，但不自动覆盖新增细分 gate：non-arm 最低 loader、
outcome/end/bootstrap 的真实 consumer、Stop finalizer 合同与历史 detector 缺口见 05 §3.2。
对已覆盖项直接复用，未覆盖项仅做定向补证，不重做完成的 A–D 或让 SHA 反复校验代替施工。

## 6. 后续检查点、变更 owner 与验收计划（未执行）

**先完成二审，再允许 C02b-P**：明确新 writer/profile 版本、实际 Controller identity/配置、准确 source binding、
Joint/Frame requirements、可用 state/admission、无力 reset/step/record 全链和必需 storage consumer 证据。
建议位置 writer 命名为 `panda-main/position-servo-v1`（待实现审核，不是现有注册项）；保持 R1 原名/需求/hash。
确认后才进入 C02b-E，不把静态审核标为执行完成。

预期修改 owner（具体 diff 在实施前最后确认，不要求全部修改）：

- `controllers/canonical/`：组合现有算法和最小 Profile/lifecycle 适配，避免改 frozen-v0/R1 的 identity/行为。
- `runtime/sessions/control.py`：actual Controller/Profile 与 plan/target identity、Group dispatch/admission/ack。
- `runtime/sessions/geophys.py`、`mujoco.py`：按新 Profile 所需数据读取，legacy 缓存/反馈保持兼容。
- 既有 facade/lifecycle integration owner：复用 C03a fault/transition receipt、terminal guard 和资源关闭，不能新增 Env。
- `recorders/` 与现有 generic H5 v3：仅在确有接线缺口时扩展；不为位置路线强制修改 canonical BoundaryRecord。
- 对应测试、public API/recording 文档与 TaskEnv Skill 按真实 API 变更再同步。本轮没有改变这些 API。

S0/S1 候选保护性回归（本轮文档提交未运行，不作为新 PASS）：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=GeoPhys/src:. \
  /home/lly/miniconda3/envs/geochora/bin/python -m pytest -q -p no:cacheprovider \
  task_env/diagnostics/tasks/test_phase_ii_c02a_controller_bindings.py \
  task_env/diagnostics/tasks/test_phase_ii_c02b_admission.py \
  task_env/diagnostics/tasks/test_phase_ii_c05a_structured_recording.py \
  task_env/diagnostics/tasks/test_reference_construction.py \
  task_env/diagnostics/tasks/test_selected_consumers.py
```

其中既有 C02a 含受限 native legacy 检查，不能将整条命令称为全 provider-free。
新增 Profile 专项须证明：缺组/extra key/NaN/错误身份在 memory/施控/clock 改变前拒绝；
force query/copy sentinel 抛错仍可完成新路线 reset/compute/apply/step/record；R1 缺 force 仍拒绝；
partial execution 保持 C03a physical-progress/Recorder evidence 区分和 fault 闭锁，不生成成功 transition。

S2 入口由 C02b-P 确定 source/集成方式后在现有 diagnostics owner 增加，当前没有可声称已运行的命令。
每 Provider 独立进程，CPU、100 Hz/5×2 ms、小规模确定性 intervals；设置显式 wall/RSS 预算和日志输出，
不得以超时替代 PASS。使用同一 candidate/source 与对应 hash-bound ResetSample，验证 reset 后 joint/frame 有效，
arm/hand 实际运动、完整 compute/apply/ack/native interval、读 state 不推进物理、T/T+1 写读。
数值 Oracle 来自确定的输入、现有算法和事前声明的容差，不以两 Provider 逐值相等或实际抓取成功作替代。
新障碍物/配置改变须记录新 identity，不更改冻结 A05 fixture。

后续 S3 是准确声明入口的短 execution/record/read 路线；不能把 advanced native probe 冒称 public make_env 全链。
若 facade 集成仍缺失、force query 仍被间接调用、真实 required state 不可用或 Recorder 必需 gate 未闭合，保留 BLOCKED/partial。
首次单 Panda PASS 不授予多 Robot、R1、NutAssembly 500 Hz、task success、replay 或正式 Qualification。

## 7. 风险、回退与二审决策

| 优先级 | 风险 | 实施前必须明确的措施 |
| --- | --- | --- |
| P1 | 只换 compute，外围仍读旧 force | 明确 reset/step/Recorder consumer；新 Profile 全链 sentinel，legacy 行为保护 |
| P1 | identity 只在字符串/静态 plan 存在 | 实际 Controller/config/source 与 binding/target 校验，拒绝跨 Profile target |
| P1 | 用零力满足旧 canonical feedback/readiness | 首选 state + H5 v3；需要新 boundary 时另审版本，不原地放松旧格式 |
| P1 | C05a 拆分后虚记 DONE 或重复实现 | evidence crosswalk；未证实 consumer 定向补证，旧 receipts 不回写 |
| P1 | 位置 PASS 被当 R1/Guard 等价或删除双 Entity gate | 分 Profile/consumer 支持范围，P99 缺必需证据保持 partial |
| P2 | Assembly 扩展扩大当前依赖 | 保持 DEFERRED；新 Scene/attachment 版本另审，不改旧 A/D 验收 |

实施回退必须以版本化 Profile 选择为边界；不能失败后静默 fallback 到 R1 或以旧入口绕过新 admission。
当前文档修订可通过普通 revert 恢复，不重写历史提交或冻结 refs；本轮未改变运行时。

二审重点：认可 state + generic H5 v3 的首次位置路线；确认新 Profile 的 identity/生命周期适配范围；
确认 C05a 缺口的定向补证与 P99 双 Entity 义务保留。方向已获维护者同意，本报告不把该同意扩展成代码实施授权。

## 8. 本轮验证范围

本轮仅做附件/源码/调用者/文档审阅、规划整合和静态文档检查；没有运行新的 native Probe、R1 compute、
MuJoCo 对照、完整回归或 S4。旧审计的 14 passed、C05a 的旧 7/41 passed 等均绑定原记录，不是本次结果。
发布提交的 `git diff --check`、链接/锚点、DAG、历史收据与 source/tree 保护检查以及现有 docs validator
结果由本轮 maintenance 校验收据记录；validator 的既有 count ceiling 不作为新运行时缺陷或全部通过的依据。

本轮发布前的实际静态检查：

| 检查 | 结果与限制 |
| --- | --- |
| 8 份变更文档的本地链接/锚点 | 196 项通过，未发现缺失目标或 anchor |
| DAG/范围 | 35 节点、33 实施切片、20 父 Goal；关键直接依赖、唯一性及无环检查通过 |
| 历史记录 | 16 个 receipt/re-audit 区块原文保持，原 P00 全文前缀不变 |
| 本轮 scope | 相对 cddee96 仅 8 个 Markdown 路径；生产源码、测试、gitlinks、冻结本地 B 分支未改 |
| git diff --check | 通过 |
| 现有 docs validator | **未全通过**：docs68/task_env24 超出现有 count ceiling；相对 consolidation 历史基线报告 84 个既有非文档路径。18 个 immutable URLs 已检查，未报告新增链接、锚点、冻结数据或 tag 错误 |

本轮没有修改 inventory、validator 或 count policy 来制造全绿。84 个 scope flags 是校验器相对其历史基线
累计扫描已有 Phase II 实现的结果，不是本次修改了 84 个源码文件；本次 diff 的 documentation-only 范围另行验证。
可复核日志与结构化检查存于 ignored `workspace/maintenance/recovery_docs_20261021/` 的
`docs_validator.log`、`planning_checks.json`；raw evidence 不随规划提交或公开资格声明自动发布。
