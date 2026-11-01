# F06 PickCube Harness multi-backend example — PARTIAL<br>
<br>
**Result:** `F06_PICKCUBE_HARNESS_THREE_BACKEND_EXAMPLE_PARTIAL_PENDING_SOL_REVIEW`<br>
**Date:** 2026-11-01<br>
**Branch:** `develop-full`<br>
**Native execution source HEAD:** `2d4c55dfec32210e60a4846b4afd3d9797b5a320`<br>
**Frozen package:** `sol_f06_001`, expected input `4a642f71440a76a94a315db1304442dfe6ddcb1f`, prompt SHA-256 `8cb16b3537e1f39677e4ed28a86bb0424311158e7c9f2e84ed40a9a7e1c0ed45`

The versioned `pickcube-harness-example-v1` selects the existing public UID
`pick-cube-p16-reference-v1` and reuses its Task, reset sampler, readiness
solution, R3 controller, Core RuntimeSession and Recorder. The strict
`pick-lift-v0` candidate/Oracle/Judge gate remains unchanged. The F06 profile
is `r3_continuous_v1`, seeds 31/32/33, 1000 control ticks and five 0.002 s
physics substeps per control tick. Task/Expert outcome remains distinct from
runtime validity.

## Route matrix

| Provider | Seeds | Runtime and H5 evidence | Task/Expert outcome | F06 disposition |
| --- | --- | --- | --- | --- |
| MuJoCo CPU, `r3_continuous_v1` | 31 attempted; 32/33 not run | Seed31 repeatedly hit the QACC DOF13 execution-fault gate at 0.448 s; no formal R3 H5. Same-gate stop rule reached. | Execution fault; not a permitted task-only failure. | `FAILED_PER_MAINTAINER_DIRECTION`; preserve R3. The separate R1 diagnostic is excluded. |
| GeoPhys CPU, `r3_continuous_v1` | 31/32/33 | Three runtime-valid episodes, actual planned actions, H5 T+1, finite numeric data, independent cold read, close PASS. Route identity is recipe `f228895d500e42d4f5de3a878b859192d4f97ace00c6a45eddfb65e2c05576f8`, source revision `dade932e71835c48af4f6ba60d79c10c0ad0517f`. | All three report `gripper_readiness_timeout`; no task success. | Runtime route valid; task/Expert failures reported. |
| Isaac Sim 6.2, CUDA `cuda:0`, GPU PhysX, `r3_continuous_v1` | 31/32/33 | Three runtime-valid episodes, actual planned actions, H5 T+1, finite numeric data, independent cold read, App close and lock/worker-group release PASS. Route identity is recipe `aaade60365f67ddea7d0460732c62e45d2b6cdf219842550adeb042a354c56f2`, source revision `2d4c55dfec32210e60a4846b4afd3d9797b5a320`. Each supervised start records `OMNI_KIT_ACCEPT_EULA=YES`; acceptance is recorded in the Goal progress file. | All three report `above_pose_readiness_timeout`; no task success. | Runtime route valid; task/Expert failures reported. |

The required primary matrix calls for 9 H5 files. Six exist (GeoPhys 3/3,
Isaac 3/3); MuJoCo R3 has 0/3 because the maintainer chose to preserve the
failed R3 configuration, record the route failure, and continue other
backends. Therefore the example Goal is **PARTIAL**, not PASS. No R1
substitution, F07 work, training, or Qualification was performed.

## Per-file H5 evidence

The per-file validation receipt is
`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/f06_primary_h5_validation.json`.
For each existing H5 it confirms runtime identity fields, route-local
recipe/source/controller/solution identities, T+1, finite floating-point
datasets, planned-action count, and the existing independent cold-reader
receipt. GeoPhys canonical H5s were also loaded through the existing canonical
H5 reader; their recorded `simulation_time` arrays are finite and monotonic.
Isaac H5 stores the fixed 10 ms/control-tick timebase in the run identity and
the T+1 state boundary count.

