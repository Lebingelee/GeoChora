# P1.8 Source Consolidation

The surviving line `codex/p1.8-frequency-robust-grasp` was published at diagnostic commit `4c91720ffe35e11210199295fdf98325eb079d9e` and remains based on current `main` `9988cf700ac1b5f7ae9ba0a284deda4fa2141917`. The redundant `codex/p1.8-integration` ref pointed to main and contributed no unique commit, so it was deleted locally and remotely without cherry-picking or rewriting history.

Nine existing annotated `archive/p1.8/*` tags were checked locally and on `public`; names, tag-object IDs and peeled commit IDs match. No tags were removed. The old integration worktree remains on disk, detached at main; its untracked log remains in place and a SHA-matched copy is preserved in ignored local Evidence. The surviving worktree's untracked log was preserved the same way. Unrelated dirty worktrees were not modified.
