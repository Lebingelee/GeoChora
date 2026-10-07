"""Diagnostic-only Flow dataset for the frozen P1.6 100 Hz corpus."""
from __future__ import annotations
from bisect import bisect_right
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset

from task_env.alg.state_bc.features import examples, features, FEATURE_CONTRACT, ACTION_CONTRACT
from task_env.trajectory.canonical import load
from task_env.alg.agent_factory.data.impl.geochora_canonical import window


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def logical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _trajectory_summary(path, row, expected_artifact, backend):
    path = Path(path)
    if not path.is_file() or sha256(path) != row["trajectory_file_sha256"]:
        raise ValueError(f"trajectory file hash mismatch seed={row['seed']}")
    trajectory = load(path)
    trajectory.validate()
    metadata = trajectory.metadata
    if trajectory.identity_hash != row["trajectory_logical_hash"]:
        raise ValueError(f"trajectory logical identity mismatch seed={row['seed']}")
    if len(trajectory.boundaries) != len(trajectory.transitions) + 1:
        raise ValueError(f"T+1/T mismatch seed={row['seed']}")
    if metadata.task_seed != row["seed"] or metadata.sample_role != row["role"]:
        raise ValueError(f"seed/role provenance mismatch seed={row['seed']}")
    if metadata.task_artifact_hash != expected_artifact or metadata.reset_sample.identity_hash != row["reset_sample_hash"]:
        raise ValueError(f"artifact/reset provenance mismatch seed={row['seed']}")
    if metadata.execution.physics_provider != "geophys" or metadata.execution.backend != backend:
        raise ValueError(f"provider/backend provenance mismatch seed={row['seed']}")
    for name, expected in (("controller", row["controller_identity"]),
                           ("expert", row["expert_identity"]),
                           ("readiness", row["readiness_identity"])):
        if getattr(metadata, name + "_identity") != expected:
            raise ValueError(f"{name} identity mismatch seed={row['seed']}")
    final = trajectory.boundaries[-1]
    if not (trajectory.stop_reason == "expert_endpoint" and final.is_success and not final.task_failure
            and float(final.task_metrics["cube_lift"]) >= 0.105):
        raise ValueError(f"selected expert trajectory does not meet endpoint seed={row['seed']}")
    if not row["pass"] or not row["roundtrip"]:
        raise ValueError(f"worker collection/roundtrip did not pass seed={row['seed']}")
    temporal = trajectory_temporal(trajectory)
    return trajectory, temporal


def trajectory_temporal(trajectory):
    dt = float(trajectory.metadata.timebase.control_dt)
    stages = {}
    for stage in sorted({t.expert_stage for t in trajectory.transitions}):
        transitions = [t for t in trajectory.transitions if t.expert_stage == stage]
        planned = sum(bool(t.planned_action) for t in transitions)
        holds = sum(bool(t.readiness_hold) for t in transitions)
        total = len(transitions)
        stages[stage] = {"planned_frames": planned, "readiness_hold_frames": holds,
                         "total_frames": total, "simulated_duration_s": total * dt}
    t = len(trajectory.transitions)
    return {"physics_dt": float(trajectory.metadata.timebase.physics_dt),
            "control_substeps": int(trajectory.metadata.timebase.control_substeps),
            "control_dt": dt, "physics_frequency_hz": 1.0 / float(trajectory.metadata.timebase.physics_dt),
            "control_frequency_hz": 1.0 / dt, "total_control_frames": t,
            "total_simulation_duration_s": float(trajectory.boundaries[-1].simulation_time - trajectory.boundaries[0].simulation_time),
            "total_planned_frames": t - trajectory.hold_count,
            "total_readiness_hold_frames": trajectory.hold_count,
            "hold_fraction": trajectory.hold_count / t if t else 0.0,
            "per_stage": stages}


def _stats(values):
    a = np.asarray(values, dtype=np.float64)
    if a.size == 0:
        return {"count": 0}
    return {"count": int(a.shape[0]), "min": np.min(a, axis=0).tolist(),
            "mean": np.mean(a, axis=0).tolist(), "median": np.median(a, axis=0).tolist(),
            "p95": np.percentile(a, 95, axis=0).tolist(), "max": np.max(a, axis=0).tolist(),
            "std": np.std(a, axis=0).tolist()}


