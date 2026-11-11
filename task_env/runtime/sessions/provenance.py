"""Mechanically identify the selected provider without constructing its runtime."""
from importlib import metadata, util
from pathlib import Path
import hashlib
import os
import signal
import subprocess
import sys


def resolve_isaac_sdk_identity(*, pip_version=None, sdk_root=None):
    """Identify supported SDK releases from explicit metadata, preserving raw text.

    The source representation's build is a separate identity from the runtime.
    An SDK directory name is never treated as a version declaration.
    """
    import re
    from packaging.version import InvalidVersion, Version

    version_file = None
    if sdk_root is not None:
        path = Path(sdk_root).expanduser().absolute() / 'VERSION'
        if path.is_file():
            version_file = path.read_text(encoding='utf-8').strip()
    def parse(raw, *, label):
        if raw is None:
            return None
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f'empty Isaac {label} version')
        if label == 'distribution' and re.search(r'(?i)(?:rc|alpha|beta|preview)', raw):
            raise ValueError(f'Isaac {label} pre-release is not admitted')
        match = (re.fullmatch(r'\d+(?:\.\d+){2,}', raw.strip())
                 if label == 'distribution' else
                 re.search(r'(?<!\d)(\d+(?:\.\d+){2,})(?![\d.])', raw))
        if match is None:
            raise ValueError(f'cannot parse Isaac {label} version')
        try:
            version = Version(match.group(0) if label == 'distribution' else match.group(1))
        except InvalidVersion as exc:
            raise ValueError(f'invalid Isaac {label} version') from exc
        release = version.release
        if any(release[3:]):
            raise ValueError(f'unsupported Isaac {label} release: {raw}')
        return tuple((release + (0, 0, 0))[:3])
    pip = parse(pip_version, label='distribution')
    installed = parse(version_file, label='SDK VERSION')
    if pip is not None and installed is not None and pip != installed:
        raise ValueError('Isaac distribution and SDK VERSION conflict')
    resolved = pip or installed
    if resolved not in {(6, 1, 0), (6, 2, 0)}:
        raise ValueError('Isaac SDK release is missing or not admitted')
    return {'schema_version': 'isaac-sdk-identity-v1',
            'normalized_version': '.'.join(map(str, resolved)) + '.0',
            'pip_version_raw': pip_version, 'sdk_version_raw': version_file,
            'sdk_root': None if sdk_root is None else str(Path(sdk_root).expanduser().absolute())}


def provider_build_identity(provider):
    if provider not in ('geophys', 'mujoco', 'sapien', 'genesis'):
        raise ValueError('unknown provider')
    spec = util.find_spec(provider)
    if spec is None or spec.origin is None:
        raise ValueError(f'{provider} import source unavailable')
    origin = Path(spec.origin).resolve()
    try:
        package_version = metadata.version('genesis-world' if provider == 'genesis' else provider)
    except metadata.PackageNotFoundError:
        package_version = None
    revision = None
    dirty = None
    if provider == 'geophys':
        try:
            revision = subprocess.check_output(['git', '-C', str(origin.parent), 'rev-parse', 'HEAD'], text=True).strip()
            # Include tracked changes and nonignored untracked content in a dirty
            # build fingerprint, rather than reporting a clean commit for them.
            status = subprocess.check_output(['git', '-C', str(origin.parent), 'status', '--porcelain'], text=True)
            if status:
                tree = Path(subprocess.check_output(['git', '-C', str(origin.parent), 'rev-parse', '--show-toplevel'], text=True).strip())
                names = subprocess.check_output(['git', '-C', str(tree), 'ls-files', '-z', '--cached', '--others', '--exclude-standard']).split(b'\0')
                digest = hashlib.sha256()
                for name in sorted(n for n in names if n):
                    path = tree / name.decode()
                    digest.update(name)
                    if path.is_file():
                        digest.update(hashlib.sha256(path.read_bytes()).digest())
                dirty = digest.hexdigest()
        except (subprocess.CalledProcessError, FileNotFoundError):
            if package_version is None:
                raise ValueError('GeoPhys build has neither checkout nor package version')
    if revision is None and package_version is None:
        raise ValueError(f'{provider} build has neither checkout nor package version')
    manifest_version = ('git:' + revision + (':dirty:' + dirty if dirty else '')
                        if revision else 'package:' + package_version)
    return {'provider': provider, 'package_version': package_version,
            'repository_revision': revision, 'dirty_build_sha256': dirty,
            'import_origin': str(origin), 'origin_sha256': hashlib.sha256(origin.read_bytes()).hexdigest(),
            'manifest_version': manifest_version}


