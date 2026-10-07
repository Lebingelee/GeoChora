# P1.6 Closure Evidence Index

Generated: 2026-10-07T14:36:45.397889+00:00

Final closure addendum audited: 2026-10-07. The original branch-consolidation index digest is retained in `evidence_index.json` as the pre-addendum index SHA256.

Closure: `codex/p1.6-closure` at `9d7c42b321eb24633df670a47e3261b62aab2c7b`; D3 runner commit `9d7c42b321eb24633df670a47e3261b62aab2c7b`.

Prior CanonicalTrajectory Evidence remains `partial_with_localized_failure`; all 284 indexed files passed recorded SHA256 verification. Historical seed1000 D0-D2 are indexed only and were not rerun.

## Historical seed1000 D0-D2

| Probe | Status | Report SHA256 |
|---|---|---|
| D0 | historical_pass | `1fee51838b012f26b577de20016eef367f363a7727893863de1d9b183ff08974` |
| D1 | historical_pass | `d2b865e04532636a97f1c18aa8715b9b3aff901aa84555853e5dca968ab6d83a` |
| D2 | historical_pass | `ae76bac590242fe0de1b5baa1f3701dbbad93f4f8a2eae1ac3285c8cf29fe05b` |

Trajectory logical hash `a10a579809ec80a7abd986d65e2a48d54a917ff353d2fa073d07daffcbdc3f27`; ResetSample `fcea59824ef61219c11016f5ca5a22ba05f72d47ee4e302150e36ce8aaed7670`. The original D0-D2 run used source commit `cda511f49eb544dabe685ec1dbcc6345884d66c8`; its provenance explicitly records a dirty working tree and the modified `flow_training.py` source snapshot. The exact status, source-file SHA256, diff SHA256, saved scripts, commands, expert H5 file SHA256, and trajectory logical hash are linked in JSON.

## 100Hz route

TaskArtifact `fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4`; corpus manifest `0e13517ce9f179daf7d4c525a6fb7d33629d3bb6fdd7683b4f06ac9492cf10dd`; logical corpus identity `f2ebc763dd98ec5c78ec77c2d988255ec112ca24e331afebeea2fe45a5bff478`; physics dt 0.002 s × five substeps = 0.010 s control dt. Temporal, expert, corpus and 100Hz replay reports are linked in JSON.

| Variant | Updates | Best checkpoint SHA256 | Final checkpoint SHA256 |
|---|---:|---|---|
| V0 | None | `563f37221c20e031bd20be095a8ff34dfcc279622181a4678371ad1c53a7ea37` | `6639a4d650dbfc7f35c87ffbaa4aee845d09de381a7dbef91f197ca519193e6f` |
| V1 | 1360 | `44cfb590572768be28e66cb7bcfba83bc029d761ddfa29ab29edda3f48c2774f` | `7ae4f6ac7f8dde6376978c61ba243396fde46d3c42c52720d4353cb89c4d5605` |
| V2 | 1360 | `d7d493a4bc6a7e88b6a887ca571cc129f51b4984d65a4067d987181526c7034a` | `9488eec46539282b4de70f953452ccdba59abed1a73b65ec7da2f46174819ae5` |
| V1a | 15000 | `92608239ac3521959e17732fb1dbcbb108182441b46b7b66aeadfba3323a62f2` | `c212ed39c49267594ea849288c02e0d8bc063534d4816a535630f9e3b185d818` |
| V2a | 15000 | `269b60b9d495c14077621c9af39bcece5b75fc6e15db7921c8ff66cdc32c3c0b` | `9c4e073659bd4862d0ef9921f6c12b9e83beb893ad949e3d4d26fda961bd24e9` |

## D3 bounded cross-provider check

Locked spec SHA256 `cfa389d3e8bffce4a852e70b1b5b418efb2b6ea6f9bde739fb67e74acea7a60f`; V2a FINAL checkpoint SHA256 `9c4e073659bd4862d0ef9921f6c12b9e83beb893ad949e3d4d26fda961bd24e9`. 40 one-shot episodes completed: GeoPhys train 10/10 and validation 10/10; MuJoCo train 10/10 and validation 10/10. All 20 paired seeds were PASS/PASS. Same checkpoint bytes, ResetSamples, 26D no-qvel observation, public absolute_joint action route, CUDA policy inference. GeoPhys used diagnostic CUDA physics; MuJoCo used native CPU physics. Simulator-freeze checks passed. This bounded sample is neither statistical robustness nor provider-wide qualification.

`d3/file_manifest.json` hashes all pre-manifest D3 files, including the lock/spec, per-episode reports/traces, commands/logs and summaries.

## Supplementary Genesis / SAPIEN validation

The same 10 frozen validation seeds were run in an additional local environment. Genesis 1.4.3 passed 10/10; SAPIEN 3.0.3 passed 9/10, with seed 2212 reaching the 2500-step cap at 0.0103369 m maximum lift. Both used CPU physics and CUDA policy inference. All 20 reports confirm the same checkpoint and unchanged paired ResetSamples, frozen simulation during inference, finite state/actions, zero clipping, and no runtime errors. All 111 files in `d3_additional_providers/evidence_manifest.json` match their recorded size and SHA256.

This is supplementary local-environment Evidence only. Its session implementation came from source commit `5e7012c70a83f26d1f6a0e51b3160efc00006c35` via a temporary source snapshot outside this P1.6 branch. No provider code was copied into P1.6; Genesis/SAPIEN are not qualified by these policy episodes, and this route is not reproducible from `codex/p1.6-closure` alone.

## Final closure candidate

The core bounded result is ready for Human closure review: the same frozen V2a FINAL checkpoint passed 10/10 train-support and 10/10 validation-support seeds on both GeoPhys and MuJoCo. All 205 core D3 manifest entries and all 111 supplementary manifest entries passed integrity checks. The final recommendation is approval within the bounded PickCube / V2a / 100Hz / GeoPhys–MuJoCo scope only.

The original state_bc `partial_with_localized_failure`, failed early Flow variants, and historical dirty-source D0–D2 provenance remain part of the record. D0–D2 were not rerun. No training, public/main update, P1.8 modification, or provider-core change occurred during closure packaging. No `phase_decision.yaml` was created; formal approval remains pending Human Review. P1.7 remains deferred and Phase I is not declared complete.
