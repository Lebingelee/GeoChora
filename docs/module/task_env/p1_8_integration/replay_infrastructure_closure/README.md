# P1.8 Replay Infrastructure Closure

**Decision:** `REPLAY_INFRASTRUCTURE_GO`, scoped to versioned live recording, canonical owner/control restoration from real boundaries, reset-based canonical replay preparation, and the tested integrated G0 cases. **Formal D0/D1/D2 campaign: BLOCKED / not run.**

The detailed run artifacts are in `workspace/qualification/phase1/p1_8_replay_infrastructure_closure/` in the `codex/p1.8-integration` worktree. Core implementation source checkpoint: `cf5f941` (preceded by recorder `39479aa`, clock `d6016e1`, checkpoint validation `78eba97`).

## Verified coverage

- Live 10 N G0 recording and exact logical H5 roundtrip: GeoPhys and MuJoCo, equal-rate 500/100/50 Hz (6/6).
- Versioned integer/native clock validation: 6/6 live cells; v0 reader/writer and PickCube regression preserved.
- Canonical owner/coordinator P0–P8 restoration and bounded next-target continuation: six provider/rate cells, exact canonical outputs; 18 malformed/incompatible restore cases reject without mutation.
- Native diagnostic continuation: MuJoCo exact for nine checkpoints and 12 boundaries at three rates. GeoPhys canonical replay is exact; native contact-state continuation is not bitwise exact (maximum observed position difference about 0.239 mm) and is not qualified.
- Fresh R1 PickCube `session.step()` smoke passed for both providers. No behavior tuning or physics changes.

## Evidence reports

Detailed reports: `workspace/qualification/phase1/p1_8_replay_infrastructure_closure/{recorder_implementation_report.md,clock_contract_report.md,checkpoint_restoration_report.md,source_change_summary.md,evidence_cleanup_report.md,recovery_verification.json,next_d0_d2_handoff.md,replay_infrastructure_acceptance.json,evidence_cleanup_manifest.json}`.

Minimal retention archive: `/home/lly/Geochora_Evidence_Archive/p1_8_integration_20261012`; post-prune inventory and selected experiment restoration are linked by `minimal_reproducibility_complete.json`. This archive is local-only; off-host backup is not verified. Cleanup removed 559 files and released 32.590 GB by measured filesystem free-space delta. The archive went from 27.011 GB logical to 10.990 GB; selected evidence references total 2.630 GB and current closure evidence 4.069 GB. Cleanup intentionally discarded nonselected historical dense traces, transient contact streams, optional videos, and verified duplicate copies; frame-level/raw transient analysis for those nonselected runs is lost. Exact paths/hashes are in the cleanup manifest. No off-host backup is verified.

No T1, full NutAssembly experts, formal D0/D1/D2, or boundary-provider qualification was started. Human Review and full-task golden prerequisites remain.
