# P1.8 branch cleanup

Status: completed. No forced deletion or forced push.

Integration published checkpoint: `f019699c224c51845e7cc00a3cbbbe46306eb034`; remote HEAD readback exact before cleanup. Final reporting commit is pushed separately after this report.
Public/main unchanged: `f977528b9b9866c50afcf8ea9b5f5deadce60892`.

9 old local P1.8 development branches deleted; 5 existing public remote P1.8 branches deleted. Nine distinct annotated archive tags remain remotely verified against original peeled HEADs. All old commits are integration ancestors after the audited R1 merge.

| Old branch | Original HEAD | Archive tag | Local deletion | Remote deletion |
|---|---|---|---|---|
| codex/p1.8-4h-multi-backend-replay | 5e7012c70a83f26d1f6a0e51b3160efc00006c35 | archive/p1.8/p1.8-4h-multi-backend-replay-5e7012c70a83 | yes | yes |
| codex/p1.8-d-multirate-timebase | 60b51e38ff3460da62296f73bbb93138f9d41b7f | archive/p1.8/p1.8-d-multirate-timebase-60b51e38ff34 | yes | yes |
| codex/p1.8-e-nutassembly-multirate | 9331d1ec0d5aeafa067ea354f5d9525acf40e2ba | archive/p1.8/p1.8-e-nutassembly-multirate-9331d1ec0d5a | yes | yes |
| codex/p1.8-e-r1-grasp-diagnosis | dde727ff0cbeaf7fbe9f07e53ec97346538191ce | archive/p1.8/p1.8-e-r1-grasp-diagnosis-dde727ff0cbe | yes | not present originally |
| codex/p1.8-e-r2-nutassembly-solution | c36e759e8b3cef16147664a107422aa4650f159b | archive/p1.8/p1.8-e-r2-nutassembly-solution-c36e759e8b3c | yes | yes |
| codex/p1.8-e-r2-rate-controls | c36e759e8b3cef16147664a107422aa4650f159b | archive/p1.8/p1.8-e-r2-rate-controls-c36e759e8b3c | yes | not present originally |
| codex/p1.8-e-r3-nutassembly-nominal | 6160ba0a8b494f0cc3989d464b5ef61d83219b10 | archive/p1.8/p1.8-e-r3-nutassembly-nominal-6160ba0a8b49 | yes | yes |
| codex/p1.8-e-r4-dynamic-retuning | 0f2290c9b25e590da04be82a74b0aea8b005735a | archive/p1.8/p1.8-e-r4-dynamic-retuning-0f2290c9b25e | yes | not present originally |
| codex/p1.8-e-r5-controller-architecture | 8e914da87e1c1afb989b86d5e2807cfecc6d6616 | archive/p1.8/p1.8-e-r5-controller-architecture-8e914da87e1c | yes | not present originally |

Independent ignored Evidence: 3576 historical files / 21,798,465,898 bytes, plus 30 integration regression files, source bundles and exact pinned submodule snapshots. Hash verification completed before cleanup; historical payloads are read-only. GeoPhys all-ref bundle has a pre-existing missing-parent restore defect; exact source-tree snapshots provide tested recovery. The defective bundle is retained as provenance, not relied on.

Old R4/R3/R2 worktrees are retained detached at their original HEADs. R2 dirty diagnostics remain unchanged on disk; tracked.diff/untracked archived independently. Current integration continues in the former R5 directory. No worktree removal, no uncommitted-file cleanup, and no modification of unrelated P1.6/detached worktrees.

Canonical main, P1.0–P1.7/P1.6 closure, unrelated branches and archive tags retained. No associated P1.8 PRs were found by public GitHub API inspection. Local durable Evidence is not an off-host backup.

Raw 225MB reporting draft was saved to an independent local bundle/ref before compacting the unpublished integration report commit. No published history or old branch history was rewritten.
