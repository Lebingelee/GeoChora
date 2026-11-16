# G04/4a attempt002 主审与第三次前重评

2026-11-06。决定 `REWORK_REQUIRED_4A_REASSESSMENT`：4a 未整体接收；001、002 共两个普通 attempt，003 是仅剩的最后普通窗口。本页是主审与讨论依据，不派发、授权或启动 003。维护者要求先完成分析，再讨论是否进入 003 及具体规划。

## 独立核查与现状

Core 输入 `codex/v211-stage4@0e229a72b306938d545e0c10a7939f8f2548abe1`；该提交是 002 本地部分交付，父提交 `842e1efd8268a6a99d075640a30840c2eeb4918f` 含已接收 G03。GeoPhys `dc2685e28c6c916fb6403a2342c04e0d2520aef7`、Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` clean；三个原保护 untracked 哈希不变。本页记录的 Core 输入身份是审阅输入，不预造后续提交 SHA。执行者报告 writer／双锁已释放，执行会话可见 idle；旧 Goal 报告 active、未完成，不能从该状态推断窗口仍有 writer 或已获接收。

002 manifest 的 119 项 SHA-256 独立核对全部匹配。检查了本地 commit、实际生产路径、测试、两个主要日志和 [002报告](../../../../../../workspace/maintenance/v211_g04_4a_attempt002/report.md)、[案例矩阵](../../../../../../workspace/maintenance/v211_g04_4a_attempt002/case-matrix.md)、[4b计划](../../../../../../workspace/maintenance/v211_g04_4a_attempt002/4b-plan.md)；路径均以本提交对应 checkout 的 ignored 输出解释。Sol 按 run16 的 17 个指定 node 在禁 SDK／XML 的 guard、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` 下独立复跑，**19 passed**；这是纯／fake 契约证据，不是 physics。执行者 source19/source20 各 6／2 passed 是实际 registry／配置／静态 source 构造后插入 fake session，不是 native build。原其他 3b/3c 证据按各自身份复用，未重复旧矩阵。

Sol 本轮无 source 解析、SDK 导入、provider/native 启动、物理步或 GPU；本机包元数据报告 MuJoCo 3.8.1、NumPy 2.2.6。前 001 的私有 solver 搜索误输出和至少两次未授权 source 解析、002 的 CodeGraph 误输出私有 solver 片段都保留；没有因这些输出宣称 provider 能力。002 自报本窗口 20 个 source 进程、`parse=39/fromstring=615`、source 进程 wall 合计 20.60 秒，仅计该两种 API；其技术日志、边界事件及所有失败保留。002 墙时 50.9 分钟，active/wait/RSS/GPU 未采样，不推导为零或当成预算使用量。

## 按原 4a 出口逐项判断

| 原目标 | 002 已完成或可复用 | 未完成及所属阶段 |
| --- | --- | --- |
| 嵌套主体、8→7＋2、多个 Controller | typed 名称、source 闭包检查、正常 `make_env` 候选配置及 fake 终端的 8→9／两 Controller，有局部正负例 | 候选用 A05 closure `aa4ca97b…`，PickCube closure `02f12b11…`；真实 native source/build 映射与可实现力域未验证。它们不能互相替代。 |
| 命令、显式组合、单一提交与 capability | JointEffort、BodyWrench、typed 槽、frame 变换、stale、重复贡献／PD 的纯／fake checks；ACK 和 measurement 分列 | [reference_env.py](../../../../../../task_env/environment/reference_env.py) 的新 profile 在 `reset` 处无条件 `StageUnavailableError`；真实 session 没有新的 assessment/build receipt/write 端口，不能实测提交。4a 的公共契约与 production 接线应审完整，4b 才要求三后端施力实证。 |
| 公共 state/model、时序 | typed snapshot、精确 boundary 及独立纯仿射 model 示例 | 使用的零 bias 不是 Panda 动力学；代码声明 cadence/max-age，但完整调用者、时序语义及 required/optional 测量覆盖仍需审查。不能仅凭类型已实现宣称全部模型能力。 |
| P1–P5、N1–N7 | 纯／fake 正负例和 source 静态事实均已留证 | 原案例按 4a 所属合同、4b 真实施力、4c reset 分层；P5 的真实往返不应提前变 4a 必需 gate。各层结果不相互升级。 |
| 4b 计划 | 002 已列 source、frame、拟施力、条件递推和资源候选 | 4a 原文要求冻结最小目标／路线／frame／作用点／数值 oracle／预算；该稿自报 BLOCKED，hand oracle 与三路线精确能力、最终参数/预算尚不明确。它不是已经执行或通过的 4b。 |

