import importlib.metadata,sys
from types import ModuleType,SimpleNamespace
import pytest
from task_env.runtime.sessions.isaac_native_io import IsaacSimAppOwnerV1

def modules(monkeypatch,runtime):
 app=SimpleNamespace(close=lambda:None)
 isaac=ModuleType('isaacsim');isaac.__path__=[]
 core=ModuleType('isaacsim.core');core.__path__=[]
 version=ModuleType('isaacsim.core.version');version.get_version=lambda:(runtime,'rc.14','6','2','0','rc','14','release.52805')
 simulation=ModuleType('isaacsim.simulation_app');simulation.SimulationApp=lambda options:app
 carb=ModuleType('carb');carb.settings=SimpleNamespace(get_settings=lambda:SimpleNamespace(get_as_int=lambda _:4))
 for name,value in [('isaacsim',isaac),('isaacsim.core',core),('isaacsim.core.version',version),('isaacsim.simulation_app',simulation),('carb',carb)]:monkeypatch.setitem(sys.modules,name,value)
 return app

@pytest.mark.parametrize('raw,runtime',[('6.1.0.0','6.1.0'),('6.2.0.0','6.2.0')])
def test_f06_app_owner_checks_runtime_and_retains_raw(monkeypatch,raw,runtime):
 app=modules(monkeypatch,runtime)
 monkeypatch.setattr(importlib.metadata,'version',lambda _:raw)
 monkeypatch.setenv('GEOCHORA_SELECTED_ISAAC_VERSION',raw)
 monkeypatch.delenv('GEOCHORA_SELECTED_ISAAC_ROOT',raising=False)
 owner=IsaacSimAppOwnerV1()
 assert owner.open(f06_compatibility=True) is app
 assert owner.sdk_identity['normalized_version']==raw
 assert owner.sdk_runtime_version_raw[0]==runtime
 owner.close()

def test_f06_app_version_conflict_closes_owned_app(monkeypatch):
 app=modules(monkeypatch,'6.1.0');closed=[];app.close=lambda:closed.append(True)
 monkeypatch.setattr(importlib.metadata,'version',lambda _:'6.2.0.0')
 monkeypatch.setenv('GEOCHORA_SELECTED_ISAAC_VERSION','6.2.0.0')
 monkeypatch.delenv('GEOCHORA_SELECTED_ISAAC_ROOT',raising=False)
 owner=IsaacSimAppOwnerV1()
 with pytest.raises(RuntimeError,match='conflicts'):
  owner.open(f06_compatibility=True)
 assert closed==[True]

def test_f06_app_without_pip_uses_root_version(monkeypatch,tmp_path):
 modules(monkeypatch,'6.2.0');(tmp_path/'VERSION').write_text('6.2.0-rc.14+release.52805')
 def absent(_):raise importlib.metadata.PackageNotFoundError
 monkeypatch.setattr(importlib.metadata,'version',absent)
 monkeypatch.setenv('GEOCHORA_SELECTED_ISAAC_ROOT',str(tmp_path))
 monkeypatch.setenv('GEOCHORA_SELECTED_ISAAC_VERSION','6.2.0.0')
 owner=IsaacSimAppOwnerV1();owner.open(f06_compatibility=True)
 assert owner.sdk_identity['pip_version_raw'] is None
 assert owner.sdk_identity['sdk_version_raw']=='6.2.0-rc.14+release.52805'
 owner.close()

def test_f06_app_rejects_different_runtime_build(monkeypatch,tmp_path):
 app=modules(monkeypatch,'6.2.0');closed=[];app.close=lambda:closed.append(True)
 (tmp_path/'VERSION').write_text('6.2.0-rc.15+release.52805')
 monkeypatch.setattr(importlib.metadata,'version',lambda _:'6.2.0.0')
 monkeypatch.setenv('GEOCHORA_SELECTED_ISAAC_ROOT',str(tmp_path))
 monkeypatch.setenv('GEOCHORA_SELECTED_ISAAC_VERSION','6.2.0.0')
 owner=IsaacSimAppOwnerV1()
 with pytest.raises(RuntimeError,match='build conflicts'):
  owner.open(f06_compatibility=True)
 assert closed==[True]

def test_f06_app_rejects_runtime_module_source_conflict(monkeypatch,tmp_path):
 app=modules(monkeypatch,'6.2.0');closed=[];app.close=lambda:closed.append(True)
 sys.modules['isaacsim'].__file__=str(tmp_path/'different'/'__init__.py')
 monkeypatch.setattr(importlib.metadata,'version',lambda _:'6.2.0.0')
 monkeypatch.setenv('GEOCHORA_SELECTED_ISAAC_ORIGIN',str(tmp_path/'expected'/'__init__.py'))
 monkeypatch.setenv('GEOCHORA_SELECTED_ISAAC_VERSION','6.2.0.0')
 monkeypatch.delenv('GEOCHORA_SELECTED_ISAAC_ROOT',raising=False)
 owner=IsaacSimAppOwnerV1()
 with pytest.raises(RuntimeError,match='module source conflicts'):
  owner.open(f06_compatibility=True)
 assert closed==[True]

