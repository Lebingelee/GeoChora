# Sol：人工接管后的阶段2成功证据复审

日期：2026-11-04。决定：**ACCEPTED_BOUNDED_MANUAL_SEED31_SUCCESS_EVIDENCE**。

接收“维护者人工调整后的PickCube在MuJoCo CPU、seed31完成一次完整任务”的证据；不是仅接收聊天中的success标记。正式2b仍为 **MANUAL_SUCCESS_PENDING_CLOSEOUT**：成功实现尚在未提交工作树，受影响回归和另两route尚未收尾。2c、阶段3及Qualification均未开始。本轮不恢复旧姿态绕行包、不新派writer、不运行仿真，也不创建Skill。

## 1. 已独立核实的成功

成功run为 `V211_pickcube_retarget_full_task_001`。原始HDF5 SHA-256：`4b9e2e78cb69d08c3b6f023112859e2f9f273eba4ff3905fd21a31a610f3b9e6`。

| 项目 | Sol复核结果 |
| --- | --- |
| 实际route | 当前public `make_env`、task-owned R3 Solution、MuJoCo3.8.1 CPU；direct example，horizon1000 |
| 生命周期／任务 | runtime_valid=true、task_success=true、expert_complete=true、solution_done=true、solution_failed=false |
| 记录 | 960 transitions／961 boundaries；逻辑／数值动作逐行一致、control step和10ms clock一致 |
| 跟踪 | 位置RMS／P95／最大1.982／4.424／7.090mm；姿态0.178／0.421／1.160°，与原独立reader一致 |
| 原task oracle | artifact仍为 `fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4`；lift门限0.10m，未改任务成功判定 |
| 收集余量 | 首次task-success在boundary946；首次达到Solution 0.105m余量在boundary960，随后完成；不是刚到0.10m即提前停止 |
| 执行阶段 | move_above_cube434、descend_vertical175、close_gripper84、lift267 transitions |
| 版本 | `4ebbcfdff1109334974c19b1b81be81d4b970871` 加未提交工作树；H5记录的26个source文件hash全部与当前字节相符 |

两个“抬升”基准要分清：初始cube z=0.488000m，最终0.592189581m，净抬升 **104.189581mm**；任务定义的rest_height为0.487000m，因此task_metrics.cube_lift为 **105.189581mm**，满足0.105m收集余量。不能因净抬升少于105mm而错误否定本次Solution完成。

同run独立reader、canonical inspector均退出0。Sol另用公开H5 parser／validator检查960条target/applied hash对应。当前direct example在finally关闭Env，runtime_valid判定必须包含close_succeeded；原run没有close_error且正常退出。原raw没有独立的native close receipt，保留这一清理证据边界，不虚构额外receipt。双锁释放日志及原运行命令已归档，本轮进程检查未见这些run的遗留worker。

## 2. 这次修复说明了什么

此前2b过早把修复方向限定到姿态绕行，没有优先检验高位waypoint本身的可跟踪性。维护者的人工排查已经给出更直接的修复依据，后续应沿该成功实现收尾。

1. Controller／planner参数及完整执行包装对齐后，原1351点高位路径仍有22.420mm RMS、49.531mm P95、50.346mm峰值误差。因此“只对齐增益／限速／慢化就能解决”已经被反证。
2. 同初始arm q/base、同冻结目标和R3配置、无任务场景接触时，NutAssembly复现了原路径误差。Sol从两份原始H5重算：requested actions逐值相等；TCP xyz最大分量差约 **3.44e-15m**，quaternion最大分量差约2.12e-15。原trace显示的“0差异”是在其保存精度下成立；完整H5不是字节级完全相等，数值差处于浮点舍入尺度。它支持排除这个具体空载实验中的环境臂体响应差异，不外推夹爪接触、所有控制模式或其他后端。
3. 维护者将高位点0.753→0.603m、接近点0.633→0.593m，横移沿新高位点。新612点空载轨迹RMS／P95／最大2.186／4.879／6.776mm，RMS与P95下降约90%，继而真实碰撞完整任务成功。
4. 既有内部诊断支持原路径局部近奇异构型下DLS修正停滞；快速原点列还会造成速率／lead限幅和动态滞后。当前证据支持“路径触发了R3的局部求解弱点，改路径能修复这一例”，不能说控制器对任何目标都无问题，也不能从局部停滞推出原目标全局不可达。

不再把旧20°姿态A/B作为继续收尾的必需项，也不要求重做一轮泛化归因或M(q)大审计。新路径未采集J/SVD，故不声称已经证明具体哪条奇异向量被避开。若以后整理排查Skill，可以固化消除混杂／固定目标与初态／分离移动与保持误差的流程；无需为写Skill而强行给每个同步改动分配独立因果贡献。

