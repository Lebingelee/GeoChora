"""G05 USD effort admission remains source-bound on the shared preflight path."""

from types import SimpleNamespace

import pytest

from task_env.runtime.sessions.api import G05_ISAAC_EFFORT_PROFILE, _validate_g05_isaac_effort_source


def test_f06_capability_manifest_stays_source_bounded(monkeypatch):
    from task_env.runtime.sessions.api import _f06_pickcube_isaac_capability_manifest

    monkeypatch.setenv('GEOCHORA_SELECTED_ISAAC_VERSION', '6.2.0.0')
    manifest = _f06_pickcube_isaac_capability_manifest(None)
    assert manifest.provider_name == 'isaacsim'
    assert manifest.physics_profile == 'isaac-gpu-physx-pickcube-f06-v1'
    assert 'rgb_camera' in manifest.known_unsupported
    assert 'no provider-wide qualification' in manifest.evidence_reference
    monkeypatch.setenv('GEOCHORA_SELECTED_ISAAC_VERSION', 'foreign')
    with pytest.raises(ValueError, match='admitted Isaac release'):
        _f06_pickcube_isaac_capability_manifest(None)


@pytest.mark.parametrize('change', ['hash', 'representation', 'local_validation', 'upstream'])
def test_f06_delivery_admission_rejects_foreign_identity(change):
    from task_env.runtime.sessions.api import _validate_f06_isaac_delivery

    digest = '6cb07d216689d1e0b6f31ef127d9a511906be90c2acbecb9a30667cdebf113e2'
    delivery = SimpleNamespace(manifest_bytes_sha256=digest, locally_validated=True,
        source_verified=False,
        delivery=SimpleNamespace(representation_id='isaacsim-6.2.0.0-pickcube-desktop-v1'))
    _validate_f06_isaac_delivery(delivery, digest)
    if change == 'hash':
        delivery.manifest_bytes_sha256 = '0' * 64
    elif change == 'representation':
        delivery.delivery.representation_id = 'foreign'
    elif change == 'local_validation':
        delivery.locally_validated = False
    else:
        delivery.source_verified = True
    with pytest.raises(ValueError, match='exact locally validated'):
        _validate_f06_isaac_delivery(delivery, digest)


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


def test_usd_effort_binding_uses_physical_observation_and_no_position_composition():
    from task_env.observations.selected_reference import selected_reference_observation_spaces
    from task_env.tasks.pick_cube.task import PickCubeReferenceEnv, physical_observation

    binding = PickCubeReferenceEnv._build_selected_binding(_formal_isaac_joint_config())
    assert binding.scalar_control_binding is None
    assert binding.observation_projection.func is physical_observation
    assert binding.observation_space_factory.func is selected_reference_observation_spaces
    assert binding.compose_robot_source is None


