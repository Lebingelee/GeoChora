# E11～E16 三处停用工作树：保全与待审删除清单

状态：**准备中，不具备执行或提交删除审批的条件**。独立复核发现子模块处置方式和缓存分类尚未闭合；下列路径及保全事实供核查，尚非可执行删除清单。维护者已确认三处停止开发和运行，维护期间不再从旧会话或终端启动，并授权本 Goal 接管保全与处置准备；该确认不等于删除许可。当前分支 `codex/v211-stage5-diagnostic`；冻结 archive 保留。没有新建分支、改变 pins、启动 native 或删除工作树。

## 待审对象与影响

| 精确路径 | 冻结 HEAD | 范围和预计方式 |
| --- | --- | --- |
| `/home/lly/.codex/worktrees/phase-ii-01-camera/Geochora` | `2cba22d99c75eca6670b4f117bc1d9dd9193ca52` | 目录中包括 GeoPhys、Menagerie 两个已初始化子模块、本地缓存和历史 workspace。已单独迁出第三方 robosuite；其余 tracked 和有用本地普通文件的保全依据如下。61 个用户拥有的 `0555` 目录需在获批后逐项临时改为 `0755`，才可避免已知的权限失败。主 workspace 的 134 个旧绝对链接将失效，历史映射见下。 |
| `/home/lly/Program_Files/Geochora/workspace/maintenance/geophys_upstream_reset_20261022_001/core-baseline` | `60b3ecac872eb2626c8bfb3683aba29ee5625262` | 两处 gitlink 实际是指向该工作树外 `geophys-upstream` 和主 Menagerie 的符号链接；只允许移除链接本身，禁止跟随链接清理目标。 |
| `/home/lly/Program_Files/Geochora/workspace/maintenance/p2_0_v1_1_clean_checkout_20261017` | `bee498d1d784015f034c5b4af34320fdffa61411` | 旧版工作树，含 GeoPhys、Menagerie 两个已初始化子模块和本地缓存；三个历史 release receipt 另有 SHA 对应的保留副本。 |

具体保留和舍弃范围仍在分类，尤其是已初始化的第三方子模块和 ignored 内容；不能据此段推断删除范围。冻结 archive、主 checkout、外部符号链接目标、主 Git 对象库、U5、原 integration 快照、版本分支及 tags 保留。

## 已做的保全与恢复验证

