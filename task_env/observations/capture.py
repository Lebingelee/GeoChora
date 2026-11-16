"""Camera RGB/depth acquisition for TaskEnv observations."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import replace
from uuid import uuid4

import numpy as np

from ..environment import RenderConfig, RuntimeSnapshot, SensorObservation
from .camera import CameraSensor
from .canonical_camera.images import normalize_rgb
from .canonical_camera.images import CanonicalCameraObservation


class BorrowedTaskCameraSessionV1:
    """Use a task camera leased from a RuntimeSession without closing its owner."""

    def __init__(self, owner, camera, state):
        self._owner, self._camera = owner, camera
        owner.bind_task_camera(camera, state)

    def capture(self, state):
        if self._owner is None:
            raise RuntimeError('task camera lease is closed')
        result = self._owner.capture_task_camera(self._camera, state)
        completion = getattr(self._owner, 'task_camera_completion', None)
        self.completion_evidence = completion(state) if callable(completion) else None
        return result

    def close(self):
        self._owner = None


class TaskRgbObservationConsumerV1:
    """One owned RGB consumer of successive typed boundaries in one episode."""

    def __init__(self, camera, renderer, session_factory, *, color_space):
        from .canonical_camera import CameraGeometry
        if type(camera) is not CameraGeometry:
            raise TypeError('task RGB requires CameraGeometry')
        camera.validate()
        if not camera.rgb or camera.depth or camera.rgb_layout != 'HWC' or camera.rgb_dtype != 'float32':
            raise ValueError('task RGB requires HWC float32 RGB without depth')
        self.camera, self.renderer = camera, renderer
        self._factory, self._session = session_factory, None
        self._closed, self._last_boundary = False, None
        self.generation = uuid4().hex
        self.color_space = color_space

    def capture(self, state):
        from ..artifacts.state import CanonicalStateViewV1
        if self._closed:
            raise RuntimeError('task RGB consumer is closed')
        if not isinstance(state, CanonicalStateViewV1):
            raise TypeError('task RGB requires a canonical state')
        state.validate()
        boundary = state.boundary
        if self._last_boundary is None:
            if boundary.control_step != 0:
                raise ValueError('task RGB must start at the reset boundary')
            phase = 'reset_initial'
        else:
            previous = self._last_boundary
            if (boundary.episode_id != previous.episode_id
                    or boundary.reset_sample_id != previous.reset_sample_id
                    or boundary.scene_instance_id != previous.scene_instance_id
                    or boundary.provider_materialization_id != previous.provider_materialization_id
                    or boundary.control_step != previous.control_step + 1):
                raise ValueError('task RGB requires the next boundary of the same episode')
            phase = 'post_control_step'
        if self._session is None:
            self._session = self._factory(state)
        result = self._session.capture(state)
        if not isinstance(result, CanonicalCameraObservation) or result.capture_identity is None:
            raise ValueError('task RGB requires an actual completed camera capture')
        identity = result.capture_identity
        identity.validate()
        if (result.metadata.camera != self.camera or identity.camera_id != self.camera.camera_id
                or identity.camera_geometry_identity_hash != self.camera.identity_hash
                or identity.task_artifact_hash != self.camera.task_artifact_hash
                or identity.state_boundary != boundary or identity.sample_clock != state.sample_clock
                or identity.renderer_selection != self.renderer or identity.modalities != ('rgb',)
                or identity.capture_phase != 'post_control_step'):
            raise ValueError('task RGB capture does not match its requested camera, renderer, or boundary')
        # The underlying renderer has completed at this boundary.  The phase
        # is derived from the consumer lifecycle, not from the camera geometry.
        identity = replace(identity, capture_phase=phase)
        identity.validate()
        self._last_boundary = boundary
        return np.array(result.rgb, copy=True), {
            'schema_version': 'task-rgb-observation-v1',
            'capture_identity': identity.to_mapping(),
            'capture_identity_sha256': identity.identity_hash,
            'camera': self.camera.to_mapping(),
            'resolved_camera': result.metadata.to_mapping(),
            'renderer_generation': self.generation,
            'completion': 'synchronous capture completed before observation publication',
            'completion_evidence': getattr(self._session, 'completion_evidence', None),
            'ownership': 'owned host copy',
            'color_space': self.color_space,
        }

    def close(self):
        if not self._closed:
            self._closed = True
            session, self._session = self._session, None
            if session is not None:
                session.close()


__all__ = ["CameraObservationProvider"]


class CameraObservationProvider:
    """Render RGB/depth observations for configured cameras using an existing visualizer."""

    def __init__(
        self,
        *,
        render_source,
        config: RenderConfig,
        camera_sensors: tuple[CameraSensor, ...],
        task_rgb_camera_name: str | None = None,
    ) -> None:
        if render_source is None:
            raise ValueError("CameraObservationProvider requires a render_source")
        if not camera_sensors:
            raise ValueError("CameraObservationProvider requires at least one camera")
        self.config = config
        self.camera_sensors = tuple(camera_sensors)
        self.task_rgb_camera_name = task_rgb_camera_name
        self._task_camera_bound = False
        if task_rgb_camera_name is not None:
            if len(self.camera_sensors) != 1 or self.camera_sensors[0].name != task_rgb_camera_name:
                raise ValueError("component task RGB requires its sole configured camera sensor")
            spec = self.camera_sensors[0].spec
            if not spec.rgb or spec.depth or spec.rgb_layout != "HWC" or spec.rgb_dtype != "float32":
                raise ValueError("component task RGB requires HWC float32 RGB without depth")
            if (
                not all(np.isfinite(float(value)) for value in (spec.fov_y, spec.near, spec.far))
                or not 0.0 < float(spec.fov_y) < np.pi
                or not 0.0 < float(spec.near) < float(spec.far)
            ):
                raise ValueError("component task RGB requires finite 0 < fov_y < pi and 0 < near < far")
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
            if sensor.name == self.task_rgb_camera_name:
                camera_metadata = replace(
                    camera_metadata,
                    renderer_readback=self._bind_and_read_task_camera(sensor, camera_metadata),
                )
                frame = self._visualizer.read_task_camera_frame(synchronized=True)
            else:
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
            metadata[sensor.name] = camera_metadata
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

    def _bind_and_read_task_camera(self, sensor, requested):
        """Bind requested component optics, then verify the renderer's own readback."""
        from math import degrees
        from ..environment import CameraRendererReadbackV1

        visualizer = self._visualizer
        bind = getattr(visualizer, "bind_task_camera", None)
        update = getattr(visualizer, "update_task_camera", None)
        read = getattr(visualizer, "read_task_camera", None)
        if not callable(bind) or not callable(update) or not callable(read):
            raise RuntimeError("component task RGB renderer lacks bind/update/read camera capability")
        spec = sensor.spec
        pose = requested.pose
        request = {
            "camera_id": sensor.name,
            "position": np.asarray(pose.position, dtype=np.float64),
            "look_at": np.asarray(pose.look_at, dtype=np.float64),
            "up": np.asarray(pose.up, dtype=np.float64),
            "fov_degrees": degrees(float(spec.fov_y)),
            "near": float(spec.near),
            "far": float(spec.far),
            "width": int(spec.width),
            "height": int(spec.height),
        }
        bind_result = (update if self._task_camera_bound else bind)(**request)
        self._task_camera_bound = True
        actual = read()
        if not isinstance(actual, dict):
            raise TypeError("renderer task camera readback must be a mapping")
        required = {
            "camera_id", "binding_id", "position", "forward", "up", "fov_degrees",
            "near", "far", "width", "height",
        }
        if not required <= set(actual):
            raise ValueError("renderer task camera readback is missing optical fields")
        if not isinstance(bind_result, dict) or bind_result.get("binding_id") != actual["binding_id"]:
            raise ValueError("renderer camera bind result differs from its independent readback")
        expected_forward = request["look_at"] - request["position"]
        expected_forward /= np.linalg.norm(expected_forward)
        expected_up = request["up"] / np.linalg.norm(request["up"])
        position = np.asarray(actual["position"], dtype=np.float64)
        forward = np.asarray(actual["forward"], dtype=np.float64)
        up = np.asarray(actual["up"], dtype=np.float64)
        same = (
            actual["camera_id"] == request["camera_id"]
            and type(actual["binding_id"]) is str and bool(actual["binding_id"])
            and actual["width"] == request["width"]
            and actual["height"] == request["height"]
            and np.isfinite(position).all() and np.isfinite(forward).all() and np.isfinite(up).all()
            and np.linalg.norm(position - request["position"]) <= 3.0e-5
            and np.linalg.norm(forward - expected_forward) <= 2.0e-4
            and np.linalg.norm(up - expected_up) <= 2.0e-4
            and abs(float(actual["fov_degrees"]) - request["fov_degrees"]) <= 2.0e-4
            and abs(float(actual["near"]) - request["near"]) <= max(2.0e-7, abs(request["near"]) * 2.0e-6)
            and abs(float(actual["far"]) - request["far"]) <= max(2.0e-6, abs(request["far"]) * 2.0e-6)
        )
        if not same:
            raise ValueError("renderer task camera readback differs from requested identity, pose, optics, or extent")
        return CameraRendererReadbackV1(
            camera_id=actual["camera_id"], binding_id=actual["binding_id"],
            position=tuple(actual["position"]), forward=tuple(actual["forward"]),
            up=tuple(actual["up"]), fov_degrees=actual["fov_degrees"],
            near=actual["near"], far=actual["far"], width=actual["width"],
            height=actual["height"],
        )

    def project_task_camera(self, point):
        """Expose the renderer's public task-camera geometry projection for audits."""
        if self.task_rgb_camera_name is None or not self._task_camera_bound:
            raise RuntimeError("component task camera has no completed native binding")
        project = getattr(self._visualizer, "project_task_camera", None)
        if not callable(project):
            raise RuntimeError("component task RGB renderer lacks camera projection readback")
        return project(point)

    def close(self) -> None:
        close = getattr(self._visualizer, "close", None)
        if close is not None:
            close()
