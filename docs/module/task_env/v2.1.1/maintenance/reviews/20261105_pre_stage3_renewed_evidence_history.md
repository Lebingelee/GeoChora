# 阶段3前维护：续作逐次证据历史快照

本页保留截至 `0b3e2a53` 的逐次记录及旧状态表；历史语句不代表当前状态。当前门状态见[当前证据与待复审项](20261105_pre_stage3_current_status.md)。

**续作预算更新（2026-11-05 10:42 CST）**：维护者授权新的离线测试累计墙时上限为 3000 秒，新的计数从此次续作开始为 0；此前可见记录的 1464.456 秒保留为历史证据，不计入新预算。原单命令 180 秒及其他资源限制未被此授权改变。续作从 `52618fad4b0882d375385bb78a61edbb5cf56ae7` 开始，以下涉及等待预算的文字保留为当时的交接记录，不再表示当前阻塞。新测试须单独记录实际墙时、源码身份及结果。

**续作诊断修复**：R02c／R06b 的 hook 和 R04b／R04c 的合成测试指向实际 environment owner，避免写到兼容导出模块而无法拦截调用。R06b 合成测试适配当前 materialization 参数；仅该合成 fixture 模拟干净工作树，真实 worker 的冻结校验未放宽。禁止原生导入的 R06b 双 episode 与六种故障路径为 7 passed（59.15 秒），不构成物理验证。前六次尝试中的失败保留在 ignored `workspace/maintenance/v211_pre_stage3_continue_marker_20261105/renewed-diagnostic-owner-001` 至 `007`；其中相机合成测试因禁止导入 `scene` 而未完成，不能将其记作通过。七次墙时合计 73.19 秒／新预算 3000 秒；本次使用 timeout 和外部 time，未采集进程树峰值 RSS，不能证明 RSS 门限。21 份生成的 source closure 逐文件 SHA 核对后保留两个唯一闭包、删除 19 份副本；清单在 `renewed-diagnostic-owner-source-copy-ledger.json`。后续测试应继续使用资源采样监督器。

**续作关闭职责**：selected、mixed 和 Position 的 session／runtime owner 关闭顺序、第一故障及后续异常说明统一交 `runtime.sessions.api`；环境仍负责路线特定收尾及回执发布。工作树上无引擎检查 146 passed（8.025 秒，峰值采样约 283 MiB）；mixed／leaf 假 provider 7 passed（5.222 秒，峰值采样约 242 MiB）。另一次 mixed 尝试因缺少合成 MJCF 环境变量有 2 项失败、5 项通过（4.698 秒），补齐原路径后重跑通过。三次均使用进程树采样监督器并确认进程组退出；详见 ignored `renewed-session-close-001` 至 `003`。上述本轮新离线预算累计 91.135 秒，测试身份为提交前工作树；提交后仍需核对干净 HEAD。

源码提交 `13a8d3c9` 后干净 tracked HEAD 上重跑无引擎检查：146 passed（8.003 秒，进程树峰值采样约 289 MiB，进程组已退出）；完整命令和资源记录保存在 ignored `renewed-session-close-clean-13a8d3c9`。新离线预算累计 99.138／3000 秒。mixed／leaf 检查仍是提交前工作树证据；本页更新未改变生产源码。

随后补充 mixed 关闭回执读取失败的故障处理：无论 session 关闭是否已失败，均继续关闭 runtime owner 并清理 source／task 资源，保留第一异常及其后的回执错误。工作树无引擎回归 148 passed，监督墙时 7.985 秒、进程树峰值采样约 283 MiB、进程组已退出；详见 ignored `renewed-close-receipt-001`。新离线预算累计 107.123／3000 秒；该证据标识提交前工作树。

外部 Solution 动作的发布边界、Solution 身份及控制请求准入收敛到 `planners.contracts`；环境仍决定实际执行路线。保留 Position 的 typed state 边界校验及既有拒绝顺序；补充不匹配时零推进检查。工作树上的 PickCube／Nut、Position 投影及 native feedback 无引擎组合为 182 passed、2 deselected；最终一次监督墙时 13.297 秒、峰值采样约 288 MiB、进程组已退出。两次运行共 26.584 秒，原始记录见 ignored `renewed-action-admission-001`、`002`；新离线预算累计 133.707／3000 秒，提交后仍需固定源码身份。此检查未运行 Isaac 或物理 rollout。

