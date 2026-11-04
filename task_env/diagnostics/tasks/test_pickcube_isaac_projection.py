"""Focused F06 PickCube-to-Isaac canonical projection checks."""

import pytest

from task_env.tasks.pick_cube.specialization import compile_pickcube_isaac_task_artifact
from task_env.tasks.pick_cube.task import _configuration, build_artifact


def test_session_admission_dispatch_uses_exact_pickcube_runtime_input_type():
    from types import SimpleNamespace

    from task_env.runtime.sessions.api import _session_admission_input_route
    from task_env.runtime.sessions.source import UsdRuntimeInputV1

    runtime_input = object.__new__(UsdRuntimeInputV1)
    object.__setattr__(runtime_input, 'schema_version', 'pick-cube-isaac-runtime-input-v1')
    assert _session_admission_input_route(runtime_input) == 'f06_pickcube'
    object.__setattr__(runtime_input, 'schema_version', 'unrelated-usd-runtime-input-v1')
    with pytest.raises(TypeError, match='exact supported task runtime input'):
        _session_admission_input_route(runtime_input)
    with pytest.raises(TypeError, match='exact supported task runtime input'):
        _session_admission_input_route(SimpleNamespace())


def test_pickcube_isaac_projection_preserves_task_semantics_and_binds_runtime_frames():
    legacy = build_artifact()
    task_source, scene, artifact = compile_pickcube_isaac_task_artifact(
        _configuration(), legacy,
    )

    assert artifact.source_artifact_identity_hash == legacy.identity_hash
    assert task_source.task_id == legacy.task_id == "pick-cube-v1"
    assert scene.scene_id == "tabletop-v1"
    assert {entity.entity_id for entity in scene.entities} == {
        "panda-v1", "cube-v1", "tabletop-v1",
    }
    assets = {asset.asset_id: asset for asset in scene.assets}
    panda_asset = assets["f05-dg03-menagerie-panda-source-preserving-isaac-usd"]
    assert panda_asset.asset_version == "f05-dg03-isaac-usd-v4"
    assert panda_asset.source_reference == "mujoco-menagerie://franka_emika_panda/panda.xml"
    assert panda_asset.source_revision == "b846dd12bc459d776cccb3dee0b1d02acbf7a9c7"
    assert panda_asset.source_content_sha256 == (
        "a59a66d0b176cb6b2634d54cd20744752742b425e5524db1b865dda0eb3adf2a"
    )
    assert assets["pick-cube-cube-v1"].source_content_sha256
    assert assets["pick-cube-tabletop-v1"].source_content_sha256 == (
        assets["pick-cube-cube-v1"].source_content_sha256
    )
    assert artifact.legacy_frame_bindings["panda-v1/base"].frame_id == "link0"
    assert artifact.legacy_frame_bindings["panda-v1/ee"].frame_id == "ee"
    assert artifact.legacy_frame_bindings["cube-v1"].frame_id == "cube"
    frame = next(
        item for item in scene.frames
        if (item.entity_id, item.frame_id) == ("tabletop-v1", "top")
    )
    assert frame.frame_kind == "runtime"

    floating = [
        joint
        for articulation in scene.articulations
        if articulation.entity_id == "cube-v1"
        for joint in articulation.joints
        if joint.kind == "floating"
    ]
    assert len(floating) == 1
    assert floating[0].joint_id == "cube_freejoint"
    panda_joints = {
        joint.joint_id
        for articulation in scene.articulations
        if articulation.entity_id == "panda-v1"
        for joint in articulation.joints
    }
    assert {
        *(f"joint{index}" for index in range(1, 8)),
        "finger_joint1", "finger_joint2",
    } <= panda_joints
    assert len(artifact.legacy_joint_bindings) == 9
    artifact.validate_scene(scene)


