# Geochora Phase I 调试与恢复手册

> 状态：active Phase-I diagnostic/recovery playbook，v0.2
> 日期：2026-10-04
> 范围：规定 Phase-I 实施或资格验证反复失败时如何处理，特别针对 coding Agent 过度聚焦单个局部 hypothesis 的情况。
> 相关文档：05-phase-1-multi-simulator-blueprint.md、07-phase-1-smoke-testing-and-acceptance.md
> 权威关系：作为 Phase-I 实施计划采纳，从属于 [系统架构基准](../../global/00-system-architecture-anchor.md)、[仓库所有权](../../global/01-repository-ownership-and-boundaries.md) 与 canonical TaskEnv contract。active 表示文档用于指导实施，不表示 capability 已实现、测试通过、qualified 或任何子阶段已获准。

## 1. 目的

重复失败表明当前 hypothesis、边界、环境或 test oracle 可能错误。

Phase I 不得退化为：

~~~text
同一 failure
 -> patch 同一文件
 -> rerun
 -> 再 patch 同一文件
 -> 放宽 tolerance
 -> rerun
~~~

本手册要求在继续修改代码前进行更广泛的诊断。

## 2. Recovery trigger

发生以下任一情况时进入 recovery mode：

- 连续两次 localized fix 产生相同 failure signature；
- 已尝试三次实现，却没有新 diagnostic Evidence；
- failure 在每次 patch 后于相邻层之间移动；
- proposed fix 要求 Core/task code 读取 provider-private state；
- proposed fix 要求 generic provider adapter 包含 task-specific behavior；
- 为保持路线为 green，必须在缺少物理/语义依据时放宽 tolerance；
- 此前已资格化的无关路线开始失败；
- failure 是 intermittent，且无法绑定到 deterministic input/provenance record。

触发后，在 recovery record 建立前停止常规 patch。

## 3. Failure record

创建：

~~~text
workspace/qualification/phase1/<subphase>/failures/<failure_id>/
├── failure_report.md
├── hypotheses.yaml
├── reproduction.txt
├── logs/
└── artifacts/
~~~

failure_report.md 应包含：

~~~text
failure ID
首次观察到的 commit
当前 commit
provider/backend/version
Task Artifact / ResetSample / trajectory ID
精确 command
预期行为
观察到的行为
第一个 failing boundary
是否 deterministic
last known good revision
已尝试的 patch
已收集 Evidence
当前 hypothesis
alternative hypothesis
~~~

## 4. 强制诊断阶梯

下一次 fix 前，必须将 failure 归类到能够解释它的最早层级：

~~~text
0. repository / dependency / environment
1. Task Artifact / asset definition
2. capability admission
3. provider materialization
4. reset realization
5. timebase / scheduler
6. canonical state mapping
7. controller / action conversion
8. provider actuator realization / physics
9. camera/render observation
10. semantic evaluation
11. recorder/replay
12. learner/policy/runner
13. report/evidence
~~~

始终从最早的合理层级开始诊断。如果 upstream invariant 尚未检查，不得从最终可见 symptom 开始。

## 5. 常识检查

在第三次同方向尝试前，Codex 或人必须显式检查以下项目。

### 5.1 Repository 与环境

- branch 和 commit 正确；
- 是否存在意外 dirty file；
- editable checkout 与 stale installed package；
- PYTHONPATH 中重复 module；
- provider/submodule/version mismatch；
- Python/conda environment 错误；
- CPU/CUDA/Vulkan backend mismatch；
- device visibility；
- stale compiled cache、graph 或 generated artifact；
- import-order side effect。

### 5.2 Unit 与 ordering

- metre 与 millimetre；
- radian 与 degree；
- second 与 millisecond；
- quaternion wxyz 与 xyzw；
- right-handed 与 provider-native camera convention；
- joint order；
- actuator order；
- gripper sign/open-close convention；
- RGB HWC 与 CHW；
- float [0,1] 与 uint8 [0,255]；
- depth unit/sign/convention。

### 5.3 Asset/materialization

- mesh scale；
- collision geometry 与 visual geometry；
- missing inertial data；
- mass/inertia 错误；
- joint axis 或 limit 错误；
- base pose 错误；
- stale asset path/base directory；
- body/frame/site name mismatch；
- collision mask 被禁用；
- static/dynamic body flag mismatch。

### 5.4 Time 与 reset

