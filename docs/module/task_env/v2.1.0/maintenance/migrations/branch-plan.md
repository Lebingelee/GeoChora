# 本地分支与工作树收口计划

本文件记录冻结包授权的本地分支收口方案。它不是实际收口回执；最终候选 C、前后 refs、worktree HEAD 与受保护文件哈希由忽略的 `branch_closeout_receipt.json` 记录，避免在候选自身写入其 commit 造成自指。

## 冻结输入与保留

- 当前候选输入：`codex/v2.1-integration@a3cd3312614212da1e589add4a6b7447c07e4e8a`，当前阶段 HEAD 以 release-preparation `RESUME.md` 和最终报告为准。
- 遗漏历史 develop：`432b70741b06b8e635bcf1ac1c55009b8f478a6b`，必须以正常 merge 进入候选。
- `main` / 历史 `v2.0.0`：`3759f917b80adb0b7df361c0928d6aff2e4cf1ec`。
- F 输入工作树：`develop-full@5de9c44be4b06e70909db9087ce3d5ceb579e335`。
- R 输入工作树：`codex/phase-ii-01-camera@2cba22d99c75eca6670b4f117bc1d9dd9193ca52`。
- 历史本地分支保持原位：`v1.1.0@f292df149f41520b484ff27cf2ff78a584903013`、`v2.0.0@3759f917b80adb0b7df361c0928d6aff2e4cf1ec`。同名历史 tag 是不同 ref，均保持原 tag object。
- GeoPhys P=`67da1165149486d3ae3e779c13ce31af49e17d50`、Menagerie=`b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`、全部现有 tag 与远端追踪引用保持不变。

## 执行顺序

1. 保持当前集成分支上的正常 develop merge 和候选提交历史，不 reset、rebase 或用 cherry-pick 代替 merge。
2. 完成 API、文档、资产/许可材料、Skill 与校验器检查并提交，得到候选 C。验证 F、R、输入 develop、main 原 HEAD、GeoPhys P 的要求祖先/固定关系。
3. 在 F、R 原工作树分别检查当前 HEAD 和 tracked 状态，然后只 detach 到各自冻结输入 HEAD。保留全部 untracked、ignored、资产、证据和 provider checkout。
4. 从当前集成工作树 `develop` 开始，`merge --ff-only C`；然后对 `main` 执行 `merge --ff-only C`；在 C 创建本地 `v2.1.0` 分支；当前工作树最终回到 `develop`。
5. 使用普通 `git branch -d` 删除已合入的 `develop-full`、`codex/phase-ii-01-camera`、`codex/v2.1-integration`。如工作树占用或 Git 安全检查拒绝，先核实原因；不使用 `-D`。
6. 最终必须仅有五条本地 heads：`develop`、`main`、`v2.1.0` 指向 C；`v1.1.0`、`v2.0.0` 保持冻结 SHA。远端追踪 refs 不计入本地分支数。

## 停止条件与收据

如果 HEAD 漂移、tracked dirty、未知 writer、v2.1.0 已存在且指向其他提交，或 unique commit 未被候选承接，停止相应分支操作并记录差异；不 stash/reset/强删，不扩大删除清单。最终收据应包含 ref 前后值、ancestor 检查、worktree 路径/branch/HEAD/dirty、protected-input hash、provider pin、tag object 和 native lock 状态。
