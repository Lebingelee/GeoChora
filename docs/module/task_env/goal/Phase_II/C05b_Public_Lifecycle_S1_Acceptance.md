# C05b Public Lifecycle S1 Acceptance

**Date:** 2026-10-22  
**Status:** bounded public lifecycle S1 passed; C05b full execution remains open and C02b remains **BLOCKED**.

## Scope and preserved checkpoint

This receipt covers two ordered pieces of work: align the Core GeoPhys gitlink to the requested fixed freshness-repair commit and re-run the affected force/admission evidence; then wire a public caller-owned Solution lifecycle through the existing PickCube `SelectedReferenceEnv`, task factory, R1 Controller, `ExpertExecutionInfo`, readiness and canonical Recorder owners.

At start, Core was on `codex/phase-ii-c03b`, HEAD `ec2dd2438da5c0bd1b79ed58c3900e54bb7433ca`. The pre-existing uncommitted typed-force implementation, tests, receipt and docs were preserved in local checkpoint commit `1eac5649afaa25b077afdd58de5f480a0a213245` (`checkpoint: preserve C02b-R1 typed force slice`). Ignored Evidence and unrelated workspace content were retained. The GeoPhys submodule is now clean and detached at the requested `a53a8cfed7c9d6464274b5c96fca601271dc4ee4`; the parent gitlink is modified to this pin. No GeoPhys branch pointer was moved, no Provider files were changed, and no push or merge occurred.

The GeoPhys delta, exact admission change, and fresh candidate/legacy force Evidence are detailed in the [C02b-R1 typed-force receipt](C02b_R1_Typed_Raw_Force_Admission_Acceptance.md). That evidence uses the exact new pin and is not inherited from the older `eb870f6f` run.

## PickCube route and identities

C05b S1 deliberately uses the existing frozen selected PickCube legacy route:

| Field | Actual value |
| --- | --- |
| UID / Artifact | `pick-cube-p16-reference-v1` / `pick-cube-v1/p1_6_experimental_100hz` |
| Artifact identity | `fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4` |
| Runtime source | `task-env-pick-cube`, composed MJCF SHA-256 `bdd119833a5ae3c8176daf1f5ef586c3601870f10f4b4b5f6d7aa730fe5f0fed` |
| TCP / action | `panda-v1/ee`; `selected-reference-absolute-pose-v1`, world absolute pose, quaternion wxyz, 8 values |
| Controller | `ProductionCanonicalPandaController`, profile `panda-production-control-r1`, identity `76108c78b8159391e448ad9f49050bed42fd7a86e0e00a0520083b4e5efb02e9` |
| Solution | `PickCubeReadinessSolution`, version `pick-cube-p16-readiness-expert-v2`, identity `514a5ed3bc0d289761ef88a00b1e7c11df2795133506ab148db9ab8e98e55241` |
| Timebase | 100 Hz outer control; five native steps at 2 ms per 10 ms interval |
| Required feedback | Existing R1 requires boundary-matched `actuator8` signed actuator-force projection; no force requirement was weakened |
| Recorder / Stop | Existing canonical-trajectory-v0; selected legacy R1 `stop()` still rejects |

The S1 lifecycle tests use the existing GeoPhys CPU selected factory with a test-only `FakeSession`, seed 19, horizon 3. The exact force-native evidence is separate: (a) the legacy PickCube GeoPhys CPU freshness/first-closing probe uses seed 31; (b) the candidate plan-bound typed-force interval uses a different, explicitly identified Scene-v3 candidate. The latter does not supply PickCube with a Scene, plan, or source identity.

## Public API and lifecycle behavior

The task package exports `build_readiness_solution()`. The bounded external sequence is:

```python
solution = build_readiness_solution()
observation, info = env.reset_for_solution(solution, seed=19)
# One control interval at a time:
observation, reward, terminated, truncated, info = env.step_with_solution(solution)
```

