# P2.0-B S2-C2 — Minimal NutAssembly task authoring

状态：S2-C2 已在本地分支完成实现、provider-free 回归和最终源码双 provider bounded full-route 回归；提交 `4d6d65c55eca994b4317bcfb80797c69e48452c6` 尚未集成，等待维护者审阅。public `develop` 仍停在已集成的 S2-C1 head `a6372099ac2055045cca16c03a0514825d635e8f`。

## S2-C1 integration receipt

核验了 `bd9096ccad5cae54df0a2361d9797b2455862d49` 到 `a6372099ac2055045cca16c03a0514825d635e8f` 的 ancestry。S2-C1 执行 commits `13063f8a20479030efdeb565f637019d30445f5b`, `38f18f397454b13b3a269502577711f6868a0af9`, `5b0058010f5416eefb08ce59cec43770602fc336` 均为该公共 head 的祖先；`public` remote 的 `refs/heads/develop` readback 为 `a6372099…`。PickCube 两 provider 回归未重跑，因为 S2-C2 没有改 PickCube 执行源码；本节只补做 C1 shared binding 改造后遗漏的 NutAssembly cases，结果见下表。

独立复核了 C1 的完整代码差异：PickCube 的 task/solution/config 与对象资产迁移，以及共享 `SelectedReferenceEnv` 到 `ReferenceTaskBinding` 的改造均与选定 P1.6 路由和既有 provider/runtime 契约一致；NutAssembly 的 binding 保持其 grouped/native stepping、guard samples、execution recording、schedule 和 runtime-error teardown 要求。没有发现重复 Artifact schema、静默重定向旧 UID 或未解释的公共 runtime API 变化。一个早期 MuJoCo 轨迹发现的 1-ULP reward/metric 差异已由 `38f18f3` 恢复原 tuple-scalar 求值顺序并加入回归；最终 C1 两 provider 运行基于修正后的源码。共享适配器仍通过 `outcome_report` 方法存在性附加 NutAssembly outcome 字段；当前绑定和完整 C1/C2 route 测试覆盖该行为，本次未发现结果偏差。

## Implementation and ownership

最终 `task_env/tasks/nut_assembly/` 目录只有以下四个文件：

```text
__init__.py
task.py
solution.py
config.yaml
```

| Concern | Before S2-C2 | S2-C2 owner |
|---|---|---|
| Artifact, task definition/evaluation, scene placement, reset, public binding | Split across canonical artifact/semantics/reset/source, definition, reference and environment modules | `task.py` |
| Selected 11-stage expert, grasp readiness, guard authorization, warning admission, Outcome V1 and strict lifecycle report | Candidate inheritance across canonical V2, stable-grasp, clearance V3/V5, guarded authorization V1/V2 and outcome solution modules | One flattened `solution.py` implementation; its MRO is `(NutAssemblyOutcomeSolutionV1, object)` |
| Nut/Peg geometry and nominal inertia | Task-local asset/profile files | Reusable geometry constants in `task_env/objects/nut_assembly.py` |
| Provider-neutral MJCF assembly and asset preparation | Task-local `assets.py` | `task_env/assembly/nut_assembly.py`, parameterized by task-owned scene data |
| Selected recipe and provider options | Several default/profile files and selectors | One tracked `config.yaml`; MuJoCo NoSlip2 remains a provider option |

The task code does not import GeoPhys or MuJoCo native physics APIs. It builds the existing `TaskArtifact`, `RuntimeSource`, `TaskSceneSource` and `ReferenceTaskBinding`, then continues through the existing public `make_env`, runtime, controller and recorder contracts. No generic runtime, provider, controller, recorder, or shared binding API changed.

