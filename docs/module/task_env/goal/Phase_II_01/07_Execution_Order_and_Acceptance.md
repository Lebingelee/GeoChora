# Phase II-01 — Execution Order / P99 Required Envelope

状态：REVISED_DRAFT / AWAITING_MAINTAINER_GOAL_DAG_APPROVAL。以下是新的 6 父 Goal / 18 切片**建议表**，不继承 Phase II 的 PASS，也不因本次文档提交启动 P00。每一 slice 均 PLANNED / NOT_STARTED。

## 基线、P00 与证据记账

以 [00 基线](00_Phase_II_01_Blueprint.md) 的 develop/gitlinks 为规划输入；本轮远端 readback 已核对。未来 P00 才重新比较执行时 refs/source/build/env、批准输入/预算/owner、保全工作区与 Evidence，并锁定新的 run manifest。现有编译/import 事实为先前审阅探针，不计作 P00/R03a 通过。

R03a 直接依赖 **P00**，与 R01a 并列早期启动；不等待 R01 codec。R05a 同样是独立 Provider gate；R04/R05 对 R01/R02/R03 Position 执行**无前置边**。实际推进可并行，下面编号仅是一个合法拓扑序。

## 18 切片 DAG 与停止条件

| 序号 | Slice | 直接依赖 | 主交付 | 最低 Evidence | Stop Condition | 当前状态 |
| ---: | --- | --- | --- | --- | --- | --- |
| 01 | R03a | P00 | MuJoCo独立资产可行性；GeoPhys拒绝 | S1/S2 | 独立fixed dynamics未证明→阻塞b/c | PLANNED / NOT_STARTED |
| 02 | R01a | P00 | 两类成员与非自指身份/codec | S1 | 旧identity变动或引用契约不明→停止 | PLANNED / NOT_STARTED |
| 03 | R05a | P00 | Provider正式cadence/设备/成本合同 | Audit/S1/probe | 无owner合同→BLOCKED_PROVIDER_CONTRACT | PLANNED / NOT_STARTED |
| 04 | R04a | P00 | public Camera消费/reader/预算 | S1 | 身份/metadata reader/资源合同缺失→停止 | PLANNED / NOT_STARTED |
| 05 | R06a | P00 | 历史原件与决议ledger | Audit/S1 | 缺原件且无独立处置→compatibility gate blocked | PLANNED / NOT_STARTED |
| 06 | R01b | R01a | 递归owning/reference解析 | S1 | 环/重复/悬空/预算失败→停止 | PLANNED / NOT_STARTED |
| 07 | R02a | R01a | Arm-only/Hand-only版本化leaf合同 | S1 | required state/TCP/资源不明→停止 | PLANNED / NOT_STARTED |
| 08 | R01c | R01b | 静态source投影与leaf refs | S1 | 隐式物理构造/旧hash变动→停止 | PLANNED / NOT_STARTED |
| 09 | R02b | R02a,R01b | effective plan与leaf adapter/preflight | S1 | 重叠native writer/部分apply假回滚→停止 | PLANNED / NOT_STARTED |
| 10 | R02c | R02b,R01c | 真实独立leaf Position隔离与H5 | S2/S3 | 只测两个完整Panda或无真实hand驱动→失败 | PLANNED / NOT_STARTED |
| 11 | R03b | R03a,R01c | 固定树lowering/root/collision/mapping | S1/S2 | wrong mount/root/顺序/约束失败→停止 | PLANNED / NOT_STARTED |
| 12 | R03c | R03b,R02c | 装配态public Env控制/记录 | S2/S3 | 不同diagnostic路径拼接或不完整H5→失败 | PLANNED / NOT_STARTED |
| 13 | R04b | R04a | 同Env真实capture/observation | S2 | stale/ghost step/teardown失败→停止 | PLANNED / NOT_STARTED |
| 14 | R04c | R04b | 同H5图像/metadata/控制读回 | S3 | 错T/T+1或无semantic reader→失败 | PLANNED / NOT_STARTED |
| 15 | R05b | R05a | Provider public sample→Core admission | S1/S2 | 错phase/validity或private bypass→停止 | PLANNED / NOT_STARTED |
| 16 | R05c | R05b | CPU/CUDA×100/500Hz正式对照/H5 | S2/S3 | 任一required cell失败/未运行→P99 blocked | PLANNED / NOT_STARTED |
| 17 | R06b | R06a,R01c,R02c | 版本/顺序/coupling保护汇总 | S1/S2 | 旧支持退化/新token混淆→停止 | PLANNED / NOT_STARTED |
| 18 | R06c | R06b,R03c,R04c,R05c | 全部required交集/证据/决议包 | S1/S2/S3 | 缺required出口/历史处置→P99 blocked | PLANNED / NOT_STARTED |

