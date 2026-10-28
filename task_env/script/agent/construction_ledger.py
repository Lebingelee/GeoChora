"""Hash-bound attempt ledger. The host agent decides; this CLI never runs an LLM."""
from pathlib import Path
from datetime import datetime,timezone
from copy import deepcopy
import argparse
import hashlib
import json

from harness_spec_schema import CandidateSpec,CheckReport,canonical_json,save_json
from completion_facts import validate_probe_report
from catalog_query import core_context

MAX_ROUNDS=5
REQUIRED_TOOLS={'asset_check','harness_compiler','semantic_check','feasibility_probe'}
V0='harness-attempt-ledger-v0'
V1='harness-attempt-ledger-v1'


def require(ok,message):
    if not ok:raise ValueError(message)


def file_ref(path):
    path=Path(path).resolve()
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def read_ref(ref):
    require(file_ref(ref['path'])==ref,f'stale/missing evidence: {ref["path"]}')
    return json.loads(Path(ref['path']).read_text())


def verify_refs(value):
    if isinstance(value,dict):
        if set(value)=={'path','sha256'}:require(file_ref(value['path'])==value,f'stale/missing evidence: {value["path"]}')
        else:
            for child in value.values():verify_refs(child)
    elif isinstance(value,list):
        for child in value:verify_refs(child)


def _load_v0(value):
    require(value['max_rounds']==MAX_ROUNDS and len(value['rounds'])<=MAX_ROUNDS,'invalid attempt budget')
    verify_refs(value)
    for i,r in enumerate(value['rounds']):
        require(r['number']==i+1,'round numbering mismatch')
        spec=CandidateSpec.from_dict(read_ref(r['spec']))
        require(spec.spec_sha256()==r['spec_sha256'],'round spec identity mismatch')
    return value


def _context(value,round_):
    context=round_.get('context')
    require(isinstance(context,dict),'round context missing')
    require(isinstance(context.get('core_commit'),str) and len(context['core_commit'])==40
        and all(ch in '0123456789abcdef' for ch in context['core_commit']),
        'round Core commit missing')
    require(context.get('provider')==value['provider'],'round provider mismatch')
    spec=CandidateSpec.from_dict(read_ref(round_['spec']))
    require(spec.spec_sha256()==round_['spec_sha256']==context.get('spec_sha256'),
        'round context/spec identity mismatch')
    catalog=read_ref(context['catalog_ref'])
    require(catalog.get('core_commit')==context['core_commit'] and catalog.get('core_dirty') is False,
        'round catalog/Core context mismatch')
    if 'catalog' in context.get('input_refs',{}):
        require(context['input_refs']['catalog']==context['catalog_ref'],
            'round catalog input ref mismatch')
    require(context['provider'] in catalog.get('providers',{})
        and catalog['providers'][context['provider']].get('available') is True,
        'round provider manifest unavailable')
    require(isinstance(context.get('runtime_refs'),dict) and context['runtime_refs'],
        'round runtime snapshot missing')
    require(isinstance(context.get('input_refs'),dict) and context['input_refs'],
        'round input refs missing')
    artifact_hash=context.get('artifact_hash')
    if artifact_hash is not None:
        require(isinstance(artifact_hash,str) and len(artifact_hash)==64,
            'invalid round artifact identity')
    return context,spec


