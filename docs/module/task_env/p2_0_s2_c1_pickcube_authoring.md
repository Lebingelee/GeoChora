# GeoChora P2.0-B — S2-B2 Integration and S2-C1 PickCube Authoring Receipt

日期：2026-10-16
状态：S2-B2 已集成到 public `develop`；S2-C1 PickCube task-authoring 与 NutAssembly 共享 binding 的有界双 provider 功能验收已完成。S2-C1 仍处于本地审阅/集成流程；没有发布 v1.0.1。

## S2-B2 public integration

S2-B2 的执行提交 `84438d470cce4f5a215a5934fdfc344b91adca30` 基于 public `develop` `71aadb8aada6c242166a1deadc610c230ba1c616`。更正后的存储风险收据和最终 integration receipt 分别为 `a5e8cd0a50b8a79a75037e0c274b0e22d3ebdde2` 与 `bd9096ccad5cae54df0a2361d9797b2455862d49`。本次重新抓取 public refs 后，`develop` 仍为 `bd9096ccad5cae54df0a2361d9797b2455862d49`；`main` 仍为 `e4e39883fbe01d4be4b172a53a535ef0095b3d64`，annotated `v1.0.0` 标签对象仍为 `17c3100d4fabcb061c23569dea49973ebd177d51`。

S2-B2 的 exact two-file NutAssembly candidate retirement 与 integration receipt 见 [S2-B2 审查记录](p2_0_s2_b2_retirement_review.md)。本次未重做架构审计或改写冻结 Evidence。

## S2-C1 实现

实现提交为 `13063f8a20479030efdeb565f637019d30445f5b`，精确标量语义修正为 `38f18f397454b13b3a269502577711f6868a0af9`，移除 hardcoded Artifact SHA runtime guard 的 identity cleanup 为 `5b0058010f5416eefb08ce59cec43770602fc336`。三项都基于 public `develop` `bd9096cc…`，只存在本地；最终 native route 与 H5 证据对应执行源码提交 `5b00580…`。本地文档收据提交不改变执行代码。Artifact SHA 由现有 Core identity contract 计算并写入 provenance，准确选定值由 provider-free regression 锁定，task module 不维护历史 SHA guard/map。

当前 PickCube task directory 只有四个文件：

```text
task_env/tasks/pick_cube/
├── __init__.py
├── config.yaml
├── solution.py
└── task.py
```

开发者可通过 task-owned API 或已注册 public route 构造所选任务：

```python
from task_env import make_env
from task_env.tasks.pick_cube.task import build_reference, sample_reset

value = build_reference(backend="cpu")
sample = sample_reset(value["artifact"], 31)
env = make_env("pick-cube-p16-reference-v1", config={"provider": "mujoco"})
```

`task.py` 拥有 TaskArtifact、task composition、reset、canonical semantics、RuntimeSource 与显式 registration；`solution.py` 拥有四阶段 P1.6 readiness expert；`config.yaml` 只声明一个 100 Hz 选定 recipe。现有 Core TaskArtifact v0、TaskDefinition、RuntimeSource/Session、Controller、Recorder 和 public `make_env` contract 继续复用。不存在第二套 artifact schema、环境工厂或任务 predicate。

`SelectedReferenceEnv` 通过内部 `ReferenceTaskBinding` 接收各 task 的构造、reset、evaluation、observation poses、expert lifecycle 参数、控制周期模式与 recorder 要求，移除了按 PickCube/NutAssembly 名称分支的协调逻辑。NutAssembly 的绑定显式保留 native interval、execution recorder、guard samples、arm schedule、NA-S0 seed19 admission 和 runtime-abort 行为。它的 selected Artifact、Outcome V1 Solution、controller、recipe/configuration、task predicates、guard/physical limits 和原始严格 lifecycle status 未改；共享 adapter 的执行字节有变化，并已用最终 S2-C1 source 在 GeoPhys/MuJoCo 各执行一次完整 native route。

PickCube 可复用物体几何、惯性与 provider-neutral scene asset preparation 从 task 目录移到 `task_env/objects/pick_cube.py`；任务特定 table/cube placement 由 `task.py` recipe 驱动。Task module 不导入 GeoPhys 或 MuJoCo 的 native physics API；provider scene compilation 仍由既有 adapter 负责。

