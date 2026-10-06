"""Preparation regression checks; fake training updates test logging, never train a policy."""
from pathlib import Path
import json
import subprocess
import sys
import numpy as np
import torch
from torch.utils.data import DataLoader
import task_env.alg.agent_factory
from agent_factory.data.impl.geochora_canonical import window
from agent_factory.training.flow_metrics import validation_loss, train_loop
from task_env.trajectory.canonical import load
from task_env.alg.state_bc.features import examples


def run(root):
    root=Path(root); root.mkdir(parents=True, exist_ok=True)
    checks={}
    script='''
import sys
import task_env.alg.agent_factory
from agent_factory.config.resolution import general_resolve
from omegaconf import OmegaConf
from agent_factory.agents.registry import make_agent
cfg,_=general_resolve(file_config=OmegaConf.load('task_env/alg/agent_factory/config/profiles/geochora_flow.yaml'))
cfg.device=cfg.train.device='cpu'
a=make_agent('Flow_Vanilla',cfg)
import task_env.alg.agent_factory.agents.registry as qualified
import agent_factory.agents.registry as legacy
assert qualified is legacy
assert a.actor_encoder.visual_encoder is None
assert not any(x.split('.')[0] in {'diffusers','transformers','lerobot','mani_skill','pynput','agent_infra','torchvision','geophys','mujoco','sapien','genesis','taichi'} for x in sys.modules)
'''
    result=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True)
    (root/'import.stdout.log').write_text(result.stdout); (root/'import.stderr.log').write_text(result.stderr)
    checks['flow_fresh_import_isolation']=result.returncode==0
    x=np.arange(5*33,dtype=np.float32).reshape(5,33); y=np.arange(5*8,dtype=np.float32).reshape(5,8)
    first=window(x,y,0);last=window(x,y,4)
    checks['history_begin_repeat']=np.array_equal(first['observations']['state'].numpy(),x[[0,0]])
    checks['history_ends_at_i']=np.array_equal(last['observations']['state'].numpy(),x[[3,4]])
    checks['action_begins_at_i']=np.array_equal(first['action'].numpy()[:5],y)
    checks['absolute_action_end_repeat']=np.array_equal(last['action'].numpy(),np.repeat(y[-1:],16,axis=0))
    t=load('workspace/qualification/phase1/p1_6_flow_preparation/trajectories/seed1000/trajectory.h5');x,y=examples(t)
    checks['canonical_loader_target_values']=np.array_equal(window(x,y,0)['action'][0].numpy(),y[0]) and y.shape==(len(t.transitions),8)
    checks['holds_have_examples']=len(x)==len(t.transitions) and t.hold_count>0

    class Actor(torch.nn.Module):
        def forward(self, obs, action):
            return torch.rand(())+action.square().mean()
    class Fake:
        device=torch.device('cpu')
        actor=Actor()
        step=0
        actor_optimizer=type('Optimizer',(),{'param_groups':[{'lr':.0001}]})()
        def _preprocess_obs(self,obs):return obs
        def normalize_action(self,action):return action
        def _batch_to_device(self,b):return b
        def train(self):self.actor.train()
        def update_actor(self,b):return {'loss_actor':2.0}
        def save(self,p,meta=None):pass
    f=Fake(); loader=DataLoader([window(x,y,0),window(x,y,1),window(x,y,2)],batch_size=2,shuffle=False)
    before=torch.get_rng_state().clone();v1=validation_loss(f,loader);after=torch.get_rng_state();v2=validation_loss(f,loader)
    checks['validation_rng_restored']=torch.equal(before,after)
    checks['validation_repeats_exactly']=v1['loss']==v2['loss'] and v1['samples']==3
    checkpoint_rows=[]
    summary=train_loop(f,loader,1001,str(root/'fake_instrumentation'),loader,
                       validation_callback=lambda agent,row: checkpoint_rows.append({'step':row['step'],'loss':row['loss']}))
    rows=[json.loads(s) for s in (root/'fake_instrumentation/training_metrics.jsonl').read_text().splitlines()]
    train=[r for r in rows if r['kind']=='train'];val=[r for r in rows if r['kind']=='validation']
    checks['train_100_and_final_partial']=len(train)==11 and train[-1]['window_steps']==1
    checks['full_validation_1000_and_final']=[v['step'] for v in val]==[0,1000,1001] and all(v['samples']==3 for v in val)
    checks['summary_schema']=summary['total_optimizer_steps']==1001 and summary['minimum_train_window_loss']==2.0
    checks['validation_checkpoint_callback_fixed_steps']=[r['step'] for r in checkpoint_rows]==[0,1000,1001]
    checks['validation_checkpoint_tie_selects_earliest']=min(checkpoint_rows,key=lambda r:(r['loss'],r['step']))['step']==0
    report={'schema':'flow-preparation-checks-v0','pass':all(checks.values()),'checks':checks,
            'instrumentation_updates':'fake constant loss; no model optimizer update','summary':summary}
    (root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
