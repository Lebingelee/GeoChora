# G05 Isaac loader 顺序历史记录更正

E15 输出分类时，独立核对发现原 [loader 顺序报告](../../../../../../workspace/maintenance/v211_g05_5c_unit005_isaac_continuation_20261110_002/isaac-loader-order-report.md)中对 `isaac-loader-order-001` 的表述与该次原始收据不一致。原报告保持历史身份，以下以同次原始记录为准，不更改已接收的 U4／U5 结论。

- **001 App-first：**同次 `scope.log` 记录 `app-first_rc=0`。事件流 758 条，序号连续，记录 ready 与 close 开始，未记录 close 返回；worker 有启动和关闭消息，这些消息不能证明 close API 已返回。不能把报告中“close 返回后段错误”归给 001。
- **001 production-order：**子进程确实启动，但在读取 `UNIT5_PENDULUM_MANIFEST` 时因变量缺失退出，production factory 未运行。原报告称子进程未启动的措辞不准确。
- **005／006：**005 App-first 的同次事件有 close 返回，scope 记录退出码 139；005 和 006 production-order 的事件序列分别保留原始运行的 factory／App 顺序。它们是其他运行，不能用来补写 001 缺失的 close 返回。

[来源及保全清单](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/retained/g05-isaac-loader-diagnostic/manifest.json)记录报告、脚本、scope、worker、005／006 事件及 clean-control 收据。001 的原始大事件流为 **226,129,691 字节**，SHA-256 `8c00baad02fcdd793d67d6c85d3b7ade6c14db102d7ce640c6985c3d35f6beab`，作为解释此处矛盾的核心诊断**在原路径保留**，不复制进第二份完整快照；任何后续处置都须显式排除此原件。该目录其他内容不因此整体认定为必要。

这些记录只支持对应运行的启动／关闭观测，不能证明进程退出原因，也不能把启动期间未知的隐式物理步数记为零；没有新的 native 运行或资格结论。E15 仍在进行，最终项目接收仍待维护者决定。
