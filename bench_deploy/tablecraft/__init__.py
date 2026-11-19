"""Source-bound TableCraft tasks and existing terminal-review integration."""

from .task import get_task, list_tasks, model_prompt, task_source
from .scene import prepare_assets, scene_resources
from .solution import reference_files
from .evaluation import prepare_terminal_review

__all__ = [
    "get_task", "list_tasks", "model_prompt", "task_source",
    "prepare_assets", "scene_resources", "reference_files", "prepare_terminal_review",
]
