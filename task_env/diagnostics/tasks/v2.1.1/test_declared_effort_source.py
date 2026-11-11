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
    task_source, artifact = task._declaration(scene)
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
