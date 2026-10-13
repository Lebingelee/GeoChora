# Mainline Publication

状态：**MAINLINE_PUBLISHED**。正常非强制 fast-forward 已成功执行，public remote 是 Lebingelee/GeoChora。

| 项目 | SHA / 结果 |
|---|---|
| 原 public/main | `f977528b9b9866c50afcf8ea9b5f5deadce60892` |
| 第一轮发布后的 public/main | `392eb7d26804d88c42e89f4a8ee5ce836ff90d56` |
| 同轮 public/codex/p1.8-integration | `392eb7d26804d88c42e89f4a8ee5ce836ff90d56` |
| P1.6/P1.8 source merge checkpoint | `be47e72fe81790813b784cb1a47c91d2f59b68ab` |
| Remote verification | main 与 integration exact SHA 一致 |
| Branch protection | main protected=false，公开 API 在发布前查询 |
| Publication method | non-force fast-forward；未使用 origin |

实际执行：

```bash
git fetch public
git merge-base --is-ancestor public/main HEAD
git push public HEAD:refs/heads/codex/p1.8-integration
git ls-remote public refs/heads/codex/p1.8-integration
git push public HEAD:refs/heads/main
git fetch public
git ls-remote public refs/heads/main refs/heads/codex/p1.8-integration
```

Remote main 包含 P1.6 closure parent 与起始 P1.8 integration。154 个受保护源码文件复核通过；7 个 historical Human decision 字节/哈希一致；既有 archive tags 未改变；gitlinks 保持原 main 指针。所有当前 module content identities 与 source manifest 对应。没有重复运行已验证的昂贵 qualification。

本回执作为独立 documentation-only followup commit 发布，source modules 与上述已验证 source HEAD 完全相同。最终回执提交自己的 SHA 由 public branch refs 和本地 `publication_receipt.json` 记录，避免自引用 commit hash。最终 exact published SHA 亦在本轮 chat handoff 给出。

发布不改变 P1.6 bounded approval、P1.7 DEFERRED 或 P1.8 PARTIAL/NOT_RUN 范围。Phase I 未关闭。未删除旧 branches/worktrees，也未改写其它工作树 dirty 文件。
