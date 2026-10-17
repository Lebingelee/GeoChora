# Planner, tracking and gripper prerequisites before NutAssembly acceptance

Operator steering: 2026-10-07. This is source/recorded-data analysis and a provider-free command-sampling fixture. No physics rerun, no frozen production change, no NutAssembly qualification claim.

## Finding

The concern about frequency dependence is supported by code. Rate-aware planning is necessary but insufficient: the current stack mixes physical-time sampling with per-control-boundary controller/gripper updates. The R2 task search has not isolated those layers. Its 13 failed paired candidates must not be interpreted as proof of an intrinsic provider physics defect.

`control_dt = physics_dt * control_substeps`; frequency is its inverse. Changing substeps with fixed physics_dt changes control frequency. Changing physics_dt and substeps together can preserve control frequency while changing integration, which is a different experiment.

## Planner ownership

CartesianPosePlanner uses cubic smoothstep and per-tick bounds. Its conservative count is max(ceil(1.5*distance/displacement_limit), ceil(sqrt(6*distance/second_difference_limit)), analogous rotation counts, requested count). To preserve authored physical speed/acceleration:

- displacement_limit = speed_m_s * control_dt
- second_difference_limit = acceleration_m_s2 * control_dt^2
- rotation limits use the same dt/dt^2 scaling
- hold/settle/budget ticks = ceil(seconds/control_dt)

These are mechanically derived parameters from one physical configuration, not independently tuned configurations for each rate. Float32 sampling/ceil introduces small duration differences. A command trajectory is not an achieved trajectory.

Provider-free fixture: 0.1m straight translation, identity orientation, 0.04m/s, 0.15m/s². All three sampled command bounds pass; these are representation checks, not newly accepted physics tolerances.

| Hz | substeps | path ticks | duration s | max command speed m/s | max command acceleration m/s² | gripper command ceiling m/s | force-mode correction m/s | legacy close duration s |
|---|---|---|---|---|---|---|---|---|
| 50 | 10 | 188 | 3.760 | 0.039892 | 0.042003 | 0.100 | 0.005 | 0.500 |
| 100 | 5 | 376 | 3.760 | 0.039893 | 0.042214 | 0.200 | 0.010 | 0.250 |
| 500 | 1 | 1876 | 3.752 | 0.039980 | 0.044703 | 1.000 | 0.050 | 0.050 |

## Arm tracking ownership

CanonicalPandaController._compute_arm derives one clipped DLS increment from achieved q on every boundary. It applies ik_position_gain=0.9, ik_max_delta_q=0.10rad, Cartesian position clamp=0.025m, then servo=desired+2.5*(desired-achieved). Its position/rotation deadbands are 0.006m/0.035rad. These operations do not take dt. Their closed-loop behavior therefore cannot be declared invariant merely because the planner is resampled.

The 6mm deadband can permit a steady pose residual unacceptable for precision insertion. This is a property to measure against the task geometry; no deadband or task threshold was changed. Do not multiply every IK/servo gain by dt blindly: these are an achieved-state IK/servo scheme, not all continuous-time rates. A clean timebase-aware controller design needs an explicit stability/precision contract and separately authorized versioning if accepted behavior changes.

## Gripper ownership

ProductionCanonicalPandaController.compute is called exactly once per control boundary. Non-force-mode commanded opening changes at most 0.002m per compute. Force mode activates on closing when measured closing force reaches max(0.5N,0.1*30N)=3N, initializes servo opening from measured opening minus 30N/2500N-per-m (=12mm), and subtracts 0.0001m per compute while force error exceeds the 1N deadband. Neither step is dt-normalized.

The table's gripper values are command ceilings/correction rates, not measured mechanical speed or achieved force. Contact, actuator saturation and servo stiffness matter. Lower control frequency provides fewer force corrections per physical second; higher frequency increases them. Holding the final public close action is still an evolving controller command, not a fixed native servo setpoint.

Readiness based on force alone cannot prove capture: a finger contacting the table/nut edge can also create load. Require object-relative pose persistence and a bounded verification lift/transport before insertion. Existing task heuristics remain frozen and are not sufficient evidence of mechanical attachment by themselves.

## Preserved six failed runs

Source: immutable R1 R0 analysis, SHA256 745062a0796f7b837dfe08216fa3119a70a0a7adb2c4c96a12c875b24e6d25a1. Pose residual is distance between the emitted EE request and measured EE, not raw EE-to-handle distance (the grasp intentionally has an offset). All end-close desired openings are zero. These runs used unchanged legacy tick counts; they are not a controlled isolated frequency experiment.

| Profile | Provider | end-descend residual mm | end-close residual mm | close physical s | measured opening mm | servo opening mm | force N | grasped heuristic |
|---|---|---|---|---|---|---|---|---|
| NA-TB100 | geophys | 1.037 | 4.469 | 0.250 | 63.400 | 58.625 | 10.417 | False |
| NA-TB100 | mujoco | 1.909 | 5.595 | 0.250 | 51.306 | 49.056 | 4.240 | False |
| NA-TB50 | geophys | 1.350 | 3.333 | 0.500 | 68.760 | 63.584 | 12.940 | False |
| NA-TB50 | mujoco | 3.511 | 5.719 | 0.500 | 67.332 | 65.434 | 4.249 | False |
| NA-TB500 | geophys | 29.971 | 5.987 | 0.050 | 67.941 | 65.487 | 0.000 | False |
| NA-TB500 | mujoco | 30.228 | 5.978 | 0.050 | 67.940 | 65.485 | 0.000 | False |

The same 25-tick close lasts 0.05/0.25/0.5 seconds at 500/100/50Hz, versus 0.8333 seconds at historical30Hz. At TB500 the pose is additionally not ready. At all rates opening remains above the historical successful close opening (~34.3mm). These observations support separate pose/closure-time/control-interaction hypotheses, not one uniquely proven cause. R2's slow physical-time candidate obtained GeoPhys verification capture but not dual-provider capture, so planner scaling alone has not closed the boundary.

## Required prerequisite sequence

1. Provider-free path contract: freeze one physical trajectory (straight translation, pure rotation, combined smooth path, stop/hold), speed/acceleration, orientation continuity, duration and sampling convention. Check sampled commands at 50/100/500Hz. Test caps when caller supplies explicit steps.
2. Unloaded arm tracking: replay that same physical path on both providers at all three rates. Measure requested→canonical→desired-joint→servo-joint→achieved EE; track pose/orientation RMS/max/end-hold error, lag, achieved speed/acceleration, joint limits/saturation and rest drift. Derive precision bounds from grasp/insertion geometry before runs. Keep integration settings fixed where possible; distinguish integration changes from control-rate changes.
3. Unloaded gripper: open/close/hold at each rate. Measure desired/commanded/measured opening versus physical time, force-mode entry, opening-direction reset, saturation and feedback boundary alignment. Native force diagnostics remain private. Decide whether rates should become physical units in an additive versioned gripper/controller contract; do not silently reinterpret existing per-tick configs.
4. Loaded capture: fixed grasp pose, close until a frozen physical readiness predicate or timeout, verification lift and short transport. Measure nut-relative-hand translation/rotation drift, slip, force, contacts and measured opening. No peg insertion or planner waypoint search until capture persists.
5. NutAssembly expert: compose previously verified arm paths and grasp/release readiness, then assess alignment/insertion. Produce successful source trajectories before D0/D1/D2.

Do not claim stability from a smooth command alone. If frozen current control fails these prerequisites, recover it under a separately governed additive control version before further task acceptance. No provider-specific gains, post-hoc tolerance changes, contact tuning or qualified claim arises from this analysis.
