# P2.0-B S1.6 — NutAssembly outcome completion

状态：implemented / maintainer integration review required。仅100Hz、NA-S0 seed19、nominal V2/V5/R3 的具名 GeoPhys/MuJoCo CPU 验收；不授予历史P1.8 FULL或D0/D1/D2 qualification。v1.0.0与历史Evidence不变。

## 当前入口与所有权

`task_env.tasks.nut_assembly.reference.build_reference(rate_hz=100, provider=...)` 默认选择 `nutassembly-outcome-oriented-completion-v1`，construction ID=`nutassembly-r5-v5-outcome-reference-construction-v2`；Solution owner为 `NutAssemblyOutcomeSolutionV1`。任务的Artifact、canonical成功谓词、NA-S0 reset、nominal物理资产、V5计划、R3控制参数与原guarded授权保持。solution/controller/recipe/source身份重新记录，不继承历史qualification。

构造仍不创建native runtime。调用者按 `act → 执行且取得真实边界 → observe` 顺序执行，提供实际control_step/time、canonical observation/metrics、readiness和原2ms native authorization samples。Solution拥有唯一的stage推进、warning准入、实际动作回执及outcome完成判定。调用者仍拥有session、原native500Hz gripper/arm-ramp安装、记录和关闭。直接省略arm-ramp或native guard samples不构成等价路线。

现有 `integration.lifecycle_full` 的 `construction_route='task-owned'` 在非diagnostic模式下使用新默认Solution。它复用现有有界执行和记录适配器，但不会实例化DiagnosticShadowCoordinator，不设置general shadow override。historical runner默认route不变。`GUARDED_EXPERT`与`DIAGNOSTIC_OBSERVATION`作为显式历史兼容选择保留；50/500Hz只允许显式历史选择，新policy在其它频率拒绝构造。

## Warning准入

唯一allowlist为 `descend_to_handle / stable_height_mismatch`，每episode至多一次。先执行原0.10mm严格高度检查；不通过时保留achieved/expected高度、residual、原容差、位置/旋转误差、实测稳定窗口、samples、span/speed与原门控状态。仅同时满足以下条件才作为warning继续原计划：

- 该stage的全部authored动作已实际执行，当前clock、state、reward、readiness和native样本有限且有效，没有task failure、termination/truncation或预算耗尽。
- 原pose就绪界限7mm/0.06rad满足；原最小wait0.5s、窗口0.2s/至少20样本、每轴span≤0.10mm、相邻速度≤2mm/s均满足。
- 补偿后的高度residual绝对值≤0.30mm。原strict高度容差仍为0.10mm，此新版本仅改变该具名readiness失败的处理方式。

不满足任何一项仍失败；未知、其它stage或重复失败不准入。保留原close primary/alternative guard、2ms采样连续0.1s、1.5s deadline、0.1s授权后hold；不会强制close或lift。10N target/cap不变。capture在verify/transport/alignment/descent/lower的每个实测外层边界执行原8mm/0.15rad检查；控制器/joint/action限制保留。该外层检查不是完整substep安全证明。

## 完成与独立报告字段

`task_success`仍由现有canonical evaluator计算 `inserted_on_peg AND released_nut`，使用measured release和原retreat距离条件。Solution拒绝与canonical metrics不一致的success输入，不锁存早期成功作为最终结果。

`planned_trajectory_completed`要求11个原计划stage按序执行、每个authored action有真实observe回执、每个stage的原endpoint gate通过，包括完整release_retreat动作及稳定末端条件。stage entry或首次task success不足以完成。

`outcome_complete`要求当前task_success、完整计划及retreat、执行生命周期完成且无失败。invalid/nonfinite状态、clock错位、task failure、capture超限、运行错误、termination/truncation、预算耗尽、未知失败或未受控退出均不得产生完成。记录失败会使外层acceptance失败并撤销outcome_complete；H5 T+1边界和byte-exact存储roundtrip是native acceptance的独立条件。

报告分别记录 `task_success`、`planned_trajectory_completed`、`outcome_complete`、`readiness_warnings`、`original_expert_lifecycle_status`、新policy的execution lifecycle和逐stage动作回执。original状态是对本次实际严格gate的审计，不是假称并行重跑历史程序：发生warning时原严格gate仍对应failed、complete=false；新policy可以outcome_complete=true。没有warning且原全部gate通过时可记录原expert complete，但不授予历史FULL资格。

policy identity来自精确mapping digest；新Solution identity另绑定历史selected Solution身份与新源码digest；recipe还绑定完整config、controller/source/provider profile。checkpoint owner新增独立版本和完整outcome字段；存储roundtrip不等于D0 reconstruction，旧D0失败不改写。

## 集成和S2边界

S1、provenance修复与S1.6均为分开的reviewable changes；不自动合入develop。S2仍需迁移实际callers、拆解selected MRO与旧helper依赖、审阅具体删除manifest和public API兼容性。不能因为新route完成就批量删除旧task。Go2/static退休和Renderer interoperability不在此范围。单盘SATA风险与缺乏独立备份的限制保留。