def _validate_owner_repair(ref,round_,value):
    receipt=read_ref(ref)
    require(receipt.get('schema_version')=='harness-owner-repair-receipt-v1',
        'unknown owner-repair receipt')
    context,spec=_context(value,round_)
    require(receipt.get('repair_commit')==context['core_commit'],
        'owner-repair commit differs from round Core context')
    require(receipt.get('spec_sha256')==round_['spec_sha256'],
        'owner-repair receipt belongs to a different spec')
    require(isinstance(receipt.get('reason'),str) and receipt['reason'].strip(),
        'owner-repair rationale missing')
    require(receipt.get('legacy_ledger_sha256')==value['legacy_ledger_ref']['sha256'],
        'owner-repair receipt does not bind the original ledger')
    diagnostics=receipt.get('diagnostic_refs')
    require(isinstance(diagnostics,list) and len(diagnostics)>=3,
        'owner-repair diagnostics missing')
    labels={}
    for item in diagnostics:
        require(isinstance(item,dict) and isinstance(item.get('label'),str),
            'invalid owner-repair diagnostic ref')
        require(file_ref(item['ref']['path'])==item['ref'],'stale owner-repair diagnostic')
        labels[item['label']]=item['ref']['sha256']
    require({'ab_diagnosis_summary','builtin_seed0_trace','old_mock_seed0_trace'}<=set(labels),
        'A/B public trace evidence incomplete')
    change=receipt.get('asset_change')
    require(isinstance(change,dict),'asset change record missing')
    require(change.get('old_uid') and change.get('new_uid') and change['old_uid']!=change['new_uid'],
        'synthetic asset replacement must use a new UID')
    require(change.get('old_sha256') and change.get('new_sha256')
        and change['old_sha256']!=change['new_sha256'],'synthetic asset replacement must change bytes')
    before=receipt.get('input_before',{});after=receipt.get('input_after',{})
    legacy=json.loads(Path(value['legacy_ledger_ref']['path']).read_text())
    legacy_round=legacy['rounds'][-1]
    legacy_refs=legacy['refs']
    require(before.get('spec_sha256')==legacy_round['spec_sha256']
        and after.get('spec_sha256')==round_['spec_sha256'],
        'owner-repair before/after spec identity missing')
    for key,receipt_key in (('catalog','catalog_sha256'),('task','task_sha256'),
                            ('asset_bundle','asset_bundle_sha256')):
        require(legacy_refs.get(key,{}).get('sha256')==before.get(receipt_key),
            f'owner-repair before {key} identity mismatch')
    require(after.get('catalog_sha256')==context['catalog_ref']['sha256'],
        'owner-repair receipt catalog mismatch')
    require(after.get('task_sha256')==context['input_refs'].get('task',{}).get('sha256'),
        'owner-repair receipt task input mismatch')
    require(after.get('asset_bundle_sha256')==context['input_refs'].get('asset_bundle',{}).get('sha256'),
        'owner-repair receipt asset bundle mismatch')
    def bound_asset(task_ref,bundle_ref,uid):
        task_path=Path(task_ref['path'])
        task_data=json.loads(task_path.read_text())
        require(task_data.get('asset_bundle'),'owner-repair task has no asset bundle')
        bundle_path=task_path.parent/task_data['asset_bundle']
        require(file_ref(bundle_path)==bundle_ref,'owner-repair task/bundle reference mismatch')
        bundle=json.loads(bundle_path.read_text())
        rows=[asset for asset in bundle.get('assets',[]) if asset.get('uid')==uid]
        require(len(rows)==1,'owner-repair asset UID is missing or ambiguous')
        asset=rows[0];asset_path=bundle_path.parent/asset['path']
        require(file_ref(asset_path)['sha256']==asset.get('sha256'),
            'owner-repair asset bytes/bundle hash mismatch')
        return asset
    old_asset=bound_asset(legacy_refs['task'],legacy_refs['asset_bundle'],change['old_uid'])
    new_asset=bound_asset(context['input_refs']['task'],context['input_refs']['asset_bundle'],change['new_uid'])
    require(change.get('old_sha256')==old_asset.get('sha256')
        and change.get('new_sha256')==new_asset.get('sha256')
        and change.get('new_uid')==spec.object_config['object_uid']
        and change.get('new_sha256')==spec.object_config.get('asset_sha256'),
        'owner-repair asset change/spec mismatch')
    require(isinstance(receipt.get('source_diff_ref'),dict),
        'owner-repair source diff evidence missing')
    require(file_ref(receipt['source_diff_ref']['path'])==receipt['source_diff_ref'],
        'stale owner-repair source diff')
    return receipt