### Ownership migration

| S2-B2 active-tree owner | S2-C1 owner / disposition |
|---|---|
| `pick_cube/artifact.py`, `definition.py` | `pick_cube/task.py`，经现有 Core Artifact/TaskDefinition contracts |
| `canonical_semantics.py` | `pick_cube/task.py`，同一 lift-only evaluator 同时服务 Core TaskDefinition 和 reference observation |
| `reset.py`, `reset_policy.py` | `pick_cube/task.py`，复用 Artifact 的 PCG64 reset dimensions |
| `reference.py`, `reference_config.py`, `reference_env.py`, `runtime_source.py`, `timebase.py` | `pick_cube/task.py`，单一 task-owned P1.6 builder 和注册入口 |
| `readiness_solution.py` 与旧 selected expert 逻辑 | `pick_cube/solution.py`，版本化为 `pick-cube-p16-readiness-expert-v2` |
| `pick_cube/assets.py` | 原文件改名并扩充为 `task_env/objects/pick_cube.py`；对象几何/惯性/scene asset preparation 共用 |
| `candidate.py`, `default.yaml` | 删除，不建立新的候选 selector 或 TB-50/TB-500 active 变体 |

active callers 现在指向 `task_env.tasks.pick_cube.task` 或 public UID：registry、reporter fixtures、trajectory plan、record CLI、selected replay 均已迁移。`historical_tasks.make_historical_env('pick-cube-v1')` 明确提示从冻结源码恢复，不映射到新任务语义。其余直接导入旧 PickCube 模块的 Phase-I campaigns 是历史 recovery-only；需使用 v1.0.0 或下表所列的不可变 pre-C1 commit，不声称它们在当前开发树可运行。

## API 和历史源码兼容性

下列旧直接导入路径在当前 develop 工作树删除；不以别名转发到新实现：

```text
task_env.tasks.pick_cube.assets          # relocated to task_env.objects.pick_cube
task_env.tasks.pick_cube.artifact
task_env.tasks.pick_cube.candidate
task_env.tasks.pick_cube.canonical_semantics
task_env.tasks.pick_cube.definition
task_env.tasks.pick_cube.readiness_solution
task_env.tasks.pick_cube.reference
task_env.tasks.pick_cube.reference_config
task_env.tasks.pick_cube.reference_env
task_env.tasks.pick_cube.reset
task_env.tasks.pick_cube.reset_policy
task_env.tasks.pick_cube.runtime_source
task_env.tasks.pick_cube.timebase
```

`default.yaml` 已删除并由单一 `config.yaml` 取代；`assets.py` 移至 `task_env.objects.pick_cube`。旧 `PickCubeEnv`、`PickCubeResetSampler`、`PickCubeVariantSpec`、默认 Gym task ID 和 profile/constants convenience exports 已退役。包级 `build_reference`、readiness config/solution 与 Core `PickCubeTaskDefinition` 的选定导出保留，但其 implementation/source identity 已版本化；旧 module path 不保证兼容。

明确移除的旧 `task.py.__all__` convenience exports 为：`PICK_CUBE_AGENT_UIDS`, `PICK_CUBE_ENV_ID`, `PICK_CUBE_EXPERT_PROFILE`, `PICK_CUBE_OBJECT_UIDS`, `PICK_CUBE_RESET_PROFILE`, `PICK_CUBE_SCENE_UID`, `PICK_CUBE_SENSOR_PROFILE`, `PICK_CUBE_SPEC`, `PICK_CUBE_SUCCESS_DEFINITION`, `PICK_CUBE_TASK_UID`, `PICK_CUBE_VARIANT`, `PickCubeEnv`, `PickCubeResetSampler`, `PickCubeVariantSpec`。旧 `candidate.build_candidate` 和 retired Gym class 不会 alias 到 P1.6 route；需访问当前P1.6 builder时使用 `task_env.tasks.pick_cube.task.build_reference` 或 package-level `build_reference`。

