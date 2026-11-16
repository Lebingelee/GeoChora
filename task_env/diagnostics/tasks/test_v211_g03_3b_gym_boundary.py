"""Worker value reconstruction can run without host-only Gymnasium spaces."""
import os
from pathlib import Path
import subprocess
import sys


def test_worker_import_without_gym_rejects_public_env_construction():
    root = Path(__file__).resolve().parents[3]
    code = r'''
import importlib.abc, sys
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, path=None, target=None):
  if fullname == 'gymnasium' or fullname.startswith('gymnasium.'):
   raise ModuleNotFoundError('test missing Gymnasium', name='gymnasium')
  if fullname.split('.')[0] in {'mujoco','taichi','taichi_forge','scene','solvers','geophys','isaacsim','omni','carb','pxr','warp'}:
   raise AssertionError('native import forbidden: ' + fullname)
sys.meta_path.insert(0, Block())
import task_env.runtime.sessions.worker
from task_env.environment.gym_compat import GYMNASIUM_AVAILABLE
from task_env.tasks.pick_cube.specialization import make_reference_binding
from task_env import make_env
assert not GYMNASIUM_AVAILABLE
value = make_reference_binding(controller_profile='r3_continuous_v1').build_seeded('mujoco','cpu',31,1000)
try:
 try: make_env('pick-cube-p16-reference-v1', config={'provider':'mujoco'})
 except ModuleNotFoundError as exc: assert exc.name == 'gymnasium'
 else: raise AssertionError('public Gym Env must reject missing dependency')
finally: value['source'].execution_source_receipt.close()
'''
    environment = dict(os.environ, PYTHONPATH=os.pathsep.join((str(root), str(root / 'GeoPhys/src'))),
                       PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run([sys.executable, '-c', code], env=environment, cwd=root,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_host_space_constructors_return_real_gymnasium_spaces():
    import gymnasium.spaces
    from task_env.environment.gym_compat import Box, Dict
    box = Box(-1.0, 1.0, (2,))
    space = Dict({'action': box})
    assert isinstance(box, gymnasium.spaces.Box)
    assert isinstance(space, gymnasium.spaces.Dict)
