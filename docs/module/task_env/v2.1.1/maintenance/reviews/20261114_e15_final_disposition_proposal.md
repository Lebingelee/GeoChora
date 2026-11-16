# E15 最终保留及集中处置方案

**状态：待维护者对本终稿中的新增删除集中授权；尚未删除、尚未作项目接收。** 本方案执行新的 E15 Goal，不重开 E11～E14、U4／U5 和 E16 已接收范围。范围及数字是点时结果，执行时还要在同一把共享锁内复核；清理后的实测和 E16 最终接收入口尚未形成。

## 最终保留与必要证据

[最终保留结论表](20261114_e15_final_retention_conclusions.md)列出 G01～G05 及优化六项的原源码／配置／运行身份、必要原始结果和资产、读取入口及已接收边界；其入口分别是 [U5 总入口](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/README.md)和包内 stage01～stage05、optimization。各路线并非全部在同一 HEAD 重跑。T19 是同次联合证据成立，H5 单文件不自含完整 completion；原 N08 FAIL、COM 原严格 FAIL、R05c NOT_REQUALIFIED、4b 中间源码缺口和 SDK 关闭限制照旧。原 integration Git 管理元数据损失也不改称已恢复。

本次复用已接收的包内七项离线复核和读回收据，并重新对最终选择中的 **1,021 个不同内容对象**验证大小和 SHA，覆盖 3,056 条 stage 选择及 13 个 supporting source 索引：[对象检查](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/final-selected-object-sha-check.json)。这证明选定对象的字节可定位，不证明历史进程加载字节，也不代表本次重跑了完整 Solution。表中已接收的源码／完成事实限制不是新缺口；**目前未发现必须新查或复制才能支持该表的具体缺失文件**。保留实际 H5、图像、同次 caller／监督／关闭收据和 source，以各自索引身份解释。

285 套 Panda 网格共 19,095 个路径、67 种内容，已有的 [Panda 内容与运行映射](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/panda-mesh-retention-mapping.json)关联 U5 对象及选中 source/receipt；67 个对象已重算 SHA。四个 receipt source 布局和 G05 cross 的 69 文件包内布局已核对。四个当前 fixture 链接有效；当前 tracked 非文档文件对 102 个旧 stage 根名的字面扫描无命中。当前 Panda 正式 source 使用保留的 Menagerie，而非这 285 套历史副本。抽查的现行 U5 reader 从包内对象读取；旧路径可作为索引键，历史收集／重建工具中仍存在旧 stage 绝对路径，其旧路径收集能力随旧目录退休，不保证继续运行。静态检查不能排除外部或动态拼接的历史调用，OBJ 间接材质和原进程内加载字节仍按原边界说明。

## 精确范围及处置结果预期

[103 根目录级处置表](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/final-root-disposition.csv)逐根列出绝对路径、数量和逻辑字节：102 个 G01～G05 历史输出根，以及 integration 剩余临时快照。**精确对象以 [范围逐项清单](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/final-scope-files.jsonl)为准**，SHA-256 `5bebe7b9e8c659041792c0d70dd58f836b1be25e159524e910d45c23efff6d37`；其 `category != exception` 行为本次新增删除候选，`exception` 行及其全部祖先保留。目录身份和可移除空目录以 [目录清单](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/final-scope-directories.jsonl)为准，SHA-256 `ca15139b4b09ad3ce5083bb978d08aed047cb2452e0af7aeaa60095d8939fbee`。仅删除清单中的文件／链接及已核实为空的列名目录；不得递归删除含例外的整根。

