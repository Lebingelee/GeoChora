"""Camera RGB/depth acquisition for TaskEnv observations."""

from __future__ import annotations

from collections import OrderedDict

import numpy as np

from ..environment import RenderConfig, RuntimeSnapshot, SensorObservation
from .camera import CameraSensor
from .canonical_camera.images import normalize_rgb
from .canonical_camera.consumer import (
    CAMERA_IDS,
    CameraObservationConfigV1,
    camera_observation_boundary_from_captures,
)
from .canonical_camera.images import CanonicalCameraObservation


class DynamicCameraObservationConsumerV1:
    """Own two D04 camera sessions and publish one cached boundary bundle.

    The consumer only reads the already-published CanonicalStateViewV1.  Its
    default factory is imported lazily, so importing TaskEnv or constructing a
    state-only candidate never imports MuJoCo or initializes a renderer.
    """

    def __init__(
        self,
        *,
        config: CameraObservationConfigV1,
        task_artifact_hash: str,
        runtime_source,
        horizon: int,
        session_factory=None,
    ) -> None:
        if not isinstance(config, CameraObservationConfigV1):
            raise TypeError("dynamic camera consumer requires CameraObservationConfigV1")
        self.config = config
        self.config.validate()
        self.capacity = config.capacity(horizon)
        self._task_artifact_hash = task_artifact_hash
        self._runtime_source = runtime_source
        self._horizon = horizon
        self._session_factory = session_factory
        self._sessions = []
        self._closed = False
        self._last_key = None
        self._last_control_step = None
        self._last_boundary = None
        self._last_leaves = None
        self._last_capture_values = None

    def _ensure_sessions(self, state):
        if self._sessions:
            return
        from ..artifacts import ExecutionSpecV1, RendererSelectionV1
        from ..render.camera import (
            D03_PHYSICS_PROFILE,
            D04_ENTITY_SEGMENTATION_PROFILE,
            DynamicCameraRenderSourceV1,
            create_dynamic_camera_session,
            dynamic_entity_instance_segmentation_manifest,
        )

        render_source = DynamicCameraRenderSourceV1.from_runtime_source(self._runtime_source)
        renderer = RendererSelectionV1(
            "renderer-selection-v1", "mujoco", "native-opengl",
            D04_ENTITY_SEGMENTATION_PROFILE, None,
        )
        execution = ExecutionSpecV1(
            "execution-spec-v1", "geophys", "cpu", D03_PHYSICS_PROFILE,
            31, "best_effort", renderer, physics_device="cpu:0",
        )
        manifest = dynamic_entity_instance_segmentation_manifest()
        geometries = self.config.geometries(self._task_artifact_hash)
        factory = self._session_factory or create_dynamic_camera_session
        try:
            for camera in geometries:
                session = factory(
                    camera,
                    execution,
                    source=render_source,
                    initial_state=state,
                    manifest=manifest,
                )
                self._sessions.append(session)
        except BaseException as error:
            try:
                self.close()
            except BaseException as cleanup_error:
                add_note = getattr(error, "add_note", None)
                if callable(add_note):
                    add_note(f"camera session cleanup after construction failure also failed: {cleanup_error!r}")
            raise

    @staticmethod
    def _state_key(state):
        boundary = state.boundary
        clock = state.sample_clock
        return (
            boundary.scene_identity_hash,
            boundary.scene_instance_id,
            boundary.provider_materialization_id,
            boundary.episode_id,
            boundary.reset_sample_id,
            boundary.boundary_id,
            boundary.state_revision,
            boundary.control_step,
            float(clock.simulation_time_s),
        )

    def capture(self, state):
        """Capture all modalities for the exact current typed boundary."""

        if self._closed:
            raise RuntimeError("camera observation consumer is closed")
        from ..artifacts.state import CanonicalStateViewV1

        if not isinstance(state, CanonicalStateViewV1):
            raise TypeError("camera observation requires CanonicalStateViewV1")
        state.validate()
        key = self._state_key(state)
        if self._last_key == key:
            return self._result()
        boundary = state.boundary
        if self._last_key is not None:
            previous = self._last_boundary
            if (boundary.episode_id != previous.episode_id
                    or boundary.reset_sample_id != previous.reset_sample_id
                    or boundary.scene_instance_id != previous.scene_instance_id
                    or boundary.provider_materialization_id != previous.provider_materialization_id
                    or boundary.control_step != self._last_control_step + 1):
                raise ValueError("camera consumer requires one contiguous episode boundary; reset the consumer first")
        self._ensure_sessions(state)
        captures = tuple(session.capture(state) for session in self._sessions)
        if len(captures) != 2 or any(not isinstance(item, CanonicalCameraObservation) for item in captures):
            raise ValueError("camera consumer requires two CanonicalCameraObservation values")
        for camera_id, capture in zip(CAMERA_IDS, captures):
            if capture.capture_identity is None or capture.segmentation is None:
                raise ValueError(f"camera {camera_id} did not publish its required capture identity and Entity mask")
            if capture.capture_identity.camera_id != camera_id:
                raise ValueError("camera capture order or identity changed")
            if (capture.capture_identity.state_boundary != state.boundary
                    or capture.capture_identity.sample_clock != state.sample_clock):
                raise ValueError("camera capture identity does not bind the supplied typed publication")
            if capture.rgb is None or capture.rgb.dtype != np.float32 or capture.rgb.shape != (
                self.config.height, self.config.width, 3,
            ) or not np.isfinite(capture.rgb).all() or np.any(capture.rgb < 0) or np.any(capture.rgb > 1):
                raise ValueError(f"camera {camera_id} RGB must be HWC float32 in [0,1]")
            if capture.depth is None or capture.depth.dtype != np.float32 or capture.depth.shape != (
                self.config.height, self.config.width,
            ) or not np.isfinite(capture.depth).all() or np.any(capture.depth < 0):
                raise ValueError(f"camera {camera_id} depth must be finite H×W optical-Z metres")
            mask = capture.segmentation.mask
            if mask.dtype != np.uint32 or mask.shape != (self.config.height, self.config.width):
                raise ValueError(f"camera {camera_id} Entity mask must be H×W uint32")
        metadata = camera_observation_boundary_from_captures(captures)
        if metadata.state_boundary_id != boundary.boundary_id:
            raise ValueError("camera capture belongs to another typed state publication")
        self._last_key = key
        self._last_control_step = boundary.control_step
        self._last_boundary = boundary
        self._last_capture_values = captures
        self._last_boundary_value = metadata
        self._last_leaves = {
            "rgb": OrderedDict((camera_id, capture.rgb) for camera_id, capture in zip(CAMERA_IDS, captures)),
            "depth": OrderedDict((camera_id, capture.depth) for camera_id, capture in zip(CAMERA_IDS, captures)),
            "entity_mask": OrderedDict((camera_id, capture.segmentation.mask) for camera_id, capture in zip(CAMERA_IDS, captures)),
        }
        return self._result()

    def _result(self):
        if self._last_leaves is None or self._last_boundary_value is None:
            raise RuntimeError("camera consumer has no captured boundary")
        return (
            OrderedDict((group, OrderedDict(values.items())) for group, values in self._last_leaves.items()),
            self._last_boundary_value,
        )

    def close(self):
        """Close each renderer once, attempting every close even after an error."""

        if self._closed:
            return
        self._closed = True
        sessions, self._sessions = tuple(self._sessions), []
        first_error = None
        for session in sessions:
            try:
                session.close()
            except BaseException as error:
                if first_error is None:
                    first_error = error
        if first_error is not None:
            raise first_error


