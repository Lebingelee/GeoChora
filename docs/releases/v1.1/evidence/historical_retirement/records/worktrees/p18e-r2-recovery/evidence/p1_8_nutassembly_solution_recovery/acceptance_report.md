# P1.8-E-R2 PARTIAL — NOT QUALIFIED

## Scope
Human-authorized new solution-layer optimization, not physics/controller/task tuning. P1.8-E remains PARTIAL / NOT APPROVED; no Human approval file is created.

## Provenance
Exact production baseline 9331d1ec0d5aeafa067ea354f5d9525acf40e2ba; independent clean historical worktree f977528b. GeoPhys c665ce5 unchanged; MuJoCo3.8.1 with159 RECORD SHA256 entries intact.52 frozen behavioral files and673 old Evidence files remain byte-identical. Original P1.6 dirty tree untouched by this run; R1 was not cherry-picked as behavior authority. Shared authored XML SHA 77962d434d1dc0df0035ef42ae1ee57bb64e78ac003d760630c5ea1be73aae43; final three-profile Artifact/reset/controller identities match prior locked Evidence.

## Historical reference
Official CPU seed19 route PASS:354 transitions, exact ten stage counts, insert/release/task success true. Full passive trace and both report-only serializer attempts preserved. CUDA optional not run. Legacy source byte-identical. Historical endpoint measured opening0.063580m relies on legacy command shortcut and cannot satisfy canonical0.065m release by itself.

## Differential and TB30
Geometry/initial physical state match, but persistent legacy arm lowering versus achieved-state canonical lowering, rate, contact iterations, and actuator realization differ. Diagnostic TB30 canonical legacy route FAIL:483 transitions, no lift; not a final qualification profile. This excludes rate alone as explanation, without proving a unique controller/physics cause.

## Implemented path
New unregistered experimental NutAssemblyCanonicalSolutionV1 uses public absolute_pose/world/wxyz, canonical observations/readiness, physical-time planning and holds, finite/full close experiments and relative-pose verification. One source/config per paired attempt, no provider or native contact input. Historical class untouched. Current candidate is not recommended configuration.

## Search execution
13 paired TB100 solution iterations, all preserved. GeoPhys candidates grasp/lift, several hover; insertion remains unqualified. MuJoCo transient heuristic lift is followed by capture loss/native QACC instability; slow finite-close iteration10 avoids reset but only reaches0.048592m lift and fails readiness. Last O1 GeoPhys PASS:835 transitions,8.35s, max lift0.095763m. Last MuJoCo FAIL:746 valid recorded transitions then native clock reset; partial H5 exact. Do not reinterpret giant pre-warning finite poses or lifted=true as capture proof.

## Stop and remaining boundary
canonical_solution_search_not_converged: no dual-provider grasp satisfying shared verification readiness after13 meaningful iterations. Underlying remaining path is MuJoCo grasp/contact evolution under the frozen controller/actuator/physics route. No provider-wide defect or physics qualification failure is established. Stronger opening, contact configuration, gains, force limit and task success cannot be tuned here. No insertion optimization after initial prototype, no final lock, no successful canonical goldens.

## Qualification gates
Six expert successes NOT ESTABLISHED; TB50/TB500 expansion NOT RUN. D0six NOT RUN; D1/D2all24 NOT RUN, not24 observed replay failures. Historical legacy success and O1/failed trajectories cannot substitute.

## Oracle and readiness
Canonical success/semantic parameters, physics dt, NA-S0 and prior physical/representation tolerances unchanged. New solution readiness parameters were experimental optimization variables, not qualification tolerances. Final verification checks8mm/.15rad nut/EE attachment stability, plus the existing lifted predicate. No post-hoc task success widening. The unchanged native binary64 time gate catches actual reset, not rounding drift.

## Regressions
PickCube TB100 seed73 D1/D2 GeoPhys+MuJoCo execution/task-valid PASS; frozen D0 PASS. P1.1 S0/S1 PASS30 checks; fresh provider-free guard also blocks taichi. Canonical H5 strict logical/numeric shape/dtype/hash/T+1/T/linkage validation PASS24 recorded files, including partial provider-exception episodes. Old source/Evidence hashes, legacy source, GeoPhys checkout/gitlink, package RECORD and diff checks PASS.

## Cost and limitations
CPU isolated workers, bounded early stop under search guard, within four hours. No Flow/D3/policy/camera or later-stage work. Contact readbacks are boundary samples, not all transient native contacts. Early native-exception runs retain raw traces without H5; later driver preserves valid partial trajectories. Optional teacher-forced native-Jacobian comparison not run. Several possible solution geometries remain unexplored; this search is not proof no provider-neutral solution exists.

## Evidence
See acceptance.json, historical/, tb30_reference/, optimization/, contact_diagnostics/, precision_report.md, replay_matrix.md, regression/, evidence_index.json and handoff.md. No prior Evidence overwritten. No qualification claim; P1.6/P1.7 not waived and Phase I not closed.

## Operator steering: planner/gripper prerequisites

Before NutAssembly acceptance, analyze physical-time planning, achieved free-space arm tracking, unloaded gripper dynamics, then loaded grasp persistence. Source and preserved-six-run analysis: [planner_gripper_analysis.md](planner_gripper_analysis.md). Existing frozen control uses per-boundary DLS/gripper updates; command resampling alone does not establish closed-loop invariance. No production changes or additional physics executions were made for this analysis.
