# GeoChora P2.0-B — S2-B1 Integration & S2-B2 Retirement Receipt

日期：2026-10-16
状态：S2-B1 已集成到 canonical public `develop`；获准的 S2-B2 exact two-file slice 已于 2026-10-16 通过普通 fast-forward 集成到 public `develop`。B2 实现提交为 `84438d470cce4f5a215a5934fdfc344b91adca30`，经更正的存储风险记录提交为 `a5e8cd0a50b8a79a75037e0c274b0e22d3ebdde2`。

## S2-B2 public integration receipt

集成前重新抓取的 canonical public `develop` 为 `71aadb8aada6c242166a1deadc610c230ba1c616`，它是本地提交链的祖先；工作区无 tracked/untracked 改动。基线到 `a5e8cd0` 的差异仅包含两项获准模块删除、两个历史诊断入口更新、provider-free 收据契约测试及当前维护文档/清单。`git push public HEAD:refs/heads/develop` 以普通 fast-forward 成功，服务端返回 `71aadb8..a5e8cd0`。随后仅为本收据追加文档记录；该文档提交也通过普通 fast-forward 发布。`main` 和 annotated `v1.0.0` 标签对象及其 peeled commit 保持不变。

## S2-B1 public integration receipt

执行前抓取的 canonical public `develop` 为 `32bdde9573cc20f8d8b2aafa975422834df2585b`。S2-B1 实现链为 `8ff33b310bd15c8f5fa5e5f8bfae5f0873b64006` → `60fafb689efe89312d4d79b0431c61ebc98642d8` → `961ff67489cf6ed1fd3665fc77db2e3f389796e9`，后者仅补充审查/依赖清单；测试过的 task-source HEAD 是 `60fafb…`，其后无任务实现字节变化。随后 fast-forward 集成到 `develop`，并提交了集成收据 `71aadb8aada6c242166a1deadc610c230ba1c616`。本次 S2-B2 开始时，本地 HEAD 与抓取后的 `public/develop` 都是该 SHA。

S2-B1 provider-free 回归为 157 passed；四个 current-source CPU full-route 收据均为 PASS，分别是 PickCube GeoPhys/MuJoCo 与 NutAssembly GeoPhys/MuJoCo，结果、H5 哈希及其边界/物理步数见 [S2-B1 review receipt](p2_0_s2_b1_review.md)。该 Evidence 是有界功能回归，不代表 P1.8 FULL 或 D0-D2 qualification。

本次未对 `main` 或 `v1.0.0` 写入：公共 main 保持 `e4e39883fbe01d4be4b172a53a535ef0095b3d64`；v1.0.0 annotated tag object 保持 `17c3100d4fabcb061c23569dea49973ebd177d51`，peeled commit 保持 `42787f5e4f658a3f81fdd2140cf7544d6342c783`。

## S2-B2 exact retirement diff

本地实现提交 `84438d470cce4f5a215a5934fdfc344b91adca30` 基于 public/develop `71aadb8…`。仅删除获准的两个候选模块：

| 删除路径 | 删除前 SHA-256 | 退役调用身份 | v1.0.0 恢复 blob |
|---|---|---|---|
| `task_env/tasks/nut_assembly/clearance_candidate_v4.py` | `10067cbdea578c17c9a1659667e8dbb5edd081ab362b2ad16b1fcdd8a53b3f83` | `NutAssemblyHandClearanceCandidateV4`, version `nutassembly-r5-stable-grasp-10n-lifecycle-v2-handle-clearance-v4-live-settle`; CLI choice `handle-clearance-v4-live-settle` | `6251ac1d861ab41c14379b3fd9af7cd9e82034e3` |
| `task_env/tasks/nut_assembly/stable_grasp_reference.py` | `b51c054bb997e294d9e3605a28d86eec1dfc253589f3da1578078a64a6908324` | `NutAssemblyStableGraspCandidate`, version `nutassembly-r5-stable-grasp-10n-v1`; module import and `stable_grasp.py --reference` | `e8cc8880ddf2e5342c74d8ef63a8acd6696f5bb9` |

`git rev-parse v1.0.0:<path>` verified both recovery blob identities before deletion; both are present in the frozen release. The exact deleted-module paths and source/recovery identities are also retained in the refreshed [S2-B deletion manifest](p2_0_s2_b_deletion_manifest.json). The following frozen report hashes were recorded before and after the edits and remained unchanged:

- `docs/module/task_env/p1_8_integration/final_diagnostic_replay_20261014/source_identity_reconciliation.json`: `2610dd7595b92daba9ec8b5bc3a806581c1f3d6777496437e9a1c6409ece38a6a`
- `docs/module/task_env/p1_8_integration/regression_results.json`: `78a1ebc20a43c83c78e934dada7137004b33ce39d41b6bda959a9a3d456d30ef`
- `docs/module/task_env/p1_8_integration/stable_grasp_integration_report.md`: `a08a7b4f26396ca503b44697ca4825b97fbffcd5e5cdf33e9a251adca20e2018`

### Historical callers and compatibility disposition

