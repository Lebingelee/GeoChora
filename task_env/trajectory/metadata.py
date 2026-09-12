"""Portable metadata serialization for TaskEnv H5 containers.

New files store both ``env_cfg`` and ``env_meta`` as YAML scalar datasets.
The reader deliberately accepts historical JSON ``env_meta`` documents because
JSON is a YAML-compatible data model and older Stage 11 files are immutable.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from collections.abc import Mapping
from typing import Any

import numpy as np
import yaml


def _json_default(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"metadata contains non-JSON value {type(value)!r}")


def plain_metadata(value: Any) -> Any:
    """Project runtime values to the portable metadata data model."""

    return json.loads(json.dumps(value, default=_json_default, sort_keys=True))


def dump_metadata(value: Any) -> str:
    """Serialize a metadata document as stable, human-readable YAML."""

    return yaml.safe_dump(
        plain_metadata(value),
        sort_keys=True,
        allow_unicode=True,
    )


def load_metadata(text: str) -> Any:
    """Read YAML metadata, including historical JSON documents."""

    value = yaml.safe_load(text)
    return {} if value is None else value


__all__ = ["dump_metadata", "load_metadata", "plain_metadata"]
