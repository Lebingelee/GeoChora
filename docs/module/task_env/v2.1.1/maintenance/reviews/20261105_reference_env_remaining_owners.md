# SelectedReferenceEnv 剩余职责核对

2026-11-05，只读检查 `f23d77ab`，`task_env/environment/reference_env.py` 共 3574 行。行数是定位线索，不是验收标准。本页列出仍在环境类内部、可核对的职责，不把抽取计划记为已实施。

| 当前方法 | 实际职责和风险 | 应继续使用的现有 owner／验证 |
| --- | --- | --- |
| `_prepare_reference_reset`（第 1390 行） | 准备不同 selected 路线的重建、session 替换、reset、状态与 observation 发布，并保留异常时清理顺序。seed／options／来源前置验证和重建后的执行路线／种子一致性验证已在 `reference_binding`；其余流程还在 Env。 | `EpisodeExecutionState.execute_reset` 保持唯一顺序与故障 owner；task binding 提供任务的准备与投影，runtime session 拥有 provider 资源。必须继续验证非法 seed／来源在关闭活跃 session 前被拒绝、部分构造回收和 fault 恢复。 |
| `_prepare_selected_step`、`_prepare_reference_step`（第 1907、2746 行） | 前者区分 caller-driven、Position、leaf、mixed 与兼容动作；后者协调 request、Controller、native 样本、recording 和发布。`step_expert()` 仍是受限兼容。 | 公共 Env 保留动作入口与 episode 协调；任务特定反馈／Solution 条件归 binding 与 task，控制准备和 ack 校验归现有 controller／runtime，记录投影归 recorder。不得删除五样本、错边界、部分推进故障或 T+1 规则。 |
| `_prepare_mixed_control`、`_prepare_leaf_position`、`_prepare_position_profile`（第 1993、2368、2497 行） | 不同控制路径分别包含请求校验、物理 interval 协调和结果发布；当前不等于已经有统一 provider 接口。 | 复用 `runtime.sessions.control`、leaf plan／binding 和 `EpisodeExecutionState`；禁止再建并行 Runtime 或把任务 callback 包装成第二状态机。现有 `test_r07c_libero_core_env_s1.py`、`test_phase_ii_01_r06b_order_regression.py` 与 selected 测试保护顺序、部分写入和 fault。 |
| `__init__`、`_build_runtime_with_rollback`、`_close_reference_resources`（第 1063、98、3050 行） | 负责多种构造／资源路线、失败回收和 close；`_close_reference_resources` 仍含 mixed、Position 和 selected 分支。续作已将共同的 session／runtime owner 关闭和故障保留归 runtime；路线特定的录制、camera、source 和 task 资源收尾仍由 Env 编排。 | 构造只协调已有组件；资源创建／关闭由各自 session、camera 和 recorder owner 承接。迁移必须保留先前异常、附加清理错误、资源所有权及重复 close 语义；禁止把未完成 interval 保存成成功轨迹。 |
| `start_recording`、`finish_recording`（第 3431、原方法所在区段） | 起始边界和 recording 生命周期在 Env；selected 来源与 metadata、H5 保存／校验已交 `recorders.reference_provenance`，mixed／Position 仍做 recorder 创建与路由。 | `recorders` 和 canonical trajectory 负责格式、元数据和持久化；Env 只判断可否开始／结束、Stop 与故障顺序。保留 `test_selected_consumers.py`、`test_pre_stage3_boundaries.py` 与真实同次 reader 检查。 |
| `_format_step_result` 和 observation 发布 | scalar 组件／selected 路线仍在 Env 投影信息；selected observation 组合已由 `observations.selected_reference` 和 task binding 承担。 | 继续区分正式反馈、task evaluation 和一次性诊断；保留 shape／dtype／space、reward、terminated／truncated 和实时边界，不把观察结果简化为静态布局。 |

后续重构应按以上可测试的职责边界逐项推进，不以机械拆文件、改变任务数学或另造 Runtime／Env 模板完成。最新物理和离线证据见[验证记录](20261105_pre_stage3_resumed_physical_checks.md)；维护者已授权续作的离线墙时重新计数，上限为 3000 秒，详见[当前状态](20261105_pre_stage3_current_status.md)。
