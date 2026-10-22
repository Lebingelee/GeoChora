# C02b-R1 Reset Force Freshness — Bounded Acceptance

Date: 2026-10-22. Result at receipt issuance: **R1 reset-force freshness prerequisite passed for the existing PickCube legacy route on GeoPhys CPU**. At that time plan-bound typed raw-force publication/admission and structured execution remained incomplete. Those later gates are recorded in the typed-force and structured R1 receipts; current C02b status is the declared-intersection bounded engineering exit satisfied. See [P99 readiness review](P99_Readiness_Review_2026-10-22.md). This receipt does not grant qualification.

## Scope and identities

The probe used the existing selected PickCube production route with one Panda, arm plus gripper, CPU, 100 Hz outer control, and five 2 ms native steps per interval. GeoPhys and MuJoCo ran in separate fresh processes with the same task seed 31 and ResetSample.

| Item | Value |
| --- | --- |
| Task / Artifact | `pick-cube-v1/p1_6_experimental_100hz`; identity `fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4` |
| Source | `task-env-pick-cube`; XML SHA-256 `bdd119833a5ae3c8176daf1f5ef586c3601870f10f4b4b5f6d7aa730fe5f0fed` |
| ResetSample | seed `31`; sample `reset-ee9644c1af42c7897f79a0cece21e5fc4bd5323ae40eba7b7259d34d681a5fb6` |
| Controller | `ProductionCanonicalPandaController`, identity `76108c78b8159391e448ad9f49050bed42fd7a86e0e00a0520083b4e5efb02e9` |
| R1 gripper config | `experimental_rate_limited`; 30 N limit, 1 N deadband, 0.002 m opening step, 0.0001 m force adjustment step |
| Timebase | `physics_dt=0.002 s`, 5 substeps, `control_dt=0.010 s`, zero-order hold, post-control-step observations |
| GeoPhys runtime | Taichi CPU x64, Python 3.12.14, Taichi 0.6.3; GeoPhys checkout `4436787e9cb85ce519506a2a9af86d1eeec9de2d` |
| MuJoCo runtime | CPU, separate process, same Python/task/source/controller/timebase |

The actuator oracle comes from the source MJCF, not from a guessed reset force. `actuator8` (index 7) drives fixed tendon `split`, with coefficients `finger_joint1=0.5`, `finger_joint2=0.5`, ctrl range `[0,255]`, fixed gain `0.78431372549`, affine bias `[0,-5000,-120]`, and no activation dynamics. The source force range is ±5 N; the active R1 adapter cap is 30 N after apply. The audited signed law is `clip(gain*ctrl + b0 + b_length*length + b_velocity*velocity, configured_force_range)`, where tendon length and velocity use those coefficients. The canonical projection remains solely in existing `control_feedback()`: `closing_force_N = max(0, -signed_actuator_force)`.

## Repair and public call chain

The prior public `RobotArmObservationReader.read_cpu_snapshot()` route could read the raw force array but returned no validity, sample phase, native index, or freshness identity. The previous audit correctly found a stale `-30 N` value after reset; its broader phrasing that no public read route existed was already corrected there. This repair extends the existing GeoPhys state and observation owners rather than switching reset entry points or letting Core inspect native solver fields.

1. GeoPhys rigid state writes to qpos, qvel, ctrl, activation, and world pose invalidate the force-sample receipt and advance its state revision. Force-limit/configuration writes also advance the configuration revision.
2. The existing restore path reevaluates actuator force from restored state and labels it `reset_forward` or `state_restore_forward`. The Core GeoPhys adapter then restores its baseline, reapplies the active actuator limit, explicitly writes the final ResetSample qpos/qvel/ctrl/activation, synchronizes kinematics, and calls `RobotArmObservationReader.refresh_reset_force_sample()` once at the end. This final evaluation recomputes the actuator law without a native step, integration, activation update, or time advance.
3. The public `RobotArmActuatorForceSampleV1` receipt carries source generation, sample sequence, state/configuration revisions, native step index, phase, validity and invalid reason. The Core `ActuatorForceMeasurementV1` adds the current selected episode, ResetSample, actuator identity, evaluation boundary, actual ctrl, signed force and sample time.
4. On normal implicitfast execution, GeoPhys invalidates the sample while a native interval is in progress and republishes only after successful solver/Graph completion. It marks the latest pre-integration force evaluation as `native_step_pre_integration`; its sample time is `(completed_native_step_index - 1) * 0.002 s`. It is not post-integration recomputation and not a five-step average. The native step index is advanced by the solver's successful completion hook, not inferred from the outer clock.
5. `_GeoPhysSession.control_feedback()` validates validity, finite values, Newton units, solver generation, actuator identity, ResetSample/episode, phase, sample sequence, native index, evaluation boundary and sample time before it passes the signed value to the existing canonical mapping. An invalid or mismatched required sample raises; the legacy route does not fill zero or soften the requirement.

