# GeoChora P2.0-B S4.5-A Review and S4.5-B Workflow Consolidation

> **Current-status amendment (2026-10-17):** this report records the S4.5-B
> implementation review at its original local-candidate state. The selected
> release-candidate target is now v1.1.0 under a project-specific policy, and
> the S5-A version alternatives below are historical context. See the current
> [v1.1.0 release-candidate package](../../releases/v1.1/README.md). This
> amendment does not integrate or publish the candidate.

Date: 2026-10-17
Status: S4.5-A integration recommended, awaiting maintainer decision; S4.5-B is local and unmerged.
S4.5-A review head: `59105726c6ec28f467b637b7124f667a6fdd6b52`
S4.5-B implementation commit: `929dd8fafe8dca5b0f375341045501c0a8eed9c7`
S4.5-B branch: `codex/p2-0-b-s4-5-b-workflow-consolidation`

This report separates the S4.5-A review from the S4.5-B implementation. Neither change was pushed or merged. `main` and the annotated `v1.0.0` tag remain untouched.

## S4.5-A final review

The canonical `public/develop` ref was fetched and read back as
`0ff2d846a36c7014d2b40a530f52d99e64266ff9`. The local S4.5-A chain is
`0ff2d846 → 5d57272d1ce7469bb214cf185137853a7eb6deb0 →
59105726c6ec28f467b637b7124f667a6fdd6b52`; ancestry is valid. The second
commit adds the review receipt and current capability/docs overlay. It does not
change task execution source.

Review of the implementation and its receipts found:

- PickCube and NutAssembly use the selected public `make_env` routes and keep
  their task-owned Artifact, Runtime, controller and recording contracts.
- NutAssembly's example admits only guarded `step_expert()`. Task outcome,
  expert lifecycle, and H5 validity remain distinct.
- The existing recorder and canonical H5 format are reused. Storage
  roundtrip is not called D0 reconstruction.
- Old task routes fail explicitly; there is no silent UID redirection.
- The ten S4.5-A recovery entries were checked against their recorded blobs
  and SHA-256 values. The PickCube receipt is
  `workspace/maintenance/p2_0_b_s4_5_a_20261016/5d57272d/pickcube_mujoco_seed31.h5`:
  470 transitions, 471 boundaries, `T+1` valid, H5 SHA-256
  `e22bcadbb142c81f2bdd8f12a432b82b22cef0c25ddeba8cec29f764bca87ae8`,
  artifact SHA-256 `fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4`,
  task success true, measured lift `0.1060650257 m`, and expert complete.
  The source is `5d57272d`; the receipt explicitly does not requalify P1.6 or
  claim D0.
- That H5 preserves controller identity
  `76108c78b8159391e448ad9f49050bed42fd7a86e0e00a0520083b4e5efb02e9`,
  solution identity
  `514a5ed3bc0d289761ef88a00b1e7c11df2795133506ab148db9ab8e98e55241`,
  resolved configuration identity
  `0ae9a147c5712846ea5a3fc8acf85059e283cc23b453feb618603265b428367f`,
  and 17 source-file SHA-256 entries. Its logical identity is
  `a71f0af2817f88e9f0c318e0103addb568202c61f297f4edd6ba671b15a3ebee`.
- The NutAssembly two-step MuJoCo smoke is an expected incomplete result:
  exit 1, `truncated=true`, and task, planned trajectory, outcome, and expert
  completion all false. It is not full-route acceptance.

The S4.5-A provider-free suite was reported and rechecked at 129 passing tests.
The current combined suite below also covers S4.5-B. The S4.5-A review found no
duplicate Artifact/Runtime/Recorder contract and no task execution change.
Resource documentation now states that Linux `RLIMIT_AS` is a per-process
virtual address-space cap, not RSS or an aggregate process-tree cap; CPU time
is per process and the real-time alarm bounds the coordinating process.

**Recommendation:** S4.5-A is ready for a normal fast-forward after maintainer
approval. At review time, `public/develop` still equals `0ff2d846`. If it still
does and the ancestry check passes, the exact integration commands are:

```bash
git fetch public
test "$(git rev-parse public/develop)" = 0ff2d846a36c7014d2b40a530f52d99e64266ff9
git merge-base --is-ancestor public/develop 59105726c6ec28f467b637b7124f667a6fdd6b52
git push public 59105726c6ec28f467b637b7124f667a6fdd6b52:refs/heads/develop
git ls-remote public refs/heads/develop
```

Expected remote `develop`: `59105726c6ec28f467b637b7124f667a6fdd6b52`.
If the first command or ancestry check reports another baseline, stop and
review the new ref. No integration was performed in this task.

## S4.5-B implementation

The implementation is commit `929dd8fafe8dca5b0f375341045501c0a8eed9c7`,
whose parent is the reviewed S4.5-A head `59105726…`. The task directories and
the Core/provider boundary were not changed.

The root `examples/` tree is now:

```text
examples/
├── README.md
├── _common.py
├── learning/
│   └── pendulum_sb3.py
├── recording/
│   ├── inspect_h5.py
│   └── record_expert.py
├── rendering/
│   ├── pendulum_parallel_rgb.py
│   └── pendulum_single_rgb.py
└── tasks/
    ├── nut_assembly.py
    └── pick_cube.py
```

Learning delegates to the existing `task_env.script.rl.pendulum_ppo` runner;
it adds no learner or training algorithm. Recording inspection uses the
canonical H5 reader. Both rendering examples use the existing Renderer and
provider paths. The scalar example constructs `pendulum-v1` through public
`make_env`; the batch example delegates to the current Pendulum-only
`render_parallel` route. No manipulation-task renderer route or
Physics × Renderer interoperability is claimed.

### Script and caller disposition

| Path or route | Disposition and current callers |
| --- | --- |
| `task_env.script.render_single` | Historical CLI retired with exit 2. The prior CLI used the historical factory for Pendulum and `pick-cube-v1`; current Pendulum scalar use is in `examples/rendering/pendulum_single_rgb.py`. `pick-cube-v1` is not redirected. No remaining production caller was found. |
| `task_env.script.camera.static`, `camera.bound` | Historical PickCube camera routes retired with exit 2. Their only shared executable dependency was `camera/_common.py`; no current production callers remain. Camera contracts remain available for Artifacts that declare camera observations. |
| `task_env.script.camera_lighting_probe` | Historical PickCube/private-renderer probe retired with exit 2; no current caller or public replacement. |
| `task_env.script.camera._common` | Deleted. Its old blob and source hash are in the recovery manifest. |
| `task_env.script.render_parallel` | Retained as the current Pendulum batch CLI. Its callable `main` accepts optional argv for wrapper delegation; default parser behavior and `None` return behavior are preserved. |
| `task_env.script.render_input_probe` | Retained as a standalone Taichi Forge window-input probe; it does not construct TaskEnv or test renderer/provider interoperability. |
| `task_env.script.rl.pendulum_ppo` | Retained. Its `main` accepts optional argv for the wrapper; default CLI behavior and runner semantics remain. RSL-RL remains generic and requires explicit `--env-id`. |
| `task_env.script.planner` and `task_env.script.trajectory.planning.*` | Retained selected planning routes; `planner.py` delegates to PickCube planning, and NutAssembly uses guarded `step_expert()`. No duplicate builder is introduced. |
| `task_env.script.recorder` and `task_env.script.trajectory.record` | Retained selected recording route; the compatibility command delegates directly to the canonical recorder CLI. |
| `task_env.script.env.*`; trajectory `record`, `convert`, `replay`, `merge` | Retained. Generic environment construction and offline operations remain separate from selected task examples and H5 inspection. Historical replay remains explicitly historical. |
| `task_env.script.stage11`, `stage11_socket` | Already explicit retired stubs from S4.5-A; unchanged in this stage. Their exact recovery identities remain in the S4.5-A manifest. |

The final `task_env/script/` inventory is:

```text
__init__.py  _bootstrap.py  environment.py  planner.py  recorder.py
camera/{__init__.py,static.py,bound.py}  camera_lighting_probe.py
env/{__init__.py,_common.py,single_inline.py,single_from_file.py,
     parallel_inline.py,parallel_from_file.py}
render_single.py  render_parallel.py  render_input_probe.py
rl/{__init__.py,pendulum_ppo.py,rsl_ppo.py}
stage11.py  stage11_socket.py
trajectory/{__init__.py,__main__.py,commands.py,record.py,convert.py,replay.py,
            planning/{__init__.py,_common.py,pick_cube.py,nut_assembly.py}}
```

`camera/_common.py` was removed; the four historical rendering/camera command
paths remain as explicit error stubs where they have a stable import path.

The old camera helper had exactly two current imports, from the retired
`camera.static` and `camera.bound` commands. Repository search after migration
found no active imports of it. The full CLI/source mapping is recorded in
[`p2_0_s4_5_b_source_recovery.json`](p2_0_s4_5_b_source_recovery.json).

### Validation and bounded results

