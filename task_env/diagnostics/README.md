# TaskEnv diagnostics

## 当前诊断开发规范

遵循[诊断开发与核心代码边界规范](../../docs/global/diagnostics-and-code-boundaries.md)。规则覆盖Env、Controller、provider／render adapter、recorder和普通函数。优先从正常接口取得输入输出；需要干预时在本目录使用包装、诊断子类／重写或局部fixture，不往核心增加实验profile、测试识别或专用probe分支。

动工顺序是：核实参考闭环→定位实际owner与相关差异→选择外部观察／干预方式→控制变量对照→将确认的缺陷修回正式owner。可复用入口与短说明放本目录的对应topic；本次临时脚本、图表和数据放ignored workspace。正式feedback、fault、T+1和来源校验保留，合成结果与物理结果分开说明。

历史路径中已有的诊断耦合不因本规范自动变为合规，本轮不立即迁移；按[v2.1.1收尾安排](../../docs/module/task_env/v2.1.1/planning/pre-stage3-environment-refactor.md#diagnostic-policy-and-final-cleanup)登记并在版本集成前集中分类处理。下文保留现有入口及历史说明，不表示所有模块已完成解耦。

## v2.1.1 current diagnostic selection

See the [v2.1.1 claim and input map](tasks/v2.1.1/README.md) for the guarded
pure/fake entry, offline historical records, and explicit source/native limits.
The inventory is still in progress; unlisted nodes are not automatically pure.

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
