"""Measured native-state relative-pose windows; no interpolation of observations."""
import gzip
import json
from pathlib import Path
import sys
import numpy as np


def relative_pose(ee_p, ee_R, object_p, object_R):
    R = np.asarray(ee_R, dtype=float).reshape(3, 3)
    return R.T @ (np.asarray(object_p) - np.asarray(ee_p)), R.T @ np.asarray(object_R).reshape(3, 3)


def drift(p, R, reference_p, reference_R):
    angle = np.arccos(np.clip((np.trace(reference_R.T @ R) - 1) / 2, -1, 1))
    return float(np.linalg.norm(p-reference_p)), float(angle)


def evaluate(folder):
    folder = Path(folder)
    summary = json.loads((folder/'summary.json').read_text())
    events = {e['event']:e['t'] for e in summary['solution_events']}
    authorization = events.get('controller_close_authorized')
    release = events.get('verify_lift_motion_start')
    if authorization is None or release is None:
        return {'run':folder.name, 'status':'no_authorized_lift', 'interpolation':False}
    with gzip.open(folder/'native.jsonl.gz', 'rt') as f:
        rows = [json.loads(line) for line in f]
    t = np.array([r['time_s'] for r in rows])
    xyz = np.array([r['ee_p'] for r in rows])
    table = np.array([r['normal_load_N'].get('table', 0.) for r in rows])
    velocities = np.array([r['ee_twist_world_rot_lin'][5] for r in rows])
    index = int(np.searchsorted(t, release))
    # Observed onset rule is an explicit diagnostic definition, not a task gate.
    onset_candidates = (t >= release) & (velocities > .0002) & (xyz[:,2]-xyz[index,2] > .000005)
    def first_sustained(mask, start):
        for i in range(start, len(mask)-9):
            if np.all(mask[i:i+10]):
                return i
        return None
    onset = first_sustained(onset_candidates, index)
    airborne = first_sustained((t >= release) & (table < 1e-6), index)
    trace = json.loads((folder/'canonical/trace.json').read_text())
    next_stage = next((x['simulation_time_s'] for x in trace if x['simulation_time_s'] > release and x['stage'] != 'verify_lift'), None)
    endpoint = next_stage if next_stage is not None else float(t[-1])
    refs = {'authorization':authorization, 'actual_lift_motion_onset':None if onset is None else float(t[onset])}
    windows = {'W0_authorization_sample':(authorization,authorization), 'W1_postclose_hold':(authorization,release),
               'W2_lift_to_airborne':(release,None if airborne is None else float(t[airborne])),
               'W3_airborne_lift':(None if airborne is None else float(t[airborne]),endpoint),
               'W4_endpoint_and_settling':(endpoint,float(t[-1])) if next_stage is None else (endpoint,endpoint)}
    poses = [relative_pose(r['ee_p'],r['ee_R'],r['nut_p'],r['nut_R']) for r in rows]
    output = {'run':folder.name,'sampling_Hz':500,'interpolation':False,'state_time':'pre-integration measured native state',
              'reference_events_s':refs,'planner_motion_release_s':release,'airborne_s':None if airborne is None else float(t[airborne]),
              'onset_rule':'EE upward speed >0.2mm/s and upward displacement >5um for 10 native samples',
              'airborne_rule':'reported Nut/table summed normal force <1e-6N for 10 native samples',
              'W0_limitation':'close completion is not separately instrumented; authorization sample only',
              'W4_limitation':'T1 starts another motion after verify_lift; no standalone post-lift settling interval is invented',
              'references':{}}
    for label, time in refs.items():
        if time is None:
            output['references'][label] = {'status':'onset_not_observed'}
            continue
        ref_i = int(np.argmin(np.abs(t-time)))
        values = np.array([drift(p,R,*poses[ref_i]) for p,R in poses])
        results = {}
        for name,(start,end) in windows.items():
            if start is None or end is None:
                results[name] = {'status':'event_not_observed'}
                continue
            indices = np.flatnonzero((t >= start-1e-9)&(t <= end+1e-9))
            if not len(indices):
                results[name] = {'status':'no_native_sample'}
                continue
            part=values[indices]
            results[name]={'start_s':float(t[indices[0]]),'end_s':float(t[indices[-1]]),'samples':len(indices),
                           'maximum_translation_m':float(part[:,0].max()),'maximum_rotation_rad':float(part[:,1].max()),
                           'endpoint_translation_m':float(part[-1,0]),'endpoint_rotation_rad':float(part[-1,1])}
        eligible = values[t>=time-1e-9]
        output['references'][label]={'actual_reference_sample_s':float(t[ref_i]),'windows':results,
            'total_recorded_max_translation_m':float(eligible[:,0].max()),'total_recorded_max_rotation_rad':float(eligible[:,1].max()),
            'recorded_endpoint_translation_m':float(eligible[-1,0]),'recorded_endpoint_rotation_rad':float(eligible[-1,1])}
    (folder/'offline_event_windows.json').write_text(json.dumps(output,indent=2)+'\n')
    return output


if __name__ == '__main__':
    for name in sys.argv[1:]:
        out=evaluate(name)
        print(out['run'],out.get('reference_events_s'))
