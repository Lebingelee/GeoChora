# R05 — GeoPhys Formal Native-rate Feedback Contract

状态（2026-10-29）：R05a `READY_FOR_CONTRACT_FORMALIZATION`，准备 attempt001；旧 `BLOCKED_PROVIDER_CONTRACT` 为历史 Sol preflight，未做 R05 新 cadence 实验。R05a 尚未接收，R05b/c 仍 PLANNED / NOT_STARTED。旧 C05c 四格实际通过；本 Goal 补齐正式合同及正常准入，不重复证明已有频率功能。

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

R05b/c实施预算由本包提出后Sol随实施合同冻结。无实时要求、无device-resident要求；历史Reader约0.3ms不是未来强制阈值。保持原CPU/CUDA×100/500Hz四格required，范围内改动补最小delta证据；只有输入/算法改变推翻原任务证据时才重跑受影响完整cell。
