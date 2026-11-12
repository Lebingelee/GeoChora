# E00～E04 主审余项修复返包

日期：2026-11-12。输入 `e25f37c5`，生产/诊断提交 `912416e6`，复用阶段分支 `codex/v211-stage5-diagnostic`。本轮由维护者明确授权实施测试，处理[独立主审](reviews/20261112_e00_e04_independent_review_76536d2a.md)提出的四项代码/资料余项。本文是实施后自检返包，不冒充对新提交的另一份独立主审，也不代替维护者最终接收。

## 1. 完成的调整

| 主审余项 | 最终改动 | 可见成效 |
| --- | --- | --- |
| 构建阶段临时字典交接 | `SourceBoundTaskBuilder` 复用既有 `CompiledReferenceTaskV1`；source 回调交 `(compiled, context)`，composition 返回具名结果，Controller selection 单独传给最终绑定；只缓存完成的 Env mapping | PickCube MJCF Position/effort、USD、Nut 和简单主体共去掉 20 种阶段私有键的读写/弹出；不再靠 `pop` 的执行顺序理解阶段字段；保留最终 Runtime 合同 |
| 错误阶段字符串决定行为 | `_prepare_solution_action` 使用显式 `strict_proposal_type` 和 `action_projector`；caller 提供原来要求的类型策略/投影，阶段和错误标签只用于 fault/报错 | 重命名 fault 阶段不会改变提案准入或动作路由；保留旧异常类型/消息、boundary 检查、act 后失败 fault，以及外部 act/observe 次数 |
| 专用账本状态滞后 | 顶部写明实施、基线独立主审、本轮余项修复与维护者接收的区别；b94 输入/判断标明历史；第 10 节改为最终模块效果表 | 恢复时不会再按 `REPLAN_ONLY` 或旧“U2 可继续”重做已有工作；R25 资料已修复，R30 保留最终维护者决定 |
| 执行记录变成 Goal、索引断链 | 保存原 dirty 完整文本与 patch 后，恢复执行计划角色及第 6 节，保留独立 Goal 文件；同步 current-state、API 和 TaskEnv Skill | API/current-state/Skill 的三处实施记录锚点恢复；修正旧 physical UID 翻译、四正式类 build_runtime=False 和旧配置输入等失实说明 |

本轮为 `EXTEND_EXISTING + FIX_EXISTING`。没有新增 Runtime、Manager、registry、Controller 算法或根 API 导出。新增具名 context 是阶段数据记录，仍由各 Task/现有 source owner 定义；它们没有生命周期或 native 资源 owner。最终 `value` mapping、配置、typed 物理语义和唯一提交/推进合同不变。

## 2. 实际调用链及 owner

`make_env → from_resolved_config → resolve_task_env_config → TaskBuildRequest → SourceBoundTaskBuilder → ReferenceTaskBinding/Env` 保留。builder 的 source/composition/Controller 阶段使用 `CompiledReferenceTaskV1` 和具名 context；source owner 的 `DeclaredReferenceSource` 明确交出 compiled source、intent、Task source/Scene、projected XML/reset plan。Task 最终绑定才产生 Env mapping；仅服务编译的 context 不进入 Runtime value。

Position/effort/MJCF/USD lowerer 继续各有合法实现。Robot 声明、source freshness、Scene writer、native Joint/DOF/actuator 和传动检查没有放宽。已有 `_physical_controller_factory`、Nut provenance 等运行期需要的字段保留；此次去掉的是阶段 scratch 字段，不把所有下划线成员一律删除。

标准 Solution 仍由调用方持有并执行 `act → env.step → observe`；两个兼容入口继续委托同一提案 helper 和 `_step → prepare_selected_control_action → submit_control_command`。外部 physical 兼容路径显式选择其精确 ExpertAction 类型与 physical action binding；expert 保留原投影优先次序。标签本身不再参与条件分派。

## 3. 验证结果与限制

| 层次 | 最终结果 | 能证明什么 |
| --- | --- | --- |
| 精确纯/fake | 76 项通过；SDK 导入/安装资产读取守卫未触发，已加载 native 模块为空 | source lease/cache、失败 owner/RNG、提案策略、worker、配置及 RGB 合同；与下行有重叠，不相加为独立用例总数 |
| 受影响 source/caller | 217 项通过：首轮 211，通过补跑的离线 USD 六项 | 四任务实际配置/source/Controller 构造、真实 USD delivery 的离线 lowering、source/factory 失败清理、现有 caller 和故障语义；其中 MuJoCo 显式子步 40 |
| MuJoCo 正式短程 | 四任务、装配 Panda、直接 effort及兼容 Position Solution 共七条通过，75 显式子步 | 真实构造、reset、一个非零 interval、TaskDefinition/Robot 重绑、第二次 reset、重复 close；不代表完整任务成功 |
| GeoPhys CPU | Panda effort、Pendulum 各一条短程通过 | 一次 interval 的 state/clock、二次 reset 与 close；native 子步未独立计数 |
| 修改前后对照 | 六条 MuJoCo 代表路线的 Artifact、source id/closure 和 native layout objects 与原 U5 结果一致；三条 Position 还比较 writer 资源 | 交接调整保留实际 source/映射；不要求 Controller provenance hash 在源码改动后不变，不扩展为跨 solver 轨迹相等 |

