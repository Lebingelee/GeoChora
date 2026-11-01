# Task Harness CLI

Compose GeoChora's selected task, controller, expert and canonical recorder to
construct a bounded task candidate, inspect failures, record an Oracle, and
prepare a **pending** Stage-1 Human Judge package. The host agent follows
[the Harness Skill](../../../.agents/skills/geochora-task-harness/SKILL.md);
there is no LLM client, autonomous agent framework or replacement runtime here.

## Setup and entry points

Use Python 3.12 and a working GeoChora MuJoCo environment. Initialize the pinned
asset dependency with `git submodule update --init asset/external/mujoco_menagerie`.
The MuJoCo-only route needs numpy, scipy, gymnasium, mujoco, h5py, PyYAML and the
asset dependencies used by the existing PickCube task. Follow the repository's
dependency instructions; do not use editable installation (there is no root
package metadata). Linux and macOS are supported by the POSIX timer used for
recording; native Windows is not currently supported (use WSL).

Run files directly with the chosen Python executable; for library use add this
CLI directory and the Core root to `PYTHONPATH`. `--core-repo` must identify the
same clean checkout imported as `task_env`. Commit local implementation changes
before collecting evidence, and regenerate the catalog after changing commits,
machines or asset inputs. Do not weaken the clean-checkout gate.

```sh
CORE=/absolute/path/to/GeoChora
PY="$CORE/.venv/bin/python"
RT="$CORE/task_env/script/agent"
UP=/absolute/path/to/supplied-upstream
OUT="$CORE/workspace/harness/my-run"
export PYTHONDONTWRITEBYTECODE=1
mkdir -p "$OUT"
cd "$OUT"
"$PY" "$RT/catalog_query.py" --core-repo "$CORE" --providers mujoco --output "$OUT/catalog.json"
```

Add `--asset-bundle "$UP/asset_bundle.json"` when consuming the explicit synthetic
handoff below. Generate the candidate from the catalog's `spec_template` and
upstream requirements; do not copy a historical successful spec as a revision.
The [workflow](../../../.agents/skills/geochora-task-harness/references/workflow.md)
gives the complete reserve → check → revise → record → package commands.
All generated reports, inputs, H5, snapshots and Judge decisions remain in
ignored `workspace/` or outside the repository; no test fixtures are needed at
runtime.

| File | Responsibility |
| --- | --- |
| `harness_spec_schema.py` | Strict candidate JSON/YAML, findings and reports |
| `catalog_query.py` | Registry/provider catalog and source identity |
| `asset_check.py` | Asset UIDs, supplied bytes and capability vocabulary |
| `harness_compiler.py` | Deterministic `pick-lift-v0` Artifact/binding |
| `semantic_check.py` | Declared lift goal and positive/negative endpoint examples |
| `feasibility_probe.py` | Separate solved/invalid/expert_failed/unknown outcomes |
| `completion_facts.py` | Versioned raw completion facts and independent row/report validation |
| `check_candidate.py` | One candidate's four checks, with real reports |
| `construction_ledger.py` | Hash-bound per-round contexts, v0 compatibility, owner-repair continuation, five-round budget and escalation |
| `oracle_candidate.py` | Existing recorder, completion check and independent H5 inspection |
| `judge_package.py` | Portable evidence index and pending-only verification |
| `builtin_example_schema.py` / `harness_compiler.compile_builtin_pickcube_example` | Versioned built-in PickCube example input; delegates to the public Core UID and never creates a CandidateSpec |
| `builtin_example_validation.py` / `builtin_example_worker.py` | Bounded fixed-seed runtime example, existing Core Recorder H5, identity/finite/T+1 readback and separate task/runtime outcome facts |

## Built-in PickCube runtime example

`--execution harness --provider {mujoco,geophys,isaacsim,genesis,sapien}` selects
the versioned `pickcube-harness-example-v1` path. It compiles the exact example
input, then delegates construction to public `task_env.make_env` with UID
`pick-cube-p16-reference-v1`; the existing PickCube task, reset sampler,
solution, controller, RuntimeSession and Recorder remain their owners. This
path does not create a `CandidateSpec`, run the candidate/Oracle/Judge flow, or
weaken the separate `pick-lift-v0` 20-seed all-solved requirement. Runtime
validity and Task/Expert outcome are reported separately.

