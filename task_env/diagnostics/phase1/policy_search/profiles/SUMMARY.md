# P1.6 100Hz GPU Flow policy-search summary

All variants use the same opt-in 100Hz timebase (`physics_dt=0.002 s`, `control_substeps=5`, `control_dt=0.010 s`) and frozen GeoPhys CUDA diagnostic dataset (80 train / 20 validation trajectories; manifest SHA `0e13517c…`). No demonstrations were recollected. h50/a36 predicts 0.50 s and executes 0.36 s between replans (nominally 2.78 Hz).

| Variant | Policy | State | qvel | Pred/act | Updates | Result | Rollout checkpoint rule | Checkpoint SHA256 |
|---|---|---:|---|---:|---:|---:|---|---|
| V0 | Flow h16/a8 | 33 | included | 16/8 | 1,360 | 1/6 | best validation | `563f37221c20…` |
| V1 | Flow h50/a36 | 33 | included | 50/36 | 1,360 | 1/6 | best validation | `44cfb5905727…` |
| V2 | Flow h50/a36 | 26 | removed | 50/36 | 1,360 | 3/6 | best validation | `d7d493a4bc6a…` |
| V1a | Flow h50/a36 15k | 33 | included | 50/36 | 15,000 | 1/2 pilot | final checkpoint | `c212ed39c492…` |
| V2a | Flow h50/a36 15k | 26 | removed | 50/36 | 15,000 | 6/6 | final checkpoint | `9c4e073659bd…` |

V1a used final checkpoint `c212ed39c49267594ea849288c02e0d8bc063534d4816a535630f9e3b185d818`: seed1000 passed (max lift 0.10209 m), while seed1010 failed (0.08707 m). The predeclared two-seed gate failed, so its remaining four seeds were not tested.

V2a used final checkpoint `9c4e073659bd4862d0ef9921f6c12b9e83beb893ad949e3d4d26fda961bd24e9` after exactly 15,000 updates (17 training batches per epoch, 882.35 epoch-equivalents). Training loss moved from 0.617358 to 0.001885. Validation loss reached 0.010424 at step 10000 and was 0.011625 at step 15,000. Evaluation used the final checkpoint rather than the best-validation checkpoint.

Seeds 1000 and 1010 both passed the V2a pilot, so the remaining four fixed cohort seeds were run.

| Seed | Result | Max cube lift (m) | Control frames | Simulated duration (s) | GPU inference p50 / p95 (ms) | Action clips |
|---:|:---:|---:|---:|---:|---:|---:|
| 1000 | PASS | 0.10119 | 106 | 1.06 | 28.4 / 309.5 | 0 |
| 1010 | PASS | 0.10225 | 115 | 1.15 | 28.7 / 265.6 | 0 |
| 1020 | PASS | 0.10090 | 98 | 0.98 | 28.4 / 285.0 | 0 |
| 1040 | PASS | 0.10229 | 124 | 1.24 | 26.8 / 268.0 | 0 |
| 1050 | PASS | 0.10076 | 98 | 0.98 | 29.8 / 289.3 | 0 |
| 1100 | PASS | 0.10014 | 100 | 1.00 | 27.2 / 287.5 | 0 |

All six V2a episodes met the task predicate (`cube_lift >= 0.10 m`), had zero action clipping, and passed finite state/action and simulator-freeze checks. The per-seed reports also preserve arm-target deltas, gripper deltas, and close-window cube drift. Native contact evidence was unavailable through this diagnostic route.

## Interpretation

V2a is a strong source-domain candidate on this fixed cohort. V1a passed only one of two pilot seeds while V2a passed six of six; their training and validation losses are similar. This makes the 26D no-qvel profile worth carrying forward, but the cohort does not establish that removing qvel alone caused the gain. The result is exploratory and does not establish statistical robustness, cross-provider transfer, or provider qualification.

Per instruction, ACT was not implemented after V2a's 6/6 result. No P1.8 files or provider-wide claims were modified. Checkpoint binaries and full traces remain in the local Evidence tree and are not committed.

Detailed profiles: [V0](profiles/v0_flow_h16_a8/README.md), [V1](profiles/v1_flow_h50_a36/README.md), [V1a](profiles/v1a_flow_h50_a36_15000/README.md), [V2](profiles/v2_flow_h50_a36_no_qvel/README.md), and [V2a](profiles/v2a_flow_h50_a36_no_qvel_15000/README.md).
