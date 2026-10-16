# GeoChora P2.0-B S2-C2 Integration & S3 Go2 Retirement

Date: 2026-10-16
Status: S2-C2 integrated; S3 prepared as one local review commit for maintainer review. No S3 push, merge, v1.0.1 publication, S4, or S4.5 work was performed.

## Part A — S2-C2 integration receipt

Canonical public `develop` before S3 is `8b950e9a2f01667c6e0f4ec8d2cf06a44b9aadae`, and the local S3 branch starts at that exact commit. The S2-C2 code commits are `ce1cd782ff26b52c4fd8738fbb1b595cfd6f44f2` and `4d6d65c55eca994b4317bcfb80797c69e48452c6`; the authoring-convention and final integration record reached public `develop` at `8b950e9a2f01667c6e0f4ec8d2cf06a44b9aadae` through normal fast-forwards. The detailed integration receipt is [S2-C2 integration receipt](p2_0_s2_c2_integration_receipt.md).

The final NutAssembly task directory contains exactly:

```text
task_env/tasks/nut_assembly/
    __init__.py
    task.py
    solution.py
    config.yaml
```

PickCube likewise has its four selected authoring files: `__init__.py`, `task.py`, `solution.py`, and `config.yaml`. The selected active UIDs remain `pick-cube-p16-reference-v1` and `nut-assembly-outcome-reference-v1`. The selected TaskArtifact, NutAssembly Outcome Completion V1 policy, readiness-warning admission, guarded close authorization, force/capture/runtime limits, and strict lifecycle observations retain the identities recorded in the S2-C2 source identity report. The final S2-C2 full-route receipts remain bounded functional acceptance only, not historical D0–D2, P1.8 FULL, or release qualification.

The final provider-free suite was rerun as part of S3 validation and passed 124 tests (plus 6 unittest subtests). No implementation byte in the selected task execution closure changed from S2-C2. Public `make_env(uid, …)` remains the canonical environment-construction API. PickCube's package-root `build_reference` export remains for compatibility; NutAssembly's former package-root alias remains retired. They are documented asymmetrically rather than silently remapped.

Remote refs read back as `develop = 8b950e9a2f01667c6e0f4ec8d2cf06a44b9aadae`, `main = e4e39883fbe01d4be4b172a53a535ef0095b3d64`, and annotated `v1.0.0` tag object `17c3100d4fabcb061c23569dea49973ebd177d51` peeling to `42787f5e4f658a3f81fdd2140cf7544d6342c783`.

## Part B — S3 scope and dependency migration

S3 removes 54 tracked Go2-dependent source/configuration files. The path-by-path SHA-256, baseline blob, and exact `v1.0.0` recovery blob are in [the S3 recovery manifest](p2_0_s3_go2_retirement_manifest.json). All 54 deleted file contents have the same SHA-256 and Git blob at the public S2-C2 baseline and immutable `v1.0.0`.

The 54 deletions consist of:

- 6 files under `task_env/tasks/go2_walk/`, 9 under `go2_walk_deploy/`, and 6 under `go2_walk_codex/`;
- 3 under `task_env/robots/go2/`, 13 under `task_env/diagnostics/go2/`, and 4 under `task_env/script/rl/go2/`;
- 2 Go2 RSL profile YAMLs, 3 Go2-only Flora diagnostics, `task_env/flora_go2_assets.py`, and `task_env/script/flora_go2_single_smoke.py`;
- five runtime diagnostics bound to Go2/static fixtures: Stage B, Stage G, both Stage 19d variants, and Stage P;
- `stage_f_cuda_graph_lifecycle.py`, whose caller trace showed it imported the retired Stage 19d and Stage B Go2 builders and had no task-neutral fixture or remaining callers.

Historical `v1.0.0` is the exact recovery point for all deleted files. The ignored experiment/H5 workspace, frozen Evidence, historical hashes, and qualification reports were not changed.

The caller migration and public removals are:

| Surface | S3 result |
| --- | --- |
| `task_env.tasks` / top-level `task_env` exports | Removed Go2 walk, deploy, height-deploy, and Codex task classes and lazy exports. |
| `task_env.robots` | Removed Go2 agent, action adapter, constants, and `go2-v1` registration. |
| `make_env` / `make_agent` | Retired Go2 UIDs raise explicit `ValueError`; no other task or robot is substituted. |
| Generic RSL runner | Removed Go2 aliases. Retired UIDs and aliases raise an explicit error. `rsl_ppo.py` now requires `--env-id`; it has no default training target. Its generic `--render`/`--hard-render` controls remain. |
| Generic runtime diagnostics | Stage A, Stage 17, and Stage 18 now require an explicit `--task-uid`; old implicit Go2 invocations no longer run. |
| Go2 checkpoint, oracle, training, and evaluation CLIs | Removed with their Go2 module trees; their historical invocation/module identities are listed in the recovery manifest and migration doc. |
| Flora Go2 adapters | Removed task-specific Go2 asset adapter, old top-level wrapper, and Go2 diagnostics/smoke. `task_env.render.flora` and generic render-description/MJCF lowering remain. |

The old `task_env/render/flora_go2_assets.py` file is retained because it is a generic re-export of `task_env.render.flora.assets`, not a Go2 loader. The generic Flora bundle still emits legacy `task_env.go2_flora_bundle.v1` metadata and `go2_` material/output names; those serialized labels were left unchanged to avoid an unreviewed renderer-output compatibility change.

## Preserved boundaries and S4 prerequisites

`task_env/alg/rsl_rl/`, `task_env/alg/sb3/`, the generic RSL/SB3 adapters, Batch/Device/Learner contracts, and `task_env/vectorization/` remain. The RSL action-transform implementation changed comments only; transform behavior is unchanged. No PickCube or NutAssembly task was selected as an RSL training target.

`task_env/runtime/providers/static/`, `task_env/runtime/static_*.py`, and GeoPhys are unchanged from the S2-C2 baseline. The removed Stage B/G/19d/P/F scripts were Go2-bound diagnostic fixtures, not the Static Physics implementation. S4 must create or select a task-neutral, reproducible fixture for any static-runtime CUDA Graph/contact/lifecycle regression; it must not rely on those retired Go2 paths or infer new qualification from their historical evidence.

The Renderer Registry and Flora renderer sources are unchanged. Registry dispatch tests and GeoPhys's external Flora/RTXNS runtime contract tests pass. This confirms the existing supported registry/fake-runtime scope only; S3 did not run or claim a native Flora qualification.

## Validation and resource record

- Provider-free selected-task, S3 registry/API, lifecycle/outcome, recorder/CLI, and Renderer Registry regression: **PASS**, 124 tests and 6 unittest subtests, 157.11 s.
- Focused S3 retirement suite: **PASS**, 22 tests.
- Focused RSL adapter CPU/host-numpy transition smoke: **PASS**, action clipping, timeout flag, terminal observation and masked reset checked with two fake environments; no simulator or training.
- `GeoPhys/test/verification/runtime/test_flora_and_rtxns_external_runtime.py`: **PASS**, 36 tests. The tests exercise adapter/fake-runtime contracts, not a native Flora renderer qualification.
- Static Physics, Vectorization, generic RSL/SB3 modules, Flora render modules, and GeoPhys: no implementation changes. The selected PickCube source identity map (17 files) and NutAssembly source identity map (24 files on each provider) match their recorded SHA-256 values and the S2-C2 baseline. Selected task/runtime/controller/recorder/provider source directories are byte-identical to that baseline.
- AST scan found no remaining production Python import of any retired Go2 or Go2-bound diagnostic module. Negative tests confirm the selected task UIDs remain registered, old Go2 task/agent UIDs fail explicitly, old RSL aliases fail, and retired source modules are not importable.
- `git diff --check` and `py_compile` passed for modified Python entry points and tests.

Before/after resource observations were approximately 3.8–3.9 GiB `MemAvailable`; memory and I/O PSI remained low. Kernel logs showed only the previously known 2026-10-15 `/dev/sda` read error and `ata5` recovery, with no newer ATA/SATA/read/write I/O error during this work. The SATA/BadCRC risk and lack of a verified independent backup remain open; no destructive cleanup or ignored-output deletion was performed.

## Maintainer handoff

S2-C2 is integrated at the public `develop` baseline above. S3 is a separate local review change on `codex/p2-0-b-s3-go2-retirement`; the public remote remains at the S2-C2 baseline. Review the exact S3 commit before deciding whether to integrate it. No S3 push/merge, main or `v1.0.0` modification, S4 Static Physics retirement, S4.5 scripts/examples reconstruction, Renderer interoperability, or v1.0.1 publication has occurred.