源码提交 `1b89bc06` 后干净 tracked HEAD 重跑同组：182 passed、2 deselected，监督墙时 13.325 秒，进程树峰值采样约 291 MiB，进程组已退出；原始记录在 ignored `renewed-action-admission-clean-1b89bc06`。新离线预算累计 147.032／3000 秒。

reset 重建后的执行路线、配置和种子一致性检查转入已有 `reference_binding`，环境保留实际 reset 编排。工作树的无引擎检查 204 passed、2 deselected（13.236 秒），mixed／leaf 合成检查 8 passed（5.860 秒）；两次均有进程树资源采样并确认进程组退出，原始记录在 ignored `renewed-reset-execution-001`、`002`。包含路线／种子篡改及不关闭现有 session 的拒绝检查，不构成真实物理结果。新离线预算累计 166.128／3000 秒；提交后需核对源码身份。

源码提交 `36e975dc` 后干净 tracked HEAD 重跑无引擎检查：204 passed、2 deselected，监督墙时 13.260 秒，进程树峰值采样约 292 MiB，进程组已退出；原始记录在 ignored `renewed-reset-execution-clean-36e975dc`。新离线预算累计 179.388／3000 秒。

Position materialization 的控制计划、source joint／frame 映射及 task 声明的 ControlBinding 准备归 runtime control owner；Env 仍拥有 session 的实际发布和失败清理。工作树无引擎组合 205 passed、2 deselected（18.304 秒），mixed／leaf 合成检查 8 passed（6.920 秒），均有资源采样和进程组退出记录。扩大到旧 Position 测试文件的尝试为 204 passed、9 failed、2 deselected（14.994 秒）：7 项被禁止的 `scene` 导入阻断，2 项旧测试替身与当前 session／Env 接口不符；不得把该组记为通过。原始证据在 ignored `renewed-position-binding-001` 至 `003`。新离线预算累计 219.606／3000 秒；提交后仍需核对源码身份。

源码提交 `6872928e` 后干净 tracked HEAD 重跑无引擎组合：205 passed、2 deselected，监督墙时 14.945 秒、进程树峰值采样约 277 MiB，进程组已退出；原始记录在 ignored `renewed-position-binding-clean-6872928e`。新离线预算累计 234.551／3000 秒。

后续修复旧 Position 文件的三个过期合成替身，保留原力反馈和 fault 断言：其中两项无引擎 2 passed（0.833 秒）；该文件在双锁、禁 Isaac／CUDA 的 GeoPhys CPU 源构造与合成控制条件下完整重跑 9 passed（3.428 秒）。首次双锁运行 8 passed、1 failed（3.713 秒），失败的旧 Env 替身修复后重跑；两个 worker 均退出并释放两把锁。该验证不是物理 rollout。14 个生成的 Panda 资产副本逐文件 SHA 核对后保留 1 份，其他 13 份删除，证据见 ignored `renewed-position-cpu-source-copy-ledger.json`。新离线累计 235.384／3000 秒；两次双锁 CPU 墙时合计 7.141 秒单独计入 native 预算。此段对应提交前工作树。

测试修复提交 `27bc9187` 后，干净 tracked HEAD 上同一双锁 CPU 源构造／合成控制文件重跑 9 passed（3.702 秒，进程树峰值采样约 106 MiB，进程组及双锁均释放）；新增 7 份 Panda 快照与已保留副本逐文件 SHA 一致并删除，证据在 ignored `renewed-position-cpu-source-clean-copy-ledger.json`。本续作三次双锁 CPU 墙时累计 10.843 秒，仍不表示真实物理 rollout。

