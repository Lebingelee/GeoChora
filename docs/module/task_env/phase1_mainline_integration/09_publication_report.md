# Mainline Publication

源码整合 checkpoint：`be47e72fe81790813b784cb1a47c91d2f59b68ab`。原 public/main：`f977528b9b9866c50afcf8ea9b5f5deadce60892`。本文件初版在发布前生成，实际 remote SHA/命令结果将在完成发布后补充为独立 receipt；不能从本初版推断发布成功。

已确认 public remote 为 Lebingelee/GeoChora；GitHub main branch protected=false（公开 API 查询）。采用正常 fast-forward push，先 integration 后 main，发布前再次 fetch 检查 ancestry。禁止 force push。

计划命令：

```bash
git fetch public
git merge-base --is-ancestor public/main HEAD
git push public HEAD:refs/heads/codex/p1.8-integration
git push public HEAD:refs/heads/main
git fetch public
git ls-remote public refs/heads/main refs/heads/codex/p1.8-integration
```

后续 receipt 文档提交若发生，只改变本次审计/发布文档；精确最终 HEAD 必须读取 public refs 与本地 `publication_receipt.json`，避免在 commit 内容内声称自己的自引用 SHA。
