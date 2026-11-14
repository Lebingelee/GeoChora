# v2.1.1 范围与实施路线

当前进度（2026-11-15）：G01～G05已按各自范围有界接收，5c诊断单元1～9收口；5c后的E00～E16代码与项目优化已获维护者有界接收，后续C1～C5精简及集中复验已完成。基于生产代码 `7f8796b4` 的[G05→G06复核](../maintenance/reviews/20261114_g05_pre_g06_readiness_7f8796b4.md)未发现须重开G05的功能阻断项，当前准备G06；G06／G07尚未实施，v2.1.1未完成。七阶段／二十二子阶段不变，G07最终矩阵保留。接收范围、实际输入和既有例外见[当前摘要](../maintenance/current-state.md)。本地develop已按维护者授权快进至现阶段成果，G06接手见[Agent handoff](../maintenance/20261115_g06_agent_handoff.md)。

路线确认基线：`ROUTE_CONFIRMED`，2026-11-03。五协议语义已由维护者确认，具体生产值映射及 native 执行由所属冻结工作包承接。

## 必达范围

1. 统一 Core、physics adapter、render adapter 的责任、值契约、生命周期和能力准入。
2. 首批真实物理路线为 MuJoCo／CPU、GeoPhys／CPU、Isaac Sim＋PhysX／CUDA，限定具体任务和资产。
3. 修复 PickCube Solution，先有当前控制链的成功参考，再迁移和复核；NutAssembly 检查复用。
4. 以具名关节广义驱动力为统一施控主路线，Robot／嵌套组件声明受控通道和 Controller，公共状态／可替换模型支持 Controller；BodyWrench 独立类型和未来 typed loads 有明确边界；reset 可切 Controller 输入规格。
5. 窗口、离屏 RGB、RGB 同步进入 observation 全部实现；相机可配置，`.render()` 不额外推进任务物理时间。
6. 在至少两个确实支持并行的物理后端上验证，至少包含一条原生 batch；记录进程并行与原生批量的区别。
7. public Env 构建时选择执行组合和 renderer；已准入后端／Controller 可按 reset 能力切换，renderer 固定到 close，同一 Env 的 renderer 切换后移；不更换配置的部分 reset 按能力支持，换后端按原生批次重建。
8. observation 构建后保持结构、shape、dtype、单位、坐标及字段语义；为非刚体表示和设备数据保留扩展边界。

2026-11-06重新编排建议：[装配Panda](stage4-assembled-panda.md)是本版附加集成用例，原G04的typed命令、三后端effort／BodyWrench及Controller reset主线保持。建议4a作接口需求审阅，4b主能力稳定后早做空载／夹爪／补偿检查，4c有效PickCube参考复用，7a完成两任务原Solution在原／新机器人上的完整复用，7b仅按输入变化定向复核。新类仍置于`task_env/robots/`并由任务配置消费；不要求物性等价。这是 2026-11-06 的排期决定；后续装配主体与双 Controller 的受测接收范围见当前摘要，完整版本用例仍由其集成门判断，不把旧“未实施”状态沿用到当前。

## 已确定的架构边界

- 一个 physics provider 负责整场景，可内部组合多个求解器；跨 provider 力学协同仿真另行规划。
- 同一原生批次使用共同执行配置，切换时整批重建；reset 不做旧物理／Controller 状态迁移；Core sampler 的 seed=None 随机流继续。
- 任务语义、奖励、成功条件与 Solution 属于任务／既有 Core owner；adapter 负责原生翻译和公开反馈。
- 配置优先级继续为 Core → 任务类 → YAML → 调用方；不新增平行 factory、Runtime 或 Recorder。
- 资产由任务提供已准备表示；原生导入、单位变换和声明的构建步骤可由 adapter 完成，重新网格化／替换物理模型等须有明确产物和身份。
- 支持某类求解器与支持其耦合是不同能力；读取文件与数值有效也是不同结论。

## G05后的开发基线与注意事项

