# TaskEnv Daily — 2026-08-14

## 范围

整理 Go2 独立 reward/control 实验、课程域随机化、deploy 指令语义、MuJoCo-Warp GPU render、hard-render 预算和 legacy PPO CLI。

## 核心数据

### Reward screening

| variant | collection median | mean reward | episode length |
|---|---:|---:|---:|
| C0 | 1.3118 s | 17.5484 | 853.4 |
| C2a | 1.3415 s | 28.5335 | 644.7 |
| C2b | 1.3509 s | 32.0595 | 733.1 |

C2b 的 held-out 结果中 gravity XY norm 为 **0.01704**、roll_abs **0.01252**、pitch_abs **0.00881**，姿态稳定性优于 C2a，但 forward velocity 仍接近零，不能宣称已经完成前向 tracking 或部署 height 目标。

### Curriculum / command

- 课程配置使用 `start_fraction=0.10`、`end_fraction=0.70`；friction/base mass 逐步扩大，push 在终点启用；默认配置未切换，必须显式使用 curriculum YAML。
- deploy 第三个 command 通道固定为显式 yaw-rate `wz`，不再使用隐藏 heading；Stage A/B/C 测试合计 **17 passed**。

### Render / legacy

- MuJoCo-Warp GPU render 支持 8192 个 world；`8192 × 24` collection time 为 **2.695 s**。
- hard-render 的 16 asset world CUDA smoke 通过；128 asset 在 1080×720 下预算估计 **16.94 GiB**、超过当前约 **5.14 GiB**，安全拒绝；bypass 后真实 allocation 在 **7.62–7.72 GiB** 触发 OOM。
- legacy Unitree PPO CLI 的 4096 env、1 iteration smoke 通过，collection **1.017 s**；render 模式仍需要图形会话，未作为 TaskEnv 默认入口。

## 结论与边界

课程随机化和 reward variant 仍是 opt-in 实验；render 预算是显式 fail-closed，不自动缩小请求规模。GPU render 的图像 readback/拼接与 physics frequency 分离，所有长训收敛和高分辨率 256-world 验收仍需单独记录。
