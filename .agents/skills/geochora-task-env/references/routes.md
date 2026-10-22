# TaskEnv source and verification routes

Paths are repository-root relative. Inspect current source and callers before relying on signatures.
With `.codegraph/` present, explore these owners first.

| Need | Current owner / reader | Contract |
| --- | --- | --- |
| Public Position candidate | `task_env/tasks/position_candidate/`, existing registry/SelectedReferenceEnv/RuntimeSession/Generic H5 v3 | `make_env("panda-position-servo-candidate-v1")`; GeoPhys CPU only, fixed seed 31, state-only, horizon 1–6000; optional fresh `source_workspace`. Same public environment 64 steps / 65 observations and same-file H5 request/target/ack/state readback passed. Internal `from_position_candidate` remains an extension hook; diagnostic facade forwards to the task owner. No freeze/Judge/Qualification |
| Public facade/factories | `task_env/__init__.py`, `task_env/registry.py`; callers `examples/tasks/pick_cube.py`, `examples/tasks/nut_assembly.py` | flat selected config vs nested generic config |
| Generic config/plan | `task_env/environment/configuration.py`, `config.py`; `BaseTaskEnv.execution_plan` in `env.py` | defaults → caller override → public-section overlay; immutable static plan precedes GeoPhys bootstrap, not actual manifest admission or reset realization |
| Generic lifecycle/resource ownership | `task_env/environment/env.py`, `task_env/environment/lifecycle.py`, `task_env/runtime/boundary.py` | reset/step/done and task-state evaluation; lifecycle closes RuntimeBoundary once, Env closes Camera/UI wrappers |
| Selected adapter | `task_env/tasks/reference_env.py` | `SelectedReferenceEnv` internal shared owner, public factory consumer; internal `step_expert`, PickCube external Solution lifecycle, bounded NutAssembly external native S1, start/finish recording |
| Task/Artifact/solution | `task_env/tasks/pick_cube/task.py`, `solution.py`, `config.yaml`; corresponding `task_env/tasks/nut_assembly/` | task-owned recipe/semantics; `build_reference` is advanced, do not assume root re-export |
| Advanced Artifact/admission | `task_env/artifacts/__init__.py`, `task_env/artifacts/contracts.py` | `TaskArtifact` v0, additive `TaskArtifactV1`/`decode_task_artifact()` and exact `validate_scene()`, legacy `ExecutionSpec`, `ExecutionSpecV1`/`decode_execution_spec`, `CanonicalStateView`, `CapabilityAdmissionError`, `admit_capabilities` |
| D02 canonical state contracts | `task_env/artifacts/state.py`, exported through `task_env.artifacts`; provider owner remains `task_env/runtime/sessions/` | exact v0/v1/v2 state dispatch; v0/v1 mappings remain compatible; additive v2 carries signed typed actuator force and provenance. `snapshot_v2()` reuses v1 Joint/Frame projection and admits raw force only for the exact GeoPhys `a53a8cf` CPU and MuJoCo 3.8.1 CPU/native build Panda R1 candidate routes; native interval/contact and generic Provider capability are not granted |
| C02b-R1 force sample | `task_env/environment/types.py` (`ActuatorForceMeasurementV1`); GeoPhys adapter `task_env/runtime/boundary.py`, `_GeoPhysSession.control_feedback()`, and MuJoCo `_MuJoCoSession` cache/`control_feedback()`/`snapshot_v2()`; Provider contract `GeoPhys/src/control/robot_arm_observation.py` | legacy PickCube reset freshness and Scene-v3 candidate typed-force admission have separate bounded receipts. GeoPhys reset-forward refresh does not integrate; MuJoCo reset uses existing `mj_forward()` and retains each completed-step pre-integration cache. Call-specific claims bind actual source/Controller/TCP/plan; MuJoCo admission also binds Python/native build digests. Shared manifests and `snapshot_v1()` remain unchanged. Legacy PickCube external Solution separately passed real S2 and canonical-v0 S3 on GeoPhys CPU and MuJoCo CPU. The single-Panda Scene-v3 R1 structured probe passed continuous behavior, arm-pose, dispatch and same-file Generic H5 v3 checks on those exact CPU routes. Current disposition: C02b's declared-intersection bounded engineering exit is satisfied; unadmitted extensions and Qualification are separate. P99 now has a separate explicit single Position candidate public `make_env()` mainline with continuous H5 readback; R1 remains diagnostic. See [structured R1 receipt](../../../../docs/module/task_env/goal/Phase_II/C_Development_Record.md#c02b) and [P99 review](../../../../docs/module/task_env/goal/Phase_II/05_Architecture_Review_and_Execution_Order.md#p99) |
| C05c NutAssembly native S1/S2/S3 | `task_env/tasks/nut_assembly/task.py`, `solution.py`; existing `ReferenceExecutionController`, `RuntimeSession`, `SelectedReferenceEnv`, `ExecutionRecorder` | the specified MuJoCo CPU route and GeoPhys `a53a8cf` CPU/CUDA × gripper 100/500 Hz diagnostic matrix passed real external Expert/Guard/H5 S2/S3. GeoPhys diagnostics call public `read_cpu_snapshot()` every native step despite its normal low-frequency guidance; this is diagnostic-only and does not expand normal Provider support or manifest. Internal `step_expert()` remains; complete C05c approval/Qualification remain open. See [C05c cadence report](../../../../docs/module/task_env/goal/Phase_II/C_Development_Record.md#c05c) and [C05c receipt](../../../../docs/module/task_env/goal/Phase_II/C_Development_Record.md#c05c) |
| Physics sessions | `task_env/runtime/sessions/api.py`, `task_env/runtime/sessions/control.py` | `RuntimeSession`, `materialize`, `provider_manifest`, `materialize_control`; public provider boundary |
| Controller/observation | `task_env/controllers/canonical/contracts.py`, `task_env/controllers/canonical/`; `task_env/observations/` | RequestedAction → canonical target → applied control; schema/frame/timebase metadata |
| Generic recording | `task_env/recorders/__init__.py`, `wrapper.py`, `vector.py`, `h5.py` | Default raw task-env-h5/v2; opt-in v3 structured controls/events/outcome; exact single-writer training conversion |
| Selected recording/inspection | `task_env/trajectory/canonical/`, `examples/recording/record_expert.py`, `examples/recording/inspect_h5.py` | canonical outer v0/v1 vs execution stream v1/v2/v3; T/T+1; strict interval validation; the legacy PickCube external Solution canonical-v0 S2/S3 is bounded passed for GeoPhys `a53a8cf` CPU and MuJoCo 3.8.1 CPU; no complete D0 owner restore or selected R1 Stop/Event/Outcome |
| Offline trajectory | `task_env/trajectory/__init__.py`, `task_env/script/trajectory/` | validate/inspect/transcode/replay; explicit historical replay is separate |
| Parallel | `task_env/vectorization/registry.py`, `task_env/vectorization/parallel.py` | explicit homogeneous tasks, local/remote spawn, masked reset/autoreset |
| Learner/render | `task_env/alg/`, `task_env/render/`, `task_env/observations/canonical_camera/` | learner flatten boundaries; camera vs UI; D05a `CameraCaptureIdentityV1` is a request value unless attached to a successful observation; legacy `create_camera_session()` remains same-provider; D03/D04/D05b historical receipts include GeoPhys CPU Scene-v3 → MuJoCo native OpenGL RGB/Depth/Entity-mask capture. D05b fixed-default + mounted-override, admission, reset/sync/capture/close S1/S2 passed for GeoPhys gitlink `4436787e…`; the current `a53a8cfe…` pin separately passed real S1/S2 and teardown on MuJoCo 3.8.1 NVIDIA EGL (RTX 5060); see [P99 run receipt](../../../../docs/module/task_env/goal/Phase_II/C_Development_Record.md#public-candidate). This diagnostic CameraSession output is not wired to BaseTaskEnv policy observations or TransitionRecorder; semantic masks, other pairings and general D05b qualification remain unsupported. See the [D05b applicability addendum](../../../../docs/module/task_env/goal/Phase_II/D_Development_Record.md#d05) and `test_phase_ii_d05b_pairing_integration.py`. |

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
raw external actions, report the exact unadmitted intersection before proposing existing-owner extension.

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
task success or qualification support. Details and receipt are in the [Phase D D01b record](../../../../docs/module/task_env/goal/Phase_II/D_Development_Record.md#d01).


D01a historical/current pin test navigation is documented in the
[independent-review handoff](../../../../docs/module/task_env/goal/Phase_II/05_Architecture_Review_and_Execution_Order.md#evidence).
The exact historical axis-change receipt remains 4436787e-only; the current-pin A05/reset/step test is in the same owner.
Unknown pins and wrong receipt identity fail; only the known baseline mismatch is explicitly historical-not-applicable.