def test_task_owned_f06_bindings_match_trusted_policy_without_native_import():
    from types import SimpleNamespace as NS
    from task_env.controllers.canonical.contracts import digest
    from task_env.runtime.sessions.api import _F06_TASK_POLICY_SHA256_V1
    from task_env.tasks.pick_cube.specialization import _source_bindings

    names = [*(f'joint{i}' for i in range(1, 8)), 'finger_joint1', 'finger_joint2']
    scene = NS(articulations=[NS(entity_id='panda-v1', joints=[
        NS(joint_id=name, kind='prismatic' if name.startswith('finger') else 'revolute')
        for name in names
    ])])
    artifact = NS(legacy_joint_bindings={f'panda-v1/{name}': None for name in names},
                  legacy_frame_bindings={key: None for key in
                      ('panda-v1/base', 'cube-v1', 'panda-v1/ee', 'tabletop-v1/top')},
                  initialization=NS(poses_world={'cube-v1': None}))
    joints, bodies, frames, free_joints = _source_bindings(scene, artifact)
    policy = {
        'schema_version': 'usd-task-admission-policy-v1',
        'bindings': {'joints': joints, 'joint_targets': dict(joints), 'bodies': bodies,
                     'frames': frames, 'free_joints': free_joints},
        'controller_profile': 'r3_continuous_v1', 'horizon_min': 1, 'horizon_max': 1000,
    }
    assert digest(policy) == _F06_TASK_POLICY_SHA256_V1


def test_f06_pickcube_tcp_is_the_task_ee_site_offset():
    from task_env.controllers.canonical.kinematics import PANDA_PICKCUBE_EE_TCP_V1

    assert PANDA_PICKCUBE_EE_TCP_V1.to_mapping() == {
        'schema_version': 'panda-tcp-profile-v1',
        'tcp_id': 'panda-v1/pickcube-ee-offset-v1',
        'hand_frame_id': 'hand',
        'position_m': [0.0, 0.0, 0.0584],
        'quaternion_wxyz': [1.0, 0.0, 0.0, 0.0],
    }


def test_f06_isaac_native_mimic_reset_commands_use_pickcube_entity_identity():
    from task_env.artifacts import JointReference
    from task_env.runtime.sessions.leaf_control import (
        IsaacNamedPositionDriveV1,
        IsaacNativeMimicPositionDriveReceiptV1,
    )

    entity_id = 'panda-v1'
    native_names = tuple(
        [f'joint{index}' for index in range(1, 8)]
        + ['finger_joint1', 'finger_joint2']
    )
    limits = {name: (-2.9, 2.9) for name in native_names[:7]}
    limits.update({'finger_joint1': (0.0, 0.04), 'finger_joint2': (0.0, 0.04)})
    active_ids = tuple(
        [f'joint{index}' for index in range(1, 8)] + ['finger_joint1']
    )
    drives = tuple(
        IsaacNamedPositionDriveV1(
            'isaac-named-position-drive-v1',
            JointReference(entity_id, joint_id), native_name, native_names.index(native_name),
            'meter' if joint_id == 'finger_joint1' else 'radian',
            *limits[native_name],
        )
        for joint_id, native_name in zip(active_ids, active_ids, strict=True)
    )
    receipt = IsaacNativeMimicPositionDriveReceiptV1(
        'isaac-native-mimic-position-drive-receipt-v1', 'synthetic_fixture',
        'a' * 64, 'b' * 64, 'c' * 64, 'isaacsim-6.2.0.0',
        'isaac-gpu-physx-pickcube-f06-v1', 'cuda', 'cuda:0', 'best_effort',
        0.002, 5, f'{entity_id}/position-servo-v1', native_names, limits, drives,
        gripper_drive_stiffness_N_m=5000.0,
        gripper_drive_damping_N_s_m=120.0,
        gripper_force_limit_N=5.0,
    )

    arm = {f'{entity_id}/joint{index}': float(index) / 10.0 for index in range(1, 8)}
    targets = receipt.commands(arm, 0.06)

    assert tuple(name for _index, name, _value in targets) == active_ids
    assert tuple(value for _index, _name, value in targets[:7]) == tuple(arm.values())
    assert targets[-1] == (7, 'finger_joint1', 0.03)
    try:
        receipt.commands(
            {f'panda-main/joint{index}': 0.0 for index in range(1, 8)}, 0.06,
        )
    except ValueError:
        pass
    else:
        raise AssertionError('F06 receipt accepted DG04 canonical entity names')


