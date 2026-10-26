# R05 — GeoPhys Formal Native-rate Feedback Contract

状态：REVISED_DRAFT；R05a 为 BLOCKED_PROVIDER_CONTRACT（Sol preflight，无新cadence probe）；R05b/c 仍 PLANNED / NOT_STARTED。Provider 合同批准是本 Goal 独立前置；不把 C05c 诊断调用改名为支持。

## 现有能力与 owner

Provider [RobotArmObservationReader](../../../../../GeoPhys/src/control/robot_arm_observation.py) 和公开 `control.robot_arm` export，Core [native feedback adapter](../../../../../task_env/runtime/sessions/geophys.py)、[boundary](../../../../../task_env/runtime/boundary.py)、[RuntimeSession API](../../../../../task_env/runtime/sessions/api.py)、[typed state](../../../../../task_env/artifacts/state.py) 是唯一复用路径。EXTEND_EXISTING；Provider 拥有 native state/sample refresh，Core 绑定 episode/reset/evaluation，不建立 force state store 或另一个 Reader facade。

GeoPhys a53 已提供 reset-forward freshness/typed raw force 的精确 CPU 交集；现有 Reader 文档明确 host snapshot 用于低频采样，不应逐 simulation substep 使用。原 C05c CPU/CUDA × 100/500Hz full runs 为维护者批准的每 2ms host Reader **诊断例外**；历史 H5/phase/Guard 事实保留，但不证明常规 500 Hz 支持或 device-resident Controller。

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
