"""Generate a bounded development handoff from retained terminal summaries."""
import datetime
import json
from pathlib import Path
import subprocess
import sys


def finalize(root):
    root=Path(root)
    head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    runs=[]
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or not (folder/'summary.json').exists():continue
        r=json.loads((folder/'summary.json').read_text())
        if r.get('case')!='arm_ramp_native_grip':continue
        row={'run':folder.name,**{k:r.get(k) for k in ['rate','mode','sample','pass','failure_boundary','max_capture_position_drift_m','max_capture_rotation_drift_rad','wall_time_s','native_samples','model_hash','recipe_identity','reset_sample_hash']}}
        trace_path=folder/'canonical/trace.json'
        if trace_path.exists():
            trace=json.loads(trace_path.read_text())
            lift=[x['capture_drift'] for x in trace if x.get('stage')=='verify_lift' and x.get('capture_drift')]
            if lift:
                row['policy_observed_verify_lift_max_translation_m']=max(x['position_m'] for x in lift)
                row['policy_observed_verify_lift_max_rotation_rad']=max(x['rotation_rad'] for x in lift)
        if (folder/'protocol_exclusion.json').exists():row['protocol_exclusion']=json.loads((folder/'protocol_exclusion.json').read_text())
        runs.append(row)
    data={'schema':'frequency-robust-grasp-final-development-v1','generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'source_head':head,'candidate':'NoSlip2 + native arm ramp v2/public ACK memory + fixed native500Hz gripper feedback',
          'CAUSAL_ATTRIBUTION':'PARTIAL','bounded_main_frequency_mechanisms':'RESOLVED','FREQUENCY_ROBUST_GRASP':'PARTIAL',
          'production_promoted':False,'formal_qualification':'NOT RUN','runs':runs}
    (root/'final_candidate_matrix.json').write_text(json.dumps(data,indent=2)+'\n')
    table='| Run | Hz | Sample | Mode | Gate | Max drift mm | Rotation rad | Wall s | Native steps |\n|---|---:|---|---|---|---:|---:|---:|---:|\n'
    for r in runs:
        gate='EXCLUDED' if r.get('protocol_exclusion') else ('PASS' if r['pass'] else 'FAIL')
        table+=f"|{r['run']}|{r['rate']}|{r['sample']}|{r['mode']}|{gate}|{1000*(r['max_capture_position_drift_m'] or 0):.3f}|{r['max_capture_rotation_drift_rad'] or 0:.6f}|{r['wall_time_s'] or 0:.1f}|{r['native_samples']}|\n"
    report=f'''# Causal Diagnosis & Frequency-Robust Grasp Report

Development investigation; source HEAD `{head}` on `codex/p1.8-frequency-robust-grasp`. No production promotion, Full Expert success claim or formal D0/D1/D2 execution. The user-defined four-hour boundary is in execution_time_boundary.json. Results below are measured runs; missing matrix cells remain missing.

## Verdict and scope

**CAUSAL_ATTRIBUTION_PARTIAL** overall. The main contrasting frequency-response mechanisms are causally resolved within the verified RoboSuite historical factorial/crossover and fresh GeoChora matched-prefix interventions. Remaining loaded transport drift, contact-model equivalence, auxiliary-pad causality and held-out full-rate transport robustness are unresolved. This conservative overall verdict supersedes any earlier bounded RESOLVED label.

**FREQUENCY_ROBUST_GRASP_PARTIAL**. The isolated candidate markedly improves G0 and restores nominal T1 capture gates at tested frequencies. T1 maximum remains approximately1.5mm, above the approximately1mm research objective. Passing existing8mm/.15rad capture bounds does not establish Full Expert or provider qualification.

## Source and measurement authority

Starting fetched public main and integration were9988cf700ac1b5f7ae9ba0a284deda4fa2141917; merge base identical. Original dirty worktrees were preserved. GeoPhys revisionc665ce5028a12bb4d2afe49f05e015fa9b684a39; menagerieb846dd12bc459d776cccb3dee0b1d02acbf7a9c7. source_evidence_audit.json verifies204 historical artifacts and nine executed canonical modules. Historical evidence is not current-HEAD qualification.

Common metric: T_EE_Nut = inverse(T_W_EE) @ T_W_Nut; p_rel=R_EE.T(p_Nut-p_EE), R_rel=R_EE.T R_Nut; translation Euclidean difference, rotation SO(3) geodesic angle. Shared native-state evaluator offline_windows.py reports authorization and observed motion onset references, per-window maxima and endpoints without interpolation. Historical policy-only limitations and historical metric recomputation remain in01_metric_alignment_report.md. Normalization preserves the approximate0.771mm versus5.436mm gap. RoboSuite has no equivalent10N readiness gate; physical close-end must remain separately labeled.

Fresh native force sidecars capture the force actually used by mj_step at its preintegration state, not force recomputed by later mj_forward. Origin/COM wrenches are distinct and contact generalized-force projection errors are near machine precision. Earlier empty or post-forward sidecars are excluded from applied-force chronology. Per-run launch provenance, source snapshots, compiled models, H5 boundary traces and native500Hz JSONL are retained. SHA256 inventory includes failures and exclusions.

## Execution semantics and RoboSuite mechanism

Installed RoboSuite1.5.2 critical source files match release commit824ac14cefcfb7ec125fe5eb2e0bad7364466154; the wheel build commit itself is unavailable. RoboSuite runs physics and OSC computation at500Hz, policy and gripper formatting at their selected cadences. PandaGripper.speed0.2 is a normalized increment per formatting call, not0.2m/s. Lower gripper cadence changes the physical-time target and acquired grasp, even with arm policy cadence unchanged.

Verified historical2×2 drift inmm: arm20/gripper20=0.770348; arm100/gripper20=0.758952; arm20/gripper100=3.679223; arm100/gripper100=3.650662. Deterministic acquisition-to-lift replay places the advantage with acquired grasp history. Arm frequency alone is rejected as the main RoboSuite explanation. This is evidence within the RoboSuite model, not cross-model physical equivalence.

GeoChora frozen R3 arm reference/servo targets update at outer policy rate and hold through physics substeps. EqualRateGripperServo uses physical-time rates rather than a universal per-call increment, but force-mode transition and feedback sampling are not fully rate invariant. Physics remains500Hz. Native actuator force, command opening, measured opening and true bilateral Nut contact load are separately recorded.

## GeoChora loaded response and controlled interventions

Matched20Hz acquisition prefix2075 native samples, same physical/contact history and same compiled model before lift:

| Lift intervention | Max G0 drift mm |
|---|---:|
|Frozen contact solver, ZOH arm|5.435607|
|Frozen contact solver, native arm ramp only|5.591232|
|NoSlip2 at lift, ZOH arm|1.928430|
|NoSlip2 at lift plus native arm ramp|0.531315|

Thus arm ramp alone cannot fix frozen loaded contact creep. Changing regularized friction-solve realization strongly changes loaded drift; smoothing arm actuator targets then removes a large residual under that solver. At100Hz the lift-only NoSlip intervention reduces5.459mm to approximately0.518mm with actual EE trajectory difference only7.25um. These counterfactuals identify a numerical contact/load-response mechanism, not proof of a defective physical friction coefficient or universal NoSlip correctness.

Under NoSlip2,20Hz ZOH arm realization produces measured peak EE acceleration5.458m/s² and angular-y ripple RMS0.006982rad/s; ramp reduces them to0.116m/s² and0.000791rad/s, with the same planned endpoints/duration and endpoint discrepancy33um. Outer rate remains varied; actual command evolution is checked at every native step. Arm-ramp memory is owned by the task-local diagnostic coordinator and uses public realized-control acknowledgements.

Historical static holds were table-supported. New fully airborne hold has only0.0578mm additional drift over approximately2.26s with no Nut/table contact. Original lift versus table-supported hold therefore cannot alone separate inertial, frictional and numerical mechanisms. Current candidate T1 maximum occurs during descend_to_peg_top; no Nut/peg contact is observed in the tracked Nut pairs. Untracked finger/peg contact is not excluded.

## Acquisition cadence remains relevant to robustness

The equal-rate-gripper NoSlip/ramp candidate fails predefined20Hz held-outs: offset_a reaches8.983mm/verify_lift failure with wide43.73mm opening; offset_b fails the unchanged close authorization deadline. Changing only gripper feedback cadence to native500Hz yields G0 PASS0.534mm/0.477mm. Preclose1575-step physical/contact prefixes are exact; first divergence is3.15s. This fresh GeoChora single-factor intervention shows force-regulation sampling affects acquisition robustness even though nominal frozen drift looked frequency insensitive.

First finger/Nut contact occurs during approach before close. Force-mode activation occurs with unilateral Nut contact and table loading; it is not evidence of bilateral Nut clamping. A10N actuator feedback value is not10N contact normal load. Grasp snapshots and contact identities are retained in grasp_clock_intervention_events.json.

## Isolated candidate and results

Selected candidate: MuJoCo NoSlip2 diagnostic solver configuration; linear native-step arm target realization after lift release; fixed500Hz gripper feedback using the same physical-time law and10N cap. No friction, geometry, force cap, controller gain, motion distance, task gate or deadline correction is selected. Candidate version identities and source snapshots differ from the frozen recipe. No per-frequency compensation constants are used.

{table}

T1 rows include verify_lift but are not independent standalone G0 trials. EXCLUDED rows retain invalid intervention pilots and do not count toward candidate coverage or mechanism claims. final_candidate_matrix.json separately records policy-observed verify_lift maxima; offline_event_windows.json uses measured native states for event windows. final_four_rate_summary.json reports the common native-event comparison. Do not blend the earlier equal-rate candidate with this candidate to fill missing cells. Predeclared held-outs are true ±1mm/±0.5degree Nut pose perturbations; trials are not favorable-seed selection. Full held-out T1 matrix remains incomplete unless explicitly shown above.

## Competing hypotheses and remaining uncertainty

Changing Nut freejoint armature to zero with refreshed model constants gives1.574mm T1; damping2→0 gives1.438mm; neither is selected. An earlier armature pilot changed the array without changing effective mass and is excluded as an invalid physical intervention. Open-loop gripper target hold during descent yields1.477mm versus1.480mm, rejecting target ratcheting as a sufficient explanation. NoSlip tolerance zero with fixed two sweeps gives identical1.480mm. Euler switching fails verify_lift with108.33mm; arm dynamics change substantially, so it cannot establish a unique integrator cause.

Measured descent contact tangent velocity remains finite. Explicit force/M predicted end velocity is smaller than actual implicitfast end velocity, but still nonzero. This is evidence of realization differences, not proof of numerical passivity failure or a unique residual cause. Auxiliary pads carry substantial loads and historical penetration risk remains, but no controlled geometry ablation establishes their causal contribution. No geometry correction is justified by these data alone.

Models differ in inertia, collision structure, friction/contact parameters, actuator transmission and freejoint mechanics. GeoChora Nut mass0.1kg with0.03 armature on all six free coordinates produces translational effective inertia0.13 and rotational approximately0.030075/0.030125; RoboSuite armature0 and damping0.0005 differ. Matching mass by density is not inertia/model equivalence. Native MuJoCo3.8.1 source is pinned to688209574d35555fb897be5795f1ce4ecca9f29a; see source_reference and integration_response_audit.md.

## Regression, tradeoffs and next decisive work

Diagnostic math/admission tests8PASS plus offline frame/metric tests2PASS; Flow21PASS; P1.1 contracts30PASS; readiness synthetic checks PASS. Fresh unchanged R1/PickCube readiness+lift passes MuJoCo and GeoPhys at predetermined seeds31/73. These are development regressions, not formal qualifications. Canonical controllers, providers, assets, task semantics and thresholds remain unchanged. See09_regression_report.md.

Native500Hz feedback and NoSlip sweeps add CPU cost; table reports measured wall time under concurrent runs and is not a controlled performance benchmark. Arm ramp changes achieved acceleration, intentionally trading actuator discontinuity for smoother physical motion without reducing transport distance or extending deadlines. Contact safety and solver transferability still need Human Review. Generic checkpoint restoration for the new coordinator memory is not qualified.

Next decisive work: complete predefined held-out T1 at all rates, then isolate descent motion direction/actual acceleration from the same verified acquired state. Estimated cost: several bounded minutes per MuJoCo run plus analysis; a geometry ablation is conditional on actual contact-wrench suspicion and would require acquisition/load-response matching. Do not start broad tuning, Full Expert optimization or D0/D1/D2. Formal solver/default promotion requires Human Review.
'''
    (root/'Causal_Diagnosis_and_Frequency_Robust_Grasp_Report.md').write_text(report)
    regression='''# Development regression report

Diagnostic test_native_math.py:8 PASS, covering native state preservation, force projection/frame handling, schedule admission, effective-inertia intervention calibration, disjoint intervention clocks and implicit damping oracle.

Offline test_offline_windows.py:2 PASS, independently verifying world-frame invariance and a known5mm/0.1rad relative-pose drift oracle. JUnit outputs retained under regression/.

Flow regression:21 PASS (flow_regression.xml). P1.1 contract runner:30 PASS (regression/p1_1). Readiness synthetic admission:PASS (regression/readiness/validation.json).

Fresh unchanged R1/PickCube readiness+lift: MuJoCo seeds31/73 PASS; GeoPhys seeds31/73 PASS. Individual launch/report/trace files retained under regression/. These runs use unchanged task endpoint/readiness gates; they are bounded development regressions, not replacement qualification.

Frozen nominal G0 evidence is retained in a01 and c07. Candidate MuJoCo G0/T1 results and held-out failures remain in final_candidate_matrix.json and run_matrix_with_sha256.json. Candidate solver is MuJoCo-only; no GeoPhys candidate G0 or formal qualification claim is made. Shared canonical controller, planner, provider, timebase, asset and task-threshold files are unchanged. No golden Full Expert, D0/D1/D2 or production promotion.
'''
    (root/'09_regression_report.md').write_text(regression)
    with (root/'10_handoff.md').open('a') as f:
        f.write(f'\n## Final bounded handoff snapshot\n\nHEAD `{head}`; branch codex/p1.8-frequency-robust-grasp. Overall causal attribution PARTIAL (main contrasting mechanisms resolved within bounded interventions); frequency-robust grasp PARTIAL. See Causal_Diagnosis_and_Frequency_Robust_Grasp_Report.md and final_candidate_matrix.json for authoritative current results. No qualification or promotion. Time boundary is execution_time_boundary.json.\n')
    decision=json.loads((root/'07_causal_decision.json').read_text())
    decision.update(status='CAUSAL_ATTRIBUTION_PARTIAL',bounded_main_mechanisms='RESOLVED',frequency_robust_grasp_status='PARTIAL',final_report='Causal_Diagnosis_and_Frequency_Robust_Grasp_Report.md')
    if not any(m.get('mechanism')=='fixed-native gripper feedback changes held-out acquisition under matched preclose history' for m in decision['mechanisms']):
        decision['mechanisms'].append({'system':'GeoChora/MuJoCo candidate',
            'mechanism':'fixed-native gripper feedback changes held-out acquisition under matched preclose history',
            'evidence':['c18_public_ack_g0_20_offset_a','c19_public_ack_g0_20_offset_b','c24_native_grip500_ramp20_offset_a_clean_protocol','c25_native_grip500_ramp20_offset_b_clean_protocol','grasp_clock_intervention_events.json'],
            'scope':'predeclared held-outs; 1575 native preclose physical/contact samples exact; not cross-model equivalence'})
    (root/'07_causal_decision.json').write_text(json.dumps(decision,indent=2)+'\n')
    print('final report generated',len(runs),'candidate summaries',head)


if __name__=='__main__':finalize(sys.argv[1])
