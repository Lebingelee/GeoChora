"""Synchronous CUDA inference against the diagnostic-only GeoPhys 100 Hz session."""
from __future__ import annotations
from datetime import datetime, timezone
import json, math, time
from pathlib import Path

import numpy as np
import torch
import task_env.alg.agent_factory
from agent_factory.agents.registry import make_agent
from agent_factory.training.identity import config_identity
from task_env.diagnostics.phase1.policy_search.timebase100 import context, sample_for_variant, _open_session, write_json, sha256_file
from task_env.diagnostics.phase1.policy_search.config_utils import load_variant_config
from task_env.diagnostics.phase1.policy_search.flow100_data import (
    select_observation_features,
    trajectory_temporal,
)
from task_env.alg.state_bc.features import features, requested_action
from task_env.tasks.pick_cube.canonical_semantics import evaluate
from task_env.diagnostics.phase1.control.worker import observation
from task_env.controllers.canonical.kinematics import ARM

ROOT=Path('workspace/experiments/p1_6_policy_search/100hz_gpu_flow')
TRAIN_ROOT=ROOT/'flow_training'
MAX_CONTROL_STEPS=2500


def percentile_ms(values,p):
    return float(np.percentile(np.asarray(values,dtype=np.float64),p)*1000.0) if values else None

def mapping(value):
    return value.to_mapping() if hasattr(value,'to_mapping') else value

def finite_state(state):
    values=[state.simulation_time,*state.joint_position.values(),*state.joint_velocity.values()]
    for pose in state.pose_world.values(): values.extend(pose.position); values.extend(pose.quaternion_wxyz)
    return bool(np.isfinite(np.asarray(values,dtype=np.float64)).all())

def _close_metrics(rows):
    indices=[i for i,row in enumerate(rows) if row['target']['gripper']['opening_m'] < 0.079999]
    if not indices: return {'close_command_observed':False,'max_close_cube_drift_m':None,'max_close_xy_drift_m':None,'max_close_single_step_displacement_m':None}
    start=indices[0]
    end=len(rows)-1
    last=rows[start]['target']['gripper']['opening_m']
    for i in range(start+1,len(rows)):
        current=rows[i]['target']['gripper']['opening_m']
        if current > last + 1e-7:
            end=i-1; break
        last=current
    c0=np.asarray(rows[start]['cube_position'],dtype=np.float64)
    drift=np.asarray([r['cube_position'] for r in rows[start:end+1]],dtype=np.float64)-c0
    step=np.diff(np.asarray([r['cube_position'] for r in rows[start:end+1]],dtype=np.float64),axis=0)
    return {'close_command_observed':True,'close_start_control_step':rows[start]['control_step'],
            'close_end_control_step':rows[end]['control_step'],
            'max_close_cube_drift_m':float(np.max(np.linalg.norm(drift,axis=1))),
            'max_close_xy_drift_m':float(np.max(np.linalg.norm(drift[:,:2],axis=1))),
            'max_close_single_step_displacement_m':float(np.max(np.linalg.norm(step,axis=1))) if len(step) else 0.0}