def _validate_spec_revision(round_,previous,value):
    revision=round_.get('revision') or {}
    require(revision.get('kind')=='spec_revision','round revision type missing')
    change=read_ref(revision['input'])
    prior=next((ref for ref in previous.get('reports',[])
        if ref['sha256']==change.get('report_sha256')),None)
    require(prior is not None,'revision must cite the immediately previous round')
    report=CheckReport.from_dict(read_ref(prior));index=change.get('finding_index')
    require(type(index) is int and 0<=index<len(report.findings),'revision finding index is invalid')
    finding=report.findings[index]
    require(finding.locality in ('task_local','unknown') and finding.category!='execution_fault',
        'owner/execution findings cannot be revised as task-local spec changes')
    old_spec=CandidateSpec.from_dict(read_ref(previous['spec']))
    new_spec=CandidateSpec.from_dict(read_ref(round_['spec']))
    require(new_spec.task_id==value['task_id'] and diff_values(old_spec.to_dict(),new_spec.to_dict())==revision['diff'],
        'spec revision diff/context mismatch')
    require(revision.get('reason')==change.get('reason') and isinstance(change.get('reason'),str)
        and change['reason'].strip(),'revision rationale missing')
    if finding.locality=='unknown':
        diagnostics=revision.get('diagnostics',[])
        require(diagnostics,'unknown attribution needs diagnostic evidence')
        context=round_['context']
        for item in diagnostics:
            diagnostic=CheckReport.from_dict(read_ref(item['report']))
            diagnostic_spec=CandidateSpec.from_dict(read_ref(item['spec']))
            require(diagnostic_spec.spec_sha256()==diagnostic.spec_sha256
                and diagnostic.spec_sha256!=previous['spec_sha256'],'diagnostic needs its own changed spec')
            require(diagnostic.core_commit==context['core_commit'] and diagnostic.core_dirty is False
                and diagnostic.details.get('provider')==context['provider'],
                'diagnostic Core/provider context mismatch')
            require(diagnostic.tool=='feasibility_probe' and diagnostic.details.get('complete') is True,
                'complete diagnostic probe required')


def _load_v1(value):
    require(value['max_rounds']==MAX_ROUNDS and len(value['rounds'])<=MAX_ROUNDS,
        'invalid attempt budget')
    verify_refs(value)
    require(isinstance(value.get('legacy_ledger_ref'),dict)
        and isinstance(value.get('history_archive_ref'),dict),
        'continuation history anchors missing')
    legacy=json.loads(Path(value['legacy_ledger_ref']['path']).read_text())
    require(value['legacy_ledger_ref']['sha256']==file_ref(value['legacy_ledger_ref']['path'])['sha256']
        and legacy.get('schema_version')==V0,'legacy ledger anchor invalid')
    archive=read_ref(value['history_archive_ref'])
    require(archive.get('schema_version')=='f00-attempt001-history-archive-v1'
        and archive.get('ledger_sha256')==value['legacy_ledger_ref']['sha256'],
        'legacy history archive does not match ledger')
    for item in archive.get('indexed_files',[]):
        path=Path(item['path'])
        require(path.is_file() and path.stat().st_size==item['bytes']
            and file_ref(path)['sha256']==item['sha256'],'archived attempt001 evidence changed')
    archived_runtime={item['name']:item for item in archive.get('runtime_snapshot',[])}
    require(set(archived_runtime)==set(value.get('runtime_refs',{})),
        'legacy runtime archive set changed')
    require(set(archived_runtime)==set(legacy.get('runtime_refs',{})),
        'legacy runtime snapshot does not cover the original runtime set')
    for name,ref in value['runtime_refs'].items():
        require(ref['sha256']==archived_runtime[name]['sha256']
            and ref['sha256']==legacy['runtime_refs'][name]['sha256']
            and file_ref(ref['path'])==ref,'legacy runtime snapshot changed')
    require(value.get('open_issues',[])==legacy.get('open_issues',[]),
        'continuation cleared or altered historical open issues')
    require(len(value['rounds'])>=len(legacy.get('rounds',[])),
        'continuation dropped historical rounds')
    historical_fields=('number','spec','spec_sha256','revision','status','reports',
        'artifact_hash','finding_keys')
    for original,continued in zip(legacy.get('rounds',[]),value['rounds'],strict=False):
        for key in historical_fields:
            if key in original:require(continued.get(key)==original[key],
                f'continuation altered historical round {original["number"]} field {key}')
    legacy_round_count=len(legacy.get('rounds',[]))
    require(len(value['rounds'])>legacy_round_count,
        'owner-repair continuation has no new round')
    first_repair=value['rounds'][legacy_round_count]
    first_revision=first_repair.get('revision') or {}
    require(first_revision.get('kind')=='owner_repair'
        and first_revision.get('repair_receipt')==value.get('owner_repair_ref'),
        'owner-repair continuation anchor missing or mismatched')
    for i,r in enumerate(value['rounds']):
        require(r['number']==i+1,'round numbering mismatch')
        _context(value,r)
        if i<legacy_round_count:
            original=legacy['rounds'][i]
            expected_context={'core_commit':legacy['core_commit'],'provider':legacy['provider'],
                'catalog_ref':legacy['refs']['catalog'],'runtime_refs':value['runtime_refs'],
                'input_refs':legacy['refs'],'spec_sha256':original['spec_sha256'],
                'artifact_hash':original.get('artifact_hash')}
            require(r.get('context')==expected_context,
                f'continuation changed historical round {i+1} execution context')
        revision=r.get('revision') or {}
        if i<legacy_round_count:
            pass  # v0 historical revision receipts are immutable and validated by their hashes.
        elif revision.get('kind')=='owner_repair':
            require(i==legacy_round_count,'owner repair must introduce the first new round')
            _validate_owner_repair(revision['repair_receipt'],r,value)
        elif revision.get('kind')=='spec_revision':
            require(i>legacy_round_count,'only post-repair rounds may be revised')
            _validate_spec_revision(r,value['rounds'][i-1],value)
        else:
            raise ValueError('new continuation round has no recognized revision evidence')
        reports=r.get('reports',[])
        if r.get('status')=='running':
            require(i==len(value['rounds'])-1 and not reports,'only the last round may be running')
        for ref in reports:
            report=CheckReport.from_dict(read_ref(ref));context=r['context']
            require(report.spec_sha256==r['spec_sha256'],'round report spec mismatch')
            require(report.core_commit==context['core_commit'] and report.core_dirty is False,
                'round report Core context mismatch')
            require(report.tool in REQUIRED_TOOLS,'unknown round report tool')
            if 'provider' in report.details:
                require(report.details['provider']==context['provider'],'round report provider mismatch')
            if report.artifact_hash is not None and context.get('artifact_hash') is not None:
                require(report.artifact_hash==context['artifact_hash'],'round artifact context mismatch')
        if reports and r.get('status')!='running':
            parsed=[CheckReport.from_dict(read_ref(x)) for x in reports]
            require(len({report.tool for report in parsed})==len(reports),'duplicate round reports')
            if r['status']=='pass':
                require({report.tool for report in parsed}==REQUIRED_TOOLS
                    and all(report.status=='pass' for report in parsed)
                    and len({report.artifact_hash for report in parsed if report.artifact_hash})==1,
                    'passing round is missing a required report/artifact')
            else:
                require(any(report.status!='pass' for report in parsed),'failed round has only passing reports')
    require(value['state'] in ('ready','running','candidate_ready','stopped'),
        'invalid ledger state')
    if value['state']=='running':require(value['rounds'][-1]['status']=='running','running state has no reservation')
    if value['state']=='candidate_ready':
        require(value['rounds'][-1]['status']=='pass','candidate_ready lacks passing final round')
    return value


