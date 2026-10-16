# GeoChora P2.0-B S4 Final Review and S4.5-A Developer Workflows

Date: 2026-10-16

Status: S4 review gates pass, integration pending explicit maintainer authorization; S4.5-A is a local review candidate

Public `develop` baseline: `5b8c901135e624a248cf73d29be9a6fea70feb2b`

S4 branch/commit: `codex/p2-0-b-s4-static-physics-retirement` / `0ff2d846a36c7014d2b40a530f52d99e64266ff9`

S4.5-A branch/implementation commit: `codex/p2-0-b-s4-5-a-developer-workflows` / `5d57272d1ce7469bb214cf185137853a7eb6deb0`

## Part A — S4 final review

The freshly queried canonical public refs still match the expected baseline:

| Ref | Readback |
| --- | --- |
| `public/develop` | `5b8c901135e624a248cf73d29be9a6fea70feb2b` |
| `public/main` | `e4e39883fbe01d4be4b172a53a535ef0095b3d64` |
| annotated `v1.0.0` tag object | `17c3100d4fabcb061c23569dea49973ebd177d51` |
| peeled `v1.0.0` commit | `42787f5e4f658a3f81fdd2140cf7544d6342c783` |
| S4 parent | `5b8c901135e624a248cf73d29be9a6fea70feb2b` |

S4 is one commit directly on the public baseline. Its exact diff contains 49 paths, including the 25 deletions enumerated in [`p2_0_s4_static_solver_retirement_manifest.json`](p2_0_s4_static_solver_retirement_manifest.json). All 25 old-file SHA-256 values and Git recovery blobs were checked against the recorded refs with no mismatch. Every recovery object is available from its recorded immutable `v1.0.0` tag or public S3 baseline commit. The checked-out v1.0.0 tree, frozen release documents, and Evidence are unchanged.

The final S4 gates passed:

- The TaskEnv batch factory registers only `merged_scene`; static-template configuration requests fail closed, and default-only static data cannot register or construct a runtime.
- Scalar resolved configuration identities remain stable. The PickCube and NutAssembly trees are byte-for-byte unchanged across the S4 parent and S4 commit: `bac089f4ace6ca0693a8261fefacbc25dc108f48` and `eed6b5c6f900e3c04f5150562f2758d17be4c9fb` respectively.
- Generic Batch/Device/Learner, Vectorization, runtime contracts, the merged-scene route, GeoPhys Rigid Batch adapter, RL adapters, Renderer Registry, and Flora renderer have no S4 diff. The adapter retains its existing limits; this review does not claim a native GeoPhys Rigid Batch capability.
- The final task-provider-free suite passes **129 tests** on the S4.5-A implementation source, including S4 retirement and protected-contract checks. The Renderer Registry/Flora contract suite previously passed **9 tests and 6 subtests**; it substitutes native endpoints and is not a renderer/provider capability test.
- A bounded native GeoPhys CPU `pendulum-v1` merged-scene batch smoke passed with two worlds, reset plus one zero-action step, finite observations/rewards, and no termination. Its preserved receipt is `workspace/maintenance/p2_0_b_part_b_s4_20261016/merged_scene_pendulum_cpu_batch_smoke_final.json`. Native GeoPhys Rigid Batch physics was **NOT_RUN**.

The exact recovery inventory, compatibility removals, preserved generic paths, and default-only config rationale remain in the S4 [deletion manifest](p2_0_s4_static_solver_retirement_manifest.json), [source identity record](p2_0_s4_source_identity.json), and [S4 review](p2_0_s4_static_solver_retirement.md). In particular, retaining the inert default object preserves scalar resolved configuration identity; it is not an executable solver route.

**Integration recommendation:** the S4 review gates pass and I recommend a normal fast-forward, but the prompt makes maintainer authorization an explicit gate. S4 has not been pushed or merged. After approval, the exact commands are:

```bash
git fetch public develop
git merge-base --is-ancestor 5b8c901135e624a248cf73d29be9a6fea70feb2b 0ff2d846a36c7014d2b40a530f52d99e64266ff9
git push public 0ff2d846a36c7014d2b40a530f52d99e64266ff9:refs/heads/develop
git ls-remote public refs/heads/develop
```

The required public readback is `0ff2d846a36c7014d2b40a530f52d99e64266ff9`. A fresh fetch/readback is required immediately before pushing; any changed public baseline cancels this recommendation and requires review again. No force option is used.

## Part B — S4.5-A workflow implementation

The implementation is a separate local change set on S4. The selected public task directory ownership and task source files are unchanged. The new root tree is:

```text
examples/
  README.md
  _common.py
  tasks/
    pick_cube.py
    nut_assembly.py
  recording/
    record_expert.py
```

The examples call `from task_env import make_env` with `pick-cube-p16-reference-v1` or `nut-assembly-outcome-reference-v1`, an explicit GeoPhys/MuJoCo provider, CPU backend, and bounded horizon. The shared helper imposes POSIX CPU-time, wall-time, address-space, and single-native-thread limits. Each environment is closed in `finally`. NutAssembly accepts only `step_expert()` and reports task outcome separately from strict expert lifecycle status. A short or truncated NutAssembly route returns nonzero and is not reported as task success.

The recording example starts the existing task-owned recorder directly after reset, steps through the selected expert, finalizes the existing canonical H5 schema, reads it back, verifies `T` transitions and `T+1` boundaries, and requires the recorder's supported roundtrip check before returning zero. It records automatically generated source, provider, Artifact, solution, controller, and resolved-configuration provenance. The H5 check is storage validation, not D0 replay.

### Current and retired caller routes

