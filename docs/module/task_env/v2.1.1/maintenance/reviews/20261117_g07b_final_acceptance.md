# G07／7b 最终独立主审与有界接收

日期：2026-11-17。结论 **ACCEPTED_BOUNDED_7B**，普通 attempt 数维持 **2**。
维护者已明确同意只处理最终影响主线的部分，并授权在检查通过后验收、小修由主 agent 收尾。主审实际核查源码、生产 caller、原始记录及资源回执后，接收下列范围。原 attempt001／002 的 **PARTIAL** 返包、失败和中断仍是原时点事实；本页是后续独立裁决，不将原失败改成通过，不声明全套测试全绿。

## 身份、改动与恢复入口

- 主审输入 HEAD：`c392b25967e05020ba303f7b47870b6295ffb964`，分支 `codex/v211-stage7-integration`；生产实现为 `81d1138d54f9397fe1bd3569871fdf8beb05dcb8`。其后只有一个配置测试修正及文档，本次最终收尾不改生产代码。
- 九格实际运行输入：`78349184d0600e2fb804e6461930c475bfcc67c1`；冻结 PR #3 head `23387a9cffd82fe02fb69fb5d2993141fdd54ae9` 的本地合并为 `ab4f9b13c17bcf522ca84bcc8bc94ad527320052`。不包含后来远端变化，也不表示已在 GitHub 合并。
- GeoPhys pin：`198d30ac64ce873a1467f55d2adfc471db18fbc5`；Menagerie：`b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。实际 provider 部署、版本、source／Robot／Controller／Solution／renderer、预算和 driver 哈希保留于原冻结文件。
- 原返包：[attempt001](20261117_g07b_attempt001_execution.md)、[attempt002](20261117_g07b_attempt002_execution.md)；小修与最小补证：[主线优先裁决](20261117_g07b_attempt002_priority_review.md)。原运行目录、原失败、H5、监督器和 SDK/profile 不清理、不改写。
- 本轮独立离线复核目录：`workspace/maintenance/v211_g07b_final_review_20261117/`。`nine-audit.json` 及九份 reader 输出记录原九格重新离线读回；`support-audit.json` 记录七组载荷证据的 **23 份 H5** 与原独立 reader SHA 对账、代表生命周期检查和源码影响。本轮 **0 native run、0 子步**。

## 原九格与其他独立门

原路线、seed、horizon 和成功判据未改变。正式 PickCube／原 Panda／R3，horizon=1000，dt=0.002s、每控制间隔5子步；Task lift 门仍为0.1m。九份 H5 原 SHA 全部一致，独立 reader 重新核对 T/T+1、实际状态重算的 Task predicates、时钟与记录结构；原同运行 caller 的 `solution_done=true`、`completion_eligible=true`、`solution_failed=false`、未截断及正常 close 分别成立。

| 实际运行路线 | seed31：T／T+1 | seed32：T／T+1 | seed33：T／T+1 | 决定 |
| --- | --- | --- | --- | --- |
| MuJoCo CPU | 883／884 | 964／965 | 923／924 | 3／3，按原输入复用 |
| GeoPhys CPU | 874／875 | 956／957 | 915／916 | 3／3，按原输入复用 |
| Isaac PhysX CUDA | 876／877 | 956／957 | 916／917 | 3／3，按原输入复用 |

**9／9 task-success** 与同运行 Solution 完成成立。`planned_trajectory_completed=null`、事件驱动成功时未穷尽点列等事实原样保留；不从 `stop_reason=pass` 或 H5 单文件推导完成，不要求补发剩余动作。GeoPhys／Isaac 的末端 grasp 诊断值不改成 true，也不把 Task lift 成功扩张为新的夹持力结论。Isaac 录制的 external-stop 投影与 caller 实际未截断分别解释，不能互相覆盖。

三个 provider 的 seed31 各自保留 reset、首个非零 step、最终返回边界图像：图像文件 SHA、同一 episode／reset／materialization 与 H5 关联已复核。renderer 分别为 MuJoCo reference／Rasterizer／Isaac RTX，未声称逐像素等价。其余 seed 为 state-only。

其他门按实际受测输入分别接收：同一 Env 的 MuJoCo→GeoPhys→MuJoCo→Isaac→MuJoCo 五段各五步及独立读回；MuJoCo joint→R3→joint 的输入规格 generation／参数恢复、7＋2 typed effort 和 native ACK；Pendulum／PickCube 固定 Rasterizer 的 Isaac↔MJWarp A→B→A；GeoPhys PickCube 部分 reset（33项）；MJWarp 交错终止（69项）及7份 H5／27边界／10组终止与重置相机关联。ACK 不冒充独立力测量；其他 provider 历史7＋2、故障注入和 RNG 范围仍限原身份。原图像归因失败、错误内存上限启动失败及 reader 重试均保留。

## BodyWrench 与受影响主线：逐门裁决

| 门 | 已核对的实现／证据 | 最终决定 |
| --- | --- | --- |
| B2-1 共同贡献与准入 | `joint_efforts` 与 `body_wrenches` 共用原场景 interval／source 身份与提交 owner；producer/body 权限、时钟、effect、冲突检查；MuJoCo／MJWarp 的非法载荷在写入／推进前拒绝 | 有界接收。保留一个 action Controller 与分别声明的场景载荷，不扩张任意多 Controller |
| B2-2 MuJoCo | 手部两构型、local offset 与公开 Jacobian 对照，最大误差2.22e-16；hold／每子步重施／clear 与非零关节 effort 并存。另行冻结零阻尼／零 armature 自由体的 ±force／±torque 对独立质量／惯量 oracle，五份同运行 H5 独立读回 | 有界接收这两种实际 source；原工作包允许独立声明的诊断夹具，其 source closure `3febbe438df9129f7c837d405fb1474a0ce496d44355a21565e6d1ff58d0f84c` 不替换旧九格 |
| B2-3 其他 provider | GeoPhys 公开可达的显式 FREE body；Isaac 6.2 scalar worker 的 hand／free body；MJWarp4.0.1 CUDA B1 world-COM。分别有正向物理响应、载荷清除及独立读回；GeoPhys／MJWarp 有事前冻结的阻尼递推 oracle | 有界接收受测 body／source／reset／轴和载荷，不扩张任意 Frame、link、batch 或 provider |
| B2-4 记录与生命周期 | Controller 动作与场景 producer 贡献分别记录，binding／native ACK／边界能关联；MJWarp 带载荷后的 same-step reset 与无载荷对照无残留，读回 terminal/reset native_step 均10 | 有界接收实际记录路线及 B1 生命周期 |
| B2-5 普通 caller 与回归 | 三条 scalar 普通示例的短程／H5／关闭；真实 PickCube 默认 Robot 往返修正后，7项既有合同／清理检查通过。主审补齐 MJWarp 无 producer 两次正常 reset→非零 action→step、两份同运行 H5 独立读回与 close | 当前受影响主线通过。原115／3、旧宽套件15／28等不相加、不改写成全绿；两个退休注入入口不恢复，当前 builder 清理由既有有效测试覆盖 |
| B2-6 影响与交付 | 实际 diff、冻结 source／caller／reader、原九格和其他代表门逐项关联；原始返包与资源保全，主矩阵恢复为真实结果 | 有界接收，无需 attempt003 或机械重跑矩阵 |

架构审阅对照[优化总账](../../planning/post-5c-code-project-optimization-diagnostic-ledger.md)及[代码约束](../../goals/07-integration.md#g07-code-constraints)：共同准入／提交在 runtime，source body 绑定归 source composition，各原生写入归 adapter，记录归 Recorder／reader；未另造 Env／Runtime／Recorder 或从诊断包导入私有执行入口。worker 沿既有 typed IPC，Isaac 依赖 overlay 限运行拥有的、经核验的少量依赖，不覆盖 SDK/NumPy/pxr 或安装升级。

九格复用不是新 HEAD 的九次 native 复验。原冻结列出的 PickCube recipe、Solution、Panda、正式 caller、相机合同及 canonical reader 字节仍一致；其中 specialization 的差异为显式 scene producer 能力声明／绑定。默认无 producer 的 R3 路径保留原 action 分派；此次影响涉及的普通 scalar／device caller 已有最短定向证据，不能据此泛化所有未测组合。G06 多行结果继续标注其原输入；本次新增载荷只验证 MJWarp B1。

## 保留限制与后续归属

**G07B-MJC-FREE-ARMATURE**：MuJoCo3.8.1／implicitfast／FREE 角向 armature 的原生独立对照已有数值异常，具体根因尚未确认。当前 port 对适用力矩／非 body-origin 矩参考保留写入前拒绝。本次不修引擎、不换生产 source／积分器、不升级依赖；原交集保持未支持／后续专题，不能称“已经修复”。这符合维护者本次主线范围裁决，不再阻断本次有界接收。

GeoPhys 不可由公共 API 达到的 body/link 组合继续拒绝；不声明其他 provider 的任意自由体参考系、任意组件或任意 B。原 GeoPhys Nut 当前源码未重跑；7a 的四个 MuJoCo 任务交集与 LIBERO 64步有限结论继续按原接收范围保留，后者 task_success=false、Solution completion未评估。学习器完整 CUDA 训练、新 R3 batch 模型／补偿包、AOT 等旧后续没有因此完成。

资源不重置：attempt001监督墙时3950.398945739秒，attempt002为2024.152010563秒，前次主审最小补证12.071495502秒，累计余额1213.377548195秒；本轮离线复核未使用 native。新子步周期保守累计2935／200000，旧周期71875另存，Isaac 隐式启动／reset 子步仍 UNKNOWN。共享锁及 pin／dirty／保护核验见本轮 `final-checks.json`；不释放、删除或替换其他线程的锁或进程。

保护日志 SHA256 仍为 `3b08b858f62dcbaa6521802455c76126f9876a3d6727c7586db90c94296ed6a8`。文档校验的既有保护基准差异单列，不能为绿灯修改日志。最终收尾只更新当前摘要／Goal／编排及单一能力矩阵，历史 NOT_RUN 规划快照另存，原 PARTIAL／失败原样保留。

7b 接收解除7c最终总结对验收结果的依赖；独立文档工作树仍按自己的真实状态推进，本轮未覆盖其 writer、未启动7c attempt002。没有 push、回合 develop/main、tag、Release、许可证选择或第三方资产分发。
