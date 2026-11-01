# LIBERO controller profile history supplement

This supplement preserves the v3–v5 profile notes removed from the active
controller module during the R-route package cleanup. The record was
transcribed from `bench_deploy/libero/controllers/osc.py` at commit
`758b28ab40a16898f98ba7f24cfca73fdcf14fca`. It records the rationale then
attached to each profile; it is not a substitute for the native run artifacts
or an independent validation of those observations.

All three profiles were unqualified joint-space PD experiments for native R07
task #1. They retained the source motor control ranges and joint limits, with
torque commands clamped to the compiled source control ranges. Their notes
explicitly did not claim a stability proof or controller qualification.

| Profile | Kp (Nm/rad) | Kd (Nm·s/rad) | Historical note |
| --- | --- | --- | --- |
| `libero-spatial-bowl-to-plate-joint-space-pd-v3` | 100 on all seven joints | 20 on all joints; joint 2 = 40 | Attempt 006 reached 148 successful boundaries before joint 2 crossed its source upper limit. Attempt 007 with uniform Kp=200/Kd=40 saturated all seven torque channels and drove joint 4 across its lower range within 10 boundaries. The v3 rationale restored uniform Kp=100/Kd=20 and kept joint 2 Kd=40 because its attempt 006 trace retained outward velocity after the target reversed. The note called for native motion and fault gates. |
| `libero-spatial-bowl-to-plate-joint-space-pd-v4` | 20 on all seven joints | 4 on all joints; joint 2 = 8 | Run 009 with source gravity feed-forward and Kp=100/Kd=20 (joint 2 Kd=40) crossed joint 3 by 0.004751 rad at boundary 25 after several joints began oscillating and saturating. The preceding v3 run 008 without feed-forward reached boundary 196 before joint 2 crossed its upper source limit by 0.002073 rad. The v4 note reduced the gains fivefold to test lower closed-loop bandwidth under a 20 Hz outer loop and 2 ms × 25 hold. |
| `libero-spatial-bowl-to-plate-joint-space-pd-v5` | 40 on all seven joints | 8 on all joints; joint 2 = 16 | The v5 note repeated the run 009 and run 008 observations above. Run 010 with source gravity feed-forward and Kp=20/Kd=4 (joint 2 Kd=8) stayed within source limits and emitted no MuJoCo warnings, but all three episodes entered descend near boundary 900 and horizon-truncated before task success. The v5 rationale doubled those gains while retaining the 20 Hz loop, 2 ms × 25 hold, and 2 mm/10 mrad per-boundary motion caps to test reference tracking. |

The active v6 stability rationale remains in `controllers/osc.py` as
`_GAIN_STABILITY_RATIONALE`; the removed dictionary's v6 entry duplicated that
active text. The v3–v5 dictionary entries had no current code or test callers
at follow-up input commit `758b28ab40a16898f98ba7f24cfca73fdcf14fca`.

## Legacy operational-space config V1

`LiberoOperationalSpaceConfigV1` was also exported by `controllers/osc.py` at
the same follow-up input commit. Its defaults were position Kp 150 N/m, orientation
Kp 150 Nm/rad, damping ratio 1, nullspace Kp 10 s⁻², 20 Hz outer control,
2 ms physics steps, 25 substeps, and
`torque_zero_order_hold_per_outer_step_v1`. Validation required finite positive
gains, the fixed 20 Hz / 2 ms × 25 cadence, and that hold policy.

The class had no package-local production caller. It was only the default
argument for private `_SourceOSCController`; the active V6/V7 construction
path passed `LiberoOperationalSpaceConfigV2`, which retains the same gains and
cadence but recomputes torque per physics substep. The maintainer approved
removing the unused V1 export and private fallback. The V2 config and active
controllers remain unchanged. The removed V1 code is recoverable from input
commit `65891af449918e7162c78dec7c01a3bc0b7eecd0`.
