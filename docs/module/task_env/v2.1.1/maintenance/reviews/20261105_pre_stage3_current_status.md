# 阶段3前维护：当前证据与待复审项

**续作预算更新（2026-11-05 10:42 CST）**：维护者授权新的离线测试累计墙时上限为 3000 秒，新的计数从此次续作开始为 0；此前可见记录的 1464.456 秒保留为历史证据，不计入新预算。原单命令 180 秒及其他资源限制未被此授权改变。续作从 `52618fad4b0882d375385bb78a61edbb5cf56ae7` 开始，以下涉及等待预算的文字保留为当时的交接记录，不再表示当前阻塞。新测试须单独记录实际墙时、源码身份及结果。

**续作诊断修复**：R02c／R06b 的 hook 和 R04b／R04c 的合成测试指向实际 environment owner，避免写到兼容导出模块而无法拦截调用。R06b 合成测试适配当前 materialization 参数；仅该合成 fixture 模拟干净工作树，真实 worker 的冻结校验未放宽。禁止原生导入的 R06b 双 episode 与六种故障路径为 7 passed（59.15 秒），不构成物理验证。前六次尝试中的失败保留在 ignored `workspace/maintenance/v211_pre_stage3_continue_marker_20261105/renewed-diagnostic-owner-001` 至 `007`；其中相机合成测试因禁止导入 `scene` 而未完成，不能将其记作通过。七次墙时合计 73.19 秒／新预算 3000 秒；本次使用 timeout 和外部 time，未采集进程树峰值 RSS，不能证明 RSS 门限。21 份生成的 source closure 逐文件 SHA 核对后保留两个唯一闭包、删除 19 份副本；清单在 `renewed-diagnostic-owner-source-copy-ledger.json`。后续测试应继续使用资源采样监督器。

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
