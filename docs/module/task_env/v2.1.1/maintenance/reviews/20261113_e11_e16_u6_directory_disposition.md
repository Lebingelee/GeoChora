# U6/U7 目录处置准备（2026-11-13）

本表是审阅清单，不是删除收据。分配字节为 `du -s -B1` 当时快照；共享硬链接、后续写入和文件系统开销会使实际回收量不同。所有操作前重查身份、owner、打开文件、锁、引用与授权。

| 路径（均位于 `/home/lly/Program_Files/Geochora/workspace/maintenance/`） | 当前决定 | 快照分配字节 | 保全与约束 |
|---|---|---:|---|
| `v211_e11_e16_u5_20261113_001/` | 保留 | 1,161,216,000 | 五入口、优化入口、最终选择与 reader；其临时子目录单列，不以整个目录为删除对象。 |
| `v211_e11_e16_u7_preparation_20261113_001/` | 保留 | 57,516,032 | refs/worktree 预备和本地保全成果；U7 还须核对恢复及独有内容。 |
| `v211_e11_e16_u5_restore_probe_20261113_001/` | 临时副本，已授权并删除 | 5,912,633,344 | 本轮从已保全对象生成的恢复试验；旧恢复验证脚本依赖此路径，删除后这些历史试验不能原地复跑。最终选择与七项代表检查不依赖该目录；必要对象留在 U5 包。 |
| `v211_e11_e16_u5_20261113_001/stage04/4a-delivery/` | 临时副本，已授权并删除 | 310,669,312 | 旧 4a 布局复制，用于旧 manifest 试验；有界 4a 核查使用包内代表日志和 source 索引。旧 manifest 重算/链接迁移提议不作为保留入口。与对象硬链接可能共享块，不能将该数字当净节省。 |
| `v211_e11_e16_u5_20261113_001/3b-nut-reconstruction/runtime/` | 临时副本，已授权并删除 | 16,089,088 | 先前 Nut XML 重建运行时，最终入口保留结果和 source receipt；含一条指向下列运行时资产的链接，删除时不得跟随。 |
| `v211_e11_e16_u5_20261113_001/nut-source-reconstruction/runtime/` 和 `runtime-minimal/` | 临时副本，已授权并删除 | 单独测量分别 52,834,304 / 41,164,800 | 先前 XML 重建运行时，保留重建报告与 source receipt；旧重建脚本在这些运行时删除后不能原地重跑，不要求重建旧 manifest。两目录含共享硬链接，不能将各自 `du` 相加当净回收。 |
| `v211_g04_4a_attempt003/` | 暂缓候选 | 310,669,312 | 编排文件中四个当前引用已切到同 SHA 的保留对象；历史审查页仍有旧目录链接，完整旧 manifest 不再是保留义务。动态调用及 owner 仍须核对。 |
| `v211_g04_4b_attempt001/` | 暂缓候选 | 2,495,217,664 | 同上；原接收的影响分析与唯一成果保全需逐项确认。 |
| `v211_g04_4c_attempt001/` | 暂缓候选 | 900,399,104 | 同上；当前锁/fixture 不得随意删。 |
| `v211_g05_5c_unit4_continuation_20261109/` | 暂缓候选 | 24,952,832 | 同上；需确认仍在使用的引用和唯一输出。 |

另一个本轮临时恢复副本 `/tmp/geochora-u6-fixture-recovery-20261113-001/`（单独 `du` 46,522,368 字节）已按维护者的后续具体授权删除；其当前测试输入已在最终包保全，并能由包内 materializer 在新目录重新复制。其验证结果已记录，删除不会删除保留包。该路径不在上次两项目录授权范围内，本次获得单独授权。

以上四个临时路径的[活动与类型快照](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/u6-temporary-runtime-candidate-check.json)未发现挂载跨越、嵌套 Git 或可见进程 cwd/fd 使用；检查存在 427 次权限拒绝，不能排除不可见或未来活动。唯一符号链接从 `3b-nut-reconstruction/runtime/asset` 指向另一个候选目录；不得跟随。先前七项代表复核的文件访问跟踪没有访问这三个运行时，最终入口引用的是保留报告和 source receipt，不依赖临时运行时。核查不保证所有历史重建脚本仍可运行。本次已按具体授权删除，执行前重查 inode、活动状态、保留对象和挂载；不可将单项目录数字相加作为净节省。

