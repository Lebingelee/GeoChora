# v1.1.0 Scope and Version Policy

**RELEASE_CANDIDATE — NOT_PUBLISHED**

GeoChora v1.1.0 is a Core consolidation release with documented breaking API
changes. The maintainer selected `v1.1.0` for release-candidate preparation.
This version uses an explicit GeoChora project-specific versioning policy;
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

## Proposed release-evidence preservation policy

S5-C3 proposes preserving a small L1 acceptance package in Git, inventorying
the selected L2 H5/log files by local size and SHA-256, and treating the
historical L3 workspace as outside the mandatory v1.1.0 off-host preservation
set. This is a governance proposal, not an approved replacement for the
previous full-workspace backup gate. Until the maintainer explicitly approves
the reduced scope and accepts the remaining raw-data risks, the current backup
gate remains **BLOCKED**. Hash metadata identifies expected bytes but cannot
restore a missing H5 or other raw artifact. See the [evidence index](evidence/README.md),
[backup manifest](backup_manifest.json), and [release readiness](release_readiness.md).