文件 hash 和恢复位置详见 [S2-C1 source identity record](p2_0_s2_c1_source_identity.json)。`v1.0.0` 精确包含 `candidate.py`、`canonical_semantics.py`、`default.yaml`、`readiness_solution.py`、`reset.py`、`runtime_source.py`、`timebase.py`、`assets.py` 等记录中的 release blobs。S2-A/S2-B 后才出现的文件在该 tag 中不存在；这些精确 pre-C1 source blobs 由不可变 public develop 前置提交 `bd9096ccad5cae54df0a2361d9797b2455862d49:<path>` 保存。恢复任何历史 import/historical evidence 时，应 checkout 对应 immutable source，不把 old API 重映射到当前行为。

## Artifact、source 与执行身份

| Identity | S2-C1 current value |
|---|---|
| Public route | `pick-cube-p16-reference-v1` |
| TaskArtifact | `pick-cube-v1/p1_6_experimental_100hz` / `ver_p1_6_experimental_100hz` |
| TaskArtifact SHA-256 | `fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4`（与 S2-B1 相同） |
| Construction | `pickcube-p16-reference-construction-v2` |
| Timebase | control 100 Hz / `0.01 s`; physics `0.002 s`; 5 substeps |
| Runtime configuration SHA-256 | `d187ad45cec5fe7ac8a12a115dcf7a185336e8c1b78524ae5d2a6ed17bac22a1` |
| Generated source XML SHA-256 | `bdd119833a5ae3c8176daf1f5ef586c3601870f10f4b4b5f6d7aa730fe5f0fed`（不变） |
| Controller identity | `76108c78b8159391e448ad9f49050bed42fd7a86e0e00a0520083b4e5efb02e9`（不变） |
| Solution | `pick-cube-p16-readiness-expert-v2`, identity `514a5ed3bc0d289761ef88a00b1e7c11df2795133506ab148db9ab8e98e55241` |
| Current implementation revision | `5b0058010f5416eefb08ce59cec43770602fc336` |

每次构造均将真实 Git revision、resolved `config.yaml`、Artifact mapping/hash、runtime config、controller/solution identity、source file hashes、source XML hash 和 provider build provenance 写入 resolved configuration / recording provenance。完整每 provider resolved JSON 与记录在本机 ignored maintenance evidence 目录；source hash 摘要在 tracked JSON。Qualification 字段为 `NOT_REQUALIFIED`。

## 回归结果

### Provider-free

命令：

```bash
PYTHONPATH=. /home/lly/miniconda3/envs/geochora/bin/python -m pytest -q \
  task_env/diagnostics/tasks/test_reference_construction.py \
  task_env/diagnostics/tasks/test_selected_consumers.py \
  task_env/diagnostics/tasks/test_nutassembly_outcome.py \
  task_env/diagnostics/tasks/test_record_cli_completion.py \
  task_env/diagnostics/tasks/test_s2_b2_legacy_retirement.py
```

结果：**100 passed**。覆盖 public UID/API 与 retired UID/import、Artifact/semantic/reset identity、four-stage expert/lifecycle、Nut guard/outcome/identity、task binding/session/recording、H5 CLI success/failure finalization、provenance/source isolation 和精确 scalar reward 回归。`compileall` 与 `git diff --check` 通过。没有运行训练、GPU、checkpoint inference 或 historical D0/D1/D2 campaign。

### 两条 current-source full route

两次最终运行均通过 public `make_env`，执行源码 revision `5b0058010f5416eefb08ce59cec43770602fc336`，GeoPhys/MuJoCo CPU，seed31，使用独立 ignored output，串行执行；分别受 180s/120s wall-time 和 2 GiB process-tree RSS 限制。路线都完成 `move_above_cube → descend_vertical → close_gripper → lift`、实际 lift-only success，无 termination/truncation，验证 T transitions/T+1 boundaries、应用控制 provider、相邻 100 Hz clock、每周期五个 native substeps、canonical H5 finalize/load/roundtrip，并与 S2-B1 的物理、控制、状态、奖励和边界记录精确等价（仅归一化明确版本化的 expert diagnostic 标签后）。