def test_pickcube_position_evaluation_projection_remains_canonical_state_v0():
    from types import SimpleNamespace

    from task_env.artifacts import CanonicalStateView, PoseWorld
    from task_env.tasks.pick_cube.task import evaluate
    from task_env.tasks.reference_env import _position_task_evaluation_state

    entity = 'panda-v1'
    names = tuple(f'{entity}/joint{index}' for index in range(1, 8)) + (
        f'{entity}/finger_joint1', f'{entity}/finger_joint2',
    )
    positions = {name: 0.0 for name in names}
    velocities = {name: 0.0 for name in names}
    cube = PoseWorld((0.55, 0.0, 0.49), (1.0, 0.0, 0.0, 0.0))
    ee = PoseWorld((0.50, 0.0, 0.50), (1.0, 0.0, 0.0, 0.0))
    state = CanonicalStateView(
        'canonical-state-v0', 'SI_right_handed_z_up_wxyz', 0, 0.0,
        positions, velocities, {'cube-v1': cube},
    )
    adapted = SimpleNamespace(
        joint_position=positions, joint_velocity=velocities,
        pose_world={f'{entity}/ee': ee},
    )

    projected = _position_task_evaluation_state(state, adapted)
    result = evaluate(projected, build_artifact().semantics)

    assert isinstance(projected, CanonicalStateView)
    assert projected.pose_world[f'{entity}/ee'] == ee
    assert result.metrics['cube_x'] == cube.position[0]


def test_f06_external_binding_constructs_only_the_solution_free_source_once():
    from unittest.mock import patch

    from task_env.tasks.pick_cube.task import make_reference_binding

    manifest = '/frozen/f06/delivery_manifest.json'
    binding = make_reference_binding(
        controller_profile='r3_continuous_v1',
        source_delivery_manifest=manifest,
    )
    with patch('task_env.tasks.pick_cube.specialization.build_isaac_reference',
               return_value={'construction': 'external'}) as build:
        result = binding.build_external('isaacsim')

    assert result == {'construction': 'external'}
    build.assert_called_once_with(
        delivery_manifest=manifest,
        include_solution=False,
        controller_profile='r3_continuous_v1',
    )


def test_position_reset_uses_artifact_frame_alias_for_single_segment_semantics():
    from types import SimpleNamespace

    from task_env.artifacts import FrameReference
    from task_env.tasks.reference_env import _position_frame_bindings_from_artifact

    artifact = SimpleNamespace(legacy_frame_bindings={
        'panda-v1/base': FrameReference('panda-v1', 'link0'),
        'panda-v1/ee': FrameReference('panda-v1', 'ee'),
        'cube-v1': FrameReference('cube-v1', 'cube'),
    })
    source = SimpleNamespace(
        bodies={'panda-v1/base': '/F06Scene/panda/link0', 'cube-v1': '/F06Scene/cube_v1'},
        frames={'panda-v1/ee': '/F06Scene/panda/hand/ee'},
    )

    assert _position_frame_bindings_from_artifact(artifact, source) == {
        'panda-v1/base': FrameReference('panda-v1', 'link0'),
        'panda-v1/ee': FrameReference('panda-v1', 'ee'),
        'cube-v1': FrameReference('cube-v1', 'cube'),
    }


