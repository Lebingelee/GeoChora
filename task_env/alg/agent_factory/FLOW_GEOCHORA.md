# GeoChora state-only Flow preparation route

This advanced integration route prepares data and one-batch readiness. It does not qualify a trained policy.

Import `task_env.alg.agent_factory` first. Its compatibility bridge gives existing `agent_factory.*` imports the same modules and registries; no operator PYTHONPATH extension to `task_env/alg` is needed. Optional agent classes are loaded when their registered name or class export is requested.

Use `config/profiles/geochora_flow.yaml` and `config.resolution.general_resolve()` before `agents.registry.make_agent('Flow_Vanilla', cfg)`. The canonical dataset registry entry is `geochora_canonical_flow`. Its expert path is a logical dataset manifest, not a historical CPIQL H5. `build_training_bundle()` supplies `offline` plus fixed `validation`.

The adapter calls the frozen `task_env.alg.state_bc.features` utilities: 33D semantic state, 8D desired absolute-joint targets. Each real transition—including every readiness hold—produces one sample. History ends at boundary i, left padding repeats boundary0; future action begins at transition i, right padding repeats the final valid absolute-joint action. Horizons are2/16/8. No RGB, depth, fitted state normalization or native control supervision.

`get_all_actions()` fits the existing min/max action normalizer from training transitions only. `get_all_states()` reports unpadded feature statistics. Successful-expert endpoint, schema, seed roles, physical-provider identity, file hash, logical hash and lower-layer identities are checked on load.

Preparation diagnostics:

```sh
PYTHONPATH=GeoPhys/src:. PYTHONDONTWRITEBYTECODE=1 \
/home/lly/miniconda3/envs/geochora/bin/python -m task_env.diagnostics.phase1.p1_6_flow_preparation
```

Run only after the frozen100-seed collection has completed. Existing output artifacts are not overwritten. Collection helper `flow_preparation.collection.freeze/collect` uses the unchanged P1.6 expert collector with a verifier-compatible collection manifest; the retained legacy state_bc learner field is not the Flow training configuration.

Future training authority is `cfg.train.actor_iters=20*len(train_loader)`, where the actual train loader uses shuffle/drop_last=True and the selected CUDA batch size. The profile's zero iteration/step fields are intentionally unusable until preparation materializes them. `agent_sp.iters` is a retained legacy field, not the budget. Full training is a separate human-authorized task.

Flow logging emits train means every100 updates plus the final partial window, and full validation at0/every1000/final steps. Fixed validation seed2026 is isolated from training RNG. Validation uses all samples, eval/no-grad, no optimizer update. A single final validation is sufficient when the final step coincides with a periodic validation. JSONL and summary report window and validation losses, minima, steps and epoch equivalents.

Logical resolved-config hashing excludes only the self-referential `agent_sp.artifact_identity` field. Dataset hashing covers the canonical manifest, not H5 bytes alone. Flow checkpoint metadata contains config/dataset/feature/action identities; file SHA256 is recorded externally after save. Loading rejects identity mismatches. CPU placement may override both device fields while all remaining config content must match. Normalizer buffers are part of the state dict. Smoke checkpoint metadata explicitly says one optimizer step, not a trained or qualified policy.

The state-only path needs requirements-flow.txt; torchvision is only loaded for an explicitly selected visual ResNet. The default19,512,264-parameter Flow model is unchanged. Preparation uses float32, batch512, then256/128 only on CUDA OOM; no AMP or model-size tuning.

Failed collection episodes are never removed. Strict dataset construction rejects failed expert endpoints by default. Preparation may explicitly set dataset.config.allow_failed_for_smoke=True to retain every schema-valid failed trajectory in the declared corpus for single-batch instrumentation/readiness ONLY. Dataset training_eligible/failed_seeds are derived from actual final boundaries. Flow.start_train rejects any failed training OR validation episode before normalizer fitting or optimizer use. A failed frozen seed makes preparation partial_with_localized_failure and future full training unauthorized, regardless of smoke results.

Success-conditioned successor: dataset manifest `geochora-canonical-flow-dataset-v1` is additive. It preserves all attempts, explicitly lists selected successes, and recomputes first-success selection over the frozen ascending supplement streams. Learner loading uses exactly80selected train and20selected validation successful expert trajectories. Unselected failed attempts do not disqualify v1; insufficient bounded successes do. Every selected file still passes strict schema/hash/provenance/count/endpoint validation. The original v0 all-attempt diagnostic corpus keeps its fail-closed behavior. Corpus eligibility permits a later separately authorized full-training task; supplementation itself runs only one optimizer-step smoke, never policy evaluation.
