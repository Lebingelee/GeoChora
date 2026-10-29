# R05 — GeoPhys Formal Native-rate Feedback Contract

状态（2026-10-29）：R05a attempt001 已获 Sol 接收 `ACCEPTED_BOUNDED_R05A_CONTRACT_PLAN`，仅合同设计/实施决议、S1与旧probe复用出口；Provider新合同/正常route尚未落地。下一包R05b attempt001，R05c未启动；旧C05c四格继续保留诊断身份。

## 现有能力与 owner

Provider [RobotArmObservationReader](../../../../../GeoPhys/src/control/robot_arm_observation.py) 和公开 `control.robot_arm` export，Core [native feedback adapter](../../../../../task_env/runtime/sessions/geophys.py)、[boundary](../../../../../task_env/runtime/boundary.py)、[RuntimeSession API](../../../../../task_env/runtime/sessions/api.py)、[typed state](../../../../../task_env/artifacts/state.py) 是唯一复用路径。EXTEND_EXISTING；Provider 拥有 native state/sample refresh，Core 绑定 episode/reset/evaluation，不建立 force state store 或另一个 Reader facade。

GeoPhys a53 已提供 typed force sample、phase/sequence/generation/state/config revisions、reset refresh 与 invalidate；Core 已有 Native Sequence/Guard/Recorder 消费。Reader 文档的 host snapshot 用途限制与 R05 正式目标存在待收口差异，但不是运行时频率上限。原 C05c CPU/CUDA × 100/500Hz 四组在维护者批准的诊断交集中完成真实任务及同文件 S3，原 H5 仍在且 hash 已核实。100Hz 组仅降低夹爪 law 更新频率，force/Guard 仍逐 2ms native step 采样；CUDA 为 GPU physics、host Controller。不得把这些事实说成频率失败，也不得直接升级为正式或 device-resident 支持。

## Provider 公共合同需明确的字段与行为

| 范围 | 需由 owner 决定/实现/验证的合同 |
| --- | --- |
| 值与映射 | raw signed actuator force、单位/dtype/shape、ordered actuator refs、source/transmission digest；不可把 tendon force/joint torque/contact wrench 混称相同 |
| 时间与相位 | native index/time、sample sequence、reset-forward 与 completed-step pre-integration 的真实定义；evaluation boundary time 与 sample time 分开，不伪作 post-integration 或平均值 |
| 有效性 | valid/stale、generation、state/config revisions；reset 第一份有效值、set-state/apply/config write、close/rebuild 的失效规则；未刷新时拒绝 required 消费 |
| 设备与同步 | CPU/CUDA × host/device 分列；谁触发 refresh、是否 GPU→CPU 同步、buffer lifetime/owned copy/alias、重复读取缓存与线程限制；读取不推进 physics |
| cadence 与成本 | 是否明确支持每 native step 500 Hz 的读取/控制合同；100Hz law+hold 与 500Hz law 的样本/应用频率分别计数；超时、读回成本与内存预算；无实时门槛不声称实时 |
| Core 消费 | sample→Scene/Entity/Actuator/materialization/episode/reset/evaluation identity；StateRequirements/admission 精确匹配 provider/build/backend/source/profile；未知交集 NOT_ADMITTED |

`closing_force_N=max(0,-signed_force)` 只在经审计 Panda tendon source 上由既有 control_feedback 转换；它丢失张开方向符号，不能替代 raw 样本。非有限、缺值、错单位/phase/旧revision/错Entity/sequence 倒退必须在 Controller 使用前拒绝。force-aware Hand 不能借 Position 不查询 force 的合同入场。

## Required Envelope 与失败决策

建议维持原草案的严格 P99 envelope：**GeoPhys CPU 与 CUDA physics，各自 host Controller，100/500 Hz law 对照 + native sample/Guard/hold-ramp + 同文件 H5**，使用精确 Panda source/reset；不要求 device-resident control。此为待维护者批准的规划目标，当前 a53 还没有该常规合同。Provider owner 必须先给出可支持 API、设备/时序与成本决定；若需新 pin/公共 API，另审变更并记录新 evidence，不修改旧收据身份。

