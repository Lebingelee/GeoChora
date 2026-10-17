# Bounded Manipulation Acceptance Summary

**RELEASE_CANDIDATE — NOT_PUBLISHED**
All four rows are **TESTED_BOUNDED**, not formally qualified. Evidence is
scoped to the listed task, provider/backend, reset, source, and configuration.

The complete machine-readable identities remain in the canonical
[capability matrix](../../../module/task_env/capability_matrix_v1_1_0_candidate.json),
[PickCube source identity](../../../module/task_env/p2_0_s2_c1_source_identity.json),
and [NutAssembly source identity](../../../module/task_env/p2_0_s2_c2_source_identity.json).
The release candidate source closure is `929dd8fafe8dca5b0f375341045501c0a8eed9c7`;
the exercised source revisions differ by task as recorded below. The candidate
matrix records the closure-preservation basis through S4.5-B.

## Selected identities

| Task route | TaskArtifact ID / SHA-256 | Task config SHA-256 | Solution / policy identities |
| --- | --- | --- | --- |
| `pick-cube-p16-reference-v1` | `pick-cube-v1/p1_6_experimental_100hz` / `fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4` | `0d6b26b08affd68c95a4f3209111f7c4ee2ce62088b664370f7c11b6045e9aa0` | P1.6 readiness expert `514a5ed3bc0d289761ef88a00b1e7c11df2795133506ab148db9ab8e98e55241`; controller `76108c78b8159391e448ad9f49050bed42fd7a86e0e00a0520083b4e5efb02e9` |
| `nut-assembly-outcome-reference-v1` | `nut-assembly-square-v1/p1_8_e/nominal-v1` / `99e374bd870c70f0dd427e34c47c6e6820aaa7067365133181a001a38239b9fe` | `749c78638a1e5c5e59374ceccd846767bacce5af969c2c50370482d2a288c531` | Solution `cba7a4932f4b36b01a855417833509d301746325ba93e85cd4cfed23a802a9b4`; Outcome V1 `a940c6cfc4b9dbe64ae55b615e7bdbd9a210dc7495c6337b08cff688c52694ee`; guard `065af38f034f896d3003d8f63cfb2ea9acac3adcefe078b678bd7596d57a0674` |

`nut-assembly-square-v1/p1_8_e/nominal-v1` is the serialized TaskArtifact
identity used by the selected route; this name does not grant P1.8 FULL status.

## Four accepted bounded runs

| Route / provider | Exercised source | Backend and reset | Result and lifecycle | H5 |
| --- | --- | --- | --- | --- |
| PickCube / GeoPhys | `5b0058010f5416eefb08ce59cec43770602fc336` | CPU, seed 31, 100 Hz | 151 transitions / 152 boundaries; 755 native steps; four expert stages completed; `task_success=true`; measured lift 0.1081811 m; no termination/truncation. | 878,784 bytes; `cd39b1d2e6c14c6a3fc39b744e26657448aedaf1d29b34ac60fcaec0026d9108` |
| PickCube / MuJoCo | `5b0058010f5416eefb08ce59cec43770602fc336` | CPU, seed 31, 100 Hz | 470 transitions / 471 boundaries; 2,350 native steps; four expert stages completed; `task_success=true`; measured lift 0.1060650 m; no termination/truncation. | 2,649,928 bytes; `579c676d542f53b1dde8e7488ccff6e1fd01b7e2d6b56e2e975e759d3af69018` |
| NutAssembly / GeoPhys | `4d6d65c55eca994b4317bcfb80797c69e48452c6` | CPU, NA-S0 seed 19, 100 Hz | All 11 planned stages and `release_retreat` completed; 2,380 transitions / 2,381 boundaries; 11,900 native steps; insertion/release measured; `task_success=true`, `outcome_complete=true`. The original strict Expert failed at step 362 on `descend_to_handle/stable_height_mismatch`; one admitted readiness warning is recorded separately. | 9,295,444 bytes; `e539d5b2662d191c0a70b1ac9dd593842279397b8627f0e3871d8852c78c2271` |
| NutAssembly / MuJoCo | `4d6d65c55eca994b4317bcfb80797c69e48452c6` | CPU, NA-S0 seed 19, 100 Hz | All 11 planned stages and `release_retreat` completed; 2,373 transitions / 2,374 boundaries; 11,865 native steps; insertion/release measured; `task_success=true`, `outcome_complete=true`; original Expert completed with no readiness warning. | 8,827,904 bytes; `f7000d28e1a47363542bef8909341d5a13582175941b394987ad31f0ea4f5931` |

For all NutAssembly rows, the controller was capped at 10 N, the selected
guarded close authorization and physical limits remained active, and five
native 2 ms physics steps were recorded per 100 Hz control interval. The
provider-specific controller and recipe identities are in the source identity
receipt: GeoPhys controller `094bbf739793610750e45c1dfd8442d1c680f7b1da4a5b8c537abcb08a92b759`,
recipe `7d1b20f30008383d9936355848b39abcb0af3d8780ee588a05c885529ced3286`;
MuJoCo controller `3c455279a7d54214fdb6a8d808df8a575d8938b17e92fd7df7d517bca2b492ec`,
recipe `9f5ce3206807557d1780e7de8d8abf6009dc237e11a799ac37878d8c2de3f767`.
The GeoPhys submodule Gitlink is `c665ce5028a12bb4d2afe49f05e015fa9b684a39`.
The NutAssembly per-run result records provider and CPU backend; it does not
serialize a MuJoCo package version, so no per-run version is inferred here.

## Evidence boundaries

- The candidate task source closure is unchanged from the accepted runs, as
  documented in the capability matrix; no new native runs were performed for
  S5-C3.
- These are functional acceptance runs, not new formal qualification.
- NutAssembly physical task success, Outcome Completion V1, readiness warning,
  and original strict Expert lifecycle are separate facts.
- No P1.8 FULL or D0/D1/D2 result is claimed.
- No manipulation checkpoint inference or general manipulation PPO is
  claimed.
- The absolute-path-sensitive PickCube controller identity remains a disclosed
  limitation; these summaries do not claim cross-checkout identity equality.
