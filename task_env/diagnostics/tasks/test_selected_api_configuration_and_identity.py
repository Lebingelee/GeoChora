"""Provider-free regressions for selected construction config and identity facts."""

import pytest
from types import SimpleNamespace

from task_env.artifacts.contracts import RendererSelectionV1
from task_env.environment.config import ResolvedEnvConfig
from task_env.environment.configuration import resolve_task_env_config


def test_position_input_classifier_fails_closed_for_missing_or_unknown_inputs():
    from task_env.environment.reference_binding import position_input_kind
    from task_env.tasks.position_candidate.builder import _versioned_position_candidate_kind

    assert position_input_kind(None, None) is None
    with pytest.raises(TypeError, match='task-owned input classifier'):
        position_input_kind(SimpleNamespace(), object())
    with pytest.raises(TypeError, match='exact supported candidate input'):
        position_input_kind(SimpleNamespace(classify_position_input=_versioned_position_candidate_kind), object())
    with pytest.raises(ValueError, match='unsupported kind'):
        position_input_kind(SimpleNamespace(classify_position_input=lambda _value: 'unknown'), object())


def test_session_route_requires_exact_candidate_type_even_for_subclasses():
    from task_env.runtime.sessions.api import _require_session_admission_input_route
    from task_env.tasks.position_candidate.builder import (
        F05NativePositionCandidateInputV1, F05Dg02GeoPhysUsdCandidateInputV1,
        F05Dg04IsaacNativeCandidateInputV1,
    )

    routes = (
        (F05NativePositionCandidateInputV1, 'f05_native'),
        (F05Dg02GeoPhysUsdCandidateInputV1, 'f05_dg02'),
        (F05Dg04IsaacNativeCandidateInputV1, 'f05_dg04'),
    )
    for cls, route in routes:
        value = object.__new__(cls)
        _require_session_admission_input_route(value, route, 'wrong candidate')
        with pytest.raises(TypeError, match='wrong candidate'):
            _require_session_admission_input_route(value, 'another-route', 'wrong candidate')
        subclass = type('UnsupportedInputSubclass', (cls,), {})
        with pytest.raises(TypeError, match='wrong candidate'):
            _require_session_admission_input_route(object.__new__(subclass), route, 'wrong candidate')


def test_native_adapters_reject_wrong_candidate_before_provider_initialization(monkeypatch):
    from task_env.runtime.sessions.geophys_native_io import F05GeoPhysUsdNativeIO
    from task_env.runtime.sessions import isaac_native_io

    with pytest.raises(TypeError, match='exact versioned native candidate input'):
        F05GeoPhysUsdNativeIO(artifact=object(), execution=object(), source=object(), input_v1=object())

    def forbidden_owner():
        raise AssertionError('invalid candidate reached Isaac App owner')
    monkeypatch.setattr(isaac_native_io, '_process_app_owner', forbidden_owner)
    source = SimpleNamespace(assert_fresh=lambda: None, scene_source=SimpleNamespace(
        source_verified=False, locally_validated=True,
        representation=SimpleNamespace(provider='isaacsim'),
    ))
    execution = SimpleNamespace(physics_profile='isaac-gpu-physx-f05-dg04-native-mimic-v1')
    with pytest.raises(TypeError, match='exact F05Dg04IsaacNativeCandidateInputV1'):
        isaac_native_io.create_isaac_native_runtime_io(
            object(), execution, source, dg04_native_input=object(),
        )


def test_f06_route_classification_does_not_import_position_candidate(monkeypatch):
    import builtins
    from task_env.runtime.sessions.api import _session_admission_input_route
    from task_env.runtime.sessions.source import UsdRuntimeInputV1

    value = object.__new__(UsdRuntimeInputV1)
    object.__setattr__(value, 'schema_version', 'pick-cube-isaac-runtime-input-v1')
    original_import = builtins.__import__
    def guarded_import(name, *args, **kwargs):
        if 'position_candidate.builder' in name:
            raise AssertionError('F06 classification imported unrelated Position task')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded_import)
    assert _session_admission_input_route(value) == 'f06_pickcube'


