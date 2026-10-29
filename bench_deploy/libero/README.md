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
the state-only Core candidate. Core admission remains false: mixed torque and
finger-position control, typed reset realization, public free-body/contact
state, and a validated task planner are unresolved. `owner_gap_matrix.json`
and `r07c_minimal_patch_checklist.json` name those gates and the minimum next
checks. No native environment, reset, step, or H5 recording is run here.
