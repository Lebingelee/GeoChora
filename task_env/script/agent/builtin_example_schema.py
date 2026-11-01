"""Versioned input contract for examples composed from a built-in Core task.

This deliberately does not extend CandidateSpec: example runs report runtime
validity and task outcomes, and can never become Oracle/Judge candidates.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


@dataclass(frozen=True)
class BuiltinPickCubeExampleV1:
    schema_version: str
    example_id: str
    task_uid: str
    provider: str
    backend: str
    device: str
    controller_profile: str
    seeds: tuple[int, ...]
    horizon_control_ticks: int
    physics_dt_s: float
    control_substeps: int

    def __post_init__(self):
        if self.schema_version != "harness-builtin-pickcube-example-v1":
            raise ValueError("unsupported built-in PickCube example schema")
        if self.example_id != "pickcube-harness-example-v1":
            raise ValueError("unsupported built-in example id")
        if self.task_uid != "pick-cube-p16-reference-v1":
            raise ValueError("built-in example must select the public PickCube UID")
        routes = {
            "mujoco": ("cpu", "cpu"),
            "geophys": ("cpu", "cpu"),
            "isaacsim": ("cuda", "cuda:0"),
            "genesis": ("cpu", "cpu"),
            "sapien": ("cpu", "cpu"),
        }
        if self.provider not in routes or (self.backend, self.device) != routes[self.provider]:
            raise ValueError("provider/backend/device must match an exact built-in route")
        if self.controller_profile != "r3_continuous_v1":
            raise ValueError("F06 requires the existing explicit r3_continuous_v1 profile")
        if (not isinstance(self.seeds, (tuple, list)) or tuple(self.seeds) != (31, 32, 33)):
            raise ValueError("F06 example runs the fixed seed set 31/32/33")
        if type(self.horizon_control_ticks) is not int or self.horizon_control_ticks != 1000:
            raise ValueError("F06 example horizon is exactly 1000 control ticks")
        if (isinstance(self.physics_dt_s, bool) or not isinstance(self.physics_dt_s, (int, float))
                or not math.isfinite(float(self.physics_dt_s)) or float(self.physics_dt_s) != 0.002):
            raise ValueError("F06 PickCube physics_dt_s is fixed at 0.002 seconds")
        if type(self.control_substeps) is not int or self.control_substeps != 5:
            raise ValueError("F06 PickCube control_substeps is fixed at 5")
        object.__setattr__(self, "seeds", tuple(self.seeds))
        object.__setattr__(self, "physics_dt_s", float(self.physics_dt_s))

    def to_dict(self):
        value = asdict(self)
        value["seeds"] = list(self.seeds)
        return value

    @property
    def identity_sha256(self):
        return hashlib.sha256(_canonical(self.to_dict()).encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            raise ValueError("built-in PickCube example must be an object")
        required = set(cls.__dataclass_fields__)
        if set(value) != required:
            raise ValueError(f"expected exact built-in example fields: {sorted(required)}")
        return cls(**value)

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text()))

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            json.dump(self.to_dict(), stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")


@dataclass(frozen=True)
class ExampleWorkingTreeScopeV1:
    """Allow tracked-clean execution with a byte-pinned untracked allowlist."""

    schema_version: str
    expected_untracked: tuple[tuple[str, str], ...]

    def __post_init__(self):
        if self.schema_version != "harness-example-working-tree-scope-v1":
            raise ValueError("unsupported example working-tree scope")
        rows = tuple(tuple(row) for row in self.expected_untracked)
        if any(len(row) != 2 or not row[0] or len(row[1]) != 64
               or any(char not in "0123456789abcdef" for char in row[1]) for row in rows):
            raise ValueError("expected_untracked rows require path and SHA-256")
        if tuple(sorted(rows)) != rows or len({row[0] for row in rows}) != len(rows):
            raise ValueError("expected_untracked must be sorted and contain unique paths")
        object.__setattr__(self, "expected_untracked", rows)

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != {"schema_version", "expected_untracked"}:
            raise ValueError("working-tree scope requires exact versioned fields")
        rows = value["expected_untracked"]
        if not isinstance(rows, list) or any(not isinstance(row, dict) or set(row) != {"path", "sha256"}
                                             for row in rows):
            raise ValueError("expected_untracked must be a list of {path, sha256}")
        return cls(value["schema_version"], tuple((row["path"], row["sha256"]) for row in rows))

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text()))

    def to_dict(self):
        return {"schema_version": self.schema_version,
                "expected_untracked": [{"path": path, "sha256": digest}
                                       for path, digest in self.expected_untracked]}