mixed／Position 的 v3 录制文件路径、覆盖拒绝、recorder 创建和成功开始后的发布归 recorder owner；环境仍保持 episode 准入、任务 metadata、Stop 与 fault 次序。工作树无引擎组合 264 passed、4 deselected（13.720 秒），另有 mixed／leaf 合成检查 4 passed（5.210 秒），覆盖开始失败重试、已有文件保护、metadata 失败不发布、追加／最终化故障及记录绑定。首次组合遗漏两个已知原生排除项而被引擎防护拦截，263 passed、2 failed、2 deselected（15.572 秒）；补排后 263 passed、4 deselected（14.055 秒），再加入 Position 新断言得到上述 264 项。记录在 ignored `renewed-record-begin-001` 至 `004`；均为提交前工作树，含资源采样且进程组退出。新离线预算累计 283.941／3000 秒。

源码提交 `a406ad82` 后干净 tracked HEAD 重跑无引擎组合：264 passed、4 deselected，监督墙时 14.002 秒、峰值采样约 286 MiB，进程组已退出；原始记录在 ignored `renewed-record-begin-clean-a406ad82`。新离线预算累计 297.943／3000 秒。

mixed interval 的结构化 transition、target／applied 投影及 stepwise 记录格式归 recorder；环境保留推进、校验时机和最终发布。工作树假 provider／无引擎检查 5 passed（3.044 秒），包括官方冻结输入上的 LIBERO V8 外部 Solution、25 substeps、H5 记录、部分故障和 recorder 故障；不是物理 rollout。首次用旧场景运行时官方来源校验正确拒绝，4 passed、1 failed（1.912 秒），替换为已冻结官方输入后通过。原始日志与输入路径在 ignored `renewed-mixed-projection-001`、`002`；进程组均退出，有资源采样。新离线预算累计 302.899／3000 秒；提交后需固定源码身份。

源码提交 `72b7c42f` 后干净 tracked HEAD 重跑同一假 provider 组合：5 passed，监督墙时 2.461 秒、进程树峰值采样约 326 MiB，进程组已退出；原始记录在 ignored `renewed-mixed-projection-clean-72b7c42f`。新离线预算累计 305.360／3000 秒。

修复 selected 构造完成 task value 后、Env 发布前的回收缺口：控制器、action／observation space 或元数据初始化失败时，依次尝试关闭来源快照和 task 资源，保留首个构造异常、附加清理错误及 `selected_construction` fault。已有 scalar binding 拒绝复用同一回收路径。工作树无引擎组合 268 passed、4 deselected（14.279 秒）；假 provider／LIBERO V8 合成组合 5 passed（3.160 秒）；早期定向故障检查 3 passed（1.116 秒）。均有进程树采样且进程组退出；原始记录在 ignored `renewed-construction-cleanup-001` 至 `003`。新离线预算累计 323.915／3000 秒；此为提交前工作树证据，不代表物理验证。

源码提交 `779f1977` 后干净 tracked HEAD 重跑无引擎组合：268 passed、4 deselected，监督墙时 15.401 秒，进程树峰值采样约 293 MiB，进程组已退出；原始记录在 ignored `renewed-construction-cleanup-clean-779f1977`。新离线预算累计 339.316／3000 秒。

selected／Position／leaf／mixed 控制器分类、writer 唯一性及来源计划准入归 runtime control owner，Env 仅装配校验结果；保留现有 Panda 类型与 leaf 编译约束，未扩展 provider 支持。工作树无引擎组合 269 passed、4 deselected（14.629 秒），mixed／leaf 假 provider 6 passed（5.510 秒）；含重复 writer／Entity、错误来源、无效 leaf、25 合成 substeps 和 failure 检查。两次均采样进程树、进程组退出；详见 ignored `renewed-controller-admission-001`、`002`。新离线预算累计 359.455／3000 秒；提交后需固定源码身份，不构成物理验证。

源码提交 `c768a5e7` 后干净 tracked HEAD 重跑无引擎组合：269 passed、4 deselected，监督墙时 14.231 秒，进程树峰值采样约 294 MiB，进程组已退出；原始记录在 ignored `renewed-controller-admission-clean-c768a5e7`。新离线预算累计 373.686／3000 秒。

