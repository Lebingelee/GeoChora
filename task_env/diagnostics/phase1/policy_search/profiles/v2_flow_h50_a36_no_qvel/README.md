# V2 Flow h50/a36 without arm velocity

This immutable profile uses the frozen GeoPhys CUDA 100 Hz corpus (80 train / 20 validation) with Flow_Vanilla / ConditionalUnet1D, h2/p50/a36, and a semantic learner-side selector excluding only `arm_velocity7`. The raw canonical 33D feature contract and trajectories are unchanged; the selected observation is 26D.

Training used CUDA float32, batch 512, 80 epoch-equivalents (17 steps/epoch; 1,360 updates), AdamW at 1e-4 with 1e-6 weight decay. The rollout checkpoint was selected by minimum fixed validation loss. This original V2 cohort completed all six locked seeds before the later pilot-first request and achieved 3/6. See `summary.json` for per-seed outcomes and identities. V1a/V2a use the later pilot-first protocol and final checkpoint as requested.

This is exploratory source-domain evidence only. No lower-layer behavior, P1.8 code, or public/main was modified.
