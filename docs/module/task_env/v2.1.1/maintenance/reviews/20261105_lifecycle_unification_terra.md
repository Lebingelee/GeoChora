# 2026-11-05 生命周期统一续作：Terra 交付

状态：`REPORTED_PENDING_REVIEW`，供 Sol 审查当前提交及其证据；本记录不是 Sol 验收，也不授权阶段3。输入为 `develop@149bea2603fad91200ce7b16280a1f38423aece1`，保留 attempt001/attempt002 原始包与报告。维护者为 Empty、Pendulum、TwoWheel 单环境续作提供更长时间；原 attempt002 的30分钟限制和结果属于历史窗口。

## 实现与范围

- `SelectedReferenceEnv` 是唯一单环境类实现；`environment.env.BaseTaskEnv`、`tasks.base.BaseTaskEnv`、`task_env.tasks.BaseTaskEnv` 和 `task_env.BaseTaskEnv` 为同一类对象。三个任务仍声明自己的场景、初态采样、动作／观测与评价，不再继承独立旧 Env。
- `EpisodeExecutionState` 协调 reset 阶段、控制 interval、Stop 和关闭；组件任务与 selected／Position／leaf／mixed 任务在同一个 owner 上提供各自阶段操作。旧 `SingleTaskLifecycleAdapter` 保留为组件 RuntimeBoundary 的状态投影、任务评价和格式适配，不持有第二个 Env；组件和 selected 可使用不同物理 runtime 类型。
- Panda 的 robot／frame／controller 绑定移至 `PandaAgent`；selected 任务绑定可以提供 action schema、空间和 action 到 `RequestedAction` 的转换。组件任务、mixed 和空物体位姿投影不强制 Panda 的 action／observation 维数。既有 Position、相机和物理能力准入限制仍按各自有界路线执行。
- 外部 Solution 路线保留 `act → env.step(action) → observe`；Nut 的来源、控制请求和 target／applied 边界仍受检查。历史 `step_expert()`／`step_with_solution()` 仅为受限兼容，不作为新标准 API；旧示例和记录的迁移不被本项虚报为完成。
- 更新当前 API、任务指南、恢复页与 TaskEnv Skill。未重写历史结果、未修改任务 reward／reset 分布、控制数学、submodule pin 或来源 manifest。

## 证据与限制

最终检查为离线组 **171 passed、3 deselected**，synthetic 组 **12 passed**；当前文档校验 **0 errors、0 stale paths、96 个历史链接问题**。逐命令 argv、退出码、耗时和完整 stdout/stderr 保存在忽略目录 `workspace/maintenance/v211_lifecycle_unification_continuation/final-checks.json` 及同目录日志。离线组覆盖公共工厂、四个同对象导出、三个任务的假 RuntimeBoundary reset／两个 step／horizon／seed／fault／恢复／Stop／close、纯组装、假 render、PickCube/Nut 外部 Solution 与 target/applied 反馈、Panda 绑定、自定义动作、Pendulum 与 TwoWheel 任务语义以及来源身份。synthetic 组覆盖 selected leaf／mixed 假 provider、观察和记录故障及 H5 记录回读；它不是物理成功证据。

未运行真实 MuJoCo／GeoPhys／Isaac、GPU、物理 rollout、真实 render、完整独立物理 reader、新安装、并行训练或后端矩阵；没有申请共享 native 锁，不干扰其他用户正在运行的 Isaac Sim。部分历史测试需要显式 `R07C_COMPOSED_MJCF` 输入，本次没有该输入，使用不依赖它的合成正负例；历史结果不重标。单环境假 runtime 与离线检查不能证明任何 provider 的数值等价或 Qualification。

`MUJOCO_LOG.TXT` 保持 untracked、SHA-256 `dfb37ada202855d609f9e210cf79b287de78f2ded70e704ceeb544d17bf7ad4b`；`docs/maintenance/20261030_runtime_route_diagnostic_handoff.md` 保持 untracked、SHA-256 `18cc56c7f0ffbcb947db4bd8725279489171efbee8f08b28603b79c47f509d61`。GeoPhys `67da1165149486d3ae3e779c13ce31af49e17d50`、Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` 保持不变。

Marker 通用构造及 F06 任务／runtime 归位为原复审中的后续项，不以本次生命周期续作宣称完成。最终物理回归及独立 reader 应在相关源码稳定、合法取得资源窗口后由后续工作单独安排。保留既有阶段2的有界决定。
