"""Ten selected development entrypoints, reconstructed from immutable sources."""
import argparse,json,os,shlex,shutil,subprocess,sys,tempfile,tarfile,hashlib
from pathlib import Path

REPO=Path(__file__).resolve().parents[4]
MANIFEST=REPO/'docs/module/task_env/p1_8_integration/experiment_manifest.json'

def main():
    p=argparse.ArgumentParser();p.add_argument('--list',action='store_true');p.add_argument('--experiment');p.add_argument('--output',type=Path);p.add_argument('--prepare-only',action='store_true');args=p.parse_args()
    manifest=json.loads(MANIFEST.read_text());entries={x['experiment_id']:x for x in manifest['selected']}
    if args.list:
        print('\n'.join(f"{x['experiment_id']}: {x['purpose']}" for x in entries.values()));return
    if args.experiment not in entries or args.output is None:p.error('--experiment ID and --output NEW_DIR required')
    entry=entries[args.experiment];output=args.output.resolve()
    if output.exists():raise FileExistsError('do not overwrite experiment evidence')
    archive=Path(manifest['archive_root'])
    if not (archive/'archive_complete.json').is_file():raise RuntimeError('verified archive unavailable')
    # Current G0 goes directly through the independent integration entry.
    if entry['experiment_id']=='R5-10N-G0':
        cmd=[sys.executable,'-m',entry['module'],*shlex.split(entry['arguments'].format(output=output,archive=archive))]
        if args.prepare_only:print(shlex.join(cmd));return
        raise SystemExit(subprocess.call(cmd,cwd=REPO))
    with tempfile.TemporaryDirectory(prefix='geochora-p18-experiment-') as temp:
        tree=Path(temp)/'source'
        subprocess.run(['git','clone','--quiet','--no-checkout',str(archive/'p1_8_source.bundle'),str(tree)],check=True)
        subprocess.run(['git','checkout','--quiet','--detach',entry['source_commit']],cwd=tree,check=True)
        if entry['phase']=='R2':
            overlay=archive/'worktrees/p18e-r2-recovery'
            subprocess.run(['git','apply',str(overlay/'tracked.diff')],cwd=tree,check=True)
            shutil.copytree(overlay/'untracked',tree,dirs_exist_ok=True)
        # Materialize exact pinned submodule sources; no dependence on old worktree.
        for rel,bundle in [('GeoPhys','geophys_source.bundle'),('asset/external/mujoco_menagerie','menagerie_source.bundle')]:
            expected=subprocess.check_output(['git','ls-tree','HEAD',rel],cwd=tree,text=True).split()[2]
            target=tree/rel
            if target.exists():shutil.rmtree(target)
            name='geophys' if rel=='GeoPhys' else 'menagerie'
            snapshots=json.loads((archive/'source_snapshots.json').read_text())
            fact=snapshots[name+'-'+expected];snapshot=Path(fact['snapshot_path'])
            if hashlib.sha256(snapshot.read_bytes()).hexdigest()!=fact['sha256']:
                raise ValueError('submodule source snapshot checksum mismatch')
            target.mkdir(parents=True)
            with tarfile.open(snapshot) as t:t.extractall(target,filter='data')
        # Retain original source location for identity and relative asset resolution.
        if entry['experiment_id']=='R5-persistent-T0':
            target=tree/'workspace/qualification/phase1/p1_8_nutassembly_r5_architecture';target.mkdir(parents=True)
            shutil.copy2(archive/'worktrees/p1-8-e-r5-controller-architecture/evidence/p1_8_nutassembly_r5_architecture/c11_dynamic_profile.yaml',target/'c11_dynamic_profile.yaml')
        argv=shlex.split(entry['arguments'].format(output=output,archive=archive))
        cmd=[sys.executable,'-m',entry['module'],*argv]
        if args.prepare_only:
            subprocess.run([sys.executable,'-m',entry['module'],'--help'],cwd=tree,env={**os.environ,'PYTHONPATH':str(tree)+':'+str(tree/'GeoPhys')},check=True,stdout=subprocess.DEVNULL)
            print(json.dumps({'experiment':entry['experiment_id'],'source_verified':True,'command':shlex.join(cmd),'environment':'same pinned packages required; physics not executed'}));return
        env=os.environ.copy();env['PYTHONPATH']=str(tree)+':'+str(tree/'GeoPhys');env['MUJOCO_GL']='egl'
        rc=subprocess.call(cmd,cwd=tree,env=env)
        output.mkdir(parents=True,exist_ok=True)
        (output/'reconstruction_provenance.json').write_text(json.dumps({'experiment':entry,'command':cmd,'returncode':rc},indent=2)+'\n')
        raise SystemExit(rc)
if __name__=='__main__':main()
