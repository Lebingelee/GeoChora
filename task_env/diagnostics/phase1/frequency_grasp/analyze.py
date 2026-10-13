"""Offline measured-state analysis; never interpolate missing native states."""
import argparse,gzip,hashlib,json
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation


def load_rows(path):
    with gzip.open(path,'rt') as f:all_rows=[json.loads(line) for line in f]
    end=next((i for i in range(1,len(all_rows)) if all_rows[i]['time_s']<=all_rows[i-1]['time_s']),len(all_rows))
    return all_rows[:end],{'recorded_samples':len(all_rows),'valid_prefix_samples':end,'native_clock_reset_observed':end<len(all_rows),'first_invalid_row':end if end<len(all_rows) else None}


def sustained_first(times,mask,duration=.020):
    run=None
    for t,on in zip(times,mask):
        if not on:run=None
        elif run is None:run=t
        elif t-run>=duration-1e-9:return float(run)
    return None


def analyze(folder):
    rows,validity=load_rows(folder/'native.jsonl.gz');s=json.loads((folder/'summary.json').read_text())
    events={e['event']:e['t'] for e in s['solution_events']};ts=np.array([r['time_s'] for r in rows]);p=np.array([r['rel_p'] for r in rows]);ee=np.array([r['ee_p'] for r in rows]);v=np.array([r['ee_twist_world_rot_lin'][3:] for r in rows]);acc=np.gradient(v,ts,axis=0)
    start=events.get('verify_lift_motion_start');auth=events.get('controller_close_authorized');result={'validity':validity,'events':events,'case':s['case'],'rate':s['rate'],'canonical_result':{k:s.get(k) for k in ['pass','failure_boundary','verify_lift_pass','live_recording']},'references':{},'observed_only':True}
    for name,t in [('authorization',auth),('lift_start',start)]:
        if t is None:continue
        idx=int(np.argmin(abs(ts-t)));assert abs(ts[idx]-t)<1e-8
        drift=np.linalg.norm(p-p[idx],axis=1);base=np.array(rows[idx]['rel_R']).reshape(3,3)
        angles=np.array([Rotation.from_matrix(base.T@np.array(r['rel_R']).reshape(3,3)).magnitude() for r in rows]);mask=ts>=t-1e-8
        result['references'][name]={'max_drift_m':float(drift[mask].max()),'endpoint_drift_m':float(drift[-1]),'max_rotation_rad':float(angles[mask].max()),'reference_rel_p':p[idx].tolist(),'first_capture_8mm_violation_s':next((float(ti) for ti,di in zip(ts[mask],drift[mask]) if di>.008),None)}
    if start is None:return result
    ix=int(np.argmin(abs(ts-start)));mask=ts>=start-1e-8;weighted=[];interior_load=[];left=[];right=[];torque=[];table=[];centroids=[]
    for r in rows:
        cs=[c for c in r['contacts'] if c['has_nut'] and any(b in ['left_finger','right_finger'] for b in c['bodies'])]
        fn=sum(c['wrench_contact_N_Nm'][0] for c in cs)
        weighted.append(np.sqrt(sum(c['wrench_contact_N_Nm'][0]*sum(v*v for v in c['relative_velocity_contact_m_s'][1:]) for c in cs)/fn) if fn>1e-8 else 0)
        interior_load.append(sum(c['wrench_contact_N_Nm'][0] for c in cs if c['cone_utilization'] is not None and c['cone_utilization']<.95)/fn if fn>1e-8 else None)
        left.append(r['normal_load_N']['left']);right.append(r['normal_load_N']['right']);table.append(r['normal_load_N']['table']);torque.append(r['nut_contact_torque_COM_world_Nm'])
        centroid={}
        for side,body in [('left','left_finger'),('right','right_finger')]:
            sidecs=[c for c in cs if body in c['bodies']];total=sum(c['wrench_contact_N_Nm'][0] for c in sidecs)
            if total>1e-8:
                cp=sum(np.array(c['position_world_m'])*c['wrench_contact_N_Nm'][0] for c in sidecs)/total
                centroid[side]=(np.array(r['nut_R']).reshape(3,3).T@(cp-r['nut_p'])).tolist()
        centroids.append(centroid)
    drift=np.linalg.norm(p-p[ix],axis=1);rate=np.gradient(drift,ts);table0=table[ix]
    cutoff=result['references']['lift_start']['first_capture_8mm_violation_s']
    safe_mask=mask & (ts<=cutoff+1e-8) if cutoff is not None else mask
    result['pre_capture_motion']={'window':'lift start through first8mm violation; later numerical failures remain in raw trace',
        'last_time_s':float(ts[safe_mask][-1]),'max_speed_m_s':float(np.linalg.norm(v[safe_mask],axis=1).max()),
        'max_acceleration_m_s2':float(np.linalg.norm(acc[safe_mask],axis=1).max()),
        'rms_acceleration_m_s2':float(np.sqrt(np.mean(np.sum(acc[safe_mask]**2,axis=1)))),
        'height_gain_m':float(ee[np.flatnonzero(safe_mask)[-1],2]-ee[ix,2])}
    result['actual_EE_motion']={'max_speed_m_s':float(np.linalg.norm(v[mask],axis=1).max()),'max_acceleration_m_s2':float(np.linalg.norm(acc[mask],axis=1).max()),'rms_acceleration_m_s2':float(np.sqrt(np.mean(np.sum(acc[mask]**2,axis=1)))),'height_gain_m':float(ee[-1,2]-ee[ix,2]),'duration_s':float(ts[-1]-start)}
    result['contact_event_chain']={'first_sustained_slip_after_lift_s':sustained_first(ts[mask],np.array(weighted)[mask]>.0002),'first_sustained_drift_growth_s':sustained_first(ts[mask],rate[mask]>.0002),'table_below_10_percent_s':next((float(t) for t,f in zip(ts[mask],np.array(table)[mask]) if f<table0*.1),None),'first_no_table_contact_s':next((r['time_s'] for r in rows if r['time_s']>=start and not any(c['has_nut'] and any('table' in b for b in c['bodies']) for c in r['contacts'])),None),'bilateral_loaded_fraction':float(np.mean((np.array(left)[mask]>.1)&(np.array(right)[mask]>.1))),'median_normal_load_L_R_N':[float(np.median(np.array(left)[mask])),float(np.median(np.array(right)[mask]))],'median_force_weighted_tangent_speed_m_s':float(np.median(np.array(weighted)[mask])),'median_normal_load_fraction_inside_cone_95pct':float(np.median([q for t,q in zip(ts,interior_load) if t>=start and q is not None]))}
    result['samples']={'time_s':ts[mask].tolist(),'event_relative_time_s':(ts[mask]-start).tolist(),'drift_m':drift[mask].tolist(),'EE_v_world':v[mask].tolist(),'EE_a_world':acc[mask].tolist(),'normal_left_N':np.array(left)[mask].tolist(),'normal_right_N':np.array(right)[mask].tolist(),'normal_table_N':np.array(table)[mask].tolist(),'COM_contact_torque_world_Nm':np.array(torque)[mask].tolist(),'force_weighted_slip_m_s':np.array(weighted)[mask].tolist(),'contact_centroid_nut_local':[c for t,c in zip(ts,centroids) if t>=start-1e-8]}
    result['fixed_time_windows']={}
    for name,t0,t1 in [('initial_2p2_s',start,start+2.2),('airborne_endpoint_hold_2p2_s',6.92,9.12)]:
        ids=np.flatnonzero((ts>=t0-1e-8)&(ts<=t1+1e-8))
        if len(ids) and ts[ids[-1]]>=t1-1e-8:
            window_name=name if s['case']=='airborne_hold' or name=='initial_2p2_s' else 'common_clock_window_6p92_9p12'
            result['fixed_time_windows'][window_name]={'from_lift_start_max_drift_m':float(drift[ids].max()),
                'increment_from_window_start_max_m':float(np.linalg.norm(p[ids]-p[ids[0]],axis=1).max()),
                'max_EE_speed_m_s':float(np.linalg.norm(v[ids],axis=1).max()),
                'max_EE_acceleration_m_s2':float(np.linalg.norm(acc[ids],axis=1).max()),
                'table_load_max_N':float(np.max(np.array(table)[ids]))}
    return result


