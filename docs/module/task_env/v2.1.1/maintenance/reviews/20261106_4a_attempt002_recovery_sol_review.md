# G04 4a attempt002 续作：Sol 独立主审

## 决定与范围

决定 `REWORK_REQUIRED_4A`：**4a 整体不接收**，普通 attempt count 保持 2，4b／4c 不自动启动。维护者要求先执行 attempt002 授权续作，若仍不接收再讨论 003；因此本次不准备或派发 003，不因实施会话的 Goal complete 倒填 4a 接收。

本次可以有界保留的成果：Core 既有公开入口在 source `aa4ca97bbe3c61b30752ba0dedc6c88a24394f03fe1b53519052d460ff9abc47` 和 MuJoCo 3.8.1 CPU 下，对指定 A05 候选实现命名映射、单／双 Controller 合批和 joint effort 及 hand wrench 的写入 ACK；受检的 source、fake 和纯契约测试也可复用。这是**构造、准入、提交及 ACK 的证据**，不是实测力或 4b 物理效果。position drive 保留；其他 provider 和 PickCube physical 均未接收。真实 body wrench 在整个区间的实现有下述缺陷，不将其能力判为完整可用。

## 原始结果与独立核对

- 续作输入 `53ca8deeaf69e139876b08d2b00caa3ecabcdea0`，执行输出 `cfb006f44ee761ae29e248def249d405d5498216`，实现提交 `5ff5a025`、`cfb006f4`；分支 `codex/v211-stage4`。GeoPhys 与 Menagerie 分别保持 `dc2685e28c6c916fb6403a2342c04e0d2520aef7`、`b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`；三项保护 untracked SHA 与冻结包一致。
- 独立重算输出 manifest **530/530** 成员 SHA，全部相符；执行者报告的 writer／双锁释放与无残留进程 receipt 存在。7 次原生运行合计 35 子步，原始证据限 A05/MuJoCo CPU，不能把 ACK 归为实测。耗时和资源 unknown 保持报告原样。
- Sol 未运行 SDK、source 解析、provider 或 native；以既有 `sitecustomize.py` 禁止 SDK 导入和 XML 解析，独立重跑 4 项受影响 pure/fake 检查，4 passed。额外执行下列纯 fake 区间检查。执行者报告的 CodeGraph 再次带出无关私有片段保留为边界事件；Sol 的定点 CodeGraph 响应也误匹配 GeoPhys 内容，已在输出前过滤，未查看、使用或记录私有片段。
- 执行者完整 [报告](../../../../../../workspace/maintenance/v211_g04_4a_attempt002_recovery/report.md)、[分层案例](../../../../../../workspace/maintenance/v211_g04_4a_attempt002_recovery/case-matrix.md)、[4b 计划](../../../../../../workspace/maintenance/v211_g04_4a_attempt002_recovery/4b-plan.md)、[原始输出清单](../../../../../../workspace/maintenance/v211_g04_4a_attempt002_recovery/output-manifest.json) 不覆盖。原 001 源解析越界、002 私有片段误输出、原 N08 失败及 6.1 close timeout 均保留。

## 不接收原因：已声明的 BodyWrench 区间语义不成立

[MuJoCoPhysicalPort.write](../../../../../../task_env/runtime/sessions/mujoco_physical.py) 将边界快照上解析的 wrench 经 `mj_applyFT` **只投影一次**到 `values`，保存在 `pending_values`；[session step](../../../../../../task_env/runtime/sessions/mujoco.py) 在后续各 physics substep 不随姿态更新 Jacobian、作用点或 frame，而是重复写入这组初始 generalized force。该 port 同时在 [assessment](../../../../../../task_env/runtime/sessions/mujoco_physical.py) 声称 body force／offset／frame 和 hold-reapply 已实现。关节姿态发生变化时，相同 `qfrc` 一般不再对应相同的 BodyWrench；对于 body-local frame／作用点，还需要明确并实现所声明的随体语义。区间结束清零和不重复累加两点成立，但不能因此证明持续外力在整个 interval 内正确。

