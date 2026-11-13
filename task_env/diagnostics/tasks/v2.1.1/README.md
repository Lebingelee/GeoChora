# v2.1.1 diagnostics: current claim and input map

This is an **in-progress U1 inventory**, not a qualification matrix. Select an
exact node; a file in this directory is not automatically a pure test. The
repository root is the working directory in the examples below. Use the
project's configured Python with pytest, NumPy, PyYAML and h5py installed.

| Claim / owner | Exact entry and inputs | Class / limits |
| --- | --- | --- |
| Formal configuration selects the four current tasks without opening declared assets or importing native SDKs; configuration/registry | `python -B task_env/diagnostics/tasks/v2.1.1/run_pure_checks.py` | Pure/fake; also runs the other pure/fake rows below. Fresh Python process, automatic pytest plugins disabled. |
| Episode import works without optional H5 tooling | Same command: `test_episode_import.py` | Fresh Python child inherits the guard; it does not construct an environment. |
| Exact USD input type/schema rejects subclasses and does not import retired candidate; Session admission | Same command: `test_isaac_effort_admission.py::test_isaac_position_input_dispatch_requires_exact_formal_type_and_schema` | Pure, this node only; the containing module also reads real source in other nodes. |
| Source lease, stale reset reconstruction, preflight failure and session ownership; Env/Runtime | Same command: `test_reset_reconstruction.py` | Fake builders plus a temporary synthetic XML snapshot; no Runtime constructed. |
| One submission owner, stale/action/resource rejection, fault without advance; lifecycle/runtime | Same command: `test_control_lifecycle.py` | Fake Runtime; no physical simulation. |
| Binding identity, stale, duplicate effects, units, wrench/measurement semantics, axis/gear, all-actuator isolation, wrong dependency; physical control and MuJoCo adapter | Same command: `test_physical_control_contract.py` | Synthetic scene/terminal; includes single-submit, duplicate and failed-ACK fault checks. The subject-free step fixture makes no post-step state claim and does not establish native admission or performance. |
| Renderer source route, foreign identity, clock mapping and camera/control publication separation; camera/renderer | Same command: `test_task_rgb_source_routing.py` | Fake state and camera sources; no App or pixel evidence. |
| Named state, effort units, stale rejection and no competing PD drive; Controller | Same command: `test_effort_servo.py` | Synthetic Controller model. |
| Nested component ownership and declared subject binding; physical control/Robot | Same command: `test_controlled_subject_declarations.py` | Synthetic scene and declarations. |
| Free-body velocity reference points and MJCF center-of-mass math; Runtime state/GeoPhys adapter | Same command: `test_free_joint_state.py` and `test_mjcf_light_com.py` | Pure numerical and invalid-input checks. They do not change the historical COM strict FAIL/bounded acceptance or requalify any provider. |
| Observation schema, frames/units, stale renderer state and Position writer identity | Same command: `test_observation_owners.py` and `test_position_outputs.py` | Pure/fake state; no asset construction. |
| GeoPhys bootstrap delegation | Same command: `test_geophys_public_bootstrap.py` | Fake `geophys` module only; no SDK initialization. |
| Example backend selection and failed factory replay | Same command: `test_script_backend_selection.py` | Pure/fake; checks `auto` selects CUDA once and exceptions retain their identity without a CPU retry. It does not prove GPU availability. |
| Ordinary completion projections and Harness eligibility | Same command: `test_completion_projections.py` | Fake Solution/Env; checks policy outcome and strict Expert eligibility remain separate, plus timeout and close-error reporting. |
| Batch admission, component factory boundary and SB3 autoreset | Same command: `test_batch_boundaries.py` | Fake component/Runtime and observations; verifies four formal UIDs reject before worker/Runtime, without claiming native batch support. |
| Learner import, model data transform and spaces | Same command: `test_learner_boundaries.py` | Fresh guarded process with a synthetic temporary H5 and spaces; no training or solver. |
| LIBERO OSC identity, gripper endpoints and replay boundaries | Same command: `bench_deploy/libero/diagnostics/test_controller_policy.py` and `test_replay_contract.py` | Fake replay and synthetic reader fixtures, including source/target/ack/clock/close tampering; no original LIBERO asset or native replay. |
| Reporter ownership and Solution lifecycle | Same command: `test_reporter_ownership.py` and four exact nodes in `test_solution_lifecycle.py` | Fake transport and pure lifecycle; stale replies do not advance, and task failure/snapshot contracts remain explicit. |
| Ordinary Isaac example configuration and launcher | Same command: `test_public_isaac_example.py` | Fake factory and subprocess; checks installed-asset routing, explicit CUDA identity and errors without opening assets or starting an App. |
| Task interval identity/time, transition guard, Nut 2 ms force cadence and fake Solution cleanup | Same command: four exact nodes in `test_task_ownership.py` | Pure/fake; the module also contains a real-source node that is excluded. |
| Worker failure and resource cleanup, fake App open/close and transport | Same command: `test_worker_resources.py` | Socketpair/thread and fake owners; no separate worker process or App. |
| Renderer capability selection, fake camera faults, pixels and resource closure | Same command: `test_renderer_capabilities.py` and `test_task_rgb.py` | Pure/fake; includes a fake window, not a real display or native rendering. |
| Recording dependency preflight and declared metadata units/frame/clock | Same command: `test_recording_preflight.py` and two exact nodes in `test_recording_observation_metadata.py` | Pure/fake; the metadata file also has a separate offline-H5 node. |
| Solution proposal ownership, fault/abort and Nut input validation | Same command: four exact `test_solution_compatibility.py` nodes | Pure/fake; other nodes in this module actually construct source and are excluded. |
| Legacy R02c/R03c reader plus strict historical Judge, including the R02c/R03c tamper matrices and changed control clock; Recorder and diagnostics Judge | `python -B task_env/diagnostics/tasks/v2.1.1/run_pure_checks.py --offline-h5` | Offline H5; explicitly reads the two files listed below and writes temporary copies. This does not exercise a solver. |
| Physical recording T/T+1, clock, schema tampering, RGB and observation metadata; Recorder | Set `TASK_ENV_PHYSICAL_RECORDINGS` and `TASK_ENV_METADATA_RECORD` to the explicit inputs below, then run `python -B task_env/diagnostics/tasks/v2.1.1/run_pure_checks.py --offline-physical` | **Offline H5**; fails before pytest if any input is missing. These one-transition records do not prove a complete Solution. |
| Formal request to source construction; Task/source owners | `PYTHONPATH=. python -B -m pytest -q -p no:cacheprovider task_env/diagnostics/tasks/v2.1.1/test_formal_configuration.py::test_formal_tasks_construct_from_common_request` | **Real source/assets**, not in the guarded pure set. Requires the actual installed inputs and a separately approved source/lock plan; it is not a native step. |
| Bounded in-process CPU route; public Task/Runtime | From a fresh run directory with repository root on `PYTHONPATH`: `python -B <repo>/task_env/diagnostics/tasks/v2.1.1/formal_cpu_probe.py --provider mujoco --case pendulum --plan <frozen-plan.json>` | **CPU native**, explicit opt-in only. Requires a unique cwd and a preflight plan with `locks_in_order`, `rss_address_space_limit_bytes` and `per_run_reserved_physics_substeps`, plus the execution-window budget. This probe is not a complete Solution. |
| Isolated worker CPU route; worker/Runtime | From a fresh run directory with repository root on `PYTHONPATH`: `python -B <repo>/task_env/diagnostics/tasks/v2.1.1/worker_cpu_probe.py <frozen-plan.json> pickcube mujoco` | **CPU native**, explicit opt-in only, same preflight; resets and executes a control interval, not a complete Solution. |
| Isaac GPU/App, existing F06 Harness | `python -B examples/tasks/pick_cube.py --provider isaacsim --execution harness --seed 31 --horizon 1000 --source-delivery-manifest <verified-manifest> --isaac-python <isaac-python> --harness-output-dir <fresh-run-dir>` | **GPU/App**; the current Harness requires horizon 1000 and is not a short smoke. Freeze the exact interpreter, manifest, locks, run directory, App/rebuild count and resource budget before an authorized run. The current manifest requirement is a Harness limitation to revisit in U2. |
| Interactive window; GeoPhys public renderer | With repository root on `PYTHONPATH`, run `python -B <repo>/task_env/diagnostics/tasks/v2.1.1/formal_cpu_probe.py --provider geophys --case pendulum --validate-schema --public-ui-check --plan <frozen-plan.json>` from a fresh run directory. | **Window/GPU plus CPU physics**; requires working display, device, public visualizer, both shared locks and explicit App/window, wall time, memory and substep budgets. The historical plan `workspace/maintenance/v211_e05_e10_u4_20261112_001/public-ui-final/native-plan.json` explains a prior run only and must not be reused blindly. |

