# G01/1a scope audit — attempt001

**Result:** PASS for the bounded source/caller audit and documentation handoff. **Execution status:** `REPORTED_PENDING_REVIEW`; this is not protocol approval or runtime qualification.

**Frozen input:** Core `develop@ba874c2d57dc9cd5e3cb710d87d3405808393967`; GeoPhys gitlink and checkout `67da1165149486d3ae3e779c13ce31af49e17d50`. The original planning baseline `fd03817c…` remains unchanged. Package manifest and frozen input hashes matched. The two protected untracked Core files retained their original hashes.

## Findings for review

| Topic | Source-backed result | Follow-up owner |
| --- | --- | --- |
| Physics shortlist | MuJoCo CPU, GeoPhys CPU, Isaac Sim 6.2.0.0 with PhysX/CUDA `cuda:0`. Historical F06 matrix evidence is bounded, runtime-only, and reports `task_success=false`; no route was rerun. | 1c, 3a–3c |
| PickCube render | Selected P1.6 still admits `renderer=none`. The current dynamic cross-camera path is GeoPhys CPU → MuJoCo native OpenGL and supports typed scalar-joint state; its source projection rejects free joints. PickCube declares a floating/free cube joint, so this candidate does not cover PickCube. | 1d, 5a–5c; asset mapping in 3b |
| Other observation camera | `PositionCandidateEnv` has an opt-in camera consumer that binds RGB, optical-Z depth, and Entity masks to the exact `CanonicalStateViewV1` boundary and clock. It is a separate GeoPhys CPU candidate, not PickCube evidence. | 1d, 5b–5c |
| Batch | `SceneBatchRuntime` is one GeoPhys merged rigid solver. `make_parallel_env` registers Pendulum and TwoWheelBalance only. CPU/CUDA are device backends of one provider; no MuJoCo or Isaac TaskEnv batch adapter was found. | 6a–6c |
| Dependency | Core declares `mujoco>=3.8.1,<3.9.0`; GeoPhys at the current gitlink declares `mujoco>=3.15.0`. These ranges conflict in one Python environment. Historical D05b evidence used an older GeoPhys pin and does not resolve current-pin reproducibility. | 3a; package/environment owner before native cross-render work |
| Asset oracle | Cube source declares 0.05 m side, 0.08 kg, diagonal inertia `(3.5e-5, 3.5e-5, 3.5e-5) kg·m²`, 1 mm contact margin, damping 0.8, armature 0.01. The stated inertia is about 5% above a homogeneous solid-cube calculation; retain the declared value pending asset-owner confirmation. Panda source is Menagerie gitlink `b846dd12…`; seven arm joints, two finger joints, seven arm actuators, and a tendon gripper actuator. | 1c, 3b–3c, 4a–4c |

The recommended second physical batch candidate is Isaac Sim/PhysX CUDA, with a new adapter required. Do not count GeoPhys CPU and CUDA as two physical providers. `RemoteBatchVecEnv` uses same-step autoreset and returns `terminal_observation` plus `reset_info`; batch rendering is not connected to the merged-scene runtime and remote `get_images()` repeats one worker frame across slots.

## Gate summary

| Gate | Result | Evidence |
| --- | --- | --- |
| G0 input and boundary | PASS | Frozen package hashes, `input_snapshot.json`, protected input recheck |
| G1 owner and caller | PASS | Current source/caller audit; raw excerpts in `current_core_lifecycle.txt`, `camera_sources.txt`, and `task_asset_sources.txt` |
| G2 route candidates | PASS | Exact candidates and unsupported/currently unconnected routes recorded in the matrix; no capability promoted to tested |
| G3 asset admission | PASS | Source values and per-route checks recorded; unmeasured tolerances remain null |
| G4 docs and protection | PASS | Documentation validator, JSON/DAG checks, diff checks, and protected hash checks recorded in the ignored report directory |
| G5 handoff | PASS | Report and command/findings manifests written; one local docs-only commit; no worker or native window remains |

## Scope and next action

No implementation, test, dependency, submodule, runtime, renderer, solver, physics, or GPU changes were made. No native route or implementation test was run. All v2.1.1 implementation targets remain `NOT_STARTED`; all validation targets and all nine final PickCube seed cells remain `NOT_RUN`.

Read the [full attempt report](../../../../../../workspace/maintenance/v211_g01_1a_attempt001/report.md) and its `findings.json`, `commands.json`, and `output_manifest.json` before review. After review, the next candidate is 1b; a separate complete package is required to begin it.
