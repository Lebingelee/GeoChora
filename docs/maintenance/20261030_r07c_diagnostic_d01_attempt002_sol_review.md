# R07c D01 diagnostic attempt002 — Sol 接收

日期：2026-10-30（Asia/Shanghai）。Luna交接输入 `bb2ad040848e517a4c2c34a2a948bf2297447883`，native绑定实现 `47d38ac40a3aa1a54107582cd4db75403dc6e0e5`。结论：**`ACCEPTED_BOUNDED_R07C_D01_PILOT_S2_S3`**。

接收限于固定LIBERO spatial bowl→plate、LIBERO `8f1084e…` / robosuite `fbee584…`、原manifest `4ad168e…`、source XML `4a922f37…` / closure `3881f687…`、seed19/原rows0/1/2、MuJoCo3.8.1/API3008001 CPU/state-only、20Hz torque ZOH / 2ms×25、诊断joint-space `Kp=100/Kd=20`、16mm aggregate finger target。它不是OSC_POSE等价、机器人任务成功或一般Provider资格。

## 独立复核结果

1. 原交付606/606文件hash匹配、无清单外文件；3321/3321保护原件匹配，12份规划Markdown及planning_manifest哈希均有效。native计划的16项源码逐项与绑定实现Git对象匹配；Luna最后的 `bb2ad040` 为文档/Skill提交。
2. 先复跑新旧受影响检查135/135通过，再加Sol拒绝门检测后143/143通过（36.16秒，进程墙钟36.45秒）。保留Luna19项focused S1的原签署记录；Sol扩展复核同时覆盖原selected consumers、leaf、recording、typed state和camera consumer，未运行native测试节点。
3. 公共Core当前D01路径无LIBERO入口/任务名/物体/固定布局/schema白名单，任务观测与On证据移到benchmark binding；Core保留typed MixedActuatorPlan与编译元数据admission、运行和记录。非LIBERO fixture用不同命名的2 torque+1 position channels、nq10/nv9/nu3，在真实相同Core/adapter路径完成三次reset、H5/独立reader/fault/close；这是synthetic公共合同证据，不授予第二个任务native能力。旧兼容类型保留，不把本包扩为全Core历史Panda重构。
4. 原contact revision和mixed/legacy MuJoCo reset-before-mutation缺陷已有生产拒绝门/回归，复核通过。原native001/002限位失败、native003启动内存门拒绝保留，不与native004拼接；14656 step/15 reset为包含失败reserve的保守账本，不冒称全部实际执行。
5. 以provider import tripwire运行当前更严格reader，native004三份原H5再次verified_complete；独立对原init row逐个named scalar/free qpos/qvel及pose复算，三个reset一致。全部195 T+1观测的实测范围、控制target相对初始偏移≤.15rad、source/episode/clock/On和parent退出/锁绑定通过；监测每episode1601个样本（reset+1600steps），覆盖13个limited joints，最大excursion0、全部7个warning counters为0。保留原5类实际bundle副本拒绝证据。

## Sol直接完成的小修复

为避免再开一次执行窗口，Sol在 `d0c89b57f4b908d02fd9548cbad0268645f0c52c` 完成三个拒绝门收紧及8项检测：

- shared reset验证拒绝v1流入非MuJoCo或无mixed plan session；GeoPhys/SAPIEN/Genesis在改episode/reset状态之前验证。先前模拟无native对象的真实adapter入口会先清reset标志再触碰其legacy字段；修复后明确TypeError，旧episode/feedback不变。
- pinned MuJoCo3.8.1监测/reader要求完整7项warning向量，空/短/长均拒绝。原native004确为7项；原S1 fake误用8项，现与锁定 `mjdata.h::mjtWarning/mjNWARNING` 一致。此数字来自provider ABI，不是任务特判。
- typed position servo拒绝非零affine bias offset及反阻尼项，避免把不同驱动律当作直接q target。原source两position actuators是标准 `<position kp="1000">`、无offset/反阻尼，原物理参数不改；新增底层compiled metadata负例验证写reset之前拒绝。

这些是异常输入/缺证拒绝与S1 fixture校正，不改本次任务source、控制增益/轨迹、reset数值或native积分路径。**没有新增native**：原生事实仍绑定 `47d38ac4`；`d0c89b57` 的改动通过S1和原H5离线重放验证，不声称当前HEAD重跑过native。原H5/result/冻结计划/失败记录及Luna清单保持原样。

## 范围与后继

G0–G6在上述精确范围内接收。D01 pilot统一路线和本次公共Core去特化出口闭合；五任务R07c整体、18/22、P99、Human Judge、Qualification、D0/D1/D2及develop-full集成均不变。task_success=false、horizon-truncated、solution_completed=null如实保留。normal reset不承诺历史每row fixture realization或上游policy evaluation全流程。

后继按原诊断计划评估D02旧BaseTaskEnv调用方迁移、D03兼容名收敛与重复路径删除，再做受影响交集/D04集成；不提前改alias，不合并或覆盖F线。任务局部配方及独立来源/成本/许可/资格门继续分开。Luna完整新工作包仍由维护者转交，本次不自动派发，不启动下一slice/native。

ignored独立复核证据：`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r07c_diag_d01_002/`，包括integrity、初/终S1、底层拒绝门复现、offline_review/reader_replay/independent_physical_review、原源码绑定、修复diff/commit、Skill/document checks和final receipt。审计脚本初版的环境/fixture误差及修正亦保留，不归到Luna故障。
