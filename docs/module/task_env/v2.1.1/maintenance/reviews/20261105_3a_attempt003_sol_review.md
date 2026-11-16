# G03/3a attempt003：Sol独立复审与人工诊断停止点

2026-11-05，Sol。决定：**NOT_ACCEPTED_3A_HUMAN_DIAGNOSIS_REQUIRED**。执行者THREE_A_PARTIAL判断成立；第三次普通窗口已结束，3a整体不接收。保留已验证的MuJoCo核心、隔离worker和记录事实，不启动attempt004／改名续包／关闭后的003续时，不进入3b或阶段4。

## 输入、独立检查与可保留结果

输入2825c5749326fcca60845dde5cae21f9cfcd04ad，执行输出3d10b3570f69d2c09400a2e8d06029e2a5bb844b，同一阶段分支。派包manifest为f154056d71ae926377c6cb8cdcc7c1c514830940b8e4d78d7814fded8fef1bce，prompt为e851bf8fd673ae37d4cd2e0eb0452d14702f33a17e8b562966810e2716c9e937。原[完整包安排](../../planning/stage3-3a-execution.md#attempt003-complete-package)和[第三次前重评](../../planning/stage3-3a-attempt003-reassessment.md)不改写。

Sol核对8个冻结包成员、110个输出成员和20个提交文件的大小／SHA，输入输出父子关系及完整patch摘要一致；两保护untracked、两submodule pin及clean状态一致。输出manifest SHA为9c4d889186e01e16f1113d03bff8248bd3b8c43d98b0a436da875fa9db02f3c8。核对发生在执行输出HEAD，随后仅作Sol复审文档提交，不重写执行者manifest或报告。

已按AGENTS先用CodeGraph，漂移后读实际diff和生产方法；没有重建索引或重复上游研究。独立运行冻结offline guard下的5项检查，5 passed／0.96秒（命令总墙时1.217秒）：实际声明检查、真实MuJoCo materializer＋SDK终端替身、已有versioned多通道反馈投影／缺Frame拒绝、logical resolver反馈投影，以及执行者真实H5的现有reader读回。它们有各自明确边界：helper／SDK替身结果不升级为完整versioned/F06生产链或真实物理。Sol未运行native、SDK、GPU或额外物理。

| 本轮可保留的范围 | 独立核对的证据和限制 |
| --- | --- |
| 普通PickCube31、Nut19 MuJoCo3.8.1 CPU | 最终两日志均为真实_MuJoCoSession，公开reset、10个control step、close，time0→0.10秒、control_step0→10；外部probe逐步断言state/pose/obs/reward有限；未替换Session/materializer，不证明task success |
| 隔离worker PickCube31 | 最终日志父Session是RemoteSession，同样10步／0.10秒及close；同一request与adapter build事实相连，不是三后端隔离运行全部通过 |
| 请求与记录回执 | 最终三运行的static assessment与build checks均绑定原request；H5实际metadata与保存receipt相等，独立reader复跑通过；native-effective保持unknown |
| 声明／layout接线的已测部分 | source具名joint/body/site/actuator检查由实际adapter调用；普通MuJoCo及部分helper正负例有证据。三个adapter的修改可保留为待诊断基线，不表示其全部交集已接收 |

执行者31 passed／7.41秒的最终离线组日志和命令已核对；Sol只独立复跑上述5项，没有重跑31项、旧108项或历史维护组。002的[核心恢复有界接收](20261105_3a_attempt002_sol_review.md)继续有效。

## 整体不能接收的两个核心缺口

### D1：F06真实来源尚未贯通selected preflight及具体build检查

影响原A02、C02及B06的Isaac部分。实际顺序是`PickCubeReferenceEnv.from_resolved_config`先调用`build_isaac_reference`；`build_pickcube_isaac_runtime_input_v1`加载delivery，`load_usd_asset_delivery`经`_inspect_snapshot`导入pxr组合USD；完成env构造后，reset才调用`preflight_selected_deployment`。冻结guard先禁止pxr，因此routes-05止于source加载，没有验证完整selected preflight。loader将该异常包装成OpenUSD unavailable，**这不是实际SDK／资产缺失的证明**。

`check_isaac_named_layout`确已接进原native I/O调用点，但现有测试使用SimpleNamespace合成source，没有真实F06 source和公开view的同链证据。单独配置解析／解释器metadata／helper成功不能补足这个出口。GeoPhys当前MuJoCo版本约束不满足已准确拒绝，真实GeoPhys/Isaac运行仍是3b，不能倒加为此次失败原因。

诊断需先区分“guard禁止了离线来源解析”“依赖预检顺序需要调整”“真实delivery/source存在问题”这三件事。目前只证实第一件及调用顺序；没有证据认定后两件为既成故障。不能通过删掉F06准入、mock source验收或把此项改标3b来过门。

### D2：versioned Controller／StateRequirements／nested声明缺完整生产source消费证据

影响原B01、B03及相关B06。当前测试分别证明compile_control_binding_plan/project_controller_feedback的多group和required/optional投影、project_leaf_feedback的既有logical resolver路径，以及合成mixed source进入assessment与layout helper。**没有一条现有versioned生产source从selected入口／assessment到同一adapter构建事实的完整正例及缺Frame反例。**将这些独立helper拼在报告中不能代替实际consumer连接。

此处尚不能断言“只缺测试”或“实现必然错误”；需要维护者选定实际已有source／Controller交集，再核对group/resource/feedback字段、逻辑leaf和原selected调用点是否一致。真正新typed执行／新nested表示仍归4a/4b，不应为了满足003临时创造另一套模型。普通scalar通过不能覆盖这个3a必达项。

## 预算与报告边界

执行窗口17:55:47→19:01:16，3929.33秒，约65.5分钟；执行者因需要外部指导完整返包并关闭窗口，并非仍有约114分钟可自动续用。日志共20次10control-step运行、零settle，合计200 control steps；按固定5substeps推算1000物理步，仍是推算而非独立native计数器。所有这些日志均有close／双锁释放。后期17次原生计时25.795秒，早期3次未单独计时；全部验证墙时与峰值进程树RSS未完整测量，不能宣称完全达标。新增输出约3.06MB，日志和输出大小在包上限内。

这些计量限制保留，不因补账本重新运行，也不另开资源审计工程。主要未通过原因是D1/D2的生产消费证据不足。早期使用模拟库映射夹具的mixed-01/02、unit-15整链证据不采用；最终unit-17的有限helper证据按其实际范围采用。

## 人工诊断入口与后续授权

当前状态HUMAN_DIAGNOSIS_REQUIRED，attempt_count=3，active_packages为空，无下一个普通候选包。按维护者明确的三次上限及[Goal编排Skill](../../../../../../.agents/skills/geochora/references/goal-orchestration.md#post-limit-diagnostic-conversation)：

> Maintainer-led human diagnosis is required before further work

由维护者裁定诊断范围与后续授权；Sol不自动创建／发送其他对话，不通过补测试或小修绕过最后窗口规则。建议人工诊断只解决：

1. D1能否在不启动Isaac App的独立OpenUSD来源解析边界形成可信证据，或应先调整metadata预检顺序；选定真实F06输入，保留准确source身份和无引擎边界。不能直接取消所有guard或伪造依赖缺失。
2. D2选定哪一个**当前已有**versioned生产source／Controller／StateRequirements作为最小完整consumer，以及一条缺Frame反例；先明确它是否真的在当前3a交集中，不开展全对象矩阵。
3. 据上述诊断区分证据缺口与代码缺口，再由维护者明确授权具体修复／验证；原三次计数和失败事实保持，不自动重置、第四次或进入3b。

现有主路已可运行，不重开G02、002核心恢复、旧前置维护或7a前全面解耦。Isaac6.1/6.2兼容仍须在v2.1.1的3b完成，5.1仍延期；本次停止不把它们移出版本目标。

执行者材料保持在ignored的workspace/maintenance/v211_g03_3a_attempt003/（report/results/commands/output-manifest及原始日志）。Sol独立核对与5项检查收据位于主工作区workspace/reviews/V211_G03_3a_attempt003_sol_review/；这只是复审证据，不是新attempt。没有派包、实现修改、native或自动消息。
