# E11～E16 现状分析与剩余实施账本

日期：2026-11-13。状态：`PLANNED_NOT_STARTED`。维护者已在本次对话统一接收 E05～E10，E00～E10 按各自范围保持接收。本页承接[总台账](post-5c-code-project-optimization-diagnostic-ledger.md)的 E11～E16，不重置七阶段／二十二子阶段或 attempt 历史。[实施 Goal](post-5c-e11-e16-goal.md)引用本页。

## 1. 判断与执行方式

**剩余重点已从底层共同构造，转向诊断／caller 收口、完整 Solution 结果、全条目接收和项目可恢复性。不能以 E00～E10 接收替代这些出口，也不需要重新进行一轮底层普遍重构。**

| 事件 | 当前实际基础 | 尚未闭合的结果 | 负责单元 |
| --- | --- | --- | --- |
| E11 诊断与测试 | 版本目录已有 30 个 Python 文件；实验 oracle 已迁出 H5；抽查的公共 Runtime 已无原实验 factory context；生产 AST 直接 import 检查未发现依赖 diagnostics/tests | 旧测试／fixture 对退休入口的引用仍在；同一模块混有纯检查和真实 source 构造；没有一个可直接使用的当前版本检查分类入口；核心证据的最终依赖需登记 | U1、U5 |
| E12 用户与兼容 caller | 四任务正式 make_env、外部 Solution 和正式配置已接通；CLI、示例和 Harness 已有部分迁移 | 普通示例与 F06 高级入口仍混排；CLI 的广泛 backend fallback、完成结果投影、旧 batch 纯构建和 LIBERO 直接 Core 依赖需集中对账 | U2 |
| E13 正式运行与完整 Solution | 已有四任务短程、真实 RGB、普通／历史 H5 与一次短重执行；G02 有历史完整成功参考 | 优化后两任务多 provider 单 seed 的完整运行和同次全程独立读回未完成；一 interval 或记录有效不能替代 task success／completion | U3 |
| E14 文档与代码优化接收 | 当前摘要和 E00～E10 专用账本已有实现／主审入口；总规范已经建立 | 能力矩阵仍为 11 月 3 日规划；指南和多处开发说明滞后；60 项没有最终统一签收表；整个代码优化尚未独立接收 | U4 |
| E15 Stage 证据与输出 | G01～G05 均有界接收，原始包和主审仍可定位，workspace 未被 Git 跟踪 | 五个最终 stage 包、必要输入闭包、独立复算和旧→新引用尚未归并；大量历史目录与当前依赖混合，尚无可执行删除清单 | U5、U6 |
| E16 refs／worktree 与项目接收 | 本地 refs 与六个 worktree 可枚举；现有分支及 detached HEAD 相对本轮 HEAD 的独有提交计数均为 0 | 仍有三个旧阶段分支、五个额外 worktree；旧 worktree 有 untracked／子模块类型变化和 ignored 证据；安全移除及清理后恢复检查、项目最终接收未完成 | U7 |

下文 **7 个大单元、44 个检查点**是交付合同，不是 44 个新 bug、44 轮测试或 44 次派包。每次完整推进一个 U：实现／迁移 → 必要修复 → 定向验证 → 结果压缩 → 本地提交 → 对照总账相应条目。小检查点不独立触发 native。发现无关问题记第 10 节，不跳去重构另一个模块。

本次仅规划与接收状态同步：不运行 pytest／SDK／native，不解析安装资产，不整理证据原件、不删除 refs/worktree，不启动实施 Goal 或 G06。实现自评、独立主审、维护者接收分别记录。

## 2. 实际输入与量度基线

输入 HEAD `a6b107ac43bed77565a643612372c6c76e641511`；最新生产小修 `7a098423`；分支 `codex/v211-stage5-diagnostic`，tracked clean。E05～E10 接收依据为[独立主审](../maintenance/reviews/20261113_e05_e10_independent_review_d9dc02c6.md)及本次维护者决定；不是将当时的主审建议改写成当时已获人工接收。

