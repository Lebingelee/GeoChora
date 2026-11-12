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


def _formal_isaac_joint_config():
    import sys
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    return resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'isaacsim', 'physics_backend': 'cuda',
                      'physics_device': 'cuda:0', 'deployment': 'in_process',
                      'interpreter': sys.executable, 'source_delivery_manifest': 'declared'},
        'episode': {'horizon': 8},
        'controller': {'profile_id': 'panda-joint-effort-reference-v1'},
    })


def test_usd_effort_binding_does_not_request_position_source_composition(monkeypatch):
    from task_env.observations.selected_reference import selected_reference_observation_spaces
    from task_env.tasks.pick_cube.task import PickCubeReferenceEnv, physical_observation
    from task_env.tasks.pick_cube import specialization

    def reject_position_binding(*args, **kwargs):
        pytest.fail('physical construction must not create a Position binding')
    monkeypatch.setattr(specialization, 'make_reference_binding', reject_position_binding)

    binding = PickCubeReferenceEnv._build_selected_binding(_formal_isaac_joint_config())
    assert binding.scalar_control_binding is None
    assert binding.observation_projection.func is physical_observation
    assert binding.observation_space_factory.func is selected_reference_observation_spaces
    assert binding.compose_robot_source is None


def test_usd_effort_rebuild_uses_requested_episode_seed(monkeypatch):
    from task_env.tasks.pick_cube import specialization
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    calls = []
    monkeypatch.setattr(specialization, 'build_isaac_reference',
                        lambda **kwargs: calls.append(kwargs) or kwargs)
    config = _formal_isaac_joint_config()
    binding = PickCubeReferenceEnv._build_selected_binding(config)
    result = binding.build_for_request('isaacsim', 'cuda', 42, 8)
    assert result['task_seed'] == 42
    assert result['horizon'] == 8
    assert result['resolved_config'] is config.environment
    assert result['robot'] is binding.robot
    with pytest.raises(ValueError, match='Isaac CUDA'):
        binding.build_for_request('mujoco', 'cpu', 42, 8)
    with pytest.raises(ValueError, match='horizon'):
        binding.build_for_request('isaacsim', 'cuda', 42, 1001)


def test_reset_reconstruction_passes_one_request_for_sampled_and_solution_paths():
    from task_env.environment.reference_binding import _StandardResetReconstruction

    binding = SimpleNamespace(compose_robot_source=None,
        build_for_request=lambda provider, backend, seed, horizon, sampled:
            (provider, backend, seed, horizon, sampled))
    strategy = _StandardResetReconstruction(binding, 'mujoco', 'cpu', 8)
    strategy.sampled_reset = (1., 2.)
    assert strategy.initial(seed=31) == ('mujoco', 'cpu', 31, 8, None)
    assert strategy.build_reset({}, 42, None) == ('mujoco', 'cpu', 42, 8, (1., 2.))
    assert strategy.build_reset({}, 42, object()) == ('mujoco', 'cpu', 42, 8, None)


@pytest.mark.parametrize('profile', ['r3_continuous_v1', 'panda-direct-effort-v1',
                                    'panda-joint-effort-reference-v1'])
def test_usd_formal_task_lift_reaches_artifact_and_reset(profile, monkeypatch):
    import sys
    from pathlib import Path
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv, build_artifact
    from task_env.runtime.sessions import source_composition_adapters

    calls = []
    build = source_composition_adapters.build_panda_effort_execution
    def record(*args, **kwargs):
        calls.append(args[3])
        return build(*args, **kwargs)
    monkeypatch.setattr(source_composition_adapters, 'build_panda_effort_execution', record)

    root = Path(__file__).resolve().parents[4]
    manifest = root / 'workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/isaac_usd_v2/delivery_manifest.json'
    if not manifest.is_file():
        pytest.skip('verified Isaac source delivery is unavailable')
    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'isaacsim', 'physics_backend': 'cuda',
                      'physics_device': 'cuda:0', 'source_delivery_manifest': str(manifest),
                      'deployment': 'in_process', 'interpreter': sys.executable},
        'controller': {'profile_id': profile}, 'episode': {'horizon': 8},
        'task': {'lift_height_m': .17},
    })
    binding = PickCubeReferenceEnv.selected_binding(config)
    value = binding.build_for_request('isaacsim', 'cuda', 42, 8)
    artifact = value['artifact']
    assert artifact.semantics.parameters_si['lift_height'] == .17
    assert artifact.initialization.joint_position == build_artifact(lift_height_m=.17).initialization.joint_position
    assert value['reset_plan'].reset_sample.task_artifact_hash == artifact.identity_hash
    if profile != 'r3_continuous_v1':
        from task_env.runtime.sessions.isaac_physical import build_isaac_panda_effort_execution
        from task_env.runtime.sessions.control import bind_selected_controller
        source = value['source']
        assert calls == [source]
        selected = bind_selected_controller(value, binding=binding, provider='isaacsim', backend='cuda')
        assert selected.selection_matches[0].selection_profile_id == profile
        assert selected.physical_execution is value['physical_execution']
        assert 'task_env/runtime/sessions/isaac_physical.py' in value['source_sha256']
        assert 'task_env/runtime/sessions/source_composition_adapters.py' in value['source_sha256']
        expected_drive = 'position' if profile == 'panda-direct-effort-v1' else 'disabled'
        assert {channel.native_drive for channel in value['physical_execution'].compiled.binding.channels} == {expected_drive}
        with pytest.raises(ValueError, match='drive differs'):
            build_isaac_panda_effort_execution(value['robot'], source.scene_definition,
                artifact, source, native_drive='disabled' if expected_drive == 'position' else 'position')
    else:
        assert calls == []