GeoPhys's public `Simulator.prepare_reset()` captures the prepared initial-state manager; `Simulator.reset()` transactionally restores that manager. The rigid owner's `restore_initial_state()` path now recomputes the force cache and marks `reset_forward`, while `synchronize_kinematic_state()` only refreshes body/geometry/site transforms and is not a force refresh. Core's existing adapter uses its own restore-plus-explicit-write route, so the restore computation is invalidated by the final qpos/qvel/ctrl/activation writes; this fix retains that route and explicitly refreshes only after its final writes. Position Profile sessions do not request this reset measurement or consume force feedback; the legacy R1 default remains force-aware. GeoPhys still computes its physical force as part of its own state/step lifecycle, which is separate from Core measurement reads.

## S1 and native S2 evidence

S1 and S2 were run after the final force-aware gating change. The GeoPhys reset-forward oracle tolerance was fixed in advance at 0.02 N; it is used alongside exact source generation, state/configuration revisions, ctrl/qpos/qvel, native index/phase and episode/reset identities. Equality to zero or inequality to the historical `-30 N` is not the oracle.

| Check | Evidence |
| --- | --- |
| Writes invalidate a previous sample | GeoPhys `robot_arm_control_runtime_smoke.py` writes same-value qpos, qvel, ctrl and activation through public state methods; each leaves the prior sample invalid until refresh. |
| Refresh is read-only for physical inputs | The same test checks qpos/qvel/ctrl/activation are unchanged after reset-forward refresh. The native probe also checks state and both clocks after readback. |
| Current reset sample is source-law consistent | After first nonzero force, two resets in the same RuntimeSession reuse the same ResetSample but have distinct episode IDs, increasing sequences/revisions/configuration revisions, index 0 and time 0. Each has ctrl 255 and signed force 0 N; the audited law predicts approximately 0 N for current qpos/qvel/ctrl and active 30 N cap, within 0.02 N. |
| Completed-step phase is distinct | After a real R1 close, sample is `native_step_pre_integration`, native index 5, evaluation boundary step 1/time 0.010 s, force sample time 0.008 s, and signed force `+0.3766021729 N`. Existing canonical closing magnitude is 0 N. |
| First R1 closing compute after reset consumes current sample | The real `ProductionCanonicalPandaController.compute()` capture sees the latest reset episode/sample at step 0 and receives `max(0,-raw_signed_force)`; it does not enter force mode on the valid 0 N sample. |
| MuJoCo semantic comparison | Separate CPU process resets through existing `mj_forward` route, steps one 0.010 s interval, and returns at control step 1/time 0.010 s. Its public legacy route exposes canonical feedback rather than the new raw provenance receipt; no cross-provider force equality is claimed. |

Raw outputs and complete logs are preserved in ignored `workspace/maintenance/c02b_r1_reset_force_freshness_20261022/`: `geophys_s2.json`, `geophys_s2.log`, `mujoco_s2.json`, `mujoco_s2.log`. The final GeoPhys and MuJoCo probes ran as independent processes (PIDs `4131465` and `4131966`).

## Verification run

- Core focused set: **78 passed**, one upstream `taichi_forge` `locale.getdefaultlocale` deprecation warning.
- GeoPhys `test/verification/rigid/robot_arm_control_runtime_smoke.py`: passed on Taichi CPU x64.
- GeoPhys `test/verification/rigid/test_rigid_state_snapshot_restore.py`: exit 0.
- GeoPhys API registry generation/check: passed; current registry reports 259 routes, 258 public routes, no collisions or unclassified routes.
- GeoPhys public registry/export contract targets: **2 passed** after updating the route-count and owner-export expectations for the new diagnostic type. The broader `test_agent_contracts.py` + `test_solver_materialization.py` invocation exposed one unrelated collision-source budget assertion (`expected 51 kernels, observed 61`); it is outside this control/observation change and remains unmodified.
- GeoPhys docs structural check: **not clean due seven unresolved local links** in untouched NutAssembly asset docs and ignored `temp_outputs` evidence. The new route/backlink itself is accepted by registry validation.
- No complete repository/Phase II regression, GPU route, NutAssembly Guard, C05b external Solution, full Expert, recorder integration, or Qualification was run.
- The public GeoPhys `Simulator.prepare_reset()/reset()` lifecycle was source-audited but not separately native-executed; S2 exercised the actual Core adapter restore-plus-write path used by PickCube.

