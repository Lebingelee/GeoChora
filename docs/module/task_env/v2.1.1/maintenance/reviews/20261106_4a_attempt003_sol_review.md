# G04 4a attempt003：Sol 独立主审

## 决定

Sol 决定 `ACCEPTED_BOUNDED_4A_CONTROL_CONTRACT`：**按原 4a 契约、统一消费与 4b 计划出口有界接收**，普通 attempt count=3。此决定接收控制主体／typed 物理命令／公共模型与消费边界，以及 4b 验证计划的已陈述设计；真实运行支持仅限本页实际证据，并不接收 4b 三后端物理施力、实测力或 4c Controller reset／PickCube 成功。维护者手动决定并转发下一个完整包前，不自动启动 4b、阶段 5 或新会话。非刚体仍仅 typed 槽，装配 Panda 保持原已采纳版本附加用例的排期。

## 输入与独立核对

- 4a 第三普通窗口输入 `0d978d0291997ad81167bcafd3c10bb6be975daf`、执行输出 `105219eda7161e7292d0d8c2ce478c49bdb4eca2`，分支 `codex/v211-stage4`；无 push／merge。GeoPhys pin `dc2685e28c6c916fb6403a2342c04e0d2520aef7`、Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` clean；三个保护 untracked 的精确 SHA 与输入一致，未更改。
- 完整重算本次输出 manifest **678/678** 文件 SHA，全部匹配；manifest 自身 SHA `0abfdec614c599d22b15ae45a57aed42798f2333d41a5b1bfdd33a48455a82bb` 与执行者 SHA 文件一致。冻结 [handoff report](../../../../../../workspace/maintenance/v211_g04_4a_attempt003/report.md)、[12 案例矩阵](../../../../../../workspace/maintenance/v211_g04_4a_attempt003/case-matrix.md)、[4b 计划](../../../../../../workspace/maintenance/v211_g04_4a_attempt003/4b-plan.md)、[输出清单](../../../../../../workspace/maintenance/v211_g04_4a_attempt003/output-manifest.json) 和原始日志；release receipt 记录 writer 和双锁释放及无本包残留测试进程。
- Sol 审阅相应代码与真实 native08／09 入口、测试和日志：两个 run 记录的受检生产源码前后 SHA 相同且与 `105219ed` 一致；native09 确认 A05 source closure `aa4ca97bbe3c61b30752ba0dedc6c88a24394f03fe1b53519052d460ff9abc47`、MuJoCo 3.8.1、`implicitfast`、一次 effort＋body-wrench batch/ACK、5 substeps、1 次预写及 5 次逐子步刷新、结束 buffer 清空和 close；native08 是同源 split Controllers 的 effort batch/ACK、5 substeps。两次是构造／映射／提交／刷新路径证据，不是独立物理力测量。整个 attempt 的真实记录为 9 个受锁 source/native 进程，其中 2 次无物理步、7 次各 5 步，共 35 步；非全部九次均成功推进。
- Sol 独立在旧 `sitecustomize.py` guard 下运行新 wrench 子步测试文件及 4 个受影响的合同／准入测试，共 **16 passed**；guard 阻止 XML source 解析和 MuJoCo／其他 SDK 导入。本审无 native／GPU／source 解析。日志 `workspace/maintenance/v211_g04_4a_attempt003_sol_review/independent-pytest.log` SHA `a619c729d5f62ba3716916a9242d81212c4191a3c68c13669a9c1a32cffc4178`。执行者的 `pure01-before` 为测试前提错误、`pure02-before` 为旧实现缺陷敏感失败，两者如实保留；此前 001 越界解析和 CodeGraph 误匹配历史不改。

## 对原 4a 的判断

1. **主体、命令与模型：**继承 002 的 nested binding、具名 Panda 8→7＋2、类型／组装、source-bound transmission、公共 state/model、ACK/测量区分；其纯计算／source/fake 证据与本次受影响检查共同覆盖 4a 的分层要求。零偏置直入力模型不是 Panda 真实动力学；按原 planning 不要求在 4a 实现所有 provider 的动力学模型。
2. **持续 BodyWrench 和唯一提交：**[MuJoCoPhysicalPort](../../../../../../task_env/runtime/sessions/mujoco_physical.py)保留原始命令，在真实 session 每个 substep 刷新当前运动学及 `mj_comPos` 后，重新解算 force／point／moment reference 并使用当前 Jacobian 投影；明确 unsupported wrench integrator 在 build 绑定时拒绝。fake 回归用 world 固定／body 随体／site、两构型和解析 oracle 检出先前固定投影问题，同时检验组合、异常清理、重复／重施和外部 buffer 冲突。native09 证明声明的 A05 代表路径及刷新实际发生，未独立证明受力响应数值。保持一次贡献一次投影、已存在 position drive 与 direct contribution 不混为 measured force。
3. **作用点和矩参考：**现有 typed 语义为 `torque_Nm` 指定关于 `moment_reference` 的总矩；pure 回归区分 point-reference 零矩的偏心作用与 origin-reference 零总矩、旋转 frame 和自由矩。原 A05 候选使用 body frame／origin reference；4b 提出的 world-force／point-reference 场景需要独立 profile 和实际接线，native09 不能代替。保留原 candidate identity 和历史结果。
4. **能力与生命周期：**实际 body-wrench 运行范围为 source-bound A05、MuJoCo 3.8.1 CPU、`implicitfast`；其他积分器的该 body binding 在写前拒绝，GeoPhys／Isaac physical profile 当前不准入。代码对已占或变化的外力 buffer 拒绝，并在可辨认范围清除自有值；若发生外部并发写入，混合所有权无法推断，须结束故障 session，不声称并发 UI 叠加能力。selected 生命周期 ACK 异常后的 abort 由 fake 测试覆盖。P1–P5/N1–N7 的精确阶段／证据见执行者矩阵；P5 真切换属于4c。
5. **4b 方案：**提交了三条 provider 的目标／source／coupling／drive、7＋2 输入、外力两个目标、force/frame/point/reference、baseline/load/clear、模型／阈值规则、preflight、owner 和待审资源预算；可作为原 4a 的条件验证规划交付。该计划不等于对三个 provider 已有能力的声明，也不自动批准未来 41 builds、600步、固定数值阈值或 4b native 执行。新 `free-body-implicitfast.xml` 在本次 ignored 证据中由 manifest 固定；后续 4b 须由既有 Task Artifact owner 正式接入并核对 source 身份。GeoPhys／Isaac 的物理端口、实际 source 与独立读回、world-force／point-reference 正式 profile、无接触初态及候选阈值应在 4b 包中明确执行与预检，不能把当前 NOT_RUN 当通过，也不把这些实测提前变成 4a 门。

## 持续限制与交接

不外推其他资产、backend、积分器、纯 fake 或 ACK 为物理合格；实际三后端 7＋2、物体／Robot body 持续外力及独立物理反馈属于 4b。当前 physical route 不支持 active Recorder；3b 原 N08 FAIL、Isaac 6.1 启动后 close timeout、3c 有界 reset 接收和非通用装配补偿的边界不变。需要明确 distinguish controller input、native joint contribution、existing position-drive force 与真正测量／估算。实现会话 Goal completed 是执行者技术交付状态，4a 接收以本主审为准。
