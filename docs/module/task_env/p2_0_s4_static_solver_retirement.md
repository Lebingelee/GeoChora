# P2.0-B S4 Static-Template Solver Retirement — Local Review Candidate

Date: 2026-10-16
Status: local candidate; not pushed or integrated
Branch: `codex/p2-0-b-s4-static-physics-retirement`
Base: public `develop` `5b8c901135e624a248cf73d29be9a6fea70feb2b` (the S3 integration receipt)

## S3 integration receipt

S3 commit `9c6548d69cbddb63c63727b7210814c1881c5180` has the expected parent `8b950e9a2f01667c6e0f4ec8d2cf06a44b9aadae` and is integrated on public `develop`. The follow-up receipt commit `5b8c901135e624a248cf73d29be9a6fea70feb2b` records that integration. A fresh fetch/readback confirmed public `develop` at that SHA. The annotated `v1.0.0` tag object remains `17c3100d4fabcb061c23569dea49973ebd177d51`, peeled commit `42787f5e4f658a3f81fdd2140cf7544d6342c783`; public `main` remains `e4e39883fbe01d4be4b172a53a535ef0095b3d64`.

The S3 retirement manifest contains 54 removed source files. All 54 recorded SHA-256 values and recovery Git blobs were rechecked against their immutable references. The 22-test S3 focused suite is recorded in the [S3 integration receipt](p2_0_s3_integration_receipt.md); the current 123-test task regression also includes the S3 negative UID/CLI tests. No current production Python imports from the retired Go2 or static-provider module prefixes were found. S3 did not change the selected PickCube/NutAssembly task trees, generic RL/Batch/Device/Learner contracts, GeoPhys Rigid Batch adapter, Static Physics, or Renderer implementation.

## S4 ownership and dependency change

Before S4, the TaskEnv batch factory had two layout registrations. The `static` registration loaded `StaticTemplateBatchRuntime`, whose implementation owned profile selection, model/materialization plans, kernels and contact workspaces. Public `task_env.runtime.static_*` facades exposed much of that implementation. Static-only Stage A, Stage G, and Stage 18 diagnostics were additional active entry points.

In this candidate, the TaskEnv batch factory has one constructible route: `merged_scene` to `SceneBatchRuntime`. `static_template` fails closed in typed configuration, public mapping/YAML resolution, the runtime factory, the Pendulum PPO CLI, and Stage 17. It is not redirected to `merged_scene` or the GeoPhys adapter. The GeoChora static solver, its compatibility modules, and three static-only diagnostics are deleted. The exact 25-path deletion and source-recovery inventory is in the [retirement manifest](p2_0_s4_static_solver_retirement_manifest.json).

| Ownership | S4 result |
| --- | --- |
| Generic `BatchRuntimeProtocol`, TaskEnv batch lifecycle, reset/step, terminal-slot and masked-reset contracts | Retained unchanged |
| Observation/action batching, host/device admission, SB3/RSL adapters, Vectorization factories/wrappers | Retained; no lifecycle or transport redesign |
| TaskEnv `merged_scene` batch route | Retained as the sole registered TaskEnv batch-physics route |
| GeoPhys-owned `GeoPhysRigidBatchRuntime` adapter | Retained unchanged, including explicit unsupported ground/domain-contact limits; not registered by this factory |
| GeoChora `task_env/runtime/providers/static/` solver, static facades, static profiles/plans/workspaces/kernels | Removed; recovery is via exact immutable refs in the manifest |
| Renderer Registry, Flora renderer, parallel render provider and its internal compatibility code | Unchanged; no Physics × Renderer work was performed |
| PickCube P1.6 and NutAssembly Outcome V1 task implementations | Their tracked task trees and TaskArtifact identities are unchanged |

The original `RuntimeConfig` static-template default object remains as default-only data so resolved scalar-task configuration identities do not drift. It cannot choose an active runtime: explicit mapping/YAML values and non-default direct values are rejected, and the package-root `StaticTemplate*Config` exports are removed. The candidate therefore retires the execution route without rewriting the selected scalar task configs. The common config/environment validators have new source identities; see [S4 source identity](p2_0_s4_source_identity.json). The selected task trees retain their baseline Git tree identities.

The preserved Renderer compatibility implementation and generic vectorization provenance still contain historical `static_template` vocabulary. Those references do not import or construct the retired physics solver. They are left in place to avoid an unrelated Renderer or vectorization schema change; the current runtime factory cannot produce that layout.

## Public API and command migration

The candidate removes the public `task_env.runtime` static runtime/profile/workspace symbols and package-root `task_env.environment.StaticTemplate*Config` exports. It removes 14 import paths and 16 package-root symbol exports listed in the manifest. `RuntimeConfig.batch_physics_layout` now declares only `merged_scene`; retired explicit layout/configuration requests fail with migration guidance. `pendulum_ppo --batch-physics-layout static_template`, `--static-template-profile`, and Stage 17's static layout/profile/precision/kinematics/candidate options fail or are removed. Stage 17's output schema is now `task-env-stage17-runtime-profile-v2`; Stage A, Stage G precision gate, and Stage 18 static bridge modules are retired.

