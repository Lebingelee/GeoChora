# PickCube Isaac twenty-seed and Oracle validation

Date: 2026-11-04 (Asia/Taipei). Status: TESTED_BOUNDED; Human decision pending.

## Result

The repaired Harness candidate route solved seeds 0 through 19: **20 solved,
0 invalid, 0 expert_failed, 0 unknown**. Representative seed 2 and seed 0
Oracles both passed the existing task/Expert completion and recording gates.
All twenty native workers and both Oracle workers closed their Apps and retired
their process groups. This does not grant Qualification or cross-provider
trajectory equivalence.

| Oracle | Task lift above declared rest | Transitions / observations | Result |
| --- | --- | --- | --- |
| seed 2 | 105.816 mm | 379 / 380 | PASS |
| seed 0 | 106.943 mm | 387 / 388 | PASS |

## Exact intersection and unchanged inputs

- Execution source: `30cf89e67cea2c7193e4d5c6a7356791508118e4`, clean branch `v2.1.0-harness-linux`.
- Owner repair commits: `2eaf29060d45f3afa3d720d0dcb794692d97b29d` and `30cf89e67cea2c7193e4d5c6a7356791508118e4`.
- Provider: Isaac Sim 6.2 / CUDA PhysX / `cuda:0`, pinned F06 USD delivery.
- Control: existing R3 continuous arm law and Position gripper; task-owned high-clearance wrist pitch and fresh-public-state-bound stable pad geometry for lift-attempt authorization.
- Canonical spec SHA-256: `b4cf0013446b70f46698b2944fb61d670109f923934e833dfcd5c3fd016e72e0`.
- Original spec bytes SHA-256: `1dc528e76764f681b134d27a7cba67188c14979ccc2f8c704c00314eabb02c2f`.
- Artifact: `3b93c0631b678fceedd190fbc4f9cd39087dfaf7efa100d05059091a4ad915b1`.
- USD delivery manifest: `6cb07d216689d1e0b6f31ef127d9a511906be90c2acbecb9a30667cdebf113e2`.

The spec is byte-identical to the successful historical MuJoCo input. The reset
half extent remains 25 mm, horizon 1000, task lift threshold 100 mm and Expert
collection endpoint 105 mm. The original 10 mm horizontal / 215 mm measured
clearance gates, close-ready contract, action budgets and resource/time limits
remain unchanged. No source, dependency, or environment rollback was used.

The task lift is relative to the declared 487 mm rest height. Reset placement
has 1 mm headroom; displacement from the first observed pose is consequently
1 mm lower than the task's lift metric. Both raw endpoints satisfy the original
Expert threshold using the declared task reference.

## Execution and independent readback

The maintainer explicitly accepted the NVIDIA EULA before native execution.
The existing project environment exports its acceptance; no dependency was
reinstalled. Representative Oracles passed before the twenty-seed campaign.

The first campaign connection ended after six completed seeds. The original
incomplete report remains unchanged. Seeds 6–19 then ran under `nohup` using
the same clean source, catalog, spec and native lock. An explicitly derived
report retains both report paths/hashes and combines their disjoint raw rows;
it does not label the interrupted invocation as a completed run.

The independent audit recomputed all twenty classifications, exact seed order,
totals, original row equality, source hashes, probe mode/provider/horizon/run
paths, worker/App-close and process-group-retirement receipts. Each seed
completed in 375–389 control transitions. Summed native launch wall time was
4386.60 seconds; this is not a real-time performance claim.

Each Oracle passes 22 production storage/identity checks. Independent H5
readback additionally checks final physical lift/success, finite numeric data,
T/T+1, actual file hashes, decoded structured controls and profile identities
against spec and worker expectations. Seven synthetic in-memory negative
controls reject failed App close, worker exit/error, Oracle errors, removed
storage checks and corrupted spec/controller identities. Raw evidence bytes
are not modified by these tests.

The core offline repair suite previously passed 59 checks with one native test
deselected. The existing documentation validator still reports the same two
missing protected local inputs; they are not repaired by this task.

## Evidence locations and retained limitations

All raw data remains ignored under `workspace/harness/isaac-core-repair-20261104-002/`:

- `verification.json`: independent twenty-seed/Oracle/source/cleanup audit.
- `check20/`: passing assets, compile and synthetic semantic checks; original six-row interrupted probe and its native evidence.
- `probe-remaining-6-19.json` and `.native/`: fourteen completed native rows and receipts.
- `feasibility-20-derived.json`: explicitly derived full twenty-seed report.
- `oracle-seed2/`, `oracle-seed0/`: successful H5, inspectors, checks, source snapshots and native receipts.
- `audit-negative-controls.json`: synthetic audit-negative-control receipt.

The earlier 0/20 Isaac report remains byte-identical with SHA-256
`b6c8f0b02e823a11b396221a237b3ad73d3db0829c93753d125198f76ca4da0f`.
Its failure evidence and original source identities are retained.

The task loop completes without termination or truncation. Separately, the
existing v3 Position recorder stops as `external_stop`, `truncated=true`,
`solution_completed=null`, `task_success=true`. It is a valid recorded
successful physical episode with separately proven Expert completion, not a
recorded `solution_completed` outcome. Canonical-v0 exact logical equality and
D0/D1/D2 replay are not claimed.

`grasped_cube` remains false because its 45 mm diagnostic threshold differs
from the approximately 50 mm opening around the lifted 50 mm cube; lift is
the unchanged task-success oracle. Geometric lift authorization is not a
contact-force measurement.

Logs retain protobuf duplicate-registration diagnostics in all twenty probe
workers and both Oracles. Probe seeds 6/10/16/18 retain respectively 2/2/1/1
menu-callback shutdown tracebacks; Oracle seed 2 retains two. Structured
worker errors are empty and App/group closure succeeded; natural Kit shutdown
is not claimed completely repaired. Video/render support, other tasks,
broader reset ranges, formal Stage-1 packaging, Human approval and Qualification
remain unassessed. Historical F06 3×3 runtime evidence is unchanged.