## 3. 维护者指示形成的新Solution基线

维护者在原执行对话明确下移waypoint，执行方说明门限同步降为65mm后，维护者要求重新测误差、改善后完整复测。本审阅按该人工接管指示处理，不机械要求恢复与新目标不相容的215mm旧Solution gate。

须同时记录：R3 clear命令相对cube top为90mm，measured gate为65mm，保留20mm headroom＋5mm tolerance；XY gate仍10mm。完整run还用了34tick close transition、50tick settle、10tick post-close hold及Controller-owned hold/ramp。**这是Solution路径／执行／readiness policy组合变化，task的10cm抬升谓词保持不变。** 单次成功不能量化这些变量各自的贡献。

报告中第7节将同初态交叉实验的冻结点列归到较早 `_002` 的 `5752d11b…`，但最新人工对齐基线与Nut公开step_expert重放实际使用的 `trajectory_points.json` 文件hash均为 **`c7d03704043eac0382f85a2ebdd197808bab2c0761e4ace60c6c8f3049d7ee28`**。这两个1351点实验应分开标识；不能把文件hash互换。原报告保持不改，本页记录勘误。

## 4. 收尾问题已缩小

当前有九个未提交文件：PickCube Solution／specialization、新回归测试，shared execution／gripper_execution、Cartesian planner，Nut Solution／specialization，以及cadence诊断兼容入口。公共变更主要是抽取共享执行包装／servo与SI planner参数换算，并让两任务实际消费同一实现；不再只有两个任务文件。Sol已保存全部diff和源码快照，没有stage或修改它们。

Sol在当前字节上运行了既有窄检查：

- safe-approach模块因仍导入旧常量 `_APPROACH_CLEARANCE` 而收集失败；此前“8 passed”不可复用于当前源码。
- 隔离该收集问题后，其余两模块 **4 passed、2 failed**：一处仍断言旧215mm gate，另一处仍断言lift427点而新profile包含10tick hold、实际437点。
- 这些是与人工新基线未同步的测试问题，需以新路径的几何安全／interlock、原task lift、真实close/hold及实际计划长度建立缺陷检测；不能简单删除断言，也不应把生产实现改回旧配置来取得绿色。
- `git diff --check`通过。Sol没有重跑native、Nut任务或其他seed／provider。
- 全局doc validator仍为FAIL：`protected local input missing: docs/maintenance/20261030_runtime_route_diagnostic_handoff.md`。该untracked保护文件在本轮修改前已缺失（初始Git/source snapshot仅有MUJOCO_LOG.TXT这一个untracked）；Sol未删除／恢复它。检查无stale path，96项历史链接问题保持。当前审阅文档可单独提交，但不能将这次全局文档检查称为PASS或改validator掩盖缺失。

下一步仅需把已经成功的实现整理成本地稳定候选，修复上述窄测试，核验共享抽取对Nut的回归及代表性不同reset，完成精确route状态与版本封存。既有成功数据应复用；只有候选字节变化／版本绑定或受影响回归需要重跑。GeoPhys／Isaac本次仍NOT_RUN，不能提升成已成功或阶段3已实施。视频不在当前证据中，但视频并非本次数字成功判据的替代物或额外阻塞。

## 5. 状态与证据保护

- 人工接管段与旧ordinary attempt001历史分开记录，不把多次人工实验伪装成新ordinary attempt，也不据此重置其预算。旧r002包的执行指令已被维护者人工接管取代，勿再次转发。
- **接收范围：**MuJoCo CPU seed31人工成功run及本轮受控诊断的有界结论；**正式2b未接收**，实现／tests／受影响回归／完整封存仍待收尾。2c和阶段3不启动。
- 四个最新run共123个文件、30,739,487字节已从 `/tmp` 逐字节复制并校验到本审阅目录 `preserved_runs/`，四份原manifest及sidecar均通过；原文件和原报告未改。
- `source_snapshot/`保留与成功H5相符的26份source及其余dirty／关键文件；`manual_worktree.patch`记录当前完整未提交diff。基线commit不能独自代表本次成功版本。
- `archive_receipt.json`、`independent_audit.json`、`canonical_readback_audit.json`、`source_snapshot_manifest.json`及两份pytest日志支持本审阅。原报告SHA-256：`e5fc395cd657dddf8746d9fe2eeda08dd5d906aef296ff51e745ab2bc35b61a1`。

审阅目录：`/home/lly/Documents/ChatGPT/GeoChora v2.1.1/handoffs/V211_G02_manual_success_sol_review_20261104/`。Sol本轮仿真启动0、physics步数0、生产修改0。
