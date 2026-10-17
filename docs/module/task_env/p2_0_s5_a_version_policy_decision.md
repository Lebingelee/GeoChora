# P2.0-B S5-A — v1.1.0 Version Policy

Status: **TARGET APPROVED FOR RELEASE-CANDIDATE PREPARATION ONLY**. This does
not authorize a release tag, publication, or modification of `main`.

The selected target is **GeoChora v1.1.0**. This decision supersedes the
previously considered `v1.0.1` project-policy exception and strict-SemVer
`v2.0.0` alternatives for this release cycle. The earlier alternatives remain
recorded in the initial [S5-A preflight snapshot](p2_0_s5_a_release_preflight.md)
and the [historical v1.0.1 candidate matrix](archive/capability_matrix_v1_0_1_candidate_historical.json).

> **GeoChora v1.1.0 is a Core consolidation release with documented breaking
> API changes.**

GeoChora uses a project-specific versioning policy for this release. The
`v1.1.0` minor increment is **not claimed to comply with strict Semantic
Versioning**, and it does not promise full backward compatibility. The release
must publish an explicit migration inventory for every incompatible task UID,
Python import, runtime/configuration option, CLI route, authoring surface, and
changed default. Incompatible identities will not be restored as aliases when
they imply different behavior. Historical users must use the exact immutable
recovery refs in the source manifests.

The policy distinguishes five separate decisions and evidence axes:

| Axis | v1.1.0 treatment |
| --- | --- |
| Release version | `1.1.0`, selected for candidate preparation only. |
| Public API compatibility | Breaking removals and changed contracts are disclosed with migration or recovery guidance; a minor increment does not imply compatibility. |
| Capability implementation | Recorded per current route and API; implementation alone does not establish execution. |
| Functional regression | Bounded results are limited to the exact task/provider/backend/configuration/source intersection in the candidate matrix. |
| Formal qualification | No new qualification is inferred from the release version, implementation, or bounded regression. Historical labels remain tied to their original source and Evidence. |

This is a Core consolidation release. It is not a declaration that the Phase II
roadmap is complete and does not imply complete Physics Provider
interoperability, complete Renderer interoperability, P1.8 FULL qualification,
D0-D2 qualification, manipulation checkpoint qualification, or general-purpose
parallel manipulation RL.

The immutable [v1.0.0 release package](../../releases/v1.0/README.md) remains
the Phase I Core baseline and is not modified by this proposal. The complete
current compatibility list is in
[`p2_0_s5_a_compatibility_inventory.json`](p2_0_s5_a_compatibility_inventory.json).
The sole current candidate capability matrix is
[`capability_matrix_v1_1_0_candidate.json`](capability_matrix_v1_1_0_candidate.json).

Release publication, tag creation, protected-branch changes, and final release
authorization remain separate maintainer decisions.
