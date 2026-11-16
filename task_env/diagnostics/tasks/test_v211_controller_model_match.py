"""Provider-free tests for subject channel/model compatibility at binding."""
from dataclasses import replace

import pytest

from task_env.controllers.canonical.model import ControllerModelRequirementV1
from task_env.controllers.canonical.physical_controller import (
    LinearEffortControllerV1,
    LinearEffortProfileV1,
)
from task_env.diagnostics.tasks.test_v211_physical_control_contract import _case


@pytest.mark.parametrize(
    ('kind', 'input_unit', 'output_unit'),
    [('revolute', 'rad', 'N*m'), ('prismatic', 'm', 'N')],
)
def test_model_joint_kind_is_checked_at_controller_binding(kind, input_unit, output_unit):
    compiled, _, _, _ = _case()
    channel = replace(compiled.binding.channels[0], kind=kind, unit=output_unit)
    binding = replace(compiled.binding, channels=(channel,))

    def candidate(model_input_unit):
        requirement = ControllerModelRequirementV1(
            'controller-model-requirement-v1', 'model', 'library', 'v1', 'dependency',
            binding.source_id, binding.source_closure_sha256, ('arm/drive',),
            (model_input_unit,), 'joint_bias', (output_unit,), 'joint-axis',
            'evaluation_boundary', .01, 0., 'pure_no_physics_step',
            'controller-a', 'none', 'required',
        )
        profile = LinearEffortProfileV1(
            'linear-effort-profile-v1', 'controller-a', ('action',),
            ('arm/drive',), ((1.,),), requirement,
        )

        class Model:
            identity_hash = 'c' * 64
            def __init__(self):
                self.requirement = requirement
                self.calls = 0
            def evaluate(self, state):
                self.calls += 1
                raise AssertionError('matching must not evaluate the model')
        return profile, Model()

    profile, model = candidate(input_unit)
    controller = LinearEffortControllerV1(profile, binding, model)
    assert controller.writer_id == 'controller-a'
    assert model.calls == 0

    wrong_unit = 'm' if input_unit == 'rad' else 'rad'
    profile, model = candidate(wrong_unit)
    with pytest.raises(ValueError, match='input units differ from bound joint kinds'):
        LinearEffortControllerV1(profile, binding, model)
    assert model.calls == 0
