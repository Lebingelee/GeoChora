# U6/U7 目录处置准备（2026-11-13）

本表是审阅清单，不是删除收据。分配字节为 `du -s -B1` 当时快照；共享硬链接、后续写入和文件系统开销会使实际回收量不同。所有操作前重查身份、owner、打开文件、锁、引用与授权。

| 路径（均位于 `/home/lly/Program_Files/Geochora/workspace/maintenance/`） | 当前决定 | 快照分配字节 | 保全与约束 |
|---|---|---:|---|
| `v211_e11_e16_u5_20261113_001/` | 保留 | 1,161,216,000 | 五入口、优化入口、最终选择与 reader；其临时子目录单列，不以整个目录为删除对象。 |
| `v211_e11_e16_u7_preparation_20261113_001/` | 保留 | 57,516,032 | refs/worktree 预备和本地保全成果；U7 还须核对恢复及独有内容。 |
| `v211_e11_e16_u5_restore_probe_20261113_001/` | 临时副本，候选删除，尚未授权 | 5,912,633,344 | 本轮从已保全对象生成的恢复试验；旧恢复验证脚本依赖此路径，删除后这些历史试验不能原地复跑。最终选择与七项代表检查不依赖该目录；必要对象留在 U5 包。 |
| `v211_e11_e16_u5_20261113_001/stage04/4a-delivery/` | 临时副本，候选删除，尚未授权 | 310,669,312 | 旧 4a 布局复制，用于旧 manifest 试验；有界 4a 核查使用包内代表日志和 source 索引。旧 manifest 重算/链接迁移提议不作为保留入口。与对象硬链接可能共享块，不能将该数字当净节省。 |
| `v211_e11_e16_u5_20261113_001/3b-nut-reconstruction/runtime/` | 暂缓候选 | 16,089,088 | 历史重建运行时，必须先逐项确认不被保留 reader 或其他任务使用。 |
| `v211_e11_e16_u5_20261113_001/nut-source-reconstruction/runtime/` 和 `runtime-minimal/` | 暂缓候选 | 52,834,304 + 6,713,344 | 同上，重建报告留存；不能仅凭目录名删除。 |
| `v211_g04_4a_attempt003/` | 暂缓候选 | 310,669,312 | 历史 tracked 文档及可能的动态调用仍引用，先完成必要引用迁移与 owner 检查；旧 manifest 非保留义务。 |
| `v211_g04_4b_attempt001/` | 暂缓候选 | 2,495,217,664 | 同上；原接收的影响分析与唯一成果保全需逐项确认。 |
| `v211_g04_4c_attempt001/` | 暂缓候选 | 900,399,104 | 同上；当前锁/fixture 不得随意删。 |
| `v211_g05_5c_unit4_continuation_20261109/` | 暂缓候选 | 24,952,832 | 同上；需确认仍在使用的引用和唯一输出。 |

两份旧 H5 的当前 codec／历史 judge 测试已切换到 U5 包中对应 SHA 对象并检查 SHA；25 项受守卫离线检查通过。四份 physical 测试输入也已在包内建立相对符号链接，指定新位置运行的 8 项受守卫检查通过；测试仍允许显式指定其他输入。旧文件保持不变。Panda Isaac 资产测试现使用包内 USD manifest；按 manifest 将 68 个已保全 source 对象以硬链接排列，包含 pxr 的定向 source 构造检查 8 项通过，solver SDK 被阻止导入。该检查不是 App 或 native 物理运行。G05 简单主体两份 delivery 的 24 个必要文件也以包内硬链接布局；三种配置安装、损坏拒绝及 source 绑定共 5 项 pxr 检查通过。历史 supervisor 的共享锁仍在 `phase_ii_01_sol_luna_handoff_20261023_001/`。该目录、现行测试样本、所有锁、保护输入、第三方源码与嵌套 worktree 均不列删除。当前 checkout 锁 inode 29918777，另一个 integration checkout 锁 inode 33310300；本次 `/proc/locks` 快照均未显示持锁项，这不是未来无 owner 的保证。既往进程 fd 扫描存在权限拒绝，不能证明全部进程没有打开目录。统一锁路径前须查清全部活动运行端，避免新旧 inode 并行形成双锁，不能通过 unlink 实现切换。

四个暂缓历史目录的 [符号链接与 worktree 快照](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/u6-candidate-symlink-worktree-snapshot.json)：4a 和 4c 各 0 条符号链接；4b 有 19 条全部指向目录外，其中包含 integration checkout 的 pytest 临时路径和当前 Python 环境的第三方包；5c unit4 有 67 条，解析后均在其目录内。所查四个目录没有发现嵌套 `.git` 标记或已注册 worktree。执行任何获授权的目录操作都不得跟随符号链接，尤其不得触及其外部目标；此快照不证明 owner 或活动状态。

锁调用补查：当前 `task_env/script/agent/builtin_example_validation.py` 仅持有本 checkout 的旧锁；U3 保留的监督器和计划按 integration 锁、主 checkout 锁的顺序分别获取两把。当前 checkout 和 integration checkout 各有多份历史 supervisor 固定引用各自旧锁；版本化的三个 probe 接收计划提供的 `locks_in_order`。因此现在只切换示例验证器或只更换其中一个 inode，会与仍运行旧代码的执行端失去共同互斥。2026-11-13 14:01 UTC 的 [锁与测试输入快照](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/u6-current-fixture-lock-verification.json)未看到这两把锁被持有；进程名检查未找到所查 supervisor／native 进程，Codex 列表中有关项目其他可见会话为 idle 或 notLoaded。这些是瞬时观察，不排除其他运行端、权限不可见进程或后续启动。保留两把锁及原计划；最终迁移前须先确定所有实际运行端并制定共用锁与过渡顺序，禁止 unlink 现有锁。

本轮测试后复核 G05 24 个文件和 Panda delivery 82 个文件，内容 SHA 均属于 U5 保留选择；这只是文件字节核验。

恢复：选择中的原始文件通过 `retained-claim-selection.json` 的 `original` → `retained` 和 SHA/长度从 U5 对象复制到新的空目标并校验；source 另由列出的索引定位。此方法不保证恢复被舍弃的完整旧目录或旧 manifest。临时试验目录可用已保留输入重新进行范围内的验证，但不承诺重建其全部历史输出。

当前测试样本的独立恢复：从保留对象和索引使用 `workspace/maintenance/v211_e11_e16_u5_20261113_001/materialize_current_test_fixtures.py` 向新空目录复制并校验 112 个文件；在恢复副本上，三份 USD delivery 经 OpenUSD 读取通过、两份 leaf H5 分别经当前 codec 与历史 judge 读取通过、四份 physical H5 的受守卫检查 8 项通过。该复核不依赖原历史目录，也不证明每个历史 reader 或物理运行。测试副本 `/tmp/geochora-u6-fixture-recovery-20261113-001/` 快照占用 46,522,368 分配字节，是本轮临时产物，保留为后续清理候选，本次未删除。

U7 的 refs/worktree 均暂保留，包含被显式锁定的历史 v1.0 worktree；未获具体授权，不进行删除或 Git prune。先前 fsck 的不可达对象缺口已登记，不继续扩大全库历史追查。清理后净空间、refs/worktree 前后以及维护者项目接收仍 OPEN。
