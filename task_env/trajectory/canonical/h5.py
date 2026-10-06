"""Additive canonical H5: exact logical mappings plus checked typed projections."""
import json,os
from pathlib import Path
import numpy as np
from .contracts import CanonicalTrajectory
from ...controllers.canonical.kinematics import ARM

FILE_SCHEMA='task-env-canonical-trajectory-v0'


def arrays(trajectory):
    b,t=trajectory.boundaries,trajectory.transitions;count=len(t)
    return {'control_step':np.array([v.control_step for v in b],dtype=np.int64),
        'simulation_time':np.array([v.simulation_time for v in b],dtype=np.float64),
        'arm_position':np.array([[v.state.joint_position[n] for n in ARM] for v in b],dtype=np.float64),
        'arm_velocity':np.array([[v.state.joint_velocity[n] for n in ARM] for v in b],dtype=np.float64),
        'requested_action':np.array([v.requested_action.values for v in t],dtype=np.float64).reshape(count,8),
        'target_position':np.array([[v.controller_target.arm_position[n] for n in ARM] for v in t],dtype=np.float64).reshape(count,7),
        'target_servo':np.array([[v.controller_target.arm_servo_position[n] for n in ARM] for v in t],dtype=np.float64).reshape(count,7),
        'reward':np.array([v.reward for v in t],dtype=np.float64),
        'terminated':np.array([v.terminated for v in t],dtype=np.bool_),'truncated':np.array([v.truncated for v in t],dtype=np.bool_),
        'readiness_hold':np.array([v.readiness_hold for v in t],dtype=np.bool_)}


def save(path,trajectory):
    import h5py
    trajectory.validate();path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix(path.suffix+'.tmp')
    if path.exists() or temporary.exists():raise FileExistsError('refusing trajectory overwrite')
    try:
        with h5py.File(temporary,'x') as h:
            h.attrs['schema']=FILE_SCHEMA;h.attrs['logical_hash']=trajectory.identity_hash
            h.create_dataset('logical_json',data=json.dumps(trajectory.to_mapping(),sort_keys=True,separators=(',',':'),allow_nan=False),dtype=h5py.string_dtype('utf-8'))
            group=h.create_group('numeric')
            for name,value in arrays(trajectory).items():group.create_dataset(name,data=value)
        os.replace(temporary,path)
    except Exception:
        if temporary.exists():temporary.unlink()
        raise
    return path


def load(path):
    import h5py
    with h5py.File(path,'r') as h:
        if set(h)!={'logical_json','numeric'} or h.attrs.get('schema')!=FILE_SCHEMA:raise ValueError('unsupported/unknown canonical file schema')
        value=CanonicalTrajectory.from_mapping(json.loads(h['logical_json'].asstr()[()]))
        if h.attrs.get('logical_hash')!=value.identity_hash:raise ValueError('logical content hash mismatch')
        expected=arrays(value)
        if set(h['numeric'])!=set(expected):raise ValueError('numeric schema mismatch')
        for name,array in expected.items():
            stored=h['numeric'][name]
            if stored.dtype!=array.dtype or stored.shape!=array.shape or not np.array_equal(stored[:],array):raise ValueError('numeric shape/dtype/content mismatch: '+name)
    return value
