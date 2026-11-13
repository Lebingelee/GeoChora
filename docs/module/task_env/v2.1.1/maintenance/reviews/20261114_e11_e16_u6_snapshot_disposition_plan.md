# U6 integration 快照候选处置方案草案

状态：**DRAFT_NOT_EXECUTABLE**。本页冻结拟审查范围及恢复限制，不是删除授权；当前没有经过审查的真实删除执行器。后续只在维护者对具体范围及恢复限制明确授权、执行前检查通过后操作。U4/U5 不重开。

## 候选及保留

1. 原快照 `workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/integration-local-snapshot/` 中，仅 [candidate-manifest.jsonl](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/snapshot-dedup-preparation/candidate-manifest.jsonl) 所列 21,929 条普通文件路径是去重候选，清单 SHA-256 `ebd4bc4b3149de129869335363823788fea74a2a849de49faf88327fc76a4113`。不是递归删除快照、目录、符号链接、非候选文件或外部链接目标。候选文件的内容已按清单映射到 U5 `objects/sha256/` 并全量重新物化；U5 对象、清单、恢复脚本、证明及日志须保留。
2. 本次生成的完整恢复试验副本 `workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/snapshot-dedup-preparation/full-restore-validation-20261114/` 独立 `du` 为 9,285,554,176 字节，可作为**另列的临时副本候选**。它须保留到候选文件处置、U5 复核及必要恢复检查完成；如操作中止或验证失败，不能继续删除它。其路径、根 inode、目录／文件类型、挂载和硬链接须在任何批准的移除前重查；删除只针对这个目录，不能顺带删除相邻清单／脚本／收据或 U5 对象。尚未取得其具体删除授权。
3. 现存 4 个其他登记工作树，包括一个 locked archive、camera 和两个嵌套 checkout，均**不在以上两个候选内**；owner、独有内容及处置／例外仍待逐项闭合。保留当前工作树、所有 pins、版本分支／tags、第三方源码、锁和四个保护输入。原 integration 专属 Git 管理元数据先前缺失，不能由本方案恢复。

## 恢复合同与影响

全量验证涵盖上述选中普通文件的内容、mode、uid/gid、mtime 和硬链接组。若删除原快照中这些文件，原路径将缺失，须通过保留清单和 U5 对象在新的隔离目录重建；保留的 `materialize.py` 不直接向原快照覆盖，不恢复原 inode、ctime/atime、目录属性、所有绝对链接或完整运行环境。将候选与未删除快照及重映射链接拼合只做了两个文件／一条链接的样本，不能作为全量验证。6,062 条原绝对链接中，按字面分析有 391 条指向包含候选的目录，删除候选会使这些目录下的相应文件缺失；链接链和快照外调用者未穷尽。该限定范围须由维护者明确决定是否接受，不能擅自视为完整恢复。

候选唯一 inode 的 `st_blocks` 合计 9,271,549,952 字节；不是释放量。恢复试验副本的 9,285,554,176 字节是新增占用。批准并执行后，须对包含原快照、恢复副本及 U5 的同一有序范围前后测量，记录文件数、逻辑字节、分配字节、共享硬链接和其余新增输出；`df` 受并发影响另报，不以各目录单独 `du` 相加当净收益。若试验副本仍保留，不得忽略其占用。

## 完整执行器尚需具备的条件

- 固定 manifest、目录属性清单和 U5/恢复证据摘要；逐路径不跟随符号链接打开并重检设备/inode、类型、长度、SHA、mode、uid/gid、mtime、xattr、nlink 和完整硬链接组；对 U5 对象及保留恢复材料重新验 hash。检查记录只证明时点，操作时再次检查，发现漂移即停止受影响操作。
- 重新检查当前锁持有者、候选路径可见 cwd/root/fd、实际 writer 和相关引用。无法检查的 `/proc` 权限、未来用户及非合作写入须如实记录；一个时点无命中不证明 owner 或未来使用。对非合作写入和 pathname 检查后替换的竞态，须有可审查的排除前提及中止策略，不能声称仅用 `O_NOFOLLOW` 就消除了 TOCTOU。
- 目录属性清单覆盖 1,784 个直接父目录，其中 368 个当前不可写。任何批准的权限调整须逐目录验证 inode、owner、mode/mtime/xattr，在持锁和适当活动检查后只对必要目录临时增加 owner 所需权限；预写持久日志，操作完恢复原 mode 与可恢复时间属性。不能递归 chmod，不能追随符号链接。目录 ctime 无法恢复；若检测到并发变化，不能盲目覆盖其时间戳。
- 每个候选文件 unlink 前后持久记录意图和结果，随硬链接逐项减少核验预期 nlink。部分删除不自动回滚：保留 U5 和完整恢复副本，输出精确已删、未删和不确定项，以便按 manifest 在新位置恢复。异常、信号、宿主崩溃或 SIGKILL 后应能基于日志重查目录身份并恢复受影响目录权限；无法判明时停止并保留状态。不得把一次合成信号试验当成真实目录的事务保证。
- 完成实际删除后才开展受影响的当前引用、包内独立读回、正式示例路径及保护 SHA/pins 的适当复核；不以物理重跑代替离线读回，也不自动进入 G06。所有结果、例外及维护者项目接收仍分别记录。