def test_f05_session_classification_uses_runtime_input_types_without_task_import(monkeypatch):
    import builtins
    from task_env.runtime.sessions.api import _session_admission_input_route
    from task_env.runtime.sessions.position_admission import (
        F05NativePositionCandidateInputV1, F05Dg02GeoPhysUsdCandidateInputV1,
        F05Dg04IsaacNativeCandidateInputV1,
    )

    original_import = builtins.__import__
    def guarded_import(name, *args, **kwargs):
        if 'position_candidate' in name:
            raise AssertionError('runtime classification imported Position task')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded_import)
    for cls, route in (
        (F05NativePositionCandidateInputV1, 'f05_native'),
        (F05Dg02GeoPhysUsdCandidateInputV1, 'f05_dg02'),
        (F05Dg04IsaacNativeCandidateInputV1, 'f05_dg04'),
    ):
        assert _session_admission_input_route(object.__new__(cls)) == route


@pytest.mark.parametrize("provider,backend,device,profile", [
    ("isaacsim", "cuda", "cuda:0", "isaac-gpu-physx-f04-position-v1"),
    ("geophys", "cpu", "cpu", "geophys-usd-position-f05-s1-v1"),
    ("geophys", "cpu", "cpu", "geophys-usd-position-f05-native-v1"),
    ("geophys", "cpu", "cpu", "geophys-usd-position-f05-dg02-core-v1"),
    ("isaacsim", "cuda", "cuda:0", "isaac-gpu-physx-f05-dg04-native-mimic-v1"),
    ("isaacsim", "cuda", "cuda:0", "isaac-gpu-physx-pickcube-f06-v1"),
])
def test_selected_position_route_rejects_each_execution_identity_drift(provider, backend, device, profile):
    from dataclasses import replace
    from task_env.artifacts import ExecutionSpecV1
    from task_env.runtime.sessions.api import validate_selected_position_route

    spec = ExecutionSpecV1(
        "execution-spec-v1", provider, backend, profile, 17, "best_effort",
        RendererSelectionV1("renderer-selection-v1", "none", "cpu", "none", None),
        device, (),
    )
    validate_selected_position_route(spec)
    changes = (
        {"physics_provider": "mujoco"}, {"physics_backend": "other"},
        {"physics_device": "other"}, {"determinism_mode": "strict"},
        {"physics_profile": "unknown-profile"},
    )
    for change in changes:
        with pytest.raises(ValueError, match="unsupported provider execution route"):
            validate_selected_position_route(replace(spec, **change))


def _resolver_target(*, class_defaults=None, task_defaults=None):
    class Target:
        uid = "resolver-target-v1"
        uses_selected_public_config = True
        selected_controller_profiles = frozenset()
        selected_parameter_limits = {}
        selected_supports_isaac = False

        @staticmethod
        def selected_default_config(task_config=None):
            return ResolvedEnvConfig()

        @staticmethod
        def selected_default_controller_profile(task_config=None):
            return None

    if class_defaults is not None:
        Target.selected_execution_defaults = class_defaults
    if task_defaults is not None:
        Target.selected_task_configuration = staticmethod(
            lambda: {"execution": task_defaults}
        )
    return Target


def test_selected_execution_defaults_follow_core_class_yaml_and_caller_order():
    core = resolve_task_env_config(_resolver_target(), None)
    assert (core.physics_provider, core.environment.runtime.backend, core.physics_device) == (
        "geophys", "cpu", "cpu",
    )

    task_class = resolve_task_env_config(
        _resolver_target(class_defaults={"physics_provider": "mujoco"}), None,
    )
    assert task_class.physics_provider == "mujoco"

    yaml_default = resolve_task_env_config(
        _resolver_target(
            class_defaults={"physics_provider": "mujoco"},
            task_defaults={"physics_provider": "geophys"},
        ),
        None,
    )
    assert yaml_default.physics_provider == "geophys"

    caller = resolve_task_env_config(
        _resolver_target(
            class_defaults={"physics_provider": "mujoco"},
            task_defaults={"physics_provider": "geophys"},
        ),
        {"execution": {"physics_provider": "mujoco"}},
    )
    assert caller.physics_provider == "mujoco"