def test_usd_rejects_unsupported_task_force():
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    with pytest.raises(ValueError, match='does not support the requested Task parameter'):
        resolve_task_env_config(PickCubeReferenceEnv, {
            'execution': {'physics_provider': 'isaacsim', 'physics_backend': 'cuda',
                          'physics_device': 'cuda:0', 'source_delivery_manifest': '/unused'},
            'controller': {'profile_id': 'r3_continuous_v1'}, 'task': {'cube_force_z_N': 1.},
        })


def test_usd_position_compiles_robot_subject_and_actual_controller_plan(monkeypatch):
    from dataclasses import replace
    from pathlib import Path
    from task_env.robots.runtime import RobotRuntime
    from task_env.runtime.sessions.control import (bind_selected_controller,
        position_subject_identity, prepare_position_control_materialization)
    from task_env.runtime.sessions.source import PositionSubjectPlanV1
    from task_env.tasks.pick_cube.specialization import build_isaac_reference, make_reference_binding

    root = Path(__file__).resolve().parents[4]
    manifest = root / 'workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/isaac_usd_v2/delivery_manifest.json'
    if not manifest.is_file():
        pytest.skip('verified Isaac source delivery is unavailable')
    from task_env.controllers.canonical.execution import ReferenceExecutionController
    def reject_unused_controller(*args, **kwargs):
        pytest.fail('USD Position must not construct an unused MJCF Controller')
    monkeypatch.setattr(ReferenceExecutionController, 'from_source', reject_unused_controller)
    value = build_isaac_reference(delivery_manifest=manifest, horizon=8, include_solution=False)
    binding = make_reference_binding(controller_profile='r3_continuous_v1', source_delivery_manifest=manifest)
    selected = bind_selected_controller(value, binding=binding, provider='isaacsim', backend='cuda')
    robot = RobotRuntime.from_selected(value, selected)
    plan, _, _, _ = prepare_position_control_materialization(
        source=value['source'], artifact=value['artifact'], profiles=selected.position_profiles,
        plan=None,
        select_binding=binding.position_control_binding, value=value,
        capabilities=selected.position_capabilities)
    assert robot.uid == 'panda-v1'
    assert robot.declaration is value['robot']
    with pytest.raises(ValueError, match='selected Robot declaration'):
        RobotRuntime.from_selected(value, selected, robot=SimpleNamespace(uid='panda-v1'))
    assert robot.subjects == value['source'].position_subject_plan.subjects
    assert robot.controller is value['controller']
    assert plan is value['source'].position_subject_plan.plan
    assert value['controller'].source is value['source'] is value['session_admission_input'].runtime_source
    assert binding.reset_runtime_input(value) is value['session_admission_input']
    assert binding.position_control_binding(value).gripper_semantic_id == 'panda-v1/gripper'
    assert robot.subjects[0].controller_writers == (robot.controller.writer_id,)
    assert selected.selection_matches[0].subject_ids == (robot.subjects[0].subject_id,)
    from task_env.runtime.sessions.control import prepare_structured_action
    request = selected.controller.prepare_action_request(
        [.4, 0., .4, 1., 0., 0., 0., 1.], scene=value['source'].scene_definition, plan=plan)
    projections = prepare_structured_action(plan, request)
    assert len(projections) == 1
    with pytest.raises(ValueError, match='finite eight-dimensional'):
        selected.controller.prepare_action_request([0.], scene=value['source'].scene_definition, plan=plan)
    from task_env.runtime.sessions.api import _validate_usd_task_policy, _F06_TASK_POLICY_SHA256_V1
    input_v1 = value['session_admission_input']
    changed_targets = dict(value['source'].joint_targets)
    changed_targets[next(iter(changed_targets))] = 'foreign-native-joint'
    changed_source = replace(value['source'], joint_targets=changed_targets)
    with pytest.raises(ValueError, match='exact task binding map'):
        _validate_usd_task_policy(replace(input_v1, runtime_source=changed_source),
                                  _F06_TASK_POLICY_SHA256_V1)
    without_subjects = {**value, 'source': replace(value['source'], position_subject_plan=None)}
    with pytest.raises(ValueError, match='requires source-owned subjects'):
        bind_selected_controller(without_subjects, binding=binding, provider='isaacsim', backend='cuda')
    wrong_writers = (replace(robot.subjects[0], controller_writers=('foreign-writer',)),)
    with pytest.raises(ValueError, match='Controller resource owners'):
        PositionSubjectPlanV1(plan, position_subject_identity(plan, wrong_writers), wrong_writers)
    foreign_subjects = (replace(robot.subjects[0], source_id='foreign-source'),)
    foreign_plan = PositionSubjectPlanV1(plan, position_subject_identity(plan, foreign_subjects), foreign_subjects)
    with pytest.raises(ValueError, match='differ from their Scene, Artifact or source'):
        replace(value['source'], position_subject_plan=foreign_plan)


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
