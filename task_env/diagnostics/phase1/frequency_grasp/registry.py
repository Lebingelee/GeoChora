"""Inventory all outcomes, preserving excluded and incomplete experiments."""
import hashlib,json,sys
from pathlib import Path

def digest_file(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def inventory(root):
    runs=[]
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or not (folder/'launch.json').exists():continue
        launch=json.loads((folder/'launch.json').read_text())
        summary_path=folder/'summary.json';canonical_path=folder/'canonical/report.json'
        summary=json.loads(summary_path.read_text()) if summary_path.exists() else {}
        canonical=json.loads(canonical_path.read_text()) if canonical_path.exists() else {}
        excluded=json.loads((folder/'protocol_exclusion.json').read_text()) if (folder/'protocol_exclusion.json').exists() else None
        capture=summary.get('native_samples',0)>0 and not summary.get('diagnostic_errors')
        row={'run':folder.name,'source_head':launch['head'],'case':launch['case'],'rate_Hz':launch['rate'],'mode':launch['mode'],'sample':launch.get('sample','nominal'),'status':'terminal_summary' if summary else 'incomplete_or_outer_failure','canonical_pass':canonical.get('pass'),'run_pass':summary.get('pass',False),'drift_m':summary.get('max_capture_position_drift_m',canonical.get('max_capture_position_drift_m')),'rotation_rad':summary.get('max_capture_rotation_drift_rad',canonical.get('max_capture_rotation_drift_rad')),'failure_boundary':summary.get('failure_boundary',canonical.get('failure_boundary')),'wall_time_s':summary.get('wall_time_s'),'native_force_capture_available':capture,'protocol_exclusion':excluded,'eligible_named_counterfactual':not excluded and capture,'source_snapshot_saved':(folder/'source_snapshot').exists(),'model_hash':summary.get('model_hash'),'module_sha256':launch['module_sha256'],'artifacts':{}}
        for relative in ['launch.json','summary.json','compiled_model.json','native.jsonl.gz','canonical/report.json','canonical/trace.json','canonical/execution.h5']:
            f=folder/relative
            if f.exists():row['artifacts'][relative]={'sha256':digest_file(f),'bytes':f.stat().st_size}
        runs.append(row)
    result={'schema':'frequency-grasp-run-inventory-v3','qualification':False,'runs':runs}
    (root/'run_matrix_with_sha256.json').write_text(json.dumps(result,indent=2)+'\n')
    print('inventoried',len(runs),'runs; all failures and exclusions retained')
if __name__=='__main__':inventory(Path(sys.argv[1]))