The launcher accepts only its fixed default set, `--offline-h5`, or
`--offline-physical`, so supplying an arbitrary native node fails before pytest starts. The child process installs
`pure_guard/sitecustomize.py` before pytest and checks its guard with import
and file-access canaries, plus a child-process startup canary. It rejects common simulator imports and Python file
opens under repository `asset/` and the configured `GEOCHORA_USD_ASSET_ROOT`
(default `~/.cache/geochora/usd`). This is an instrumentation guard, not an OS
sandbox: native libraries, manually opened directory descriptors, Python
`-I`/`-S` subprocesses, and other external asset locations are outside its
claim. The selected episode-import check starts a child that inherits this guard; isolated `-I`/`-S` processes do not. Other nodes require individual fixture and resource review before being added.

## Module selection index

This index is conservative. “Mixed” means select an exact node and inspect its
fixtures; it is not permission to run the whole module as a pure check.

| Files | Class and selection |
| --- | --- |
| `test_control_lifecycle.py`, `test_controlled_subject_declarations.py`, `test_effort_servo.py`, `test_episode_import.py`, `test_free_joint_state.py`, `test_geophys_public_bootstrap.py`, `test_mjcf_light_com.py`, `test_observation_owners.py`, `test_physical_control_contract.py`, `test_position_outputs.py`, `test_recording_preflight.py`, `test_renderer_capabilities.py`, `test_reset_reconstruction.py`, `test_task_rgb.py`, `test_task_rgb_source_routing.py`, `test_worker_resources.py` | Entire files are in the fixed pure/fake set, with subprocess, fake modules or temporary synthetic files where their rows above state so. |
| `test_formal_configuration.py`, `test_isaac_effort_admission.py`, `test_solution_compatibility.py`, `test_task_ownership.py` | Mixed pure, source/asset and/or native; only the exact named nodes in `NODES` are in the pure set. |
| `test_recording_observation_metadata.py` | Mixed: two exact pure nodes and one explicit offline physical H5 node. |
| `test_legacy_leaf_codec.py`, `test_physical_recording_readback.py` | Offline H5 only; use the respective fixed offline mode and input list. |
| `test_component_source_declarations.py`, `test_declared_effort_source.py`, `test_panda_effort_source.py`, `test_tabletop_robot_source.py`, `test_usd_asset_cache.py` | Mixed fake and actual source/asset construction; no whole-file pure claim. Some nodes read pinned asset closures or USD delivery files. |
| `test_panda_effort_profiles.py` | Mixed source and real native reset/step nodes; select only after an explicit execution budget. |
| `test_scene_source_roots.py` | Synthetic temporary source inputs, but imports the `scene` package; treat as a separate source-construction check. |
| `test_replay_inspection.py` | Offline H5 files created in pytest temp; format inspection is not replay eligibility. Not included in the fixed H5 evidence modes. |

