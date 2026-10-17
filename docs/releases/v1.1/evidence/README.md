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

## L1 — Release acceptance metadata

The files in this directory are small release metadata intended to be retained
in Git:

- [Four manipulation/provider acceptance summaries](manipulation_acceptance.md)
- [Recording, regression, learning, and rendering smokes](system_smoke_acceptance.md)
- Candidate API, task identities, and status definitions in the [capability matrix](../../../module/task_env/capability_matrix_v1_1_0_candidate.json)
- Implementation and recovery identities in the [source/recovery manifest](../source_recovery_manifest.json)

The summaries preserve bounded results and raw-evidence hashes. Hash metadata
can identify a missing file but cannot restore its contents.

## L2 — Selected raw evidence inventory

All paths below are existing ignored workspace files. Their sizes and hashes
were read from the current local disk on 2026-10-17 and checked against the
candidate matrix or the source/recovery manifest where those records enumerate
them. No files were copied, moved, or modified. The five H5 files total
**24,301,972 bytes** (about **23.17 MiB**).

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

The listed L2 inventory totals **24,390,405 bytes** (about **23.26 MiB**). This is a local
integrity inventory, not an independent backup or restore verification. L2
remains on the existing disk. Preserve it in place until a separately
authorized archive destination and transfer procedure are available.

## L3 — Historical workspace

Historical qualification campaigns, previous task candidates, exploratory
experiments, and unrelated raw datasets remain in the ignored workspace. The
previous workspace estimate was about 71 GB. Under the proposed reduced policy,
L3 is outside the mandatory v1.1.0 off-host preservation set, but that scope
change still requires explicit maintainer approval. Nothing in L3 was deleted
or rewritten. Tracked v1.0.0 release records and qualification decisions remain
unchanged and available through the immutable `v1.0.0` release.

## Validation and status

- **PASS — local metadata/hash check:** the five H5 SHA-256 values match the
  existing candidate/source-recovery records; all listed L2 files exist and
  match their recorded byte size and SHA-256.
- **PASS — bounded regression receipt:** 147 tests and 6 subtests passed on
  `2fb60de`; this did not create a formal qualification decision.
- **NOT_RUN:** independent L2 copy or restore read.
- **NOT_RUN:** remote Git preservation of this new evidence package; no remote
  integration authorization was given in this task.
- **BLOCKED pending maintainer decision:** adoption of scoped preservation in
  place of the previously recorded full-workspace backup requirement.
