# U6/U7 目录处置准备（2026-11-13）

本表汇总处置清单与已执行操作；具体执行事实见链接的删除收据。分配字节为 `du -s -B1` 当时快照；共享硬链接、后续写入和文件系统开销会使实际回收量不同。所有操作前重查身份、owner、打开文件、锁、引用与授权。

| 路径（均位于 `/home/lly/Program_Files/Geochora/workspace/maintenance/`） | 当前决定 | 快照分配字节 | 保全与约束 |
|---|---|---:|---|
| `v211_e11_e16_u5_20261113_001/` | 保留 | 1,161,216,000 | 五入口、优化入口、最终选择与 reader；其临时子目录单列，不以整个目录为删除对象。 |
| `v211_e11_e16_u7_preparation_20261113_001/` | 保留 | 本次快照 15,523,999,744；早前快照 57,516,032 | refs/worktree 预备和本地保全成果；其中 integration 临时快照单独为 15,385,866,240，不能与整个父目录 `du` 相加重复计量。 |
| `v211_e11_e16_u5_restore_probe_20261113_001/` | 临时副本，已授权并删除 | 5,912,633,344 | 本轮从已保全对象生成的恢复试验；旧恢复验证脚本依赖此路径，删除后这些历史试验不能原地复跑。最终选择与七项代表检查不依赖该目录；必要对象留在 U5 包。 |
| `v211_e11_e16_u5_20261113_001/stage04/4a-delivery/` | 临时副本，已授权并删除 | 310,669,312 | 旧 4a 布局复制，用于旧 manifest 试验；有界 4a 核查使用包内代表日志和 source 索引。旧 manifest 重算/链接迁移提议不作为保留入口。与对象硬链接可能共享块，不能将该数字当净节省。 |
| `v211_e11_e16_u5_20261113_001/3b-nut-reconstruction/runtime/` | 临时副本，已授权并删除 | 16,089,088 | 先前 Nut XML 重建运行时，最终入口保留结果和 source receipt；含一条指向下列运行时资产的链接，删除时不得跟随。 |
| `v211_e11_e16_u5_20261113_001/nut-source-reconstruction/runtime/` 和 `runtime-minimal/` | 临时副本，已授权并删除 | 单独测量分别 52,834,304 / 41,164,800 | 先前 XML 重建运行时，保留重建报告与 source receipt；旧重建脚本在这些运行时删除后不能原地重跑，不要求重建旧 manifest。两目录含共享硬链接，不能将各自 `du` 相加当净回收。 |
| `v211_g04_4a_attempt003/` | 已授权并删除 | 310,669,312 | 编排文件中四个当前引用已切到同 SHA 的保留对象；历史审查页的旧链接保留为历史记录并附有新入口；旧 manifest 的全部条目不再是保留义务。 |
| `v211_g04_4b_attempt001/` | 已授权并删除 | 2,495,217,664 | 保留最终选择及原接收范围；未选历史文件不保证恢复，外部链接目标未触及。 |
| `v211_g04_4c_attempt001/` | 已授权并删除 | 900,399,104 | 保留最终选择；未选历史文件不保证恢复，运行锁和当前 fixture 未触及。 |
| `v211_g05_5c_unit4_continuation_20261109/` | 已授权并删除 | 24,952,832 | 保留最终选择；未选历史文件不保证恢复。 |

另一个本轮临时恢复副本 `/tmp/geochora-u6-fixture-recovery-20261113-001/`（单独 `du` 46,522,368 字节）已按维护者的后续具体授权删除；其当前测试输入已在最终包保全，并能由包内 materializer 在新目录重新复制。其验证结果已记录，删除不会删除保留包。该路径不在上次两项目录授权范围内，本次获得单独授权。

以上四个临时路径的[活动与类型快照](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/u6-temporary-runtime-candidate-check.json)未发现挂载跨越、嵌套 Git 或可见进程 cwd/fd 使用；检查存在 427 次权限拒绝，不能排除不可见或未来活动。唯一符号链接从 `3b-nut-reconstruction/runtime/asset` 指向另一个候选目录；不得跟随。先前七项代表复核的文件访问跟踪没有访问这三个运行时，最终入口引用的是保留报告和 source receipt，不依赖临时运行时。核查不保证所有历史重建脚本仍可运行。本次已按具体授权删除，执行前重查 inode、活动状态、保留对象和挂载；不可将单项目录数字相加作为净节省。

维护者对上述四项临时副本另行明确答复“同意删除”后执行；[四项清理收据](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/u6-approved-four-temporary-cleanup-receipt.json)记录范围、inode 和保护 SHA/pins。包目录 `du` 从 850,927,616 降至 812,814,336 字节，差 38,113,280 字节；单独 `/tmp` 副本删除前为 46,522,368 分配字节。外部硬链接及并发变化不在测量范围内，不能据此宣称整个项目净节省。删除后七项代表性包内检查 PASS、历史 H5 25 项和 physical 8 项通过。预查未发现可见进程 cwd/fd 命中，有 428 次权限拒绝，不能排除不可见或后续活动。

