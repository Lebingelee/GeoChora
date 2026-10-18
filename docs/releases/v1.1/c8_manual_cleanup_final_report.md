# S5-C8 手工清理后观察与原 Goal 最终交付

**GeoChora v1.1.0 — RELEASE_CANDIDATE — NOT_PUBLISHED**

观察时间：2026-10-18 11:27（Asia/Shanghai）。本报告续接 [C8 执行停止与 Phase 2.0 回顾](c8_execution_and_phase2_closure.md)，不新增 C9。此前报告的“零删除”描述属于助手停止执行时的历史状态；以下是用户手工处理后的独立观察。

## 清理结果与边界

| 批次 | 已观察消失的普通文件路径 | 仍保留 |
|---|---:|---|
| A | 17/17 | 无本批原有 holdout |
| B | 173/173 | 6,619 个注册 worktree 条目、3 个历史 holdout |
| C1 | 3,382/3,382 | 1 个历史 source bundle |
| C2 | 62,254/62,254 | 518 个 holdout（含未知/未解决项和符号链接） |

合计 65,826 个批准普通候选路径均不存在。助手没有删除或搬动原始文件；没有逐项用户 unlink 执行日志，因此结果为 **ABSENT_OBSERVED**，不将其冒充助手执行成功收据。注册 worktree 未删除；其 Git/submodule 处理限制仍成立。522 个原有 holdout 全部存在且身份核验通过。

87 个当前 L1 文件、22 个 L2 文件（24,563,669 字节）的 SHA-256 均匹配原保护快照。四份批准清单哈希仍匹配。原始 L1 历史版本和 37 份历史元数据保留于 Git。新报告和观察收据是追加的 L1，不覆盖保护快照、批准清单或原始结果。

Workspace 分配空间由 76,170,403,840 字节降至 2,815,557,632 字节，观察减少 **73,354,846,208 字节（68.317 GiB）**。文件系统可用空间观察增加 73,363,390,464 字节（68.325 GiB）。这两个值是不同时间点的全局观测，包含后台活动；不是每个文件 unlink 所释放块的精确计量。路径消失也不能排除移至其他位置，不据此证明所有原始字节已销毁。

C1/C2 相应历史原始轨迹、实验数据和 GeoPhys 源码快照已不在批准原路径；如用户已永久删除，缺少独立副本的内容可能永久不可恢复，历史重审和原环境重建能力随之损失。维护者已明确接受相应损失。哈希不能恢复原字节。冻结 v1.0.0 Git 决策、源码、tag 与保留元数据不变；原有 P1.6 恢复归档未找到的问题仍是历史缺口。

## 验证与停止条件

- 最新只读监测：L1/L2 全部哈希通过；候选路径均消失；worktree 和 holdout 无异常。
- 本轮执行源码相对 public/develop 的 `task_env`、GeoPhys Gitlink、asset、`docs/releases/v1.0` 无 diff；未重复已接受的 native full routes。
- 恢复原 Goal 后，已在清理后源码 `fa4d898` 上重新运行相同 9 项 provider-free 检查：7 passed in 1.51s，2 passed in 0.81s。覆盖选定 Artifact、reset、semantics、retired UID、import isolation、workspace independence 与 task binding。Python 3.12.14、2 GiB RLIMIT_AS、150 秒 CPU ceiling、180 秒 subprocess timeout；无 native 执行。日志和命令保留在原 C8 execution 目录的 post_manual_cleanup_tests.json 与两个 .log。没有新增 Qualification、D0–D2、训练或 native 渲染验证。
- public/develop 读回 `2fb60de7851bf2e5651c2dc99fff7451c16e1a94`；main `e4e39883fbe01d4be4b172a53a535ef0095b3d64`；v1.0.0 tag object `17c3100d4fabcb061c23569dea49973ebd177d51`、peeled `42787f5e4f658a3f81fdd2140cf7544d6342c783`。
- `/sys/block/sda/device/ioerr_cnt` 从上轮 `0x7ee` 增至 `0x7f3`。这是尚未分类的 SCSI 错误计数异常；可读 kernel log 未提供同期新 ATA 读写错误解释，不能证明存储健康。停止所有进一步删除和高负载操作；不重置停止标记、不绕过安全门。

[机器可读观察收据](evidence/retirement/c8_manual_cleanup_observation_20261018.json)保留计数、空间、监测/清单哈希和限制。完整扫描记录仍在 ignored 的 C8 手工监测目录。

## Phase 2.0 原目标与阶段完成度