def test_selected_execution_is_strict_and_rejects_inherited_device_conflicts():
    target = _resolver_target()
    with pytest.raises(ValueError, match="provider.*conflicts"):
        resolve_task_env_config(
            target,
            {"provider": "mujoco", "execution": {"physics_provider": "geophys"}},
        )
    with pytest.raises(KeyError, match="unsupported selected execution fields"):
        resolve_task_env_config(target, {"execution": {"surprise": True}})
    with pytest.raises(ValueError, match="'geophys'/'cuda'/'cpu'"):
        resolve_task_env_config(target, {"execution": {"physics_backend": "cuda"}})


def test_selected_scalar_accepts_render_configuration_and_roundtrips_it():
    config = {
        "render": {
            "backend": "mujoco_reference",
            "width": 96,
            "height": 72,
        },
    }
    from task_env.tasks.pendulum import PendulumEnv
    resolved = resolve_task_env_config(PendulumEnv, config)
    assert resolved.environment.render.backend == "mujoco_reference"
    assert (resolved.environment.render.width, resolved.environment.render.height) == (96, 72)
    assert resolve_task_env_config(PendulumEnv, resolved) == resolved


def test_state_only_renderer_is_resolved_recorded_and_roundtrips():
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    resolved = resolve_task_env_config(PickCubeReferenceEnv, None)
    assert type(resolved.render_default) is RendererSelectionV1
    state_only = {
        "schema_version": "renderer-selection-v1",
        "provider": "none",
        "backend": "cpu",
        "profile": "none",
        "device": None,
    }
    assert resolved.render_default.to_mapping() == state_only
    assert resolve_task_env_config(PickCubeReferenceEnv, resolved) == resolved

    env = PickCubeReferenceEnv.from_resolved_config(resolved)
    assert env.session is None
    assert env._recorded_execution_configuration()["execution"]["render_default"] == state_only


def test_selected_config_rejects_unsupported_renderer_selections():
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    unsupported = RendererSelectionV1(
        "renderer-selection-v1", "mujoco", "cpu", "offscreen", "cpu",
    ).to_mapping()
    with pytest.raises(ValueError, match="state-only renderer|physics-renderer"):
        resolve_task_env_config(
            PickCubeReferenceEnv,
            {"execution": {"physics_provider": "mujoco", "render_default": unsupported}},
        )


@pytest.mark.parametrize("task_module", [
    "task_env.tasks.pick_cube.specialization",
    "task_env.tasks.nut_assembly.specialization",
])
def test_selected_task_yaml_uses_duplicate_key_rejecting_loader(
    task_module, tmp_path, monkeypatch,
):
    import importlib
    from yaml.constructor import ConstructorError

    module = importlib.import_module(task_module)
    path = tmp_path / "duplicate.yaml"
    path.write_text("recipe: {}\nrecipe: {}\nenvironment: {}\n")
    monkeypatch.setattr(module, "CONFIG_PATH", path)
    with pytest.raises(ConstructorError, match="found duplicate key 'recipe'"):
        module._configuration()


def test_two_section_task_yaml_remains_compatible(tmp_path, monkeypatch):
    import yaml

    from task_env.tasks.pick_cube import specialization
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    legacy = specialization._configuration()
    legacy.pop("execution")
    path = tmp_path / "legacy.yaml"
    path.write_text(yaml.safe_dump(legacy, sort_keys=False))
    monkeypatch.setattr(specialization, "CONFIG_PATH", path)
    resolved = resolve_task_env_config(PickCubeReferenceEnv, None)
    assert resolved.physics_provider == "geophys"
    assert resolved.render_default.provider == "none"


def test_optional_controller_identity_is_explicit_and_bound_identity_is_preserved():
    from types import SimpleNamespace

    from task_env.assembly.compiler import CompiledReferenceTaskV1
    from task_env.assembly.panda_box import compile_panda_box_task
    from task_env.tasks.pick_cube.specialization import _declaration, _environment_config

    compiled = compile_panda_box_task(_declaration(), config=_environment_config())
    assert compiled.controller is None
    assert compiled.identity_fields()["controller_identity"] is None

    bound = CompiledReferenceTaskV1(
        compiled.artifact, compiled.source, SimpleNamespace(identity="controller-v1"),
    )
    assert bound.identity_fields()["controller_identity"] == "controller-v1"


