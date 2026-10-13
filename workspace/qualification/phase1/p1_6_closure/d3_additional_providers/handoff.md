# P1.6 Additional Provider Validation Handoff

Status: completed; this is a bounded 10-seed provider behavior check, not provider-wide qualification.

## Frozen identities

- P1.6 source: 9d7c42b321eb24633df670a47e3261b62aab2c7b
- Provider session source: 5e7012c70a83f26d1f6a0e51b3160efc00006c35
- Evaluation spec SHA256: 33abf5d55aa2240017031c9d1f5aedddca99ef1ec35af14db4734dceddf670e3
- V2a FINAL checkpoint SHA256: 9c4e073659bd4862d0ef9921f6c12b9e83beb893ad949e3d4d26fda961bd24e9
- TaskArtifact SHA256: fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4
- 100Hz dataset manifest SHA256: 0e13517ce9f179daf7d4c525a6fb7d33629d3bb6fdd7683b4f06ac9492cf10dd
- Policy inference: CUDA; Genesis and SAPIEN physics: CPU.
- All episodes used the same locked ResetSample per seed, and every report confirms the sample was unchanged.
- Synchronous inference froze the simulator on every inference call; all states/actions were finite and no action clipping occurred.
- No training, retries, seed replacements, P1.8 worktree edits, or provider-core edits were performed.

## Per-seed outcomes

| Validation seed | GeoPhys (prior D3) | MuJoCo (prior D3) | Genesis | SAPIEN |
|---:|---:|---:|---:|---:|
| 2200 | PASS (0.10192 m) | PASS (0.10104 m) | PASS (0.10117 m) | PASS (0.10056 m) |
| 2202 | PASS (0.10022 m) | PASS (0.10310 m) | PASS (0.10161 m) | PASS (0.10250 m) |
| 2204 | PASS (0.10121 m) | PASS (0.10118 m) | PASS (0.10113 m) | PASS (0.10072 m) |
| 2206 | PASS (0.10327 m) | PASS (0.10126 m) | PASS (0.10062 m) | PASS (0.10035 m) |
| 2208 | PASS (0.10314 m) | PASS (0.10197 m) | PASS (0.10049 m) | PASS (0.10076 m) |
| 2210 | PASS (0.10042 m) | PASS (0.10090 m) | PASS (0.10007 m) | PASS (0.10005 m) |
| 2212 | PASS (0.10219 m) | PASS (0.10072 m) | PASS (0.10087 m) | FAIL (0.01034 m) |
| 2214 | PASS (0.10392 m) | PASS (0.10184 m) | PASS (0.10243 m) | PASS (0.10090 m) |
| 2216 | PASS (0.10247 m) | PASS (0.10001 m) | PASS (0.10194 m) | PASS (0.10071 m) |
| 2219 | PASS (0.10080 m) | PASS (0.10232 m) | PASS (0.10194 m) | PASS (0.10160 m) |

- Genesis: 10/10 succeeded.
- SAPIEN: 9/10 succeeded.
- Previous GeoPhys and MuJoCo D3 validation results were 10/10 each; those episodes were not rerun.
- Paired Genesis/SAPIEN results: 9 PASS/PASS and 1 PASS/FAIL. The only discordant seed is 2212.

## Localized SAPIEN result

Seed 2212 used the exact D3 ResetSample and ran one episode to the frozen 2500-control-step limit (25.0 simulated seconds). It did not reach the 0.10 m task-success threshold; maximum measured cube lift was 0.0103369 m. The run had no runtime error, remained finite, had no action clipping, and passed the simulator-frozen inference checks. No retry was made.

## Evidence paths

- Frozen protocol: workspace/qualification/phase1/p1_6_closure/d3_additional_providers/d3_eval_spec.yaml and workspace/qualification/phase1/p1_6_closure/d3_additional_providers/d3_eval_spec_lock.json
- Aggregate results: workspace/qualification/phase1/p1_6_closure/d3_additional_providers/d3_summary.json and workspace/qualification/phase1/p1_6_closure/d3_additional_providers/d3_summary.md
- Per-provider episode reports/traces: workspace/qualification/phase1/p1_6_closure/d3_additional_providers/genesis/ and workspace/qualification/phase1/p1_6_closure/d3_additional_providers/sapien/
- Runtime versions: workspace/qualification/phase1/p1_6_closure/d3_additional_providers/runtime_environment.json
- Provider source manifest: workspace/qualification/phase1/p1_6_closure/d3_additional_providers/provider_source_manifest.json

Interpretation: this V2a checkpoint succeeded on all ten tested validation ResetSamples through Genesis and nine through SAPIEN. The single SAPIEN seed 2212 failure shows the bounded result is not uniform across these two adapters; no broader robustness or qualification claim follows.