| Provider | T / boundaries | Native steps | 最终 cube lift | 结果 / H5 SHA-256 | 时间 / 峰值进程 RSS |
|---|---:|---:|---:|---|---:|
| GeoPhys CPU | 151 / 152 | 755 native substeps (151 grouped 5-step intervals) | `0.10818110752105708 m` | PASS / `cd39b1d2e6c14c6a3fc39b744e26657448aedaf1d29b34ac60fcaec0026d9108` | 46.19 s / 627 MiB |
| MuJoCo CPU | 470 / 471 | 2,350 adapter `mj_step` calls | `0.10606502570351223 m` | PASS / `579c676d542f53b1dde8e7488ccff6e1fd01b7e2d6b56e2e975e759d3af69018` | 10.05 s / 289 MiB |

Current H5 bytes and overall logical identities differ from S2-B1 because source revision/provenance/solution identity changed. The raw transition+boundary comparison first differs only at `transitions[0].expert_diagnostics.expert_version`: old `pick-cube-readiness-v1`, new `pick-cube-p16-readiness-expert-v2`. Replacing only that explicit version label with the old value makes the complete transition and boundary mappings exactly equal for both providers. The first MuJoCo attempt on commit `13063f8` was retained as FAIL: it exposed a one-ULP `eef_to_cube_dist`/reward difference at boundary 12 due NumPy scalar coercion. Commit `38f18f3` restores old tuple-scalar evaluation order; the exact values are protected by a tracked regression and both providers were rerun on final execution source `5b00580`. The failed H5 and result JSON remain in the ignored evidence directory. A separate final-commit GeoPhys supervisor attempt stopped before simulation because its preflight treated pending docs-only edits as dirty; it created no H5 and ran no physics. After narrowing the preflight to execution source, both final v4 cases passed.

Raw final-source receipts: [GeoPhys result](../../../workspace/maintenance/p2_0_part_b_s2_c1_20261016/pickcube_geophys_v4/result.json), [GeoPhys resource monitor](../../../workspace/maintenance/p2_0_part_b_s2_c1_20261016/pickcube_geophys_v4/supervisor.json), [MuJoCo result](../../../workspace/maintenance/p2_0_part_b_s2_c1_20261016/pickcube_mujoco_v4/result.json), [MuJoCo resource monitor](../../../workspace/maintenance/p2_0_part_b_s2_c1_20261016/pickcube_mujoco_v4/supervisor.json), and [preserved first MuJoCo divergence](../../../workspace/maintenance/p2_0_part_b_s2_c1_20261016/pickcube_mujoco/result.json). The final implementation review baseline and source mapping are in the adjacent tracked [identity record](p2_0_s2_c1_source_identity.json).

### NutAssembly shared-binding full-route regression

The two selected full routes used the final S2-C1 execution code commit `5b0058010f5416eefb08ce59cec43770602fc336`, public UID `nut-assembly-outcome-reference-v1`, seed 19 / NA-S0, CPU, 100 Hz control and 2 ms physics (`5` native steps per control interval). Both completed all eleven authored stages, including `release_retreat`, produced T transitions and T+1 boundaries, finalized and round-tripped canonical H5, and returned `task_success=true`, `planned_trajectory_completed=true`, `outcome_complete=true`. No runtime termination/truncation or unapproved override occurred. Original strict lifecycle reporting is retained independently from the Outcome V1 result.

| Provider | T / boundaries | Native steps | Strict lifecycle / warning | Terminal measured state | H5 SHA-256 | Time / peak sampled process-tree RSS |
|---|---:|---:|---|---|---|---:|
| GeoPhys CPU | 2380 / 2381 | 11900 | Original Expert `failed`, `stable_height_mismatch` at `descend_to_handle`, step 362; admitted and recorded as the selected readiness warning | inserted/released/task success true; peg XY error `0.00147766146 m`, peg Z error `-0.00114415097 m`, yaw error `0.06758438 rad`, opening `0.0799999274 m` | `0afcc143cbfc3091dc005200a0891c1ece4e6e786d035fe748abee4349b54982` | 305.17 s / 812,478,464 B |
| MuJoCo CPU | 2373 / 2374 | 11865 | Original strict Expert `completed`; no readiness warnings | inserted/released/task success true; peg XY error `0.00039858347 m`, peg Z error `-0.00002656040 m`, yaw error `0.00081279402 rad`, opening `0.07999999999 m` | `0d927e416260e20fe00d7e011debf6b2da35ee31dfe9d8d1a2e32b81411189c4` | 102.38 s / 428,929,024 B |

