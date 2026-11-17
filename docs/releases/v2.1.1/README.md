# GeoChora v2.1.1 release record

**Published on 2026-11-17.** [GitHub Release](https://github.com/Lebingelee/GeoChora/releases/tag/v2.1.1), annotated tag `v2.1.1`, commit `15f85f35fc5488d01540db3ff3f7215241aa8abb`. The tag freezes the accepted source; subsequent documentation commits update branch navigation without retagging the release.

G01–G07 / all twenty-two substages have bounded acceptance. The [manifest](release-manifest.json) records publication and preserves the candidate inputs, source hashes and original acceptance identities. The original nine PickCube runs retain Core `78349184d0600e2fb804e6461930c475bfcc67c1`; they were not rerun at the release commit. See the [single capability matrix](../../module/task_env/v2.1.1/capabilities/capability-matrix.json), [7b acceptance](../../module/task_env/v2.1.1/maintenance/reviews/20261117_g07b_final_acceptance.md) and [7c acceptance](../../module/task_env/v2.1.1/maintenance/reviews/20261117_g07c_attempt002_acceptance.md).

## Recovery and dependencies

- GeoPhys pin: `198d30ac64ce873a1467f55d2adfc471db18fbc5`, preserved on its origin branch `geochora/v2.1.1`. GeoPhys is private: access to the repository is required; a connector lookup failure does not establish commit absence. Upstream main integration remains a separate deferred decision.
- Menagerie pin: `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`.
- Core main/develop/v2.1.1 were synchronized to the release commit before publication; authorized documentation-only successors can advance them. The frozen source archive excludes ignored outputs and SDK installations.
- [Installation](../../module/task_env/v2.1.1/guides/installation-and-start.md), [learning guides](../../module/task_env/v2.1.1/guides/README.md), [API/migration](../../module/task_env/v2.1.1/guides/api-usage.md), [module reference](../../../task_env/doc/index.md), [current state](../../module/task_env/v2.1.1/maintenance/current-state.md).

## Scope and follow-up

The original/assembled Panda MuJoCo task intersections, Nut ordinary actions, and the specified GeoPhys Nut Scene-bound observer are accepted within their recorded scope. Old failures, process deviations, null completion fields and provider-specific exclusions remain preserved. Publication does not grant a new Qualification or third-party asset redistribution permission.

[Remaining work](remaining-work.md) separates deferred implementation, unmeasured intersections and provider issues. In particular, batch R3/models/compensation, CUDA learner integration, other LIBERO routes, Isaac6.1 full lifecycle and dynamic renderer switching remain unfinished. The MuJoCo FREE angular-armature/implicitfast moment guard remains; the GeoPhys Nut same-input 32-action comparison and short rendering lifecycle do not establish a new full Solution run or visual-geometry qualification.

The repository's legacy protected-log validator discrepancy remains disclosed; the protected log bytes were not changed. This publication-state update performs no native simulation and does not relabel historical evidence as a rerun.
