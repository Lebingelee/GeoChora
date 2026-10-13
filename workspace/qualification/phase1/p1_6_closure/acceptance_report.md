# P1.6 Final Closure Acceptance

Status: `approved`
Human decision: approved within the bounded PickCube / V2a / 100Hz scope.
Formal decision: approved by Human Judge; see `phase_decision.yaml` (SHA256 `65f64d034f73ebf26b4749891825c4fedf188d684335ba562eea0f12d2db25ee`).

## 1. Scope

This package answers whether one source-domain-capable, provider-neutral PickCube state policy can execute the same frozen checkpoint through GeoPhys and MuJoCo under the same canonical observation, normalization, public action, controller, Task Artifact, and ResetSample contract. The bounded answer is **yes** for the frozen V2a and 100Hz evaluation scope documented here.

This is not a claim of statistical robustness, arbitrary-task or arbitrary-policy portability, provider-wide physics qualification, visual policy portability, P1.7 completion, or Phase-I completion.

## 2. Historical progression

The first state_bc route remains `partial_with_localized_failure` (31/73 EvaluationSampleSet success matrix 1/8). Later Flow engineering candidates were preserved as separate variants: V0 Flow h16/a8 33D (1/6), V1 Flow h50/a36 33D (1/6), V2 Flow h50/a36 26D without qvel (3/6), V1a Flow h50/a36 33D at 15,000 updates (1/2 pilot), and V2a Flow h50/a36 26D without qvel at 15,000 updates (6/6 on its fixed source-domain cohort). This was an engineering search, not a causal ablation; the improvement is not attributed to horizon or qvel alone.

## 3. CanonicalTrajectory result

The additive `task-env-canonical-trajectory-v0` route preserves T transitions and T+1 boundary records, including the four control layers, feedback/readiness, task outcome, and readiness-hold transitions. The historical H5 v2 route was not redefined. The original canonical trajectory acceptance remains available with its historical status and 284-file evidence index; its old partial result remains historical and is not rewritten by this final P1.6 closure decision.

## 4. D0–D2 replay result

D0 teacher-forced absolute_joint target equivalence, D1 exact `CanonicalControlTarget` replay, and D2 transformed public-action closed-loop replay all passed historically on seed 1000. They use ResetSample `fcea59824ef61219c11016f5ca5a22ba05f72d47ee4e302150e36ce8aaed7670`, trajectory logical hash `a10a579809ec80a7abd986d65e2a48d54a917ff353d2fa073d07daffcbdc3f27`, and historical TaskArtifact `461d2f08fc08685583d4e7a9ff0cf8401a223e6b719c9ecc32e4f32476f3c25e`.

D0–D2 are historical PASS Evidence whose original source provenance was preserved rather than retroactively regenerated. Their execution source tree was dirty; the source commit, dirty status, modified-file snapshot, and hashes remain recorded in the provenance Evidence. D0–D2 were not rerun for this package. They provide action/target/replay diagnostics and are not the final learned-policy portability evidence.

## 5. 100Hz temporal-profile result

The opt-in experimental artifact uses physics dt 0.002 s, five physics substeps per control boundary, and control dt 0.010 s (500 Hz physics, 100 Hz canonical control). Its Artifact identity is `fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4`. The default/historical 500Hz PickCube Artifact (`461d2f08...`) remains unchanged.

G0 timebase smoke, seed1000 expert collection, D0, D1, and D2 passed; the expert reliability pilot was 18/20 and the selected corpus has 80 train plus 20 validation trajectories. Average control frames changed from about 519.10 to 112.94 while mean simulated task duration remained of similar order (about 1.0382 s to 1.1294 s). This demonstrates reduced control-boundary density for this experiment, not that 100Hz is universally optimal.

## 6. V2a learner identity

The frozen candidate is `Flow_Vanilla` / `ConditionalUnet1D`, 26D state-only observation with arm joint velocity excluded, observation horizon 2, prediction horizon 50, action horizon 36, and 8D public `absolute_joint` action. It uses the 100Hz experimental timebase and the final checkpoint from 15,000 optimizer updates. The checkpoint SHA256 is `9c4e073659bd4862d0ef9921f6c12b9e83beb893ad949e3d4d26fda961bd24e9`; the selected 100Hz dataset manifest SHA256 is `0e13517ce9f179daf7d4c525a6fb7d33629d3bb6fdd7683b4f06ac9492cf10dd`; the resolved config identity is `b40fdb55041c98bf0defb08aa1675ee42317a447eca8daecad360294a9699e1f`. No retraining, checkpoint reselection, or normalizer refit occurred for D3.

