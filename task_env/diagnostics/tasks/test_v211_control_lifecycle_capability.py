"""Provider-free checks for declaration-driven default and R3 dispatch."""
from types import SimpleNamespace

import pytest

from task_env.controllers.canonical.execution import ReferenceExecutionController, StableArmTargetHold
from task_env.runtime.sessions.control_lifecycle import (
    has_canonical_position_control_capability,
    prepare_selected_control_action,
)
from task_env.diagnostics.tasks.test_v211_control_submission_contract import _Session


class _DeclaredController:
    control_submission_capabilities = frozenset({'canonical-position-target-v1'})
    control_submission_writer_id = 'declared-controller-writer-v1'
    identity = 'declared-controller-identity'
    generation = 0

    def compute(self, *_args):
        return None


def _environment(controller):
    session = _Session()
    source = SimpleNamespace(source_id='task', source_closure_digest='a' * 64)
    return SimpleNamespace(
        _stopped=False,
        session=session,
        binding=SimpleNamespace(physical_control_profile=None),
        mixed_control_profile=False,
        position_profiles=(),
        position_plan=None,
        value={'source': source},
        artifact=SimpleNamespace(identity_hash='b' * 64),
        controller=controller,
        _episode_mode=None,
        _prepare_reference_step=lambda action: ('reference', action),
    )


@pytest.mark.parametrize('wrapped', (False, True), ids=('default-r1-declaration', 'r3-wrapper'))
def test_default_and_r3_controller_declarations_install_common_lifecycle(wrapped):
    controller = _DeclaredController()
    if wrapped:
        r3 = object.__new__(ReferenceExecutionController)
        r3.hold = StableArmTargetHold(controller)
        controller = r3
    env = _environment(controller)
    assert has_canonical_position_control_capability(env)
    assert prepare_selected_control_action(env, 'action') == ('reference', 'action')
    dispatch = env.session._control_lifecycle_dispatch
    assert dispatch.source_id == 'task'
    assert dispatch.controller_identities == ('declared-controller-identity',)
    assert dispatch.stage == 'prepared'


def test_capability_dispatch_does_not_require_source_composition_request_or_panda_class():
    controller = _DeclaredController()
    env = _environment(controller)
    assert 'source_composition_request' not in env.value['source'].__dict__
    assert has_canonical_position_control_capability(env)
    prepare_selected_control_action(env, 'action')
    assert env.session._control_lifecycle_dispatch.stage == 'prepared'


@pytest.mark.parametrize('admitted', [False, True])
def test_position_array_admission_belongs_to_task_binding(monkeypatch, admitted):
    from task_env.controllers.canonical.contracts import StructuredActionRequestV1
    from task_env.runtime.sessions import control

    env = _environment(_DeclaredController())
    env.horizon = 4
    env.state = SimpleNamespace(control_step=0)
    env.position_profiles = (_DeclaredController(),)
    env.position_plan = object()
    env.position_scene = object()
    # A historical task key alone must not grant plain-array admission.
    if not admitted:
        env.value['f06_pickcube_isaac_input'] = object()
    env.binding.legacy_position_expert_admission = lambda _value: admitted
    request = object.__new__(StructuredActionRequestV1)
    converted = []
    monkeypatch.setattr(control, 'single_position_action_request',
                        lambda action, **_kwargs: converted.append(action) or request)
    monkeypatch.setattr(control, 'prepare_structured_action', lambda *_args: None)
    env._prepare_position_profile = lambda action: action
    action = [.1] * 8
    if admitted:
        assert prepare_selected_control_action(env, action) is request
        assert converted == [action]
        assert env.session._control_lifecycle_dispatch.stage == 'prepared'
    else:
        with pytest.raises(TypeError, match='StructuredActionRequestV1'):
            prepare_selected_control_action(env, action)
        assert converted == []


