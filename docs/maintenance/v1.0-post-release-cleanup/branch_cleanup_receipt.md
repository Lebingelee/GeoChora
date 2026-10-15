# Branch cleanup receipt

## Reference baseline

The verified public repository remote is `public` (`Lebingelee/GeoChora`).
Before documentation publication, `public/main`, `public/develop`, and the
peeled `v1.0.0` tag all resolved to `42787f5e4f658a3f81fdd2140cf7544d6342c783`.
The annotated tag object was
`17c3100d4fabcb061c23569dea49973ebd177d51`.

## P1.3 redundant branch

Before removal, local and remote `codex/p1.3-4h-conformance` both pointed to
`4db06e6f740a70b51cbf2eec87771321ba02d864`. The commit was an ancestor of
public `main` and had no commits unique to it. The worktree had no tracked or
untracked changes and no active P1.3 process was found. Its ignored local
`workspace/` (191 MiB) and `temp_outputs/` (144 KiB) were left in place.

The worktree was switched to detached HEAD at the same commit. The local and
remote branch refs were then deleted. The worktree and its data were retained;
no archive copy or off-host backup is claimed.

## P1.6 branch

`codex/p1.6-closure` remains at
`761f1fde7fb0d2831ab5ee780821637c0f7e6215` locally and remotely. It is checked
out in the primary worktree, which has uncommitted P1.6 changes and untracked
files. That worktree was not changed, so the branch ref is retained pending a
safe later review.

## Release protection

The documentation commit `652899b2829eac226164d8eb5c2770b1c29c9233` was
published to `develop` by normal fast-forward. The remote readback resolved
`develop` to that commit, `main` to
`42787f5e4f658a3f81fdd2140cf7544d6342c783`, and the annotated `v1.0.0` tag to
object `17c3100d4fabcb061c23569dea49973ebd177d51` peeled to
`42787f5e4f658a3f81fdd2140cf7544d6342c783`. The P1.3 remote ref was absent
and P1.6 remained at `761f1fde7fb0d2831ab5ee780821637c0f7e6215`.

This readback and the publication disposition are recorded in
`validation_results.json`. A follow-up commit updates that validation record
on `develop`; the final remote tip is read back after that push as well. No
command in this cleanup moved `main` or the annotated v1.0.0 tag.