维护者对以上两项明确答复“同意删除”后执行，当时其他候选未获此次授权；后续另有四项历史目录授权和执行记录。[清理收据](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/u6-approved-two-copies-cleanup-receipt.json)记录原 inode、范围、保护文件 SHA 和 pins。按同一次 `du` 口径，包和恢复试验合计分配字节从 7,074,217,984 降至包内 850,919,424，差 6,223,298,560 字节；这是所测两目录的差额，并非扣除所有归并新增量的项目净节省，外部硬链接和并发变化不在该测量范围内。删除后七项代表性包内检查 PASS，历史 H5 检查 25 项和 physical 检查 8 项通过。两个目录没有嵌套工作树、符号链接或跨挂载；可见 cwd/root/fd 无命中，但进程检查有 1,015 次权限拒绝，无法排除不可见或后续活动。

维护者对四个历史目录另行答复“同意删除”后执行；[历史目录清理收据](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/u6-four-historical-cleanup-receipt.json)记录逐项路径、inode、文件数量、保护 SHA/pins 和执行过程。删除前 1,637 条选中证据映射的 SHA/长度均匹配，七项代表性检查 PASS；可见 cwd/fd 无命中，但有 428 次权限拒绝，不能排除不可见或后续活动。未跨挂载、未递归工作树或 Git、未跟随目录内链接。按 package + 四目录同口径 `du` 测量，差额为 **3,731,234,816 分配字节**；共享外部硬链接及并发变化不在范围内，项目级净下降仍需扣除归并新增量并完整核对。删除后七项代表性包内检查 PASS、历史 H5 25 项和 physical 8 项通过；保护文件 SHA 与 pins 未变。文档 validator 仍报告保护输入 `MUJOCO_LOG.TXT` 的 1 项错误、79 项历史链接问题、0 项 stale path；旧目录历史链接不会全部继续有效，三处历史页面已添加到 G04 有界入口的定位说明。

两份旧 H5 的当前 codec／历史 judge 测试已切换到 U5 包中对应 SHA 对象并检查 SHA；25 项受守卫离线检查通过。四份 physical 测试输入也已在包内建立相对符号链接，指定新位置运行的 8 项受守卫检查通过；测试仍允许显式指定其他输入。旧文件保持不变。Panda Isaac 资产测试现使用包内 USD manifest；按 manifest 将 68 个已保全 source 对象以硬链接排列，包含 pxr 的定向 source 构造检查 8 项通过，solver SDK 被阻止导入。该检查不是 App 或 native 物理运行。G05 简单主体两份 delivery 的 24 个必要文件也以包内硬链接布局；三种配置安装、损坏拒绝及 source 绑定共 5 项 pxr 检查通过。历史 supervisor 的共享锁仍在 `phase_ii_01_sol_luna_handoff_20261023_001/`。该目录、现行测试样本、所有锁、保护输入、第三方源码与嵌套 worktree 均不列删除。迁移前快照中当前 checkout 锁 inode 为 29918777、integration 锁 inode 为 33310300，`/proc/locks` 未显示持锁项；既往进程 fd 扫描存在权限拒绝。后续经维护者确认停用后实施的迁移及其范围见下文。

针对四个历史目录的[保留检查](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/u6-stage-directory-retention-check.json)：U5 最终选择中分别有 148／1,243／229／17 条原路径映射，内容对象 SHA 和长度均匹配；只覆盖选中的有界结论，不保证其余历史文件或整包可恢复。4a 的当前 `orchestration.json` 四个 report／matrix／plan／manifest 引用已切到与原文件 SHA 相同的对象；manifest 仍是历史清单，不表示其全部旧条目将被保留。历史审查页及可能的外部调用仍可能使用旧路径。当前进程 cwd/fd 快照无可见命中，有 427 次权限拒绝，无法证明所有 owner 释放；四目录当时尚未授权；现已按后续明确授权删除。定向纯/fake 入口 240 passed；当前文档 validator 保持 1 项保护文件 `MUJOCO_LOG.TXT` 错误、79 项历史链接问题和 0 项 stale path，不称全绿。

四个历史目录删除前的 [符号链接与 worktree 快照](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/u6-candidate-symlink-worktree-snapshot.json)：4a 和 4c 各 0 条符号链接；4b 有 19 条全部指向目录外，其中包含 integration checkout 的 pytest 临时路径和当前 Python 环境的第三方包；5c unit4 有 67 条，解析后均在其目录内。所查四个目录没有发现嵌套 `.git` 标记或已注册 worktree。执行任何获授权的目录操作都不得跟随符号链接，尤其不得触及其外部目标；此快照不证明 owner 或活动状态。

