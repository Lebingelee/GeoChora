# TaskEnv route and owner map

Use this page to locate the current owner; the versioned public API and capability matrix are canonical.

## Public construction and selected config

- Facade/factory/registries: `task_env/__init__.py`, `task_env/registry.py`; `make_env(uid, *, config=None, render_mode=None, **kwargs)` is the single-environment entry.
- Config declarations and normalization: `task_env/environment/config.py`, `task_env/environment/configuration.py`; selected precedence and state-only render validation are resolved once here.
- Task Artifact declaration `TaskArtifactDeclarationV1` is defined in `task_env/environment/task_source.py`.
- Shared task/source compiler `ReferenceTaskDeclarationV1` is defined in `task_env/assembly/compiler.py`; its Controller factory is optional and identity records `null` when omitted.
- PickCube and NutAssembly task semantics, binding and Solution live in their respective `task.py`, `specialization.py` and `solution.py` files under `task_env/tasks/`; task policy remains task-local.
- Benchmark consumer: `bench_deploy/libero/`; do not promote its source/control semantics to a generic Core UID.

## Lifecycle, recording, and evidence

- Selected lifecycle class `SelectedReferenceEnv` is defined in `task_env/environment/reference_env.py`; `task_env/tasks/reference_env.py` retains compatibility exports and `BaseTaskEnv` is the same class object. Empty retains the component RuntimeBoundary; Pendulum and TwoWheel have bounded shared RuntimeSession routes on GeoPhys CPU and MuJoCo CPU, pending their respective review gates. Pendulum human construction does not provide a display; render raises RenderUnavailableError. The lifecycle migration and bounded pre-stage3 core closeout have been accepted; G03 routing/admission, frozen three-route execution and the explicit PickCube reset-switch profile are separately accepted. See the v2.1.1 [handoff](../../../../docs/module/task_env/v2.1.1/maintenance/20261106_stage3_closeout_stage4_sol_handoff.md); provider evidence remains tied to its actual source commit.
- Phase C's standard target is an external Solution producing actions for `env.step(action)`. The retained PickCube/Nut `step_expert()` is restricted compatibility; `step_with_solution()` is transitional. NutAssembly accepts caller-driven source-bound `ExpertAction` with its control request, not unrestricted arrays. PickCube seed31 and NutAssembly seed19 have bounded MuJoCo CPU rollouts and independent readback at `f06ee2f5`; this does not qualify other providers or task combinations. See `task_env/doc/api/planning/task_owned_solutions.md`.
- Position reset/transition recording projections and selected coordinator provenance: `task_env/recorders/position_metadata.py` and `task_env/recorders/reference_provenance.py`; canonical H5 storage is in `task_env/recorders/h5.py`, and independent reader examples live under `examples/recording/`.
- Selected observation projection: `task_env/observations/selected_reference.py`; each non-mixed binding explicitly declares its observation space and projection, while mixed tasks supply their own observation contract. Task-specific evaluation and Solution hooks remain with their tasks; classic component observations retain their own builders.
- Source-bound F05 runtime admission types and their exact frozen source constraints: `task_env/runtime/sessions/position_admission.py`; Position task construction remains in `task_env/tasks/position_candidate/`. DG04 lowest-I/O synthetic checks can reuse an explicitly configured, SHA-verified external delivery via `F05_DG04_DELIVERY_MANIFEST`; this is not an Isaac physical test.
- Public TaskEnv contracts: `docs/module/task_env/v2.1.0/api/` and `contracts/`.
- Versioned capability evidence: `docs/module/task_env/v2.1.0/capabilities/capability-matrix.json`. Provider status is an exact source × provider × backend × control intersection.

## Current examples and focused tests

- Scalar public route: `examples/start.py`, `examples/README.md` and `examples/tasks/pick_cube.py`; this maintenance has bounded GeoPhys CPU reset/one-step/close results for all three classic tasks at `8b3c8d93`. The unified lifecycle has bounded source/contract acceptance; these checks do not establish a new installation or other provider routes.
- Declarative construction example: `examples/tasks/declared_marker.py`; it demonstrates existing shared composition, but its adapter class is internal.
- Selected-config and optional-Controller regressions: `task_env/diagnostics/tasks/test_selected_api_configuration_and_identity.py`.
- Existing construction/consumer regressions: `task_env/diagnostics/tasks/test_reference_construction.py` and `test_selected_consumers.py`.
- Current user instructions and provider examples: `docs/module/task_env/v2.1.0/guides/` and `examples/README.md`.

## Unsupported or deferred

- Selected PickCube/NutAssembly rendering remains state-only. A non-`none` renderer or unsupported Physics × Renderer pair fails closed.
- GeoPhys/MuJoCo selected CPU routes and the exact PickCube Isaac Sim 6.2/CUDA PhysX source route are bounded; no arbitrary task/provider/backend capability is implied.
- LIBERO public TaskDefinition migration and lightweight task compatibility checks are deferred to the next API Goal. Its benchmark implementation remains in `bench_deploy/libero`.
- F06 task success, A123 task success, task1 GeoPhys fluid projection, P renderer evidence, natural Kit destruction, and strict DG03 retain the limits in the current matrix and follow-up pages.
