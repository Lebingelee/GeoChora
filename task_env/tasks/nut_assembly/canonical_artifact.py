"""Provider-free explicit NutAssembly Artifact family with frozen authored reset."""
from dataclasses import replace
import json
from pathlib import Path
from ...artifacts import (TaskArtifact, Timebase, WorldDefinition, EntityDefinition,
    ActionIntent, InitializationContract, PoseWorld, RequiredCapabilitySet)
from ...controllers.canonical.kinematics import ARM, FINGERS
from .canonical_semantics import semantic_definition, EEF
from .assets import (NUT_MASS, NUT_DIAG_INERTIA, NUTASSEMBLY_NOMINAL_V1_ID,
    NUTASSEMBLY_NOMINAL_V1_MASS, NUTASSEMBLY_NOMINAL_V1_DIAG_INERTIA,
    PEG_HALF_HEIGHT, TABLE_TOP_Z)

PROFILES = {'NA-TB500': (1, .002), 'NA-TB100': (5, .010), 'NA-TB50': (10, .020)}
ASSET_PROFILES = {
    'legacy-1kg-v0': (NUT_MASS, NUT_DIAG_INERTIA),
    NUTASSEMBLY_NOMINAL_V1_ID: (NUTASSEMBLY_NOMINAL_V1_MASS, NUTASSEMBLY_NOMINAL_V1_DIAG_INERTIA),
}


def initialization_data():
    return json.loads(Path(__file__).with_name('canonical_initialization.json').read_text())


def build_candidate(profile='NA-TB500', *, asset_profile='legacy-1kg-v0'):
    if profile not in PROFILES:
        raise ValueError('unsupported explicit NutAssembly profile')
    if asset_profile not in ASSET_PROFILES:
        raise ValueError('unsupported NutAssembly asset profile')
    nut_mass, nut_inertia = ASSET_PROFILES[asset_profile]
    nominal = asset_profile == NUTASSEMBLY_NOMINAL_V1_ID
    data = initialization_data(); substeps, dt = PROFILES[profile]
    task_id = 'nut-assembly-square-v1/p1_8_e/nominal-v1' if nominal else 'nut-assembly-square-v1/p1_8_e'
    version = 'ver_p1_8_e_nutassembly_nominal_v1' if nominal else 'ver_p1_8_e_' + profile.lower().replace('-', '')
    nut_asset = 'nut-assembly-square-v1/task-local/square-nut/' + NUTASSEMBLY_NOMINAL_V1_ID if nominal else 'nut-assembly-square-v1/task-local/square-nut'
    return TaskArtifact('task-artifact-v0', task_id, 'nut-assembly-square-v1',
        version,
        WorldDefinition('world-v0', 'SI_right_handed_z_up_wxyz', (
            EntityDefinition('tabletop-v1', 'static', 'nut-assembly-square-v1/task-local/table', (), (), 'box', 'support_contact', {'top_z': TABLE_TOP_Z}),
            EntityDefinition('panda-v1', 'embodiment', 'mujoco_menagerie/b846dd12bc459d776cccb3dee0b1d02acbf7a9c7/franka_emika_panda/panda.xml',
                             ('panda-v1/base', EEF), (*ARM, *FINGERS), 'referenced_articulation', 'arm_hand_finger_collision', {}),
            EntityDefinition('square-nut-v1', 'movable', nut_asset, (), (),
                             'authored_compound', 'table_hand_peg_contact', {'mass': nut_mass, **{f'inertia_{a}':v for a,v in zip('xyz', nut_inertia)}}),
            EntityDefinition('square-peg-v1', 'static', 'nut-assembly-square-v1/task-local/square-peg', (), (), 'box', 'nut_contact', {'half_height': PEG_HALF_HEIGHT}),
            EntityDefinition('round-peg-v1', 'static', 'nut-assembly-square-v1/task-local/round-peg', (), (), 'cylinder', 'nut_contact', {'half_height': PEG_HALF_HEIGHT})),
            ActionIntent('absolute_pose', 'world', 'quaternion_wxyz', 'arm_joint_position_and_gripper'),
            ('task-env-state-v2', 'privileged_state'), ()),
        InitializationContract('initialization-v0', {'square-nut-v1': PoseWorld.from_mapping(data['nut_pose'])},
            data['joint_position'], (), 'zero_named_joint_and_entity_velocities_arm_targets_at_initial_joints_gripper_open',
            'NA-S0_frozen_deterministic_semantic_joint_and_pose_request', 0),
        semantic_definition(), Timebase(.002, substeps, dt), RequiredCapabilitySet((
            'rigid_body', 'free_body', 'articulated_robot', 'joint_position_actuation', 'joint_state_query', 'body_pose_query', 'frame_pose_query')))


def build_nominal_candidate(profile='NA-TB500'):
    """Build one rate-specific Artifact in the frozen 0.1 kg nominal family."""
    return build_candidate(profile, asset_profile=NUTASSEMBLY_NOMINAL_V1_ID)


def require_family(artifact):
    if not isinstance(artifact, TaskArtifact):
        raise TypeError('TaskArtifact required')
    for profile in PROFILES:
        for asset_profile in ASSET_PROFILES:
            expected = build_candidate(profile, asset_profile=asset_profile)
            if artifact.to_mapping() == expected.to_mapping() and artifact.identity_hash == expected.identity_hash:
                return profile
    raise ValueError('not an exact declared NutAssembly Artifact family member')
