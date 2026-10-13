# V2a — Flow h50/a36, no-qvel, 15,000 updates

This immutable exploratory profile reuses the frozen 100Hz CUDA-collection corpus and changes no task, controller, expert, runtime timebase, or provider behavior. It uses Flow_Vanilla / ConditionalUnet1D with a learner-side 26D semantic observation that omits the seven arm-velocity features. The training budget is exactly 15,000 optimizer updates.

The final checkpoint was used for the predeclared pilot-first evaluation. Seeds 1000 and 1010 both passed, so the remaining four fixed cohort seeds were run; all six succeeded. This is a source-domain policy-search result, not cross-provider or provider qualification.

The large checkpoints and full traces remain in the local workspace evidence tree. `summary.json`, the resolved configuration, locked training/rollout specs, and provenance are the compact review record.