`formal_cpu_probe.py`, `worker_cpu_probe.py`, `canonical_position_probe.py`,
`r06b_order_recipe.py`, and the historical `legacy_leaf_judge.py` are utilities
or probes, not pytest suites. Their necessary inputs differ; invoking a name
containing `probe` does not by itself establish a native or pure classification.

## Historical H5 dependencies

Both samples are read-only inputs. U5 must copy and independently recheck them
before any U6 path switch; this inventory does not authorize deletion.

| Existing path under `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/` | bytes | SHA-256 |
| --- | ---: | --- |
| `r02c_005/native_run_001/E3-simultaneous-default.h5` | 1,967,311 | `65c8858cde1695c2687cf78080961d8e03e6ae599989c9a88aa367f5995d8357` |
| `r03c_004/native/E3.h5` | 2,034,080 | `6aefd11b074481f78c613a5fc275b4a7c8931c7ff0b02accd5545bccbaf5cd72` |

The physical readback nodes additionally require these exact inputs for this
round's evidence (paths under the repository root):

| Input | bytes | SHA-256 |
| --- | ---: | --- |
| `workspace/maintenance/v211_e05_e10_u6_20261113_001/physical-record-final/pendulum-rgb/episode.h5` | 84,056 | `f73e7a5736682817244f656a385679f34fca1900e55ad07ce621d8abde30af61` |
| `workspace/maintenance/v211_e05_e10_u6_20261113_001/physical-record-final/two-wheel/episode.h5` | 85,816 | `7575a344057e6745b2c73af7df382586ab9ff0172511be35c1956ef203c2c224` |
| `workspace/maintenance/v211_e05_e10_u6_20261113_001/physical-record-final/panda-rgb/episode.h5` | 202,488 | `edfe54bc9af7aac3ef2380484d405fad16c405e28c5158b6bd1e757649998f4c` |
| `workspace/maintenance/v211_e05_e10_metadata_followup_20261113_001/native/pendulum-rgb/episode.h5` | 84,304 | `af2d2800ac05211064711157a810717ad8f57b23793549392372de9e9e70e07e` |

