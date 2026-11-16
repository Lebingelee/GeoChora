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

    def __init__(self, *, render_source: object, config: object, frame_capture=None,
                 frame_presenter=None, frame_color_space='unverified native framebuffer encoding') -> None:
        if render_source is None and frame_capture is None:
            raise ValueError("TaskEnv UI rendering requires a render source")
        self._render_source = render_source
        self._config = config
        self._render_processor = RenderProcessor(config)
        self._visualizer = None
        self._fixed_camera_pose = None
        self._camera_controller = None
        self._window = None
        self._canvas = None
        self._closed = False
        self._frame_submission_enabled = True
        self._frame_capture = frame_capture
        self._frame_presenter = frame_presenter
        self._frame_color_space = frame_color_space
        self._window_image = None
        self._window_label = None
        self._window_closed_by_user = False
        self._last_frame_receipt = None

    @property
    def last_frame_receipt(self):
        return self._last_frame_receipt

    def invalidate_frame(self):
        self._last_frame_receipt = None

    def _capture_owned_frame(self):
        frame = self._frame_capture()
        self._last_frame_receipt = {
            'camera': frame.metadata.to_mapping(),
            'capture_identity': frame.capture_identity.to_mapping(),
            'completion': 'synchronous native readback and owned host copy',
            'layout': 'HWC', 'dtype': 'float32', 'range': [0, 1], 'channels': 'RGB',
            'color_space': self._frame_color_space,
        }
        return np.array(frame.rgb, dtype=np.float32, copy=True, order='C')

    def _present_owned_frame(self):
        # Window resources belong to this existing UI provider.  The camera
        # session owns the native renderer and its completed host frame.
        if self._window_closed_by_user:
            self._capture_owned_frame()
            self._last_frame_receipt['presentation'] = {
                'status': 'display_closed_capture_only',
                'event_pump': 'not_run',
                'completion': 'capture retained; observer window was closed by user',
                'window_id': None,
            }
            return
        if self._window is None:
            import tkinter as tk
            window = tk.Tk()
            try:
                window.title('GeoChora observer')
                label = tk.Label(window, borderwidth=0, highlightthickness=0)
                label.pack()
                def closed():
                    self._window_closed_by_user = True
                    self._close_window()
                window.protocol('WM_DELETE_WINDOW', closed)
            except BaseException:
                window.destroy()
                raise
            self._window, self._window_label = window, label
        frame = self._capture_owned_frame()
        import tkinter as tk
        pixels = np.rint(np.clip(frame, 0, 1) * 255).astype(np.uint8)
        ppm = f'P6\n{frame.shape[1]} {frame.shape[0]}\n255\n'.encode() + pixels.tobytes()
        self._window_image = tk.PhotoImage(data=ppm, format='PPM', master=self._window)
        self._window_label.configure(image=self._window_image)
        window_id = int(self._window.winfo_id())
        self._window.update_idletasks()
        self._window.update()
        if self._window_closed_by_user:
            self._last_frame_receipt['presentation'] = {
                'status': 'closed_during_event_pump',
                'event_pump': 'Tk update',
                'completion': 'window closed during event processing after image submission',
                'window_id': window_id,
            }
            return
        self._last_frame_receipt['presentation'] = {
            'status': 'presented',
            'event_pump': 'Tk update', 'completion': 'synchronous Tk image update',
            'window_id': window_id,
        }

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
                self._render_source, self._render_processor.request.backend
            )
        return self._visualizer

    @staticmethod
    def _read_initial_camera_pose(source: object, backend: str):
        """Resolve the source's public authored/default camera declaration."""
        read_scene = getattr(source, 'read_render_scene', None)
        scene = read_scene(backend=backend) if callable(read_scene) else None
        camera = getattr(scene, 'camera', None)
        if camera is not None:
            pose = (camera.position, camera.look_at, camera.up)
        else:
            default = getattr(source, 'compute_default_camera', None)
            if not callable(default):
                raise RuntimeError('render source does not declare a default camera pose')
            pose = default()
        if len(pose) != 3:
            raise RuntimeError('render source declared an invalid default camera pose')
        return tuple(tuple(float(value) for value in component) for component in pose)

    def _restore_fixed_camera_pose(self, visualizer: object) -> None:
        pose = self._fixed_camera_pose
        if pose is None:
            pose = self._read_initial_camera_pose(
                self._render_source, self._render_processor.request.backend)
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
        if self._frame_capture is not None:
            self._window_label = self._window_image = None
            if window is not None:
                window.destroy()
            return
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
        return self._read_visualizer_frame(visualizer)

    def _read_visualizer_frame(self, visualizer):
        frame = visualizer.read_frame(
            width=int(self._config.width), height=int(self._config.height), synchronized=True)
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
            import taichi as ti
            if self._camera_controller is None:
                from ..tools.camera import InteractiveCameraController
                position, look_at, up = self._fixed_camera_pose
                lower = getattr(self._render_source, 'domain_min_vec', None)
                upper = getattr(self._render_source, 'domain_max_vec', None)
                diagonal = (float(np.linalg.norm(np.asarray(upper) - np.asarray(lower)))
                            if lower is not None and upper is not None else 0.0)
                self._camera_move_speed = max(diagonal * 0.48, 0.3)
                self._camera_controller = InteractiveCameraController(
                    position=position, look_at=look_at, up=up,
                    pose_sink=visualizer.set_camera_pose,
                    pan_speed_per_norm=max(diagonal, 0.1),
                    wheel_dolly_step=max(diagonal * 0.08, 0.05))
            self._camera_controller.update(window, right_key=ti.ui.RMB,
                                           left_key=ti.ui.LMB, ctrl_key=ti.ui.CTRL,
                                           extended=True, middle_key=ti.ui.MMB,
                                           shift_key=ti.ui.SHIFT, alt_key=ti.ui.ALT,
                                           move_speed_per_second=self._camera_move_speed)
            frame = self._read_visualizer_frame(visualizer)
            # Public readback is HWC with a top-left origin; the window canvas
            # consumes width-major pixels with a lower-left origin.
            canvas.set_image(np.ascontiguousarray(frame[::-1].transpose(1, 0, 2)))
        window.show()

    def render(self, *, mode: RenderMode, snapshot: object) -> np.ndarray | None:
        del snapshot
        self._require_open()
        if self._frame_capture is not None:
            self.invalidate_frame()
            if mode is RenderMode.RGB_ARRAY:
                return self._capture_owned_frame()
            if mode is RenderMode.HUMAN:
                try:
                    if self._frame_presenter is None:
                        self._present_owned_frame()
                    else:
                        self._capture_owned_frame()
                        self._last_frame_receipt['presentation'] = self._frame_presenter()
                except BaseException as error:
                    self.invalidate_frame()
                    try:
                        self._close_window()
                    except BaseException as cleanup_error:
                        error.add_note(f'observer window cleanup also failed: {cleanup_error!r}')
                    raise
                return None
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
        self.invalidate_frame()
        self._close_window()
        self._visualizer = None


__all__ = ["TaskEnvRenderProvider"]
