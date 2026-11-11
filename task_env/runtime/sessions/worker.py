"""Construct one selected scalar RuntimeSession in its selected interpreter."""
from __future__ import annotations

import os
from pathlib import Path
import socket
import sys

from .transport import (_receive, _send, _error, request_identity,
                        serve_session, source_execution_facts)


def _write_runtime_scope_receipt() -> None:
    """Write the worker's actual cgroup facts after provider cleanup."""
    receipt_path = os.environ.get('GEOCHORA_RUNTIME_SCOPE_POST_CLOSE')
    if not receipt_path:
        return
    cgroup = '/sys/fs/cgroup' + next(
        (line[3:] for line in Path('/proc/self/cgroup').read_text().splitlines()
         if line.startswith('0::')), '')
    root = Path(cgroup)
    values = {
        'stage': 'after_runtime_session_and_owner_close',
        'pid': os.getpid(),
        'cgroup': cgroup,
        'memory_max': (root / 'memory.max').read_text().strip() if (root / 'memory.max').exists() else None,
        'memory_peak': (root / 'memory.peak').read_text().strip() if (root / 'memory.peak').exists() else None,
        'cpu_max': (root / 'cpu.max').read_text().strip() if (root / 'cpu.max').exists() else None,
        'cpuset_cpus': (root / 'cpuset.cpus.effective').read_text().strip()
        if (root / 'cpuset.cpus.effective').exists() else None,
    }
    Path(receipt_path).write_text(
        __import__('json').dumps(values, indent=2, sort_keys=True) + '\n', encoding='utf-8',
    )


