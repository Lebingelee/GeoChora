# Remote reporter

**Import path**：`task_env.reporter`
**任务域**：Remote inference boundary
**稳定性**：Public API

`ReporterSession` 在 Gym 边界执行严格的一帧闭环：`reset/step` 产出完整 raw observation tree 后发布 `ObservationPacket`；只有收到 identity、env metadata hash、action schema 和 `action_space` 都通过校验的 `ActionReply` 时，才调用一次 `env.step(action)`。没有 action 时不会步进，最近一次 reset/step packet 会一直保留。

`LoopbackReporterTransport` 用于同进程集成；`TcpReporterTransport` / `TcpReporterClient` 是一对长度前缀 TCP port adapter。连接中断时，调用方重新 `accept()` 后可调用 `ReporterSession.republish_latest()` 重发同一 identity 的最后 packet，期间不会步进。TCP wire 格式为 JSON 与 base64 ndarray，不做 action chunk、stack、flatten 或 safe action 处理；这些职责属于上游 runner/wrapper。
