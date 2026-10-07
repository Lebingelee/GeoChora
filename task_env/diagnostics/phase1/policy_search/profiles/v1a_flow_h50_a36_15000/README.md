# V1a Flow h50/a36 — 15,000 updates

V1a retains V1's 33D state (including arm velocity), Flow_Vanilla / ConditionalUnet1D, h2/p50/a36, the frozen 80/20 100 Hz GeoPhys CUDA corpus, and all prior optimization/normalization settings. It trains for exactly 15,000 float32 CUDA optimizer updates (17 batches per epoch-equivalent; 882.35 epoch-equivalents).

The predeclared rollout checkpoint was the final update, not the best-validation checkpoint. Pilot seed1000 succeeded; seed1010 failed. Because both fixed pilots did not succeed, the four remaining cohort seeds were not run. The exact reports, traces, validation curve, checkpoint hashes, and locked pilot protocol are represented in the local experiment Evidence and summarized in `summary.json`.

This is exploratory source-domain evidence only. No lower-layer behavior, P1.8 code, or public/main was modified.