锁调用与过渡：示例验证器使用 `workspace/locks/shared_native_execution.lock`，它是本 checkout 历史锁的硬链接，打开及获取时核对设备和 inode；旧锁缺失、替换或不匹配时拒绝运行。维护者确认 integration 已停用并授权接管后，检查未见相关持锁者或运行进程，非阻塞获取两把旧锁并保持持有，原子切换 integration 旧路径。现两处旧路径及主 checkout 新路径同为设备 2052、inode 29918777，原 integration inode 33310300 以硬链接保存在 [迁移记录目录](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/lock-migration-receipt.json)；[六种有序跨路径进程争用检查](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/lock-cross-path-contention.json)通过。路径运行期间不得替换或 unlink。三份当前版本 probe 已按 inode 去重加锁；历史 U3 监督器及冻结双锁计划保留原样，不能按原双路径直接重跑（会对同一 inode 再次加锁而拒绝），新运行应使用新计划。示例只获取本 checkout 锁，其他未迁移 checkout 不保证互斥。

监督器原先可能在监控异常或终止信号后提前放锁，现于所测路径持锁直至进程组退休；强制退休使运行结果 INVALID。[独立只读复核](../../../../../../workspace/maintenance/v211_e11_e16_independent_review_0506ae26/u6-lock-transition-review.md)对本地过渡未发现新增阻断：七项受守卫的锁争用、替换、合成进程异常／SIGTERM／SIGHUP及强制退休状态检查通过；最终实现另通过固定纯/fake 入口 240 项。未运行 native；SIGKILL、宿主故障、未处理或重复信号、逃逸进程组以及运行时路径被替换等仍不受保证，不能据此认定全局锁安全。

本轮测试后复核 G05 24 个文件和 Panda delivery 82 个文件，内容 SHA 均属于 U5 保留选择；这只是文件字节核验。

恢复：选择中的原始文件通过 `retained-claim-selection.json` 的 `original` → `retained` 和 SHA/长度从 U5 对象复制到新的空目标并校验；source 另由列出的索引定位。此方法不保证恢复被舍弃的完整旧目录或旧 manifest。临时试验目录可用已保留输入重新进行范围内的验证，但不承诺重建其全部历史输出。

当前测试样本的独立恢复：从保留对象和索引使用 `workspace/maintenance/v211_e11_e16_u5_20261113_001/materialize_current_test_fixtures.py` 向新空目录复制并校验 112 个文件；在恢复副本上，三份 USD delivery 经 OpenUSD 读取通过、两份 leaf H5 分别经当前 codec 与历史 judge 读取通过、四份 physical H5 的受守卫检查 8 项通过。该复核不依赖原历史目录，也不证明每个历史 reader 或物理运行。测试副本 `/tmp/geochora-u6-fixture-recovery-20261113-001/` 快照占用 46,522,368 分配字节，是本轮临时产物，已按本次授权删除。

U7 的 stage3/stage4 refs 已按具体授权删除；integration 此前一次 Git 移除失败，现已按2026-11-14维护者续授权完成残留及 stage5 分支清理，见文末收尾记录。其余候选仍保留，不进行未经授权的删除或 Git prune。

| 对象 | 当前准备与未解决事项 |
|---|---|
| 主 checkout `/home/lly/Program_Files/Geochora` 与 `codex/v211-stage5-diagnostic` | 保留；含四份保护输入、最终证据包和当前工作。 |
| `codex/v211-stage3`、`codex/v211-stage4` | 已按维护者明确授权，以 `git branch -d` 删除；原 ref 分别为 `842e1efd8268a6a99d075640a30840c2eeb4918f`、`3ca161c41340d6015be4fc949ac43771c233ee1c`。删除前确认均为当前 HEAD 祖先、未被工作树检出，refs bundle 与恢复仓库复核通过；[删除收据](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/approved-stage3-stage4-deletion.json)记录保护 SHA、pins 与恢复入口。本地 heads 9→7，未删除工作树。 |
| `codex/v211-stage5` 与 `/home/lly/.codex/worktrees/v210-integration/Geochora` | **残留与分支已删除。** 前次 Git 移除失败的事故保留原结论；2026-11-14续授权后逐项核验剩余内容，给368个只读目录补充所有者权限，以不跟随符号链接的目录描述符流程清除已注销残留，再用普通 `git branch -d` 删除旧分支。未重建旧登记、未再次调用 `worktree remove --force`。详见[收尾收据](../../../../../../workspace/maintenance/v211_integration_residual_cleanup_20261114_001/cleanup-result.json)。 |
| `/home/lly/.codex/worktrees/archive_v1_0_0` | 保留；Git 明确标记为冻结历史参考且锁定。 |
| `/home/lly/.codex/worktrees/phase-ii-01-camera/Geochora` | 暂缓候选；tracked 状态干净但有 ignored 内容，须确认实际归属和保全。 |
| `workspace/maintenance/geophys_upstream_reset_20261022_001/core-baseline` | 暂缓候选；嵌套注册 worktree，`GeoPhys` 和 `asset/external/mujoco_menagerie` 存在类型变化，不能随父目录递归删除。 |
| `workspace/maintenance/p2_0_v1_1_clean_checkout_20261017` | 暂缓候选；嵌套注册 worktree，tracked 状态干净但有 ignored 内容，须确认归属与保全。 |
| `main`、`develop`、`v1.1.0`、`v2.0.0`、`v2.1.0` 和四个现有 tags | 保留。 |

