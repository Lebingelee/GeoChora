# LIBERO benchmark deployment

This package owns LIBERO source bindings, reset and object semantics, task
controllers, optional task policy, and benchmark evidence checks. Runtime,
Recorder, and generic lifecycle behavior remain owned by `task_env/`.

## Current accepted boundary

`ACCEPTED_BOUNDED_R07_A123_TECHNICAL` covers the frozen A-stage environment and
upstream-control-flow evidence for tasks 1–3 on MuJoCo and GeoPhys CPU. The
accepted A replay uses the final V6 OSC profile and PandaGripper v1 mapping;
V7 rim control and V8 Solution remain opt-in. Task 2 GeoPhys has one accepted
exception for this frozen replay: before its first finger-to-cabinet contact
(action 82), its TCP differs from upstream by 33.143/37.916 mm position and
229.074/259.412 mrad orientation (P95/maximum). This exception does not establish
general provider parity. Task success and new Qualification are not
established. File-specific license and attribution for the `wine_bottle` and
`wine_rack` model files remain unresolved. High-precision tracking and
autonomous Solution success remain optional; tasks B/C and Isaac Sim are
deferred.

The CLI's default `--run-worker` path is the bounded D01 joint-space diagnostic;
it is not the accepted A replay route, and the CLI does not regenerate the
frozen A action sequence. The A replay evidence remains in its acceptance
record. The CLI's `--task-solution` path selects the optional V8 policy.

## Current route

1. `asset/benchmarks/libero/tools/source_bundle.py` verifies the pinned source
   and writes the bounded task recipe.
2. `environment.selected_reference.build_libero_selected_candidate()` composes the
   TaskEnv `SelectedReferenceEnv` route and binds LIBERO source/reset semantics.
3. `script/cli.py` runs the bounded worker or reads a closed result bundle.
4. `trajectory/reader.py` validates task-specific result semantics on top of
   the existing TaskEnv record/readback owners.

No parallel Runtime or Recorder is maintained here. LIBERO asset names,
source hashes, reset sampling, contact policy, and task thresholds remain
task-owned.

## Active versions and recovery

The D01 CLI route uses `LiberoMixedControllerV1`; the accepted A reference
profile is `LiberoMixedControllerV6`, and optional rim control is V7. The only
active Solution class is optional `LiberoPickPlaceSolutionV8`; V5–V7 identity
payload builders remain as internal dependencies because V8 binds their frozen
parent hashes.
`trajectory/reader.py` accepts the current D01 result schema and optional V8
Solution schema. It does not dispatch historical worker or Solution versions.

Retired implementations are recoverable from input HEAD
`65891af449918e7162c78dec7c01a3bc0b7eecd0`; for example:

```sh
git show 65891af449918e7162c78dec7c01a3bc0b7eecd0:bench_deploy/libero/solution.py
```

The R-route documentation snapshots are byte-preserved under
[`docs/archive/phase_ii_01_r_routes/`](../../docs/archive/phase_ii_01_r_routes/README.md)
with source paths, byte counts, and SHA-256 values.

## Build a recipe

From the repository root, with the pinned LIBERO and robosuite source installed
and verified:

```sh
PYTHONPATH=. python asset/benchmarks/libero/tools/source_bundle.py recipe \
  --manifest asset/benchmarks/libero/source_manifest.json \
  --target /local/audit/libero-pilot \
  --task-input bench_deploy/libero/artifacts/task_input.json \
  --output /local/audit/libero-pilot.recipe.json
```

The recipe records the bounded A123 technical status and its remaining limits.
Creating the recipe does not run native physics or produce new trajectory
evidence.

## Run or read a bounded diagnostic

Use the frozen run package, its resource limits, and the shared native lock.
The normal entry point is:

```sh
PYTHONPATH=. python -m bench_deploy.libero.script.cli --help
```

The CLI default `--run-worker` route is the bounded D01 joint-space diagnostic;
it does not regenerate the accepted A-stage replay. `--task-solution` selects
the optional V8 demonstration-derived policy. The accepted A-stage reference
profile and task 2 exception are recorded in
[`20261101_r07_a123_sol_acceptance.md`](../../docs/maintenance/20261101_r07_a123_sol_acceptance.md).
A short smoke or completed worker bundle is not task success, provider parity,
or Qualification.

## Responsibilities

| Package | Responsibility |
| --- | --- |
| `artifacts/` | Task source contracts, recipe inputs, and source provenance |
| `assembly/` | Pinned source verification and MJCF composition |
| `controllers/` | Reference OSC, gripper mapping, and optional rim-control profile |
| `environment/` | Candidate construction, public Runtime binding, and reset glue |
| `objects/`, `robots/` | LIBERO object/fixture and mounted Panda semantics |
| `observations/`, `planners/`, `tasks/` | Public state projection, planner configuration, predicates, optional Solution |
| `trajectory/`, `diagnostics/`, `script/` | Task result validation, focused regression coverage, CLI/worker entry |

Historical R00–R07 decisions and attempt details are indexed from
`docs/module/task_env/goal/Phase_II_01/README.md`; fixed source commits remain
the recovery route for retired implementations.