| 项目 | 拟处置或保留 | 重要边界 |
| --- | --- | --- |
| 重复 Panda 网格 | 19,095 文件候选，原路径、SHA、内容对象关联保留；[专项清单](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/panda-mesh-285-candidate.jsonl)与总清单交叉使用 | 同内容一份、运行身份分别解释；19,095 原件本次没有重新逐个计算 SHA，沿用既有结果并核对了文件身份 |
| 历史自有缓存 | 62 组 Kit/OV/Taichi 等缓存、29 组 OptiX 自有缓存及其他清单内可重建产物随范围候选清理；[既有缓存清单](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/cache-exact-candidate-manifest-v2.jsonl)、[OptiX 清单](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/stage-optix-cache-candidate.jsonl)为分类依据 | 清单与总清单有重叠，不能重复计数；不碰全局 SDK cache、安装资产、第三方原件或外部项目 |
| 其他历史输出 | 50,445 个普通文件候选，包括已选对象的原位置副本、未选历史结果及其私有缓存；仅已选结果及另列成果由 U5 或现有保留集支撑 | 这不是声称所有文件内容相同；未选旧 attempt、manifest 与早期成功 H5 不保证可完整重放。旧报告的过程链接不生成新的保全义务 |
| 历史链接 | 6,637 条链接候选，包括 257 条旧 overlay；原始 link target 保留在总清单和 [旧映射](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/snapshot-symlink-provenance.jsonl) | 仅 unlink 链接本身，绝不跟随或修改外部目标；目标映射不是旧环境可复现证明 |
| 私人输入例外 | integration 快照的 `temp_outputs/auth/auth.txt` 及祖先保留，不读取其内容 | 36,889 字节；不可整根删除快照 |
| 既有历史更正例外 | `v211_g05_5c_unit005_isaac_continuation_20261110_002/isaac-loader-order-001/app-first/events.jsonl` 原件及祖先保留 | 226,129,691 字节；此前已用于 [历史更正](20261114_g05_isaac_loader_history_correction.md)。它不是最终接收结论的新增必要核心证据，也不要求继续调查该历史矛盾 |
| 本轮临时副本和过程草稿 | [157 条精确候选](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/final-scratch-candidates.jsonl)，185,195,233 逻辑字节，SHA-256 `d896770fb6e4326a4bdd2095e7b006366fafa66c5ca557e72cec9359d1237697` | 含 147 个与 U5 对象 SHA 相符的新增重复归位副本及 10 份被最终清单／v7／v3 取代的旧分类草稿。旧草稿历史引用以新清单和 v7／v3 映射；147 份旧 retained manifest 中原副本路径退休后不再直接有效，以本清单 `retained_object` 与 SHA 关联 U5。最终清单、必要审查记录、U5 对象和保留索引均不删除 |

总范围清单为 69,542 普通文件和 6,637 链接；其中两项普通文件是例外，**76,177 项**列为新增删除候选，普通文件合计 **28,719,167,127 逻辑字节**。另有上述 157 条分类目录候选，不包括在这 76,177 项中。逻辑字节不是预计释放的分配字节。候选包含既有阶段性授权涉及的对象时，本次仅把它们归并入终稿，不改变或扩大既有授权；本终稿中尚未授权的对象需集中确认。

其他保留项：U5 包及内容对象、优化运行和当前短程 H5 证据、当前代码和 fixture、共享锁与旧锁硬链接、四项保护输入、两个 submodule pins、第三方原件、其他项目及锁定的冻结 archive，均不在上述清单内。当前运行锁为 `workspace/locks/shared_native_execution.lock`，旧 alias 与它同 inode，不可单独 unlink 造成双锁。

## 检查结果及执行方法

[点时范围预检](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/final-retention-scope-preflight.json)取得共享锁并检查可见进程及历史锁，未发现冲突；受限 `/proc` 访问 1,048 次，不能证明不可见或非协作进程不存在。未发现范围内嵌套挂载或已登记 worktree。重新不跟随链接枚举的 76,179 个文件／链接及 24,661 个目录与清单一致，扫描问题 0。独立只读复核逐项核对了路径、身份和原始链接目标，未发现当前共享锁或 U5 选中 stage 对象与候选 inode 冲突；它不证明全部动态／仓库外 caller。586 个目录为本人拥有的 `0555`：快照内 368 个、stage 内 218 个；具体路径和身份见目录清单与 [权限结果](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/final-scope-summary.json)。

获得本终稿授权后的受控执行顺序：

