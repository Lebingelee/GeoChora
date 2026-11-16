# Sol：2b attempt001 暂停中间复审

日期：2026-11-04。结论：**PAUSED_INTERIM_REVIEW / NEEDS_REWORK**。这是中间主审，不是完整报告接收，也不是 `REPORTED_PENDING_REVIEW`。保留候选，不接收2b，不进入2c／阶段3。维护者手动转发同一个 attempt001 的完整续包后才能恢复实施；不另建 attempt002。

## 身份与已验证范围

原包输入 `08103c5156020c340b2d1f373a78a63515e67bb3`；候选 `987873018c48ff3c677db521b58838b898e7ebe3`，父提交等于原包输入。提交仅改 PickCube `solution.py`、`specialization.py` 和新增窄回归测试；生产代码未由Sol改动。GeoPhys pin／checkout仍为 `67da1165149486d3ae3e779c13ce31af49e17d50`。tracked clean，两个保护untracked保持原hash。未push／merge／tag。

Sol独立重跑 safe-approach、R3 velocity-limit、新回归：**8 passed**（pytest 0.64s，整进程0.81s，峰值RSS70,648KiB，禁用自动加载环境插件）。另用纯构造／XML／规划点列及临时锁文件做缺陷审计。Sol本轮没有构造Env／session、启动provider／App或推进physics。

原2a与补充诊断仍是历史输入，不能充当本包运行。2b尚无A/B、完整任务或Nut原生回归，无同run HDF5／独立读回／close封存。

## 必须修复或核清的发现

| ID | 证据与影响 | 恢复要求 |
| --- | --- | --- |
| R1：A/B时间混杂 | 同一测试观测下A为1073动作、B为1183动作；over-cube gate分别在745／855动作后，B额外110ticks=1.10s。现测试压缩重复xyz后比较，掩盖额外等待。 | A/B逐tick xyz、长度、开爪指令、gate计划位置及共同settle一致，仅quaternion路径不同。实际gate等待可以因测量不同而不同，必须单列。保留反证，不能以B多等后通过证明姿态因果。 |
| R2：异常清理不足 | 第二锁open失败的临时文件故障注入，确认第一锁仍被持有；测试已关闭泄漏fd且未触碰真实共享锁。主循环／reader缺少覆盖Popen、日志open、监控异常的外层finally与中断清理。 | 部分锁失败、启动失败、监控异常、SIGINT／SIGTERM、超时和reader失败均有自有进程组清理、每把锁回收与持久receipt；先做无provider故障测试再启动native。不能先释放锁再留下worker。 |
| R3：预算并未强制执行 | 当前脚本只在run结束写ledger；声明总步数／时间但未在启动前汇总拒绝超额；缺失worker结果时actual steps默认0，可能漏记部分执行；worker秒还包含reader耗时；未强制窗口8GiB输出限额。 | 启动前持久预留、累计检查，事件仅追加；故障时记录已确认下界及未知区间，无法核销的预留继续占用，不伪造0；分开worker／reader时间；执行单run和全窗口输出限制。 |
| R4：配置相同≠完整控制链相同 | Pick与Nut底层R3 config／gripper config／rate mapping及planner值相同；Nut实际Controller还有ReferenceExecutionController／StableArmTargetHold／native-rate gripper封装，Pick为裸R3。 | 每run冻结完整Controller配置、wrapper、实际arm hold/ramp请求、gripper内环及5个substep执行事实。先证明比较区段语义一致；不能只比较identity或dataclass。 |
| R5：动力学尚未证明一致 | 纯XML审计：Panda body变换、惯量、joint/default、臂actuator、tendon／equality记录相同；但gripper actuator8 forcerange为Pick `-5 5`、Nut `-400 400`，Nut另有noslip_iterations=2；三处碰撞proxy还存在名称／显示透明度差异。 | 区分臂体自由空间动力学、夹爪驱动／transmission、接触求解与初态。需在相同具名q／qdot下核对编译模型M(q)、bias／gravity、FK／J与驱动读回；不能由配置10N推断native等效力相同。保留物性和oracle，不为“对齐”静默改资产。 |
| R6：夹爪接线提前变更 | 候选已将MuJoCo PickCube R3改为native interval；原包要求到close后有证据才接线。8项测试只确认binding字符串，没有验证真实内环节拍。 | 姿态A/B采用相同已冻结binding；明确其与2a baseline差异，单独核验已有servo是否被推进。若保留，需5×2ms、outer compute一次／outer clock一次、真实反馈／ack和受影响Nut回归；不将该变更归因于姿态效果。 |