Current migration documentation records these removals in `task_env/doc/api/appendix/migration.md` and the runtime field behavior in `task_env/doc/api/appendix/configuration.md`. The final v1.0.1 policy for direct module imports, serialized config compatibility, and metadata consumers remains for maintainer release review. The immutable v1.0.0 docs and qualification records were not edited.

## Validation

### Provider-free regression

Command:

```text
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=GeoPhys/src:. python -m pytest -q task_env/diagnostics/tasks
```

Result: **PASS — 123 passed in 156.87 s**, with one upstream Taichi `locale.getdefaultlocale` deprecation warning. Coverage includes selected task/artifact identities, task semantics, reset and lifecycle construction, recording/CLI gating, current S3 UID and CLI errors, retired static imports/exports/configuration/CLI, the one-route factory, generic Batch/Device and SB3/RSL import boundaries, and the GeoPhys adapter's unsupported-contact failure. These are provider-free contract checks except where noted below; they are not qualification.

The existing Renderer Registry/Flora backend contract suite also passed: **9 passed, 6 subtests passed** in 3.43 s. Its contract smoke substitutes native endpoints and does not create a window, load Flora native runtime, or claim a physics/rendering intersection.

The first full run during the config edit had 121 passes and two source-identity assertion failures because removing the default static config object changed resolved scalar-task hashes. The default object was restored as inert default-only data, with explicit static configuration still rejected. The targeted identity/retirement tests then passed 23/23, and the final complete task suite passed 123/123.

### Native and fake-runtime evidence

One bounded native GeoPhys CPU batch smoke passed: `pendulum-v1`, `merged_scene`, local execution, two worlds, reset plus one zero-action step, 19.539 s; returned observations and rewards were finite and terminal flags were false. This verifies that the supported merged-scene route still constructs and steps. It is not PickCube/NutAssembly evidence, a learner run, or a capability qualification.

The first probe attempt supplied a flat NumPy action to the task's Dict action space and stopped at adapter validation before physics stepping. The second attempt used a valid batched Dict action and completed the physics step, but the probe's receipt formatter assumed a shallow observation mapping and failed while serializing nested shapes. Both receipts are preserved under ignored `workspace/maintenance/p2_0_b_part_b_s4_20261016/`; the corrected third attempt passed. These were harness errors, not runtime failures.

No reusable bounded native `GeoPhysRigidBatchRuntime` probe was present. Its import path and unsupported-contact admission were checked provider-free; native Rigid Batch physics was **NOT_RUN**. No fake-runtime test is described as native physics evidence. The S2-C2 PickCube/NutAssembly full-route receipts remain the current accepted task evidence; S4 did not repeat them because the task implementation trees, providers, controllers, recorders, and task Artifact identities are unchanged. The config/environment source changes are limited to static-route rejection and removal of a static-only preload branch; provider-free selected-route tests and the native merged-scene smoke cover the affected construction boundary. No historical D0–D2 or v1.0.0 qualification is inherited.

### Resource and storage observation

The 123-test provider-free run and native smoke ran serially. During the native smoke, available memory remained above 3.7 GiB and memory/I/O PSI stayed near zero; swap remained available. A read-only kernel journal query showed no ATA/SATA/read-write error lines in the retrieved recent records, but the kernel log view is not a complete storage health test. The known single-disk `/dev/sda` / `ata5` BadCRC risk and lack of verified independent backup remain **OPEN**. No ignored H5, experiment, or frozen Evidence directories were removed. No release or historical Evidence paths were changed.

## S4.5 prerequisites and review boundary

S4.5 must separately inventory scripts/examples that expose the retired layout and remove or migrate only those callers with their own API review. It must not infer support for GeoPhys Rigid Batch profiles, change Renderer interoperability, or reconstruct every historical script. A maintainer must also decide the v1.0.1 compatibility treatment for direct imports, default-only serialized config data, and old metadata consumers before release freeze.

### Public integration receipt (2026-10-17)

After the review gates above passed, the maintainer authorized the bounded S4
integration. The exact S4 commit `0ff2d846a36c7014d2b40a530f52d99e64266ff9`
was pushed to public `develop` by normal fast-forward from
`5b8c901135e624a248cf73d29be9a6fea70feb2b`. Public readback returned the S4
SHA. `main` remained `e4e39883fbe01d4be4b172a53a535ef0095b3d64`, and the
annotated `v1.0.0` tag object remained
`17c3100d4fabcb061c23569dea49973ebd177d51`. This integration did not create
new provider/capability qualification. S4.5, S5, v1.0.1 publication, and any
main/v1.0.0 change remain outside the S4 change set.