def provider_module_origins(provider, module_names=('control', 'geophys', 'scene', 'simulation', 'solvers')):
    """Report the resolved sibling package origins for a bounded GeoPhys run.

    Already-imported modules use their live ``__file__`` so the receipt binds
    the modules consumed by this process. A package not yet imported uses its
    normal import spec, allowing startup checks before first materialization.
    This diagnostic does not establish a capability or replace build identity.
    """
    if provider != 'geophys':
        raise ValueError('module-origin inventory is currently defined only for geophys')
    names = tuple(module_names)
    if not names or any(not isinstance(name, str) or not name for name in names):
        raise ValueError('module_names must be a nonempty sequence of package names')
    origins = {}
    for name in names:
        module = sys.modules.get(name)
        raw_origin = getattr(module, '__file__', None) if module is not None else None
        if raw_origin is None:
            spec = util.find_spec(name)
            raw_origin = None if spec is None else spec.origin
        if raw_origin is None:
            raise ValueError(f'{name} import source unavailable')
        origins[name] = str(Path(raw_origin).resolve())
    return origins

# The probe executes only standard-library code in the requested interpreter.
# Paths are inserted exactly as they will be for a source checkout worker;
# find_spec on these top-level packages does not import the packages.
_ENVIRONMENT_METADATA_PROBE = r'''
import importlib.metadata as metadata
import importlib.util as util
import json, os, pathlib, sys, sysconfig
from importlib.abc import MetaPathFinder
from importlib.machinery import PathFinder

class BlockNative(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'mujoco', 'taichi', 'taichi_forge', 'scene', 'solvers', 'geophys', 'isaacsim', 'omni', 'carb', 'pxr', 'isaaclab', 'sapien', 'genesis', 'warp'}:
            raise RuntimeError('native import forbidden: ' + fullname)
sys.meta_path.insert(0, BlockNative())
core, geophys, launcher_mode = sys.argv[1:4]
# -S suppresses site hooks/.pth code. Query this interpreter's environment
# directories directly, without executing installed package code.
prefix = str(pathlib.Path(sys.executable).parent.parent)
paths = sysconfig.get_paths(vars={'base': prefix, 'platbase': prefix})
launcher_paths = ([str(pathlib.Path(item).resolve()) for item in os.environ.get('PYTHONPATH', '').split(os.pathsep) if item]
                  if launcher_mode == 'launcher' else [])
sys.path[:0] = [core, geophys, *launcher_paths, paths['purelib'], paths['platlib']]
origins = {}
for name in ('task_env', 'geophys', 'scene', 'control', 'simulation', 'solvers'):
    spec = PathFinder.find_spec(name, sys.path)
    origins[name] = None if spec is None or spec.origin is None else str(pathlib.Path(spec.origin).resolve())
versions = {}
for name in ('numpy', 'scipy', 'psutil', 'pydantic', 'taichi-forge', 'trimesh', 'pyvista', 'Pillow', 'mujoco', 'geophys', 'isaacsim', 'gymnasium', 'h5py', 'PyYAML', 'packaging'):
    try:
        versions[name] = metadata.version(name)
    except metadata.PackageNotFoundError:
        versions[name] = None
modules = {'numpy':'numpy', 'scipy':'scipy', 'psutil':'psutil', 'pydantic':'pydantic',
           'taichi-forge':'taichi_forge', 'trimesh':'trimesh', 'pyvista':'pyvista',
           'Pillow':'PIL', 'mujoco':'mujoco', 'gymnasium':'gymnasium',
           'h5py':'h5py', 'PyYAML':'yaml', 'isaacsim':'isaacsim', 'packaging':'packaging'}
module_origins, origin_ownership = {}, {}
isaacsim_namespace_owner = None
for distribution, name in modules.items():
    spec = PathFinder.find_spec(name, sys.path)
    origin = None if spec is None else spec.origin
    if origin is None and spec is not None and spec.submodule_search_locations:
        origin = list(spec.submodule_search_locations)[0]
    origin = None if origin is None else pathlib.Path(origin).resolve()
    module_origins[distribution] = None if origin is None else str(origin)
    if origin is None:
        origin_ownership[distribution] = 'missing'
        continue
    try:
        dist = metadata.distribution(distribution)
        files = dist.files
        if files is None:
            origin_ownership[distribution] = 'unknown'
            continue
        relative = origin.relative_to(pathlib.Path(dist.locate_file('')).resolve()).as_posix()
        names = {str(item).replace('\\', '/') for item in files}
        owned = relative in names or any(item.startswith(relative + '/') for item in names)
        if distribution == 'isaacsim' and not owned:
            try:
                kernel = metadata.distribution('isaacsim-kernel')
                kernel_base = pathlib.Path(kernel.locate_file('')).resolve()
                kernel_relative = origin.relative_to(kernel_base).as_posix()
                kernel_files = {str(item).replace('\\', '/') for item in (kernel.files or ())}
                if kernel.version == dist.version and kernel_relative in kernel_files:
                    owned = True
                    isaacsim_namespace_owner = 'isaacsim-kernel'
            except (metadata.PackageNotFoundError, ValueError):
                pass
        origin_ownership[distribution] = 'owned' if owned else 'mismatch'
    except metadata.PackageNotFoundError:
        origin_ownership[distribution] = 'unknown'
    except ValueError:
        origin_ownership[distribution] = 'mismatch'
print('GEOCHORA_METADATA_V1:' + json.dumps({'python': str(pathlib.Path(sys.executable).resolve()),
                  'launcher_pythonpath': launcher_paths,
                  'worker_executable': str(pathlib.Path(sys.executable).absolute()),
                  'python_version': list(sys.version_info[:3]), 'origins': origins,
                  'versions': versions, 'module_origins': module_origins,
                  'origin_ownership': origin_ownership,
                  'isaacsim_namespace_owner': isaacsim_namespace_owner}, sort_keys=True))
'''


