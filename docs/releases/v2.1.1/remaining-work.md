# v2.1.1 remaining work after publication

Reviewed 2026-11-17 against the seven Goals, orchestration, capability matrix and final acceptance. All twenty-two substages have bounded acceptance; this list is input for a later scope decision, not an authorized v2.1.2 execution package.

| Item | Delivered boundary | Remaining work |
| --- | --- | --- |
| CUDA R3 / model / body compensation | Three providers × Pendulum/PickCube canonical batch accepted | Separate batched R3/model/compensation package; provider list not yet selected |
| General assembly compensation | Specified original/assembled Panda own-model MuJoCo CPU/in-process case accepted | Arbitrary connected subtree, fixed accessories and other provider support not delivered |
| LIBERO | task1 default seven-axis effort and selected pose tracking, reset/record/close accepted | task2/3, GeoPhys replay, V8 Solution execution and independent gripper writer remain unmigrated; 64-step representative run was not task success |
| CUDA learners | Existing SB3/RSL contracts and explicit rejection boundaries retained | Coordinated same-step device Env training integration; avoid double autoreset and old step_device contract |
| Isaac6.1 | Shared adapter/offline version checks and actual App startup/version | close timeout; complete Env lifecycle not passed. Isaac5.1 remains separately deferred |
| Dynamic renderer selection | Renderer fixed at Env construction; compatible reset rebuilding accepted | Same-Env renderer A→B→A explicitly deferred |
| Scalar receipt migration / AOT | Static provenance caching and device semantics retained | Scalar dynamic receipt hash migration remains separate; AOT/package admission has no accepted pass |

## Provider topics and unmeasured intersections

MuJoCo FREE angular-armature/implicitfast moments retain pre-write rejection (`G07B-MJC-FREE-ARMATURE`). GeoPhys continuous mesh/constraints and old default-budget penetration remain unresolved; tested PickCube CUDA uses explicit discrete/contact32/coupled32. These are provider topics, not a requirement to repair simulator internals in Core.

New Scene-bound GeoPhys Nut has the accepted 32-action old/new comparison and observer reset/step/reset/close, without a new full Solution run. Scalar named multicamera, MuJoCo/GeoPhys mounted task cameras, arbitrary BodyWrench body/frame/batch combinations, GeoPhys cross-provider switching, cross-row visual isolation, Nut batch and unmeasured large scales remain outside the accepted evidence. Fresh installation and every tutorial command have not been exhaustively exercised.

GeoPhys `198d30ac` has now been pushed and verified on private origin `geochora/v2.1.1`; version-branch preservation is complete. Merging it upstream main is a distinct deferred decision and is not a prerequisite imposed here.

## Completed items and historical records

Do not reopen the PickCube nine-cell success matrix, four MuJoCo original/assembled Panda task cases, Nut ordinary actions, marker, specified rendering, G05 E00–E16/C1–C5 optimization or 34 current module tutorials from old NOT_RUN/PARTIAL text. Their acceptance and exact inputs remain in the [current state](../../module/task_env/v2.1.1/maintenance/current-state.md). Historical failed tests against retired injection points do not require restoring retired factories.

Flora/new providers, full F07/asset-harness automation, non-rigid examples, RL/IL demos, agent_factory/R07 expansion, strict F05/DG03 equivalence and formal Qualification remain longer-term candidates. Asset Skills integration does not establish those products. No item here automatically expands the next release scope.
