"""Fixed CPU supervised learner and identical-checkpoint provider-free inference."""
from pathlib import Path
import hashlib,json,copy
import numpy as np
import torch
from .features import FEATURE_CONTRACT,ACTION_CONTRACT,examples
from ...trajectory.canonical import load


def network(config):
    if config['input_dim']!=33 or config['output_dim']!=8 or config['hidden']!=[128,128] or config['activation']!='ReLU':raise ValueError('unsupported state-bc-v0 architecture')
    return torch.nn.Sequential(torch.nn.Linear(33,128),torch.nn.ReLU(),torch.nn.Linear(128,128),torch.nn.ReLU(),torch.nn.Linear(128,8))


def dataset(paths):
    trajectories=[load(p) for p in paths];xy=[examples(t) for t in trajectories];x=np.concatenate([v[0] for v in xy]);y=np.concatenate([v[1] for v in xy])
    roles={t.metadata.sample_role for t in trajectories}
    if len(roles)!=1:raise ValueError('mixed dataset roles')
    hashes=[t.identity_hash for t in trajectories];manifest={'schema':'state-bc-dataset-v0','trajectory_hashes':hashes,'role':next(iter(roles)),
        'provider':trajectories[0].metadata.execution.physics_provider,'transitions':len(x),'holds':sum(t.hold_count for t in trajectories),'stage_counts':{}}
    if any(t.metadata.execution.physics_provider!=manifest['provider'] for t in trajectories):raise ValueError('mixed source dataset')
    for t in trajectories:
        if not t.boundaries[-1].is_success or t.stop_reason!='expert_endpoint':raise ValueError('failed required expert data')
        for row in t.transitions:manifest['stage_counts'][row.expert_stage]=manifest['stage_counts'].get(row.expert_stage,0)+1
    manifest['planned']=len(x)-manifest['holds'];manifest['hold_fraction']=manifest['holds']/len(x)
    for name,array in (('features',x),('actions',y)):
        if array.dtype!=np.float32 or not np.isfinite(array).all():raise ValueError('invalid dataset dtype/finiteness')
        manifest[name+'_stats']={k:getattr(np,k)(array,axis=0).astype(float).tolist() for k in ('min','max','mean','std')}
    manifest['logical_hash']=hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return x,y,manifest


class StatePolicy:
    def __init__(self,checkpoint):
        if checkpoint['schema']!='state-bc-checkpoint-v0' or checkpoint['feature_contract']!=FEATURE_CONTRACT or checkpoint['action_contract']!=ACTION_CONTRACT:raise ValueError('checkpoint contract mismatch')
        self.checkpoint=checkpoint;self.model=network(checkpoint['learner_config']);self.model.load_state_dict(checkpoint['state_dict'],strict=True);self.model.eval()
        self.norm=checkpoint['normalization']
        for name,width in (('input_mean',33),('input_std',33),('output_mean',8),('output_std',8)):
            v=self.norm[name]
            if v.dtype!=torch.float32 or v.shape!=(width,) or not torch.isfinite(v).all() or ('std' in name and torch.any(v<=0)):raise ValueError('invalid checkpoint normalization')
        if any(not torch.isfinite(v).all() for v in self.model.parameters()):raise ValueError('nonfinite checkpoint')
    def __call__(self,values):
        array=np.asarray(values)
        if array.dtype!=np.float32 or array.shape[-1:]!=(33,) or array.ndim not in (1,2) or not np.isfinite(array).all():raise ValueError('policy feature contract mismatch')
        with torch.no_grad():
            x=torch.from_numpy(array.copy());n=self.norm;y=self.model((x-n['input_mean'])/n['input_std'])*n['output_std']+n['output_mean']
        out=y.numpy()
        if not np.isfinite(out).all():raise ValueError('nonfinite policy output')
        return out


def load_checkpoint(path):return StatePolicy(torch.load(path,map_location='cpu',weights_only=True))


def train(train_paths,validation_paths,config,output,*,provider_provenance,parity_tolerance):
    torch.set_num_threads(1);torch.manual_seed(config['seed']);np.random.seed(config['seed']);torch.use_deterministic_algorithms(True)
    x,y,manifest=dataset(train_paths);vx,vy,validation=dataset(validation_paths)
    if manifest['role']!='train' or validation['role']!='validation' or manifest['provider']!=validation['provider']:raise ValueError('training/validation provenance mismatch')
    n={'input_mean':torch.from_numpy(x.mean(0)), 'input_std':torch.from_numpy(np.maximum(x.std(0),config['normalization_epsilon'])),
        'output_mean':torch.from_numpy(y.mean(0)),'output_std':torch.from_numpy(np.maximum(y.std(0),config['normalization_epsilon']))}
    tx=(torch.from_numpy(x)-n['input_mean'])/n['input_std'];ty=(torch.from_numpy(y)-n['output_mean'])/n['output_std']
    tvx=(torch.from_numpy(vx)-n['input_mean'])/n['input_std'];tvy=(torch.from_numpy(vy)-n['output_mean'])/n['output_std']
    model=network(config);optimizer=torch.optim.Adam(model.parameters(),lr=config['lr']);loss_fn=torch.nn.MSELoss();best=float('inf');best_state=None;selected=None;history=[];smoke=None
    for epoch in range(1,config['epochs']+1):
        order=torch.randperm(len(tx));total=0.
        for start in range(0,len(tx),config['batch_size']):
            idx=order[start:start+config['batch_size']];optimizer.zero_grad();loss=loss_fn(model(tx[idx]),ty[idx]);loss.backward()
            gradients=all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters())
            if not torch.isfinite(loss) or not gradients:raise ValueError('nonfinite loss/gradient')
            optimizer.step()
            if any(not torch.isfinite(p).all() for p in model.parameters()):raise ValueError('nonfinite parameters')
            if smoke is None:smoke={'batch_shape':[len(idx),33],'actions_shape':[len(idx),8],'dtype':'float32','finite_loss':float(loss),'finite_gradients':True,'finite_parameters':True}
            total+=float(loss.detach())*len(idx)
        with torch.no_grad():validation_loss=float(loss_fn(model(tvx),tvy))
        if not np.isfinite(validation_loss):raise ValueError('nonfinite validation loss')
        history.append({'epoch':epoch,'train_loss':total/len(tx),'validation_loss':validation_loss})
        if validation_loss<best:best=validation_loss;selected=epoch;best_state=copy.deepcopy(model.state_dict())
    checkpoint={'schema':'state-bc-checkpoint-v0','architecture':{'input':33,'hidden':[128,128],'output':8,'activation':'ReLU'},'state_dict':best_state,
        'feature_contract':FEATURE_CONTRACT,'action_contract':ACTION_CONTRACT,'normalization':n,'training_provider_provenance':provider_provenance,
        'dataset_manifest':manifest,'validation_manifest':validation,'learner_config':config,'seed':config['seed'],'selected_epoch':selected,'validation_loss':best}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():raise FileExistsError('checkpoint overwrite prohibited')
    policy=StatePolicy(checkpoint);fixture=vx[:min(16,len(vx))];before=policy(fixture);torch.save(checkpoint,output);loaded=load_checkpoint(output)
    parity=float(np.max(np.abs(before-loaded(fixture))))
    if parity>parity_tolerance:raise ValueError('checkpoint_portability: parity bound exceeded')
    return {'pass':True,'smoke':smoke,'checkpoint':str(output),'checkpoint_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'selected_epoch':selected,
        'validation_loss':best,'parity_max_abs':parity,'history':history,'training_manifest':manifest,'validation_manifest':validation}
