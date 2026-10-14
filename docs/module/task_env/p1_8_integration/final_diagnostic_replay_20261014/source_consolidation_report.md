# P1.8 Source Consolidation

The active line is `codex/p1.8-frequency-robust-grasp` at `bc34b0e58b12d63ae808273e28c79b79f2272ad6`. It descends from current `main` `9988cf700ac1b5f7ae9ba0a284deda4fa2141917` and contains 17 development commits after it. The other P1.8 branch, `codex/p1.8-integration`, points to the exact `main` commit and contributes no unique commit. Thus consolidation requires publishing the active line and retiring only the redundant ref; it does not require cherry-picking, merging or rewriting history.

Nine existing `archive/p1.8/*` tags were checked locally and on `public`; names, annotated tag object IDs and peeled commit IDs match. No tags will be removed. The old integration worktree is retained, its untracked `MUJOCO_LOG.TXT` remains in place, and an independently hashed copy is preserved in local Evidence. Unrelated dirty worktrees were left untouched.