| Caller | S4.5-A disposition |
| --- | --- |
| `task_env.script.env.single_*` | Retained; selected single-task routes use the current public factory. |
| `task_env.script.env.parallel_*` | Retained as generic registered batch/vectorization workflows; no selected task is substituted as a learning target. |
| PickCube/NutAssembly planning CLIs | Retained on selected `make_env` routes; NutAssembly advances only through guarded `step_expert()`. Result fields keep task success, planned completion, outcome completion, and expert lifecycle distinct. |
| `task_env.script.trajectory.record` / `task_env.script.recorder` | Current selected expert recording remains on the canonical recorder. The compatibility module forwards `main` only; private historical task-config helpers are removed. |
| `trajectory.convert`, `trajectory.replay`, collection merge | Retained after caller inspection as generic offline utilities. Historical H5 replay requires its explicit historical path; current-source reexecution is a different operation. |
| `trajectory collect`, `--historical-grouped`, `trajectory._task_plans` | Retired explicitly. No old task IDs or grouped routes are silently mapped to the selected tasks. |
| Stage 11 collection/socket entry points | Retained only as explicit retirement messages; historical bytes are restored from the exact ref in the recovery manifest, in a separate checkout. |
| `diagnostics.phase1.nutassembly_recovery.historical` | Provider-private legacy route explicitly retired; current workflow uses the selected public NutAssembly UID. |

The ten changed/deleted legacy script source blobs, hashes, recovery refs, and retired invocation identities are in [`p2_0_s4_5_a_source_recovery.json`](p2_0_s4_5_a_source_recovery.json). The manifest identifies the S4 commit for source versions that differ from v1.0.0, and v1.0.0 only where its bytes match. No obsolete implementation was copied to another active directory.

### Validation and bounded examples

On exact implementation commit `5d57272d1ce7469bb214cf185137853a7eb6deb0`:

- **Provider-free PASS:** `129 passed, 1 upstream Taichi locale deprecation warning in 154.84s`; includes task/API/import boundaries, selected UID and retired-route failures, guard admission, lifecycle and outcome reporting, CLI result gating, failed-task H5 finalization, and the S4 runtime/contract gates. The focused CLI/example subset also passed **41 tests**. Example and CLI `--help`, Python compilation, and `git diff --check` passed.
- **PickCube example PASS:** MuJoCo CPU, seed 31, selected P1.6 route, 100 Hz, 470 transitions; `task_success=true`, `expert_complete=true`, measured lift `0.1060650257 m`, no termination/truncation. Artifact SHA-256 `fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4`; construction `pickcube-p16-reference-construction-v2`.
- **PickCube recording PASS:** MuJoCo CPU, seed 31, 470 transitions / 471 boundaries, canonical-trajectory-v0, `T+1=true`, logical mapping roundtrip exact. Ignored H5: `workspace/maintenance/p2_0_b_s4_5_a_20261016/5d57272d/pickcube_mujoco_seed31.h5`; file SHA-256 `e22bcadbb142c81f2bdd8f12a432b82b22cef0c25ddeba8cec29f764bca87ae8`; canonical logical identity `a71f0af2817f88e9f0c318e0103addb568202c61f297f4edd6ba671b15a3ebee`. The H5 source revision is the exact implementation commit above, with 17 source-file SHA entries. Artifact SHA-256 is `fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4`; controller identity `76108c78b8159391e448ad9f49050bed42fd7a86e0e00a0520083b4e5efb02e9`; solution identity `514a5ed3bc0d289761ef88a00b1e7c11df2795133506ab148db9ab8e98e55241`; resolved configuration identity `0ae9a147c5712846ea5a3fc8acf85059e283cc23b453feb618603265b428367f`. D0 and qualification are **NOT_ASSESSED**.
- **NutAssembly expected incomplete smoke:** MuJoCo CPU, NA-S0 seed 19, horizon 2; two guarded expert steps, exit code 1, `task_success=false`, `planned_trajectory_completed=false`, `outcome_complete=false`, `expert_complete=false`, and truncation reason `environment_truncated_before_expert_completion`. No readiness bypass or external action was used. This validates construction and guarded step admission only; it is **not** a full-route result or task acceptance.

The selected task execution trees and runtime/provider sources are unchanged by S4.5-A. The new PickCube run verifies the example route; it is not policy checkpoint inference or P1.6 requalification. No NutAssembly full native route was rerun. The incomplete smoke is intentionally not normalized to PASS.

## Scope, compatibility, and remaining work

Go2, Static Physics beyond the S4 retirement, generic RL, Batch/Device/Vectorization, GeoPhys internals, Renderer implementations, and Physics × Renderer interoperability were not modified. Current Flora and Renderer claims remain limited to their pre-existing capability contract. No PPO target or training workflow is added. S4.5-B remains responsible for separate learning/rendering workflow cleanup and any additional caller migration after its own review.

Current API removals are listed in the migration appendix: the private trajectory task-plan module/helpers, private recorder helper exports, grouped historical collector, and retired Stage 11/provider-private recovery invocations. Their exact recoverable source is listed in the recovery manifest. v1.0.1 compatibility treatment remains a maintainer release decision; no frozen release documentation or qualification label was edited.

Resource runs were serial. The latest snapshot showed about 5.2 GiB available and low memory/I/O PSI. No ATA/SATA/read-write error lines appeared in the retrieved recent kernel journal, which does not establish that the known single-disk `/dev/sda` / `ata5` BadCRC risk or independent-backup limitation is resolved. Both remain **OPEN**.

S4.5-A is local and reviewable on `codex/p2-0-b-s4-5-a-developer-workflows`; implementation commit `5d57272d1ce7469bb214cf185137853a7eb6deb0`. The report and capability overlay are a separate follow-up documentation change. Nothing has been pushed, S4 is not integrated, and `main`/`v1.0.0` remain unchanged.
