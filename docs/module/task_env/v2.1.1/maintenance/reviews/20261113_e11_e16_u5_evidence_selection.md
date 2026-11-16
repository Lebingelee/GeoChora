# E11～E16 U5：有界证据选择与复核

输入 HEAD `0df56e433208bd6c6ccd31e9d0e58d63b85b0766`；U4 独立主审及维护者有界接收沿用原记录。U5 按维护者收窄后的目标自评完成，项目清理与 U7 接收仍 OPEN；没有删除原件、重跑 native 或变更生产代码。输出 HEAD 为本文件所在提交。

[最终包](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/README.md) 中分别保留 [G01 设计](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/stage01/README.md)、[G02 诊断/参考](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/stage02/README.md)、[G03 构建/reset](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/stage03/README.md)、[G04 控制/切换](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/stage04/README.md)、[G05 renderer/主体](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/stage05/README.md) 和 [优化汇总](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/optimization/README.md)。入口列原始事实、复核和边界；不同 stage 或路线不是一次运行，也不宣称当前 HEAD 重跑。

[保留选择](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/retained-claim-selection.json) 冻结 3,056 条 stage 条目及必要 source 索引，共 1,021 个去重对象、572,124,256 内容字节，逐一核对 SHA/长度；同时保留入口、reader、脚本和所引用派生结果。物理目录暂含额外材料，旧索引可能列出未选文件；被舍弃的旧 manifest 不再构成永久闭包要求。原件及临时恢复副本均未删除。

[七项代表性检查](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/core-offline-checks.json) PASS，覆盖五 stage 与五路线联合证据，部分复用已保存 reader 输出。文件系统跟踪观察到所读 179 个包内内容对象均属于保留选择，未观察到成功访问其他 maintenance 目录；此结果不代表所有历史 reader 可重放，也不代表新的物理测量。执行仍依赖外部 Python、numpy、h5py、YAML，部分资产检查依赖 pxr。

T19：四条 CPU 的 H5 completion 不存在，Isaac 为 null；以同次 caller 权威完成事实、实际生成代码、H5 SHA、身份、seed、边界、监督与关闭收据联合支持完成，结论是**联合证据成立，H5 单文件不自含完整 completion**。Isaac `solution-002` 原 1000 步 horizon、seed31，951 步完成、4,755 显式子步、抬升 105.254 mm 并关闭；原失败与空载/方块/RGB 对照为诊断。`external_stop` 和 recording `truncated` 反映后续主动结束，不等于 caller 最后一步的终止标志。

已知边界：原 N08 两份源码字节缺失但失败可由 H5 复算；4b 部分中间源码缺少独立进程字节，沿用主审影响分析；OBJ 的间接 MTL 未保存，现有加载器结果不能推广到历史加载器。记录源码身份不等于独立测量进程加载字节。原 COM FAIL、N08 FAIL、R05c NOT_REQUALIFIED 与原窗口/SDK 边界不变。

U5 本单元生产代码 **0 文件、+0/−0 行**；新增本报告、更新专用账本，证据文件为 ignored 生成物，未提交原始数据。T29～T33 按本有界选择完成；T34 形成目录级初步保留/候选，实际安全处置、引用切换、活动 owner 和锁的执行时复核及授权由 U6 继续，不能据此宣称净空间下降。TEST-04 的有界证据入口已归并，项目整理义务继续 OPEN。
