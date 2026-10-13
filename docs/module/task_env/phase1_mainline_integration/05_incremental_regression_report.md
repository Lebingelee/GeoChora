# 增量回归

本轮执行 10 组低成本检查，复用 12 组历史检查。实际新增 21 个 pytest case 全部 PASS。没有重新训练，也没有运行新的 provider episode、T1、Full NutAssembly 或正式 P1.8 D0–D2。

| 当前整合源码检查 | 结果 |
|---|---|
| 五个 Flow unit-test files | 21/21 PASS：quantile compatibility、obs normalization、horizon windows、U-Net shape/gradient、long-profile guards |
| P1.1 S0/S1 detector | 30 项 PASS；无 simulator construction |
| V2a checkpoint/config/normalizer load | SHA 匹配；CPU 输出 [1,50,8] finite；冻结 config identity 匹配 |
| Provider/module imports | GeoPhys/MuJoCo/SAPIEN/Genesis session 模块及 R3/v2/新旧 Flow 入口均 import |
| Default PickCube / experimental 100Hz Artifact | historical 461d2f08… / fd5bc968… exact |
| Synthetic owner/interval/readiness checks | 12204 次正向比对、9 个负向拒绝 case PASS；v0 T+1 roundtrip PASS |
| Real recorded MuJoCo TB100 canonical reconstruction | 9 checkpoint × 12 boundaries exact；无真实 physics replay |
| Real recorded GeoPhys TB100 canonical reconstruction | 9 checkpoint × 12 boundaries exact；无 native physical-resume claim |
| Compileall / diff check | PASS |
| Relative docs links / new blob hygiene | 发布前校验结果记录在 publication_gate.json |

物理和 qualification reuse 依赖字节对照与原始证据，而非新的 success 声明。147 个 P1.8 protected source files 保持起始 integration 字节；7 个 P1.6 learner files 保持 closure branch 字节。历史批准保存为原范围，当前检查只证明整合兼容性。

实际执行入口：

```bash
python -m pytest -q task_env/diagnostics/phase1/test_flow_normalization_variant.py task_env/diagnostics/phase1/test_flow_horizon_chunks.py task_env/diagnostics/phase1/policy_search/test_conditional_unet_horizon_padding.py task_env/diagnostics/phase1/policy_search/test_flow_window_profiles.py task_env/diagnostics/phase1/policy_search/test_long_training_flow_profiles.py
python -m task_env.diagnostics.phase1.p1_1_contracts --output <new-evidence-directory>
python -m task_env.diagnostics.phase1.integration.readiness_synthetic --output <new-evidence-directory>
python -m task_env.diagnostics.phase1.integration.checkpoint_validation --provider <geophys|mujoco> --rate 100 --input <existing-execution.h5> --output <new-result.json>
python -m compileall -q task_env/alg/agent_factory task_env/diagnostics/phase1/policy_search
```

checkpoint/import smoke 与完整 stdout、JUnit XML、source hashes、archive checks 保存在本地 `workspace/qualification/phase1/phase1_mainline_integration/20261013/`。未出现行为差异；GeoPhys native contact-checkpoint bitwise resume 仍不属于已证明能力。
