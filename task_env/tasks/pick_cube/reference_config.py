"""Tracked public configuration for selected PickCube construction."""
from pathlib import Path

from ...environment.configuration import (
    load_yaml_mapping,
    overlay_public_env_config,
    resolve_env_config,
)
from .definition import PICK_CUBE_SPEC


DEFAULT_CONFIG_PATH = Path(__file__).with_name("default.yaml")


def build_reference_config():
    """Resolve the same public defaults without importing the legacy TaskEnv."""
    spec = PICK_CUBE_SPEC
    base = resolve_env_config(
        task_uid=spec.task_uid,
        scene_uid=spec.scene_uid,
        agent_uids=spec.agent_uids,
        object_uids=spec.object_uids,
        success_definition=spec.success_definition,
    )
    return overlay_public_env_config(base, load_yaml_mapping(DEFAULT_CONFIG_PATH))


__all__ = ["DEFAULT_CONFIG_PATH", "build_reference_config"]
