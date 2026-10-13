# Frequency-causality development diagnostics

This package is task-local, opt-in evidence infrastructure. It changes no canonical controller, asset, provider, task threshold or qualification default. Formal D0/D1/D2 and production promotion are outside this package's scope.

The frozen reference retains R3, 10N target/cap and45.895mm grasp offset. The isolated `arm_ramp_native_grip` candidate combines a versioned MuJoCo NoSlip2 option, a public-acknowledgement-owned native arm-target ramp after lift release, and the existing physical-time gripper feedback law at native500Hz. It is not the frozen recipe. NoSlip changes contact-solve semantics and requires Human Review before any default promotion.

Example, from repository root with the validated GeoChora Python environment:

```sh
python -m task_env.diagnostics.phase1.frequency_grasp.run \
  --rate 20 --mode T1 --case arm_ramp_native_grip --sample nominal \
  --causal-gate /absolute/path/to/causal_gate.json \
  --output /absolute/path/to/new/additive/run_directory
python -m task_env.diagnostics.phase1.frequency_grasp.offline_windows \
  /absolute/path/to/completed/run_directory
python -m pytest task_env/diagnostics/phase1/frequency_grasp/test_native_math.py \
  task_env/diagnostics/phase1/frequency_grasp/test_offline_windows.py
python -m task_env.diagnostics.phase1.frequency_grasp.registry \
  /absolute/path/to/evidence_root
python -m task_env.diagnostics.phase1.frequency_grasp.finalize_report \
  /absolute/path/to/evidence_root
```

20Hz uses a separate diagnostic Timebase admission with25 native2ms steps; formal profile registry/defaults remain unchanged. Per-run source snapshots, provenance, physical-state native traces, controller/public-ACK history and strict T/T+1 H5 recording are retained. Named interventions must pass cadence admission and preserve matched prefixes before being called controlled counterfactuals. `protocol_exclusion.json` preserves invalid intervention pilots rather than hiding them.

Native contact forces are SI forces actually used by mj_step, expressed in explicitly labeled contact/world frames. Nut body-origin and COM torque use different lever arms. Actuator force is not bilateral Nut clamping force. The relative-pose metric is `inverse(T_W_EE) @ T_W_Nut`; offline windows use measured500Hz states with no interpolation. W0/W4 event instrumentation limitations are explicitly reported.

Current evidence lives under the ignored local directory `workspace/qualification/phase1/p1_8_frequency_robust_grasp_20261013/`. The comprehensive report, final candidate matrix, run SHA256 inventory, exclusions and four-hour resource boundary are retained there. Large H5, raw native traces and videos are not public Git artifacts. The baseline historical factorial and current development runs are distinguished in all reports.

The main mechanism is mixed: RoboSuite's per-call gripper target evolution changes acquisition; GeoChora's original loaded drift responds strongly to contact-solve realization, with arm scheduling and force-feedback cadence contributing after that intervention. Overall attribution and engineering robustness remain PARTIAL until residual loaded transport and predefined held-out frequency coverage are resolved.
