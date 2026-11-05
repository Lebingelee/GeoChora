# 阶段3前维护：待处理的复审检查点

> 2026-11-05 恢复更新：下文为原检查点，预算、存储及物理回归状态以[恢复后的验证记录](20261105_pre_stage3_resumed_physical_checks.md)为准。维护仍未整体完成，等待职责整理及 Sol 独立复审。

状态：**PREPARED_PARTIAL_AWAITING_BUDGET_AND_SOL**。本页供维护者人工转交Sol或恢复工作，不是最终验收、资源超限豁免或阶段3启动授权。检查时 `develop@dce469ab470f37fb7ab475c6a30c218513fd1220`，tracked clean；本页所在提交只增加交接文档。实际执行前重新固定HEAD并核对保护项。

## 结论与门

- **G0 FAIL**：原2 GiB总新输出上限已超出。attempt001及续作目录目前合计约9.34 GiB；12组F04篡改测试副本约8.64 GiB。supervisor未统计目录外pytest basetemp；原因、证据与不可倒填原则见[资源复核](20261105_pre_stage3_gate_audit.md)。现有目录、历史raw和日志均未删除。占用量不是已写入字节的完整账本，不能用它证明此前总写入低于某个更大额度。
- **G1 PARTIAL，待Sol复审**：`48401525` 的R1已由Sol有限接收。此后Marker通用编译／动作／观测接线、F06受信任务声明与runtime准入、Nut外部Solution及task／recorder／runtime职责归位均有新提交，尚无本轮独立复审。`SelectedReferenceEnv` 现3683行，仍含多种路线接线；F05 session分类仍导入任务候选类型。见[功能owner与调用者](20261105_pre_stage3_owner_and_document_map.md)和[逐项续作](20261105_pre_stage3_continuation.md)。
- **G2 PARTIAL**：clean `7756812f` 完整无引擎门290 passed／1 skipped／5 deselected；之后至检查点仅文档变化。真实Marker一次单步属于 `bc190964`。PickCube／Nut最终源码代表物理回归与同次独立reader均未运行；此前classic `3ed14c08`、PickCube `f9cb51fd` 物理证据保持原身份。
- **G3 PARTIAL**：当前任务开发指南、API、示例、显式路径启动器及安装文档已有更新；Marker在已有MuJoCo 3.8.1 CPU上有一次单步。全新安装、全部适用启动路径及最终源码完整代表回归未核实，不声称完整新手路线已验收。
- **G4 PARTIAL**：现有物理H5与独立读回按各自源码保留；当前reader已只读通过 `f9cb51fd` 历史PickCube记录，不等于当前源码物理成功。本续作最后一次native supervisor记录自己的进程组退出、双锁释放；不能据此推断其他用户的锁或进程状态。
- **G5 PARTIAL**：本地提交和逐项证据已保留；尚未完成本维护项的最终交付、Sol复审或阶段3移交。不能以本检查点更改阶段2接受结论或标记阶段3开始。

## 请求维护者决定及准备情况

原物理步上限120000，当前保守预留115807、余4193。PickCube horizon1000／5 substeps需预留5000，Nut horizon6000／5 substeps需预留30000，两者合计需在原上限之外至少追加30807步；不得通过缩短horizon冒充原回归。是否追加及是否调整输出预算已向维护者提出，尚无答复。

在输出超限发现前，对 `dc95e1d9` 的两条路线完成不导入引擎的纯构造预检：horizon、substeps和调用方Solution身份匹配。备选命令、源码origin wrapper、独立reader及资源限制在ignored `workspace/maintenance/v211_pre_stage3_continue_marker_20261105/physical-gate-preflight-dc95e1d9/`；该计划不是运行授权，且HEAD已变化，执行前必须重新冻结实际提交。若维护者批准，需同时明确对已超限的处理和后续输出计量口径：当前约9.34 GiB是目录占用，不是历史累计写入量。应将worker实际H5、日志和测试临时输出置于受监控目录，另核对维护项总量；保留原失败记录。

## 可核对的原始证据

- 完整离线门：ignored `workspace/maintenance/v211_pre_stage3_continue_marker_20261105/audit-7756812f-offline/`；首次发现的边界测试替身失败及修复也列在[门核对](20261105_pre_stage3_gate_audit.md)。
- Marker真实单步：ignored `workspace/maintenance/v211_pre_stage3_continue_marker_20261105/marker-guide-bc190964/`，含源码HEAD、锁与资源收据。
- 当前reader对旧PickCube H5的只读检查：ignored `workspace/maintenance/v211_pre_stage3_continue_marker_20261105/historical-reader-33c51a4f/`；输入H5 SHA `264b35a9f08e754287957d8d7271be072bc5c06157d3755e80b155b9a2896763`。
- F06真实来源输入与提前拒绝（非Isaac物理）：ignored `workspace/maintenance/v211_pre_stage3_continue_marker_20261105/f06-current-input-7d15d1e1/`。
- 本检查点 `git diff --check 48401525..dce469ab` 通过；两份保护untracked SHA分别为 `dfb37ada202855d609f9e210cf79b287de78f2ded70e704ceeb544d17bf7ad4b`、`18cc56c7f0ffbcb947db4bd8725279489171efbee8f08b28603b79c47f509d61`；GeoPhys `67da1165149486d3ae3e779c13ce31af49e17d50`、Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。

保持原约束：单writer、native串行及双锁、不得启动Isaac／GPU、不得修改冻结历史或push／merge；Sol结论应独立给出，不由Terra预填。