三个阶段分支的 [bundle 恢复验证](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/ref-restore-verification.json)仅覆盖 Git refs：三条 ref 在新 bare 仓库恢复并通过 fsck；本次重新计算 bundle SHA 与报告一致。它不覆盖 ignored 文件、子模块或工作树归属。先前 fsck 的不可达对象缺口已登记，不继续扩大全库历史追查。清理后净空间、refs/worktree 前后以及维护者项目接收仍 OPEN。

若需恢复已删除的两条分支，在确认同名 ref 仍不存在后，从主仓库运行 `git fetch workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/stage-refs.bundle refs/heads/codex/v211-stage3:refs/heads/codex/v211-stage3 refs/heads/codex/v211-stage4:refs/heads/codex/v211-stage4`，再将两条 ref 分别与上表 OID 比较；不要用强制 refspec 覆盖新创建的同名分支。该操作恢复 Git refs，不恢复已删除的未选历史文件或工作树。

维护者接管后的 integration 保全：三份 untracked 原件、保全副本和恢复样本的 SHA 再次相同。其 workspace、temp_outputs 及另外 443 个 ignored 路径已作[临时快照](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/integration-local-snapshot-receipt.json)，带校验和的 `rsync` 干运行比对无差异，并从快照实际恢复三个文件和一条符号链接样本。GeoPhys 子模块另有 3,858 个 ignored 路径已[复制、校验并恢复三个样本](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/integration-geophys-ignored-receipt.json)，单独占 1,296,580,608 分配字节；Menagerie 未列出 ignored 项。符号链接只保全原链接文本，不复制外部目标，样本恢复不等于完整运行环境恢复。源工作区扫描未发现嵌套 `.git`、跨设备或特殊文件；两个子模块的 tracked 状态干净。

上述三个 GeoPhys 恢复样本均来自 `.pytest_cache`；另从本地 `.taichi_cache` 和 `temp_outputs` 各选一份文件实际恢复，原件、快照和恢复副本 SHA-256 均一致，见[补充样本记录](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/geophys-representative-restore.json)。这仍是抽样，不证明完整环境可运行。

后续删除前复核中，最终证据包的四个符号链接均不指向 integration；当前编排索引的三个 G02 旧路径已切到 SHA 相同的保留对象，历史 source-map 另加有界定位。integration 临时快照本身有 6,062 条绝对符号链接指向原 workspace，其中 6,050 个目标条目存在于快照，12 条在原目录中已失效；见[链接核查](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/integration-snapshot-absolute-links-audit.json)。移除原工作树后，这些原样保留的绝对链接不会自动指向快照，历史快照需要恢复到原路径或在恢复副本上重映射；不改写原始快照冒称历史环境仍可直接运行。

integration 的 GeoPhys 是独立浅仓库，单独 bundle 普通克隆失败；保全其 shallow 边界后在新 bare 仓库恢复全部 10 个 refs 和符号 HEAD，`git fsck` 通过，详情见[恢复报告](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/integration-geophys-restore-report.json)。结果只覆盖来源已有浅历史，不能声称历史完整；Menagerie 的 12 个 refs 与主 checkout 相同。维护者后续已具体授权受条件约束的一次 Git 官方强制移除；该次尝试失败且部分生效，见下文。

在隔离合成仓库中测试当前 Git 2.43.0：普通 `git worktree remove` 对含已初始化子模块的工作树拒绝；正常 `git submodule deinit` 后再次执行仍拒绝。完整输出见[合成流程收据](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/synthetic-worktree-submodule-removal.json)。维护者后续授权 integration 一次官方 `--force` 后，另一个含子模块与未跟踪文件的合成仓库试验成功；真实 integration 的结果不同：尝试返回权限错误并部分移除。