- `integration/lifecycle_full.py` was the only direct V4 importer. Its V4 import, `solution_classes` entry, `--trajectory-candidate` choice, and V4 source-hash entry were removed. Invoking the retired choice now gets argparse exit 2 (`invalid choice`). V3, V5, guarded V1/V2, and task-owned routes remain as they were.
- `integration/stable_grasp.py` was the only direct importer of `stable_grasp_reference.py`. Its reference-module import and dynamic route were removed. `context(reference=True)` raises a retired-route error; the CLI rejects `--reference` with exit 2 and the v1.0.0 recovery instruction before creating the output directory. It does not alias the call to `stable_grasp_candidate`.
- An AST scan of current `task_env/**/*.py` found no remaining direct imports of either removed module. The active NutAssembly selected construction imports neither module; its Outcome V1 MRO and active source closure remain unchanged.
- These are direct Python module/import and diagnostic CLI compatibility removals. Neither module was exported by `task_env.tasks.nut_assembly.__all__`; selected public UIDs and `make_env` APIs are unchanged. The current v1.0.1 task migration document records the removed calls and recovery route. Historical replay that requires the old selector must use v1.0.0 or its immutable source ref.

## Active task and source identity preservation

The selected active public routes remain `pick-cube-p16-reference-v1` and `nut-assembly-outcome-reference-v1`.

| Route | Preserved task identity | Selected implementation identities |
|---|---|---|
| PickCube | Artifact `pick-cube-v1/p1_6_experimental_100hz`, SHA-256 `fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4`; 100 Hz and lift-only semantics; seed-31 reset sample `reset-ee9644c1af42c7897f79a0cece21e5fc4bd5323ae40eba7b7259d34d681a5fb6` | controller `76108c78b8159391e448ad9f49050bed42fd7a86e0e00a0520083b4e5efb02e9`; solution `fcef1d3a9c093a1d0adfce394a44099f5bff61edae48b3dce2ff50406118cd61` |
| NutAssembly | Artifact `nut-assembly-square-v1/p1_8_e/nominal-v1`, SHA-256 `99e374bd870c70f0dd427e34c47c6e6820aaa7067365133181a001a38239b9fe`; Outcome Completion V1 | Outcome Solution `4bf902b9b0bcc84955e9d51177c5811e65e02b2b540678fa14235d13d7cad923`; policy `a940c6cfc4b9dbe64ae55b615e7bdbd9a210dc7495c6337b08cff688c52694ee`; guard policy `065af38f034f896d3003d8f63cfb2ea9acac3adcefe078b678bd7596d57a0674` |

NutAssembly's provider-specific controller identities remain GeoPhys `cad9c5d2c1a619bc2ae94e240e7d4fb632b60599a7073e5c5adc616af0311a8f` and MuJoCo `ce29b631ef50e842bbc0d51a5350ac668e9dca431caefc6a57afeedeb2ee05f3`; recipe identities remain `84912989baf66361da3db2f5dbd3f514c0a509ccf1aac479f0639ed567bfa3a5` and `c6747b2634c50f00703df2f09db179eb0e806cd6bfb411e79155d95b7e35ec46`. Artifact, controller, solution, policy, reset, source XML, warning admission, physical limits, recorder and strict lifecycle semantics were not edited.

The S2-B1 identity record has 18 tracked source-file fingerprints; all 18 still match. Neither retired module is in the selected task source map. The active NutAssembly inheritance still includes the required V2/V5/R3 and selected candidate bases; no MRO simplification or candidate-base deletion occurred. The old module identity maps to `retired from current develop` while its v1.0.0 blob remains the recovery identity. No selected TaskArtifact or task-source identity changed, and no historical qualification was inherited or relabeled.

## Regression results and limits

The provider-free suite passed **168 tests in 17.60 s** on the S2-B2 source. It includes API/import, Artifact identity, task semantics, reset, selected Outcome behavior, controller/guard/lifecycle, provenance, recording, result-gated trajectory CLI, the two retired-route negative paths, 18 source fingerprint checks, selected Outcome MRO, and provider-specific native-step/clock contract tests. The new receipt-contract tests promote reusable T/T+1 boundary, 100 Hz ULP clock, PickCube GeoPhys grouped-step, and direct provider native-step checks from the ignored S2-B1 verifier into tracked regression code. `compileall` and `git diff --check` passed.

The four native routes were not rerun: this slice changes only historical diagnostic selection, removes modules outside the selected source closure, and adds provider-free receipt validation; no selected execution dependency or configuration fingerprint changed. Prior S2-B1 full-route PASS results remain the latest native evidence. No D0-D2 qualification is inferred. Existing ignored failure receipts and H5 outputs were not overwritten.

The later kernel-journal review found an Oct 15 ata5 `BadCRC` event followed by failed queued reads and `/dev/sda` READ I/O errors at sectors `1922308096` and `1922310144`. Direct `dmesg` access was denied, so the earlier empty result was not evidence that the kernel log was clean. The maintainer subsequently confirmed that the storage issue was handled and explicitly authorized bounded GeoPhys/MuJoCo CPU full-route and H5 tests. This authorization supports the upcoming S2-C1 validation; it does not erase the historical error receipt. Preserve the known single-disk SATA and independent-backup limitations in active risk records.

## Remaining active legacy dependencies and recommendation

This is the complete authorized S2-B2 retirement slice; no further deletion is part of it. Active and mixed-support legacy dependencies remain, including selected NutAssembly `clearance_candidate_v3.py`, `clearance_candidate_v5.py`, guarded authorization candidates and their Outcome V1 MRO; task-local generic artifact/reset/semantics/config/controller/execution contracts; and historical PickCube/NutAssembly `task.py`, candidate and solution support with existing historical callers. They were not removed or copied. Generic Core lifecycle/provider/controller/recording contracts, Go2 and custom static physics are untouched. S2-B2 is ready for maintainer review as a scoped local change; do not merge or push it until reviewed.
