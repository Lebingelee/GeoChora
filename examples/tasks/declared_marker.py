"""Declare a new marker task using the shared Panda/table/box construction."""
from __future__ import annotations

from task_env.artifacts import SemanticDefinition, Timebase
from task_env.assembly.panda_box import PandaBoxDeclaration
from task_env.environment import TaskEvaluation
from task_env.registry import register_env
from task_env.tasks.declarative_reference import DeclaredPandaBoxEnv


@register_env()
class MarkerHeightEnv(DeclaredPandaBoxEnv):
    """Observe a movable marker and report whether it reaches a height."""

    uid = 'marker-height-example-v1'

    @classmethod
    def declaration(cls):
        semantics = SemanticDefinition(
            'semantics-v0', 'marker-height-v1', ('marker-v1', 'panda-v1/ee'), (),
            {'height_m': 0.60}, 'marker_above_height_v1',
        )
        return PandaBoxDeclaration(
            task_id=cls.uid, artifact_id='marker-height-example-v1/initial', version='v1',
            object_id='marker-v1', success_definition='marker_above_height_v1',
            table_half_size=(.28, .20, .01), table_top_z=.462, table_center_xy=(.5545, 0.),
            source_box_position=(.50, 0., .488), source_box_quaternion_wxyz=(1., 0., 0., 0.),
            reset_center_xy=(.5545, 0.), reset_half_extent_m=.05, semantics=semantics,
            timebase=Timebase(.002, 5, .01),
        )

    @staticmethod
    def evaluate_task(state, semantics):
        semantics.require_state(state)
        height = state.pose_world['marker-v1'].position[2]
        success = height >= semantics.parameters_si['height_m']
        return TaskEvaluation(float(success), success, False,
                              {'marker_height_m': height, 'task_success': success},
                              {'height': float(success)})
