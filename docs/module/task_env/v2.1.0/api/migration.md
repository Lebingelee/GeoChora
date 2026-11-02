# TaskEnv migration notes

## Selected reference UIDs

Use `pick-cube-p16-reference-v1` for the current PickCube reference and `nut-assembly-outcome-reference-v1` for the current NutAssembly outcome-oriented reference. The old selected UIDs `pick-cube-v1` and `nut-assembly-square-v1` fail explicitly in `make_env`; no silent replacement is performed. Historical source and behavior remain recoverable from the versioned history/tag records.

`BaseTaskEnv` and existing import names remain available through the 2.x line while callers move to the single `SelectedReferenceEnv → RuntimeSession → provider adapter` route. Their eventual deprecation/removal is a 3.0 planning item, not part of this candidate.

## Configuration migration

New selected-task callers should pass nested `execution`, `episode`, and `task` mappings. Existing `recipe` / `environment` and supported flat aliases are normalized by the common resolver. Do not send duplicate aliases with different values. The precedence and complete renderer mapping are specified in [configuration](configuration.md).

PickCube's selected default controller profile is `r3_continuous_v1`; selecting `r1` is explicit. Provider, backend, device, source manifest, renderer, and task parameters retain separate identities. A recorded configuration is not a task artifact or a new source identity.

## Recording and historical data

Continue to read historical H5 schemas using their original readers and versioned contracts. The new resolved configuration field does not relabel old files, rewrite historical identities, or upgrade a storage roundtrip into replay or task-success evidence. Preserve T transitions and T+1 boundary observations and use an independent reader when the workflow requires one.

## Task and benchmark ownership

PickCube and NutAssembly remain task-owned references on the Core route. LIBERO-specific source binding, action replay, and benchmark semantics remain in `bench_deploy/libero`; no generic LIBERO task UID is introduced by this candidate. The next API work will complete TaskDefinition migration for PickCube and NutAssembly, share the public construction capability with LIBERO, and compatibility-check other lightweight tasks. See [current scope](../planning/current-scope.md).