**真实移除失败及影响（2026-11-14 本地时间）：** 执行前四项保全比对日志为空、三份未跟踪输入和 refs bundle 已核对，持共享锁执行一次 `git worktree remove --force` 后，Git 报 `error: failed to delete ... Permission denied`（退出 255）。我在执行前没有识别出受影响树中只读目录；事后[只读检查](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/integration-partial-removal-permission-scan.json)发现 368 个不可写目录，Git 未指明具体失败子项，不能断言它们中哪一个是根因。Git 已移除 `.git/worktrees/Geochora1` 登记，残留目录内 `.git` 因此指向不存在的管理目录；现在有 5 个注册 worktree，但 integration 的残留目录仍存在，不能称完整移除。原 commit 所列 1,298 个 tracked 路径中，按存在性检查 925 个缺失；三份未跟踪原件及其备份 SHA 仍匹配。旧 `codex/v211-stage5` 仍在，严格遵守先完整移除后删除分支的顺序，未对其执行删除。详见[影响核查](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/integration-partial-removal-impact.json)。

保全包、三份未跟踪文件、stage refs bundle、GeoPhys refs 和浅边界均保留；**此前并未逐字节备份被删除的 worktree Git 管理目录**，因此无法保证原配置、reflog、钩子或不可达对象可恢复，不能把 refs 和内容快照称为完整 worktree 备份。[独立复核](../../../../../../workspace/maintenance/v211_e11_e16_independent_review_0506ae26/u7-project-preparation-review.md)确认了登记丢失、残留、分支和上述保全限制。不得重复使用本次仅一次的 `--force` 授权，也未更改残留目录权限。后续需先明确残留及 Git 登记的恢复／清理方案和授权。

对 camera、core-baseline 和旧版本 clean checkout 的[只读 gitlink 快照](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/remaining-worktree-gitlink-snapshot.json)显示，三者各自的 HEAD 都含 GeoPhys 和 Menagerie gitlink；camera 与旧版本 checkout 两个子模块均已初始化。core-baseline 的两处类型变化实际为指向 `geophys-upstream` 和主 checkout Menagerie 的符号链接，目标都在该 worktree 外，不能跟随或当作其私有内容删除。此快照未保全 ignored 内容或确认其他 worktree 的 owner，合成试验也未在这些真实 worktree 上执行；它们仍不具备删除条件。

剩余工作树的有界保全：camera 和旧版 checkout 的 GeoPhys 均为独立浅仓库。各自在新 bare 仓库恢复命名 refs、符号／detached HEAD 和浅边界并通过 `git fsck`；camera 的本地分支 `codex/phase-ii-01-r05-provider` 在主 GeoPhys 中没有同名本地 ref，不能仅以提交对象存在代替名称保全。[恢复收据](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/remaining-geophys-ref-preservation-20261114-v2/receipt.json)记录两个 bundle 的 SHA、来源及恢复位置。首次试验对 bare 仓库误用 `git status` 而以 128 停止，源未修改；该试验保留占 79,040,512 分配字节，修正后独立新目录占 103,567,360 字节。此保全仅覆盖命名可达 refs 及现有浅边界，不涵盖 ignored 文件、Git 配置／reflog／index／hooks、不可达对象或更早历史。

[本地类型盘点](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/remaining-local-roots-inventory-20261114/receipt.json)发现 camera 的 ignored workspace 内有独立的第三方 `robosuite/.git`，故 workspace 未作为普通目录复制或删除；符号链接检查仅核对字面目标，未解析所有链接链。对 camera 和旧版 checkout 的五个不含嵌套 Git 标记的本地输出根，已[复制并逐文件核验](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/remaining-local-outputs-preserved-20261114/receipt.json) 196 个普通文件，副本占 8,257,536 分配字节；源／副本逐项 SHA、大小及所列基本属性一致，带校验和的复制后 dry-run 无差。[独立复核](../../../../../../workspace/maintenance/v211_e11_e16_independent_review_0506ae26/u7-remaining-geophys-ref-review.md)另核两仓库 refs、shallow、bundle 和 fsck，以及上述 196 个源／副本文件的路径、长度和 SHA；五根目录各取一文件从副本恢复至新路径并与源和清单 SHA 对比，所有受检路径扩展属性均为空，见[样本收据](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/remaining-local-output-restore-samples-20261114/receipt.json)。进程快照前后均有 1,033 次权限拒绝，不能排除不可见或 mmap 持有者及后续写入；这不是完整工作树或运行环境恢复，其他 worktree 归属仍未确认，也不是删除授权。

针对快照候选的分组恢复工具，审查发现父目录检查后被替换可能导致写入错误位置；现以目录描述符和身份检查约束目标，7 项合成测试通过，并在新目录恢复一个含 33 条硬链接路径的组。该测试不证明能抵御非合作进程在检查与系统调用之间移动目录；真实执行仍要求独占使用安排，修订版尚未完成独立审查。原快照和全量恢复副本均保留，快照删除仍无完成审查的执行器或具体授权。

