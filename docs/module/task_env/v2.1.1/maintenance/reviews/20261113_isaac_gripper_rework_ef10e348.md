# Isaac PickCube 夹爪返工：物理对照与 Task 就绪修复

2026-11-13。输入 `ef10e348`，复用 `codex/v211-stage5-diagnostic`。这是维护者授权的诊断／修复实施记录，不是整轮 U4 独立主审或 E11～E16 接收。遵守[总台账](../../planning/post-5c-code-project-optimization-diagnostic-ledger.md)的 REN-03／07、TEST-03／04、REC 分层与[诊断边界规范](../../../../../global/diagnostics-and-code-boundaries.md)。原 U3 失败、历史接收及冻结记录不改写。

## 四项问题的实际结果

| 问题 | 实测与范围 |
| --- | --- |
| 空载收到关闭指令能否到 0 | R1-003 保持初始 EE，EE 与 cube 初始相距 118.36 mm；关闭 200 tick 后关节开口和为 **0.0000346 mm**，在预定 0.1 mm 零点容差内。随后 60 tick 重开到 40.90 mm，不能称已重开到 80 mm。 |
| 方块是否为 50～55 mm | 对实际安装 USD delivery 的碰撞 Cube 读 world bound，三边均 **50.0000007 mm**，stage 为米。不是 55 mm，也不是从夹爪关节和反推的尺寸。 |
| 是否夹持、是否摩擦不足 | R2-005 中关闭后关节开口 53.644 mm，随后调用方保持关闭并命令抬升；方块从关闭边界升高 **136.185 mm**，最终高于任务 rest 136.380 mm。30 tick／0.3 s 保持中 EE 与 cube 相对高度变化仅 **0.0175 mm**，腕部图像可见方块留在双指之间。该 seed／资产／5 N 条件支持有效夹持与抬升，不支持把原失败归因于摩擦不足或 53.6 mm 的空载硬限位。 |
| 腕部相机与 H5 | 正式 CameraSpec 挂载 `panda-v1/ee`，256×192 float32 RGB；H5 有 **430 个 transition、431 个 observation／RGB、2,150 个连续显式 native 子步**。图像、开口、物体／末端位姿与动作均可读回；五个阶段末帧与另存原图逐字节对应。 |

这里的 opening 是两个关节位置之和，不能当作碰撞垫净间距。接触事件订阅返回空报告，**不能据此认为没有接触，也没有获得独立接触力／摩擦系数测量**。有效夹持依据是正常控制下的物体共同抬升、保持和原始图像。历史 `grasped_cube` 是 45 mm 奖励代理，本次可在实际抬起时仍为 false；实际成功判据仅为方块抬高 100 mm，未修改它或奖励。

## 根因与正式修复

原 Task `PickCubePositionExecutionInfoV1` 要求目标、实测开口均 ≤45 mm 且速度和 ≤5 mm/s。Solution 在关闭阶段消费该值，未就绪就不进入抬升。R2 原控制／力限幅不变即可在约 53.6 mm 夹持并抬起，直接证明“已能抬起，但旧就绪门不允许试举”的缺口。

修复放在 `tasks/pick_cube/task.py` 与 `solution.py`，不在 Env、Controller 或 PhysX adapter 添加任务特判：

1. 新 Task 输出 `pickcube_position_execution_info_v2`。完整零开口请求、实测小于全开 80 mm、速度和 ≤5 mm/s 表示该边界关闭已稳定，**不表示已抓住物体**。未收到完整关闭命令、仍运动或全开都不满足。
2. Solution 在关闭计划耗尽且连续稳定 50 ms 后尝试抬升；稳定计数遇运动归零。实际是否成功仍取决于物体抬升，空载／错误抓取仍可能失败。
3. v1 显式输入保留原 45 mm 定义，不重解释旧记录。没有扩大到某个新“抓住阈值”，没有改 drive、材料、摩擦、资产、5 N 限幅、planner 或 100 mm 成功门槛。

正式调用链仍是 `make_env → Task binding → Runtime`，调用方持有 Solution，执行 `act → env.step → observe`，一个 interval 仍由原 owner 提交及推进。R3-002 在与原 U3 相同的 seed31／1000-step horizon 下，关闭阶段于第 694 步结束，正式 Solution 于第 **951 步完成**，任务 lift **105.254 mm**，`solution.done=True`、`failed=False`。没有诊断抬升、接触订阅或额外动作。H5 独立读回 **951／952、4,755 个连续显式子步、9.51 s**；第 689～694 步的全关指令、约 53.632 mm 开口及约 2.025 mm/s 速度均可核对，这六个边界按旧 v1 全部不就绪。

## 相机与诊断归属

`CameraGeometry`／resolver 处理 qualified Frame 与安装变换；renderer capability 明确声明移动挂载支持；Isaac camera owner 从当前公开 typed state 更新自有 USD camera，原绑定检查核验实际位姿及 optics，原采集路径保持零额外物理推进。MuJoCo／GeoPhys 移动 task RGB 和 world-only observer 之外的路线仍拒绝，不从该腕部实例推广任意组合。

诊断驱动、公开 SDK 接触订阅、原始行采样与 pure／fake 检查全部位于 `task_env/diagnostics/tasks/v2.1.1`。没有 Core 对 diagnostics 的反向依赖、实验名分支、私有 provider 引用或第二个物理推进者。相机是正常 CameraSpec 产品能力，不是 Core probe 开关。R2 人工抬升是明确干预，不能冒充完整 Solution 成功。R3 使用普通 caller loop；进度代理只将原 Solution.observe 调用一次后复制公开 info。

## 验证、冻结身份与保全

