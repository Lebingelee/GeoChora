# G03/3a：维护者指定诊断001的范围与完整包

2026-11-05，Sol。准备输入为5e6df9d327cf25ebc2f65df6a8751cdb102defbc，实施基线3d10b357。维护者在本会话询问主要缺口、模块、阶段边界、矩阵/SHA与时间后，明确要求“请构建诊断attempt的工作包，我来转交给terra”。据此指定Terra按本范围诊断、最小修复和聚焦验证；Sol仅准备，不自动派发／开对话或运行native。

## 普通历史与诊断授权

[003独立复审](../maintenance/reviews/20261105_3a_attempt003_sol_review.md)保持NOT_ACCEPTED_3A_HUMAN_DIAGNOSIS_REQUIRED，普通attempt_count=3，三包与原结果不改写。当前诊断001为PREPARED_NOT_DISPATCHED，diagnostic_attempt_count=0；维护者手动转发后才实际登记1，不能称普通004或续用003剩余时长。诊断来自维护者本次指定，遵循[Goal编排Skill](../../../../../.agents/skills/geochora/references/goal-orchestration.md#post-limit-diagnostic-conversation)，不靠改名自授例外。窗口结束仍需Sol独立复审，不自动下一诊断或3b。

同一checkout／codex/v211-stage3，一个writer，新增分支／worktree0。准确input HEAD、保护文件/pins及包hash在本次准备文档提交后于外部snapshot/manifest冻结；不循环写入自身提交。当前active_packages为空，003及Sol复审窗口已释放；Terra开工再做一次准确输入核对。

## 人工讨论确认的阶段边界

| 工作 | 阶段及验收边界 |
| --- | --- |
| F06来源前的目标环境metadata检查、来源身份／声明与准确拒绝 | 3a；真实不可用解释器正常拒绝是有效准入证据，guard先拦pxr不是缺SDK/资产证明 |
| 现有Position／leaf入口、实际ControllerBindingPlan／StateRequirements／group/resource求交、具体adapter检查及同请求回执 | 3a；生产consumer必须接通，单独helper不足；静态未确认native事实保留pending |
| 真实Isaac App/PhysX、DOF/view、三后端物性／执行／读回、6.1/6.2兼容实施 | 3b；5.1仍后续版本，本诊断不安装或运行 |
| 同Env跨后端重建／代次 | 3c |
| 新typed effort/wrench、扩展nested表示及真实施控 | 4a/4b；render/batch实际运行仍在5/6 |

这明确区分来源／检查接线与真实SDK读回，不倒改003 PARTIAL，不把未完成的3a需求移到后续阶段。三后端都必须准确消费选择与准入；不强迫不可用环境在3a返回正常session。

## 可复用结论及已定位的输入

普通MuJoCo CPU PickCube31／Nut19各10步、隔离worker PickCube、同请求H5回执证据保留；Sol独立5项通过。未改的parser、旧codec、worker和记录路径直接复用，旧31／108项及历史维护不重跑。

本次只读定位实际输入，未导入SDK或解析USD/MJCF：

- F06真实delivery位于原历史checkout的f06_001/isaac_usd_v2/delivery_manifest.json，SHA256为6cb07d216689d1e0b6f31ef127d9a511906be90c2acbecb9a30667cdebf113e2；与Core冻结常量一致，entry为pickcube_scene.usda、prim为/F06Scene。准确本机路径在外部包中，原loader继续验证实际消费闭包；不全库扫描或重新翻译资产。
- versioned正例用当前build_position_candidate(provider=mujoco,horizon=8)的TaskArtifactV1／PositionServoV1／ControllerBindingPlan；seed用现有常量。
- leaf正例用当前build_leaf_position_candidate(provider=mujoco,horizon=8,environment_type=SelectedReferenceEnv)的默认参数、seed31和两writer计划，不扩gain／fixed-attachment矩阵。
- 受影响ExecutionSpecV1兼容分支可用现存F04 menagerie delivery，Core路径workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f04_003/assets/local_menagerie_panda_r009/usd_delivery.json，SHA256为ac33a5a406b9d4c2ba20a30a1605bfa8e7ddf4607b8dae5df25f70c81412aa66；已有f04_candidate_s1_support.build_candidate是consumer。两checkout该manifest字节相同，不迁移整个历史F04/F05。

两份delivery的存在与manifest SHA已核对；这不替代来源loader验证、不证明SDK可用。目标Isaac解释器路径存在，003实际metadata为unavailable；不得由路径或guard异常推定运行能力。

## 已选择的修复owner

1. **依赖／来源顺序**：PickCubeReferenceEnv.from_resolved_config先build_isaac_reference→来源loader→pxr，reset才preflight_selected_deployment。将不依赖Artifact/source的metadata检查在environment configuration／specialization与sessions.provenance原owner前移；source-bound能力检查仍在来源形成后。前置拒绝不伪造尚未形成的source request，不新建准入服务。
2. **candidate入口实际接线**：from_position_candidate／from_leaf_position_candidate没有设置resolved_public_config；build_versioned_position_candidate只传ExecutionSpecV1，而reset/get_execution_receipt通过execution_spec_v2决定是否进入新链路。应在原configuration／reference_env／reference_binding建立一个受验证的共同执行上下文，必要在原builder/source/leaf传递已有声明，保留旧ExecutionSpec身份。不在测试中手工注入resolved配置，不伪造registered task配置。
3. **实际声明与回执**：原api/control消费已编译plan、StateRequirements和logical leaf，核对实际group/resource与joint/Frame；003的adapter helper、bind_selected_build_checks和Recorder投影复用。只修在这条生产链实际暴露的缺陷，不扩MuJoCo、Recorder、oracle平台或安全矩阵。

分类FIX_EXISTING／EXTEND_EXISTING／COMPOSE_EXISTING。任务语义、Solution数学、物性、2ms/5substeps/10ms时间基、requirements/pins不改；旧codec/hash保持。G02、前置有限接收及7a集中解耦不重开。

## 聚焦验收、解析边界与SHA

完整包仅七组：三route共同依赖入口；Position完整consumer；leaf完整consumer；一个required缺Frame反例；同请求JSON/H5 metadata；受影响MuJoCo主路短程；完整结果/提交/释放。原20case只追踪新证据／REUSED／未决，不要求全跑。worker没改就复用003，未改optional detector与8组旧codec不重复生成。

普通静态／预检用原严格offline guard，证明依赖拒绝不先导入来源SDK。真实来源组另以source-only命令允许pxr/OpenUSD和原GeoPhys Scene解析；禁止GeoPhys物理Runtime/solver、Taichi.init、GPU、Isaac App，以少量外部scoped sentinel守住实际启动点。允许SDK终端fixture，不绕过source/assessment/helper或伪造库映射/版本。解析器确实不可用则准确归因，不安装下载；guard不能再次制造虚假缺失。若解析实际使用MuJoCo原生编译器，计入CPU预算和双锁。Sol准备没有执行这些解析／检查。

SHA只做一次开工HEAD／保护字节／pins核对、loader正常来源校验，以及最终提交/diff/新输出manifest；不核验全资产库或重新扫旧110输出。共同reset/admission/materialize受影响时，稳定源码上PickCube31／Nut19各一次真实CPU创建/reset/10步/close，finite与0.10秒推进按原规则。失败在同窗口修复重试，不用fake替代。

## 冻结预算与交付

主动60–90分钟，总墙时120分钟含等待／解析／实现／修复／文档／提交／返包；0–5分钟核对，5–30分钟依赖/来源边界，30–65分钟入口，65–95分钟聚焦验证，95–120分钟修复和交付，105分钟后不启新实现。

验证累计30分钟、单组10分钟；MuJoCo CPU及原生编译累计10分钟、1000物理substeps（含reset/settle/失败重试），无一次启动限制。进程树／并发RSS预算8GiB、输出128MiB／单日志8MiB；未测不声称已测。GeoPhys物理、Isaac App、GPU、render、安装/下载、新worktree0。原双锁仅在MuJoCo原生编译/运行期间按Core→历史checkout获取、逆序释放，等锁计入窗口，不删锁／盘点全机。

外部完整包为主工作区handoffs/V211_G03_3a_diagnostic_attempt001，Terra维护者手动转发。输出新ignored目录workspace/maintenance/v211_g03_3a_diagnostic_attempt001，report/results/commands/logs/output-manifest及跟踪短执行摘要；只本地明确路径提交，不push/merge。返回DIAGNOSIS_RESOLVED/PARTIAL/BLOCKED和整个3a技术结果、真实计量与未决、input/output HEAD和writer/进程/锁释放，状态REPORTED_PENDING_SOL_REVIEW。Sol独立复审预计另10–15分钟，不自动接收或进入3b。
