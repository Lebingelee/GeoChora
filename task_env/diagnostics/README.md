# TaskEnv diagnostics

## Stage G contact precision gate

```text
PYTHONPATH=GeoPhys/src:. python -m task_env.diagnostics.runtime.stage_g_contact_precision --backend cuda --batches 1 2 17 32 --checkpoints 10 100 1000 --output temp_outputs/task_env/go2_contact_precision/parity.json
```

三会话性能准入门禁消费按参数位置配对的三份 f64 baseline 与三份 f32 candidate
Stage A idle CUDA 报告：

```text
PYTHONPATH=GeoPhys/src:. python -m task_env.diagnostics.runtime.stage_g_contact_precision_gate --baseline-inputs baseline-1.json baseline-2.json baseline-3.json --candidate-inputs candidate-1.json candidate-2.json candidate-3.json --output temp_outputs/task_env/go2_contact_precision/performance-gate.json
```

每份输入必须恰含 B=32/1024/4096，且满足 warmup、采样数和 GPU 空闲证明。
门禁同时检查 B=4096 的 100 ms mean / 110 ms P95 绝对上限，以及每对 batch
的 1.05x mean / 1.10x P95 回滚上限；验证失败和性能失败都会保留 JSON 报告并返回 1。

这些脚本只用于开发者验证，不属于用户训练 API，也不参与 `task_env` 核心 import。

## 目录约定

- `go2/`：Go2 的跨引擎 oracle、reward/checkpoint contract、RSL-RL fingerprint 和 legacy 探针。
- `runtime/`：统一 runtime 的性能、数值 parity、workspace、CUDA Graph 和 Taichi/Torch 边界诊断。
- `render/`：TaskEnv render backend contract、路径和实例化边界诊断；当前 smoke 不创建窗口、不加载 Flora native runtime。

Render backend contract smoke：

```text
PYTHONPATH=GeoPhys/src:. python -m task_env.diagnostics.render.backend_contract
```

生产 RSL-RL 只在 `task_env.alg.rsl_rl` 使用 current_5；legacy runner shim 和
legacy/current checkpoint 转换必须从 `diagnostics/go2` 启动，避免兼容分支进入 PPO 热路径。

Stage 17/18/19/19d 与 Stage A–F 是有报告和 smoke 覆盖的 runtime 证据链；运行命令见
`task_env/README.md` 和对应 `doc/task_env/update_log/features/`。
