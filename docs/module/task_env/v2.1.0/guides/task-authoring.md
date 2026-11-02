# Task authoring

A task owns its Task Artifact semantics: Entity/source references, action and observation contracts, reset distribution, timebase, task predicates, and evaluation. Reusable construction, runtime lifecycle, recording, and provider admission belong to the existing Core owners in `task_env/`.

## Existing public construction owners

- `task_env.environment.TaskArtifactDeclarationV1` declares the task-facing artifact contract.
- `task_env.assembly.ReferenceTaskDeclarationV1` binds the artifact to a named source and optional pure Controller.
- `task_env.make_env(uid, config=...)` is the public registered runtime entry.
- `SelectedReferenceEnv` owns the mutable task lifecycle; `RuntimeSession` and provider adapters own execution below it.

The declarations are not themselves provider admission or Qualification. Source bytes, asset identity, reset policy, provider capability, and a valid runtime profile remain separate checks.

## Example and boundaries

Read [`examples/tasks/declared_marker.py`](../../../../../examples/tasks/declared_marker.py) with the matching [developer workflow](../../../../../examples/README.md). It reuses existing Panda/table/box construction and registers through `make_env`. The example's `DeclaredPandaBoxEnv` adapter is internal; use it to understand composition, not as a new stable authoring protocol.

Keep benchmark-specific LIBERO construction and action semantics in `bench_deploy/libero`. Do not add a Core LIBERO UID, duplicate the factory, or read provider-private solver/renderer state. Use the [current scope](../planning/current-scope.md) for the approved next migration and [capability matrix](../capabilities/capability-matrix.json) for tested intersections.
