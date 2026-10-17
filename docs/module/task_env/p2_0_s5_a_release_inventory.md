# GeoChora P2.0-B S5-A — Release-Candidate Source Inventory

Status: **preflight draft; not a release or capability qualification**. S4.5-B
implementation head: `929dd8fafe8dca5b0f375341045501c0a8eed9c7`; its documentation
receipt is `fc12780dcaebcb12f9740ae7f3f28224a47c3bbf`. S5-A compatibility fix:
`bee498d1d784015f034c5b4af34320fdffa61411`. Public
`develop` at review: `0ff2d846a36c7014d2b40a530f52d99e64266ff9`.

The status words below are deliberately separate. `IMPLEMENTED` means code or
an API exists; `TESTED_BOUNDED` is restricted to a named test intersection;
`QUALIFIED` requires an independent decision for that exact source and scope.
Historical approvals do not transfer to the candidate source.

## Current public surface

| Surface | Current identity and owner | Status and boundary |
| --- | --- | --- |
| Public construction | `from task_env import make_env`; optional `make_parallel_env`, `make_agent`, `make_object`, `make_scene` | **IMPLEMENTED**. `make_env` is the canonical scalar environment API. Provider, task, and configuration admission remains fail-closed. |
| PickCube | UID `pick-cube-p16-reference-v1`; Artifact `pick-cube-v1/p1_6_experimental_100hz`; Artifact SHA-256 `fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4`; config SHA-256 `0d6b26b08affd68c95a4f3209111f7c4ee2ce62088b664370f7c11b6045e9aa0`; task tree `bac089f4ace6ca0693a8261fefacbc25dc108f48` | **TESTED_BOUNDED** on GeoPhys CPU and MuJoCo CPU, 100 Hz, seed 31. Its serialized Artifact identity is distinct from its public environment UID. No checkpoint inference; current source has no inherited P1.6 qualification. |
| NutAssembly | UID `nut-assembly-outcome-reference-v1`; Artifact `nut-assembly-square-v1/p1_8_e/nominal-v1`; Artifact SHA-256 `99e374bd870c70f0dd427e34c47c6e6820aaa7067365133181a001a38239b9fe`; config SHA-256 `749c78638a1e5c5e59374ceccd846767bacce5af969c2c50370482d2a288c531`; task tree `eed6b5c6f900e3c04f5150562f2758d17be4c9fb` | **TESTED_BOUNDED** on GeoPhys CPU and MuJoCo CPU, 100 Hz, NA-S0 seed 19. It uses guarded `step_expert()` and Outcome Completion V1. Task success, outcome completion, readiness warning and strict Expert lifecycle remain separate. No P1.8 FULL or D0-D2 inheritance. |
| Generic built-in tasks | `pendulum-v1`, `two-wheel-balance-v1`; generic task definitions in `task_env.tasks` | **IMPLEMENTED**. Pendulum has the bounded current batch, SB3 and rasterizer examples listed below. |
| Physics providers | Scalar selected reference routes: GeoPhys CPU and MuJoCo CPU. Pendulum smoke: GeoPhys CPU. | **TESTED_BOUNDED** only for the named cases in the [candidate matrix](capability_matrix_v1_0_1_candidate.json). No provider-wide claim. SAPIEN/Genesis remain roadmap targets, not evidenced by S4.5. |
| Batch/runtime | `BatchRuntimeProtocol`, `make_parallel_env`, `merged_scene`; retained GeoPhys-owned `GeoPhysRigidBatchRuntime` adapter | **IMPLEMENTED**. Pendulum/GeoPhys CPU/`merged_scene` bounded batch smoke is recorded. The adapter has no native validation in S4/S4.5 receipts; `static_template` is **RETIRED**, never redirected. |
| Task Artifact | Existing canonical `TaskArtifact` and `task-artifact-v0`; selected PickCube/NutAssembly Artifact hashes above | **IMPLEMENTED** and identity-tested. S4.5 changes no Artifact schema or selected serialized task identity. |
| Recording and trajectory | Existing task-owned recorder and canonical H5 readers; `trajectory.record`, `convert`, `replay`, `merge`; explicit historical replay option | **TESTED_BOUNDED** for the PickCube/MuJoCo/CPU/seed31 470-transition recording and offline validation. H5 storage/logical roundtrip is not D0 reconstruction. Incomplete task runs finalize H5 where possible and still return nonzero. |
| Learner adapters | Generic SB3 and RSL-RL interfaces | **IMPLEMENTED**. **TESTED_BOUNDED**: one SB3 Pendulum update (2 envs, 4 timesteps); RSL-RL import/explicit-UID/fail-closed admission tests only. No general learning qualification, manipulation PPO target, or native RSL run. |
| Renderer | Renderer Registry, Flora and rasterizer APIs | **IMPLEMENTED** within existing declared contracts. **TESTED_BOUNDED**: Pendulum × GeoPhys CPU × scalar or `merged_scene` batch × rasterizer RGB, one small frame/step. Provider-free Flora registry tests use fake endpoints. No Native Flora qualification or Physics × Renderer interoperability. |
| Current examples | `examples/tasks`, `examples/recording`, `examples/learning`, `examples/rendering` | **IMPLEMENTED**. Their narrow tested intersections and limits are recorded in the candidate matrix and S4.5-B report. |
| Go2 | Task/robot/diagnostic/RSL-specific active implementation | **RETIRED** from current develop; **HISTORICAL_ONLY** under `v1.0.0` and its frozen Evidence. No replacement UID or training target. |
| GeoChora Static Template solver | Static solver modules, factories, profiles, and public static-template configuration | **RETIRED**. Old immutable sources and recovery refs are enumerated by the S4 manifest. Generic batch contracts and the separate GeoPhys-owned adapter remain. |
| Physics × Renderer interoperability | No declared selected-task/provider/renderer intersection | **NOT_IMPLEMENTED**. |
| Further release/capability expansion | S5 release decisions; Phase II renderer interoperability; new provider or training qualifications | **PLANNED**, not part of this candidate. |

