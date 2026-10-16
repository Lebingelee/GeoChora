# P2.0-B S1 — Active reference construction

状态：implemented construction；S1.6当前默认变化见下文链接；需要 maintainer integration review，未重新授予 historical qualification。

S1 在 task owner 中提供 versioned construction API，仍使用现有 TaskArtifact v0。它不替换 `make_env` 默认路线，不删除历史实现，不执行 Go2/static retirement 或 v1.0.1 发布。

## PickCube

```python
from task_env.tasks.pick_cube.reference import build_reference, sample_reset
value = build_reference(backend="cpu")
sample = sample_reset(value["artifact"], 31)
```

`pickcube-p16-reference-construction-v1` 构造精确 `pick-cube-v1/p1_6_experimental_100hz` / `ver_p1_6_experimental_100hz`，Artifact SHA256 为 `fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4`。physics_dt=0.002s、5 substeps、100Hz control；不是 TB-100。

返回 artifact/source/controller/solution/readiness 与完整 `resolved_configuration`。P1.6 canonical semantics、PCG64 reset、readiness expert、ProductionCanonicalPandaController 保留。既有 `policy_search.timebase100.context(backend)` 转发构造并保留原六项 tuple 和错误文本；V2a policy 26D/no_qvel、h50/a36、absolute_joint 的原合同未修改。没有复制、加载或修改 frozen checkpoint。

## NutAssembly

```python
from task_env.tasks.nut_assembly.reference import (
    build_reference, OUTCOME_COMPLETION, GUARDED_EXPERT, DIAGNOSTIC_OBSERVATION,
)
value = build_reference(rate_hz=100, provider="mujoco",
                        execution_policy=OUTCOME_COMPLETION)
```

当前100Hz默认为 `nutassembly-r5-v5-outcome-reference-construction-v2` / `nutassembly-outcome-oriented-completion-v1`，精确合同见 [S1.6 outcome completion](p2_0_nutassembly_outcome_completion.md)。原 `nutassembly-r5-v5-guarded-reference-construction-v1` 保留显式50/100/500Hz历史兼容选择；三种 execution policy：

- `nutassembly-outcome-oriented-completion-v1`：S1.6在100Hz task-owned API中的默认；任务自身拥有具名warning准入、原计划推进和最终outcome，未使用diagnostic shadow。

- `nutassembly-guarded-expert-execution-v1`：S1时默认，现为显式历史兼容选择；严格 Expert gate、Lifecycle V2、原 guarded V2/V5 Solution 不变。
- `nutassembly-diagnostic-outcome-observation-v1`：必须显式选择；现有 diagnostic runner 可继续观测原计划，原 expert failure 保留，不能由此授予 FULL Expert PASS。

构造不创建 simulator/session，不执行 continuation。它返回selected V2/V5计划与所选completion Solution、R3/10N controller、native500Hz gripper support、arm-ramp memory、原 task semantics、execution policy 和 resolved receipt；caller 仍拥有 reset/step、arm-ramp installation、recording、shadow coordinator 与 close 生命周期。直接调用普通 session.step 并不能自动获得 native arm-ramp schedule。

完整配方从 tracked `nutassembly-nominal-v2.json` 与 `r5-controller-planner-reference.yaml` 明确解析，再施加已选定的10N、0.045895m grasp offset、V5 path、native500Hz/arm-ramp覆盖。基础profile中的 workspace dynamic-profile path不参与查找。source/config/profile/controller/solution/policy hashes 全部写入 `resolved_configuration`；在不同cwd并阻止workspace读取和native/diagnostic导入的fresh subprocess中验证。旧30N/R2 profile的字段不代表最终resolved R3/10N控制配置。

现有 `integration.lifecycle_full` 保留historical默认构造。显式新caller：

```bash
python -m task_env.diagnostics.phase1.integration.lifecycle_full \
  --construction-route task-owned \
  --trajectory-candidate guarded-primary-readiness-alternative-8n-v2-v5-clearance \
  --provider mujoco --rate 100 --output <new-evidence-directory>
```

Diagnostic observation还须显式 `--diagnostic-shadow-mode --acceptance-contract-id p1.8-nutassembly-cross-provider-acceptance-v2`。这是执行命令示例，不表示本次跑过完整轨迹；该diagnostic兼容选择不代表新outcome source获得历史qualification；当前source验收与未执行的物理replay须分列。新run在H5 recipe与sidecar记录真实construction factory/source identities及policy，旧Evidence不回写。

## Identity、验证与迁移边界

PickCube Artifact/controller/expert身份保持；Nut三率Artifact与显式历史选择的selected Solution identity保持（`15bfc3745c622ecb9eeb0b22248d2b12417ca3c40dbfd6b849ee06729b1dba2e`）；S1.6 outcome Solution与policy使用独立新身份。Nut执行support从diagnostic cadence抽出，controller construction identity和recipe identity明确更新，原physical profile、XML、task/controller behavior按独立pre-S1快照比较。旧hash只作migration来源，不把旧qualified状态复制给新source。

旧→新owner：

| 旧owner | S1 owner / compatibility |
|---|---|
| policy_search/timebase100.context | tasks/pick_cube/reference.build_reference；原tuple入口转发 |
| nominal/common → tracking_worker._context → stable_grasp → grasp_height_probe → frequency_grasp → lifecycle_full.context | tasks/nut_assembly/reference.build_reference；旧context链继续可调用，new route显式选择 |
| frequency_grasp/cadence.NativeRateGripperServo、stable_grasp.ExecutionController | tasks/nut_assembly/reference_execution；旧类继续保留；新source独立标识 |
| existing lifecycle_full / diagnostic_shadow runtime | owner未迁动；S1只增加构造选择与provenance |

provider-free固定快照检查保护Artifact、reset、source config/XML、controller physical profile、Solution identity；独立semantic fixtures与原lifecycle/guard/recording tests保护任务结果和Expert完成区别。最小native smoke只覆盖具名CPU reset/两步，不是FULL、D0/D1/D2或新qualification。

[原Outcome-Oriented Completion Policy proposal](proposals/nutassembly-outcome-completion-v1.md) 保留提案背景；S1.6已实施并版本化100Hz task-owned默认。复用现有Core lifecycle enum，独立policy identity和outcome字段见当前合同，不将新结果标为历史FULL。

S2前仍需：新source完整selected路径与record/replay验证；迁移公开plans/reporter及余下callers；抽出旧expert继承与yaw helper；移交Nut candidate MRO依赖；review API removal与删除清单。S1不提前删除这些实现。

## S2-A 调用者迁移（待审阅）

当前公开构造、录制/重执行和兼容移除边界见 [active task consumers](p2_0_active_task_consumers.md)。S1.6 evidence 的 source identity 保持冻结；新适配器须独立验收，不能继承历史资格。
