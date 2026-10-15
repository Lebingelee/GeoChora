"""T01/T09: isolated import and dispatch contracts, without native runtimes.

Each subprocess has a 30 s timeout and 512 MiB address-space limit. Native
imports are rejected, including attempted imports, rather than just checking
sys.modules after an operation. No renderer availability/qualification claim.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[3]
ADAPTERS = ("raytracer", "rasterizer", "flora")
ALIASES = (*ADAPTERS, "mujoco_reference", "mujoco", "external_mujoco")


def _expected_descriptor(name):
    """Independent pre-M1 value oracle, not derived from the registry."""
    capabilities = {
        "supports_human": True,
        "supports_rgb_array": True,
        "supports_parallel": True,
        "supports_asset_instancing": False,
        "supports_shared_asset_table": False,
        "supports_gpu_geometry_instancing": False,
        "supports_batch_transform_update": False,
        "transform_transport": "unknown",
        "output_transport": "geophys_framebuffer",
    }
    if name == "raytracer":
        capabilities.update(
            supports_asset_instancing=True, supports_shared_asset_table=True,
            supports_gpu_geometry_instancing=True, supports_batch_transform_update=True,
            transform_transport="device_world_major",
        )
        implementation = "task_env.render.raytracer.backend.RaytracerRenderBackend"
    elif name == "rasterizer":
        capabilities["transform_transport"] = "device_world_major"
        implementation = "task_env.render.rasterizer.backend.RasterizerRenderBackend"
    elif name == "flora":
        capabilities.update(supports_asset_instancing=True, output_transport="external_host_rgba8")
        implementation = "task_env.render.flora.backend.FloraRenderBackend"
    else:
        name = "mujoco_reference"
        capabilities.update(supports_parallel=False, output_transport="external_reference")
        implementation = "task_env.render.base.backend.LegacyReferenceRenderBackend"
    return {"name": name, "capabilities": capabilities, "implementation": implementation}


def _fresh(body, *, selected=()):
    prelude = """
import resource
resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
import importlib.abc
import json
import sys
native = {'geophys', 'visualization', 'taichi', 'flora', 'flora_backend',
          'FloraRenderPyNative', 'solvers', 'scene', 'geometry', 'runtime',
          'mujoco', 'sapien', 'genesis', 'torch', 'triton'}
attempts = []
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        parts = fullname.split('.')
        adapter = (len(parts) > 2 and parts[:2] == ['task_env', 'render']
                   and parts[2] in {'raytracer', 'rasterizer', 'flora'})
        if parts[0] in native or (adapter and parts[2] not in selected):
            attempts.append(fullname)
            raise AssertionError('forbidden import: ' + fullname)
sys.meta_path.insert(0, Guard())
"""
    epilogue = """
