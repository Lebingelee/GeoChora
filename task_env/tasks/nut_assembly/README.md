> 当前 active route 见 [P2.0-B selected consumers](../../../docs/module/task_env/p2_0_active_task_consumers.md)。下文旧 env UID/config 属历史接口；当前 make_env 明确拒绝，恢复请使用冻结 v1.0.0。

# NutAssemblySquare solution ownership

`solution.py` remains the historical compatibility solution. Its implementation,
task geometry, canonical task semantics, initialization, production controller,
and provider adapters are unchanged by P1.8-E-R2.

`canonical_solution.py` contains the **experimental, unqualified**
`NutAssemblyCanonicalSolutionV1`. It emits public `absolute_pose/world/wxyz`
actions from canonical observations and readiness. One configuration expresses
planning and holds in physical time; `control_dt` derives tick counts. It has no
provider selection, native contact input, or simulator import. It is not
registered as a replacement for the historical solution.

The paired recovery detector lives in
`task_env.diagnostics.phase1.nutassembly_recovery`. Its `campaign` entry point
archives each solution/configuration before isolated provider execution. The
`grasp_lift` scope stops after verification lift and cannot establish full task
success. `analysis` consumes recorded traces without simulation. Required
governed source bytes and run artifacts belong under
`workspace/qualification/phase1/p1_8_nutassembly_solution_recovery/`.

The instantaneous `gripper_stable_speed_m_s` configuration value is retained in
archived configurations; current readiness uses a physical-time opening window
and measured canonical load instead. The production controller's force
readiness remains unchanged. Verification lift additionally checks the
nut/EE relative pose rather than treating `grasped_nut` or `lifted_nut` alone as
proof of stable capture.

Historical 30 Hz legacy success does not qualify this canonical candidate.
Qualification requires six successful source trajectories, a solution lock,
six exact D0 reconstructions, and 24 valid D1/D2 replay cells. Until those gates
and Human review succeed, P1.8-E remains PARTIAL / NOT APPROVED.

Before further task acceptance, qualify the constituent paths: physical-time
planner sampling, unloaded EE tracking at 50/100/500 Hz, unloaded gripper
open/close, then loaded grasp persistence under a verification lift/transport.
The current production gripper applies fixed opening and force-correction
steps per control boundary. Resampling a planner alone cannot establish
closed-loop rate invariance. Existing production behavior remains frozen.
`nutassembly_recovery.timebase_analysis` consumes preserved R0 Evidence and
checks a provider-free sampled trajectory; it does not run physics or qualify
tracking, grip, or task success.

## R5 stable grasp development candidate

`stable_grasp_candidate.py` adds the explicitly selected
`NutAssemblyStableGraspCandidate` and task-local `StableArmTargetHold`.
The candidate profile is `profiles/nutassembly-r5-stable-grasp-10n-v1.json`.
This is a development profile descriptor, not an input to the legacy nominal
profile loader or a replacement for registered historical routes.

Its resolved gripper target and actuator force limit are 10 N with a 1 N
deadband. The close transition accepts only `controller_close_ready`
continuously for 0.1 s; the solution has no stable-grasp force fallback.
Inherited legacy configuration fields do not authorize this close transition.
The procedure is:

`pose_stable -> close_gripper -> authorized hold 0.1 s -> verify_lift`.

The arm target is held at descent completion until the achieved pose is
stable (minimum wait 0.5 s; continuous 0.2 s window; each position-axis span
at most 0.1 mm; speed at most 2 mm/s). The achieved pose becomes the fixed
close reference. The arm target remains held through the additional 0.1 s
post-authorization window, then the underlying persistent R3 tracker resumes.
There is no post-authorization seating displacement. The canonical grasp
height offset is 44.895 mm and includes the shared measured static servo
compensation from the NA-S0 investigation; this has not been qualified across
other reset samples or geometries.

MuJoCo close + verify-lift passed at equal outer/gripper rates of
500/100/50 Hz. The physics step remained 2 ms. This evidence is scoped to G0;
loaded transport, full task, D0-D2 and the other providers are not qualified by
these runs. Fixed-500-Hz inner execution at slower outer rates is not part of
this candidate's evidence. Arm R3 source, R1, legacy solution, assets, physics
settings and historical profiles remain unchanged. The task-local hold wrapper
is an additional stateful execution policy and needs its own future replay
reconstruction checks.

Detailed evidence and wrist-camera manifests are stored under
`workspace/qualification/phase1/p1_8_nutassembly_r5_architecture/historical_current_crossover/stable_grasp_10n_candidate/`.

## v1.0 release status and current diagnostics

The v1.0.0 release accepts the scoped Phase I Core baseline and the P1.8
infrastructure regression in its declared test scope. NutAssembly itself has
no formal P1.8 qualification. The R5 stable-grasp result above is a MuJoCo G0
development result; it does not cover loaded transport, the full task, D0–D2,
or other providers.

The later V5 guarded diagnostic candidate preserves the original Expert gate
failure at `descend_to_handle / stable_height_mismatch` for GeoPhys 50/100/500
Hz. An opt-in shadow progression executes the authored 11-stage sequence and
reaches raw insertion/release/task-success predicates, but the lifecycle has
no first-observed task-success event and `final_task_success_valid=false`.
This is not canonical Expert completion or a FULL golden. The environment
does not terminate or truncate during that diagnostic continuation.

For cross-provider replay, D1 freezes the native target/applied-control stream;
D2 freezes RequestedAction and recomputes control from live canonical state.
All 12 GeoPhys-source D1/D2 runs at 50/100/500 Hz were execution-valid and had
raw task metrics true, but they remain diagnostic. Cross-provider trajectory
differences appear at the first control boundary and later reach roughly
4.6–6.5 mm in Nut-to-EE relative-vector distance and 0.063–0.081 rad in Nut
rotation. These are cross-provider differences, not the separate within-run
same-provider D2 controller-recomputation drift. GeoPhys D0 was run only at
50 Hz; it first diverges at transition 157 and is partial/invalid for exact
reconstruction. Formal P1.8 Human review and cross-provider qualification are
pending.

See the [v1.0 release progress summary](../../../docs/releases/v1.0/phase1_progress_summary.md),
[known limitations](../../../docs/releases/v1.0/known_limitations.md), and
[P1.8 final diagnostic report](../../../docs/module/task_env/p1_8_integration/final_diagnostic_replay_20261014/P1.8_Final_Diagnostic_Replay_and_Branch_Integration_Report.md).