The exact tested intersections, source revisions, result receipts, and explicit
non-claims are in [`capability_matrix_v1_0_1_candidate.json`](capability_matrix_v1_0_1_candidate.json).
The immutable v1.0.0 matrix remains
[`docs/releases/v1.0/capability_matrix.json`](../../releases/v1.0/capability_matrix.json).

## Authoring and import convention

Both selected task directories contain exactly `__init__.py`, `task.py`,
`solution.py`, and `config.yaml`. The public environment route for both is
`task_env.make_env`. Package helper exports are not symmetrical today:
`task_env.tasks.pick_cube` exposes selected builder helpers, while
`task_env.tasks.nut_assembly.build_reference` raises an explicit retired-API
error and the task-owned builder lives in
`task_env.tasks.nut_assembly.task`. Recommend treating `make_env` as the only
public environment constructor and treating task module builders as authoring
internals. Do not silently alias the inconsistent helper imports. Release API
policy is listed in the compatibility inventory.

## Source and evidence boundaries

S4.5-A/B and the S5-A dispatcher fix do not modify selected task definitions or their RuntimeSession,
provider, controller, or task execution dependencies. The four-file PickCube
tree is byte-identical to the tested S2-C1 tree; NutAssembly's four-file tree
is byte-identical to the tested S2-C2 tree. S4 did change static-template
configuration and batch-factory paths, but its source identity receipt shows
that selected scalar resolved configuration identity remains unchanged. PickCube's full routes were run at S2-C1 source
`5b0058010f5416eefb08ce59cec43770602fc336`; NutAssembly's final accepted routes
were run at S2-C2 source `4d6d65c55eca994b4317bcfb80797c69e48452c6`. The task
source trees at the S4.5-B implementation remain identical to those accepted
task sources. S4.5-A separately exercised the public PickCube example and
canonical recording at `5d57272d1ce7469bb214cf185137853a7eb6deb0`; S4.5-B added
bounded Pendulum learning/rendering and H5 inspection at `929dd8f…`.

`QUALIFIED` current-source intersections: **none added by P2.0-B**. Historical
P1.0–P1.6 bounded approvals and the historical Go2 route remain tied to the
v1.0.0 implementation and evidence. No new D0, D1, or D2 qualification, no
manipulation checkpoint inference, no manipulation PPO, and no Native Flora or
GeoPhys Rigid Batch qualification is claimed.
