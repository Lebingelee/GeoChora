# R07 v2.1.0 window001 暂停复核与 attempt002

日期：2026-10-30。维护者因执行时间过长手动停止，Luna明确暂停Solution实施、无新代码/测试/native，交回clean camera `a6efc3e70e445a4be1b225c8a91766fe6f580d20`。Sol复核确认当前无旧worker匹配，观察时共享flock可取得；这不是后续时刻全局资源保证。主checkout/F线可并发推进，未写入它。

**结论：`PARTIAL_PROGRESS_RETAINED_TASK1_SOLUTION_REWORK_REQUIRED`。** 没有完整旧最终交付报告，原progress仍为in_progress；依据维护者停止与Luna暂停交接接管，只在本复核/新包记录中标记旧窗口已中断，不改写旧目录补造最终报告。R07三个required任务/九格部署/分层Solution目标仍未完成；不授予R07/P99或Qualification。

## 独立核验与可复用事实

- 原window001包100项SHA全部匹配；原保护输入16,265项全部匹配。camera相对输入 `77cfeba4` 的增量15文件、3,153插入/145删除，主要为source-bound TCP/FK、mixed external Solution lifecycle、任务2/3语义S1、task1 Solution/重力模型及worker/reader；不是15文件全部已接收的声明。
- 15次native启动、144,132实际physics step、17 reset；逐run parent记录重算wall130.819秒，全部记录PG已结束/lock释放。该wall只计native worker，不是本窗口开发时间；不能据此声称整体工作仅两分钟。源重力计算的独立model compile/forward不是physics step，继续分栏记账。
- provider-free `test_r07v210_required123_semantics_s1.py` 独立复跑10/10通过、无engine imports（0.35s）；不追认其他旧集合或把S1当三任务native。
- task1原source install/verify与MuJoCo CPU构造/reset/record/close事实可保留。run010三episode、3,000 transitions/3,003 obs/75,000steps全horizon失败；三row阶段分别approach833/824/880步，descend167/176/120步，均无抓取成功。它是定位失败与存储事实，不是task或Solution成功。
- controller_tracking_002：原H5 SHA、worker/parent/tracehash核对，64条trace的实际joint/TCP逐行与原H5后续64观测完全一致；重新算全部64边界最大TCP误差0.011731137456785674m，四段末四边界最大0.004056516696376581m，均小于已有0.012m诊断容差。无trace力矩饱和/Ack clipping，原source-limit报告为空；64T/65obs、1,600steps/1reset。**只保留为此四setpoint、空载、MuJoCo3.8.1 CPU/v6控制器的有界诊断，不证明动态抓取路径、任务成功或控制器资格。** 若控制计算/trajectory/通道语义改变，只针对受影响部分补验证。

## 已确认返工点与仍未知

1. `LiberoPickPlaceSolutionV1.act` 在任务模块直接取FK/Jacobian并写位置DLS，未调用现CartesianPosePlanner、JointPositionPlanner、CanonicalPandaController的arm解释/DLS owner；没有末端姿态目标。复用`PandaKinematics`不足以证明Controller/Planner复用。姿态缺失与joint7累积运动是风险，当前证据不能把它当唯一失败根因；run010主要停在approach/descend，仍需以实测pose/速度/碰撞/stage日志分清跟踪速度、位姿和抓取问题。
2. `LiberoPickPlaceSolutionV2.act` 拥有MuJoCo source gravity模型，并用 `q_action=q_planner+gravity/Kp` 编码feed-forward；控制参数泄漏进Solution、关节“目标”不再表示真实几何目标，且绑定MuJoCo。旧模型本身只用独立source bytes/公开MuJoCoAPI、不读live session私有模型，不能笼统称provider-private违规。新路线应将feed-forward输入/计算移交现task controller/公开动力学primitive，真实关节目标、torque和clipping分别记账，旧schema/reader仍可历史读取。
3. run010 source_inputs只剩`closure.tar.gz`与成员manifest；当前consumer先resolve expanded `closure`，所以Sol直接重读在解析H5前FileNotFoundError。原reader签署结果和H5保留，**当前reader对归档后的同一bundle不可直接复读**。不得在旧目录重建或改路径伪装通过；在原source/reader owner增加有界archive-aware读取，核原路径/逐成员hash/闭包，读副本/新工作目录并保留原parent绑定，不造第二reader。
4. task2/3酒瓶/酒架来源门仍未解决，尚无其native。不得据已选required删门/换物体/简化场景。其他provider尚无本三任务运行证据。
5. 旧输出2,086,407,142bytes，距2GiB余61,076,506bytes（约58.25MiB）；接续使用新独立输出根，不再向旧包追加大产物，不删除/重新压旧证据来制造空间。

## attempt002 接续决定

按维护者暂停与等待新包的明确指令准备一个短窗口：优先task1/MuJoCo真实完整Solution，修复上述复用/职责和归档读回，复用未改的环境/source/空载结果。预计主动150–210分钟、timebox240分钟（最后30分钟报告）；不是再次发送全九格13小时包。不新增GeoPhys/Isaac native或provider实现，不把本次task1局部收口记成R07完成；task2/3来源核实限20分钟并只记录新增可验证事实。此为整体required123 window002，旧window001与历史pilot/D01不清零；手动暂停不是预算耗尽，剩余额度在新包中显式分配而非重置。

目标调用链：task stage/世界SE(3)目标 → 现CartesianPosePlanner pose插值 → 同CanonicalPandaController arm解释/DLS（必要在该owner抽复用primitive，不能新复制DLS）→ 需要的JointPositionPlanner连续目标/夹爪过渡 → 原task mixed controller的真实q target+torque feed-forward → RuntimeSession/MuJoCo。不是要求每个阶段机械同时调用三类或仅创建对象凑调用；适用路径有实值验证，planner规范化夹爪[-1,1]与原signed双指总开度m显式映射。Core保持通用、task几何/阶段不下沉；抓取需要source-bound姿态与实际object/contact反馈，不能靠12mm TCP标量独立宣布成功。

新输出 `r07_v210_required123_002/`；新证据512MiB、试验临时空间512MiB（单独计量、不得删旧文件）；最多新增150,000实际MuJoCo step/24reset/native wall3,600s，累计含旧≤294,132step/41reset/3,730.819s，其他旧全目标余额不被自动授权。无固定launch次数上限，但单row/短stage probe先定位，只有已显示实质改善才跑三row完整campaign；不连续换gain盲扫、不重复完整source大包/海量tamper副本。完整prompt/精确HEAD/保护hash/预算/验收在 `sol_r07_v210_required123_002/` 冻结，维护者转发，Sol不自动发线程消息。

Sol本次没有修改实现或新增native；只做证据hash/离线H5/10项provider-free复核和本地文档/包。审计脚本初版误把worker的all-boundary最大值当endpoint最大值，已按原trace更正；一次系统Python缺h5py改用现geochora解释器，均不归为Luna故障。ignored复核原件在 `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r07_v210_required123_001/`。