def test_position_end_payload_preserves_published_boundary_and_switch_status():
    from task_env.recorders.position_metadata import position_episode_end_payload

    state = SimpleNamespace(control_step=4, simulation_time=0.04)
    boundary = SimpleNamespace(boundary_id='published-boundary')
    controller = SimpleNamespace(identity='current-controller', profile_id='position-profile')
    pending = {'effective_control_step': 4, 'controller_identity': 'next-controller',
               'effective_boundary_id': 'published-boundary'}
    common = dict(state=state, boundary=boundary, source_closure_digest='source-digest',
                  controller=controller, position_profiles=(), pending_switch=pending,
                  runtime_step=lambda: 5)
    result = position_episode_end_payload(**common)
    assert result['state_boundary_id'] == 'published-boundary'
    assert result['control_step'] == 4 and result['simulation_time_s'] == 0.04
    assert result['controller_identity'] == 'current-controller'
    assert result['position_writers'] == ()
    assert result['pending_controller_switch_application']['status'] == 'not_attempted_before_episode_end'
    assert 'status' not in pending

    target = SimpleNamespace(identity_hash='target-hash')
    transition = (None, SimpleNamespace(controller_identity='next-controller', target=target,
                                      source_boundary=boundary),
                  SimpleNamespace(target_hash='target-hash'))
    result = position_episode_end_payload(**common, execution_fault=object(),
                                          last_transition=transition,
                                          switch_fault_receipt={'result': 'record_failed'})
    switch = result['pending_controller_switch_application']
    assert switch['status'] == 'target_ack_observed_but_transition_not_recorded'
    assert switch['observed_runtime_boundary'] == 5
    assert result['controller_switch_fault_receipt'] == {'result': 'record_failed'}


def test_mixed_stepwise_receipt_checks_count_and_first_target():
    from task_env.runtime.sessions.control import mixed_stepwise_receipt, mixed_substep_controller

    target = SimpleNamespace(identity_hash='target-1', to_mapping=lambda: {'value': 1})
    row = {'target_identity_sha256': 'target-1', 'target': {'value': 1},
           'applied': {'target_hash': 'target-1'}}
    receipts = [{'index': 0}, {'index': 1}]
    combined, applied = mixed_stepwise_receipt({'substeps': [row, row]}, receipts,
                                               substeps=2, target=target)
    assert applied == row['applied']
    assert [item['controller_receipt'] for item in combined['substeps']] == receipts
    assert 'controller_receipt' not in row
    with pytest.raises(ValueError, match='substep count'):
        mixed_stepwise_receipt({'substeps': [row]}, receipts, substeps=2, target=target)
    with pytest.raises(ValueError, match='first command'):
        mixed_stepwise_receipt({'substeps': [{**row, 'target_identity_sha256': 'wrong'}, row]},
                               receipts, substeps=2, target=target)
    callback, collected = mixed_substep_controller(lambda *_args: {'target': object()}, None, None)
    with pytest.raises(TypeError, match='unknown or missing fields'):
        callback(None, 0, 2, 0)
    assert collected == []


@pytest.mark.parametrize('task_class', [
    'task_env.tasks.pick_cube.specialization.PickCubeReferenceEnv',
    'task_env.tasks.nut_assembly.specialization.NutAssemblyReferenceEnv',
])
def test_direct_selected_constructor_revalidates_fabricated_resolved_config(task_class, monkeypatch):
    from dataclasses import replace
    from importlib import import_module
    module_name, class_name = task_class.rsplit('.', 1)
    module = import_module(module_name)
    cls = getattr(module, class_name)
    resolved = resolve_task_env_config(cls, None)
    bad = replace(resolved, physics_provider='not-a-provider')
    # The binding must not be built and no existing session can be touched.
    if hasattr(cls, 'selected_binding'):
        monkeypatch.setattr(cls, 'selected_binding', lambda *args: pytest.fail('binding reached'))
    else:
        monkeypatch.setattr(module, 'make_reference_binding', lambda **kwargs: pytest.fail('binding reached'))
    with pytest.raises(ValueError, match='unsupported selected physics'):
        cls.from_resolved_config(bad)