空间：四个获授权历史目录清理在记录的 package 加目标范围内，`du` 差额为 3,731,234,816 分配字节；新 integration 快照单独 `du` 为 15,385,866,240 分配字节，GeoPhys bundle 和恢复仓库另约 38,899,712／40,267,776 字节。上述范围和时间不同，硬链接及并发变化不完整，不能相减称为项目真实净下降；显然也不能忽略新增保全量。项目净空间目标仍 OPEN。除已获条件式授权的 integration 和其阶段分支外，其他 refs/worktree 删除必须由维护者针对具体候选另行决定。

本次失败尝试前后对同一有序集合（integration 残留、U7 准备含快照、U5 包）测得 `du` 降低 **1,822,535,680 字节**；同期整个 `/home` 所在文件系统 `df` 已用减少 **2,469,957,632 字节**，见[空间收据](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/integration-partial-removal-space.json)。两者口径不同，后者含并发系统活动；两者均从快照建立之后开始，不能证明扣除原保全新增量后的项目净下降。失败后纯／fake 固定集 240 项通过，U5 3,056 条 stage 映射的 816 个唯一对象 SHA／长度全检无错；主 checkout 的保护文件 SHA 和两个 pins 未变。

[独立项目准备复核](../../../../../../workspace/maintenance/v211_e11_e16_independent_review_0506ae26/u7-project-preparation-review.md)复算 3,056 条 stage 映射对应的 816 个去重对象，大小和 SHA 均匹配；该数不包括其他 source 索引对象。复核当时确认上述两分支可作为审核候选，后续又复核了获授权的删除结果、GeoPhys ignored 清单及样本恢复。integration 与其他未闭合的工作树仍不可直接移除；U6/U7、项目净下降及维护者项目接收仍 OPEN。

## 2026-11-14：integration 残留与旧阶段分支收尾

维护者授权本轮完成所述删除任务，输入 `fe53e1a9`、当前优化分支，tracked clean。范围仅为已注销的 integration 残留和 `codex/v211-stage5`；约15.4 GB临时快照、Git恢复材料、其余工作树和版本 refs 均保留。前文事故及独立复核是其原时点记录，不是本轮当前状态。

删除前对64,337个残留条目逐项核对：[保全校验](../../../../../../workspace/maintenance/v211_integration_residual_cleanup_20261114_001/audit-result.json)确认40,151个普通文件和6,328条链接与快照对应、3份未跟踪文件与保留副本对应、3,412个文件与保留的Core／Menagerie Git blob对应；两个失效 `.git` 指针另存小副本。全部43,568个普通文件均有保全来源，未跟随链接读取外部目标。复核stage5为当前HEAD祖先、bundle及恢复ref相同，GeoPhys恢复仓库全部10个refs及浅边界保持一致；本轮不恢复前次已经丢失的worktree专用Git配置、reflog等管理元数据。

持主checkout共享锁期间，仅对368个属于当前用户的只读目录补充所有者读／写／执行权限，普通文件权限修改为0；在核对无挂载跨越、嵌套注册工作树和有效子Git管理目录后，使用不跟随链接的 `shutil.rmtree(..., dir_fd=...)` 删除这个已不受Git管理的残留。随后普通 `git branch -d` 成功删除stage5。残留路径已不存在；259个去重外部链接目标的存在性及所查设备／inode／模式／大小／mtime未变，主锁inode、四保护SHA、两pins未变。注册worktree仍为5个（本轮开始前已注销integration），本地heads由7减至6。当前可见进程无目标cwd/fd冲突；`/proc`权限限制与维护者已确认停用的使用安排分别记录在收据中。

删除后纯／fake **240 PASS**、历史H5 **25 PASS**、physical离线读回 **8 PASS**，证据包七项代表离线检查 **PASS**；现有reader按原设计只刷新派生结果JSON，非新native运行。3,056条stage映射的816个唯一对象及包内现存1,370个内容对象（含source等支持对象）的SHA／长度核验通过，原H5／source内容对象未改写。文档检查与先前快照相同：1项既存 `MUJOCO_LOG.TXT` 保护基准错误、79项历史链接问题、0项stale path，本轮保护SHA未变、新增错误0。日志和[内容核验](../../../../../../workspace/maintenance/v211_integration_residual_cleanup_20261114_001/retained-package-integrity.json)保留在本轮ignored目录；生产代码与测试代码修改均为0。

同一次 `du -s -x -B1` 对有序集合“integration残留＋主checkout”计量，包含现有快照及新收尾记录，清理前155,104,763,904、清理后139,519,737,856分配字节，减少 **15,585,026,048字节（约15.59 GB）**；[前测量](../../../../../../workspace/maintenance/v211_integration_residual_cleanup_20261114_001/space-before.json)与[后测量](../../../../../../workspace/maintenance/v211_integration_residual_cleanup_20261114_001/space-after.json)使用相同顺序去重硬链接，测量之后的日志／文档写入另有少量增量。这证明本轮固定范围的下降，不补造建立快照前的E00～E16项目净下降。integration删除事项闭合；临时快照精简、其他工作树处置、累计空间核算及项目最终接收继续OPEN，U4／U5不重开，G06不启动。