def test_f06_public_model_consumer_reads_tensor_values_and_rejects_missing_api():
 import numpy as np
 from task_env.runtime.sessions.isaac_native_io import _read_f06_public_physical_model
 class Array:
  def __init__(self, value):self.value=np.asarray(value)
  def numpy(self):return self.value
 art=SimpleNamespace(link_names=['link1'],is_physics_tensor_entity_valid=lambda:True,
   get_link_masses=lambda:Array([[2.0]]),
   get_link_coms=lambda:(Array([[[0.1,0.2,0.3]]]),Array([[[1,0,0,0]]])),
   get_link_inertias=lambda:Array([[[1,2,3,4,5,6,7,8,9]]]))
 body=SimpleNamespace(is_physics_tensor_entity_valid=lambda:True,
   get_masses=lambda:Array([[0.08]]),get_coms=lambda:(Array([[0,0,0]]),Array([[1,0,0,0]])),
   get_inertias=lambda:Array([[1,0,0,0,1,0,0,0,1]]))
 facts=_read_f06_public_physical_model(art,{'cube-v1':body})
 assert facts['links'][0]['inertia_body_at_com_kg_m2']==[[1,4,7],[2,5,8],[3,6,9]]
 assert facts['free_bodies']['cube-v1']['mass_kg']==0.08
 del body.get_inertias
 with pytest.raises(ValueError,match='get_inertias'):
  _read_f06_public_physical_model(art,{'cube-v1':body})

def test_f06_authored_usd_never_promotes_defaults_to_declarations():
 from task_env.runtime.sessions.isaac_native_io import _read_f06_authored_mass_properties
 class Attr:
  def __init__(self,authored,value):self.authored,self.value=authored,value
  def HasAuthoredValueOpinion(self):return self.authored
  def Get(self):return self.value
 class Quat:
  def GetReal(self):return 1.0
  def GetImaginary(self):return [0,0,0]
 class API:
  def __init__(self,_prim):pass
  def GetMassAttr(self):return Attr(True,0.08)
  def GetCenterOfMassAttr(self):return Attr(False,[0,0,0])
  def GetDiagonalInertiaAttr(self):return Attr(True,[1,2,3])
  def GetPrincipalAxesAttr(self):return Attr(True,Quat())
 prim=SimpleNamespace(IsValid=lambda:True,HasAPI=lambda _:True)
 stage=SimpleNamespace(GetPrimAtPath=lambda _path:prim)
 facts=_read_f06_authored_mass_properties(stage,{'cube-v1':'/World/Cube'},SimpleNamespace(MassAPI=API))
 assert facts['cube-v1']['mass_kg']=={'authored':True,'value':0.08}
 assert facts['cube-v1']['center_of_mass_m']=={'authored':False,'value':None}
 assert facts['cube-v1']['principal_axes_wxyz']['value']==[1.0,0.0,0.0,0.0]

@pytest.mark.parametrize('source_fails',[False,True])
def test_f06_worker_opens_app_before_source_and_closes_owner(monkeypatch,source_fails):
 from task_env.runtime.sessions import worker, isaac_native_io
 events=[]
 class Socket:
  def close(self):events.append('socket_close')
 class Owner:
  def open(self,*,f06_compatibility):
   assert f06_compatibility is True;events.append('app_open')
  def close(self):events.append('app_close')
 payload={'uid':'pick-cube-p16-reference-v1','selection':{'physics_provider':'isaacsim'}}
 request={'kind':'build','payload':payload,'request_identity':worker.request_identity(payload)}
 monkeypatch.setattr(worker.socket,'socket',lambda **_:Socket())
 monkeypatch.setattr(worker.sys,'argv',['worker','1'])
 monkeypatch.setattr(worker,'_receive',lambda _:request)
 monkeypatch.setattr(worker,'_send',lambda _sock,reply:events.append(reply['kind']))
 monkeypatch.setattr(worker,'_validate_environment',lambda _payload:events.append('validate'))
 monkeypatch.setattr(isaac_native_io,'_process_app_owner',lambda **_:Owner())
 def materialize(_payload):
  events.append('source')
  if source_fails:raise ValueError('source failure')
  return object(),{},None
 monkeypatch.setattr(worker,'_materialize_selected',materialize)
 monkeypatch.setattr(worker,'serve_session',lambda *_args,**_kwargs:events.append('serve'))
 worker.main()
 assert events[:3]==['validate','app_open','source']
 assert ('startup_error' in events)==source_fails
 assert events[-2:]==['app_close','socket_close']
