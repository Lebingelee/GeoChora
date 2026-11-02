# Post-release 文档与 Module Skill 整合回执

2026-10-18。状态：**本地整合与验证完成，维护者已明确授权推送**。
维护者要求 `v1.1.0`、`develop`、`main` 三个分支同步到同一文档提交；
本次按 branch refs 执行正常快进，已发布的 annotated v1.1.0/v1.0.0 tags 保持不变。
以下验证与未发布描述记录此前审阅准备时点；推送后的 refs 以远端读取为准。
Topic branch 为 `codex/docs-module-skill-consolidation`，基于已 fetch 的 `public/develop`
`7ed9e78a60d407fa1150c99209e06c70bfa0ed87`。开始时工作区干净；生产实现、tests、examples、
GeoPhys/Menagerie Gitlinks 均未修改。

## 基线、处置与保全

完整[逐文件 inventory/KEEP–MERGE–DELETE mapping](consolidation-inventory.json)含原路径、类型、
bytes/SHA-256/Git blob、release identity、owner、原引用者及行号、canonical contract、required 内容、
immutable recovery、最终去向；共 291 条。`contract_reconciliation` 逐页记录原 02–08/lifecycle/guard
headings 及有效 contract 去向，不机械拼接历史文字。

| 范围 | 前 | 后 | 原基线占比 / 上限 |
| --- | ---: | ---: | --- |
| docs 全部 tracked files | 291 | 58 | 19.93% / 58 |
| TaskEnv tracked files | 175 | 14 | 8.00% / 35 |
| docs 人类 Markdown | 129 | 21 | 16.28% |
| TaskEnv 人类 Markdown | 84 | 7 | 8.33% |
| docs 非 Markdown（含机器 Evidence） | 162 | 37 | 单列，不与人类页混计 |

初始 TaskEnv 根目录 45 files，v1.1 93、v1.0 10。处置为 225 HISTORICAL_TAG_ONLY、
25 MERGE_INTO_CANONICAL、31 PRESERVE_MACHINE_EVIDENCE、10 KEEP_CANONICAL；
无未决 REVIEW_REQUIRED。未采用 DELETE_OBSOLETE：所有移除原 bytes 均可从已发布 tag 恢复。
移除 248 个原活动路径，新建 15 个 docs 路径；没有把历史搬到新的 docs archive。

全部原文件在处置前验证与 annotated v1.1.0 tag byte-equal，逐项 SHA-256 和 blob 可恢复。
22 L2 originals（24,563,669 bytes）原路径/bytes 不变；6 个 H5 全部可打开。
唯一发布矩阵、source/backup manifests 原 bytes 保留。6 份仍被 tests、CLI errors 或历史 diagnostic
读者使用的机器 JSON 原路径保留，避免文档清理破坏调用。

v1.0 的 10 files 均保留；仅 README/handoff 中三处 roadmap 导航链接改指冻结 v1.1.0 原文，
其余文本和机器数据不变。两版 annotated tags、release branch、main/develop 远端 refs 未变。
历史 Judge decisions/retirement records 仍在原 tag，未改历史 verdict，也未删除 workspace raw data。

## 新结构与交付项

| 交付要求 | 当前证据 |
| --- | --- |
| 1–2 初始 inventory 与精确 disposition | inventory 的 baseline、records、reference_migration、contract_reconciliation |
| 3 semantic structure | global 两页；TaskEnv 七页；roadmap README；release 五页；无 numeric canonical prefixes |
| 4 global architecture/ownership | [architecture](../global/architecture.md)、[ownership](../global/ownership.md) |
| 5 TaskEnv canonical contracts | [README/quickstart](../module/task_env/README.md)、public-api、task-artifact、runtime-and-providers、recording-and-learning、qualification、troubleshooting |
| 6 post-v1.1 roadmap | [roadmap](../roadmap/README.md)：LIBERO/Panda/MuJoCo 对照候选、Oracle/质量/data 优先、Task/Asset Harness 分离、完整 Policy Harness 延后 |
| 7–8 release history | [CHANGELOG](../releases/v1.1/CHANGELOG.md)、[development-log](../releases/v1.1/development-log.md)、migration、known-limitations、README/Evidence 索引 |
| 9 generic module maintainer | [.agents/skills/geochora-module-skill-maintainer](../../.agents/skills/geochora-module-skill-maintainer/SKILL.md)，四 modes、七步 reuse gate、四 proposal 分类、refresh triggers/procedure/receipt |
| 10 TaskEnv module Skill | [geochora-task-env](../../.agents/skills/geochora-task-env/SKILL.md)，focused routes，复用已有 Experiment/Evidence Skill |
| 11 activation protocol | [AGENTS.md](../../AGENTS.md)：普通 prompt 的 module/mode，不假造 slash command |
| 12 Skill drift/refresh verification | 两个 checker、source/API/examples 验证、独立 cold-start 与修订 readback，见下 |
| 13 docs/link/API checks | 仓库 validator、35 public symbols、13 CLI helps、remote original blobs、JSON/hash/source-reference checks |
| 14 before/after | 上表与 inventory final_counts |
| 15 exceptions/risks | 本页下方和 release known-limitations，未隐藏已复现 CLI failure |

