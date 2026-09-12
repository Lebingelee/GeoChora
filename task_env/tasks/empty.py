"""可构造和 reset 的纯背景环境。"""

from ..registry import register_env
from .base import BaseTaskEnv


@register_env()
class EmptyTaskEnv(BaseTaskEnv):
    uid = "empty-v1"
    task_uid = "empty-v1"
    scene_uid = "tabletop-v1"
    agent_uids = ()
    object_uids = ()
    success_definition = "none"


__all__ = ["EmptyTaskEnv"]
