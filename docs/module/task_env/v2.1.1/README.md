# TaskEnv v2.1.1 — 协议与实施规划

日期：2026-11-06。G03 的 3a、3b、3c 及 G04 的 4a、4b、4c 均经 Sol 按各自冻结范围独立有界接收；准确当前进度以[编排索引](maintenance/orchestration.json)、[恢复页](maintenance/recovery.md)和各独立主审为准。4c 的范围为 MuJoCo CPU 单 Env reset 切换及迁移后 PickCube seed31 成功；原 N08 FAIL、Isaac 6.1 close 超时、通用装配补偿与未验证交集保留，不外推正式 Qualification。

阶段 5 的 5a 按 PickCube MuJoCo CPU renderer-only 代表绑定有界接收；5b 普通 count=3 后进入维护者主导诊断。[诊断 attempt002 独立主审](maintenance/reviews/20261107_5b_diagnostic_attempt002_sol_review.md)为 `DIAGNOSIS_PARTIAL_REWORK_REQUIRED`，诊断 count=2，5b 未接收。通用 reset 恢复有界修复；Isaac headless RGB、独立窗口和关闭后继续采集有界成果及 CPU 路线关窗证据保留；相机隔离和可辨图像判据仍待闭合。5c 仍 PLANNED、attempt0；同步 observation 与跨组合尚未完成。遵循 [G05 原目标](goals/05-rendering.md)及已确认的 render／生命周期协议。装配 Panda 仍为版本附加用例，不替代阶段 5 主线；完整两任务 Solution 用例留 7a。

历史状态：日期：2026-11-06。状态：G01/1a–1d、G02阶段2和3a已按各自限定范围接受；3b attempt002已由Sol复审，整体REWORK_REQUIRED_3B、count=2。已测Panda MuJoCo CPU重力补偿与launcher／F06记录修复有界接收，最终补偿记录及required物性等仍待闭合；原N08 FAIL保留，不自动003或3c。详见[002主审](maintenance/reviews/20261106_3b_attempt002_sol_review.md)。原2b attempt002的G2 FAIL、G3 PARTIAL、G5 INCOMPLETE_USER_PAUSED历史保留，见[阶段2主审](maintenance/reviews/20261104_2c_sol_review.md)。

## 版本目标

以统一任务表示为中枢，明确 Core、physics provider adapter、render adapter 之间的协议，实际接通 MuJoCo、GeoPhys、Isaac Sim＋PhysX 的首批路线。支持构建及 reset 时选择后端、renderer 和 Controller；episode 内维持已选执行组合。reset 重新初始化下一轮，不迁移上一轮物理状态。

控制器统一、PickCube Solution 修复、窗口与同步 RGB、并行执行都服务于上述协议的真实落地。接口注册、静态通过或窗口截图不代表整条路线完成。

## 阅读入口

- [范围与七阶段路线](planning/roadmap.md)：7 个阶段、22 个 a/b/c/d 子阶段及延期事项。
- [执行顺序与验收](planning/execution-and-acceptance.md)：依赖、阶段出口、工作包、证据及分支约束。
- [阶段3前维护方案](planning/pre-stage3-environment-refactor.md)：生命周期R1与限定的核心代码／开发文档收尾已获[Sol有限接收](maintenance/reviews/20261105_pre_stage3_closeout_120min_sol_review.md)，该前置核心窗口结束；更广整理和未验证能力保留边界。Pendulum并行适配留阶段6。
- [源码 owner 与外部参考](planning/source-map-and-references.md)：当前基础、缺口、待讨论事项和官方项目链接。
- 协议实施基线：[统一任务表示](contracts/unified-task-representation.md)、[physics provider](contracts/physics-provider.md)、[render provider](contracts/render-provider.md)、[控制与反馈](contracts/control-and-feedback.md)、[生命周期与数据](contracts/lifecycle-and-data.md)。
- 阶段 Goal：[01 协议](goals/01-protocols.md)、[02 Solution](goals/02-pickcube-solution.md)、[03 后端](goals/03-backends.md)、[04 控制](goals/04-control.md)、[05 渲染](goals/05-rendering.md)、[06 并行](goals/06-parallel.md)、[07 集成](goals/07-integration.md)。
- [API 迁移入口](api/README.md)、[指南交付要求](guides/README.md)、[单一能力矩阵](capabilities/README.md)。
- [恢复页](maintenance/recovery.md)、[编排索引](maintenance/orchestration.json)、[本轮文档收据](maintenance/20261103_documentation_receipt.md)。

## 来源和当前能力

规划输入 Core：`develop@fd03817c9f6ef8ce9fd68c1db30125efda68e1c8`；GeoPhys pin：`67da1165149486d3ae3e779c13ce31af49e17d50`。本地 `refs/tags/v2.1.0` 指向该 Core；本轮未查询远端或 GitHub Release，不能从旧候选措辞推断当前发布状态。

当前实现与证据仍按 [v2.1.0 API](../v2.1.0/api/public-api.md)和[有界能力矩阵](../v2.1.0/capabilities/capability-matrix.json)理解。selected 渲染仍只准入 state-only；R3 主要输出位置参考；LIBERO 有限定的力矩＋位置混合控制。G02/2a 与 2b 有当前 MuJoCo 原生证据；PickCube seed32 有效运行但任务失败。阶段2接收范围为seed31成功实现、受影响Nut回归及可复现参考，不将原2b扩展包的未过门改为PASS。该段记述旧规划时点，其余阶段实际状态以编排索引及恢复页为准。

F06 历史 9/9 runtime-valid、0/9 task-success，R07 A123 的有界接收与例外、F05 未决研究门均保留。不将 v2.1.1 的目标或后续结果改写进冻结证据。

## 当前 G02 证据

MuJoCo PickCube seed31 和 NutAssembly seed19 的任务、Solution、runtime 与独立 HDF5 读回均通过；PickCube seed32 的 runtime/记录有效，但在 horizon 1000 时任务与 Solution 失败。GeoPhys PickCube 在执行边界时间 guard 抛出 stale execution time；Isaac delivery 文件校验通过，但 GPU admission 不稳定，本包未启动 Isaac App。详见 [2b 收尾报告](maintenance/reviews/20261104_2b_closeout.md) 与 [恢复页](maintenance/recovery.md)。2c文档封存已由Sol有界接收，该阶段2收尾记录的时点早于阶段3执行。

## 文档边界

本目录拥有 v2.1.1 的规划及已确认语义协议；v2.1.0 保留来源版本行为。每项协议只在对应 `contracts/` 页面维护，Goal 引用它并记录具体实施与验收。实现后再更新 API、指南和矩阵，不能把设计基线当成现有可调用 API。系统归属仍服从[架构](../../../global/architecture.md)与[ownership](../../../global/ownership.md)。

## 本体重力补偿（有界接收）

维护者已授权实施默认关闭的 [Panda 本体重力补偿](guides/panda-gravity-compensation.md)。当前仅 MuJoCo CPU 进程内 selected PickCube／Nut 路线有界实现；原 3b 默认关闭的 N08 历史失败保留，其他 provider 的开启请求不支持。
