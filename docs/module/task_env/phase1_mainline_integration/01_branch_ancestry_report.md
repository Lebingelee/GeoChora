# Phase-I 分支关系审计

起始 integration：`1f1cd67c56ea30e7b2c14f03a9a4dc6ca7bccbdd`。审计 fetch 后 public/main：`f977528b9b9866c50afcf8ea9b5f5deadce60892`；public/integration：`5c8ac356d46c521f768367a7a90622249535e6cc`；P1.6 closure：`761f1fde7fb0d2831ab5ee780821637c0f7e6215`。

P1.6 与本地 integration 的 merge-base 为 `cda511f49eb544dabe685ec1dbcc6345884d66c8`。P1.6 独有 12 个提交，本地 integration 独有 42 个提交（远端 integration 比本地少一个 loaded-episode runner commit）。采用正常 Git merge，合并提交 `be47e72fe81790813b784cb1a47c91d2f59b68ab` 同时保留两侧 parent 与全部原始历史。main 是整合 HEAD 的祖先。

| 来源 | 纳入决定 | 范围 |
|---|---|---|
| P1.0–P1.5 公共 lineage | 保留已有 ancestry | contracts、runtime、conformance、camera、R1/PickCube |
| public/codex/p1.6-closure | Git merge，12 个独有提交全部纳入 | Flow/V2a、quantile normalization、horizon padding、100 Hz diagnostics、D3、bounded approval |
| codex/p1.8-integration 本地 HEAD | 保留起始全部源码 | 四 provider adapters、persistent R3、10 N development recipe、v0/v2 recording、clock、owner snapshots、T1/full runner |
| P1.6 未提交历史 diagnostic overlays | 有选择恢复四个入口 | 原始补丁/源码已单独保存；非 learner/controller 行为重写 |
| P1.7 | DEFERRED | 未发现独立已批准阶段或完成分支；没有生成实现或批准 |

完整分支 HEAD、merge-base、独有提交和本次起始 worktree inventory 保存于本地审计 `branch_inventory.json`。原始分支、archive tags 和 worktrees 均保留。本次没有修改其它工作树的 dirty 文件。

P1.6 七个 learner 文件与原闭合分支 byte-identical；P1.8 147 个 control/runtime/task/planner/trajectory 文件与起始 integration byte-identical，详见 [源码对照](source_identity_proof.json)。

## Audited refs

| Ref | HEAD | Branch-only / integration-only |
|---|---|---|
| codex/p1.1-overnight-contracts | `1fde9dcb235bf7ea4f4d31268864b2507efb7003` | 0 / 67 |
| codex/p1.2-4h-runtime | `22b0a229a741a7e7f11663cd5a0635e3ed6053c4` | 0 / 66 |
| codex/p1.3-4h-conformance | `4db06e6f740a70b51cbf2eec87771321ba02d864` | 0 / 63 |
| codex/p1.4-4h-camera | `d983d31c107bead06e3f0f22a0bc2085044d08d8` | 0 / 61 |
| codex/p1.5-4h-control-expert | `9c5fcc26fa1164baccd72bfca450d79187b27470` | 0 / 57 |
| codex/p1.6-closure | `761f1fde7fb0d2831ab5ee780821637c0f7e6215` | 12 / 42 |
| codex/p1.8-integration | `1f1cd67c56ea30e7b2c14f03a9a4dc6ca7bccbdd` | 0 / 0 |
| public/codex/p1.1-overnight-contracts | `1fde9dcb235bf7ea4f4d31268864b2507efb7003` | 0 / 67 |
| public/codex/p1.2-4h-runtime | `22b0a229a741a7e7f11663cd5a0635e3ed6053c4` | 0 / 66 |
| public/codex/p1.3-4h-conformance | `4db06e6f740a70b51cbf2eec87771321ba02d864` | 0 / 63 |
| public/codex/p1.4-4h-camera | `d983d31c107bead06e3f0f22a0bc2085044d08d8` | 0 / 61 |
| public/codex/p1.5-4h-control-expert | `9c5fcc26fa1164baccd72bfca450d79187b27470` | 0 / 57 |
| public/codex/p1.6-closure | `761f1fde7fb0d2831ab5ee780821637c0f7e6215` | 12 / 42 |
| public/codex/p1.8-integration | `5c8ac356d46c521f768367a7a90622249535e6cc` | 0 / 1 |
| public/main | `f977528b9b9866c50afcf8ea9b5f5deadce60892` | 0 / 71 |