TaskEnv quickstart 并入 README，Evidence index 并入 release README，保持内聚且满足 58-file 上限。
`task_env/doc/api/` 继续为符号级 reference，入口指回 canonical module docs；不维护第二份能力矩阵。
旧架构图片在 tag 精确保留；当前入口不以旧图建立能力声明。

## 实际验证

依赖环境为已有 Python 3.12.14 GeoChora conda environment；未重装依赖。

| 检查/命令 | 结果与边界 |
| --- | --- |
| `python .agents/skills/geochora-doc-governance/scripts/validate_docs.py` | PASS：全部 root-repository tracked Markdown 的 relative links/images/anchors、tag targets、JSON、protected hashes、源代码文档引用、counts、doc-only scope |
| `python .agents/skills/geochora-module-skill-maintainer/scripts/check_module_skill.py <new-skill-dir>` | 两个新 Skill metadata、local links、explicit source paths PASS |
| system skill-creator `scripts/quick_validate.py <skill-dir>` | 全部 8 个仓库/模块 Skill frontmatter/naming/scaffold、local refs 在最终 gate PASS |
| `PYTHONPATH=GeoPhys/src:. python -m pytest -q task_env/diagnostics/tasks` | 138 passed / 161.93 s；taichi_forge 有 locale.getdefaultlocale DeprecationWarning；contract/retirement/workflow regression，不是正式 native qualification |
| public import probe | 35 个实际公开 API symbols PASS；registry queried，internal lifecycle/guard owner imports 单列检查 |
| 13 current CLI `--help` probes | PASS；包含两 task、record/inspect、learning、scalar/batch RGB、scalar/batch env、trajectory record/convert/replay、RSL；仅 parsing，不等于执行成功 |
| public Pendulum API | GeoPhys CPU：make_env/reset(seed=73)/one step/close PASS |
| existing `single_inline` Pendulum smoke | **FAIL**：run_single 读取通用 env 不存在的 binding；记录原失败并将 quickstart 改为已通过的 public route，不改实现 |
| L2 | 22/22 sizes/SHA-256 与 tag/inventory 相符；6/6 H5 readable |
| GitHub Release/API | 已发布；body 中 matrix/evidence/test/migration 四链接在远端 v1.1.0 tree 存在且 blob identity 与本地 fetched tag 相同 |
| `git diff --check HEAD` | PASS |

以上运行详细结果与 exact scopes 位于 inventory `validation`。验证脚本独立检查，maintenance inventory
不是 capability schema。外部消费者不在本地引用扫描范围。

## 独立 cold-start 与修订

新 Agent 使用 `fork_turns=none`，只接收 repo、AGENTS、TaskEnv Skill 和具体 PickCube
record/inspect/evaluation 请求（另询 SAPIEN/Flora）。它通过 CodeGraph 找到 public factory、
shared selected adapter、task-owned solution、既有 runtime/recorder，给出正确构造/录制/检查路线，
并验证 SAPIEN/backend/render overlay 拒绝。没有提议新 Runtime、Recorder 或 evaluator。

该 Agent 执行三个现有测试文件：57 passed / 7.23 s；离线读取 retained PickCube MuJoCo H5：
470 transitions/471 boundaries、T+1 有效、provenance 存在。原 recorded source 为 `5b005801...`，
不冒充 current HEAD 运行；未执行新 rollout/collection/replay。

反馈揭示四处需要明确：Evidence 文件为手动 workspace contract；矩阵历史路径通过 tag 恢复；
built-in Artifact hash 不等于独立 Stage-1 approval；inspector 的 storage_roundtrip 不执行新 save/load。
现已补充 Skill/references，Agent readback 确认四项明确，原 cold-start 要求均无阻碍。
真实 Artifact freeze/acceptance 仍需 explicit validation/Human Judge，不由本轮 walkthrough 授予。

## 例外、未执行与审阅边界

- 已发现 `single_inline` Pendulum step implementation defect，保留到单独授权的修复任务；
  已准确定位既有 helper，不建立替代 factory/runtime。见[troubleshooting](../module/task_env/troubleshooting.md#已复现的-cli-缺陷)。
- 历史 matrix/source/backup manifest 保留 candidate/status 字段及原路径，按冻结记录时点解释。
  当前出版状态独立在 release README；tag-only refs 通过 inventory 恢复。无第二 capability schema。
- 当前 historical diagnostic 可能本来依赖已退休 candidates、缺失 raw archive 或旧 goal paths；
  保留 reader 所需 metadata 不等于恢复原执行能力。不可据此宣称 full recovery。
- 未执行 fresh dependency install、完整 selected native trajectories/新 collection、昂贵 qualification、
  D0/D1/D2、training/renderer campaign 或完整 relocated-checkout regression。
- 原 checkout-dependent controller hash、same-account L2 copy、独立管理域/完整历史备份未验证、
  historical SATA 风险、已接受 L3 loss 等限制继续保留；metadata 不能重建丢失 bytes。
- 审阅准备时仅有本地 diff；随后维护者明确批准推送，并要求三个 branch refs 指向同一提交。
  本次使用 atomic fast-forward push 同步 develop、main、v1.1.0 分支，保留两个 annotated tags
  和 GitHub Release 原记录。此授权仅适用于本次文档整合，不授权改写发布 tags。
  当前不存在数值目标与强制保留的冲突。
