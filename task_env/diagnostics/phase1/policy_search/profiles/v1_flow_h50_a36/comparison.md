# V0 vs V1

| Variant | Policy | State | Pred/act | Prediction | Open loop | Replan | Epochs/updates | Success |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| V0 | Flow | 33D, qvel | 16/8 | 0.16 s | 0.08 s | 12.5 Hz | 80 / 1,360 | 1/6 |
| V1 | Flow | 33D, qvel | 50/36 | 0.50 s | 0.36 s | 2.7778 Hz | 80 / 1,360 | 1/6 |

V1 did not improve cohort success. Its six per-seed outcomes and checkpoint/config identities are recorded in `summary.json`.
