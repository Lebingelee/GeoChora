# TaskEnv source and verification routes

Paths are repository-root relative. Inspect current source and callers before relying on signatures.
With `.codegraph/` present, explore these owners first.

| Need | Current owner / reader | Contract |
| --- | --- | --- |
| Public facade/factories | `task_env/__init__.py`, `task_env/registry.py`; callers `examples/tasks/pick_cube.py`, `examples/tasks/nut_assembly.py` | flat selected config vs nested generic config |
| Generic config/plan | `task_env/environment/configuration.py`, `config.py`; `BaseTaskEnv.execution_plan` in `env.py` | defaults → caller override → public-section overlay; immutable static plan precedes GeoPhys bootstrap, not actual manifest admission or reset realization |
| Generic lifecycle/resource ownership | `task_env/environment/env.py`, `task_env/environment/lifecycle.py`, `task_env/runtime/boundary.py` | reset/step/done and task-state evaluation; lifecycle closes RuntimeBoundary once, Env closes Camera/UI wrappers |
| Selected adapter | `task_env/tasks/reference_env.py` | `SelectedReferenceEnv` internal shared owner, public factory consumer; `step_expert`, start/finish recording |
| Task/Artifact/solution | `task_env/tasks/pick_cube/task.py`, `solution.py`, `config.yaml`; corresponding `task_env/tasks/nut_assembly/` | task-owned recipe/semantics; `build_reference` is advanced, do not assume root re-export |
| Advanced Artifact/admission | `task_env/artifacts/__init__.py`, `task_env/artifacts/contracts.py` | `TaskArtifact` v0, additive `TaskArtifactV1`/`decode_task_artifact()` and exact `validate_scene()`, legacy `ExecutionSpec`, `ExecutionSpecV1`/`decode_execution_spec`, `CanonicalStateView`, `CapabilityAdmissionError`, `admit_capabilities` |
| D02a canonical state contracts | `task_env/artifacts/state.py`, exported through `task_env.artifacts`; D02b provider owner remains `task_env/runtime/sessions/` | strict v0/v1 state dispatch, explicit scalar v0 projection, consumer requirements, native interval evidence and alias lifetime descriptors; no provider projection/native capability claim |
| Physics sessions | `task_env/runtime/sessions/api.py`, `task_env/runtime/sessions/control.py` | `RuntimeSession`, `materialize`, `provider_manifest`, `materialize_control`; public provider boundary |
| Controller/observation | `task_env/controllers/canonical/contracts.py`, `task_env/controllers/canonical/`; `task_env/observations/` | RequestedAction → canonical target → applied control; schema/frame/timebase metadata |
| Generic recording | `task_env/recorders/__init__.py`, `wrapper.py`, `vector.py` | `RecorderConfig`, `TransitionRecordWrapper`, `VectorTransitionRecorder`, `FrozenTrajectory` |
| Selected recording/inspection | `task_env/trajectory/canonical/`, `examples/recording/record_expert.py`, `examples/recording/inspect_h5.py` | canonical outer vs execution stream; T/T+1; no complete D0 owner restore |
| Offline trajectory | `task_env/trajectory/__init__.py`, `task_env/script/trajectory/` | validate/inspect/transcode/replay; explicit historical replay is separate |
| Parallel | `task_env/vectorization/registry.py`, `task_env/vectorization/parallel.py` | explicit homogeneous tasks, local/remote spawn, masked reset/autoreset |
| Learner/render | `task_env/alg/`, `task_env/render/`, `task_env/observations/canonical_camera/` | learner flatten boundaries; camera vs UI; D05a static `CameraCaptureIdentityV1` is request identity only; active native admission still requires physics/render provider match |

