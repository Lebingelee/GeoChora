"""UI rendering contract, deliberately separate from observation sensors."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class TaskRgbCapability:
    """One registered task-camera route; discovery does not load an SDK."""
    renderer: str
    backend: str
    profile: str
    device: str | None
    color_space: str
    ownership: str
    physics_profile: str | None = None
    shared_framebuffer: bool = False


TASK_RGB_CAPABILITIES = {
    ('mujoco', 'cpu', 'mujoco'): TaskRgbCapability(
        'mujoco', 'native-opengl', 'v211_mujoco_cpu_native_rgb_v1', None,
        'GL_LINEAR framebuffer RGB; primaries uncalibrated', 'independent visual model',
        'mujoco-scene-v3-runtime-v1'),
    ('geophys', 'cpu', 'mujoco'): TaskRgbCapability(
        'mujoco', 'native-opengl', 'v211_geophys_cpu_mujoco_native_rgb_v1', None,
        'GL_LINEAR framebuffer RGB; primaries uncalibrated', 'independent visual model',
        'geophys-scene-v3-runtime-v1'),
    ('geophys', 'cpu', 'geophys'): TaskRgbCapability(
        'geophys', 'rasterizer', 'v211_geophys_cpu_task_rgb_v1', 'cpu',
        'sRGB transfer after ACES; primaries uncalibrated', 'borrowed Runtime camera',
        shared_framebuffer=True),
    ('isaacsim', 'cuda', 'isaacsim'): TaskRgbCapability(
        'isaacsim', 'rtx', 'v211_isaac_rtx_task_rgb_v1', 'cuda:0',
        'sRGB transfer after RTX tone mapping; primaries uncalibrated', 'borrowed Runtime camera'),
}
TASK_RGB_PAIRINGS = frozenset(TASK_RGB_CAPABILITIES)


@dataclass(frozen=True)
class ObserverCapability:
    """An admitted observer route and the actual native camera capability it uses."""
    source_family: str
    provider: str
    physics_backend: str
    modes: frozenset[str]
    controller_kinds: frozenset[str] | None
    reset_selection: bool | None
    camera: TaskRgbCapability


def _observer_capability(family, provider, backend, modes, kinds=None, reset_selection=None):
    return ObserverCapability(family, provider, backend, frozenset(modes),
        None if kinds is None else frozenset(kinds), reset_selection,
        TASK_RGB_CAPABILITIES[(provider, backend, provider)])


OBSERVER_CAPABILITIES = {
    ('inline-articulation-v1', 'geophys', 'cpu'): _observer_capability(
        'inline-articulation-v1', 'geophys', 'cpu', ('human', 'rgb_array'), ('joint-effort',)),
    ('inline-articulation-v1', 'mujoco', 'cpu'): _observer_capability(
        'inline-articulation-v1', 'mujoco', 'cpu', ('human',), ('joint-effort',)),
    ('panda-articulation-v1', 'geophys', 'cpu'): _observer_capability(
        'panda-articulation-v1', 'geophys', 'cpu', ('human', 'rgb_array'), ('joint',), False),
    ('panda-articulation-v1', 'mujoco', 'cpu'): _observer_capability(
        'panda-articulation-v1', 'mujoco', 'cpu', ('human', 'rgb_array'), reset_selection=True),
    ('panda-articulation-v1', 'isaacsim', 'cuda'): _observer_capability(
        'panda-articulation-v1', 'isaacsim', 'cuda', ('human', 'rgb_array')),
}


def task_rgb_capability(provider, backend, renderer):
    try:
        return TASK_RGB_CAPABILITIES[(provider, backend, renderer)]
    except KeyError as error:
        raise ValueError('unsupported fixed task RGB renderer and physics pairing') from error


def validate_camera_declarations(*, render_mode=None, observer_camera=None, task_camera=None,
                                 task_rgb_camera=None, task_renderer=None):
    """Reject incompatible declarations before source or native preparation."""
    from ...environment.config import CameraSpec
    from ...observations.canonical_camera import CameraGeometry
    if (task_rgb_camera is None) != (task_renderer is None):
        raise ValueError('task RGB camera and fixed renderer must be declared together')
    if task_camera is not None and task_rgb_camera is not None:
        raise ValueError('declare either a task RGB camera or a legacy task camera binding')
    for camera in (observer_camera, task_camera, task_rgb_camera):
        if camera is None:
            continue
        if type(camera) is CameraGeometry:
            camera.validate()
        elif type(camera) is CameraSpec:
            if (camera.frame != 'world' or not np.isfinite((*camera.position, *camera.quaternion_wxyz,
                    camera.fov_y, camera.near, camera.far)).all()
                    or np.linalg.norm(camera.quaternion_wxyz) < 1e-12
                    or not 0 < camera.fov_y < np.pi):
                raise ValueError('task RGB requires a finite world CameraSpec with nonzero quaternion')
        else:
            raise TypeError('camera must be CameraSpec or linked CameraGeometry')
        if not camera.rgb or camera.depth or camera.rgb_layout != 'HWC' or camera.rgb_dtype != 'float32':
            raise ValueError('camera output requires HWC float32 RGB without depth')
    if task_camera is not None and getattr(task_camera, 'parent_frame', 'world') != 'world':
        raise ValueError('task camera supports world mounts only')
    if task_camera is not None and render_mode is None:
        raise ValueError('task camera requires an observer-enabled scene')
    if render_mode is None and observer_camera is not None:
        raise ValueError('observer camera requires a configured render mode')
    if render_mode is not None:
        normalize_render_mode(render_mode)
        if observer_camera is None:
            raise ValueError('rendering requires an explicit observer camera')
    if observer_camera is not None:
        identity = lambda camera: getattr(camera, 'camera_id', getattr(camera, 'name', None))
        for camera in (task_camera, task_rgb_camera):
            if camera is not None and identity(camera) == identity(observer_camera):
                raise ValueError('task and observer cameras require distinct identities')
        if (task_rgb_camera is not None and task_renderer == 'geophys'
                and (task_rgb_camera.width, task_rgb_camera.height) != (observer_camera.width, observer_camera.height)):
            raise ValueError('GeoPhys task and observer cameras require the same framebuffer extent')


class RenderMode(str, Enum):
    """Stable modes accepted by the future :meth:`BaseTaskEnv.render` API."""

    HUMAN = "human"
    RGB_ARRAY = "rgb_array"


class RenderBackendName(str, Enum):
    """Backend names owned by the TaskEnv render boundary."""

    RAYTRACER = "raytracer"
    RASTERIZER = "rasterizer"
    FLORA = "flora"


@dataclass(frozen=True)
class ObserverRenderRequestV1:
    """Source-bound observer request, assessed before native materialization."""
    camera: object
    mode: str
    provider: str
    backend: str

    def validate(self, *, artifact, physics_provider, physics_backend):
        from ...observations.canonical_camera import CameraGeometry
        if type(self.camera) is not CameraGeometry:
            raise TypeError('observer request requires CameraGeometry')
        self.camera.validate()
        if (self.camera.task_artifact_hash != artifact.identity_hash or
                not self.camera.rgb or self.camera.depth or
                self.camera.rgb_layout != 'HWC' or self.camera.rgb_dtype != 'float32'):
            raise ValueError('observer request does not match its artifact and RGB contract')
        if (self.provider, self.backend, physics_provider, physics_backend) not in {
                ('isaacsim', 'rtx', 'isaacsim', 'cuda'),
                ('geophys', 'rasterizer', 'geophys', 'cpu')}:
            raise ValueError('unsupported observer request and physics route')
        normalize_render_mode(self.mode)


@dataclass(frozen=True)
class RenderBackendCapabilities:
    """Stable capability description exposed before a renderer is created."""

    supports_human: bool = True
    supports_rgb_array: bool = True
    supports_parallel: bool = True
    # ``supports_asset_instancing`` is retained as a compatibility field for
    # existing callers.  New code should use the explicit capabilities below.
    supports_asset_instancing: bool = False
    supports_shared_asset_table: bool = False
    supports_gpu_geometry_instancing: bool = False
    supports_batch_transform_update: bool = False
    transform_transport: str = "unknown"
    output_transport: str = "geophys_framebuffer"


class RenderUnavailableError(RuntimeError):
    """Raised when an environment has no configured UI rendering backend."""


class RenderBackendBuildError(RuntimeError):
    """Raised when a selected backend cannot build its visualizer."""


def normalize_render_mode(mode: RenderMode | str) -> RenderMode:
    """Validate one public UI render mode without accepting sensor aliases."""

    try:
        return RenderMode(mode)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in RenderMode)
        raise ValueError(f"unsupported UI render mode {mode!r}; expected one of: {allowed}") from exc


class UiRenderProvider(Protocol):
    """TaskEnv UI backend; it is separate from camera observation capture."""

    def render(self, *, mode: RenderMode, snapshot: object) -> np.ndarray | None:
        """Present a frame or return an RGB frame according to ``mode``."""

    def close(self) -> None:
        """Release window and visualizer resources; the operation is idempotent."""


__all__ = [
    "RenderMode",
    "RenderBackendName",
    "RenderBackendCapabilities",
    "RenderUnavailableError",
    "RenderBackendBuildError",
    "UiRenderProvider",
    "normalize_render_mode",
]
