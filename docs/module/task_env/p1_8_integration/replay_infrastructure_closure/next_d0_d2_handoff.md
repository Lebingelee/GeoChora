# Next D0–D2 handoff

Replay infrastructure: GO for canonical reconstruction and reset-based replay preparation. This is not a formal D0–D2 result.

Required before campaign: Human Review; GeoPhys/MuJoCo frozen 10 N candidate loaded tracking T1 and complete expert competence; successful goldens at equal 500/100/50 Hz; explicit controller/coordinator memory initialization and serialization. Keep +1 mm diagnostic grasp offset scope explicit; do not silently promote it to a qualified task profile.

Current evidence: six live G0 cells, H5 logical exact roundtrip, v0 compatibility, integer/native clock validation, 54 P0–P8 canonical restorations, hold-unlock coverage, malformed-restore rejection, fresh R1 legacy smoke and fresh integrated TB100 G0 on both providers. No thresholds or physics changed.

MuJoCo native restoration: tested twelve-boundary continuation exact at all nine points and rates. GeoPhys native public snapshot excludes transient contact state; contact continuation is not bitwise exact (maximum observed position discrepancy approximately 0.239 mm). Arbitrary GeoPhys contact-state native resume is unsupported; use reset-based replay. Native data never enters canonical policy.

Suggested entry: python -m task_env.diagnostics.phase1.integration.live_recording --provider mujoco --rate 100 --output NEW_DIRECTORY, with PYTHONPATH=.:GeoPhys/src:GeoPhys and pinned geochora Python environment. Historical reconstruction: python -m task_env.diagnostics.phase1.integration.experiments --experiment ID --output NEW_DIRECTORY --prepare-only.

Future matrix: two primary providers × three equal rates; six D0 source cells, twelve symmetric D1 and twelve symmetric D2 cells after competence/goldens. D0 requires deterministic canonical state/action/control/memory equivalence; D1 exact recorded target execution; D2 recomputation from public state/feedback/action plus frozen memory semantics. Preserve T+1/T, exact integer substep counts and versioned clock rule. Fail closed at first discrepancy; record first divergent owner/field/boundary. Never expand capture thresholds to obtain PASS.

Campaign: BLOCKED pending prerequisites and Human Review. T1/full task/formal D0–D2/SAPIEN/Genesis were not run. Work stops after this handoff at user's quota request; no automatic continuation.


## Reproduction entry points

- Live recorder: `python -m task_env.diagnostics.phase1.integration.live_recording --provider {geophys|mujoco} --rate {50|100|500} --output NEW_DIRECTORY`.
- Load/validate a recorded H5: `from task_env.trajectory.canonical.execution import load; episode = load(".../execution.h5")`.
- Canonical checkpoint replay validation: `python -m task_env.diagnostics.phase1.integration.checkpoint_validation --provider PROVIDER --rate HZ --input PATH/execution.h5 --output NEW_DIRECTORY`.
- Provider-native diagnostic restore: `python -m task_env.diagnostics.phase1.integration.native_checkpoint --provider PROVIDER --rate HZ --reference PATH/execution.h5 --output PATH/native --restore-only`.
- Historical recipe/source check: `python -m task_env.diagnostics.phase1.integration.experiments --experiment EXPERIMENT_ID --output NEW_DIRECTORY --prepare-only`.

These tools are infrastructure diagnostics. Their existence and smoke results do not establish task qualification or full D0/D1/D2 acceptance. The handoff matrix and oracle remain in `docs/module/task_env/p1_8_integration/next_d0_d2_validation_plan.md`.
