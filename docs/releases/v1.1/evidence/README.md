# GeoChora v1.1.0 Release Acceptance Evidence

**RELEASE_CANDIDATE — NOT_PUBLISHED**
**Evidence class:** bounded acceptance and smoke evidence; no new formal qualification.

This Git-trackable index summarizes the acceptance evidence selected for the
v1.1.0 candidate. It reuses the existing [candidate capability matrix](../../../module/task_env/capability_matrix_v1_1_0_candidate.json),
[source/recovery manifest](../source_recovery_manifest.json), and named
acceptance reports. It does not define a second Artifact, provenance, or
qualification schema.

The S5-C3 governance and hash-check report is
[here](../../../module/task_env/p2_0_s5_c3_minimal_release_evidence.md).
The current TaskEnv retention audit is
[here](../../../module/task_env/p2_0_s5_c4_evidence_retention_audit.md).
The L3 retirement review and separate approval proposals are in the
[S5-C6 report](../../../module/task_env/p2_0_s5_c6_l3_retirement_preparation.md)
and the [Batch A](retirement/l3_a_approval_candidate.json),
[Batch B](retirement/l3_b_approval_candidate.json), and
[Batch C](retirement/l3_c_approval_candidate.json) proposals. The
[post-deletion receipt template](retirement/deletion_receipt_template.json)
is not an authorization.

## L1 — Release acceptance metadata

The files in this directory are small release metadata intended to be retained
in Git:

- [Four manipulation/provider acceptance summaries](manipulation_acceptance.md)
- [Recording, regression, learning, and rendering smokes](system_smoke_acceptance.md)
- Candidate API, task identities, and status definitions in the [capability matrix](../../../module/task_env/capability_matrix_v1_1_0_candidate.json)
- Implementation and recovery identities in the [source/recovery manifest](../source_recovery_manifest.json)

The wider L1 release metadata also includes the v1.1.0 release scope/version
policy, installation and migration guides, public API/task inventory, known
limitations, test summary, backup/readiness records, the single candidate
capability matrix, the S2-C1/S2-C2 source identity records, S3/S4 recovery
manifests, S4.5 workflow receipts, and the current TaskEnv migration guide.
The exact paths are enumerated in the S5-C4 audit. They are present in local
Git through `28dc2f48`; the C4 changes remain local and none of these latest
retention updates has been integrated into public `develop`.

The summaries preserve bounded results and raw-evidence hashes. Hash metadata
can identify a missing file but cannot restore its contents.

## L2 — Selected raw evidence inventory

All paths below are existing ignored workspace files. Their sizes and hashes
were checked on the current local disk on 2026-10-17 against the candidate
matrix or source/recovery records where available. No files were copied,
moved, or modified. The five original task/recording H5 files total
**24,301,972 bytes**; adding the bounded SB3 return H5 brings the six-H5 total
to **24,333,284 bytes** (about **23.21 MiB**).

### Accepted full-route and recording H5 files

| Scope | Local path | Size (bytes) | SHA-256 |
| --- | --- | ---: | --- |
| PickCube, GeoPhys CPU, seed 31 | `workspace/maintenance/p2_0_part_b_s2_c1_20261016/pickcube_geophys_v4/execution.h5` | 878,784 | `cd39b1d2e6c14c6a3fc39b744e26657448aedaf1d29b34ac60fcaec0026d9108` |
| PickCube, MuJoCo CPU, seed 31 | `workspace/maintenance/p2_0_part_b_s2_c1_20261016/pickcube_mujoco_v4/execution.h5` | 2,649,928 | `579c676d542f53b1dde8e7488ccff6e1fd01b7e2d6b56e2e975e759d3af69018` |
| NutAssembly, GeoPhys CPU, NA-S0 seed 19 | `workspace/maintenance/p2_0_part_b_s2_c2_20261016/nutassembly_geophys_final/execution.h5` | 9,295,444 | `e539d5b2662d191c0a70b1ac9dd593842279397b8627f0e3871d8852c78c2271` |
| NutAssembly, MuJoCo CPU, NA-S0 seed 19 | `workspace/maintenance/p2_0_part_b_s2_c2_20261016/nutassembly_mujoco_final/execution.h5` | 8,827,904 | `f7000d28e1a47363542bef8909341d5a13582175941b394987ad31f0ea4f5931` |
| Canonical PickCube recording, MuJoCo CPU, seed 31 | `workspace/maintenance/p2_0_b_s4_5_a_20261016/5d57272d/pickcube_mujoco_seed31.h5` | 2,649,912 | `e22bcadbb142c81f2bdd8f12a432b82b22cef0c25ddeba8cec29f764bca87ae8` |

