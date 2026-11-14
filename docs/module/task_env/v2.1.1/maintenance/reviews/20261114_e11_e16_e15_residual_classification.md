# E15 剩余输出分类：第一轮核验

输入 `932a98dc`。按照[独立项目复核 R1～R4](20261114_e11_e16_final_project_review_e3f13d72.md)，E15 仍 OPEN；本记录是分类工作进度，不是最终保留／删除决定，也不授权删除。E11～E14 与 U4/U5 既有接收保持不变。

对主 maintenance 的 102 个 G01～G05 目录和 integration 快照补集进行不跟随符号链接的只读枚举，记录 **69,542 个普通文件、6,637 条符号链接**，扫描错误 0。[逐目录表](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/directory-classification.csv)、[逐文件事实](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/files.jsonl)和[初步逐文件类别](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/file-claim-classes.jsonl)将保留 claim 原路径、冻结 stage 对象的内容匹配、非冻结 U5 对象、锁／Git、链接和未决内容分开；仅扫描对象大小可能匹配 U5 的文件才计算该比较哈希。内容相同不证明当前 caller 或资产闭包不需要原路径。

102 个目录中，27 个包含 U5 冻结 stage 原路径，54 个含其他 U5 内容匹配但无冻结 stage 原路径，21 个未发现 U5 内容匹配。逐文件中 1,166 个冻结 stage 原路径均与其所选对象 SHA 相符；另有 19,761 个文件内容匹配冻结 stage 对象，407 个只匹配当前存在但尚未证明属于冻结 stage 选择的 U5 对象。锁路径及 6,637 条符号链接单独保留审查；29,528 个文件暂为未决内容／缓存。文件分类按优先级互斥，不把这些数字相加当可删量；未使用历史目录名或无引用扫描作为最终处置证明。

[快照与主路径比对](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/snapshot-comparison-summary.json)覆盖快照中 18,498 个 `workspace/maintenance` 普通文件：18,066 个与当时主路径内容哈希一致，430 个主路径不存在，2 个同路径大小不同。两个不同项包括历史 kinematics JSON 和 Python 字节码，保留待具体归属；18,066 个依赖主路径继续保留，不能在另行处置主路径时同时假设两份均冗余。对 430 项，主路径分别在此前已清理的 G04 4b/4c 目录，合计 121,502,685 逻辑字节；经核对没有对应 U5 stage 最终选择、stage 索引或 selected-source-trees 原路径，已生成[逐项 SHA 候选](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/snapshot-retired-unselected-candidates.jsonl)，清单 SHA-256 `753b8f89651f15564eb6fb3b455f8bca7526a3ae1757cc0314d87cd7527cd4a3`。这只是保全和用途待核的候选，不排除其他引用，不是删除许可。

快照其余材料包括约 1.2 GiB GeoPhys Taichi 缓存和约 266 MiB CodeGraph 数据；这些是待核验的重建候选，而非凭名称直接删除。快照还包含原地无法用同一主路径证明重复的 ignored 项、链接及主审所列过程材料，须结合 U5 保留索引、当前测试和必要诊断作最后处置。E11～E16 本轮产生的 U3 运行、三工作树保全、审查和执行收据也须分别按 claim 与恢复义务分类，不可直接当作缓存整体删除。

[有序同口径基线](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/ordered-du-baseline.json)：102 个 stage 根目录 **23,108,485,120 B**，其后快照 **6,114,316,288 B**，合计 **29,222,801,408 B**。GNU `du` 按此顺序对共享 inode 计一次，这不是预计可回收量；本轮新建分类材料另计。后续执行前仍需活动锁/路径/权限核验、明确必要材料归位和统一的具体删除授权；历史累计精确净额仍 UNKNOWN。

现已另外标出[25 处历史输出内的缓存候选](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/owned-cache-candidates-measured.json)：Isaac 每运行自有 `isaac-kit-cache`／副本、一次历史 `source-import/cache/ov`、快照 GeoPhys `.taichi_cache` 与快照 CodeGraph 数据，共 6,364 个普通文件；观察到候选内部符号链接 0，冻结 stage 及 selected-source-trees 的原路径均无候选子项。部分历史 runner 收据明确将对应目录记录为运行缓存；历史收据本身继续保留。候选目录按清单顺序 `du` 共 **11,805,884,416 B**，只描述候选范围的当前占用，不是扣除其他归并或共享路径后的最终净收益，也不是删除许可。执行前仍须核验当前使用、挂载、目录权限及最新引用；不包含全局 SDK 缓存。

继续按明确的历史运行缓存路径核查，另列 [34 处 Taichi 运行缓存候选](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/taichi-cache-candidates.json)，7,379 个普通文件、符号链接 0，与冻结 stage 和 selected-source-trees 原路径无交集。两组共 59 处按同一次有序 `du` 为 **13,717,110,784 B**；仍不是已实现净节省。[初次持锁预检](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/cache-owner-permission-preflight.json)未发现可见路径使用者、非规范根、嵌套挂载、不可写目录或扫描错误，但 `/proc` 有 1,036 次权限拒绝，执行前必须重新核对；保全与执行方式也未最终签定。缓存候选仅限列出的历史输出内目录，不含外部或全局 SDK 缓存。

在 `v211_g05_5c_human_diagnostic_attempt002` 中另发现四份不在冻结 stage 原路径选择中的独立主审记录，包含 human 接口维护者范围决定及 unit 2／3 的有界审查结论。为支撑这些历史决定，已把四份原文（合计 15,537 B）归位到[独立保留位置及来源／SHA 清单](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/retained/g05-human-reviews/manifest.json)，再次逐份核对原件与保留副本哈希；不代表新 native 运行、不改 U5 冻结选择。另有 690 条现存源路径与 `selected-source-trees.json` 对应对象 SHA 一致；该 draft 索引仍需结合最终保留选择判断，不能自动扩大 claim。

59 处缓存已在共享锁下生成[精确候选清单](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/cache-exact-candidate-manifest.jsonl)，含 1,425 个目录、13,743 个普通文件的设备／inode／权限／大小／mtime 等；未对可重建缓存复制内容，清单 SHA-256 `06895f69c4ef09f8fa516196b4f65c11f7470e8c005d10d3d808e9cd5536be9b`。缓存内发现的锁标记均未与共享锁同 inode，但删除前仍须检查当前持锁和活动情况。此清单只是候选，其他未决项尚未合并成最终集中授权清单。
