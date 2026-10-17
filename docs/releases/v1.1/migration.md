# v1.1.0 Breaking-Change Migration Guide

**RELEASE_CANDIDATE — NOT_PUBLISHED**

GeoChora v1.1.0 is a Core consolidation release with documented breaking API
changes under the project-specific versioning policy. It does not promise
strict SemVer compatibility. The source of truth for the exhaustive old
identity, current replacement, equivalence, classification, migration, and
immutable recovery ref is the
[`v1.1.0 compatibility inventory`](../../module/task_env/p2_0_s5_a_compatibility_inventory.json).

| Old identity or route | Current route | Compatibility and migration |
| --- | --- | --- |
| `pick-cube-v1` environment UID | `pick-cube-p16-reference-v1` via `task_env.make_env` | Breaking identity; not semantically aliased. Review selected P1.6 Artifact and task contract. |
| `nut-assembly-square-v1` environment UID | `nut-assembly-outcome-reference-v1` via `task_env.make_env` | Breaking identity; use guarded `step_expert()`. No arbitrary external gripper route. |
| Direct legacy task constructors and old package helper imports | `from task_env import make_env` for public environment construction | Breaking API. PickCube and NutAssembly helper exports are not symmetrical; use public `make_env`, not package-root builder assumptions. |
| Go2 UIDs, `go2-v1`, Go2 modules, aliases, profiles and defaults | No replacement | Retired without aliases. Restore immutable `v1.0.0` for historical source/execution. |
| Static Template imports, runtime symbols, `static_template` layout/config and diagnostic options | `merged_scene` only where separately admitted | Breaking removal. Unsupported requests fail closed; no redirect to another runtime. Recover exact source from the S4 manifest refs. |
| Historical Stage 11, Phase I grouped collection and old task-specific recorder helpers | Current selected recording examples and `task_env.script.trajectory.record` | Historical routes are retired; current examples use public task UIDs and the canonical recorder. Historical execution needs the recorded immutable source. |
| Historical camera/render scripts and removed private helper | Pendulum rasterizer examples for the two tested intersections | No general replacement. Camera contracts remain; task/provider combinations must be separately admitted. |
| RSL CLI without explicit environment/task UID | Supply `--env-id` and satisfy current learner capability admission | Removed default; unsupported combinations fail closed. |

The exact removed Python paths, public symbols, CLI flags, serialized runtime
fields, defaults, and per-file source recovery refs are in the compatibility
inventory and the S3/S4/S4.5 recovery manifests. Historical release documents
and Evidence are not rewritten. For historical runs, check out the exact
immutable ref in a separate working tree rather than porting old task
implementations into current Core.
