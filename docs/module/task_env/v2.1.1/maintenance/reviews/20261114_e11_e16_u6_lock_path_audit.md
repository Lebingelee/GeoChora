# U6 共享锁与旧 integration 路径核对

2026-11-14，输入 `4a7cd0e9`；不启动 native、不修改原始运行记录。此表是当前 checkout 内的静态调用核对，不证明所有外部程序或其他工作树已使用同一锁。

| 消费者 | 实际使用 | 处置与边界 |
|---|---|---|
| `task_env/script/agent/builtin_example_validation.py` | 新路径 `workspace/locks/shared_native_execution.lock` 及历史目录的旧锁路径；打开后、取得锁后比对 inode | 当前正式示例依赖两条路径。当前两者设备 2052、inode 29918777、链接数 2；旧路径缺失、替换或 inode 不一致时拒绝。旧锁及其父目录须保留，不能以新路径存在为由删除旧路径。 |
| `task_env/diagnostics/tasks/v2.1.1/{formal_cpu_probe,canonical_position_probe,worker_cpu_probe}.py` | 分别从冻结计划 `locks_in_order` 读取路径，调用 `native_locks.acquire_plan_locks`，按 inode 去重并加锁 | 要使用适用于当前 checkout 的新计划；历史计划的原 integration 路径已失效，不能未经修改重跑。计划调用者负责指定所有必须的锁；该 helper 不自动发现其他 worktree 的锁，也不验证与示例锁相同。 |
| `task_env/diagnostics/tasks/f05_dg02_{n1_plan,n1_semantic_plan_v2,mjcf_usd_source_plan,equality_coupling_plan,core_s1_refresh_plan,core_n2_reader_supervisor}.py` | 源码明确引用主 checkout 历史锁；部分 F05 监督器及计划还从计划传递锁路径 | 这是特定历史诊断入口，不作为本轮新运行的资格。旧路径当前仍在且与示例新路径同 inode；不能将这些脚本统称已切换到新路径，也不把旧计划改写为新证据。 |
| `task_env/diagnostics/tasks/r06b_order_supervisor.py`、`r05b_native_feedback_supervisor.py` 和 `test_phase_ii_01_r04c_camera_h5_s3.py` | 分别固定引用或向被测调用传递主 checkout 历史锁 | 保留原入口和旧锁；R05b 监督器另把已删除的 integration 当成 `CORE` 和 worker 路径，不能依原路径重跑。若将来需要新运行，须另行冻结当前输入并检查锁和预算，不恢复旧 checkout 冒充原运行。 |
| `r05b_native_feedback_independent_reader.py`、`test_phase_ii_01_r05c_full_campaign_s1.py`、`test_v211_controlled_subjects.py` | 旧 integration 路径作为历史 provider 来源或闭包字节的期望值 | 这些特定出现位置是历史身份比较／fixture 文本，不是要求旧目录存在；不可改写原身份以消除路径字符串。独立 reader 仍须按各自输入要求运行。 |

本次以 `git grep` 核对 tracked Python 中 `shared_native_execution.lock` 和 integration 绝对路径的字面量，并检查 `fcntl.flock` 的调用文件；这不是对 shell、动态拼接、ignored 脚本、其他 checkout 或外部进程的穷尽证明。F05、R04、R05、R06 的计划驱动锁仍以各自真实计划为准；跨 checkout 锁统一没有证明。已删 integration 路径及两锁同时取得的旧双锁计划不得当成当前可运行方案。

受守卫定向测试：`/home/lly/miniconda3/envs/geochora/bin/python`，设置 `GEOCHORA_PURE_GUARD_ROOTS` 为本 checkout `asset` 和 `~/.cache/geochora/usd`，加入版本化 `pure_guard`，禁用 pytest 插件自动加载及缓存，执行 `test_native_locks.py` 的 3 项与 `test_builtin_example_mode.py` 的锁争用、不同 inode、替换、监控异常、强制退休以及两种终止信号节点，共 **10 passed**；只使用临时文件和合成进程，不是 native 测试。第一次错误使用系统 Python 3.14 且未设置守卫根变量，发生守卫初始化错误和缺少 NumPy，10 项在收集阶段 ERROR；上述结果来自正确环境的独立重试，不把第一次失败计为通过。

同日该次审计时，对四个剩余注册工作树的 `/proc` 可见 cwd、root 和 fd 做瞬时路径检查，未见命中；有 1,042 次权限拒绝及 4 个检查时消失的条目，不能由此确认 owner、未来使用、所有映射或不可见进程状态。该观察不构成删除许可。此后维护者明确确认停用并批准具体清单，camera、core-baseline、旧版 clean checkout 已按[执行记录](20261114_e11_e16_three_worktree_execution.md)移除；冻结 archive 继续 locked。

T35 的当前可用锁采用**有界过渡并保留旧路径**；按原退出条件“当前运行不再依赖旧路径”仍 OPEN。其他 checkout、旧计划和锁路径被并发替换的风险亦未消除，不把本表称为全局锁迁移完成。

文档检查（current 模式）退出 1：仍报告既有保护输入 `MUJOCO_LOG.TXT` 基准错误 1 项、历史链接问题 79 项，stale path 0；结果与前次收尾记录的计数一致，不称检查全绿。[原始报告](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/docs-after-lock-audit.log)保留在 ignored workspace。