- 三个 Core HEAD 均为当前分支祖先；其树中的 954／799／852 个去重 blob 在主 Git 对象库存在，分别各恢复两份文件并验证。三个工作树的 959／800／854 条 tracked blob 路径实际内容均与各自 Git blob 一致；两处 core-baseline 类型变化按外链记录。独立复核对 tracked 文件作了抽样。见 [Core 恢复](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/core-git-recovery-receipt.json)及[检出内容](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/core-worktree-bytes-receipt.json)。
- camera HEAD reflog 有 5 个提交不被当前命名 refs 包含且不是当前分支祖先；其 [bundle 及恢复](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/camera-reflog-bundle-receipt.json)保留全部 5 个 ref，隔离仓库验证树、blob 可得及样本。bundle 原 pack 含相对基线新增的 69 个对象；基线对象依赖保留的主 `.git/objects`。首次错误地检查 fetch 后本地 pack，因 alternate 命中而得出缺失结果；[直接检查原 bundle pack](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/camera-reflog-original-pack-coverage.json)通过。主对象库和当前分支须保留，不能把该 bundle 称为无依赖的完整历史备份。
- camera／p2 GeoPhys 的 refs、HEAD、shallow 和现有可达对象已保留到 [v2 恢复仓库](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/remaining-geophys-ref-preservation-20261114-v2/receipt.json)，tracked 实际内容分别 2,854／2,149 条与冻结树一致。Menagerie 的三个 checkout 各 3,040 条 tracked 路径逐文件与相同 pin 的主副本一致，命名 refs 和 shallow 边界已对比；保留主副本。[子模块样本恢复](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/submodule-restore-samples.json)覆盖四个保留树各两文件。GeoPhys 另有三个**原本未初始化且为空**的嵌套 gitlink；保留其 commit 身份，不声称 `data/assets` 或 `dexjoco` 上游对象均已离线恢复。
- 七份 worktree／子模块 Git 管理资料已复制并校验；其中 worktree 副本排除 `modules/`，子模块副本排除 `objects/`，对象依赖上述主库／bundles。14 个 HEAD/index 文件在独立目录恢复验证；这不是完整、可直接启动的 worktree 管理目录恢复。[管理资料收据](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/git-admin-copy-receipt.json)。
- camera 中独立第三方 `robosuite` 已从旧 workspace **同设备整体迁出**到 [保全位置](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/third-party/robosuite/)，1,260 个文件迁移前后 SHA/基本属性一致，root inode 未变；detached HEAD `fbee5844`、master `5ce6643f`、refs、shallow、fsck 和两个恢复样本已核对。它是 shallow `blob:none` partial clone：当前 HEAD 的 988 个不同 blob 本地存在，master 树有 558 个不同 blob 原本不在本地；不声称完整历史离线可恢复。[迁移收据](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/robosuite-move-result.json)记录旧→新路径。
- camera workspace 除上述迁出仓库外的 3,409 个普通文件，与主 workspace 相同相对路径逐文件 SHA-256 一致，独立复核也全量重算；这不证明目录元数据或符号链接完全等价。三份 p2 历史 receipt 均有 SHA 相同的保留副本。主 workspace 的 134 条旧 camera 链接保留历史文本及[逐项映射](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/camera-historical-link-map.jsonl)：68 项有主 workspace 候选镜像但不声称目录完整等价，66 项原目标为空或仅含目录，不迁入；旧链接未来可能悬空，历史目录不要求继续原位运行。当前生产／测试及 U5 的有界静态检查未发现三旧路径的字面执行依赖，迁出 robosuite 后七项包内离线检查通过；这不证明所有环境变量和外部动态调用均无依赖。p2 的旧→新 receipt 映射见[映射收据](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/historical-reference-map-receipt.json)。
- 一个 camera 文件与工作树外历史文件共 inode；[保留路径及 SHA](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/camera-outside-hardlink.json)已登记。移除 camera 链接将使其链接数减少、ctime 变化，须在操作前后核对保留路径的设备、inode、长度和内容 SHA，不得修改该外部文件内容。
- 五个输出根的 196 个普通文件此前已复制并校验，见[收据](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/remaining-local-outputs-preserved-20261114/receipt.json)。[Git 忽略项分类](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/git-untracked-cache-classification.json)另按仓库列出 Python、pytest、Taichi 缓存名称及历史输出；这是路径名分类，不单独证明每项可重建，也不覆盖空目录与符号链接。
- [忽略项大小分类](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/ignored-content-sized-classification.json)按当前 Git ignore 规则逐项 `lstat`，没有跟随链接：两个 Menagerie 仓库均未列出 ignored 项；camera GeoPhys 的 `.taichi_cache` 为 860 个普通文件、约 415.6 MB 分配块，p2 GeoPhys 为 70 个、约 7.8 MB。camera workspace 除优先归入 Python 缓存的项外，列出 3,362 个普通文件及 134 条链接；47 个 workspace 内的 Python 缓存计入 Python 类，故合计仍为 3,409 个普通文件。此计数不含空目录、非 ignored 项和 Git 管理资料，分类名不单独证明可重建；块计数仅在各类别内按 inode 去重，不能用作实际回收量。

以上结果经[独立复核](../../../../../../workspace/maintenance/v211_e11_e16_independent_review_0506ae26/u7-three-worktree-preservation-review.md)；合成 Git 试验、实际内容及恢复样本各有界限。原 integration 专属 Git 管理元数据先前损失无法补回。旧 `robosuite master` 缺失的 promisor blob 与未初始化 gitlink 在操作前已不具备本地完整内容，不作为本次新物理运行或完整历史可重建的依据。

## 尚未闭合的执行方式

