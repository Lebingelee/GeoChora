"""Provider-free explicit NutAssembly Artifact family with frozen authored reset."""
from dataclasses import replace
import json
from pathlib import Path
from ...artifacts import (TaskArtifact, Timebase, WorldDefinition, EntityDefinition,
    ActionIntent, InitializationContract, PoseWorld, RequiredCapabilitySet)
from ...controllers.canonical.kinematics import ARM, FINGERS
from .canonical_semantics import semantic_definition, EEF
from .assets import NUT_MASS, NUT_DIAG_INERTIA, PEG_HALF_HEIGHT, TABLE_TOP_Z

PROFILES = {'NA-TB500': (1, .002), 'NA-TB100': (5, .010), 'NA-TB50': (10, .020)}


def initialization_data():
    return json.loads(Path(__file__).with_name('canonical_initialization.json').read_text())


def build_candidate(profile='NA-TB500'):
    if profile not in PROFILES:
        raise ValueError('unsupported explicit NutAssembly profile')
    data = initialization_data(); substeps, dt = PROFILES[profile]
    return TaskArtifact('task-artifact-v0', 'nut-assembly-square-v1/p1_8_e', 'nut-assembly-square-v1',
        'ver_p1_8_e_' + profile.lower().replace('-', ''),
        WorldDefinition('world-v0', 'SI_right_handed_z_up_wxyz', (
            EntityDefinition('tabletop-v1', 'static', 'nut-assembly-square-v1/task-local/table', (), (), 'box', 'support_contact', {'top_z': TABLE_TOP_Z}),
            EntityDefinition('panda-v1', 'embodiment', 'mujoco_menagerie/b846dd12bc459d776cccb3dee0b1d02acbf7a9c7/franka_emika_panda/panda.xml',
                             ('panda-v1/base', EEF), (*ARM, *FINGERS), 'referenced_articulation', 'arm_hand_finger_collision', {}),
            EntityDefinition('square-nut-v1', 'movable', 'nut-assembly-square-v1/task-local/square-nut', (), (),
                             'authored_compound', 'table_hand_peg_contact', {'mass': NUT_MASS, **{f'inertia_{a}':v for a,v in zip('xyz', NUT_DIAG_INERTIA)}}),
            EntityDefinition('square-peg-v1', 'static', 'nut-assembly-square-v1/task-local/square-peg', (), (), 'box', 'nut_contact', {'half_height': PEG_HALF_HEIGHT}),
            EntityDefinition('round-peg-v1', 'static', 'nut-assembly-square-v1/task-local/round-peg', (), (), 'cylinder', 'nut_contact', {'half_height': PEG_HALF_HEIGHT})),
            ActionIntent('absolute_pose', 'world', 'quaternion_wxyz', 'arm_joint_position_and_gripper'),
            ('task-env-state-v2', 'privileged_state'), ()),
        InitializationContract('initialization-v0', {'square-nut-v1': PoseWorld.from_mapping(data['nut_pose'])},
            data['joint_position'], (), 'zero_named_joint_and_entity_velocities_arm_targets_at_initial_joints_gripper_open',
            'NA-S0_frozen_deterministic_semantic_joint_and_pose_request', 0),
        semantic_definition(), Timebase(.002, substeps, dt), RequiredCapabilitySet((
            'rigid_body', 'free_body', 'articulated_robot', 'joint_position_actuation', 'joint_state_query', 'body_pose_query', 'frame_pose_query')))


def require_family(artifact):
    if not isinstance(artifact, TaskArtifact):
        raise TypeError('TaskArtifact required')
    for profile in PROFILES:
        expected = build_candidate(profile)
        if artifact.to_mapping() == expected.to_mapping() and artifact.identity_hash == expected.identity_hash:
            return profile
    raise ValueError('not an exact declared NutAssembly Artifact family member')
