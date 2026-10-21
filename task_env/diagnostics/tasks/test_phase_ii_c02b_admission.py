"""C02b must fail before materialization when bound feedback is unadmitted."""

from types import SimpleNamespace

import pytest

from task_env.artifacts import CapabilityAdmissionError, ExecutionSpec
from task_env.diagnostics.tasks.test_phase_ii_c02a_controller_bindings import (
    _binding,
    _scene,
)
from task_env.runtime.sessions import control as control_sessions
from task_env.runtime.sessions.control import (
    ControlBinding,
    compile_control_binding_plan,
    materialize_control,
)
from task_env.runtime.sessions.api import provider_manifest


@pytest.mark.parametrize("provider", ("geophys", "mujoco"))
def test_c02b_materialization_fails_before_runtime_for_missing_feedback_capability(
    provider, monkeypatch,
):
    scene = _scene()
    binding_plan = compile_control_binding_plan(scene, (_binding(),))
    manifest = provider_manifest(provider)
    assert "actuator_force_query" not in {claim.name for claim in manifest.capabilities}

    source = SimpleNamespace(
        scene_definition=scene,
        joint_targets={f"actuator{index}": index for index in range(1, 8)},
        open_actuators=("actuator8",),
    )
    materialize_calls = []

    def unexpected_materialization(*args, **kwargs):
        materialize_calls.append((args, kwargs))
        raise AssertionError("unsupported feedback must reject before Runtime construction")

    monkeypatch.setattr(control_sessions, "materialize", unexpected_materialization)
    with pytest.raises(CapabilityAdmissionError, match="actuator_force_query"):
        materialize_control(
            object(),
            ExecutionSpec(provider, "p1_2_scalar_cpu_v0", "none", "cpu", 0, "strict"),
            source=source,
            binding=ControlBinding("panda-main/gripper", 0.08),
            controller_binding_plan=binding_plan,
        )

    assert materialize_calls == []


def test_legacy_materialize_control_without_binding_plan_keeps_existing_route(monkeypatch):
    provider = "mujoco"
    source = SimpleNamespace(
        joint_targets={f"actuator{index}": index for index in range(1, 8)},
        open_actuators=("actuator8",),
    )
    binding = ControlBinding("panda-main/gripper", 0.08)
    session = SimpleNamespace()

    def materialize(*_args, **_kwargs):
        return session

    monkeypatch.setattr(control_sessions, "materialize", materialize)
    result = materialize_control(
        object(),
        ExecutionSpec(provider, "p1_2_scalar_cpu_v0", "none", "cpu", 0, "strict"),
        source=source,
        binding=binding,
    )

    assert result is session
    assert result._control_binding is binding
