# GeoChora asset and scene preparation

Read this reference when the upstream task needs a real USD asset or scene before candidate construction. Use sibling `scene-orchestration`, `asset-creation`, and `asset-material-creation` for their production methods. The host agent orchestrates them; GeoChora TaskEnv remains the owner of task semantics, reset, control, runtime admission, recording, and review evidence.

## First supported target and scope

The first integration target is one fixed-base Panda, one real rigid graspable object, and a fixed support surface. The object's actual visual geometry and collision representation must be consumed by Isaac. Preserve the source object identity, dimensions, mass/physical assumptions, materials, and any conversion losses. A texture over the built-in cube or a proxy box is not evidence for the real asset.

This reference declares an implementation target, not an already-supported runtime route. Check the current candidate/compiler/admission code and exact capability matrix before running. The existing frozen F06 PickCube manifest and `cube-v1` route are regression inputs; registering a USD in the catalog does not admit it for execution. Use a separately versioned asset-scene admission profile through existing Core owners.

## Workspace and ownership

Keep each preparation job under ignored `workspace/asset-preparation/<task-id>/<job-id>/`:

```text
request.json
src/        # frozen source, authoring files and recipes
output/     # asset/instance layout supplied by the three skills
handoff/    # immutable GeoChora delivery and semantic binding references
evidence/   # raw checks, logs, images, versions and hashes
```

Deliveries must resolve without authoring-library paths or files outside the delivery's declared relative dependency closure. Preserve original source/recipe/checker hashes and applicable source terms in the handoff. Do not copy generated assets into the skill folders or third-party submodules.

Use `task_env.artifacts` for versioned identities/contracts, `task_env.assembly` for validated deliveries and immutable source snapshots, and the owning task for semantic entity/frame bindings. Keep `task_env/script/agent` as thin orchestration. Candidate/Oracle/Judge packaging remains in the existing task workspace and review workflow.

## Robot and task adaptation

The distributed scene skill's `left/right` arms, `standard_rig`, fixed head camera, and old instance `task.py` interface belong to its original project. For GeoChora, supply an explicit Panda profile and bind the real articulation root, base support, DOFs, drives/limits, hand/TCP, target body, and support frame. Bind cameras only when the chosen route actually admits them. Do not fabricate a second arm or mandatory head camera to satisfy the old config checker.

Reuse an existing approved task brief and its randomization scope. New visual/layout choices follow the scene skill's design review; technical adapter work already authorized by the maintainer can proceed. Asset preparation does not authorize changing task success thresholds or shrinking the reset distribution after failures.

## Required handoff facts

Reference, rather than independently duplicate, the loader's strict delivery contract:

- request/task and asset/source identities, revision, origin and applicable source terms;
- entry file/prim, variants, file inventory and exact USD/material/texture closure hashes;
- recipe, checker, options, report and tool-version identities, with input/output provenance and conversion losses;
- explicit semantic role-to-prim bindings and robot/profile identity;
- task-owned initial/reset state and success semantics;
- raw evidence with scope and status: pass, fail, execution error, not run, or not applicable.

Unknown provenance, stale bytes, missing dependencies, absent required prim roles, wrong robot profiles, and empty required claim sets must reject before a native task launch. Provider representation selection is not runtime admission.

## Preparation checks and their limits

`asset-creation/scripts/verify_claims.py` covers supplied geometry/property assertions. It uses NumPy/OpenUSD, writes a result JSON, and can pass an empty claim list; enforce nonempty required coverage and retain the exact claims, result, exit status and checker/input hashes. It does not establish collision, support, provenance, complete material correctness, or task success.

`scene-orchestration/scripts/check_usd_static.py` launches Isaac and measures five seconds of physics with selected robot roots frozen. Its stock `--config` schema requires two arms. For a Panda QA run use an explicitly adapted profile, or the Python `roots` interface with a separate structural validator. Preserve the full result dictionary, logs, checked object count and frozen roots. A successful frozen-robot stability check does not prove operational graspability.

Run physics QA on an isolated copy through the existing shared native lock, resource gates, timeout and process-group cleanup. Never use its advanced/frozen stage as a task reset state, and do not perform hidden settling before the first task step.

View a nonblank actual Isaac render of the final delivery for applicable geometry/material checks. Blender/process previews are development evidence. Asset QA rendering is distinct from task RGB/video support; do not label a state-only task route as camera-qualified.

## End-to-end completion

1. Validate and relocate the exact asset/scene delivery, with required structural, material, geometry and physics checks.
2. Compile and admit its explicit task/scene/source identities through the existing selected environment and runtime route.
3. Pass a fresh-process smoke with actual geometry/collision and recorded reset, task/Expert outcomes, and cleanup.
4. Pass the existing four candidate checks with 20 distinct declared solved seeds under the final identities and unchanged task criteria.
5. Record a successful Oracle, inspect/read back its actual versioned H5 schema, and keep task/Expert receipts separate from recorder stop flags.
6. Prepare and independently verify a portable Stage-1 package with Human decision pending. Preserve historical rounds, failures, unsupported checks and source snapshots; do not reuse mock/cube success as proof of new-asset success.

Use the existing `task-env-experiment-evidence` skill for Artifact/Judge boundaries. Integration is complete only for the exercised task/asset/provider/profile intersection. Asset intake alone, one native demo, a generated H5, and a pending package are separate milestones.

## Source package integrity

The original archive SHA-256 is `86855fb83b4225846913a10efcaad9181cf013baa29d9ea9f0c8c529fe4987c5`. Retain it and its original manifest under ignored `workspace/incoming/asset-skills-20261104-86855fb83b42/`. The manifest lists `asset-material-creation/references/drink-ring.md`, but the archive does not contain that file. That optional reference remains unavailable; do not invent its contents or claim the original manifest verifies it. The installed adaptation record captures this omission and exact changed file hashes.