维护者对上述四项临时副本另行明确答复“同意删除”后执行；[四项清理收据](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/u6-approved-four-temporary-cleanup-receipt.json)记录范围、inode 和保护 SHA/pins。包目录 `du` 从 850,927,616 降至 812,814,336 字节，差 38,113,280 字节；单独 `/tmp` 副本删除前为 46,522,368 分配字节。外部硬链接及并发变化不在测量范围内，不能据此宣称整个项目净节省。删除后七项代表性包内检查 PASS、历史 H5 25 项和 physical 8 项通过。预查未发现可见进程 cwd/fd 命中，有 428 次权限拒绝，不能排除不可见或后续活动。

维护者对以上两项明确答复“同意删除”后执行，其他候选未获此次授权、未删除。[清理收据](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/u6-approved-two-copies-cleanup-receipt.json)记录原 inode、范围、保护文件 SHA 和 pins。按同一次 `du` 口径，包和恢复试验合计分配字节从 7,074,217,984 降至包内 850,919,424，差 6,223,298,560 字节；这是所测两目录的差额，并非扣除所有归并新增量的项目净节省，外部硬链接和并发变化不在该测量范围内。删除后七项代表性包内检查 PASS，历史 H5 检查 25 项和 physical 检查 8 项通过。两个目录没有嵌套工作树、符号链接或跨挂载；可见 cwd/root/fd 无命中，但进程检查有 1,015 次权限拒绝，无法排除不可见或后续活动。

两份旧 H5 的当前 codec／历史 judge 测试已切换到 U5 包中对应 SHA 对象并检查 SHA；25 项受守卫离线检查通过。四份 physical 测试输入也已在包内建立相对符号链接，指定新位置运行的 8 项受守卫检查通过；测试仍允许显式指定其他输入。旧文件保持不变。Panda Isaac 资产测试现使用包内 USD manifest；按 manifest 将 68 个已保全 source 对象以硬链接排列，包含 pxr 的定向 source 构造检查 8 项通过，solver SDK 被阻止导入。该检查不是 App 或 native 物理运行。G05 简单主体两份 delivery 的 24 个必要文件也以包内硬链接布局；三种配置安装、损坏拒绝及 source 绑定共 5 项 pxr 检查通过。历史 supervisor 的共享锁仍在 `phase_ii_01_sol_luna_handoff_20261023_001/`。该目录、现行测试样本、所有锁、保护输入、第三方源码与嵌套 worktree 均不列删除。当前 checkout 锁 inode 29918777，另一个 integration checkout 锁 inode 33310300；本次 `/proc/locks` 快照均未显示持锁项，这不是未来无 owner 的保证。既往进程 fd 扫描存在权限拒绝，不能证明全部进程没有打开目录。统一锁路径前须查清全部活动运行端，避免新旧 inode 并行形成双锁，不能通过 unlink 实现切换。

针对四个历史目录的[保留检查](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/u6-stage-directory-retention-check.json)：U5 最终选择中分别有 148／1,243／229／17 条原路径映射，内容对象 SHA 和长度均匹配；只覆盖选中的有界结论，不保证其余历史文件或整包可恢复。4a 的当前 `orchestration.json` 四个 report／matrix／plan／manifest 引用已切到与原文件 SHA 相同的对象；manifest 仍是历史清单，不表示其全部旧条目将被保留。历史审查页及可能的外部调用仍可能使用旧路径。当前进程 cwd/fd 快照无可见命中，有 427 次权限拒绝，无法证明所有 owner 释放；四目录仍未授权删除。定向纯/fake 入口 240 passed；当前文档 validator 保持 1 项保护文件 `MUJOCO_LOG.TXT` 错误、79 项历史链接问题和 0 项 stale path，不称全绿。

四个暂缓历史目录的 [符号链接与 worktree 快照](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/u6-candidate-symlink-worktree-snapshot.json)：4a 和 4c 各 0 条符号链接；4b 有 19 条全部指向目录外，其中包含 integration checkout 的 pytest 临时路径和当前 Python 环境的第三方包；5c unit4 有 67 条，解析后均在其目录内。所查四个目录没有发现嵌套 `.git` 标记或已注册 worktree。执行任何获授权的目录操作都不得跟随符号链接，尤其不得触及其外部目标；此快照不证明 owner 或活动状态。