def test_usd_effort_rebuild_uses_requested_episode_seed(monkeypatch):
    from task_env.tasks.pick_cube import specialization
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    calls = []
    def capture_builder(**kwargs):
        def build(request):
            calls.append(request)
            return {**kwargs, 'task_seed': request.seed, 'horizon': request.horizon}
        return build
    monkeypatch.setattr(specialization, '_isaac_reference_builder', capture_builder)
    config = _formal_isaac_joint_config()
    binding = PickCubeReferenceEnv._build_selected_binding(config)
    result = binding.build_for_request('isaacsim', 'cuda', 42, 8)
    assert result['task_seed'] == 42
    assert result['horizon'] == 8
    assert result['resolved_config'] is config.environment
    assert result['robot'] is binding.robot
    assert calls[0].binding is binding
    with pytest.raises(ValueError, match='provider differs'):
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
    from task_env.tasks.pick_cube import specialization
    from task_env.assembly import usd_delivery
    from task_env.runtime.sessions import source_composition_adapters
    from task_env.runtime.sessions import source as source_module

    def unexpected_mjcf(*args, **kwargs):
        pytest.fail('USD task construction must not compile an extra MJCF RuntimeSource')
    monkeypatch.setattr(specialization, 'compile_panda_box_task', unexpected_mjcf)

    dynamic_profiles = []
    original_profile = specialization._r3_dynamic_profile
    def capture_profile():
        profile = original_profile()
        dynamic_profiles.append(profile)
        return profile
    monkeypatch.setattr(specialization, '_r3_dynamic_profile', capture_profile)
    usd_bindings = []
    original_usd_bind = source_module.bind_declared_usd_paths
    def capture_usd_bind(*args, **kwargs):
        usd_bindings.append(kwargs)
        return original_usd_bind(*args, **kwargs)
    monkeypatch.setattr(source_module, 'bind_declared_usd_paths', capture_usd_bind)
    loads = []
    original_load = usd_delivery.load_usd_asset_delivery
    def record_load(*args, **kwargs):
        result = original_load(*args, **kwargs)
        loads.append(result)
        return result
    monkeypatch.setattr(usd_delivery, 'load_usd_asset_delivery', record_load)
    calls = []
    build = source_composition_adapters.build_panda_source_effort_profile
    def record(*args, **kwargs):
        calls.append(args[3])
        return build(*args, **kwargs)
    monkeypatch.setattr(source_composition_adapters, 'build_panda_source_effort_profile', record)

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
    if profile == 'r3_continuous_v1':
        assert len(dynamic_profiles) == 1
    assert len(loads) == 1
    assert len(usd_bindings) == 1
    assert usd_bindings[0]['world_bodies'] == {'cube-v1': 'cube_v1'}
    assert usd_bindings[0]['world_frames'] == {'tabletop-v1/top': 'tabletop_v1/top'}
    assert usd_bindings[0]['free_body_semantics'] == ('cube-v1',)
    assert value['source'].scene_source.loaded_delivery is loads[0]
    assert value['kinematics_source_xml'] == loads[0].source_input_bytes[
        loads[0].delivery.source_entry_file].decode('utf-8')
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


def test_readiness_from_resolved_config_matches_source_bound_readiness():
    from types import SimpleNamespace
    from task_env.tasks.pick_cube import specialization
    from task_env.tasks.pick_cube.solution import PickCubeReadinessConfig

    artifact = specialization.build_artifact()
    config = specialization._nut_aligned_environment_config(specialization._environment_config())
    dynamic, _ = specialization._r3_dynamic_profile()
    options = specialization._readiness_options(artifact, is_r3_profile=True, dynamic_profile=dynamic)
    source = SimpleNamespace(task_artifact_hash=artifact.identity_hash, config=config)
    expected = PickCubeReadinessConfig.from_source(artifact, source, **options)
    actual = PickCubeReadinessConfig.from_resolved_config(artifact, config, **options)
    assert actual == expected and actual.identity == expected.identity
    source.task_artifact_hash = 'foreign'
    with pytest.raises(ValueError, match='source/Artifact mismatch'):
        PickCubeReadinessConfig.from_source(artifact, source, **options)


def test_custom_action_config_produces_same_mjcf_and_usd_readiness():
    from dataclasses import replace
    from pathlib import Path
    from task_env.runtime.sessions.source import source_resource_receipt
    from task_env.tasks.pick_cube import specialization

    root = Path(__file__).resolve().parents[4]
    manifest = root / 'workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/isaac_usd_v2/delivery_manifest.json'
    if not manifest.is_file():
        pytest.skip('verified Isaac source delivery is unavailable')
    config = specialization._environment_config()
    changed = replace(config, action=replace(config.action,
        ik_position_deadband=config.action.ik_position_deadband * 2))
    mjcf = specialization.build_reference(controller_profile='r3_continuous_v1',
                                           resolved_config=changed, include_solution=False)
    try:
        usd = specialization.build_isaac_reference(delivery_manifest=manifest, horizon=8,
                                                   resolved_config=changed, include_solution=False)
        assert mjcf['readiness'].identity == usd['readiness'].identity
        default_solution = specialization.build_readiness_solution()
        assert mjcf['readiness'].identity != default_solution.readiness_config.identity
    finally:
        source_resource_receipt(mjcf['source']).close()


