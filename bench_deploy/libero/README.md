# LIBERO pilot deployment recipe

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
`SelectedReferenceEnv.from_libero_diagnostic_candidate()`. The route uses the
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
2 ms physics steps, and applies the source actuator ranges. Its explicit
`Kp=20 Nm/rad`, `Kd=4 Nm·s/rad` values are unqualified diagnostic gains, not
upstream OSC_POSE gains. Their bounded engineering rationale and limits are
part of the controller identity and run plan. The existing joint planner
produces the bounded targets; neither it nor the benchmark worker calls
`mj_step`.

Run the native worker only from the frozen D01 package using its bounded
launcher and shared native lock. The separate readback command accepts both
the worker result and the parent run record, and verifies the compiled MuJoCo
identity/layout, all three H5 files, and parent exit/process-group/lock-release
receipts. Provider-free S1 substitutes only MuJoCo public primitive/model/data
IO; its synthetic records are not native evidence.

Current D01 evidence and the exact gates still pending Sol review are recorded
in the Phase II execution/acceptance and R07 pages. Even a bounded D01 pass is
limited to this single source/task, MuJoCo 3.8.1 CPU, state-only route, seed,
reset algorithm and controller; it does not complete the five-task R07 goal,
18/22 slice count, P99, Human Judge or Qualification. The current
`owner_gap_matrix.json` and `r07c_minimal_patch_checklist.json` summarize this
bounded status rather than authorize broader admission.
