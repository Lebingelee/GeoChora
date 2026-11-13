# E11–E16 U4：文档、能力与 Skills 实施记录

状态：独立主审复审无代码范围阻断，维护者按本轮明确条件授权有界接收；详见[独立接收记录](20261113_e11_e16_u4_independent_acceptance.md)。初始输入 HEAD `5742e956`，后续纳入 `0506ae26`。维护者已明确允许 T19 使用同次联合证据，五路离线核对与 H5 字段三态见[联合证据](20261113_e11_e16_u4_joint_completion.md)，独立复审已支持此有界口径。原始静态检查、矩阵复算和测试输出位于 ignored `workspace/maintenance/v211_e11_e16_u4_20261113_001/`。

| 范围 | 结果与限制 |
| --- | --- |
| 能力矩阵 | 单一 `capability-matrix.json` 新增五条 U3 完整运行的 task/source/controller/provider/record/close 结果和四条有界历史短程；原计划 `baseline`、`target_resolution`、`targets`、最终九格保留原值并标为历史快照。矩阵五条与各自 H5 SHA、同次关联和结果复算一致；单 seed 不填 G07 九格、不声称 Qualification。 |
| 当前入口 | 版本 README → current-state → API/矩阵/账本更新，编排索引区分 U1/U2 自评、U3 OPEN 和 U4 进行中；G06/G07 未开始，代码与项目接收分别保留。 |
| 正式示例 | TaskEnv 例子删除会被正式 batch 边界拒绝的 Pendulum 伪可运行代码；component batch 的原范围保留。PickCube Isaac 真实 caller 结果代替“只有合成检查”的过时说明，保留任务失败及 T19。旧 candidate 章节标为历史，未恢复退役 UID。 |
| Skills | 核对根 `AGENTS.md` 和项目、TaskEnv、测试、API、架构、文档、Harness、证据等九个现有 Skill 的静态入口；TaskEnv 的 routes 存在退休 `position_admission.py` 引用以及过时 state-only 说明，已按现行 owner 和有界证据更正。九份静态链接／路径检查通过，`skill-creator` quick validator 通过；这些不是对全部 Skill 行为的独立主审。 |
| 定向验证 | 禁止 SDK/安装资产的 fresh-process 守卫下，backend 选择、正式 batch 拒绝和 Isaac 示例的精确节点 **45 passed**；新增历史源码行号检查的 9 个正负例并入固定集合后 **232 passed**，两组有重叠不能相加；不启动物理、训练或窗口。 |
| 文档 validator | 原 2 errors 中，历史 review 的退休 Position 源已改为原审查提交及 blob 的精确 Git 来源，原判断保留；当前剩 1 error：受保护 `MUJOCO_LOG.TXT` 与历史 hash 不同。原 96 个历史链接问题逐项只读核查后，17 个是历史 Git 源码及行号真实存在而 validator 误按 Markdown 锚点处理；修复检查器后保留 79 个历史源目标不存在的问题，其中 27 个去掉越过仓库根的 `../` 后存在同 ref 的候选对象，但原作者意图未经确认，仍不自动改链或算通过。完整 96 项来源、目标、类别和决定见 ignored `historical-link-audit.json`；未改保护原件、expected hash 或复活退休代码，不能称全库通过。 |
| 总账与 V01–V10 | [60 项逐行表](20261113_e11_e16_u4_row_reconciliation.md)是实施者初步映射；原 60 ID 各出现一次，V01–V10 另列。项目、证据包、refs 和实际清理均 OPEN；行数/覆盖检查不等于逐行独立审计。 |

| 节点 | 实施者现状／下一 owner |
| --- | --- |
| T22 | 能力矩阵已列当前交集和原始计划，实际 source、controller、读回与 close 的范围需独立复审；G06/G07 不提升。 |
| T23 | README、current-state、API、指南与实际例子已更新，历史候选文字标明原时点；renderer 固定至 close 和 Isaac 本轮结果不再误写。 |
| T24 | TaskEnv Skill 主入口、routes 和根 AGENTS 已按当前 owner 更新，九份现有 Skill 的静态检查及 45 项定向检查已执行；独立行为审查未完成。 |
| T25 | 当前 validator 1 项保护文件差异和 79 条历史缺失目标；原报告、误报修复及逐项归属已保留，未经批准不改保护字节或将剩余问题称通过。 |
| T26 | 原 60 ID 与 V01–V10 已映射并独立核对编号和标题；已接收历史实现按影响复用，项目部分 OPEN。 |
| T27 | 独立审查与复审已完成；按维护者本轮明确条件授权记录代码范围有界接收，限制见独立接收记录。 |
| T28 | 当前入口、逐行表、五路联合证据及有界 claim 已压缩；U5 按此保全复算，项目最终接收另列。 |

独立主审已审阅 U1–U3 关键调用链、五条运行和 0506ae26 专项并提出联合证据与当前矩阵映射缺口；实施者已补充，独立复审未发现新的阻断；依据维护者本次明确条件记录代码范围有界接收，U5 随后执行；具体删除、worktree 和项目接收另行处理，不由本记录授权。

独立主审入口：以本记录所在提交及 [U3](20261113_e11_e16_u3_solution_evidence.md)、[U2](20261113_e11_e16_u2_caller_review.md)、[60 项表](20261113_e11_e16_u4_row_reconciliation.md)为待审输入；逐项核实际代码／caller、生产与诊断 diff、五份同次 H5／原始报告和 V01–V10。特别决定 T19 的 caller completion 与 v3 H5 缺失能否满足要求，以及剩余 1 项保护文件错误／79 条历史链接的处理；不要把实现者自评、单 seed 或关联器 PASS 当成维护者批准、独立 Solution 复算或 G07 通过。主审的结论、普通修复和维护者决定必须分别记录。

提交前计量：相对输入 `5742e956`，生产代码 `+0/−0`，诊断 `+34/−0`，文档／Skills `+442/−101`，文档检查工具 `+8/−1`；新增一个诊断和两份文档，无整文件删除或迁移。相对规划输入 `a6b107ac` 为生产 `+340/−232`、诊断 `+3069/−1188`、文档 `+1160/−123`、检查工具 `+8/−1`；累计相对 `1f1359ee` 为生产 `+8487/−16975`、诊断 `+9417/−1187`、文档 `+3105/−241`、检查工具 `+8/−1`，另有其他 `+1/−3`。累计含此前已接收工作和 Git 重命名判断，不是本单元独占成果。
