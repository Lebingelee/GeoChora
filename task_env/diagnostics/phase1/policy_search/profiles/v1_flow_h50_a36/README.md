# V1 Flow h50/a36 profile

This immutable diagnostic profile uses the frozen 100 Hz GeoPhys CUDA corpus with Flow_Vanilla / ConditionalUnet1D. It retains the full 33D state including arm joint velocity and uses obs=2, pred=50, act=36. At 100 Hz that is a 0.50 s prediction span, 0.36 s open-loop execution span, and 2.7778 Hz nominal replanning.

Training used CUDA float32, batch 512, 80 epoch-equivalents (17 steps/epoch; 1,360 updates), AdamW at 1e-4 with 1e-6 weight decay. The best checkpoint is selected by minimum fixed validation loss. Its identity and the complete per-seed rollout summary are in `summary.json`; large checkpoints and traces remain in local experiment Evidence.

The fixed cohort result was 1/6, unchanged from V0. This is exploratory source-domain evidence, not a qualification claim. No lower-layer behavior, P1.8 work, or public/main was modified.