### Supporting results and key logs

| Evidence | Local path | Size (bytes) | SHA-256 |
| --- | --- | ---: | --- |
| PickCube GeoPhys result JSON | `workspace/maintenance/p2_0_part_b_s2_c1_20261016/pickcube_geophys_v4/result.json` | 24,698 | `f746f7a4f3785a762cd9fa174e263fd1415b6920fa1098c712334beb9725dda5` |
| PickCube GeoPhys worker log | `workspace/maintenance/p2_0_part_b_s2_c1_20261016/pickcube_geophys_v4/worker.log` | 2,239 | `66e6783bbae541748729acb3aee9555057509ec036fedf56ef627e80eae437df` |
| PickCube MuJoCo result JSON | `workspace/maintenance/p2_0_part_b_s2_c1_20261016/pickcube_mujoco_v4/result.json` | 24,614 | `96e85d923987ace7fe8980561b00e3df9023d3c6242d347fadacdc191aa7a6fd` |
| PickCube MuJoCo worker log | `workspace/maintenance/p2_0_part_b_s2_c1_20261016/pickcube_mujoco_v4/worker.log` | 1,547 | `a18ccfe34c3a88d5a6655dda1b2d5e085bc268c811e2d057dce30de6fe67e017` |
| NutAssembly GeoPhys result JSON | `workspace/maintenance/p2_0_part_b_s2_c2_20261016/nutassembly_geophys_final/result.json` | 15,899 | `cf97d8f3c61dce71ede1307669be2a9217fa27f9b18bb342afb74dad85b3c6f5` |
| NutAssembly GeoPhys worker log | `workspace/maintenance/p2_0_part_b_s2_c2_20261016/nutassembly_geophys_final/worker.log` | 2,115 | `0934302ca7f0b1e7d71ba82923c80dc024dac75e06d1d6a0827c9ff123e1fd7e` |
| NutAssembly MuJoCo result JSON | `workspace/maintenance/p2_0_part_b_s2_c2_20261016/nutassembly_mujoco_final/result.json` | 14,927 | `ea25746cbfc18c068cce3dc7c46246237d5570be0b6ecaf8c590be2f8e6b168c` |
| NutAssembly MuJoCo worker log | `workspace/maintenance/p2_0_part_b_s2_c2_20261016/nutassembly_mujoco_final/worker.log` | 1,422 | `deacad498bbf4ba7bab5ad00a657809018eccdfa555a3889e8ee7699d077a53e` |
| S5-C2 provider-free regression log | `workspace/maintenance/p2_0_s5_c2_20261017/provider_free_final.log` | 874 | `077f593c60258c00ffc3eb9c693b1a3c97c695d10c8d0b7acec1335bf9c0f8b2` |
| Converter and failure-gating tests | `workspace/maintenance/p2_0_s5_b_20261017/cli_and_failure_gates.log` | 98 | `fbd78fec782001f93d58ec55c49ed2f14ea9bf835f6197896c81813538559ce5` |

### Additional current batch and learning smoke files

