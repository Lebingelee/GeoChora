# R1–R5 core experiment catalog

Exactly two active entries per milestone. Historical R1 controller successes collected in the R2 mass/fallback investigation remain identified as R1-controller behavior, not re-labelled phase approval. All other reports, scripts, configurations, failed results, traces and media remain in the verified independent archive.

| Phase | ID | Purpose | Original outcome / oracle | Selection reason |
|---|---|---|---|---|
| R1 | R1-forensic | Exact reconstruction of initial failed close and pose lag | forensic failure; exact target reconstruction | Separates pose lag from failure to close |
| R1 | R1-final-close | Hold the exact final legacy close request | diagnostic mechanical-contact hold; original result retained | Explains why timed close exhaustion is not mechanical authorization |
| R2 | R2-history-25N | Historical 0.1kg 25N fallback MuJoCo positive lift control | verify-lift PASS; 97.338mm, 3.054mm drift; NOT full-task acceptance | Strong same-task mechanical positive control; requires archived dirty worker overlay |
| R2 | R2-heavy-load | Same fallback with historical 1kg load | retention failure; original measured result preserved | Demonstrates readiness and load retention are distinct; historical asset only |
| R3 | R3-precheck | Nominal 0.1kg source and reset materialization | materialization diagnostics; consult archived report | Reconstructs nominal asset identity without claiming grasp competence |
| R3 | R3-lower-timeout | Nominal GeoPhys lower_nut_to_table failure | lower_nut_to_table_readiness_timeout at 28.740s | Motivates measuring dynamics instead of increasing timeouts |
| R4 | R4-C11-T0 | C11 endpoint pass versus path transient error | T0 6/6 endpoints; TB500 path peak 43.36mm | Endpoint readiness alone does not establish trajectory tracking |
| R4 | R4-C11-G0 | C11 MuJoCo TB50 outer-rate force failure | no authorization; force plateau about 2.42N | Causal baseline for fixed-rate gripper inner loop |
| R5 | R5-persistent-T0 | Persistent q_ref free-space tracking | T0 6/6; no observed arm saturation | Preserves supported arm structure and comparison to rejected rebase |
| R5 | R5-10N-G0 | Latest controller-only stable 10N grasp | MuJoCo equal rates 500/100/50 G0 PASS; development only | Current continuation baseline, no fallback/bypass/seating |

Run selected entries through `python -m task_env.diagnostics.phase1.integration.experiments --list` or `--experiment ID --output NEW_DIR`. Historical execution creates a temporary source checkout from the archive bundle, overlays the preserved worktree diff/untracked source, restores exact pinned submodule source snapshots, and uses archived configuration. It never runs an entire qualification campaign. GeoPhys availability is a separate environment prerequisite.

All unselected evidence: `/home/lly/Geochora_Evidence_Archive/p1_8_integration_20261012/file_manifest.json`; source/history: `p1_8_source.bundle`; dirty sources: worktree `tracked.diff` and `untracked/`. Historical failure results are immutable. Current archive is local durable storage; remote off-host backup remains a handoff risk.
