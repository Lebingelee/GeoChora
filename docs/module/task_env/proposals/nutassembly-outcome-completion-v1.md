# Proposal — NutAssembly outcome-oriented completion v1

Proposal ID：`nutassembly-outcome-oriented-completion-v1-draft`。
状态：**PROPOSED / REVIEW REQUIRED / NOT IMPLEMENTED / NOT DEFAULT**。

本提案面向 maintainer 以已完成计划和最终物理任务结果选择活动开发实现的要求。它不是历史 Expert FULL gate 的修订，也不修改既有 TaskArtifact/Experiment、D0失败或资格决定。S1只交付本提案；现有ON_TASK_SUCCESS与ON_EXPERT_TERMINAL_STAGE均不改。

## 拟议完成条件

一个具有新policy identity的执行，可报告 `outcome_completed=true`，仅当：

1. 具有明确task/controller/asset/source/config/provider/rate/seed身份，实际执行有效，状态有限，时钟与记录边界一致，没有runtime error。
2. 已执行声明的完整计划阶段，完成原末端release/retreat动作及其endpoint检查，而非只进入stage或在首次task_success时提前停止。
3. 最终实测canonical `inserted_on_peg AND released_nut` 为真；不使用commanded-open代替measured release，不降低几何/force/capture参数。中间success不锁存为最终success。
4. 继续执行的每一个未通过readiness gate都有policy明确准入和原始事件。候选白名单可审阅 `stable_height_mismatch` 的诊断继续证据；是否准入其他原因待maintainer决定。环境termination/truncation、runtime error、action budget耗尽不作为可继续成功。

如果完成上述条件但原Expert gate失败：`outcome_completed=true` 可以与 `expert_failed=true`、`expert_complete=false` 并存。不能把这个组合转换为FULL_EXPERT_PASS。

## 拟议结果字段与判定

使用既有Evidence/report扩展字段，不建立第二个TaskArtifact schema。至少分列：`physical_task_success_final`、`planned_sequence_complete`、`outcome_completed`、`expert_complete`、`expert_failed`、`diagnostic_continuation_used`、`replay_execution_valid`、`d0_exact_reconstruction`、`formal_qualification_status`，以及原gate失败清单和source identities。

Policy identity拟由版本、准入原因白名单、完整阶段/endpoint合同、最终task predicate和失败规则的mapping digest确定。若改变task semantics或frozen task identity，必须产生新TaskArtifact版本；只新增completion policy也需新execution/source身份和bounded acceptance。历史D0 transition157失败不要求改成PASS。

## 未来bounded acceptance（本轮未执行）

先验证无首次成功提前退出、最终success丢失、遗漏retreat、环境终止、runtime错误、无授权继续原因等negative fixtures，再在已声明50/100/500Hz与具名provider/config上分批运行完整轨迹及record/replay。分别报告真实物理结果、执行有效性与exact reconstruction；不得将不同source/配置拼成单一PASS。

Maintainer需审阅：继续原因白名单、是否以完整retreat作为必需条件、报告字段及新bounded decision、是否将该policy作为未来默认。批准本提案前，S1 guarded expert继续使用原严格gate；diagnostic observation保持显式diagnostic标签。