## 为什么两次没有完成

1. **001 的编排错误。** Sol 首包将 source 解析定为 0，然而正常 PickCube source 构造必经 source snapshot／XML 解析；这一限制是本窗口安排，并非 4a 规范要求。首次宽泛搜索误输出私有内容，续作误选包含真实构造的旧测试并造成至少两次 source 解析，后分别提前返包。事件应保留，但没有发现 4a 已不可实现的证据。001 最终只有 fake 草稿，没有生产构造证据或冻结计划。
2. **002 有实质增量，但生产会话仍不能执行。** 在允许纯 XML 后，002 接通 candidate 的实际注册／配置／source 和 fake 终端，提交了契约、controller、测试和文档。它没有为真实 RuntimeSession 完成 physical assessment、source/build 映射及 batch-write；当前 reset 明确拒绝。source 静态值、fake `native_build` 字样及 fake ACK 不能当真实 provider 执行。部分缺口是否属于 4a 的必要公共 binding/consumer、哪些是 4b adapter/native 实现，必须在最后窗口前逐项裁定，而非两端相互等待。
3. **002 的 4b 计划中有真实未知，也有前置边界混淆。** 同源实际 contact、驱动、body/frame 与动力学参数没有被 002 运行读取，不能说它们已验证；但 4a 原门要求冻结验证方案，不要求在 4a 先完成所有 4b 的三后端物理验证。我写的 002 包既禁止 native 又要求仅当参数具体验证后才给出可执行数值轨迹方案，且将受物理实现约束的未知判为整个计划 BLOCKED，存在在规划门之前要求执行证据的风险。应由 Sol 把明确可冻结的输入／预测／容差／预检和需要 4b 真实读回的条件分开，不以无证明的假设冒充事实，也不事后扩大原门。
4. **不是算力或预算耗尽导致。** 002 使用约 51 分钟、窗口上限 360 分钟；它按冻结的授权与遇到外部决定时的停止规则返包，不能据此断言执行者偷工，也不能因预算剩余自行变更权限。职责上 Sol 应为包内边界不一致及 001 的人为限制负责。

## 官方与开源资料核查