def test_versioned_reset_rejects_distinct_or_changed_artifact():
    from dataclasses import dataclass
    from types import SimpleNamespace
    from task_env.environment.reference_env import _artifact_for_reset

    @dataclass(frozen=True)
    class Artifact:
        identity_hash: str

    current, rebuilt = Artifact('same'), Artifact('same')
    assert _artifact_for_reset(current, {'artifact': rebuilt}) is current
    assert _artifact_for_reset(current, {'artifact': rebuilt}, SimpleNamespace(artifact=rebuilt)) is rebuilt
    with pytest.raises(ValueError, match='not identical'):
        _artifact_for_reset(current, {'artifact': rebuilt}, SimpleNamespace(artifact=current))
    with pytest.raises(ValueError, match='changed'):
        _artifact_for_reset(current, {'artifact': Artifact('different')})


def test_f06_reset_materializes_the_exact_rebuilt_runtime_input_artifact():
    from dataclasses import dataclass
    from types import SimpleNamespace
    from unittest.mock import patch

    from task_env.artifacts import ExecutionSpecV1, RendererSelectionV1
    from task_env.runtime.sessions.control import ControlBindingPlanV1
    from task_env.runtime.sessions.api import F06_PICKCUBE_ISAAC_PROFILE
    from task_env.tasks.reference_env import SelectedReferenceEnv

    @dataclass(frozen=True)
    class Artifact:
        identity_hash: str

    initial_artifact = Artifact('a' * 64)
    rebuilt_artifact = Artifact('a' * 64)
    assert rebuilt_artifact == initial_artifact
    assert rebuilt_artifact is not initial_artifact

    reset_plan = SimpleNamespace(reset_sample=SimpleNamespace(task_seed=31))
    execution = ExecutionSpecV1(
        schema_version='execution-spec-v1',
        physics_provider='isaacsim',
        physics_backend='cuda',
        physics_profile=F06_PICKCUBE_ISAAC_PROFILE,
        provider_seed=31,
        determinism_mode='best_effort',
        render_default=RendererSelectionV1(
            'renderer-selection-v1', 'none', 'none', 'none',
        ),
        physics_device='cuda:0',
    )
    runtime_input = SimpleNamespace(artifact=rebuilt_artifact, reset_plan=reset_plan)
    source = SimpleNamespace(
        scene_definition=SimpleNamespace(articulations=()),
        free_joints={}, bodies={}, frames={},
    )
    plan = ControlBindingPlanV1(
        'control-binding-plan-v1', 'b' * 64, (), (),
    )
    rebuilt_value = {
        'artifact': rebuilt_artifact,
        'source': source,
        'reset_plan': reset_plan,
        'execution_spec_v1': execution,
        'f06_pickcube_isaac_input': runtime_input,
        'controller_binding_plan': plan,
        'solution': None,
    }

    env = object.__new__(SelectedReferenceEnv)
    env._closed = False
    env._stopped = False
    env.position_profile = True
    env.leaf_position_profile = False
    env.fixed_attachment_leaf_position_profile = False
    env.position_profiles = (object(),)
    env.position_plan = plan
    env.provider, env.backend, env.horizon = 'isaacsim', 'cuda', 1000
    env.artifact = initial_artifact
    env.value = {'artifact': initial_artifact, 'reset_plan': reset_plan}
    env.binding = SimpleNamespace(
        reset_seed=lambda seed: seed,
        build_seeded=lambda *_args: rebuilt_value,
        reset_runtime_input=lambda value: value.get('f06_pickcube_isaac_input'),
    )
    env._diagnostic_profile = None
    env._native_feedback_profile = None
    env._mixed_control_candidate = False
    env._position_episode_end = None
    env.session = None
    env.recorder = None
    env._declared_execution_spec_v1 = execution
    env._close_camera_consumer = lambda: None
    env._bind_selected_controller = lambda _value: None
    env._latch_fault = lambda _phase, _error: None

    class StopAtMaterialization(Exception):
        pass

    observed = {}

    def capture_materialization(artifact, *_args, **_kwargs):
        observed['artifact'] = artifact
        raise StopAtMaterialization

    with patch('task_env.environment.reference_env.materialize_control', capture_materialization):
        try:
            env.reset(seed=31)
        except StopAtMaterialization:
            pass
        else:
            raise AssertionError('the reset did not reach the materialization boundary')

    assert observed['artifact'] is rebuilt_artifact
    assert observed['artifact'] is runtime_input.artifact