def compare(base,other,boundary):
    a,va=load_rows(base/'native.jsonl.gz');b,vb=load_rows(other/'native.jsonl.gz')
    keys=['time_s','qpos','qvel','ctrl','ee_p','ee_R','nut_p','nut_R'];aa=[{k:r[k] for k in keys} for r in a if r['time_s']<=boundary+1e-9];bb=[{k:r[k] for k in keys} for r in b if r['time_s']<=boundary+1e-9]
    eq=aa==bb;shared=min(len(a),len(b));position=np.array([r['ee_p'] for r in a[:shared]])-np.array([r['ee_p'] for r in b[:shared]])
    return {'prefix_boundary_s':boundary,'prefix_samples':len(aa),'recorded_prefix_exact':eq,'prefix_sha256_base':hashlib.sha256(json.dumps(aa).encode()).hexdigest(),'prefix_sha256_other':hashlib.sha256(json.dumps(bb).encode()).hexdigest(),'max_EE_position_difference_common_samples_m':float(np.linalg.norm(position,axis=1).max()),'limitation':'deterministic native prefix replay, not restoration of every unobserved solver buffer'}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('root',type=Path);a=ap.parse_args();results={}
    for p in sorted(a.root.iterdir()):
        if (p/'native.jsonl.gz').exists() and (p/'summary.json').exists():results[p.name]=analyze(p)
    prefix={}
    for name,r in results.items():
        if name=='a01_frozen_100' or r['rate']!=100:continue
        boundary=results['a01_frozen_100']['events']['verify_lift_motion_start'] if r['case'] in ['slow_lift','noslip_lift'] else (6.90 if r['case']=='lateral' else 6.92)
        prefix[name]=compare(a.root/'a01_frozen_100',a.root/name,boundary)
    (a.root/'analysis.json').write_text(json.dumps({'runs':results,'prefix_validation':prefix},indent=2)+'\n')
    for n,r in results.items():print(n,{k:v for k,v in r.items() if k not in ['samples','references']},r['references'].get('lift_start'))

if __name__=='__main__':main()
