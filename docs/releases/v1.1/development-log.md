# v1.1.0 Development Log

这是已发布版本的工程历史摘要，stage IDs 只用于定位 receipts，不作为当前 API 名称。
精确 source/evidence hashes 继续由[source manifest](source_recovery_manifest.json)和唯一能力矩阵维护。

| 工程单元 | 主要 commits | 结果/记录 |
| --- | --- | --- |
| Task ownership / Outcome V1 | `d01cc3b`、`0dde256` | task-owned reference construction；NutAssembly outcome 与 strict Expert 分离 |
| PickCube/NutAssembly authoring | `13063f8`、`38f18f3`、`5b00580`、`ce1cd78`、`4d6d65c` | selected 四文件路径，GeoPhys/MuJoCo CPU bounded receipts |
| Go2 retirement | `9c6548d`、`5b8c901` | 移除专用实现，保留 generic contracts |
| Static-template retirement | `0ff2d84` | GeoChora-owned solver 退出，merged_scene 与受限 provider adapter 保留 |
| Developer workflows | `5d57272`、`5910572`、`929dd8f`、`fc12780` | examples、record/inspect、bounded learning/rendering |
| CLI/发布准备 | `bee498d`、`e0e4dbc`、`2fb60de` | argv fix、compatibility inventory、provider-free regression 与候选 release content |
| S5-C1–C8 审查与清理 | 冻结 receipts 见下 | 精确 manifests 获批；assistant 在首个 unlink 前停止；维护者 manual cleanup 后 65,826 ordinary paths absent，无 per-file unlink logs |
| L2 Git 保留 | `745efc6a6693a7d10407c6ddd02837a2ae574131` | 22/22 size/hash 相符，代表性 H5/JSON readback，same-account GitHub copy |
| 正式发布 | `7ed9e78a60d407fa1150c99209e06c70bfa0ed87` | annotated v1.1.0 与 GitHub Release，2026-10-18 |

[原 retrospective](https://github.com/Lebingelee/GeoChora/blob/v1.1.0/docs/releases/v1.1/p2_0_retrospective.md)
保留 review 时点的 completed/partial 分类，不事后改写。
[C8 final report](https://github.com/Lebingelee/GeoChora/blob/v1.1.0/docs/releases/v1.1/c8_manual_cleanup_final_report.md)、
[completion audit](https://github.com/Lebingelee/GeoChora/blob/v1.1.0/docs/releases/v1.1/c8_goal_completion_audit.md)、
[monitoring revision](https://github.com/Lebingelee/GeoChora/blob/v1.1.0/docs/releases/v1.1/c8_storage_monitoring_revision.md)
记录授权/停止/手工后观察和 evidence limits。Registered worktree 与 522 holdouts 仍保留；
历史 bundle/raw recoverability 不能从 source manifest 推导。发布最终接受 same-account L2 copy 与历史
full-workspace backup gate waiver，含义为 RELEASE_RISK_ACCEPTED，完整备份/独立管理域未验证。

本次 post-release 文档整合只重写活动导航与 contract，总 inventory/disposition/recovery/hash/reference
验证见[整合回执](../../maintenance/consolidation-review.md)。不重开 Phase 2.0 实现，不授予 qualification。
后续 benchmark/Harness/PhysPi 方向见[roadmap](../../roadmap/README.md)。
