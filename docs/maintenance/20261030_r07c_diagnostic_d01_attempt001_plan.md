# R07c diagnostic D01 attempt001 — 统一 RuntimeSession 路线

日期：2026-10-30（Asia/Shanghai）。维护者已指定本诊断对话可使用多个 diagnostic attempts，目标是最终完成原五任务 R07c；普通 attempts001–003 的 partial/失败记录保持。本页仅冻结首个可交付窗口，不声明实现、native 或验收已经完成。

## 分支、窗口和集成

- 复用 camera 工作树 `codex/phase-ii-01-camera`，规划输入 `b34d88a668d50e5a59f93e9613a110e6face3e2c`；执行输入取本计划提交后的实际 HEAD，保存在 ignored 包 snapshot。新增 Core branch/worktree 数量为 0。
- Luna 2号执行 D01。主 checkout `develop-full@b087afee98e97875c0875175e3a756820d9a0b33` 为 F05 比较基线，由 F05 writer 持有；本包不写主 checkout、F05 provider worktree 或任何 submodule。
- 两 checkout 的同名 owner 可独立开发；严禁复制 camera 旧文件覆盖 F 线、merge/rebase/cherry-pick 或更新 pins。交付列与冻结 F05 基线的 owner 冲突，后续由 Sol 审查具体 patch 后另行授权集成；camera 结果不能直接声称当前 develop-full 已支持。
- Luna 2号先确认前次中断的 F05 转述请求没有仍在执行的进程/写入。本包替代该转述请求，只执行 R07c，不向其他线程转发、不创建 subagent。

## 本窗口交付

分类为 FIX_EXISTING / EXTEND_EXISTING / COMPOSE_EXISTING。在现有 `SelectedReferenceEnv → RuntimeSession → MuJoCo adapter` owner 内补齐固定 bowl→plate pilot 的真实构造、mixed control、非零速度 reset、具名姿态/contact、公开生命周期和同一 H5。benchmark 专属配方、增益、PD 策略和 On 语义放在 `bench_deploy/libero/`；Core 只承担可复用合同、admission、运行和记录。删除 candidate 的旧 BaseTaskEnv 活跃接线与伪 MuJoCo S1，不删除统一 GeoPhys session 仍依赖的 bootstrap/helper。

现有 ResetSample v0 只允许零速度，MuJoCo reset 清零 qvel；SelectedReferenceEnv 默认 hardcode Panda/tendon controller 和时间零点。必须在既有 owner 中版本化扩展并保留旧 codec/hash/默认行为，不能靠改 provider 字符串、设 Position flag、raw flat array 写入或 benchmark solver 循环绕过。

本包完整实施与验证 D01；只输出 D02–D04 的调用方/集成矩阵，不批量迁移 Empty/Pendulum/TwoWheelBalance，不提前改 BaseTaskEnv alias。原五任务、后续 caller 迁移和 develop-full 集成仍需独立证据。

## 初始化合同修正

正常部署按锁定上游 reset 后 set_init_state 的语义处理：fixture realization 来自当前 reset sampler，随后恢复所选 `.pruned_init` 的 time/qpos/qvel；不要求找回该 row 的历史 fixture sample。保留 BDDL placement、采样顺序、坐标/旋转、碰撞与 quaternion 约定，记录 seed、realization、源码/hash。静态 XML 默认位置不自动等于上游 reset。

该修正仅替代旧 attempt003 中“一般部署必须绑定历史 fixture realization”的额外门，不追溯改写旧 G1 为 PASS；compiled nq/nv/na、具名 joint/order/address、非零 qvel、fixture placement 和真实 semantic readback 仍必须验证。精确 demo XML/state 历史重放不在本包，不下载 demo HDF5。

固定源参考：[LIBERO reset](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/bddl_base_domain.py)、[state restore](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/env_wrapper.py)、[evaluation](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/lifelong/metric.py)。

## 出口和预算

完整 prompt 在 ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_r07c_diag_d01_001/`；新输出只用同维护根 `r07c_diag_d01_001/`。维护者转交完整包后，才进入该包新的实施/有条件 native 窗口。不是沿用旧 attempt003 未消耗额度。

预计主动 240–360 分钟；总 timebox 420 分钟，最后 30 分钟收口。先真实同路线底层替身 S1、worker/reader/fault/cleanup，再冻结每 run 输入。native 仅 MuJoCo 3.8.1 CPU/state-only，独占现有 shared native lock；每进程 600 秒、采样 RSS 2 GiB/终止 3 GiB，累计 native 3600 秒/20000 mj_step/30 reset，启动 MemAvailable 至少 6 GiB，低于 2 GiB 中止。允许预算内修复重跑，没有单次启动上限；失败和探针计入预算。S1 每进程 300 秒/2 GiB，资源密集进程一次一个。输出至多 1 GiB；固定官方文本来源补充至多 32 MiB，不安装/升级/下载新模型。

native compiled layout 校验属于锁内首阶段，先于 reset/step；不设“必须在任何 native import 前取得真实 compiled proof”的循环门。一个成功 run 同一 Env 对 rows0/1/2 各 64 outer，2ms×25，共 192 transitions/195 observations/4800 mj_step；保留原 motion/reset/contact/On/T+1 门，额外语义端点单列。具体阈值、错误门、资源和所有权规则以冻结完整 prompt 为准。

全部门通过只报告 `R07C_DIAG_D01_PILOT_BOUNDED_S2_S3_PASS_PENDING_SOL_REVIEW`；只完成实现/S1时报告 PARTIAL 并列具体未过门。不得自授五任务 R07c、18/22 增量、P99、Human Judge、Formal Qualification 或 F 线集成接收。新诊断 attempt 没有固定次数上限，但每轮必须产出修复或可验证增量，完成报告后释放窗口，由 Sol 核实际 diff/Evidence 再决定下一包。