def _distribution(values):
    a = np.asarray(values, dtype=np.float64)
    return {"count": int(len(a)), "min": float(a.min()), "mean": float(a.mean()),
            "median": float(np.median(a)), "p95": float(np.percentile(a, 95)), "max": float(a.max())}


def _aggregate(trajectories):
    frames, durations, holds = [], [], 0
    stage_counts = Counter(); stage_planned = Counter(); stage_holds = Counter()
    stage_durations = defaultdict(float)
    all_states, all_actions, state_deltas, action_deltas = [], [], [], []
    for tr in trajectories:
        temp = trajectory_temporal(tr)
        T = len(tr.transitions)
        frames.append(T); durations.append(temp["total_simulation_duration_s"]); holds += tr.hold_count
        x, y = examples(tr)
        all_states.append(x); all_actions.append(y)
        boundary_x = np.stack([features(b.state, b.feedback) for b in tr.boundaries])
        if len(boundary_x) > 1: state_deltas.append(np.diff(boundary_x, axis=0))
        if len(y) > 1: action_deltas.append(np.diff(y, axis=0))
        for stage, item in temp["per_stage"].items():
            stage_counts[stage] += item["total_frames"]
            stage_planned[stage] += item["planned_frames"]
            stage_holds[stage] += item["readiness_hold_frames"]
            stage_durations[stage] += item["simulated_duration_s"]
    X = np.concatenate(all_states) if all_states else np.empty((0,33),dtype=np.float32)
    Y = np.concatenate(all_actions) if all_actions else np.empty((0,8),dtype=np.float32)
    dX = np.concatenate(state_deltas) if state_deltas else np.empty((0,33))
    dY = np.concatenate(action_deltas) if action_deltas else np.empty((0,8))
    total_frames = int(sum(frames))
    return {"trajectory_count":len(trajectories), "control_frames":_distribution(frames),
            "simulated_duration_s":_distribution(durations), "readiness_hold_frames":holds,
            "hold_fraction":holds/total_frames if total_frames else 0.0,
            "planned_frames":total_frames-holds,
            "per_stage":{"total_frames":dict(stage_counts),"planned_frames":dict(stage_planned),
                         "readiness_hold_frames":dict(stage_holds),
                         "simulated_duration_s":dict(stage_durations)},
            "state_feature_values":_stats(X), "action_values":_stats(Y),
            "per_control_boundary_state_delta":_stats(dX),
            "per_control_boundary_action_delta":_stats(dY),
            "state_sample_count":int(len(X)),"action_sample_count":int(len(Y))}


class Flow100Dataset(Dataset):
    """Same feature/action/window contracts, bound to this experiment's manifest."""
    def __init__(self, manifest_path, role, *, pred_horizon=16):
        self.manifest_path = Path(manifest_path)
        manifest = json.loads(self.manifest_path.read_text())
        if manifest["schema"] != "p1_6-100hz-flow-dataset-v0" or role not in ("train", "validation"):
            raise ValueError("unsupported 100Hz Flow dataset manifest")
        if manifest["feature_contract"] != FEATURE_CONTRACT or manifest["action_contract"] != ACTION_CONTRACT:
            raise ValueError("feature/action contract mismatch")
        if not manifest["full_training_authorized"]:
            raise ValueError("100Hz selected corpus is incomplete")
        self.manifest_identity = manifest["logical_identity"]
        self.role = role
        self.pred_horizon = int(pred_horizon)
        self.records=[]; self.ends=[]; total=0
        rows = manifest["trajectories"][role]
        if len(rows) != (80 if role == "train" else 20):
            raise ValueError("frozen selected corpus count mismatch")
        for row in rows:
            trajectory,_ = _trajectory_summary(Path(row["file"]), row,
                manifest["identities"]["task_artifact"], manifest["execution_backend"])
            x,y = examples(trajectory)
            if x.dtype != np.float32 or y.dtype != np.float32 or x.shape != (len(trajectory.transitions),33) or y.shape != (len(trajectory.transitions),8):
                raise ValueError("invalid state/action shape or dtype")
            self.records.append((x,y)); total += len(y); self.ends.append(total)
        self.statistics = manifest["dataset_statistics"][role]
    def __len__(self): return self.ends[-1]
    def __getitem__(self,index):
        if not 0 <= index < len(self): raise IndexError(index)
        record=bisect_right(self.ends,index); start=self.ends[record-1] if record else 0
        return window(*self.records[record],index-start,pred_horizon=self.pred_horizon)
    def get_all_actions(self): return torch.from_numpy(np.concatenate([y for x,y in self.records]))
    def get_all_states(self): return torch.from_numpy(np.concatenate([x for x,y in self.records]))