For that set, `TASK_ENV_PHYSICAL_RECORDINGS` is the parent `physical-record-final`
and `TASK_ENV_METADATA_RECORD` is the fourth file. U5 must preserve and remap
these inputs or select and validate replacement evidence; the current test
accepts explicit alternate paths but does not assert they have these hashes.

`task_env.recorders.load_legacy_leaf_control_h5` is the generic decoder;
`legacy_leaf_judge.py` owns the historical experiment-specific stricter
oracle. Its old `load_leaf_control_records_h5` name is intentional and is
not a production fallback.

## Migration and historical references

- `test_v211_physical_control_contract.py`: 19 current provider-free
  contract functions moved to `test_physical_control_contract.py` here.
  The fake model now declares actuator count and checks refusal before global
  drive isolation. Three candidate-specific functions and an old reset fake remain historical;
  the current reset-preflight claim is covered by the precise node above.
  Those old functions must not be used as evidence for the present API.
- `fixtures/synthetic_panda_scene_v3.json` is the synthetic scene used by the
  eight-action/nine-joint unit check. It is a byte-identical copy of the
  still-consumed historical fixture `fixtures/phase_ii_d01a/a05_scene_definition_v3.json`
  (SHA-256 `1cf511f1df55da24e1a36222769b7c9395003a4da14ddd293eb4a46cd6752e1e`);
  it is not an installed model or a native source receipt.
- `test_v211_mjcf_light_com.py` → `test_mjcf_light_com.py`; two pure free-joint
  convention checks moved from `test_phase_ii_f03_core_contract_call_chain.py`
  to `test_free_joint_state.py`, preserving its shared readback fixture for
  remaining old callers. A numeric rotated-offset oracle was added.
- `test_v211_task_rgb_source_routing.py`: six behavioral checks moved to
  `test_task_rgb_source_routing.py` here (seven parametrized cases); the old
  source-text assertions remain historical and are not used as current proof.
- `test_v211_effort_servo.py` → `test_effort_servo.py` and
  `test_v211_unit4_subject_declarations.py` →
  `test_controlled_subject_declarations.py`; assertions are retained.
- `physical_contract_fixtures.py` owns the shared synthetic scene, logical
  assembly, command and receipt fixtures. The old logical-resolution and
  physical test modules re-export the former helpers for existing historical
  callers. Current version tests no longer import those old test modules.
- The old R02/R03/R04/R06, C02/D01, F04/F05 and P99 candidate scripts and
  tests are historical artifacts, not an instruction to restore retired
  production factories. Their complete per-file claim mapping is still OPEN.
  In particular, F05 naming alone is not a reason to remove provider
  admission, native readback or a useful detector. Find the matching source
  and input identity from the corresponding original report before a
  historical reproduction; `04bb926bf12636a46328e1ddcb07f00eb46e2bdd` is an
  example of a commit that still contains the old candidate builder, not a
  claim that every historical test works at that revision.
