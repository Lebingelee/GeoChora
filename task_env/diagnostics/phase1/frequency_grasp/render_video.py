"""Offline hand_camera rendering of measured states, without physics replay."""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import mujoco
from scipy.spatial.transform import Rotation
from .run import context
from ..nutassembly_r5_architecture.tracking_worker import _reset
from .offline_windows import relative_pose, drift


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--ffmpeg',required=True)
    p.add_argument('--preview-only',action='store_true');a=p.parse_args()
    summary=json.loads((a.run/'summary.json').read_text())
    launch=json.loads((a.run/'launch.json').read_text())
    v=context(summary['rate'],summary['case']);s,*_=_reset(v,'mujoco')
    model=s._model;data=mujoco.MjData(model)
    model.vis.global_.offwidth=720;model.vis.global_.offheight=720
    model.vis.global_.fovy=60
    model.vis.headlight.active=1
    model.vis.headlight.ambient[:]=.5;model.vis.headlight.diffuse[:]=.8
    renderer=mujoco.Renderer(model,height=720,width=720)
    # Diagnostic hand-mounted visibility variant. Fixed mount/aim in EE frame;
    # it never tracks the Nut or changes physical asset/collision geometry.
    offset=np.array([.11,-.12,-.03]);aim=np.array([.053,0.,.047])
    forward=(aim-offset)/np.linalg.norm(aim-offset)
    right=np.cross(forward,[0.,0.,-1.]);right/=np.linalg.norm(right)
    local_R=np.column_stack([right,np.cross(forward,right),forward])
    font_path='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    font=ImageFont.truetype(font_path,20);big=ImageFont.truetype(font_path,25)
    auth=next(e['t'] for e in summary['solution_events'] if e['event']=='controller_close_authorized')
    ref=None;max_p=0.;frames=0;next_frame=0.;sidecars=[];first_bad=None
    label='NoSlip2 + arm ramp' if model.opt.noslip_iterations==2 else 'Original contact solve + arm ramp'
    a.output.parent.mkdir(parents=True,exist_ok=True)
    proc=None
    if not a.preview_only:
        proc=subprocess.Popen([a.ffmpeg,'-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s','720x960','-r','25','-i','-','-an','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(a.output)],stdin=subprocess.PIPE)
    max_ee_error=0.;max_nut_error=0.;previous_time=-1.;clock_reset=False
    try:
        with gzip.open(a.run/'native.jsonl.gz','rt') as f:
            for line in f:
                r=json.loads(line);t=r['time_s']
                if t<previous_time-1e-9:
                    clock_reset=True
                    break  # Do not render a simulator-reset state as trajectory continuation.
                previous_time=t
                rel_p,rel_R=relative_pose(r['ee_p'],r['ee_R'],r['nut_p'],r['nut_R'])
                if ref is None and t>=auth-1e-9:ref=(rel_p.copy(),rel_R.copy())
                dp,angle=(None,None) if ref is None else drift(rel_p,rel_R,*ref)
                if dp is not None:
                    max_p=max(max_p,dp)
                    if first_bad is None and (dp>.008 or angle>.15):first_bad=t
                if a.preview_only:
                    if t<4.8:continue
                elif t+1e-9<next_frame:continue
                data.qpos[:]=r['qpos'];data.qvel[:]=r['qvel'];data.ctrl[:]=r['ctrl'];data.time=t
                mujoco.mj_forward(model,data)
                ee=data.site_xpos[s._frames['panda-v1/ee']]
                nut=data.xpos[s._bodies['square-nut-v1']]
                max_ee_error=max(max_ee_error,float(np.linalg.norm(ee-r['ee_p'])))
                max_nut_error=max(max_nut_error,float(np.linalg.norm(nut-r['nut_p'])))
                assert max_ee_error<1e-8 and max_nut_error<1e-8,'offline render state mismatch'
                R=np.asarray(r['ee_R']).reshape(3,3);world_R=R@local_R
                cam_p=np.asarray(r['ee_p'])+R@offset
                renderer.update_scene(data)
                for camera in renderer.scene.camera:
                    camera.pos[:]=cam_p;camera.forward[:]=world_R[:,2];camera.up[:]=-world_R[:,1]
                rgb=renderer.render().copy()
                canvas=Image.new('RGB',(720,960),(15,20,28));canvas.paste(Image.fromarray(rgb),(0,80))
                draw=ImageDraw.Draw(canvas)
                draw.text((18,9),label,font=big,fill='white')
                draw.text((18,45),f'hand_camera | policy {summary["rate"]}Hz | physics/gripper 500Hz | 1x',font=font,fill=(180,200,225))
                draw.text((18,806),f'Physical time {t:6.3f}s   Phase: {r["phase"]}',font=font,fill='white')
                if dp is None:
                    draw.text((18,837),'Drift reference pending: close authorization',font=font,fill=(180,200,225))
                else:
                    color=(255,90,80) if first_bad is not None else (100,235,160)
                    draw.text((18,837),f'Drift {dp*1000:7.3f} mm   Peak {max_p*1000:7.3f} mm   Rot {math.degrees(angle):6.3f} deg',font=font,fill=color)
                    d=(rel_p-ref[0])*1000
                    draw.text((18,865),f'EE-frame delta: x {d[0]:+.3f}  y {d[1]:+.3f}  z {d[2]:+.3f} mm',font=font,fill=(180,200,225))
                status='Capture exceeds 8mm / 0.15rad' if first_bad is not None else 'Capture bound: 8mm / 0.15rad'
                draw.text((18,895),status,font=font,fill=(255,140,100) if first_bad is not None else (180,200,225))
                draw.text((18,924),'Measured native states | Offline rendering | Development only',font=font,fill=(145,160,180))
                sidecars.append({'frame':frames,'native_time_s':t,'phase':r['phase'],'translation_drift_m':dp,'rotation_drift_rad':angle,'maximum_translation_drift_m':max_p})
                if frames==0 or a.preview_only:canvas.save(a.output.with_suffix('.preview.png'))
                if a.preview_only:break
                proc.stdin.write(np.asarray(canvas).tobytes());frames+=1;next_frame=frames/25
        if proc is not None:
            draw=ImageDraw.Draw(canvas)
            draw.rectangle((0,0,720,80),fill=(95,22,24) if not summary['pass'] else (18,65,40))
            draw.text((18,10),'T1 attempt STOPPED' if not summary['pass'] else 'T1 development gates PASS',font=big,fill='white')
            reason='Native solver / clock consistency failure' if summary.get('error') else str(summary.get('failure_boundary') or 'End of complete T1 trajectory')
            draw.text((18,47),reason,font=font,fill='white')
            for _ in range(50):proc.stdin.write(np.asarray(canvas).tobytes())
    finally:
        if proc is not None:proc.stdin.close();code=proc.wait();assert code==0,code
        renderer.close();s.close()
    metadata={'schema':'hand-camera-native-state-video-v1','run':str(a.run.resolve()),'source_head':launch['head'],
       'camera':{'name':'hand_camera','profile':'diagnostic-hand-mounted-visibility-v1','parent':'nutassembly_ee_site / panda-v1/ee','position_local_m':offset.tolist(),'quaternion_wxyz':Rotation.from_matrix(local_R).as_quat(scalar_first=True).tolist(),'fixed_aim_local_m':aim.tolist(),'vertical_fov_deg':60,'tracks_object':False},
       'physics_restepped':False,'pose_interpolation':False,'native_sample_rate_Hz':500,'video_fps':25,
       'reference_event':'controller_close_authorized','reference_time_s':auth,'translation_metric':'norm(R_EE.T(p_Nut-p_EE) - reference_relative_p)',
       'T1_pass':summary['pass'],'failure_boundary':summary.get('failure_boundary'),'native_first_capture_violation_s':first_bad,
       'execution_error':summary.get('error'),'native_clock_reset_observed':clock_reset,'last_valid_native_time_s':previous_time,
       'end_card_duration_s':0 if a.preview_only else 2,'native_trace_sha256':hashlib.sha256((a.run/'native.jsonl.gz').read_bytes()).hexdigest(),
       'offline_render_max_EE_position_error_m':max_ee_error,'offline_render_max_Nut_position_error_m':max_nut_error,
       'video_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest() if a.output.exists() else None,'frames':sidecars}
    a.output.with_suffix('.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(json.dumps({k:metadata[k] for k in ['T1_pass','failure_boundary','native_first_capture_violation_s','offline_render_max_EE_position_error_m','offline_render_max_Nut_position_error_m']}))


if __name__=='__main__':main()
