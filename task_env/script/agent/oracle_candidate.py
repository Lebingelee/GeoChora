"""Record a compiled candidate using Core's selected recorder; no new recorder."""
from dataclasses import asdict
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import signal
import subprocess
import sys
import time

from harness_spec_schema import CandidateSpec, CheckFinding, CheckReport, save_json
from catalog_query import core_context, validate_catalog
from harness_compiler import compile_candidate, CompilationRejected


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record_candidate(spec, catalog, *, provider, seed, directory, time_limit_s=120):
    """Return the independent completion, storage and provenance checks for one run."""
    if type(seed) is not int or seed < 0:
        raise ValueError('nonnegative seed required')
    if not 1 <= time_limit_s <= 420:
        raise ValueError('time_limit_s must be 1..420')
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    ctx = validate_catalog(catalog)
    spec.save(directory/'candidate.spec.json')
    save_json(catalog, directory/'catalog.json')
    started = time.perf_counter()
    deadline = started + time_limit_s
    details = {'created_at':datetime.now(timezone.utc).isoformat(), 'provider':provider,
        'backend':'cpu', 'seed':seed, 'horizon':spec.horizon,
        'synthetic_upstream':spec.object_config['object_uid'] in catalog.get('external_assets',{}),
        'physics_execution':'real', 'time_limit_s':time_limit_s,
        'qualification':'NOT_ASSESSED', 'D0':'NOT_ASSESSED', 'D1':'NOT_ASSESSED', 'D2':'NOT_ASSESSED',
        'video':{'status':'NOT_RECORDED','reason':'selected reference route has no supported render configuration'},
        'episode':None,'recording':None,'verification':None,'errors':[],
        'tool_sha256':{n:sha256(Path(__file__).parent/n) for n in
            ('oracle_candidate.py','harness_compiler.py','harness_spec_schema.py')}}
    env = None
    artifact_hash = None
    findings = []
    recording_started = False
    h5 = directory/'oracle.h5'
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    def timeout(*_):
        raise TimeoutError('Oracle wall-clock budget exhausted')
    try:
        signal.signal(signal.SIGALRM, timeout)
        signal.setitimer(signal.ITIMER_REAL, time_limit_s)
        compiled = compile_candidate(spec,catalog,provider=provider)
        artifact_hash = compiled.artifact_hash
        save_json(compiled.artifact.to_mapping(),directory/'candidate.artifact.json')
        env = compiled.env_class()(provider=provider,backend='cpu')
        _, reset_info = env.reset(seed=seed)
        env.start_recording(h5)
        recording_started = True
        from examples._common import run_expert, identity_summary
        details['episode'] = run_expert(env,seed=seed,horizon=spec.horizon,
            already_reset=True,initial_info=reset_info)
        details['identity'] = identity_summary(env,provider=provider)
        details['controller_identity'] = env.controller.identity
        details['expert_identity'] = env.solution.identity
        fault = getattr(env,'execution_fault',None)
        details['execution_fault'] = fault.to_mapping() if hasattr(fault,'to_mapping') else (str(fault) if fault else None)
        if details['episode']['status'] != 'PASS':
            findings.append(CheckFinding('oracle_completion','expert_failed','unknown','',
                details['episode'],'task success AND complete expert without truncation',{'seed':seed}))
        if fault:
            raise RuntimeError('execution fault remains latched')
    except CompilationRejected as error:
        findings.extend(error.report.findings)
    except Exception as error:
        fault=getattr(error,'execution_fault',None) or (getattr(env,'execution_fault',None) if env is not None else None)
        if fault is not None:
            details['execution_fault']=fault.to_mapping() if hasattr(fault,'to_mapping') else str(fault)
        details['errors'].append({'phase':'execute','type':type(error).__name__,'message':str(error)})
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        if env is not None:
            if recording_started:
                try:
                    remaining = deadline-time.perf_counter()
                    if remaining <= 0:raise TimeoutError('no budget remains for recording finalization')
                    signal.setitimer(signal.ITIMER_REAL,remaining)
                    reason = (details['episode'] or {}).get('failure_reason') or ('pass' if not details['errors'] else 'execution_error')
                    details['verification'] = env.finish_recording(reason)
                except Exception as error:
                    details['errors'].append({'phase':'finalize','type':type(error).__name__,'message':str(error)})
                finally:
                    signal.setitimer(signal.ITIMER_REAL,0)
            try:
                env.close()
            except Exception as error:
                details['errors'].append({'phase':'close','type':type(error).__name__,'message':str(error)})
        signal.signal(signal.SIGALRM,previous_handler)
        signal.setitimer(signal.ITIMER_REAL,*previous_timer)
    if h5.is_file():
        try:
            remaining = deadline-time.perf_counter()
            if remaining <= 0:raise TimeoutError('no budget remains for inspection')
            process = subprocess.run([sys.executable,str(Path(ctx['core_repo'])/'examples/recording/inspect_h5.py'),
                '--input',str(h5)],capture_output=True,text=True,timeout=min(30,remaining))
            (directory/'inspect.stdout.txt').write_text(process.stdout)
            (directory/'inspect.stderr.txt').write_text(process.stderr)
            summary = json.loads(process.stdout.strip().splitlines()[-1])
            save_json(summary,directory/'inspect.json')
            details['recording'] = summary
            details['h5'] = {'path':'oracle.h5','sha256':sha256(h5),'bytes':h5.stat().st_size}
            from task_env.trajectory.canonical.h5 import load
            trajectory = load(h5)
            metadata = trajectory.metadata.to_mapping()
            config = json.loads(metadata['source_provenance']['resolved_configuration_json'])
            for name,expected in {**config['source_sha256'],**details['tool_sha256']}.items():
                source = Path(ctx['core_repo'])/name if name.startswith('task_env/') else Path(__file__).parent/name
                if sha256(source)!=expected:raise ValueError(f'source changed during run: {name}')
                target=directory/'source_snapshot'/name
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
            checks = {
                'inspector_pass':process.returncode==0 and summary['status']=='PASS',
                't_plus_one':summary['t_plus_one_valid'],
                'roundtrip_exact':bool((details['verification'] or {}).get('logical_mapping_exact')),
                'artifact_identity':summary['task_artifact_sha256']==artifact_hash,
                'core_identity':summary['source_revision']==ctx['core_commit'],
                'spec_identity':config['spec_sha256']==spec.spec_sha256(),
                'controller_identity':summary['controller_identity']==details.get('controller_identity'),
                'expert_identity':summary['expert_identity']==details.get('expert_identity'),
                'episode_transition_count':summary['transitions']==(details['episode'] or {}).get('transitions'),
                'task_success_at_last_boundary':trajectory.boundaries[-1].is_success == bool((details['episode'] or {}).get('task_success')),
            }
            details['storage_identity_checks'] = checks
            if not all(checks.values()):
                raise ValueError(f'Oracle storage/identity checks failed: {checks}')
        except Exception as error:
            details['errors'].append({'phase':'inspect','type':type(error).__name__,'message':str(error)})
    elif not findings:
        details['errors'].append({'phase':'inspect','type':'MissingRecording','message':'no H5 was finalized'})
    for error in details['errors']:
        findings.append(CheckFinding('oracle_'+error['phase'],'execution_fault','unknown','',error,
            'successful recorded execution and storage checks',{'seed':seed}))
    passed = not findings and (details['episode'] or {}).get('status')=='PASS'
    status = 'pass' if passed else ('error' if details['errors'] else 'fail')
    details['wall_time_s'] = time.perf_counter()-started
    report = CheckReport(spec.spec_sha256(),artifact_hash,ctx['core_commit'],ctx['core_dirty'],
        'oracle_candidate',status,findings,details)
    report.save(directory/'oracle.check.json')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('core-repo','spec','catalog','output-dir'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--provider',default='mujoco')
    parser.add_argument('--seed',type=int,default=0)
    parser.add_argument('--time-limit-s',type=int,default=120)
    args=parser.parse_args()
    core_context(args.core_repo)
    report=record_candidate(CandidateSpec.load(args.spec),json.loads(args.catalog.read_text()),
        provider=args.provider,seed=args.seed,directory=args.output_dir,time_limit_s=args.time_limit_s)
    print(json.dumps({'status':report.status,'output':str(args.output_dir),'episode':report.details['episode'],
        'recording':report.details['recording'],'errors':report.details['errors']}))
    return {'pass':0,'fail':1,'error':2}[report.status]


if __name__=='__main__':
    raise SystemExit(main())