- Current version `legacy_leaf_judge.py` and `test_legacy_leaf_codec.py`
  deliberately retain the old Judge function name. The two old H5 paths above
  remain live dependencies until U5/U6 supply a verified mapping.

Mixed modules and historically retained claims still need their precise node and fixture checked before additional runs;
do not infer they are pure or completed from their file names.

## Retired-reference inventory (U1 review; mixed historical files remain scoped)

The list is the planning snapshot, not a request to import these files. “Historical” means its old candidate/reader reference is not a current entry; it does **not** assert every claim in a mixed file has already been migrated. The relevant original ref and evidence remain the historical owner. Mixed files retain their other historical or independent consumers; only the named current claims are asserted here. Names are relative to `task_env/diagnostics/tasks/`.

| File | Initial disposition | Reference sites in snapshot |
| --- | --- | ---: |
| `c02b_position_candidate.py` | Historical factory shim; current make_env/config and control checks own the public route | 1 |
| `f04_candidate_s1_support.py` | Historical F04 fixture; current provider admission and source checks have separate owners | 2 |
| `f05_dg02_core_n2_plan.py` | Historical DG02 frozen plan, retained for its original input/ref; not current solver evidence | 1 |
| `f05_dg02_core_source_receipt.py` | Historical DG02 candidate receipt builder; retain original receipt, use current source receipt owner | 2 |
| `f05_source_control_support.py` | Historical F05 input builder and source lowering; do not remove current GeoPhys admission/readback | 1 |
| `original_panda_test_source.py` | Historical Panda fixture uses retired candidate constants; source-bound current checks do not import it | 3 |
| `r02c_leaf_position_probe.py` | Historical native run; its nine H5 corruption cases now exercise current strict historical Judge | 7 |
| `r03b_fixed_attachment_probe.py` | Historical fixed-attachment native probe; provider receipt and current declaration checks remain | 2 |
| `r03c_attached_leaf_probe.py` | Historical native run; its twelve H5 corruption cases now exercise current strict historical Judge | 6 |
| `r03c_freeze.py` | Historical candidate freeze; preserve original input/ref, not a current make_env entry | 1 |
| `r03c_offline_readback.py` | Historical reader name; current legacy codec and strict Judge consume the retained H5 | 2 |
| `r04b_public_camera_s2_probe.py` | Historical camera/candidate probe; current source routing and camera-owner fake checks retained | 3 |
| `r06b_order_worker.py` | Historical candidate worker; current order recipe/attachment checks remain, old raw run stays historical | 3 |
| `test_f05_dg04_isaac_native_core_s1.py` | Historical candidate S1; F06 exact USD input and source admission checks are current, not an equivalent native run | 1 |
| `test_p99_public_position_candidate.py` | Retired public candidate UID/factory assertions; current formal task configuration rejects retired UIDs | 5 |
| `test_phase_ii_01_r02c_leaf_candidate.py` | Historical leaf candidate contract; preserve generic leaf/strict codec and actual current control-owner tests | 1 |
| `test_phase_ii_01_r02c_rework.py` | Historical candidate fixture; nine old H5 corruption claims now run on the retained R02c record | 5 |
| `test_phase_ii_01_r03b_source_declarations.py` | Historical candidate-source negatives; current fixed-attachment and transmission declarations remain | 1 |
| `test_phase_ii_01_r03c_attached_leaf.py` | Historical candidate controls; twelve old H5 corruption claims now run on the retained R03c record | 7 |
| `test_phase_ii_01_r04a_camera_consumer.py` | Historical opt-in candidate camera; current task RGB routing, identity, stale and lifecycle tests remain | 1 |
| `test_phase_ii_01_r06b_order_regression.py` | Historical candidate order tests; versioned order recipe/current source admission preserved; raw historical run is separate | 6 |
| `test_phase_ii_01_r06b_worker_regression.py` | Historical candidate worker; current worker resource-failure/close checks retained, not claimed equivalent native evidence | 1 |
| `test_phase_ii_c02b_position_profile.py` | Historical Position candidate fixture needs real source and deleted product input; current profile/control owners are separate | 1 |
| `test_phase_ii_d01a_scene_materialization.py` | Historical candidate-source fixture; minimal synthetic scene copied for current unit checks; original retained for old callers | 1 |
| `test_phase_ii_d01b_vnext_materialization.py` | Historical candidate source and old materialization; current formal TaskBuildRequest and source owners retained | 1 |
| `test_phase_ii_f05_dg02_core_candidate.py` | Historical DG02 candidate input checks; current F06 formal USD type/schema rejects foreign types | 7 |
| `test_phase_ii_f05_dg02_source_actuation.py` | Historical frozen F05 candidate config; current adapter capability and source admission remain separate | 1 |
| `test_phase_ii_f05_geophys_native_adapter.py` | Historical F05 candidate and host-model fixture; preserve GeoPhys public source/adapter checks and original evidence | 1 |
| `test_pre_stage3_boundaries.py` | Mixed; retired leaf compatibility alias is historical; other tests have independent callers and remain in place | 2 |
| `test_selected_api_configuration_and_identity.py` | Mixed; retired classifier and switch helpers historical; current exact F06 type/schema and config tests retained | 2 |
| `test_v211_physical_control_contract.py` | 19 provider-free claims moved; three retired candidate checks and one obsolete reset fake are explicit skips | 3 |
| `test_v211_physical_factory_contract.py` | Historical candidate source/fake terminal; current source transmission, fake single-submit/ACK and stale checks retained | 1 |
| `v2.1.1/legacy_leaf_judge.py` | Current historical Judge; old function name intentional, retained and exercised on both H5 samples | 2 |
| `v2.1.1/test_legacy_leaf_codec.py` | Current offline Judge/codec tests; retained plus 23 copy-only negative cases | 1 |

