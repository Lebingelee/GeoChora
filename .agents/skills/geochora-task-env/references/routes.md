# TaskEnv route and owner map

Use this page to locate the current owner; the versioned public API and capability matrix are canonical.

## Public construction and selected config

- Facade/factory/registries: `task_env/__init__.py`, `task_env/registry.py`; `make_env(uid, *, config=None, render_mode=None, **kwargs)` is the single-environment entry.
- Config declarations and normalization: `task_env/environment/config.py`, `task_env/environment/configuration.py`; selected precedence and state-only render validation are resolved once here.
- Task Artifact declaration `TaskArtifactDeclarationV1` is defined in `task_env/environment/task_source.py`.
- Shared task/source compiler `ReferenceTaskDeclarationV1` is defined in `task_env/assembly/compiler.py`; its Controller factory is optional and identity records `null` when omitted.
- PickCube and NutAssembly implementations are owned by `task_env/tasks/pick_cube/task.py` and `task_env/tasks/nut_assembly/task.py`; task semantics and Solution policy remain task-local.
- Benchmark consumer: `bench_deploy/libero/`; do not promote its source/control semantics to a generic Core UID.

## Lifecycle, recording, and evidence

- Selected lifecycle class `SelectedReferenceEnv` is defined in `task_env/environment/reference_env.py`; `task_env/tasks/reference_env.py` retains compatibility exports. It delegates execution to `task_env/runtime/sessions/` and one provider adapter. The three classic-control tasks still use the independent `BaseTaskEnv` route; unification is incomplete.
- Phase C's standard target is an external Solution producing actions for `env.step(action)`. The retained PickCube/Nut `step_expert()` is restricted compatibility; `step_with_solution()` is transitional. NutAssembly now accepts caller-driven source-bound `ExpertAction` with its control request, not unrestricted arrays; full physical validation is pending. See `task_env/doc/api/planning/task_owned_solutions.md`.
- Position recording metadata and selected coordinator provenance: `task_env/recorders/position_metadata.py` and `task_env/recorders/reference_provenance.py`; canonical H5 storage is in `task_env/recorders/h5.py`, and independent reader examples live under `examples/recording/`.
- Selected observation projection: `task_env/observations/selected_reference.py`; task-specific evaluation and Solution hooks remain with their tasks. Legacy scalar observation components retain their existing owners pending lifecycle unification.
- Public TaskEnv contracts: `docs/module/task_env/v2.1.0/api/` and `contracts/`.
- Versioned capability evidence: `docs/module/task_env/v2.1.0/capabilities/capability-matrix.json`. Provider status is an exact source × provider × backend × control intersection.

## Current examples and focused tests

- Scalar public route: `examples/start.py`, `examples/README.md` and `examples/tasks/pick_cube.py`; this maintenance has bounded GeoPhys CPU reset/one-step/close results for the three classic tasks using the launcher, not a migrated unified lifecycle or a new-install validation.
- Declarative construction example: `examples/tasks/declared_marker.py`; it demonstrates existing shared composition, but its adapter class is internal.
- Selected-config and optional-Controller regressions: `task_env/diagnostics/tasks/test_selected_api_configuration_and_identity.py`.
- Existing construction/consumer regressions: `task_env/diagnostics/tasks/test_reference_construction.py` and `test_selected_consumers.py`.
- Current user instructions and provider examples: `docs/module/task_env/v2.1.0/guides/` and `examples/README.md`.

## Unsupported or deferred

- Selected PickCube/NutAssembly rendering remains state-only. A non-`none` renderer or unsupported Physics × Renderer pair fails closed.
- GeoPhys/MuJoCo selected CPU routes and the exact PickCube Isaac Sim 6.2/CUDA PhysX source route are bounded; no arbitrary task/provider/backend capability is implied.
- LIBERO public TaskDefinition migration and lightweight task compatibility checks are deferred to the next API Goal. Its benchmark implementation remains in `bench_deploy/libero`.
- F06 task success, A123 task success, task1 GeoPhys fluid projection, P renderer evidence, natural Kit destruction, and strict DG03 retain the limits in the current matrix and follow-up pages.
