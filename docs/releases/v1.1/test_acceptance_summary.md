# Test and Acceptance Summary

**RELEASE_CANDIDATE — NOT_PUBLISHED**

## Bounded current-source results

The four accepted task executions remain bound to their tested source trees;
S4.5 workflow changes did not alter their task execution closures. They were
not rerun in this release-preflight task.

| Intersection | Source | Result and bounded scope |
| --- | --- | --- |
| PickCube / GeoPhys CPU | `5b0058010f5416eefb08ce59cec43770602fc336` | seed31, 100 Hz; 151 transitions / 152 boundaries, 755 native steps, measured lift success; H5 `cd39b1d2e6c14c6a3fc39b744e26657448aedaf1d29b34ac60fcaec0026d9108`. |
| PickCube / MuJoCo CPU | `5b0058010f5416eefb08ce59cec43770602fc336` | seed31, 100 Hz; 470 / 471, 2,350 native steps, measured lift success; H5 `579c676d542f53b1dde8e7488ccff6e1fd01b7e2d6b56e2e975e759d3af69018`. |
| NutAssembly / GeoPhys CPU | `4d6d65c55eca994b4317bcfb80797c69e48452c6` | NA-S0 seed19, 100 Hz; 11 stages, 2,380 / 2,381, 11,900 native steps; task/outcome complete. Original strict Expert `stable_height_mismatch` and admitted warning are separately retained; H5 `e539d5b2662d191c0a70b1ac9dd593842279397b8627f0e3871d8852c78c2271`. |
| NutAssembly / MuJoCo CPU | `4d6d65c55eca994b4317bcfb80797c69e48452c6` | NA-S0 seed19, 100 Hz; 11 stages, 2,373 / 2,374, 11,865 native steps; task/outcome complete, strict Expert completed; H5 `f7000d28e1a47363542bef8909341d5a13582175941b394987ad31f0ea4f5931`. |

Canonical PickCube recording produced 470 transitions / 471 boundaries and
passed storage/logical roundtrip. The H5 output was finalized on both
successful and failed task paths, with failure returning nonzero. H5
roundtrip is not D0 replay.

S4.5-B bounded evidence includes a Pendulum `merged_scene` CPU batch smoke, a
one-update SB3 Pendulum smoke, scalar/batch Pendulum rasterizer RGB smokes,
H5 inspection, provider-free RSL admission checks, and renderer contract tests
with fake endpoints. No native GeoPhys Rigid Batch test, Native Flora
qualification, general RL training, or Physics × Renderer interoperability
was established.

## Provider-free preflight

### S5-C2 rerun on the integrated candidate source

- **PASS:** `PYTHONPATH=GeoPhys/src:. /home/lly/miniconda3/envs/geochora/bin/python -m pytest -q task_env/diagnostics/tasks task_env/diagnostics/render/test_backend_registry.py` on code/document target `2fb60de7851bf2e5651c2dc99fff7451c16e1a94`, Python 3.12.14: **147 passed, 6 subtests passed, 1 upstream Taichi locale deprecation warning, 160.07 s**. Receipt: `workspace/maintenance/p2_0_s5_c2_20261017/provider_free_final.log`.
- **NOT_RUN / environment error:** the first shell invocation selected the default Python 3.14.7 environment, where pytest is not installed. The observed output and exit code are preserved separately at `workspace/maintenance/p2_0_s5_c2_20261017/provider_free_default_python_attempt.log`. This is not a test result.

- **PASS:** 147 tests and 6 subtests, 155.10 s, at the exact patch committed as
  `bee498d`; one upstream Taichi locale deprecation warning. Log:
  `workspace/maintenance/p2_0_s5_a_20261017/provider_free_final.log`.
- **PASS:** final bounded provider-free run after the negative-import test
  helper correction: 147 tests and 6 subtests in 157.83 s, one upstream
  Taichi locale deprecation warning. Command:
  `python -m pytest -q task_env/diagnostics/tasks task_env/diagnostics/render/test_backend_registry.py`.
  The S5-B change only makes the retired-Go2 module test treat a missing
  dotted parent package as an unavailable import; it changes no runtime code.
  Log: `workspace/maintenance/p2_0_s5_b_20261017/provider_free_final.log`.
- **PASS:** S5-C1 final provider-free release suite, 147 passed, 6 subtests,
  one upstream Taichi locale deprecation warning, 160.51 s. Same command as
  above; receipt:
  `workspace/maintenance/p2_0_s5_c1_20261017/provider_free_final.log`.
- **PASS:** the trajectory converter forwarding fix's focused tests and
  post-fix workflow checks; conversion algorithm, H5 schema, and action
  semantics are unchanged.
- **PASS:** CLI `--help`, public task Artifact/config identity checks, source
  recovery manifest parsing, candidate JSON parsing, and reviewed Markdown
  local-link checks as recorded by S5-A.
- **PASS:** nine final CLI help probes for the converter dispatcher, both
  selected task examples, canonical recording, H5 inspection, SB3 Pendulum,
  scalar/batch RGB examples, and generic RSL-RL. Exact receipt:
  `workspace/maintenance/p2_0_s5_b_20261017/cli_help_check.json`.
- **PASS:** three focused gates covering forwarded `trajectory convert
  --help`, failed expert recording with finalized readable H5, and nonzero CLI
  exit on failed task outcome: 3 passed in 0.42 s. Receipt:
  `workspace/maintenance/p2_0_s5_b_20261017/cli_and_failure_gates.log`.
- **PASS — BOUNDED:** clean detached source checkout at `bee498d`, exact root
  submodule Gitlinks, and make/reset/close for PickCube and NutAssembly on both
  GeoPhys/CPU and MuJoCo/CPU. No expert routes were run. The checkout used the
  existing validated Python 3.12.14 environment.
- **PASS — PROVIDER-FREE IDENTITY PROBE:** replacing the absolute checkout root
  with `${REPO_ROOT}` produced identical PickCube MJCF. A synthetic controller
  compute generated identical physical target fields and FK/Jacobian values.
  No detached provider-applied target or full task route was run; this does not
  establish relocated full-route equivalence.
- **NOT_RUN:** a fresh dependency installation.
- **EXPLORATORY FAIL — ENVIRONMENT/IDENTITY SENSITIVITY:** the first full
  provider-free suite launched from a path under ignored `workspace/` reported
  139 passed and 8 failed. Six failures came from `find_spec()` raising
  `ModuleNotFoundError` for intentionally retired dotted modules with absent
  parent packages; the test helper was corrected and the canonical-path suite
  then passed. One failure was the test's `/workspace/` path guard being
  triggered by the checkout location. One was the PickCube controller hash
  changing with the absolute checkout root embedded in raw MJCF; the Artifact,
  config, source files, and normalized MJCF matched. A full relocated-checkout
  suite was not rerun after this analysis. See the source identity receipt and
  known limitations.
- **NOT_RUN:** broad qualification, historical Phase I campaigns, GPU
  workloads, broad RL training, checkpoint inference, and expensive task route
  reruns whose source closures are unchanged.

Test results are regression evidence only; they do not create new formal
qualification labels. The precise evidence revision, Artifact identities,
H5 hashes, and explicit non-claims are in the
[candidate matrix](capability_matrix.md).
