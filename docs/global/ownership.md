# GeoChora ownership and change boundaries

Current source, production callers, and qualified evidence define behavior. Canonical contracts describe intended interfaces; historical plans and reports remain scoped to their recorded source revisions.

## Canonical owners

| Concern | Owner | Boundary |
|---|---|---|
| Public environment registry and facade | `task_env/__init__.py`, `task_env/registry.py` | `make_env` and other public entry points; registration alone is not qualification |
| Task configuration and lifecycle | `task_env/environment/`, `task_env/tasks/` | One environment lifecycle owner; task-specific semantics stay with the task |
| Runtime and provider admission | `task_env/runtime/`, `task_env/artifacts/` | Consume provider public/runtime-facing APIs; do not inspect private solver state |
| Controllers and actions | `task_env/controllers/`, `task_env/planners/` | Convert declared actions to canonical targets and feedback |
| Recording and data conversion | `task_env/recorders/`, `task_env/trajectory/` | Keep schema, source, clock, and identity checks explicit |
| Physics and native rendering | GeoPhys or another provider | Provider-owned implementations; no dependency on GeoChora internals |
| Task/asset/policy harness direction | `docs/module/task_harness/`, `asset_harness/`, `policy_harness/` | Documentation describes responsibilities; it does not assert unimplemented modules |
| Agent orchestration and memory | External consumers | Use GeoChora public APIs and evidence; remain outside Core |

## Reuse gate

Before adding behavior, identify its owner and public API, find the existing implementation and production callers, inspect the relevant tests, reproduce the limitation, and decide whether the change fixes, extends, or composes that owner. A new Runtime, Recorder, Controller, task factory, provider abstraction, or Skill requires a concrete reason existing owners cannot support the behavior.

## Capability and publishing

The [v2.1.0 matrix](../module/task_env/v2.1.0/capabilities/capability-matrix.json) records exact bounded task/provider/source/backend intersections. `IMPLEMENTED`, `TESTED_BOUNDED`, `PARTIAL`, `NOT_RUN`, and `DEFERRED` are not interchangeable. The v1.1.0 release matrix and historical decisions remain version-scoped. v2.1.0 is a local candidate; it is not a tag, formal release, or Qualification.

The GeoChora and GeoPhys project code licenses are currently undeclared by the maintainer. Third-party code, dependencies, and assets have separate terms. See the [v2.1.0 asset and distribution record](../releases/v2.1.0/third-party-assets.md). No release decision may infer a license from team authorship or a dependency notice.