__all__ = ["CameraObservationProvider", "DynamicCameraObservationConsumerV1"]


class CameraObservationProvider:
    """Render RGB/depth observations for configured cameras using an existing visualizer."""

    def __init__(
        self,
        *,
        render_source,
        config: RenderConfig,
        camera_sensors: tuple[CameraSensor, ...],
    ) -> None:
        if render_source is None:
            raise ValueError("CameraObservationProvider requires a render_source")
        if not camera_sensors:
            raise ValueError("CameraObservationProvider requires at least one camera")
        self.config = config
        self.camera_sensors = tuple(camera_sensors)
        first_camera = self.camera_sensors[0].spec
        self._visualizer = render_source.build_visualizer(
            backend=config.backend,
            width=first_camera.width,
            height=first_camera.height,
        )

    def reset(self) -> None:
        return None

    def capture(self, snapshot: RuntimeSnapshot) -> SensorObservation:
        rgb: OrderedDict[str, np.ndarray] = OrderedDict()
        depth: OrderedDict[str, np.ndarray] = OrderedDict()
        metadata = OrderedDict()
        for sensor in self.camera_sensors:
            camera_metadata = sensor.metadata(snapshot)
            metadata[sensor.name] = camera_metadata
            self._visualizer.write_camera_pose(
                {
                    "pos": camera_metadata.pose.position,
                    "look_at": camera_metadata.pose.look_at,
                    "up": camera_metadata.pose.up,
                }
            )
            frame = self._visualizer.read_frame(
                width=sensor.spec.width,
                height=sensor.spec.height,
                synchronized=True,
            )
            if sensor.spec.rgb:
                array = np.asarray(frame, dtype=np.float32)
                expected_shape = (sensor.spec.height, sensor.spec.width, 3)
                if array.shape != expected_shape:
                    raise ValueError(
                        f"camera {sensor.name} RGB shape {array.shape} != {expected_shape}"
                    )
                rgb[sensor.name] = normalize_rgb(array, sensor.spec)
            if sensor.spec.depth:
                depth_frame = self._visualizer.read_depth()
                depth_array = np.asarray(depth_frame, dtype=np.float32)
                expected_depth_shape = (sensor.spec.height, sensor.spec.width)
                if depth_array.shape != expected_depth_shape:
                    raise ValueError(
                        f"camera {sensor.name} depth shape {depth_array.shape} "
                        f"!= {expected_depth_shape}"
                    )
                depth[sensor.name] = np.ascontiguousarray(depth_array)
        return SensorObservation(rgb=rgb, depth=depth, camera_metadata=metadata)

    def close(self) -> None:
        close = getattr(self._visualizer, "close", None)
        if close is not None:
            close()
