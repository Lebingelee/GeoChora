"""GeoChora-owned import route with legacy top-level package compatibility.

The qualified spelling aliases legacy submodules rather than executing them twice.
No optional agent implementation is imported by this bridge.
"""
import importlib
import importlib.abc
import importlib.util
import sys

_QUALIFIED = "task_env.alg.agent_factory"
_root = sys.modules[__name__]
for _name in (_QUALIFIED, "agent_factory"):
    if _name in sys.modules and sys.modules[_name] is not _root:
        raise ImportError("agent_factory package name is already owned by another package")
    sys.modules[_name] = _root

class _AliasLoader(importlib.abc.Loader):
    def __init__(self, target):
        self.target = target
    def create_module(self, spec):
        return importlib.import_module(self.target)
    def exec_module(self, module):
        pass

class _AliasFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(_QUALIFIED + "."):
            legacy = "agent_factory" + fullname[len(_QUALIFIED):]
            spec = importlib.util.find_spec(legacy)
            if spec is not None:
                return importlib.util.spec_from_loader(fullname, _AliasLoader(legacy),
                    is_package=spec.submodule_search_locations is not None)
        return None

sys.meta_path.insert(0, _AliasFinder())