def load(path):
    value=json.loads(Path(path).read_text())
    version=value.get('schema_version')
    if version==V0:return _load_v0(value)
    if version==V1:return _load_v1(value)
    raise ValueError('unknown ledger version')


def write(value,path):
    path=Path(path);temporary=path.with_name(path.name+'.tmp')
    with temporary.open('x') as stream:json.dump(value,stream,indent=2,ensure_ascii=False,allow_nan=False);stream.write('\n')
    temporary.replace(path)


def diff_values(a,b,prefix=''):
    if isinstance(a,dict) and isinstance(b,dict):
        result=[]
        for key in sorted(set(a)|set(b)):
            path=f'{prefix}.{key}' if prefix else key
            if key not in a or key not in b:result.append({'path':path,'before':a.get(key),'after':b.get(key)})
            else:result.extend(diff_values(a[key],b[key],path))
        return result
    return [] if a==b else [{'path':prefix,'before':a,'after':b}]


def initialize(*,ledger,task,catalog,provider):
    t=json.loads(Path(task).read_text());c=json.loads(Path(catalog).read_text())
    require(c['core_dirty'] is False,'clean Core required')
    require(provider in c['providers'] and c['providers'][provider].get('available') is True,'provider manifest unavailable')
    base=Path(task).resolve().parent
    refs={'task':file_ref(task),'catalog':file_ref(catalog)}
    for key in ('asset_bundle','semantic_examples'):
        if key in t:refs[key]=file_ref(base/t[key])
    runtime={p.name:file_ref(p) for p in Path(__file__).parent.glob('*.py') if not p.name.startswith('test_')}
    value={'schema_version':'harness-attempt-ledger-v0','created_at':datetime.now(timezone.utc).isoformat(),
        'task_id':t['task_id'],'provider':provider,'core_commit':c['core_commit'],'max_rounds':MAX_ROUNDS,
        'initial_candidate_counts_as_round':True,'refs':refs,'runtime_refs':runtime,
        'state':'ready','rounds':[],'open_issues':[],'judge_decision':None}
    save_json(value,ledger);return value