Detailed maintained contracts: [public API](../../../../docs/module/task_env/public-api.md),
[runtime](../../../../docs/module/task_env/runtime-and-providers.md),
[recording/learning](../../../../docs/module/task_env/recording-and-learning.md),
[qualification](../../../../docs/module/task_env/qualification.md),
[troubleshooting](../../../../docs/module/task_env/troubleshooting.md).
Symbol-level reference is [task_env/doc/api](../../../../task_env/doc/api/index.md), not a second capability schema.

## Existing defect-sensitive tests

- `task_env/diagnostics/tasks/test_reference_construction.py`: Artifact/config/source/reset identities, provider-free.
- `task_env/diagnostics/tasks/test_phase_ii_d01b_vnext_materialization.py`: bounded TaskArtifact v1/Role/Reset route on GeoPhys and MuJoCo CPU; not general scene-import or task qualification.
- `task_env/diagnostics/tasks/test_nutassembly_outcome.py`: outcome/stage/strict lifecycle distinctions.
- `task_env/diagnostics/tasks/test_selected_consumers.py`, `test_record_cli_completion.py` in the same directory:
  current public consumers, recording and incomplete-run failure.
- `task_env/diagnostics/tasks/test_s2_b2_legacy_retirement.py`, `test_s3_go2_retirement.py`,
  `test_s4_static_retirement.py`, `test_s4_5_b_workflows.py`: retirement/fail-closed/workflow contracts.
- `task_env/diagnostics/phase1/integration/test_solution_lifecycle.py`, `test_guarded_transition.py`,
  `test_recording_streaming.py`: internal state/guard/storage infrastructure; not native qualification.

Bounded provider-free task regression:

```bash
PYTHONPATH=GeoPhys/src:. python -m pytest -q task_env/diagnostics/tasks
```

Use current examples for admitted native execution only when needed. Do not run all historical phase1
diagnostics: some intentionally reference retired candidate implementations and require immutable-source
recovery. Retained historical `experiment_manifest.json` enables list/recovery metadata, not a claim that
its source bundles or retired raw Evidence remain available.

## Concrete cold-start route

For “record a supported PickCube expert and prepare evaluation evidence”: choose MuJoCo CPU/seed 31,
construct through public UID, use root record_expert command at a new workspace path, inspect retained
H5 via inspect_h5, bind Artifact/Core/provider/controller/solution/config provenance, then follow the
existing Experiment/Evidence Skill for report and Human Judge. Do not invent an evaluator/Runner or
claim training/qualification. If asked for SAPIEN, Flora, batch manipulation or arbitrary NutAssembly
external actions, report the exact unadmitted intersection before proposing existing-owner extension.

The built-in task recipe supplies a deterministic Artifact identity, not an automatically approved
workspace Artifact/Judge package. Locate an existing approved version and its explicit decision before
claiming freeze; if unavailable, identify the gap and prepare Stage-1 validation/Human review under
the Evidence Skill. For current recipe execution receipts, record the actual release/source identity
and do not invent a new approval.

`inspect_h5.py` checks a loaded file; its `storage_roundtrip` result does not execute a fresh save/load.
Keep any actually executed new roundtrip evidence separate from offline load/T+1 validation.

## Current Phase II vNext materialization slice

`sample_episode_reset_plan()` accepts the original TaskArtifact v0 route and the bounded D01b TaskArtifactV1 route.
For v1, the Task Source snapshot and exact Scene-v3 identity must match; `RuntimeSession.materialize()` also requires
one RobotInstance, scalar reset/state fields and a bounded source root. Only GeoPhys/MuJoCo CPU is TESTED_BOUNDED for
the Panda + static square-peg probe. MuJoCo consumes the Scene scalar-axis projection through its existing adapter and
checks public model Frame/Joint topology. Do not infer multi-Robot, free-body pose reset, contact, controller, render,
task success or qualification support. Details and receipt are in the [Phase D D01b record](../../../../docs/module/task_env/goal/Phase_II/04_Phase_D_Physics_Rendering.md#d01b-bounded-vnext-two-provider-receipt-2026-10-20).
