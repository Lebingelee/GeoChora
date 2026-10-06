"""Oracle-first bounded five-probe conformance; no provider-wide qualification."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

from .conformance.fixtures import PROBES
from .conformance.lock import identities,prepare,verify
from ...runtime.sessions import provider_manifest


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')


def worker(args):
    spec,lock=verify(args.oracle)
    value=spec['probes'][args.probe]
    report={'provider':args.provider,'probe':args.probe,'fixture_hash':value['fixture_hash'],
            'oracle_sha256':lock['oracle_spec_sha256'],'status':'error','series':[],
            'started_at':datetime.now(timezone.utc).isoformat(),'stage':'materialization'}
    timer=time.monotonic();adapter=None
    try:
        report['provenance']=identities()
        report['manifest']=provider_manifest(args.provider).to_mapping()
        from .conformance.adapters import GeoPhysProbe,MuJoCoProbe
        from .conformance.evaluate import evaluate
        adapter=(GeoPhysProbe if args.provider=='geophys' else MuJoCoProbe)(value)
        report['facts']=adapter.facts()
        report['stage']='initial_readback'
        report['series'].append(adapter.read())
        report['stage']='physics_step'
        for _ in range(value['recipe']['timebase']['steps']):
            adapter.step();report['series'].append(adapter.read())
        camera=None
        if args.probe=='camera_depth':
            report['stage']='native_camera_depth'
            camera=adapter.camera(args.output.parent)
            report['camera']=camera
        report['stage']='oracle_evaluation'
        report.update(evaluate(value,report['series'],report['facts'],camera))
    except Exception as exc:
        report['failure']=f'{type(exc).__name__}: {exc}';traceback.print_exc()
    finally:
        if adapter is not None:
            try:adapter.close();report['closed']=True
            except Exception as exc:report['status']='error';report['close_error']=str(exc)
        report['wall_time_s']=time.monotonic()-timer
        verify(args.oracle)
        write(args.output,report)
    return 0 if report['status']=='pass' else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--oracle',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prepare',action='store_true');parser.add_argument('--provider',choices=('geophys','mujoco'))
    parser.add_argument('--probe',choices=PROBES)
    args=parser.parse_args()
    if args.prepare:
        print(json.dumps(prepare(args.oracle.parent),indent=2));return 0
    if args.provider:return worker(args)
    try:spec,lock=verify(args.oracle);identity=identities()
    except Exception as exc:
        write(args.output,{'status':'blocked','failure':str(exc)});return 1
    started=datetime.now(timezone.utc).isoformat()
    marker=args.oracle.parent/'first_provider_execution.json'
    if not marker.exists():write(marker,{'timestamp':started,'oracle_sha256':lock['oracle_spec_sha256']})
    # This marker is durable before child launch. Lock mismatch stops every run.
    report={'status':'partial_with_localized_failure','oracle_sha256':lock['oracle_spec_sha256'],
            'first_provider_execution_after_lock':True,'tolerance_changed_after_lock':False,
            'provenance':identity,'started_at':started,'probes':{}}
    for probe in PROBES:
        report['probes'][probe]={}
        for provider in ('geophys','mujoco'):
            raw=args.output.parent/'raw'/probe/provider;raw.mkdir(parents=True,exist_ok=True)
            output=raw/'report.json'
            if output.exists():raise ValueError('raw Evidence collision; choose a fresh output directory')
            command=[sys.executable,'-m','task_env.diagnostics.phase1.p1_3_conformance','--oracle',str(args.oracle),'--output',str(output),'--provider',provider,'--probe',probe]
            write(raw/'command.json',command)
            environment=dict(os.environ);environment.update(GEOPHYS_HEADLESS='1',MUJOCO_GL='egl',
                GEOPHYS_LOG_AGENT_DIR=str((raw/'native_logs').resolve()),GEOPHYS_LOG_AGENT_DETAIL='detail')
            with (raw/'stdout.log').open('w') as stdout,(raw/'stderr.log').open('w') as stderr:
                try:
                    result=subprocess.run(command,env=environment,stdout=stdout,stderr=stderr,timeout=420)
                    measured=json.loads(output.read_text()) if output.exists() else {'status':'error','failure':'worker produced no report'}
                    measured['exit_code']=result.returncode
                except subprocess.TimeoutExpired:
                    measured={'status':'timeout','failure':'isolated intersection exceeded 420 s'}
            report['probes'][probe][provider]=measured
            write(args.output,report)
            print(probe,provider,measured['status'],measured.get('failure',''),flush=True)
    verify(args.oracle)
    report['ended_at']=datetime.now(timezone.utc).isoformat()
    if all(p['status']=='pass' for v in report['probes'].values() for p in v.values()):report['status']='ready_for_human_review'
    write(args.output,report)
    return 0 if report['status']=='ready_for_human_review' else 1


if __name__=='__main__':raise SystemExit(main())
