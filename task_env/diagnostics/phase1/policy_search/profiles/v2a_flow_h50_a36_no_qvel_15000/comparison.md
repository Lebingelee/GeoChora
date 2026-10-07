# V2a source-domain pilot and cohort

The fixed evaluation is gated: seeds 1000 and 1010 were evaluated first, and both succeeded before the remaining four seeds were started. All episodes used the final checkpoint `9c4e073659bd4862d0ef9921f6c12b9e83beb893ad949e3d4d26fda961bd24e9` and a deterministic policy RNG seed of `100000 + task_seed`.

| Seed | Result | Max cube lift (m) | Control frames | Simulated duration (s) | GPU inference p50 / p95 (ms) |
|---:|:---:|---:|---:|---:|---:|
| 1000 | PASS | 0.10119 | 106 | 1.06 | 28.4 / 309.5 |
| 1010 | PASS | 0.10225 | 115 | 1.15 | 28.7 / 265.6 |
| 1020 | PASS | 0.10090 | 98 | 0.98 | 28.4 / 285.0 |
| 1040 | PASS | 0.10229 | 124 | 1.24 | 26.8 / 268.0 |
| 1050 | PASS | 0.10076 | 98 | 0.98 | 29.8 / 289.3 |
| 1100 | PASS | 0.10014 | 100 | 1.00 | 27.2 / 287.5 |

Result: 6/6 task successes on the fixed GeoPhys source-domain cohort. Each report also records arm target/servo smoothness, gripper opening changes, clipping, and close-window cube drift. These remain exploratory policy-search diagnostics.
