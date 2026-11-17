# 7b 当前 BodyWrench 准入缺口：供 Sol 讨论

此项未实施扩展，维护者将与 Sol 确定方案。它是 7b 其他独立门之外的未完成项；不能由九格成功、task COM 力回执或历史源码结论代替。

## 需要保持的原目标

G04/4b 原有界目标包括 MuJoCo 上真实 Robot hand／自由体 BodyWrench、坐标和偏置力矩、joint effort 与外力有意组合、持续载荷的 clear/reapply、typed 准入与 native 回执。原独立接收只覆盖特定 source／route，不要求三后端 BodyWrench 或所有组合。7b 要求先复用输入匹配的旧证据；当前公共控制与 source 绑定在原接收后发生变化，旧真实结果与数学函数未变的静态对照不能单独证明当前链路。

## 当前可复现事实

- `panda-v1` 正式 PickCube MuJoCo source 的 `panda-v1/hand → hand` 映射真实存在。当前受控主体的 writer 仅为 `panda-direct-effort`，支持的选择是五种 Panda effort profile；现有 binding 中无 body-wrench binding。见 `workspace/maintenance/v211_g07b_attempt001/wrench-admission/admission.json`。
- 将真实 hand 身份、frame、source closure 和 body owner 编译进 binding 可以成功；保留原 Panda subject、`panda-direct-effort-v1` 选择，重建原 effort Controller 并加入现有 `WrenchControllerV1` 后，`PhysicalControlExecutionV1` 因后者没有同一 selection profile 而在任何物理推进前拒绝。`wrench-combination/combination.json` 记录 binding_compiled=true、0 子步、原错误和 close 成功。
- 原构建入口 `build_existing_subject_effort` 经 `build_declared_effort_execution` 要求单 subject／单 writer，并最终绑定选中 profile；`PhysicalControlExecutionV1.__post_init__` 同时检查每个 Controller 的 profile 与每个 subject 的支持声明。`WrenchControllerV1` 的 typed profile 声明 body、表达坐标、作用点和力矩参考，但当前并未声明该选中组合的 authority。相关代码分别在 `task_env/runtime/sessions/physical_control.py` 和 `task_env/controllers/canonical/physical_controller.py`。
- 当前另有 MuJoCo effort 加 task COM +2 N 的 5 子步 native ACK 与 close（`effort-wrench-impact-002`），但这是另一类载荷；它不是 `BodyWrenchV1` 手部作用点／力矩回执，也不证明 hold/reapply/clear。当前 7＋2 typed effort 和 ACK 的三个切换段独立对账亦不能替代 BodyWrench。

## 请 Sol 决定的边界

需要明确谁拥有真实 body writer／subject 权限，以及组合 selection 如何在 source、场景 body、Controller、绑定与唯一提交之间表达和核对；还需决定采用原公共 Runtime 的哪个合法入口，如何维持单位、frame、时钟、冲突、载荷生命周期及 reset/close。不能通过清空原 subject、把 selection 置空、给 Controller 临时伪加 profile／channels、删除一致性 guard 或直接旁路 session 提交来制造通过。现有两 Controller 的 fake 测试不是 native 可用路线。

若决定实施，建议先冻结具体受限路线及其 owner，测试真实绑定与拒绝外部 writer／错误 body/profile，再用同运行 MuJoCo 独立 oracle 验证 hand 与自由体的方向／偏置力矩、effort＋wrench 唯一提交、逐步 hold/reapply/clear、实际响应、ACK 和 close；列清不要求的 provider／组合。若改变会影响最终九格使用的公共源码，按实际依赖重新冻结并复验受影响运行，不能把跨输入结果拼成通过。是否采用这一设计及其扩展范围由维护者与 Sol 决定，此文不预设授权。

证据与此前纠正见同目录 `20261117_g07b_attempt001_execution.md`、ignored 输出根的 `reuse-and-impact.md`，以及工作包目录 `clarification004-bodywrench-runtime-evidence.md` 和 `clarification006-bodywrench-admission-gap.md`。原 4b 独立接收见 `20261106_4b_attempt002_sol_review.md`。
