"""G05 USD effort admission remains source-bound on the shared preflight path."""

from types import SimpleNamespace

import pytest

from task_env.runtime.sessions.api import G05_ISAAC_EFFORT_PROFILE, _validate_g05_isaac_effort_source


def test_g05_effort_rejects_foreign_delivery_and_timebase():
    renderer = SimpleNamespace(provider='none', backend='cpu', profile='none', device=None)
    execution = SimpleNamespace(physics_provider='isaacsim', physics_backend='cuda',
        physics_device='cuda:0', physics_profile=G05_ISAAC_EFFORT_PROFILE,
        determinism_mode='best_effort', render_default=renderer, camera_overrides=(), validate=lambda: None)
    artifact = SimpleNamespace(identity_hash='artifact', scene_identity_hash='scene',
        timebase=SimpleNamespace(physics_dt=.002, control_substeps=25, control_dt=.05))
    representation = SimpleNamespace(provider='isaacsim', provider_build_identity='isaacsim-6.2.0.0',
        representation_format='usd', runtime_admitted=False)
    delivery = SimpleNamespace(locally_validated=True, source_verified=False,
        delivery=SimpleNamespace(representation_id='isaacsim-6.2.0.0-g05-mjcf-v1'))
    source = SimpleNamespace(validate=lambda: None, task_artifact=artifact,
        scene_definition=SimpleNamespace(identity_hash='scene'),
        scene_source=SimpleNamespace(representation=representation, loaded_delivery=delivery),
        joints={'joint': 'joint'}, joint_targets={'joint': 'joint'})
    _validate_g05_isaac_effort_source(artifact, execution, source)
    delivery.delivery.representation_id = 'foreign'
    with pytest.raises(ValueError, match='reviewed MJCF conversion'):
        _validate_g05_isaac_effort_source(artifact, execution, source)
    delivery.delivery.representation_id = 'isaacsim-6.2.0.0-g05-mjcf-v1'
    artifact.timebase.control_substeps = 24
    with pytest.raises(ValueError, match='25 substep'):
        _validate_g05_isaac_effort_source(artifact, execution, source)


def test_compiled_action_contract_requires_a_real_physical_execution():
    from dataclasses import replace
    from task_env.tasks.pick_cube.specialization import make_reference_binding

    binding = replace(make_reference_binding(), action_schema=None, action_space_factory=None)
    with pytest.raises(ValueError, match='requires its execution'):
        binding.bind_compiled_control({})
    with pytest.raises(TypeError, match='requires PhysicalControlExecutionV1'):
        binding.bind_compiled_control({'physical_execution': object()})


def test_usd_effort_binding_does_not_request_position_source_composition():
    from task_env.tasks.pick_cube.physical_isaac_candidate import make_isaac_physical_binding
    from task_env.tasks.pick_cube.task import PickCubeReferenceEnv

    binding = make_isaac_physical_binding(delivery_manifest='unused-until-build', seed=31,
        horizon=8, drive_mode='effort-only', control_kind='joint')
    assert binding.scalar_control_binding is None
    assert PickCubeReferenceEnv._bind_robot_source_composer(binding, object()) is binding


def test_isaac_position_input_dispatch_requires_exact_formal_type_and_schema():
    from task_env.runtime.sessions.api import _session_admission_input_route
    from task_env.runtime.sessions.source import UsdRuntimeInputV1

    value = object.__new__(UsdRuntimeInputV1)
    object.__setattr__(value, 'schema_version', 'pick-cube-isaac-runtime-input-v1')
    assert _session_admission_input_route(value) == 'f06_pickcube'
    object.__setattr__(value, 'schema_version', 'old-position-input-v1')
    with pytest.raises(TypeError, match='exact supported task runtime input'):
        _session_admission_input_route(value)
    with pytest.raises(TypeError, match='exact supported task runtime input'):
        _session_admission_input_route(object())
