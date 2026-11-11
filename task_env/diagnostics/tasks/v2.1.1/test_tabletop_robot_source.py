"""Check that tabletop Artifacts and sources share one declared Robot."""
from types import SimpleNamespace

import pytest

from task_env.assembly.compiler import compile_reference_source
from task_env.environment.types import TaskCompositionSpec
from task_env.robots.panda import PandaAgent


@pytest.mark.parametrize('task_name', ['pickcube', 'nut'])
def test_artifact_and_runtime_source_share_robot(task_name, monkeypatch):
    from task_env.tasks.pick_cube.specialization import build_reference as build_pickcube
    from task_env.tasks.nut_assembly.specialization import build_reference as build_nut

    original = PandaAgent.artifact_entity
    used = []
    def capture(robot, *args, **kwargs):
        used.append(robot)
        return original(robot, *args, **kwargs)
    monkeypatch.setattr(PandaAgent, 'artifact_entity', capture)
    value = (build_pickcube(backend='cpu', include_solution=False)
             if task_name == 'pickcube' else build_nut(provider='mujoco', include_solution=False))
    source = value['source']
    try:
        assert used and all(robot is source.agents[0] for robot in used)
        assert source.agents[0].uid == 'panda-v1'
    finally:
        source.execution_source_receipt.close()


def test_source_rejects_robot_outside_task_composition():
    artifact = SimpleNamespace(initialization=SimpleNamespace(joint_position={}), identity_hash='a' * 64)
    composition = TaskCompositionSpec('task-test', 'tabletop-v1', ('panda-v1',), ())
    with pytest.raises(ValueError, match='supplied Robots differ'):
        compile_reference_source(artifact=artifact, scene_source=None, composition=composition, config=None,
            bodies={}, frames={}, free_joints={}, joint_targets={}, open_actuators=(),
            agents=(SimpleNamespace(uid='foreign-robot'),))


@pytest.mark.parametrize('task_name', ['pickcube', 'nut'])
def test_r3_execution_controller_owns_hold_and_gripper(task_name):
    from task_env.controllers.canonical.execution import ReferenceExecutionController, StableArmTargetHold
    from task_env.tasks.pick_cube.specialization import build_reference as build_pickcube
    from task_env.tasks.nut_assembly.specialization import build_reference as build_nut

    value = (build_pickcube(backend='cpu', include_solution=False, controller_profile='r3_continuous_v1')
             if task_name == 'pickcube' else build_nut(provider='mujoco', include_solution=False))
    try:
        controller = value['controller']
        assert isinstance(controller, ReferenceExecutionController)
        assert isinstance(controller.hold, StableArmTargetHold)
        assert controller.inner.controller is controller.hold.controller
        assert controller.gripper_rate_hz == 500
        assert controller.gripper_config.force_limit_N == 10.0
        assert controller.control_dt == value['artifact'].timebase.control_dt
    finally:
        value['source'].execution_source_receipt.close()


@pytest.mark.parametrize('uid', ['pick-cube-p16-reference-v1', 'nut-assembly-outcome-reference-v1'])
def test_each_public_environment_owns_its_binding_and_source(uid):
    import sys
    from task_env import make_env

    config = {'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu',
                            'physics_device': 'cpu', 'deployment': 'in_process',
                            'interpreter': sys.executable}, 'episode': {'horizon': 8}}
    first = make_env(uid, config=config)
    second = None
    try:
        second = make_env(uid, config=config)
        assert first.binding is not second.binding
        assert first.controller is not second.controller
        first_receipt = first.value['source'].execution_source_receipt
        second_receipt = second.value['source'].execution_source_receipt
        assert first_receipt is not second_receipt
        first.close()
        assert not first_receipt.snapshot_root.exists()
        assert second_receipt.snapshot_root.exists()
    finally:
        first.close()
        if second is not None:
            second.close()
