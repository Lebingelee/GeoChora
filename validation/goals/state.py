"""Normalized input model for goal evaluation (world frame, metres, Z up, WXYZ)."""
from __future__ import annotations

from dataclasses import dataclass, field
import math

import numpy as np

FINGER_BODIES = ('finger_left', 'finger_right')


def _vec(value, size, label):
    a = np.asarray(value, dtype=float)
    if a.shape != (size,) or not np.isfinite(a).all():
        raise ValueError(f'{label}: finite vector of length {size} required')
    return a


@dataclass
class SceneState:
    """One observation. Missing objects/drawers/contacts stay missing (-> unknown).

    positions: public object name -> body-origin xyz (manifest frame convention).
    orientations_wxyz: public object name -> unit quaternion (optional for balls).
    drawer_openings: drawer name -> opening = -joint_position in metres.
    finger_positions: 'finger_left'/'finger_right' -> xyz (point model of the finger link).
    contacts: set of unordered body-name pairs; only meaningful when contacts_available.
      Names: object names, drawer names, 'table', 'finger_left', 'finger_right', 'robot'.
    settled: True/False when the producer knows whether all task objects came to rest.
    """

    positions: dict = field(default_factory=dict)
    orientations_wxyz: dict = field(default_factory=dict)
    drawer_openings: dict = field(default_factory=dict)
    finger_positions: dict = field(default_factory=dict)
    contacts: frozenset | None = None
    contacts_available: bool = False
    time: float | None = None
    settled: bool | None = None

    def __post_init__(self):
        self.positions = {k: _vec(v, 3, f'position[{k}]') for k, v in self.positions.items()}
        self.orientations_wxyz = {k: _vec(v, 4, f'orientation[{k}]') for k, v in self.orientations_wxyz.items()}
        self.finger_positions = {k: _vec(v, 3, f'finger[{k}]') for k, v in self.finger_positions.items()}
        self.drawer_openings = {k: float(v) for k, v in self.drawer_openings.items()
                                if v is not None and math.isfinite(float(v))}
        self.contacts_available = bool(self.contacts_available)
        self.contacts = (frozenset(frozenset(pair) for pair in self.contacts)
                         if self.contacts is not None else None)
        if self.contacts_available and self.contacts is None:
            self.contacts = frozenset()
        if not self.contacts_available:
            self.contacts = None


@dataclass
class Trace:
    """Timed samples (strictly increasing time) plus an independent completeness fact."""

    samples: list
    recording_complete: bool = False

    def __post_init__(self):
        self.samples = list(self.samples)
        if any(s.time is None for s in self.samples):
            raise ValueError('every trace sample needs a time')
        times = self.times
        if len(times) and (np.any(np.diff(times) <= 0) or times[0] < 0):
            raise ValueError('trace times must be nonnegative and strictly increasing')
        self.recording_complete = bool(self.recording_complete)

    @property
    def times(self):
        return np.array([s.time for s in self.samples], dtype=float)

    def settle_report(self, names, *, speed_mps=0.02, window_s=0.5):
        """Final-window linear speed of the named objects (finite differences).

        Settled when every object has speed < speed_mps over the last window_s seconds
        (every sample step inside the window). Returns dict(settled: bool|None, max_speed, ...).
        None when the record is shorter than the window or objects are missing.
        """
        times = self.times
        if len(times) < 2 or times[-1] - times[0] < window_s:
            return {'settled': None, 'reason': 'record_shorter_than_window'}
        start = times[-1] - window_s
        index = int(np.searchsorted(times, start - 1e-9, side='left'))
        index = max(0, min(index, len(times) - 2))
        worst, missing = 0.0, []
        for name in names:
            pts = []
            for s in self.samples[index:]:
                p = s.positions.get(name)
                if p is None:
                    missing.append(name)
                    break
                pts.append(p)
            else:
                dt = np.diff(times[index:])
                v = np.linalg.norm(np.diff(np.array(pts), axis=0), axis=1) / dt
                worst = max(worst, float(v.max()))
        if missing:
            return {'settled': None, 'reason': 'object_missing_in_window', 'missing': sorted(set(missing))}
        return {'settled': worst < speed_mps, 'max_speed_mps': worst, 'window_s': window_s,
                'speed_limit_mps': speed_mps}
