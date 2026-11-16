"""Provider-free failures for the source-bound operational-space Controller."""
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import pytest
from task_env.artifacts import FrameReference
from task_env.artifacts.state import StateBoundaryIdentity, StateSampleClock
from task_env.controllers.canonical.operational_space_effort import OperationalSpaceEffortControllerV1
from task_env.controllers.canonical.physical_commands import PhysicalCommandContextV1
from task_env.diagnostics.tasks.physical_contract_fixtures import _case


def test_operational_controller_rejects_foreign_model_and_invalid_input():
    plan, _, _, _ = _case()
    template = plan.binding.channels[0]
    channels = tuple(replace(template, joint_id=f'joint{i}', component_path=('arm', f'joint{i}'))
                     for i in range(1, 8))
    binding = replace(plan.binding, channels=channels)
    controller = OperationalSpaceEffortControllerV1(binding, tcp_frame=FrameReference('arm', 'tool'), cadence_s=.05)
    with pytest.raises(ValueError, match='source'):
        controller.bind_model(SimpleNamespace(source_id='foreign', source_closure_sha256=binding.source_closure_sha256,
                                               evaluate=lambda *args: None))
    with pytest.raises(ValueError, match='source'):
        controller.bind_model(SimpleNamespace(source_id=binding.source_id,
            source_closure_sha256=binding.source_closure_sha256,
            tcp_frame=FrameReference('arm', 'base'), evaluate=lambda *args: None))
    model = SimpleNamespace(source_id=binding.source_id, source_closure_sha256=binding.source_closure_sha256,
                            tcp_frame=controller.tcp_frame,
                            evaluate=lambda *args: pytest.fail('invalid action reached model'))
    controller.bind_model(model)
    boundary = StateBoundaryIdentity('state-boundary-identity-v1', 'episode', 'reset-'+'d'*64,
        binding.scene_sha256, 'scene', 'material', 0, 0)
    clock = StateSampleClock('state-sample-clock-v1', 'evaluation_boundary', 0, 0.)
    joints = tuple(SimpleNamespace(entity_id='arm', joint_id=f'joint{i}', position=(0.,), velocity=(0.,))
                   for i in range(1, 8))
    state = SimpleNamespace(boundary=boundary, sample_clock=clock, joints=joints)
    controller.reset_from_realized_state(state)
    context = PhysicalCommandContextV1('physical-command-context-v1', binding.source_id,
        binding.source_closure_sha256, binding.artifact_sha256, boundary, clock, 0, 1, .05, .05)
    for action in ([0.] * 8, [0.] * 7, [float('nan')] * 7):
        with pytest.raises(ValueError, match='pose'):
            controller.compute(action, state, context)
    controller.release_model()
    assert controller._model is None
