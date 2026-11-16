# G05 阶段 5 误提交证据的受限历史清理

维护者明确选择仅清理阶段 5 本次误提交及其后续提交；历史改写范围从 `c13ae2703230eb633833bfdefdd88acaea4e2d59` 之后开始，限定 `codex/v211-stage5` 分支。4 个线性提交中的仓库根 `workspace/`、`temp_output/`、`temp_outputs/` 已从每个新提交树排除。其他路径的每个新树与对应旧树比较一致；author、committer、时间和提交说明保留。未改早期历史、其他 branch/tag、其他 worktree、GeoPhys 或 Menagerie pin；没有 reset、clean、push、merge 或发布。

| 原始执行／审阅提交 | 当前阶段 5 重写后提交 | 内容 |
| --- | --- | --- |
| `1c6b7e4f49107fe57e31e9be43e2729162ffaca1` | `09023b0b7dc2a7874ab5077aa64323650823d54c` | 5c attempt002 实施 |
| `13111ca78f3c678a02da1d7ffb5a7c248447b036` | `2b9d2a4c0d8aca58ec38954ddc9798eb854042d7` | 原 release 记录提交；去除 workspace 文件后成为保留历史事件的空提交 |
| `f710697a500304979be95a4228b7a51da43c948f` | `a402241a031ba46f79ede2361159e7bad41a52cd` | Sol 独立主审 |
| `c3034a9c6e35f15c334adfb6087e2cddcf9f0de2` | `159eae52deea6625f7fc558fe7300dd92681e449` | 第三次前重评 |

执行前后逐一复核原 219 个被跟踪 workspace 文件的磁盘 SHA-256 一致，attempt002 output manifest 217/217 项仍匹配；文件和证据没有删除。具体映射和本地磁盘校验记录在 ignored `workspace/reviews/V211_G05_5c_history_cleanup/`。前包 release receipt 等原始证据保留原执行提交身份；此表是原始身份与现有分支提交的对应，不把重写后的 hash 伪称为原先执行时的 hash。

本操作不清理 Git 对象或 reflog，旧对象可能在本机暂时可见；已选范围仅保证当前分支上述 4 个重写后的提交树不包含相应目录，不宣称清除其他历史。未来交付不得 force-add 受忽略的诊断产物或私有 source snapshot；如需可版本化索引，应在文档 owner 保存精简索引而非工作区产物。
