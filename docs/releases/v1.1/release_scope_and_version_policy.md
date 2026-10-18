# v1.1.0 Scope and Version Policy

**RELEASE_CANDIDATE — NOT_PUBLISHED**

GeoChora v1.1.0 is a Core consolidation release with documented breaking API
changes. The maintainer selected `v1.1.0` as the target version for this
release. Publication, tag creation, and protected-branch updates remain
separate authorization and ref-verification steps. This version uses an
explicit GeoChora project-specific versioning policy;
strict Semantic Versioning compliance is not claimed. A minor version
increment under this policy does not imply full backward compatibility.

The immutable `v1.0.0` release remains the scoped Phase I Core baseline. The
v1.1.0 candidate consolidates the active PickCube and NutAssembly task
authoring, retires Go2-specific and GeoChora-owned Static Template
implementations, and rebuilds current task, recording, learning, and rendering
developer workflows around the current APIs. It preserves generic Core
contracts and reports exact tested intersections rather than provider-wide
claims.

The release policy keeps these axes separate:

| Axis | Meaning in this candidate |
| --- | --- |
| Release version | `1.1.0`, selected for RC preparation only. |
| API compatibility | Breaking removals are listed with migration or immutable recovery guidance. No incompatible aliases are added. |
| Capability implementation | An API or route exists in source; this does not prove execution. |
| Functional regression | `TESTED_BOUNDED` applies only to the named source/config/provider/backend case. |
| Formal qualification | No new qualification is inferred from implementation, regression, or version change. Historical labels remain tied to their original refs and Evidence. |

This release does not declare the Phase II roadmap complete and does not imply
complete Physics Provider interoperability, complete Renderer
interoperability, P1.8 FULL qualification, D0-D2 qualification, manipulation
checkpoint qualification, or general-purpose parallel manipulation RL. See
the candidate [capability matrix](capability_matrix.md) and [known
limitations](known_limitations.md).

The previously considered `v1.0.1` and `v2.0.0` alternatives are historical
decision context only; the current target is not an open version-selection
gate. Publication, tag creation, and protected-branch updates still require
separate maintainer authorization.

## Release-evidence retention and backup status

The S5-C3/C4/C5 L1/L2/L3 reduction began as a proposal; its historical
approval boundary is retained in those dated reports. For the current v1.1.0
candidate, the maintainer subsequently selected an L2-only off-host copy capped
below 100 MB and authorized publishing the exact 22-file L2 set
(24,563,669 bytes) to the public GitHub `v1.1.0` branch, including embedded
local absolute-path strings. The remote copy was read back and verified:
22/22 file sizes and SHA-256 values match; a representative NutAssembly H5
opened and a PickCube result JSON parsed from fetched Git objects. The exact
payload commit and verification receipt are in the [backup manifest](backup_manifest.json).

This satisfies the selected L2 off-host-copy scope. The branch is in the same
public repository/account, so a separately administered backup is not
established. No full-workspace bundle, all-ref Git bundle, or independent
submodule bundle was made. The C8 maintainer accepted the specified L3
historical retirement and residual loss; hashes cannot restore those removed
raw files. The known single-disk SATA risk remains open. These limits are
disclosed in [known limitations](known_limitations.md) and [release readiness](release_readiness.md).

The earlier `BACKUP_NOT_VERIFIED` full-scope observation remains historical;
the current L2 transfer has its own verification status. No broader backup
waiver is claimed, and this copy does not authorize publication, a release tag,
or protected-branch updates.