锁调用补查：当前 `task_env/script/agent/builtin_example_validation.py` 仅持有本 checkout 的旧锁；U3 保留的监督器和计划按 integration 锁、主 checkout 锁的顺序分别获取两把。当前 checkout 和 integration checkout 各有多份历史 supervisor 固定引用各自旧锁；版本化的三个 probe 接收计划提供的 `locks_in_order`。因此现在只切换示例验证器或只更换其中一个 inode，会与仍运行旧代码的执行端失去共同互斥。2026-11-13 14:01 UTC 的 [锁与测试输入快照](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/u6-current-fixture-lock-verification.json)未看到这两把锁被持有；进程名检查未找到所查 supervisor／native 进程，Codex 列表中有关项目其他可见会话为 idle 或 notLoaded。这些是瞬时观察，不排除其他运行端、权限不可见进程或后续启动。保留两把锁及原计划；最终迁移前须先确定所有实际运行端并制定共用锁与过渡顺序，禁止 unlink 现有锁。

本轮测试后复核 G05 24 个文件和 Panda delivery 82 个文件，内容 SHA 均属于 U5 保留选择；这只是文件字节核验。

恢复：选择中的原始文件通过 `retained-claim-selection.json` 的 `original` → `retained` 和 SHA/长度从 U5 对象复制到新的空目标并校验；source 另由列出的索引定位。此方法不保证恢复被舍弃的完整旧目录或旧 manifest。临时试验目录可用已保留输入重新进行范围内的验证，但不承诺重建其全部历史输出。

当前测试样本的独立恢复：从保留对象和索引使用 `workspace/maintenance/v211_e11_e16_u5_20261113_001/materialize_current_test_fixtures.py` 向新空目录复制并校验 112 个文件；在恢复副本上，三份 USD delivery 经 OpenUSD 读取通过、两份 leaf H5 分别经当前 codec 与历史 judge 读取通过、四份 physical H5 的受守卫检查 8 项通过。该复核不依赖原历史目录，也不证明每个历史 reader 或物理运行。测试副本 `/tmp/geochora-u6-fixture-recovery-20261113-001/` 快照占用 46,522,368 分配字节，是本轮临时产物，已按本次授权删除。

U7 的 refs/worktree 均暂保留，未获具体授权，不进行删除或 Git prune。以下是 U7 只读处置准备，不是移除指令；每项在实际操作前仍须核对 owner、忽略文件和其他会话使用情况。

| 对象 | 当前准备与未解决事项 |
|---|---|
| 主 checkout `/home/lly/Program_Files/Geochora` 与 `codex/v211-stage5-diagnostic` | 保留；含四份保护输入、最终证据包和当前工作。 |
| `codex/v211-stage3`、`codex/v211-stage4` | 暂缓候选；两者均为当前 HEAD 祖先，已含在 refs bundle 中，未授权删除。 |
| `codex/v211-stage5` 与 `/home/lly/.codex/worktrees/v210-integration/Geochora` | 暂缓候选；分支已被该 worktree 检出，worktree 有三份 untracked 输入、ignored 输出及旧锁，不能先删分支或以 bundle 代替本地内容。三份 untracked 的[范围内复制与恢复验证](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/integration-untracked-restore-report.json)不覆盖 ignored 内容或 owner。 |
| `/home/lly/.codex/worktrees/archive_v1_0_0` | 保留；Git 明确标记为冻结历史参考且锁定。 |
| `/home/lly/.codex/worktrees/phase-ii-01-camera/Geochora` | 暂缓候选；tracked 状态干净但有 ignored 内容，须确认实际归属和保全。 |
| `workspace/maintenance/geophys_upstream_reset_20261022_001/core-baseline` | 暂缓候选；嵌套注册 worktree，`GeoPhys` 和 `asset/external/mujoco_menagerie` 存在类型变化，不能随父目录递归删除。 |
| `workspace/maintenance/p2_0_v1_1_clean_checkout_20261017` | 暂缓候选；嵌套注册 worktree，tracked 状态干净但有 ignored 内容，须确认归属与保全。 |
| `main`、`develop`、`v1.1.0`、`v2.0.0`、`v2.1.0` 和四个现有 tags | 保留。 |

三个阶段分支的 [bundle 恢复验证](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/ref-restore-verification.json)仅覆盖 Git refs：三条 ref 在新 bare 仓库恢复并通过 fsck；本次重新计算 bundle SHA 与报告一致。它不覆盖 ignored 文件、子模块或工作树归属。先前 fsck 的不可达对象缺口已登记，不继续扩大全库历史追查。清理后净空间、refs/worktree 前后以及维护者项目接收仍 OPEN。