| Check | Result |
| --- | --- |
| Provider-free task, recording, renderer-contract and workflow suite | **PASS** — 146 tests, 6 subtests, 1 upstream Taichi locale deprecation warning, 158.32 s. Renderer endpoint substitutions are fake-runtime contract tests, not native rendering evidence. The suite ran serially under an 8 GiB per-process address-space cap, 330 s CPU cap, and 360 s outer wall cap. |
| New workflow unit tests | **PASS** — 8 tests, including RSL explicit-task parsing, retired CLI errors, Linux-only limits, learner/render delegation, scalar `make_env` route, and H5 inspector success/failure. Included in the 146-test suite. |
| Retired command direct invocation | **PASS** — `render_single`, `camera.static`, `camera.bound`, and `camera_lighting_probe` each exit 2 and print retirement/recovery guidance. |
| PickCube/NutAssembly and Core source closure | **UNCHANGED** — no S4.5-B diff in `task_env/tasks`, `task_env/runtime`, `task_env/alg`, `task_env/vectorization`, `task_env/render`, `task_env/objects`, `GeoPhys/src`, or `GeoPhys/test`. Full PickCube and NutAssembly routes were not repeated. |
| Native scalar rendering example | **PASS_BOUNDED_RENDER_SMOKE_NOT_QUALIFICATION** — Pendulum, GeoPhys CPU, scalar TaskEnv, rasterizer RGB; 32×24 finite float32 frame, reset plus one zero-torque step. Task success false for this one-step smoke; no expert is involved. |
| Native batch rendering example | **PASS_BOUNDED_RENDER_SMOKE_NOT_QUALIFICATION** — Pendulum, GeoPhys CPU, `merged_scene`, rasterizer RGB; one world, one step, 32×24 frame. Does not establish other provider/backend or headed-window support. |
| Native learning example | **PASS_BOUNDED_SMOKE_NOT_QUALIFICATION** — existing SB3 runner, Pendulum, GeoPhys CPU, `merged_scene`, two environments, one update/four timesteps, seed configuration 73 (runner records its worker seed 75). Existing summary, return H5 and checkpoint finalized. This is wiring only, not training/convergence qualification. |
| Current offline H5 inspection | **PASS** — inspected the S4.5-A PickCube H5: canonical schema, 470 transitions/471 boundaries, valid `T+1`, storage roundtrip PASS, D0 NOT_ASSESSED. |
| Current-source NutAssembly short-run gate | **EXPECTED FAIL / PASS GATING** — exact S4.5-B HEAD `929dd8f`; MuJoCo seed 19, horizon 2; exit 1 with truncation and all task/trajectory/outcome/expert completion fields false. |
| Source/docs checks | **PASS** — `compileall`, `git diff --check`, 19-file relative Markdown link check, and four retired-command subprocess checks. |

The provider-free suite also retains the trajectory CLI result-gating regression:
an incomplete or failed task exits nonzero even when its H5 is successfully
finalized; recorder validity does not turn task failure into success.

The one-update SB3 output is preserved under
`workspace/maintenance/p2_0_b_s4_5_b_20261017/pendulum_sb3_smoke/`:
`summary.json` SHA-256 `3496cfc76a886dcbe5337fef27daea0d36a3d11e59f9bd4fdac9fe6481571654`,
`return_curve.h5` SHA-256 `e87a3100cf8b7d775932ebf14749c4f4a6e8336ee7c1db314fddfee1b45c6c96`,
and checkpoint SHA-256
`361069281b5ed745f89d031933e220edc3e7c52e760e36922b9f3b3b62d0e61d`. These
ignored outputs are not committed.

## API and capability status

The public task UIDs, TaskArtifact identities, task outcomes, generic batch
contracts, learning adapters, Renderer Registry, Camera API, and provider APIs
are unchanged. Explicit current migration entries cover the old renderer and
camera CLI behaviors and the deleted private camera helper. The existing
`--memory-limit-mb` example flag remains an alias; the clearer
`--address-space-limit-mb` name was added. Direct compatibility for the retired
script options and imports must be decided in the v1.0.1 migration review.

Supported workflow intersections demonstrated by this candidate are:

| Workflow | Demonstrated intersection | Evidence limit |
| --- | --- | --- |
| Selected manipulation | PickCube P1.6 and NutAssembly Outcome V1 through current public task APIs | S4.5-A receipts; no new full routes in S4.5-B because selected source closures are unchanged. |
| Recording / inspection | Existing selected expert recorder and canonical H5 reader | H5 schema, storage and boundary checks only; not D0. |
| Learning | Pendulum / GeoPhys CPU / `merged_scene` / existing SB3 runner | One update, four timesteps; no training qualification. |
| Rendering | Pendulum / GeoPhys CPU / scalar or `merged_scene` batch / rasterizer RGB | One-frame smoke each; no Flora, selected manipulation, other-provider or Physics × Renderer claim. |
| RSL-RL | Generic CLI and adapters | Explicit task UID is required; no native training run. |
| Camera | Camera and CameraSpec contracts remain | Selected manipulation camera observations are not qualified. |

## S5 preflight and open risks

Before S5, obtain maintainer review for both local stages; decide v1.0.1
compatibility treatment for the retired CLI/import identities; refresh the
public ref and capability overlay; verify that release docs and frozen
v1.0.0/Evidence remain unchanged; and run the release-specific preflight only
after approved integration. S4.5-B does not publish a release.

The known `/dev/sda`/`ata5` BadCRC risk and the lack of a verified independent
backup remain **OPEN**. The recent kernel scan showed no matching ATA/SATA or
read/write error in its 45-minute window; this does not resolve that risk.
Memory available after bounded runs was about 4.0 GiB, swap remained available,
and the latest memory/I/O PSI averages were low. No broad training, GPU,
checkpoint inference, native RSL run, Renderer interoperability, S5 work, or
full task acceptance rerun was performed.
