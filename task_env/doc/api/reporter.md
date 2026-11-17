# Remote reporter

**Import path**：`task_env.reporter`
**任务域**：Remote inference boundary
**稳定性**：Public API

`ReporterSession` 在 Gym 边界执行严格的一帧闭环：`reset/step` 产出完整 raw observation tree 后发布 `ObservationPacket`；只有收到 identity、env metadata hash、action schema 和 `action_space` 都通过校验的 `ActionReply` 时，才调用一次 `env.step(action)`。没有 action 时不会步进，最近一次 reset/step packet 会一直保留。

`LoopbackReporterTransport` 用于同进程集成；`TcpReporterTransport` / `TcpReporterClient` 是一对长度前缀 TCP port adapter。连接中断时，调用方重新 `accept()` 后可调用 `ReporterSession.republish_latest()` 重发同一 identity 的最后 packet，期间不会步进。TCP wire 格式为 JSON 与 base64 ndarray，不做 action chunk、stack、flatten 或 safe action 处理；这些职责属于上游 runner/wrapper。

## 同进程接口检查

`ReporterSession(env, transport)` 要求环境提供 mapping `metadata`、reset/step 与 action space；`reset(seed=None, options=None)` 返回环境的 `(observation, info)` 并发布 packet。`step_if_action(timeout_s=None)` 最多消费一个 action；无 reply 返回 `None` 且不推进。`close()` 关闭 transport，环境本身由调用方关闭。这个可选协议适配器不拥有 provider 或环境的时钟；不使用 reporter 时普通 `make_env` 无需创建连接。

```python
from task_env.reporter import LoopbackReporterTransport, ReporterSession

class ExampleEnv:
    metadata = {'name': 'offline-example'}
    def reset(self, *, seed=None, options=None):
        return {'position': 0.0}, {}
    def close(self):
        pass

env = ExampleEnv()
transport = LoopbackReporterTransport()
session = ReporterSession(env, transport)
try:
    observation, info = session.reset(seed=19)
    packet = transport.take_observation()
    assert packet.kind == 'reset' and session.step_if_action() is None
    print(packet.transition_id, observation)
finally:
    session.close()
    env.close()
```

该例已在本轮受监督的无物理步骤脚本中执行，只检查内存队列空动作行为，不联网，也不证明真实 Task/provider 支持。未先 reset 调用 step 或 republish 会报 `RuntimeError`；身份、metadata hash 或 action schema 不匹配时拒绝该 reply，连接断开则按 transport 异常处理。TCP 和 v2 协议为显式选择，不能把 local queue 成功当成远端认证或交付成功。源码位置见 [session](../../reporter/session.py)、[loopback](../../reporter/loopback.py) 和 [contracts](../../reporter/contracts.py)。