- physics dt；
- control substep；
- action hold policy；
- observation 在 step 前还是后采样；
- hidden provider settle；
- reset 被 provider initialization 覆盖；
- seed 应用到 Geochora sampler 还是 provider RNG；
- episode horizon 或 early termination；
- simulation clock reset。

### 5.5 Control

- action clipping；
- target clipping；
- actuator limit；
- controller target 使用 requested state 还是 achieved state；
- pose reference frame；
- IK damping/gain；
- joint target 与 raw actuator control 混淆；
- gripper controller force/position semantics。

### 5.6 Contact

- contact 意外禁用；
- friction model/convention mismatch；
- restitution/compliance default；
- collision margin；
- solver iteration/stabilization 差异；
- contact 在不同 geometric configuration 开始；
- task semantics 消费 provider-native contact flag，而非 canonical Evidence。

### 5.7 Camera/render

- vertical 与 horizontal FOV；
- camera forward/up axis；
- mount frame 与 optical frame；
- intrinsic principal point convention；
- image origin；
- near/far clipping；
- render state 比 physics state 落后一 tick；
- depth 表示 ray distance 还是 camera-axis depth。

### 5.8 Recorder/data

- stale H5 schema；
- T 与 T+1 off-by-one；
- source action 与 canonical action 混淆；
- provenance 缺少 ResetSample；
- trajectory 使用不同 controller contract 转换；
- 旧 dataset/checkpoint 与新 Task Artifact hash 配对。

## 6. 独立 hypothesis 规则

第三次实施尝试前至少记录三个合理 hypothesis：

~~~text
H1：局部 code defect
H2：upstream contract/configuration defect
H3：provider/environment/test-oracle defect
~~~

至少一个 hypothesis 必须位于当前编辑 file/function 之外。

每个 hypothesis 都需要一个有区分力的 Experiment。有用的诊断应让至少一个 hypothesis 更可能或更不可能；另一次无法归因的长 full-task rollout 不够。

~~~yaml
hypotheses:
  - id: H1
    claim: canonical joint order is wrong in MuJoCo adapter
    test: one-joint impulse / target probe
  - id: H2
    claim: ResetSample base pose differs before first control tick
    test: compare realized initial state with zero stepping
  - id: H3
    claim: provider actuator defaults differ
    test: native provider minimal joint-hold probe using the same declared target
~~~

## 7. Known-good control path

每个困难 failure 都应至少对比一条 known-good control path：

~~~text
同一 Task Artifact，另一个已资格化 provider
同一 provider，更简单的 conformance probe
同一 controller，无 contact 的 free-space scene
同一 camera，static calibration scene
同一 dataset，用 state policy 替代 RGB policy
同一 recorder，synthetic transition fixture
~~~

如果简单 control path 失败，就不要继续调试完整任务。

## 8. 按 symptom 恢复

### 8.1 第一步之前失败

检查 capability admission、asset/reference resolution、provider construction、ResetSample validation、reset realization 与 controller/action schema。此时不要调查 long-horizon dynamics。

### 8.2 第一步强烈发散

检查 joint/actuator order、controller target、timebase、action clipping、initial state 与 provider actuator semantics。

### 8.3 Free-space 一致但 contact 发散

检查 collision geometry、contact enable/mask、friction/compliance、solver-native contact parameter 与 gripper/contact control。不能只因最终 object pose 不同就修改 world-frame 或 camera code。

### 8.4 C1 open-loop 失败但 C2 expert 成功

这可能是可接受的 numerical-dynamics gap。应确认声明的 C1 behavioral tolerance 是否过严，或 divergence 是否揭示真实 contract defect。

如果 tolerance contract 从未要求 pointwise trajectory equality，就不要强制它。

### 8.5 State policy 可迁移但 visuomotor 失败

优先检查 camera geometry、render timing、RGB normalization/layout、lighting/material/renderer domain gap。不要立即修改 physics parameter。

### 8.6 State 与 visuomotor policy 都跨 provider 失败

优先检查 reset distribution、observation semantics、controller target、timebase、physics/contact 与 dataset/action convention。

### 8.7 只有 replay 失败

检查 recorded action layer、controller version、ResetSample、timebase、trajectory transform provenance 与 H5 schema/version。

在证明 replay input 等价前，不得把 provider physics 标记为错误。

### 8.8 从 action 转换到 learned-policy portability 的 D0–D3 梯子

PickCube state-policy 问题按以下顺序定位，并为每一层保存独立、可哈希的 Evidence：