def test_usd_readiness_rejects_foreign_artifact_timebase(monkeypatch):
    from types import SimpleNamespace
    from task_env.runtime.sessions import isaac_usd_admission
    from task_env.tasks.pick_cube import specialization

    foreign = SimpleNamespace(artifact=SimpleNamespace(timebase=object()))
    monkeypatch.setattr(isaac_usd_admission, 'compile_f06_task_input',
                        lambda *args, **kwargs: foreign)
    with pytest.raises(ValueError, match='timebase differs'):
        specialization.build_isaac_reference(delivery_manifest='unused', include_solution=False)


def test_usd_rejects_unsupported_task_force():
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    with pytest.raises(ValueError, match='does not support the requested Task parameter'):
        resolve_task_env_config(PickCubeReferenceEnv, {
            'execution': {'physics_provider': 'isaacsim', 'physics_backend': 'cuda',
                          'physics_device': 'cuda:0', 'source_delivery_manifest': '/unused'},
            'controller': {'profile_id': 'r3_continuous_v1'}, 'task': {'cube_force_z_N': 1.},
        })


def test_position_binding_uses_selected_controller_identity_and_recorded_owner():
    import hashlib
    from pathlib import Path
    from task_env.recorders.position_metadata import position_control_binding_provenance
    from task_env.runtime.sessions import control

    class PositionController:
        def __init__(self, entity):
            self.entity_id = entity
            self.gripper_semantic_id = f'{entity}/gripper'
        def selected_position_capability(self):
            return control.SelectedPositionCapabilityV1(self)

    selector = control.position_control_binding_from_selected
    first, second = PositionController('robot-a'), PositionController('robot-b')
    binding = selector({'controller': [second, first]})
    assert binding.gripper_semantic_id == 'robot-a/gripper'
    provenance = position_control_binding_provenance(binding, selector)
    assert provenance['binding']['gripper_semantic_id'] == binding.gripper_semantic_id
    assert provenance['selector_source_sha256'] == hashlib.sha256(
        Path(control.__file__).read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='distinct Entities'):
        selector({'controller': [first, first]})
    with pytest.raises(TypeError, match='Controller capabilities'):
        selector({'controller': object()})


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
    identities = input_v1.construction_identity_fields()
    assert identities['runtime_source_id'] == value['source'].source_id
    assert identities['runtime_source_closure_sha256'] == value['source'].source_closure_digest
    assert identities['reset_plan_identity_sha256'] == value['reset_plan'].identity_hash
    assert identities['runtime_source_bindings']['joints'] == dict(value['source'].joints)
    assert all(value['resolved_configuration'][key] == item for key, item in identities.items())
    inventory = value['source_sha256']
    assert inventory['f06_delivery_manifest_sha256'] == input_v1.delivery_manifest_sha256
    assert 'task_env/runtime/sessions/isaac_usd_admission.py' in inventory
    assert 'task_env/runtime/sessions/provenance.py' in inventory
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


def test_usd_controller_failure_does_not_allocate_mjcf_snapshot(monkeypatch):
    from pathlib import Path
    from task_env.controllers.canonical.position_profile import PandaPositionServoProfileV1
    from task_env.runtime.sessions import source as source_module
    from task_env.tasks.pick_cube.specialization import build_isaac_reference

    root = Path(__file__).resolve().parents[4]
    manifest = root / 'workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/isaac_usd_v2/delivery_manifest.json'
    if not manifest.is_file():
        pytest.skip('verified Isaac source delivery is unavailable')
    def unexpected(*args, **kwargs):
        pytest.fail('USD construction must not allocate an MJCF snapshot')
    def reject(*args, **kwargs):
        raise RuntimeError('USD Controller rejected')
    monkeypatch.setattr(source_module, 'snapshot_legacy_mjcf_source', unexpected)
    monkeypatch.setattr(PandaPositionServoProfileV1, 'from_usd_source', reject)
    with pytest.raises(RuntimeError, match='USD Controller rejected'):
        build_isaac_reference(delivery_manifest=manifest, horizon=8, include_solution=False)


