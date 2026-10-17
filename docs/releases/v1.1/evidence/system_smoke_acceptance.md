# Recording, Regression, Learning, and Rendering Smokes

**RELEASE_CANDIDATE — NOT_PUBLISHED**
All results below are bounded tests/smokes, not formal qualification.

## Canonical recording and storage validation

- PickCube P1.6, MuJoCo CPU, seed 31: 470 transitions / 471 boundaries,
  `T+1=true`, canonical trajectory schema, exact logical mapping roundtrip.
- H5 size: 2,649,912 bytes; SHA-256
  `e22bcadbb142c81f2bdd8f12a432b82b22cef0c25ddeba8cec29f764bca87ae8`.
- Canonical logical identity:
  `a71f0af2817f88e9f0c318e0103addb568202c61f297f4edd6ba671b15a3ebee`.
- An incomplete recording finalizes a readable H5 and the CLI exits nonzero.
- Storage/logical roundtrip validation is not D0 reconstruction or replay
  qualification.

## Provider-free release regression

- Source target: public `develop` candidate `2fb60de7851bf2e5651c2dc99fff7451c16e1a94`.
- Command: `PYTHONPATH=GeoPhys/src:. /home/lly/miniconda3/envs/geochora/bin/python -m pytest -q task_env/diagnostics/tasks task_env/diagnostics/render/test_backend_registry.py`.
- Result: 147 passed, 6 subtests passed, one upstream Taichi locale
  deprecation warning, 160.07 seconds.
- Log: `workspace/maintenance/p2_0_s5_c2_20261017/provider_free_final.log`,
  SHA-256 `077f593c60258c00ffc3eb9c693b1a3c97c695d10c8d0b7acec1335bf9c0f8b2`.
- Converter argv forwarding and failure-result gates: 3 tests passed; log
  `workspace/maintenance/p2_0_s5_b_20261017/cli_and_failure_gates.log`,
  SHA-256 `fbd78fec782001f93d58ec55c49ed2f14ea9bf835f6197896c81813538559ce5`.

## Learning and rendering

| Route | Bounded result | Evidence boundary |
| --- | --- | --- |
| Pendulum `merged_scene` batch, GeoPhys CPU | Two worlds; reset and one zero-action step; finite observations/rewards. | Not GeoPhysRigidBatchRuntime validation. |
| Pendulum SB3, GeoPhys CPU `merged_scene` | Two environments, one update, four timesteps; requested seed 73, runner worker seed 75; summary, return H5, and checkpoint finalized. | No convergence, manipulation PPO, or general RL qualification. |
| Pendulum scalar rasterizer RGB, GeoPhys CPU | Reset and one step; finite float32 32×24 RGB frame. | GeoPhys rasterizer smoke, not Flora qualification. |
| Pendulum batch rasterizer RGB, GeoPhys CPU `merged_scene` | One world, one step; bounded 32×24 RGB frame. | Not a Physics × Renderer interoperability claim. |
| Generic RSL-RL adapter | Provider-free import and explicit task admission checks. | No native training run or qualification. |
| Renderer Registry / Flora contracts | Provider-free fake-endpoint contract tests. | No native Flora qualification. |

The exact summaries and source revisions are recorded in the candidate
[capability matrix](../../../module/task_env/capability_matrix_v1_1_0_candidate.json)
and [S4.5-B review](../../../module/task_env/p2_0_s4_5_b_workflow_consolidation.md).

## Non-claims

This package adds no new qualification decision. It does not claim D0-D2,
P1.8 FULL, manipulation checkpoint inference, general manipulation PPO,
native GeoPhys Rigid Batch acceptance, Native Flora qualification, or complete
Physics × Renderer interoperability. Historical v1.0.0 qualifications remain
bound to the immutable v1.0.0 source and Evidence.