R05a 若无法给出正式合同即 BLOCKED_PROVIDER_CONTRACT，禁止 R05b 通过诊断开关继续。某 backend 未测/失败就不能把双 backend required 写成 PASS；减少为 CPU-only 或接受继续延期都需要维护者先批准 scope change 与 P99/DAG 更新。保持诊断报告原结果，不生成虚构 owner approval。

R05 不作为 R01/R02/R03 Position-only 前置；R04 也不依赖 R05。仅整阶段 P99 汇总两项独立 required gate。

## 切片

| ID | 前置 | 工作与交付 | 必需 Evidence / Stop Condition |
| --- | --- | --- | --- |
| R05a | P00 | Provider owner 正式 API/phase/cadence/CPU-CUDA成本决议；最小可行性测量 | Audit/S1 + bounded cadence probe；无 owner 合同或只允许 diagnostic 即阻塞 b/c |
| R05b | R05a | 既有 Provider owner 的受限公开扩展、Core sample/admission/invalidations | S1/S2：reset/旧generation/错phase/NaN/config write/重复读取、零物理推进；不穿透私有数组 |
| R05c | R05b | CPU/CUDA 各 100/500Hz、same source/reset 的 Native Sequence/Guard/hold-ramp/H5 对照 | S2/S3：raw/closing force 分列、sample/ack/time/identity 和磁盘原值、费用/故障；任何 required cell 不通过阻塞 P99 |

预算必须在 R05a 冻结并保留实际成本；旧约 0.3ms host Reader 和低于实时速度只是历史测量，不是未来门槛或本轮复测。没有正式调用合同即使画面/Guard 运行正常也不构成 capability。

## 与检查点后 Provider 补丁的分界（2026-10-28）