def test_f06_gripper_readback_failure_reports_exact_boundary_values():
    from task_env.tasks.pick_cube.solution import PickCubePositionExecutionInfoV1

    with pytest.raises(ValueError) as error:
        PickCubePositionExecutionInfoV1(
            'pickcube-position-execution-info-v1', 52, 0.52,
            -0.001, 0.2, 0.0, False,
        )

    message = str(error.value)
    assert 'control_step=52' in message
    assert 'simulation_time=0.52' in message
    assert 'measured_opening_m=-0.001' in message
    assert 'measured_opening_velocity_m_s=0.2' in message
    assert 'target_opening_m=0.0' in message


def test_f06_gripper_readback_normalizes_only_submicrometer_lower_limit_residue():
    from types import SimpleNamespace

    from task_env.tasks.reference_env import SelectedReferenceEnv

    def env_for_opening(opening_m):
        env = object.__new__(SelectedReferenceEnv)
        env.position_profile = True
        from task_env.tasks.pick_cube.specialization import make_reference_binding
        env.binding = make_reference_binding()
        env.value = {'f06_pickcube_isaac_input': object()}
        env.state = SimpleNamespace(
            control_step=52,
            simulation_time=0.52,
            joint_position={
                'panda-v1/finger_joint1': opening_m / 2,
                'panda-v1/finger_joint2': opening_m / 2,
            },
            joint_velocity={
                'panda-v1/finger_joint1': 0.002,
                'panda-v1/finger_joint2': 0.002,
            },
        )
        target = SimpleNamespace(gripper=SimpleNamespace(opening_m=0.08))
        env.last_position_transition = (None, SimpleNamespace(target=target), None)
        return env

    env = env_for_opening(-5.300285010889638e-7)
    info = env.expert_execution_info()
    assert info.measured_opening_m == 0.0
    assert info.target_opening_m == 0.08
    assert not info.close_ready
    output = {}
    env._publish_task_position_execution_info(output)
    assert output['pickcube_position_execution_info_v1'] == info.to_mapping()
    env.value = {}
    output = {}
    env._publish_task_position_execution_info(output)
    assert output == {}

    with pytest.raises(ValueError, match='measured_opening_m=-1.000001e-06'):
        env_for_opening(-1.000001e-6).expert_execution_info()