Position 回归的 7 次相同 Panda 源快照构建收敛为模块级 1 份共享副本；来源仍通过原 68 文件、固定 revision 和 closure SHA 检查，测试前后再核对一次 closure，模块退出时清理该副本。工作树双锁 CPU 源导入／合成控制检查两次均为 9 passed，监督墙时分别 1.384、1.371 秒；最终一次监督输出峰值约 32.7 MiB，退出后无残留 Panda 快照，进程组和双锁均释放。原日志在 ignored `renewed-position-reuse-001`、`002`。本续作双锁 CPU 墙时累计 13.598 秒；此验证未运行 Isaac／GPU 或物理 rollout，提交后需固定源码身份。

测试提交 `bccf4f43` 后干净 tracked HEAD 重跑：9 passed，监督墙时 1.361 秒、输出峰值约 32.7 MiB，退出后源快照数为零，进程组和两把锁均释放；记录在 ignored `renewed-position-reuse-clean-bccf4f43`。本续作双锁 CPU 墙时累计 14.959 秒。

通用 Env 不再直接读取 PickCube F06 字段判断旧 Position expert 兼容路线：准入由 PickCube 任务 binding 显式声明，其他 binding 默认不开放。`step_expert()` 仍只是受限兼容，调用方的 `act → step(action) → observe` 路线不变。工作树无引擎组合 270 passed、4 deselected（15.094 秒）；定向检查 16 passed、1 deselected（0.819 秒）。首次定向测试遗漏一个既有 scene 原生排除项，被防护阻断为 16 passed、1 failed（0.820 秒），日志保留。三次均采样资源并确认进程组退出；记录在 ignored `renewed-f06-binding-001` 至 `003`。新离线预算累计 390.419／3000 秒；此为提交前工作树证据，不证明 Isaac 物理。

源码提交 `59fba768` 后干净 tracked HEAD 重跑无引擎组合：270 passed、4 deselected，监督墙时 14.243 秒、进程树峰值采样约 294 MiB，进程组已退出；记录在 ignored `renewed-f06-binding-clean-59fba768`。新离线预算累计 404.662／3000 秒。

当前源码 `5a04140a` 的 PickCube／Nut MuJoCo CPU 代表运行与同次独立 reader 均通过；分别 960／2377 transitions，详见[验证记录](20261105_pre_stage3_resumed_physical_checks.md)。累计保守物理步预留 257107／300000；未运行 Isaac／GPU，R05b 无 Solution 物化与整体职责整理仍未完成。

复核发现 R05b 原生反馈物化仍直接依赖 Nut Solution 精确类型与固定身份，独立无 Solution 物化尚未实现；这与普通调用方 `act → step(action) → observe` 已解耦的事实应分开描述。新增缺失 Solution 与复制同字段的子类均在 native 物化前拒绝的检查，保留冻结 profile 的现有准入强度；无引擎 R05b 组合 20 passed、1 deselected（6.289 秒），含资源采样且进程组退出，记录在 ignored `renewed-r05b-solution-boundary-001`。新离线预算累计 410.951／3000 秒。此为提交前工作树证据，不代表该耦合已消除或真实物理已验证。

检查提交 `32162885` 后干净 tracked HEAD 重跑 R05b 组合：20 passed、1 deselected，监督墙时 6.331 秒，进程树峰值采样约 196 MiB，进程组退出；记录在 ignored `renewed-r05b-solution-boundary-clean-32162885`。新离线预算累计 417.282／3000 秒。

2026-11-05；源码检查点 `2afe9d88`，本页只补充交接状态。维护 goal 仍在进行；本页不是 Sol 接收决定或阶段3启动授权。运行身份、失败与原始输出位置以[恢复后的验证记录](20261105_pre_stage3_resumed_physical_checks.md)为准。

后续检查点：`27af77bf` 为文档／skill／账本更新后的源码状态，较 `f06ee2f5` 无生产代码变更。原 pytest 总墙时超限及追加预算问题仍待维护者决定；先释放本次 writer，准备部分结果供维护者按原手动流程转交 Sol。恢复实施时重新固定 HEAD、资源与锁状态，不把此交接当作整项维护完成。

