"""Check declared effort source mappings without starting a physics SDK."""
from types import SimpleNamespace

import pytest

from task_env.robots.pendulum import PendulumEntity
from task_env.robots.two_wheel_balance import TwoWheelBalanceEntity
from task_env.runtime.sessions import isaac_g05
from task_env.runtime.sessions.declared_effort_source import compile_declared_effort_source
from task_env.tasks import pendulum_physical, two_wheel_physical
from task_env.tasks.pendulum import PendulumEnv
from task_env.tasks.two_wheel_balance import TwoWheelBalanceEnv


@pytest.mark.parametrize(('robot', 'env_type'), [
    (PendulumEntity(), PendulumEnv),
    (TwoWheelBalanceEntity(), TwoWheelBalanceEnv),
])
def test_task_controller_choices_match_robot_subject(robot, env_type):
    subject, _ = robot.physical_subject_declaration(source_id='source', source_closure_sha256='a' * 64)
    assert env_type.selected_controller_profiles == frozenset(subject.supported_controller_profiles)
    assert env_type.selected_default_controller_profile() in subject.supported_controller_profiles


@pytest.mark.parametrize(('uid', 'robot_type'), [
    ('pendulum-v1', PendulumEntity),
    ('two-wheel-balance-v1', TwoWheelBalanceEntity),
])
def test_source_uses_selected_robot_asset_root(uid, robot_type, tmp_path, monkeypatch):
    from task_env import make_env

    monkeypatch.setattr(robot_type, 'source_base_dir', tmp_path)
    env = make_env(uid)
    try:
        assert env.binding.robot.source_base_dir == tmp_path
        assert env.value['source'].scene_source.base_dir == tmp_path
    finally:
        env.close()


@pytest.mark.parametrize(('uid', 'robot_type'), [
    ('pendulum-v1', PendulumEntity), ('two-wheel-balance-v1', TwoWheelBalanceEntity),
])
def test_scene_identity_uses_the_selected_robot_source(uid, robot_type, monkeypatch):
    import hashlib
    from task_env import make_env

    source_xml = robot_type.source_xml + '\n<!-- selected Robot source -->'
    monkeypatch.setattr(robot_type, 'source_xml', source_xml)
    env = make_env(uid)
    try:
        source = env.value['source']
        assert env.binding.robot.source_xml == source_xml
        assert source.scene_definition.assets[0].source_content_sha256 == hashlib.sha256(
            source_xml.encode()).hexdigest()
        assert source.scene_source.xml == source_xml
        assert env.artifact.timebase.physics_dt == env.config.runtime.physics_dt
        assert env.artifact.timebase.control_substeps == env.config.runtime.control_substeps
    finally:
        env.close()


@pytest.mark.parametrize('uid', ['pendulum-v1', 'two-wheel-balance-v1'])
def test_effort_build_uses_provider_from_request_and_selected_robot(uid, monkeypatch):
    from task_env import make_env
    from task_env.runtime.sessions import declared_effort_source

    seen = []
    original = declared_effort_source.declared_effort_scene
    intercept = False

    class CapturedRequest(Exception):
        pass

    def capture(robot, *, provider, source_delivery_manifest):
        if not intercept:
            return original(robot, provider=provider, source_delivery_manifest=source_delivery_manifest)
        seen.append((robot, provider))
        raise CapturedRequest

    monkeypatch.setattr(declared_effort_source, 'declared_effort_scene', capture)
    env = make_env(uid)
    intercept = True
    try:
        with pytest.raises(CapturedRequest):
            env.binding.build_for_request('geophys', env.backend, 31, env.horizon)
        assert seen == [(env.binding.robot, 'geophys')]
        with pytest.raises(ValueError, match='backend differs'):
            env.binding.build_for_request('geophys', 'wrong-backend', 31, env.horizon)
        assert len(seen) == 1
    finally:
        env.close()