def _materialize_selected(payload):
    """Rebuild the existing task binding, then call its normal session owner."""
    import importlib
    from ...artifacts import ExecutionSpec, ExecutionSpecV1, ExecutionSpecV2, decode_execution_spec
    from ...environment.configuration import resolve_task_env_config
    from ...registry import ENV_REGISTRY
    from .control import (bind_selected_controller, materialize_control,
                          prepare_position_control_materialization,
                          _validate_position_source_boundary, apply_position_control_target)

    importlib.import_module('task_env.tasks')
    cls = ENV_REGISTRY.get(payload['uid'])
    if not getattr(cls, 'uses_selected_public_config', False):
        raise ValueError('worker deployment requires a selected public task binding')
    config = resolve_task_env_config(cls, payload['config'])
    selection = ExecutionSpecV2.from_mapping(payload['selection'])
    identity_facts = payload['preflight_identity_facts']
    if (request_identity(identity_facts) != payload['preflight_request_identity']
            or identity_facts['selection'] != selection.to_mapping()
            or identity_facts['environment'] != payload['environment']
            or identity_facts['task_uid'] != payload['uid']
            or identity_facts['seed'] != payload['seed']
            or selection.deployment != 'isolated_worker'
            or selection.physics_provider != config.physics_provider
            or selection.physics_backend != config.environment.runtime.backend
            or selection.physics_device != config.physics_device
            or selection.render_default != config.render_default):
        raise ValueError('worker selection or preflight request identity mismatch')
    from .provenance import assess_declared_dependencies
    dependency = assess_declared_dependencies(selection.physics_provider, payload['environment'],
                                             solver_family=selection.solver_family)
    if dependency != identity_facts['dependency'] or dependency['status'] != 'available':
        raise ValueError('worker dependency facts differ from admissible preflight')
    if not callable(getattr(cls, 'selected_binding', None)):
        raise ValueError('selected task has no reconstructible binding')
    binding = cls._bind_robot_source_composer(cls.selected_binding(config), config)
    provider, backend = config.physics_provider, config.environment.runtime.backend
    seed, horizon = payload['seed'], config.environment.episode.horizon
    value = binding.reset_reconstruction_strategy(provider, backend, horizon).initial(seed=seed)
    source = value['source']
    try:
        artifact = value['artifact']
        execution = decode_execution_spec(payload['execution'])
        if type(execution) not in (ExecutionSpec, ExecutionSpecV1):
            raise TypeError('worker requires the existing execution codec')
        backend = execution.backend if type(execution) is ExecutionSpec else execution.physics_backend
        if execution.physics_provider != selection.physics_provider or backend != selection.physics_backend:
            raise ValueError('worker execution differs from the requested route')
        if type(execution) is ExecutionSpecV1 and (execution.physics_device != selection.physics_device
                                                  or execution.render_default != selection.render_default):
            raise ValueError('worker device/renderer differs from the requested route')
        rebuilt_execution = value.get('execution_spec_v1')
        if rebuilt_execution is not None and rebuilt_execution.to_mapping() != execution.to_mapping():
            raise ValueError('worker rebuilt a different execution spec')
        actual = source_execution_facts(artifact, execution, source, value['controller'])
        if actual != payload['facts']:
            raise ValueError('worker rebuilt source/Artifact/execution/Controller identity mismatch')
        for name in ('artifact_identity', 'source_id', 'source_bindings', 'source_xml_sha256', 'source_closure', 'scene_identity', 'controller_identities'):
            if actual[name] != identity_facts[name]:
                raise ValueError(f'worker rebuilt source differs from preflight {name}')
        if artifact.timebase.to_mapping() != identity_facts['timebase']:
            raise ValueError('worker timebase differs from preflight')
        # The worker independently rechecks the rebuilt declarations; a caller
        # cannot authorize materialization by fabricating preflight JSON.
        from .api import assess_selected_request
        assessment = assess_selected_request(
            selection=selection, artifact=artifact, source=source, value=value,
            binding=binding, dependency_status=dependency['status'],
            request_identity=payload['preflight_request_identity'],
        )
        plan = value.get('controller_binding_plan')
        if (assessment.to_mapping()['rows'] != identity_facts.get('assessment_rows')
                or (None if plan is None else plan.identity_hash) != identity_facts.get('control_binding_plan')):
            raise ValueError('worker rebuilt assessment or Controller plan differs from preflight')
        if assessment.decision == 'rejected':
            raise ValueError('worker rebuilt request failed capability preflight')
        selected = bind_selected_controller(value, binding=binding, provider=provider, backend=backend)
        handlers = {}
        if selected.mixed or len(selected.position_profiles) > 1:
            raise ValueError('worker route does not implement mixed or multi-writer profiles')
        if selected.position:
            plan, joints, frames, control_binding = prepare_position_control_materialization(
                source=source, artifact=artifact, profiles=selected.position_profiles,
                leaf_position=False, plan=value.get('controller_binding_plan'),
                select_binding=binding.position_control_binding, value=value,
            )
            session = materialize_control(
                artifact, execution, source=source, binding=control_binding,
                controller_binding_plan=plan, controller_profile=selected.position_profiles,
                session_admission_input=value.get('session_admission_input'),
            )
            profile = selected.position_profiles[0]
            scene = source.scene_definition
            handlers['position_preflight'] = lambda publication: _validate_position_source_boundary(
                session, profile, plan, publication, scene=scene, joint_bindings=joints, frame_bindings=frames)
            handlers['position_apply'] = lambda target, publication: apply_position_control_target(
                session, target, controller_profile=profile, plan=plan, publication=publication,
                scene=scene, joint_bindings=joints, frame_bindings=frames)
        else:
            session = materialize_control(artifact, execution, source=source,
                                          binding=binding.scalar_control_binding,
                                          selected_controller=(selected.controller
                                              if binding.interval_mode == 'native' else None))
            from contextlib import nullcontext
            from .control import position_subject_interval
            from .legacy_native_feedback_binding import native_feedback_interval

            def subject_scoped(operation):
                def invoke(target, *args, **kwargs):
                    state = session.snapshot()
                    if getattr(source, 'position_subject_binding', None) is not None:
                        scope = position_subject_interval(session, target, state, controller=selected.controller)
                    elif getattr(session, '_legacy_native_feedback_binding', None) is not None:
                        scope = native_feedback_interval(session, target, state, controller=selected.controller)
                    else:
                        scope = nullcontext()
                    with scope:
                        return operation(target, *args, **kwargs)
                return invoke

            for name in ('apply_control', 'step_control_interval'):
                operation = getattr(session, name, None)
                if callable(operation):
                    handlers[name] = subject_scoped(operation)
        return session, handlers, source
    except BaseException:
        receipt = getattr(source, 'execution_source_receipt', None)
        if receipt is not None:
            receipt.close()
        raise