def test_f06_native_mimic_receipt_uses_task_scoped_five_newton_contract():
    from task_env.runtime.sessions.native_io import NativeAdvanceReceiptV1

    application = {
        'schema_version': 'native-physx-mimic-substep-application-v1',
        'profile_id': 'isaacsim-6.2-pickcube-physx-mimic-5n-v1',
        'provenance_kind': 'native_runtime',
        'drive_receipt_identity_sha256': 'a' * 64,
        'target_identity_sha256': 'b' * 64,
        'native_step_index': 1,
        'reference_joint': 'finger_joint1',
        'follower_joint': 'finger_joint2',
        'reference_position_m': 0.02,
        'follower_position_m': 0.02,
        'reference_velocity_m_s': 0.0,
        'follower_velocity_m_s': 0.0,
        'relation_error_m': 0.0,
        'reference_target_m': 0.02,
        'reference_effort_N': 0.25,
        'maximum_effort_N': 5.0,
        'public_effort_api': 'Articulation.get_dof_efforts',
        'effort_measurement_semantics': 'actuation_force',
        'projected_joint_force_N': 6.40239954,
        'public_projected_joint_force_api': 'Articulation.get_dof_projected_joint_forces',
        'projected_force_measurement_semantics': 'projected_active_joint_force',
        'native_mimic_api': 'PhysxMimicJointAPI:transX',
        'native_drive_api': 'PhysicsDriveAPI:linear',
    }
    assert 'public_contact_witness' not in application
    NativeAdvanceReceiptV1(
        'native-advance-receipt-v1', 1, 1, 0.002,
        native_adaptation_application=application,
    ).validate(1, 0.002)

    # Projected physical force may exceed the actuator's 5 N cap; it must
    # remain visible without being misclassified as actuator output.
    projected_force_above_limit = dict(application, projected_joint_force_N=6.40239954)
    NativeAdvanceReceiptV1(
        'native-advance-receipt-v1', 1, 1, 0.002,
        native_adaptation_application=projected_force_above_limit,
    ).validate(1, 0.002)

    wrong_declared_limit = dict(application, maximum_effort_N=100.0)
    with pytest.raises(ValueError, match='maximum_effort_N=100'):
        NativeAdvanceReceiptV1(
            'native-advance-receipt-v1', 1, 1, 0.002,
            native_adaptation_application=wrong_declared_limit,
        ).validate(1, 0.002)

    over_limit_effort = dict(application, reference_effort_N=5.01)
    with pytest.raises(ValueError, match='reference_effort_N=5.01'):
        NativeAdvanceReceiptV1(
            'native-advance-receipt-v1', 1, 1, 0.002,
            native_adaptation_application=over_limit_effort,
        ).validate(1, 0.002)

    broken_relation = dict(application, relation_error_m=0.003)
    with pytest.raises(ValueError, match='relation_error_m=0.003'):
        NativeAdvanceReceiptV1(
            'native-advance-receipt-v1', 1, 1, 0.002,
            native_adaptation_application=broken_relation,
        ).validate(1, 0.002)

    wrong_profile = dict(application, profile_id='isaacsim-6.2-physx-native-mimic-leader-drive-v1')
    with pytest.raises(ValueError, match='receipt is incomplete or malformed'):
        NativeAdvanceReceiptV1(
            'native-advance-receipt-v1', 1, 1, 0.002,
            native_adaptation_application=wrong_profile,
        ).validate(1, 0.002)

    wrong_effort_api = dict(application, public_effort_api='Articulation.get_dof_projected_joint_forces')
    with pytest.raises(ValueError, match='receipt is incomplete or malformed'):
        NativeAdvanceReceiptV1(
            'native-advance-receipt-v1', 1, 1, 0.002,
            native_adaptation_application=wrong_effort_api,
        ).validate(1, 0.002)

    non_finite_projection = dict(application, projected_joint_force_N=float('nan'))
    with pytest.raises(ValueError, match='receipt is incomplete or malformed'):
        NativeAdvanceReceiptV1(
            'native-advance-receipt-v1', 1, 1, 0.002,
            native_adaptation_application=non_finite_projection,
        ).validate(1, 0.002)


