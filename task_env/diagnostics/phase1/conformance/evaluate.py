"""Recompute all gates from measured series, independently of provider adapters."""
import numpy as np


def maxabs(a,b):
    return float(np.max(np.abs(np.asarray(a)-np.asarray(b))))


def evaluate(spec,series,facts,camera=None):
    name=spec['probe_id'];oracle=spec['oracle'];tolerance=spec['tolerance']
    finite=all(np.isfinite(v) for row in series for v in leaves(row))
    checks={'finite':finite,'native_dt':facts['native_dt']==spec['recipe']['timebase']['physics_dt']}
    metrics={}
    if name=='asset_frame':
        measured=series[0]
        root=measured['bodies']['probe/root'];child=measured['frames']['probe/child']
        metrics={'position_max_abs':max(maxabs(root['position'],oracle['root_position']),maxabs(child['position'],oracle['child_position'])),
                 'quaternion_max_abs':max(maxabs(root['quaternion_wxyz'],oracle['root_wxyz']),maxabs(child['quaternion_wxyz'],oracle['root_wxyz'])),
                 'materialized_facts_max_abs':max(abs(facts['mass']-oracle['mass']),maxabs(facts['inertia'],oracle['inertia']),maxabs(facts['geometry'],oracle['geometry']))}
        checks['semantic_names']=set(measured['bodies'])=={'probe/root'} and set(measured['frames'])=={'probe/child'}
    elif name=='free_fall':
        state=[s['bodies']['probe/body'] for s in series]
        velocity=np.array([s['linear_velocity'] for s in state])
        positions=np.array([s['position'] for s in state])
        times=np.array([s['time'] for s in series])
        acceleration=np.diff(velocity,axis=0)/np.diff(times)[:,None]
        metrics={'vertical_acceleration_error':float(np.max(abs(acceleration[:,2]+9.81))),
                 'lateral_acceleration':float(np.max(abs(acceleration[:,:2]))),
                 'lateral_displacement':float(np.max(abs(positions[:,:2]-positions[0,:2]))),
                 'quaternion_drift':max(maxabs(s['quaternion_wxyz'],oracle['orientation']) for s in state),
                 'acceleration_z_mean':float(np.mean(acceleration[:,2])),
                 'continuous_position_error':abs(float(positions[-1,2])-(3.-.5*9.81*times[-1]**2))}
        checks['downward']=bool(np.all(np.diff(positions[:,2])<=0) and positions[-1,2]<positions[0,2])
        checks['zero_initial_velocity']=maxabs(velocity[0],[0.,0.,0.])==0
    elif name=='joint_tracking':
        q=np.array([s['joints']['probe/hinge']['position'] for s in series]);target=oracle['final_target']
        metrics={'initial_error':abs(float(q[0])),'final_error_rad':abs(float(q[-1])-target),
                 'limit_excess':max(0.,float(np.max(q))-.5,-.5-float(np.min(q))),
                 'final_joint_position':float(q[-1]),'overshoot':max(0.,float(np.max(q))-target)}
        settled=np.where(np.maximum.accumulate(np.abs(q-target)[::-1])[::-1]<=.03)[0]
        metrics['settling_time']=float(series[int(settled[0])]['time']) if len(settled) else None
        checks['target_direction']=bool(q[1]>q[0]);checks['tracking_error_decreases']=bool(abs(q[-1]-target)<abs(q[0]-target))
    elif name=='camera_depth':
        metrics={'projection_max_abs_pixels':maxabs(camera['pixels'],oracle['pixels']),
                 'center_depth_error_m':abs(camera['center_depth_m']-oracle['center_depth_m']),
                 'center_depth_m':camera['center_depth_m'],'pixels':camera['pixels']}
        checks['native_depth_finite_positive']=bool(np.isfinite(camera['center_depth_m']) and camera['center_depth_m']>0)
    elif name=='contact':
        state=[s['bodies']['probe/body'] for s in series]
        height=np.array([s['position'][2] for s in state]);velocity=np.array([s['linear_velocity'][2] for s in state])
        window=oracle['settle_window_steps'];expected=oracle['contact_center_height']
        metrics={'support_height_error_m':abs(float(height[-1])-expected),
                 'persistent_penetration_m':max(0.,float(np.max(expected-height[-window:]))),
                 'post_settle_vertical_speed':float(np.max(abs(velocity[-window:]))),
                 'final_height':float(height[-1]),'minimum_height':float(np.min(height)),
                 'maximum_transient_penetration':max(0.,float(np.max(expected-height)))}
        checks['falls']=bool(np.min(height)<height[0]-.05)
        checks['no_tunneling']=bool(np.min(height)>=oracle['no_tunneling_center_min'])
    for metric,bound in tolerance.items():
        checks[metric]=bool(np.isfinite(metrics[metric]) and metrics[metric]<=bound)
    return {'status':'pass' if all(checks.values()) else 'fail','metrics':metrics,'checks':checks}


def leaves(value):
    if isinstance(value,dict):
        for v in value.values():yield from leaves(v)
    elif isinstance(value,list):
        for v in value:yield from leaves(v)
    elif isinstance(value,(int,float)):yield value
