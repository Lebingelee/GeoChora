"""Provider-free P1.1 PickCube candidate builder; no materialization."""
from ...artifacts import (
    ActionIntent, EntityDefinition, InitializationContract, PoseWorld,
    RequiredCapabilitySet, TaskArtifact, Timebase, UniformDimension, WorldDefinition,
)
from ...environment.configuration import load_yaml_mapping, overlay_public_env_config
from .assets import (
    CUBE_HALF_SIZE, CUBE_MASS, CUBE_DIAG_INERTIA, CUBE_CONTACT_MARGIN,
    TABLE_TOP_Z, TABLE_HALF_SIZE,
)
from .canonical_semantics import EEF, FINGERS, semantic_definition
from .task import PICK_CUBE_SPEC, PickCubeEnv, PickCubeResetSampler


def build_candidate() -> TaskArtifact:
    """Explicit default timeline and current reset envelope, still candidate."""
    spec = PICK_CUBE_SPEC
    config = overlay_public_env_config(
        PickCubeEnv.default_config(), load_yaml_mapping(PickCubeEnv.default_config_path())
    )
    rt = config.runtime
    center = tuple(float(v) for v in PickCubeResetSampler.table_center_xy)
    extent = PickCubeResetSampler.half_extent_m
    dimensions = tuple(
        UniformDimension(f'cube-v1.position_world.{axis}', bounds, bounds, bounds, bounds)
        for axis, value in zip(('x', 'y'), center, strict=True)
        for bounds in ((value - extent, value + extent),)
    )
    return TaskArtifact(
        schema_version='task-artifact-v0', artifact_id='pick-cube-v1/p1_1_candidate',
        task_id=spec.task_uid, artifact_version='ver_p1_1_candidate',
        world=WorldDefinition(
            schema_version='world-v0', convention='SI_right_handed_z_up_wxyz',
            entities=(
                EntityDefinition('tabletop-v1', 'static', 'tabletop-v1/task-local',
                                 ('tabletop-v1/top',), (), 'box', 'support_contact',
                                 {'top_z': TABLE_TOP_Z, **{f'half_size_{a}': v for a, v in zip('xyz', TABLE_HALF_SIZE, strict=True)}}),
                EntityDefinition('panda-v1', 'embodiment',
                                 'mujoco_menagerie/b846dd12bc459d776cccb3dee0b1d02acbf7a9c7/franka_emika_panda/panda.xml',
                                 ('panda-v1/base', EEF),
                                 (*tuple(f'panda-v1/joint{i}' for i in range(1, 8)), *FINGERS),
                                 'referenced_articulation', 'arm_hand_finger_collision', {}),
                EntityDefinition('cube-v1', 'movable', 'cube-v1/task-local', (), (),
                                 'free_box', 'table_hand_contact',
                                 {'half_size': CUBE_HALF_SIZE, 'mass': CUBE_MASS,
                                  **{f'inertia_{a}': v for a, v in zip('xyz', CUBE_DIAG_INERTIA, strict=True)}}),
            ),
            action=ActionIntent('absolute_pose', 'world', 'quaternion_wxyz',
                                'arm_joint_position_and_gripper'),
            observation_requirements=('task-env-state-v2', 'privileged_state'),
            randomization_dimensions=tuple(d.name for d in dimensions),
        ),
        initialization=InitializationContract(
            schema_version='initialization-v0',
            poses_world={'cube-v1': PoseWorld((center[0], center[1], TABLE_TOP_Z + CUBE_HALF_SIZE + CUBE_CONTACT_MARGIN), (1., 0., 0., 0.))},
            joint_position={}, randomization=dimensions,
            inherited_state_policy='preserve_referenced_initial_non_cube_qpos_and_all_qvel_qacc_ctrl_act',
            reset_validity='cube_free_pose_in_declared_xy_envelope_fixed_z_identity_wxyz',
            settle_steps=0,
        ),
        semantics=semantic_definition(),
        timebase=Timebase(rt.physics_dt, rt.control_substeps, rt.physics_dt * rt.control_substeps),
        required_capabilities=RequiredCapabilitySet((
            'rigid_body', 'free_body', 'articulated_robot', 'joint_position_actuation',
            'joint_state_query', 'body_pose_query', 'frame_pose_query',
        )),
    )
