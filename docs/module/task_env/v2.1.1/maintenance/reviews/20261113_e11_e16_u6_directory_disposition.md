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

U7 的 stage3/stage4 refs 已按具体授权删除；integration 已获条件式删除授权但尚未执行，其余候选仍保留，不进行未经授权的删除或 Git prune。下表记录具体状态；剩余候选在实际操作前仍须核对 owner、忽略文件和其他会话使用情况。

| 对象 | 当前准备与未解决事项 |
|---|---|
| 主 checkout `/home/lly/Program_Files/Geochora` 与 `codex/v211-stage5-diagnostic` | 保留；含四份保护输入、最终证据包和当前工作。 |
| `codex/v211-stage3`、`codex/v211-stage4` | 已按维护者明确授权，以 `git branch -d` 删除；原 ref 分别为 `842e1efd8268a6a99d075640a30840c2eeb4918f`、`3ca161c41340d6015be4fc949ac43771c233ee1c`。删除前确认均为当前 HEAD 祖先、未被工作树检出，refs bundle 与恢复仓库复核通过；[删除收据](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/approved-stage3-stage4-deletion.json)记录保护 SHA、pins 与恢复入口。本地 heads 9→7，未删除工作树。 |
| `codex/v211-stage5` 与 `/home/lly/.codex/worktrees/v210-integration/Geochora` | 维护者后续已明确授权在保全及使用冲突闭合后，对此 worktree 执行一次 Git 官方 `worktree remove --force`，然后正常删除该分支；不扩展到其他 worktree。删除前复核发现 VS Code Markdown language server 的 PID 765269 当前 cwd 在该 worktree，故暂停实际移除，[预检记录](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/integration-removal-preflight-current.json)列出保全校验和冲突。进程释放后需重查，不重复询问已给出的删除授权。 |
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

integration 的 GeoPhys 是独立浅仓库，单独 bundle 普通克隆失败；保全其 shallow 边界后在新 bare 仓库恢复全部 10 个 refs 和符号 HEAD，`git fsck` 通过，详情见[恢复报告](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/integration-geophys-restore-report.json)。结果只覆盖来源已有浅历史，不能声称历史完整；Menagerie 的 12 个 refs 与主 checkout 相同。维护者后续已具体授权受条件约束的一次 Git 官方强制移除；目前因上表的实际使用冲突尚未执行。

在隔离合成仓库中测试当前 Git 2.43.0：普通 `git worktree remove` 对含已初始化子模块的工作树拒绝；正常 `git submodule deinit` 后再次执行仍拒绝。完整输出见[合成流程收据](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/synthetic-worktree-submodule-removal.json)。维护者后续授权 integration 一次官方 `--force` 后，另一个含子模块与未跟踪文件的合成仓库试验以该选项成功移除；两次试验均未操作真实 integration。实际移除仍须先解除发现的 VS Code 使用冲突并重新预检。

对 camera、core-baseline 和旧版本 clean checkout 的[只读 gitlink 快照](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/remaining-worktree-gitlink-snapshot.json)显示，三者各自的 HEAD 都含 GeoPhys 和 Menagerie gitlink；camera 与旧版本 checkout 两个子模块均已初始化。core-baseline 的两处类型变化实际为指向 `geophys-upstream` 和主 checkout Menagerie 的符号链接，目标都在该 worktree 外，不能跟随或当作其私有内容删除。此快照未保全 ignored 内容或确认其他 worktree 的 owner，合成试验也未在这些真实 worktree 上执行；它们仍不具备删除条件。

空间：四个获授权历史目录清理在记录的 package 加目标范围内，`du` 差额为 3,731,234,816 分配字节；新 integration 快照单独 `du` 为 15,385,866,240 分配字节，GeoPhys bundle 和恢复仓库另约 38,899,712／40,267,776 字节。上述范围和时间不同，硬链接及并发变化不完整，不能相减称为项目真实净下降；显然也不能忽略新增保全量。项目净空间目标仍 OPEN。除已获条件式授权的 integration 和其阶段分支外，其他 refs/worktree 删除必须由维护者针对具体候选另行决定。

[独立项目准备复核](../../../../../../workspace/maintenance/v211_e11_e16_independent_review_0506ae26/u7-project-preparation-review.md)复算 3,056 条 stage 映射对应的 816 个去重对象，大小和 SHA 均匹配；该数不包括其他 source 索引对象。复核当时确认上述两分支可作为审核候选，后续又复核了获授权的删除结果、GeoPhys ignored 清单及样本恢复。integration 与其他未闭合的工作树仍不可直接移除；U6/U7、项目净下降及维护者项目接收仍 OPEN。
