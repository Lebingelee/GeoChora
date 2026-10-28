# Phase II-01 — Composite Robot & Core Integration

当前规划状态：**CHECKPOINT_RECOVERY_PLAN_UPDATED**，2026-10-28。R03c attempt002 静态修正已接收，
检查点 `c30d97e`，S2 不完整、S3 未运行。恢复入口为 [07](07_Execution_Order_and_Acceptance.md#r03c-checkpoint-recovery)，
新增 USD/Isaac/GeoPhys/Harness 补丁为 [10](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md)。
本轮仅修订文档，没有实施或 native 授权；原 7 父 Goal/22 切片及 P99 保留，逐 slice 的已授权/已接收事实见 manifest。

原 2026-10-23 规划状态为 REVISED_DRAFT / AWAITING_MAINTAINER_GOAL_DAG_APPROVAL，目标版本 v2.0.1；
后续已有独立 P00 与逐 slice 指令。原基线、签署时点与历史批准边界保留，不能再把“R01–R07均未启动”作为当前状态。
新 P00 从 Core `259f27f…` 起，见 [README](README.md) 与 [manifest](planning_manifest.json)。

## 基线与治理

本轮规划基线为已fetch并独立核验的 develop `535ce2516e61ecd538d5ff6dccf7493a1cfe2cac`（已提交的首版 R07 规划；其输入为 `234da21b…`，原工程冻结仍为 `3759f917…`），远端 public/develop 本轮 readback 相同；本地 main/public/main 记录为 `f292df149f41520b484ff27cf2ff78a584903013`，本轮未重新抓取 main。GeoPhys gitlink `a53a8cfed7c9d6464274b5c96fca601271dc4ee4`；Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。规划文档的新提交不冒充被接受功能源码 `90071ace…` 的新行为证据。

本地 v2.0.0 分支和 annotated Tag 均指向 `3759f917…`；Tag 对象 `4ebd8d536c0c054641c6edc1a31fcd317fa237cc`。这两个引用已另经维护者授权推送并回读远端，指向相同冻结提交；本轮不执行 main promotion 或 GitHub Release。本轮不移动它们。[Phase II 范围决定](../../../../maintenance/phase_ii_scope_freeze_20261023/maintainer_scope_decision.yaml) 及[九文件状态入口](../Phase_II/05_Architecture_Review_and_Execution_Order.md) 原样保留；历史“未授权 Tag”描述保留其签署时点含义，后续建立本地引用的授权来自维护者对话。

Scoped Engineering Acceptance、Task Freeze、Release Promotion、Formal Qualification 分别决议。此草案及文档提交不产生后三者；也不重新打开 Phase II 20/33/P00/P99 的已接受范围。

## 端到端目标与独立能力链

首条新执行交集拟定为 **MuJoCo 3.8.1 CPU × Menagerie 独立 panda_nohand.xml + hand.xml × 静态 Fixed Attachment × Arm-only/Hand-only Position Profiles**。未来须由同一公开 Environment 完成 reset→连续真实 step→typed/public observation→既有 Recorder→同 H5 readback→close。预组装完整 Panda 与两个自由 Panda 都不能作为独立 Attachment 成功证据。

| Goal | 最低新出口 | 独立边界 |
| --- | --- | --- |
| [R01](01_R01_Logical_Robot_Assembly.md) | Entity Member / Existing-Entity Subcomponent Reference、递归身份和静态解析 | 不创建物理 joint 或第二 Entity |
| [R02](02_R02_Composite_Control_Profiles.md) | Arm-only/Hand-only leaf profiles、preset/override 编译、唯一 writer、真实 leaf S2/S3 | 两个完整 Panda Controller 不充分；Position 不依赖 R05 |
| [R03](03_R03_Physical_Attachment.md) | 独立资产真实固定装配、状态/控制/公开录制 | MuJoCo CPU 为首个 required Provider 候选；GeoPhys 精确导入路线未准入 |
| [R04](04_R04_Dynamic_Camera_Consumer.md) | 现有 dynamic Camera→public observation→同 H5 semantic reader | 独立 GeoPhys CPU × MuJoCo EGL 路线，不是 R01/R02 Position 前置 |
| [R05](05_R05_Native_Rate_Feedback.md) | GeoPhys Provider 批准的正式 native-rate sample、CPU/CUDA 精确准入与实测 | 不提升原 host diagnostic；不是 Position 前置 |
| [R06](06_R06_Compatibility_and_Regression.md) | 顺序映射/机械语义/版本保护、缺失原件决议与交付汇总 | 不补造历史 bytes，不自动退休 Reader |
| [R07](09_R07_Benchmark_Deployment_and_Agent_Cost.md) | 五个固定LIBERO候选Task真实部署/语义对照、Agent成本与独立质量审阅；RoboCasa早期feasibility | 独立父Goal，不隶属R06；不要求Expert/训练/任务完成，不宣称成本因果下降 |

R07新增4切片；P99建议直接依赖R06c与R07d。R07c每Task的R02/R03/R04条件前置须在配方中明确选择；首版authentic预集成MountedPanda/state-only方案为none，缺Core通用构造/谓词/公开状态能力仍BLOCKED_CORE。

R04、R05 各自独立施工，但按当前建议均为整阶段 P99 的 required gates。某项失败不阻止不依赖它的 Position 子链继续，却阻止最终 P99 通过，除非维护者先批准精确范围变更。R03 第二 Provider 的执行不是默认 required；其拒绝原因和未获 Qualification 的状态必须可追溯。详见[执行表](07_Execution_Order_and_Acceptance.md)。

2026-10-25维护者工作流补充：上述独立能力链不对应逐Goal新建Git分支。Phase II-01复用既有`codex/phase-ii-01-p00-20261023`作为本阶段集成分支，计划内开发分支总数为1、新增worktree为0；原名称保留，其职责覆盖本阶段多个子阶段和Goal。按[07的Sol/Luna顺序与提交闭环](07_Execution_Order_and_Acceptance.md#sol-luna-workflow)逐包推进。该流程偏好已明确，不代替尚待决定的具体实施范围和运行合同。

## Owner 与组合路线

依赖始终为 Core→Provider public/runtime-facing API。[architecture](../../../../global/architecture.md)、[ownership](../../../../global/ownership.md)、[Public API](../../public-api.md)、[Artifact/Evidence](../../task-artifact.md)、[qualification](../../qualification.md) 为当前规范；本阶段草案不改变已支持 API。

```text
Asset closure / existing importer → Scene Entity instances
  → versioned logical refs + independent attachment intent
  → preset + leaf overrides → existing ControlBindingPlan
  → existing RuntimeSession / admitted Provider (one physics owner)
  → typed publication → public observation / camera consumer
  → existing Recorder / strict versioned readers / Evidence
```

Logical contracts 属 `task_env/artifacts/`；编译/source mapping 属 `task_env/assembly/` 与现有 runtime source/admission；控制复用 `controllers/canonical/`、`runtime/sessions/control.py`；环境与故障归现有 Environment；Camera、Observation 和 Recorder 各持有自己的资源/输出，不复制 Runtime/physics store/Registry/Controller 算法。当前 dual diagnostic builder 仍依赖 test helpers，未来公开化需在既有 task/source owner 提取必要构造，诊断反向复用。

优先 COMPOSE_EXISTING / EXTEND_EXISTING。新不可变引用值并不授权新 Runtime abstraction；NEW_IMPLEMENTATION 必须另证既有 owner 不足。完整 source→consumer→failure→close 路线和[风险/修订对照](README.md)须在 P00 批准后细化。

## 原 7/22 外部原则与非目标

原规划固定引用为 Isaac Lab v3.0.0（官方 Release 2026-10-20）与 Isaac Sim 6.1.0；[参考锁定表](README.md#references)保留原用途。
2026-10-28 新增计划按 [10](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md) 接收已验证 USD，并规划 Isaac 6.2 pip 环境与 provider adapter；
这不是把原 6.1 引用当作安装版本，也不引入第二 Runtime 或统一 Provider storage ABI。旧 reference 的 source/身份不因新计划升级。

R07只规划 `asset/benchmarks/`（资产来源/许可/安装验证）与 `bench_deploy/`（benchmark配方/最小adapters）；不创建新TaskEnv/registry/Agent runtime。PhysPi仍外部消费方。

原 7/22 不做动态 attach/detach、闭环拓扑热切换、通用 Assembly/仲裁、双臂 IK、所有 Provider/CUDA 矩阵、Camera async/semantic masks、训练/跨引擎 policy transfer 或自动 Qualification。
Task Harness 从原非目标调整为 [10](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md) 的独立接入计划，
消费既有 Core；不改变 R07 原五任务的 Expert/训练非必需边界。保持 Scene v1/v2/v3、旧 Artifact/Entity/Recorder identities 与历史 Evidence；新增合同独立版本化，不向旧 codec 静默增字段。

原规划批准顺序为：维护者审阅→批准最终Goal/DAG/Required Envelope→单独启动P00→逐slice执行与Evidence→独立P99 scope decision→另行Release Gate。后续明确授权允许P00基线核查和准入准备先行；这不批准最终范围，也不越过逐slice实施gate。相关范围未获明确批准前，工作包只能为AUDIT_ONLY，不能标READY_TO_IMPLEMENT。
