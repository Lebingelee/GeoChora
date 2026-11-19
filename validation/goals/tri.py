"""Three-valued (Kleene) results shared by the goal engine and every vocabulary plugin."""
from __future__ import annotations

from dataclasses import dataclass, field
import math

import numpy as np


@dataclass(frozen=True)
class Tri:
    value: bool | None
    reason: str | None = None
    measurements: dict = field(default_factory=dict)
    basis: str | None = None

    def to_dict(self):
        out = {'value': self.value}
        if self.reason:
            out['reason'] = self.reason
        if self.measurements:
            out['measurements'] = _clean(self.measurements)
        if self.basis:
            out['basis'] = self.basis
        return out


def _clean(x):
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if not math.isfinite(float(x)) else float(x)
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.ndarray):
        return _clean(x.tolist())
    return x


def unknown(reason, **m):
    return Tri(None, reason, m)


def k_and(items):
    items = [i if isinstance(i, Tri) else Tri(i) for i in items]
    if any(i.value is False for i in items):
        return next(i for i in items if i.value is False)
    first = next((i for i in items if i.value is None), None)
    return first if first else Tri(True)


def k_or(items):
    items = [i if isinstance(i, Tri) else Tri(i) for i in items]
    if any(i.value is True for i in items):
        return next(i for i in items if i.value is True)
    first = next((i for i in items if i.value is None), None)
    return first if first else Tri(False)


def k_not(t):
    return Tri(None if t.value is None else not t.value, t.reason, t.measurements, t.basis)