The public UID remains `nut-assembly-outcome-reference-v1`; the serialized TaskArtifact remains `nut-assembly-square-v1/p1_8_e/nominal-v1`, version `ver_p1_8_e_nutassembly_nominal_v1`, SHA-256 `99e374bd870c70f0dd427e34c47c6e6820aaa7067365133181a001a38239b9fe`. The one 100 Hz recipe fixes `physics_dt=0.002 s`, five native steps per 0.01 s control interval, NA-S0 seed19, selected nominal V2 assets, R3 controller settings, 10 N target/cap, 0.008 m / 0.15 rad capture limits, 60 s action budget, close guard and Outcome Completion V1. The policy identity remains `a940c6cfc4b9dbe64ae55b615e7bdbd9a210dc7495c6337b08cff688c52694ee`; diagnostic continuation and full Expert PASS promotion remain disabled.

## Removed modules and compatibility

The S2-C2 commit removes 27 task-local paths. The former `assets.py` implementation moved to the assembly owner; the other removed implementation, config and profile paths are:

```text
README.md
canonical_artifact.py
canonical_initialization.json
canonical_reset.py
canonical_semantics.py
canonical_solution.py
canonical_solution_v2.py
canonical_source.py
clearance_candidate_v3.py
clearance_candidate_v5.py
default.yaml
definition.py
geometry.py
guarded_authorization_candidate.py
guarded_authorization_candidate_v2.py
outcome_solution.py
profiles/mujoco-noslip2-v1.json
profiles/nutassembly-nominal-v1.json
profiles/nutassembly-nominal-v2.json
profiles/nutassembly-r5-stable-grasp-10n-v1.json
profiles/r5-controller-planner-reference.yaml
reference.py
reference_config.py
reference_env.py
reference_execution.py
stable_grasp_candidate.py
```

SHA-256, pre-consolidation Git blobs and v1.0.0 recovery blobs are recorded per path in [the S2-C2 source identity and recovery manifest](p2_0_s2_c2_source_identity.json). All 27 paths are recoverable from immutable pre-consolidation commit `a6372099ac2055045cca16c03a0514825d635e8f`; eight were added after v1.0.0 and therefore have no v1.0.0 blob. Frozen v1.0.0 files and historical qualification reports were not changed.

The selected builder now lives at `task_env.tasks.nut_assembly.task.build_reference(provider=...)`. The old `task_env.tasks.nut_assembly.reference` API and its `rate_hz` / `execution_policy` selectors are removed. The former package-level `from task_env.tasks.nut_assembly import build_reference` now raises an explicit `ImportError` with migration guidance; it is not redirected to the new builder. The old `nut-assembly-square-v1` trajectory-plan route is explicitly rejected. The selected public UID remains available through the existing registry. This is a task-specific breaking import/API change that must be included in the planned v1.0.1 migration guide and reviewed before release.

Current selected consumers in package registration, trajectory recording/replay and reference execution were migrated to `task.py`. Phase I historical diagnostics may still name removed candidate modules; do not run those scripts against this active tree and do not map their old selectors to Outcome V1. Restore commit `a6372099…` or the applicable immutable v1.0.0 blobs to recover historical source. Frozen reports and Evidence remain untouched.

### Authoring API convention review

The package roots are currently inconsistent: `task_env.tasks.pick_cube` re-exports `build_reference`, while `task_env.tasks.nut_assembly` explicitly rejects that package-level import and keeps its builder at `task_env.tasks.nut_assembly.task`. Recommend one convention for v1.0.1: `task_env.make_env(uid, ...)` is the canonical public environment construction API; task-package roots expose registration identity/types only; exact `task.py` builders remain task-owned construction helpers for internal authoring and bounded verification. Do not restore the NutAssembly package alias or silently remove the PickCube export during this integration. Retire the PickCube root export only through a separately documented, versioned compatibility change after its callers migrate.

## Validation

The provider-free suite passed **93 tests in 154.30 s** after the explicit package-level API retirement was added. It covers Artifact/config/reset identity, semantics, readiness and Outcome V1, guard failures, invalid state, termination/truncation/budget behavior, route registration/import isolation, recorder/replay boundaries, CLI result gating, retired imports and source provenance. `py_compile` and `git diff --check` passed.