只读预检、父目录属性快照及合成故障试验见[处置账本](20261113_e11_e16_u6_directory_disposition.md)。它们没有实现上述真实执行器，不作为一次性删除请求的充分依据。


## 合成事务及日志对账原型

在 ignored `snapshot-dedup-preparation/` 准备了仅供新建合成目录使用、无真实执行 CLI 的 [事务核心](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/snapshot-dedup-preparation/transaction_core.py)和[只读日志对账原型](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/snapshot-dedup-preparation/reconcile_transaction.py)。它们没有取得维护者删除授权，不建立真实 owner 独占、共享锁或 U5 执行期完整检查；marker 只是合成测试约定，不能视为安全隔离。

独立审查先复现 `fchmod` 已生效时立即中断导致权限未恢复但记录成功的缺陷，已按实际 mode 恢复并重新核对；还复现日志对账中未开始目录 mode 变化未标冲突、无待处理 intent 却接受 `uncertain`、journal 跟随链接及 FIFO 打开阻塞等问题，均已补充拒绝或冲突分类和合成回归。最新固定版本独立运行 **18 项合成测试通过**；journal 本身通过调用方提供的目录 fd 以 no-follow、nonblocking 方式读取，仍须由最终调用方证明目录和日志来源可信。[独立复核](../../../../../../workspace/maintenance/v211_e11_e16_independent_review_0506ae26/u6-journal-reconciler-review.md)记有版本及限制。

[两种 SIGKILL 合成演练](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/snapshot-dedup-preparation/synthetic-transaction-crash-reconciled-v5.json)在写入 unlink 意图后分别于实际 unlink 前、后终止，日志对账均标为不确定，并在核对目录 inode／owner／mode 后由测试父进程手动恢复 mode；未回填文件或恢复 mtime。它不证明真实清理或断电可靠性，也不能将日志确认等同排除非合作写入。原快照和完整恢复副本未修改。真实执行器、进程／owner／引用排除、执行期对象核验及维护者具体授权仍 OPEN。


## 持锁只读检查与分组恢复准备

[只读闸门 v2](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/snapshot-dedup-preparation/read-only-gate-v2-20261114.json)在持主 checkout 共享锁期间，从固定目录 fd 读取并在结束时重新核对 manifest／父目录清单，重算候选快照、完整恢复副本和 U5 对象，前后核验四保护输入及两 pins。前后可见 cwd/root/fd 扫描无命中，权限拒绝分别 1,030／1,033 次；不覆盖不可见或 mmap-only 使用者、未来活动和非配合 writer。闸门返回后释放锁，结果不是删除许可，也不能代替同次实际操作时持锁重新检查。早期 v1 收据使用过在锁外先摘要再读取的实现，只作历史结果，不证明 v2 的输入绑定。

部分操作后的[恢复清单原型](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/snapshot-dedup-preparation/recovery_plan.py)将受影响路径的完整硬链接组列为隔离重建候选，并将目录中断、冲突或不一致状态列为人工复核；[分组物化原型](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/snapshot-dedup-preparation/materialize_recovery.py)只向新目录复制对象，不覆盖现存文件。以真实保留对象和**假设的**单个路径缺失做[33 条硬链接路径演练](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/snapshot-dedup-preparation/partial-recovery-demo-verification.json)，原快照实际没有删除，恢复组的内容、基本属性和链接数通过自检。这是一个组的演练；调用者仍须绑定可信 manifest／journal、提供全部保护根并处理目录、链接和完整快照拼合。

合成测试分别覆盖持锁闸门 9 项、恢复清单 9 项、分组物化 6 项及事务／对账集成 19 项；未运行 native。审查期间独立子代理的后续复核请求被系统标记为可能涉及网络安全风险而终止，故最新恢复清单与分组物化程序**尚未完成独立复核**；之前已完成的独立复核不自动覆盖后续修改。以上仍不能替代真实执行器、同次 owner 独占、具体授权及维护者对恢复限制的决定。


## 维护者待审：仅清理本轮验证副本的替代方案

为避免先改变尚有恢复及引用限制的 integration 快照，提出下列替代方案：**保留原快照及 21,929 条候选原件，本次不申请删除它们；只申请删除两个本轮创建的临时验证副本**。此方案须由维护者对下表精确路径批准；在此之前均保留。它若获批，取代上文“恢复副本须保留到候选处置后”的顺序：未来如另行申请处置候选原件，须先重新建立完整恢复副本并通过核验，再准备新的一次具体授权；不能沿用当前已删除的副本或将旧检查称为实时结果。

