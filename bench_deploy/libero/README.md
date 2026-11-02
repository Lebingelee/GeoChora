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

The CLI runs an explicitly selected frozen action sequence for task1, task2,
or task3 on MuJoCo or GeoPhys. Task2/3 also require the accepted source reset
sample. The optional V8 policy uses the same runner and result format; it is
not selected by default.

## Current route

1. The pinned upstream LIBERO `ControlEnv` and robosuite model owners build the
   source MJCF during source preparation; the input plan records its task,
   source revisions, model hash, and asset closure. This package does not
   reconstruct the MJCF from fragments.
2. `asset/benchmarks/libero/tools/source_bundle.py` verifies pinned source
   bytes and installs/verifies the source closure.
3. `environment.selected_reference.build_libero_selected_candidate()` binds
   the source plan and LIBERO reset semantics to the existing TaskEnv route.
4. `script/cli.py` runs a frozen A action sequence or the optional V8 policy.
5. `trajectory/reader.py` validates task-specific result semantics on top of
   the existing TaskEnv record/readback owners.

No parallel Runtime or Recorder is maintained here. LIBERO asset names,
source hashes, reset sampling, contact policy, and task thresholds remain
task-owned.

## Reset realization record

The normal-reset receipt uses `libero-normal-reset-realization-v2`. It stores
the actual seed, selected `.pruned_init` row and hash, source and BDDL hashes,
`ResetSampleV1` identity and state, placement draws, and asset geometry hashes.
The fixed `libero-normal-reset-order-v1` algorithm is described here instead of
being copied into every receipt.

For each reset, the sampler uses a task-seeded `numpy.random.RandomState`. It
consumes seven zero-magnitude Panda arm-noise draws before placement sampling,
then samples movable objects in BDDL order with horizontal-radius margins and
the upstream overlap rule. It samples fixtures in BDDL order without overlap
rejection, applies the selected `.pruned_init` row, restores source simulation
time, and forwards derived state without integrating physics. These draws are
retained even though the pruned row overwrites movable-object placement.

## Active versions and recovery

The active A reference profile is `LiberoMixedControllerV6`; optional rim
control remains V7. The only active Solution class is optional
`LiberoPickPlaceSolutionV8`; its private V5–V7 parent-hash data remains inside
identity construction to preserve existing V8 hashes. Only
`solution_identity_v8` is exported as the identity entry point. The independent
reader accepts one current replay-result schema. Retired D01 and V8 bundle
formats remain recoverable from the frozen input commit.

Retired implementations are recoverable from input HEAD
`b5e93509b758d523bb8328e9104f6b82ea086570`; for example:

```sh
git show b5e93509b758d523bb8328e9104f6b82ea086570:bench_deploy/libero/trajectory/reader.py
```

Unused `LiberoOperationalSpaceConfigV1` defaults are summarized in the
[controller profile history supplement](../../docs/module/task_env/v2.1.0/history/r_route_originals/libero-controller-profile-history.md)
and recoverable from that same input commit.

The R-route documentation snapshots are byte-preserved under
[`docs/archive/phase_ii_01_r_routes/`](../../docs/module/task_env/v2.1.0/history/r_route_originals/README.md)
with source paths, byte counts, and SHA-256 values.

## Source bundle commands

The old `source_bundle.py recipe` command and its v1 deployment metadata are
retired. The source bundle CLI still supports `build-manifest`, `install`, and
`verify`; use `assembly.official_model` for the pinned upstream model capture.
That capture currently records exact XML and builder receipt only. A complete
source-preparation route must also emit and validate the plan and closure before
its output is used for task execution.

## Capture an upstream source model

Run source preparation from a fresh Python process with local checkouts at the
pinned LIBERO and robosuite revisions. The upstream `ControlEnv` builds the
model; the command captures its exact XML, records the options and closure
identity, and closes the upstream environment before writing the result:

```sh
PYTHONPATH=. python -m bench_deploy.libero.assembly.official_model \
  --task task2 --libero-source-root /local/LIBERO \
  --robosuite-source-root /local/robosuite \
  --source-closure-sha256 <verified-source-closure-sha256> \
  --output /local/task2-source-model
```

This captures the model and its build receipt. The pinned source-bundle and
asset-closure verifier remains responsible for verifying and packaging the
referenced bytes.

## Replay frozen actions or read a result

Use the frozen run package, its resource limits, and the shared native lock.
The normal entry point is:

```sh
PYTHONPATH=. python -m bench_deploy.libero.script.cli --help
```

Use the selected source build, action sequence, task, and provider explicitly:

```sh
PYTHONPATH=. python -m bench_deploy.libero.script.cli --run-replay /local/run \
  --task task2 --provider mujoco --actions /local/task2-actions.json \
  --reset-sample /local/task2-reset.json --source-xml /local/source.xml \
  --composition-plan /local/composition-plan.json --install-root /local/libero \
  --init-path /local/task2/install/init.pruned_init
```

`--solution` selects optional V8 and uses the same runner and result reader.
The accepted A-stage reference profile and task 2 exception are recorded in
[`20261101_r07_a123_sol_acceptance.md`](../../docs/module/task_env/v2.1.0/maintenance/reviews/r_route/20261101_r07_a123_sol_acceptance.md).
A short smoke or completed worker bundle is not task success, provider parity,
or Qualification.

## Responsibilities

| Package | Responsibility |
| --- | --- |
| `artifacts/` | Task source contracts and source provenance |
| `assembly/` | Official source model intake and compile-first model verification |
| `controllers/` | Reference OSC, gripper mapping, and optional rim-control profile |
| `environment/` | Candidate construction, public Runtime binding, and reset glue |
| `objects/` | LIBERO object/fixture layout facts used by source reset |
| `artifacts/`, source manifest | Pinned Panda, mount, gripper and source asset identities |
| `tasks/` | Public observation projection, predicates, optional Solution |
| `trajectory/`, `diagnostics/`, `script/` | Task result validation, focused regression coverage, CLI/worker entry |

The former `robots/mounted_panda.py` and `observations/libero.py` files were
planning-only dictionary wrappers; the installed robot assets and runtime
observation schema are owned by the pinned source manifest and TaskEnv route.
They are recoverable with the frozen input commit below, but are not current
deployment modules.

Historical R00–R07 decisions and attempt details are indexed from
`docs/module/task_env/v2.1.0/history/phase_ii_01/README.md`; fixed source commits remain
the recovery route for retired implementations.