## 7. Core D3 GeoPhys / MuJoCo result

The locked D3 spec SHA256 is `cfa389d3e8bffce4a852e70b1b5b418efb2b6ea6f9bde739fb67e74acea7a60f`. The same V2a FINAL checkpoint and paired ResetSamples were run once per provider for 10 train-support and 10 validation-support seeds.

| Cohort | GeoPhys | MuJoCo |
|---|---:|---:|
| Train-support | 10/10 | 10/10 |
| Validation-support | 10/10 | 10/10 |
| Combined | 20/20 | 20/20 |

All 20 paired seeds were PASS/PASS. The episodes used the same 26D observation contract (`be8fb4cc60b33454c9ae2a87e3e4cc9017016ccdf6770656d5ebb955d3c1c076`), normalization/config, public `absolute_joint` action route (`4888f67cacb175ad4bf41195c1c4dc9465e653485e05b53f5ca33a61ad93eba5`), and `ProductionCanonicalPandaController`. Policy inference was CUDA on both providers; GeoPhys physics used its diagnostic CUDA route and MuJoCo used CPU. Every episode passed simulator-freeze and finite-state/action checks, had zero action clipping, and confirmed the ResetSample was unchanged. No provider-specific learner patch was used.

This supports software/checkpoint portability and bounded behavioral portability for the tested PickCube contract and paired seeds. It does not establish statistical robustness or provider-wide qualification.

## 8. Supplementary Genesis / SAPIEN result

The same 10 validation seeds were also run as supplementary bounded local-environment Evidence: Genesis 10/10, SAPIEN 9/10. All 20 records used the same checkpoint and matching ResetSamples, passed simulator-freeze checks, remained finite, and had zero action clipping; there were no runtime errors. SAPIEN seed 2212 reached the 2500-control-step limit (25 s), with maximum cube lift 0.0103369 m. Genesis was 1.4.3 and SAPIEN 3.0.3; physics was CPU and policy inference CUDA.

The provider session implementation came from source commit `5e7012c70a83f26d1f6a0e51b3160efc00006c35`, supplied as a temporary local source snapshot outside `codex/p1.6-closure` (the provenance manifest lists the exact source files and hashes). The provider implementation was not copied into P1.6. These runs are not reproducible from the P1.6 closure branch alone and do not grant Genesis or SAPIEN provider qualification. They are supplemental only and do not alter the GeoPhys/MuJoCo core result.

## 9. Unsupported claims and non-goals

This package does not claim statistical robustness, all-policy or all-task portability, provider-wide qualification, visuomotor portability, P1.7 completion, or Phase-I completion. It does not resume P1.7. P1.8 remains independent and was not modified.

## 10. Provenance limitations

The D0–D2 historical source tree was dirty; that fact and the exact recorded source snapshot are retained. Genesis/SAPIEN used a temporary source overlay from outside the P1.6 branch, so those results are not closure-branch reproducible. Core D3 was run from closure source commit `9d7c42b321eb24633df670a47e3261b62aab2c7b`; the exact report and all raw D3 files are covered by `d3/file_manifest.json`. The original reciprocal train-source matrix was not completed in all directions; the accepted bounded route is one competent frozen GeoPhys-trained policy evaluated under the same provider-neutral contract on GeoPhys and MuJoCo.

## 11. Integrity and isolation checks

- Core D3: all 205 entries in `d3/file_manifest.json` matched file presence, byte size, and SHA256.
- Supplementary Genesis/SAPIEN: all 111 entries in `d3_additional_providers/evidence_manifest.json` matched file presence, byte size, and SHA256.
- Core and supplementary spec files matched their SHA256 locks; V2a checkpoint and 100Hz dataset manifest matched the frozen SHA256 values.
- D0–D2 linked report/trace/command/script hashes were checked; historical reports were read, not rerun.
- The 40 core and 20 supplementary episode records match their frozen validation/train seed membership and contract identity. Core D3 has no failed episodes; supplementary SAPIEN has only seed 2212 failure.
- No Python source was modified for closure. `compileall` of the existing D3 runner passed as a smoke check, and `git diff --check` is recorded in the final handoff. No provider simulator episodes were rerun for closure.
- GeoPhys and MuJoCo core, CanonicalTrajectory schema, controller semantics, task success, default PickCube Artifact, `public/main`, and P1.8 were not modified.

## 12. Human decision

The Human Judge approved P1.6 closure within the bounded PickCube / V2a / 100Hz / GeoPhys–MuJoCo scope. P1.7 remains deferred, P1.8 continues independently, and this result does not close Phase I.