| 待批准的精确目录（均在 `workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/` 下） | 现测独立 `du -s -x -B1` | 保留依据及影响 |
| --- | ---: | --- |
| `snapshot-dedup-preparation/full-restore-validation-20261114/` | 9,285,554,176 字节 | 全量恢复试验副本；原 integration 快照、U5 对象、候选 manifest、工具和校验收据均保留。删除后 `verify_full_restore.py`、`demo_partial_recovery.py`、`verify_combined_sample.py` 和 `run_read_only_gate.py` 原路径依赖失效；要再次运行须先生成并验证副本。恢复试验仍只证明候选普通文件及已登记的属性，不证明完整快照或环境。 |
| `remaining-geophys-ref-preservation-20261114/` | 79,040,512 字节 | 首次 camera GeoPhys 恢复试验；包含专为试验建立的 `camera-restored.git` bare 仓库。v2 的 camera bundle 和 shallow SHA 与其一致，恢复 refs、符号 HEAD 一致，两恢复仓库 `git fsck --full --strict` 均通过；v2 与独立复核保留。首次因对 bare 仓库运行 `git status` 退出 128 的记录保留。 |

两项单独 `du` 之和为 9,364,594,688 字节，既不是保证释放量，也不是 E00～E16 项目累计净节省。原快照约 15.4 GB、U5 包及后续验证资料仍占空间。待审项的[只读盘点](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/remaining-temporary-copy-disposition-inventory-20261114.json)在持主共享锁时记录根 inode、类型和外部硬链接：完整恢复副本 21,929 个文件、19,785 个 inode，首次 refs 试验 32 个文件，两项均无发现的符号链接、跨设备条目或范围外硬链接；首次试验中的 bare 仓库为已明确列出的例外，不能因没有 `.git` 文件名而忽略其 Git 类型。可见 cwd/root/fd 前后无命中，但各有 1,030 次 `/proc` 权限拒绝，无法排除不可见及 mmap 使用或检查后变化。逐条身份快照分别为 [恢复副本清单](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/restore-copy-disposition-inventory-20261114.jsonl)（SHA-256 `e3a2d67502e4a1741238bb35c4fa90e8d1e5fccd84ac3e7a18f11c68396e1654`）和 [首次 refs 副本清单](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/geophys-first-copy-disposition-inventory-20261114.jsonl)（SHA-256 `37fc28effdcfefd294842ab3b7464e8f92cbcc7ac25a33f60782fd7b01d28539`），清单只含元数据而非内容 hash。执行前须持锁再次核对根与全部条目身份、目录权限、挂载、真实 Git/worktree 类型和可见活动；遇变化或冲突中止，不能跟随链接或涉及其他目录，并在同一包含保留材料的范围前后测量空间。

[独立处置复核](../../../../../../workspace/maintenance/v211_e11_e16_independent_review_0506ae26/u6-temporary-validation-copies-review.md)独立核对两个目录的类型、权限和内部硬链接，并重算 561 个 U5 对象；认为二者可作为单独批准的候选，要求执行前重新核验保留材料、活动、身份及权限。本次未重哈希完整恢复副本，核查不能排除不可见使用者。

获批后的执行安排：只处理上述两根目录，先持现有共享锁，复核四保护 SHA、两 pins、原快照、U5 内容与 manifest、v2 bundle 和 HEAD／refs；逐项核对盘点身份、类型、设备、硬链接与当前目录写权限，读取 `/proc/locks` 并扫描可见使用者，出现冲突或任何无法解释的变化即停止，不以旧收据替代当次检查。采用限定两根目录的 no-follow、目录描述符相对操作，不递归跨挂载、不 chmod、不触及同级文件；删除前在候选外持久记录预检及目标身份，逐目录记录结果。若执行异常或进程中断，停止另一候选，保留原快照、U5、v2 和日志，列出已删除、剩余及不确定项，经复核后另行处理，不宣称自动回滚或继续重试。不可见、仅 mmap 和非合作并发活动仍无法由扫描完全排除。删除后复查保留材料与保护 SHA／pins，同范围实测空间变化并提交实际收据。

其他所有 worktree（包括 locked archive、camera、core-baseline、旧版 checkout）、主锁及旧锁、四保护输入、pins、第三方源码、版本 refs/tags、U5 证据、原 integration 快照及其候选文件均**不在此次申请内**。camera 存在主 checkout 指向它的 134 条绝对链接，归属及引用尚未闭合。U6/U7 和维护者项目接收仍 OPEN，本表不是最终项目接收。
