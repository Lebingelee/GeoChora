"""Construct one selected scalar RuntimeSession in its selected interpreter."""
from __future__ import annotations

import os
from pathlib import Path
import socket
import sys

from .transport import (_receive, _send, _error, request_identity,
                        serve_session, source_execution_facts)


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
    dependency = assess_declared_dependencies(selection.physics_provider, payload['environment'])
    if dependency != identity_facts['dependency'] or dependency['status'] != 'available':
        raise ValueError('worker dependency facts differ from admissible preflight')
    if not callable(getattr(cls, 'selected_binding', None)):
        raise ValueError('selected task has no reconstructible binding')
    binding = cls.selected_binding(config)
    provider, backend = config.physics_provider, config.environment.runtime.backend
    seed, horizon = payload['seed'], config.environment.episode.horizon
    if binding.build_seeded is not None:
        value = binding.build_seeded(provider, backend, seed, horizon)
    else:
        value = binding.build_for_provider(provider)
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
        if selected.mixed or selected.leaf_plan is not None or len(selected.position_profiles) > 1:
            raise ValueError('worker route does not implement mixed, leaf, or multi-writer profiles')
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
                                          binding=binding.scalar_control_binding)
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
    if str(Path(sys.executable).resolve()) != facts['python']:
        raise ValueError('worker interpreter identity differs from preflight')
    for name, expected in facts['origins'].items():
        spec = PathFinder.find_spec(name, sys.path)
        actual = None if spec is None or spec.origin is None else str(Path(spec.origin).resolve())
        if actual != expected:
            raise ValueError(f'worker source origin changed for {name}')
    modules = {'numpy':'numpy', 'scipy':'scipy', 'psutil':'psutil', 'pydantic':'pydantic',
               'taichi-forge':'taichi_forge', 'trimesh':'trimesh', 'pyvista':'pyvista',
               'Pillow':'PIL', 'mujoco':'mujoco', 'gymnasium':'gymnasium', 'h5py':'h5py', 'PyYAML':'yaml', 'isaacsim':'isaacsim'}
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
                    ownership = ('owned' if relative in names or any(item.startswith(relative + '/') for item in names)
                                 else 'mismatch')
            except metadata.PackageNotFoundError:
                pass
            except ValueError:
                ownership = 'mismatch'
        if ownership != facts['origin_ownership'].get(name):
            raise ValueError(f'worker distribution origin ownership changed for {name}')
    for name, expected in facts['versions'].items():
        try:
            actual = metadata.version(name)
        except metadata.PackageNotFoundError:
            actual = None
        if actual != expected:
            raise ValueError(f'worker package metadata changed for {name}')


def main():
    sock = socket.socket(fileno=int(sys.argv[1]))
    request = _receive(sock)
    identity = request.get('request_identity')
    payload = request.get('payload')
    handed_off = False
    source = None
    try:
        if request.get('kind') != 'build' or not isinstance(payload, dict) or request_identity(payload) != identity:
            raise ValueError('worker build request identity mismatch')
        _validate_environment(payload)
        session, handlers, source = _materialize_selected(payload)
        handed_off = True
        serve_session(sock, session, identity, handlers=handlers)
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
        sock.close()


if __name__ == '__main__':
    main()