GeoPhys pin `c1ea3cc9fb99ccbd1d31c36d6fc7b84aa936b3d7`，Menagerie pin `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。四个既有 untracked 输入继续保护：`MUJOCO_LOG.TXT`、runtime route handoff、stage3 gravity proposal、总台账本身；不加入本轮提交。

| 范围 | tracked 文件 | Python 文件／文本行 | 口径 |
| --- | ---: | ---: | --- |
| 项目／task_env | 1,394／997 | task_env 864／230,335 | 项目仅 Git blob，排除两个 gitlink；使用 NUL 分隔解析路径 |
| 全 diagnostics | 451 | 394／106,944 | 含其他版本，不等于本轮全部迁移或删除范围 |
| tasks 诊断目录（含 v2.1.1） | 259 | 250／85,746 | 不能与下一行相加 |
| v2.1.1 诊断 | 30 | 30／7,085 | 已有工作基础，不能重建另一套重复框架 |
| script／examples | 54／15 | 53／8,226；12／1,351 | CLI／Harness 与普通示例分别核查 |
| Task 目录／LIBERO | 27／31 | 21／5,810；27／6,202 | 不为减少数字拆散有明确任务语义的模块 |

静态字符串命中 34 个文件引用旧 Position candidate／旧 physical candidate 模块或旧 `load_leaf_control_records_h5` 名称，其中 32 个含对应 AST import。这个数包含历史诊断，也包含合法保留的严格 Judge 名称／引用，不是 34 个生产缺陷。精确文件／行在[静态盘点](../../../../../workspace/maintenance/v211_e11_e16_replan_20261113_001/static-inventory.json)和[范围统计](../../../../../workspace/maintenance/v211_e11_e16_replan_20261113_001/scope-summary.json)。AST 检查不替代 fresh-process 导入验证。

| 实际磁盘范围 | `du -x -s -B1` 分配字节 | 说明 |
| --- | ---: | --- |
| 主 checkout `workspace/maintenance` | 84,457,574,400（约 78.66 GiB） | 第一层 514 项，含本次规划目录；全部版本／嵌套 worktree，不能全算可清理量 |
| `workspace/evidence_import_v211_stage5_20261108` | 27,226,112 | 有 inventory、conflicts、link audit，不能按“import 副本”直接全删 |
| `temp_outputs` | 85,344,256 | 实际路径为复数；单数不是此处清理目标 |
| 旧 v210-integration checkout 的 workspace | 13,790,777,344（约 12.84 GiB） | 外部 checkout；先保全实际 stage 证据和本地文件 |

该数是规划时快照，写入本次摘要会略有增长；不是承诺回收量。hardlink、嵌套路径及共享块不能重复记节省。[磁盘分区盘点](../../../../../workspace/maintenance/v211_e11_e16_replan_20261113_001/maintenance-disk-inventory.json)中最大目录 `phase_ii_01_sol_luna_handoff_20261023_001` 约 16.74 GB，且当前 Harness 仍使用其中共享锁。输入、保护 SHA、refs/worktree 状态和文档检查均保存在同一[规划快照目录](../../../../../workspace/maintenance/v211_e11_e16_replan_20261113_001/input-snapshot.json)。

## 3. 大单元与依赖

| 单元 | 检查点 | 完成后可见成效 | 对照总账／前置 |
| --- | --- | --- | --- |
| U1 当前诊断与测试闭环 | T01～T07 | 有可直接运行的纯检查入口、明确 opt-in 的资产/native 检查；退休 fixture 不再牵引生产架构；有效检测器保全 | TEST-01～04；复用 E00～E10 |
| U2 正式 caller 与外围兼容 | T08～T14 | 普通配置／示例可直接用；结果与错误一致；batch／learner／LIBERO 有逐 caller 结论和真实边界 | CALL-01～04；U1 为验证入口 |
| U3 完整 Solution 与同次读回 | T15～T21 | 两任务各支持 provider 单 seed 完整结果，至少两任务各自 MuJoCo 成功；有效执行、任务成功、completion、close 独立可查 | V01～09；U1/U2 的受影响入口稳定 |
| U4 文档／Skills 与代码接收 | T22～T28 | 60 项按职责／证据逐行对账；现行导航和能力表准确；独立代码优化接收，项目清理仍单列 | GOV、DOC、全部代码项；U3 出口 |
| U5 五个 Stage 最终包与依赖闭包 | T29～T34 | G01～G05 各有唯一成功入口／核心诊断；可从归并包独立复算；删除候选已有依赖证明 | PROJ-01／02、TEST-04；U4 接收后执行归并 |
| U6 输出清理与引用切换 | T35～T38 | 按具体清单清理，实测目录／文件／分配空间下降；锁和最终证据不依赖被删目录 | PROJ-01～04；U5 已独立复核 |
| U7 refs／worktree 与项目接收 | T39～T44 | 安全处置旧分支/worktree，独有内容可恢复；最终入口及正式示例通过清理后检查；项目单独接收 | BRANCH-01、V10；U6、代码接收和具体处置授权 |

下一单元执行前只读取本页、上单元结果及其必需源码；不再重新逐字审计总账。每单元结束回看第 8 节对应总账项。发生已接收合同回归时在当前单元修复，不重新启动 E00～E10；真正扩大范围的发现集中登记。

## 4. U1：当前诊断与测试闭环

接收 owner 为 `task_env/diagnostics/tasks/v2.1.1/`、对应 provider／Recorder 的已有正式 owner，以及 diagnostics README。历史源码和旧结果由原 ref／必要核心证据保留；不承诺所有旧测试继续在当前 HEAD 可运行。

| ID | 当前源码／调用事实 | 实施步骤及退出证据 |
| --- | --- | --- |
| T01 | 30 个版本文件已有配置、source、worker、camera、recording 检查；无本版本统一 README／执行分类表 | ①按实际 node 和 fixture 建 claim 表，列 owner、输入、oracle、成本；②分纯/fake、离线 H5、真实资产/source、CPU native、GPU/App、窗口；③复用现有 pytest 与 runner，给最小命令，不新建测试平台。退出：接手者不读整个旧包也能选对检查。 |
| T02 | `test_formal_configuration.py` 明示混合纯配置和真实 source；旧 `test_phase_ii_c02b_position_profile.py::position_candidate` 会读真实资产并 import 已删 source | ①拆开或明确选择混合节点，先审 collection/fixture 副作用；②纯入口在 fresh process 守卫 SDK import 和安装资产读取，离线 H5 允许只读指定证据；③asset/native 必须显式选择并登记预算。退出：纯入口真实通过且无 SDK／资产访问，错误选 native 明确拒绝。 |
| T03 | 旧 `c02b_position_candidate.py`、`original_panda_test_source.py`、R02/R03/R06 fixtures 仍依赖退休 Position 包；版本旧 Judge 名称合法 | ①逐项处理盘点中的 34 文件：当前公共行为迁入版本诊断、历史 oracle 留显式入口、仅旧实现细节删除、未触及其他版本按 ref 恢复；②先迁有价值 claim，再删孤立 fixture／imports；③列每个删除／迁移／保留理由和调用者。退出：本版本当前检查不再要求恢复 candidate，合法旧格式判断仍严格。不得全局替换旧 reader 名称。 |
| T04 | `api.py` 的 CompiledModelOptions/PhysicsFingerprint 是可选公开读回；MuJoCo fixed_attachment receipt/diagnostics、精确原生名检查仍有用途；原注入 context 和直接诊断施控已退出当前实现 | ①按真实 caller 复核旧总账 TEST-03 的已解决部分并复用；②将剩余纯实验注入／计数包装放 diagnostics 或局部 fixture；③保留 source admission、native readback、typed fault、资源/单位/clock 检查。退出：列出实际移除/保留符号；不因 `_f05`、`probe_hand_` 等名称删合法准入或历史 codec，不再搬一次已迁完的代码。 |
| T05 | 部分 v211 测试、RGB/source routing、提交/fault 检查仍在未版本化 tasks 目录，互相 import 测试 fixture | ①按当前 claim 找已有更强 detector；②把仍支撑 v2.1.1 的行为检查及最少 shared fixture 迁到版本目录；③移除重复实现细节测试与旧位置依赖，保证检测 stale、资源冲突、副作用后 fault 等真实退化。退出：迁移表＋关键拒绝案例；不复制全部旧测试，也不为凑数新增镜像测试。 |
| T06 | `test_legacy_leaf_codec.py` 读取 `phase_ii_01_sol_luna_handoff...` 的两份旧 H5；现有离线检查会受后续路径清理影响 | ①为历史 H5/Judge 和当前 H5 readback 列依赖；②当前 reader 与实验 oracle 分别检查；③冻结将来最终包逻辑位置及旧→新映射要求，实际路径切换交 U5/U6。退出：所需原始样本明确，不新增生产 fallback，E15 不会误删测试唯一输入。 |
| T07 | 没有本轮完整的最终检查选择和移交记录 | ①跑迁移影响的精确纯/fake／离线节点；②只有实际改 native owner 才补最短路线；③输出单份分类/退休对照及统计，压缩 README/账本。退出：提交、原始命令/结果、未测边界；E11 代码部分自评完成，TEST-04 证据归并义务继续交 U5。 |

## 5. U2：正式 caller 与外围兼容

正式调用链继续是 `make_env → 统一配置/TaskBuildRequest → builder → Env → Runtime`。任务 Solution 由 caller 执行 `act → env.step → observe`。外围有自己的合法协议时，只适配受影响 Core 交接，不重造 Env 或强迫 benchmark 改任务语义。

| ID | 当前源码／调用事实 | 实施步骤及退出证据 |
| --- | --- | --- |
| T08 | `script/env/_common.py` 已生成正式 execution/episode；`examples/tasks/pick_cube.py` 同时提供 public 与高级 Harness，Isaac 示例仍展示手工临时 manifest | ①列 single/file/inline、camera、trajectory、四任务示例到实际入口；②普通路径只使用正式配置、已安装资产和相机声明；③高级 frozen Harness/外部 Candidate 单独说明，保留有真实消费者的高级功能。退出：四任务调用对照和一个 YAML 等价 mapping 示例，无需用户先理解 F06/receipt/临时 source。 |
| T09 | `_bootstrap.backend_candidates/with_backend_fallback` 对 auto 和明确 cuda 都捕获广泛异常并转 CPU；记录日志不等于运行了请求交集 | ①区分普通脚本“auto 选择”与明确 provider/device；②显式选择失败不得改成另一个交集的成功，保留原异常／请求/实际身份；③检查并行/learning 示例共同 helper 影响，更新相关 caller。退出：fake 故障例证明配置错误不触发伪 PASS；不另造 resolver。 |
| T10 | `record._completion_result`、planning `_completion_fields`、`examples._common.episode_result`、Harness completion facts 分别投影结果，close 部分在 finally | ①对照 Task/Solution 权威字段，列触发条件差异；②消除实质重复或修正不一致，纯展示可保留，Harness 专用 schema 不搬进 Task；③保证失败/timeout/close 异常仍形成报告。退出：相同 facts 的各入口结果一致，task_success、expert_complete、planned/outcome、runtime_valid、close 分栏；不得降低 Nut 策略或把 truncated 当成功。 |
| T11 | `vectorization/factory.py` 仍走 component config 与 `environment_type(config=..., build_runtime=False)`；parallel/SB3 另有 autoreset、terminal observation、render owner；G06 未开始 | ①以假 Runtime/工厂截获方式检查纯构建、space 和延迟 native；②保留尚被使用的 component batch 能力及合法配置；③四正式任务未有 batch adapter 时，在启动资源前明确拒绝并写 G06 边界。退出：逐 caller 的支持/拒绝证据，auto-reset/terminal observation 既有合同未退化；不顺手实现 G06、训练或 CPU 回退。 |
| T12 | `alg/agent_factory/`、`alg/rsl_rl`、`script/rl/pendulum_ppo.py`、`examples/learning/pendulum_sb3.py` 消费 spaces／batch 和数据；总账旧 `alg/agent_factory.py` 路径已不准确 | ①查实际 imports 和 schema/shape/action consumers；②选 fresh import、space/数据离线合同，修受影响直接 caller；③明确历史 Go2 退休与旧 batch 示例运行条件。退出：无引擎的 learner import 和代表 space/dataset 兼容证据；不要求全算法或完整训练回归，不把旧示例标题当当前成功。 |
| T13 | LIBERO `environment/selected_reference.py`、`controllers/{osc,source_gravity}.py`、`trajectory/{worker,reader}.py` 使用 Core binding/session/H5；worker 的 step_with_solution 是受限兼容 caller | ①逐符号核对受影响 API、source/readback、Frame/单位、OSC/gripper cadence、close；②真实失配在 bench owner 薄适配，现合同允许保留兼容入口；③以 bench 现有合同节点/代表离线 reader 证明，未改的原生链做 diff 复用。退出：保持 LIBERO 原任务谓词和来源，不改成 PickCube，不重跑全 A123。 |
| T14 | objects/planners/reporter/utils 既有合法职责，不能从文件大或旧名字直接判断需重构 | ①查反向依赖和真实 step/success owner，修有证据的问题；②更新普通示例/CLI 帮助及兼容去向；③冻结 U3 可复用的真实运行命令和报告出口。退出：CALL-01～04 逐项结果、最小验证、文件/代码变化与提交；无问题的模块给原样保留依据。 |

## 6. U3：完整 Solution 与同次读回

这是本轮必须新交付的功能证据；不能用 E05～E10 短程覆盖。接收 owner 为现有 Task/Solution、正式 caller、Runtime 和 Recorder；版本 diagnostics 可以增加薄监督 runner/独立 reader，但不复制 Solution、controller、Env 或任务成功判据。

| ID | 当前事实 | 实施步骤及退出证据 |
| --- | --- | --- |
| T15 | 两 CPU 示例/CLI 已有完整循环，Isaac 需要选定解释器及正式 USD；旧短 probe 非完整运行 | ①冻结下表五条正式交集、seed/horizon、原任务/Controller 参数、source 和代码身份；②确认实际 command/interpreter/安装资产、单 writer、现有共享锁、资源窗口；③按实际 timebase 写 interval/substep/capture/App 启动预算（含构造/reset 重建），输出唯一新目录。退出：一份能执行且能诊断重试的 native-plan，不用默认一次 App 或一个 launch 人为拆包。 |
| T16 | PickCube MuJoCo G02 历史 seed31 960 transitions 成功；GeoPhys 曾有时间 guard，后续仅有短链；新架构尚无完整结果 | ①MuJoCo seed31、既定 R3 做一次完整记录；②GeoPhys 同 seed/正式 profile 一次完整尝试；③一般构建/控制/时钟/记录问题在当前窗口修复并只复验受影响项。退出：两条完整结果＋同次 H5；MuJoCo task success 与完整 Solution 成立，不把 solver 失败隐藏为没测。 |
| T17 | PickCube 现在正式准入 Isaac CUDA 的 R3；现有 Position/effort 短程和 SDK 关闭限制不证明完整 Solution | ①走正式 make_env 与已安装 delivery，复用既有监督 worker/公开接口；②运行 seed31 完整 R3 并记录，同次 close/App 结果；③若现有 CLI 只支持 CPU，只补其缺少的正式参数或版本薄 runner，不另开 candidate。退出：真实完整结果；资产/能力阻塞如实 OPEN 并给方案/维护者决定，不拿 mock/短程填 PASS。 |
| T18 | Nut 仅正式支持 MuJoCo/GeoPhys CPU R3；G02 seed19 曾2377 transitions 成功，优化后未完整复验 | ①两 provider 各 seed19 一次完整运行和记录；②保留五 native samples、阶段/guard和原 completion；③适配缺陷在原 owner 修，solver/策略未成功单列。退出：两条结果，Nut MuJoCo task success、planned trajectory/outcome 与 completion 满足原标准；不添加 Nut Isaac 或简单主体策略。 |
| T19 | H5 reader/短 readback 已有；worker JSON 或 finish_recording 返回不能独立证明完整运行 | ①独立进程从本次关闭 H5 读动作/Target-Ack或当前等价控制、T/T+1、state/clock/source、最终任务 facts、有关 RGB；②复算谓词所需量并与同次结果关联，缺可观测字段则明确补齐 owner；③原始记录与读回绑定路径/大小/hash。退出：完整同次 V09；不要求再模拟、不拼不同 run、不升格 D0。 |
| T20 | V01～V07 多数有强旧证据；共同 caller/报告修复可能改变部分路径 | ①逐 claim 列旧输入/当前相关 diff/复用原因；②本次完整运行已覆盖的短程不重复；③只补未被覆盖的受影响 reset/错误/非Position或RGB边界。退出：V01～V09 短映射，三原生与 cross 有证据去向；不增全矩阵或像素评分门。 |
| T21 | E13 还无最终结果表，失败执行次数与 task failure 需区分 | ①给每条 runtime validity、task success、Solution completion、record/readback、close、测得步数/unknown；②只对适配缺陷定向修复，不反复调参追 solver 成功；③交付冻结输入/补丁/提交关联，保留失败原因与更正。退出：原总账完整 Solution 门满足或显式 OPEN，未经维护者批准的例外不算事件完成。 |

### 6.1 完整运行的有限矩阵

| Task | provider/backend | Controller／seed | horizon 规划起点 | 必须报告 |
| --- | --- | --- | --- | --- |
| PickCube | MuJoCo CPU | 正式 R3 `r3_continuous_v1`／31 | 1000 | 完整执行、任务成功、Solution 完成、同次读回、close；此路线必须成功 |
| PickCube | GeoPhys CPU | 同上／31 | 1000 | 同样字段；solver/策略失败可如实报告，运行合同缺陷必须处理 |
| PickCube | Isaac PhysX CUDA | 正式 R3／31，预装 USD | 1000，按实际准入冻结 | 同样字段，实际 SDK/设备/App/close 和未知启动步；不静默改成 CPU |
| NutAssembly | MuJoCo CPU | 正式 R3 Outcome／19 | 6000 上限内 | 完整 planned/outcome 与任务成功、同次读回；此路线必须成功 |
| NutAssembly | GeoPhys CPU | 同上／19 | 6000 上限内 | 同样字段，区分 solver/策略结果与执行故障 |

seed/horizon 是依据当前正式参考的冻结建议，不是新资格门。T15 核对实际任务/Timebase及授权后固定；不擅改 seed、阈值、guard 或策略来追 PASS。Nut Isaac 当前 `selected_supports_isaac=False`，不在本表；不是本轮应实现的新能力。其他正式能力真实不可用时，按总账给具体边界、修复方案及维护者例外决定，不能自行记 N/A。

CPU 现有入口可复用：`examples/recording/record_expert.py --env-id <正式UID> --provider <mujoco|geophys> --seed <31|19> --horizon <1000|6000> --output <新run>/episode.h5`。四个 CPU 组合按表显式展开，分别输出；外层资源/锁计划必须先生效，示例的 RLIMIT_AS 不等于进程树 RSS 限制。Isaac 命令在 T15 经现有 caller/worker 明确解析后冻结，不能照抄 CPU 示例并假定已支持。预计显式子步由每条 horizon×实际 substeps 算上界，启动/reset 隐式推进测不到则 unknown，不伪造零。完整运行默认 state-only；已接收 RGB 依影响复用，不强制五条都录图像。

## 7. U4～U7：代码接收与项目收尾

### U4：文档、Skills 与代码优化接收

| ID | 当前落点 | 实施步骤及退出证据 |
| --- | --- | --- |
| T22 | `capabilities/capability-matrix.json` 仍是 `PLANNING`／2026-11-03，旧 pin 与 NOT_RUN 不能代表当前能力 | ①保持版本单一能力 owner，区分原目标和当前实现/受测证据；②按具体 task/source/controller/provider/backend/render/camera 填最终身份、readback、close 与限制；③关联 U3，不能一键全表 PASS。退出：每个当前支持断言可回查，G06/G07 未实现明确。 |
| T23 | README/current-state/api/guides、protocol map、task_env/doc 和 examples 各有历史/当前混写风险 | ①建立版本 README→current-state→API/能力/本账本单向恢复；②把设计/已接收/未测分开，过时“当前”移为有时间的历史；③落实已有指南要求，给规范配置、主体/Controller、相机、Solution、记录示例。退出：不要求内部 receipt 的最短用户流程与源码相符，冻结历史不改事实。 |
| T24 | 根 AGENTS、项目/TaskEnv/test/API/architecture/证据 Skills 部分已更新、部分仍以旧矩阵或 candidate 为当前 | ①逐 owner→API→caller→失败语义→测试命令核对；②更新发现入口及相关引用，不复制新 Skill；③只在行为实际变化处写可执行约束。退出：后续 agent 不再恢复旧 candidate 或重复 lifecycle，Skill 示例有最小检查收据。 |
| T25 | doc validator 基线2 errors：保护 MUJOCO 日志对旧基准不同、历史主审源码链接指向已退休文件；另96历史链接问题 | ①区分当前断链、历史 source-ref、已知保护字节；②修当前导航及历史源码定位方式，保留原决定和保护原件；③检查器若需改进历史/保护报告语义，在实际 owner 有依据地修，不能改保护文件/随意改 expected hash 来“全绿”。退出：无新增当前错误，遗留逐项处置/决定；剩余错误不能笼统写 validator PASS 或因96条历史问题重造候选。 |
| T26 | 原60项尚无最终统一 owner/证据表；E00～E10 已接收不等于全项目已接收 | ①按第8节展开恰好60个唯一 ID；②已有实现复用其接收、实际 owner 与证据，新增义务由 T 节点补齐；③对交叉项区分代码部分和 E15/E16 项目部分。退出：没有漏项或用测试总数代替结案；N/A 必须维护者明确确认。 |
| T27 | 当前只有分批有界主审，E11～E14 与完整 Solution 未独立审 | ①独立审实际 diff、最终调用链、测试纯度、五条完整结果及未成功原因；②修普通主审小缺口并只补受影响证据；③实现自评、独立结论与人工决定分列。退出：代码优化独立主审＋维护者代码范围接收；不把 E15/E16 未完成的项目条目强行 PASS。 |
| T28 | 每批记录容易叠加并再次变成逐命令日记 | ①将 E00～E14 最终效果按模块压缩，保留源码/证据/限制入口；②同步 API/Skill/current-state/orchestration，保留历史输入与 attempt；③冻结 U5 的最终能力 claim 表。退出：一个当前恢复入口，代码接收与项目待完成单列，G06 不启动。 |

### U5：五个 Stage 最终包与依赖闭包

| ID | 当前落点 | 实施步骤及退出证据 |
| --- | --- | --- |
| T29 | G01～G05 主审在版本 maintenance；大量原包在主/旧 checkout、evidence_import，G02还有外部 execution-output 人工时间线 | ①从最终接收 claim 反查实际同次原始证据，不按目录编号最大选包；②列每个 substage/source 身份、输入、reader、原始H5/RGB/receipt和外部依赖；③分最终成功、核心诊断、可重建、其他版本、活动/保护项。退出：五 stage 候选保留表，不复制全目录充数。 |
| T30 | G01 是协议/设计接收；G02 有 seed31/seed19 同次成功，也有 seed32 FAIL；不能混成全成功矩阵 | ①G01 以权威协议/主审/ref为核心，不伪造 native 数据；②G02 保留真实完整成功记录及独立reader和必要来源，失败只留解释最终范围的核心材料；③分别建立 stage01/02 唯一包入口。退出：能复算各自原结论；不将 U3 新结果冒充 G02 当时结果。 |
| T31 | G03 原N08与修订结论、G04 effort/wrench/reset、G05 5a/5b/5c及单元4～9，证据来自多个不同源码身份 | ①分别选 G03 三 provider/reset、G04 typed/实际effort/wrench/控制器reset、G05 原生/窗口/taskRGB/cross/统一主体受测结果；②保留 COM严格FAIL/有界采纳、R05c资格、未知推进及重要执行偏差；③建立 stage03/04/05 包并声明每个子结果身份。退出：五个包齐全；不把 ACK当测力、不拼不存在的一次全stage成功。 |
| T32 | source snapshots/派生 USD/mesh、副本/cache 和 frozen输入混在 run 内；E00 dirty 副本、历史 H5/Judge和 E05 review 样本仍有消费者 | ①按实际引用闭包选必要字节，用内容身份去重；②第三方原件和已安装资产独立保全，只记录冻结ref/hash/必要闭包；③把 E00～E14 优化结果另设简洁汇总入口并迁移其必要证据，不硬塞进历史stage。退出：manifest能绑定实际保留字节；没有只留失效绝对路径或凭hash声称已恢复。 |
| T33 | 各最终结论目前需跨旧 attempt 寻找 | ①复用现有 manifest/receipt，生成新包清单及旧→新映射；②从新包独立读回并校验必要输入/原记录/结果；③验证不需要待删目录，原manifest不冒称原目录未变化。退出：另一人只从五个入口和优化汇总即可复核；不重跑原物理、不覆盖旧结果。 |
| T34 | 未形成具体删除对象及外部依赖检查 | ①列确切路径、类型、owner、分配空间、保留/归并位置、所有已知入向引用、恢复方式；②排除子worktree、锁、live lease、保护输入、第三方/全局cache；③提交可审查处置单和独立复算结果。退出：准备好 U6 最终操作清单；U5 本身不删除原件。 |

### U6：输出清理与引用切换

| ID | 当前落点 | 实施步骤及退出证据 |
| --- | --- | --- |
| T35 | `script/agent/builtin_example_validation.py::LOCK` 仍固定指向 `phase_ii_01_sol_luna_handoff.../shared_native_execution.lock`；测试也读该目录旧H5 | ①列所有锁使用者/双锁协议/原 inode 与数据消费者；②无活动 owner 时在现有协调 owner 迁移锁配置，所有写/运行端一致切换；③将 tests/reader/当前索引改为归并后位置，历史页保留可定位映射。退出：旧路径不再被当前运行依赖；不得在有 flock owner 时删除/替换锁制造两个并行锁。锁若不迁移，该目录/锁须从删除清单排除并如实标 OPEN。 |
| T36 | 84.46 GB 是混合总量，无证据支持全删；另有 temp_outputs、cache、旧cwd日志 | ①核对 U5 具体清单与执行时授权及活动窗口；②先完成可恢复保全和路径切换，再按清单清理冗余 attempts/cache/副本；③发现类型/hash/owner漂移停止该项，其他独立已授权项继续。退出：真实删除收据及失败原因，无范围外/全局SDKcache/保护原件清理；不递归跨嵌套worktree。 |
| T37 | 已有 workspace/temp 输出不跟踪，cwd 副产物可能漏盘点 | ①复查实际路径、包外cwd输出及忽略规则；②确保新 worker 独立cwd/显式output与cache；③归并后查 tracked生成物、保护 SHA/pins 和当前引用。退出：Git 中原始生成物仍0，保护输入未变，无必要证据遗漏或悬空引用。 |
| T38 | 尚无清理后的独立复算/空间成果 | ①相同口径重算目录/文件/分配字节，扣除归并新增量，区分逻辑去重与实占回收；②从最终包再读关键结论；③压缩 E15 交付，列未处理/保留例外。退出：E15 的包/引用/真实下降三者同时成立；只复制归并而不清理不能写 E15 全完成。 |

### U7：refs／worktree 与项目最终接收

| ID | 当前落点 | 实施步骤及退出证据 |
| --- | --- | --- |
| T39 | 本地9 heads、4 tags、7 cached remote refs、6 worktrees；当前chat artifacts为空；本地HEAD关系不证明路径无私有内容 | ①在操作前刷新 refs/owner/锁/writer/工作树、pins、ignored和本地文件；②检查祖先/独有提交及未跟踪/类型变化；③确认手工worktree归属，不用当前chat archive工具强行删除其他chat checkout。退出：逐对象处置表；远程缓存不是本次fetch结果。 |
| T40 | 三旧阶段分支独有提交数均0；各detached HEAD也已在当前历史中，但 frozen worktree 有锁，core-baseline 有 `T GeoPhys`/`T Menagerie` | ①保存 refs/object ID清单、必要恢复ref/bundle/本地字节及输入属性；②原件/ignored/submodule内容在适当保留位置实际恢复验证；③维护者要求保留的冻结tag、v1.1.0分支不改。退出：证明代码与本地证据都已保全，不能用祖先关系或bundle替代ignored文件保全。 |
| T41 | 要删除的旧 checkout 包含子模块/嵌套worktree，App 管理工具可能不支持 archive | ①按对象确认 Git/App 能力和本次清理授权，先解除实际依赖；②有子模块用受支持流程处置，locked/historical需确认已保全和明确授权；③逐 worktree 移除并验证管理状态，不以 `rm -rf`/`--force` 绕过未解决检查。退出：旧checkout安全退出或具体阻塞保留；不得动其他会话活动目录。 |
| T42 | 清理白名单为 main/develop/确定版本分支/一个当前主题分支，冻结tag保留 | ①在 worktree 释放后删除三个已保全的旧阶段branch；②保留当前stage、main、develop、v1.1.0/v2.0.0/v2.1.0和4 tags；③不为白名单新建/移动v2.1.1，不merge/push或改remote refs。退出：预计本地heads9→6，worktrees6→1，实际/例外逐项报告；数量目标不授权强删。 |
| T43 | 原 source、锁、H5或脚本可能仍有旧绝对路径 | ①从保留checkout运行纯配置/import/space/正式示例路径检查；②从五stage包及优化汇总独立读取并做一项实际恢复演练；③如移除改变native资产/运行路径，仅补受影响最短路线，不再跑五条完整Solution。退出：清理后路径与资源合同可用、无旧worktree必要依赖，保护/pins/refs核对。 |
| T44 | 代码优化接收与项目优化接收是两项决定 | ①交最终文件/代码/目录/空间/refs/worktree前后、60项结果、恢复和剩余限制；②独立主审项目清理与恢复，维护者最终接收分列；③同步唯一当前入口。退出：E11～E16逐事件结论、代码与项目接收分别成立后才建议决定G06；不自动开始G06，不称v2.1.1完成。 |

本轮观察：旧 `v210-integration` checkout 有3个 untracked保护类文件；嵌套 `core-baseline` 有两处类型变化；`archive_v1_0_0` 为 locked。完整路径/状态见[refs-worktrees.json](../../../../../workspace/maintenance/v211_e11_e16_replan_20261113_001/refs-worktrees.json)。当前主chat无附属worktree不代表这些手工历史checkout可直接由App归档。目标6→1以满足保全、归属及具体处置授权为前提；若例外未被维护者接受，E16留OPEN。

| 规划时额外 worktree | 当时 HEAD／本地状态 | 后续具体处置前提 |
| --- | --- | --- |
| `~/.codex/worktrees/v210-integration/Geochora` | `f3674a0b`／stage5；3个untracked文件，workspace约13.79GB | U5保全stage证据及本地文件，解除当前锁/资产/脚本路径依赖 |
| `~/.codex/worktrees/phase-ii-01-camera/Geochora` | detached `2cba22d9`，普通status干净 | 核ignored及历史引用/owner；干净status不等于没有必要本地数据 |
| `~/.codex/worktrees/archive_v1_0_0` | detached `42787f5e`，locked，普通status干净 | 冻结tag/必要原件和本地字节实际可恢复，明确解除锁/移除授权 |
| 主checkout `workspace/maintenance/geophys_upstream_reset_20261022_001/core-baseline` | detached `60b3ecac`，两处submodule类型变化 | 先查类型变化及本地内容；U6删除父目录时不得递归跨越此worktree |
| 主checkout `workspace/maintenance/p2_0_v1_1_clean_checkout_20261017` | detached `bee498d1`，普通status干净 | 原版本依据/ignored内容保全，按worktree流程处理 |

规划时额外分支为 `codex/v211-stage3@842e1efd`、`codex/v211-stage4@3ca161c4`、`codex/v211-stage5@f3674a0b`。它们相对规划HEAD独有提交数为0，仅证明提交可达，不证明所有原始证据已保全；stage3/stage4 后续已按具体授权删除，当前状态见第11节。当前分支与main/develop/版本分支仍未集成，不据此merge。

## 8. 总账映射与证据选择

| 总账条目（合计60） | 本轮处理 | 接收/收口所在 |
| --- | --- | --- |
| GOV-01～04（4） | E00～E10 已接收机制复用；当前规范、状态和全局恢复补齐 | T23～T28、T44 |
| ENTRY-01～03（3） | 不重写入口/配置/相机，核真实caller和示例 | T08～T09、T20、T23 |
| TASK-01～04（4） | Task owner已接收；正式Solution和下游回归补齐 | T14、T16～T21、T26 |
| ENV-01～05（5） | 生命周期/提交已接收；按当前diff复用或补受影响项 | T04、T10～T11、T20、T26 |
| SUBJ-01～03（3） | 四主体/嵌套构建已有证据；不重开共同builder | T05、T20、T26 |
| CTRL-01～05（5） | typed/资源/时钟不弱化，完整动作链验证 | T05、T10、T13、T16～T20 |
| SRC-01～04（4） | source/admission已归位，最终资产闭包/迁移引用补齐 | T04、T15、T20、T32、T43 |
| RUN-01～04（4） | 复用公共Runtime与worker，完整运行/锁/路径验证 | T04、T15～T21、T35、T43 |
| REN-01～08（8） | 三原生/cross/RGB的受测证据按影响复用，保全最终包 | T05、T08、T20、T22、T31～T33 |
| OBS-01～02（2） | schema/space/数组已有实现，caller/记录读回补齐 | T11～T13、T19～T20 |
| REC-01～03（3） | E10普通/历史/重执行分层复用，全程记录与路径收口 | T03、T06、T10、T19、T32～T35 |
| CALL-01～04（4） | 本轮直接交付 | T08～T14 |
| TEST-01～04（4） | 本轮分类/迁移/检测器与最小充分证据 | T01～T07、T19、T29～T38 |
| DOC-01～02（2） | 本轮当前文档/Skills与链接收口 | T22～T28、T35、T44 |
| PROJ-01～04（4） | 本轮实际归并、清理和ignored保全 | T29～T38 |
| BRANCH-01（1） | 本轮refs/worktree/恢复及项目接收 | T39～T44 |

V01～V10为验证清单，另列不混入60个代码/项目条目。T20负责V01～V07的精确复用/补测表，T16～T18负责V08，T19负责V09，T22～T44负责V10。每条写实际命令/node、输入/source/config、owner diff、预期成本、原始证据和限制，不能只写“relevant tests”。

已有可复用节点示例（执行前必须核 fixture 和依赖；不是本页授权整模块运行）：

- `v2.1.1/test_formal_configuration.py::test_config_resolution_does_not_open_assets_or_import_native_sdks` 与 `::test_make_env_resolves_public_config_once`：配置纯度与一次解析；该文件其他节点不全纯。
- `v2.1.1/test_episode_import.py::test_episode_contract_import_does_not_load_h5py`、`test_recording_observation_metadata.py` 的声明保全：import及metadata合同，不代表物理执行。
- `v2.1.1/test_task_rgb.py` owned/stale/close fake节点：公共边界与生命周期；真实采图依旧证据/受影响最短路线。
- 旧 `test_record_cli_completion.py` 的 timeout/terminal完成检查、`script/agent/test_completion_facts.py`：在T10对比原oracle后迁移/复用；不是让旧fixture要求产品分支。
- `bench_deploy/libero/diagnostics/test_controller_policy.py`、`test_replay_contract.py`：按实际node选择，不默认全资产/原生流程。
- E00～E04生产`912416e6`、E05～E10主审输入`d9dc02c6`/小修`7a098423`和各单元native证据，按其原冻结输入和实际diff复用，不改称本轮HEAD重跑。完整Solution仍需T16～T19。

## 9. 度量、状态与操作边界

每个 U 结束在第11节更新一行，并提供一份精简结果/证据入口，不新建44份报告。必须报告：

1. 实际输入/输出HEAD、生产patch身份、相关本地提交、节点/运行结果及证据。纯/fake、离线资产、native短程、完整Solution分开；失败、修复及复用不能混报全绿。
2. 范围内与项目 tracked blob 数前后；新增/删除/迁移路径；生产 Python +/−/净量、迁移量、诊断/测试和文档分桶。本轮相对`a6b107ac`与累计相对`1f1359ee`分列，不冒领既有成果。文件迁移代码不同时算删除/新能力。
3. 构建与调用链：消除的入口/分流/越权，实际最终owner；无生产变化如实记0。可读性用更直接的依赖和明确职责说明，不以行数单独评价。
4. adapter 对齐：source/state/clock/submit/resource的变化及保全；未涉及写未涉及。若共同owner改动，列受影响claim及最短复验。
5. E15/E16追加同口径目录/文件/逻辑字节/分配字节、refs/worktrees/空间及恢复测量；保留/删除原因与实际净变化，不能用84GB总量作收益承诺。

本规划不授权清理执行。正式实施时，代码/测试修复按维护者给予的范围自主完成；U5先交付具体可审查保留/删除/恢复清单。若其后已有维护者对该具体清单的授权，U6/U7按授权执行，不重复询问；若缺授权、对象归属/活动状态或保全仍不明确，先完成所有可逆准备，在实际不可逆操作前提出**一次具体问题**，标明缺哪项依据。不得用等待时间当批准，也不得为避免询问强删。push/merge/tag/发布、改子模块pin和启动G06均不包含在本Goal。

最终结果分为实现自评、独立主审、维护者接收。代码优化在U4单独判断，项目优化在U7单独判断。U4可完成代码范围接收而PROJ/BRANCH保持OPEN；只有全部对应义务完成或维护者明确批准例外，才结束整体优化。不得把DEFERRED/BLOCKED/NOT_RUN自动视为总账关闭。

## 10. 范围外发现

| 事项 | 处置 |
| --- | --- |
| G06 batch真实并行、部分reset、整批重建，G07最终三provider×三seed | 后续阶段；本轮仅保全已有caller合同，不补新并行能力 |
| 任意Robot/Controller/source组合、动态renderer切换、完整D0或跨源码重执行、完整训练 | 不纳入；不以本轮接收扩大能力 |
| 其他版本全部diagnostics、全局SDKcache、全部failed attempts永久保留 | 不泛化为本轮清理/归档任务；只保留最终结果所需及核心限制材料 |
| 实施中新发现 | 按“当前事实—影响T项—是否阻塞—未来owner”在本表集中补一行；影响当前合同才在同单元修复 |

## 11. 当前实施结果（唯一更新区）

2026-11-13 仅交付规划；E00～E10维护者接收已记录。下表不预填PASS。

| 单元 | 状态 | 最终效果／提交／验证／限制 |
| --- | --- | --- |
| U1 T01～T07 | SELF_ASSESSED_COMPLETE | 版本诊断入口、历史去向及证据依赖见[诊断 claim/owner 表](../../../../../task_env/diagnostics/tasks/v2.1.1/README.md)；本行所在提交为输出 HEAD。TEST-04 最终证据归并仍归 U5；代码整体独立主审及维护者接收不由本单元自封。 |
| U2 T08～T14 | SELF_ASSESSED_COMPLETE | 正式 caller、batch 边界、完成事实及 LIBERO 检查见[U2 caller 对账](../maintenance/reviews/20261113_e11_e16_u2_caller_review.md)；输出为本行所在提交。直接 Isaac 与完整 Solution 的真实执行归 U3，独立主审和维护者接收归 U4，不由实施者自封。 |
| U3 T15～T21 | IMPLEMENTED_REVIEW_PENDING | 原五条完整尝试见[U3 实施结果](../maintenance/reviews/20261113_e11_e16_u3_solution_evidence.md)，旧 Isaac 失败原样保留；后续 `0506ae26` 的 `solution-002` 完成原任务。维护者同意的 T19 同次联合口径及五路读回见[联合证据](../maintenance/reviews/20261113_e11_e16_u4_joint_completion.md)，H5 单文件不自含完整 completion；T19/T20 的有界联合口径已通过 U4 独立复审，限制保持明确。 |
| U4 T22～T28 | MAINTAINER_ACCEPTED_BOUNDED_U4_CODE | 单一能力矩阵、当前入口、Skills、[60 项逐行表](../maintenance/reviews/20261113_e11_e16_u4_row_reconciliation.md)及[独立主审／条件接收](../maintenance/reviews/20261113_e11_e16_u4_independent_acceptance.md)已记录；项目和分支仍 OPEN。 |
| U5 T29～T34 | SELF_ASSESSED_COMPLETE_BOUNDED | [有界证据选择与复核](../maintenance/reviews/20261113_e11_e16_u5_evidence_selection.md)：五 stage、优化五路线及必要诊断入口已冻结，七项代表性离线检查 PASS；限制如报告。原件未删除；T34 的处置授权与执行时 owner/锁核查、U6 清理及 U7 最终接收仍 OPEN。 |
| U6 T35～T38 | IN_PROGRESS | [目录保留与处置准备](../maintenance/reviews/20261113_e11_e16_u6_directory_disposition.md)已列具体候选、保全及锁快照；两份历史 H5 测试已切到保留对象并通过 25 项检查，四份 physical 输入从新位置通过 8 项检查，Panda 和 G05 USD 测试切换到包内文件，定向 pxr source 检查分别 8 项及 5 项通过；六项临时副本和四个历史目录已分别按具体授权删除并完成代表性复核。经维护者确认停用，integration 和主 checkout 旧锁及新路径已统一为同 inode；旧双锁计划和其他 checkout 的限制见处置表。[当前锁及旧路径调用核对](../maintenance/reviews/20261114_e11_e16_u6_lock_path_audit.md)补充逐类使用与受守卫 10 项通过；旧路径仍为正式示例依赖，T35 保持 OPEN。refs/worktree、本地内容保全与项目净空间核算仍 OPEN；integration 快照候选普通文件已全量恢复及独立复核，拼合仅抽样且 368 个候选父目录不可写，新增恢复目录约 9.29 GB；只读预检及合成故障试验已完成，真实删除执行器和具体授权仍缺，暂不具备删除条件，详见处置表。 |
| U7 T39～T44 | IN_PROGRESS_INTEGRATION_RETIRED | [处置与恢复入口](../maintenance/reviews/20261113_e11_e16_u6_directory_disposition.md)记录前次部分失败及2026-11-14维护者续授权收尾：64,337个残留条目逐项保全核验后，仅修复368个目录权限，已注销integration残留和stage5分支均已删除；本地heads 9→6，注册worktree为5（本轮开始前已注销integration）。四保护SHA、pins及包内内容对象不变，240项纯/fake、25＋8项离线H5及七项包检查通过。本轮固定范围下降约15.59 GB；约15.4 GB临时快照仍保留，原Git管理元数据缺口仍明确。其他工作树、快照精简、历史累计空间和维护者项目接收继续OPEN，不重开U4/U5。 |

### U1 结果（2026-11-13，实施自评）

输入 HEAD `cd486aff5ce6b5d0bcdc6561529b5c6c388efc22`；输出为本结果所在提交。T01～T07 在本单元按以下范围 PASS：T01 按版本文件及精确 node 区分纯/fake、离线 H5、真实 source、CPU、GPU/App 和窗口；T02 纯入口 fresh-process 守卫及子进程 canary，错误选择原生节点拒绝；T03 对规划盘点的 34 个旧引用文件列出历史／当前去向，保留历史 Judge、codec 与原结果；T04 保留 provider 准入、可选 compiled readback、fixed attachment receipt 与 typed fault，465 个非诊断生产 Python 文件的直接、相对及字面量动态 import 静态检查未见反向依赖；T05 迁移有当前职责的物理、相机、effort、主体及自由关节检查，旧 candidate 与旧 reset fake 明列历史；T06 冻结两份历史 H5 和四份当前短程 H5 路径、大小及 SHA-256，U5/U6 负责复算与重定位；T07 完成定向验证与本地提交。未列入固定入口的混合模块不是纯测试；历史旧功能不因当前表格被重建或扩大认证。总账回核：TEST-01/02 的本单元诊断分层与 claim 已覆盖；TEST-03 复用已接收的 S04/S32 迁移并核对当前 owner，本轮无新的越权生产实现需迁；TEST-04 的五 stage 最终证据闭包仍 OPEN，归 U5/U6。

固定纯/fake 入口 132 PASS；R02c/R03c 离线读回和复制品篡改 25 PASS；四份显式一 interval 记录的离线读回／篡改 8 PASS。`strace` 验证所测纯集无成功打开受守卫的资产／SDK 路径，旧 H5 和当前 H5 原件分别只读；守卫并非 OS sandbox，`-I/-S` 和其他外部目录不在其声明内。旧 R01b 文档示例节点因输入 HEAD 已缺原标题而失败，列 U4 文档历史归属；不得称全部历史测试通过。文档 validator 保持基线 2 errors/96 历史链接问题，新增错误 0。未运行 source/native/App/window；没有生产代码变化，COM 原严格 FAIL/有界采纳不变。原始命令和跟踪文件在 [本单元 ignored 记录](../../../../../workspace/maintenance/v211_e11_e16_execution_20261113_001/)；不等于完整 Solution 或项目接收。

变更量按 `git diff --cached --no-renames --numstat` 计：本 U 相对输入 HEAD，生产 **+0/−0/净0**，诊断 22 路径 +2,590/−1,309（净 +1,281），账本 1 路径 +9/−1；`--no-renames` 将 3 次改名计为 6 路径。诊断全目录 tracked 451→459、Python 394→400；版本目录 tracked 30→40、Python 30→38。按原函数／整文件行数统计，约 1,221 行已有测试/fixture 迁移并适配；另复制一份 736 行合成 Scene JSON 给版本检查，旧副本仍有历史 caller。其余新增为守卫、负例及索引，不是生产能力扩张。相对 `a6b107ac`：生产 +0/−0；诊断 +2,590/−1,309；文档/Skills +368/−27（含两次规划提交）。累计相对 `1f1359ee`：生产 +8,284/−17,638；诊断 +9,674/−1,308；文档/Skills +2,302/−114。累计量包含 E00～E10，不归功本单元。既有 Runtime/adapter 合同未变；相机、控制、Recorder 与历史 source 的检测入口更集中，未测试的新物理交集仍留 U3。

### U2 结果（2026-11-13，实施自评）

输入 HEAD `d0c25ae49afe3e1fceebaa9fa77f35587447976e`，输出为本结果所在提交。T08～T14 在 U2 的 caller/离线合同范围按[逐项对账](../maintenance/reviews/20261113_e11_e16_u2_caller_review.md)完成：正式示例及 YAML 入口、无广泛重试的 backend 请求、独立完成事实及关闭错误、正式 batch 资源前拒绝与 component 保留、learner space/data、LIBERO source/OSC/gripper 与外围 owner 均有实际 caller 和定向证据。T14 的五条公开命令及报告出口已备好；T15 必须在执行窗口复核并冻结 argv、资源、锁和 source，不能将这些准备称为 native 结果。总账回核 CALL-01～04：入口、并行/learner、外围 owner 与 LIBERO 的本单元边界见对账表，完整运行与代码接收分别仍为 U3/U4。

固定纯/fake 入口 **207 passed**，系统调用跟踪中受查 SDK/资产路径成功打开 **0**；现有完成语义/Harness 定向检查 **23 passed、29 subtests passed**。当前独立 reader 对两份历史 LIBERO H5 通过完整性读回（95/96 与 103/104 transitions/boundaries），两者任务成功均 false，不是本轮物理重跑。文档 validator 保持基线 **2 errors、96 历史链接问题**，无新增 error；保护文件 SHA 和 GeoPhys/Menagerie pins 与输入一致。未运行 native、App、训练或删除。原始验证和离线 readback 在 ignored `workspace/maintenance/v211_e11_e16_u2_20261113_001/`；U3–U7 及独立/维护者接收仍 OPEN。

按 `git diff --cached --no-renames --numstat` 分类，本单元相对输入：生产 +291/−216（净 +75，20 路径），诊断/测试 +587/−1（9 路径），文档/Skills +101/−18（4 路径）。相对 `a6b107ac`：生产 +291/−216、诊断 +3,177/−1,310、文档 +468/−44；累计相对 `1f1359ee`：生产 +8,555/−17,814、诊断 +10,261/−1,309、文档 +2,420/−169，累计包含先前单元，不冒领；分桶收据在 ignored 目录。新增共享 completion 投影减少三个 caller 的重复判断；batch 仅补准入和关闭错误处理，不改变物理控制、来源、时钟或单一提交 owner。既有物理 adapter、LIBERO、objects/planners/reporter/utils 未改；非本轮原生资格不因静态验证升级。

实施时本节链接一份44点最终结果表及60项签收表即可；保留第1～10节为明确的规划时点。当前文档/保护检查只证明规划交付，不证明任何新功能或清理已完成。

规划检查：T01～T44连续唯一，总账分组覆盖60项；文档检查无新增错误，既有2项错误与96项历史链接问题如第7节T25所列保留，不能称检查全绿。四保护输入SHA与两pins相对输入快照一致；无生产修改、pytest/native或清理操作。原始盘点和检查结果在本轮ignored规划目录，交付文档及索引以同阶段本地提交保全。
