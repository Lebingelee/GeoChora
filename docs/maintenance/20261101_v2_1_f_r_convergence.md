# v2.1.0：F／R 清理与合并后的收敛边界

日期：2026-11-01。维护者已授权先清理 F；R 在独立 camera worktree 清理。本文是当前实施决策，不改变历史验收。

## 发布顺序

1. F、R 分别完成职责收敛、必要验证和本地提交。
2. 维护者复核两份最终交接后，另行授权合并。当前清理包不授权 merge、rebase、cherry-pick、push、tag 或 Release。
3. 合并后统一 GeoPhys 依赖，完成公共任务构造与配置重构，再更新 API、示例和 Skill，完成受影响回归后发布 v2.1.0。
4. R07 Solution 优化、F06 Solution 优化和 F07 延后为 v2.1.x 可选项。

## 两分支共同遵守的接口与职责

| 关注点 | 决策 |
| --- | --- |
| Runtime／Recorder | 继续一个 Core Runtime，复用现有记录 owner；provider adapter 负责 native 生命周期，不新增执行框架 |
| 公共构造 | 保持 `make_env()` 为用户主入口；合并后将任务声明、既有编译器和现有 Artifact／source／Execution 合同贯通，不将内部 `ReferenceTaskBinding` 冻结为公共协议 |
| 任务声明 | 任务提供控制主体、实例、初态、语义和判别；机械臂／夹爪组合、任务特定控制选择和资产准备配方属于任务目录；通用准备机制属于既有公共 owner |
| 配置方向 | 合并后的目标优先级：Core 默认 < 任务类默认 < 任务 YAML < 显式调用覆盖；届时列出并迁移现有 flat／nested 差异。physics 与 renderer 分开声明、按已支持配对准入，不静默 fallback |
| 任务目录 | 合并后向 `task.py`、`specialization.py`、`solution.py`、`config.yaml` 四个业务文件收敛；必要 init／资产不受此数量限制 |
| 计量 | F 按冻结职责清单计量至少 60% 净删减，生产和诊断／测试分别披露；合并后 task.py 至少 60% 瘦身另设基线。R 保持自己的原基线，不相互抵扣 |
| 破坏性收敛 | 维护者允许，但必须先列旧接口／格式、实际 caller、替代 owner、迁移与损失、历史恢复方法。F 清理前后不自行改动 R 依赖的 Core v0／V1 基础合同 |
| 数据 | 活跃 CPU canonical 与 Isaac Generic H5 路线均须有明确当前 reader；不能按 v0／v2／v3 数字推断退役。历史实验 bundle 可随历史代码恢复，不伪造缺失字段 |
| 验收 | 保留独立 source／reset／Target-Ack／T+1／失败-close／unavailable 检测。只重跑受影响证据，容器可打开不能代替语义检查 |

## F 清理的保留与退役

保留 USD delivery／closure／表示选择、官方 Panda 的 Isaac 有界兼容、Menagerie 派生路线、GeoPhys 公共 USD 消费、typed state/control/reset/free-body、F06 Harness→PickCube→三后端执行及冷读。F06 原 9/9 runtime valid、0/9 task success 的人工接收范围不变；不要求此次修好 Solution。严格候选 Harness 的 20-seed all-solved／Oracle／pending Judge 流程也不退役，与三 seed 示例的运行验收分开。

允许退役 F03/F04/F05/DG 的阶段专用候选类、kwargs、布尔分支、worker／supervisor／reader／结果协议，以及严格 DG03 mimic 热更新和 MuJoCo 柔顺／传力逐项等价研究的活跃实现。能力先由最终 source／adapter／receipt owner 承接，再删除旧包装。尤其须先解除 PickCube Isaac 对 `_f05_dg01_scene` 的递归字符串改名依赖。必要 schema／source 检查不能变成无条件放行。

F 清理复用 `develop-full`，不改 R worktree。跨分支共有的 Session、control 和 `SelectedReferenceEnv` 只做本次必需的 F 分支收敛，完整公共构造重构留到合并后。每项退役、承接和检测记录在本次交接中，供合并时逐项核对。

2026-11-01 的 F 清理冻结包为 `sol_f_cleanup_20261101_001`，位于本地 Phase II-01 handoff 工作区。生产代码基线为 `0d066737fbdb6a5103b720b141256550eb49600c`：22 个生产文件／symbol 组计 14,652／13,642 物理／源码行；专用诊断 26,852／24,638，专用测试 8,293／7,171。总计 49,797／45,451，至少 60% 净删减出口为 ≤19,918／18,180；生产独立 60% 设计目标为 ≤5,860／5,456。分别披露实际达成情况，不用删除实验脚本替代生产职责收敛。新增和跨目录迁移代码计回原职责，混合文件内非 F 行为保持。

## GeoPhys 依赖是发布前置

清理期间保留主 gitlink `a53a8cfed7c9d6464274b5c96fca601271dc4ee4`、隔离 USD 候选 `a9e4c4850bd225f5929e74831ac282b18ff517ce`，以及 Menagerie pin。合并后选择覆盖 R 能力、F06 运行链和 GeoPhys/USD 的统一 GeoPhys 提交，再验证。不能仅将 gitlink 改成候选值并宣称兼容。

## 合并前交接必须带回

- 两分支最终 HEAD、保留／退役／新 owner 与 caller 迁移表、实际验证和失败记录。
- Core 共有文件冲突清单，尤其 Session、control、source 和 reference env；R 保留的 V8 identity／动作与 reset 语义不能因选择一侧文件而丢失。
- 当前格式读写与历史 Git 恢复索引、依赖 pin 和未跟踪文件状态。
- 公共任务构造与配置待合并后实施项，以及 source 许可／署名等尚未关闭的发布问题。

维护者将在两分支清理完成后恢复本对话的分支，复核上述材料再确定合并操作。本文不代表已完成合并或 v2.1.0 发布验收。
