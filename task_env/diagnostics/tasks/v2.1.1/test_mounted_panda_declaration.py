"""Source-only checks for a pre-existing mounted Panda arm declaration."""
from xml.etree import ElementTree as ET
import pytest

from task_env.robots.mounted_panda import MountedPandaArm


def mounted_source():
    root = ET.Element('mujoco')
    world = ET.SubElement(root, 'worldbody')
    base = ET.SubElement(world, 'body', name='robot0_base')
    link = ET.SubElement(base, 'body', name='robot0_link0')
    actuators = ET.SubElement(root, 'actuator')
    for index in range(1, 8):
        link = ET.SubElement(link, 'body', name=f'robot0_link{index}', pos='0 0 .1')
        ET.SubElement(link, 'joint', name=f'robot0_joint{index}', axis='0 0 1')
        ET.SubElement(actuators, 'motor', name=f'robot0_torq_j{index}',
                      joint=f'robot0_joint{index}', ctrllimited='true', ctrlrange='-12 12')
    ET.SubElement(actuators, 'position', name='independent_finger', joint='finger')
    return ET.tostring(root, encoding='unicode')


def test_mounted_arm_references_one_source_and_binds_only_torque_channels():
    robot = MountedPandaArm('source', 'a' * 64)
    assert robot.default_controller is robot.default_controller
    assert not robot.default_controller.is_bound
    subject, channels = robot.physical_subject_declaration(source_xml=mounted_source())
    assert subject.source_ownership == 'references_existing'
    assert len(channels) == 7 and all(c.native_drive == 'disabled' for c in channels)
    assert [c.native_actuator for c in channels] == [f'robot0_torq_j{i}' for i in range(1, 8)]
    scene = robot.scene_definition(source_xml=mounted_source(), scene_id='mounted-scene')
    assert scene.robots[0].articulation_roots[0].frame_id == 'robot0_base'
    assert robot.source_recipe().controlled_joints == robot.state_joint_names


def test_mounted_arm_rejects_foreign_motor_mapping():
    xml = mounted_source().replace('joint="robot0_joint4"', 'joint="robot0_joint3"')
    with pytest.raises(ValueError, match='joint or motor mapping'):
        MountedPandaArm('source', 'a' * 64).physical_subject_declaration(source_xml=xml)


def test_mounted_arm_binds_default_through_shared_effort_owner():
    from types import SimpleNamespace
    from task_env.artifacts import FrameReference
    from task_env.runtime.sessions.physical_control import build_declared_effort_execution

    robot = MountedPandaArm('source', 'a' * 64)
    scene = robot.scene_definition(source_xml=mounted_source(), scene_id='mounted-scene')
    subject, declarations = robot.physical_subject_declaration(source_xml=mounted_source())
    definitions = {joint.joint_id: joint for joint in scene.articulations[0].joints}
    source = SimpleNamespace(source_id='source', source_closure_digest='a' * 64,
        joints={f'panda-v1/{name}': name for name in robot.state_joint_names},
        free_joints={}, bodies={'panda-v1/robot0_base': 'robot0_base'}, frames={})
    def bind(binding, writer):
        return robot.default_controller.bind(subject, binding, writer_id=writer, units=('N*m',) * 7)
    execution = build_declared_effort_execution(scene=scene,
        artifact=SimpleNamespace(identity_hash='b' * 64), source=source, subject=subject,
        declarations=declarations, assembly_id=robot.assembly_id, controller_factory=bind,
        state_joint_names=robot.state_joint_names,
        joint_bindings={f'panda-v1/{name}': definitions[name] for name in robot.state_joint_names},
        frame_bindings={'panda-v1/robot0_base': FrameReference('panda-v1', 'robot0_base')})
    assert robot.default_controller.is_bound
    assert robot.default_controller.profile_id == 'direct_joint_effort_v1'
    from task_env.runtime.sessions.control import bind_selected_controller
    artifact = SimpleNamespace(identity_hash='b' * 64, timebase=SimpleNamespace(control_dt=.05))
    selected = bind_selected_controller({'controller': robot.default_controller, 'artifact': artifact,
        'source': source, 'physical_execution': execution,
        'selected_controller_profile_id': 'direct_joint_effort_v1'},
        binding=SimpleNamespace(), provider='mujoco', backend='cpu')
    assert selected.selection_matches[0].selection_profile_id == 'direct_joint_effort_v1'
    assert execution.controllers == (robot.default_controller,)
    assert execution.action_schema()['controllers'][0]['components'] == {
        'torque': {'shape': [7], 'dtype': 'float32'}}
    from task_env.artifacts.state import StateBoundaryIdentity, StateSampleClock
    from task_env.controllers.canonical.physical_commands import PhysicalCommandContextV1
    boundary = StateBoundaryIdentity('state-boundary-identity-v1', 'episode', 'reset-' + 'd' * 64,
        scene.identity_hash, 'instance', 'material', 0, 0)
    clock = StateSampleClock('state-sample-clock-v1', 'evaluation_boundary', 0, 0.)
    context = PhysicalCommandContextV1('physical-command-context-v1', 'source', 'a' * 64,
        'b' * 64, boundary, clock, 0, 1, .05, .05)
    state = SimpleNamespace(boundary=boundary, sample_clock=clock)
    robot.default_controller.reset_from_realized_state(state)
    command = robot.default_controller.compute({'torque': [1., 0., 0., 0., 0., 0., 0.]}, state, context)
    assert command.joint_efforts[0].value == 1.
    assert len(command.joint_efforts) == 7
    assert tuple(channel.unit for channel in execution.compiled.binding.channels) == ('N*m',) * 7
    assert tuple(channel.native_actuator for channel in execution.compiled.binding.channels) == tuple(
        f'robot0_torq_j{i}' for i in range(1, 8))
    with pytest.raises(ValueError, match='source'):
        execution.validate_source(scene=scene, artifact_sha256='b' * 64,
            source_id='foreign', source_closure_sha256='a' * 64, source=source)


def test_task_source_accepts_safe_namespaced_ids_and_rejects_unsafe_segments():
    from task_env.environment.task_source import TaskSourceV1
    source = TaskSourceV1('libero_spatial/pick-and-place', 'v1', 'scene', (), None)
    assert TaskSourceV1.from_mapping(source.to_mapping()).task_id == source.task_id
    for bad in ('/root', 'a//b', 'a/../b', 'a/./b', 'a/space name'):
        with pytest.raises(ValueError, match='task id'):
            TaskSourceV1(bad, 'v1', 'scene', (), None)
