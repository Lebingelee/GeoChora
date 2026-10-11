# P1.8 engineering integration

## Branch authority

Review/development branch codex/p1.8-integration. Canonical public/main is unchanged at f977528b9b9866c50afcf8ea9b5f5deadce60892. origin is a different repository; all publishing/archive cleanup uses public (Lebingelee/GeoChora).

Start R5 HEAD e8ee54fa16e6537a39b61038d892f2646c0e1ac7, dirty candidate source/profile/README checkpointed as 8e914da. Integration created from that checkpoint. Audited unique R1 diagnostic file cherry-picked as 6dc4074, followed by an explicit ancestry merge after identical-file proof. No old controller overrides the current arm. R2→R3→R4→R5 linear lineage retained; unique R1 diagnostic source retained. Old R2 worktree also has dirty diagnostic worker/source, separately archived as patch/untracked source, not silently merged into production.

## Module disposition

| Module | Disposition |
|---|---|
| canonical contracts/runtime providers/replay | keep cohesive, all four implementations preserved |
| R1/PickCube production | byte-preserved, no migration |
| R2/C11 | historical dependency/source identity preserved; not promoted as accepted production |
| persistent R3 arm | byte-preserved supported development candidate |
| actual pose stability + arm target hold | extracted canonical execution owner |
| equal-rate gripper cadence | extracted canonical gripper execution owner; unchanged law |
| Planner move/hold | additive vocabulary over existing plan_to_pose/hold_pose |
| NutAssembly offset/height compensation/authorization/capture | task-local candidate policy |
| experiments | 10 selected catalog entries; independent source/overlay reconstruction |
| other experiments/videos/traces | immutable independent Evidence archive; no result rewriting |

TaskArtifact, ResetSample, CanonicalStateView, CanonicalTrajectory, RequestedAction, CanonicalControlTarget, AppliedCanonicalControl, ControlFeedback, Readiness and ProviderCapabilityManifest contracts preserved. No new production controller family per experiment. No simulator source change, asset/physics/friction/gain tuning or threshold relaxation.

## Verified and deferred

Three MuJoCo equal-rate 10N G0 runs physically exact vs original candidate, provider-free contracts PASS, PickCube/R1 MuJoCo smoke PASS. 1.5s fail-closed deadline now enforced in task-local coordinator and negatively tested. Source identities intentionally change; metadata equality is not conflated with physical equality.

Full NutAssembly/GeoPhys10N/T1/D0–D2/boundary-provider qualification remains unexecuted. Auxiliary-pad penetration remains a residual risk. Replay interval/snapshot serialization requires next-stage implementation and Human Review. Phase decisions are untouched.

## History and cleanup

Read branch_inventory.json, archive_manifest.json and branch_cleanup_report.md for original SHAs, independent persistence, remote annotated archive verification and cleanup disposition. Independent archive includes ignored Evidence and dirty source patches; a Git tag alone is insufficient. Historical worktrees can remain as detached local evidence views; unrelated worktrees remain untouched. This round does not delete any unique unarchived content.