1. **D0 — target equivalence**：用记录的 canonical state/feedback 与重建的 public action 调用生产 controller，比较其 `CanonicalControlTarget` 与记录目标。
2. **D1 — exact-target replay**：从同一个 ResetSample 直接回放记录的 canonical targets，隔离 trajectory/control target 本身是否足以执行。
3. **D2 — transformed-action replay**：把重建的 public action 输入当前 replay state/feedback，经生产 controller 后再执行；这检查闭环 action-mode/controller 路线。
4. **D3 — learned-policy portability**：固定 checkpoint、feature/normalization/action contract 与配对 ResetSamples，在多个 provider 上运行 policy，并分别报告 contract/software portability 与任务结果。

D0–D2 通过不能替代 learned-policy task success；D3 的 seed 数有限时也不能推导 statistical robustness 或 provider-wide qualification。历史 Evidence 必须标记执行时 source provenance，包含 dirty working tree 的事实不能被事后改写。

## 9. Native-provider 诊断

必要时可以使用最小 direct provider script，判断 bug 位于 Geochora adapter 还是 provider。

规则：

- 它是 diagnostic Evidence，不是 production bypass；
- 必须使用 provider 公共 API；
- 任何结论都必须记录 provider version/config；
- 最终 Geochora 路线仍必须通过公共 provider adapter；
- 不得把 provider-private workaround 复制到 Core。

## 10. Rollback 与 redesign 标准

以下情况 rollback 到 last known-good revision：

- 无关已资格化路线 regression；
- patch 改变多个边界，导致无法归因；
- 重复 fix 需要越来越多 provider-specific exception；
- 公共 contract 比之前更不清晰；
- Evidence 表明初始 abstraction 错误。

以下情况提出 contract redesign：

- 两个或更多 provider 无法在不泄漏 task/provider-specific 内容时实现 contract；
- field 没有稳定的 provider-independent semantics；
- controller boundary 无法将 action meaning 与 provider realization 隔离；
- test oracle 测量 provider internal 而非 task/physical semantics；
- 同一 mismatch 在多个 task 重复出现。

Redesign proposal 必须说明：

~~~text
现有 contract
观察到的矛盾
受影响 provider/task
最小 revised contract
migration impact
需要的新 qualification
~~~

## 11. Tolerance-change 恢复

如果 failure 看似纯 numerical：

1. 确认 input 与 timebase 完全相同；
2. 确认被比较 quantity 具有 provider-independent meaning；
3. 运行 scale sweep 或 analytical check；
4. 在多个 fixed sample 上描述 error distribution；
5. 提出有物理/数值依据的新 tolerance；
6. 在 failure 与 acceptance report 中记录 change。

不能只因为当前实现不通过就放宽 tolerance。

## 12. Codex 防 tunnel vision 规则

如果 Codex 在 Phase-I 实施 handoff 中出现以下情况，应拒绝 handoff：

- 重复修改同一 subsystem，却不更新 failure hypothesis；
- 只报告最终 exception，而不是第一个 violated invariant；
- 忽略 branch/dependency/provider provenance；
- 假定最新 patch 必然更接近正确；
- 把 provider native representation 当作 Geochora contract；
- 为适配单个 provider 改变 task semantics；
- 明明 microprobe 可以隔离缺陷，却使用宽泛 full-task run；
- 仅根据 import、construction 或 visual appearance 宣布成功。

触发 recovery 后，Codex 必须明确说明：

~~~text
哪个 hypothesis 已被否定
正在测试什么新 hypothesis
当前认为哪个 boundary 最先失败
哪个最小测试可以区分 alternative
~~~

## 13. Escalation 所有权

修复前先对确认的 defect 分类：

~~~text
Task-local defect：
    Task Artifact

共享 contract/lifecycle defect：
    Geochora Core

Provider implementation defect：
    provider adapter 或 provider project

Learner/policy integration defect：
    Geochora learner adapter / 外部 learner project

Agent workflow/retry issue：
    外部 Agent/PhysPi，不属于 Phase-I Core
~~~

不能用 Core patch 隐藏 provider defect，也不能用 Task Artifact workaround 隐藏 Core contract defect。

## 14. Recovery 完成标准

只有满足以下条件才能结束 recovery mode：

- 已通过 Evidence 识别 first-failing layer；
- 已有 minimal reproducer；
- 选择的 fix 处理该层；
- 相关 targeted smoke 通过；
- 相邻 known-good control path 仍为 green；
- failure record 已更新结论。

之后仅在 fix 影响所声明 envelope 时，才重新运行昂贵 subphase qualification。
