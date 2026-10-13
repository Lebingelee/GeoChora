"""Matched acquired-state, lift-only 2x2 analysis, bounded streaming reads."""
import gzip,hashlib,json,sys
from pathlib import Path
import numpy as np
NAMES=['c07_frozen20_applied_capture','c06_frozen_model_arm_ramp20','c11_noslip_switch20_matched_acquisition','c12_noslip_and_ramp_switch20_matched_acquisition']
KEYS=['time_s','qpos','qvel','ctrl','ee_p','ee_R','nut_p','nut_R','contacts','nut_contact_force_world_N','nut_contact_torque_COM_world_Nm']
def rows(path):
    with gzip.open(path/'native.jsonl.gz','rt') as f:
        for line in f:yield json.loads(line)
def run(root):
    out={'definition':'identical deterministic acquired physical prefix; lift-only NoSlip0/2 x arm-ZOH/ramp interventions','qualification':False,'runs':{}}
    baseline=root/NAMES[0]
    for name in NAMES:
        p=root/name;s=json.loads((p/'summary.json').read_text());digest=hashlib.sha256();count=0;first=None
        for a,b in zip(rows(baseline),rows(p)):
            if any(a[k]!=b[k] for k in KEYS):first=b['time_s'];break
            digest.update(json.dumps({k:b[k] for k in KEYS},sort_keys=True,separators=(',',':')).encode());count+=1
        metric={'same_prefix_samples':count,'first_physical_or_contact_divergence_time_s':first,'prefix_sha256':digest.hexdigest(),'model_hash':s['model_hash'],'G0_pass':s['pass'],'canonical_drift_m':s['max_capture_position_drift_m'],'canonical_rotation_rad':s['max_capture_rotation_drift_rad']}
        twists=[];omegas=[];normal=[];last=None
        for r in rows(p):
            last=r
            if 4.45<=r['time_s']<6.15:
                twists.append(r['ee_twist_world_rot_lin']);omegas.append(r['nut_omega_world_rad_s']);normal.append([r['normal_load_N']['left'],r['normal_load_N']['right']])
        tw=np.asarray(twists);om=np.asarray(omegas)
        metric.update(EE_angular_rms_rad_s=np.sqrt(np.mean(tw[:,:3]**2,axis=0)).tolist(),Nut_angular_rms_rad_s=np.sqrt(np.mean(om**2,axis=0)).tolist(),EE_acceleration_peak_m_s2=float(np.max(np.linalg.norm(np.diff(tw[:,3:],axis=0)/.002,axis=1))),bilateral_mean_normal_N=np.mean(normal,axis=0).tolist(),last_native_pose_time_s=last['time_s'],last_EE_position_m=last['ee_p'])
        out['runs'][name]=metric
    others=[out['runs'][n] for n in NAMES[1:]]
    out['matched_acquisition_confirmed']=all(x['same_prefix_samples']==2075 and abs(x['first_physical_or_contact_divergence_time_s']-4.15)<1e-9 for x in others)
    out['compiled_model_same_before_intervention']=len({x['model_hash'] for x in out['runs'].values()})==1
    out['limitation']='deterministic replay prefix, not native checkpoint restore; corrections intentionally change achieved lift dynamics; no work/energy passivity conclusion'
    (root/'matched_lift_factorial20.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':run(Path(sys.argv[1]))
