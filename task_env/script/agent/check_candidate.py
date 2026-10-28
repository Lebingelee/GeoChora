"""Compose four existing checks for one candidate; no decisions or retry loop."""
from dataclasses import replace
from pathlib import Path
import argparse
import json
from catalog_query import core_context,validate_catalog
from harness_spec_schema import CandidateSpec,CheckReport,CheckFinding,save_json
from asset_check import check_assets
from harness_compiler import compile_candidate,CompilationRejected
from semantic_check import check_semantics
from feasibility_probe import run_candidate_probe


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('core-repo','spec','catalog','examples','output-dir'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--provider',required=True);p.add_argument('--count',type=int,default=20);p.add_argument('--base-seed',type=int,default=0)
    args=p.parse_args();ctx=core_context(args.core_repo)
    root=args.output_dir.resolve();root.mkdir(parents=True,exist_ok=False)
    spec=CandidateSpec.load(args.spec);catalog=json.loads(args.catalog.read_text());validate_catalog(catalog)
    spec.save(root/'candidate.spec.json');save_json(catalog,root/'catalog.json')
    paths=[];report=None;current_tool='asset_check';artifact_hash=None
    def emit(name,value):
        path=root/name;value.save(path);paths.append(str(path))
        return value
    try:
        report=emit('assets.json',check_assets(spec,catalog))
        if report.status=='pass':
            current_tool='harness_compiler'
            try:
                compiled=compile_candidate(spec,catalog,provider=args.provider)
                artifact_hash=compiled.artifact_hash
                save_json(compiled.artifact.to_mapping(),root/'candidate.artifact.json')
                report=emit('compile.json',CheckReport(spec.spec_sha256(),compiled.artifact_hash,
                    ctx['core_commit'],ctx['core_dirty'],'harness_compiler','pass',details={
                        'provider':args.provider,'artifact':compiled.artifact.to_mapping(),'source_xml_sha256':compiled.source_xml_sha256}))
            except CompilationRejected as error:report=emit('compile.json',error.report)
        if report.status=='pass':
            current_tool='semantic_check'
            report=emit('semantic.json',check_semantics(spec,catalog,args.examples,provider=args.provider))
        if report.status=='pass':
            current_tool='feasibility_probe'
            path=root/'feasibility.json'
            report=run_candidate_probe(spec,catalog,args.provider,list(range(args.base_seed,args.base_seed+args.count)),output=path)
            paths.append(str(path))
    except Exception as error:
        report=emit('tool-error.json',CheckReport(spec.spec_sha256(),artifact_hash,ctx['core_commit'],ctx['core_dirty'],
            current_tool,'error',[CheckFinding('check_execution','execution_fault','harness','',
                f'{type(error).__name__}: {error}','checks execute successfully',{})],details={'provider':args.provider}))
    print(json.dumps({'status':report.status,'reports':paths,'artifact_hash':report.artifact_hash}))
    return {'pass':0,'fail':1,'error':2}[report.status]


if __name__=='__main__':raise SystemExit(main())