def _current_context(*,task,catalog,spec,provider):
    t=json.loads(Path(task).read_text());c=json.loads(Path(catalog).read_text())
    require(c['core_dirty'] is False,'clean Core required')
    live=core_context(c['core_repo'])
    require(live['core_dirty'] is False and live['core_commit']==c['core_commit'],
        'catalog does not describe the current clean Core checkout')
    require(provider in c['providers'] and c['providers'][provider].get('available') is True,
        'provider manifest unavailable')
    base=Path(task).resolve().parent
    inputs={'task':file_ref(task)}
    for key in ('asset_bundle','semantic_examples'):
        if key in t:inputs[key]=file_ref(base/t[key])
    runtime={p.name:file_ref(p) for p in Path(__file__).parent.glob('*.py')
        if not p.name.startswith('test_')}
    return {'core_commit':c['core_commit'],'provider':provider,
        'catalog_ref':file_ref(catalog),'runtime_refs':runtime,'input_refs':inputs,
        'spec_sha256':spec.spec_sha256(),'artifact_hash':None}


def continue_owner_repair(*,legacy_ledger,history_archive,repair_receipt,task,catalog,
                          spec,provider,ledger):
    """Migrate a failed v0 history and reserve one evidence-bound owner-repair round."""
    require(not Path(ledger).exists(),'continuation output already exists')
    legacy_path=Path(legacy_ledger).resolve();archive_path=Path(history_archive).resolve()
    receipt_path=Path(repair_receipt).resolve();candidate=CandidateSpec.load(spec)
    legacy=json.loads(legacy_path.read_text());legacy_hash=file_ref(legacy_path)['sha256']
    require(legacy.get('schema_version')==V0,'owner repair continuation requires a v0 source ledger')
    archive=file_ref(archive_path);archive_data=read_ref(archive)
    require(archive_data.get('schema_version')=='f00-attempt001-history-archive-v1'
        and archive_data.get('ledger_sha256')==legacy_hash,'attempt001 archive/ledger mismatch')
    old_runtime={row['name']:row for row in archive_data.get('runtime_snapshot',[])}
    require(set(old_runtime)==set(legacy.get('runtime_refs',{})),'archived runtime set differs from v0 ledger')
    migrated=deepcopy(legacy)
    archived_runtime={}
    for name,old_ref in legacy['runtime_refs'].items():
        row=old_runtime[name];path=Path(row['archive_path']).resolve()
        ref=file_ref(path)
        require(ref['sha256']==old_ref['sha256']==row['sha256'],'archived legacy runtime mismatch')
        archived_runtime[name]=ref
    migrated['runtime_refs']=archived_runtime
    _load_v0(migrated)
    require(legacy['state']=='ready' and legacy['rounds'],'legacy candidate is not eligible for continuation')
    require(legacy['rounds'][-1]['status']=='fail','only a failed candidate can be owner-repaired')
    require(len(legacy['rounds'])<MAX_ROUNDS,'attempt budget exhausted')
    require(legacy['task_id']==candidate.task_id,'cross-task continuation')
    context=_current_context(task=task,catalog=catalog,spec=candidate,provider=provider)
    receipt_ref=file_ref(receipt_path);receipt=json.loads(receipt_path.read_text())
    require(receipt.get('legacy_ledger_sha256')==legacy_hash,'owner receipt does not bind legacy ledger')
    require(receipt.get('repair_commit')==context['core_commit'],'owner receipt does not bind current Core commit')
    require(receipt.get('spec_sha256')==candidate.spec_sha256(),'owner receipt spec mismatch')
    context['owner_repair_receipt']=receipt_ref
    current={**migrated,'schema_version':V1,'runtime_refs':archived_runtime,
        'legacy_ledger_ref':file_ref(legacy_path),'history_archive_ref':archive,
        'owner_repair_ref':receipt_ref,'rounds':[],'state':'ready'}
    for old_round in legacy['rounds']:
        old_spec=CandidateSpec.from_dict(read_ref(old_round['spec']))
        old_context={'core_commit':legacy['core_commit'],'provider':legacy['provider'],
            'catalog_ref':legacy['refs']['catalog'],'runtime_refs':archived_runtime,
            'input_refs':legacy['refs'],'spec_sha256':old_round['spec_sha256'],
            'artifact_hash':old_round.get('artifact_hash')}
        current['rounds'].append({**old_round,'context':old_context})
    _validate_owner_repair(receipt_ref,
        {'spec':file_ref(spec),'spec_sha256':candidate.spec_sha256(),'context':context},current)
    round_number=len(current['rounds'])+1
    current['rounds'].append({'number':round_number,'spec':file_ref(spec),
        'spec_sha256':candidate.spec_sha256(),
        'revision':{'kind':'owner_repair','parent_round':legacy['rounds'][-1]['number'],
            'repair_receipt':receipt_ref},
        'context':context,'status':'running','reports':[]})
    current['state']='running'
    write(current,ledger)
    return load(ledger)