P99 直接依赖 R06c，且复核所有 18 slices 的 required contract、运行与独立范围决定。R06a 记录缺口可以形成自己的 ledger，但不代表 compatibility decision gate 已接受；R06c/P99 不能把未决决定忽略。各 slice 自带受影响兼容检查，R06b/c 不取代局部回归。

## P99 Required Envelope（待批准）

| Gate | 必需交集/证据 | 当前已知与未获得资格 |
| --- | --- | --- |
| R01 logical composition | 两类typed member、稳定路径、无环/唯一owning、source/hash、旧Scene/Artifact不变 | 全部 PLANNED；不构成动力学 |
| R02 leaf control | Arm-only + Hand-only Position，preset/override→唯一资源writer；真实分开/同时施控、target/ack/state/H5 | 双完整 Panda 历史证据仅作对照；force-aware新leaf不在装配required范围 |
| R03 first Provider | **MuJoCo 3.8.1 CPU**、Menagerie独立Arm+Hand、新固定连接source；reset/连续运动/开合/接触或负载/constraint误差与资源关闭 | 仅先前compile成功；Native S2/S3 NOT_RUN，未获Assembly Qualification |
| R03 public S3 | 同一公开candidate make_env（或另经明确批准的公共入口）→reset→真实steps→observation→既有Recorder→同文件T/T+1读回→close | 扩展现有factory/RuntimeSession/Recorder；不导入test helpers、不拼接diagnostics |
| R03 second Provider disposition | GeoPhys a53同导出source拒绝、原因/策略/owner与未测项清楚列出；新S1 negative admission保护 | **NOT_ADMITTED/BLOCKED**，无新装配S2/S3/Qualification；第二Provider执行不为首版required，不自动DEFERRED |
| R04 Camera | GeoPhys a53 CPU × MuJoCo3.8.1 Native OpenGL/EGL、原单Panda source，双fixed/mounted RGB/Depth/Entity mask→同Env→同H5 semantic reader | 旧直接capture不代消费连通；需实际context/device、identity/calibration/label-map、T/T+1/故障/close |
| R05 formal feedback | GeoPhys CPU/CUDA physics × host Controller，各100/500Hz law对照、native sample/Guard/hold-ramp/H5；Provider正式公开cadence合同先批准 | 原C05c每子步host Reader仅诊断例外；a53未建立正常500Hz合同；device-resident/实时不要求 |
| R06 compatibility | canonical/native顺序与逆映射、Hand equality/tendon/真实驱动资源、旧版本/admission保护；缺失历史原件独立处置 | B04a/eb870限制保留；恢复/退休/继续延期须新阶段精确决定，缺决定则blocked |
| scope/Release separation | Source Manifest、真实receipts、独立maintainer phase decision、失败/NOT_RUN明细 | S0-S3不授予Qualification；main/tag/v2.0.1Release另行Gate |

R04/R05 的失败或 NOT_RUN：仅阻塞其依赖后继与整阶段 P99，不阻塞无边的 Position 子链；不得自动记为 DEFERRED、跳过required cell或将diagnostic改为PASS。维护者范围变更必须记录 affected gate/source/provider/backend、理由、证据、风险、替代required出口、DAG影响及新的明确批准；在批准前保留原BLOCKED/FAIL/NOT_RUN。

R03 第二Provider若加入required，也须上述scope变更；若GeoPhys修复要求新pin，必须另审其Source/Provider变更与受影响回归，原Evidence不改。R05 CPU-only替代双backend同理；本轮没有批准这些变更。

## 每次实施的通用 Gate

每 slice 开始前冻结 owner/caller、Artifact/Scene/Assembly/Profile/Source/Provider/build/backend identity、seed/reset/horizon、Oracle/tolerance（单位/物理依据/生命周期片段）、timeout/内存/磁盘预算、正/负例与失败/close行为。Source存在、import/compile、S1、真实S2、public集成S3分开记账；不根据phase名称猜通过。

只有受影响明确问题才拓宽实验，不重跑完整 A–D/NutAssembly矩阵/485 interval R1 作为日常文档校验。禁止更换Provider求绿、提升阈值、删断言/全局skip、隐式fallback、私有状态穿透、重复Runtime、ghost transition、假物理回滚。

维护者批准最终 Goal/DAG 后才启动 P00。提交此表只完成规划交付；[本轮校验](validation_receipt.json)不是新阶段验收报告。