@pytest.mark.parametrize(('robot', 'task', 'expected_bodies'), [
    (PendulumEntity(), pendulum_physical, {
        'pendulum-v1/pendulum_anchor': 'Geometry/pendulum_anchor',
        'pendulum-v1/pendulum_link': 'Geometry/pendulum_anchor/pendulum_link'}),
    (TwoWheelBalanceEntity(), two_wheel_physical, {
        'two-wheel-balance-v1/balance_anchor': 'Geometry/balance_anchor',
        'two-wheel-balance-v1/balance_chassis': 'Geometry/balance_anchor/balance_chassis',
        'two-wheel-balance-v1/left_wheel': 'Geometry/balance_anchor/balance_chassis/left_wheel',
        'two-wheel-balance-v1/right_wheel': 'Geometry/balance_anchor/balance_chassis/right_wheel'}),
])
def test_source_maps_subject_and_rejects_wrong_motor(robot, task, expected_bodies, monkeypatch):
    scene = robot.scene_definition()
    task_source, artifact = task._declaration(scene, robot)
    seen = {}
    def build_source(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(source_id='usd-source', source_closure_digest='a' * 64)
    monkeypatch.setattr(isaac_g05, 'build_g05_isaac_runtime_source', build_source)
    args = dict(scene=scene, artifact=artifact, task_source=task_source,
                composition=None, config=None, provider='isaacsim',
                source_delivery_manifest='fixture', seed=31)
    source, spec, closure, subject, declarations = compile_declared_effort_source(robot=robot, **args)
    assert subject.source_id == source.source_id
    assert subject.source_closure_sha256 == source.source_closure_digest
    assert len(declarations) == len(subject.channel_paths)
    assert seen['bodies'] == expected_bodies
    assert seen['joints'] == {f'{robot.uid}/{name}': name for name in robot.state_joint_names}
    assert seen['joint_targets'] == seen['joints']
    assert closure == source.source_closure_digest
    assert spec.physics_provider == 'isaacsim'
    corrupted = SimpleNamespace(source_xml=robot.source_xml.replace('gear="1"', 'gear="2"', 1),
                                source_base_dir=robot.source_base_dir,
                                physical_subject_declaration=robot.physical_subject_declaration,
                                state_joint_names=robot.state_joint_names)
    with pytest.raises(ValueError, match='transmission differs'):
        compile_declared_effort_source(robot=corrupted, **args)


def test_task_compiler_rejects_robot_joint_declaration_mismatching_scene():
    from dataclasses import replace
    robot = PendulumEntity()
    scene = robot.scene_definition()
    with pytest.raises(ValueError, match='state joints differ'):
        pendulum_physical._declaration(scene, replace(robot, joint_name='foreign_hinge'))


@pytest.mark.parametrize(('task_name', 'robot_uid'), [
    ('pickcube', 'panda-v1'), ('nut', 'panda-v1'),
    ('pendulum', 'pendulum-v1'), ('wheel', 'two-wheel-balance-v1'),
])
def test_task_artifact_uses_registered_robot_entity(task_name, robot_uid):
    from task_env.registry import make_agent
    from task_env.assembly.panda_box import compile_panda_box_artifact
    from task_env.tasks.pick_cube.specialization import _declaration as pickcube_declaration
    from task_env.tasks.nut_assembly.specialization import build_artifact as nut_artifact

    robot = make_agent(robot_uid)
    if task_name == 'pickcube':
        artifact = compile_panda_box_artifact(pickcube_declaration())
        expected = robot.artifact_entity()
    elif task_name == 'nut':
        artifact = nut_artifact()
        expected = robot.artifact_entity()
    else:
        scene = robot.scene_definition()
        task = pendulum_physical if task_name == 'pendulum' else two_wheel_physical
        _, artifact = task._declaration(scene, robot)
        expected = robot.artifact_entity(scene)
        assert artifact.scene_identity_hash == scene.identity_hash
        assert set(artifact.initialization.joint_position) == set(expected.joints)
        assert set(artifact.legacy_joint_bindings) == set(expected.joints)
        return
    matching = tuple(item for item in artifact.world.entities if item.semantic_id == robot_uid)
    assert matching == (expected,)


def test_two_wheel_state_requirements_include_passive_pitch():
    import sys
    from task_env import make_env

    config = {'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu',
                            'physics_device': 'cpu', 'deployment': 'in_process',
                            'interpreter': sys.executable}, 'episode': {'horizon': 8}}
    env = make_env('two-wheel-balance-v1', config=config)
    try:
        execution = env.value['physical_execution']
        state_joints = {item.subject_id for item in execution.requirements.requirements}
        driven_joints = {item.joint_id for item in execution.compiled.binding.channels}
        assert 'chassis_pitch' in state_joints and 'chassis_pitch' not in driven_joints
        assert driven_joints < state_joints
    finally:
        env.close()


@pytest.mark.parametrize('profile', ['direct_joint_effort_v1', 'velocity_damped_joint_effort_v1'])
def test_effort_controller_rejects_foreign_subject_source(profile):
    from dataclasses import replace
    from task_env.controllers.canonical.default_identity import DefaultCanonicalController
    from task_env.controllers.canonical.physical_controller import select_subject_effort_controller
    from task_env.runtime.sessions.physical_control import compile_existing_subject_assembly

    robot = PendulumEntity()
    scene = robot.scene_definition()
    _, artifact = pendulum_physical._declaration(scene, robot)
    subject, declarations = robot.physical_subject_declaration(source_id='test-source',
        source_closure_sha256='a' * 64)
    compiled = compile_existing_subject_assembly(scene=scene, artifact_sha256=artifact.identity_hash,
        source_id=subject.source_id, source_closure_sha256=subject.source_closure_sha256,
        subject=subject, declarations=declarations, assembly_id=robot.assembly_id)
    direct = select_subject_effort_controller(subject, compiled.binding,
        profile_id='direct_joint_effort_v1', writer_id=subject.controller_writers[0],
        units=('N*m',), cadence_s=.05)
    default = DefaultCanonicalController().bind(subject, compiled.binding,
        writer_id=subject.controller_writers[0], units=('N*m',))
    assert default.is_bound and default.identity == direct.identity
    foreign = replace(subject, source_closure_sha256='b' * 64)
    with pytest.raises(ValueError, match='differs from subject source'):
        select_subject_effort_controller(foreign, compiled.binding, profile_id=profile,
            writer_id=subject.controller_writers[0], units=('N*m',), cadence_s=.05)


@pytest.mark.parametrize(('uid', 'robot_type'), [
    ('pendulum-v1', PendulumEntity), ('two-wheel-balance-v1', TwoWheelBalanceEntity),
])
def test_source_checked_declaration_is_used_by_the_controller(uid, robot_type, monkeypatch):
    import sys
    from task_env import make_env

    original = robot_type.physical_subject_declaration
    declared = []
    def capture(robot, **kwargs):
        value = original(robot, **kwargs)
        declared.append(value)
        return value
    monkeypatch.setattr(robot_type, 'physical_subject_declaration', capture)
    config = {'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process',
                            'interpreter': sys.executable}, 'episode': {'horizon': 8}}
    env = make_env(uid, config=config)
    try:
        assert len(declared) == 1
        execution = env.value['physical_execution']
        assert execution.subjects[0] == declared[0][0]
        assert tuple(channel.native_actuator for channel in execution.compiled.binding.channels) == tuple(
            item.native_actuator for item in declared[0][1])
    finally:
        env.close()
