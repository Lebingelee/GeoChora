# TaskEnv public API — v2.1.0 candidate

**Status:** local candidate documentation. The exact tested intersections and evidence limits are in the [capability matrix](../capabilities/capability-matrix.json). This page describes current owners and routes; it does not grant a task, provider, renderer, or Qualification.

## Public construction entry

`task_env.make_env(uid, config=..., render_mode=..., **kwargs)` is the public single-environment factory. It resolves the registered task and its configuration before calling the task's constructor. `ENV_REGISTRY` and the sibling component registries describe constructible classes; registration or import success alone does not establish runtime support.

The facade also exposes `make_agent`, `make_object`, `make_scene`, `resolve_env_config`, and the optional homogeneous `make_parallel_env` route. Parallel registration, worker lifecycle, and learner dependencies remain separate from the single-environment factory.

The selected reference UIDs are `pick-cube-p16-reference-v1` and `nut-assembly-outcome-reference-v1`. The older `pick-cube-v1` and `nut-assembly-square-v1` selected routes are retired from active `make_env`; retired Go2 UIDs fail explicitly and do not substitute another task. See [migration](migration.md).

## Task construction declarations

The lower-level construction owners are `task_env.environment.TaskArtifactDeclarationV1` and `task_env.assembly.ReferenceTaskDeclarationV1`. A declaration binds the task contract and named source references; compiling it returns the declared Artifact, RuntimeSource, and an optional pure Controller. Compilation does not instantiate a provider or prove runtime admission. `examples/tasks/declared_marker.py` shows a bounded Core construction example; its `DeclaredPandaBoxEnv` adapter is an internal example, not a required task-authoring protocol.

Keep reset, observation, action, semantics, and evaluation in the Task Artifact/task owner. Keep task composition and source references in the Assembly declaration. Do not add a task-local Runtime, Recorder, Controller, provider abstraction, or second factory.

## Selected execution configuration

Selected tasks resolve `execution`, `episode`, and `task` through one strict configuration boundary. Defaults flow from Core, to the task class, to task YAML, then to the caller. Unknown fields, conflicting legacy aliases, mismatched resolved-task identities, and unsupported provider/backend/device or physics/renderer combinations fail clearly.

The current selected renderer fact is the complete `RendererSelectionV1` mapping with `schema_version=renderer-selection-v1`, `provider=none`, `backend=cpu`, `profile=none`, and `device=null`. It records state-only selection; it does not enable selected-task rendering. See [configuration](configuration.md).

## Lifecycle, expert, and recording routes

A selected task has one mutable `SelectedReferenceEnv` lifecycle owner for reset, step, recording integration, and close. Runtime sessions and provider adapters implement the admitted execution below that owner. Task-specific reset and evaluation remain task-owned. Expert/Solution execution is explicit and task-specific; it is not inferred from registration or from a successful constructor.

The canonical H5 recorder preserves task, source, controller, solution, provider, and resolved-configuration facts. Use the current recording commands in the [quickstart](../guides/quickstart.md) and validate saved files with the independent H5 reader. Storage validity, replay validity, task success, Expert completion, and Judge decisions are separate results.

## Advanced and diagnostic interfaces

Public diagnostic/readback protocols are optional capabilities. Examples include compiled-model options and physical-fingerprint readbacks; they are not requirements on every RuntimeSession and do not admit an otherwise unsupported provider. Internal adapters, provider solver state, renderer layouts, and task bindings are not public authoring interfaces.

## Support boundary

The selected resolver currently covers GeoPhys CPU and MuJoCo CPU routes, plus the exact bounded PickCube Isaac Sim CUDA/PhysX source route documented by the matrix. This statement does not generalize to arbitrary tasks, assets, provider versions, or renderer pairings. Unsupported combinations fail closed. Use the [v2.1.0 capability matrix](../capabilities/capability-matrix.json) for evidence heads, source identities, controller scope, test status, and explicit limits.

The repository has no root packaging metadata. Follow [installation](../guides/installation.md); do not use `pip install -e .`.
