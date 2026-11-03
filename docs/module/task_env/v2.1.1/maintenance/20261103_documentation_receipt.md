# 2026-11-03 v2.1.1 文档构建收据

## 授权与输入

维护者已审阅确认 7 阶段／22 子阶段路线，并明确要求开始构建文档。此次范围为 v2.1.1 规划、协议草案、Goal、能力／编排记录和必要导航／文档 Skill 更新；不实施功能、不运行仿真、不派发代理、不启动执行 Goal。

输入 Core：`develop@fd03817c9f6ef8ce9fd68c1db30125efda68e1c8`，GeoPhys pin／实际检出：`67da1165149486d3ae3e779c13ce31af49e17d50`。本地 `refs/tags/v2.1.0^{}` 为同一 Core。没有 fetch／push 或远端发布查询。

初始 dirty 仅为以下两个既有未跟踪文件；本轮保留路径和字节：

| 输入 | SHA-256 |
| --- | --- |
| MUJOCO_LOG.TXT | `dfb37ada202855d609f9e210cf79b287de78f2ded70e704ceeb544d17bf7ad4b` |
| docs/maintenance/20261030_runtime_route_diagnostic_handoff.md | `18cc56c7f0ffbcb947db4bd8725279489171efbee8f08b28603b79c47f509d61` |

## 输出与语义

本版入口为 [README](../README.md)，阶段依赖与统一验收由[执行表](../planning/execution-and-acceptance.md)维护。五份协议标记 `DRAFT_FOR_DISCUSSION`；7 个 Goal 为规划标识；22 子阶段 PLANNED／attempt 0；本版能力目标全部 NOT_RUN。API／guides 只说明迁移和交付要求，不提供虚构可运行接口。

v2.1.0 原始能力矩阵、历史结果、发布材料和迁移清单不修改。当前导航说明本地可核实 tag 与规划状态，旧 candidate 收口文字按来源时点解释；不根据旧文字断言当前没有 tag 或未推送。

## 检查记录

| 检查 | 实际结果 |
| --- | --- |
| `PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/geochora-doc-governance/scripts/validate_docs.py --mode current` | exit 0，errors 为空；当前链接／锚点、JSON、迁移、维护路径扫描通过。另报 96 项历史来源相对链接问题，保持历史记录，不计作新文档通过或改写它们。 |
| v2.1.1 定向结构核对 | 7 个 Goal、22 个唯一子阶段、5 份草案；所有依赖存在且在默认顺序前，未发现循环。13 个目标和 9 个最终 cell 均 NOT_RUN，无伪造证据或实现接收。 |
| Markdown／JSON 内容范围 | 草案、规划与未实现 API 边界明确；新版本页面未写入本机绝对路径；官方参考已只读查阅。 |
| Skill 导航刷新 | 仅更新 doc-governance／TaskEnv Skill 的版本导航和规划边界；未改变生产 API、运行命令或宣称新能力。复核已有源码 owner／caller 入口与文档链接；未做 native／示例运行验证。 |

`git diff --cached --check` 已通过；暂存范围为本版 23 个新文件和 7 个必要导航／Skill 文件，共 30 文件，无实现代码。两项保护输入 SHA-256 与输入记录一致；GeoPhys pin 未修改。本收据不把文档校验称为实现测试。

现有 validator 的 `current` 模式自动扫描新增未跟踪 Markdown／JSON，但 required-path 清单仍针对 v2.1.0 来源版本。此次补充定向核对 v2.1.1 的 7 个 Goal、22 子阶段、依赖和初始状态，不修改 validator 代码、不把旧 required-path 检查冒充新版本完整性门。

本轮 native／App／solver／model compilation／physics／GPU 启动为 0；未运行实现测试、训练或 Solution。后续功能能力、正式 Qualification 与发布状态均不从此收据推导。

## 交付

必要本地文档提交完成后，以本页所属提交及 Git 历史识别输出，不在同一提交中伪造自身 commit hash。未 push、merge、tag 或发布。下一步为维护者审阅文档与阶段 1 协议讨论。