For runnable CPU/CUDA commands and optional-provider behavior, use the
[PickCube example matrix](../../../examples/README.md#workflow-matrix). The
current final headroom-identity 3×3 runtime evidence, task outcomes and limits
are in the [F06 matrix report](../../../docs/maintenance/20261101_f06_pickcube_harness_headroom_matrix.md).

Passing feasibility rows use `harness-feasibility-completion-v1`. The probe,
construction ledger and pending Judge verifier require raw task/expert outcome,
termination, fault, reset/step and cleanup evidence; they do not accept a
`classification` label or declared totals by themselves. Older rows without
those facts remain historical and unverifiable; regenerate evidence under the
current clean Harness commit instead of rewriting an old report.

## Supplied input contracts

Candidate fields come from `catalog.json` →
`template_details.pick-lift-v0.spec_template`; the dataclass is the executable
schema. Semantic examples are a JSON object with
`schema_version: harness-semantic-examples-v0`, boolean `synthetic`,
`goal_predicate: lift_height`, and `cases`: unique names, `cube_world_z_m`, and
boolean `expected_success`. Supply both negative and positive cases. Synthetic
endpoints test the checker, not equivalence to a source benchmark demonstration.

The ledger's task input includes `task_id` (matching the candidate), and relative
`asset_bundle` / `semantic_examples` filenames. The host agent also reads the
upstream's requested object, scene, initialization and goal to construct a spec.

The ledger keeps `harness-attempt-ledger-v0` readable for existing workflows.
Owner-level repair continuation writes `harness-attempt-ledger-v1`: every round
has its own clean Core/catalog/runtime/provider/spec/input context. The
`continue-owner-repair` operation requires a hash-bound receipt for the legacy
ledger, archived runtime refs, diagnosis, owner commit/diff, and input changes;
it reserves the next available round without replacing earlier failures or
open issues. A passing round does not automatically resolve a prior issue.
Ordinary task-local revisions remain supported; v1 revisions that change the
Core/catalog/input context supply that context explicitly.

Current **package preparation** supports the explicit synthetic handoff only:
`task.json`, `semantic_examples.json`, `asset_bundle.json` and referenced XML
assets in one upstream directory. The bundle requires
`schema_version: harness-mock-asset-bundle-v0`, `synthetic: true`, and `assets`.
Each asset has `uid`, `version`, relative `path`, byte `sha256`,
`template_kind: pick-lift-box-proxy-v0` and original `source_request_uid`.
The candidate binds its external `object_uid` and `asset_sha256` to that entry.
The XML body must be `PickCube`, with free joint `PickCube_joint`, an inertial
mass of 0.08 kg and box geom `PickCube_collision` of half-size 0.025 m per axis.
Treat additional asset semantics as an owner-reviewed extension, not a general
importer contract. The tool does not invent missing upstream assets.

## Scope and review

This is COMPOSE_EXISTING on the selected canonical-v0 Panda/PickCube route;
`ReferenceTaskBinding` remains an internal integration seam for maintainer review.
The strict `pick-lift-v0` candidate path is unchanged. The separate
`harness-builtin-pickcube-example-v1` mode below composes the same public task
factory and does not create a candidate, Oracle, or Judge package.
Only the `pick-lift-v0` table + one box-collision object template is implemented:
fixed z, 0.002 × 5 timebase, no extra fixtures, lift goal at most 0.105 m.
Reach/grasp values are diagnostics; lift is the sole success predicate.

### Built-in PickCube example mode

The built-in mode accepts only the public UID
`pick-cube-p16-reference-v1`, existing `r3_continuous_v1`, seeds 31/32/33,
and the task recipe's 0.002 s × 5 timebase. The checked-in example defaults to
1000 control ticks; a versioned run spec may choose a horizon from 1 through
1000 for a bounded smoke without changing that default. The compiler
delegates construction, reset sampling, evaluation, solution, controller and
recording to the existing Core PickCube owners. The current CPU routes are
MuJoCo and GeoPhys. Catalog entries for Isaac Sim, Genesis and SAPIEN are
requested routes with `runtime_tested: false` until exact source/runtime
execution is implemented and verified; presence in the catalog is not runtime
admission. Example Task/Expert failure is reported separately from a runtime
fault. It cannot enter the strict 20-seed candidate/Oracle/Judge path.

For the F06 Isaac USD source rebuild, invoke the source file directly so
`--help` does not import Core or start Isaac. The build runs under Isaac's
Python, uses the matching Core Python to expose shared dependencies, and keeps
Isaac's `pxr` package first:

```sh
CORE=/absolute/path/to/GeoChora
ISAAC_PY="$CORE/workspace/environments/isaacsim-6.2.0/bin/python"
CORE_PY=/absolute/path/to/geochora-py312/bin/python
"$ISAAC_PY" "$CORE/task_env/diagnostics/tasks/pickcube_isaac_usd_delivery.py" \
  --help
"$ISAAC_PY" "$CORE/task_env/diagnostics/tasks/pickcube_isaac_usd_delivery.py" \
  --core-python "$CORE_PY" \
  --source-package "$CORE/workspace/path/to/frozen-source-package" \
  --output "$CORE/workspace/path/to/derived-f06-usd"
```

The Core and Isaac interpreters must use the same Python major/minor ABI. An
existing filtered `GEOCHORA_CORE_SITE` overlay may be used instead of
`--core-python`. This operation validates and writes USD evidence only; it
does not launch `SimulationApp` or advance physics.

Generate a fresh catalog after each Core commit, then run the three fixed seeds
for one provider:

```sh
CORE=/absolute/path/to/GeoChora
PY=/path/to/python-3.12-with-geochora-dependencies
RT="$CORE/task_env/script/agent"
OUT="$CORE/workspace/harness/pickcube-example/mujoco"
export PYTHONPATH="$CORE/GeoPhys/src:$CORE"
"$PY" "$RT/catalog_query.py" --core-repo "$CORE" --providers mujoco geophys \
  --output "$OUT/catalog.json"
"$PY" "$RT/builtin_example_validation.py" \
  --spec "$CORE/examples/tasks/pick_cube_harness.json" \
  --provider mujoco --catalog "$OUT/catalog.json" \
  --working-tree-scope "$CORE/examples/tasks/pick_cube_harness_working_tree_scope.json" \
  --output-dir "$OUT/runs"
```

Use `--provider geophys` for the other CPU route. A clean checkout can use the
checked-in empty working-tree scope. A Goal run with one unrelated untracked
file must supply a separate versioned scope pinning its exact path and SHA-256;
tracked changes remain rejected. The legacy strict catalog validator still
requires a fully clean checkout. Each example episode holds the shared native
lock through worker process-group exit and writes a separate run receipt and
canonical H5.

A passing probe covers its declared seeds only. Preserve execution faults and
sampling-distribution revisions for Human review. Recording/storage validity is
not replay qualification, training readiness or approval. The existing
[Experiment/Evidence Skill](../../.agents/skills/task-env-experiment-evidence/SKILL.md)
owns the procedure; this CLI prepares candidates and never freezes or approves.