- 最终相机代码与就绪修复下 **240 项 guarded pure／fake 检查通过**。新回归覆盖 qualified／歧义 Frame、unsupported mount、相机自有写入、53.632 mm 记录边界、未关闭／仍运动、连续稳定被运动打断，以及 v1 历史定义保全。纯检查不证明 native 接触或像素。
- R1 H5 独立读回 260／261 边界与 1,300 个连续显式子步；R2 独立读回 430／431 与 2,150 个连续显式子步，所有相机 receipt／诊断 boundary 与 H5 typed witness 对应。Position 记录使用既有 F06 witness；`load_physical_recording_h5` 因缺少其要求的 physical boundary_contexts 而拒绝，实际使用 `load_structured_control_records_h5` 加独立 h5py 检查，不声称前一 reader 已通过。
- R2 源码冻结在输入 HEAD 加 `native-plan-contact-005.json` 所列 patch／文件 SHA；R3 另行冻结 `native-plan-solution-002.json`。成功的 R1／R2 诊断脚本精确字节已恢复并核对原冻结 SHA，R3 的全部冻结源码也已另存；相机生产字节二者相同，R3 的 Task 就绪变化没有用于 R2 人工抬升。原 USD manifest SHA `6cb07d216689d1e0b6f31ef127d9a511906be90c2acbecb9a30667cdebf113e2`、entry SHA `c225852355f62b1ea8baa86699b246459e2d93a93b6d9877bc6fd728e061f7c5` 不变。
- 各 native run 使用原双共享锁、唯一 cwd／输出、cgroup CPU400%／Tasks128、RAM 6或8 GiB 上限、host／GPU／disk 水位及独立墙钟预算。SDK 隐式 startup／reset 推进数 unknown，不计入显式子步；没有并发 native 写者、覆盖旧结果或安装依赖。
- R1-001 启动前混入 pip USD ABI、R1-002 缺 h5py；均未完成显式 interval。R2-001 接触视图初始化顺序失败；R2-002 首 interval 后相机 xform 布局拒绝；R2-003 首帧等待后由本轮停止自有 scope。这三次关闭没有最终回执，不补写“已正常关闭”。R2-004 和 R3-001 在定时栈转储期间以 -11 退出，没有最终 H5；不能将此作为夹爪物理失败或已确定的 SDK 根因。最终诊断已移除全部定时转储，仅保留故障处理和公开进度。失败输出保留，可比较代码与采样差异。
- R1-003、R2-005、R3-002 均有 native IO／source lease／App close completed 回执、空 scope 与释放锁。R1 的 SDK 菜单 callback 日志限制保留；close 回执不代表 SDK 日志无异常。

R3 H5 的 `solution_completed` 仍为 null，最终 outcome 为 `external_stop`／`truncated=True`；这是外部 caller 完成后主动结束记录的既存投影。上述完成结论来自同次 caller result（`terminated=False`、`truncated=False`）与实际 H5 SHA 的关联，不能称从 H5 独立读出了 completion。这一 Recorder 口径仍留原 U4／T19 处理。

本轮共触及 20 个文件，新增 4、删除 0、整文件迁移 0；按 `git ls-files`（含两个 gitlink）项目文件 1,421 → 1,425。9 个生产 Python 文件 **+78／−24、净增54行**；6 个诊断／测试 Python 文件 **+561／−2、净增559行**，无迁移代码充作删除。新增代码分别承担正式移动相机、就绪语义及三个外部对照／回归，未把净增说成代码精简成果。API、Skill、诊断入口和当前摘要同步到实际边界，文档检查较本轮输入没有新增错误，既有 MUJOCO_LOG.TXT 保护检查差异和79项历史链接问题保留。

## 原始证据与查看

所有原始文件位于 ignored [本轮目录](../../../../../../workspace/maintenance/v211_isaac_gripper_rework_20261113_001)，保持历史输入原样：

- [空载 H5](../../../../../../workspace/maintenance/v211_isaac_gripper_rework_20261113_001/empty-close-003/experiment/episode.h5)，SHA `ce32105b660794df25e24258525452b56f95119950f3b9ba7fa76fb1af0914fd`；同目录 `independent-readback.json`。
- [腕部 H5](../../../../../../workspace/maintenance/v211_isaac_gripper_rework_20261113_001/contact-lift-005/experiment/episode.h5)，SHA `61107e476d16b1a8b3c3575238891143414ef94761dc8398c241efc43e32dbd5`；[独立读回](../../../../../../workspace/maintenance/v211_isaac_gripper_rework_20261113_001/contact-independent-readback.json)、`rows.jsonl`、逐帧 camera receipt 与各 run supervisor 同存。
- [正式 Solution H5](../../../../../../workspace/maintenance/v211_isaac_gripper_rework_20261113_001/solution-002/experiment/episode.h5)，SHA `95add33866ad97627ad0deb6e44fc53cae75aa2fcadb80ec59c28781387d92f4`；[独立读回](../../../../../../workspace/maintenance/v211_isaac_gripper_rework_20261113_001/solution-independent-readback.json)及同次 `result.json`。
- [腕部阶段图](../../../../../../workspace/maintenance/v211_isaac_gripper_rework_20261113_001/wrist-contact-lift.png)、[腕部动画](../../../../../../workspace/maintenance/v211_isaac_gripper_rework_20261113_001/wrist-contact-lift.gif)、[开口与抬升曲线](../../../../../../workspace/maintenance/v211_isaac_gripper_rework_20261113_001/opening-and-lift.png)。动画为每四帧抽样，播放速度不等同仿真时间。

本轮未重跑 CPU／effort 矩阵或其他 seed；未改四个保护输入和两个 submodule pin，未操作 refs／worktree、合并、push 或发布。E11～E16 原 U4 的独立主审、H5 completion 口径及维护者决定仍是各自待办，不能用本次专项替代。