For GeoPhys, an initial worker receipt was marked FAIL because its harness looked for a nonexistent `resolved.source_revision` field and mapped semantic identity aliases to literal paths. That run did complete the route and preserve H5. The corrected independent verifier used the recorded `source_head`, checked each resolved source SHA using the correct owner path, and produced a fresh direct PASS receipt at `nutassembly_geophys_c1_verified/`. The earlier failed harness receipt is preserved and not relabeled. Both providers were then compared with S2-B1 H5. The first raw difference in each file is `boundaries[0].owners.integrity_hash`, derived from the changed `ReferenceTaskBinding` source SHA (`b18d3a...` to `c13f67...`); after removing only that source identity and its dependent integrity digest, all transition and boundary mappings match exactly. Artifact SHA `99e374bd870c70f0dd427e34c47c6e6820aaa7067365133181a001a38239b9fe`, solution identity `4bf902b9b0bcc84955e9d51177c5811e65e02b2b540678fa14235d13d7cad923`, reset identity `767d56397dec41243aec445232d8d726b0891e7eeb49f655b789a86b23b5f4a2`, Outcome V1 policy identity `a940c6cfc4b9dbe64ae55b615e7bdbd9a210dc7495c6337b08cff688c52694ee`, and the per-provider recipes/controllers match their accepted S2-B1 identities. This is bounded functional regression, not historical P1.8 FULL or D0-D2 qualification.

Raw receipts: [GeoPhys result](../../../workspace/maintenance/p2_0_part_b_s2_c1_20261016/nutassembly_geophys_c1_verified/result.json), [GeoPhys resource monitor](../../../workspace/maintenance/p2_0_part_b_s2_c1_20261016/nutassembly_geophys_c1_verified/supervisor.json), [GeoPhys S2-B1 reconciliation](../../../workspace/maintenance/p2_0_part_b_s2_c1_20261016/nutassembly_geophys_c1_verified/reconciliation.json), [MuJoCo result](../../../workspace/maintenance/p2_0_part_b_s2_c1_20261016/nutassembly_mujoco_c1/result.json), [MuJoCo resource monitor](../../../workspace/maintenance/p2_0_part_b_s2_c1_20261016/nutassembly_mujoco_c1/supervisor.json), and [MuJoCo S2-B1 reconciliation](../../../workspace/maintenance/p2_0_part_b_s2_c1_20261016/nutassembly_mujoco_c1/reconciliation.json). The corrected GeoPhys run's source revision, full resolved configuration, source SHA list, H5 and outcome report are retained in the ignored maintenance directory.

运行期间 memory/I/O PSI 未达到 stop threshold，监督器未观察到新 kernel ATA/SATA/read-write I/O errors。既有 Oct 15 BadCRC/READ I/O 事件仍保留在 S2-B2 receipt；single-disk SATA 与 independent-backup 风险仍然存在。

## 影响范围与建议

NutAssembly 的选定 task/outcome 逻辑、artifact、solution/controller/recipe identity、guard/物理限制和 recorded lifecycle 语义未改变；共享 reference adapter 的源码身份更新已被记录，H5 行为仅在 source identity 与派生 digest 字段上不同。Go2、静态 physics solver、通用 vectorization/Batch/Device/Learner、Renderer、Phase II interoperability、P1.6 checkpoint 与 v1.0.0 发布内容均未修改。

此次已移除上述列出的当前 PickCube 模块/导入和便利 API；S2-B2 删除的两项 NutAssembly candidate 不在当前树。`task_env` 的通用 lifecycle/controller/recorder/provider/API contract 保留。v1.0.1 的公开兼容策略仍需维护者审阅。S2-C1 review 和 native regression 门槛已通过，现按用户指示核验并执行正常 fast-forward 集成；S2-C2 随后在独立分支实现，不与 C1 集成提交混合。S3、S4、S4.5 和 S5 均未开始。