| Provider / seed | Transitions / observations | Planned actions | H5 SHA-256 | Cold read |
| --- | ---: | ---: | --- | --- |
| GeoPhys / 31 | 954 / 955 | 48 | `1099d205fea092dc9cd6fbe338a92d1772b00d51aa2fa2793516c4b028365f45` | PASS |
| GeoPhys / 32 | 946 / 947 | 51 | `a0b8e2c7239d4532451445e92669b0217685bacb7dd15faccd5edd0aba5186a3` | PASS |
| GeoPhys / 33 | 950 / 951 | 49 | `b39876c70fd8fb1ad41a9a2976a73344217c1c2f87f8fbb0265afa30f8a4e6e8` | PASS |
| Isaac / 31 | 176 / 177 | 76 | `d5e41cb362178a2f8fd746fbe3d00553001a8b2c05b35471d69cf5625fafd489` | PASS |
| Isaac / 32 | 158 / 159 | 58 | `fbea69100ba27087f73c9b42b052f4d64e3aeab7d54169931b256fcd332bb53d` | PASS |
| Isaac / 33 | 165 / 166 | 65 | `8dcb3c64b087ef5a30d677a2859a1153a44699e223583449037a2d6a7ffa78f0` | PASS |

Exact `run.json`, `cold_read.json`, lock receipts, run plans, worker logs and
per-seed provider matrices remain under the ignored F06 workspace directory;
raw evidence was not staged or committed. The cumulative run ledger retains
all earlier failures and charges; seed33's completed worker result was
appended without rewriting prior entries.

## Trajectory and optional backends

The tracked plot generator is
[`f06_pickcube_trajectory_plot.py`](../../task_env/diagnostics/tasks/f06_pickcube_trajectory_plot.py).
It reads the seed31 GeoPhys canonical trajectory and Isaac task-env H5, plots
planned world TCP against post-step public EE pose and measured gripper
opening, and labels task/Expert failure. The MuJoCo panel labels the R3 QACC
failure and explicitly excludes the separate R1 diagnostic H5.

![F06 seed31 planned and measured TCP and gripper opening](../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/f06_seed31_trajectory.png)

Genesis and SAPIEN import probes both report the package missing in the
configured `geochora` Python environment. Their commands now return
`NOT_RUN_DEPENDENCY`, persist a preflight receipt, and start zero workers. No
optional engine was installed. Receipts are under
`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/optional_genesis_seed31/`
and `optional_sapien_seed31/`.

## Implementation and checks

The final native Isaac identity follows the local commits through
`20d8bd6d4cf685ecebb18029a37a4244b60b259d` (separate actuator-effort
readback) and `2d4c55dfec32210e60a4846b4afd3d9797b5a320` (18-step bootstrap
plan/H5-bound validation). Earlier local commits include the authorized
reset-Artifact identity repair `f22ba458627506ff678ffbaa99af681150c345e4`
and profile-specific native receipt repairs. After the native identity froze,
the closeout added only the example CLI wrapper/optional dependency preflight,
trajectory plotting helper, documentation and this evidence summary; no
Core runtime or provider behavior changed and no further native run was
started.

Checks for this closeout:

- `pytest -q examples/tasks/test_pick_cube_cli.py task_env/script/agent/test_builtin_example_mode.py` — 17 passed.
- `py_compile` and `compileall` for the touched example/plot and Harness owner files — PASS.
- Module Skill checker and skill-creator `quick_validate.py` — PASS after local-reference repair.
- Optional Genesis and SAPIEN preflights — `NOT_RUN_DEPENDENCY`, zero native starts.
- Seed31 plot generated and visually inspected; per-file H5 validation receipt — PASS for all six available files.
- TaskEnv Module Skill refresh receipt, including a read-only cold-start walkthrough, is retained at `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/task_env_skill_refresh_receipt.json`.
- `validate_docs.py` returned exit 1: it checked 18 immutable URLs and reported no link, anchor, JSON, protected-byte or frozen-URL error, but its docs-only scope rejected 283 cumulative code/asset differences and its 90-document count exceeded the frozen inventory limit. The complete log is preserved at `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/docs_validator.log`; this validator result is not a PASS.
- Final staged `git diff --check` passed. The exact local output HEAD/commit and validator disposition are recorded in the closeout ledger/progress after commit.

This report pairs tracked code/documentation commits with the exact ignored
Evidence paths above. It is a diagnostic example result pending independent
Sol review, not a formal task/provider qualification.
