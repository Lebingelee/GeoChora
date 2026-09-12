"""Backend-neutral interactive camera input for headed TaskEnv rendering.

The controller owns only camera interaction state.  It does not know about a
scene, a robot, or a renderer; a backend supplies a pose sink that receives
GeoPhys/world-space camera poses.  The mouse contract mirrors the existing
Rasterizer FPS camera:

* RMB drag rotates the view;
* Ctrl+RMB drag translates in the current view plane;
* the wheel dollies along the current view direction;
* no keyboard movement is handled here.
"""

from __future__ import annotations

import math
from typing import Callable

import numpy as np
import taichi as ti


CameraPoseSink = Callable[
    [
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ],
    None,
]


def _finite_vector(value: object, *, name: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64).reshape(-1)
    if array.size != 3 or not np.isfinite(array).all():
        raise ValueError(f"camera {name} must be a finite 3-vector")
    return array.copy()


class InteractiveCameraController:
    """FPS-style camera controller shared by external headed backends."""

    def __init__(
        self,
        *,
        position: object,
        look_at: object,
        up: object = (0.0, 0.0, 1.0),
        pose_sink: CameraPoseSink,
        pan_speed_per_norm: float = 0.05,
        wheel_dolly_step: float = 0.05,
        mouse_sensitivity: float = 1.2,
    ) -> None:
        if not callable(pose_sink):
            raise TypeError("camera pose_sink must be callable")
        self._pose_sink = pose_sink
        self._pan_speed_per_norm = float(pan_speed_per_norm)
        self._wheel_dolly_step = float(wheel_dolly_step)
        self._mouse_sensitivity = float(mouse_sensitivity)
        if (
            not math.isfinite(self._pan_speed_per_norm)
            or self._pan_speed_per_norm <= 0.0
            or not math.isfinite(self._wheel_dolly_step)
            or self._wheel_dolly_step <= 0.0
            or not math.isfinite(self._mouse_sensitivity)
            or self._mouse_sensitivity <= 0.0
        ):
            raise ValueError("camera interaction scales must be finite and positive")
        self._position = np.zeros(3, dtype=np.float64)
        self._look_distance = 2.0
        self._yaw = 0.0
        self._pitch = 0.0
        self._last_mouse: tuple[float, float] | None = None
        self._mouse_drag_mode: str | None = None
        self.sync_pose(position, look_at, up)

    @property
    def position(self) -> tuple[float, float, float]:
        return tuple(float(value) for value in self._position)

    @property
    def look_distance(self) -> float:
        return float(self._look_distance)

    def sync_pose(self, position: object, look_at: object, up: object) -> None:
        """Synchronize state after a backend or layout changes the pose."""

        del up  # The interactive basis is the world-Z-up FPS basis, as in Rasterizer.
        position_np = _finite_vector(position, name="position")
        look_at_np = _finite_vector(look_at, name="look_at")
        direction = look_at_np - position_np
        distance = float(np.linalg.norm(direction))
        if distance > 1.0e-8:
            direction /= distance
            self._pitch = math.asin(float(np.clip(direction[2], -1.0, 1.0)))
            self._yaw = math.atan2(float(direction[1]), float(direction[0]))
            self._look_distance = distance
        self._position = position_np
        self._last_mouse = None
        self._mouse_drag_mode = None

    def set_motion_scale(
        self,
        *,
        pan_speed_per_norm: float | None = None,
        wheel_dolly_step: float | None = None,
    ) -> None:
        """Update world-space mouse travel without changing camera optics."""

        if pan_speed_per_norm is not None:
            value = float(pan_speed_per_norm)
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError("camera pan speed must be finite and positive")
            self._pan_speed_per_norm = value
        if wheel_dolly_step is not None:
            value = float(wheel_dolly_step)
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError("camera wheel step must be finite and positive")
            self._wheel_dolly_step = value

    @staticmethod
    def _consume_scroll_delta(window: object) -> float:
        getter = getattr(window, "get_scroll_delta", None)
        if not callable(getter):
            return 0.0
        try:
            value = getter()
            if isinstance(value, (tuple, list, np.ndarray)):
                if len(value) == 0:
                    return 0.0
                value = value[1] if len(value) > 1 else value[0]
            resolved = float(value)
        except (AttributeError, TypeError, ValueError, RuntimeError):
            return 0.0
        if not math.isfinite(resolved):
            return 0.0
        return max(-8.0, min(8.0, resolved))

    @staticmethod
    def _is_pressed(window: object, key: object) -> bool:
        getter = getattr(window, "is_pressed", None)
        if not callable(getter):
            return False
        candidates = (key, str(key), str(key).lower(), str(key).upper())
        for candidate in candidates:
            try:
                if bool(getter(candidate)):
                    return True
            except (AttributeError, TypeError, ValueError, RuntimeError):
                continue
        return False

    @classmethod
    def _is_ctrl_pressed(cls, window: object) -> bool:
        """Accept Forge's aggregate and left/right Ctrl key spellings."""

        return any(
            cls._is_pressed(window, key)
            for key in (ti.ui.CTRL, "Control", "Control_L", "Control_R", "Ctrl")
        )

    @staticmethod
    def _input_available(window: object) -> bool:
        getter = getattr(window, "is_render_input_available", None)
        if not callable(getter):
            return True
        try:
            return bool(getter())
        except (AttributeError, TypeError, ValueError, RuntimeError):
            return False

    @staticmethod
    def _cursor_position(window: object) -> tuple[float, float] | None:
        getter = getattr(window, "get_render_cursor_pos", None)
        if callable(getter):
            for args in ((False,), ()):
                try:
                    value = getter(*args)
                    if value is not None and len(value) == 2:
                        return float(value[0]), float(value[1])
                except (AttributeError, TypeError, ValueError, RuntimeError):
                    continue
        getter = getattr(window, "get_cursor_pos", None)
        if not callable(getter):
            return None
        try:
            value = getter()
            if value is None or len(value) != 2:
                return None
            return float(value[0]), float(value[1])
        except (AttributeError, TypeError, ValueError, RuntimeError):
            return None

    @staticmethod
    def _view_basis(
        yaw: float,
        pitch: float,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        cos_yaw = math.cos(yaw)
        sin_yaw = math.sin(yaw)
        cos_pitch = math.cos(pitch)
        sin_pitch = math.sin(pitch)
        front = np.array(
            [cos_yaw * cos_pitch, sin_yaw * cos_pitch, sin_pitch],
            dtype=np.float64,
        )
        front /= max(float(np.linalg.norm(front)), 1.0e-12)
        right = np.cross(front, np.array([0.0, 0.0, 1.0]))
        norm_right = float(np.linalg.norm(right))
        right = (
            np.array([1.0, 0.0, 0.0], dtype=np.float64)
            if norm_right < 1.0e-8
            else right / norm_right
        )
        up = np.cross(right, front)
        return front, right, up

    def _emit(self, position: np.ndarray, front: np.ndarray, up: np.ndarray) -> None:
        self._position = np.asarray(position, dtype=np.float64).copy()
        look_at = self._position + front * self._look_distance
        self._pose_sink(
            tuple(float(value) for value in self._position),
            tuple(float(value) for value in look_at),
            tuple(float(value) for value in up),
        )

    def update(self, window: object) -> bool:
        """Consume one window state and emit at most one changed camera pose."""

        scroll_delta = self._consume_scroll_delta(window)
        input_available = self._input_available(window)
        right_pressed = self._is_pressed(window, ti.ui.RMB)
        left_pressed = self._is_pressed(window, ti.ui.LMB)
        ctrl_pressed = self._is_ctrl_pressed(window)
        cursor = (
            self._cursor_position(window)
            if right_pressed or abs(scroll_delta) > 1.0e-8
            else None
        )
        cursor_valid = bool(
            input_available
            and cursor is not None
            and all(0.0 <= value <= 1.0 for value in cursor)
        )
        front, right, up = self._view_basis(self._yaw, self._pitch)
        position = self._position.copy()
        changed = False

        drag_mode = "pan" if ctrl_pressed else "rotate"
        if right_pressed and input_available:
            if not cursor_valid:
                self._last_mouse = None
                self._mouse_drag_mode = None
            elif self._last_mouse is None or self._mouse_drag_mode != drag_mode:
                self._last_mouse = cursor
                self._mouse_drag_mode = drag_mode
            else:
                dx = cursor[0] - self._last_mouse[0]
                dy = cursor[1] - self._last_mouse[1]
                if abs(dx) > 1.0e-8 or abs(dy) > 1.0e-8:
                    if ctrl_pressed:
                        try:
                            window_width, window_height = window.get_window_shape()
                            aspect = max(
                                float(window_width) / max(float(window_height), 1.0),
                                1.0e-6,
                            )
                        except (AttributeError, TypeError, ValueError, RuntimeError):
                            aspect = 1.0
                        # The window cursor grows from the lower-left.  Make
                        # camera translation follow the cursor in its screen
                        # basis: right drag moves along ``right`` and upward
                        # drag moves along ``up``.  This is a pure translation;
                        # yaw/pitch are intentionally untouched.
                        position += right * (dx * self._pan_speed_per_norm * aspect)
                        position += up * (dy * self._pan_speed_per_norm)
                    else:
                        self._yaw -= dx * self._mouse_sensitivity
                        self._pitch = max(
                            -1.5,
                            min(1.5, self._pitch + dy * self._mouse_sensitivity),
                        )
                    changed = True
                self._last_mouse = cursor
        else:
            self._last_mouse = None
            self._mouse_drag_mode = None

        if changed and not ctrl_pressed and right_pressed:
            front, right, up = self._view_basis(self._yaw, self._pitch)

        if (
            abs(scroll_delta) > 1.0e-8
            and not right_pressed
            and not left_pressed
            and cursor_valid
        ):
            position += front * scroll_delta * self._wheel_dolly_step
            changed = True

        if not changed:
            return False
        self._emit(position, front, up)
        return True


__all__ = ["CameraPoseSink", "InteractiveCameraController"]
