"""Process-start guard used only by the explicitly selected pure checks."""
import builtins
import importlib.abc
import io
import os
from pathlib import Path
import sys

_ROOTS = tuple(Path(p).expanduser().resolve() for p in
               os.environ['GEOCHORA_PURE_GUARD_ROOTS'].split(os.pathsep) if p)
_BLOCKED = {'mujoco', 'taichi', 'isaacsim', 'isaaclab', 'omni', 'pxr', 'warp', 'carb', 'geophys'}


class _NoNative(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.partition('.')[0].lower() in _BLOCKED:
            raise RuntimeError(f'pure-check guard blocked native import: {fullname}')


if any(name.partition('.')[0].lower() in _BLOCKED for name in sys.modules):
    raise RuntimeError('native module already imported before pure-check guard')
sys.meta_path.insert(0, _NoNative())


def _guard(opener):
    def guarded(path, *args, **kwargs):
        if isinstance(path, (str, bytes, os.PathLike)):
            candidate = Path(os.fsdecode(path)).resolve()
            if any(candidate == root or candidate.is_relative_to(root) for root in _ROOTS):
                raise RuntimeError(f'pure-check guard blocked asset access: {candidate}')
        return opener(path, *args, **kwargs)
    return guarded


builtins.open = _guard(builtins.open)
io.open = _guard(io.open)
os.open = _guard(os.open)
READY = True