- 机器元数据为 MuJoCo **3.8.1**。其 [3.8.1 公共头文件](https://github.com/google-deepmind/mujoco/blob/3.8.1/include/mujoco/mujoco.h)声明 `mj_applyFT`、`mj_jac`、`mj_jacBodyCom` 等。公开文档解释 `mj_applyFT` 将物体某点力／矩投影并累加到广义力向量，故必须定义清除／重施并拒绝同一 wrench 与其投影重复写入；这只证明上游候选 API，不证明本项目 adapter。与其他版本的文档对应关系需按本机头文件／部署核对。[MuJoCo API](https://mujoco.readthedocs.io/en/3.3.5/APIreference/APIfunctions.html#mj-applyft)；[3.8.1 许可证](https://github.com/google-deepmind/mujoco/blob/3.8.1/LICENSE)为 Apache-2.0。
- PickCube 文档所述 1 mm 间隙与 1 mm margin 不足以证明接触状态。**3.8.1** 对接触 margin/gap 的语义以[该版本源码文档](https://github.com/google-deepmind/mujoco/blob/3.8.1/doc/computation/index.rst)为准；不应从最新版不同表述反推本机，更不能凭几何零穿透推断接触力为零。历史 3b 已验证的是冻结条件下无机器人接触与 11 个控制边界，不是所有子步都无桌面接触。
- Isaac Sim **6.2.0** [官方 prim API](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/py/source/extensions/isaacsim.core.experimental.prims/docs/index.html)说明 DOF effort 需按更新调用，并提示纯 effort 控制时关闭 drive 或置零增益；[Omni Physics 107.0 tensors](https://docs.omniverse.nvidia.com/kit/docs/omni_physics/107.0/extensions/runtime/source/omni.physics.tensors/docs/api/python.html)提供 DOF force 与指定点力矩候选，且 DOF 力独立于 implicit PD。107.0 与本机 6.2 的实际 extension 对应尚未核验；Newton API 文档不应冒充 PhysX 证据。
- [GeoPhys 正式控制文档](../../../../../../GeoPhys/docs/reference/control-observation.md)允许 scalar direct-joint 与 fixed-tendon actuator，但 `TORQUE` 标签本身不保证真实 effort；point-load spring-damper 不等于一般 body wrench。公开能力缺口需在 provider 正式 owner 最小扩展，而非 Core 读取私有 solver。
- [Pinocchio](https://github.com/stack-of-tasks/pinocchio/blob/devel/doc/Overview.md) 是 BSD 开源动力学候选，提供刚体动力学／运动学；当前 Python 环境无该包分发元数据，现有版本与 source、传动／接触一致性未核验。此刻不建议为最后普通 attempt 安装或引入它；优先评估现有 source-bound MuJoCo 公共模型与现有 Controller。MuJoCo 模型可提供独立于被测写入链的数值计算，但同引擎模型不是完全独立的物理真值，须明确对照边界。

## 讨论前的可行性和具体最小路线

**判断：有条件可行，尚未达到派发就绪。** 正式类型／pre-native consumer 已有基础，已知上游候选公开接口可以支持定向设计；但真实 adapter、源约束到能力的证明和被允许的验证交集未闭合。不能承诺 003 必然完成；未确定权限、4a 结束定义和 4b 可执行计划之前不应消耗最后窗口。

建议讨论时将 4a 原出口拆为可核查而不新增门的三层：①真实公开入口从配置到 binding、命令聚合／拒绝的代码和聚焦测试；②provider 能力／映射以 source、build、runtime 分层，未执行层标 unknown，不能把 fake 变成 native；③4b 固定三后端 effort 与普通物体／Robot body 的最小验证方案，写明动作、frame、作用点、预期公式／单位、预先约定的容差或推导规则、先决 readback、数目与资源。具体需要实际 native 才能确认的接触／compiled 参数，作为 **4b 执行前 preflight**，不事先当作 4a 已证明或无限期要求 4a 完成全三后端施力。若本项目认为实际 RuntimeSession 写端口本身是 4a 必达，应先决定至少哪条真实端口和可用授权；若认为 4b 才实现，也要确认现有 fail-closed reset 是否足以满足原“落地”与真实生产 consumer，不能自行宣布通过。

数值方案的最小讨论：优先对照相同 source、状态和控制周期的 baseline/load，分别保留外部物体与 Robot body；记录独立的 wrench 坐标／力矩换算、控制边界、实际 adapter 写入和状态测量，不将二者混为同一贡献。对 free cube 的解析递推仅在真实质量、armature、阻尼、积分与接触前提成立时使用；002 的 `1e-5` 是条件候选，参数 ±`1e-8` 的灵敏度不构成跨实现误差证明。条件不成立时应在运行前选择已冻结的另一 oracle／预检处置，不把跑出结果后调阈值当修复。原 4a 不指定必须使用 PickCube 的贴桌初态，可讨论独立的有明确 source 与无接触预检的代表普通物体场景；这不替代 4c PickCube 成功，也不允许改写任务 reset。

如决定申请 003，应冻结一份覆盖所有实际缺口的单包：准确 HEAD/pins 和窗口；唯一 writer／双锁；能否进行 provider build／reset／step 等明确权限及合理 CPU/GPU/时间/物理步预算；各公开 owner 的必要修复；12 案例分阶段映射、真实性质与受影响回归；4b 的具体 oracle/预检/资源和失败处置；提交、reader、释放与 Sol 主审。不能把所有 4b 原生成功提前塞进 4a，也不能删掉原 4a 的 BodyWrench 规划门。相同 signature 两次局部修复仍失败、或三次尝试无新 Evidence，遵循现有 troubleshooting 的三个可区分假设与最小实验；不重复整个历史矩阵。

用户尚未决定是否派发 003，本页不构造执行包、不更改验收门或权限。若 003 经授权后仍未接收，按 [Goal 编排 Skill](../../../../../../.agents/skills/geochora/references/goal-orchestration.md) 停止普通 attempt，进入维护者主导诊断；不得自动 004 或改名清零。G03 三项有限接收、原 N08 FAIL、6.1 启动后 close 超时、通用装配子树补偿尚未实现和附加用例在 7a 收口均保持。
