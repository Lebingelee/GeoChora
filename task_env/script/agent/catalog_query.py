"""Read-only public registry/provider catalog; unavailable providers stay explicit."""
import argparse
import hashlib
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
from harness_spec_schema import save_json


def core_context(core_repo):
    repo = Path(core_repo).resolve()
    sys.path.insert(0,str(repo))
    import task_env
    if Path(task_env.__file__).resolve().parent.parent != repo:
        raise ValueError('core_repo does not match imported task_env')
    commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    dirty=bool(subprocess.check_output(['git','-C',str(repo),'status','--porcelain'],text=True))
    return {'core_repo':str(repo),'core_commit':commit,'core_dirty':dirty}


class CatalogProvenanceError(ValueError):
    """Catalog cannot establish the identity of the currently imported Core."""


def validate_catalog(catalog):
    if catalog.get('schema_version') != 'harness-catalog-v0':
        raise CatalogProvenanceError('unsupported catalog schema')
    ctx=core_context(catalog['core_repo'])
    if catalog.get('core_commit')!=ctx['core_commit'] or catalog.get('core_dirty') is not False or ctx['core_dirty']:
        raise CatalogProvenanceError('cached catalog requires the same clean Core checkout; regenerate/reconcile provenance')
    return ctx


def attach_asset_bundle(catalog, bundle_path):
    bundle_path=Path(bundle_path).resolve()
    bundle=json.loads(bundle_path.read_text())
    if bundle.get('schema_version')!='harness-mock-asset-bundle-v0' or bundle.get('synthetic') is not True:
        raise ValueError('explicit synthetic asset bundle required')
    catalog['external_assets']={}
    for asset in bundle['assets']:
        asset=dict(asset)
        path=(bundle_path.parent/asset['path']).resolve()
        if not path.is_relative_to(bundle_path.parent):raise ValueError('asset escapes bundle directory')
        if asset['uid'] in catalog['object_uids'] or asset['uid'] in catalog['external_assets']:
            raise ValueError('external asset UID collision')
        asset.update(path=str(path),synthetic=True,bundle_ref=str(bundle_path))
        # Record missing/mismatched bytes as evidence for asset_check, not fabricated presence.
        asset['available']=path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==asset['sha256']
        catalog['external_assets'][asset['uid']]=asset
    catalog['asset_bundle_sha256']=hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    return catalog


def attach_asset_delivery(catalog, delivery_path, *, provider_build_identities=None, allow_synthetic=False):
    """Attach a verified USD delivery in its own catalog namespace.

    USD is deliberately not added to ``external_assets``: the existing box
    template and asset checker continue to accept only their mock bundle type.
    """
    from task_env.assembly.usd_delivery import load_usd_asset_delivery, resolve_provider_representation

    loaded = load_usd_asset_delivery(delivery_path, allow_synthetic=allow_synthetic)
    provider_build_identities = dict(provider_build_identities or {})
    selections = {
        provider: resolve_provider_representation(
            loaded,
            provider=provider,
            provider_build_identity=build_identity,
        ).to_mapping()
        for provider, build_identity in sorted(provider_build_identities.items())
    }
    rows = catalog.setdefault('asset_deliveries', [])
    if any(row.get('asset_identity_hash') == loaded.delivery.asset_identity_hash for row in rows):
        raise ValueError('duplicate USD AssetDefinition in catalog')
    rows.append({
        'schema_version': 'catalog-usd-asset-delivery-v1',
        'asset_identity_hash': loaded.delivery.asset_identity_hash,
        'delivery_sha256': loaded.delivery_sha256,
        'source_revision': loaded.delivery.source_revision,
        'provenance_kind': loaded.delivery.provenance_kind,
        'source_verified': loaded.source_verified,
        'entry_file': loaded.delivery.entry_file,
        'entry_file_sha256': hashlib.sha256(loaded.file_bytes[loaded.delivery.entry_file]).hexdigest(),
        'entry_prim': loaded.delivery.entry_prim,
        'variant_selections': dict(sorted(loaded.delivery.variant_selections.items())),
        'representation_format': loaded.delivery.representation_format,
        'representation_id': loaded.delivery.representation_id,
        'closure_policy': loaded.delivery.closure_policy,
        'closure_sha256': loaded.closure_sha256,
        'file_count': len(loaded.file_bytes),
        'validation_report_sha256': loaded.delivery.validation_report_sha256,
        'inspection': dict(loaded.inspection),
        'provider_selections': selections,
        'runtime_admitted': False,
    })
    return catalog