def _begin_v1(value,*,ledger,spec,revision=None,context_path=None):
    require(value['state']=='ready','ledger cannot begin: '+value['state'])
    require(len(value['rounds'])<MAX_ROUNDS,'attempt budget exhausted')
    candidate=CandidateSpec.load(spec)
    require(candidate.task_id==value['task_id'],'cross-task candidate')
    require(value['rounds'] and value['rounds'][-1]['status']=='fail',
        'v1 revisions require a failed immediately previous round')
    require(revision is not None,'revision rationale required after a failed round')
    change=json.loads(Path(revision).read_text());previous=value['rounds'][-1]
    require(isinstance(change.get('reason'),str) and change['reason'].strip(),'revision reason required')
    previous_report=next((r for r in previous.get('reports',[])
        if r['sha256']==change.get('report_sha256')),None)
    require(previous_report is not None,'revision must cite a report from the immediately previous round')
    report=CheckReport.from_dict(read_ref(previous_report));index=change.get('finding_index')
    require(type(index) is int and 0<=index<len(report.findings),'revision must cite an actual finding index')
    finding=report.findings[index]
    require(finding.locality in ('task_local','unknown') and finding.category!='execution_fault',
        'owner/execution findings cannot be repaired by spec tuning')
    old=CandidateSpec.from_dict(read_ref(previous['spec']))
    changes=diff_values(old.to_dict(),candidate.to_dict())
    require(bool(changes),'empty spec revision')
    if context_path is None:
        require(candidate.object_config['object_uid']==old.object_config['object_uid']
            and candidate.object_config.get('asset_sha256')==old.object_config.get('asset_sha256'),
            'asset revision requires an explicit new Core/catalog/input context')
        context=deepcopy(previous['context']);context['spec_sha256']=candidate.spec_sha256()
        context['artifact_hash']=None
        context.pop('owner_repair_receipt',None)
    else:
        context=json.loads(Path(context_path).read_text())
        context['spec_sha256']=candidate.spec_sha256();context['artifact_hash']=None
    verify_refs(context)
    _context(value,{'spec':file_ref(spec),'spec_sha256':candidate.spec_sha256(),'context':context})
    require(context.get('owner_repair_receipt') is None,
        'ordinary spec revision cannot inherit an owner-repair receipt')
    diagnostic_refs=[]
    if finding.locality=='unknown':
        require(bool(change.get('diagnostic_reports')),'unknown attribution needs independent diagnostic reports')
        require(len(change.get('diagnostic_specs',[]))==len(change['diagnostic_reports']),
            'each diagnostic report needs its actual separate spec')
        for path,spec_path in zip(change['diagnostic_reports'],change['diagnostic_specs'],strict=True):
            ref=file_ref(path);diagnostic=CheckReport.from_dict(read_ref(ref))
            spec_ref=file_ref(spec_path);diagnostic_spec=CandidateSpec.from_dict(read_ref(spec_ref))
            require(ref['sha256']!=previous_report['sha256'],'cited failure is not an independent diagnostic')
            require(diagnostic_spec.spec_sha256()==diagnostic.spec_sha256
                and diagnostic.spec_sha256!=previous['spec_sha256'],'diagnostic spec/report mismatch')
            require(diagnostic_spec.task_id==value['task_id'],'cross-task diagnostic')
            require(diagnostic.core_commit==context['core_commit'] and diagnostic.core_dirty is False,
                'diagnostic Core mismatch')
            require(diagnostic.tool=='feasibility_probe' and diagnostic.details.get('complete') is True,
                'complete diagnostic probe required')
            require(diagnostic.details.get('provider')==context['provider'],'diagnostic provider mismatch')
            diagnostic_refs.append({'report':ref,'spec':spec_ref})
    revision_receipt={'kind':'spec_revision','input':file_ref(revision),
        'report':previous_report,'finding_index':index,'reason':change['reason'],
        'diff':changes,'diagnostics':diagnostic_refs}
    value['rounds'].append({'number':len(value['rounds'])+1,'spec':file_ref(spec),
        'spec_sha256':candidate.spec_sha256(),'revision':revision_receipt,
        'context':context,'status':'running','reports':[]})
    value['state']='running';write(value,ledger);return load(ledger)


