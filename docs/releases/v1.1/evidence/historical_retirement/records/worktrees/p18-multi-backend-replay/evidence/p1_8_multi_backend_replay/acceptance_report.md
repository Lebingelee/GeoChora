# P1.8 bounded replay acceptance report

**PARTIAL / ready for Human review of a localized result; not approved qualification.**

The operational status is `partial_with_localized_failure`, first boundary `sapien_native_timebase_representation`. Twelve actual GeoPhys/MuJoCo/Genesis D1/D2 cells pass both execution validity and final task success for frozen seeds 31 and 73. The four SAPIEN cells were gated off, not run, and provide no task-success evidence.

## Human authority and isolated provenance

P1.6 remains PARTIAL / NOT APPROVED, Flow remains historical negative learner evidence, D3 source-byte provenance remains incomplete. P1.7 is deferred. Human authorized this provider-centric deviation without waiving P1.6/P1.7 or closing Phase I. No Flow/D3/policy/training or P1.7/P1.8 closure work was run.

The clean attached worktree branches from exact `cda511f49eb544dabe685ec1dbcc6345884d66c8`, containing all required ancestors. public/main does not contain the baseline and remains untouched. Original P1.6 branch/HEAD, status and inventoried source bytes are retained. GeoPhys gitlink and independent checkout remain clean at `c665ce5028a12bb4d2afe49f05e015fa9b684a39`. MuJoCo is 3.8.1. SAPIEN 3.0.3 and genesis-world 1.4.3 were initially absent and installed into isolated provider_deps, not project requirements or provider source.

## Common source and identity

TaskArtifact, controllers, readiness, expert, CanonicalTrajectory and task semantics are unchanged. Their frozen source SHA set and mechanically derived semantic identities are in provenance.json and provider_spec.yaml. The shared MJCF bytes used for governed source/golden sessions are approved_shared_source.xml (SHA256 bdd119833a5ae3c8176daf1f5ef586c3601870f10f4b4b5f6d7aa730fe5f0fed). Original absolute mesh paths are retained read-only to preserve approved controller identity; relocation changes identity and is documented separately, not silently accepted as the same identity.

Genesis imports the same authored MJCF. MuJoCo's source compiler resolves authoring defaults and actuator/name facts only; MuJoCo runtime state is not a truth oracle. Private semantic bindings resolve native joints/links and EE site offset. Source-derived fixed symmetric tendon member PD/force mapping is approximate; source gain coefficients are not tuned to replay outcomes. Native gripper control force and measured opening are projected into canonical feedback. Source contact dimensions select torsional/rolling support before replay; no post-output contact tuning. Unsupported provider/routes reject without fallback; SAPIEN remains explicitly unsupported for task sessions.

## P0/P1 prerequisites

Genesis lifecycle reset/repeat/zero velocity/finite semantic state/time/sample immutability and open-close feedback checks pass. Requested joint error 0, cube position max abs 6.637928096075996e-09 m, quaternion error 0. Reset has no settle; one no-control step measures time 0.002 and step1.

The existing locked P1.3 shared microfixtures/oracle were reused unchanged (SHA256 bb0a717ff98c0f0f862c6b31a68d2de5f69e14614643dbe7f8aaa5c227f8bfda). Genesis all four replay-critical microprobes pass. SAPIEN numerical asset/frame, acceleration, tracking and contact gates pass, but public native_dt=0.0020000000949949026 fails exact authored dt=0.002 in all four probes. No tolerance widening, timestamp rounding or SAPIEN replay debugging was attempted. Native clock limitation is disclosed in raw facts. Boundary-provider camera_depth remains deferred.

## D0, golden and replay

GeoPhys source trajectories are successful: seed31 T716/holds596; seed73 T445/holds325. Every H5 load validates T+1/T and exact logical roundtrip. D0 transforms stored targets into public absolute_joint actions, using recorded state/feedback with fresh sequential ProductionCanonicalPandaController. All target mappings and hashes match exactly (716/716, 445/445), including desired/servo gripper and arm layers.

provider_spec.yaml was SHA256 locked before first D1/D2 execution. The creation-time first_replay_started=false field in lock is a historical marker; first_replay_execution.json records the later execution. Source, sample, golden, action and oracle lock verification remain exact after all runs. No trajectories/seeds/actions/tolerances/config were replaced.

D1 uses exact loaded targets without expert/controller. D2 uses exactly the frozen D0 public-action sequence with fresh production controller and current measured provider state/feedback; no expert/planner/policy. All twelve executed cells preserve immutable requests/target linkage, finite semantic canonical state and monotonic time, reach cube_lift>=0.10 m and retain final semantic success. D2 target divergence is expected and reported independently. See replay_matrix.md for every cell and pairwise diagnostic final-state differences; equality is not a gate.

## Debug history and regressions

Failed attempts remain as separate immutable directories. SAPIEN ActorBuilder public property correction: one fix. Genesis Asset/Frame: public timestep property fix, then non-collision visual geometry facts fix (two distinct evidence-backed attempts). Genesis lifecycle: free-joint semantic public index binding correction (one fix). No fix or widening for SAPIEN timebase representation. The P1.2 initial authority-file absence in isolated worktree is preserved; copied existing Human authority yielded a new passing run.

Unchanged GeoPhys/MuJoCo P1.3 full ten intersections pass; P1.2/P1.1 pass. Four P1.5 readiness/controller seed31/73 anchors pass and each canonical H5 roundtrip passes. P1.4 provider-free geometry/import and fresh control import guard pass. Negative control-capability admission rejects before native constructors; unknown dispatch has no MuJoCo fallback. Frozen lower-phase source hashes are unchanged. No GeoPhys/MuJoCo/package-source modification.

## Review boundary and residual risks

This does not claim four-provider completion, provider-wide qualification, physics/contact/controller equivalence, learned-policy transfer or Phase-I closure. Recommend splitting the next review around SAPIEN native timestep representation/admission. Genesis's bounded replay support may be reviewed independently.

- SAPIEN requires Human review of exact timebase representation boundary before lifecycle/replay admission
- Genesis fixed symmetric tendon actuator translation is an approximate source-derived mapping, not controller/contact equivalence
- Golden source retains approved absolute mesh directory; original immutable Menagerie assets must remain accessible
- Provider wheels and transitive dependencies are isolated outside project requirements; dependency packaging is not complete
- Genesis replay uses reusable replay.run callable with recorded commands; top-level worker CLI currently advertises only GeoPhys/MuJoCo
- Evidence is local ignored workspace content, not published by source git push; retain attached worktree

## Evidence references

- provenance.json
- provider_spec.yaml
- provider_spec_lock.json
- first_replay_execution.json
- golden_trajectories/seed31_ref.json
- golden_trajectories/seed73_ref.json
- d0/seed31/report.json
- d0/seed73/report.json
- prerequisites/sapien/asset_frame/attempt1/report.json
- prerequisites/genesis/asset_frame/attempt2/report.json
- prerequisites/genesis/lifecycle/attempt1/report.json
- regression/final_dispatch_admission.json
- replay_matrix.json
- replay_matrix.md
