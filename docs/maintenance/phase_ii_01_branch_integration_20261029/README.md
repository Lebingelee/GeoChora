# Phase II-01 双线开发与 v2.1.0 集成安排

2026-10-29，维护者要求整理历史中间分支，保持F线、R线分别开发，develop及时集成，main指向上一稳定版v2.0.0。复用现有分支，不按子阶段新建Core分支/worktree。

| 分支 | 职责 | 本次集成输入 |
| --- | --- | --- |
| `develop-full` | Luna1，F00–F07；保留现有名称与工作树 | `ad8ee10a7fe7013a94d0b9d7d5ef3269307fd15b` |
| `codex/phase-ii-01-camera` | Luna2，原R01–R07/P99；名称为历史沿用，职责已扩展 | `b5b75dda74adcab6706cb09b875dc64b92485d33` |
| `develop` | 两线已交付checkpoint的集成分支，未来v2.1.0候选来源 | 本次为上述两输入的双parent merge |
| `main` | 已发布/冻结稳定基线 | `v2.0.0^{commit}` = `3759f917b80adb0b7df361c0928d6aff2e4cf1ec` |

## 集成与执行窗口

本次在独立temporary index/文件快照中完成merge，不切换或修改两个Luna checkout，不新增Git worktree。R05b正在camera执行，纳入develop的仅为其开始前R05a接收提交；在途代码和新Provider pin均排除。准备期间F线新增F02 Sol接收提交ad8ee10，本次一并集成该已完成接收记录；接收仅限source contract/fixture，不表示provider runtime已准入。代码/文档合并不证明跨线runtime组合已验证，未启动native或行为回归。

此后每个完整交回窗口由Sol审阅实际diff/Evidence，按所记录状态推进develop；未完成窗口不得被移动HEAD、追加prompt或强行merge。两个topic需要同步集成变更时，先等完整报告/窗口释放，再准备包含新HEAD的一个完整包。两线仍共用native排他锁。

最终v2.1.0需要F线与原R表各自required出口、历史处置与总验收齐备后，再冻结source/Provider pins、验证组合并单独授权tag/发布。当前没有创建v2.1.0 tag，也不继承未完成或诊断证据为正式Qualification。

## Harness来源已合入

最新fetch核实 `public/develop-harness` 位于 `9d0b3e524d67105e67ddb98e6dec903f19eb4255`（PR #1合并提交，包含源提交 `710b42253dae2ce0175c3c51eee97d0ce83fabeb`）。它已经是develop-full的祖先，F线比该源分支新增80个提交。`5d890891ac6172d343d0cd904768bf415e0f9907`将此前Core阶段整入以Harness为基线的develop-full；F00修复和验收继续在该分支完成。本次develop双parent merge自然包含Harness，不重复cherry-pick，不删除协作者的远端交付分支。

## 历史topic清理与恢复

仅删除已完整包含在后继提交中的两个本地中间topic名称：

| 已退休topic | 保留的精确提交 | 其他可达性 |
| --- | --- | --- |
| `codex/phase-ii-01-p00-20261023` | `0d11d33ee6e6a9b09f2924b3450bbedff9aefd91` | F线与develop祖先 |
| `codex/phase-ii-scope-freeze-20261023` | `3759f917b80adb0b7df361c0928d6aff2e4cf1ec` | v2.0.0 tag/稳定分支及后继祖先 |

删除前备份到ignored `workspace/maintenance/phase_ii_01_branch_integration_20261029_001/retired_topics.bundle`，经git bundle verify确认完整；refs前后、精确映射、哈希与操作收据在同一目录。恢复可从bundle fetch对应旧ref到本地branch，或直接从上表精确commit重建。旧报告中的branch名保留签署时点语义，原commit/raw不变。

保留v1.1.0/v2.0.0稳定分支与annotated tags；保留archive_v1_0_0及其他历史detached worktree，不清理ignored Evidence或submodules。本次只更新本地main/develop并退休上述本地topic；未获得单独push指令，远端refs保持fetch核实时点。