| 门 | 当前状态 | 证据与剩余边界 |
| --- | --- | --- |
| G0 输入与资源 | **PARTIAL** | 两份保护 untracked 的 SHA 和 GeoPhys／Menagerie pin 与原记录一致。维护者将物理步总限额调整为 300000，并以两目录现存占用检查 2 GiB；当前约 1.03 GiB。两目录中可见的 121 条 pytest supervisor 记录累计约 1464 秒，超过原 1200 秒离线墙时上限；已请求调整并暂停新增离线测试。逐项路径、PID、时间和分类保存在 ignored `workspace/maintenance/v211_pre_stage3_continue_marker_20261105/visible-supervisor-budget-ledger-20261105.json`；该数字不是完整历史命令账本。 |
| G1 代码职责 | **PARTIAL，待复审** | 三个旧任务使用统一 scalar Env，四个 BaseTaskEnv 出口为同对象别名；PickCube／Nut 各保留四个业务文件与薄 `__init__.py`。公共 factory 为 `make_env(uid, *, config=None, render_mode=None, **kwargs)`；调用方 Solution 路线为 `act → step(action) → observe`，`step_expert()` 仅为受限兼容。F05 source-bound 准入类型归 runtime，任务 builder 保留兼容导出；reset 输入校验归现有 binding，录制来源／持久化归 recorder。`SelectedReferenceEnv` 仍有 3574 行及多种接线分支，不能宣布整体减责完成。 |
| G2 功能与身份 | **PARTIAL** | `f06ee2f5` 上 PickCube／Nut MuJoCo CPU 代表回归及独立 reader 均通过；`8b3c8d93` 上 Empty／Pendulum／TwoWheel GeoPhys CPU 各一个 reset／step／close 通过。`f06ee2f5` 干净无引擎组合 335 passed、1 skipped、5 deselected，mixed 假 provider 9 passed；`0c224302` 上 Nut Solution 35 项无引擎语义测试分批全通过。每项只属于所记源码／路线；DG04 为冻结来源加最低 I/O 合成测试，不是 Isaac 物理。 |
| G3 文档与启动 | **PARTIAL** | [安装与启动指南](../../guides/installation-and-start.md)、[任务开发指南](../../../../../../task_env/doc/自定义任务构建指南.md)及[Solution 接口](../../../../../../task_env/doc/api/planning/task_owned_solutions.md)提供当前入口；显式路径启动器 Pendulum CPU 已执行。完整新克隆安装和全部适用入口未验证，不能据此宣称完整新手流程验收。 |
| G4 证据与清理 | **PARTIAL** | 同次 H5、独立 reader、原始输出、资源／锁收据及失败均保留，已确认复制的 F04 测试副本删除并保留可重建证据。旧 FULL 诊断依赖已退役任务实现，入口现明确拒绝；其余历史诊断引用尚未逐项迁移。未启动 Isaac／GPU 或将旧证据重标。 |
| G5 交付 | **PARTIAL** | 本地提交和逐项记录已保存；须在停止写入后固定实际 HEAD、更新窗口状态并交 Sol 独立复审。不得预填 Sol 决定或更改阶段3的 PLANNED 状态。 |

## 后续最小工作

1. 对照[职责／文档处置清单](20261105_pre_stage3_owner_and_document_map.md)、[环境类剩余职责](20261105_reference_env_remaining_owners.md)和[规划](../../planning/pre-stage3-environment-refactor.md)，继续处理环境类内剩余路线接线、旧诊断与新手入口的实际缺口；不以行数、改名或单纯移动代码代替职责判断。
2. 按维护者对离线墙时预算的决定安排必要验证；若继续修改生产源码，对受影响路线重新固定源码身份及运行预算，不将既有 H5 重标。
3. 最终执行文档 validator、保护项和 gitlink 核对，完成报告及本地提交；确认本次 worker／进程组退出并释放两把锁，再交 Sol 独立复审。

2026-11-05 静态检查：活跃非测试、非 diagnostics 的 Python 中未发现 `make_marker_env`、`DeclaredPandaBoxEnv`、三个旧 task 支持模块或旧 PickCube `isaac` 模块引用；`git diff --check 48401525..2afe9d88` 通过。该扫描不覆盖历史文档和诊断，不代替运行验证。
