# v1.0.0 → v1.1.0 CHANGELOG

v1.1.0：2026-10-18，Core consolidation release。项目选择 v1.1.0 标识带 breaking API
的整合发布，不承诺 strict SemVer；v1.0.0 历史版本保持不可变。

| 变更 | v1.1.0 行为 |
| --- | --- |
| Task authoring | selected PickCube/NutAssembly 四文件 task-owned 路线，复用现有 Artifact/runtime/controller/recorder contracts |
| 公共任务构造 | 使用 `task_env.make_env` 的两个 selected UID；与 legacy UID/配置不语义 alias |
| NutAssembly | Outcome Completion V1 guarded expert，11-stage completion 与物理 task outcome、strict lifecycle 分别报告 |
| Go2 retirement | 专用 task/robot/profile/training/default routes 移除，历史从 v1.0.0 恢复 |
| Static-template retirement | 移除 GeoChora-owned static-template physics；显式 layout/config 拒绝，支持范围内使用 merged_scene |
| 保留接口 | Generic RL、Batch/Device/Vectorization、受限 GeoPhys-owned adapter、Renderer/Camera contracts |
| 当前工作流 | selected task examples、canonical expert record/inspect、Pendulum bounded PPO、scalar/batch rasterizer RGB |
| CLI 修正 | trajectory converter 正确转发 argv，不改变转换/动作/schema 语义 |
| Evidence | 22 个 L2 原 bytes 公共 Git 保留，source/recovery/migration 记录；历史风险按发布决定接受 |

四个 manipulation/provider 交集仅 TESTED_BOUNDED，无新增 formal qualification。
P1.0–P1.6 历史 bounded approvals 保留其原 scope，P1.7 deferred；P1.8 infrastructure/diagnostic
不自动提升。没有一般 manipulation PPO、checkpoint inference、native Flora/GeoPhys Rigid Batch
或 Physics × Renderer 资格。详见[限制](known-limitations.md)、[迁移](migration.md)与[开发记录](development-log.md)。