def build_catalog(core_repo, asset_bundle=None, providers=None, *, asset_deliveries=None,
                  asset_provider_build_identities=None, allow_synthetic_asset_deliveries=False):
    context=core_context(core_repo)
    import task_env
    from task_env.artifacts.contracts import CAPABILITY_NAMES
    from task_env.runtime.sessions import provider_manifest
    result=dict(schema_version='harness-catalog-v0',**context,errors=[],asset_deliveries=[])
    for kind in ('env','agent','object','scene'):
        registry=getattr(task_env,kind.upper()+'_REGISTRY')
        result[kind+'_uids']=list(registry.uids())
        if kind=='env':continue
        result[kind+'s']={}
        for uid in registry.uids():
            try:
                component=registry.create(uid)
                entry={'asset_manifest':json.loads(json.dumps(asdict(component.asset_manifest()),default=str))}
                if kind=='agent':entry['supported_controller_kinds']=list(component.supported_controller_kinds())
                result[kind+'s'][uid]=entry
            except Exception as error:
                result[kind+'s'][uid]={'error':f'{type(error).__name__}: {error}'}
                result['errors'].append({'owner':uid,'error':str(error)})
    result['capability_names']=sorted(CAPABILITY_NAMES)
    result['providers']={}
    for provider in providers or ('geophys','mujoco'):
        try:
            result['providers'][provider]={'available':True,'manifest_available':True,'execution_tested':False,
                **provider_manifest(provider).to_mapping()}
        except Exception as error:
            result['providers'][provider]={'available':False,'capabilities':None,'known_unsupported':None,
                'error':f'{type(error).__name__}: {error}'}
    root=Path(core_repo).resolve()/'asset/external/mujoco_menagerie'
    result['menagerie_root']={'path':str(root),'commit':None,'models':[]}
    try:
        # Avoid git walking into the parent Core repo for an uninitialized submodule.
        top=subprocess.check_output(['git','-C',str(root),'rev-parse','--show-toplevel'],text=True,stderr=subprocess.PIPE).strip()
        if Path(top).resolve()!=root.resolve():raise ValueError('Menagerie is not initialized')
        result['menagerie_root']['commit']=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
        result['menagerie_root']['models']=sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith('.'))
    except Exception as error:
        result['menagerie_root']['error']=str(error)
    result['harness_templates']=['pick-lift-v0']
    result['template_details']={'pick-lift-v0':{'description':'Panda tabletop single cube lift; lift is the sole success predicate.',
        'required_object_kinds':['cube-v1'],'required_scene_uid':'tabletop-v1',
        'timebase':{'physics_dt':.002,'control_substeps':5},'reset_z_fixed':True,
        'additional_fixtures':False,'lift_height_m_max':.105}}
    from task_env.tasks.pick_cube.task import build_artifact
    base=build_artifact()
    result['template_details']['pick-lift-v0']['spec_template']={
        'schema_version':'harness-candidate-spec-v0','task_id':'suite/task-v0','template':'pick-lift-v0',
        'scene_config':{'table_top_z':.462,'table_center_xy':[.5545,0.],'table_half_size':[.28,.20,.01]},
        'object_config':{'object_uid':'cube-v1','initial_pos_xy':[.5545,0.],
            'reset_half_extent_m':.06,'reset_z_fixed':True},
        'success_config':{'lift_height_m':.10,'reach_distance_m':.09,'gripper_closed_opening_m':.045},
        'timebase_config':{'physics_dt':.002,'control_substeps':5},
        'required_capabilities':sorted(base.required_capabilities.names),'horizon':6000}
    if asset_bundle is not None:attach_asset_bundle(result,asset_bundle)
    for delivery_path in asset_deliveries or ():
        attach_asset_delivery(
            result,
            delivery_path,
            provider_build_identities=asset_provider_build_identities,
            allow_synthetic=allow_synthetic_asset_deliveries,
        )
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core-repo',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--asset-bundle',type=Path,help='explicit synthetic upstream bundle overlay; Core registries unchanged')
    parser.add_argument('--asset-delivery',action='append',type=Path,help='versioned, byte-closed USD delivery manifest; kept separate from mock external_assets')
    parser.add_argument('--asset-provider-build',action='append',default=[],help='provider=exact-build identity for a USD representation selection; repeatable')
    parser.add_argument('--allow-synthetic-asset-delivery',action='store_true',help='test-only opt-in for explicitly synthetic USD fixtures')
    parser.add_argument('--providers',nargs='+',default=['geophys','mujoco'],help='query manifest names; does not install or qualify providers')
    args=parser.parse_args()
    provider_builds={}
    for item in args.asset_provider_build:
        provider,sep,build=item.partition('=')
        if not sep or not provider or not build or provider in provider_builds:
            parser.error('--asset-provider-build must be unique provider=exact-build entries')
        provider_builds[provider]=build
    catalog=build_catalog(
        args.core_repo,args.asset_bundle,args.providers,
        asset_deliveries=args.asset_delivery,
        asset_provider_build_identities=provider_builds,
        allow_synthetic_asset_deliveries=args.allow_synthetic_asset_delivery,
    )
    save_json(catalog,args.output)
    print(json.dumps({'output':str(args.output),'env_uids':catalog['env_uids']}))
    return 0

if __name__=='__main__':raise SystemExit(main())