后续代码开发必须以[5c后代码与项目优化总账](post-5c-code-project-optimization-diagnostic-ledger.md)作为重要依据，尤其是普通任务构建、模块职责、公共Runtime／状态、adapter边界、诊断归位及真实证据要求。该文件已于 `0722341b` 按维护者授权原样纳入Git；原文保留2026-11-11诊断起点，其历史“未完成”描述不代表当前待办。实际现行完成状态应与[60项结案表](../maintenance/reviews/20261114_e14_current_state_alignment_closeout.md)、[当前摘要](../maintenance/current-state.md)和对应源码／证据一起读取，不能重新执行已关闭的E00～E16。

| 已发生的改造 | 后续开发必须继承的成果 |
| --- | --- |
| G05c诊断单元4：任务构建与共同主体重构 | 一体Panda、装配Panda、Pendulum、双轮车沿共同主体声明、Assembly／具名通道、Controller绑定及场景interval提交机制运行；允许不同source lowerer和原生映射，不另造任务专用Env／Runtime。见[诊断路线单元4](stage5-5c-diagnostic-refactor-roadmap.md#工作单元-4一体-panda-与多层装配-panda-的同一主体流程)及后续有界接收。 |
| G05c接收后的E00～E16优化 | 四正式任务统一配置／构建入口，Task／Robot／Controller／Env／source／provider／renderer职责归位；普通记录、历史codec及实验oracle分层；受影响caller、诊断、文档和已批准项目清理完成。不是整体版本或任意组合完成。见原总账与60项结案表。 |
| 后续C1～C5精简 | 继续复用既有Env发布／interval owner、provider共同值封装及Isaac正式RGB完成证明；最终 `close_receipt` property回归已修复。263项guarded检查及两条MuJoCo完整state-only Solution有对应证据，见[C5交付](../maintenance/reviews/20261114_post_optimization_c5_final.md)。 |

实施G06及后续阶段时遵守以下原则：

1. **沿共同构建合同扩展。** Task表达任务语义、reset、奖励和Solution；Robot声明主体、能力及组合；Controller处理typed输入／输出和绑定；Env协调共同生命周期；provider／renderer负责原生映射与资源。新batch适配须继承正式配置语义，不能仅移除准入拒绝，或为某个任务复制一套构建、step、reset、记录与关闭。
2. **一个明确的状态与推进owner。** 一个场景interval的控制只提交一次；多个Controller按既有资源合同聚合。physics substep、外部step、Controller tick及render cadence分别说明。renderer消费公开state／boundary／clock，不推进第二份physics；不把Position、effort、wrench或原生无量纲ctrl互相改名。
3. **诊断与正式实现分开。** 本版诊断集中在`task_env/diagnostics/tasks/v2.1.1/`，经公开API、组合或有范围的测试注入工作；不向公共路径添加实验名分支、探针开关或对diagnostics的反向依赖。保留身份、单位、source、clock、资源冲突、fault及独立native读回等必要检查。
4. **按影响验证。** 每个大单元交付实际调用链、owner、文件／代码净变化及证据；迁移行数单列，不把拆文件当净删除。纯／fake、离线reader、真实Runtime、完整Solution、任务成功和Qualification分别报告。未变输入及调用链可复用原证据；不为小修扩成全历史矩阵，也不用旧fixture恢复已退休入口。
5. **G06建立真正的batch语义。** 四正式任务当前无formal batch adapter，旧vector／native runtime存在不代表已接通。继承每slot身份、episode／clock／RNG、mask、buffer lifetime、控制资源及图像边界；至少两个物理后端、至少一个native batch仍为必达。`num_env=1`、N个串行scalar Env或单个remote进程不能代替该证明。
6. **保持已批准范围。** renderer在Env创建时固定至close；6c切backend须与它兼容，部分reset不能污染未选slot。Isaac受测腕部相机不推广到其他renderer；颜色、source、SDK隐式推进unknown、同次联合completion及其他已接收例外保留。RGB完整Solution、D0、新资格和G07三seed矩阵不新增为G06启动门。
7. **从现行集成基线继续。** 维护者已授权本轮将本地`develop`快进至当前阶段成果；G06接手者应核对实际refs／dirty及pins，再按阶段规划分支并复用至6a～6c，不能从落后的develop丢失G05及优化代码，也不能每个Goal创建新worktree。执行包冻结输入、资源与共享锁；本轮同步不授权push、main合并、tag或发布。

## 七阶段、二十二子阶段

| 阶段 | 数量 | 子阶段 | 主交付 |
| --- | --- | --- | --- |
| 1 协议 | 4 | 1a 现状与范围；1b 统一表示；1c physics 协议；1d render 与共享资源 | 已确认实施基线；具体实现不由设计 PASS 代替 |
| 2 PickCube | 3 | 2a 归因；2b 修复；2c 成功参考 | 现有控制链的有效参考与差异记录 |
| 3 后端 | 3 | 3a 路由与准入；3b 三后端翻译；3c reset 重建 | 统一协议驱动真实初始化与步进 |
| 4 控制 | 3 | 4a typed 命令／反馈；4b Controller／外力组合；4c 切换与复核 | 多种输入进入同一施控主路线 |
| 5 渲染 | 3 | 5a 场景数据；5b 窗口与采集；5c 同步 observation／固定 renderer 与跨组合 | 三个渲染完成目标分别成立 |
| 6 并行 | 3 | 6a 批量契约；6b 多后端；6c 部分 reset／整批重建 | 状态、动作、图像与 episode 正确对应 |
| 7 集成 | 3 | 7a 任务复用；7b 最终矩阵；7c 文档收口 | 有证据的版本交付与未决项 |

默认顺序为 `1a → 1b → 1c → 1d → 2a … → 7c`。具体依赖及阻塞处置由[执行表](execution-and-acceptance.md)维护；不因某项技术上独立就静默重排。

阶段 2 先建立 MuJoCo 成功参考，检查 GeoPhys／Isaac 差异；三后端完整三 seed 矩阵放在 7b。固定目标是最终 PickCube 9/9 task-success，不能用 runtime-valid 替代。控制迁移后必须复核，不能沿用迁移前成功作为最终结果。

## 渲染与并行组合

原生适配路线优先。阶段 1a 冻结 MuJoCo 自带 renderer、GeoPhys 可用 renderer、Isaac 原生展示／图像路径的具体实现、版本、设备和限制。GeoPhys 的 renderer 名称不得只写“原生”，也不以历史证据替代当前 pin 验证。

首个跨组合已在GeoPhys CPU physics × MuJoCo renderer-only上有界实测并接收，公开状态映射、同步RGB及零额外MuJoCo物理推进见G05复核及原证据。该成果完成阶段5要求的一个真实跨组合，不扩大为任意physics × renderer矩阵；新增组合仍须核对公开数据、资产绑定及具体准入。

并行候选优先核对 GeoPhys 原生 batch 和 Isaac GPU batch。1a 冻结至少两个后端的名单、原生／进程方式及 6b 的实现范围；能力未就绪列为实现缺口，不能靠减少数量完成阶段。

## 后续 v2.1.x

Flora 不属于 v2.1.1 必达。SAPIEN、Genesis、独立 Newton、Isaac 内 Newton 需要在架构与能力表达上有合法位置，本版不承诺全部实际接通。

完整 F07、asset harness 自动适配、软体／流体／绳索真实样例、RL／IL demo、`agent_factory` 优化、R07 自主 Solution 扩展与 Isaac Lab 全功能差距研究后移。当前只研究与本版协议相关的优秀实现。

严格 F05 源柔顺／传力等价、同 USD 全后端等价、DG03、正式 Qualification 和发布不成为本版普通执行的隐含前置。已接收原生适配及其限定例外保持；不恢复旧 D01、退役执行器或整体 60% 删减指标。
