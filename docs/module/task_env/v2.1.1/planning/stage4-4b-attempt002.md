# G04/4b attempt002：围绕原出口收尾和接收准备

状态：准备手动派发，4b 未接收。维护者要求优先修正和复用，避免重新跑已覆盖测试。此窗口继承 [001 独立主审](../maintenance/reviews/20261106_4b_attempt001_sol_review.md)及其保留证据；不把文件级 hash 不同本身当成实现缺陷或自动要求新 native。Sol 在本规划先区分实际功能、证据及状态收尾：

1. **已有实现与受限实测：**输出 `a7181de4` 已在 selected Env／现有 session 下实现三后端具名 direct effort、共享 joint/R3 reference，以及 MuJoCo 的 hand／自由体 BodyWrench 候选；目标 source 的 tendon／mimic 未被移除。最终代码的三个后端参考 Controller 真实方向对照、旧版本的各 direct 基向量和两类 wrench 实验均有原始证据；这些是具体 source、驱动状态、初态和有限物理响应的证据，不是全资产、独立测力或 4c 成功。不存在已确认的新增 4b 实现缺陷，不据此宣称所有场景均可运行。
2. **证据关联是接收工作：**旧运行前后各自源码一致，但部分文件后来改变，当前缺的是可供主审判断的改变影响说明，并非已证实的物理缺陷。按实际调用和分支判定能否继承；已有差异与当前结果足以支持时不要求复原全部历史工作树、对全部文件逐字证明、重复 5409 项清单或重跑完整基向量矩阵。不能从 hash 不同直接断定必须重新运行，也不能把未知的真实关键改变简单说成无关。
3. **已确认的状态漂移：**当前 API 对早期 4a 限定路线的历史表述和 4b 候选的现状需要分清；`geochora-task-env` 等路由不能继续暗示 4b attempt0。`recovery.md`、原 Goal 顶部及编排索引由 Sol 负责状态和计数；执行者负责与其实际交付直接相关的 API／受影响现有 Skill、功能边界和迁移说明。任何人不能将候选自行写为 Sol 已接收。

## 001 证据的初步差异定位

- MuJoCo hand `native04/05` 的 selected Env、MuJoCo session 与 MuJoCo physical port 三个受检文件的运行时 SHA 均与输入提交 `c1115694` 对应文件一致，可直接用 `git diff c1115694..a7181de4` 查看真实差异。selected Env 增加 GeoPhys/Isaac 分支；MuJoCo physical port 新增仅在 `pickcube-mjcf-physical-effort-no-drive-v1` Artifact 下启用的 drive 隔离；`native04/05` 的 Artifact／profile 是不同的 A05 hand 路线。MuJoCo session 新增 floating joint 校验，需对相应 scene 和路径确认；另外核对 hand profile/builder 在运行时之后的具体调整。此静态对照已缩小问题，**不是要求把上述三文件重新测一遍**。
- `native11` 自由体使用独立 Artifact 与 floating joint；不能仅凭 hand 路线无变化推断它同样无变化。以已记录的 source identity、运行输入、相关 source/builder/validation/physical writer 的变更及 source30 源层结果判断是否可继承；确实不能判断时仅补受影响的自由体路径。
- MuJoCo `native27`、GeoPhys `native30/31` 覆盖逐输入 direct；对后续新增 no-drive reference 控制分支、默认 direct profile／coexist 分支、provider setter／读取路径分别核对。最终 `native40`、`native38/39` 对同一 source 的 reference 路线和最终 session 提供补充证据，但不能因输出类型不同就冒充逐基输入实验。
- Isaac `isaac13/15` 对无 drive 逐输入有正负实测；最终 `isaac24/25` 对同 source／相同 effort owner 的 reference 路线有实测。重点核对 `isaac_native_io.py` 的后续 contact witness／readback 与写入、清除、source axis／mimic 在本例的关系，及 `physical_isaac_candidate.py` 添加 reference 模式后 direct 默认分支的变化。已有运行、源码、可核验编辑记录、同路径最终 real 证据和函数级分析可组成复用理由，不强制复原完整中间提交。若某条必要路径仍存在具体无法排除的行为差异，再做最少受影响的真实对照。

## 最终目标与职责

执行者以原 [4b](../goals/04-control.md#4b) 为准，针对以上差异和遗漏整理原门→实现→证据→限制矩阵，完成证据影响分析、必要的轻量文档／Skill 修正及真实缺陷的有界修复。限幅、采样／cadence、重复 PD、组合与清理分别注明证据层次、后端范围与未测；保留原 `isaac09/11/17` 失败、接触无效和关闭异常；不把真实写入 ACK 称为独立测力。对可复用证据说明理由，无证据的能力明确不支持或未证明，不扩大原 G04 交付。仅发现具体原门缺陷才修现有 owner；用户维护的优先级仍是先使用既有公共接口及 Core adapter、必要时才改 GeoPhys。对文档／证据修改仅用静态文档校验，不触发物理采样；确有行为变更只测受影响范围。

输出包含差异判断（已证可复用／合理有界复用／真正未知的依据）、原门矩阵、必要调整、复用和任何新测试理由、失败历史、完整报告与 writer／锁释放。Sol 独立主审后才能作 4b 决定；Sol 负责后续接收状态和下一阶段编排，执行者不能自行修改为已接收。4c 的切换和 PickCube 成功、装配 Panda 附加用例、阶段5 均不前置。原 Attempt001 与 G03／4a 接收范围保持不变。
