# Absolute-height gate removal diagnostic

User authorized removal of the preclose absolute-Z gate for observation. Same branch, baseline d609a06, separate new Evidence. The original default still enforces its gate; explicit --skip-absolute-height-gate selects a distinct diagnostic identity. The existing candidate gained a task-local predicate seam; no arm/gripper/physics/planner configuration changed. Historical frozen source is preserved in Git and the previous prequalification lock is not updated or treated as current approval.

| Provider | Hz | stable -> close | authorization | last close force N | opening mm | controller ready / canonical grasp | verify-lift |
|---|---:|---|---|---:|---:|---|---|
| geophys | 500 | YES | FAIL at1.5s deadline | 9.006577 | 76.818977 | True / False | NOT AUTHORIZED / NOT RUN |
| geophys | 100 | YES | FAIL at1.5s deadline | 9.085724 | 76.740637 | True / False | NOT AUTHORIZED / NOT RUN |
| geophys | 50 | YES | FAIL at1.5s deadline | 9.043198 | 76.763690 | True / False | NOT AUTHORIZED / NOT RUN |
| mujoco | 100 | YES | 0.93s | 9.038163 | 28.586530 | True / True | PASS |

## Meaning

GeoPhys3/3 now reaches closing, but0/3 authorizes. Actual measured pose stability meets the original0.5s minimum and0.2s position/speed window. The frozen expected-height offset is no longer a decision input. However, GeoPhys force mode enters while the fingers are still near79–80mm combined opening; end opening remains about76mm. Force >=9N alone makes controller_close_ready true, but canonical grasped_nut remains false because opening exceeds45mm. The unchanged composite readiness therefore never completes0.1s and the unchanged1.5s deadline fails closed. No forced lift or fallback is introduced.

This supports removing the simulator-dependent absolute-height checkpoint as a necessary gate for this diagnostic. It does not establish GeoPhys10N grasp/lift competence. Force readiness is not mechanical capture proof. GeoPhys public diagnostic is body-aggregate contact only, not bilateral finger/Nut pair readback; internal/inertial actuator load vs unintended collision is unresolved. Do not infer a specific contact pair or repair the simulator from these readings. Next bounded diagnostic should compare precontact force-mode entry and actual closing motion, keeping target/cap10N and mechanical verify-lift requirements.

MuJoCo/TB100 authorizes at0.930s, verify-liftPASS; drift5.337382mm/0.037341481rad. Against the independent frozen trace all700 physical boundaries, inner targets, feedback/readiness/memory and applied physical quantities are exact. Source-based identities and one diagnostic event differ intentionally. MuJoCo500/50 were not rerun in this ablation.

## Preserved requirements

Actual pose stability; held arm target; equal-rate gripper;10N target/cap;1N deadband; controller-only composite readiness0.1s;1.5s deadline; additional force-regulated hold0.1s; original capture baseline and8mm/0.15rad bounds; no seating, fallback, q_ref reset or forced lift. Absolute height remains recorded (signed actual-vs-old-expectation), rather than removed from Evidence. Native step counts and actuator caps checked. NoT1/full/D0–D2/boundary provider run.

Run:

```sh
PYTHONPATH=.:GeoPhys/src:GeoPhys MUJOCO_GL=egl python -m task_env.diagnostics.phase1.integration.stable_grasp --provider geophys --rate 100 --skip-absolute-height-gate --output NEW_DIR
```

Raw trajectories/contact diagnostics and matrix command: height_gate_ablation/g0/ and run_matrix.py. Detailed predicate/force-mode timings and protected source checks: comparison.json. No push or main update.