def rollout(seed:int, output:Path, variant_root:Path|None=None):
    output=Path(output)
    if output.exists(): raise FileExistsError(f'refusing to overwrite rollout evidence {output}')
    root=Path(variant_root) if variant_root is not None else ROOT
    train_root=root/'training' if variant_root is not None else TRAIN_ROOT
    rollout_spec_path=root/'rollout_spec.yaml'
    training_spec_path=train_root/'training_spec.yaml'
    resolved_config_path=(root/'resolved_config.yaml' if variant_root is not None
                          else train_root/'resolved_flow_config.yaml')
    hist,artifact,source,readiness,controller,expert=context('cuda')
    sample=sample_for_variant(artifact,seed)
    spec=yaml_load(rollout_spec_path)
    lock=json.loads(root.joinpath('rollout_spec_lock.json').read_text())
    if sha256_file(rollout_spec_path)!=lock['sha256']:
        raise ValueError('rollout spec lock mismatch')
    cohort_seeds=spec.get('cohort_seeds',spec.get('episodes',{}).get('fixed_followup_cohort',[]))
    if seed not in cohort_seeds:
        raise ValueError('seed is not in the locked policy-search cohort')
    checkpoint_role=spec.get('checkpoint_role','best_validation')
    if 'checkpoint_path' in spec:
        checkpoint=Path(spec['checkpoint_path'])
        expected_checkpoint_sha=spec.get('checkpoint_sha256')
    else:
        checkpoint=(train_root/'checkpoints/flow_best_validation.pth' if variant_root is None
                    else Path(spec['best_checkpoint_path']))
        expected_checkpoint_sha=spec['best_checkpoint_sha256']
    if expected_checkpoint_sha!=sha256_file(checkpoint):
        raise ValueError(f'{checkpoint_role} checkpoint changed after rollout protocol lock')
    frozen=spec['reset_samples'][str(seed)]
    from task_env.artifacts.execution import ResetSample
    if ResetSample.from_mapping(frozen).identity_hash!=sample.identity_hash:
        raise ValueError('reset sample differs from locked rollout manifest')
    config=load_variant_config(resolved_config_path)
    train_spec=yaml_load(training_spec_path)
    if config_identity(config)!=train_spec['resolved_config_sha256']:
        raise ValueError('Flow resolved config mismatch')
    if config.agent_sp.artifact_identity != train_spec['identities']:
        raise ValueError('Flow artifact identity does not match frozen training specification')
    agent=make_agent('Flow_Vanilla',config)
    checkpoint_meta=agent.load(str(checkpoint))
    if checkpoint_meta.get('artifact_identity')!=train_spec['identities']:
        raise ValueError('Flow checkpoint identity mismatch')
    agent.to(torch.device('cuda')); agent.eval()
    policy_seed=100000+seed
    torch.manual_seed(policy_seed); torch.cuda.manual_seed_all(policy_seed)
    np.random.seed(policy_seed)
    session=None; rows=[]; h2d=[]; inference=[]; d2h=[]; errors=[]
    max_lift=-float('inf'); state=None; info=None; result=None
    try:
        session=_open_session(artifact,source)
        session.reset(sample)
        state=session.snapshot(); feedback=session.control_feedback(state)
        controller.reset(state,feedback)
        obs,info,evaluation=observation(state,artifact)
        excluded_fields=spec.get('observation_contract',{}).get('excluded_fields',())
        policy_features=lambda state,feedback: select_observation_features(
            features(state,feedback), excluded_fields)
        obs_horizon=int(spec.get('obs_horizon',2))
        pred_horizon=int(spec.get('pred_horizon',config.env.pred_horizon))
        act_horizon=int(spec.get('act_horizon',8))
        max_control_steps=int(spec.get('max_control_steps',spec.get('max_control_steps_per_episode',MAX_CONTROL_STEPS)))
        if (obs_horizon!=2 or pred_horizon!=int(config.env.pred_horizon)
                or act_horizon<1 or act_horizon>pred_horizon):
            raise ValueError('runner_action_boundary: rollout horizons disagree with Flow checkpoint')
        history=[policy_features(state,feedback)]
        max_lift=float(info['task_metrics']['cube_lift'])
        issued=0; replans=0; clips=0; clip_dims=np.zeros(8,dtype=np.int64); max_violation=np.zeros(8,dtype=np.float64)
        finite_actions=True; simulation_unchanged_checks=0; stop_reason='control_step_budget'
        while state.control_step < max_control_steps and not info['is_success'] and not info['task_failure']:
            if len(history)<obs_horizon: recent=[history[0]]*obs_horizon
            else: recent=history[-obs_horizon:]
            cpu_obs=torch.from_numpy(np.stack(recent).astype(np.float32,copy=False)).unsqueeze(0).contiguous()
            torch.cuda.synchronize(); t0=time.perf_counter()
            gpu_obs=cpu_obs.to('cuda',non_blocking=False)
            torch.cuda.synchronize(); h2d.append(time.perf_counter()-t0)
            before_step=int(state.control_step); before_time=float(state.simulation_time)
            torch.cuda.synchronize(); t0=time.perf_counter()
            action_chunk=agent.sample_action({'state':gpu_obs})
            torch.cuda.synchronize(); inference.append(time.perf_counter()-t0)
            if tuple(action_chunk.shape)!=(1,pred_horizon,8): raise ValueError(f'Flow output shape {tuple(action_chunk.shape)}')
            if not bool(torch.isfinite(action_chunk).all()):
                finite_actions=False; stop_reason='nonfinite_action'; break
            # Explicit D2H synchronization completes inference before any simulation step.
            t0=time.perf_counter(); chunk=action_chunk[0].detach().to('cpu',non_blocking=False).numpy().copy(); torch.cuda.synchronize(); d2h.append(time.perf_counter()-t0)
            frozen_state=session.snapshot()
            if frozen_state.control_step!=before_step or frozen_state.simulation_time!=before_time:
                raise RuntimeError('simulator advanced during synchronous policy inference')
            simulation_unchanged_checks+=1; replans+=1
            for row_index in range(min(act_horizon,max_control_steps-state.control_step)):
                action=np.asarray(chunk[row_index],dtype=np.float32)
                request=requested_action(action)
                canonical,target=controller.compute(state,feedback,request)
                interpreted=np.asarray(canonical.interpreted_values,dtype=np.float64).reshape(-1)
                if interpreted.shape==(8,):
                    delta=np.abs(action.astype(np.float64)-interpreted)
                    max_violation=np.maximum(max_violation,delta)
                    clip_dims += (delta>1e-8).astype(np.int64)
                clips += int(bool(canonical.clipped)); issued+=1
                applied=session.apply_control(target)
                next_state=session.step(); next_feedback=session.control_feedback(next_state)
                next_obs,next_info,next_eval=observation(next_state,artifact)
                cube=np.asarray(next_state.pose_world['cube-v1'].position,dtype=np.float64)
                arm_target=[float(target.arm_position[n]) for n in ARM]
                arm_servo=[float(target.arm_servo_position[n]) for n in ARM]
                rows.append({'control_step':int(next_state.control_step),'simulation_time':float(next_state.simulation_time),
                    'requested_absolute_joint':action.astype(float).tolist(),'canonical_action':canonical.to_mapping(),
                    'target':target.to_mapping(),'applied_control':applied.to_mapping(),
                    'arm_position':{n:float(next_state.joint_position[n]) for n in ARM},
                    'arm_velocity':{n:float(next_state.joint_velocity[n]) for n in ARM},
                    'ee_pose':next_state.pose_world['panda-v1/ee'].to_mapping(),
                    'cube_pose':next_state.pose_world['cube-v1'].to_mapping(),'cube_position':cube.tolist(),
                    'measured_gripper_opening_m':float(next_feedback.gripper.opening_m),
                    'gripper_closing_force_N':float(next_feedback.gripper.closing_force_N),
                    'task_metrics':{str(k):float(v) for k,v in next_info['task_metrics'].items()},
                    'is_success':bool(next_info['is_success']),'task_failure':bool(next_info['task_failure']),
                    'finite_state':finite_state(next_state),'finite_action':bool(np.isfinite(action).all()),
                    'action_clipped':bool(canonical.clipped)})
                if not rows[-1]['finite_state']:
                    stop_reason='nonfinite_state'; state=next_state;feedback=next_feedback;info=next_info;break
                state,feedback,obs,info,evaluation=next_state,next_feedback,next_obs,next_info,next_eval
                max_lift=max(max_lift,float(info['task_metrics']['cube_lift']))
                history.append(policy_features(state,feedback))
                if info['is_success']:
                    stop_reason='task_success'; break
                if info['task_failure']:
                    stop_reason='task_failure'; break
            if stop_reason in ('task_success','task_failure','nonfinite_state','nonfinite_action'): break
        if info is not None and info.get('is_success'): stop_reason='task_success'
        if info is not None and info.get('task_failure'): stop_reason='task_failure'
        target_delta=[];servo_delta=[];grip_delta=[]
        targets=[r['target'] for r in rows]
        for a,b in zip(targets,targets[1:]):
            target_delta.append(max(abs(a['arm_position'][n]-b['arm_position'][n]) for n in ARM))
            servo_delta.append(max(abs(a['arm_servo_position'][n]-b['arm_servo_position'][n]) for n in ARM))
            grip_delta.append(abs(a['gripper']['opening_m']-b['gripper']['opening_m']))
        result={'schema':'p1_6-100hz-flow-rollout-v0','seed':seed,'policy_rng_seed':policy_seed,
          'checkpoint_role':checkpoint_role,
          'provider':'geophys','physics_backend':'cuda','policy_device':'cuda','diagnostic_only':True,
          'provider_qualification_claim':False,'task_artifact_sha256':artifact.identity_hash,
          'reset_sample_hash':sample.identity_hash,'checkpoint_sha256':sha256_file(checkpoint),
          'resolved_config_sha256':train_spec['resolved_config_sha256'],'dataset_manifest_sha256':train_spec['dataset_manifest_sha256'],
          'task_success':bool(info['is_success']),'steps_to_success':len(rows) if info['is_success'] else None,
          'max_cube_lift_m':max_lift,'control_frames':len(rows),'simulated_duration_s':float(state.simulation_time),
          'simulation_time_after_inference_unchanged_checks':simulation_unchanged_checks,
          'all_inference_checks_pass':simulation_unchanged_checks==replans,
          'finite_state':all(r['finite_state'] for r in rows) and finite_state(state),
          'finite_action':finite_actions and all(r['finite_action'] for r in rows),
          'stop_reason':stop_reason,'action_count':issued,'replan_count':replans,'action_clipping_count':clips,
          'per_dimension_clip_count':clip_dims.tolist(),'max_preclamp_violation':max_violation.tolist(),
          'latency_ms':{'h2d_observation':{'p50':percentile_ms(h2d,50),'p95':percentile_ms(h2d,95),'mean':percentile_ms(h2d,50)},
                        'gpu_inference':{'p50':percentile_ms(inference,50),'p95':percentile_ms(inference,95),'mean':float(np.mean(inference)*1000) if inference else None},
                        'd2h_action':{'p50':percentile_ms(d2h,50),'p95':percentile_ms(d2h,95),'mean':float(np.mean(d2h)*1000) if d2h else None},
                        'inference_calls':len(inference)},
          'max_per_step_arm_target_delta_rad':max(target_delta) if target_delta else 0.0,
          'max_per_step_arm_servo_delta_rad':max(servo_delta) if servo_delta else 0.0,
          'max_per_step_gripper_opening_delta_m':max(grip_delta) if grip_delta else 0.0,
          'close_window':_close_metrics(rows),'trace_path':str(output.with_name('trace.json')),
          'native_contact_evidence':'not collected: no existing session diagnostic contact readback was wired into this route',
          'trace_count':len(rows),'finished_at':datetime.now(timezone.utc).isoformat()}
        output.parent.mkdir(parents=True,exist_ok=True)
        write_json(output.with_name('trace.json'),rows)
        write_json(output,result)
    finally:
        if session is not None: session.close()
    return result


def yaml_load(path):
    import yaml
    return yaml.safe_load(Path(path).read_text())

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--variant-root',type=Path)
    a=p.parse_args();print(json.dumps(rollout(a.seed,a.output,a.variant_root),sort_keys=True,indent=2,allow_nan=False))
if __name__=='__main__':main()