The task binding provides paired `build_external` and `validate_external_solution` callbacks. They reuse the same Artifact, source, readiness configuration and Solution identity as the existing factory. `reset_for_solution()` validates the supplied task-owned Solution before Runtime teardown/materialization and again against the rebuilt selected task value. A foreign identity is refused before Runtime reset. For an external episode the Environment has no active `self.solution`; the caller-owned instance is the sole mutable owner of stage, wait, counter and completion state. The Environment retains only that instance for identity/lifecycle control, and `step_with_solution()` rejects any other object.

`SelectedReferenceEnv.expert_execution_info()` is the public typed readiness getter. Reset and each legacy R1 evaluation boundary also publish these required info fields unconditionally:

- `expert_execution_info_v1`: validated `ExpertExecutionInfo` mapping with canonical `CanonicalControlReadiness`;
- `control_readiness_v1`: its typed readiness mapping;
- `expert_execution_boundary_v1`: versioned Core execution-boundary identity containing a generated Core episode ID, Artifact hash, actual source ID/XML hash/source closure, actual Controller and Solution identity, ResetSample ID, control step and simulation time.

The execution boundary is deliberately not a `StateBoundaryIdentity`, Scene identity or `ControlBindingPlan` identity. The legacy RuntimeSource has no Scene-v3 closure, so its closure field remains null. This truthful boundary identity does not retrofit frozen plan provenance.

Reset publishes no `control_application_v1`, because reset does not apply a controller target. A completed step publishes `control_application_v1` with requested and canonical action, computed target, actual `AppliedCanonicalControl`, matching target/applied hashes, source identity, request and evaluation boundaries, and the actual Artifact/Controller/Provider/reset identities. The publisher checks target-to-ack, exact Artifact/Controller/Provider, one completed evaluation step, and the selected 10 ms boundary. It is part of the required info contract, not optional diagnostics; this selected config exposes no diagnostics-off switch.

`step_with_solution()` validates the returned public readiness and boundary before calling `Solution.act()`. The existing `_step()` then performs Controller compute, RuntimeSession apply and step, reads fresh feedback/state, publishes readiness and application acknowledgement, calls `Solution.observe()`, and only then appends the canonical Recorder transition. No new Runtime, Environment, Provider, Recorder or Solution registry was added. Existing internal `step_expert()` remains available.

The external lifecycle reuses existing execution faults:

- Missing/stale readiness or a wrong boundary identity is latched before `Solution.act()`, Controller compute/apply, or physics advancement.
- A throwing `Solution.observe()` latches at `solution_observation` after the physical interval. The fault reports `physical_progress=advanced` and an unrecorded/incomplete transition; it does not claim the Provider or Controller was rolled back.
- A Recorder append exception latches at `record_interval` after observe and physical execution. The tested pre-append failure leaves no transition and reports a rejected transition. Another step is blocked without additional compute, apply or physical advancement.
- Task `is_success`, Solution completion, Gymnasium terminated/truncated flags, old Stop rejection and canonical-v0 storage semantics remain distinct and unchanged.

## S1 validation and evidence

The affected Core regression command was:

```text
PYTHONPATH=GeoPhys/src:. python -m pytest -q \
  task_env/diagnostics/tasks/test_selected_consumers.py \
  task_env/diagnostics/tasks/test_phase_ii_c03a_fault_lifecycle.py \
  task_env/diagnostics/tasks/test_phase_ii_c03b_stop_outcome.py \
  task_env/diagnostics/tasks/test_phase_ii_c02b_position_profile.py \
  task_env/diagnostics/tasks/test_phase_ii_c02b_position_execution_h5.py \
  task_env/diagnostics/tasks/test_phase_ii_c02b_dual_entity_position.py \
  task_env/diagnostics/tasks/test_phase_ii_c02b_admission.py \
  task_env/diagnostics/tasks/test_phase_ii_c02a_controller_bindings.py
```

