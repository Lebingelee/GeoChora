# GeoChora v1.1.0

v1.1.0 于 **2026-10-18** 正式发布，是带有 documented breaking API changes 的 Core
consolidation release，采用项目版本策略，不声称严格 SemVer。
[GitHub Release](https://github.com/Lebingelee/GeoChora/releases/tag/v1.1.0) 的发布时刻为
06:53:35 UTC（北京时间 14:53:35）。

- Annotated tag object：`da46f1d213a457af7784a97d6d8470b7fa20cc32`。
- Source commit：`7ed9e78a60d407fa1150c99209e06c70bfa0ed87`。
- [CHANGELOG](CHANGELOG.md)、[development log](development-log.md)、[migration](migration.md)、
  [known limitations](known-limitations.md)。
- 当前操作说明统一在 [TaskEnv](../../module/task_env/README.md) 与 [examples](../../../examples/README.md)。

## 能力与 Evidence

唯一能力 schema/矩阵继续使用已发布的
[`capability_matrix_v1_1_0_candidate.json`](../../module/task_env/capability_matrix_v1_1_0_candidate.json)。
其 candidate 字段保留原记录时点；publication 以 tag 和 GitHub Release 为准，不修改历史矩阵来追补状态。
四个 selected manipulation/provider CPU 交集是 TESTED_BOUNDED，未授予新 qualification。
范围和状态定义见[qualification](../../module/task_env/qualification.md)。

所有 **22 个原始 L2 文件、24,563,669 bytes** 保留在
[`evidence/raw/l2/`](evidence/raw/l2/)，文件的精确分类以
[清理 inventory](../../maintenance/consolidation-inventory.json) 中逐文件类型、size/SHA-256 为准。
L2 文件清单与 hashes 的冻结权威记录是
[原 Evidence index](https://github.com/Lebingelee/GeoChora/blob/v1.1.0/docs/releases/v1.1/evidence/README.md)
及保留原 bytes 的[backup_manifest](backup_manifest.json)。
[Source/recovery manifest](source_recovery_manifest.json) 绑定源码、Gitlinks、Artifact identities 与恢复 refs。
这两个历史 manifest 内的 workspace/相对路径按原时点解释；移出活动树的路径通过 tag 恢复，
完整 old→new/tag mapping 在清理 inventory，不重新写 frozen provenance。

[Manipulation receipts](https://github.com/Lebingelee/GeoChora/blob/v1.1.0/docs/releases/v1.1/evidence/manipulation_acceptance.md)
保留 PickCube/NutAssembly × GeoPhys/MuJoCo CPU 100 Hz 指定 seeds 的结果。
[System smoke receipts](https://github.com/Lebingelee/GeoChora/blob/v1.1.0/docs/releases/v1.1/evidence/system_smoke_acceptance.md)
保留录制、147 tests/6 subtests、Pendulum learning/rendering 的原有界检查。
[Test summary](https://github.com/Lebingelee/GeoChora/blob/v1.1.0/docs/releases/v1.1/test_acceptance_summary.md)
记录执行范围；本轮文档检查不重新授予这些结果。

## 冻结历史

已发布 GitHub Release 的 capability/evidence/test/migration 链接使用 v1.1.0 tag，仍指向原 bytes。
历史 S5 review、Judge decisions、source-recovery 与 cleanup receipts 全部通过冻结 tag 保留。
本活动分支的文档重写不修改 tag、发布 body 或历史 verdict。若需精确恢复某文件：

```bash
git show refs/tags/v1.1.0:docs/releases/v1.1/test_acceptance_summary.md
```

Hash metadata 不恢复已丢失 L3 raw data；完整历史工作区与独立管理域备份仍未验证。
发布接受状态为 RELEASE_RISK_ACCEPTED，不能写成 FULL_BACKUP_VERIFIED。