| Evidence | Local path | Size (bytes) | SHA-256 |
| --- | --- | ---: | --- |
| Pendulum merged-scene CPU batch accepted receipt | `workspace/maintenance/p2_0_b_part_b_s4_20261016/merged_scene_pendulum_cpu_batch_smoke_final.json` | 736 | `19bc6f82e4e7adf5ea6102df8c169108d6ab37ba8fa657b93593d17f4ea7d296` |
| Pendulum SB3 one-update runner summary | `workspace/maintenance/p2_0_b_s4_5_b_20261017/pendulum_sb3_smoke/summary.json` | 742 | `3496cfc76a886dcbe5337fef27daea0d36a3d11e59f9bd4fdac9fe6481571654` |
| Pendulum SB3 example result and resource limits | `workspace/maintenance/p2_0_b_s4_5_b_20261017/pendulum_sb3_smoke/example_result.json` | 1,715 | `d016b19b7f36c8728e65edd66da52de43df4c061922580caa70e8c5756ae42fe` |
| Pendulum SB3 stdout | `workspace/maintenance/p2_0_b_s4_5_b_20261017/pendulum_sb3_smoke.stdout.log` | 2,097 | `7ec6e2fe2ec44c71c2caf58f5a7447a5a1fe57266a587736e7ecc0c6a6ed35d5` |
| Pendulum SB3 stderr warning | `workspace/maintenance/p2_0_b_s4_5_b_20261017/pendulum_sb3_smoke.stderr.log` | 480 | `f9bbbc5dba19f006d959d6140fdcc758b8a3ebc4bb8f664c0f8ce2fe55007a2c` |
| Pendulum SB3 return H5 | `workspace/maintenance/p2_0_b_s4_5_b_20261017/pendulum_sb3_smoke/return_curve.h5` | 31,312 | `e87a3100cf8b7d775932ebf14749c4f4a6e8336ee7c1db314fddfee1b45c6c96` |
| Pendulum SB3 one-update checkpoint | `workspace/maintenance/p2_0_b_s4_5_b_20261017/pendulum_sb3_smoke/pendulum_ppo_b2_cpu.zip` | 136,182 | `361069281b5ed745f89d031933e220edc3e7c52e760e36922b9f3b3b62d0e61d` |

The SB3 stderr file is retained because it records a PyTorch CUDA initialization
warning during the CPU run; the bounded run still reported one completed update.
Do not suppress this warning in later evidence summaries. The scalar and batch
rasterizer examples produced in-memory RGB frames only; no native Flora frame
artifact exists to preserve. Their bounded run scope and source identities are
recorded in L1 rather than represented as a missing raw image.

The expanded minimum L2 inventory contains **22 files totaling 24,563,669
bytes** (about **23.43 MiB**). This is a local integrity inventory, not an
independent backup or restore verification. L2 remains on the existing disk.
Preserve it in place until a separately authorized archive destination and
transfer procedure are available.

## L3 — Historical workspace

Historical qualification campaigns, previous task candidates, exploratory
experiments, and unrelated raw datasets remain in the ignored workspace. A
metadata-only, no-follow scan observed 85,467 filesystem entries. `du` reports
75,974,623,232 allocated bytes for `workspace/`; apparent-size accounting that
deduplicates hardlinks reports 75,732,668,547 bytes. These differ from a
path-by-path logical sum because 750 file-path entries are hardlinked. The
qualification subtree alone occupies 65,536,290,816 allocated bytes. The full
per-path inventory remains in ignored
`workspace/maintenance/p2_0_s5_c4_20261017/`. The S5-C5 [retention plan](../../../module/task_env/p2_0_s5_c5_l3_retirement_planning.md)
and its three exact, DRY_RUN_ONLY manifests reclassify L3 into regenerable
L3-A, superseded/review L3-B, historical raw L3-C, and unresolved L3-D. S5-C6
binds those inventories to separate approval proposals; each has an empty
execution allowlist. The proposed `L3_HISTORICAL_RAW_RETIREMENT_ALLOWED`
policy is not effective; the previous `BACKUP_NOT_VERIFIED` gate remains
active until explicit maintainer approval. The registered worktree receipts,
516 unresolved C rows, two symlinks, and external-consumer review remain
holds. Nothing was deleted or rewritten. Tracked v1.0.0 release records and
qualification decisions remain unchanged and available through immutable
`v1.0.0`.

## Validation and status

- **PASS — local metadata/hash check:** all 22 proposed L2 files exist and
  match their recorded byte size and SHA-256; the five original task/recording
  H5s also match the existing candidate/source-recovery records.
- **PASS — bounded regression receipt:** 147 tests and 6 subtests passed on
  `2fb60de`; this did not create a formal qualification decision.
- **PASS — S5-C5 L2 recheck:** all 22 paths still match the indexed size and
  SHA-256; no L2 bytes were changed.
- **NOT_RUN:** independent L2 copy or restore read.
- **NOT_RUN:** remote Git preservation of this new evidence package; no remote
  integration authorization was given in this task.
- **BLOCKED pending maintainer decision:** the new L1/L2/L3 retention proposal
  does not replace the full-workspace backup requirement until explicitly
  approved.
- **DRY_RUN_ONLY:** exact L3-A/B/C file manifests were prepared. No cleanup was
  performed. The earlier 17-file cache allowlist remains in the S5-C4 audit;
  all A/B/C groups require separate review before deletion.