独立项目复核指出，原 Goal 禁止强删绕过子模块问题，现有工作树含已初始化子模块；此前草案提出的 `--force` 不满足该条件，已撤回，不作为审批方案。隔离试验中普通 `git worktree remove` 在 `submodule deinit` 后仍拒绝。Git 2.43 的[官方实现](https://raw.githubusercontent.com/git/git/v2.43.0/builtin/worktree.c)会检查工作树管理目录中的 `modules` 目录，即使它为空；这一发现只解释试验现象，不构成修改真实管理目录的授权。正在隔离验证保全第三方内容后如何遵守正常移除流程，并须独立复核。历史输出和缓存的逐项舍弃范围、操作事务、权限预检及恢复措施也尚需闭合。

进一步的[合成试验](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/git-noforce-retirement-synthetic-v4.json)在迁出子模块、修改其管理指针并手动删除空管理目录后，普通移除返回成功；但[独立复核](../../../../../../workspace/maintenance/v211_e11_e16_independent_review_0506ae26/u7-noforce-retirement-v4-review.md)认为这不足以证明没有绕过子模块保护，官方文档也未保证该组合受支持。合成脚本还通过 `info/exclude` 隐藏测试链接，不能照搬真实工作树。真实多子模块、事务恢复和权限场景未验证；不执行该方案。

另外，对指向外部 Git 仓库的 gitlink 符号链接直接执行不带 `--force` 的 `git submodule deinit`，在[隔离合成试验](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/git-deinit-external-symlink-synthetic.json)中返回失败前，已先把外部仓库的 `.git` 管理目录迁入 worktree 的 `modules`。哨兵内容虽仍在，外部仓库管理状态已改变。此流程不符合外部目标保护边界，**不得对 core-baseline 的两条外链直接使用**；试验只操作了临时目录。五个既有输出根的[当前 checksum 复核](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/output-roots-current-rsync-recheck.json)仍与保留副本一致，范围仅限这些根。

对 camera／p2 四个已初始化子模块的[只读迁移预检](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/submodule-relocation-preflight.json)显示：各 checkout、对应 Git 管理目录和拟保全位置位于同一设备，四者都是浅仓库，未发现 objects alternates；Git 文件和 `core.worktree` 均使用指向旧位置的相对路径，单纯移动目录会破坏其关联。两个 GeoPhys checkout 共三个嵌套 gitlink 原本未初始化。一次[隔离恢复试验](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/submodule-relocation-recovery-synthetic.json)在五个顺序阶段分别模拟停止，并恢复 checkout／管理目录 inode、Git 文件、配置、HEAD 和状态；首次试验因迁出后尚未修正 `core.worktree` 而不能通过 `git -C` 打开仓库，修正合成步骤后通过。这是进程内控制的临时实验，不覆盖断电、持久日志、真实嵌套子模块、竞争替换或外链，不构成真实迁移程序。四个真实子模块均未移动。

[独立复核](../../../../../../workspace/maintenance/v211_e11_e16_independent_review_0506ae26/u7-submodule-relocation-review.md)还发现真实 Git 管理树与单子模块试验不同：[只读目录盘点](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/submodule-admin-parent-shapes.json)中，两处均为 `modules/GeoPhys` 和 `modules/asset/external/mujoco_menagerie`。即使保全迁出四个叶管理目录，`modules/asset/external` 等祖先仍会存在；此前单层空 `modules` 合成试验不能直接套用。祖先目录的身份、是否为空、恢复及该操作是否符合原 Goal 均未解决，不递归删除管理目录。复核另指出，整体迁出虽不新增复制，仍会保留两份 Menagerie 现有字节，并非去重；应优先复用已保全内容，不可仅凭 tracked 相同就舍弃 ignored 或管理资料。

随后[双子模块隔离试验](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/multisubmodule-crash-experiment.json)模拟一层及多层管理路径、未初始化嵌套 gitlink、ignored 文件及外部链接，并在八个步骤后让子进程立即退出；每次由外部进程恢复后，两子模块的 inode、HEAD、原始 Git 文件／配置、嵌套 gitlink 状态、ignored 文件与外部哨兵均符合试验前状态。首次启动因测试程序把相对 Git common-dir 当绝对路径而失败，未进入迁移阶段；修正临时路径解析后重试通过。这不覆盖系统调用中断、断电、非合作并发、xattr 或原始目录属性；预先存放的备份也不是完整持久日志，仍不是可运行于真实工作树的执行器，未进行真实工作树移除。

[独立审查](../../../../../../workspace/maintenance/v211_e11_e16_independent_review_0506ae26/u7-multisubmodule-crash-experiment-review.md)指出，合成的两个子模块复用了同一嵌套路径，不覆盖真实的三种路径；仅检查外链存在及外部哨兵，未核验其原始文本或实际目标。恢复按路径存在性判断，未防止目标替换，且 `rename` 可覆盖。审查还发现测试 worker 最初可接受任意路径：现已增加临时目录／标记防误用检查，受测主 checkout 路径[被拒绝](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/relocation-worker-guard-test.json)，并重新通过八个合成停止点；该检查不是抵抗恶意替换的安全边界，也不使试验脚本成为真实执行器。

### 第三方 checkout 保全路径草案（未执行）

为避免复制整棵工作树，一个待验证方案是在同设备内，分别将下表的 checkout 和其 Git 管理目录迁入 `workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/third-party/submodules/` 下各自的 `checkout`、`gitdir`，再修正迁出 checkout 的 Git 文件及迁出管理目录中的 `core.worktree`。这是四对各自独立的路径，不应把父目录或外部链接目标作为对象；同设备迁移仍保留现有缓存和重复的 Menagerie 文件占用。

| 标识及目标子目录 | 当前 checkout | 当前 Git 管理目录（相对主 `.git/worktrees/`） |
| --- | --- | --- |
| `camera-geophys/` | `/home/lly/.codex/worktrees/phase-ii-01-camera/Geochora/GeoPhys` | `Geochora/modules/GeoPhys` |
| `camera-menagerie/` | `/home/lly/.codex/worktrees/phase-ii-01-camera/Geochora/asset/external/mujoco_menagerie` | `Geochora/modules/asset/external/mujoco_menagerie` |
| `p2-geophys/` | `/home/lly/Program_Files/Geochora/workspace/maintenance/p2_0_v1_1_clean_checkout_20261017/GeoPhys` | `p2_0_v1_1_clean_checkout_20261017/modules/GeoPhys` |
| `p2-menagerie/` | `/home/lly/Program_Files/Geochora/workspace/maintenance/p2_0_v1_1_clean_checkout_20261017/asset/external/mujoco_menagerie` | `p2_0_v1_1_clean_checkout_20261017/modules/asset/external/mujoco_menagerie` |

任何真实迁移前必须先实现并独立审查事务工具：持共享锁并重新查具体活动冲突；逐路径以不跟随链接的目录 fd 核验设备、inode、目标不存在和源内容；持久记录原 Git 文件、配置、权限和每步意图；以不覆盖方式迁移并同步父目录；迁移后复核 HEAD、refs、shallow、内容、三处未初始化嵌套 gitlink、外链文本和外部目标。中断时须依据日志和实际 inode 判断、逐项恢复或报告不确定状态，不自动覆盖目标或假定回滚成功。现有合成程序不满足这些要求；该草案也**没有解决**后续 Git worktree 移除的子模块检查，因此不是操作命令或待批准删除清单。保全后的常规 `git worktree remove` 能否按原 Goal 支持仍须另行解决。

[草案独立复核](../../../../../../workspace/maintenance/v211_e11_e16_independent_review_0506ae26/u7-submodule-relocation-path-draft-review.md)核对了四对当前路径、双向相对指针和设备，并确认拟目标目录当时不存在；建议定案前比较复用主 Menagerie 副本与整体迁出时对独有数据、缓存和空间的影响。其结论仅确认草案所列路径和限制，不是实际迁移或删除的批准。

执行前仍须重新检查锁、进程、保全、路径身份、外链和硬链接；任何具体冲突或保全缺口须停止受影响操作。先前 integration 强制移除部分失败且损失 Git 管理元数据，本次不得假定失败可自动回滚。维护者最终项目接收仍单独决定。

## 空间口径

在 robosuite 迁出后，各候选单独 `du -s -x -B1` 分别为 **6,456,983,552／37,482,496／1,993,269,248 字节**，合计 **8,487,735,296 字节**；对应三处 Git worktree 管理目录另合计 **1,264,984,064 字节**。两组不能当作保证回收量：共享块、硬链接、Git 实际删除内容、日志和并发均会影响结果。本次三工作树保全目录含迁出的 robosuite，测得约 **857.5 MB**；它是保留占用，不应只计算旧路径消失量。完整有序测量范围及当时合计 **26,910,564,352 字节**见[空间收据](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/three-worktree-space-before.json)；若获批，执行前重测并在执行后按同一顺序把不存在路径计 0，单列新增日志。不能将此次候选估算称作 E00～E16 历史累计净节省。

为评估不复制而整体迁出第三方 checkout 的保留成本，对 camera GeoPhys、camera Menagerie、p2 GeoPhys、p2 Menagerie 分别单独测得 **500,371,456／1,909,256,192／68,640,768／1,909,256,192 字节**，见[分项测量](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/submodule-retention-space-estimates.json)。这些数包括各 checkout 内缓存，不含主 Git 目录中的子模块管理资料；单独测量不证明独占块或实际回收量，也不意味着已决定迁出方式。
