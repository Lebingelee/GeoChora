"""Shared immutable profile/source context and diagnostic native-step audit."""
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import yaml
from ....assembly.source import TaskSceneSource
from ....tasks.pick_cube.timebase import build_timebase_candidate
from ....tasks.pick_cube.runtime_source import build_runtime_source
from ....tasks.pick_cube.readiness_solution import PickCubeReadinessConfig, PickCubeReadinessSolution
from ....controllers.canonical import ProductionCanonicalPandaController
from ....controllers.canonical.contracts import digest


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def label(profile):return profile.lower().replace('-','')


def context(root,profile):
    artifact=build_timebase_candidate(profile);source=build_runtime_source(artifact)
    source=replace(source,scene_source=TaskSceneSource((Path(root)/'approved_shared_source.xml').read_text(),source.scene_source.base_dir,source.scene_source.source_id))
    return artifact,source,PickCubeReadinessConfig.from_source(artifact,source)


def identities(root,profile):
    a,s,cfg=context(root,profile)
    return {'task_artifact':a.identity_hash,'controller':ProductionCanonicalPandaController.from_source(a,s).identity,
        'expert':PickCubeReadinessSolution(config=cfg).identity,'config':cfg.identity,
        'readiness':digest({'schema':'canonical-control-readiness-v1','policies':[p.to_mapping() for p in cfg.policies],
            'profile_identity':cfg.profile_identity,'config_identity':cfg.identity,
            'contract_source_sha256':hashlib.sha256(Path('task_env/controllers/canonical/readiness.py').read_bytes()).hexdigest()})}


def verify(root):
    root=Path(root);path=root/'multirate_spec.yaml';spec=yaml.safe_load(path.read_text())
    lock=json.loads((root/'multirate_spec_lock.json').read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest()!=lock['sha256']:raise ValueError('multirate spec changed')
    for path,value in {**spec['frozen_behavioral_sources'],**spec['implementation_source_hashes']}.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=value:raise ValueError('source changed after lock: '+path)
    return spec


class NativeAudit:
    """Observe native public step calls/hooks; never change provider computation."""
    def __init__(self,session,provider,timebase):
        self.session=session;self.provider=provider;self.timebase=timebase
        self.count=0;self.active=None;self.hashes=[];self.boundaries=[];self.restore=None
        if provider=='geophys':
            session._boundary._scheduler.add_hook(self)
        elif provider=='mujoco':
            owner=session._mj;native=owner.mj_step
            def step(*args,**kwargs):
                self.before();result=native(*args,**kwargs);self.after();return result
            owner.mj_step=step;self.restore=lambda:setattr(owner,'mj_step',native)
        elif provider in ('sapien','genesis'):
            owner=session._scene;native=owner.step
            def step(*args,**kwargs):
                self.before();result=native(*args,**kwargs);self.after();return result
            owner.step=step;self.restore=lambda:setattr(owner,'step',native)
        else:raise ValueError('unknown native audit provider')

    def before_substep(self,simulator,substep_id):self.before()
    def after_substep(self,simulator,substep_id):self.after()
    def before(self):
        if self.active is None:raise ValueError('hidden native step outside governed boundary')
        if self.active.identity_hash!=self.expected_hash:raise ValueError('target changed within boundary')
        self.hashes.append(self.active.identity_hash)
    def after(self):self.count+=1

    def step(self,target):
        self.active=target;self.expected_hash=target.identity_hash;before=self.count
        state=self.session.snapshot();self.hashes=[]
        try:after=self.session.step()
        finally:self.active=None
        observed=self.count-before;dt=after.simulation_time-state.simulation_time
        error=abs(dt-self.timebase.control_dt);bound=max(math.ulp(state.simulation_time),math.ulp(after.simulation_time),math.ulp(self.timebase.control_dt))
        row={'control_step':after.control_step,'simulation_time_s':after.simulation_time,'observed_native_substeps':observed,
            'requested_native_substeps':self.timebase.control_substeps,'target_hash':target.identity_hash,
            'all_substep_hashes_identical':len(self.hashes)==observed and all(h==target.identity_hash for h in self.hashes),
            'time_increment_s':dt,'time_increment_error_s':error,'existing_boundary_representation_bound_s':bound}
        self.boundaries.append(row)
        if observed!=self.timebase.control_substeps:raise ValueError('provider_native_substep_count')
        if after.control_step!=state.control_step+1 or error>bound:raise ValueError('canonical_timebase_alignment')
        if not row['all_substep_hashes_identical']:raise ValueError('ZOH target identity changed')
        return after

    def close(self):
        if self.restore:self.restore()