def finalize(root: Path):
    root=Path(root)
    source_manifest_path=root/'dataset_manifest.yaml'
    source_lock=json.loads((root/'dataset_manifest_lock.json').read_text())
    if sha256(source_manifest_path)!=source_lock['sha256']:
        raise ValueError('candidate manifest SHA256 mismatch')
    collection=json.loads((root/'corpus_collection_report.json').read_text())
    if not collection['full_80_20_corpus_available']:
        raise ValueError('expert_dataset_feasibility: incomplete candidate streams')
    source_manifest=__import__('yaml').safe_load(source_manifest_path.read_text())
    if collection['manifest_sha256']!=source_lock['sha256']:
        raise ValueError('collection/candidate manifest identity mismatch')
    if collection['attempted_seeds']['train'] != [r['seed'] for r in collection['rows']['train']]:
        raise ValueError('train attempt order mismatch')
    if collection['attempted_seeds']['validation'] != [r['seed'] for r in collection['rows']['validation']]:
        raise ValueError('validation attempt order mismatch')

    all_trajectories={"train":[],"validation":[]}; selected_rows={"train":[],"validation":[]}
    attempt_rows=[]; selected_seed_map={}
    selected_temporal={"train":[],"validation":[]}; attempt_sample_xy=[]
    from .timebase100 import context, sha256_file
    from task_env.controllers.canonical.contracts import digest
    _, variant_artifact, variant_source, readiness, controller, expert = context('cuda')
    readiness_contract_identity=digest({
        "schema":"canonical-control-readiness-v1",
        "policies":[p.to_mapping() for p in readiness.policies],
        "profile_identity":readiness.profile_identity,
        "config_identity":readiness.identity,
        "contract_source_sha256":sha256_file("task_env/controllers/canonical/readiness.py")})
    expected_ids={"task_artifact":source_manifest['experimental_task_artifact']['identity_hash'],
                  "controller":source_manifest['controller_identity'],"expert":source_manifest['expert_identity'],
                  "readiness":readiness_contract_identity}
    for role in ("train","validation"):
        expected_candidates=source_manifest['streams'][role]['candidate_seeds']
        if collection['attempted_seeds'][role] != expected_candidates[:len(collection['attempted_seeds'][role])]:
            raise ValueError(f"{role} candidate stream is not an ascending frozen prefix")
        selected_count=0
        for worker_row in collection['rows'][role]:
            seed=int(worker_row['seed']); frozen=source_manifest['reset_samples'][str(seed)]
            from task_env.artifacts.execution import ResetSample
            sample=ResetSample.from_mapping(frozen)
            if sample.identity_hash != worker_row['reset_sample_hash'] or not worker_row['success'] and worker_row['failure_boundary'] is None:
                raise ValueError(f"frozen sample/failure metadata mismatch seed={seed}")
            attempt_sample_xy.append({"role":role,"seed":seed,"xy":sample.poses_world['cube-v1'].position[:2],"success":bool(worker_row['success'])})
            report_path=Path(worker_row['report_path']); report=json.loads(report_path.read_text())
            path=Path(worker_row['trajectory_path']) if worker_row['trajectory_path'] else None
            row={"seed":seed,"role":role,"pass":bool(report.get('pass')),
                 "endpoint":bool(report.get('endpoint_reached')),
                 "success":bool(report.get('task_success')),
                 "roundtrip":bool(report.get('roundtrip')),
                 "failure_reason":report.get('failure_reason') or report.get('error'),
                 "first_boundary":report.get('first_boundary'),
                 "file":str(path) if path else None,
                 "file_sha256":report.get('trajectory_file_sha256'),
                 "logical_hash":report.get('trajectory_logical_hash'),
                 "reset_sample_hash":report.get('reset_sample_hash'),
                 "T":report.get('T'),"holds":report.get('hold_count'),
                 "max_cube_lift":report.get('max_cube_lift_m'),
                 "controller_identity":report.get('controller_identity'),
                 "expert_identity":report.get('expert_identity'),
                 "readiness_identity":readiness_contract_identity,
                 "readiness_config_identity":report.get('readiness_config_identity'),
                 "wall_time_s":worker_row['wall_time_s'],
                 "native_backend":report.get('native_backend'),
                 "trajectory_file_sha256":report.get('trajectory_file_sha256'),
                 "trajectory_logical_hash":report.get('trajectory_logical_hash')}
            attempt_rows.append(row)
            if row['pass']:
                if not path: raise ValueError(f"successful attempt missing trajectory file seed={seed}")
                trajectory,temp=_trajectory_summary(path,row,expected_ids['task_artifact'],'cuda')
                if trajectory.metadata.controller_identity != expected_ids['controller'] or trajectory.metadata.expert_identity != expected_ids['expert']:
                    raise ValueError(f"lower-layer identity mismatch seed={seed}")
                if trajectory.metadata.readiness_identity != expected_ids['readiness']:
                    raise ValueError(f"readiness identity mismatch seed={seed}")
                all_trajectories[role].append(trajectory)
                if selected_count < (80 if role=='train' else 20):
                    selected_count+=1
                    selected_rows[role].append(row)
                    selected_temporal[role].append(trajectory)
            elif worker_row['success']:
                raise ValueError(f"worker/strict validation status disagreement seed={seed}")
        target=80 if role=='train' else 20
        if selected_count != target:
            raise ValueError(f"expert_dataset_feasibility: {role} selected {selected_count}/{target}")
        selected_seed_map[role]=[r['seed'] for r in selected_rows[role]]

    if len(all_trajectories['train']) < 80 or len(all_trajectories['validation']) < 20:
        raise ValueError('successful attempts insufficient')
    train_stats=_aggregate(selected_temporal['train']); val_stats=_aggregate(selected_temporal['validation'])
    dataset={"schema":"p1_6-100hz-flow-dataset-v0","collection_manifest_sha256":source_lock['sha256'],
             "source_provider":"geophys","execution_backend":"cuda","diagnostic_only":True,
             "identities":expected_ids,"controller_identity":expected_ids['controller'],
             "expert_identity":expected_ids['expert'],"readiness_identity":expected_ids['readiness'],
             "readiness_config_identity":readiness.identity,
             "feature_contract":FEATURE_CONTRACT,"action_contract":ACTION_CONTRACT,
             "target_train_success_count":80,"target_validation_success_count":20,
             "attempted_train_seeds":collection['attempted_seeds']['train'],
             "attempted_validation_seeds":collection['attempted_seeds']['validation'],
             "successful_train_seeds":[r['seed'] for r in attempt_rows if r['role']=='train' and r['pass']],
             "successful_validation_seeds":[r['seed'] for r in attempt_rows if r['role']=='validation' and r['pass']],
             "failed_train_seeds":[r['seed'] for r in attempt_rows if r['role']=='train' and not r['pass']],
             "failed_validation_seeds":[r['seed'] for r in attempt_rows if r['role']=='validation' and not r['pass']],
             "selected_train_seeds":selected_seed_map['train'],"selected_validation_seeds":selected_seed_map['validation'],
             "selected_train_trajectory_hashes":[r['logical_hash'] for r in selected_rows['train']],
             "selected_validation_trajectory_hashes":[r['logical_hash'] for r in selected_rows['validation']],
             "full_training_authorized":True,
             "attempts":attempt_rows,
             "trajectories":{"train":selected_rows['train'],"validation":selected_rows['validation']},
             "dataset_statistics":{"train":train_stats,"validation":val_stats},
             "execution_profile":source_manifest['execution_profile'],"experimental_task_artifact":source_manifest['experimental_task_artifact']}
    dataset['logical_identity']=logical_hash(dataset)
    out_manifest=root/'training_dataset_manifest_100hz.json'
    out_lock=root/'training_dataset_manifest_100hz_lock.json'
    for p in (out_manifest,out_lock):
        if p.exists(): raise FileExistsError(f"refusing to overwrite {p}")
    text=json.dumps(dataset,sort_keys=True,indent=2,allow_nan=False)+'\n'
    out_manifest.write_text(text)
    file_hash=sha256(out_manifest)
    out_lock.write_text(json.dumps({'schema':'p1_6-100hz-flow-dataset-lock-v0','sha256':file_hash,
        'logical_identity':dataset['logical_identity'],'candidate_manifest_sha256':source_lock['sha256']},sort_keys=True,indent=2)+'\n')

    # Paired historical comparison for the predeclared reliability pilot.
    old_manifest_path=Path('workspace/qualification/phase1/p1_6_flow_preparation/training_dataset_manifest_v1.json')
    old_manifest=json.loads(old_manifest_path.read_text())
    old_attempts={(r['role'],r['seed']):r for r in old_manifest['attempts']}
    pilot=json.loads((root/'pilot_report.json').read_text())
    paired=[]
    for p in pilot['rows']:
        seed=p['seed']; oldrow=old_attempts.get(('train' if seed<1080 else 'validation',seed))
        oldfile=Path(oldrow['file']) if oldrow and oldrow['file'] else Path(f'workspace/qualification/phase1/p1_6_flow_preparation/trajectories/seed{seed}/trajectory.h5')
        current_report=p['report']; newfile=Path(current_report['trajectory_file'])
        if oldfile.exists() and newfile.exists():
            oldtr=load(oldfile); newtr=load(newfile)
            paired.append({'seed':seed,'old_500hz':trajectory_temporal(oldtr),'new_100hz':trajectory_temporal(newtr),
                           'historical_success':bool(oldtr.boundaries[-1].is_success),
                           'new_success':bool(current_report['pass'])})
    old_tr=[]
    for row in old_manifest['trajectories']:
        tr=load(row['file']); tr.validate()
        old_tr.append(tr)
    # aggregate new 100 Hz corpus from the selected successful episodes only.
    new_tr=selected_temporal['train']+selected_temporal['validation']
    temporal_report={'schema':'p1_6-100hz-vs-500hz-temporal-report-v0',
        'historical_500hz_dataset':_aggregate(old_tr),'new_100hz_dataset':_aggregate(new_tr),
        'paired_reliability_pilot':paired,
        'interpretation':'New selected corpus seeds are disjoint from the historical dataset; aggregate comparisons are distribution summaries, while same-seed pairing is reported only for the predeclared pilot.'}
    temporal_path=root/'temporal_comparison_report.json'
    if temporal_path.exists(): raise FileExistsError(temporal_path)
    temporal_path.write_text(json.dumps(temporal_report,sort_keys=True,indent=2,allow_nan=False)+'\n')
    result={'schema':'p1_6-100hz-selected-dataset-summary-v0','manifest_sha256':file_hash,
            'logical_identity':dataset['logical_identity'],'selected_train_seeds':selected_seed_map['train'],
            'selected_validation_seeds':selected_seed_map['validation'],
            'failed_train_seeds':dataset['failed_train_seeds'],'failed_validation_seeds':dataset['failed_validation_seeds'],
            'train':train_stats,'validation':val_stats,
            'attempted_counts':collection['attempted_counts'],'full_training_authorized':True,
            'temporal_comparison_file':str(temporal_path)}
    summary_path=root/'selected_dataset_report.json'
    if summary_path.exists(): raise FileExistsError(summary_path)
    summary_path.write_text(json.dumps(result,sort_keys=True,indent=2,allow_nan=False)+'\n')
    return result

if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,default=Path('workspace/experiments/p1_6_policy_search/100hz_gpu_flow'))
    args=p.parse_args()
    print(json.dumps(finalize(args.root),sort_keys=True,indent=2,allow_nan=False))
