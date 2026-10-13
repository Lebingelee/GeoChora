"""Physical event snapshots from measured native states; no interpolation."""
import gzip,json,sys
from pathlib import Path
import numpy as np

NAMES=['c18_public_ack_g0_20_offset_a','c24_native_grip500_ramp20_offset_a_clean_protocol','c19_public_ack_g0_20_offset_b','c25_native_grip500_ramp20_offset_b_clean_protocol']

def compact(row):
    sides={}
    for side in ['left','right']:
        cs=[c for c in row['contacts'] if c['has_nut'] and side+'_finger' in c['bodies']]
        sides[side]={'pairs':[{'geom_ids':c['geom_ids'],'geom_names':c['geom_names'],'force_N':c['wrench_contact_N_Nm'][:3],'position_world_m':c['position_world_m'],'torque_COM_world_Nm':c['torque_on_nut_COM_world_Nm']} for c in cs],'force_on_Nut_world_N':np.sum([c['force_on_nut_world_N'] for c in cs],axis=0).tolist() if cs else [0.,0.,0.]}
    ee=np.array(row['ee_twist_world_rot_lin']);omega=np.array(row['nut_omega_world_rad_s'])
    origin_v=np.array(row['nut_COM_velocity_world_m_s'])+np.cross(omega,np.array(row['nut_p'])-row['nut_COM_p'])
    relative_v=np.array(row['ee_R']).reshape(3,3).T@(origin_v-ee[3:]-np.cross(ee[:3],np.array(row['nut_p'])-row['ee_p']))
    return {'time_s':row['time_s'],'phase':row['phase'],'finger_qpos_m':row['qpos'][7:9],'finger_qvel_m_s':row['qvel'][7:9],'measured_joint_sum_opening_m':sum(row['qpos'][7:9]),'native_ctrl':row['ctrl'],'actuator_force_applied':row['actuator_force_current'],'EE_pose_p_R':[row['ee_p'],row['ee_R']],'EE_twist_world_rot_lin':row['ee_twist_world_rot_lin'],'Nut_pose_p_R':[row['nut_p'],row['nut_R']],'Nut_COM_velocity_world_m_s':row['nut_COM_velocity_world_m_s'],'Nut_omega_world_rad_s':row['nut_omega_world_rad_s'],'relative_pose_p_R':[row['rel_p'],row['rel_R']],'relative_origin_velocity_in_EE_m_s':relative_v.tolist(),'normal_load_N':row['normal_load_N'],'Nut_contact_torque_body_origin_world_Nm':row['nut_contact_torque_body_origin_world_Nm'],'Nut_contact_torque_COM_world_Nm':row['nut_contact_torque_COM_world_Nm'],'contacts_by_side':sides,'loaded_finger_table_pairs':[c['geom_ids'] for c in row['contacts'] if c['finger_table'] and c['wrench_contact_N_Nm'][0]>.1]}

def analyze(root):
    result={'qualification':False,'bilateral_contact_threshold_N':.1,'runs':{}}
    for name in NAMES:
        folder=root/name;summary=json.loads((folder/'summary.json').read_text());trace=json.loads((folder/'canonical/trace.json').read_text())
        event_times={e['event']:e['t'] for e in summary['solution_events']}
        mode=next((d for row in trace for d in row['gripper_inner_trace'] if d['force_mode_active']),None)
        if mode:event_times['force_mode_first']=mode['simulation_time_s']
        events={};last=None;motion_run=None;release_z=None
        for line in gzip.open(folder/'native.jsonl.gz','rt'):
            row=json.loads(line);last=row;t=row['time_s'];loads=row['normal_load_N']
            if 'first_finger_Nut_contact' not in events and loads['left']+loads['right']>.1:events['first_finger_Nut_contact']=compact(row)
            if 'first_bilateral_contact' not in events and min(loads['left'],loads['right'])>.1:events['first_bilateral_contact']=compact(row)
            for key,target in event_times.items():
                if abs(t-target)<1e-8:events[key]=compact(row)
            release=event_times.get('verify_lift_motion_start')
            if release is not None and t>=release-1e-8:
                if release_z is None:release_z=row['ee_p'][2]
                on=row['ee_twist_world_rot_lin'][5]>.0002 and row['ee_p'][2]-release_z>5e-6
                if not on:motion_run=None
                elif motion_run is None:motion_run=t
                elif t-motion_run>=.020-1e-9 and 'observed_upward_motion_onset_s' not in events:events['observed_upward_motion_onset_s']=motion_run
        events['last_measured_native_state']=compact(last)
        result['runs'][name]={'summary_pass':summary['pass'],'failure_boundary':summary['failure_boundary'],'max_capture_drift_m':summary['max_capture_position_drift_m'],'model_hash':summary['model_hash'],'first_mode_feedback':mode,'events':events}
    result['observed_motion_definition']='after scheduled lift release, EE vertical speed>0.2mm/s and height gain>5um sustained20ms; operational diagnostic onset, not a qualification threshold'
    (root/'grasp_clock_intervention_events.json').write_text(json.dumps(result,indent=2)+'\n')
    print({n:{'pass':r['summary_pass'],'contact_time':r['events']['first_finger_Nut_contact']['time_s'],'mode_time':r['events']['force_mode_first']['time_s'],'mode_Nut_normal':r['events']['force_mode_first']['normal_load_N'],'opening_at_lift':r['events'].get('verify_lift_motion_start',r['events']['last_measured_native_state'])['measured_joint_sum_opening_m']} for n,r in result['runs'].items()})
if __name__=='__main__':analyze(Path(sys.argv[1]))