1. 在同一把已验证双路径身份的共享锁内，重新检查实际持锁者、相关可见进程、挂载、worktree、四项保护输入、pins、U5 对象及清单 SHA；清单逐项 `lstat` 核对设备、inode、类型、大小、mtime、链接数和链接原始 target。新增或变化对象、锁冲突、意外挂载／`.git`、权限异常使相关批次停止，不把变化自动并入授权范围。
2. 对 586 个列名 `0555` 目录，只在确认身份及 owner 后按需临时增加 owner 写权限；逐目录记录原模式、变更和恢复状态。保留的祖先和任何中断时尚在的目录恢复原模式；权限不可恢复或归属变化即停止受影响批次并保留日志。已有权限调整授权不扩展到其他目录。
3. 逐项依据总清单 unlink 列名普通文件与链接本身，采用目录 fd、不跟随符号链接、验证父目录及目标身份；不使用递归通配删除，不越挂载，不跟随外部链接。每批记录意图、成功、失败和中断状态；对于两项例外，保留其全部祖先。按深度逆序仅移除清单中已确认空且不含例外的内部目录；103 个范围根本身可作为空锚点保留，不跨出范围修改其父目录。中断后先根据日志和当前身份对账，不盲目重试。157 条临时副本同样逐项核验并独立处置，U5 关联对象始终保留。
4. 复核包内选定对象、必要离线 reader、当前 fixture、共享锁、保护输入和 pins；按下面同一有序范围实测结果，登记实际剩余及保留例外，再交独立复核和维护者作最终项目接收。

**执行器与中断边界：**[受控入口](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/dispose_final_scope.py)固定四份清单 SHA；`--check` 只读检查现存对象与范围（不写旧收据）。清单外保留 14 个 U5 选择／source 索引的固定 SHA。隔离合成测试覆盖正常执行、清单漂移、锁替换、日志失败、SIGTERM、SIGKILL、两项例外及 scratch；使用临时真实 flock 和 `/proc` 扫描，但保护输入／pins 为空、U5 校验为替身。原语另测不跟随外部链接、权限恢复；未穷尽每个系统调用处的中断，SIGKILL 恢复需人工核对。真实范围另做只读 `--check`，不等于已执行或验证了全部崩溃场景。[测试和脚本身份收据](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/final-executor-test-receipt.json)记录脚本 SHA 与结果；scratch 父目录身份清单 SHA 为 `eb247b1ddc349d0a88d5953bac24c89ab5d8392efc9c22c37d0232115eef3d0e`。执行入口须在取得本清单授权并完成锁内复核后才能对真实范围启用；无权运行旧 `candidate_transaction.py` 原型。SIGKILL／断电可能留下已记意图但未恢复模式的目录，不保证自动恢复。

中断时禁止自动续跑。[只读对账辅助](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/reconcile_disposal_journal.py)始终要求人工复核，不能证明执行完成。维护者或实施者持共享锁后：固定日志及四份清单 SHA，逐项将 intent／完成记录与当前 `lstat`、inode、链接目标和 U5 保留对象对照；对未闭合目录先核对 inode／owner，再恢复并复验原模式；对缺失但无完成记录、重现／替换路径、日志缺损或清单漂移标记不确定并停止相关批次。仅在全部候选及例外完成逐项对账、U5 和保护项复核、实际空间测量及独立复核后才可报告完成。不能凭日志末尾单个事件或文件消失推定完成。

## 空间核算

[同一次有序 `du -s -x -B1` 基线](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/final-space-baseline.json)依次包含 102 个 stage 根、快照、U5 包、当前分类目录，硬链接按该调用顺序只计一次：stage **23,108,485,120 B**，快照 **6,114,316,288 B**，U5 **812,830,720 B**，本轮分类与保全目录 **544,112,640 B**，合计 **30,579,744,768 B**。测量后生成的清单、执行器和日志也要包含在实际后的同一范围；若范围有被移除的根，按零计并保留同序记录。U5 和本轮分类目录已在范围内，不可只报告旧目录减少；再报告 retained U5／分类占用及新产生量。[点时目录／文件及逻辑字节清点](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/final-count-baseline.json)分别记录路径总量与去重 inode 总量，执行前后应即时重测以计入新增日志。该基线是本次清理前点时值，尚无本次实际下降；U5 建立前的累计精确基线缺失，E00～E16 历史净额仍为 **UNKNOWN**。

[压缩当前状态](20261114_e11_e16_e15_residual_classification.md)给出接收边界。授权执行、清理后读回和实际空间测量完成前，E15 保持 OPEN；E16 最终项目接收仍由维护者决定。
