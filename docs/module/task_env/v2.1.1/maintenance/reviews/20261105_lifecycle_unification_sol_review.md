# 2026-11-05 生命周期统一：Sol 独立复审

决定：`ACCEPTED_BOUNDED_LIFECYCLE_UNIFICATION`。接收 R1 的单环境源码迁移及无引擎契约结果；整体阶段3前维护仍为 PARTIAL，阶段3未开始。本决定不覆盖物理一致性、任务成功或 Qualification。

## 输入与核对

审阅 `develop@4840152530e55fb8a3e77517c3b187e99647b5b7`，父提交为 `149bea2603fad91200ce7b16280a1f38423aece1`。实施差异为28个文件；复审开始时 tracked clean，仅有两个原保护 untracked。依据[Terra 交付](20261105_lifecycle_unification_terra.md)、实际 diff、当前调用链及原始日志核对。维护者授权的较长续作与原30分钟 attempt002 分开记账，旧 RW1 FAIL 不倒填。

## 实现判断

| 关注点 | 当前源码与复审结论 |
| --- | --- |
| 唯一 Env 类与公共入口 | `environment/env.py` 仅保留同对象别名；四个 `BaseTaskEnv` 出口均指向 `SelectedReferenceEnv`。Empty、Pendulum、TwoWheel 的实际公共工厂构造得到该类的任务子类，旧独立 Env 实现已删除 |
| 生命周期 | Env 的 reset、step、stop、close 分别调用同一 `EpisodeExecutionState` 的 execute 方法；selected 的兼容 step 路线也调用共同 interval 协调器。组件任务的 `SingleTaskLifecycleAdapter` 与 Env 共用同一 episode state 实例，保留任务评价、RuntimeSnapshot 投影和 RuntimeBoundary 清理，没有第二个 Env |
| 运行时差异 | 组件 RuntimeBoundary 与 selected RuntimeSession 仍有不同阶段接线和结果投影；共同 owner 管理顺序与 episode 状态。此次不把底层 provider 统一或后端切换提前算作已实现 |
| 任务语义与消费者 | 三个旧任务动作、观测、seed、horizon、任务评价及假 render 接线有离线保护；Panda 的控制器／frame 接线回到 robot owner。Nut 外部 Solution、来源边界、target/applied、五样本反馈及记录故障检测保留；`step_expert()` 仍是受限兼容 |
| 故障与资源 | 检查 shared fault、部分推进、最后发布边界、Stop、构造回收和重复 close；新增 leaf／mixed 故障测试保留原故障拒绝语义。未发现需要阻断本次 R1 接收的问题 |

这不是仅修改别名后的接收：公共构造、共用状态实例及实际协调器调用均经检查。不同任务仍提供必要的准备／投影操作，不把这些操作误称为全部运行时接口已经统一。

## Sol 独立验证

在上述提交重新执行 Terra 的最终两组命令，保留同样的三个物理相关排除项，禁用外部 pytest 插件并使用禁止引擎导入的 guard。假 provider 组仅允许既有明确标记的 synthetic fixture。复审输出使用独立目录 `workspace/maintenance/v211_lifecycle_unification_sol_review_20261105/`，未覆盖 Terra 日志。

- offline：**171 passed、3 deselected**；排除真实 Pendulum 两项和依赖真实场景的 Position close 一项。
- synthetic：**12 passed**；包含 leaf／mixed 假 provider、故障、记录及 H5 回读。该回读不是独立物理 reader。
- `checks.json` 记录 reviewed HEAD、cwd、完整 argv、退出码、耗时与 stdout/stderr；两组均退出码0。
- `git diff --check 149bea26..48401525` 通过。保护文件 SHA 与原快照一致；GeoPhys `67da1165149486d3ae3e779c13ce31af49e17d50`、Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` 未变。

本次未启动真实引擎、GPU、Isaac、物理 rollout、安装或共享 native 窗口。Sol更新当前复审状态后运行文档检查：0 errors、0 stale paths，保留96条历史链接问题；日志保存在上述 Sol 输出目录。

## 保留项与下一步边界

R1 在源码／无引擎契约层有限通过；原维护 G2–G4 不因这些测试改为全部 PASS。当前源码上的代表性物理回归及独立物理 reader 仍为 NOT_RUN，阶段2旧源码成功记录保持原身份。

Marker 通用构造简化、F06 任务／runtime 职责分离、诊断和静态 SHA 后续整理，以及完整新手入口验证仍按原规划保留。`SelectedReferenceEnv` 当前仍有4011行、含多种接线分支；本次消除了旧 Env 的重复实现，但未完成使环境类只负责有机组合的整体整理目标。不得据此宣布整个重构收尾。

维护者计划后续从 develop 建立独立阶段3分支。本次实施提交可作为待选基线；本轮未建分支／worktree、未派发3a，也未修改3a–3c的 PLANNED 状态。后续工作包应固定实际提交与接口边界，并单列必要物理验证，避免把旧证据用于新源码验收。
