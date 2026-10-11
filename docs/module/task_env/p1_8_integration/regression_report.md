# P1.8 integration minimum regression

## Executed

- PickCube TB500/TB100/TB50 artifact/controller/expert/config/readiness identities: exact match to archived multirate_spec.
- Provider-free P1.1 contracts: 30 checks PASS, including contract parsing/identity/capability admission. This reuses the governed detector; no new approval inference.
- MuJoCo PickCube, existing R1 controller, seed31: PASS; 1091 transitions/1092 boundaries, final lift 105.317 mm; strict canonical H5 logical roundtrip exact. Existing session.step path used, not inner servo.
- MuJoCo 10N G0 equal rates 500/100/50: 3/3 PASS, controller-only authorization and mandatory verify-lift.
- Frozen vs integrated: all 4550 physical control boundaries exact; no physical first divergence. AppliedControl differs only target_hash owing to source/controller identity. Comparison does not assert full target metadata bitwise identity.
- Stability helper: static window accepts; measured motion rejects. Planner move/hold adapters exact arrays. Synthetic 1.5s deadline rejects expired close even before close-plan exhaustion.
- R1 production, persistent R3 arm source, original planner, canonical solution, assets, PickCube readiness, MuJoCo runtime bytes unchanged relative checkpoint 8e914da.

One initial smoke invocation used nonexistent function name expert. It failed before physics and was corrected to existing collect; both command outcomes are reported, not hidden. No grasp behavior changed to pass.

## Sources

Machine-readable results: regression_results.json; original detailed traces and audits: workspace/qualification/phase1/p1_8_integration/regression, copied into independent archive before cleanup.

Commands:

```sh
PYTHONPATH=. MUJOCO_GL=egl python -m task_env.diagnostics.phase1.integration.stable_grasp --rate 100 --provider mujoco --output NEW_DIR
python -m task_env.diagnostics.phase1.integration.regression --reference-root FROZEN_CANDIDATE_EVIDENCE --integrated-root INTEGRATION_REGRESSION_ROOT --output NEW_JSON
python -m task_env.diagnostics.phase1.p1_1_contracts --output NEW_JSON
```

No new NutAssembly D0/D1/D2, T1, full expert or SAPIEN/Genesis qualification executed. Earlier PickCube multibackend capability remains source-preserved; bounded MuJoCo smoke does not requalify all providers/rates.

Historical entry restore checks: 10/10 source hash + CLI preparation PASS. First GeoPhys bundle clone failed from pre-existing missing history; exact source snapshots resolve restore. Making archives read-only exposed a temporary overlay directory permission defect; fixed in the reconstructor only, and both affected R2 entries then passed. Failed restore logs retained in experiment_entry_validation_attempt2.json. No physics was run in these prepare checks.
