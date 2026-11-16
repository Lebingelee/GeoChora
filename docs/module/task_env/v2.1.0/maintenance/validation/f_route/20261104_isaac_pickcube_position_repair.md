# PickCube Isaac Position Repair Attempt 2

Date: 2026-11-04 (Asia/Taipei)

## Scope and input

- Repository: `/home/lly/projects/geochora-harness-20261103/GeoChora`
- Branch: `v2.1.0-harness-linux`
- Input HEAD: `2eaf29060d45f3afa3d720d0dcb794692d97b29d`
- Provider route: PickCube / Isaac Sim 6.2 / CUDA PhysX / R3 arm / Position gripper
- Original MuJoCo spec SHA-256: `1dc528e76764f681b134d27a7cba67188c14979ccc2f8c704c00314eabb02c2f`
- Original horizon, reset range, success predicates, gates, and limits are unchanged.

## Changes

The task-owned R3 approach adds a continuous high-clearance wrist-pitch waypoint and restores the original grasp orientation while descending. It keeps the 10 mm horizontal gate, 215 mm measured clearance, original descent/hover target, and action budget. Its current reachability regression is kinematic and does not model contact physics.

The Position close-ready contract remains unchanged. When the cube prevents the measured opening from reaching 45 mm, task code may authorize a lift attempt only after both public pad OBBs agree with the cube within 0.1 mm, the opposed grasp geometry is within its existing bounds, and relative translation/rotation remains stable for at least 100 ms. Each sample is bound to the same public state-boundary identity, observation digest, execution step/time, episode, reset sample, scene, and provider materialization; state revision must increase. Stale or contradictory publications interrupt dwell. A completion event distinguishes this geometric authorization from measured closure and records its first sample, stable interval count, and elapsed duration. This is not a contact or grasp-success claim.

Harness Oracle finalization now uses the environment's actual structured stop outcome rather than the Expert's diagnostic failure reason. Recorder validation remains strict.

## Validation

On the existing Core Python environment, the focused suite passed:

```bash
source /home/lly/projects/geochora-harness-20261103/environment.sh
cd /home/lly/projects/geochora-harness-20261103/GeoChora
"$GEOCHORA_CORE_PYTHON" -m pytest -q \
  task_env/diagnostics/tasks/test_pickcube_r3_approach_reachability.py \
  task_env/diagnostics/tasks/test_pickcube_safe_approach_path.py \
  task_env/diagnostics/tasks/test_pickcube_position_capture_authorization.py \
  task_env/script/agent/test_isaac_candidate_startup.py \
  task_env/script/agent/test_oracle_candidate_wiring.py \
  task_env/diagnostics/tasks/test_phase_ii_c03b_stop_outcome.py \
  task_env/diagnostics/tasks/test_phase_ii_c05a_structured_recording.py \
  -k "not position_close_stops"
```

```text
59 passed, 1 deselected in 3.26s
```

The deselected test launches the native environment. The run covered the R3 approach, original safe-approach regressions, capture authorization, Isaac candidate startup, Oracle wiring, and strict stop/recording contracts. Defect-sensitive tests first reproduced four failures for missing dwell evidence, stale publication acceptance, interrupted dwell, and a stale authorization label; the updated implementation passes those checks.

`git diff --check` passed. Current documentation validation was run both before and after the documentation edit. Both invocations report the same two pre-existing missing protected local inputs (`docs/maintenance/20261030_runtime_route_diagnostic_handoff.md` and `MUJOCO_LOG.TXT`); no new documentation validator error was introduced.

## Native limitation and qualification boundary

A representative seed 2 Oracle launch at input HEAD `2eaf29060d45f3afa3d720d0dcb794692d97b29d`, with the original horizon 1000 and 420-second cap, exited before Kit startup or physics because NVIDIA Omniverse EULA acceptance is not configured. The worker receipt is `workspace/harness/isaac-core-repair-20261103-001/oracle-seed2-repair-v1/native/native_run_receipt.json`. The EULA was not accepted by this run. No new physics episode, H5 recording, or success evidence was produced.

Consequently, these source changes are only offline-tested. The preserved earlier Isaac campaign remains 0/20 solved, with a failed diagnostic Oracle. No seed success, successful Oracle, completed twenty-seed campaign, provider parity, or Qualification is claimed. Once EULA acceptance is explicitly authorized, run representative seeds 2 and 0 under the unchanged spec, inspect their physical outcomes, then start the twenty-seed campaign and successful Oracle only if those gates pass.
