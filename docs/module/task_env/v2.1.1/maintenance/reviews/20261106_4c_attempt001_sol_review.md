# G04/4c attempt001：Sol 独立主审

## 决定

`ACCEPTED_BOUNDED_4C_RESET_PICKCUBE`，普通 attempt count=1。原 4c 同一 Env 的 Controller／输入规格 reset、原任务迁移后成功和记录出口，在此包的 MuJoCo 3.8.1 CPU、PickCube 指定 source、单环境与两类 declared controller 下有界接收。完整 G04 的 4a、4b、4c 分别在各自此前／本次有界结论下接收；这不是全部后端、所有任务、全部机器人或正式 Qualification。维护者未授权自动进入阶段5、push/merge。

## 独立核对

- `codex/v211-stage4` 输入 `ef998e253a53f0c799fc3c6401ce235086e78ccc`，实施输出 `0f2e9053a32e2cb7058864b3ef18ebd4c91dfbf1`。清单 1716/1716 文件／链接摘要及尺寸相符；release receipt、两个 gitlink 及三保护输入核对一致，实施会话 idle。此次主审不运行 source/native/GPU，不重跑物理矩阵。
- `native16` 同一 Env 的 R3→joint（`kp=100`）→R3 三个 episode 的 generation 为 1/2/3，旧动作在真实推进和记录前拒绝；同 shape 不同语义固定策略在破坏旧 session 前拒绝。3 个 H5 由 Sol 独立重跑既有 reader，分别确认规格、generation、每集 1 条 transition 和 2 个 observation boundary。对 initial state，R3 使用 source EE pose 及独立 H5 state；注意原运行日志 `realized_joints` 字段在 R3 分支实际上存的是动作位姿，不将其误称为关节样本。新 R3 从 realized state 重置记忆；Sol 以守护的 12 项定向纯／fake 测试复核 generation、参数、state、Recorder 投影和动态模型等。
- `native16` 发生在提交 `41e2b899d2c22b59b173ee0e58be4604bc70f21f` 的实现下；独立 `git diff` 与最终 `0f2e9053` 的唯一生产差异为将 `resolved_configuration.finger_initial_position_m` 报告值从常量更正为真实初始化声明。该报告元数据修复不改变 native16 切换控制路径；不声称 native16 在最终字节代码重跑。`native18` 对更正后的实现实际校验初值，最终完整 `native19` 的 11 个声明关键文件运行前／后 SHA 均与最终提交匹配。
- Sol 独立重跑守护 reader 核验 `native19/episode.h5` 的 993 transition／994 boundary、task success、Solution complete、未截断和所有记录的 typed batch/ACK 关联；task metric cube_lift `0.10535127009556083 m`，独立 H5 起末 cube z 差 `0.10435125231742859 m`，都超过原 0.10 m。此为 seed31、单 source 的真实 MuJoCo 物理响应，不是独立测力；成功来自任务 predicate 和 observation，不来自 ACK。早期失败、reader失败、native17 保守计账与结果保留。
- 提交对 4b 旧路线的共享改动按条件及调用路径审查：旧调用保持默认参数，新 gripper 限制／禁用 drive 分支只对新 task Artifact 生效，新 model 仅为 opt-in reset selection 注入；4b 的三后端和外力原有有界接收及历史失败不变，不重跑其矩阵。

## 条件及未覆盖项

- MuJoCo 原 source MJCF 的 actuator8 声明 ±5 N；本次任务 profile 经明确检查后将 native runtime cap 配为 ±10 N，paired joint effort 的准入域按该配置映射，source 文件本身未改。原 2c 的 selected PickCube runtime 也显式配置 10 N，故此是同任务运行配置的有界迁移，不是声称 source 原声明未被运行时覆盖或 ±5 N 条件下已成功。MuJoCo 的 direct effort 写入广义力，实际受 Core admission 显式限幅；ACK 不是传感实测力。
- 真实 A→B→A 覆盖单 Env、单 writer 的 R3 与 joint 规格及参数，scalar 路线拒绝 batch；并非 native batch Controller 切换覆盖。切换 profile 未声明 BodyWrench，未真实演示带持续外力切换；4a/4b 原已接受的 typed context、新鲜度、隔离 buffer、清理和代表外力证据各依原范围保留。不可将它表述为所有外力、所有嵌套 binding、不同 provider 的 reset 组合已做真实验证。
- `native15` 注入 Recorder 错误时已运行一个 interval；错误向调用方暴露、故障锁存并禁止再推进，但故障收据的进展为 unknown，不能声称精确故障前原生边界。执行者记录的夹爪 force、源身份和实际样本说明见原始 report。进程树 RSS 为离散采样而非连续峰值保证。
- 维护者已将本窗口物理子步预算由 30000 增至 60000；执行者保守记账 30350，其余限额不变。更正：4b001 的 GeoPhys A05 joint2 诊断最初 `native16` 超时仅完成两次基线；维护者扩额后已由 `native17` 完成两次基线与正／负载荷，结果为 `PASS_DIRECTION_ONLY`。4c 未重复运行该诊断，不能将它误写为仍未完成；它只证明 A05 joint2 的有界方向响应，不证明独立测力，亦不替代后续 PickCube 八输入的独立有界结果。原 N08 失败、Isaac 6.1 关闭超时、通用装配补偿未完成、装配 Panda 与 7a/7b 后续事项继续保留。
