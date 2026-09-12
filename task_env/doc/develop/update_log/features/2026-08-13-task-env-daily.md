# TaskEnv Daily — 2026-08-13

## 范围

收口 Go2 height-deploy 的 observation/reward/action contract、显式 yaw 指令、canonical asset、MuJoCo evaluator、runtime support 和 checkpoint 存储。

## 核心发现与数据

- height-deploy 保持独立的 **46D actor** 输入与 **49D privileged critic** 输入；deploy 的第三个 command 通道是显式 `wz`，不再使用隐藏 heading 状态。
- host/device reward、reset、action latency 和 TensorBoard reward-term 记录已形成对应测试；reward 变体、gait shaping、height target 等实验仍以当前 YAML/代码为准，不能用历史候选参数代替。
- canonical Go2 XML 的 SHA-256 为 `2014a3d76e30f17ab9447d8a67bd015291f74fa4d71ae30d005f1a32bd693d4b`；新旧 asset 存在 damping/friction 等动力学差异，checkpoint 必须记录 asset fingerprint。
- MuJoCo evaluator：viewer 运行到 137 tick 时 base X 为 **0.71025 m**；headless 1000 tick 时位移为 **4.84565 m**。该结果只说明 evaluator 可运行，不等价于 TaskEnv 训练收敛。
- 46D CUDA PPO smoke 的 actor/critic 输入分别为 46D/49D，reward 与训练统计 finite；定向 reward、RSL profile、reset 和 checkpoint 测试通过。

## 结论与边界

TaskEnv 已不再依赖测试目录的 `_support` 才能导入，通用 runtime helper 已内聚到 `task_env.utils`。canonical XML 与旧 checkpoint 的物理一致性、长 rollout、跨主机 asset 复现、render teardown 仍需独立验证；本日未据此宣称训练收敛或吞吐提升。
