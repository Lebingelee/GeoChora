# 阶段3前维护 attempt002：30分钟生命周期返工

状态：`REPORTED_PENDING_REVIEW`。输入 `develop@7a5943a7b50c0ae13ffae52fffd88262870c5aa9`；本窗口按维护者决定只优先处理 R1，未启动阶段3。此记录是执行结果，不是 Sol 验收。

本次把 scalar episode 的 closed、stopped、fault、episode identity 和 end receipt 收到 `task_env/environment/lifecycle.py::EpisodeExecutionState`。classic `BaseTaskEnv` 与实际创建的 `SingleTaskLifecycleAdapter` 共用同一状态实例；selected Env 使用同一状态类型，两个独立 Env 实例各有自己的状态。reset 开始和完成、step 结束、fault、Stop 的状态、closed/fault 准入由共同状态实现；实际 runtime 调用、任务评价、状态发布和 finalizer 仍由各路线既有实现负责。Position 与 mixed 互斥路线的 end receipt 落在各自 episode 的同一状态字段中，旧内部访问名仍可用。

classic close 保留 RuntimeBoundary 的单一关闭者，并在 lifecycle 已先关闭时仍恰好一次释放 Env 自有 UI／sensor。PickCube、Nut 和 Marker 的源码身份增加新引入的 lifecycle 源码，旧证据不重标。

| 项目 | 结果 | 依据及限制 |
| --- | --- | --- |
| RW0 | PARTIAL | 输入 HEAD、包 manifest／snapshot、两个保护文件及两个 pin 匹配；本窗口无 native／GPU／引擎 import 和共享锁申请。早期 pytest 使用系统临时目录并自动轮转，无法重建所有临时输出的累计字节。 |
| RW1 | FAIL | episode 部分状态和准入已共用，但 `BaseTaskEnv` 仍是独立类，Empty／Pendulum／TwoWheel 仍继承它；selected 与 classic 的完整 reset／step／fault／Stop／close 流程未合并，BaseTaskEnv 同对象别名和旧实现删除未完成。 |
| RW2 | PARTIAL | 最终有界合成检查 146 passed、4 deselected：三个旧任务经真实 public `make_env`、假 RuntimeBoundary 的 reset／两步／horizon／故障／reset／stop／close、纯组装和假 render 路由得到检查；selected 合成检查及 Position/mixed Stop 检查通过。原生、真实渲染与物理 reader 按预算 NOT_RUN；尚无 R1 完整合并的验证。 |
| RW3 | PASS | 必要的当前状态、有限检查、报告和本地提交按本窗口记录；该结果不构成 R1 或整体维护完成。 |

与 R1 直接相关的首次失败保留在 ignored 工作输出：`construct_first` 的辅助 close 假对象缺少 `episode_end`，随后 close 读取改为安全获取并复测通过；`mixed_candidate` 三项被禁止引擎 import 的 tripwire 在 MuJoCo `find_spec` 处拦截；随后以只读取已安装文件位置、禁止执行 native 模块的隔离器运行原有标记假 provider fixture，3 项通过。这些均为合成检查，不是 native 证据。真实 Pendulum 与依赖真实 Scene 的 Position close 测试明确排除。

R2 Marker 构造／SHA 简化、R3 F06 任务规则归位、完整物理回归／独立物理 reader 和新安装验证按包延期。本次 Marker 来源字段更新仅用于记录 R1 新引入的真实 lifecycle 依赖，不表示 R2 已完成。

续作须把三个 classic 任务的声明／组装、reset、action／observation 接入规范 `SelectedReferenceEnv` 的共同 episode 执行流程，统一 task/runtime 的 boundary publication、step／fault／Stop／close 决策，保留各任务 shape、seed、reward、horizon、render 和纯组装；然后删除旧 `BaseTaskEnv` 独立实现并令所有既有导出直接指向同一类对象。不能将现有共享状态包装成两个状态机通过，也不能把 fake runtime 合成结果当作物理验证。完整工作报告和逐命令 supervisor 在 `workspace/maintenance/v211_pre_stage3_refactor_attempt002/`。
