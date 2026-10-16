# TaskEnv diagnostics

## Static-template diagnostics

Stage A contact precision profiling, the Stage G precision gate, and the
Stage 18 static-template bridge benchmark are retired in the S4 local
candidate. Their modules are absent; historical reports and source remain
recoverable through the S4 retirement manifest and immutable Git refs. Stage 17
remains a task-UID-explicit `merged_scene` runtime profile; its
`--layout static_template` request fails explicitly.

## 目录约定

- `runtime/`：当前保留的统一 runtime 性能和边界诊断；静态模板专用历史模块按上文所述退休。
- `render/`：TaskEnv render backend contract、路径和实例化边界诊断；当前 smoke 不创建窗口、不加载 Flora native runtime。

Go2 oracle、checkpoint compatibility、RSL fingerprint 与旧训练探针已由 P2.0-B S3 从当前 develop 移除；需要历史复现时从不可变 `v1.0.0` 恢复。

Render backend contract smoke：

```text
PYTHONPATH=GeoPhys/src:. python -m task_env.diagnostics.render.backend_contract
```

生产 RSL-RL 只在 `task_env.alg.rsl_rl` 使用 current_5。旧 Go2 runner shim 与
checkpoint 转换已退休，不再作为当前诊断入口。

Stage 19/19d 与 Stage A–F 的其余阶段说明见对应历史记录；S4 不重写这些结果。

## Phase-I P1.1 contract detector

```text
python -m task_env.diagnostics.phase1.p1_1_contracts --output workspace/qualification/phase1/p1_1_contracts/smoke/p1_1_contracts/report.json
```

使用 TaskEnv 已配置 Python 环境。`phase1/` 的此 detector 只运行 S0/S1 strict schema、roundtrip、capability admission、CanonicalStateView 和 PickCube pure semantic fixtures。Fresh subprocess import guard 与 sys.modules 检查禁止四个 simulator/Taichi/Torch import，不构造 runtime。Manifest 为 synthetic fixture；这些结果不授予 provider 或 PickCube qualification。Report 绑定执行 commit、changed tree、command 与 candidate identity。
