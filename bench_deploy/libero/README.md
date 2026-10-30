# LIBERO deployment recipe and current scope

Current planning authority: [R07 three-task scope, completion gates and Harness integration](../../docs/module/task_env/goal/Phase_II_01/09_R07_Benchmark_Deployment_and_Agent_Cost.md#r07-current-scope-20261030). Required tasks are the original bowl-to-plate, middle-drawer and plate-to-stove-front tasks. All three must be deployable through configuration on MuJoCo, GeoPhys and Isaac Sim; required Solution success is MuJoCo 3/3, GeoPhys at least 1/3 and Isaac Sim at least 1/3. Remaining Solution successes are stretch goals. These are planned gates, not current implementation claims. The current implementation below remains a single-task diagnostic. Original tasks #4/#5 are optional v2.1.0 supplements. Once #1/#2/#3 meet the current required gates, enter R00-R07 route closeout without waiting for those optional tasks; see the [closeout boundary](../../docs/module/task_env/goal/Phase_II_01/09_R07_Benchmark_Deployment_and_Agent_Cost.md#v210-r00-r07-closeout).

This is benchmark-specific deployment metadata, not a Core `TaskArtifact` or
task registration. Its modules compose the actual task, robot, controller,
planner, observation, assembly, and evaluation sections. The fixed input binds
the source manifest, BDDL and opaque selected init identity to the reviewed
source pins.

After installing and independently verifying the source bundle, compile the
recipe with:

```sh
python asset/benchmarks/libero/tools/source_bundle.py recipe \
  --manifest asset/benchmarks/libero/source_manifest.json \
  --target /local/audit/libero-pilot \
  --task-input bench_deploy/libero/task_input.json \
  --output /local/audit/libero-pilot.recipe.json
```

The CLI re-verifies the target, checks its receipt against the fixed task input,
and writes a versioned recipe with a canonical SHA-256. It records the native
MountedPanda actuator layout and 20 Hz OSC_POSE source control separately from
the Core diagnostic controller. The Core route does not claim OSC_POSE
equivalence.

## R07c D01 bounded diagnostic route

`bench_deploy/libero/selected_candidate.py::build_libero_selected_candidate`
constructs the one fixed spatial bowl-to-plate diagnostic through
`SelectedReferenceEnv.from_mixed_control_candidate()`. The route uses the
existing RuntimeSession, Controller, observation, `ContactSummaryV2`, Generic
H5 v3 Recorder and independent reader owners. It is not registered as a
`make_env()` UID and does not widen normal MuJoCo admission.

The candidate pins the LIBERO `8f1084e3132a39270c3a13ebe37270a43ece2a01`
and robosuite `fbee5844ff5632f5b5698e204ec5357ca50be0df` reset source. Its
versioned reset receipt records the tabletop sampler, per-asset placement
geometry, deterministic seed, fixture realization and subsequent complete
`.pruned_init` row restore. This is a source-derived normal reset; it does not
claim that the new deterministic fixture sample reproduces a historical
per-row fixture realization. The upstream five dummy zero-action steps belong
to policy evaluation and are not part of this deployment pilot.

The fixed controller sends seven named arm torques and two signed finger
position targets. It updates at 20 Hz, holds each torque target across 25
2 ms physics steps, and applies the source actuator ranges. The accepted
R07c native004 evidence used its frozen diagnostic `Kp=100`, `Kd=20` and a
16 mm aggregate finger target. The current R07 v2.1.0 task #1 experiment uses
source-closure-bound static gravity feed-forward with `Kp=40` and `Kd=8`
(joint2 `Kd=8`); its profile is explicitly unqualified and follows native
run009's early oscillation and joint3 limit failure. These are separate
versioned profiles, neither equivalent to upstream OSC_POSE. Bind gains and
targets to each frozen run configuration. The existing joint planner
produces the bounded targets; neither it nor the benchmark worker calls
`mj_step`.

Run the native worker only from the frozen D01 package using its bounded
launcher and shared native lock. The separate readback command accepts both
the worker result and the parent run record, and verifies the compiled MuJoCo
identity/layout, all three H5 files, and parent exit/process-group/lock-release
receipts. Provider-free S1 substitutes only MuJoCo public primitive/model/data
IO; its synthetic records are not native evidence.

D01 attempt002 has Sol acceptance `ACCEPTED_BOUNDED_R07C_D01_PILOT_S2_S3`,
limited to native004's exact single-task MuJoCo CPU source/control envelope.
It records `task_success=false` and `solution_completed=null`; it does not pass
the new Solution-success or provider-switching gates. See the
[Sol review](../../docs/maintenance/20261030_r07c_diagnostic_d01_attempt002_sol_review.md).
The existing owner-gap/checklist JSON files remain signed diagnostic records,
not authority for the revised scope or general admission.

## Task Harness integration boundary

`bench_deploy` owns benchmark recipes, reset/semantic bindings and task-owned
Solutions. The existing `task_env/script/agent/` Harness owns catalog/spec,
construction checks, feasibility/ledger, Oracle and pending Judge packaging.
It must consume the same recipe, Artifact/source/reset identities, completion
facts and Core construction route. Extend those owners for LIBERO On/region/Open;
the current synthetic `pick-lift-v0` template cannot represent these tasks.
Do not duplicate Runtime/Recorder/factory or mark real LIBERO assets synthetic.

R07c acceptance and Harness candidate acceptance are separate. Actual Harness
claims retain its four reports, at least 20 distinct solved seeds, Oracle and
pending Stage-1 package per declared task/provider intersection. A bounded R07c
success episode cannot be relabeled as that campaign. The current-scope page
also binds the inspected develop-harness snapshot and required lifecycle fixes;
no branch merge or LIBERO Harness implementation is claimed here.