def probe_interpreter_environment(python, *, core_root=None, geophys_src=None):
    """Read source origins and package metadata without importing native modules.

    This is an inventory, not admission or evidence of native availability.
    Only the current Core and its GeoPhys source are permitted.  The caller
    must separately check route-specific dependencies and build requirements.
    """
    from ...utils._paths import GEOCHORA_ROOT, GEOPHYS_PROVIDER_ROOT

    expected_core = GEOCHORA_ROOT.resolve()
    expected_geophys = (GEOPHYS_PROVIDER_ROOT / 'src').resolve()
    core = Path(core_root or expected_core).expanduser().resolve()
    geophys = Path(geophys_src or expected_geophys).expanduser().resolve()
    if core != expected_core or geophys != expected_geophys:
        raise ValueError('deployment source origin differs from the current Core or GeoPhys checkout')
    interpreter = Path(python).expanduser().absolute()
    if not interpreter.is_file():
        raise ValueError(f'deployment interpreter unavailable: {interpreter}')
    if not (geophys / 'geophys' / '__init__.py').is_file() or not (geophys / 'scene' / '__init__.py').is_file():
        raise ValueError(f'current GeoPhys source unavailable: {geophys}')
    try:
        process = subprocess.Popen(
            [str(interpreter), '-I', '-S', '-B', '-c', _ENVIRONMENT_METADATA_PROBE, str(core), str(geophys),
             'launcher' if interpreter.name == 'python.sh' else 'python'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            raise
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, process.args, stdout, stderr)
    except subprocess.TimeoutExpired as exc:
        raise ValueError('deployment interpreter metadata probe timed out') from exc
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError(f'deployment interpreter metadata probe failed: {exc}') from exc
    import json
    try:
        frames = [line.removeprefix('GEOCHORA_METADATA_V1:') for line in stdout.splitlines()
                  if line.startswith('GEOCHORA_METADATA_V1:')]
        if len(frames) != 1:
            raise ValueError('expected exactly one metadata frame')
        receipt = json.loads(frames[0])
    except (TypeError, ValueError) as exc:
        raise ValueError('deployment interpreter metadata probe returned invalid JSON') from exc
    receipt['launcher'] = str(interpreter)
    expected = {'task_env': core / 'task_env' / '__init__.py',
                'geophys': geophys / 'geophys' / '__init__.py',
                'scene': geophys / 'scene' / '__init__.py',
                'control': geophys / 'control' / '__init__.py',
                'simulation': geophys / 'simulation' / '__init__.py',
                'solvers': geophys / 'solvers' / '__init__.py'}
    for name, path in expected.items():
        if receipt['origins'].get(name) != str(path.resolve()):
            raise ValueError(f'deployment {name} origin mismatch: {receipt["origins"].get(name)!r}')
    return receipt


def assess_mujoco_distribution(provider, metadata_receipt, *, solver_family=None):
    """Assess the declared MuJoCo distribution constraint, not all dependencies."""
    import re
    constraints = {
        'mujoco': '>=3.8.1,<3.9.0',
        'geophys': '>=3.15.0',
        'isaacsim': 'sdk-managed',
    }
    if provider not in constraints:
        raise ValueError(f'unknown deployment provider: {provider}')
    version = metadata_receipt['versions'].get('mujoco')
    result = {'dependency': 'mujoco', 'constraint': constraints[provider],
              'observed_version': version, 'status': 'unknown', 'reason': ''}
    if provider == 'geophys' and solver_family == 'rigid':
        result.update(status='not_selected', reason='GeoPhys native rigid solver does not consume MuJoCo solver')
        return result
    if provider == 'isaacsim':
        result['reason'] = 'Isaac SDK dependency compatibility requires its own build oracle'
        return result
    if version is None:
        result.update(status='unavailable', reason='MuJoCo distribution metadata is missing')
        return result
    # Do not misclassify pre-releases, local builds, epochs or malformed versions.
    if not isinstance(version, str) or not re.fullmatch(r'\d+(?:\.\d+)*', version):
        result['reason'] = 'version requires a PEP 440-aware check'
        return result
    components = tuple(int(part) for part in version.split('.'))
    release = (components + (0, 0, 0))[:3]
    if len(components) > 3 and any(components[3:]):
        result['reason'] = 'version requires a PEP 440-aware check'
        return result
    admitted = ((3, 8, 1) <= release < (3, 9, 0) if provider == 'mujoco'
                else release >= (3, 15, 0))
    result.update(status='available' if admitted else 'unavailable',
                  reason='declared distribution constraint satisfied' if admitted
                  else 'installed distribution conflicts with declared constraint')
    return result


def assess_declared_dependencies(provider, metadata_receipt, *, solver_family=None):
    """Check recorded distributions against the current route's declarations.

    GeoPhys worker and Core/MuJoCo worker have separate MuJoCo constraints;
    the Core source remains the same in both. Metadata is not native evidence.
    Isaac dependency compatibility requires a separate SDK oracle.
    """
    from ...utils._paths import GEOCHORA_ROOT, GEOPHYS_PROVIDER_ROOT
    if provider not in {'mujoco', 'geophys', 'isaacsim'}:
        raise ValueError(f'unknown deployment provider: {provider}')
    core_file = GEOCHORA_ROOT / 'task_env' / 'requirements.txt'
    geo_file = GEOPHYS_PROVIDER_ROOT / 'pyproject.toml'
    source_hashes = {'core_requirements_sha256': hashlib.sha256(core_file.read_bytes()).hexdigest(),
                     'geophys_pyproject_sha256': hashlib.sha256(geo_file.read_bytes()).hexdigest()}
    try:
        import tomllib
        from packaging.requirements import Requirement
        from packaging.version import InvalidVersion, Version
    except ImportError:
        return {'status': 'unknown', 'reason': 'dependency specification parser unavailable',
                'requirements': [], 'source_hashes': source_hashes}
    import re
    declared = [line.strip() for line in core_file.read_text().splitlines()
                if line.strip() and not line.lstrip().startswith('#')]
    geo = tomllib.loads(geo_file.read_text())['project']
    if provider in {'geophys', 'isaacsim'}:
        declared = [line for line in declared if Requirement(line).name.lower() != 'mujoco']
    if provider == 'geophys':
        declared += [line for line in geo['dependencies']
                     if solver_family != 'rigid' or Requirement(line).name.lower() != 'mujoco']
    elif provider == 'isaacsim':
        # These are selected worker imports, not a claim that the SDK Python
        # satisfies Core's complete installation requirements.  Renderer and
        # GeoPhys-only dependencies belong to their own consumers.
        worker_names = {'numpy', 'scipy', 'psutil', 'pydantic', 'pyyaml', 'trimesh'}
        declared = [line for line in declared if Requirement(line).name.lower() in worker_names]
        declared = ['numpy>=1.26,<3' if Requirement(line).name.lower() == 'numpy' else line
                    for line in declared]
        declared.append('isaacsim>=6.1.0,<6.3.0')
        declared.append('packaging')
    versions = {re.sub(r'[-_.]+', '-', name).lower(): value
                for name, value in metadata_receipt['versions'].items()}
    module_origins = {re.sub(r'[-_.]+', '-', name).lower(): value
                      for name, value in metadata_receipt.get('module_origins', {}).items()}
    ownership = {re.sub(r'[-_.]+', '-', name).lower(): value
                 for name, value in metadata_receipt.get('origin_ownership', {}).items()}
    rows = []
    for declaration in declared:
        requirement = Requirement(declaration)
        name = re.sub(r'[-_.]+', '-', requirement.name).lower()
        observed = versions.get(name)
        row = {'name': name, 'requirement': declaration, 'observed_version': observed}
        if requirement.marker is not None or requirement.extras:
            row.update(status='unknown', reason='target-environment marker or extra is not evaluated')
        elif name not in versions:
            row.update(status='unknown', reason='distribution was not queried')
        elif (name == 'isaacsim' and observed is None
              and metadata_receipt.get('isaac_sdk_identity', {}).get('sdk_version_raw')):
            sdk_root = metadata_receipt['isaac_sdk_identity'].get('sdk_root')
            origin = module_origins.get(name)
            try:
                if not sdk_root or not origin:
                    raise ValueError('no SDK module origin')
                Path(origin).resolve().relative_to(Path(sdk_root).resolve())
            except ValueError:
                row.update(status='unknown', reason='SDK VERSION exists; App module origin still requires verification')
            else:
                row.update(status='available', reason='explicit SDK VERSION and module origin inside SDK root; no pip metadata')
        elif observed is None:
            row.update(status='unavailable', reason='distribution metadata missing')
        elif name not in module_origins:
            row.update(status='unknown', reason='module origin was not queried')
        elif module_origins[name] is None:
            row.update(status='unavailable', reason='distribution import source missing')
        elif ownership.get(name) == 'mismatch':
            row.update(status='unavailable', reason='module origin does not belong to its distribution')
        elif ownership.get(name) != 'owned':
            row.update(status='unknown', reason='distribution ownership of module origin is unverified')
        else:
            try:
                compatible = Version(observed) in requirement.specifier
                if name == 'isaacsim':
                    try:
                        resolve_isaac_sdk_identity(pip_version=observed)
                    except ValueError:
                        compatible = False
            except InvalidVersion:
                row.update(status='unknown', reason='invalid distribution version metadata')
            else:
                row.update(status='available' if compatible else 'unavailable',
                           reason='declared requirement satisfied' if compatible else 'version conflicts with declaration')
        rows.append(row)
    if provider == 'geophys':
        from packaging.specifiers import SpecifierSet
        py_version = '.'.join(str(part) for part in metadata_receipt['python_version'])
        compatible = Version(py_version) in SpecifierSet(geo['requires-python'])
        rows.append({'name': 'python', 'requirement': geo['requires-python'],
                     'observed_version': py_version,
                     'status': 'available' if compatible else 'unavailable',
                     'reason': 'declared requirement satisfied' if compatible else 'version conflicts with declaration'})
    status = ('unavailable' if any(row['status'] == 'unavailable' for row in rows)
              else 'unknown' if any(row['status'] == 'unknown' for row in rows)
              else 'available')
    return {'status': status, 'requirements': rows, 'source_hashes': source_hashes,
            'dependency_scope': ('geophys-native-rigid' if provider == 'geophys' and solver_family == 'rigid'
                                 else 'geophys-declared' if provider == 'geophys' else provider),
            'installation_scope': ('selected SDK worker imports; Core full installation not assessed'
                                   if provider == 'isaacsim' else 'declared route dependencies'),
            'reason': 'distribution metadata only; native build remains unverified'}


class DeploymentPreflightError(ValueError):
    """Existing ValueError boundary with a request-bound offline receipt."""
    def __init__(self, reason, receipt):
        self.reason = reason
        self.phase = 'static_preflight'
        self.request_identity = receipt['request_identity']
        receipt['status'] = 'rejected'
        receipt['failure_reason'] = reason
        self.receipt = receipt
        super().__init__(f'{self.phase}: {reason}; request={self.request_identity}')


def inspect_selected_interpreter(selection):
    """Read and assess one selected interpreter without importing provider SDKs."""
    environment = probe_interpreter_environment(selection.interpreter)
    if selection.physics_provider == 'isaacsim':
        launcher = Path(selection.interpreter).expanduser().absolute()
        sdk_root = launcher.parent if launcher.name == 'python.sh' else None
        environment['isaac_sdk_identity'] = resolve_isaac_sdk_identity(
            pip_version=environment['versions'].get('isaacsim'), sdk_root=sdk_root)
    return environment, assess_declared_dependencies(selection.physics_provider, environment,
                                                      solver_family=selection.solver_family)


def preflight_selected_source(selection, *, requested, task_uid):
    """Admit source builds that require their native interpreter environment."""
    if selection.physics_provider == 'isaacsim':
        return preflight_interpreter_before_source(selection, requested=requested, task_uid=task_uid)
    return None


def preflight_interpreter_before_source(selection, *, requested, task_uid):
    """Reject unavailable interpreter dependencies before source construction."""
    from .transport import request_identity
    facts = {'selection': selection.to_mapping(), 'requested': requested, 'task_uid': task_uid,
             'artifact_identity': None, 'source_id': None, 'source_closure': None,
             'controller_identities': None}
    receipt = {'schema_version': 'deployment-preflight-v1',
               'request_identity': request_identity(facts), 'phase': 'static_preflight',
               'identity_scope': 'selection_only_source_not_evaluated', 'identity_facts': facts,
               'requested': requested, 'resolved': selection.to_mapping(), 'environment': None,
               'dependency': {'status': 'unknown', 'reason': 'not checked'},
               'assessment': None, 'native_effective': {'status': 'unknown',
                   'reason': 'native build/readback not run'}, 'evidence': 'none'}
    if selection.interpreter is None:
        receipt['dependency'] = {'status': 'unavailable', 'reason': 'interpreter path not configured'}
        raise DeploymentPreflightError('interpreter_unavailable', receipt)
    try:
        environment, dependency = inspect_selected_interpreter(selection)
    except ValueError as error:
        receipt['dependency'] = {'status': 'unavailable', 'reason': str(error)}
        raise DeploymentPreflightError('environment_probe_failed', receipt) from error
    receipt['environment'] = environment
    receipt['dependency'] = dependency
    if receipt['dependency']['status'] != 'available':
        raise DeploymentPreflightError('dependency_' + receipt['dependency']['status'], receipt)
    return environment, receipt['dependency']


def describe_execution_selection(selection, *, requested, task_uid, artifact, source, controller, seed):
    """Return a request-bound selection; native effective values remain unknown."""
    from .transport import request_identity, source_binding_facts
    profiles = tuple(controller) if isinstance(controller, (tuple, list)) else (controller,)
    controller_ids = [getattr(item, 'identity', None) or getattr(item, 'identity_sha256', None)
                      for item in profiles]
    if any(not isinstance(item, str) or not item for item in controller_ids):
        raise ValueError('worker preflight requires Controller identities')
    scene = getattr(source, 'scene_definition', None)
    identity_facts = {
        'selection': selection.to_mapping(), 'requested': requested, 'task_uid': task_uid,
        'artifact_identity': artifact.identity_hash,
        'source_id': source.scene_source.source_id,
        'source_bindings': source_binding_facts(source),
        'source_xml_sha256': (None if getattr(source.scene_source, 'xml', None) is None
                              else hashlib.sha256(source.scene_source.xml.encode()).hexdigest()),
        'source_closure': getattr(source, 'source_closure_digest', None),
        'scene_identity': None if scene is None else scene.identity_hash,
        'controller_identities': sorted(controller_ids), 'seed': seed,
        'timebase': artifact.timebase.to_mapping(),
    }
    receipt = {'schema_version': 'deployment-preflight-v1',
               'request_identity': request_identity(identity_facts), 'phase': 'declaration',
               'requested': requested, 'resolved': selection.to_mapping(),
               'native_effective': {'status': 'unknown', 'reason': 'native build/readback not run'},
               'identity_facts': identity_facts, 'environment': None,
               'dependency': {'status': 'unknown', 'reason': 'not checked'},
               'evidence': 'none'}
    receipt['status'] = 'selection_only'
    return receipt


def preflight_selected_deployment(selection, *, requested, task_uid, artifact, source, controller, seed, binding, value):
    """Check an isolated deployment before any previous session is closed."""
    receipt = describe_execution_selection(selection, requested=requested, task_uid=task_uid,
                                           artifact=artifact, source=source, controller=controller, seed=seed)
    receipt['phase'] = 'static_preflight'

    def assess(status):
        from .api import assess_selected_request
        assessment = assess_selected_request(
            selection=selection, artifact=artifact, source=source, value=value, binding=binding,
            dependency_status=status, request_identity=receipt['request_identity'],
        )
        # Bind the actual declaration projection (without its outer request ID)
        # into the canonical request before publishing the final assessment.
        from .transport import request_identity
        receipt['identity_facts']['assessment_rows'] = assessment.to_mapping()['rows']
        plan = value.get('controller_binding_plan') or value.get('leaf_plan')
        receipt['identity_facts']['control_binding_plan'] = (None if plan is None else
            getattr(plan, 'identity_hash', None) or plan.identity_sha256)
        receipt['request_identity'] = request_identity(receipt['identity_facts'])
        assessment = assess_selected_request(
            selection=selection, artifact=artifact, source=source, value=value, binding=binding,
            dependency_status=status, request_identity=receipt['request_identity'],
        )
        receipt['assessment'] = {**assessment.to_mapping(), 'decision': assessment.decision}
        return assessment

    if selection.interpreter is None:
        receipt['dependency'] = {'status': 'unavailable', 'reason': 'interpreter path not configured'}
        assess('unavailable')
        raise DeploymentPreflightError('interpreter_unavailable', receipt)
    try:
        environment, dependency = inspect_selected_interpreter(selection)
    except ValueError as error:
        receipt['dependency'] = {'status': 'unavailable', 'reason': str(error)}
        assess('unavailable')
        raise DeploymentPreflightError('environment_probe_failed', receipt) from error
    receipt['environment'] = environment
    receipt['dependency'] = dependency
    # Bind the actual interpreter, package versions, origins and source
    # declaration digests into the request before capability assessment.
    from .transport import request_identity
    receipt['identity_facts']['environment'] = environment
    receipt['identity_facts']['dependency'] = dependency
    receipt['request_identity'] = request_identity(receipt['identity_facts'])
    assessment = assess(dependency['status'])
    if dependency['status'] != 'available':
        raise DeploymentPreflightError('dependency_' + dependency['status'], receipt)
    if assessment.decision == 'rejected':
        raise DeploymentPreflightError('capability_rejected', receipt)
    receipt['status'] = assessment.decision
    return receipt


def bind_selected_build_checks(receipt, facts, *, materialization_id):
    """Bind concrete adapter layout facts to the same static request.

    This records only named layout/read-view checks, not physical qualification
    or a native-effective parameter readback.
    """
    if not isinstance(facts, dict) or not isinstance(facts.get('objects'), dict):
        raise ValueError('adapter did not return request-specific named layout facts')
    identity = receipt['identity_facts']
    if (facts.get('provider') != receipt['resolved']['physics_provider']
            or facts.get('source_id') != identity['source_id']
            or facts.get('source_closure') != identity['source_closure']
            or facts.get('materialization_id') != materialization_id):
        raise ValueError('adapter layout facts differ from preflight source or materialization')
    groups = {'joint': 'joints', 'free': 'free_joints', 'body': 'bodies',
              'frame': 'frames', 'actuator': 'actuators'}
    fields = {'joints': 'joints', 'free_joints': 'free_joints', 'bodies': 'bodies',
              'frames': 'frames', 'joint_targets': 'actuators',
              'torque_actuators': 'actuators', 'position_actuators': 'actuators'}
    declared = identity['source_bindings']
    reference_hash = declared.get('source_reference_plan')
    if reference_hash is not None:
        reference = facts.get('source_reference')
        if (not isinstance(reference, dict) or reference.get('schema_version') != 'source-composition-materialization-receipt-v1'
                or reference.get('plan_sha256') != reference_hash
                or reference.get('materialization_id') != materialization_id
                or reference.get('objects') != facts.get('objects')):
            raise ValueError('adapter reference receipt differs from the requested plan or session')
    composition_hash = declared.get('source_composition_plan')
    if composition_hash is not None:
        composition = facts.get('source_composition')
        if (not isinstance(composition, dict)
                or composition.get('schema_version') != 'source-composition-materialization-receipt-v1'
                or composition.get('plan_sha256') != composition_hash
                or composition.get('materialization_id') != materialization_id
                or composition.get('objects') != facts.get('objects')):
            raise ValueError('adapter composition receipt differs from the requested plan or session')
    for source_field, checked_field in fields.items():
        for semantic, native in declared[source_field].items():
            checked_object = facts['objects'].get(checked_field, {}).get(semantic)
            if not isinstance(checked_object, dict) or checked_object.get('native') != native:
                raise ValueError(f'adapter layout differs from declared binding: {source_field}/{semantic}')
    for native in declared['open_actuators']:
        checked_object = facts['objects'].get('actuators', {}).get('open:' + native)
        if not isinstance(checked_object, dict) or checked_object.get('native') != native:
            raise ValueError(f'adapter layout lacks declared opening actuator: {native}')
    checked = []
    for row in receipt['assessment']['rows']:
        if row['requiredness'] != 'required' or row['requirement_status'] != 'unknown':
            continue
        if row['build_oracle'] != facts.get('helper'):
            raise ValueError('adapter layout helper differs from pending requirement')
        ref = row['object_ref']
        if ref.startswith('state:'):
            matched = False
            for kind, field in (('joint', 'joints'), ('frame', 'frames'), ('frame', 'bodies')):
                for semantic in facts['objects'].get(field, {}):
                    if ref.startswith('state:' + kind + ':' + semantic + ':'):
                        matched = True
                        break
                if matched:
                    break
        else:
            kind, _, semantic = ref.partition(':')
            matched = semantic in facts['objects'].get(groups.get(kind, ''), {})
        if not matched:
            raise ValueError(f'adapter build did not check required object: {ref}')
        checked.append(ref)
    receipt['build_checks'] = {
        'schema_version': 'selected-build-layout-checks-v1',
        'request_identity': receipt['request_identity'],
        'materialization_id': materialization_id,
        'phase': 'native_build', 'status': 'checked',
        'checked_requirements': checked, 'adapter_facts': facts,
        'scope': 'named layout and bound public state views; no physical qualification or parameter readback',
    }
    return receipt