## 2026-11-14：integration 快照去重候选复核

复用 integration 残留逐项保全证明，仅筛选 `integration-local-snapshot/workspace/` 中已有证明且 SHA 与 U5 内容对象对应的普通文件；没有重开 U4/U5，也没有改动快照或 U5 对象。对 **21,929 条路径、19,785 个独立 inode 和 561 个 U5 对象**逐一核验：快照与 U5 内容 SHA 均匹配，候选硬链接组在该清单中完整。候选 inode 的 `st_blocks` 合计 **9,271,549,952 字节**，不是实际可释放字节；共享块、范围外引用和并发变化尚未计入。清单及结果见[候选审计](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/snapshot-dedup-preparation/candidate-audit.json)，清单 SHA-256 为 `ebd4bc4b3149de129869335363823788fea74a2a849de49faf88327fc76a4113`。

候选 inode 的扩展属性检查均为空；恢复样本覆盖 4 组、36 条路径（含多硬链接组），内容、mode、uid、gid、mtime 和组内硬链接符合记录，未与 U5 对象共用 inode。另一个仅写新目录的候选材料化工具以 20 组进行 smoke；当时二者均为抽样；后续全量候选文件恢复见下段。现有工具不恢复目录属性、原 inode、ctime 或绝对链接的重映射，不能称完整原快照恢复。原快照 6,062 条指向旧 integration workspace 的绝对链接限制仍适用。

候选路径涉及 1,784 个直接父目录，其中 **368 个当前不可写**。排除含不可写父目录的完整硬链接组后，剩 7,089 组、9,233 条路径，独立 inode 分配块合计 2,930,221,056 字节；这仍只是筛选结果，未证明可删除或可回收。未更改目录权限。独立审查复算全部候选内容及 U5 对象，同意清单可审核，但认为执行前仍须准备逐路径身份与内容重验、路径安全、owner/引用、异常中止与逐项收据，并明确恢复义务；详见[独立审查](../../../../../../workspace/maintenance/v211_e11_e16_independent_review_0506ae26/u6-snapshot-dedup-review.md)。现阶段不请求把该清单作为可直接执行的删除授权；快照、其他工作树和第三方内容均保留。

后续将全部候选从 U5 对象复制到新的隔离恢复目录 `snapshot-dedup-preparation/full-restore-validation-20261114/`（[恢复收据](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/snapshot-dedup-preparation/full-restore-verification.json)）；实施者与[独立复核](../../../../../../workspace/maintenance/v211_e11_e16_independent_review_0506ae26/u7-full-snapshot-restore-review.md)各自遍历校验 21,929 条路径、19,785 个 inode、9,234,545,951 内容字节，SHA、长度、mode、uid/gid、mtime、链接数及组内／组间身份均一致，未与 U5 对象硬链接，缺失／额外文件 0。这个结果只涵盖选中的普通文件，不还原目录属性、atime/ctime 或原 inode。另在新目录拼合一个 3 字节候选、一个 26,337 字节非候选文件和一条由旧绝对目标重映射的链接并校验；这只是[拼合样本](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/snapshot-dedup-preparation/combined-recovery-nonempty-result.json)，不是完整快照或运行环境恢复。[链接分析](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/snapshot-dedup-preparation/link-dependency-audit.json)记录 6,062 条旧绝对链接中 0 条直接指向候选文件、391 条指向包含候选的目录，只按字面前缀匹配，不覆盖链接链或外部引用。

全量恢复目录独立 `du -s -x -B1` 为 **9,285,554,176 字节**，是本轮新增保全试验空间；原快照同口径为 15,385,866,240 字节，两者都保留。候选去重如要实际产生净收益，必须计入该新增副本及其未来去向，不能只列被删条目的块数。[候选直接父目录属性清单](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/snapshot-dedup-preparation/parent-directory-metadata.json)记录 1,784 个目录的身份、模式、所有者、mtime 和 xattr：368 个当前不可写，全部属于当前 uid，均无列出的 xattr；这是时点检查，不授权 chmod 或删除。执行方案仍须逐路径身份／内容、U5、owner／引用、完整链接组和目录属性复核，设计异常中止及可追踪收据，明确未恢复范围后再集中申请具体授权。

本次复核后四个保护输入 SHA 和两项子模块 HEAD 均与 integration 收尾收据一致。生产代码无变化；U6 的快照处置与项目净空间核算、U7 其他工作树的归属/保全和维护者项目接收仍 OPEN。

