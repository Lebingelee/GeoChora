"""Stage 1 将消费的任务场景 source 描述。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TaskSceneSource:
    xml: str
    base_dir: Path
    source_id: str
    diagnostics: tuple[str, ...] = ()


__all__ = ["TaskSceneSource"]
