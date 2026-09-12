"""Single-environment UI rendering adapter.

The provider owns only the optional visualizer and headed window.  Physics
state remains owned by ``BaseTaskEnv``/``RuntimeBoundary``; ``rgb_array`` is
an explicit render readback and is never used to build observations.
"""

from __future__ import annotations

import numpy as np

from ..base.contracts import RenderMode
from ..tools.processing import RenderProcessor


class TaskEnvRenderProvider:
    """Lazy adapter from a TaskEnv render source to the existing visualizers."""

    def __init__(self, *, render_source: object, config: object) -> None:
        if render_source is None:
            raise ValueError("TaskEnv UI rendering requires a render source")
        self._render_source = render_source
        self._config = config
        self._render_processor = RenderProcessor(config)
        self._visualizer = None
        self._fixed_camera_pose = None
        self._window = None
        self._canvas = None
        self._closed = False
        self._frame_submission_enabled = True

    @property
    def visualizer(self):
        """Return the lazily created visualizer for diagnostics and smoke tests."""

        return self._visualizer

    @property
    def frame_submission_enabled(self) -> bool:
        return bool(self._frame_submission_enabled)

    def set_frame_submission_enabled(self, enabled: bool) -> None:
        """Pause/resume rendering work without touching the simulation."""

        self._frame_submission_enabled = bool(enabled)

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("TaskEnv render provider is closed")

    def _ensure_visualizer(self):
        self._require_open()
        if self._visualizer is None:
            self._visualizer = self._render_processor.build_visualizer(
                self._render_source
            )
            self._fixed_camera_pose = self._read_initial_camera_pose(
                self._visualizer
            )
        return self._visualizer

    @staticmethod
    def _read_initial_camera_pose(visualizer: object):
        pose = getattr(visualizer, "_initial_camera_pose", None)
        if pose is None or len(pose) != 3:
            raise RuntimeError(
                "TaskEnv visualizer does not expose an initial camera pose"
            )
        return tuple(
            tuple(float(value) for value in component)
            for component in pose
        )

    def _restore_fixed_camera_pose(self, visualizer: object) -> None:
        pose = self._fixed_camera_pose
        if pose is None:
            pose = self._read_initial_camera_pose(visualizer)
            self._fixed_camera_pose = pose
        set_camera_pose = getattr(visualizer, "set_camera_pose", None)
        if not callable(set_camera_pose):
            raise RuntimeError(
                "TaskEnv visualizer does not expose set_camera_pose()"
            )
        set_camera_pose(*pose)

    @staticmethod
    def _window_is_running(window: object | None) -> bool:
        if window is None:
            return False
        return bool(getattr(window, "running", True))

    def _close_window(self) -> None:
        window = self._window
        self._window = None
        self._canvas = None
        close = getattr(window, "close", None)
        if not callable(close):
            close = getattr(window, "destroy", None)
        if callable(close):
            close()

    def _ensure_window(self):
        visualizer = self._ensure_visualizer()
        if self._window_is_running(self._window):
            return self._window, self._canvas

        # A closed headed window is a display lifecycle event, not a session
        # stop.  The next human render may create a fresh window around the
        # same visualizer and current runtime state.
        self._close_window()
        import taichi as ti

        width = int(self._config.width)
        height = int(self._config.height)
        disable_ime = getattr(visualizer, "_disable_ime_for_process", None)
        if callable(disable_ime):
            disable_ime()
        visualizer._refresh_render_snapshot()
        visualizer._render_frame_to_buffer(width, height)
        visualizer._synchronize_taichi_runtime()
        window = ti.ui.Window(
            "GeoPhys TaskEnv",
            res=(width, height),
            vsync=False,
            fps_limit=60,
        )
        canvas = window.get_canvas()
        self._window = window
        self._canvas = canvas
        return window, canvas

    def _render_rgb(self) -> np.ndarray:
        visualizer = self._ensure_visualizer()
        # rgb_array is a deterministic observation-like export.  It must not
        # inherit a camera pose left behind by headed interaction.
        self._restore_fixed_camera_pose(visualizer)
        frame = visualizer.read_frame(
            width=int(self._config.width),
            height=int(self._config.height),
            synchronized=True,
        )
        frame = np.asarray(frame, dtype=np.float32)
        if frame.shape != (int(self._config.height), int(self._config.width), 3):
            raise RuntimeError(
                "TaskEnv rgb_array visualizer returned an unexpected frame shape: "
                f"expected {(int(self._config.height), int(self._config.width), 3)}, "
                f"got {frame.shape}"
            )
        if not np.isfinite(frame).all():
            raise RuntimeError("TaskEnv rgb_array visualizer returned non-finite pixels")
        return np.ascontiguousarray(np.clip(frame, 0.0, 1.0), dtype=np.float32)

    def _render_human(self) -> None:
        visualizer = self._ensure_visualizer()
        window, canvas = self._ensure_window()
        poll_events = getattr(window, "poll_events", None)
        if callable(poll_events):
            poll_events()
        if not self._window_is_running(window):
            self._close_window()
            return
        if self._frame_submission_enabled:
            process_camera_input = getattr(
                visualizer, "_process_camera_input", None
            )
            if callable(process_camera_input):
                process_camera_input(window)
            visualizer._refresh_render_snapshot()
            visualizer._render_frame_to_buffer(
                int(self._config.width), int(self._config.height)
            )
            visualizer._synchronize_taichi_runtime()
            visualizer._present_rendered_frame(canvas)
            visualizer._mark_displayed_snapshot()
        window.show()

    def render(self, *, mode: RenderMode, snapshot: object) -> np.ndarray | None:
        del snapshot
        self._require_open()
        if mode is RenderMode.RGB_ARRAY:
            return self._render_rgb()
        if mode is RenderMode.HUMAN:
            self._render_human()
            return None
        raise ValueError(f"unsupported TaskEnv render mode: {mode!r}")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._close_window()
        self._visualizer = None


__all__ = ["TaskEnvRenderProvider"]