@pytest.mark.parametrize('provider,backend,module,method', [
    ('mujoco', 'cpu', 'mujoco_physical', 'preflight_physical_mujoco'),
    ('geophys', 'cpu', 'geophys_physical', 'preflight_physical_geophys'),
    ('isaacsim', 'cuda', 'isaac_physical', 'preflight_physical_isaac'),
])
def test_physical_execution_delegates_admission_to_adapter(monkeypatch, provider, backend, module, method):
    from importlib import import_module
    from task_env.runtime.sessions.physical_control import PhysicalControlExecutionV1

    owner = import_module('task_env.runtime.sessions.' + module)
    execution = object.__new__(PhysicalControlExecutionV1)
    artifact, source = object(), object()
    calls = []
    monkeypatch.setattr(owner, method, lambda *args: calls.append(args))
    execution.preflight(provider=provider, backend=backend, artifact=artifact, source=source)
    assert calls == [(execution, artifact, source)]


def test_unsupported_physical_adapter_rejects_before_adapter_import(monkeypatch):
    import importlib
    from task_env.environment.types import StageUnavailableError
    from task_env.runtime.sessions.physical_control import PhysicalControlExecutionV1

    monkeypatch.setattr(importlib, 'import_module',
                        lambda *_args: pytest.fail('unsupported adapter must not import a provider'))
    execution = object.__new__(PhysicalControlExecutionV1)
    with pytest.raises(StageUnavailableError, match='not implemented'):
        execution.preflight(provider='mujoco', backend='cuda', artifact=object(), source=object())


@pytest.mark.parametrize('controller_started', (False, True))
def test_physical_preparation_faults_only_after_unrecoverable_controller_work(controller_started):
    from task_env.runtime.sessions.physical_control import PhysicalControlExecutionV1

    env = _environment(_DeclaredController())
    profile = object.__new__(PhysicalControlExecutionV1)
    object.__setattr__(profile, 'controllers', (_DeclaredController(),))
    object.__setattr__(profile, 'generation', 0)
    env.binding.physical_control_profile = lambda _env: profile
    env.state = object()
    faults = []
    env._latch_fault = lambda phase, error, **kwargs: faults.append((phase, error, kwargs))

    def prepare(_action):
        env._physical_controller_preparation_started = controller_started
        raise ValueError('preflight failed')

    env._prepare_physical_control = prepare
    with pytest.raises(ValueError, match='preflight failed'):
        prepare_selected_control_action(env, 'action')
    assert bool(faults) is controller_started
    assert env._physical_controller_preparation_started is False


@pytest.mark.parametrize('controller_started', (False, True))
def test_mixed_preparation_latches_if_controller_may_have_changed(controller_started):
    from task_env.environment.reference_env import SelectedReferenceEnv

    env = SimpleNamespace(state=object())
    faults = []
    env._latch_fault = lambda phase, error, **kwargs: faults.append((phase, error, kwargs))

    def prepare(_action, **_kwargs):
        env._mixed_controller_preparation_started = controller_started
        raise ValueError('preflight failed')

    env._prepare_mixed_control_impl = prepare
    with pytest.raises(ValueError, match='preflight failed'):
        SelectedReferenceEnv._prepare_mixed_control(env, 'action')
    assert bool(faults) is controller_started
    assert env._mixed_controller_preparation_started is False


def test_source_composition_provider_dispatch_selects_only_registered_real_adapter():
    import inspect
    from task_env.runtime.sessions.source_composition_adapters import (
        SourceCompositionCapabilityUnavailable,
        resolve_pickcube_robot_source_adapter,
    )
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    adapter = resolve_pickcube_robot_source_adapter('mujoco', 'cpu')
    assert adapter.capability_id == 'pickcube-robot-source-composition-v1'
    assert adapter.provider == 'mujoco' and adapter.backend == 'cpu'
    with pytest.raises(SourceCompositionCapabilityUnavailable, match='registered'):
        resolve_pickcube_robot_source_adapter('isaacsim', 'cpu')
    selected_binding_source = inspect.getsource(PickCubeReferenceEnv.selected_binding)
    assert 'mujoco_composition' not in selected_binding_source
    assert "('mujoco', 'cpu')" not in selected_binding_source