原目标是明确 Core/Task/Provider 所有权、减少重复实现和冗余实验负担、保留可审计的证据与恢复边界，为后续跨框架工作准备稳定 Core，不是宣告全部 Phase II 功能完成。

| 阶段 | 结论 |
|---|---|
| P2.0-A 所有权、Evidence 与 Workspace | 文档和证据分层已建立；本轮普通候选路径清理已观察完成；注册 worktree、holdout、存储和备份问题保留，不能称全部清理完成 |
| S0 | Renderer Registry M1 完成；没有新增 native renderer 资格 |
| S1/S1.6 | task-owned construction 与 NutAssembly Outcome V1 完成；严格 Expert 状态与物理任务结果保持区分 |
| S2 | 两个选定任务均四文件 authoring；两个 CPU provider 的选定路线有 bounded acceptance |
| S3/S4 | Go2 与 GeoChora static solver 的批准退休范围完成；通用 RL、Batch/Device/Vectorization 与 GeoPhys adapter 保留 |
| S4.5 | 当前 task/expert/recording、Pendulum learning/rendering 工作流完成批准范围；不代表通用互操作 |
| S5-A/B | v1.1.0 candidate、兼容性披露和能力矩阵准备完成 |
| S5-C8 | 批准普通候选的手工清理后核验与本报告完成；B worktree 保留，publication 仍 BLOCKED |

## v1.1.0 Release Readiness

| Gate | 状态 |
|---|---|
| 当前 L1/L2 完整性 | PASS（本地哈希核验） |
| protected refs 与选定执行源码未变 | PASS（远端 ref 读回与本地 diff） |
| 选定任务功能 | PASS，限既有 TESTED_BOUNDED 的四个 task/provider CPU 交集 |
| API migration、项目版本策略 | 文档已准备；v1.1.0 为含 breaking changes 的项目特定 consolidation 版本，不宣称严格 SemVer |
| 注册 worktree 退休 | BLOCKED，继续保留 |
| 存储异常 | BLOCKED，未分类计数继续增加 |
| 独立备份 | BLOCKED / NOT_VERIFIED，清理授权没有豁免备份门槛 |
| Controller Option B 风险、能力矩阵批准 | MAINTAINER_DECISION_REQUIRED |
| Fresh-install / 全量 relocated regression | NOT_RUN；既有 detached-checkout smoke 不等于这两项；139 PASS / 8 FAIL 记录保持 |
| 新 L1 远端保留 | NOT_RUN，未获 push 授权 |
| 正式发布授权 | MAINTAINER_DECISION_REQUIRED |

无新的 P1.8 FULL、D0–D2、操作策略 checkpoint、通用 manipulation PPO、Native Flora 或 Native GeoPhys Rigid Batch qualification。GeoPhys NutAssembly 原 strict Expert failure 与 Outcome V1 成功独立保留。

## 后续 Phase II 方向与交接

优先处理存储异常和独立恢复验证；再决定 worktree 的合规处理、controller identity Option B、candidate capability matrix 和 L1 公共集成。发布必须另行授权，本任务没有 push、main 修改、tag 或 GitHub Release。

未来 P2.x 应从一个外部 benchmark/任务框架入手，比较其 native route 与 canonical TaskArtifact/TaskEnv 路线，再建立可验证的 controller/observation/provider 映射、双向轨迹转换与执行验证、Task Harness 和后续 PhysPi 消费边界。通用 Physics × Renderer interoperability、跨 benchmark 完整兼容和自主 RSI 均不在本次完成范围。

普通清单已经无剩余路径，定时监测在本次交付后停用，避免继续无变化的扫描。B worktree 和全部 holdout 不会因此获得删除授权。未解决风险不会被标记为完成。

## 原 Goal 完成情况复核

按原 Goal A–K 判据：A/B/C/D/E/F/I/J 已有完成证据；G 为部分完成（普通候选路径消失，但缺少用户逐项 unlink 收据，B worktree 未退休）；H 的保护数据和空间观测已完成，精确逐项回收归因不可验证；K 的 readiness 报告已完成，但 release 仍 BLOCKED。不能将整项 Goal 标记为无条件 complete，也不因保留例外再开启一轮常规清理。当前 release_readiness.md 等此前版本仍记录执行停止时状态，应结合本追加交付阅读；统一这些当前状态页仍是文档同步待办。目标系统查询仍为旧 blocked 状态；工具仅支持 complete/blocked/paused，恢复 active 由用户端控制，不虚报已更改系统状态。