## 环境和资源纠正

维护者明确：6GiB主要用于Isaac，MuJoCo不应共用此启动门；允许定位原develop旁既有环境／依赖／资产。旧包未复制ignored workspace造成相对路径失效，不是已证明Isaac安装消失。

- Isaac现存解释器：`/home/lly/Program_Files/Geochora/workspace/environments/isaacsim-6.2.0/bin/python`。Python3.12.14及isaacsim6.2.0.0 metadata存在。旧F06 `isaac_usd_v2/delivery_manifest.json` SHA-256 `6cb07d216689d1e0b6f31ef127d9a511906be90c2acbecb9a30667cdebf113e2`；其9个USD delivery文件与4个配套metadata文件逐一hash相符。尚未验证当前source兼容性、SDK导入／admission或原生运行。
- GeoPhys历史使用既有geochora Python；当前metadata有MuJoCo3.8.1、taichi-forge及runtime0.6.3，当前checkout的GeoPhys/src可定位scene／runtime／geophys包。没有pip geophys distribution不等于源码route不可用。Core与GeoPhys的MuJoCo声明无交集仍是真实问题；恢复包仅授权有记录地探测既有历史组合，不修改声明／pin或跳过显式admission拒绝。
- 续包按route区分：MuJoCo启动MemAvailable≥2GiB、运行低于0.75GiB停止、进程组RSS≤3GiB；GeoPhys≥3／低于1／RSS≤6GiB；Isaac≥6／低于1／RSS≤14GiB。它们是本次有界续包的操作门，不是声称已测得的通用最低配置。其他步数／时间／输出总预算不增加，暂停前消耗须重建并延续。

不运行／import旧Core或旧GeoPhys源码；解释器、site-packages及冻结delivery可复用，所有源码origin必须为当前develop及其当前GeoPhys/src。缺路径先查origin／closure；不复制整个worktree、不安装升级。

## 归因边界与续包出口

先修A/B和监督器，再确认动力学／驱动／完整执行配置，才做真实碰撞、相同reset的姿态对照。减速改善运动误差支持动态滞后；局部J弱方向和DLS输出趋零支持该构型的局部停滞。二者都不等于“目标全局不可达”。可用source-bound纯FK／多起点IK寻找满足原最终pose／joint limits的正例；找到正例也须检查碰撞，找不到正例不能证明不可达。

原始gate仍是height≥0.215m、XY≤0.010m，等待100ticks，原task lift≥0.10m、Solution margin0.105m、horizon6000。保留source、reset、碰撞、旧失败和原oracle。最终仍需MuJoCo seed31完整成功、seed32代表检查、必要Nut seed19回归及另两route精确差异；任何缺失如实PARTIAL。

| Gate | 本次中间复审 |
| --- | --- |
| G0 | 候选／包身份核实；资源门与环境定位已提出纠正，恢复前重验 |
| G1 | 配置接线和离线测试有进展；A/B混杂、plant／完整执行语义未核清，不能PASS |
| G2 | 本包原生任务结果NOT_RUN |
| G3 | 既有环境／delivery找回；当前route readiness／native仍待验证，PARTIAL |
| G4 | 无本包run；监督器需返工，不能PASS |
| G5 | 只有候选提交；完整报告／ledger／manifest／release尚缺 |

证据目录：`/home/lly/Documents/ChatGPT/GeoChora v2.1.1/handoffs/V211_G02_2b_sol_interim_review_20261104/`，含可复现审计脚本、candidate_audit.json、plant_sources.json、environment_audit.json、offline_tests.log及后续review commit receipt。完整恢复包入口：`/home/lly/Documents/ChatGPT/GeoChora v2.1.1/handoffs/V211_G02_2b_attempt001_resume_r002/README.md`。原包／原候选／原helper字节保留，由维护者转发恢复，不自动执行。