assert not attempts, attempts
assert not sorted(n for n in sys.modules if n.split('.')[0] in native)
"""
    code = "selected = " + repr(tuple(selected)) + "\n" + prelude + textwrap.dedent(body) + epilogue
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1",
               OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                            text=True, capture_output=True, timeout=30)
    if result.returncode:
        raise AssertionError(f"isolated worker failed ({result.returncode}):\n{result.stdout}\n{result.stderr}")
    return json.loads(result.stdout) if result.stdout.strip() else None


class BackendRegistryContractTests(unittest.TestCase):
    def test_metadata_discovery_and_compatibility_exports(self):
        result = _fresh("""
            from dataclasses import FrozenInstanceError
            import task_env
            import task_env.render as public
            from task_env.render.backend import available_render_backends
            from task_env.render.base import RenderBackendDescriptor, RenderBackendCapabilities
            from task_env.render.contracts import RenderMode
            from task_env.render.processing import RenderBuildRequest
            from task_env.render.tools import normalize_render_backend
            descriptors = available_render_backends()
            assert isinstance(descriptors, tuple)
            assert public.RenderBackendDescriptor is RenderBackendDescriptor
            assert public.RenderBackendCapabilities is RenderBackendCapabilities
            assert public.RenderBuildRequest is RenderBuildRequest
            assert task_env.RenderMode is RenderMode
            assert normalize_render_backend('RASTERIZER') == 'rasterizer'
            try:
                descriptors[0].name = 'changed'
            except FrozenInstanceError:
                pass
            else:
                raise AssertionError('descriptor must remain immutable')
            print(json.dumps([d.describe() for d in descriptors]))
        """)
        self.assertEqual(result, [_expected_descriptor(n) for n in ADAPTERS])

    def test_alias_normalization_and_unknown_name(self):
        result = _fresh("""
            from task_env.render import normalize_render_backend, create_render_backend, RenderBackendName
            names = ('raytracer', 'rasterizer', 'flora', 'mujoco_reference', 'mujoco', 'external_mujoco')
            assert normalize_render_backend(RenderBackendName.RAYTRACER) == 'raytracer'
            class Value:
                value = ' FLORA '
            assert normalize_render_backend(Value()) == 'flora'
            for operation in (normalize_render_backend, create_render_backend):
                for value in (' unknown ', '', None):
                    try:
                        operation(value)
                    except ValueError as error:
                        normalized = str(value).strip().lower()
                        assert str(error) == (f"unsupported task_env render backend {normalized!r}; "
                                              "expected one of: raytracer, rasterizer, flora")
                    else:
                        raise AssertionError('unsupported name accepted')
            print(json.dumps([normalize_render_backend(' ' + n.upper() + ' ') for n in names]))
        """)
        self.assertEqual(result, list(ALIASES))

    def test_only_selected_backend_is_imported_and_constructed(self):
        for name in ALIASES:
            with self.subTest(backend=name):
                result = _fresh(f"""
                    from task_env.render import create_render_backend, RenderBackend
                    a = create_render_backend({name!r})
                    b = create_render_backend({name!r})
                    assert a is not b and isinstance(a, RenderBackend)
                    assert a.source_backend_name == a.name
                    assert a.descriptor.implementation == type(a).__module__ + '.' + type(a).__qualname__
                    print(json.dumps(a.descriptor.describe()))
                """, selected=(name,) if name in ADAPTERS else ())
                self.assertEqual(result, _expected_descriptor(name))

    def test_request_defaults_overrides_and_validation(self):
        result = _fresh("""
            from task_env.render import RenderBuildRequest
            default = RenderBuildRequest.from_config(object())
            configured = default.with_overrides(backend=' MUJOCO ', width='123', height=45,
                render_preset=' custom ', render_preset_overrides={'samples': 2},
                use_render_snapshot=False, render_snapshot_consumer=' live ')
            assert configured.backend == 'mujoco' and configured.width == 123
            assert configured.height == 45 and configured.render_preset == 'custom'
            assert configured.render_snapshot_consumer == 'live'
            assert configured.visualizer_kwargs() == {'width': 123, 'height': 45,
                'render_preset': 'custom', 'render_preset_overrides': {'samples': 2},
                'use_render_snapshot': False, 'render_snapshot_consumer': 'live'}
            for overrides, message in (({'width': 0}, 'render width and height must be positive'),
                ({'height': -1}, 'render width and height must be positive'),
                ({'render_preset': ' '}, 'render_preset cannot be empty'),
                ({'render_snapshot_consumer': 'bad'}, "render_snapshot_consumer must be 'slot' or 'live'")):
                try:
                    default.with_overrides(**overrides)
                except ValueError as error:
                    assert str(error) == message
                else:
                    raise AssertionError('invalid request accepted')
            try:
                default.with_overrides(unknown=1)
            except TypeError as error:
                assert str(error) == "unknown render build request fields: ['unknown']"
            else:
                raise AssertionError('unknown request field accepted')
            print(json.dumps(default.describe()))
        """)
        self.assertEqual(result, {
            "schema": "task_env.render_build_request.v1", "backend": "raytracer",
            "width": 640, "height": 480, "render_preset": "interactive",
            "render_preset_overrides": None, "use_render_snapshot": None,
            "render_snapshot_consumer": "slot",
        })

    def test_public_signatures_and_descriptor_fields(self):
        result = _fresh("""
            import inspect
            from dataclasses import fields
            from task_env.render import (normalize_render_backend, available_render_backends,
                create_render_backend, RenderBuildRequest, RenderProcessor, RenderBackendDescriptor)
            assert [f.name for f in fields(RenderBackendDescriptor)] == ['name', 'capabilities', 'implementation']
            print(json.dumps({f.__name__: str(inspect.signature(f)) for f in (
                normalize_render_backend, available_render_backends, create_render_backend,
                RenderBuildRequest, RenderProcessor)}))
        """)
        self.assertEqual(result, {
            "normalize_render_backend": "(value: 'str | RenderBackendName') -> 'str'",
            "available_render_backends": "() -> 'tuple[RenderBackendDescriptor, ...]'",
            "create_render_backend": "(value: 'str | RenderBackendName') -> 'RenderBackend'",
            "RenderBuildRequest": "(backend: 'str', width: 'int', height: 'int', render_preset: 'str', "
                "render_preset_overrides: 'Mapping[str, object] | None' = None, "
                "use_render_snapshot: 'bool | None' = None, render_snapshot_consumer: 'str' = 'slot') -> None",
            "RenderProcessor": "(config: 'object', *, backend: 'str | None' = None) -> 'None'",
        })

    def test_processor_override_dispatch_and_source_error_contract(self):
        _fresh("""
            from types import SimpleNamespace
            from task_env.render import RenderProcessor, RenderBackendBuildError
            class Source:
                def __init__(self): self.calls = []
                def build_visualizer(self, **kwargs):
                    self.calls.append(kwargs)
                    return kwargs
            source = Source()
            processor = RenderProcessor(SimpleNamespace(backend='rasterizer'))
            backend = processor.backend
            assert processor.describe()['backend'] == backend.descriptor.describe()
            result = processor.build_visualizer(source, width=80,
                visualizer_kwargs={'width': 99, 'backend': 'must_be_overridden'})
            assert result['width'] == 99 and result['backend'] == 'rasterizer'
            result = processor.build_visualizer(source, backend='external_mujoco')
            assert result['backend'] == 'mujoco_reference'
            assert len(source.calls) == 2
            assert processor.backend is backend and processor.request.width == 640
            try:
                processor.build_visualizer(object())
            except RenderBackendBuildError as error:
                assert str(error) == "render source does not expose build_visualizer() for backend 'rasterizer'"
            else:
                raise AssertionError('missing factory accepted')
            class Broken:
                def build_visualizer(self, **kwargs): raise RuntimeError('source failure')
            try:
                processor.build_visualizer(Broken())
            except RenderBackendBuildError as error:
                assert str(error) == "failed to build TaskEnv render backend 'rasterizer': source failure"
                assert isinstance(error.__cause__, RuntimeError)
            else:
                raise AssertionError('source failure swallowed')
        """, selected=("rasterizer",))

    def test_backend_contract_smoke_uses_real_adapters_with_native_endpoints_substituted(self):
        result = _fresh("""
            from task_env.diagnostics.render.backend_contract import run_backend_contract_smoke
            print(json.dumps(run_backend_contract_smoke()))
        """, selected=ADAPTERS)
        self.assertEqual(result["backends"], list(ADAPTERS))
        self.assertEqual(result["source_calls"], {
            n: {"backend": n, "width": 320, "height": 240} for n in ADAPTERS
        })

    def test_raytracer_real_scene_builder_snapshot_wiring(self):
        _fresh("""
            from types import ModuleType, SimpleNamespace
            from unittest.mock import patch
            from task_env.render import RenderBuildRequest, create_render_backend, RenderBackendBuildError
            calls = []
            publishers = []
            snapshot_source = object()
            binding = SimpleNamespace(snapshot_source=snapshot_source, publisher=object())
            visualization = ModuleType('visualization'); visualization.__path__ = []
            snapshots = ModuleType('visualization.snapshot_source')
            def bind(source, *, consumer_mode):
                calls.append((source, consumer_mode))
                return binding
            snapshots.create_scene_render_snapshot_binding = bind
            module = ModuleType('task_env.render.raytracer.visualizer')
            class Visualizer:
                def __init__(self, source, **kwargs): self.source, self.kwargs = source, kwargs
                def set_render_snapshot_publisher(self, publisher): publishers.append(publisher)
            module.RaytracerSceneVisualizer = Visualizer
            class Source:
                def __init__(self): self.representations = []
                def _apply_build_representation(self, value): self.representations.append(value)
                def _can_use_render_snapshot(self): return True
                def build_visualizer(self, **kwargs): raise AssertionError('wrong raytracer route')
            source = Source()
            request = RenderBuildRequest.from_config(object())
            with patch.dict(sys.modules, {visualization.__name__: visualization,
                snapshots.__name__: snapshots, module.__name__: module}):
                backend = create_render_backend('raytracer')
                visualizer = backend.create_visualizer(source, request=request,
                    visualizer_kwargs={'representation': 'surface', 'width': 17})
                assert calls == [(source, 'slot')] and publishers == [binding.publisher]
                assert visualizer.source is snapshot_source
                assert visualizer.kwargs == {'width': 17, 'height': 480,
                    'render_preset': 'interactive', 'render_preset_overrides': None}
                assert source.representations == ['surface']
                # The actual adapter preserves wrapping and already-wrapped errors.
                import task_env.render.raytracer.scene as scene
                with patch.object(scene, 'build_raytracer_visualizer', side_effect=RuntimeError('native failure')):
                    try: backend.create_visualizer(source, request=request)
                    except RenderBackendBuildError as error:
                        assert str(error) == 'failed to build TaskEnv RayTracer backend: native failure'
                    else: raise AssertionError('raytracer failure swallowed')
                original = RenderBackendBuildError('already wrapped')
                with patch.object(scene, 'build_raytracer_visualizer', side_effect=original):
                    try: backend.create_visualizer(source, request=request)
                    except RenderBackendBuildError as error: assert error is original
                    else: raise AssertionError('wrapped failure swallowed')
        """, selected=("raytracer",))

    def test_lazy_package_exports_preserve_identity(self):
        _fresh("""
            from types import ModuleType
            from unittest.mock import patch
            import task_env.render.raytracer as raytracer
            import task_env.render.flora as flora
            import task_env.render.tools as tools
            for package, exports in ((raytracer, {'build_raytracer_visualizer': '.scene',
                    'RaytracerSceneVisualizer': '.visualizer'}),
                (flora, {'FloraSceneBundle': '.assets', 'build_scene_file_from_assemblies': '.assets',
                    'build_scene_file_from_mjcf': '.assets', 'build_scene_file_from_render_scene': '.assets',
                    'FloraRuntimeConfig': '.runtime', 'FloraRuntimeProbe': '.runtime',
                    'load_flora_backend': '.runtime', 'probe_flora_runtime': '.runtime',
                    'FloraScene': '.scene', 'build_flora_scene_from_source': '.scene',
                    'FloraParallelVisualizer': '.parallel'}),
                (tools, {'CameraPoseSink': '.camera', 'InteractiveCameraController': '.camera'})):
                modules = {}
                for name, suffix in exports.items():
                    path = package.__name__ + suffix
                    module = modules.setdefault(path, ModuleType(path))
                    setattr(module, name, object())
                with patch.dict(sys.modules, modules):
                    for name, suffix in exports.items():
                        assert name in package.__all__
                        expected = getattr(modules[package.__name__ + suffix], name)
                        assert getattr(package, name) is expected
                        assert getattr(package, name) is expected
                try: getattr(package, 'unknown_export')
                except AttributeError: pass
                else: raise AssertionError('unknown package export accepted')
        """, selected=("raytracer", "flora"))


if __name__ == "__main__":
    unittest.main()