本轮显式 MuJoCo 子步合计 **115 = 40 + 75**；原生运行均使用原有双锁，释放已记录。没有启动 Isaac App、GPU 或 GUI。OpenUSD 是离线 source 检查依赖，不是一次 Isaac 物理运行。独立输出 cwd、内存/CPU/墙时及每次子步上限在冻结计划中；未将原生测试藏在“纯测”数量中。

验证在 `e25f37c5` 加冻结生产 patch 下进行；对应生产/诊断文件 SHA 已与 `912416e6` 逐项核对相同。运行 provenance 中的 source_revision 仍为 e25，不能写成提交后裸 HEAD 重新运行。文档提交不改变该生产验证身份。

首轮检查把 pxr/OpenUSD 也拦截，造成六个 USD 失败；原失败日志和 40 子步保留。允许离线 OpenUSD 后只补六项，物理推进计数为 0。结果比较器最初把 Position 专有的 writer 字段也要求于 physical 输出，改为按实际字段核对，未改原始输出。正常修复/补测在同一授权窗口完成，未重置既有阶段/attempt 历史。

本轮没有改 provider/renderer lowerer、状态/RGB publication、时钟或 App/camera 生命周期。先前 RGB/Isaac 原生结果继续保留自己的输入和范围：renderer 证据按最终公开 source、映射和生命周期接口未变复用；Isaac 的新构造交接在本轮由离线真实 source/Controller 检查覆盖，不能将旧 native 收据升级为新 HEAD GPU 实测。真实 SDK 失败注入、完整 Solution、E05 以后和 G06 仍未完成或自动启动。

## 4. 文件、代码及资料保全

相对输入 `e25f37c5`，生产修改 5 文件，+208/−143，净 **+65**；版本诊断修改 2 文件，+35/−9，净 **+26**。没有新增/删除/重命名生产或诊断文件。增量用于具名阶段数据及显式提案策略，不能描述成本轮又净删数千行。文档/Skill 修改 5 文件并新增本文；项目文件净增 1，未整文件迁移实现。原 stage5→765 的累计净减少不与本轮混算。

执行记录修改前 SHA `af50897d…` 已完整保存，原 dirty patch 和 Git 中执行计划原件均保留。恢复以授权的文档勘误为目的，独立 Goal 不动；不是声称 dirty 跨时点从未变化。四个 untracked 保护输入及两个 submodule pins 按输入快照逐字节/identity 保全，原始证据、refs 和 worktree 不清理。

文档/Skill 仅同步此次直接涉及的 owner、配置、退休入口和 evidence 边界；历史 G04/G05 candidate 说明标记为历史，不以历史命令复活退休实现。E14 全量文档接收仍保留。

本轮文档/Skill 相对 Git 输入基线共 +118/−85，净 +33 行（含新增本文）；该桶按本轮职责统计，不与历史“生产及其他”桶中的 root Skill 混算。文档检查由 5 项错误降至 2 项：三个实施记录断链已修复；剩余是保护的 MUJOCO_LOG 与检查器旧哈希不同、历史 review 指向退休 Position 文件，96 项历史链接问题保留，不为全绿改保护原件或复活旧代码。

## 5. 恢复入口与接收状态

当前效果以[执行记录第 6 节](../planning/post-5c-optimization-execution.md#6-e00e04-实施记录)、[专用账本第 10 节](../planning/post-5c-e00-e04-remaining-ledger.md#10-当前效果与接收状态)及[当前状态](current-state.md)为入口。本轮四项余项已实施并验证；基线独立主审及本轮自检材料齐备，**维护者最终接收仍待完成**。原主审报告保留其审查时点，不回写成当时已经没有余项。

冻结输入、原 dirty/原件、副本恢复 receipt、精确节点/JUnit、首轮失败、USD 补跑、九条 CPU 原始结果及最终交付 receipt 位于 [本轮输出](../../../../../workspace/maintenance/v211_e00_e04_review_fixes_20261112_001/input-snapshot.json)。本地提交后没有 merge、push、tag 或发布。
