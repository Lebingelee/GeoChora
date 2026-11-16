# G03/3a诊断001：Sol独立复审与3a接收

2026-11-05，Sol。决定 **ACCEPTED_3A_ROUTING_ADMISSION**，whole_3a_accepted=true。维护者指定的诊断001已闭合D1/D2，按[Goal03/3a](../../goals/03-backends.md#3a)及[诊断包范围](../../planning/stage3-3a-diagnostic-001.md)接收执行选择、环境准入、已有声明求交、具体构建检查接线与配置回执。不是三后端原生能力或Qualification接收；3b/3c与后续阶段未启动。

普通attempt_count=3、diagnostic_attempt_count=1。普通001–003及003的THREE_A_PARTIAL／人工诊断停止点保留，不能倒改成原第三次通过。本次诊断由维护者人工讨论后明确指定并手动交Terra，单独完成与接收。

## 输入和独立核对

输入1284afea430b000022563260f67d92c976d41d65，执行输出6b11123e3293743e01c90ed0ce94e0be450e3833，阶段分支codex/v211-stage3。冻结包manifest SHA为68c7748a443177b7550382f387a627e2783287a27e342ede8e38457cf30cc6e6，prompt SHA为5788cb4f8ca16412b3cff1e34651cd3a03628c2613b103678e04f4e12beb21f8。

Sol核对8个包成员、215个输出文件、10个提交文件的大小/hash、输入输出父子关系和patch摘要，均一致。输出manifest SHA为a7da114c2415c22abb682599bacc5a96b30f1fb59a451c0ff504158007c8c9a5，patch SHA为b67dbd793eee7c37c25dd03d4d736260eb012ed29c2cbbf8c6db204d67df0153。两保护untracked、两submodule pin、4个外部冻结输入均匹配；执行提交tracked/index clean。后续Sol仅更新复审、当前文档与Skill，不改执行者报告／manifest。

按AGENTS先用CodeGraph，漂移后读当前diff／caller，没有重建索引或重复上游研究。独立执行严格offline guard下5项：缺解释器的source-free拒绝、旧ExecutionSpecV1映射及identity保持、真实F06 factory的实际依赖拒绝、实际Position H5 metadata读回、普通实际声明的具体check。**5 passed／1.21秒，命令总墙时1.467秒**。没有Sol来源解析、SDK、native、GPU或额外物理；来源／原生日志通过代码、输入输出身份与实际数据核对。

## 七组验收及两个根因的闭合

| 组 | 结果与独立核对 |
| --- | --- |
| DG01 共同配置／依赖入口 | PASS。F06在build_isaac_reference／USD加载前复用原provenance metadata检查，真实目标不满足当前声明时准确dependency_unavailable。receipt明确selection_only_source_not_evaluated，source/artifact/assessment未评估。严格guard下也得到该结果，没有先触发pxr错误。GeoPhys既有>=3.15.0与当前3.8.1冲突证据有效 |
| DG02 Position完整consumer | PASS。原TaskArtifactV1/Scene/source/ControllerBindingPlan进入正常selected preflight、真实MuJoCo materializer和具体layout helper；2 groups、8 resources、10 state rows，required均出现在实际checked_requirements |
| DG03 leaf完整consumer | PASS。原logical assembly／两writer进入同一链，2 groups、8 resources、20 state rows，required均绑定真实check。无新nested模型或typed effort执行 |
| DG04 required缺Frame | PASS。真实candidate移除hand来源绑定，正常preflight产生该state:frame对象unsatisfied，session仍None；没有patch source/admission/helper使其通过。未改optional反例复用003 |
| DG05 同请求及记录 | PASS。Position的query/info/get_record_metadata一致，request等于assessment及build_checks的request。原结构化H5 metadata owner补保留该mapping；实际零transition记录经既有reader读回匹配。只证明metadata合同，不宣称完整轨迹或物理replay |
| DG06 受影响主路 | PASS。最终提交后的PickCube31／Nut19均真实MuJoCo3.8.1 CPU公开创建/reset/10次Solution-act/step/observe/close，time0→0.10秒、control_step0→10、state/pose/obs/reward有限。worker未改，复用003已保留的真实隔离运行 |
| DG07 追踪和交付 | PASS。原20case均有当前或有效REUSED证据，无本范围未决required；本地提交／文档／完整报告与释放具备，普通历史及诊断计数分开 |

**D1闭合的是预检顺序和准确状态，不是实际Isaac构建。** 当前目标环境不满足Core/Isaac已声明依赖（包括版本冲突和缺分发元数据），不能由此泛称整机Isaac SDK不存在。原F06 loader、manifest和source-bound admission未改；真实USD解析／DOF/view／App执行仍交3b，依据维护者在诊断前明确的阶段边界，不追加到3a。

**D2闭合了实际入口接线。** 新内部resolve_candidate_execution_selection由原configuration owner解析已有MuJoCo CPU来源与可选ExecutionSpecV1；原factory和candidate通过_selected_execution_context进入同一个preflight/receipt owner。保留旧ExecutionSpec与codec身份，没有在测试中注入resolved config，也没有替换Session、materializer或helper。接收固定Position／leaf state-only CPU交集，不扩展全部历史candidate、camera或其他provider。

原20case中未改resolver默认/aliases、旧codec/timebase、typed未知/未实现、render/batch拒绝与worker证据按原身份复用。没有重跑31/108项历史大组、全库资产SHA或任务成功矩阵。执行者offline-final 18passed、最终交付聚焦组6passed及独立H5组1passed的日志／命令均一致。

## 资源、流程偏差与限制

窗口19:53:05→20:14:01，1256.65秒，约20分57秒；目标工具累计约1小时29分钟不是本诊断窗口。25个已记录验证命令累计37.075秒，MuJoCo/source相关18.921秒，低于30分钟／10分钟预算。普通CPU4次10control steps合计40，按固定5substeps推算200物理步，零settle；source组是构建与零settle reset，无control step。推算不是独立native计数器。

215个输出约70.4MB，小于128MiB；日志未越8MiB。进程树峰值RSS未测，单进程8GiB地址空间限制不能当作进程树RSS合规测量。保留该限制，不为计量重跑。实际来源组使用GeoPhys Scene解析和MuJoCo构建，不表示GeoPhys物理；OpenUSD没有加载，因为F06在来源前正常拒绝。GeoPhys物理、Isaac App、GPU、render均未运行。

第一次source-position命令的cwd错误为Core根，违背包内约定；执行者披露、保护MUJOCO_LOG hash未变，生成目录已移入本包，后续命令cwd正确，最终只保留原两untracked及pins。该偏差不隐去，不把它扩大成新的核心故障或补账本运行。

## 当前文档与Skill维护

按Module Skill Maintainer的refresh流程核对现有TaskEnv Skill，发现其“stage3未开始”和当前work queue仍指前置待审的陈旧叙述。本次仅更新当前阶段状态、已有selection/admission/receipt范围及恢复入口；factory／Runtime／Recorder owner和public facade不变，历史阶段2事实按旧时点保留。行为依据是当前调用链、5项独立检查及本次真实来源/短程证据；metadata/frontmatter/链接检查与人工provider-free路线walkthrough另附收据，没有新Agent或native qualification。

Sol收据位于主工作区workspace/reviews/V211_G03_3a_diagnostic_attempt001_sol_review/；执行者原始材料仍在ignored workspace/maintenance/v211_g03_3a_diagnostic_attempt001/，原字节保留。源diff不是单独的接收依据。

## 推进决定

3a已接收，D1/D2与本次诊断关闭。下一候选仅为3b完整包准备：真实三后端场景翻译、公开反馈/物性检查，以及本版Isaac6.1/6.2共同路线与部署适配。当前目标环境不可用和GeoPhys依赖隔离是3b准备输入，6.1缺安装仍要明确NOT_RUN边界；不把5.1移入本版，不因3a接收声称3b已验证。

3b保持PLANNED／attempt0，尚无完整包、执行者或派发，3c及阶段4未开始。维护者继续手动指定／转发，Sol不自动启动或消息其他对话，不推送／合并。