def begin(*,ledger,spec,revision=None,context=None):
    value=load(ledger)
    if value['schema_version']==V1:
        return _begin_v1(value,ledger=ledger,spec=spec,revision=revision,context_path=context)
    require(value['state']=='ready','ledger cannot begin: '+value['state'])
    require(len(value['rounds'])<MAX_ROUNDS,'attempt budget exhausted')
    candidate=CandidateSpec.load(spec)
    require(candidate.task_id==value['task_id'],'cross-task candidate')
    revision_receipt=None
    if value['rounds']:
        require(revision is not None,'revision rationale required after a failed round')
        previous=value['rounds'][-1];change=json.loads(Path(revision).read_text())
        require(isinstance(change.get('reason'),str) and change['reason'].strip(),'revision reason required')
        previous_report=next((r for r in previous['reports'] if r['sha256']==change.get('report_sha256')),None)
        require(previous_report is not None,'revision must cite a report from the immediately previous round')
        report=CheckReport.from_dict(read_ref(previous_report));index=change.get('finding_index')
        require(type(index) is int and 0<=index<len(report.findings),'revision must cite an actual finding index')
        finding=report.findings[index]
        require(finding.locality in ('task_local','unknown'),'non-task-local finding must be escalated')
        require(finding.category!='execution_fault','execution faults cannot be repaired by spec tuning')
        diagnostic_refs=[]
        if finding.locality=='unknown':
            require(bool(change.get('diagnostic_reports')),'unknown attribution needs independent diagnostic reports')
            require(len(change.get('diagnostic_specs',[]))==len(change['diagnostic_reports']),
                'each diagnostic report needs its actual separate spec')
            for path,spec_path in zip(change['diagnostic_reports'],change['diagnostic_specs'],strict=True):
                ref=file_ref(path);diagnostic=CheckReport.from_dict(read_ref(ref))
                spec_ref=file_ref(spec_path);diagnostic_spec=CandidateSpec.from_dict(read_ref(spec_ref))
                require(ref['sha256']!=previous_report['sha256'],'cited failure is not an independent diagnostic')
                require(diagnostic_spec.spec_sha256()==diagnostic.spec_sha256,'diagnostic spec/report mismatch')
                require(diagnostic.spec_sha256!=previous['spec_sha256'],'diagnostic requires a separate changed spec')
                require(diagnostic_spec.task_id==value['task_id'],'cross-task diagnostic')
                require(diagnostic.core_commit==value['core_commit'] and diagnostic.core_dirty is False,'diagnostic Core mismatch')
                require(diagnostic.tool=='feasibility_probe' and diagnostic.details.get('complete') is True,'complete diagnostic probe required')
                require(diagnostic.details.get('provider')==value['provider'],'diagnostic provider mismatch')
                diagnostic_refs.append({'report':ref,'spec':spec_ref})
        old=CandidateSpec.from_dict(read_ref(previous['spec']))
        changes=diff_values(old.to_dict(),candidate.to_dict())
        require(bool(changes),'empty spec revision')
        revision_receipt={'input':file_ref(revision),'report':previous_report,'finding_index':index,
            'reason':change['reason'],'diff':changes,'diagnostics':diagnostic_refs}
    else:
        require(revision is None,'initial round has no parent revision')
    value['rounds'].append({'number':len(value['rounds'])+1,'spec':file_ref(spec),
        'spec_sha256':candidate.spec_sha256(),'revision':revision_receipt,'status':'running'})
    value['state']='running';write(value,ledger);return value


def stable_findings(report):
    keys={canonical_json([report.tool,f.check,f.category,f.locality,f.spec_path]) for f in report.findings}
    if report.status!='pass' and not keys:
        keys.add(canonical_json([report.tool,'inconclusive','unknown']))
    return sorted(keys)