## Known historical check drift

`test_phase_ii_01_r01b_logical_resolution.py::test_public_documented_minimal_example_executes`
expects a `Bounded Logical Assembly resolution (R01b)` fenced example in the
v2.0.0 public API document. That heading is already absent at input HEAD
`cd486aff`; the historical node failed on that missing match during fixture
validation. Its remaining logical-resolution assertions are distinct from the
current physical checks. Do not restore a retired document solely to make that
old node green; disposition belongs with the documentation audit in U4.

## Current provider/readback ownership check

At input HEAD `cd486aff`, the non-diagnostic `task_env` Python files contain
no direct, relative, or literal dynamic import of `task_env.diagnostics` or
`task_env.tests` (465 tracked production files parsed; this static check does
not resolve computed dynamic imports). This U1 slice has no production diff.

| Interface | Actual owner and caller | Disposition |
| --- | --- | --- |
| `CompiledModelOptionsReadbackV1`, `CompiledModelPhysicsFingerprintReadbackV1` | Optional interfaces exported from `runtime/sessions/__init__.py`; MuJoCo builds source-bound receipts in `sessions/mujoco.py` | Preserve optional provider readback. No non-definition current in-tree caller was found in `task_env`; absence of an in-tree caller is not evidence that external callers do not exist. |
| `fixed_attachment_receipt`, `fixed_attachment_close_receipt` | MuJoCo session; R03c/R06b historical probes read these, and the current strict legacy Judge validates the H5-linked attachment receipt identity | Preserve provider/native readback and historical identity checks. Historical probes themselves still require their original candidate inputs. |
| F06 USD source admission | `sessions/isaac_usd_admission.py`, task and Robot source declarations; exact Session input dispatch in `sessions/api.py` | Preserve current provider admission and identity/type rejection. The guarded exact input node exercises the dispatch only; source delivery still requires a real-source check. |
| Legacy leaf H5 codec versus experiment Judge | Generic `recorders.load_legacy_leaf_control_h5`; strict `legacy_leaf_judge.py` | Keep generic decode separate from strict historical profile assessment. The current offline matrix checks both original records and copy-only corruptions. |

The source- and SDK-bound probes are not covered by this static check; no
native execution or qualification is implied. No legitimate provider check,
resource/clock/fault guard, or historical codec was removed in this slice.
