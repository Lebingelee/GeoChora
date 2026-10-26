"""Check candidate asset references and capability names (not runtime admission)."""
import argparse
import hashlib
import json
from pathlib import Path
from harness_spec_schema import CandidateSpec, CheckFinding, CheckReport
from catalog_query import core_context, validate_catalog, CatalogProvenanceError


def check_assets(spec,catalog,*,catalog_ref='in-memory',artifact_hash=None):
    validate_catalog(catalog)
    from task_env.artifacts.contracts import CAPABILITY_NAMES
    findings=[]
    refs=[('object_config.object_uid',spec.object_config['object_uid'],set(catalog['object_uids'])|set(catalog.get('external_assets',{})))]
    fixtures=set(catalog['object_uids'])|set(catalog['scene_uids'])
    refs.extend((f'scene_config.fixtures[{i}]',uid,fixtures) for i,uid in enumerate(spec.scene_config.get('fixtures',[])))
    for path,uid,available in refs:
        if uid not in available:
            findings.append(CheckFinding('uid_resolvable','asset_missing','asset',path,uid,sorted(available),
                {'catalog_ref':catalog_ref},'Escalate to asset owner; do not silently substitute a different object.'))
    external=catalog.get('external_assets',{}).get(spec.object_config['object_uid'])
    if external is not None:
        path=Path(external['path'])
        actual=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        expected=spec.object_config.get('asset_sha256')
        if not external.get('version') or actual!=external.get('sha256') or expected!=actual:
            findings.append(CheckFinding('asset_bytes_version_bound','asset_missing','asset','object_config.asset_sha256',
                {'actual':actual,'spec':expected,'version':external.get('version')},external.get('sha256'),
                {'asset_ref':str(path),'catalog_ref':catalog_ref},'Restore the delivered asset bytes/version and bind their hash in the spec.'))
    elif 'asset_sha256' in spec.object_config:
        findings.append(CheckFinding('external_asset_hash_context','spec_invalid','task_local','object_config.asset_sha256',
            spec.object_config['asset_sha256'],'hash only for external bundle asset',{}))
    for i,cap in enumerate(spec.required_capabilities):
        if cap not in CAPABILITY_NAMES:
            findings.append(CheckFinding('capability_name_known','spec_invalid','task_local',
                f'required_capabilities[{i}]',cap,sorted(CAPABILITY_NAMES),{'catalog_ref':catalog_ref},'Use a known capability name.'))
    return CheckReport(spec.spec_sha256(),artifact_hash,catalog['core_commit'],catalog['core_dirty'],
        'asset_check','fail' if findings else 'pass',findings,
        details={'scope':'UID presence and capability vocabulary only; not asset equivalence or provider admission.'})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ('spec','catalog','core-repo','output'):parser.add_argument('--'+arg,required=True,type=Path)
    args=parser.parse_args()
    ctx=core_context(args.core_repo)
    try:
        catalog=json.loads(args.catalog.read_text())
        if catalog['core_commit']!=ctx['core_commit'] or catalog['core_repo']!=ctx['core_repo']:
            raise CatalogProvenanceError('catalog does not match current Core provenance')
        spec=CandidateSpec.load(args.spec)
        report=check_assets(spec,catalog,catalog_ref=str(args.catalog.resolve()))
    except CatalogProvenanceError as error:
        report=CheckReport(None,None,ctx['core_commit'],ctx['core_dirty'],'asset_check','error',
            [CheckFinding('catalog_provenance','execution_fault','harness','',str(error),'matching clean Core snapshot',{})])
    except (ValueError,TypeError,KeyError,OSError) as error:
        report=CheckReport(None,None,ctx['core_commit'],ctx['core_dirty'],'asset_check','error',
            [CheckFinding('input_valid','spec_invalid','task_local','',str(error),'valid spec and catalog',{})])
    report.save(args.output)
    print(report.to_json())
    return {'pass':0,'fail':1,'error':2}[report.status]

if __name__=='__main__':raise SystemExit(main())
