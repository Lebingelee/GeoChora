# GeoChora v1.0 Phase I handoff

## Release decision

The maintainer scope decision accepts GeoChora v1.0 as a Phase I Core baseline. It does not assert completion of the original Phase I blueprint or add a Human Judge signature. P1.0–P1.6 decisions remain historical APPROVED_BOUNDED outcomes. P1.7 and the remaining formal P1.8 routes continue as follow-up tracks.

## Source and validation

The release source was prepared from public main at 9988cf700ac1b5f7ae9ba0a284deda4fa2141917 and the P1.8 integration line at 285aa0acc77b87f4d7d6819182315957b21a7213. The latter contained 19 commits ahead of main and no main-only commits. GeoPhys and MuJoCo Menagerie gitlinks match the starting main pins.

Current candidate verification includes 66 focused P1.8 tests and a real GeoPhys Taichi CPU PickCube expert smoke. Exact commands and limits are in validation_report.md. The source commit deliberately contains no self-referential final SHA; the local/off-repository publication receipt records remote readback after publication.

## Evidence recovery

- P1.6 recovery archive ID: phase1_mainline_p16_recovery_20261013. Its 205,486,080-byte tar matched the recorded SHA-256 and all 441 file entries matched size and SHA-256. The frozen V2a checkpoint, selected dataset manifest, and resolved config matched their local resolver hashes. This archive is local-only; off-host backup is not verified.
- P1.8 archive ID: p1_8_integration_20261012. The extracted local archive occupies 10,989,629,850 bytes. The historical file-manifest hash matched; representative H5 restoration and hashes were checked. GeoPhys bundle extraction through its Git history fails because a historical parent object is missing; the archive retains exact source-tree snapshots. No old worktree or evidence data was removed.
- Nine existing annotated archive/p1.8 tags were read back from the public remote and remain unchanged.
- Seven historical Human decision copies match the indexed SHA-256 values.

Private absolute recovery paths are held only in the local evidence resolver and are not published in this package.

## Next work

Start with [Phase I follow-ups](../../roadmap/phase1_followups.md). P1.7 and formal P1.8 work can continue alongside Phase II. The open limitations and each replay mode's status are stated in [known limitations](known_limitations.md) and the [capability matrix](capability_matrix.json).
