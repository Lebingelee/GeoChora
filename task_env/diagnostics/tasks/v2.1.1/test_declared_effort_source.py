"""Check declared effort source mappings without starting a physics SDK."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from task_env.robots.pendulum import PendulumEntity
from task_env.robots.two_wheel_balance import TwoWheelBalanceEntity
from task_env.runtime.sessions import isaac_g05
from task_env.runtime.sessions.declared_effort_source import compile_declared_effort_source
from task_env.tasks import pendulum_physical, two_wheel_physical


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
        return SimpleNamespace(source_closure_digest='a' * 64)
    monkeypatch.setattr(isaac_g05, 'build_g05_isaac_runtime_source', build_source)
    args = dict(scene=scene, artifact=artifact, task_source=task_source,
                composition=None, config=None, provider='isaacsim',
                source_delivery_manifest='fixture', seed=31, base_dir=Path(task.__file__).parent)
    source, spec, closure = compile_declared_effort_source(robot=robot, **args)
    assert seen['bodies'] == expected_bodies
    assert seen['joints'] == {f'{robot.uid}/{name}': name for name in robot.state_joint_names}
    assert seen['joint_targets'] == seen['joints']
    assert closure == source.source_closure_digest
    assert spec.physics_provider == 'isaacsim'
    corrupted = SimpleNamespace(source_xml=robot.source_xml.replace('gear="1"', 'gear="2"', 1),
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