def test_f06_runtime_admission_keeps_exact_delivery_and_task_bindings(monkeypatch):
    """Exercise F06-specific rejection independently of native/USD loading."""
    from types import SimpleNamespace as NS
    from task_env.runtime.sessions import api
    from task_env.runtime.sessions.source import UsdRuntimeInputV1

    monkeypatch.setattr(api, '_validate_exact_admission_binding', lambda *args: None)
    joints = {**{f'panda-v1/joint{i}': f'joint{i}' for i in range(1, 8)},
              'panda-v1/finger_joint1': 'finger_joint1', 'panda-v1/finger_joint2': 'finger_joint2'}
    delivery = NS(manifest_bytes_sha256=api._F06_DELIVERY_MANIFEST_SHA256_V1,
                  delivery=NS(representation_id=api._F06_REPRESENTATION_V1),
                  locally_validated=True, source_verified=False)
    representation = NS(provider='isaacsim', provider_build_identity='isaacsim-6.2.0.0',
                        representation_format='usd', runtime_admitted=False, source_verified=False)
    scene = NS(loaded_delivery=delivery, representation=representation,
               locally_validated=True, source_verified=False)
    source = NS(scene_source=scene, joints=joints, joint_targets=joints,
                bodies={'panda-v1/base': '/F06Scene/panda/Geometry/link0', 'cube-v1': '/F06Scene/cube_v1'},
                frames={'panda-v1/ee': '/F06Scene/panda/Geometry/link0/link1/link2/link3/link4/link5/link6/link7/hand/ee',
                        'tabletop-v1/top': '/F06Scene/tabletop_v1/top'},
                free_joints={'cube-v1': '/F06Scene/cube_v1'})
    execution = NS(physics_provider='isaacsim', physics_backend='cuda', physics_device='cuda:0',
                   physics_profile=api.F06_PICKCUBE_ISAAC_PROFILE, provider_seed=31,
                   determinism_mode='best_effort', render_default=NS(provider='none'), camera_overrides=())
    policy = {
        'schema_version': 'usd-task-admission-policy-v1',
        'bindings': {name: dict(getattr(source, name)) for name in
                     ('joints', 'joint_targets', 'bodies', 'frames', 'free_joints')},
        'controller_profile': 'r3_continuous_v1', 'horizon_min': 1, 'horizon_max': 1000,
    }
    value = object.__new__(UsdRuntimeInputV1)
    for name, item in dict(schema_version='pick-cube-isaac-runtime-input-v1', runtime_source=source,
                           execution=execution, reset_plan=NS(reset_sample=NS(task_seed=31)),
                           controller_profile='r3_continuous_v1', horizon=1000,
                           admission_policy=policy,
                           delivery_manifest_sha256=delivery.manifest_bytes_sha256).items():
        object.__setattr__(value, name, item)
    api._validate_f06_pickcube_isaac_input(value, object(), execution, source)
    object.__setattr__(value, 'horizon', 1001)
    with pytest.raises(ValueError, match='frozen controller'):
        api._validate_f06_pickcube_isaac_input(value, object(), execution, source)
    object.__setattr__(value, 'horizon', 1000)
    delivery.manifest_bytes_sha256 = '0' * 64
    with pytest.raises(ValueError, match='exact locally validated'):
        api._validate_f06_pickcube_isaac_input(value, object(), execution, source)
    delivery.manifest_bytes_sha256 = value.delivery_manifest_sha256
    source.bodies['cube-v1'] = '/wrong'
    with pytest.raises(ValueError, match='binding map'):
        api._validate_f06_pickcube_isaac_input(value, object(), execution, source)
    # A caller cannot bypass the binding check by changing the declaration too.
    policy['bindings']['bodies']['cube-v1'] = '/wrong'
    with pytest.raises(ValueError, match='trusted policy identity'):
        api._validate_f06_pickcube_isaac_input(value, object(), execution, source)
    policy['bindings']['bodies']['cube-v1'] = '/F06Scene/cube_v1'
    source.bodies['cube-v1'] = '/F06Scene/cube_v1'
    policy['horizon_max'] = 1001
    with pytest.raises(ValueError, match='trusted policy identity'):
        api._validate_f06_pickcube_isaac_input(value, object(), execution, source)
    policy['horizon_max'] = 1000
    for name in ('joints', 'joint_targets', 'frames', 'free_joints'):
        # Copy because the fixture's joint maps initially share a dictionary.
        original = getattr(source, name)
        altered = dict(original)
        altered[next(iter(altered))] = '/wrong'
        setattr(source, name, altered)
        with pytest.raises(ValueError, match='binding map'):
            api._validate_f06_pickcube_isaac_input(value, object(), execution, source)
        setattr(source, name, original)
