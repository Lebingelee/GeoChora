"""Provider-free declarations for a Panda and one free box on a table."""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from ..artifacts import (ActionIntent, EntityDefinition, InitializationContract, PoseWorld,
                         SemanticDefinition, Timebase, UniformDimension)
from ..environment.task_source import compile_declared_artifact
from ..environment.types import TaskCompositionSpec
from ..objects.pick_cube import (CUBE_CONTACT_MARGIN, CUBE_DIAG_INERTIA, CUBE_HALF_SIZE,
                                 CUBE_MASS, EE_SITE_NAME, PickCubeSceneComposer)
from ..robots.panda import PandaAgent
from .compiler import compile_reference_source, panda_entity_declaration


PANDA_BOX_CAPABILITIES = ('rigid_body', 'free_body', 'articulated_robot',
                          'joint_position_actuation', 'joint_state_query',
                          'body_pose_query', 'frame_pose_query')


@dataclass(frozen=True)
class PandaBoxDeclaration:
    """Task identity, physical placement, and semantics for the shared box asset."""

    task_id: str
    artifact_id: str
    version: str
    object_id: str
    success_definition: str
    table_half_size: tuple[float, float, float]
    table_top_z: float
    table_center_xy: tuple[float, float]
    source_box_position: tuple[float, float, float]
    source_box_quaternion_wxyz: tuple[float, float, float, float]
    reset_center_xy: tuple[float, float]
    reset_half_extent_m: float
    semantics: SemanticDefinition
    timebase: Timebase
    object_asset_reference: str = 'cube-v1/task-local'
    cast_reset_center_float32: bool = True
    include_table_center: bool = False
    capabilities: tuple[str, ...] = PANDA_BOX_CAPABILITIES

    def __post_init__(self):
        if not all(isinstance(v, str) and v for v in
                   (self.task_id, self.artifact_id, self.version, self.object_id, self.success_definition)):
            raise ValueError('task and Entity identities must be nonempty strings')
        if not math.isfinite(self.reset_half_extent_m) or self.reset_half_extent_m < 0:
            raise ValueError('reset half extent must be finite and nonnegative')
        if self.semantics.success_definition != self.success_definition:
            raise ValueError('semantic success definition differs from task declaration')
        if self.object_id not in self.semantics.required_poses:
            raise ValueError('task semantics must reference the declared box Entity')


def compile_panda_box_artifact(declaration: PandaBoxDeclaration):
    """Compile declarations into the current Artifact with no native runtime."""
    d = declaration
    center = (tuple(float(value) for value in np.asarray(d.reset_center_xy, dtype=np.float32))
              if d.cast_reset_center_float32 else tuple(float(value) for value in d.reset_center_xy))
    extent = float(d.reset_half_extent_m)
    dimensions = tuple(
        UniformDimension(f'{d.object_id}.position_world.{axis}',
                         (value - extent, value + extent), (value - extent, value + extent),
                         (value - extent, value + extent), (value - extent, value + extent))
        for axis, value in zip(('x', 'y'), center, strict=True)
    ) if extent else ()
    joints = {f'panda-v1/{name}': value for name, value in PandaAgent().initial_state_spec().joint_positions}
    entities = (
        EntityDefinition('tabletop-v1', 'static', 'tabletop-v1/task-local',
                         ('tabletop-v1/top',), (), 'box', 'support_contact',
                         {'top_z': float(d.table_top_z), **{
                             f'half_size_{axis}': float(value)
                             for axis, value in zip('xyz', d.table_half_size, strict=True)},
                          **({'center_x': d.table_center_xy[0], 'center_y': d.table_center_xy[1]}
                             if d.include_table_center else {})}),
        panda_entity_declaration(),
        EntityDefinition(d.object_id, 'movable', d.object_asset_reference, (), (),
                         'free_box', 'table_hand_contact',
                         {'half_size': CUBE_HALF_SIZE, 'mass': CUBE_MASS, **{
                             f'inertia_{axis}': value
                             for axis, value in zip('xyz', CUBE_DIAG_INERTIA, strict=True)}}),
    )
    initialization = InitializationContract(
        schema_version='initialization-v0',
        poses_world={d.object_id: PoseWorld((center[0], center[1],
                     float(d.table_top_z) + CUBE_HALF_SIZE + CUBE_CONTACT_MARGIN), (1., 0., 0., 0.))},
        joint_position=joints, randomization=dimensions,
        inherited_state_policy='zero_named_joint_and_entity_velocities_arm_targets_at_initial_joints_gripper_open',
        reset_validity='cube_free_pose_in_declared_xy_envelope_fixed_z_identity_wxyz', settle_steps=0,
    )
    return compile_declared_artifact(
        artifact_id=d.artifact_id, task_id=d.task_id, version=d.version, entities=entities,
        action=ActionIntent('absolute_pose', 'world', 'quaternion_wxyz', 'arm_joint_position_and_gripper'),
        observations=('task-env-state-v2', 'privileged_state'), initialization=initialization,
        semantics=d.semantics, timebase=d.timebase,
        capabilities=d.capabilities,
    )


def compile_panda_box_source(declaration: PandaBoxDeclaration, artifact, config):
    """Resolve the same box asset into source names and registered components."""
    d = declaration
    composer = PickCubeSceneComposer(
        table_half_size=d.table_half_size, table_top_z=d.table_top_z,
        table_center_xy=d.table_center_xy, cube_world_pos=d.source_box_position,
        cube_world_quat=d.source_box_quaternion_wxyz,
    )
    composition = TaskCompositionSpec(d.task_id, 'tabletop-v1', ('panda-v1',), ('cube-v1',),
                                      success_definition=d.success_definition)
    return compile_reference_source(
        artifact=artifact, scene_source=composer.build_source_description(), composition=composition,
        config=config, bodies={d.object_id: 'PickCube'}, frames={'panda-v1/ee': EE_SITE_NAME},
        free_joints={d.object_id: 'PickCube_joint'},
        joint_targets={f'panda-v1/joint{i}': f'actuator{i}' for i in range(1, 8)},
        open_actuators=('actuator8',),
    )
