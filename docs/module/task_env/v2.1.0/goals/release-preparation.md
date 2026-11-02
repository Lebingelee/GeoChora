# v2.1.0 本地发布候选准备

**Goal:** `V210_LOCAL_RELEASE_PREPARATION_20261102_001`，attempt 001；执行中。**状态：**两项 API 修复与 10 条定向离线回归已完成；版本文档、迁移记录、release kits、Skill 与校验器正在收敛，候选提交及本地 refs 收口尚未完成。

## 输入与范围

- 冻结输入：`codex/v2.1-integration@a3cd3312614212da1e589add4a6b7447c07e4e8a`；随后按冻结计划正常合入 develop `432b70741b06b8e635bcf1ac1c55009b8f478a6b`。
- 当前 GeoPhys pin：P=`67da1165149486d3ae3e779c13ce31af49e17d50`，Menagerie pin=`b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。
- API implementation commit：`0bf4a8e21cc0c19c087e6ca683c1d97eb990e50`。本地候选最终 C 由 closeout receipt 记录。

本 Goal 修复 selected execution 默认优先级与 typed state-only renderer 的解析/metadata 接线，并明确无 Controller 编译身份为 `null`；按 130 行冻结映射重组版本文档；建立 v2.0 冻结来源说明、v2.1 本地候选材料、资产/许可记录和文档验证器。历史v1.1/v2.0 tag与证据原件不重写。

## 发布与资产边界

GeoChora 与 GeoPhys 自有来源按维护者声明记录，许可证 `UNDECLARED`；不代选许可证。第三方未决资产为 `EXCLUDED`；不复制/提交本机 USD、LIBERO/robosuite 安装、mesh/data/H5 或 ignored workspace。Menagerie 子模块 pin 不变。当前仅做本地候选，**不 push、不建/移 tag、不发布 Release、不改远端、不授予 Qualification**。

## 执行约束

本 Goal 的 native/App/solver/model compilation/physics/GPU 启动预算为 0。仅运行必要离线 API、文档/链接/JSON/Skill/refs 检查。保留 `MUJOCO_LOG.TXT` 与既有 untracked diagnostic handoff 的原路径和字节。旧 F/R 工作树只在候选内容完成后 detach；所有 ignored/untracked资产和Evidence保留。

完成后提交内容，再按 [branch plan](../maintenance/migrations/branch-plan.md) 本地快进 develop/main，创建 `v2.1.0` 本地 branch 并收口到指定五个 heads。最终由维护者转 Sol 独立复核；本地候选不代表正式发布接受。
