"""Episode lifecycle does not require optional offline H5 tooling."""
import subprocess
import sys


def test_episode_contract_import_does_not_load_h5py():
    script = '''
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == 'h5py' or name.startswith('h5py.'):
        raise AssertionError('episode contract must not load h5py')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from task_env.trajectory.canonical.episode import make_episode_end_v1
assert callable(make_episode_end_v1)
'''
    subprocess.run([sys.executable, '-c', script], check=True)


def test_offline_exports_remain_available():
    from task_env.trajectory import inspect_trajectory
    from task_env.trajectory.processing import inspect_trajectory as implementation
    assert inspect_trajectory is implementation