## Remaining contract and exit boundary

The reset-freshness prerequisite is closed for the existing PickCube R1 legacy GeoPhys CPU route. This does **not** close C02b or permit plan-bound required-force admission:

- Provider manifest/capability schema still does not advertise `actuator_force_query`.
- `snapshot_v1()` still does not publish `required` raw signed `actuator_force` through a versioned typed-state value.
- No production plan-bound R1 binding/structured dispatch, full C02b multi-group execution/recording, NutAssembly 500 Hz Guard, or complete Expert was tested.

The next minimal Core scope, if authorized, is a versioned extension of the existing typed-state publication owner that carries signed raw Newton force, actuator identity, source/episode/reset generation, phase/native sample clock and validity, followed by exact manifest/admission wiring and S1. It must keep `control_feedback()` as the sole canonical conversion owner. Only after that contract is admitted can a restricted plan-bound R1 S2/S3 be attempted. C05b external Solution migration remains unstarted and out of this receipt.

## Skill refresh receipt

The TaskEnv Skill now points to the GeoPhys observation sample contract, names the bounded legacy PickCube R1 route, distinguishes completed-step pre-integration from reset-forward samples, and retains the structured admission limitation. Cold-start route: start at the TaskEnv Skill → C02b-R1 route entry → GeoPhys `control.robot_arm` API reference → this acceptance receipt. The Skill describes no new generic runtime, measurement manager or provider capability.

## Checkpoint preservation and upstream-main recheck (2026-10-22)

After maintainer authorization, the local Provider changes were preserved as
`eb870f6f8812abea9022594b702df0c395d98d48` on
`codex/r1-force-freshness-checkpoint-20261022`. Core checkpoint
`89efbe9803335fd0ec1c0d3bac97ec248677d448` records the integration and points its
GeoPhys gitlink to that local Provider commit. The earlier passing freshness
evidence exercised base `4436787` **plus the repair**, not the unmodified base.
Neither checkpoint was pushed.

Fetching GeoPhys main resolved to `9a43b92032deee90c1aef3a7f5f15216dc8e4b42`
(17 commits after `4436787`). An isolated, unpatched checkout was tested with
the pre-repair Core `60b3eca` and the original public-Reader diagnostic adapter.
Imported module paths and Provider HEAD were captured to exclude the local
repair from this experiment. The PickCube XML SHA-256 remained
`bdd119833a5ae3c8176daf1f5ef586c3601870f10f4b4b5f6d7aa730fe5f0fed`.

**Result: upstream reset-force staleness reproduced.** After producing signed
force `-30 N`, resets at seeds 73 and 31 both restored control step/time to
zero and actuator8 ctrl to 255; both finger positions were approximately
0.04 m, but the public Reader still returned `-30 N`. No R1 compute was called.
The upstream Reader has no `refresh_reset_force_sample()` method. This is a
bounded diagnostic defect reproduction, not a new R1/Expert acceptance.
The wrapper's requested-substep count and reset zero-step field are not an
independent Provider completion counter; clock observations and the reviewed
reset path support the no-step interpretation.

The GeoPhys local main was fast-forwarded to the fetched commit. A clean
`codex/fix-reset-force-freshness` branch was created there in the isolated
worktree at `workspace/maintenance/geophys_upstream_reset_20261022_001/geophys-upstream/`.
The repair has **not** been ported to that branch. The active Core checkout
continues using the preserved Provider checkpoint, without adopting upstream
main or changing any frozen reference.

Raw probe, log, structured result and provenance/hash manifest are preserved
in ignored `workspace/maintenance/geophys_upstream_reset_20261022_001/`
(`upstream_native_probe.py`, `upstream_native_probe.log`,
`upstream_probe_result.json`, `verification_manifest.json`). No broad
regression, GPU, standalone Simulator reset or Qualification was run in this
upstream check. Typed raw-force publication/admission and C05b remain open.