def _validate_environment(payload):
    """Bind this actual interpreter and imports to the parent's metadata receipt."""
    from importlib import metadata
    from importlib.machinery import PathFinder
    from ...utils._paths import GEOCHORA_ROOT, GEOPHYS_PROVIDER_ROOT
    expected_core = Path(payload['core_root']).resolve()
    expected_geo = Path(payload['geophys_src']).resolve()
    if GEOCHORA_ROOT.resolve() != expected_core or (GEOPHYS_PROVIDER_ROOT / 'src').resolve() != expected_geo:
        raise ValueError('worker loaded a different Core or GeoPhys checkout')
    facts = payload['environment']
    launcher_paths = facts.get('launcher_pythonpath', [])
    if Path(facts.get('launcher', '')).name == 'python.sh':
        actual_paths = [str(Path(item).resolve()) for item in os.environ.get('PYTHONPATH', '').split(os.pathsep) if item]
        if actual_paths != launcher_paths:
            raise ValueError('worker launcher Python path differs from preflight')
    if str(Path(sys.executable).absolute()) != facts.get('worker_executable', str(Path(sys.executable).absolute())):
        raise ValueError('worker executable differs from preflight')
    if str(Path(sys.executable).resolve()) != facts['python']:
        raise ValueError('worker interpreter identity differs from preflight')
    for name, expected in facts['origins'].items():
        spec = PathFinder.find_spec(name, sys.path)
        actual = None if spec is None or spec.origin is None else str(Path(spec.origin).resolve())
        if actual != expected:
            raise ValueError(f'worker source origin changed for {name}')
    modules = {'numpy':'numpy', 'scipy':'scipy', 'psutil':'psutil', 'pydantic':'pydantic',
               'taichi-forge':'taichi_forge', 'trimesh':'trimesh', 'pyvista':'pyvista',
               'Pillow':'PIL', 'mujoco':'mujoco', 'gymnasium':'gymnasium', 'h5py':'h5py', 'PyYAML':'yaml', 'isaacsim':'isaacsim', 'packaging':'packaging'}
    isaacsim_namespace_owner = None
    for name, expected in facts['module_origins'].items():
        spec = PathFinder.find_spec(modules[name], sys.path)
        origin = None if spec is None else spec.origin
        if origin is None and spec is not None and spec.submodule_search_locations:
            origin = list(spec.submodule_search_locations)[0]
        actual = None if origin is None else str(Path(origin).resolve())
        if actual != expected:
            raise ValueError(f'worker dependency origin changed for {name}')
        ownership = 'missing' if actual is None else 'unknown'
        if actual is not None:
            try:
                dist = metadata.distribution(name)
                if dist.files is not None:
                    relative = Path(actual).relative_to(Path(dist.locate_file('')).resolve()).as_posix()
                    names = {str(item).replace('\\', '/') for item in dist.files}
                    owned = relative in names or any(item.startswith(relative + '/') for item in names)
                    if name == 'isaacsim' and not owned:
                        try:
                            kernel = metadata.distribution('isaacsim-kernel')
                            kernel_relative = Path(actual).relative_to(Path(kernel.locate_file('')).resolve()).as_posix()
                            kernel_files = {str(item).replace('\\', '/') for item in (kernel.files or ())}
                            if kernel.version == dist.version and kernel_relative in kernel_files:
                                owned = True
                                isaacsim_namespace_owner = 'isaacsim-kernel'
                        except (metadata.PackageNotFoundError, ValueError):
                            pass
                    ownership = 'owned' if owned else 'mismatch'
            except metadata.PackageNotFoundError:
                pass
            except ValueError:
                ownership = 'mismatch'
        if ownership != facts['origin_ownership'].get(name):
            raise ValueError(f'worker distribution origin ownership changed for {name}')
    if isaacsim_namespace_owner != facts.get('isaacsim_namespace_owner'):
        raise ValueError('worker Isaac namespace owner differs from preflight')
    for name, expected in facts['versions'].items():
        try:
            actual = metadata.version(name)
        except metadata.PackageNotFoundError:
            actual = None
        if actual != expected:
            raise ValueError(f'worker package metadata changed for {name}')
    sdk_identity = facts.get('isaac_sdk_identity')
    if sdk_identity is not None:
        from .provenance import resolve_isaac_sdk_identity
        try:
            pip_version = metadata.version('isaacsim')
        except metadata.PackageNotFoundError:
            pip_version = None
        if resolve_isaac_sdk_identity(pip_version=pip_version,
                                      sdk_root=sdk_identity['sdk_root']) != sdk_identity:
            raise ValueError('worker Isaac SDK version differs from preflight')
        os.environ['GEOCHORA_SELECTED_ISAAC_VERSION'] = sdk_identity['normalized_version']
        if facts['module_origins'].get('isaacsim') is not None:
            os.environ['GEOCHORA_SELECTED_ISAAC_ORIGIN'] = facts['module_origins']['isaacsim']
        if sdk_identity['sdk_root'] is not None:
            os.environ['GEOCHORA_SELECTED_ISAAC_ROOT'] = sdk_identity['sdk_root']


