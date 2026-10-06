"""Camera RGB/depth acquisition for TaskEnv observations."""

from __future__ import annotations

from collections import OrderedDict

import numpy as np

from ..environment import RenderConfig, RuntimeSnapshot, SensorObservation
from .camera import CameraSensor
from .canonical_camera.images import normalize_rgb


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
