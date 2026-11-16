# E11～E16 三处停用工作树集中处置提案

状态：维护者已同意本清单及两项具体例外；[执行结果](20261114_e11_e16_three_worktree_execution.md)已记录。下文保留决定前的原始条件和边界。冻结 archive、主 checkout、版本分支及 tags 保留，不进入 G06。

| 精确候选及冻结 HEAD | 删除拟包括 | 拟执行方式与具体限制 |
| --- | --- | --- |
| `/home/lly/.codex/worktrees/phase-ii-01-camera/Geochora`，`2cba22d99c75eca6670b4f117bc1d9dd9193ca52` | 此工作树、其 ignored 缓存和已保全的子模块副本，以及 Git 自动移除的对应管理目录 | 确认锁与进程、保全和路径身份；仅在获批后对[已登记](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/camera-permission-precheck.json)且身份仍一致的 61 个用户自有只读目录补最低必要权限（其中 60 个位于 scratch/upstream，包含第三方 LIBERO／robosuite source 快照，属于原 Goal 排除的第三方 source，须在本次决定中明确列入例外；文件内容复用不证明目录／链接／元数据完全相等）；**若维护者明确同意子模块限制的具体例外**，执行一次 Git 官方 `git worktree remove --force`。包含已初始化 GeoPhys 和 Menagerie，不运行 deinit；出现失败或部分失败立即停止，不自动重试或改用手工删除。 |
| `/home/lly/Program_Files/Geochora/workspace/maintenance/geophys_upstream_reset_20261022_001/core-baseline`，`60b3ecac872eb2626c8bfb3683aba29ee5625262` | 该工作树内文件、缓存和两条链接本身，以及 Git 自动移除的管理目录 | 对保存的两条外链核实 inode、链接文本及父目录身份；仅在授权后以不跟随方式移除链接项并建立未初始化 gitlink 空目录，核对 Git 状态干净，再执行一次普通 `git worktree remove`。不对外链执行 deinit，不操作目标；失败停止，不自动强制。 |
| `/home/lly/Program_Files/Geochora/workspace/maintenance/p2_0_v1_1_clean_checkout_20261017`，`bee498d1d784015f034c5b4af34320fdffa61411` | 此工作树、其 ignored 缓存和已保全的子模块副本，以及 Git 自动移除的对应管理目录 | 确认锁与进程、保全和路径身份；**若维护者明确同意子模块限制的具体例外**，执行一次 Git 官方 `git worktree remove --force`。包含已初始化 GeoPhys 和 Menagerie，不运行 deinit；失败或部分失败立即停止，不自动重试或改用手工删除。 |

## 保留和恢复证据

- 三个 Core HEAD 为当前分支祖先；当前主 Git 对象库保留其 tracked 树。camera 另有 5 个 reflog 独有提交，已保存 [bundle 与恢复证据](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/camera-reflog-bundle-receipt.json)，该 bundle 依赖保留的主 Git 对象库。七份工作树及子模块管理资料副本保留于[保全目录](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/)；管理副本排除 objects，不能单独原样重建工作树。
- camera/p2 的 GeoPhys 命名 refs、浅边界和对象保留在 [v2 bundle 与恢复库](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/remaining-geophys-ref-preservation-20261114-v2/receipt.json)；隔离恢复各 HEAD 的 2,854／2,149 个 tracked 文件全部匹配，三个未初始化的嵌套 gitlink 仅保存身份。[恢复与独立复核](../../../../../../workspace/maintenance/v211_e11_e16_independent_review_0506ae26/u7-geophys-restore-deinit-config-review.md)。两个 Menagerie 的已验证同一 tracked 内容及命名 refs/可达对象复用主副本；[对象闭包核对](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/submodule-reachable-closure-20261114.json)不声称覆盖浅边界外或不可达对象。
- camera 的独立第三方 robosuite 已迁到[保全位置](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/third-party/robosuite/)；它本来是部分浅克隆，不声称完整离线历史。五个必要输出根在[保留副本](../../../../../../workspace/maintenance/v211_e11_e16_u7_preparation_20261113_001/remaining-local-outputs-preserved-20261114/receipt.json)校验；camera workspace 其他 3,409 个文件与主 workspace 同路径内容一致。134 条历史链接中 68 项有候选镜像但未证明完整等价，66 项原目标为空或仅含目录；逐项见[映射](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/camera-historical-link-map.jsonl)，删除后旧链接可悬空，不承诺历史目录原位可运行。U5 最终包、约 15.4 GB 原 integration 快照、四个保护输入、两处外部链接目标和当前 pins 均保留。
- camera 存在一条指向外部保留文件的硬链接；删除前后须核对[外部保留路径](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/camera-outside-hardlink.json)的设备、inode 和内容，链接数与 ctime 可变化。独立和实施者复核范围及限制见[详细账本](20261114_e11_e16_three_worktree_disposition.md)。

## 删除前提、失败和验证

三处已由维护者确认停止使用；执行时仍须核查可见持锁者、相关进程、固定共享锁和路径身份，发现具体冲突即停止；操作及失败须记录日志，异常后根据现场重新判断，不预设恢复成功；`/proc` 可见性受权限限制，不以此要求证明未来不会启动。核验四个保护输入和 pins、外链文本与外部目标身份、保全证据及目录权限；不用跟随外部链接。camera 权限只在具体删除获批后调整。若校验漂移或遇未知目录/挂载，停下并重新核对，不扩大删除范围。

Git 官方允许 `worktree remove --force` 移除有子模块的工作树；原 Goal 禁止强删绕过子模块问题。现有保全与解除停用减少风险，但**不能自行视作原限制已解除**。隔离双子模块试验与[独立复核](../../../../../../workspace/maintenance/v211_e11_e16_independent_review_0506ae26/u7-direct-force-two-submodule-review.md)显示 Git 强制移除成功且主配置、主子模块和外部哨兵不变，不证明真实路径无风险。普通 deinit 在隔离多工作树试验中改写共享配置并改变主工作树状态，不能将它当作无影响的替代方案。

先前 integration 的 Git 移除曾部分生效并损失管理元数据；本次即使有现存内容与管理文件备份，**也不能保证失败后逐字节恢复原 worktree Git 管理状态**。失败时保留余下路径、记录 Git 返回和实际登记状态，核查保全与主工作树后报告；不自动补删、不更换命令、不冒称成功。core 如在 Git 移除之前仅完成部分链接替换，也须停止并依据已保存链接文本和身份检查制定有界恢复，不能覆盖未知新路径。camera 若已改权限而未删除，仅对身份仍匹配且操作可安全完成的目录恢复原权限，异常时停止报告。批准本提案需要接受这一失败边界；它不授权其他对象或第二次强制移除。

## 空间与后续

[最新固定有序范围](../../../../../../workspace/maintenance/v211_e11_e16_three_worktree_preservation_20261114_001/three-worktree-space-current-20261114.json)共 **26,922,086,400 字节**，已计入 U5、保全目录与 **15,385,866,240 字节**的原 integration 快照。三个候选在该固定顺序下分别归入 **6,456,983,552／37,482,496／1,993,269,248 字节**；对应 Git 管理目录分别归入 **647,114,752／131,072／617,738,240 字节**。这些是删除前 `du` 值，不保证实际物理回收量或历史累计净节省；保留快照和证据不能扣除。若获批，执行前后同序复测，消失路径记 0，新增日志单列。

完成后复查主 checkout、两处 pins、四保护输入、工作树登记和保留 refs、外链目标、U5 与所需测试；记录实际空间变化和任何失败，再提交独立项目审查与维护者 U7 接收入口。项目最终接收由维护者决定。
