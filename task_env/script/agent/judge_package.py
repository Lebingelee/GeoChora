"""Prepare/verify a portable Stage-1 candidate review package, never approve it."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import shutil
import sys
import yaml

from harness_spec_schema import CandidateSpec, CheckReport, save_json
from catalog_query import core_context
from completion_facts import validate_probe_report


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition,message):
    if not condition:
        raise ValueError(message)


def load_report(path,spec_hash,artifact_hash,core_commit,*,provider=None,expected_tool=None):
    report=CheckReport.from_dict(json.loads(Path(path).read_text()))
    require(report.status=='pass' and not report.findings,f'not passing: {path}')
    if expected_tool:require(report.tool==expected_tool,f'wrong check tool for {path}')
    require(report.spec_sha256==spec_hash,f'stale/cross-spec report: {path}')
    require(report.artifact_hash==artifact_hash or (report.tool=='asset_check' and report.artifact_hash is None),f'cross-artifact report: {path}')
    require(report.core_commit==core_commit and report.core_dirty is False,f'Core provenance mismatch: {path}')
    if provider and report.tool!='asset_check':
        require(report.details.get('provider')==provider,f'provider missing/mismatch: {path}')
    return report


def check_probe(report, *, expected_spec_sha256=None, expected_artifact_hash=None,
                expected_core_commit=None, expected_provider=None,
                expected_horizon=None):
    """Independently verify report context and every raw completion fact."""
    return validate_probe_report(report,
        expected_spec_sha256=expected_spec_sha256,
        expected_artifact_hash=expected_artifact_hash,
        expected_core_commit=expected_core_commit,
        expected_provider=expected_provider,
        expected_horizon=expected_horizon,
        require_passing=True)


def check_semantic(report,examples_path,artifact):
    require(report.details['examples_sha256']==digest(examples_path),'semantic examples changed since check')
    examples=json.loads(Path(examples_path).read_text())
    require(examples['goal_predicate']=='lift_height','unmapped source goal')
    source={c['name']:c for c in examples['cases']}
    require(len(source)==len(examples['cases']) and {c['expected_success'] for c in source.values()}=={False,True},'positive/negative endpoint set required')
    rows=report.details['cases'];require(len(rows)==len(source),'semantic case count mismatch')
    for row in rows:
        case=source[row['name']]
        actual=case['cube_world_z_m']-artifact.semantics.parameters_si['rest_height']>=artifact.semantics.parameters_si['lift_height']
        require(row['cube_world_z_m']==case['cube_world_z_m'] and row['expected']==case['expected_success']
            and row['actual']==actual==case['expected_success'],'semantic endpoint receipt mismatch')


def check_oracle(directory,spec_hash,artifact_hash,core_commit,provider):
    directory=Path(directory)
    report=load_report(directory/'oracle.check.json',spec_hash,artifact_hash,core_commit,provider=provider,expected_tool='oracle_candidate')
    d=report.details;e=d['episode']
    require(e['status']=='PASS' and e['task_success'] is True and e['solution_done'] is True
        and e['solution_failed'] is False and e['task_failure'] is False
        and e['terminated'] is False and e['truncated'] is False,'Oracle completion failed')
    require(not d['errors'] and not d.get('execution_fault'),'Oracle has execution errors')
    require(d['verification'].get('logical_mapping_exact') is True,'Oracle roundtrip missing')
    require(d['h5']['sha256']==digest(directory/'oracle.h5'),'Oracle H5 bytes changed')
    from examples._common import load_recording_summary
    actual=load_recording_summary(directory/'oracle.h5')
    for key in ('task_artifact_sha256','source_revision','transitions','boundaries','controller_identity','expert_identity'):
        require(actual[key]==d['recording'][key],f'Oracle inspected {key} mismatch')
    require(actual['task_artifact_sha256']==artifact_hash and actual['source_revision']==core_commit,'Oracle identity mismatch')
    require(actual['t_plus_one_valid'] and actual['transitions']==e['transitions'],'Oracle T+1/count mismatch')
    from task_env.trajectory.canonical.h5 import load
    trajectory=load(directory/'oracle.h5')
    require(trajectory.metadata.task_seed==d['seed'],'Oracle seed mismatch')
    require(trajectory.metadata.execution.physics_provider==provider,'Oracle provider mismatch')
    config=json.loads(trajectory.metadata.source_provenance['resolved_configuration_json'])
    require(config['spec_sha256']==spec_hash,'Oracle embedded spec mismatch')
    require(trajectory.boundaries[-1].is_success is True,'Oracle final physical success missing')
    for name,expected in {**config['source_sha256'],**d['tool_sha256']}.items():
        source=directory/'source_snapshot'/name
        require(source.is_file() and digest(source)==expected,f'Oracle source snapshot changed: {name}')
    inspector=json.loads((directory/'inspect.json').read_text())
    require(inspector==d['recording'],'Oracle inspector receipt differs')
    return report


def diagnostic_bindings(log,spec_paths=()):
    """Bind legacy and current diagnostic receipts to the actual hashed specs."""
    from construction_ledger import read_ref,file_ref
    by_hash={CandidateSpec.load(p).spec_sha256():file_ref(p) for p in spec_paths}
    result=[]
    for round_ in log['rounds']:
        revision=round_.get('revision') or {}
        for item in revision.get('diagnostics',[]):
            report_ref=item.get('report',item)
            report=CheckReport.from_dict(read_ref(report_ref))
            spec_ref=item.get('spec') or by_hash.get(report.spec_sha256)
            require(spec_ref is not None,'diagnostic spec missing; bind legacy runs with --diagnostic-specs')
            spec=CandidateSpec.from_dict(read_ref(spec_ref))
            require(spec.spec_sha256()==report.spec_sha256,'diagnostic spec/report mismatch')
            require(spec.task_id==log['task_id'],'cross-task diagnostic')
            require(report.tool=='feasibility_probe' and report.details.get('complete') is True,'incomplete diagnostic')
            require(report.core_commit==log['core_commit'] and report.core_dirty is False,'diagnostic Core mismatch')
            require(report.details.get('provider')==log['provider'],'diagnostic provider mismatch')
            result.append({'report':report_ref,'spec':spec_ref})
    return result


def prepare(*,core_repo,validation_dir,construction_log,oracle_dirs,upstream_dir,output,historical_archive=None,diagnostic_specs=()):
    ctx=core_context(core_repo)
    require(ctx['core_dirty'] is False,'clean Core snapshot required')
    v=Path(validation_dir).resolve();u=Path(upstream_dir).resolve();logpath=Path(construction_log).resolve()
    spec=CandidateSpec.load(v/'candidate.spec.json')
    from task_env.artifacts import decode_task_artifact
    artifact=decode_task_artifact(json.loads((v/'candidate.artifact.json').read_text()))
    sh,ah=spec.spec_sha256(),artifact.identity_hash
    compile_report=load_report(v/'compile.json',sh,ah,ctx['core_commit'],provider=None,expected_tool='harness_compiler')
    provider=compile_report.details['provider']
    require(compile_report.details['artifact']==artifact.to_mapping(),'compile artifact differs')
    for name in ('assets','semantic','feasibility'):
        r=load_report(v/f'{name}.json',sh,ah,ctx['core_commit'],provider=provider,
            expected_tool={'assets':'asset_check','semantic':'semantic_check','feasibility':'feasibility_probe'}[name])
        if name=='feasibility':
            check_probe(r, expected_spec_sha256=sh, expected_artifact_hash=ah,
                expected_core_commit=ctx['core_commit'], expected_provider=provider,
                expected_horizon=spec.horizon)
        if name=='semantic':check_semantic(r,u/'semantic_examples.json',artifact)
    oracle_reports=[check_oracle(d,sh,ah,ctx['core_commit'],provider) for d in oracle_dirs]
    require(bool(oracle_reports),'at least one passing Oracle recording required')
    log=json.loads(logpath.read_text());last=log['rounds'][-1]
    require(last['spec_sha256']==sh and last['artifact_hash']==ah,'construction log final candidate mismatch')
    if log.get('schema_version')=='harness-attempt-ledger-v0':
        require(log['state']=='candidate_ready' and last['status']=='pass','construction is not candidate_ready')
    diagnostics=diagnostic_bindings(log,diagnostic_specs)
    require(log.get('judge_decision') is None,'refuse to repackage a decided artifact')
    upstream_hash=log.get('upstream_sha256') or log.get('refs',{}).get('task',{}).get('sha256')
    bundle_hash=log.get('asset_bundle_sha256') or log.get('refs',{}).get('asset_bundle',{}).get('sha256')
    require(upstream_hash==digest(u/'task.json'),'upstream task changed since construction')
    require(bundle_hash==digest(u/'asset_bundle.json'),'asset bundle changed since construction')
    bundle=json.loads((u/'asset_bundle.json').read_text())
    asset=next(a for a in bundle['assets'] if a['uid']==spec.object_config['object_uid'])
    require(bundle.get('synthetic') is True and digest(u/asset['path'])==asset['sha256']==spec.object_config['asset_sha256'],
        'asset bytes/bundle/spec hash mismatch')
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    relocation={}
    def copy_file(source,dest):
        source=Path(source).resolve();dest=output/dest
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
        relocation[str(source)]=str(dest.relative_to(output))
    def copy_tree(source,dest):
        for path in sorted(Path(source).rglob('*')):
            if path.is_file():copy_file(path,Path(dest)/path.relative_to(source))
    copy_file(v/'candidate.spec.json','candidate.spec.json')
    copy_file(v/'candidate.artifact.json','artifact.json')
    copy_tree(v,'validation/current')
    copy_tree(u,'local_assets')
    copy_file(logpath,'validation/history/construction_log.json')
    if 'evidence_directory' in log:copy_tree(Path(log['evidence_directory']),'validation/history/rounds')
    elif log.get('schema_version')=='harness-attempt-ledger-v0':
        from construction_ledger import load
        load(logpath)
        def collect(value):
            if isinstance(value,dict):
                if set(value)=={'path','sha256'}:
                    copy_file(value['path'],f"validation/history/refs/{value['sha256']}/{Path(value['path']).name}")
                else:
                    for child in value.values():collect(child)
            elif isinstance(value,list):
                for child in value:collect(child)
        collect(log)
    portable_diagnostics=[]
    for i,pair in enumerate(diagnostics):
        entry={}
        for kind,ref in pair.items():
            dest=f'validation/history/diagnostics/{i}/{kind}.json'
            copy_file(ref['path'],dest)
            entry[kind]={'path':dest,'sha256':ref['sha256']}
        portable_diagnostics.append(entry)
    save_json(portable_diagnostics,output/'validation/history/diagnostics.json')
    for i,d in enumerate(oracle_dirs):copy_tree(Path(d),f'validation/oracle-{i}')
    for path in sorted(Path(__file__).parent.glob('*.py')):
        if not path.name.startswith('test_'):copy_file(path,'validation/tool_snapshot/'+path.name)
    if historical_archive:copy_file(historical_archive,'validation/history/original_delivery.zip')
    manifest={'task_id':spec.task_id,'artifact_id':artifact.artifact_id,'artifact_version':artifact.artifact_version,
        'artifact_hash':ah,'spec_sha256':sh,'lifecycle':'candidate','stage':1,'core_commit':ctx['core_commit'],
        'core_dirty':False,'provider':provider,'backend':'cpu','synthetic_upstream':True,
        'original_request_uid':asset.get('source_request_uid'),'asset_uid':asset['uid'],'asset_sha256':asset['sha256'],
        'validation_ref':'validation/current','construction_ref':'validation/history/construction_log.json',
        'evidence_ref':'validation/evidence.json','judge_decision_ref':'judge_decision.yaml',
        'video':{'status':'NOT_RECORDED','reason':'selected route has no supported render configuration'},
        'qualification':'NOT_ASSESSED','D0':'NOT_ASSESSED','D1':'NOT_ASSESSED','D2':'NOT_ASSESSED',
        'open_issues':log.get('open_issues',[]),
        'scope':'synthetic lift candidate; no LIBERO equivalence, freeze, training readiness or replay qualification'}
    (output/'manifest.yaml').write_text(yaml.safe_dump(manifest,allow_unicode=True,sort_keys=False))
    rows='\n'.join(f"| {r.details['seed']} | {r.details['episode']['transitions']} | {r.details['recording']['boundaries']} | PASS |" for r in oracle_reports)
    (output/'validation/report.md').write_text(f'''# Stage-1 Candidate review facts

Task: `{spec.task_id}`. Lifecycle: candidate. Human decision: pending.

Spec: `{sh}`. Artifact: `{ah}`. Core: `{ctx['core_commit']}` (clean).

Current assets/compile/semantic checks pass. Feasibility: 20 or more declared distinct seeds, all solved; see current/feasibility.json for exact sample set.
Physics execution: real {provider} CPU. Upstream assets and semantic endpoints: explicitly synthetic.

| Oracle seed | Transitions | Boundaries | Completion + storage |
|---|---|---|---|
{rows}

Existing selected recorder performs exact logical save/load comparison. Core inspector separately validates H5/T+1.
Expert completion, physical task success and termination flags are retained independently in each oracle.check.json.

## Review gaps and limits

- Review open_issues in manifest.yaml and the full construction history; a later passing candidate does not resolve earlier execution faults.
- Lift surrogate and box-collision proxy do not establish LIBERO In/On equivalence.
- No supported selected-route camera video; no video is claimed. H5 and checks are available for review.
- ReferenceTaskBinding is still an internal extension pending maintainer confirmation.
- No D0/D1/D2, replay qualification, Human approval, freeze, or training-ready dataset.
- Historical bytes are preserved under history; their absolute refs are relocated by evidence.json.

This package follows Core's existing task-env-experiment-evidence procedure. It is Stage 1, not an Experiment of a frozen artifact.
''')
    files=[{'path':str(p.relative_to(output)),'sha256':digest(p),'bytes':p.stat().st_size}
        for p in sorted(output.rglob('*')) if p.is_file()]
    evidence={'schema_version':'harness-stage1-evidence-index-v0','created_at':datetime.now(timezone.utc).isoformat(),
        'spec_sha256':sh,'artifact_hash':ah,'core_commit':ctx['core_commit'],'files':files,'relocations':relocation,
        'judge':{'path':'judge_decision.yaml','status':'pending','mutable_decision_excluded_from_digest':True}}
    save_json(evidence,output/'validation/evidence.json')
    judge={'stage':1,'decision':'pending','judge_type':'human','judge_identity':None,'decided_at':None,
        'task_id':spec.task_id,'artifact_version':artifact.artifact_version,'artifact_hash':ah,'spec_sha256':sh,
        'basis':{'evidence_manifest':'validation/evidence.json','evidence_manifest_sha256':digest(output/'validation/evidence.json')},
        'reasons':[],'required_changes':[],'quality_notes':[]}
    (output/'judge_decision.yaml').write_text(yaml.safe_dump(judge,allow_unicode=True,sort_keys=False))
    return verify(output,core_repo=core_repo)


def verify(directory,*,core_repo):
    ctx=core_context(core_repo)
    root=Path(directory).resolve();index=root/'validation/evidence.json'
    data=json.loads(index.read_text());seen=set()
    require(data.get('core_commit')==ctx['core_commit'] and ctx['core_dirty'] is False,
            'pending package requires the same clean Core commit')
    require(data.get('schema_version')=='harness-stage1-evidence-index-v0','unknown evidence index')
    for item in data['files']:
        path=(root/item['path']).resolve()
        require(path.is_relative_to(root) and item['path'] not in seen,'unsafe/duplicate evidence ref')
        seen.add(item['path'])
        require(path.is_file(),f'missing evidence: {item["path"]}')
        require(path.stat().st_size==item['bytes'] and digest(path)==item['sha256'],f'evidence changed: {item["path"]}')
    required={'candidate.spec.json','artifact.json','manifest.yaml','validation/current/compile.json',
        'validation/current/assets.json','validation/current/semantic.json','validation/current/feasibility.json',
        'validation/history/construction_log.json','local_assets/task.json','local_assets/asset_bundle.json',
        'local_assets/semantic_examples.json','validation/report.md'}
    require(required<=seen,'required candidate evidence missing from index')
    actual_files={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    require(actual_files==seen|{'validation/evidence.json','judge_decision.yaml'},'unindexed or missing package files')
    spec=CandidateSpec.load(root/'candidate.spec.json')
    from task_env.artifacts import decode_task_artifact
    artifact=decode_task_artifact(json.loads((root/'artifact.json').read_text()))
    require(spec.spec_sha256()==data['spec_sha256'] and artifact.identity_hash==data['artifact_hash'],'package identity mismatch')
    manifest=yaml.safe_load((root/'manifest.yaml').read_text())
    require(manifest['lifecycle']=='candidate' and manifest['core_dirty'] is False,'invalid lifecycle/Core identity')
    require(manifest['spec_sha256']==data['spec_sha256'] and manifest['artifact_hash']==data['artifact_hash']
        and manifest['core_commit']==data['core_commit'] and manifest['task_id']==spec.task_id,'manifest identity mismatch')
    provider=manifest['provider']
    history=json.loads((root/'validation/history/construction_log.json').read_text())
    expected_diagnostics=sum(len((r.get('revision') or {}).get('diagnostics',[])) for r in history['rounds'])
    diagnostic_index=root/'validation/history/diagnostics.json'
    require(diagnostic_index.is_file() or not expected_diagnostics,'portable diagnostic evidence missing')
    diagnostic_rows=json.loads(diagnostic_index.read_text()) if diagnostic_index.is_file() else []
    require(len(diagnostic_rows)==expected_diagnostics,'diagnostic count mismatch')
    for pair in diagnostic_rows:
        for ref in pair.values():
            require(ref['path'] in seen and digest(root/ref['path'])==ref['sha256'],'diagnostic index mismatch')
        ds=CandidateSpec.load(root/pair['spec']['path'])
        dr=CheckReport.from_dict(json.loads((root/pair['report']['path']).read_text()))
        require(ds.spec_sha256()==dr.spec_sha256 and ds.task_id==spec.task_id,'diagnostic spec/report identity mismatch')
        require(dr.core_commit==data['core_commit'] and not dr.core_dirty and dr.details.get('provider')==provider,
            'diagnostic execution identity mismatch')
    for name,tool in {'compile':'harness_compiler','assets':'asset_check','semantic':'semantic_check','feasibility':'feasibility_probe'}.items():
        r=load_report(root/f'validation/current/{name}.json',data['spec_sha256'],data['artifact_hash'],data['core_commit'],provider=provider,expected_tool=tool)
        if name=='feasibility':
            check_probe(r, expected_spec_sha256=data['spec_sha256'],
                expected_artifact_hash=data['artifact_hash'],
                expected_core_commit=data['core_commit'], expected_provider=provider,
                expected_horizon=spec.horizon)
        if name=='semantic':check_semantic(r,root/'local_assets/semantic_examples.json',artifact)
    oracle_dirs=sorted((root/'validation').glob('oracle-*'))
    require(bool(oracle_dirs),'Oracle evidence missing')
    for directory in oracle_dirs:
        for name in ('oracle.check.json','oracle.h5','inspect.json'):
            require(str((directory/name).relative_to(root)) in seen,'unindexed Oracle evidence')
        check_oracle(directory,data['spec_sha256'],data['artifact_hash'],data['core_commit'],provider)
    judge=yaml.safe_load((root/'judge_decision.yaml').read_text())
    require(judge['decision']=='pending' and judge['judge_identity'] is None and judge['decided_at'] is None,
        'this verifier covers pending packages only; human decisions require separate review')
    require(judge['basis']['evidence_manifest_sha256']==digest(index),'Judge evidence basis changed')
    require(judge['artifact_hash']==artifact.identity_hash and judge['spec_sha256']==spec.spec_sha256(),'Judge candidate mismatch')
    return {'status':'pass','files_verified':len(seen),'spec_sha256':spec.spec_sha256(),
        'artifact_hash':artifact.identity_hash,'decision':'pending','qualification':'NOT_ASSESSED'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--core-repo',type=Path,required=True)
    subs=p.add_subparsers(dest='command',required=True)
    a=subs.add_parser('prepare')
    for name in ('validation-dir','construction-log','upstream-dir','output'):a.add_argument('--'+name,type=Path,required=True)
    a.add_argument('--oracle-dirs',type=Path,nargs='+',required=True);a.add_argument('--historical-archive',type=Path)
    a.add_argument('--diagnostic-specs',type=Path,nargs='*',default=[])
    b=subs.add_parser('verify');b.add_argument('--directory',type=Path,required=True)
    args=vars(p.parse_args());command=args.pop('command')
    try:result=prepare(**args) if command=='prepare' else verify(**args)
    except Exception as error:
        print(json.dumps({'status':'error','error':f'{type(error).__name__}: {error}'}));return 2
    print(json.dumps(result));return 0


if __name__=='__main__':raise SystemExit(main())
