# G04 4a 最后普通 attempt003：Sol 重评与收口方案

2026-11-06，维护者要求先做好 4a、准备最后一个普通 attempt003，并授权手动转发的实施者在双锁和预算内做 MuJoCo CPU 最小 build／reset／短步验证。准备不计执行次数：count=2，002 续作已释放、未整体接收；4b／4c 不自动启动。完整包及准备提交后的精确输入在外部 `handoffs/V211_G04_4a_attempt003/manifest.json` 冻结；同一 `codex/v211-stage4` checkout，继承 G03 和已提交 4a 工作。

## 按原规划区分阶段

[G04 原目标](../goals/04-control.md#4a)要求 4a 落地统一控制主体、JointEffort／BodyWrench／扩展槽、公共 state/model、capability、回执和单一组合提交；Panda 8 输入映射到 7 个 arm torque 与 2 个源约束 finger force；冻结三后端 7＋2 effort 与普通物体／Robot body 的最小真实外力路线和验收计划。4a 必须让已开放能力真实可信，不能假装 unsupported 是 supported；不以 4a 已完成三后端实际施力作为原门。

4b 才要求 MuJoCo CPU、GeoPhys native rigid CPU、Isaac Sim 6.2 PhysX CUDA 三后端的真实 7＋2 effort，以及原计划的物体／Robot body 最小真实 BodyWrench、叠加及 clear/reapply；原文没有强制在 4a 先实现三后端或把每个外力场景乘全后端矩阵。4c 才要求同一 Env 的 Controller/input spec reset 切换与迁移后 PickCube 成功。版本附加装配 Panda 仍依维护者已采纳的 4b 稳定后早验证／7a 两任务完整复用安排，不追加为 4a–4c 接收门。

## 证据、根因与仍需处理

001 的 source=0 设计与正常构造不兼容且曾发生越界解析；002 最初禁止 native 同时要求依赖 build 的结果，002 续作纠正权限后完成 source-bound A05／MuJoCo CPU 的真实构造、named mapping、单／双 Controller 与 effort＋hand-wrench 提交和写入 ACK。001、002 及续作结果与原违规、7 次 native／35 substeps 原始证据保留；ACK 非测量。参见[002 主审](../maintenance/reviews/20261106_4a_attempt002_recovery_sol_review.md)和[后续跨后端核对](../maintenance/reviews/20261106_4a_wrench_cross_backend_followup.md)。不重审 G03，原 N08 FAIL、Isaac 6.1 close timeout、通用装配子树补偿未实现不改。

当前精确缺陷：`task_env/runtime/sessions/mujoco_physical.py::MuJoCoPhysicalPort.write` 用边界状态一次投影 BodyWrench 并保存广义力，`mujoco.py::_MuJoCoSession.step` 将此值重复用于后续 substep，但 `assessment` 声称 body force/frame/offset 和 hold 能力。姿态变化时这不是一般的持续空间力。Sol 的 SDK/XML guard 纯 fake 调用真实 step 循环证实该结构；未测 Panda 实际误差。

第二个已确认差异：`tasks/position_candidate/physical_profile.py` A05 候选力按 body frame，偏移点 `(0.01,0,0)` m，而零总力矩参考为 body 原点；现有 4b 计划的 Robot hand 是 world 力、同偏移 body 点、作用点处零矩。纯算术单位姿态示例 F=(0,0,1) N：前者原点总矩为0，后者为 `(0,-0.01,0)` N·m。两种定义均可合法；历史 native05 不能冒充后一场景。`physical_control.py::prepare_physical_command_batch` 将用户 torque 解释为关于明确 reference 的总矩，此含义须稳定、可查和可测。

## 官方路线与可行性

[MuJoCo 3.8.1 `mj_applyFT`](https://github.com/google-deepmind/mujoco/blob/3.8.1/src/engine/engine_support.c)按当前 Jacobian 累加广义力；[鼠标扰动](https://github.com/google-deepmind/mujoco/blob/3.8.1/src/engine/engine_vis_interact.c)按 body 状态算弹簧阻尼和偏心矩并使用 `xfrc_applied`。可复用其作用点→质心力矩和 buffer 思路，但不能把鼠标弹簧等同固定 N／N·m；须保证同一贡献不同时走 `xfrc` 和 `Jᵀ` 两路。当前调用必须使用当个子步有效的构型及派生 frame／Jacobian。[3.8 官方 simulation 文档](https://mujoco.readthedocs.io/en/3.8.0/programming/simulation.html)指出 `mj_step1/2` 的积分器限制；3.8.1 实际 A05 积分器须先核对。`mj_forward` 不推进物理，但必须保留时钟、step 计数和清理，不可误用成第二 step。新第三方依赖无必要。

优先在已有 MuJoCo session／port 内实现声明范围的逐 physics-substep 空间语义：维持 outer command 一次准入与组合，明确 world/body 表达、点／矩参考的有效时域；子步更新必须依据当前状态，joint effort 与 body wrench 的不同贡献精确合成，释放／异常清空且不覆盖外部 writer。可比较 body-COM `xfrc` 和经新鲜 Jacobian 的 `qfrc` 两个现有公开机制，选能正确覆盖冻结 case、证据清晰且不扩增 owner 的一条；不改变 source tendon/equality，不能用隐式 position drive 冒充 direct effort 或未知测量。未知 frame／integrator／并发持有状态严格拒绝。

后备方案是**真实关闭并拒绝未能兑现的 BodyWrench 实际准入**，保留 typed 契约、受影响能力声明清晰、选中 joint effort 代表路线与4b 实施计划；必须有正负例证实现有错误路径不可通过，不可仅改文档。此方案不删原 4a BodyWrench 契约或 4b 的真实外力目标，且必须满足原 4a 其他出口与已冻结的真实 session 代表证据；优先完成正确实现，不因一次常规测试失败就提前走后备。

GeoPhys [已有 UI 点力](../../../../../GeoPhys/docs/guides/simulation-ui.md)采用 provider 接受的弹簧阻尼点力；与通用 typed wrench 的 public port 是否可复用需 4b 核对，不读取 provider 私有 solver。[Isaac Sim 6.2 prim](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/py/source/extensions/isaacsim.core.experimental.prims/docs/index.html)提供位置／力／矩和坐标候选，具体本机 extension、传动与生命周期留 4b。可行性判断：现有 source、代码 owner、上游 API、已批准的最小验证范围足以形成完整 4a 修复路线；时间内真实效果不能预先保证。仅 4b public API 尚未实现本身不是本次提前人工诊断或新增 4a native 物理门的理由。

## 检查顺序、证据与停止

1. 确认 scope、writer、HEAD/pin、保护文件、预算；阅读 002 续作 manifest 和直接相关 logs，不重算无变化全部 530 项。冻结 native 源／积分器后再执行。
2. 首先以无 SDK／source fake 和精确数学例证明旧缺陷可被检出；逐 substep 验 world 与 body 表达、偏置力矩参考、改变 pose 下当前投影、不同贡献一次组合、清除／失败／reset、stale/duplicate、unsupported 写前拒绝。固定 `F=(0,0,1)`、p=(.01,0,0)、参考分别为 point 与 origin，原点矩分别为 `(0,-.01,0)` 与0；这是区分契约的算术例，不是单次 native 轨迹误差阈值。
3. 保持旧 codec/hash／position compatibility、8→9 source-bound 映射和 drive 限制；仅对受影响相关正负例回归。允许维护者授权的双锁 MuJoCo CPU 代表建模／短步，在源身份和状态上分开 native_build、write ACK 与物理测量；不重复三后端物理矩阵。
4. 复核原 P1–P5／N1–N7 逐项阶段与证据；4a 的 P5 仅 stale／边界，A→B→A 真切换归 4c；4b 计划保留三后端 effort 与两类 BodyWrench 目标／route／frame／point／reference／baseline／oracle／阈值规则／预检／资源和 owner，将仅 build/runtime 可知的值作为有明确判定和失败处置的 4b preflight，不要求本轮证明三后端力效果。
5. 限时内对普通失败自主修复重跑，保留每次日志、source、step、资源和完整输出清单；交付清晰的逐门结果、生产路径、4b 计划、报告及 release receipt，由 Sol 独立主审。失败返回真实缺口；attempt003 完整返包仍未接收时，普通窗口停止，维护者主导诊断，不自动004或改名续作。
