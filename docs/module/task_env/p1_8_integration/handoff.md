# P1.8 integration handoff

Branch: codex/p1.8-integration (review only). Resolve final HEAD with git rev-parse HEAD; remote verification/cleanup SHAs are in branch_cleanup_report.md. Repository worktree remains /home/lly/.codex/worktrees/p1-8-e-r5-controller-architecture/Geochora.

Run explicit development candidate:

```sh
PYTHONPATH=. MUJOCO_GL=egl /home/lly/miniconda3/envs/geochora/bin/python -m task_env.diagnostics.phase1.integration.stable_grasp --rate 100 --provider mujoco --output NEW_EVIDENCE_DIR
python -m task_env.diagnostics.phase1.integration.experiments --list
python -m task_env.diagnostics.phase1.integration.experiments --experiment R2-history-25N --output NEW_EVIDENCE_DIR
```

Rates 500/100/50 require equal-rate gripper cadence for current evidence. GeoPhys entry exists but 10N competence is not yet established. Historical entries reconstruct original pinned source, including archived dirty R2 diagnostic overlay. They are development experiments, not a qualification campaign.

Independent archive: /home/lly/Geochora_Evidence_Archive/p1_8_integration_20261012. Original videos/traces preserved, no embedded media. Final integration regression also copied before branch deletion. Large media remain outside Git. Archive tags preserve all old heads; checksum/bundle metadata accompany raw Evidence. Local archive is durable relative to worktree removal, not an off-host backup.

Review stable_grasp_integration_report.md and controller_api_summary.md for exact timing and ownership; regression_report.md for checks; experiment catalog for ten selected experiments; next_d0_d2_validation_plan.md for prerequisites and recording gaps. Do not use legacy nominal replay entry as current-candidate qualification.

Residual risks: auxiliary collision penetration1.7–2.0mm; single NA-S0 sample only; GeoPhys10N untested; no loaded transport/full task/replay/boundary qualification; arm hold adapter still accesses canonical R3-owned reference state explicitly; snapshot/interval-stream serialization remains proposed. Dirty unrelated P1.6/detached worktrees are untouched. Main unchanged, P1.6/P1.7 unwaived, Phase I not closed.

Next: Human Review, then separately authorize GeoPhys10N G0, recording/state reconstruction prerequisites, T1/full experts and frozen D0–D2 matrix. No broad tuning recommended or performed.
