# G04 BodyWrench：三后端与交互施力的主审补充

本页回答维护者对[002 续作主审](20261106_4a_attempt002_recovery_sol_review.md)的进一步问题，基于 `a739510e` 的生产代码和现有证据；不更改 4a 原验收门，也不派发 003 或运行 native。4a 当前仍 `REWORK_REQUIRED_4A`，普通 count=2。

## 已确认问题的范围

对具名关节直接请求 JointEffort（N·m／N）和对 body 某点请求空间力／力矩是不同命令：前者按照关节轴定义一个关节广义力；后者通过当前 body 姿态、作用点和 Jacobian 影响一组关节。当前 MuJoCo port 对后者在边界仅 `mj_applyFT` 一次，然后整个 interval 复用同一 `qfrc`；已知的时变投影问题不能直接外推成 JointEffort 也有同一错误。joint effort 仍仅有 A05 source、写入及 ACK 的有界证据，不代表 4b 真实测力或完整物理表现通过。

MuJoCo 上游的 [3.8.1 `mj_applyFT` 实现](https://github.com/google-deepmind/mujoco/blob/3.8.1/src/engine/engine_support.c)使用当时 Jacobian 累加投影；此处发现的是 GeoChora 适配器的使用方式，不是 MuJoCo 引擎已被证明有缺陷。[MuJoCo 3.8 文档](https://mujoco.readthedocs.io/en/3.8.0/programming/simulation.html)解释：step 前的派生状态可能滞后；`mj_step1/2` 适用于单步积分器，RK4 的依赖状态控制需另一合适路径。实施前应对本机 3.8.1、选定积分器和 actual native step 次序核实，不能单纯在循环中调用投影而使用旧 frame／Jacobian，也不得增加第二个物理推进。

GeoChora 当前仅允许 MuJoCo CPU position candidate 的 physical profile reset；[其他 provider 在公开入口拒绝](../../../../../../task_env/environment/reference_env.py)。因此对 GeoPhys／Isaac 的同一新 typed BodyWrench 生产路径，本次没有代码运行结果，不能声称它们存在相同错误，也不能声称不存在。GeoPhys 原有 position/actuator 或 UI 施力和 Isaac 原生引擎能力都不是该新路径已经实现。

## 原生交互方案和可复用性

MuJoCo 3.8.1 [`mjv_applyPerturbForce`](https://github.com/google-deepmind/mujoco/blob/3.8.1/src/engine/engine_vis_interact.c)从当前 body 状态、拖拽参考、选中局部点计算弹簧阻尼力、偏心力矩并写入 `xfrc_applied`；后者是作用于 body 质心的空间 wrench。引擎[公开实现](https://github.com/google-deepmind/mujoco/blob/3.8.1/src/engine/engine_support.c)在动力学计算时将它映射进广义力。[交互文档](https://mujoco.readthedocs.io/en/3.8.0/programming/visualization.html)要求调用方清除旧外力并处理其他来源的叠加。可借鉴其 body 空间 force／torque 与 COM 偏置转化、动态状态、清理和单一组合 owner；UI 弹簧阻尼并不是恒定指定 N／N·m 命令。直接用 `xfrc_applied` 是待设计和验证的备选，不是已完成的修复。当前 port 拒绝任一非零 `qfrc_applied`／`xfrc_applied`，因此未来如果要程序施力与鼠标拖拽同时存在，必须另外设计明确的所有权／叠加，不能直接覆盖已有缓冲。

GeoPhys [UI 文档](../../../../../../GeoPhys/docs/guides/simulation-ui.md)确有针对可接受动态目标的鼠标点力、偏心力矩、关节约束和释放语义；其默认是质量归一化弹簧阻尼，直接 `PointForceParameters` 则由调用方决定单位。现有点力不证明通用恒定 BodyWrench 的公开程序写入、torque、frame／reference、cadence 与清理均可用；应从现有 public owner 调查可否扩展，不能读 provider 私有 solver。Isaac Sim 6.2 [官方 prim API](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/py/source/extensions/isaacsim.core.experimental.prims/docs/index.html)列出位置、力／力矩和 local/world 参数的公开候选；具体本机 extension、生命周期和当前 Core 接线未验证。不得把公开文档、现有 Position route 或某一旧硬件运行当作 4b qualification。

## 另一项已确认的候选／计划差异

[A05 候选 profile](../../../../../../task_env/tasks/position_candidate/physical_profile.py)把手部作用点设为 body-local `(0.01,0,0)`，力矩参考点设为 body-local 原点；`native05` 对这个 profile 输入 body-frame `(0,0,1)` N 和参考点处零总力矩。[4b 候选计划](../../../../../../workspace/maintenance/v211_g04_4a_attempt002_recovery/4b-plan.md)则规定 world `(0,0,1)` N、body-local 同一偏置作用点、以该作用点为参考的零力矩。这不仅 force frame 不同，参考点也不同。

以姿态单位阵、body 原点 `(0,0,0)`、点 `(0.01,0,0)`、F `(0,0,1)` N 为纯算术例，依[当前 resolver](../../../../../../task_env/runtime/sessions/physical_control.py) 的“torque 是关于 reference 的总力矩”语义：候选指定原点零总力矩，换算后原点力矩为 0；4b 若在作用点指定零力矩，原点力矩为 `(0,-0.01,0)` N·m。候选的结果与其当前声明一致，不能仅因数值不同判为代码数学错误；但不能把 `native05` 当作 4b 的偏心作用力。独立 pure probe 和日志在 ignored `workspace/maintenance/v211_g04_wrench_followup_sol/{point_reference_probe.py,point_reference_probe.log}`，SHA-256 分别 `6cefa0548d179960005fb72905b7df00e07780f1dd0aca8aad04ea01f5426081`、`6fa74668fd4f6f02498911fe060e22fd25effab3eabc61af01b55e4c9079c0d6`，使用 SDK/XML 导入防护，无真实构造或物理步。后续须明确“纯力施加在 point”与“指定关于 reference 的总力矩”的输入解释，并为两者提供可区分的测试；如复用现有 candidate 作为 4b case，修正其配置或选择匹配计划的其他现有 owner，不能在运行后改 oracle。

## 其余已知缺口，不混同为新增 4a 物理门

1. 当前 physical profile 只覆盖 A05、MuJoCo CPU；PickCube physical 与另外两后端须在 4b 接线，source 身份不能混认。
2. source 原有 position drive 仍保留并可叠加 direct joint effort；被测 contribution 的限幅不保证总力限幅，不能把 ACK 当实测力。手指是 8 输入到 9 输出的受限成对力，不代表任意两指独立力。
3. 4b 计划的公共 M/Jc、逐边界读回、soft-constraint oracle 和 G/I 的 force API 仍需实际适配；部分阈值、接触／相同初态、f32/f64 和 41 次建模的预算尚未经本轮真实运行验证。应先选择可实际提供的公开数据与可预检条件，避免前置条件全部 NOT_RUN；不为 4a 重跑矩阵。
4. 当前 physical route 主动拒绝 active recorder；4c Controller reset、状态清理和迁移后 PickCube 成功均未完成。3b 原 N08 失败、Isaac 6.1 启动成功但 close timeout、通用装配补偿未实现保持原历史边界。

可将时变外力和作用点／参考点差异一并纳入后续 4a 受影响范围；后两后端真实施力、物理测量和 4c 留各自阶段。应保留 original 4a 可选择的“正确实现或真实拒绝并留 4b”出口；维护者尚未要求派发新的执行包。
