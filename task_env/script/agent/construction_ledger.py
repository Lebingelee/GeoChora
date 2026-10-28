"""Hash-bound attempt ledger. The host agent decides; this CLI never runs an LLM."""
from pathlib import Path
from datetime import datetime,timezone
import argparse
import hashlib
import json

from harness_spec_schema import CandidateSpec,CheckReport,canonical_json,save_json
from completion_facts import validate_probe_report

MAX_ROUNDS=5
REQUIRED_TOOLS={'asset_check','harness_compiler','semantic_check','feasibility_probe'}


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


def load(path):
    value=json.loads(Path(path).read_text())
    require(value['schema_version']=='harness-attempt-ledger-v0','unknown ledger version')
    require(value['max_rounds']==MAX_ROUNDS and len(value['rounds'])<=MAX_ROUNDS,'invalid attempt budget')
    verify_refs(value)
    for i,r in enumerate(value['rounds']):
        require(r['number']==i+1,'round numbering mismatch')
        spec=CandidateSpec.from_dict(read_ref(r['spec']))
        require(spec.spec_sha256()==r['spec_sha256'],'round spec identity mismatch')
    return value


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


def begin(*,ledger,spec,revision=None):
    value=load(ledger)
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
    for path in reports:
        ref=file_ref(path);report=CheckReport.from_dict(read_ref(ref))
        require(report.spec_sha256==current['spec_sha256'],'report belongs to a different spec')
        require(report.core_commit==value['core_commit'] and report.core_dirty is False,'report Core identity mismatch')
        require(report.tool not in tools,'duplicate tool report');tools.add(report.tool)
        require(report.tool in REQUIRED_TOOLS,'unrecognized candidate check tool')
        if report.status=='pass' and report.tool!='asset_check':
            require(report.artifact_hash is not None,'passing compiled check requires artifact identity')
            require(report.details.get('provider')==value['provider'],'passing check must declare provider')
        if 'provider' in report.details:require(report.details['provider']==value['provider'],'report provider mismatch')
        if report.artifact_hash:artifacts.add(report.artifact_hash)
        if report.tool=='feasibility_probe':
            validate_probe_report(report,
                expected_spec_sha256=current['spec_sha256'],
                expected_core_commit=value['core_commit'],
                expected_provider=value['provider'],
                expected_horizon=current_spec.horizon,
                require_passing=report.status=='pass')
        parsed.append(report);refs.append(ref)
    require(parsed and len(artifacts)<=1,'missing reports or inconsistent artifact identities')
    passed=all(r.status=='pass' for r in parsed)
    if passed:require(tools==REQUIRED_TOOLS and len(artifacts)==1,'all four checks and artifact required for candidate acceptance')
    keys=sorted({k for r in parsed for k in stable_findings(r)})
    repeated=set(keys)&set(value['rounds'][-2].get('finding_keys',[])) if len(value['rounds'])>1 else set()
    current.update(status='pass' if passed else 'fail',reports=refs,artifact_hash=next(iter(artifacts),None),finding_keys=keys)
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
    for name in ('init','begin','finish','status'):
        a=s.add_parser(name);a.add_argument('--ledger',type=Path,required=True)
        if name=='init':
            for field in ('task','catalog'):a.add_argument('--'+field,type=Path,required=True)
            a.add_argument('--provider',required=True)
        elif name=='begin':a.add_argument('--spec',type=Path,required=True);a.add_argument('--revision',type=Path)
        elif name=='finish':a.add_argument('--reports',type=Path,nargs='+',required=True)
    args=vars(p.parse_args());command=args.pop('command')
    try:
        result={'init':initialize,'begin':begin,'finish':finish,'status':lambda ledger:load(ledger)}[command](**args)
        print(json.dumps({'state':result['state'],'rounds':len(result['rounds']),'max_rounds':MAX_ROUNDS,
            'stop_reason':result.get('stop_reason'),'open_issues':len(result['open_issues'])}))
        return 1 if result['state']=='stopped' else 0
    except Exception as error:
        print(json.dumps({'status':'error','error':f'{type(error).__name__}: {error}'}));return 2


if __name__=='__main__':raise SystemExit(main())