Final native runs used exact source revision `4d6d65c55eca994b4317bcfb80797c69e48452c6`, public `make_env`, CPU only, serial execution, NA-S0 seed19, and fresh ignored output directories. Each supervisor allowed up to 480 s, capped the worker process tree at 2 GiB RSS, reserved at least 3 GiB available memory and 5 GiB free disk, and checked PSI and kernel storage errors. Neither final run observed a new SATA/ATA/read/write error.

| Provider | Result | T / boundaries | Native steps | Final task state and strict lifecycle | H5 SHA-256 |
|---|---:|---:|---:|---|---|
| GeoPhys CPU | PASS | 2380 / 2381 | 11,900 | All 11 authored stages and `release_retreat` completed; `inserted_on_peg`, `released_nut`, `task_success`, `planned_trajectory_completed`, and `outcome_complete` true. One `descend_to_handle/stable_height_mismatch` readiness warning at step 362; original strict Expert remains failed at step 362. | `e539d5b2662d191c0a70b1ac9dd593842279397b8627f0e3871d8852c78c2271` |
| MuJoCo CPU | PASS | 2373 / 2374 | 11,865 | All 11 authored stages and `release_retreat` completed; task/outcome predicates true. No readiness warning; original strict Expert completed. | `f7000d28e1a47363542bef8909341d5a13582175941b394987ad31f0ea4f5931` |

Both recordings use canonical execution-v2 and passed byte-exact H5 roundtrip. The route checked five applied native controls per interval, T transitions/T+1 boundaries, final physical measurements, guard authorization, unchanged force/capture limits, no runtime override, and no termination or truncation. The final current-source transition and boundary payloads match the accepted S2-C1 H5 records exactly after normalizing only source-derived identity fields. This comparison verifies each outer and native applied target hash against that episode's own canonical target before excluding the hash; actual target payloads, applied control values, states, task metrics, clocks, stage records and native audits are compared without normalization. There is no remaining behavioral divergence.

The preserved first raw comparison difference was `target_hash`: `CanonicalControlTarget.identity_hash` contains the changed controller identity. Its arm positions and gripper targets match; both old and new applied hashes independently resolve to their respective canonical target. The initial pre-final checker did not normalize this source-derived field and retained a FAIL verifier receipt; a separate reconciliation passed. The final-source GeoPhys and MuJoCo reruns use the corrected verifier and both report PASS. Intermediate receipts remain preserved and are not substituted for the final-source results.

### Identity migration

| Identity | S2-C1 | S2-C2 final |
|---|---|---|
| TaskArtifact SHA | `99e374bd870c70f0dd427e34c47c6e6820aaa7067365133181a001a38239b9fe` | unchanged |
| Construction ID | `nutassembly-r5-v5-outcome-reference-construction-v2` | `nut-assembly-outcome-reference-v1` |
| Solution identity | `4bf902b9b0bcc84955e9d51177c5811e65e02b2b540678fa14235d13d7cad923` | `cba7a4932f4b36b01a855417833509d301746325ba93e85cd4cfed23a802a9b4` |
| GeoPhys controller / recipe | `cad9c5d2…` / `84912989…` | `094bbf73…` / `7d1b20f3…` |
| MuJoCo controller / recipe | `ce29b631…` / `c6747b26…` | `3c455279…` / `9f5ce320…` |
| Outcome V1 policy identity | `a940c6cf…` | unchanged |

The resolved source SHA map (24 files), provider build/contact profiles, full config, controller parameters, solution settings, source XML and H5 receipts are in the linked source identity JSON. New implementation identities do not inherit P1.8 FULL or D0-D2 labels. These runs are bounded functional regression only.

## Scope and handoff

S2-C2 changes task-owned NutAssembly authoring, its asset/assembly ownership, task-local historical files, relevant task imports and focused tests. It does not change Go2, static physics, generic RL, Batch/Device/Vectorization, Renderer, Phase II interoperability, shared runtime/provider contracts, or PickCube execution. No examples/scripts were reconstructed. S3, S4, S4.5 and S5 have not started. The local S2-C2 commits are not pushed or merged; stop here for maintainer review of the implementation, API migration, and bounded acceptance evidence.