独立纯 fake 检查直接调用现有 `_MuJoCoSession.step`：一个简化转动关节的 body-local 作用点为 `(1,0)`，world 力为 `(0,1)`；姿态由 0 变为 π/2 时，同一持续世界力对应的 generalized torque 应由 `1` 变为 `0`，实际 session 循环写入 `[1,1]`。仅有 fake 引擎、无 native 或真实轨迹；它验证 session 循环对时变投影的处理，而不是预测 Panda 的运动。复现源码与输出保存在 ignored `workspace/maintenance/v211_g04_4a_attempt002_recovery_sol_review/{wrench_substep_probe.py,wrench_substep_probe.log}`，分别 SHA-256 `af1b03bdc7a119a322e5cf84c3f73ff5ebbb7056856e20911ac8d21a453b8790`、`898f799e9113c087bd0cebc3fd2a2252beb8bcb54067c54ce960975c14495b53`。

原 4a 明确要求 BodyWrench 的 frame、point、duration、capability 和 hold/reapply 边界，不是只要求一个可写 ACK；本问题属于已暴露生产能力的语义错误，不用 4b 物理实验尚未执行来推定，也不是要求在 4a 提前通过 4b 三后端矩阵。修复可以在既有 session owner 逐子步根据声明重新解析并投影，或以明确能力拒绝不能正确兑现的语义；不得将固定关节力重新命名为持续外力，也不能只修改文档。无论选何路线都须保持一次贡献、frame/point/reference 正确、失败清理和 source 身份。

## 4b 计划与后续

续作计划比 002 版本更具体：提出三个 route、source/owner、7＋2 和八个基向量、独立自由体及 hand、固定候选 oracle、前置拒绝和 41 build／345 测量子步的预算。它是可复用的**候选计划**，不是批准运行或已验证的物理真值。尤其其 MuJoCo 手部力和无接触自由体在持续阶段依赖正确的逐子步力语义；当前缺陷必须先处理。软约束 `mj_forward` 对照与实际 writer 共享引擎数值实现，适合检查写入／映射，不是独立跨引擎物理真值。各 provider 公开只读模型、力输入、场景接线和条件阈值仍待 4b 工作包逐项确认；不提前运行三后端或 4c。

维护者可先讨论是否使用普通 attempt003；此前的[第三次前重评](20261106_4a_attempt002_sol_reassessment.md)仍有效，但需将这次新增的具体缺陷、精确修复选择、受影响测试及端到端 4a 出口补入最后窗口安排。不得重跑不受影响的历史矩阵，也不得把新物理验证范围悄悄扩大成 4a 前置。

## 补充澄清：原 4a 与 4b 的边界

维护者要求重新对照原开发需求。Sol 澄清：原 4a 要求 BodyWrench typed 契约、准确 capability／拒绝和映射边界，以及可执行的 4b 计划；**原 4a 并未要求所有后端的持续外力物理实现及实测通过**。上次总结把问题表述为“持续 BodyWrench 必须解决”容易使人误解为完整物理实现就是原 4a 硬门，这是 Sol 的表述不够准确。当前阻止整体接收的是实际启用的候选路线**声称支持了不能按一般声明保证的语义**，不是仅因为 4b 的真实外力尚未完成。

4a 的合理收口存在两条路线：其一，修好本候选被声明支持的持续语义，并做受影响的有界验证；其二，真正关闭／拒绝该范围的生产准入，修正 capability 和文档、通过针对性拒绝测试，将真实实现与物理验证明确留给 4b。第二条不能仅改文字或删掉 typed BodyWrench 和原 4b 计划，也不把已发生的 ACK／短跑改写成更强证据。两条都须核对 4a 其他原出口及已冻结续作约定，最终接收由 Sol 看实际提交和证据决定；现有代码尚未满足其中任一路线，当前决定不变。推荐优先评估第一条，因为 4b 确实需要真实外力；如果它不能在合理边界内完成，第二条是符合原阶段分工的可选方案，而不是必须反复尝试物理实验。

实现方案需要明确 world／body frame 和作用点的持续意义、每个 substep 使用当前构型而不是上一步陈旧派生数据、与 joint effort 一次组合及 buffer 的异常／reset 清理。MuJoCo 3.8.1 的[上游实现](https://github.com/google-deepmind/mujoco/blob/3.8.1/src/engine/engine_support.c)显示 `mj_applyFT` 基于当时 Jacobian 累加投影；调用策略需验证对应积分器和状态更新次序，不能只在旧代码位置重复调用。以上是修复方向，尚未形成或派发 attempt003。

维护者进一步询问关节外力、MuJoCo 鼠标拖拽、其他后端和其他阻塞风险；完整核对及 A05/4b 手部作用点参考差异见[跨后端补充](20261106_4a_wrench_cross_backend_followup.md)。
