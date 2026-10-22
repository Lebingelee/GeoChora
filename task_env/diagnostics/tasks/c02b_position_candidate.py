"""Compatibility diagnostic route; construction is owned by the task package."""

from task_env.tasks.position_candidate.builder import (
    POSITION_CANDIDATE_SEED,
    POSITION_CANDIDATE_TASK_ID,
    POSITION_CANDIDATE_VERSION,
    build_position_candidate,
)

__all__ = [
    'POSITION_CANDIDATE_SEED', 'POSITION_CANDIDATE_TASK_ID',
    'POSITION_CANDIDATE_VERSION', 'build_position_candidate',
]
