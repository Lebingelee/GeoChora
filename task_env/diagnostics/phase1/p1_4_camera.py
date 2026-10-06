"""Locked P1.4 geometry/schema/admission and isolated native camera detector."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
from unittest.mock import patch
import numpy as np
from .camera.lock import prepare,verify,identities
from .camera.checks import pure_checks,admission_checks
from ...artifacts import ExecutionSpec
from ...observations.canonical_camera import CameraGeometry, project_world, back_project_world
from ...render.camera import CameraRenderSource, create_camera_session, render_manifest


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')


def fresh_guard():
    command=[sys.executable,'-c',"import sys; import task_env; import task_env.observations.canonical_camera; import task_env.render.camera; from task_env.tasks.pick_cube.candidate import build_candidate; assert build_candidate().identity_hash=='461d2f08fc08685583d4e7a9ff0cf8401a223e6b719c9ecc32e4f32476f3c25e'; forbidden=('geophys','mujoco','sapien','genesis','taichi','visualization','solvers','scene'); loaded=[n for n in sys.modules if n.split('.')[0] in forbidden]; assert not loaded,loaded; print('PASS provider-free, approved PickCube hash unchanged')"]
    result=subprocess.run(command,text=True,capture_output=True)
    return {'pass':result.returncode==0,'command':command,'stdout':result.stdout,'stderr':result.stderr}


def worker(args):
    spec,lock=verify(args.oracle);recipe=spec['recipe'];bounds=spec['tolerances']
    raw=args.output.parent
    report={'provider':args.provider,'status':'error','stage':'parent_materialization','rows':[],
            'oracle_sha256':lock['sha256'],'recipe_sha256':spec['recipe_sha256'],'provenance':identities(),
            'started_at':datetime.now(timezone.utc).isoformat(),'render_manifest':render_manifest(args.provider).to_mapping()}
    probe=None;sessions=[];start=time.monotonic()
    try:
        from .camera.native import parent_probe,canonical_parent,native_projection
        probe=parent_probe(args.provider,recipe)
        state0=canonical_parent(probe,0)
        for _ in range(recipe['control_substeps']):probe.step()
        state1=canonical_parent(probe,1)
        report['parent_states']=[state0.to_mapping(),state1.to_mapping()]
        report['clock_provenance']=('completed native substeps * measured solver.dt, matching approved GeoPhys scheduling; no exported native clock'
            if args.provider=='geophys' else 'MuJoCo MjData.time')
        execution=ExecutionSpec(args.provider,'p1_4_microfixture',args.provider,'cpu',0,'strict')
        source=CameraRenderSource.from_mapping(recipe['render_source'])
        report['render_source_hash']=source.identity_hash
        for fixture in ('fixed','dynamic'):
            camera=CameraGeometry.from_mapping(recipe['cameras'][fixture])
            report['stage']=fixture+'/native_renderer_construction'
            session=create_camera_session(camera,execution,source=source);sessions.append(session)
            for state in (state0,state1):
                report['stage']=fixture+f'/capture_step_{state.control_step}'
                directory=raw/fixture/f'step_{state.control_step}';directory.mkdir(parents=True,exist_ok=True)
                native=[]
                original=session._render
                def record(metadata):
                    rgb,depth=original(metadata);native.append((rgb.copy(),depth.copy()));return rgb,depth
                with patch.object(session,'_render',side_effect=record):observation=session.capture(state)
                m=observation.metadata;T=np.array(m.T_world_from_camera)
                expected_camera=np.array([[1,0,0,.1],[0,-1,0,-.15],[0,0,-1,2],[0,0,0,1]],dtype=float)
                expected_mount=np.array(recipe['cameras'][fixture]['T_parent_from_mount'],dtype=float)
                if fixture=='dynamic':
                    p=state.pose_world[camera.parent_frame]
                    from ...utils.rotation import quat_wxyz_to_matrix
                    parent=np.eye(4);parent[:3,:3]=quat_wxyz_to_matrix(p.quaternion_wxyz);parent[:3,3]=p.position
                    expected_camera=parent@expected_camera;expected_mount=parent@expected_mount
                expected_K=np.array([[32/math.tan(math.pi/6),0,40],[0,32/math.tan(math.pi/6),32],[0,0,1]])
                pixels=native_projection(args.provider,session,recipe['landmarks'])
                analytic=project_world(m,recipe['landmarks'])
                indices=np.array(recipe['sample_pixel_indices']);centers=indices+.5
                sampled=observation.depth[indices[:,1],indices[:,0]]
                points=back_project_world(m,centers,sampled)
                # Independent plane intersection: unnormalized world ray from K.
                rays=np.c_[centers,np.ones(len(centers))]@np.linalg.inv(expected_K).T
                directions=rays@expected_camera[:3,:3].T
                distance=(recipe['surface_top_z']-expected_camera[2,3])/directions[:,2]
                expected_points=expected_camera[:3,3]+distance[:,None]*directions
                expected_depth=distance  # optical ray z == 1
                metrics={'transform_max_abs':float(max(np.max(abs(T-expected_camera)),np.max(abs(np.array(m.T_world_from_mount)-expected_mount)))),
                    'K_max_abs':float(np.max(abs(np.array(m.K)-expected_K))),
                    'projection_pixels':float(np.max(abs(pixels-analytic))),
                    'depth_m':float(np.max(abs(sampled-expected_depth))),
                    'back_projection_m':float(np.max(abs(points-expected_points))),
                    'timestamp_s':abs(m.capture_simulation_time-state.simulation_time)}
                expected_time=state.control_step*recipe['control_dt']
                checks={key:bool(value<=bounds[key]) for key,value in metrics.items()}
                checks.update(image_schema=observation.rgb.shape==(camera.height,camera.width,3) and observation.rgb.dtype==np.float32
                    and np.isfinite(observation.rgb).all() and observation.rgb.min()>=0 and observation.rgb.max()<=1
                    and observation.depth.shape==(camera.height,camera.width) and observation.depth.dtype==np.float32
                    and np.isfinite(observation.depth).all() and np.all(sampled>0),
                    timestamp_step=m.capture_control_step==state.control_step,
                    state_timebase=abs(state.simulation_time-expected_time)<=bounds['timestamp_s'],
                    reset_time_zero=(state.control_step!=0 or state.simulation_time==0),
                    metadata_roundtrip=type(m).from_mapping(m.to_mapping()).to_mapping()==m.to_mapping())
                checks={k:bool(v) for k,v in checks.items()}
                np.save(directory/'native_rgb.npy',native[0][0]);np.save(directory/'native_depth.npy',native[0][1])
                np.save(directory/'canonical_rgb.npy',observation.rgb);np.save(directory/'canonical_depth.npy',observation.depth)
                row={'fixture':fixture,'step':state.control_step,'metrics':metrics,'checks':checks,
                    'metadata':m.to_mapping(),'native_pixels':pixels.tolist(),'analytic_pixels':analytic.tolist(),
                    'sampled_pixel_centers':centers.tolist(),'sampled_optical_z':sampled.tolist(),
                    'back_projected_world':points.tolist(),'expected_intersections':expected_points.tolist(),
                    'native_depth_convention':session.native_depth_convention,'status':'pass' if all(checks.values()) else 'fail'}
                write(directory/'measurements.json',row);report['rows'].append(row)
            session.close();sessions.remove(session)
        dynamic=[r for r in report['rows'] if r['fixture']=='dynamic']
        motion=float(np.max(abs(np.array(dynamic[1]['metadata']['T_world_from_camera'])-dynamic[0]['metadata']['T_world_from_camera'])))
        report['dynamic_parent_distinct']=motion>bounds['transform_max_abs']
        report['status']='pass' if all(r['status']=='pass' for r in report['rows']) and report['dynamic_parent_distinct'] else 'fail'
    except Exception as exc:
        report['failure']=f'{type(exc).__name__}: {exc}';traceback.print_exc()
    finally:
        for session in sessions:session.close()
        if probe is not None:probe.close()
        report['closed']=True;report['wall_time_s']=time.monotonic()-start
        verify(args.oracle);write(args.output,report)
    return 0 if report['status']=='pass' else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--oracle',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prepare',action='store_true');parser.add_argument('--provider',choices=('geophys','mujoco'))
    args=parser.parse_args()
    if args.prepare:print(json.dumps(prepare(args.oracle.parent),indent=2));return 0
    if args.provider:return worker(args)
    spec,lock=verify(args.oracle)
    if args.output.exists():raise ValueError('Evidence collision: choose fresh output')
    report={'status':'partial_with_localized_failure','oracle_sha256':lock['sha256'],'recipe_sha256':spec['recipe_sha256'],
        'provenance':identities(),'started_at':datetime.now(timezone.utc).isoformat(),
        'pure_geometry':pure_checks(spec['tolerances']['pure_geometry']),'provider_free_guard':fresh_guard(),
        'capability_admission':admission_checks(),'providers':{}}
    pure=all(report['pure_geometry'].values()) and report['provider_free_guard']['pass']
    admission=all(v['rejected'] and v['native_construction_count']==0 and v.get('positive_admission',True) for v in report['capability_admission'].values())
    write(args.output,report)
    if not pure or not admission:
        report['first_failing_boundary']='provider_free_geometry_or_admission';write(args.output,report);return 1
    marker=args.oracle.parent/'first_native_execution.json'
    if not marker.exists():write(marker,{'timestamp':datetime.now(timezone.utc).isoformat(),'oracle_sha256':lock['sha256']})
    for provider in ('geophys','mujoco'):
        raw=args.output.parent/'raw'/provider;raw.mkdir(parents=True,exist_ok=True)
        command=[sys.executable,'-m','task_env.diagnostics.phase1.p1_4_camera','--oracle',str(args.oracle),'--output',str(raw/'report.json'),'--provider',provider]
        write(raw/'command.json',command)
        environment=dict(os.environ,GEOPHYS_HEADLESS='1',MUJOCO_GL='egl',GEOPHYS_LOG_AGENT_DIR=str((raw/'native_logs').resolve()))
        with (raw/'stdout.log').open('w') as out,(raw/'stderr.log').open('w') as err:
            try:
                result=subprocess.run(command,env=environment,stdout=out,stderr=err,timeout=420)
                measured=json.loads((raw/'report.json').read_text()) if (raw/'report.json').exists() else {'status':'error','failure':'no worker report'}
                measured['exit_code']=result.returncode
            except subprocess.TimeoutExpired:measured={'status':'timeout','failure':'420 s isolated provider budget exceeded'}
        report['providers'][provider]=measured;write(args.output,report)
        print(provider,measured['status'],measured.get('stage',''),measured.get('failure',''),flush=True)
    verify(args.oracle)
    if all(v['status']=='pass' and v['exit_code']==0 for v in report['providers'].values()):report['status']='ready_for_human_review'
    report['ended_at']=datetime.now(timezone.utc).isoformat();write(args.output,report)
    return 0 if report['status']=='ready_for_human_review' else 1


if __name__=='__main__':raise SystemExit(main())
