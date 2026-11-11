"""Prepare/verify a portable Stage-1 candidate review package, never approve it."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import shutil
import sys
import subprocess
import yaml

from harness_spec_schema import CandidateSpec, CheckReport, save_json
from catalog_query import core_context
from completion_facts import validate_probe_report
from provider_routes import backend_for, device_for


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
    require(d['h5']['sha256']==digest(directory/'oracle.h5'),'Oracle H5 bytes changed')
    from examples._common import load_recording_summary
    actual=load_recording_summary(directory/'oracle.h5')
    for key in ('task_artifact_sha256','source_revision','transitions','boundaries','controller_identity','expert_identity'):
        require(actual[key]==d['recording'][key],f'Oracle inspected {key} mismatch')
    require(actual['task_artifact_sha256']==artifact_hash,'Oracle artifact identity mismatch')
    require(actual['t_plus_one_valid'] and actual['transitions']==e['transitions'],'Oracle T+1/count mismatch')
    if actual.get('schema') == 'task-env-h5/v3':
        check_v3_oracle(directory, d, actual, spec_hash, artifact_hash, core_commit, provider)
    else:
        require(d['verification'].get('logical_mapping_exact') is True,'Oracle roundtrip missing')
        require(actual['source_revision']==core_commit,'Oracle source revision mismatch')
        from task_env.trajectory.canonical.h5 import load
        trajectory=load(directory/'oracle.h5')
        require(trajectory.metadata.task_seed==d['seed'],'Oracle seed mismatch')
        require(trajectory.metadata.execution.physics_provider==provider,'Oracle provider mismatch')
        config=json.loads(trajectory.metadata.source_provenance['resolved_configuration_json'])
        require(config['spec_sha256']==spec_hash,'Oracle embedded spec mismatch')
        require(trajectory.boundaries[-1].is_success is True,'Oracle final physical success missing')
        check_source_snapshots(directory,{**config['source_sha256'],**d['tool_sha256']})
    inspector=json.loads((directory/'inspect.json').read_text())
    require(inspector==d['recording'],'Oracle inspector receipt differs')
    return report


def check_source_snapshots(directory, expected):
    for name, sha in expected.items():
        relative=Path(name)
        require(not relative.is_absolute() and '..' not in relative.parts,'unsafe Oracle source path')
        source=Path(directory)/'source_snapshot'/relative
        require(source.is_file() and digest(source)==sha,f'Oracle source snapshot changed: {name}')


def check_v3_oracle(directory, details, summary, spec_hash, artifact_hash, core_commit, provider):
    """Validate actual v3 records and native receipts without claiming canonical equality."""
    from task_env.recorders import load_structured_control_records_h5
    records=load_structured_control_records_h5(Path(directory)/'oracle.h5')
    worker=json.loads((Path(directory)/'native/worker_receipt.json').read_text())
    native=json.loads((Path(directory)/'native/native_run_receipt.json').read_text())
    facts=worker.get('facts') or {}
    compiled=worker.get('compiled') or {}
    identity=facts.get('recording_identity') or {}
    profile=records['env_meta']['reference_profile']
    check_v3_recorded_provenance(directory,profile,details,compiled,spec_hash,core_commit)
    require(worker.get('mode')=='oracle' and worker.get('provider')==provider
        and worker.get('seed')==details['seed']==identity.get('seed'), 'Oracle native seed/provider mismatch')
    require(worker.get('core_commit')==core_commit and worker.get('core_dirty') is False
        and not worker.get('errors') and worker.get('exit_code')==0,'Oracle worker provenance/exit mismatch')
    require(compiled.get('spec_sha256')==spec_hash and compiled.get('artifact_hash')==artifact_hash
        and compiled.get('source_revision')==core_commit,'Oracle compiled identity mismatch')
    require(details.get('worker')=={key:worker.get(key) for key in
        ('core_commit','core_dirty','compiled','app','errors')},'Oracle embedded worker receipt mismatch')
    require(details.get('native_run')==native and native.get('status')=='COMPLETED'
        and native.get('returncode')==0 and native.get('process_group_retired') is True
        and native.get('mode')=='oracle' and native.get('seed')==details['seed']
        and native.get('provider')==provider,'Oracle native close/retirement mismatch')
    close=(worker.get('app') or {}).get('close_receipt') or {}
    require(close.get('close_completed') is True and close.get('closed') is True
        and not close.get('close_failure'),'Oracle App close missing')
    require(facts.get('close_attempted') is True and facts.get('close_succeeded') is True
        and not facts.get('errors') and not facts.get('execution_fault'),'Oracle environment close failed')
    for key in ('episode','verification','controller_identity','expert_identity'):
        require(facts.get(key)==details.get(key),f'Oracle worker {key} mismatch')
    expected=identity.get('profile') or {}
    for key in ('execution_identity_sha256','reset_plan_identity_hash','reset_sample_id',
                'source_id','source_closure_digest','delivery_manifest_sha256','provider','backend','device'):
        require(bool(expected.get(key)) and profile.get(key)==expected[key],f'Oracle recorded {key} mismatch')
    require(profile.get('provider')==provider and profile.get('backend')==backend_for(provider)
        and profile.get('device')==device_for(provider),'Oracle recorded execution mismatch')
    require(profile.get('controller_identity')==details['controller_identity']
        and compiled.get('controller_identity')==details['controller_identity']
        and compiled.get('solution_identity')==details['expert_identity'],'Oracle controller/expert mismatch')
    verification=details.get('verification') or {}
    require(records['transition_count']==details['episode']['transitions']==verification.get('transition_count')
        and records['observation_count']==summary['boundaries']==verification.get('observation_count'),
        'Oracle structured T/T+1 mismatch')
    require(records['outcome'].to_mapping()==verification.get('outcome')
        and records['outcome'].task_success is True,'Oracle recorded outcome mismatch')
    expected_sources={**compiled.get('source_sha256',{}),**details['tool_sha256']}
    identity_only=details.get('source_identity_only') or {}
    require(all(expected_sources.get(name)==sha for name,sha in identity_only.items())
        and set(identity_only)<={'f06_delivery_manifest_sha256','f06_delivery_source_entry_sha256'},'Oracle source-only digest mismatch')
    check_source_snapshots(directory,{name:sha for name,sha in expected_sources.items()
                                      if name not in identity_only})
    require(compiled.get('source_closure_sha256')==profile.get('source_closure_digest')
        and compiled.get('source_sha256',{}).get('f06_delivery_manifest_sha256')
            ==profile.get('delivery_manifest_sha256'),'Oracle source closure/delivery mismatch')
    from task_env.tasks.pick_cube.isaac import ISAAC_ADMITTED_DELIVERIES_V1
    require(profile.get('delivery_manifest_sha256') in ISAAC_ADMITTED_DELIVERIES_V1,
        'Oracle recorded delivery differs from Core pin')
    checks=details.get('storage_identity_checks') or {}
    expected_checks={'inspector_pass','t_plus_one','artifact_identity','controller_identity','expert_identity',
        'episode_transition_count','requested_seed','provider_provenance','source_provenance',
        'core_identity','spec_identity','worker_artifact_identity','roundtrip_readback',
        *('recorded_'+key for key in ('execution_identity_sha256','reset_plan_identity_hash',
            'reset_sample_id','source_id','source_closure_digest','delivery_manifest_sha256',
            'provider','backend','device'))}
    require(set(checks)==expected_checks and all(value is True for value in checks.values()),
        'Oracle storage checks missing/failed')
    require(summary.get('storage_roundtrip')=='PASS' and summary.get('provider_provenance_present') is True
        and summary.get('source_provenance_present') is True,'Oracle v3 readback/provenance missing')


def check_v3_recorded_provenance(directory, profile, details, compiled, spec_hash, core_commit):
    """Bind receipts to immutable H5 declarations and Git source bytes."""
    from task_env.artifacts import ExecutionSpecV1
    from task_env.artifacts.execution import EpisodeResetPlanV1
    require(profile.get('recording_provenance_schema')=='pickcube-isaac-replay-provenance-v1',
        'Oracle v3 recorded replay provenance missing; regenerate this historical recording')
    plan=EpisodeResetPlanV1.from_mapping(profile['reset_plan_v1'])
    execution=ExecutionSpecV1.from_mapping(profile['execution_spec_v1'])
    require(type(details['seed']) is int and details['seed']>=0
        and profile.get('task_seed')==details['seed']==plan.reset_sample.task_seed
        ==execution.provider_seed,'Oracle recorded task seed mismatch')
    require(plan.identity_hash==profile.get('reset_plan_identity_hash')
        and plan.reset_sample.sample_id==profile.get('reset_sample_id')
        and plan.reset_sample.task_artifact_hash==compiled.get('artifact_hash')
        and plan.role_binding.scene_identity_hash==profile.get('scene_identity_hash'),
        'Oracle recorded reset plan identity mismatch')
    require(execution.identity_hash==profile.get('execution_identity_sha256')
        and execution.physics_provider==profile.get('provider')
        and execution.physics_backend==profile.get('backend')
        and execution.physics_device==profile.get('device'), 'Oracle recorded ExecutionSpec mismatch')
    require(profile.get('source_revision')==core_commit,'Oracle recorded Core revision mismatch')
    require(profile.get('source_sha256')==compiled.get('source_sha256'),
        'Oracle recorded source snapshot identity mismatch')
    spec=CandidateSpec.load(Path(directory)/'candidate.spec.json')
    require(spec.spec_sha256()==spec_hash,'Oracle recorded candidate spec mismatch')
    overlay=(compiled.get('route') or {}).get('harness_task_config_recipe_overlay') or {}
    recipe=(profile.get('task_recipe') or {}).get('recipe') or {}
    require(overlay.get('artifact_id')==recipe.get('artifact_id')
        and recipe.get('artifact_id','').endswith('/spec-'+spec_hash)
        and all(recipe.get(key)==overlay.get(key) for key in ('reset','success')),
        'Oracle recorded task recipe mismatch')
    repo=Path(__file__).resolve().parents[3]
    for name,sha in {**profile['source_sha256'],**details['tool_sha256']}.items():
        if name in ('f06_delivery_manifest_sha256','f06_delivery_source_entry_sha256'):
            continue
        path=Path(name)
        require(not path.is_absolute() and '..' not in path.parts,'unsafe Oracle Git source path')
        relative=name if '/' in name else 'task_env/script/agent/'+name
        result=subprocess.run(['git','-C',str(repo),'show',core_commit+':'+relative],
            capture_output=True,check=False)
        require(result.returncode==0 and hashlib.sha256(result.stdout).hexdigest()==sha,
            f'Oracle source bytes differ from recorded Core commit: {name}')


def check_asset_binding(spec, upstream, provider):
    """Preserve synthetic input; separately admit the exact Core-pinned built-in USD."""
    upstream=Path(upstream).resolve()
    bundle=json.loads((upstream/'asset_bundle.json').read_text())
    matches=[asset for asset in bundle.get('assets',[]) if asset.get('uid')==spec.object_config['object_uid']]
    require(len(matches)==1,'candidate object missing or ambiguous in upstream asset binding')
    asset=matches[0]
    if bundle.get('schema_version')=='harness-builtin-source-bundle-v1':
        from task_env.tasks.pick_cube.isaac import ISAAC_ADMITTED_DELIVERIES_V1
        from task_env.assembly.usd_delivery import load_usd_asset_delivery
        require(provider=='isaacsim' and asset.get('uid')=='cube-v1'
            and asset.get('source_kind')=='core-builtin-pinned-usd'
            and bundle.get('synthetic') is False and 'asset_sha256' not in spec.object_config,
            'unsupported built-in source binding')
        path=(upstream/asset['delivery_manifest']).resolve()
        require(path.is_relative_to(upstream) and digest(path)==asset.get('sha256')
            and asset.get('sha256') in ISAAC_ADMITTED_DELIVERIES_V1,'built-in USD delivery pin mismatch')
        loaded=load_usd_asset_delivery(path)
        require(loaded.locally_validated and not loaded.source_verified,'built-in delivery provenance mismatch')
        return {'kind':'core-builtin-pinned-usd','asset_uid':asset['uid'],'asset_sha256':asset['sha256'],
            'synthetic':False,'original_request_uid':None,'source_verified':False,
            'provenance_kind':loaded.delivery.provenance_kind,'source_closure_sha256':loaded.closure_sha256}
    path=(upstream/asset['path']).resolve()
    require(path.is_relative_to(upstream),'asset escapes upstream directory')
    require(bundle.get('synthetic') is True and digest(path)==asset['sha256']==spec.object_config.get('asset_sha256'),
        'asset bytes/bundle/spec hash mismatch')
    return {'kind':'synthetic-box-proxy','asset_uid':asset['uid'],'asset_sha256':asset['sha256'],
        'synthetic':True,'original_request_uid':asset.get('source_request_uid')}


def diagnostic_bindings(log,spec_paths=()):
    """Bind legacy and current diagnostic receipts to the actual hashed specs."""
    from construction_ledger import read_ref,file_ref
    by_hash={CandidateSpec.load(p).spec_sha256():file_ref(p) for p in spec_paths}
    result=[]
    for round_ in log['rounds']:
        revision=round_.get('revision') or {}
        round_core=(round_.get('context') or {}).get('core_commit',log['core_commit'])
        for item in revision.get('diagnostics',[]):
            report_ref=item.get('report',item)
            report=CheckReport.from_dict(read_ref(report_ref))
            spec_ref=item.get('spec') or by_hash.get(report.spec_sha256)
            require(spec_ref is not None,'diagnostic spec missing; bind legacy runs with --diagnostic-specs')
            spec=CandidateSpec.from_dict(read_ref(spec_ref))
            require(spec.spec_sha256()==report.spec_sha256,'diagnostic spec/report mismatch')
            require(spec.task_id==log['task_id'],'cross-task diagnostic')
            require(report.tool=='feasibility_probe' and report.details.get('complete') is True,'incomplete diagnostic')
            require(report.core_commit==round_core and report.core_dirty is False,'diagnostic Core mismatch')
            require(report.details.get('provider')==log['provider'],'diagnostic provider mismatch')
            result.append({'report':report_ref,'spec':spec_ref,'core_commit':round_core})
    return result


def owner_repair_bundle(log, output, copy_file):
    """Copy owner-level diagnosis and repair provenance into the pending package."""
    from construction_ledger import read_ref
    ref=log.get('owner_repair_ref')
    if not ref:
        for round_ in log.get('rounds',[]):
            revision=round_.get('revision') or {}
            if revision.get('kind')=='owner_repair':ref=revision.get('repair_receipt')
    if not ref:return None
    receipt=read_ref(ref)
    receipt_dest='validation/history/owner_repair/receipt.json'
    copy_file(ref['path'],receipt_dest)
    diagnostics=[]
    for index,item in enumerate(receipt.get('diagnostic_refs',[])):
        dest=f'validation/history/owner_repair/diagnostics/{index:02d}_{item["label"]}{Path(item["ref"]["path"]).suffix}'
        copy_file(item['ref']['path'],dest)
        diagnostics.append({'label':item['label'],'path':dest,'sha256':item['ref']['sha256']})
    source_diff=receipt.get('source_diff_ref')
    diff_dest=None
    if source_diff:
        diff_dest='validation/history/owner_repair/source.diff'
        copy_file(source_diff['path'],diff_dest)
    index={'receipt_path':receipt_dest,'receipt_sha256':ref['sha256'],
        'diagnostics':diagnostics,'source_diff_path':diff_dest}
    return index


def round_history(log):
    return [{'number':r['number'],'status':r['status'],'spec_sha256':r['spec_sha256'],
        'core_commit':(r.get('context') or {}).get('core_commit',log['core_commit']),
        'artifact_hash':r.get('artifact_hash'),
        'finding_keys':r.get('finding_keys',[])} for r in log.get('rounds',[])]


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
    from construction_ledger import load as load_ledger
    log=load_ledger(logpath);last=log['rounds'][-1]
    require(last['spec_sha256']==sh and last['artifact_hash']==ah,'construction log final candidate mismatch')
    final_context=last.get('context') or {'core_commit':log['core_commit']}
    require(ctx['core_commit']==final_context['core_commit'],
        'current Core differs from final construction round context')
    require(log['state']=='candidate_ready' and last['status']=='pass','construction is not candidate_ready')
    diagnostics=diagnostic_bindings(log,diagnostic_specs)
    require(log.get('judge_decision') is None,'refuse to repackage a decided artifact')
    current_inputs=final_context.get('input_refs',log.get('refs',{}))
    upstream_hash=current_inputs.get('task',{}).get('sha256')
    bundle_hash=current_inputs.get('asset_bundle',{}).get('sha256')
    require(upstream_hash==digest(u/'task.json'),'upstream task changed since construction')
    require(bundle_hash==digest(u/'asset_bundle.json'),'asset bundle changed since construction')
    binding=check_asset_binding(spec,u,provider)
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
    else:
        def collect(value):
            if isinstance(value,dict):
                if set(value)=={'path','sha256'}:
                    copy_file(value['path'],f"validation/history/refs/{value['sha256']}/{Path(value['path']).name}")
                else:
                    for child in value.values():collect(child)
            elif isinstance(value,list):
                for child in value:collect(child)
        collect(log)
    repair_index=owner_repair_bundle(log,output,copy_file)
    history=round_history(log)
    save_json(history,output/'validation/history/rounds.json')
    portable_diagnostics=[]
    for i,pair in enumerate(diagnostics):
        entry={}
        for kind in ('report','spec'):
            ref=pair[kind]
            dest=f'validation/history/diagnostics/{i}/{kind}.json'
            copy_file(ref['path'],dest)
            entry[kind]={'path':dest,'sha256':ref['sha256']}
        entry['core_commit']=pair['core_commit']
        portable_diagnostics.append(entry)
    save_json(portable_diagnostics,output/'validation/history/diagnostics.json')
    for i,d in enumerate(oracle_dirs):copy_tree(Path(d),f'validation/oracle-{i}')
    for path in sorted(Path(__file__).parent.glob('*.py')):
        if not path.name.startswith('test_'):copy_file(path,'validation/tool_snapshot/'+path.name)
    if historical_archive:copy_file(historical_archive,'validation/history/original_delivery.zip')
    manifest={'task_id':spec.task_id,'artifact_id':artifact.artifact_id,'artifact_version':artifact.artifact_version,
        'artifact_hash':ah,'spec_sha256':sh,'lifecycle':'candidate','stage':1,'core_commit':ctx['core_commit'],
        'core_dirty':False,'provider':provider,'backend':backend_for(provider),'device':device_for(provider),'synthetic_upstream':binding['synthetic'],
        'original_request_uid':binding['original_request_uid'],'asset_uid':binding['asset_uid'],
        'asset_sha256':binding['asset_sha256'],'asset_binding':binding,
        'validation_ref':'validation/current','construction_ref':'validation/history/construction_log.json',
        'evidence_ref':'validation/evidence.json','judge_decision_ref':'judge_decision.yaml',
        'video':{'status':'NOT_RECORDED','reason':'selected route has no supported render configuration'},
        'qualification':'NOT_ASSESSED','D0':'NOT_ASSESSED','D1':'NOT_ASSESSED','D2':'NOT_ASSESSED',
        'open_issues':log.get('open_issues',[]),
        'construction_rounds':history,'owner_repair_evidence':repair_index,
        'scope':'bounded lift candidate; no LIBERO equivalence, freeze, training readiness or replay qualification'}
    (output/'manifest.yaml').write_text(yaml.safe_dump(manifest,allow_unicode=True,sort_keys=False))
    rows='\n'.join(f"| {r.details['seed']} | {r.details['episode']['transitions']} | {r.details['recording']['boundaries']} | PASS |" for r in oracle_reports)
    (output/'validation/report.md').write_text(f'''# Stage-1 Candidate review facts

Task: `{spec.task_id}`. Lifecycle: candidate. Human decision: pending.

Spec: `{sh}`. Artifact: `{ah}`. Core: `{ctx['core_commit']}` (clean).

Current assets/compile/semantic checks pass. Feasibility: 20 or more declared distinct seeds, all solved; see current/feasibility.json for exact sample set.
Physics execution: real {provider} {backend_for(provider).upper()} ({device_for(provider)}). Asset provenance: {binding['kind']}; semantic endpoints: explicitly synthetic.

| Oracle seed | Transitions | Boundaries | Completion + storage |
|---|---|---|---|
{rows}

Storage is validated according to each Oracle schema: canonical exact logical comparison or v3 structured-control readback.
Core inspector separately validates H5/T+1. V3 external-stop outcome is preserved; it is not Expert-completion evidence.
Expert completion, physical task success and termination flags are retained independently in each oracle.check.json.

## Review gaps and limits

- Review open_issues in manifest.yaml and the full construction history; a later passing candidate does not resolve earlier execution faults.
- Construction round history preserves each round's Core context, including prior failures; owner-repair diagnosis and source diff are indexed under `validation/history/owner_repair/`.
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
        'validation/history/construction_log.json','validation/history/rounds.json',
        'local_assets/task.json','local_assets/asset_bundle.json',
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
    binding=check_asset_binding(spec,root/'local_assets',provider)
    if 'asset_binding' in manifest:
        require(manifest['asset_binding']==binding and manifest['synthetic_upstream']==binding['synthetic']
            and manifest['asset_uid']==binding['asset_uid'] and manifest['asset_sha256']==binding['asset_sha256'],
            'manifest asset binding mismatch')
    history=json.loads((root/'validation/history/construction_log.json').read_text())
    require(manifest.get('open_issues',[])==history.get('open_issues',[]),
        'package altered historical open issues')
    require(isinstance(history.get('rounds'),list),'construction history rounds are malformed')
    expected_bindings=[]
    for round_ in history['rounds']:
        require(isinstance(round_,dict),'construction history round is malformed')
        revision=round_.get('revision') or {}
        require(isinstance(revision,dict),'construction history revision is malformed')
        round_context=round_.get('context') or {}
        require(isinstance(round_context,dict),'diagnostic round context is malformed')
        round_core=round_context.get('core_commit',history.get('core_commit'))
        diagnostics=revision.get('diagnostics',[])
        require(isinstance(diagnostics,list),'construction diagnostics are malformed')
        for diagnostic in diagnostics:
            require(isinstance(diagnostic,dict),'construction diagnostic is malformed')
            expected_bindings.append((diagnostic,round_core))
    expected_diagnostics=len(expected_bindings)
    diagnostic_index=root/'validation/history/diagnostics.json'
    require(diagnostic_index.is_file() or not expected_diagnostics,'portable diagnostic evidence missing')
    diagnostic_rows=json.loads(diagnostic_index.read_text()) if diagnostic_index.is_file() else []
    require(len(diagnostic_rows)==expected_diagnostics,'diagnostic count mismatch')
    for pair,(diagnostic,round_core) in zip(diagnostic_rows,expected_bindings,strict=True):
        require(isinstance(pair,dict) and set(pair)=={'report','spec','core_commit'},
            'portable diagnostic entry has invalid fields')
        for kind in ('report','spec'):
            ref=pair[kind]
            require(isinstance(ref,dict) and set(ref)=={'path','sha256'}
                and isinstance(ref.get('path'),str) and isinstance(ref.get('sha256'),str),
                f'portable diagnostic {kind} ref is malformed')
            require(ref['path'] in seen and digest(root/ref['path'])==ref['sha256'],
                f'portable diagnostic evidence ref mismatch: {kind}')
        report_source=diagnostic.get('report',diagnostic)
        require(isinstance(report_source,dict) and set(report_source)=={'path','sha256'}
            and isinstance(report_source.get('path'),str) and isinstance(report_source.get('sha256'),str)
            and pair['report']['sha256']==report_source['sha256'],
            'portable diagnostic report/source reference mismatch')
        spec_source=diagnostic.get('spec')
        if spec_source is not None:
            require(isinstance(spec_source,dict) and set(spec_source)=={'path','sha256'}
                and isinstance(spec_source.get('path'),str) and isinstance(spec_source.get('sha256'),str)
                and pair['spec']['sha256']==spec_source['sha256'],
                'portable diagnostic spec/source reference mismatch')
        core_commit=pair['core_commit']
        require(isinstance(core_commit,str) and len(core_commit)==40
            and all(ch in '0123456789abcdef' for ch in core_commit),
            'portable diagnostic Core commit is malformed')
        require(isinstance(round_core,str) and core_commit==round_core,
            'portable diagnostic Core identity mismatch with round context')
        ds=CandidateSpec.load(root/pair['spec']['path'])
        dr=CheckReport.from_dict(json.loads((root/pair['report']['path']).read_text()))
        require(ds.spec_sha256()==dr.spec_sha256 and ds.task_id==spec.task_id,'diagnostic spec/report identity mismatch')
        require(dr.tool=='feasibility_probe' and dr.details.get('complete') is True,
            'portable diagnostic report is incomplete')
        require(dr.core_commit==core_commit and dr.core_commit==round_core
            and not dr.core_dirty and dr.details.get('provider')==provider,
            'diagnostic execution identity mismatch')
    round_rows=json.loads((root/'validation/history/rounds.json').read_text())
    require(manifest.get('construction_rounds')==round_rows,'manifest/history round summary mismatch')
    require(round_rows and round_rows[-1]['status']=='pass','final construction round is not passing')
    if len(round_rows)>1:
        require(any(row['status']=='fail' for row in round_rows[:-1]),
            'continuation package dropped its historical failed round')
    repair=manifest.get('owner_repair_evidence')
    if repair:
        receipt_path=root/repair['receipt_path']
        require(repair['receipt_path'] in seen and digest(receipt_path)==repair['receipt_sha256'],
            'owner-repair receipt missing from index')
        receipt=json.loads(receipt_path.read_text())
        require(receipt.get('repair_commit')==data['core_commit'],'owner-repair receipt/Core mismatch')
        require(history.get('schema_version')=='harness-attempt-ledger-v1'
            and history.get('legacy_ledger_ref',{}).get('sha256')==receipt.get('legacy_ledger_sha256'),
            'owner-repair receipt does not match preserved ledger history')
        require(len(round_rows)>=2 and round_rows[0]['status']=='fail'
            and round_rows[-1]['status']=='pass'
            and round_rows[-1]['core_commit']==data['core_commit'],
            'v1 package dropped its failed predecessor or final round context')
        for item in repair['diagnostics']:
            path=root/item['path']
            require(item['path'] in seen and digest(path)==item['sha256'],'owner-repair diagnostic changed')
        if repair.get('source_diff_path'):
            path=root/repair['source_diff_path']
            require(repair['source_diff_path'] in seen and digest(path)==receipt['source_diff_ref']['sha256'],
                'owner-repair source diff changed')
    require(manifest.get('qualification')=='NOT_ASSESSED' and manifest.get('D0')=='NOT_ASSESSED'
        and manifest.get('D1')=='NOT_ASSESSED' and manifest.get('D2')=='NOT_ASSESSED',
        'pending package overstates qualification status')
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
