# Real-boundary checkpoint restoration

This is infrastructure development evidence, not formal D0/D2 qualification. Source implementation checkpoint: 78eba97.

## Canonical level

Actual completed-boundary records contain CanonicalStateView, ControlFeedback, all explicitly versioned controller/coordinator owners and the executed interval stream. Independent fresh contexts initialize the original reset, verify full ResetSample and TaskArtifact mappings, then restore the exact selected checkpoint. RequestedAction, canonical action, outer target, each inner-substep target/update/application identity, readiness and complete post-observe owner snapshot are compared exactly for bounded continuation.

All six provider/rate cells passed P0–P8. Each check continues 12 control boundaries. An additional near-end-of-hold P6 verifies hold-to-unlock across all rates; 12 boundaries from the middle of a 500 Hz hold would not cover this transition. Actual phase indices are selected from recorded stage and owner state, never interpolated. The frozen coordinator locks the arm at plan exhaustion before evaluating its stability window; P3 can precede P2. That ordering is reported rather than changed.

Restore identity validation now works for a genuinely fresh owner at a later boundary, rather than requiring its pre-restore expected-step counter already to match. Required memory and stage-dependent capture/close fields are validated before any mutation. Eighteen negative cases reject with no partial owner mutation. Source-bound schemas reject future incompatible owners.

References: `checkpoints/*/tb*/canonical.json`, `stage_c_transition_coverage.json`, `stage_c_negative_restore.json`.

## Native level

Native checkpoints are separate provider-owned NPZ sidecars. They never enter task policy or canonical owner memory. MuJoCo uses public mj_getState/mj_setState with mjSTATE_INTEGRATION followed by mj_forward, and preserves runtime completed-actuator-force cache and model actuator force-cap arrays. GeoPhys uses public boundary snapshot_state/restore_state, with explicit session control/native-step counters. Restoration occurs in an independent materialized runtime.

MuJoCo TB100 and TB500 demonstrated exact 12-boundary physical continuation at all nine checkpoints. Per-cell final results are in `native/*/tb*/native_restoration.json`.

GeoPhys TB100 is not bitwise complete at contact/stability checkpoints. P0/P1 were exact; the maximum observed world-position difference over 12 boundaries at P2 was about 0.239 mm. Subsequent action/target/owner differences are disclosed separately from exact canonical reconstruction. The public GeoPhys snapshot source explicitly excludes transient contact packets/manifolds and resets those owners on restore. No engine change or private-state workaround was introduced. Actual additional rates and first-divergence records govern the final reported envelope.

Therefore arbitrary GeoPhys contact-checkpoint native continuation must not be described as exact or qualified. Canonical controller replay readiness and native physics checkpoint readiness are separate capabilities. The intended next reset-based D0–D2 campaign requires exact canonical reconstruction; native mid-contact resume is an unsupported optional mode unless separately accepted. Final infrastructure decision must preserve that scope restriction.

Final scope: canonical restoration 54/54 exact; MuJoCo native nine checkpoints × three rates exact for tested twelve boundaries. GeoPhys public native contact continuation is not bitwise exact; largest observed position discrepancy approximately 0.239 mm. This limitation does not qualify arbitrary native contact resume.
