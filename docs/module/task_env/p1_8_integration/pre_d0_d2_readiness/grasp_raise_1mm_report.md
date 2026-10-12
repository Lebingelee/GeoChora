# Shared grasp target +1 mm diagnostic

## Configuration and order
Start commit 7390da0998dfe7402e8bce6d4de82ab11434fd45, codex/p1.8-integration. Diagnostic only; default production candidate remains unchanged.
Shared grasp_offset_Z 44.895 -> 45.895 mm. Absolute expected-height gate remains disabled as in the preceding ablation; actual pose stability remains unchanged. 10 N actuator cap/target, 1 N deadband, controller-only continuous 0.1 s readiness, additional 0.1 s grasp hold, 1.5 s fail-closed deadline. No force fallback, seating or forced lift. Persistent arm, planner, assets and physics unchanged. Outer/gripper equal-rate 100 Hz.
GeoPhys/TB100 was run first; only after normal closure and verify-lift PASS was MuJoCo/TB100 run with the same configuration.

## Results

| Provider | Authorization s | Opening mm | Force N | Nut lift from reset mm | Max capture translation mm | Max capture rotation rad | G0 |
|---|---:|---:|---:|---:|---:|---:|---|
| GeoPhys | 0.930 | 33.468 | 9.132 | 101.523 | 0.022 | 0.000318 | PASS |
| MuJoCo | 0.930 | 28.524 | 9.163 | 97.299 | 5.459 | 0.037839 | PASS |

Both authorization branches are controller_close_ready; verify_lift PASS, using unchanged 8 mm / 0.15 rad capture thresholds. Lift is measured from reset, not from authorization.

## Table interference and causality
Authored geometry reconstructed from recorded poses gives minimum finger/table clearance during close of +0.762 mm on GeoPhys and +1.949 mm on MuJoCo. Prior unchanged GeoPhys close had approximately -0.832 mm reconstructed clearance. MuJoCo native diagnostics show no finger/table contact samples during this close. GeoPhys lacks native pair-level contact evidence; its clearance remains authored reconstruction, not a force decomposition or proof of exact realized collision parity.
Actual stable EE Z on GeoPhys changes from 515.499 to 517.099 mm: the physical shift is about 1.600 mm even though the reference shift is 1 mm. Removing contact/loading can alter servo equilibrium, so this is not a pure 1 mm achieved-pose translation.
Force mode still enters early, at about 77.69 mm opening on GeoPhys and 78.86 mm on MuJoCo. Thus early activation alone is not sufficient to cause failure; table interference is a supported explanation for the previous closure blockage, not an isolated proof of sole causality.

## Media and scope
Both wrist MP4s stored under the evidence root: geophys/tb100/media/hand_camera.mp4 and mujoco/tb100/media/hand_camera.mp4. Manifests include SHA256, trace hash and camera parameters. Renderer-only replay of recorded provider state; no rendering-time physics rerun. No media embedded.
Only TB100 equal-rate was tested. TB500/TB50, fixed-inner/slower-outer combinations, T1, full NutAssembly and D0-D2 were not run. This is bounded G0 development evidence, not full qualification.

## Recommendation
Preserve +1 mm as a shared diagnostic candidate. Next validate identical frozen settings at 500/500 and 50/50 Hz before adopting the task profile; preserve table-clearance and auxiliary pad-penetration risks. No production migration applied.

## Evidence
workspace/qualification/phase1/p1_8_pre_d0_d2_readiness/grasp_raise_1mm/
Contains run.py, render.py, clearance.py, provenance.json, comparison.json, authored_geometry_clearance.json, provider traces/reports and media manifests.