@pytest.mark.parametrize('provider,backend,device,host,engine', [
    ('mujoco', 'cpu', 'cpu', 'standalone', 'mujoco'),
    ('geophys', 'cpu', 'cpu', 'standalone', 'geophys'),
    ('isaacsim', 'cuda', 'cuda:0', 'isaacsim', 'physx'),
])
def test_layered_selected_route_resolves_without_native_build(provider, backend, device, host, engine):
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv
    execution = {'physics_provider': provider, 'physics_backend': backend, 'physics_device': device}
    if provider == 'isaacsim':
        execution['source_delivery_manifest'] = '/not-read-by-resolver/manifest.json'
    config = {'execution': execution}
    if provider == 'isaacsim':
        config['task'] = {'controller_profile': 'r3_continuous_v1'}
    selected = resolve_task_env_config(PickCubeReferenceEnv, config)
    route = selected.execution_spec_v2
    assert (route.host, route.engine, route.batch_layout) == (host, engine, 'scalar')
    assert route.native_dt is None
    assert route.physics_profile == 'unknown'
    assert resolve_task_env_config(PickCubeReferenceEnv, selected) == selected


def test_layered_route_rejects_unimplemented_selection_and_different_native_dt():
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv
    for override, message in [
        ({'engine': 'newton'}, 'no implemented adapter'),
        ({'host': 'isaacsim', 'engine': 'newton'}, 'no implemented adapter'),
        ({'batch_layout': 'native_batch'}, 'batch is not implemented'),
        ({'native_dt': 0.004}, 'no versioned mapping'),
    ]:
        with pytest.raises(ValueError, match=message):
            resolve_task_env_config(PickCubeReferenceEnv, {'execution': override})
    route = resolve_task_env_config(PickCubeReferenceEnv, {'execution': {'native_dt': 0.002}})
    assert route.execution_spec_v2.native_dt == 0.002
    remote = resolve_task_env_config(PickCubeReferenceEnv, {'execution': {'deployment': 'isolated_worker'}})
    assert remote.execution_spec_v2.deployment == 'isolated_worker'


def test_public_factory_consumes_same_layered_selected_resolution(monkeypatch):
    from task_env import registry
    target = _resolver_target()
    target.from_resolved_config = classmethod(lambda cls, resolved, **kwargs: resolved)
    monkeypatch.setattr(registry.ENV_REGISTRY, 'get', lambda uid: target)
    result = registry.make_env('resolver-target-v1', config={'provider': 'mujoco'})
    assert result.execution_spec_v2.physics_provider == 'mujoco'
    assert result.execution_spec_v2.engine == 'mujoco'
    assert result.execution_spec_v2.native_dt is None


def test_invalid_task_seed_rejects_before_existing_session_or_camera_close(monkeypatch):
    from types import SimpleNamespace
    from task_env import make_env
    env = make_env('nut-assembly-outcome-reference-v1', config={'provider': 'mujoco'})
    effects = []
    sentinel = SimpleNamespace(close=lambda: effects.append('session.close'))
    env.session = sentinel
    monkeypatch.setattr(env, '_close_camera_consumer', lambda: effects.append('camera.close'))
    try:
        with pytest.raises(ValueError, match='seed19'):
            env._prepare_reference_reset(seed=31)
        assert env.session is sentinel
        assert effects == []
    finally:
        env.session = None
        env.close()


def test_public_static_rejection_has_stable_json_receipt_and_no_binding(monkeypatch, tmp_path):
    import json
    from task_env import make_env
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv
    monkeypatch.setattr(PickCubeReferenceEnv, 'selected_binding', lambda *args: pytest.fail('binding reached'))
    def rejected(config):
        with pytest.raises(Exception) as failure:
            make_env('pick-cube-p16-reference-v1', config=config)
        error = failure.value
        assert error.phase == 'static_config'
        assert error.receipt['request_identity'] == error.request_identity
        assert error.receipt['native_effective']['status'] == 'unknown'
        assert json.loads(json.dumps(error.receipt)) == error.receipt
        return error.request_identity
    first = {'execution': {'engine': 'newton'}}
    assert rejected(first) == rejected(first)
    assert rejected(first) != rejected({'execution': {'host': 'isaacsim', 'engine': 'newton'}})
    bad_yaml = tmp_path / 'duplicate.yaml'
    bad_yaml.write_text('execution: {}\nexecution: {}\n')
    assert len(rejected(bad_yaml)) == 64
