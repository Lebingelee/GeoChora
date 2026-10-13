"""Compare integrated-force pilots; never substitute post-forward evaluations."""
import gzip,json,sys
from pathlib import Path
import numpy as np

def analyze(root):
    result={}
    for name,reference in [('c01_applied_force_candidate20','b04_candidate_20'),('c02_applied_force_candidate100','b02_candidate_100')]:
        summary=json.loads((root/name/'summary.json').read_text());old=json.loads((root/reference/'summary.json').read_text())
        rows=[json.loads(line) for line in gzip.open(root/name/'native.jsonl.gz','rt')]
        assert all(r['sampling_semantics']=='integrated_step_force_preintegration_state' for r in rows)
        assert not summary['diagnostic_errors']
        # Common physical lift-relative interval, well before lift completion.
        lift=4.15 if summary['rate']==20 else 4.12
        selected=[r for r in rows if lift+.3<=r['time_s']<lift+2.0]
        powers=[];moments=[];omega=[];normal=[]
        for r in selected:
            power=0.
            for c in r['contacts']:
                if c['has_nut'] and any('finger' in b for b in c['bodies']):
                    w=np.asarray(c['wrench_contact_N_Nm']);v=np.asarray(c['relative_velocity_contact_m_s']);av=np.asarray(c['relative_angular_velocity_contact_rad_s'])
                    # Force acts on body2; velocities body2-body1. Includes spin.
                    power+=float(w[1:3]@v[1:3]+w[3:]@av)
            powers.append(power);moments.append(r['nut_contact_torque_COM_world_Nm']);omega.append(r['nut_omega_world_rad_s']);normal.append([r['normal_load_N']['left'],r['normal_load_N']['right']])
        moments=np.asarray(moments);omega=np.asarray(omega)
        result[name]={'rate_Hz':summary['rate'],'native_samples':len(rows),'trajectory_logical_hash_equal':summary['live_recording']['logical_hash']==old['live_recording']['logical_hash'],'drift_equal':summary['max_capture_position_drift_m']==old['max_capture_position_drift_m'],'max_projection_error':summary['max_contact_projection_error'],'window_relative_lift_s':[.3,2.0],'samples_in_window':len(selected),'mean_friction_power_W':float(np.mean(powers)),'friction_power_positive_fraction':float(np.mean(np.array(powers)>1e-8)),'torque_COM_mean_Nm':moments.mean(axis=0).tolist(),'torque_COM_rms_Nm':np.sqrt(np.mean(moments**2,axis=0)).tolist(),'omega_mean_rad_s':omega.mean(axis=0).tolist(),'omega_rms_rad_s':np.sqrt(np.mean(omega**2,axis=0)).tolist(),'bilateral_mean_normal_N':np.mean(normal,axis=0).tolist()}
    (root/'applied_force_sampling_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':analyze(Path(sys.argv[1]))