[10 的 F03/F05](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md#5-分阶段顺序与出口)
计划先接已验证 USD、single-Panda/刚体 Position 与 GeoPhys public source/session。
这些基础 reset/step 检查可以独立推进，不要求本页 500Hz/双 backend 合同先通过；
它们的成功也不能关闭 `R05a=BLOCKED_PROVIDER_CONTRACT` 或替代 R05b/c 的正式 sample/freshness/cadence 证据。
Isaac R1 force-aware 若需要读取力，同样先核 source/transmission、单位/phase/freshness 和公开能力，不能借 Position 准入。

<a id="r05a-implementation-20261029"></a>

## R05a attempt001 实施定位（2026-10-29）

分类 `EXTEND_EXISTING`。Luna2 在现有 camera 阶段分支完成一次合同研究/布置窗口，预计60–90分钟、主动工作timebox120分钟；窗口内允许多轮定向S1修正，不把一次失败当作attempt耗尽。本包不启动R05b/c；owner决议候选交Sol审阅后才成为R05a接收依据，缺口不得靠删除diagnostic字样掩盖。

| 层级 / 现有 owner与方法 | R05a 必须交付的定位与决定 | 后继改动位置 |
| --- | --- | --- |
| GeoPhys `src/control/robot_arm_observation.py`：`RobotArmActuatorForceSampleV1`、`read_cpu_snapshot`、`refresh_reset_force_sample`、`invalidate_actuator_force_sample`；公开 `control.robot_arm` exports | 逐字段/行为对应本页六类合同；CPU/CUDA、owned copy、同步、重复读取、线程/close边界分别核实。已实现/缺实现/只缺说明分列 | R05b优先扩现有Reader及 `docs/reference/control-observation.md`；不新建Reader facade/状态库 |
| GeoPhys `src/solvers/rigid/state/host_io.py` 的 force status、reset refresh、begin/complete与失效owner | 从调用链确认reset-forward与completed-step pre-integration的真实意义；state/config写入、失败/重建失效与sample时间不能靠字段名猜测 | 只有证明实际失效缺陷才修owner；Core不调用其私有方法/数组 |
| Core `runtime/boundary.py`、`runtime/sessions/geophys.py`、`artifacts/state.py` | public sample到typed measurement、episode/reset/evaluation identity、NaN/错phase/旧generation与required消费的真实路径、已有S1及缺口 | R05b有界修复既有adapter；不复制NativeFeedback/Recorder |
| Core `runtime/sessions/api.py::_diagnostic_manifest`、既有provider registry/manifest owner、`tasks/nut_assembly/task.py` | 列出CPU正常路线与CUDA process-local diagnostic白名单的精确差别，提出版本化正常admission及source/build/backend/profile拒绝门 | R05b在既有注册/构造入口扩展；不能全局放行CUDA、不能把所有force-aware leaf一并准入 |
| `controllers/canonical/gripper_execution.py::EqualRateGripperServo`、`tasks/nut_assembly/solution.py::NativeRateGripperServo`与既有Native Sequence/Guard | 固定500Hz physics/force/Guard、100Hz outer，law100Hz更新+4hold或law500Hz逐步更新；reset首样本、ack、hold/ramp及H5对应规则 | 复用生产算法，不为R05另建控制循环 |
| `diagnostics/tasks/c05c_geophys_gripper_cadence.py::run_group/validate_h5`、原四格result/probe/H5 | 建立原证据→新条款复用矩阵、可复用源码hash/identity和受影响差异；只为新增条款补defect-sensitive S1与后继最小native | 原四格task success保留在旧身份；R05c正常合同新证据单独记录，不拼接新旧run |

原证据根：ignored `workspace/maintenance/nutassembly_gripper_cadence_geophys_20261022/`。跨分支/对话纠偏收据：ignored `workspace/maintenance/r05_phase_ii_ii01_reconciliation_20261029_001/`。后者核实原H5 hash/root及源码未变，未重新运行历史完整S3；R05a必须继续区分已核实内容和原报告结论。

**R05a出口**：可审阅的正式host native-step合同候选（包括明确支持/拒绝交集、刷新/失效/同步/线程/close行为）、条款到公开方法/调用者/证据的矩阵、最小probe的逐项复用或确缺说明、CPU/CUDA成本预算、R05b精确补丁与测试清单及新pin必要性判定。已有证据足以覆盖未变化的最小probe时不重跑；本attempt不新增native，若出现不能靠源码/S1/原probe回答的决策关键未知项，具体指出再由Sol一次性定后继范围。

Provider正式说明如需改动，R05a交付对应owner可落地候选文本/patch与是否需新API的判定；R05b再落入Provider仓库并冻结实际commit/gitlink，不能用Core文档替Provider当前公共合同作已生效宣称。Sol是本包合同审阅/接收责任人，不让Luna因“尚无神秘外部owner签字”循环返回同一句BLOCKED；若确需维护者范围决定，须提供实际不支持的方法/行为和可选择的具体方案。

<a id="r05a-attempt001-contract-candidate-20261029"></a>

### R05a attempt001 合同候选（2026-10-29，待 Sol 复核）

状态为 `R05A_CONTRACT_AND_IMPLEMENTATION_PLAN_READY_PENDING_SOL_REVIEW`，不是 R05a 接收、正常 capability、正式 Qualification 或 R05b 授权。本 attempt 只跑 provider-free 的既有 cadence S1：`test_c05c_geophys_gripper_cadence.py` 4 passed；没有启动新 native，也没有取得共享 native 锁。合同矩阵、原证据复用、成本、Provider 文档候选和精确补丁计划在 ignored 输出 `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r05a_001/`。

现有实现已提供 owned `float32` actuator 数组副本、reset-forward 与 implicitfast pre-integration 样本、generation/sequence/revision/phase/validity、状态与 ctrl 写失效、以及 Core 的 source/episode/reset/evaluation/sample 顺序校验。Provider v1 没有 sample-time、source-id、actuator refs 或 per-index unit；`force_unit="N"` 只适用于已审计的 Panda 固定 tendon 标量绑定，不能描述任意数组。Core 以 `native_step_index` 和 `physics_dt` 派生 `native_sample_time_s`，并单独保留 evaluation boundary clock。

当前确定的 R05b 行为缺口：`GeoPhysRuntimeBoundary._apply_actuator_force_limit_overrides()` 在 Core 侧读写 Provider 私有 `act_forcerange_field` / `act_forcelimited_field`，且每次 `GeoPhysSession.apply_control()` 都重复上传同一限值并增加 configuration revision；Provider 没有公开的 force-limit setter。另一个接线缺口是普通 manifest 中没有单任务 force capability：GeoPhys CUDA 目前只有 process-local diagnostic manifest，CPU 诊断运行不等于正式 force admission。C05c 的 source closure digest 为空，现有 diagnostic manifest 只检查文本 source id；后继 admission 需绑定 source XML/closure bytes、顺序映射、Provider build、backend、profile、solver/integrator、TaskArtifact 与实际 Controller。

候选范围仅为 NutAssembly 单一 source 的 GeoPhys CPU 与 CUDA physics、host Controller、strict `p1_2_scalar_cpu_v0`、implicitfast、2 ms×5、100 Hz outer；force/Guard 仍为 500 Hz，夹爪 law 为 100 Hz（更新一次并 hold 四步）或 500 Hz（每 native step 更新）。这不是 device-resident 或 2 ms real-time 保证。Provider 已有“诊断/低频”文档与该窄路径 per-step 观测之间需要 Provider owner 文档收口；R05a 已提供精确候选。无需新增 Reader facade；R05b 需要在既有 Provider host-I/O owner 增加公开 force-limit setter，并用新 clean Provider commit/gitlink 绑定版本，不能机械替换 a53 常量。

旧 C05c 两步 probe 与四份 full-task/S3 H5 均已复核哈希、source、Artifact、seed19、integrator 与 cadence；不复制受保护 H5。CPU100 原 `result.json` 的 S2 完成且 strict Expert/Outcome 完成，但 S3 初始读回 assertion 使原顶层结果保持 failed、`s3=not_run`；同一 H5 的独立 follow-up 读回随后通过。其他三格原结果及 S3 均通过。它们仍是 a53 下的诊断证据，不能证明新正常 admission。

R05b 顺序建议：先完成 Provider public setter、Core idempotent configuration call 与 source/build-bound normal admission；在 native 前通过真实 public construction 接线的 worker/finalizer/independent-reader 成功和 tamper/identity 负例 S1；再运行每 backend 的最小 reset + 两 outer probe。R05c 四格保持分别必需，每格使用正式 route 与独立 H5；旧 full-task 证据只对未受影响的物理任务/控制律输出复用，任一 source、solver、integrator、force law、reset、Controller 或 task 输入改变时重跑受影响完整 cell。预算上限和条件见 ignored `cost_budget.md`，由 Sol 在后继工作包冻结。

本合同候选由 Sol 实际审阅后才可能接收。旧 R05a preflight 阻塞记录和 C05c 诊断记录继续保留；R05b/c、原 DAG、Required Envelope、P99 与 Qualification 状态不因本次文档更新而改变。

<a id="r05a-sol-acceptance-20261029"></a>

## R05a Sol接收与R05b实施合同（2026-10-29）

Sol复核Luna提交 `e8d233a7bfd31a38d30759fdea861518616c19b7`：18项输出manifest、20项保护hash、31项输入source核对、12份Markdown hash匹配；四probe各2/3、四full H5分别2443/2444、2442/2443、2443/2444、2442/2443及native index递增由独立h5py进程核实。复用原4项provider-free S1，Sol零新pytest/native，不把结构核验称为完整S3重跑。接收 `ACCEPTED_BOUNDED_R05A_CONTRACT_PLAN`，不是Provider API生效、R05b/c或Qualification接收。完整复核见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r05a_001/`。

### R05b attempt001：EXTEND_EXISTING

预计90–150分钟、主动窗口上限180分钟；同窗口可多轮修复/S1/native，不设置默认一次启动额度。Core复用camera分支；其中GeoPhys checkout从a53建立一个本地 `codex/phase-ii-01-r05-provider` 依赖topic，原因是public setter修复属于Provider且必须有可追溯commit/gitlink。不新增Core分支/worktree、不改主checkout或其GeoPhys副本；后续整合分别审阅Core/Provider提交，未经授权不push/merge。

| 改动点 | 实施与验收要求 |
| --- | --- |
| Provider public setter | `RigidSolverStateHostIOMixin`增加中性effort bounds的公开setter；整数ID、非bool、不截断float，有限且float32可表示的精确shape/range/重复ID检查。整批校验后再写，真实变更才增加configuration revision并失效；相同有效值幂等，零physics推进。失败不能留下错误valid状态。private fields仅留Provider内部。 |
| Core boundary | 调用public setter，消除私有字段访问；相同cap不重复上传，reset/restore必须使Core缓存与Provider实际配置一致；不改变控制律/限值/源物理参数。 |
| 正式public读取说明 | Provider说明定义独立native-step host primitive及同步/phase/单位/线程/lifetime限制，不依赖Core import或Task token；Core负责窄NutAssembly来源/build/backend/profile/Controller准入。不得把一般effort槽统一称N。 |
| 源内容与准入 | 复用现有source-closure-v1算法，精确绑定XML及Importer实际消费依赖的同一不可变文件快照；版本化receipt归source/provenance owner。旧v0 RuntimeSource在无Scene时禁止nonnull closure digest，不能直接赋值、伪造Scene或为此迁移旧v0。新正常profile绑定实际Provider clean commit/origin、Artifact/source/mapping/timebase/integrator/backend/law/Controller；generic manifest不扩，旧a53 diagnostic白名单不改成新pin。 |
| 接线与测试 | S1覆盖真实构造/reset/step/sample/Guard/Ack/Recorder/reader/close链；native仅以IO doubles替换。setter批次拒绝/幂等/reset缓存、同boundary重复读、跨boundary旧值/错phase/generation/revision/NaN/错源、finalizer和独立reader成功/篡改/收尾门在native前通过。旧a53 diagnostic S1可mock历史build，但另测新build被旧diagnostic拒绝。 |
| 最小S2 | CPU和CUDA分别一个fresh run，500Hz law、seed19、implicitfast、2ms×5，目标各2 outer/10 native；验证首reset样本、连续样本、重复cap/读、零额外推进、source/build/clock与同run小H5/独立reader。不得以两个outer声称完成task/Guard dwell/Expert；R05c留待后续。 |

每S1进程180秒/2GiB RSS；每backend native run 15分钟/4GiB RSS、CUDA worker显存采样上限7GiB（启动前须留足桌面余量）、每run输出64MiB、最多32 outer/160 native/2 reset；整个attempt输出256MiB、主动180分钟。硬预算与采样最大值分列；GPU用可观测按PID/设备采样，不要求Taichi不存在的torch allocator计数。共享native锁覆盖实际worker整个生命周期；失败修复后使用新run目录并重新freeze实现commit/源码，失败原件保留，不拼接PASS。

R05c的完整cell/最小delta选择由Sol按R05b实际diff决定，旧任务证据可复用事实与新正式route实际未测事实分列；当前不授权把旧task成功与新短H5拼成新run task PASS。R05b只完成本行，不提前运行/关闭R05c、R06c/P99。
