# TaskEnv 调试与恢复

## 进入 recovery

相同 signature 经两次局部修复仍失败、三次尝试无新 Evidence、失败在相邻层漂移、
需访问 provider-private state/给 generic adapter 加 task behavior、无依据放宽 tolerance、
无关既有路线 regression 或 intermittent failure 无法绑定 deterministic inputs 时，停止常规 patch。
先写 ignored workspace 下 failure_report、hypotheses、reproduction、logs/artifacts，再继续修复。

记录 first/current commit、branch/dirty paths、provider/backend/version、Artifact/ResetSample/trajectory
identity、精确 command、expected/actual、first failing boundary、determinism、last known good、
已尝试 patch、Evidence 与 alternative hypotheses。只报最终 exception 不足。

## 从最早失败边界定位

```text
repository/dependencies -> Artifact/assets -> admission -> materialization -> reset realization
-> clock/timebase -> state mapping -> controller/action -> actuator/physics
-> camera/render -> semantics -> recorder/replay -> learner/runner -> report/Evidence
```

第三次同方向尝试前必须记录至少三个可区分 hypothesis：局部 defect、upstream contract/config、
provider/environment/oracle；至少一个位于当前编辑文件外，并给每个 hypothesis 一个最小区分实验。
与 known-good control 比较：更小 conformance、free-space controller、static camera、state policy、
synthetic recorder 或同 Artifact 的已验证 provider。小 control 失败时不要继续 full-task 调参。

| 现象 | 先检查 |
| --- | --- |
| import/构造失败 | Python/conda、PYTHONPATH 重复/stale package、Gitlinks、UID/config 分支、admission/profile |
| 第一步前失败 | asset/name/reference、ResetSample/realized reset、controller/action schema |
| 一步发散 | SI/rad/seconds、quaternion wxyz、joint/actuator order、sign、clipping、timebase、初态 |
| free-space 好、contact 差 | collision/visual geometry、scale/inertia、masks、friction/compliance、solver iterations/gain、force control |
| state policy 好、RGB 差 | K/FOV、mount/optical frames、image origin、HWC/CHW、uint8/float、depth convention、render tick、lighting domain gap |
| state/RGB 均差 | reset distributions、obs semantics、controller、timebase、contact、dataset/action convention |
| replay 独失败 | action layer、controller/version、ResetSample、schema、transform provenance、T/T+1；未证输入等价前不怪 physics |

同时排查 backend/device visibility、cache/graph、import order、asset base path、body/site names、
static/dynamic flags、hidden settle、seed owner、horizon/early stop、clock reset、requested/achieved target。
C1 open-loop 失败但 C2 expert 成功可能是 dynamics gap；只按已声明 behavioral tolerance 判断，
不能强加 contract 从未要求的 pointwise equality。

## 恢复、回退与升级

按 D0 target reconstruction → D1 frozen controls → D2 frozen action/live recomputation → D3 fixed-policy
paired evaluation 逐层保存可哈希 Evidence；各层含义见[recording](recording-and-learning.md#回放与离线验证)。
通过低层不替代 policy task outcome，有限 seeds 不证明 provider-wide robustness。
可用 public native-provider 最小脚本诊断 adapter/provider 归因；它不是 production bypass，
结论记录 provider/version/config，最终路线仍须经过公共 adapter。

无关 regression、多边界难归因、越来越多 provider exceptions、contract 更不清楚或 abstraction 被
Evidence 推翻时回退到 known good。多个 provider 无法遵守独立语义、同 mismatch 跨任务重复或
oracle 测 native internals 时提出 redesign，写明原 contract、矛盾、受影响交集、最小修订、migration
与新 qualification，不能以 task workaround 掩盖 Core defect。

纯 numerical failure 先确认输入/timebase/quantity 同义，运行 scale sweep/analytical check，
描述 fixed samples error distribution，再论证 tolerance；不能为当前实现变绿而放宽。
Owner 分类遵循[ownership](../../global/ownership.md)：task-local、shared Core、provider、learner、Agent workflow。

恢复结束须有 first-failing layer 的 Evidence、minimal reproducer、针对该层的 fix、targeted smoke
通过、相邻 known-good 仍通过以及更新后的 failure record。报告已否定的 hypothesis、新 hypothesis、
first violated invariant 与区分实验；仅影响 declared envelope 时重跑昂贵 qualification。

## 已复现的 CLI 缺陷

2026-10-18 在当前发布 source/Python 3.12.14/GeoPhys CPU 环境执行：

```bash
PYTHONPATH=GeoPhys/src:. python -m task_env.script.env.single_inline --env-id pendulum-v1 --backend cpu --steps 1
```

construct/reset 后，`task_env/script/env/_common.py` 的 `run_single` 在选择 step 路由时
读取 `env.binding.external_actions`；通用 `PendulumEnv` 没有 binding，抛 AttributeError。
CLI `--help` 成功不验证这一执行路径。此为已存在的 implementation defect，不是退休 UID
或 provider admission 失败；本次文档工作不修实现。直接公共 `make_env/reset/step/close`
路线已完成 CPU 一步 smoke，见模块 README。future fix 应修复既有 helper 并添加缺陷敏感检测，
不另建 task factory/runtime；实现需另行授权。
