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