def test_usd_position_factory_rejects_unsupported_profile_before_materialization():
    from task_env.controllers.canonical.execution import build_reference_position_controller
    from task_env.runtime.sessions.source import UsdRuntimeSourceV1

    source = object.__new__(UsdRuntimeSourceV1)
    with pytest.raises(ValueError, match='requires the declared R3 Controller profile'):
        build_reference_position_controller(None, source, profile_id='r1')


def test_usd_controller_rejects_mismatched_compiled_source():
    from types import SimpleNamespace
    from task_env.runtime.sessions.source_composition_adapters import build_usd_panda_control

    artifact, source = object(), object()
    runtime_input = SimpleNamespace(artifact=artifact, runtime_source=object())
    with pytest.raises(ValueError, match='differs from the compiled Artifact or source'):
        build_usd_panda_control(artifact, source, runtime_input=runtime_input, robot=None,
            controller_profile='r3_continuous_v1', action_config=None, dynamic_profile=None,
            velocity_limit=2., tcp_profile=None, end_frame_id='ee')


def test_pickcube_usd_rejects_stale_source_before_controller_binding(tmp_path, monkeypatch):
    import sys
    from pathlib import Path
    from task_env.assembly.usd_cache import install_usd_delivery
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.pick_cube import specialization
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    root = Path(__file__).resolve().parents[4]
    original = root / 'workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/isaac_usd_v2/delivery_manifest.json'
    if not original.is_file():
        pytest.skip('verified Isaac source delivery is unavailable')
    manifest = install_usd_delivery(original, provider='isaacsim', robot_uid='panda-v1', root=tmp_path)
    from task_env.runtime.sessions import isaac_usd_admission
    build_input = isaac_usd_admission.compile_f06_task_input
    def corrupt_after_admission(*args, **kwargs):
        value = build_input(*args, **kwargs)
        delivery = value.runtime_source.scene_source.loaded_delivery
        entry = delivery.manifest_path.parent / delivery.delivery.source_entry_file
        entry.write_bytes(entry.read_bytes() + b'\n<!-- changed -->\n')
        return value
    monkeypatch.setattr(isaac_usd_admission, 'compile_f06_task_input', corrupt_after_admission)
    config = resolve_task_env_config(PickCubeReferenceEnv, {
        'execution': {'physics_provider': 'isaacsim', 'physics_backend': 'cuda',
                      'physics_device': 'cuda:0', 'deployment': 'in_process',
                      'interpreter': sys.executable, 'source_delivery_manifest': str(manifest)},
        'controller': {'profile_id': 'r3_continuous_v1'}, 'episode': {'horizon': 8},
    })
    binding = PickCubeReferenceEnv._build_selected_binding(config)
    with pytest.raises(ValueError, match='stale local USD original source'):
        binding.build_for_request('isaacsim', 'cuda', 31, 8)


def test_retired_f04_profile_is_rejected_before_native_initialization(monkeypatch):
    from types import SimpleNamespace
    from task_env.runtime.sessions.api import validate_selected_position_route
    from task_env.runtime.sessions import isaac_native_io

    execution = SimpleNamespace(physics_provider='isaacsim', physics_backend='cuda',
        physics_device='cuda:0', determinism_mode='best_effort',
        physics_profile='isaac-gpu-physx-f04-position-v1')
    with pytest.raises(ValueError, match='unsupported provider execution route'):
        validate_selected_position_route(execution)
    monkeypatch.setattr(isaac_native_io, '_process_app_owner', lambda **_kwargs:
                        pytest.fail('retired profile must not create an Isaac App'))
    source = SimpleNamespace(assert_fresh=lambda: None)
    with pytest.raises(ValueError, match='unsupported Isaac native execution profile'):
        isaac_native_io.create_isaac_native_runtime_io(object(), execution, source)