2026-11-14 当前只读 `git status --ignored=matching` 快照：冻结工作树无 tracked/untracked 变化；camera 无 tracked/untracked 变化且列出 56 个 ignored 顶层条目；core-baseline 有两处已知子模块类型变化及 18 个 ignored 顶层条目；旧版本 clean checkout 无 tracked/untracked 变化且列出 66 个 ignored 顶层条目。这里的数字是 Git 压缩显示的条目数，并非文件总数，不证明 owner 已释放或 ignored 内容已保全。四者均未移除。

剩余工作树的[2026-11-14 只读快照](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/remaining-worktrees-20261114.json)另分别测量：冻结 archive 12,279,808、camera 7,301,443,584、core-baseline 37,482,496、旧版 clean checkout 1,993,269,248 分配字节。每项为单独 `du -s -x`，包含其源码和本地子模块，跨对象共享块可能重复计数，不代表候选或可释放空间；不能把它们相加当净空间。camera 的 ignored `workspace` 另测 4,826,411,008 字节、`temp_outputs` 7,069,696 字节；旧版 checkout 两者分别为 40,960／20,480 字节。其内容和归属未确认，均保留。该快照对可见进程 cwd/root/fd 未见命中，但有 1,048 次权限拒绝，不能证明无使用者或未映射内容，也不是删除授权。

当前锁和旧 integration 字面路径的逐类调用及限制见[共享锁与旧路径核对](20261114_e11_e16_u6_lock_path_audit.md)。本 checkout 的新旧锁仍是同一 inode；受守卫锁定向检查 10 项通过，旧路径仍是正式示例依赖，T35 不提前关闭。

只读[预检 v3](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/snapshot-dedup-preparation/read-only-preflight-v3-20261114.json)再次通过：不跟随符号链接逐路径核对快照和全量恢复文件、父目录属性以及 561 个 U5 对象；快照与恢复各读取 9,234,545,951 内容字节。新增输出目录固定 fd、独占创建和 U5 包根保护，并检查恢复文件 xattr；10 项合成预检通过。[独立复核](../../../../../../workspace/maintenance/v211_e11_e16_independent_review_0506ae26/u6-preflight-output-fix-review.md)确认两处已发现的输出误写问题在所测边界修复；审计目录／祖先被非合作进程移动等仍不保证。v2 先于输出防护修订，不能证明新防护；v3 启动后观察到的脚本 SHA 与报告摘要另见[身份记录](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/snapshot-dedup-preparation/preflight-v3-code-identity.json)，不是签名执行证明。v3 首次启动时手工输错 manifest 摘要，程序在只读检查前拒绝且未产生报告；修正后通过。

只在新建临时目录进行 3 项两文件事务试验和单目录 SIGKILL 后 mode／mtime 恢复试验；这些均为合成试验，未验证真实候选 unlink、断电或完整重启恢复，部分删除也不会自动回滚。

快照候选的具体路径、保留材料、恢复限制、预计权限处理与中止要求列于[处置方案草案](20261114_e11_e16_u6_snapshot_disposition_plan.md)；目前尚无完成审查的真实执行器，草案不是删除授权。

### 项目接收入口（准备中）

* **代码范围：** [U4 独立主审及有界接收](20261113_e11_e16_u4_independent_acceptance.md)；不因项目清理重开。T19 的同次联合证据及 H5 单文件不自含完整 completion 的限制见 [联合证据报告](20261113_e11_e16_u4_joint_completion.md)。
* **最终证据：** [U5 五 stage 与五路线选择](20261113_e11_e16_u5_evidence_selection.md)；按各自冻结源码、配置和运行身份阅读，不称五路线均在最新 HEAD 重跑。
* **项目范围：** 本页记录已授权清理、锁迁移、恢复样本、失败事故及后续收尾；[专用账本第 11 节](../../planning/post-5c-e11-e16-remaining-ledger.md)为 U1～U7 当前状态入口。与规划输入 `a6b107ac` 比较，至 `a5991ea0` 的 tracked diff 为 108 文件、+6,063/−1,667 行；与 `1f1359ee` 比较为 280 文件、+22,473/−18,499 行，均包括代码、测试与文档，不代表本次快照审计的生产改动。
* **独立项目中途审查：** [U6/U7 收尾审查](../../../../../../workspace/maintenance/v211_e11_e16_independent_review_0506ae26/u6-u7-closeout-review.md)逐项列出 T35～T44 尚未闭合的条件；它不是最终整理后的主审，也不是维护者接收。
* **未闭合：** 快照候选普通文件已全量恢复校验，拼合仅为样本，删除方案及具体授权仍待闭合；其他三个非冻结旧工作树的归属及本地内容保全尚待闭合，冻结工作树保持锁定；累计项目净空间无法由现有不同时点口径直接相减；清理后完整项目复核和维护者项目接收仍未完成。当前 6 heads、5 注册 worktrees；原 integration 专属 Git 管理元数据无法保证恢复。

此入口用于后续审查，并非实施者自行宣布项目接收。除此前具体批准的对象外，不隐含删除许可，也不启动 G06。