def finish(*,ledger,reports):
    value=load(ledger);require(value['state']=='running','no active round')
    current=value['rounds'][-1];parsed=[];refs=[];artifacts=set();tools=set()
    current_spec=CandidateSpec.from_dict(read_ref(current['spec']))
    context=current.get('context') or {'core_commit':value['core_commit'],'provider':value['provider']}
    for path in reports:
        ref=file_ref(path);report=CheckReport.from_dict(read_ref(ref))
        require(report.spec_sha256==current['spec_sha256'],'report belongs to a different spec')
        require(report.core_commit==context['core_commit'] and report.core_dirty is False,'report Core identity mismatch')
        require(report.tool not in tools,'duplicate tool report');tools.add(report.tool)
        require(report.tool in REQUIRED_TOOLS,'unrecognized candidate check tool')
        if report.status=='pass' and report.tool!='asset_check':
            require(report.artifact_hash is not None,'passing compiled check requires artifact identity')
            require(report.details.get('provider')==context['provider'],'passing check must declare provider')
        if 'provider' in report.details:require(report.details['provider']==context['provider'],'report provider mismatch')
        if report.artifact_hash:artifacts.add(report.artifact_hash)
        if report.tool=='feasibility_probe':
            validate_probe_report(report,
                expected_spec_sha256=current['spec_sha256'],
                expected_core_commit=context['core_commit'],
                expected_provider=context['provider'],
                expected_horizon=current_spec.horizon,
                require_passing=report.status=='pass')
        parsed.append(report);refs.append(ref)
    require(parsed and len(artifacts)<=1,'missing reports or inconsistent artifact identities')
    passed=all(r.status=='pass' for r in parsed)
    if passed:require(tools==REQUIRED_TOOLS and len(artifacts)==1,'all four checks and artifact required for candidate acceptance')
    keys=sorted({k for r in parsed for k in stable_findings(r)})
    repeated=set(keys)&set(value['rounds'][-2].get('finding_keys',[])) if len(value['rounds'])>1 else set()
    current.update(status='pass' if passed else 'fail',reports=refs,artifact_hash=next(iter(artifacts),None),finding_keys=keys)
    if value['schema_version']==V1:current['context']['artifact_hash']=next(iter(artifacts),None)
    for ref,r in zip(refs,parsed,strict=True):
        for i,f in enumerate(r.findings):
            if f.category=='execution_fault' or f.locality in ('asset','core','provider','harness'):
                value['open_issues'].append({'report':ref,'finding_index':i,'status':'open','sent':False})
    stop=None
    if repeated:stop='repeated_finding'
    elif not passed and len(value['rounds'])>=MAX_ROUNDS:stop='budget_exhausted'
    elif not passed and any(f.locality in ('harness','asset','core','provider') for r in parsed for f in r.findings):stop='owner_escalation'
    value['state']='candidate_ready' if passed else ('stopped' if stop else 'ready')
    if stop:value['stop_reason']=stop
    write(value,ledger);return value


def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True)
    for name in ('init','begin','finish','status','continue-owner-repair'):
        a=s.add_parser(name);a.add_argument('--ledger',type=Path,required=True)
        if name=='init':
            for field in ('task','catalog'):a.add_argument('--'+field,type=Path,required=True)
            a.add_argument('--provider',required=True)
        elif name=='begin':
            a.add_argument('--spec',type=Path,required=True);a.add_argument('--revision',type=Path)
            a.add_argument('--context',type=Path,
                help='explicit round context JSON for v1 revisions that change Core/catalog/input identity')
        elif name=='finish':a.add_argument('--reports',type=Path,nargs='+',required=True)
        elif name=='continue-owner-repair':
            for field in ('legacy-ledger','history-archive','repair-receipt','task','catalog','spec'):
                a.add_argument('--'+field,type=Path,required=True)
            a.add_argument('--provider',required=True)
    args=vars(p.parse_args());command=args.pop('command')
    try:
        result={'init':initialize,'begin':begin,'finish':finish,'status':lambda ledger:load(ledger),
            'continue-owner-repair':continue_owner_repair}[command](**args)
        print(json.dumps({'state':result['state'],'rounds':len(result['rounds']),'max_rounds':MAX_ROUNDS,
            'stop_reason':result.get('stop_reason'),'open_issues':len(result['open_issues'])}))
        return 1 if result['state']=='stopped' else 0
    except Exception as error:
        print(json.dumps({'status':'error','error':f'{type(error).__name__}: {error}'}));return 2


if __name__=='__main__':raise SystemExit(main())