Final affected regression result: **103 passed**, with one upstream Taichi `locale.getdefaultlocale` deprecation warning. It compared internal `step_expert()` with external `reset_for_solution()` / `step_with_solution()` at the same sample/config; verified repeat reset creates a distinct Core episode ID; confirmed reset has no acknowledgement; compared Task flags, action, target and applied acknowledgement; observed that `Solution.observe()` completed before canonical Recorder append; and injected missing/stale readiness, wrong source boundary, foreign Solution identity, observer exception, and Recorder append exception. Fault tests prove no follow-up execution and retain the original physical step evidence. These are lifecycle S1 tests using `FakeSession`, not native physical S2. Final log: `workspace/maintenance/c05b_public_lifecycle_s1_20261022/core_c05b_affected_final_pytest.log`.

The full `test_selected_consumers.py` file also passed **46 tests**, and the focused C05b cases passed **7 tests** after the final mode-mixing assertion and Solution identity-preservation cleanup. These narrower logs remain in the same ignored evidence directory.

The same aligned GeoPhys pin received fresh provider-side verification:

- Typed-force/admission compatibility S1: **35 passed, 1 native test deselected**, one upstream deprecation warning. Log: `workspace/maintenance/c02b_r1_geophys_a53a8cf_20261022/s1_pytest.log`.
- Same candidate plan-bound GeoPhys CPU S2: **1 passed**. The fresh `typed_candidate_final/s2_probe.json` records provider commit/manifest `a53a8cfed7c9d6464274b5c96fca601271dc4ee4`, exact candidate/plan/Controller, valid reset-forward `+4.0 N` raw sample and canonical `0 N`, a real 5-step interval to 10 ms, and next raw `−0.038249071687459946 N` at native step 5 / pre-integration phase. Target and applied hashes match.
- Legacy PickCube freshness/first closing: JSON `legacy_pickcube_geophys_s2_final.json` reports `PASS`, GeoPhys a53 CPU, seed 31, legacy Artifact/source, 100 Hz / 5×2 ms. It first produced `+0.3766021728515625 N`; two same-sample reset-forward reads returned `0.0 N`, each within 0.02 N of the audited actuator-law value `4.470298364367409e-6 N`. The final R1 first closing compute consumed that sample and did not activate force mode. Repeated readback left the control clock at step 1 / 10 ms. This remains a legacy no-plan route, distinct from candidate admission.
- GeoPhys `test_rigid_state_snapshot_restore.py`: **7 passed**; corrected `robot_arm_control_runtime_smoke.py` including repeated-reset/implicitfast refresh passed. Logs are preserved in the same ignored Provider evidence directory. A first smoke invocation had a helper import path error and is retained but excluded from the pass claim.

The complete raw commands and outputs are retained in ignored paths `workspace/maintenance/c05b_public_lifecycle_s1_20261022/` and `workspace/maintenance/c02b_r1_geophys_a53a8cf_20261022/`. The previous `workspace/maintenance/c02b_r1_typed_force_20261022/` and reset-freshness Evidence remain unchanged.

## Exit status and remaining work

This closes only C05b **public lifecycle S1** and the required GeoPhys baseline re-verification gates. For future full PickCube execution, this slice explicitly selected the existing legacy PickCube source/Artifact/R1 consumer route. It does not transfer the separate candidate's `panda-main` typed-force admission or fabricate a plan-bound identity for PickCube.

Not run: full external PickCube Expert S2 on real GeoPhys and MuJoCo processes; native close/contact/readiness stage comparison; canonical-v0 disk recording and reader S3; failed recording finalization/recovery beyond the injected append boundary; MuJoCo typed-force; NutAssembly Guard; C05c, Assembly, complete C02b, full Expert campaign, and Qualification. C02b remains **BLOCKED**. C05b S2/S3 and Phase II are not complete.

**Next bounded target:** decide whether the planned full PickCube S2/S3 continues on the selected legacy entry with its current no-plan R1 required feedback contract, or whether a separate truthful plan/source identity is required first. Any future route must preserve the frozen Artifact and required force, use the actual source/Controller/ResetSample identities, and prove full execution before recording claims. Do not substitute the Scene-v3 candidate receipt for legacy PickCube evidence.