def main():
    sock = socket.socket(fileno=int(sys.argv[1]))
    request = _receive(sock)
    identity = request.get('request_identity')
    payload = request.get('payload')
    handed_off = False
    source = None
    early_app_owner = None
    completed = False
    try:
        if request.get('kind') != 'build' or not isinstance(payload, dict) or request_identity(payload) != identity:
            raise ValueError('worker build request identity mismatch')
        _validate_environment(payload)
        # Kit must establish its USD libraries before F06 reconstructs the
        # USD source. Importing the standalone USD wheel first can load an
        # incompatible set of libraries into the same process.
        if (payload.get('uid') == 'pick-cube-p16-reference-v1'
                and payload.get('selection', {}).get('physics_provider') == 'isaacsim'):
            from .isaac_native_io import _process_app_owner, F06_ISAAC_APP_LAUNCH_PROFILE_V1
            early_app_owner = _process_app_owner(launch_profile_id=F06_ISAAC_APP_LAUNCH_PROFILE_V1)
            early_app_owner.open(f06_compatibility=True)
        session, handlers, source = _materialize_selected(payload)
        handed_off = True
        completed = serve_session(sock, session, identity, handlers=handlers)
    except BaseException as error:
        if not handed_off:
            try:
                _send(sock, {'kind': 'startup_error', 'request_identity': identity, 'error': _error(error)})
            except OSError:
                pass
        else:
            raise
    finally:
        receipt = getattr(source, 'execution_source_receipt', None)
        if receipt is not None:
            receipt.close()
        if early_app_owner is not None:
            early_app_owner.close()
        _write_runtime_scope_receipt()
        sock.close()
    if isinstance(payload, dict) and payload.get('selection', {}).get('physics_provider') == 'isaacsim':
        return 0 if completed else 1
    return None


def _exit_after_isaac_cleanup(exit_code=0):
    """Terminate the isolated SDK process only after all owner cleanup and ACK.

    Kit 6.2 may segfault in CPython's later module finalization even when
    SimulationApp.close has returned.  The worker is the process owner; it
    flushes its output and leaves only after session, App, source and socket
    cleanup have completed. This does not apply to a failed cleanup path.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except (OSError, ValueError):
            pass
    os._exit(int(exit_code))


if __name__ == '__main__':
    exit_code = main()
    if exit_code is not None:
        _exit_after_isaac_cleanup(exit_code)
