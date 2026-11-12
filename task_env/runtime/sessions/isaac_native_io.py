"""Narrow Isaac Sim public-API implementation of NativeRuntimeIOV1.

This module is imported only by the admitted runtime materialization route.
It owns Isaac's process App and one stage/view lease; Core's shared USD
RuntimeSession continues to own reset, control, clock projection and faults.
"""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
import copy
from importlib import metadata as importlib_metadata
import hashlib
import math
import os
from pathlib import Path
import sys
from threading import RLock
from typing import Any

from ...artifacts import ExecutionSpecV1, PoseWorld, TaskArtifactV1
from ...artifacts.execution import ResetSample
from ...assembly.source import UsdSnapshotLeaseV1
from .free_joint_state import PublicRigidBodyReadbackV1
from .native_io import (
    NativeAdvanceReceiptV1, NativePositionWriteAckV1,
    NativeResetWriteReceiptV1, NativeRuntimeIOMetadataV1,
    NativeRuntimeReadbackV1, _is_sha256_identity,
)
from .source import UsdRuntimeSourceV1


_APP_LOCK = RLock()
_PROCESS_APP_OWNER: "IsaacSimAppOwnerV1 | None" = None

_ISAAC_62_OBSERVER_OCIO_SHA256 = '4a34410a6a94c27eb057c155473abacd66bee79f41c7b9a0c649d44dead6c914'
_ISAAC_62_OBSERVER_COLOR_SETTINGS = {
    '/rtx/post/tonemap/op': 6,
    '/rtx/post/tonemap/colorMode': 0,
    '/rtx/post/tonemap/enableSrgbToGamma': True,
    '/rtx/post/tonemap/ocio/display': None,
    '/rtx/post/tonemap/ocio/view': None,
    '/rtx/post/colorgrad/enabled': False,
    '/rtx/post/colorcorr/enabled': False,
}


def _validate_isaac_observer_color_settings(values, ocio_sha256):
    """Admit only the measured Isaac 6.2 display-transfer configuration."""
    if any(type(values.get(key)) is not type(expected) or values.get(key) != expected
           for key, expected in _ISAAC_62_OBSERVER_COLOR_SETTINGS.items()):
        raise RuntimeError(f'Isaac observer color settings are not qualified: {values!r}')
    if ocio_sha256 != _ISAAC_62_OBSERVER_OCIO_SHA256:
        raise RuntimeError('Isaac observer OCIO configuration is not qualified')
    return {'settings': dict(values), 'ocio_sha256': ocio_sha256,
            'transfer': 'sRGB after RTX tone mapping; primaries and source assets uncalibrated'}


def _read_isaac_observer_color_settings():
    import carb
    settings = carb.settings.get_settings()
    values = {key: settings.get(key) for key in _ISAAC_62_OBSERVER_COLOR_SETTINGS}
    path = settings.get('/rtx/post/tonemap/ocio/cfgFilePath')
    if not isinstance(path, str) or not path:
        raise RuntimeError('Isaac observer OCIO configuration path is unavailable')
    try:
        digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError as error:
        raise RuntimeError('Isaac observer OCIO configuration cannot be read') from error
    return _validate_isaac_observer_color_settings(values, digest)


def configure_isaac_task_rgb_color_defaults():
    """Fill absent App-local RTX settings with the measured 6.2 contract.

    Existing values are never overwritten.  The SDK's own OCIO file must
    match the previously measured digest before it can be selected.
    """
    import carb
    import isaacsim
    settings = carb.settings.get_settings()
    applied = {}
    initial = {key: settings.get(key) for key in _ISAAC_62_OBSERVER_COLOR_SETTINGS}
    for key, expected in _ISAAC_62_OBSERVER_COLOR_SETTINGS.items():
        actual = initial[key]
        if actual is not None and (type(actual) is not type(expected) or actual != expected):
            raise RuntimeError(f'Isaac task RGB rejects incompatible App setting {key}: {actual!r}')
    key = '/rtx/post/tonemap/ocio/cfgFilePath'
    configured_path = settings.get(key)
    if configured_path:
        if (not isinstance(configured_path, str) or not Path(configured_path).is_file()
                or hashlib.sha256(Path(configured_path).read_bytes()).hexdigest() != _ISAAC_62_OBSERVER_OCIO_SHA256):
            raise RuntimeError('Isaac App task RGB OCIO differs from the qualified configuration')
    else:
        package_file = getattr(isaacsim, '__file__', None)
        if not package_file:
            raise RuntimeError('Isaac SDK root is unavailable for task RGB OCIO')
        path = Path(package_file).resolve().parent / 'kit/rendering-data/runtime/ov-0.1.0.ocio'
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != _ISAAC_62_OBSERVER_OCIO_SHA256:
            raise RuntimeError('Isaac SDK task RGB OCIO does not match the qualified configuration')
        settings.set(key, str(path))
        applied[key] = str(path)
    for key, expected in _ISAAC_62_OBSERVER_COLOR_SETTINGS.items():
        if initial[key] is None and expected is not None:
            settings.set(key, expected)
            applied[key] = expected
    return {'applied_absent_settings': applied, 'qualified': _read_isaac_observer_color_settings()}


DEFAULT_ISAAC_APP_LAUNCH_PROFILE_V1 = "isaac-headless-default-v1"
F06_ISAAC_APP_LAUNCH_PROFILE_V1 = "f06-headless-no-render-v1"
V211_ISAAC_RENDER_APP_LAUNCH_PROFILE_V1 = "v211-headless-camera-v1"
_ISAAC_APP_LAUNCH_PROFILE_OVERRIDES = {
    DEFAULT_ISAAC_APP_LAUNCH_PROFILE_V1: {},
    F06_ISAAC_APP_LAUNCH_PROFILE_V1: {
        "renderer": "MinimalRendering",
        "minimal_shading_mode": 4,
        "disable_viewport_updates": True,
    },
    V211_ISAAC_RENDER_APP_LAUNCH_PROFILE_V1: {
        "headless": True,
        "enable_cameras": True,
        "multi_gpu": False,
        "max_gpu_count": 1,
    },
}


def _validate_isaac_task_thread_count(actual: int) -> int:
    if type(actual) is not int or not 1 <= actual <= 4:
        raise RuntimeError(f"Isaac task thread pool is outside the F04 1-4 thread bound: {actual}")
    return actual


def _isaac_app_launch_profile_id(*, f06_pickcube: bool,
                                 observer_render_request,
                                 task_render_requested: bool) -> str | None:
    if type(f06_pickcube) is not bool or type(task_render_requested) is not bool:
        raise TypeError('Isaac launch-profile selectors must be exact booleans')
    if observer_render_request is not None or task_render_requested:
        return V211_ISAAC_RENDER_APP_LAUNCH_PROFILE_V1
    if f06_pickcube:
        return F06_ISAAC_APP_LAUNCH_PROFILE_V1
    return None


def _numeric_value_matches(actual, expected, *, abs_tol: float) -> bool:
    """Compare public USD numeric readback without requiring float64 equality."""
    return math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=abs_tol)


def _numeric_tuple_matches(actual, expected, *, abs_tol: float) -> bool:
    """Compare public USD numeric tuples without rejecting float32 readback."""
    if len(actual) != len(expected):
        return False
    return all(
        _numeric_value_matches(value, target, abs_tol=abs_tol)
        for value, target in zip(actual, expected, strict=True)
    )


def _task_render_clock_mapping(*, provider_time_s, episode_time_s):
    """Record the provider/episode epoch relation without mutating Kit time."""
    provider_time = float(provider_time_s)
    episode_time = float(episode_time_s)
    if not math.isfinite(provider_time) or not math.isfinite(episode_time):
        raise ValueError('task render clock mapping requires finite clock values')
    return {
        'schema_version': 'isaac-task-render-clock-observation-v1',
        'clock_mapping': 'episode-local state time + measured provider epoch offset = provider-global time',
        'episode_time_s': episode_time,
        'provider_time_s': provider_time,
        'provider_epoch_offset_s': provider_time - episode_time,
        'timeline_mutated': False,
        'physics_step_requested': False,
    }




def _g05_scene_handoff_payload(
    *, scene_path: str, applied_schemas, authored_values: Mapping[str, object],
    configured_dt: float, meters_per_unit: float,
) -> dict[str, object]:
    """Validate and capture the narrow PhysicsScene semantics G05 can hand off.

    This intentionally accepts only an explicit gravity vector and an
    optional PhysX rate equal to the TaskArtifact timebase. Unknown authored
    properties or APIs may carry solver semantics that cannot be reconstructed
    by the shared SimulationManager owner, so the route fails closed.
    """
    schemas = {str(value) for value in applied_schemas}
    unsupported_schemas = sorted(schemas - {"PhysxSceneAPI"})
    if unsupported_schemas:
        raise ValueError(
            "G05 PhysicsScene cannot be transferred with unsupported APIs: "
            f"{unsupported_schemas!r}"
        )
    allowed_properties = {
        "physics:gravityDirection",
        "physics:gravityMagnitude",
        "physx:timeStepsPerSecond",
    }
    unsupported_properties = sorted(set(authored_values) - allowed_properties)
    if unsupported_properties:
        raise ValueError(
            "G05 PhysicsScene cannot be transferred with unsupported authored properties: "
            f"{unsupported_properties!r}"
        )
    if "physics:gravityDirection" not in authored_values or "physics:gravityMagnitude" not in authored_values:
        raise ValueError("G05 PhysicsScene handoff requires explicit authored gravity direction and magnitude")
    if not math.isfinite(float(meters_per_unit)) or float(meters_per_unit) <= 0.0:
        raise ValueError("G05 PhysicsScene handoff requires a finite positive meters-per-unit scale")
    direction = tuple(float(value) for value in authored_values["physics:gravityDirection"])
    magnitude = float(authored_values["physics:gravityMagnitude"])
    if len(direction) != 3 or any(not math.isfinite(value) for value in direction):
        raise ValueError("G05 PhysicsScene gravity direction must be a finite 3-vector")
    direction_length = math.sqrt(sum(value * value for value in direction))
    if direction_length <= 0.0 or not math.isfinite(magnitude) or magnitude < 0.0:
        raise ValueError("G05 PhysicsScene gravity magnitude/direction is invalid")
    normalized_direction = tuple(value / direction_length for value in direction)
    gravity_world = tuple(
        value * magnitude / float(meters_per_unit) for value in normalized_direction
    )
    expected_steps_per_second = int(round(1.0 / float(configured_dt)))
    authored_steps_per_second = authored_values.get("physx:timeStepsPerSecond")
    if authored_steps_per_second is not None:
        if type(authored_steps_per_second) not in (int, float):
            raise ValueError("G05 PhysicsScene authored PhysX rate must be numeric")
        if int(authored_steps_per_second) != expected_steps_per_second:
            raise ValueError(
                "G05 PhysicsScene authored PhysX rate conflicts with the TaskArtifact timebase: "
                f"{authored_steps_per_second!r} != {expected_steps_per_second}"
            )
    return {
        "schema_version": "g05-scene-owner-handoff-v1",
        "source_scene_path": str(scene_path),
        "source_applied_schemas": sorted(schemas),
        "source_authored_values": dict(authored_values),
        "gravity_direction_normalized": list(normalized_direction),
        "gravity_magnitude_stage_units": magnitude,
        "meters_per_unit": float(meters_per_unit),
        "gravity_world_m_s2": list(gravity_world),
        "physics_dt_s": float(configured_dt),
        "steps_per_second": expected_steps_per_second,
        "source_bytes_modified": False,
    }




class IsaacSimAppOwnerV1:
    """One headless Isaac App per worker process, separate from Env sessions."""

    def __init__(self, *, launch_profile_id: str = DEFAULT_ISAAC_APP_LAUNCH_PROFILE_V1) -> None:
        if launch_profile_id not in _ISAAC_APP_LAUNCH_PROFILE_OVERRIDES:
            raise ValueError(f"unsupported Isaac App launch profile: {launch_profile_id!r}")
        self.launch_profile_id = launch_profile_id
        self._app = None
        self._closed = False
        self._process_lifetime_holds = 0
        self._close_requested = False
        self._runtime_invalidation_reason = None
        self.start_attempts = 0
        self.close_attempts = 0
        self._close_attempted = False
        self._close_completed = False
        self._close_failure: dict[str, str] | None = None
        self._framework_unload_attempted = False
        self._framework_unload_completed = False
        self._framework_unload_failure: dict[str, str] | None = None
        self._atexit_close_unregister_attempted = False
        self._atexit_close_unregister_completed = False
        self._atexit_close_unregister_failure: dict[str, str] | None = None
        self.sdk_identity = None
        self.sdk_runtime_version_raw = None

    @property
    def app(self):
        return self._app

    def launch_profile_receipt(self) -> dict[str, object]:
        config = {
            "headless": True,
            "enable_cameras": False,
            "limit_cpu_threads": 4,
            "fast_shutdown": False,
            **_ISAAC_APP_LAUNCH_PROFILE_OVERRIDES[self.launch_profile_id],
        }
        return {"profile_id": self.launch_profile_id, "simulation_app_config": config}

    def open(self, *, f06_compatibility=False):
        if self._closed or self._close_attempted:
            raise RuntimeError("Isaac App owner cannot reopen after close")
        if self._runtime_invalidation_reason is not None:
            raise RuntimeError('Isaac App runtime is invalid; a new worker is required: '
                               + self._runtime_invalidation_reason)
        if self._app is not None:
            is_running = getattr(self._app, 'is_running', None)
            if callable(is_running) and not is_running():
                raise RuntimeError('Isaac App stopped after window closure; a new worker is required')
        if self._app is not None and f06_compatibility and self.sdk_identity is None:
            raise RuntimeError('already-open Isaac App lacks F06 version verification')
        if self._app is None:
            try:
                installed = importlib_metadata.version("isaacsim")
            except importlib_metadata.PackageNotFoundError:
                installed = None
            if f06_compatibility:
                from .provenance import resolve_isaac_sdk_identity
                root = os.environ.get('GEOCHORA_SELECTED_ISAAC_ROOT') or os.environ.get('ISAAC_PATH')
                self.sdk_identity = resolve_isaac_sdk_identity(pip_version=installed, sdk_root=root)
                expected = os.environ.get('GEOCHORA_SELECTED_ISAAC_VERSION')
                if expected is not None and expected != self.sdk_identity['normalized_version']:
                    raise RuntimeError('Isaac App version differs from selected preflight version')
            elif installed != "6.2.0.0":
                raise RuntimeError(f"F04 requires the installed isaacsim 6.2.0.0 distribution, found {installed}")
            self.start_attempts += 1
            # Isaac Sim 6.2 exposes the supported standalone entry point from
            # the package root.  Keep the extension-module fallback only for
            # the older compatible shim used by existing boundary fixtures;
            # the production package takes the package-root branch.
            try:
                from isaacsim import SimulationApp
            except ImportError as package_root_error:
                try:
                    from isaacsim.simulation_app import SimulationApp
                except ImportError:
                    raise package_root_error

            # Kit's default fast shutdown can terminate Python before the
            # worker writes its producer-owned completion receipt.
            self._app = SimulationApp(self.launch_profile_receipt()["simulation_app_config"])
            import carb

            try:
                if f06_compatibility:
                    from isaacsim.core.version import get_version
                    expected_origin = os.environ.get('GEOCHORA_SELECTED_ISAAC_ORIGIN')
                    actual_origin = getattr(sys.modules.get('isaacsim'), '__file__', None)
                    if expected_origin and (actual_origin is None or
                            Path(actual_origin).resolve() != Path(expected_origin).resolve()):
                        raise RuntimeError('Isaac runtime module source conflicts with selected preflight')
                    expected_root = os.environ.get('GEOCHORA_SELECTED_ISAAC_ROOT')
                    actual_root = os.environ.get('ISAAC_PATH')
                    if (expected_root and actual_root
                            and Path(expected_root).resolve() != Path(actual_root).resolve()):
                        raise RuntimeError('Isaac runtime SDK root conflicts with selected preflight')
                    runtime_version = tuple(str(value) for value in get_version())
                    if len(runtime_version) != 8 or not runtime_version[0]:
                        raise RuntimeError('Isaac runtime did not publish its SDK version')
                    runtime_identity = resolve_isaac_sdk_identity(pip_version=runtime_version[0])
                    if runtime_identity['normalized_version'] != self.sdk_identity['normalized_version']:
                        raise RuntimeError('Isaac runtime version conflicts with static SDK version')
                    runtime_full = (runtime_version[0]
                                    + ('-' + runtime_version[1] if runtime_version[1] else '')
                                    + ('+' + runtime_version[7] if runtime_version[7] else ''))
                    if (self.sdk_identity['sdk_version_raw'] is not None
                            and runtime_full != self.sdk_identity['sdk_version_raw']):
                        raise RuntimeError('Isaac runtime build conflicts with static SDK VERSION')
                    self.sdk_runtime_version_raw = runtime_version
                actual = int(carb.settings.get_settings().get_as_int(
                    "/plugins/carb.tasking.plugin/threadCount"
                ))
                _validate_isaac_task_thread_count(actual)
            except BaseException as primary:
                try:
                    self._close_now()
                except BaseException as cleanup_error:
                    primary.add_note(
                        "Isaac App cleanup after task-thread validation also failed: "
                        f"{type(cleanup_error).__name__}: {cleanup_error}"
                    )
                raise
        return self._app

    def invalidate_runtime(self, reason: str) -> None:
        """Reject new scene leases when the process App has lost its runtime state."""
        if not isinstance(reason, str) or not reason:
            raise ValueError('Isaac runtime invalidation requires a reason')
        if self._runtime_invalidation_reason is None:
            self._runtime_invalidation_reason = reason

    def close(self) -> None:
        if self._closed or self._close_attempted:
            return
        if self._process_lifetime_holds:
            self._close_requested = True
            return
        self._close_now()

    def retain_process_lifetime(self) -> None:
        """Keep the process App alive while sequential Core Env leases are exchanged."""
        if self._closed or self._close_attempted:
            raise RuntimeError("cannot retain a closed process Isaac App")
        self._process_lifetime_holds += 1

    def release_process_lifetime(self) -> None:
        if self._process_lifetime_holds <= 0:
            raise RuntimeError("process Isaac App lifetime hold is not retained")
        self._process_lifetime_holds -= 1
        if self._process_lifetime_holds == 0 and self._close_requested:
            self._close_now()

    def _close_now(self) -> None:
        if self._closed or self._close_attempted:
            return
        self.close_attempts += 1
        self._close_attempted = True
        self._close_requested = False
        app = self._app
        if app is not None:
            try:
                app.close()
            except BaseException as error:
                self._close_failure = {
                    "type": type(error).__name__, "message": str(error),
                }
                raise
        # The process owner deliberately retains the closed wrapper until the
        # isolated worker reaches its explicit terminal boundary. Core Env and
        # Session close must never trigger native process termination or force
        # CPython to finalize SDK objects in an unsafe unload order.
        self._closed = True
        self._close_completed = True

    def close_receipt(self) -> dict[str, object]:
        """Expose whether the native App close call was attempted and returned."""
        return {
            "close_attempted": self._close_attempted,
            "close_completed": self._close_completed,
            "close_failure": self._close_failure,
            "closed": self._closed,
            "close_attempts": self.close_attempts,
            "framework_unload_attempted": self._framework_unload_attempted,
            "framework_unload_completed": self._framework_unload_completed,
            "framework_unload_failure": self._framework_unload_failure,
            "atexit_close_unregister_attempted": self._atexit_close_unregister_attempted,
            "atexit_close_unregister_completed": self._atexit_close_unregister_completed,
            "atexit_close_unregister_failure": self._atexit_close_unregister_failure,
        }


def _process_app_owner(*, launch_profile_id: str | None = None) -> IsaacSimAppOwnerV1:
    global _PROCESS_APP_OWNER
    with _APP_LOCK:
        if _PROCESS_APP_OWNER is None:
            _PROCESS_APP_OWNER = IsaacSimAppOwnerV1(
                launch_profile_id=(
                    DEFAULT_ISAAC_APP_LAUNCH_PROFILE_V1
                    if launch_profile_id is None else launch_profile_id
                )
            )
        elif (launch_profile_id is not None
              and _PROCESS_APP_OWNER.launch_profile_id != launch_profile_id):
            raise RuntimeError(
                "the process Isaac App already has a different launch profile"
            )
        if _PROCESS_APP_OWNER._closed:
            raise RuntimeError("the process Isaac App was already closed")
        return _PROCESS_APP_OWNER


def isaac_worker_app_owner() -> IsaacSimAppOwnerV1:
    """Select the provider's App profile before worker source reconstruction."""
    return _process_app_owner(launch_profile_id=F06_ISAAC_APP_LAUNCH_PROFILE_V1)


def open_isaac_worker_app(owner: IsaacSimAppOwnerV1) -> None:
    """Open an already-owned worker App with the provider's SDK policy."""
    owner.open(f06_compatibility=True)


@contextmanager
def prepare_isaac_source(*, rendering):
    """Open the process App before any SDK source inspection.

    A successful construction transfers App lifetime to the normal Runtime
    leases. Failure closes only an App opened by this preparation.
    """
    owner, opened_here = None, False
    try:
        profile = (V211_ISAAC_RENDER_APP_LAUNCH_PROFILE_V1 if rendering
                   else F06_ISAAC_APP_LAUNCH_PROFILE_V1)
        owner = _process_app_owner(launch_profile_id=profile)
        opened_here = owner.app is None
        owner.open(f06_compatibility=True)
        yield
    except BaseException as error:
        if opened_here:
            try:
                owner.close()
            except BaseException as cleanup_error:
                error.add_note(f'Isaac App construction cleanup failed: {cleanup_error!r}')
        raise


def _tensor_rows(value, *, width: int, label: str) -> tuple[tuple[float, ...], ...]:
    array = value.numpy()
    rows = array.tolist()
    if rows and not isinstance(rows[0], (tuple, list)):
        rows = [rows]
    if not rows or any(len(row) != width for row in rows):
        raise ValueError(f"public Isaac {label} view has unexpected shape")
    result = tuple(tuple(float(item) for item in row) for row in rows)
    import math

    if any(not math.isfinite(item) for row in result for item in row):
        raise ValueError(f"public Isaac {label} view contains non-finite values")
    return result


def _verify_f06_public_joint_axes(stage, usd_physics, witness):
    """Compare authored joint frames with same-boundary public Jacobian axes."""
    import numpy as np
    def rotation(q):
        w, x, y, z = (float(v) for v in q)
        norm = math.sqrt(w*w + x*x + y*y + z*z)
        if not math.isfinite(norm) or abs(norm - 1.) > 1e-4:
            raise ValueError('F06 axis witness quaternion is not normalized')
        w, x, y, z = (v / norm for v in (w, x, y, z))
        return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                         [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                         [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
    order = witness['dof_order']
    links = witness['link_order']
    poses = {row['path']: row for row in witness['link_world_poses']}
    jac = np.asarray(witness['jacobian'], dtype=float)
    if jac.ndim != 3 or jac.shape[1] != 6 or not np.isfinite(jac).all():
        raise ValueError('F06 public Jacobian shape differs from the axis witness')
    result = {}
    for prim in stage.Traverse():
        name = prim.GetName()
        if name not in order:
            continue
        if prim.IsA(usd_physics.RevoluteJoint):
            joint, kind = usd_physics.RevoluteJoint(prim), 'revolute'
        elif prim.IsA(usd_physics.PrismaticJoint):
            joint, kind = usd_physics.PrismaticJoint(prim), 'prismatic'
        else:
            raise ValueError(f'F06 named DOF lacks a scalar USD joint: {name}')
        if name in result:
            raise ValueError('F06 source has duplicate named DOFs')
        children = joint.GetBody1Rel().GetTargets()
        if len(children) != 1 or str(children[0]) not in poses:
            raise ValueError('F06 joint child is absent from the public link witness')
        pose = poses[str(children[0])]
        link_index = links.index(pose['name'])
        row = link_index - (1 if jac.shape[0] == len(links)-1 else 0)
        column = order.index(name) + (jac.shape[2]-len(order))
        if row < 0 or row >= jac.shape[0] or column < 0 or column >= jac.shape[2]:
            raise ValueError('F06 native Jacobian indexing differs from its public names')
        q = joint.GetLocalRot1Attr().Get()
        quaternion = [float(q.GetReal()), *(float(v) for v in q.GetImaginary())]
        token = str(joint.GetAxisAttr().Get())
        if token not in {'X', 'Y', 'Z'}:
            raise ValueError('F06 USD joint axis token is invalid')
        source_axis = rotation(pose['orientation_world_wxyz']) @ rotation(quaternion) @ np.eye(3)[{'X':0, 'Y':1, 'Z':2}[token]]
        native_axis = jac[row, 3:6, column] if kind == 'revolute' else jac[row, 0:3, column]
        length = float(np.linalg.norm(native_axis))
        if length <= 1e-6:
            raise ValueError('F06 native Jacobian axis is unobservable')
        native_axis = native_axis / length
        error = math.atan2(float(np.linalg.norm(np.cross(source_axis, native_axis))),
                           float(np.dot(source_axis, native_axis)))
        if error > 1e-5:
            raise ValueError(f'F06 USD and public Jacobian axis differ: {name} {error}')
        result[name] = {'kind': kind, 'source_path': str(prim.GetPath()), 'child_path': str(children[0]),
                        'source_axis_world': source_axis.tolist(), 'native_axis_world': native_axis.tolist(),
                        'error_rad': error}
    if set(result) != set(order):
        raise ValueError('F06 USD axis witness does not cover all native DOFs')
    return {'schema_version': 'f06-public-source-native-axis-witness-v1', 'rows': result}


def _read_f06_public_physical_model(articulation, free_views):
    """Read F06 link/free-body mass properties through public tensor views."""
    import numpy as np

    def array(value, shape, label):
        actual = np.asarray(value.numpy(), dtype=np.float64)
        if actual.shape != shape or not np.isfinite(actual).all():
            raise ValueError(f'public Isaac {label} has invalid shape or nonfinite values: {actual.shape}')
        return actual
    names = tuple(articulation.link_names)
    if not names or any(not isinstance(name, str) or not name for name in names) or len(set(names)) != len(names):
        raise ValueError('public Isaac articulation link names must be unique and nonempty')
    for name in ('get_link_masses', 'get_link_coms', 'get_link_inertias'):
        if not callable(getattr(articulation, name, None)):
            raise ValueError(f'public Isaac articulation lacks required {name}')
    if not callable(getattr(articulation, 'is_physics_tensor_entity_valid', None)) or not articulation.is_physics_tensor_entity_valid():
        raise ValueError('public Isaac articulation tensor view is unavailable')
    count = len(names)
    masses = array(articulation.get_link_masses(), (1, count), 'link masses')
    positions, orientations = articulation.get_link_coms()
    positions = array(positions, (1, count, 3), 'link COM positions')
    orientations = array(orientations, (1, count, 4), 'link COM orientations')
    inertias = array(articulation.get_link_inertias(), (1, count, 9), 'link inertias')
    links = [{'name': name, 'mass_kg': float(masses[0, i]),
              'com_body_m': positions[0, i].tolist(),
              'inertial_quaternion_body_wxyz': orientations[0, i].tolist(),
              'inertia_body_at_com_kg_m2': inertias[0, i].reshape((3, 3), order='F').tolist()}
             for i, name in enumerate(names)]
    free = {}
    for semantic, view in free_views.items():
        for name in ('get_masses', 'get_coms', 'get_inertias'):
            if not callable(getattr(view, name, None)):
                raise ValueError(f'public Isaac rigid-body view lacks required {name}: {semantic}')
        if not callable(getattr(view, 'is_physics_tensor_entity_valid', None)) or not view.is_physics_tensor_entity_valid():
            raise ValueError(f'public Isaac rigid-body tensor view is unavailable: {semantic}')
        mass = array(view.get_masses(), (1, 1), f'{semantic} mass')
        position, orientation = view.get_coms()
        position = array(position, (1, 3), f'{semantic} COM position')
        orientation = array(orientation, (1, 4), f'{semantic} COM orientation')
        inertia = array(view.get_inertias(), (1, 9), f'{semantic} inertia')
        free[semantic] = {'mass_kg': float(mass[0, 0]), 'com_body_m': position[0].tolist(),
                          'inertial_quaternion_body_wxyz': orientation[0].tolist(),
                          'inertia_body_at_com_kg_m2': inertia[0].reshape((3, 3), order='F').tolist()}
    return {'schema_version': 'isaac-public-tensor-model-facts-v1', 'links': links, 'free_bodies': free,
            'inertia_reference': 'center_of_mass', 'inertia_frame': 'body',
            'inertia_tensor_storage': 'provider column-major, projected as rows',
            'scope': 'public Isaac articulation and rigid-body tensor views'}


def _read_f06_authored_mass_properties(stage, paths, usd_physics):
    """Retain authored USD values separately from computed native tensor values."""
    result = {}
    for label, path in paths.items():
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsValid():
            raise ValueError(f'F06 physical source prim is unavailable: {path}')
        row = {'path': str(path), 'has_mass_api': bool(prim.HasAPI(usd_physics.MassAPI))}
        if not row['has_mass_api']:
            result[label] = row
            continue
        api = usd_physics.MassAPI(prim)
        for key, getter in (('mass_kg', 'GetMassAttr'), ('center_of_mass_m', 'GetCenterOfMassAttr'),
                            ('diagonal_inertia_kg_m2', 'GetDiagonalInertiaAttr'),
                            ('principal_axes_wxyz', 'GetPrincipalAxesAttr')):
            attr = getattr(api, getter)()
            authored = bool(attr and attr.HasAuthoredValueOpinion())
            value = attr.Get() if authored else None
            if value is not None and key == 'principal_axes_wxyz':
                value = [float(value.GetReal()), *(float(v) for v in value.GetImaginary())]
            elif value is not None and key != 'mass_kg':
                value = [float(v) for v in value]
            elif value is not None:
                value = float(value)
            row[key] = {'authored': authored, 'value': value}
        result[label] = row
    return result


def _pose_from_view(view) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
    positions, orientations = view.get_world_poses()
    p = _tensor_rows(positions, width=3, label="world position")[0]
    q = _tensor_rows(orientations, width=4, label="world orientation")[0]
    # Isaac Sim's experimental public RigidPrim API returns scalar-first wxyz.
    return p, q


def _nearest_rigid_body_ancestor(prim, rigid_body_api):
    """Find the nearest public rigid-body owner above a fixed frame prim."""
    ancestor = prim.GetParent()
    while ancestor and ancestor.IsValid():
        if ancestor.HasAPI(rigid_body_api):
            return ancestor
        ancestor = ancestor.GetParent()
    return None


def _static_frame_local_pose(frame_prim, rigid_body_prim, UsdGeom):
    """Read a rigid frame's fixed local pose below its moving rigid-body owner.

    XformPrim reads authored USD transforms; it does not read the live pose of
    a non-root articulation link from PhysX. For a fixed frame nested below a
    public RigidPrim, keep the USD-authored local transform and compose it with
    the RigidPrim tensor pose at each state boundary.
    """
    parent_path = str(rigid_body_prim.GetPath())
    frame_path = str(frame_prim.GetPath())
    if not frame_path.startswith(parent_path.rstrip("/") + "/"):
        raise ValueError("rigid-body frame source must be a descendant of its live pose owner")

    cursor = frame_prim
    while str(cursor.GetPath()) != parent_path:
        if not cursor or not cursor.IsValid():
            raise ValueError("rigid-body frame source lost its declared ancestor")
        xformable = UsdGeom.Xformable(cursor)
        if not xformable or xformable.GetResetXformStack():
            raise ValueError("rigid-body child frame may not reset its USD transform stack")
        if any(op.GetAttr().GetNumTimeSamples() for op in xformable.GetOrderedXformOps()):
            raise ValueError("rigid-body child frame must have a static authored USD transform")
        cursor = cursor.GetParent()

    cache = UsdGeom.XformCache()
    frame_world = cache.GetLocalToWorldTransform(frame_prim)
    body_world = cache.GetLocalToWorldTransform(rigid_body_prim)
    local = frame_world * body_world.GetInverse()
    basis = tuple(
        tuple(float(local[row][column]) for column in range(3))
        for row in range(3)
    )
    for row in range(3):
        for other in range(3):
            dot = sum(basis[row][axis] * basis[other][axis] for axis in range(3))
            expected = 1.0 if row == other else 0.0
            if not math.isclose(dot, expected, rel_tol=0.0, abs_tol=1e-6):
                raise ValueError("rigid-body child frame transform must be unit-scale and shear-free")
    determinant = (
        basis[0][0] * (basis[1][1] * basis[2][2] - basis[1][2] * basis[2][1])
        - basis[0][1] * (basis[1][0] * basis[2][2] - basis[1][2] * basis[2][0])
        + basis[0][2] * (basis[1][0] * basis[2][1] - basis[1][1] * basis[2][0])
    )
    if not math.isclose(determinant, 1.0, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError("rigid-body child frame transform must preserve handedness")
    position = tuple(float(value) for value in local.ExtractTranslation())
    quaternion = local.ExtractRotationQuat()
    orientation = (
        float(quaternion.GetReal()),
        *(float(value) for value in quaternion.GetImaginary()),
    )
    return PoseWorld(position, orientation)


def _compose_world_pose(parent_position, parent_orientation_wxyz,
                        local_position, local_orientation_wxyz):
    """Compose a fixed child-frame pose with a live public rigid-body pose."""
    parent_position = tuple(float(value) for value in parent_position)
    local_position = tuple(float(value) for value in local_position)
    if len(parent_position) != 3 or len(local_position) != 3:
        raise ValueError("rigid-body and child-frame positions must have width three")
    if any(not math.isfinite(value) for value in (*parent_position, *local_position)):
        raise ValueError("rigid-body and child-frame positions must be finite")

    def normalize(quaternion):
        values = tuple(float(value) for value in quaternion)
        if len(values) != 4 or any(not math.isfinite(value) for value in values):
            raise ValueError("rigid-body and child-frame orientations must be finite wxyz quaternions")
        norm = math.sqrt(sum(value * value for value in values))
        if norm <= 1e-12:
            raise ValueError("rigid-body and child-frame orientations cannot be zero")
        return tuple(value / norm for value in values)

    parent_q = normalize(parent_orientation_wxyz)
    local_q = normalize(local_orientation_wxyz)
    w, x, y, z = parent_q
    vx, vy, vz = local_position
    # Rotate with q * (0, v) * conjugate(q), without a SciPy dependency.
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    rotated = (
        vx + w * tx + (y * tz - z * ty),
        vy + w * ty + (z * tx - x * tz),
        vz + w * tz + (x * ty - y * tx),
    )
    world_position = tuple(parent_position[index] + rotated[index] for index in range(3))

    lw, lx, ly, lz = local_q
    world_orientation = normalize((
        w * lw - x * lx - y * ly - z * lz,
        w * lx + x * lw + y * lz - z * ly,
        w * ly - x * lz + y * lw + z * lx,
        w * lz + x * ly - y * lx + z * lw,
    ))
    return world_position, world_orientation


def _body_local_com_offset_from_public_tensor_pose(com_position_body_local_m) -> tuple[float, float, float]:
    """Validate the Tensor RigidPrim COM translation, which is body-local in Isaac 6.2."""
    if len(com_position_body_local_m) != 3:
        raise ValueError("public rigid-body COM translation must have three components")
    result = tuple(float(value) for value in com_position_body_local_m)
    import math
    if any(not math.isfinite(value) for value in result):
        raise ValueError("public rigid-body COM translation must be finite")
    return result


def _native_prim_path(native_name: str, entry_prim: str) -> str:
    """Resolve an explicit stage prim path or entry-root-relative path."""
    if type(native_name) is not str or not native_name or "\\" in native_name:
        raise ValueError("native frame/body bindings must be explicit USD prim paths")
    if native_name.startswith("/"):
        if any(part in {"", ".", ".."} for part in native_name.split("/")[1:]):
            raise ValueError("native USD prim path is not canonical")
        return native_name
    if any(part in {"", ".", ".."} for part in native_name.split("/")):
        raise ValueError("native USD prim path is not canonical")
    return entry_prim.rstrip("/") + "/" + native_name


def check_isaac_named_layout(source, dof_names, frame_views, free_views, read_views):
    """Validate selected USD/DOF mappings against live public tensor views."""
    dofs = tuple(dof_names)
    if len(dofs) != len(set(dofs)):
        raise ValueError('Isaac public DOF names are ambiguous')
    index = {name: i for i, name in enumerate(dofs)}
    joints, velocities, frames, free = read_views()
    result = {'joints': {}, 'free_joints': {}, 'bodies': {}, 'frames': {}, 'actuators': {}}
    for semantic, native in source.joints.items():
        if native not in index or semantic not in joints or semantic not in velocities:
            raise ValueError(f'Isaac public joint state missing: {semantic}')
        result['joints'][semantic] = {'native': native, 'id': index[native], 'qpos_width': 1, 'dof_width': 1}
    for semantic, native in source.joint_targets.items():
        if semantic not in source.joints or native not in index or native != source.joints[semantic]:
            raise ValueError(f'Isaac public position target mismatch: {semantic}')
        result['actuators'][semantic] = {'native': native, 'id': index[native]}
    for field in ('bodies', 'frames'):
        for semantic, native in getattr(source, field).items():
            if semantic not in frame_views or semantic not in frames:
                raise ValueError(f'Isaac public {field} pose view missing: {semantic}')
            result[field][semantic] = {'native': native, 'view': 'public_world_pose'}
    for semantic, native in source.free_joints.items():
        if semantic not in free_views or semantic not in free:
            raise ValueError(f'Isaac public free-body state missing: {semantic}')
        result['free_joints'][semantic] = {'native': native, 'view': 'public_rigid_body'}
    return result


class IsaacSimNativeRuntimeIOV1:
    """Implement the six Core native-I/O operations over public Isaac APIs."""

    execution_provenance_kind = "native_runtime"

    def __init__(self, artifact: TaskArtifactV1, execution: ExecutionSpecV1,
                 source: UsdRuntimeSourceV1, lease: UsdSnapshotLeaseV1,
        app_owner: IsaacSimAppOwnerV1, *,
                 f06_pickcube_input=None,
                 g05_effort=False, observer_render_request=None):
        if type(artifact) is not TaskArtifactV1 or type(execution) is not ExecutionSpecV1:
            raise TypeError("Isaac native I/O requires exact TaskArtifactV1 and ExecutionSpecV1")
        if type(source) is not UsdRuntimeSourceV1 or type(lease) is not UsdSnapshotLeaseV1:
            raise TypeError("Isaac native I/O requires verified USD RuntimeSource and owned snapshot lease")
        self._artifact, self._execution, self._source = artifact, execution, source
        self._lease, self._app_owner = lease, app_owner
        self._observer_render_request = observer_render_request
        self._observer_stage_time_range_receipt = None
        self._observer_render_light_receipt = None
        self._task_renderer_stage_preparation = None
        self._observer_sensor = None
        self._observer_path = None
        self._task_camera_path = None
        self._task_camera_geometry = None
        self._task_camera_sensor = None
        self._observer_faulted = False
        self._f06_pickcube_input = f06_pickcube_input
        self._f06_pickcube = execution.physics_profile == 'isaac-gpu-physx-pickcube-f06-v1'
        self._g05_effort = execution.physics_profile == 'isaac-gpu-physx-g05-5c-effort-v1'
        if type(g05_effort) is not bool or g05_effort != self._g05_effort:
            raise ValueError('G05 Isaac I/O requires its exact effort profile flag')
        if self._f06_pickcube != (f06_pickcube_input is not None) or (
                self._f06_pickcube and self._g05_effort):
            raise ValueError('Isaac I/O requires one exact native route/profile alone')
        self._closed = False
        self._runtime_owner_closed = False
        self._context = None
        self._stage = None
        self._manager = None
        self._torch = None
        self._physics_scene = None
        self._articulation = None
        self._body_views: dict[str, Any] = {}
        self._frame_views: dict[str, Any] = {}
        self._frame_local_poses: dict[str, PoseWorld] = {}
        self._frame_pose_readback_receipts: dict[str, dict[str, object]] = {}
        self._free_views: dict[str, Any] = {}
        self._dof_names: tuple[str, ...] = ()
        self._dof_index: dict[str, int] = {}
        self._position_limits: dict[str, tuple[float, float]] = {}
        self._episode_origin_step: int | None = None
        self._episode_origin_time: float | None = None
        self._native_step_count = 0
        self._metadata: NativeRuntimeIOMetadataV1 | None = None
        self._bootstrap_receipt = None
        self._startup_observation = {
            "schema_version": "isaac-public-physics-bootstrap-observation-v2",
            "status": "construction_started",
            "source_id": self._source.source_id,
            "source_closure": self._source.source_closure_digest,
            "scene_identity": self._source.scene_definition.identity_hash,
            "configured_physics_dt_s": float(self._artifact.timebase.physics_dt),
            "stage_physics_scene_paths": [],
            "stage_physics_scene_count": None,
            "stage_start_time_code": None,
            "stage_end_time_code": None,
            "stage_time_codes_per_second": None,
            "scene_gravity_direction": None,
            "scene_gravity_magnitude": None,
            "scene_time_steps_per_second": {},
            "scene_time_steps_per_second_after_setup": {},
            "scene_applied_schemas_before": [],
            "scene_applied_schemas_after": [],
            "runtime_scene_owner_adaptation": None,
            "physics_scene_dt_s": None,
            "simulation_manager_scene_count": None,
            "simulation_manager_device": None,
            "simulation_manager_owner": "isaacsim.core.simulation_manager.SimulationManager",
            "clock_owner": "SimulationManager.get_simulation_time",
            "step_index_before": None,
            "step_index_after_play": None,
            "step_index_after": None,
            "simulation_time_before_s": None,
            "simulation_time_after_play_s": None,
            "simulation_time_after_s": None,
            "physics_step_delta": None,
            "physics_time_delta_s": None,
            "timeline_playing_before_pause": None,
            "timeline_playing_after_pause": None,
            "application_updates": 2,
            "bootstrap_update_samples": [],
            "failure_boundary": None,
        }
        self._build_layout_facts = {
            "native_startup_observation": self._startup_observation,
        }
        self.drive_receipt = None
        self._f06_native_mimic_receipt = None
        self._last_native_mimic_target = None
        self._open_public_runtime()

    def _update_startup_observation(self, **values) -> None:
        """Keep failure-visible App/scene/clock facts in the adapter receipt."""
        self._startup_observation.update(values)
        self._build_layout_facts["native_startup_observation"] = dict(self._startup_observation)

    def _open_public_runtime(self) -> None:
        try:
            self._app_owner.open(f06_compatibility=True) if self._f06_pickcube else self._app_owner.open()
            import omni.usd
            import torch
            from pxr import Gf, PhysxSchema, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics
            from isaacsim.core.experimental.prims import Articulation, RigidPrim, XformPrim
            from isaacsim.core.simulation_manager import SimulationManager
            from isaacsim.core.experimental.utils import app as app_utils

            if not torch.cuda.is_available() or torch.cuda.current_device() != 0:
                raise RuntimeError("F04 requires CUDA device 0; CPU fallback is not admitted")
            expected_profile = (
                'isaac-gpu-physx-pickcube-f06-v1' if self._f06_pickcube
                else 'isaac-gpu-physx-g05-5c-effort-v1' if self._g05_effort
                else 'isaac-gpu-physx-f04-position-v1'
            )
            if (self._execution.physics_provider, self._execution.physics_backend,
                    self._execution.physics_device, self._execution.determinism_mode,
                    self._execution.physics_profile) != (
                    "isaacsim", "cuda", "cuda:0", "best_effort", expected_profile):
                raise ValueError("unsupported exact Isaac execution identity")
            if SimulationManager.get_active_physics_engine() != "physx":
                raise RuntimeError("F04 requires the public PhysX simulation engine")

            delivery = self._source.scene_source.loaded_delivery.delivery
            snapshot_entry = self._lease.root.joinpath(*delivery.entry_file.split("/"))
            if not snapshot_entry.is_file():
                raise ValueError("verified snapshot does not contain its declared USD entry")
            self._context = omni.usd.get_context()
            if self._context.get_stage() is not None:
                self._context.close_stage()
            opened = self._context.open_stage(str(snapshot_entry))
            if opened is False:
                raise RuntimeError("Isaac public USD context rejected the verified snapshot")
            self._stage = self._context.get_stage()
            if self._stage is None:
                raise RuntimeError("Isaac public USD context did not publish a stage")
            load_stage = getattr(self._stage, 'Load', None)
            if callable(load_stage):
                load_stage()
            if self._observer_render_request is not None:
                start_time_code = float(self._stage.GetStartTimeCode())
                source_end_time_code = float(self._stage.GetEndTimeCode())
                end_time_code = source_end_time_code
                extended = end_time_code <= start_time_code
                if extended:
                    # RTX annotators need a non-degenerate USD time range even
                    # for a static scene. Keep the authored time origin and
                    # extend only the disposable in-memory stage metadata.
                    end_time_code = start_time_code + 1.0
                    self._stage.SetEndTimeCode(end_time_code)
                self._observer_stage_time_range_receipt = {
                    "schema_version": "isaac-observer-stage-time-range-v1",
                    "source_start_time_code": start_time_code,
                    "source_end_time_code": source_end_time_code,
                    "effective_start_time_code": start_time_code,
                    "effective_end_time_code": end_time_code,
                    "extended_in_memory": extended,
                    "time_codes_per_second": float(self._stage.GetTimeCodesPerSecond()),
                    "frames_per_second": float(self._stage.GetFramesPerSecond()),
                }
                light_paths = sorted(
                    str(prim.GetPath()) for prim in self._stage.Traverse()
                    if prim.HasAPI(UsdLux.LightAPI)
                )
                added_light_path = None
                if not light_paths:
                    # This frozen F06 stage has no authored lights. A camera
                    # render product has no viewport headlight, so add a
                    # renderer-only neutral dome light to the in-memory stage.
                    added_light_path = "/GeoChoraObserverEnvironmentLight"
                    dome = UsdLux.DomeLight.Define(self._stage, Sdf.Path(added_light_path))
                    if not dome or not dome.GetPrim().IsValid():
                        raise RuntimeError("Isaac observer could not define its renderer-only dome light")
                    dome.GetIntensityAttr().Set(1000.0)
                    dome.GetColorAttr().Set(Gf.Vec3f(1.0, 1.0, 1.0))
                self._observer_render_light_receipt = {
                    "schema_version": "isaac-observer-render-light-v1",
                    "source_light_paths": light_paths,
                    "added_light_path": added_light_path,
                    "added_light_type": "UsdLux.DomeLight" if added_light_path else None,
                    "added_light_intensity": 1000.0 if added_light_path else None,
                    "added_light_color_linear_rgb": [1.0, 1.0, 1.0] if added_light_path else None,
                    "stage_saved": False,
                }
            if (float(UsdGeom.GetStageMetersPerUnit(self._stage)) != 1.0
                    or str(UsdGeom.GetStageUpAxis(self._stage)) != "Z"):
                raise ValueError("F04 admission requires meter units and Z-up source stage")
            for key, selection in delivery.variant_selections.items():
                prim_path, set_name = key.rsplit("#", 1)
                variant_prim = self._stage.GetPrimAtPath(prim_path)
                if not variant_prim or not variant_prim.IsValid():
                    raise ValueError(f"variant prim is absent in composed delivery: {prim_path}")
                variant_set = variant_prim.GetVariantSets().GetVariantSet(set_name)
                if (not variant_set.IsValid() or selection not in variant_set.GetVariantNames()
                        or not variant_set.SetVariantSelection(selection)):
                    raise ValueError(f"delivery variant is not available: {key}={selection}")

            if self._f06_pickcube:
                self._f06_pickcube_input.validate()
                self._verify_native_mimic_profile(
                    PhysxSchema, UsdPhysics, route='f06',
                )

            authored_scenes = [p for p in self._stage.Traverse() if p.IsA(UsdPhysics.Scene)]
            authored_scene_paths = sorted(str(prim.GetPath()) for prim in authored_scenes)
            scene_gravity_direction = None
            scene_gravity_magnitude = None
            scene_time_steps_per_second = {}
            scene_applied_schemas_before = []
            runtime_scene_owner_adaptation = None
            if len(authored_scenes) == 1:
                scene_prim = authored_scenes[0]
                scene_applied_schemas_before = sorted(str(value) for value in scene_prim.GetAppliedSchemas())
                gravity_direction_attr = scene_prim.GetAttribute("physics:gravityDirection")
                gravity_magnitude_attr = scene_prim.GetAttribute("physics:gravityMagnitude")
                if gravity_direction_attr and gravity_direction_attr.IsValid() and gravity_direction_attr.HasAuthoredValue():
                    scene_gravity_direction = [float(value) for value in gravity_direction_attr.Get()]
                if gravity_magnitude_attr and gravity_magnitude_attr.IsValid() and gravity_magnitude_attr.HasAuthoredValue():
                    scene_gravity_magnitude = float(gravity_magnitude_attr.Get())
                for attribute_name in (
                        "physx:timeStepsPerSecond",
                        "physics:timeStepsPerSecond",
                        "newton:timeStepsPerSecond"):
                    time_steps_attr = scene_prim.GetAttribute(attribute_name)
                    if time_steps_attr and time_steps_attr.IsValid() and time_steps_attr.HasAuthoredValue():
                        scene_time_steps_per_second[attribute_name] = int(time_steps_attr.Get())
            self._update_startup_observation(
                status="stage_scene_checked",
                stage_physics_scene_paths=authored_scene_paths,
                stage_physics_scene_count=len(authored_scene_paths),
                stage_start_time_code=float(self._stage.GetStartTimeCode()),
                stage_end_time_code=float(self._stage.GetEndTimeCode()),
                stage_time_codes_per_second=float(self._stage.GetTimeCodesPerSecond()),
                scene_gravity_direction=scene_gravity_direction,
                scene_gravity_magnitude=scene_gravity_magnitude,
                scene_time_steps_per_second=scene_time_steps_per_second,
                scene_applied_schemas_before=scene_applied_schemas_before,
            )
            if len(authored_scenes) not in (0, 1) or (not self._g05_effort and len(authored_scenes) != 1):
                self._update_startup_observation(
                    status="failed",
                    failure_boundary="authored_physics_scene_count",
                )
                raise ValueError(
                    "verified USD source must author at most one PhysicsScene; non-G05 routes require exactly one"
                )
            if self._g05_effort and len(authored_scenes) == 1:
                scene_prim = authored_scenes[0]
                get_authored_properties = getattr(scene_prim, "GetAuthoredProperties", None)
                if not callable(get_authored_properties):
                    self._update_startup_observation(
                        status="failed",
                        failure_boundary="physics_scene_authored_property_inspection_unavailable",
                    )
                    raise RuntimeError("USD public API cannot enumerate authored PhysicsScene properties")
                authored_values = {}
                for authored_property in get_authored_properties():
                    property_name = str(authored_property.GetName())
                    attribute = scene_prim.GetAttribute(property_name)
                    if not attribute or not attribute.IsValid():
                        raise ValueError(
                            "G05 PhysicsScene has an authored non-attribute property that cannot be transferred: "
                            f"{property_name}"
                        )
                    value = attribute.Get()
                    if property_name == "physics:gravityDirection":
                        value = [float(component) for component in value]
                    elif property_name == "physics:gravityMagnitude":
                        value = float(value)
                    elif property_name == "physx:timeStepsPerSecond":
                        value = int(value)
                    authored_values[property_name] = value
                try:
                    handoff = _g05_scene_handoff_payload(
                        scene_path=str(scene_prim.GetPath()),
                        applied_schemas=scene_applied_schemas_before,
                        authored_values=authored_values,
                        configured_dt=float(self._artifact.timebase.physics_dt),
                        meters_per_unit=float(UsdGeom.GetStageMetersPerUnit(self._stage)),
                    )
                except (TypeError, ValueError) as error:
                    self._update_startup_observation(
                        status="failed",
                        failure_boundary="physics_scene_semantic_conflict",
                        runtime_scene_owner_adaptation={
                            "schema_version": "g05-scene-owner-handoff-v1",
                            "status": "rejected_semantic_conflict",
                            "scene_path": str(scene_prim.GetPath()),
                            "authored_properties": authored_values,
                            "applied_schemas": scene_applied_schemas_before,
                            "error": str(error),
                        },
                    )
                    raise
                session_layer = self._stage.GetSessionLayer()
                if session_layer is None:
                    raise RuntimeError("G05 PhysicsScene handoff requires a USD session layer")
                with Usd.EditContext(self._stage, session_layer):
                    scene_prim.SetActive(False)
                if scene_prim.IsActive():
                    raise RuntimeError("USD session-layer PhysicsScene deactivation did not take effect")
                remaining_scene_paths = sorted(
                    str(prim.GetPath()) for prim in self._stage.Traverse()
                    if prim.IsA(UsdPhysics.Scene)
                )
                if remaining_scene_paths:
                    raise RuntimeError(
                        "G05 PhysicsScene handoff did not leave a scene-free stage for the existing owner: "
                        f"{remaining_scene_paths!r}"
                    )
                overlay_text = session_layer.ExportToString()
                session_layer_scene_override = {
                    "schema_version": "g05-session-layer-physics-scene-override-v1",
                    "prim_path": handoff["source_scene_path"],
                    "active": False,
                    "layer_identifier": str(session_layer.identifier),
                    "session_layer_sha256": hashlib.sha256(overlay_text.encode("utf-8")).hexdigest(),
                    "remaining_active_physics_scene_paths": remaining_scene_paths,
                    "stage_saved": False,
                }
                runtime_scene_owner_adaptation = {
                    **handoff,
                    "status": "session_layer_deactivated_pending_manager_scene",
                    "owner": "isaacsim.core.simulation_manager.SimulationManager",
                    "session_layer_override": session_layer_scene_override,
                }
                self._update_startup_observation(
                    status="runtime_scene_owner_handoff_staged",
                    runtime_scene_owner_adaptation=runtime_scene_owner_adaptation,
                    session_layer_scene_override=session_layer_scene_override,
                )
            elif self._g05_effort:
                # A local G05 delivery may contain only the task body.  Let
                # the existing SimulationManager owner construct its single
                # PhysX scene after source inspection; do not author a second
                # scene or mutate the frozen delivery bytes.
                self._update_startup_observation(
                    status="runtime_scene_owner_deferred_to_manager",
                    runtime_scene_owner_adaptation={
                        "schema_version": "g05-runtime-physx-scene-owner-adaptation-v1",
                        "status": "deferred_to_simulation_manager",
                        "scene_path": None,
                        "physx_scene_api": None,
                        "time_steps_per_second": int(round(1.0 / float(self._artifact.timebase.physics_dt))),
                        "physics_dt_s": float(self._artifact.timebase.physics_dt),
                        "source_bytes_modified": False,
                        "owner": "isaacsim.core.simulation_manager.SimulationManager",
                    },
                )
            articulation_roots = [
                p for p in self._stage.Traverse()
                if p.HasAPI(UsdPhysics.ArticulationRootAPI)
            ]
            if len(articulation_roots) != 1:
                raise ValueError("F04 requires exactly one authored articulation root")
            SimulationManager.setup_simulation(
                dt=float(self._artifact.timebase.physics_dt),
                device=self._execution.physics_device,
            )
            scenes = SimulationManager.get_physics_scenes()
            manager_scene_paths = [str(scene.path) for scene in scenes]
            self._update_startup_observation(
                status="simulation_manager_scene_checked",
                simulation_manager_scene_count=len(scenes),
                simulation_manager_device=str(SimulationManager.get_device()),
                public_physics_scene_paths=manager_scene_paths,
            )
            if len(scenes) != 1:
                self._update_startup_observation(
                    status="failed",
                    failure_boundary="simulation_manager_scene_count",
                )
                raise ValueError(f"F04 requires exactly one public PhysX scene, found {len(scenes)}")
            self._physics_scene = scenes[0]
            if self._g05_effort and len(authored_scenes) == 1:
                expected_gravity = runtime_scene_owner_adaptation["gravity_world_m_s2"]
                self._physics_scene.set_gravity(Gf.Vec3f(*expected_gravity))
                actual_gravity = [float(value) for value in self._physics_scene.get_gravity()]
                if not _numeric_tuple_matches(actual_gravity, expected_gravity, abs_tol=1e-5):
                    raise RuntimeError(
                        "SimulationManager-owned PhysX scene did not retain transferred source gravity: "
                        f"{actual_gravity!r} != {expected_gravity!r}"
                    )
            self._physics_scene.set_enabled_gpu_dynamics(True)
            if self._physics_scene.get_enabled_gpu_dynamics() is not True:
                raise RuntimeError("GPU PhysX dynamics did not remain enabled")
            scene_rate_after_setup = int(self._physics_scene.get_steps_per_second())
            expected_scene_rate = int(round(1.0 / float(self._artifact.timebase.physics_dt)))
            if scene_rate_after_setup != expected_scene_rate:
                raise ValueError(
                    "public PhysicsScene rate differs from the TaskArtifact timebase: "
                    f"{scene_rate_after_setup} != {expected_scene_rate}"
                )
            manager_scene_prim = self._physics_scene.prim
            manager_scene_facts = {
                "path": str(self._physics_scene.path),
                "gravity_world_m_s2": [float(value) for value in self._physics_scene.get_gravity()],
                "dt_s": float(self._physics_scene.get_dt()),
                "steps_per_second": scene_rate_after_setup,
                "enabled_gpu_dynamics": bool(self._physics_scene.get_enabled_gpu_dynamics()),
                "applied_schemas": sorted(str(value) for value in manager_scene_prim.GetAppliedSchemas()),
            }
            if runtime_scene_owner_adaptation is not None and runtime_scene_owner_adaptation.get(
                    "status") == "session_layer_deactivated_pending_manager_scene":
                runtime_scene_owner_adaptation = {
                    **runtime_scene_owner_adaptation,
                    "status": "transferred_to_unique_simulation_manager_scene",
                    "manager_scene_path": manager_scene_facts["path"],
                    "manager_scene_facts": manager_scene_facts,
                }
            self._update_startup_observation(
                runtime_scene_owner_adaptation=runtime_scene_owner_adaptation,
                manager_scene_facts=manager_scene_facts,
                physics_scene_dt_s=float(self._physics_scene.get_dt()),
                scene_applied_schemas_after=manager_scene_facts["applied_schemas"],
                scene_time_steps_per_second_after_setup={
                    "physx:timeStepsPerSecond": scene_rate_after_setup,
                },
            )
            if abs(float(self._physics_scene.get_dt()) - float(self._artifact.timebase.physics_dt)) > 1e-12:
                raise ValueError("public PhysicsScene dt differs from the TaskArtifact timebase")
            if str(SimulationManager.get_device()) != "cuda:0":
                raise RuntimeError("public SimulationManager did not retain the requested cuda:0 device")
            self._articulation = Articulation(str(articulation_roots[0].GetPath()))
            self._articulation_path = str(articulation_roots[0].GetPath())
            entry_prim = delivery.entry_prim
            for semantic, native in self._source.bodies.items():
                path = _native_prim_path(native, entry_prim)
                if path not in self._body_views:
                    prim = self._stage.GetPrimAtPath(path)
                    if not prim or not prim.IsValid():
                        raise ValueError(f"USD RuntimeSource frame binding is not a composed prim: {path}")
                    if not prim.HasAPI(UsdPhysics.RigidBodyAPI):
                        raise ValueError(f"USD RuntimeSource body lacks authored RigidBodyAPI: {path}")
                    if (self._f06_pickcube and semantic == 'cube-v1' and self._artifact.artifact_id in {
                            'pickcube-f06-physical-effort-fixture-v1',
                            'pickcube-f06-physical-effort-no-drive-v1'}):
                        self._body_views[path] = RigidPrim(path, max_contact_count=64)
                        self._body_views[path].set_enabled_contact_tracking(True, threshold=0.0)
                    else:
                        self._body_views[path] = RigidPrim(path)
                self._frame_views[semantic] = self._body_views[path]
                self._frame_pose_readback_receipts[semantic] = {
                    "mode": "rigid_body_public_world_pose",
                    "frame_path": path,
                    "rigid_body_path": path,
                }
            for semantic, native in self._source.frames.items():
                path = _native_prim_path(native, entry_prim)
                if path not in self._frame_views:
                    prim = self._stage.GetPrimAtPath(path)
                    if not prim or not prim.IsValid():
                        raise ValueError(f"USD RuntimeSource Frame binding is not a composed prim: {path}")
                    if prim.HasAPI(UsdPhysics.RigidBodyAPI):
                        self._frame_views[semantic] = RigidPrim(path)
                        self._frame_pose_readback_receipts[semantic] = {
                            "mode": "rigid_body_public_world_pose",
                            "frame_path": path,
                            "rigid_body_path": path,
                        }
                        continue
                    rigid_ancestor = _nearest_rigid_body_ancestor(
                        prim, UsdPhysics.RigidBodyAPI,
                    )
                    if rigid_ancestor is None:
                        self._frame_views[semantic] = XformPrim(path)
                        self._frame_pose_readback_receipts[semantic] = {
                            "mode": "public_xform_world_pose",
                            "frame_path": path,
                            "rigid_body_path": None,
                        }
                        continue
                    rigid_path = str(rigid_ancestor.GetPath())
                    rigid_view = self._body_views.get(rigid_path)
                    if rigid_view is None:
                        rigid_view = RigidPrim(rigid_path)
                        self._body_views[rigid_path] = rigid_view
                    local_pose = _static_frame_local_pose(prim, rigid_ancestor, UsdGeom)
                    self._frame_views[semantic] = rigid_view
                    self._frame_local_poses[semantic] = local_pose
                    self._frame_pose_readback_receipts[semantic] = {
                        "mode": "rigid_body_tensor_pose_plus_static_local_frame",
                        "frame_path": path,
                        "rigid_body_path": rigid_path,
                        "local_position_m": list(local_pose.position),
                        "local_orientation_wxyz": list(local_pose.quaternion_wxyz),
                    }
            # The versioned force-observation fixture owns explicit public
            # contact reporters on every robot rigid body. The original F06
            # position route remains unchanged.
            self._f06_robot_contact_views = {}
            if (self._f06_pickcube and self._artifact.artifact_id in {
                    'pickcube-f06-physical-effort-fixture-v1',
                    'pickcube-f06-physical-effort-no-drive-v1'}):
                robot_prefix = str(entry_prim).rstrip('/') + '/panda/'
                for prim in self._stage.Traverse():
                    path = str(prim.GetPath())
                    if path.startswith(robot_prefix) and prim.HasAPI(UsdPhysics.RigidBodyAPI):
                        view = RigidPrim(path, max_contact_count=64)
                        view.set_enabled_contact_tracking(True, threshold=0.0)
                        self._f06_robot_contact_views[path] = view
                if len(self._f06_robot_contact_views) < 9:
                    raise ValueError('F06 physical fixture lacks robot contact reporters')
            for semantic in self._source.free_joints:
                body_path = _native_prim_path(self._source.bodies[semantic], entry_prim)
                self._free_views[semantic] = self._body_views[body_path]
            if not self._g05_effort and len(self._free_views) != 1:
                raise ValueError("F04 requires exactly one mapped floating rigid body")
            # Isaac's tensor views become live only after the public timeline
            # starts and Kit processes its stage callbacks. Count this bootstrap
            # separately from Core reset and public interval advances.
            self._bootstrap_before = (
                int(SimulationManager.get_num_physics_steps()),
                float(SimulationManager.get_simulation_time()),
            )
            self._update_startup_observation(
                status="bootstrap_before_recorded",
                step_index_before=self._bootstrap_before[0],
                simulation_time_before_s=self._bootstrap_before[1],
            )
            app_utils.play()
            after_play = (
                int(SimulationManager.get_num_physics_steps()),
                float(SimulationManager.get_simulation_time()),
            )
            update_samples = []

            def _record_update(update_index, update_count):
                update_samples.append({
                    "update_index": int(update_index),
                    "update_count": int(update_count),
                    "step_index": int(SimulationManager.get_num_physics_steps()),
                    "simulation_time_s": float(SimulationManager.get_simulation_time()),
                })
                return True

            app_utils.update_app(steps=2, callback=_record_update)
            self._bootstrap_after = (
                int(SimulationManager.get_num_physics_steps()),
                float(SimulationManager.get_simulation_time()),
            )
            self._update_startup_observation(
                status="bootstrap_after_recorded",
                step_index_after_play=after_play[0],
                simulation_time_after_play_s=after_play[1],
                bootstrap_update_samples=update_samples,
                step_index_after=self._bootstrap_after[0],
                simulation_time_after_s=self._bootstrap_after[1],
                physics_step_delta=self._bootstrap_after[0] - self._bootstrap_before[0],
                physics_time_delta_s=self._bootstrap_after[1] - self._bootstrap_before[1],
            )
            # App updates used for tensor-view bootstrap leave the public
            # timeline playing. Pause the existing timeline owner before
            # reset/interval ownership; no second App or clock is made.
            # This pause alone has not resolved the observed mismatch between
            # one explicit step and the manager's counter/time deltas.
            timeline_playing_before_pause = bool(app_utils.is_playing())
            app_utils.pause()
            timeline_playing_after_pause = bool(app_utils.is_playing())
            self._update_startup_observation(
                status="bootstrap_timeline_paused",
                timeline_playing_before_pause=timeline_playing_before_pause,
                timeline_playing_after_pause=timeline_playing_after_pause,
            )
            if timeline_playing_after_pause:
                raise RuntimeError("Isaac public timeline remained playing after bootstrap pause")
            for view in (self._articulation, *self._body_views.values(),
                         *(v for v in self._frame_views.values() if isinstance(v, RigidPrim))):
                if hasattr(view, "is_physics_tensor_entity_valid") and not view.is_physics_tensor_entity_valid():
                    raise RuntimeError("public physics tensor view did not initialize after Kit bootstrap")
            self._dof_names = tuple(str(name) for name in self._articulation.dof_names)
            expected_dofs = set(self._source.joint_targets.values())
            if ((not self._g05_effort and len(self._dof_names) != 9)
                    or not self._dof_names
                    or len(set(self._dof_names)) != len(self._dof_names)
                    or set(self._dof_names) != expected_dofs):
                raise ValueError(
                    "public articulation DOF names differ from the exact source-bound joint mapping: "
                    f"actual={self._dof_names!r}, expected={sorted(expected_dofs)!r}"
                )
            self._dof_index = {name: index for index, name in enumerate(self._dof_names)}
            low_array, high_array = self._articulation.get_dof_limits()
            lows = _tensor_rows(low_array, width=len(self._dof_names), label="joint lower limits")[0]
            highs = _tensor_rows(high_array, width=len(self._dof_names), label="joint upper limits")[0]
            self._position_limits = {
                name: (float(lows[index]), float(highs[index]))
                for index, name in enumerate(self._dof_names)
            }
            self._simple_effort_drive_receipt = None
            self._torch = torch
            if self._g05_effort:
                before_stiffness, before_damping = self._articulation.get_dof_gains()
                before_stiffness = _tensor_rows(
                    before_stiffness, width=len(self._dof_names),
                    label='G05 pre-isolation stiffness',
                )[0]
                before_damping = _tensor_rows(
                    before_damping, width=len(self._dof_names),
                    label='G05 pre-isolation damping',
                )[0]
                indices = list(range(len(self._dof_names)))
                self._articulation.set_dof_gains(
                    [0.0] * len(indices), [0.0] * len(indices),
                    dof_indices=indices, update_default_gains=False,
                )
                self._sync()
                stiffness, damping = self._articulation.get_dof_gains()
                after_stiffness = _tensor_rows(
                    stiffness, width=len(self._dof_names),
                    label='G05 isolated stiffness',
                )[0]
                after_damping = _tensor_rows(
                    damping, width=len(self._dof_names),
                    label='G05 isolated damping',
                )[0]
                if any(abs(after_stiffness[index]) > 1e-8 or abs(after_damping[index]) > 1e-8
                       for index in indices):
                    raise RuntimeError('G05 public gain readback did not confirm explicit effort mode')
                self._simple_effort_drive_receipt = {
                    'schema_version': 'g05-public-effort-drive-isolation-v1',
                    'native_dof_names': list(self._dof_names),
                    'before_stiffness': list(before_stiffness),
                    'before_damping': list(before_damping),
                    'after_stiffness': list(after_stiffness),
                    'after_damping': list(after_damping),
                    'source_usd_modified': False,
                    'api': 'Articulation.set_dof_gains tensor',
                }
            static_collision_paths = ()
            for semantic, view in self._free_views.items():
                masses = _tensor_rows(view.get_masses(), width=1, label=f"{semantic} mass")
                if masses[0][0] <= 0.0:
                    raise ValueError(f"mapped floating body has no positive public mass: {semantic}")
                native_path = _native_prim_path(self._source.bodies[semantic], entry_prim)
                if (native_path == self._articulation_path
                        or native_path.startswith(self._articulation_path.rstrip("/") + "/")):
                    raise ValueError("mapped floating body must be separate from the Panda articulation")
                prim = self._stage.GetPrimAtPath(native_path)
                collision_paths = tuple(
                    str(candidate.GetPath()) for candidate in self._stage.Traverse()
                    if candidate.HasAPI(UsdPhysics.CollisionAPI)
                    and (str(candidate.GetPath()) == native_path
                         or str(candidate.GetPath()).startswith(native_path.rstrip("/") + "/"))
                )
                if not collision_paths:
                    raise ValueError(f"mapped floating body lacks authored collision geometry: {native_path}")
                static_collision_paths = tuple(
                    str(candidate.GetPath()) for candidate in self._stage.Traverse()
                    if candidate.HasAPI(UsdPhysics.CollisionAPI)
                    and not (str(candidate.GetPath()) == self._articulation_path
                             or str(candidate.GetPath()).startswith(self._articulation_path.rstrip("/") + "/"))
                    and not (str(candidate.GetPath()) == native_path
                             or str(candidate.GetPath()).startswith(native_path.rstrip("/") + "/"))
                )
                if not static_collision_paths:
                    raise ValueError("verified USD scene has no static collision surface outside Panda and the free body")
            bootstrap_steps = self._bootstrap_after[0] - self._bootstrap_before[0]
            bootstrap_time = self._bootstrap_after[1] - self._bootstrap_before[1]
            if bootstrap_steps < 0 or bootstrap_time < 0:
                self._update_startup_observation(
                    status="failed",
                    failure_boundary="bootstrap_counter_backwards",
                )
                raise RuntimeError("public physics counters moved backwards during bootstrap")
            if abs(bootstrap_time - bootstrap_steps * float(self._artifact.timebase.physics_dt)) > 1e-8:
                self._update_startup_observation(
                    status=("bootstrap_clock_offset_recorded" if self._g05_effort else "failed"),
                    failure_boundary=(
                        "bootstrap_clock_offset_recorded" if self._g05_effort
                        else "bootstrap_counter_time_consistency"
                    ),
                    clock_alignment=(
                        "startup_counter_time_mismatch_recorded; explicit_steps_remain_strict"
                        if self._g05_effort else None
                    ),
                    bootstrap_dt_error_s=(
                        bootstrap_time - bootstrap_steps * float(self._artifact.timebase.physics_dt)
                    ),
                )
                if not self._g05_effort:
                    raise RuntimeError("public physics bootstrap counter/time deltas disagree with the configured dt")
            self._bootstrap_receipt = {
                **self._startup_observation,
                "schema_version": "isaac-public-physics-bootstrap-v1",
                "status": "complete",
                "step_index_before": self._bootstrap_before[0],
                "step_index_after": self._bootstrap_after[0],
                "simulation_time_before_s": self._bootstrap_before[1],
                "simulation_time_after_s": self._bootstrap_after[1],
                "physics_steps": bootstrap_steps,
                "physics_time_s": bootstrap_time,
                "physics_dt_s": float(self._artifact.timebase.physics_dt),
                "application_updates": 2,
                "frame_pose_readback_bindings": {
                    key: dict(value)
                    for key, value in sorted(self._frame_pose_readback_receipts.items())
                },
                "mapped_floating_body_paths": sorted(
                    _native_prim_path(self._source.bodies[semantic], entry_prim)
                    for semantic in self._source.free_joints
                ),
                "static_collision_paths": list(static_collision_paths),
            }
            checked = check_isaac_named_layout(self._source, self._dof_names,
                self._frame_views, self._free_views, self._read_views)
            self._build_layout_facts = {'helper': 'task_env.runtime.sessions.isaac_native_io:check_isaac_named_layout',
                'provider': 'isaacsim', 'source_id': self._source.source_id,
                'source_closure': self._source.source_closure_digest, 'objects': checked}
            if self._g05_effort:
                self._build_layout_facts['native_effort_mode'] = copy.deepcopy(
                    self._simple_effort_drive_receipt
                )
            if self._observer_stage_time_range_receipt is not None:
                self._build_layout_facts['observer_stage_time_range'] = dict(
                    self._observer_stage_time_range_receipt
                )
            if self._observer_render_light_receipt is not None:
                self._build_layout_facts['observer_render_light'] = dict(
                    self._observer_render_light_receipt
                )
            if self._f06_pickcube:
                self._build_layout_facts['sdk_identity'] = dict(self._app_owner.sdk_identity)
                self._build_layout_facts['sdk_runtime_version_raw'] = list(self._app_owner.sdk_runtime_version_raw)
                from isaacsim.core.experimental.utils import backend as backend_utils
                with backend_utils.use_backend('tensor', raise_on_fallback=True):
                    self._build_layout_facts['physical_model'] = _read_f06_public_physical_model(
                        self._articulation, self._free_views)
                link_names = tuple(self._articulation.link_names)
                link_paths = self._articulation.link_paths
                if len(link_paths) != 1 or len(link_paths[0]) != len(link_names):
                    raise ValueError('public Isaac articulation link paths do not match link names')
                # Capture the actual solver Jacobian and link-frame poses at
                # the same bootstrap boundary. This is a read-only model
                # witness; it neither advances physics nor treats USD axes as
                # if they were runtime solver output.
                with backend_utils.use_backend('tensor', raise_on_fallback=True):
                    import numpy as np
                    before_kinematic = (int(SimulationManager.get_num_physics_steps()),
                                        float(SimulationManager.get_simulation_time()))
                    jacobian = np.asarray(self._articulation.get_jacobian_matrices().numpy(), dtype=np.float64)
                    if (jacobian.ndim != 4 or jacobian.shape[0] != 1
                            or jacobian.shape[1] not in (len(link_names) - 1, len(link_names))
                            or jacobian.shape[2] != 6
                            or jacobian.shape[3] not in (len(self._dof_names), len(self._dof_names) + 6)
                            or not np.isfinite(jacobian).all()):
                        raise ValueError(f'public Isaac Jacobian has unexpected shape or values: {jacobian.shape}')
                    tensor_view = SimulationManager.get_physics_simulation_view()
                    if tensor_view is None:
                        raise ValueError('public Isaac physics tensor simulation view is unavailable')
                    link_pose_rows = []
                    for link_name, link_path in zip(link_names, link_paths[0], strict=True):
                        # RigidPrim's constructor can author optional PhysX
                        # APIs. A tensor-only view keeps this readback from
                        # changing the source stage or provider model.
                        link_view = tensor_view.create_rigid_body_view(str(link_path))
                        transform = np.asarray(link_view.get_transforms().numpy(), dtype=np.float64)
                        if transform.shape != (1, 7) or not np.isfinite(transform).all():
                            raise ValueError(f'public Isaac link tensor pose unavailable: {link_name}')
                        position = transform[0, :3].tolist()
                        orientation = transform[0, [6, 3, 4, 5]].tolist()
                        link_pose_rows.append({'name': str(link_name), 'path': str(link_path),
                                               'position_world_m': list(position),
                                               'orientation_world_wxyz': list(orientation)})
                    after_kinematic = (int(SimulationManager.get_num_physics_steps()),
                                       float(SimulationManager.get_simulation_time()))
                    if after_kinematic != before_kinematic:
                        raise RuntimeError('public Isaac model readback advanced physics')
                    self._build_layout_facts['native_kinematic_model_witness'] = {
                        'schema_version': 'isaac-public-kinematic-model-witness-v1',
                        'provenance': 'native_effective_public_tensor',
                        'sample_phase': 'physics_bootstrap_before_reset',
                        'link_order': list(link_names), 'dof_order': list(self._dof_names),
                        'link_world_poses': link_pose_rows, 'jacobian': jacobian[0].tolist(),
                        'jacobian_shape': list(jacobian.shape),
                        'before_counter': list(before_kinematic), 'after_counter': list(after_kinematic),
                        'physics_step_index': int(SimulationManager.get_num_physics_steps()),
                        'simulation_time_s': float(SimulationManager.get_simulation_time()),
                    }
                self._build_layout_facts['native_joint_axis_witness'] = _verify_f06_public_joint_axes(
                    self._stage, UsdPhysics, self._build_layout_facts['native_kinematic_model_witness'])
                mass_paths = {f'link:{name}': str(path) for name, path in zip(link_names, link_paths[0], strict=True)}
                mass_paths.update({semantic: _native_prim_path(self._source.bodies[semantic], entry_prim)
                                   for semantic in self._free_views})
                self._build_layout_facts['authored_usd_mass_properties'] = _read_f06_authored_mass_properties(
                    self._stage, mass_paths, UsdPhysics)
            self._metadata = NativeRuntimeIOMetadataV1(
                "native-runtime-io-metadata-v1", self._source.source_id,
                self._source.source_closure_digest, self._source.scene_definition.identity_hash,
                self._artifact.identity_hash, self._execution.identity_hash,
                "isaacsim", ("isaacsim-" + self._app_owner.sdk_identity['normalized_version']
                             if self._f06_pickcube else "isaacsim-6.2.0.0"), "cuda", "cuda:0", "best_effort",
                float(self._artifact.timebase.physics_dt),
                int(self._artifact.timebase.control_substeps), self._dof_names,
                self._position_limits,
            )
            if self._f06_pickcube:
                from .leaf_control import compile_isaac_native_mimic_position_receipt_v1

                witness = self._verify_public_drives(route='f06')
                self.drive_receipt = compile_isaac_native_mimic_position_receipt_v1(
                    execution=self._execution, source=self._source,
                    native_metadata=self._metadata,
                    writer_id='panda-v1/position-servo-v1',
                    native_drive_witness=witness,
                    provenance_kind='native_runtime',
                )
                self._bootstrap_receipt['native_mimic_drive_witness'] = witness
                self._bootstrap_receipt['native_adaptation_receipt'] = self.drive_receipt.to_mapping()
                self._build_layout_facts['native_public_bootstrap_receipt'] = copy.deepcopy(self._bootstrap_receipt)
                self._build_layout_facts['native_runtime_metadata'] = self._metadata.to_mapping()
            self._build_layout_facts['native_public_bootstrap_receipt'] = copy.deepcopy(self._bootstrap_receipt)
            self._build_layout_facts['native_runtime_metadata'] = self._metadata.to_mapping()
            self._manager = SimulationManager
        except BaseException as primary:
            import gc
            import traceback

            # Constructor failures happen before RuntimeSession can attach the
            # adapter to Env. Preserve the scalar startup receipt on the
            # exception so the production runner can write it after cleanup.
            primary._g05_startup_observation = dict(self._startup_observation)
            original_traceback = "".join(traceback.format_exception(
                type(primary), primary, primary.__traceback__,
            ))
            # Failed construction can keep CUDA/Warp views alive through the
            # traceback. Detach it and release views before closing Kit.
            primary.__traceback__ = None
            self._free_views.clear()
            self._f06_robot_contact_views = {}
            self._frame_views.clear()
            self._frame_local_poses.clear()
            self._frame_pose_readback_receipts.clear()
            self._body_views.clear()
            self._articulation = None
            self._physics_scene = None
            self._manager = None
            self._torch = None
            self._stage = None
            gc.collect()
            if original_traceback:
                primary.add_note("Original Isaac adapter startup traceback:\n" + original_traceback)
            for label, cleanup in (
                ("USD stage close", lambda: self._context.close_stage() if self._context is not None else None),
                ("USD snapshot lease close", self._lease.close),
                ("Isaac App owner close", self._app_owner.close),
            ):
                try:
                    cleanup()
                except BaseException as cleanup_error:
                    primary.add_note(f"{label} after adapter startup failure also failed: "
                                     f"{type(cleanup_error).__name__}: {cleanup_error}")
            raise primary.with_traceback(None)



    def _read_f06_robot_contact_witness(self):
        """Read bounded public contacts for every source robot body after a step."""
        views = getattr(self, '_f06_robot_contact_views', None)
        if not views:
            raise RuntimeError('F06 robot contact reporters are unavailable')
        rows = []
        for path, view in sorted(views.items()):
            result = view.get_raw_contact_data(dt=float(self._artifact.timebase.physics_dt))
            if type(result) is not tuple or len(result) != 7:
                raise ValueError('F06 public robot contact result has unexpected shape')
            counts, starts = result[4].numpy().tolist(), result[5].numpy().tolist()
            if len(counts) != 1 or len(starts) != 1:
                raise ValueError('F06 contact reporter does not represent one robot body')
            count, start = int(counts[0]), int(starts[0])
            if count < 0 or count >= 64 or start < 0:
                raise ValueError('F06 robot contact reporter is invalid or at capacity')
            rows.append({'body_path': path, 'count': count})
        cube_view = self._free_views.get('cube-v1')
        if cube_view is None:
            raise ValueError('F06 contact diagnostic lacks its known cube body')
        cube_result = cube_view.get_raw_contact_data(dt=float(self._artifact.timebase.physics_dt))
        if type(cube_result) is not tuple or len(cube_result) != 7:
            raise ValueError('F06 public cube contact result has unexpected shape')
        cube_counts, cube_starts = cube_result[4].numpy().tolist(), cube_result[5].numpy().tolist()
        if len(cube_counts) != 1 or len(cube_starts) != 1:
            raise ValueError('F06 cube contact reporter does not represent one body')
        cube_count, cube_start = int(cube_counts[0]), int(cube_starts[0])
        if cube_count < 0 or cube_count >= 64 or cube_start < 0:
            raise ValueError('F06 cube contact reporter is invalid or at capacity')
        cube_actor_paths = (cube_view.get_actor_paths_from_ids(
            cube_result[6].to('cpu')[cube_start:cube_start + cube_count]) if cube_count else [])
        if len(cube_actor_paths) != cube_count:
            raise ValueError('F06 cube contact actor paths do not cover the raw contacts')
        return {'schema_version': 'f06-public-robot-contact-witness-v1',
                'known': True, 'capacity_per_body': 64, 'rows': rows,
                'total_contacts': sum(row['count'] for row in rows),
                'cube_contact_count': cube_count, 'cube_contact_actor_paths': list(cube_actor_paths)}


    def _verify_native_mimic_profile(self, PhysxSchema, UsdPhysics, *, route: str) -> None:
        """Verify the shared Panda mimic relation with route-owned drive settings."""
        if route != 'f06' or not self._f06_pickcube or self._stage is None:
            raise RuntimeError('F06 native mimic requires its exact composed USD stage')
        label, entity_id = 'F06', 'panda-v1'
        leader_drive = ('force', 5000.0, 120.0, 5.0)

        import xml.etree.ElementTree as ET

        finger_joints = ('finger_joint1', 'finger_joint2')
        if {self._source.joints.get(f'{entity_id}/{name}') for name in finger_joints} != set(finger_joints):
            raise ValueError(f'{label} RuntimeSource does not bind the exact finger Joint pair')
        source_xml = self._source.scene_source.loaded_delivery.source_input_bytes.get('panda.xml')
        if type(source_xml) is not bytes:
            raise ValueError(f'{label} source delivery omits the original Panda XML bytes')
        source_xml_sha256 = hashlib.sha256(source_xml).hexdigest()
        equalities = ET.fromstring(source_xml).findall('./equality/joint')
        if len(equalities) != 1:
            raise ValueError(f'{label} source must contain exactly one finger equality')
        equality = equalities[0]
        polycoef = tuple(float(value) for value in equality.get('polycoef', '0 1 0 0 0').split())
        if ((equality.get('joint1'), equality.get('joint2'), equality.get('active', 'true'))
                != ('finger_joint1', 'finger_joint2', 'true')
                or polycoef != (0.0, 1.0, 0.0, 0.0, 0.0)):
            raise ValueError(f'{label} source must retain its exact active affine finger relation')

        matches = {name: [] for name in finger_joints}
        for prim in self._stage.Traverse():
            if prim.GetName() in matches and prim.IsA(UsdPhysics.PrismaticJoint):
                matches[prim.GetName()].append(prim)
        if any(len(rows) != 1 for rows in matches.values()):
            raise ValueError(f'{label} source must compose exactly one public prismatic prim per finger Joint')
        reference, follower = matches['finger_joint1'][0], matches['finger_joint2'][0]
        if not follower.HasAPI(PhysxSchema.PhysxMimicJointAPI, 'transX'):
            raise ValueError(f'{label} source-derived PhysxMimicJointAPI is absent from the composed delivery')
        relationship = follower.GetRelationship('physxMimicJoint:transX:referenceJoint')
        if not relationship or relationship.GetTargets() != [reference.GetPath()]:
            raise ValueError(f'{label} native mimic reference differs from the source finger equality')
        for name, expected in (('gearing', 1.0), ('offset', 0.0)):
            attribute = follower.GetAttribute(f'physxMimicJoint:transX:{name}')
            if not attribute or not attribute.IsValid() or not math.isclose(
                    float(attribute.Get()), expected, rel_tol=0.0, abs_tol=1e-6):
                raise ValueError(f'{label} authored mimic {name} differs from its exact affine source relation')
        frequency_attr = follower.GetAttribute('physxMimicJoint:transX:naturalFrequency')
        damping_attr = follower.GetAttribute('physxMimicJoint:transX:dampingRatio')
        if not frequency_attr or not frequency_attr.IsValid() or not damping_attr or not damping_attr.IsValid():
            raise ValueError(f'{label} authored PhysX mimic omits its native profile attributes')
        if (frequency_attr.Set(25.0) is False or damping_attr.Set(1.0) is False
                or not math.isclose(float(frequency_attr.Get()), 25.0, rel_tol=0.0, abs_tol=1e-6)
                or not math.isclose(float(damping_attr.Get()), 1.0, rel_tol=0.0, abs_tol=1e-6)):
            raise ValueError(f'{label} native PhysX mimic profile could not be authored/read back')

        drive_exists = reference.HasAPI(UsdPhysics.DriveAPI, 'linear')
        if not drive_exists:
            raise ValueError('F06 source-bound leader DriveAPI is absent from the desktop USD')
        drive = UsdPhysics.DriveAPI(reference, 'linear')
        actual_drive = (
            str(drive.GetTypeAttr().Get()), float(drive.GetStiffnessAttr().Get()),
            float(drive.GetDampingAttr().Get()), float(drive.GetMaxForceAttr().Get()),
        )
        if (actual_drive[0] != leader_drive[0]
                or any(not math.isclose(actual_drive[index], leader_drive[index], rel_tol=0.0, abs_tol=1e-6)
                       for index in range(1, 4))):
            raise ValueError(f'{label} source-bound leader drive differs from its exact profile: {actual_drive!r}')

        self._f06_native_mimic_receipt = {
            'schema_version': 'isaac-f06-pickcube-native-mimic-stage-receipt-v1',
            'source_xml_sha256': source_xml_sha256,
            'source_polycoef': polycoef,
            'follower_path': str(follower.GetPath()), 'reference_path': str(reference.GetPath()),
            'native_mimic_api': 'PhysxMimicJointAPI:transX',
            'mimic_frequency_hz': float(frequency_attr.Get()),
            'mimic_damping_ratio': float(damping_attr.Get()),
            'leader_drive_api': 'PhysicsDriveAPI:linear',
            'leader_stiffness_N_m': actual_drive[1], 'leader_damping_N_s_m': actual_drive[2],
            'leader_max_force_N': actual_drive[3],
            'runtime_stage_mutated_for_native_mimic_profile': True,
        }

    def _verify_public_drives(self, *, route: str) -> dict[str, object]:
        """Check the shared seven-arm/one-leader surface against its exact profile."""
        if route == 'f06':
            if (not self._f06_pickcube or self._stage is None
                    or self._f06_native_mimic_receipt is None):
                raise RuntimeError('F06 source-bound mimic/drive profile was not initialized')
            label = 'F06'
            schema_version = 'isaac-f06-pickcube-native-mimic-drive-witness-v1'
            arm_expected = {
                'joint1': (4500.0, 450.0, 250.0),
                'joint2': (4500.0, 450.0, 250.0),
                'joint3': (3500.0, 350.0, 250.0),
                'joint4': (3500.0, 350.0, 250.0),
                'joint5': (2000.0, 200.0, 250.0),
                'joint6': (2000.0, 200.0, 250.0),
                'joint7': (2000.0, 200.0, 250.0),
            }
            leader_expected = (5000.0, 120.0, 5.0)
        else:
            raise ValueError(f'unsupported Isaac public-drive route: {route!r}')

        authored = []
        for prim in self._stage.Traverse():
            for schema in prim.GetAppliedSchemas():
                if str(schema).startswith('PhysicsDriveAPI:'):
                    authored.append((str(prim.GetPath()), str(prim.GetName()), str(schema)))
        expected_apis = {f'joint{index}': 'PhysicsDriveAPI:angular' for index in range(1, 8)}
        expected_apis['finger_joint1'] = 'PhysicsDriveAPI:linear'
        authored_apis = {name: schema for _path, name, schema in authored}
        if len(authored) != 8 or authored_apis != expected_apis:
            raise ValueError(
                f'{label} composed stage must expose seven Arm drives and one leader-finger drive'
            )

        stiffness_tensor, damping_tensor = self._articulation.get_dof_gains()
        stiffness = _tensor_rows(
            stiffness_tensor, width=len(self._dof_names), label=f'{label} public stiffness',
        )[0]
        damping = _tensor_rows(
            damping_tensor, width=len(self._dof_names), label=f'{label} public damping',
        )[0]
        effort_rows = self._articulation.get_dof_max_efforts().numpy().tolist()
        if effort_rows and not isinstance(effort_rows[0], (tuple, list)):
            effort_rows = [effort_rows]
        if not effort_rows or len(effort_rows[0]) != len(self._dof_names):
            raise ValueError(f'{label} public maximum-effort view has unexpected shape')
        max_effort = tuple(float(value) for value in effort_rows[0])
        drive_rows = self._articulation.get_dof_drive_types()
        if not drive_rows or len(drive_rows[0]) != len(self._dof_names):
            raise ValueError(f'{label} public drive-type view has unexpected shape')
        drive_types = tuple(None if value is None else str(value).lower() for value in drive_rows[0])

        values = {}
        for native_name, index in self._dof_index.items():
            actual = (stiffness[index], damping[index], max_effort[index], drive_types[index])
            if native_name in arm_expected:
                wanted = (*arm_expected[native_name], 'force')
                if (any(not math.isclose(actual[i], wanted[i], rel_tol=0.0, abs_tol=1e-4)
                        for i in range(3)) or actual[3] != wanted[3]):
                    raise ValueError(
                        f'{label} public Arm drive differs from its exact profile: '
                        f'{native_name}={actual!r}'
                    )
            elif native_name == 'finger_joint1':
                wanted = (*leader_expected, 'force')
                if (any(not math.isclose(actual[i], wanted[i], rel_tol=0.0, abs_tol=1e-4)
                        for i in range(3)) or actual[3] != wanted[3]):
                    raise ValueError(f'{label} active leader drive differs from its exact profile: {actual!r}')
            elif (not math.isclose(actual[0], 0.0, rel_tol=0.0, abs_tol=1e-8)
                    or not math.isclose(actual[1], 0.0, rel_tol=0.0, abs_tol=1e-8)
                    or actual[3] not in (None, 'none')):
                raise ValueError(f'{label} mimic follower has a duplicate articulation drive: {actual!r}')
            values[native_name] = {
                'stiffness': actual[0], 'damping': actual[1],
                'max_effort': actual[2], 'drive_type': actual[3],
            }

        return {
            'schema_version': schema_version,
            'native_dof_order': list(self._dof_names),
            'active_drive_dofs': [f'joint{index}' for index in range(1, 8)] + ['finger_joint1'],
            'passive_mimic_dof': 'finger_joint2',
            'leader_stiffness_N_m': leader_expected[0],
            'leader_damping_N_s_m': leader_expected[1],
            'leader_max_effort_N': leader_expected[2],
            'leader_drive_type': 'force',
            'follower_stiffness_N_m': 0.0,
            'follower_damping_N_s_m': 0.0,
            'follower_drive_type': 'none',
            'mimic_api': 'PhysxMimicJointAPI:transX',
            'drive_api': 'PhysicsDriveAPI:linear',
            'mimic_reference_joint': 'finger_joint1',
            'mimic_follower_joint': 'finger_joint2',
            'mimic_gearing': 1.0,
            'mimic_offset_m': 0.0,
            'mimic_natural_frequency_hz': 25.0,
            'mimic_damping_ratio': 1.0,
            'passive_mimic_constraint_authored': True,
            'public_consumers': values,
            'authored_drive_apis': [
                {'path': path, 'joint': name, 'api': schema}
                for path, name, schema in sorted(authored)
            ],
        }

    @property
    def build_layout_facts(self):
        import copy
        return copy.deepcopy(self._build_layout_facts)

    def metadata(self) -> NativeRuntimeIOMetadataV1:
        if self._closed or self._metadata is None:
            raise RuntimeError("Isaac native I/O is closed or not materialized")
        return self._metadata

    def bootstrap_receipt(self) -> Mapping[str, object]:
        """Return measured public Kit/view bootstrap facts for the worker ledger."""
        if (self._closed or self._bootstrap_receipt is None
                or self._bootstrap_receipt.get("status") != "complete"):
            raise RuntimeError("Isaac bootstrap receipt is unavailable before native materialization")
        return dict(self._bootstrap_receipt)

    def _sync(self) -> None:
        # A CUDA synchronization is a read/write barrier; it is not a physics step.
        self._torch.cuda.synchronize(0)

    def _counter(self) -> tuple[int, float]:
        return (int(self._manager.get_num_physics_steps()),
                float(self._manager.get_simulation_time()))

    def _prepare_task_rgb_render_stage(self):
        """Prepare only the live USD stage for task RGB, preserving source bytes and physics."""
        import copy
        import omni.timeline
        from pxr import Gf, Sdf, UsdLux

        if self._task_renderer_stage_preparation is not None:
            return copy.deepcopy(self._task_renderer_stage_preparation)
        if self._stage is None or self._manager is None:
            raise RuntimeError('task RGB stage preparation requires the live source stage and manager')
        timeline = omni.timeline.get_timeline_interface()
        if timeline.is_playing():
            raise RuntimeError('task RGB stage preparation requires the existing timeline to be paused')
        before = self._counter()
        timeline_before_s = float(timeline.get_current_time())
        stage_id = int(self._context.get_stage_id())

        reused_observer_preparation = (
            self._observer_stage_time_range_receipt is not None
            and self._observer_render_light_receipt is not None
        )
        if not reused_observer_preparation:
            start_time_code = float(self._stage.GetStartTimeCode())
            source_end_time_code = float(self._stage.GetEndTimeCode())
            end_time_code = source_end_time_code
            extended = end_time_code <= start_time_code
            if extended:
                # RTX annotators need a non-degenerate playback range for a
                # static source. This touches only the disposable live stage;
                # the verified USD closure is never saved or rewritten.
                end_time_code = start_time_code + 1.0
                self._stage.SetEndTimeCode(end_time_code)
            self._observer_stage_time_range_receipt = {
                'schema_version': 'isaac-task-rgb-stage-time-range-v1',
                'source_start_time_code': start_time_code,
                'source_end_time_code': source_end_time_code,
                'effective_start_time_code': start_time_code,
                'effective_end_time_code': end_time_code,
                'extended_in_memory': extended,
                'time_codes_per_second': float(self._stage.GetTimeCodesPerSecond()),
                'frames_per_second': float(self._stage.GetFramesPerSecond()),
                'stage_saved': False,
            }

            light_paths = sorted(
                str(prim.GetPath()) for prim in self._stage.Traverse()
                if prim.HasAPI(UsdLux.LightAPI)
            )
            added_light_path = None
            if not light_paths:
                added_light_path = '/GeoChoraObserverEnvironmentLight'
                existing = self._stage.GetPrimAtPath(added_light_path)
                if existing and existing.IsValid():
                    if not existing.HasAPI(UsdLux.LightAPI):
                        raise RuntimeError(
                            'task RGB renderer-light path is occupied by a non-light prim'
                        )
                    light_paths.append(added_light_path)
                    added_light_path = None
                else:
                    dome = UsdLux.DomeLight.Define(self._stage, Sdf.Path(added_light_path))
                    if not dome or not dome.GetPrim().IsValid():
                        raise RuntimeError('task RGB could not define its renderer-only dome light')
                    dome.GetIntensityAttr().Set(1000.0)
                    dome.GetColorAttr().Set(Gf.Vec3f(1.0, 1.0, 1.0))
            self._observer_render_light_receipt = {
                'schema_version': 'isaac-task-rgb-render-light-v1',
                'source_light_paths': sorted(light_paths),
                'added_light_path': added_light_path,
                'added_light_type': 'UsdLux.DomeLight' if added_light_path else None,
                'added_light_intensity': 1000.0 if added_light_path else None,
                'added_light_color_linear_rgb': [1.0, 1.0, 1.0] if added_light_path else None,
                'stage_saved': False,
            }

        after = self._counter()
        timeline_after_s = float(timeline.get_current_time())
        if (after != before or timeline.is_playing()
                or not math.isclose(timeline_before_s, timeline_after_s, rel_tol=0.0, abs_tol=1e-12)
                or int(self._context.get_stage_id()) != stage_id):
            self._observer_runtime_invalid = True
            owner = getattr(self, '_app_owner', None)
            if owner is not None:
                owner.invalidate_runtime('task RGB renderer-stage preparation changed the live runtime clock')
            raise RuntimeError('task RGB renderer-stage preparation changed physics, timeline, or stage identity')

        self._task_renderer_stage_preparation = {
            'schema_version': 'isaac-task-rgb-render-stage-preparation-v1',
            'purpose': 'source-bound task RGB only; no physics owner created',
            'stage_id': stage_id,
            'physics_counter_before': {'step': before[0], 'time_s': before[1]},
            'physics_counter_after': {'step': after[0], 'time_s': after[1]},
            'timeline_time_before_s': timeline_before_s,
            'timeline_time_after_s': timeline_after_s,
            'timeline_remained_paused': True,
            'reused_observer_preparation': reused_observer_preparation,
            'stage_time_range': copy.deepcopy(self._observer_stage_time_range_receipt),
            'render_light': copy.deepcopy(self._observer_render_light_receipt),
            'source_closure_digest': self._source.source_closure_digest,
            'source_bytes_modified': False,
            'stage_saved': False,
        }
        if isinstance(getattr(self, '_build_layout_facts', None), dict):
            self._build_layout_facts['task_rgb_render_stage_preparation'] = copy.deepcopy(
                self._task_renderer_stage_preparation
            )
        return copy.deepcopy(self._task_renderer_stage_preparation)

    def write_reset(self, sample: ResetSample,
                    position_targets: tuple[tuple[int, str, float], ...]) -> NativeResetWriteReceiptV1:
        if self._closed:
            raise RuntimeError("Isaac native I/O is closed")
        if getattr(self, '_observer_runtime_invalid', False):
            raise RuntimeError('Isaac runtime was invalidated after the native clock regressed; rebuild required')
        sample.validate()
        if set(sample.joint_position) != set(self._source.joints):
            raise ValueError("reset joint sample differs from exact USD RuntimeSource mapping")
        expected_targets = tuple(sorted(position_targets))
        # Provider-free F04 boundary tests construct this adapter with
        # ``__new__`` to exercise reset behavior without opening Isaac.
        f06_pickcube = getattr(self, "_f06_pickcube", False)
        g05_effort = getattr(self, "_g05_effort", False)
        if g05_effort:
            valid_targets = not expected_targets
        elif f06_pickcube:
            expected_active_names = {f'joint{index}' for index in range(1, 8)} | {'finger_joint1'}
            valid_targets = (
                len(expected_targets) == 8
                and {item[1] for item in expected_targets} == expected_active_names
                and len({item[0] for item in expected_targets}) == 8
                and all(item[0] == self._dof_index.get(item[1]) for item in expected_targets)
            )
        else:
            valid_targets = (
                len(expected_targets) == 9
                and tuple(item[1] for item in expected_targets)
                == tuple(self._dof_names[index] for index, _name, _value in expected_targets)
                and tuple(item[0] for item in expected_targets) == tuple(range(9))
            )
        if not valid_targets:
            raise ValueError("reset targets differ from actual post-materialization DOF metadata")
        written_joints: list[str] = []
        written_free: list[str] = []
        attempted = 0
        before = self._counter()
        try:
            positions = [0.0] * len(self._dof_names)
            for semantic, native in self._source.joints.items():
                if native not in self._dof_index:
                    raise ValueError(f"source Joint name is absent from actual articulation metadata: {native}")
                positions[self._dof_index[native]] = float(sample.joint_position[semantic])
            attempted = len(self._dof_names)
            self._articulation.set_dof_positions(positions)
            written_joints.extend(self._source.joints)
            velocities = [0.0] * len(self._dof_names)
            if g05_effort:
                for semantic, native in self._source.joints.items():
                    velocities[self._dof_index[native]] = float(sample.joint_velocity[semantic])
            self._articulation.set_dof_velocities(velocities)
            if f06_pickcube:
                self._articulation.set_dof_position_targets(
                    [item[2] for item in expected_targets],
                    dof_indices=[int(item[0]) for item in expected_targets],
                )
                target_readback = _tensor_rows(
                    self._articulation.get_dof_position_targets(
                        dof_indices=[int(item[0]) for item in expected_targets],
                    ),
                    width=8, label='F06'
                    + ' reset active position-target readback',
                )[0]
                if any(not math.isclose(actual, item[2], rel_tol=0.0, abs_tol=1e-6)
                       for actual, item in zip(target_readback, expected_targets, strict=True)):
                    raise ValueError('native mimic reset target readback differs from the source-bound adaptation')
                leader_index = self._dof_index['finger_joint1']
                self._articulation.set_dof_efforts([0.0], dof_indices=[leader_index])
                finger_entity = next(
                    name.split('/', 1)[0] for name in sample.joint_position
                    if name.endswith('/finger_joint1')
                )
                self._last_native_mimic_target = {
                    'target_identity_sha256': None,
                    'drive_receipt_identity_sha256': self.drive_receipt.identity_sha256,
                    'reference_target_m': float(
                        sample.joint_position[f'{finger_entity}/finger_joint1']
                    ),
                }
            elif not g05_effort:
                self._articulation.set_dof_position_targets([item[2] for item in expected_targets])
            else:
                self._articulation.set_dof_efforts([0.0] * len(self._dof_names))
            for semantic, pose in sample.poses_world.items():
                view = self._free_views.get(semantic)
                if view is None:
                    raise ValueError(f"reset pose has no declared public free-body view: {semantic}")
                view.set_world_poses(positions=pose.position, orientations=pose.quaternion_wxyz)
                view.set_velocities(linear_velocities=(0.0, 0.0, 0.0),
                                    angular_velocities=(0.0, 0.0, 0.0))
                written_free.append(semantic)
            self._sync()
            simulation_view = self._manager.get_physics_simulation_view()
            if simulation_view is None:
                raise RuntimeError("public Isaac physics simulation view is unavailable for reset refresh")
            refresh = getattr(simulation_view, "update_articulations_kinematic", None)
            if not callable(refresh):
                raise RuntimeError("public Isaac simulation view lacks articulation kinematic refresh")
            refresh_result = refresh()
            if refresh_result is False:
                raise RuntimeError("public Isaac articulation kinematic refresh reported failure")
            self._sync()
            after = self._counter()
            if after != before:
                raise RuntimeError(
                    "public Isaac reset setters/kinematic refresh advanced physics or changed time: "
                    f"before={before!r}, after={after!r}"
                )
            self._episode_origin_step, self._episode_origin_time = after
            self._native_step_count = 0
            self._last_reset_refresh_receipt = {
                "api": "SimulationManager.get_physics_simulation_view().update_articulations_kinematic",
                "step_index_before": before[0], "step_index_after": after[0],
                "simulation_time_before_s": before[1], "simulation_time_after_s": after[1],
                "refresh_return": refresh_result,
                "physics_advanced": False,
            }
            return NativeResetWriteReceiptV1(
                "native-reset-write-receipt-v1", sample.sample_id,
                tuple(sorted(written_joints)), tuple(sorted(written_free)),
                tuple(item[1] for item in expected_targets), not g05_effort, False,
            )
        except BaseException as error:
            error.add_note(
                "Isaac reset may have partially applied; no physical rollback is claimed. "
                f"joint writes={written_joints!r}, free-body writes={written_free!r}, "
                f"target channels attempted={attempted}/{len(self._dof_names)}."
            )
            raise

    def _read_views(self) -> tuple[dict[str, float], dict[str, float], dict[str, PoseWorld],
                                    dict[str, PublicRigidBodyReadbackV1]]:
        q = _tensor_rows(self._articulation.get_dof_positions(), width=len(self._dof_names),
                         label="DOF position")[0]
        qd = _tensor_rows(self._articulation.get_dof_velocities(), width=len(self._dof_names),
                          label="DOF velocity")[0]
        joints = {semantic: q[self._dof_index[native]] for semantic, native in self._source.joints.items()}
        velocities = {semantic: qd[self._dof_index[native]] for semantic, native in self._source.joints.items()}
        frame_poses = {}
        for semantic, view in self._frame_views.items():
            p, q_wxyz = _pose_from_view(view)
            local_pose = self._frame_local_poses.get(semantic)
            if local_pose is not None:
                p, q_wxyz = _compose_world_pose(
                    p, q_wxyz, local_pose.position, local_pose.quaternion_wxyz,
                )
            frame_poses[semantic] = PoseWorld(p, q_wxyz)
        free_readbacks = {}
        for semantic, view in self._free_views.items():
            p, q_wxyz = _pose_from_view(view)
            linear, angular = view.get_velocities()
            v = _tensor_rows(linear, width=3, label="COM linear velocity")[0]
            w = _tensor_rows(angular, width=3, label="angular velocity")[0]
            com_positions_body, _com_orientations_body = view.get_coms()
            p_com_body = _tensor_rows(
                com_positions_body, width=3, label="body-local COM position",
            )[0]
            # Isaac 6.2's public Tensor RigidPrim.get_coms() returns the COM
            # pose relative to the rigid-body-prim frame, already in body axes.
            com = _body_local_com_offset_from_public_tensor_pose(p_com_body)
            frame = self._artifact.legacy_frame_bindings[semantic]
            free_readbacks[semantic] = PublicRigidBodyReadbackV1(
                "public-rigid-body-readback-v1", frame,
                p, q_wxyz, tuple(float(x) for x in com), v, w, "world", "center_of_mass",
            )
        return joints, velocities, frame_poses, free_readbacks

    def read_state(self) -> NativeRuntimeReadbackV1:
        if self._closed or self._episode_origin_step is None:
            raise RuntimeError("Isaac state read requires an active reset episode")
        self._sync()
        before = self._counter()
        joints, velocities, frames, free = self._read_views()
        after = self._counter()
        if before != after:
            raise RuntimeError("public Isaac state read advanced physics or changed its counter")
        assert self._episode_origin_time is not None
        return NativeRuntimeReadbackV1(
            "native-runtime-readback-v1", joints, velocities, frames, free,
            max(0.0, after[1] - self._episode_origin_time),
        )

    def write_position_targets(self, target_identity_sha256: str,
                               targets: tuple[tuple[int, str, float], ...]) -> NativePositionWriteAckV1:
        if self._closed:
            raise RuntimeError("Isaac native I/O is closed")
        if getattr(self, '_g05_effort', False):
            raise RuntimeError('G05 simple-effort route does not admit position target writes')
        ordered = tuple(sorted(targets))
        f06_pickcube = getattr(self, "_f06_pickcube", False)
        if f06_pickcube:
            expected_active_names = {f'joint{index}' for index in range(1, 8)} | {'finger_joint1'}
            valid_targets = (
                len(ordered) == 8
                and {item[1] for item in ordered} == expected_active_names
                and len({item[0] for item in ordered}) == 8
                and all(item[0] == self._dof_index.get(item[1]) for item in ordered)
            )
        else:
            valid_targets = (
                len(ordered) == 9 and tuple(item[0] for item in ordered) == tuple(range(9))
                and tuple(item[1] for item in ordered) == self._dof_names
            )
        if not valid_targets:
            raise ValueError("Position Target names/index order differ from actual Isaac metadata")
        attempted = 0
        try:
            attempted = len(ordered)
            self._articulation.set_dof_position_targets(
                [float(item[2]) for item in ordered],
                dof_indices=[int(item[0]) for item in ordered],
            )
            self._sync()
            applied_values = tuple(float(item[2]) for item in ordered)
            if f06_pickcube:
                label = 'F06'
                target_readback = _tensor_rows(
                    self._articulation.get_dof_position_targets(
                        dof_indices=[int(item[0]) for item in ordered],
                    ),
                    width=len(ordered), label=f'{label} public position-target readback',
                )[0]
                if any(not math.isclose(actual, item[2], rel_tol=0.0, abs_tol=1e-6)
                       for actual, item in zip(target_readback, ordered, strict=True)):
                    raise ValueError(f'{label} public Articulation position-target readback differs from its admitted target')
                applied_values = tuple(float(value) for value in target_readback)
            if f06_pickcube:
                leader_index = next(index for index, item in enumerate(ordered)
                                    if item[1] == 'finger_joint1')
                self._last_native_mimic_target = {
                    'target_identity_sha256': target_identity_sha256,
                    'drive_receipt_identity_sha256': self.drive_receipt.identity_sha256,
                    'reference_target_m': float(applied_values[leader_index]),
                }
            return NativePositionWriteAckV1(
                "native-position-write-ack-v1", target_identity_sha256,
                tuple(item[1] for item in ordered), applied_values,
                False, attempted,
            )
        except BaseException as error:
            error.add_note(
                f"Position target setter failed after attempting {attempted}/{len(ordered)} channels; "
                "no physical rollback is claimed."
            )
            raise


    def disable_f06_physical_drives(self):
        """Disable implicit PD through the public tensor API for the exact fixture."""
        if (self._closed or not self._f06_pickcube or self._artifact.artifact_id
                != 'pickcube-f06-physical-effort-no-drive-v1'
                or getattr(self, '_physical_drives_disabled', False)):
            raise ValueError('native drive isolation requires the exact fresh F06 fixture')
        from isaacsim.core.experimental.utils import backend as backend_utils
        names = tuple(f'joint{i}' for i in range(1, 8)) + ('finger_joint1',)
        indices = [self._dof_index[name] for name in names]
        with backend_utils.use_backend('tensor', raise_on_fallback=True):
            before_stiffness, before_damping = self._articulation.get_dof_gains()
            before = {'stiffness': list(_tensor_rows(before_stiffness, width=len(self._dof_names), label='F06 pre-isolation stiffness')[0]),
                      'damping': list(_tensor_rows(before_damping, width=len(self._dof_names), label='F06 pre-isolation damping')[0])}
            self._articulation.set_dof_gains([0.0]*8, [0.0]*8, dof_indices=indices, update_default_gains=False)
            self._sync()
            stiffness, damping = self._articulation.get_dof_gains()
            after_stiffness = _tensor_rows(stiffness, width=len(self._dof_names), label='F06 isolated stiffness')[0]
            after_damping = _tensor_rows(damping, width=len(self._dof_names), label='F06 isolated damping')[0]
        if any(abs(after_stiffness[index]) > 1e-8 or abs(after_damping[index]) > 1e-8 for index in indices):
            raise ValueError('F06 public gain readback did not confirm native drive isolation')
        self._physical_drives_disabled = True
        return {'schema_version': 'f06-public-drive-isolation-v1', 'names': list(names),
                'before': before, 'after_stiffness': list(after_stiffness),
                'after_damping': list(after_damping), 'source_usd_modified': False,
                'api': 'Articulation.set_dof_gains tensor'}

    def read_f06_physical_drive_gains(self):
        """Read the live public tensor gains without changing the physics clock."""
        if not getattr(self, '_physical_drives_disabled', False):
            raise RuntimeError('F06 physical drives have not been isolated')
        from isaacsim.core.experimental.utils import backend as backend_utils
        before = self._counter()
        with backend_utils.use_backend('tensor', raise_on_fallback=True):
            stiffness, damping = self._articulation.get_dof_gains()
            result = {'stiffness': list(_tensor_rows(stiffness, width=len(self._dof_names), label='F06 live stiffness')[0]),
                      'damping': list(_tensor_rows(damping, width=len(self._dof_names), label='F06 live damping')[0])}
        if self._counter() != before:
            raise RuntimeError('F06 gain readback advanced physics')
        return result

    def write_physical_effort(self, values):
        """Apply one F06 source-bound effort interval through the public API."""
        import math
        if getattr(self, '_g05_effort', False):
            expected = set(self._dof_names)
            if (self._closed or self._episode_origin_step is None
                    or getattr(self, '_physical_effort_fault', False)
                    or getattr(self, '_physical_effort_pending', None) is not None):
                raise RuntimeError('G05 physical effort requires an available reset interval')
            if (not isinstance(values, dict) or set(values) != expected
                    or any(isinstance(v, bool) or not math.isfinite(float(v))
                           for v in values.values())):
                raise ValueError('G05 physical effort requires every finite named source DOF')
            names = tuple(self._dof_names)
            indices = [self._dof_index[name] for name in names]
            efforts = [float(values[name]) for name in names]
            self._physical_effort_pending = (indices, efforts)
            try:
                self._articulation.set_dof_efforts(efforts, dof_indices=indices)
                self._sync()
                readback = _tensor_rows(
                    self._articulation.get_dof_efforts(dof_indices=indices),
                    width=len(names), label='G05 public effort readback',
                )[0]
                if any(not math.isclose(actual, requested, rel_tol=0.0, abs_tol=1e-5)
                       for actual, requested in zip(readback, efforts, strict=True)):
                    raise RuntimeError('G05 public effort setter readback differs from requested values')
                self._last_effort_write_receipt = {
                    'schema_version': 'g05-public-effort-write-v1',
                    'native_dof_names': list(names),
                    'requested_efforts': list(efforts),
                    'readback_efforts': list(readback),
                    'public_effort_api': 'Articulation.get_dof_efforts',
                }
            except BaseException:
                self._physical_effort_fault = True
                raise
            return
        expected = {f'joint{i}' for i in range(1, 8)} | {'finger_joint1'}
        if (self._closed or self._episode_origin_step is None or not self._f06_pickcube
                or getattr(self, '_physical_effort_fault', False)
                or getattr(self, '_physical_effort_pending', None) is not None):
            raise RuntimeError('F06 physical effort requires an available reset interval')
        if (not isinstance(values, dict) or set(values) != expected
                or any(isinstance(v, bool) or not math.isfinite(float(v)) for v in values.values())):
            raise ValueError('F06 physical effort requires the eight finite named active DOFs')
        names = tuple(f'joint{i}' for i in range(1, 8)) + ('finger_joint1',)
        if any(abs(float(values[name])) > (250.0 if name.startswith('joint') else 5.0)
               for name in names):
            raise ValueError('F06 direct effort exceeds its separately declared bound')
        indices = [self._dof_index[name] for name in names]
        efforts = [float(values[name]) for name in names]
        # Reserve the interval before the setter: it may partially write and
        # still raise, so the Env's abort path must attempt to clear it.
        self._physical_effort_pending = (indices, efforts)
        try:
            self._articulation.set_dof_efforts(efforts, dof_indices=indices)
            self._sync()
        except BaseException:
            self._physical_effort_fault = True
            raise

    def clear_physical_effort(self):
        """Clear the owned direct contribution; a failed clear faults the owner."""
        pending = getattr(self, '_physical_effort_pending', None)
        if pending is None:
            return
        try:
            indices, _efforts = pending
            self._articulation.set_dof_efforts([0.0] * len(indices), dof_indices=indices)
            self._sync()
        except BaseException:
            self._physical_effort_fault = True
            raise
        finally:
            self._physical_effort_pending = None

    def advance(self) -> NativeAdvanceReceiptV1:
        if self._closed or self._episode_origin_step is None:
            raise RuntimeError("Isaac advance requires an active reset episode")
        before = self._counter()
        attempted_index = self._native_step_count + 1
        native_adaptation_application = None
        after_effort_setter = None
        after_effort_sync = None
        after_manager_step = None
        try:
            pending = getattr(self, '_physical_effort_pending', None)
            if pending is not None:
                indices, efforts = pending
                self._articulation.set_dof_efforts(efforts, dof_indices=indices)
                if self._g05_effort:
                    after_effort_setter = self._counter()
                self._sync()
                if self._g05_effort:
                    after_effort_sync = self._counter()
            self._manager.step(steps=1, update_fabric=False)
            after_manager_step = self._counter()
            self._sync()
            if self._g05_effort:
                if pending is None:
                    raise RuntimeError('G05 native substep has no current effort interval')
                indices, efforts = pending
                readback = _tensor_rows(
                    self._articulation.get_dof_efforts(dof_indices=indices),
                    width=len(indices), label='G05 post-step effort readback',
                )[0]
                if any(not math.isclose(actual, requested, rel_tol=0.0, abs_tol=1e-5)
                       for actual, requested in zip(readback, efforts, strict=True)):
                    raise RuntimeError('G05 effort hold/reapply readback differs from requested values')
                native_adaptation_application = {
                    'schema_version': 'native-physx-effort-substep-application-v1',
                    'profile_id': 'isaacsim-6.2-physx-direct-effort-v1',
                    'provenance_kind': 'native_runtime',
                    'native_step_index': attempted_index,
                    'native_dof_names': list(self._dof_names),
                    'requested_efforts': list(efforts),
                    'readback_efforts': list(readback),
                    'public_effort_api': 'Articulation.get_dof_efforts',
                }
            elif self._f06_pickcube:
                target = self._last_native_mimic_target
                if (not isinstance(target, dict)
                        or target.get('drive_receipt_identity_sha256') != self.drive_receipt.identity_sha256
                        or not _is_sha256_identity(target.get('target_identity_sha256'))):
                    raise RuntimeError('F06 physics substep has no current acknowledged leader position target')
                self._sync()
                q = _tensor_rows(self._articulation.get_dof_positions(), width=len(self._dof_names),
                                 label='F06 post-step DOF position')[0]
                qd = _tensor_rows(self._articulation.get_dof_velocities(), width=len(self._dof_names),
                                  label='F06 post-step DOF velocity')[0]
                reference_index = self._dof_index['finger_joint1']
                follower_index = self._dof_index['finger_joint2']
                # F06's 5 N contract bounds the leader drive's actuator
                # output. Projected joint force also includes forces
                # arriving through the joint and is retained separately
                # as a physical observation.
                applied_effort = _tensor_rows(
                    self._articulation.get_dof_efforts(
                        dof_indices=[reference_index],
                    ),
                    width=1, label='F06 public leader actuation-effort readback',
                )[0][0]
                projected_joint_force = _tensor_rows(
                    self._articulation.get_dof_projected_joint_forces(
                        dof_indices=[reference_index],
                    ),
                    width=1, label='F06 public projected active leader-force readback',
                )[0][0]
                reference_position = float(q[reference_index])
                follower_position = float(q[follower_index])
                reference_velocity = float(qd[reference_index])
                follower_velocity = float(qd[follower_index])
                native_adaptation_application = {
                    'schema_version': 'native-physx-mimic-substep-application-v1',
                    'profile_id': (
                        'isaacsim-' + self._app_owner.sdk_identity['normalized_version'].rsplit('.', 2)[0]
                        + '-pickcube-physx-mimic-5n-v1'
                    ),
                    'provenance_kind': 'native_runtime',
                    'drive_receipt_identity_sha256': self.drive_receipt.identity_sha256,
                    'target_identity_sha256': target['target_identity_sha256'],
                    'native_step_index': attempted_index,
                    'reference_joint': 'finger_joint1',
                    'follower_joint': 'finger_joint2',
                    'reference_position_m': reference_position,
                    'follower_position_m': follower_position,
                    'reference_velocity_m_s': reference_velocity,
                    'follower_velocity_m_s': follower_velocity,
                    'relation_error_m': follower_position - reference_position,
                    'reference_target_m': float(target['reference_target_m']),
                    'reference_effort_N': float(applied_effort),
                    'maximum_effort_N': 5.0,
                    'public_effort_api': (
                        'Articulation.get_dof_efforts'
                    ),
                    'effort_measurement_semantics': (
                        'actuation_force'
                    ),
                    'native_mimic_api': 'PhysxMimicJointAPI:transX',
                    'native_drive_api': 'PhysicsDriveAPI:linear',
                }
                if self._f06_pickcube:
                    if getattr(self, '_f06_robot_contact_views', None):
                        native_adaptation_application['public_robot_contacts'] = self._read_f06_robot_contact_witness()
                    native_adaptation_application.update({
                        'projected_joint_force_N': float(projected_joint_force),
                        'public_projected_joint_force_api': (
                            'Articulation.get_dof_projected_joint_forces'
                        ),
                        'projected_force_measurement_semantics': 'projected_active_joint_force',
                    })
        except BaseException as error:
            if getattr(self, '_physical_effort_pending', None) is not None:
                self._physical_effort_fault = True
            error.add_note(
                f"one native physics step was attempted; pre-step counter={before!r}; "
                f"native adaptation receipt={native_adaptation_application!r}"
            )
            raise
        after = self._counter()
        delta_steps = after[0] - before[0]
        delta_time = after[1] - before[1]
        advance_observation = None
        if self._g05_effort:
            try:
                from isaacsim.core.experimental.utils import app as app_utils
                timeline_state = {
                    "playing": bool(app_utils.is_playing()),
                    "paused": bool(app_utils.is_paused()),
                    "stopped": bool(app_utils.is_stopped()),
                }
            except BaseException as observation_error:
                timeline_state = {
                    "observation_error": f"{type(observation_error).__name__}: {observation_error}",
                }
            advance_observation = {
                "schema_version": "g05-native-advance-counter-observation-v1",
                "attempted_index": attempted_index,
                "before": list(before),
                "after_effort_setter": (
                    None if after_effort_setter is None else list(after_effort_setter)
                ),
                "after_effort_sync": (
                    None if after_effort_sync is None else list(after_effort_sync)
                ),
                "after_manager_step": None if after_manager_step is None else list(after_manager_step),
                "after_cuda_sync": list(after),
                "effort_setter_counter_delta": (
                    None if after_effort_setter is None
                    else [after_effort_setter[0] - before[0], after_effort_setter[1] - before[1]]
                ),
                "effort_sync_counter_delta": (
                    None if after_effort_sync is None or after_effort_setter is None
                    else [after_effort_sync[0] - after_effort_setter[0],
                          after_effort_sync[1] - after_effort_setter[1]]
                ),
                "manager_step_counter_delta": (
                    None if after_manager_step is None or after_effort_sync is None
                    else [after_manager_step[0] - after_effort_sync[0],
                          after_manager_step[1] - after_effort_sync[1]]
                ),
                # The final counter follows synchronization and effort
                # readback, so it cannot attribute movement to sync alone.
                "post_manager_counter_delta": (
                    None if after_manager_step is None
                    else [after[0] - after_manager_step[0], after[1] - after_manager_step[1]]
                ),
                "manager_physics_dt_s": float(self._manager.get_physics_dt()),
                "physics_scene_dt_s": None if self._physics_scene is None else float(self._physics_scene.get_dt()),
                "physics_scene_steps_per_second": (
                    None if self._physics_scene is None
                    else int(self._physics_scene.get_steps_per_second())
                ),
                "simulation_manager_is_simulating": bool(self._manager.is_simulating()),
                "simulation_manager_is_paused": bool(self._manager.is_paused()),
                "timeline": timeline_state,
                "counter_delta": delta_steps,
                "time_delta_s": delta_time,
            }
            self._build_layout_facts["native_last_advance_observation"] = advance_observation
        if delta_steps != 1 or abs(delta_time - float(self._artifact.timebase.physics_dt)) > 1e-9:
            error = RuntimeError(
                "Isaac public step did not accept exactly one configured physics substep: "
                f"counter_delta={delta_steps}, time_delta={delta_time}"
            )
            if advance_observation is not None:
                setattr(error, '_g05_native_last_advance_observation', advance_observation)
            raise error
        self._native_step_count = attempted_index
        assert self._episode_origin_time is not None
        episode_time = after[1] - self._episode_origin_time
        return NativeAdvanceReceiptV1(
            "native-advance-receipt-v1", 1, attempted_index, episode_time,
            native_adaptation_application=native_adaptation_application,
        )

    def bind_task_camera(self, camera, state):
        """Author an owned USD camera in the existing live scene, without a sensor."""
        import uuid
        import numpy as np
        from pxr import Gf, UsdGeom
        from ...observations.canonical_camera import CameraGeometry, resolve_camera
        if self._closed or self._stage is None or self._task_camera_path is not None:
            raise RuntimeError('task camera binding unavailable or already bound')
        if type(camera) is not CameraGeometry:
            raise TypeError('task camera must be CameraGeometry')
        camera.validate()
        if camera.task_artifact_hash != self._artifact.identity_hash or camera.parent_frame != 'world':
            raise ValueError('task camera must be linked to this artifact and world mounted')
        self._prepare_task_rgb_render_stage()
        metadata = resolve_camera(camera, state)
        path = '/GeoChoraTaskCamera_' + uuid.uuid4().hex
        try:
            prim_camera = UsdGeom.Camera.Define(self._stage, path)
            prim = prim_camera.GetPrim()
            focal = 24.0
            vertical = 2.0 * focal * math.tan(camera.fov_y / 2.0)
            prim_camera.GetFocalLengthAttr().Set(focal)
            prim_camera.GetVerticalApertureAttr().Set(vertical)
            prim_camera.GetHorizontalApertureAttr().Set(vertical * camera.width / camera.height)
            prim_camera.GetClippingRangeAttr().Set(Gf.Vec2f(camera.near, camera.far))
            world = np.asarray(metadata.T_world_from_camera, dtype=np.float64).copy()
            world[:3, :3] = world[:3, :3] @ np.diag([1., -1., -1.])
            UsdGeom.Xformable(prim).AddTransformOp().Set(
                Gf.Matrix4d(*[float(value) for value in world.T.reshape(-1)]))
            self._task_camera_path, self._task_camera_geometry = path, camera
            return self.task_camera_binding(state)
        except BaseException as error:
            self._task_camera_path = self._task_camera_geometry = None
            try:
                if self._stage.GetPrimAtPath(path):
                    self._stage.RemovePrim(path)
            except BaseException as cleanup_error:
                error.add_note(f'Isaac task camera cleanup also failed: {cleanup_error!r}')
            raise

    def task_camera_binding(self, state):
        import copy
        import numpy as np
        from pxr import UsdGeom
        from ...observations.canonical_camera import resolve_camera
        camera, path = self._task_camera_geometry, self._task_camera_path
        if self._closed or self._stage is None or camera is None or path is None:
            raise RuntimeError('no task camera is bound to the current scene')
        prim = self._stage.GetPrimAtPath(path)
        if not prim or not prim.IsA(UsdGeom.Camera):
            raise RuntimeError('bound task camera prim is unavailable')
        native = UsdGeom.Camera(prim)
        metadata = resolve_camera(camera, state)
        expected = np.asarray(metadata.T_world_from_camera, dtype=np.float64).copy()
        expected[:3, :3] = expected[:3, :3] @ np.diag([1., -1., -1.])
        actual = np.asarray(UsdGeom.XformCache().GetLocalToWorldTransform(prim), dtype=np.float64).T
        focal = float(native.GetFocalLengthAttr().Get())
        vertical = float(native.GetVerticalApertureAttr().Get())
        horizontal = float(native.GetHorizontalApertureAttr().Get())
        clipping = tuple(float(v) for v in native.GetClippingRangeAttr().Get())
        if (not np.allclose(actual, expected, atol=1e-6, rtol=0)
                or not math.isclose(2 * math.atan(vertical / (2 * focal)), camera.fov_y, abs_tol=1e-6)
                or not math.isclose(horizontal / vertical, camera.width / camera.height, abs_tol=1e-6)
                or not np.allclose(clipping, (camera.near, camera.far), atol=1e-6, rtol=0)):
            raise RuntimeError('native task camera geometry no longer matches its declaration')
        return {'camera': camera.to_mapping(), 'camera_identity': camera.identity_hash,
                'source_closure': self._source.source_closure_digest,
                'renderer_stage_preparation': copy.deepcopy(
                    self._task_renderer_stage_preparation
                ),
                'native_camera_prim': path, 'native_world_transform': actual.tolist(),
                'native_focal_length': focal, 'native_vertical_aperture': vertical,
                'native_horizontal_aperture': horizontal, 'native_clipping': clipping,
                'state_boundary': state.boundary.to_mapping(),
                'capture': 'none; geometry binding only'}

    def capture_observer(self, camera, state):
        """Capture the published F06 boundary through the existing App/scene owner."""
        if self._closed or self._observer_faulted or self._observer_render_request is None:
            raise RuntimeError('Isaac observer is unavailable or faulted')
        from ...observations.canonical_camera import CameraGeometry, resolve_camera, CanonicalCameraObservation
        from ...observations.canonical_camera.images import normalize_rgb
        if type(camera) is not CameraGeometry:
            raise TypeError('Isaac observer requires CameraGeometry')
        camera.validate()
        initial = self._observer_render_request.camera
        if (camera.task_artifact_hash != self._artifact.identity_hash or
                (camera.width, camera.height, camera.rgb, camera.depth, camera.rgb_layout, camera.rgb_dtype) !=
                (initial.width, initial.height, True, False, 'HWC', 'float32')):
            raise ValueError('Isaac observer camera changed the admitted output contract')
        try:
            return self._capture_observer_admitted(camera, state, resolve_camera, normalize_rgb,
                                                   CanonicalCameraObservation)
        except BaseException as error:
            self._observer_faulted = True
            try:
                self._close_observer()
            except BaseException as cleanup_error:
                error.add_note(f'Isaac observer cleanup also failed: {cleanup_error!r}')
            raise

    def capture_task_camera(self, camera, state):
        """Capture the separately bound task camera using an owned RTX sensor."""
        from ...observations.canonical_camera import resolve_camera, CanonicalCameraObservation
        from ...observations.canonical_camera.images import normalize_rgb
        if self._closed or self._observer_faulted or self._observer_render_request is None:
            raise RuntimeError('Isaac task renderer is unavailable or faulted')
        if camera != self._task_camera_geometry or self._task_camera_path is None:
            raise ValueError('Isaac task capture camera differs from its binding')
        binding_receipt = self.task_camera_binding(state)
        self._task_camera_binding_receipt = binding_receipt
        try:
            return self._capture_observer_admitted(camera, state, resolve_camera, normalize_rgb,
                                                   CanonicalCameraObservation, task=True)
        except BaseException as error:
            self._observer_faulted = True
            for close in (self._close_observer, self._close_task_camera_sensor):
                try:
                    close()
                except BaseException as cleanup_error:
                    error.add_note(f'Isaac task camera cleanup also failed: {cleanup_error!r}')
            raise

    def task_camera_completion(self, state):
        receipt = getattr(self, '_task_camera_completion', None)
        if receipt is None or receipt['state_boundary'] != state.boundary.to_mapping():
            raise RuntimeError('Isaac task camera has no completion for this boundary')
        return copy.deepcopy(receipt)

    def _check_observer_clock(self, before, *, playing, operation):
        """A native clock regression means the scene/App was stopped, not a physics step."""
        after = self._counter()
        if after != before or playing:
            self._observer_runtime_invalid = True
            self._episode_origin_step = self._episode_origin_time = None
            owner = getattr(self, '_app_owner', None)
            if owner is not None:
                owner.invalidate_runtime(f'{operation}: before={before!r}, after={after!r}, playing={playing!r}')
            raise RuntimeError(f'Isaac {operation} changed the physics clock or resumed the timeline: '
                               f'before={before!r}, after={after!r}, playing={playing!r}')

    def _capture_observer_admitted(self, camera, state, resolve_camera, normalize_rgb,
                                   observation_type, *, task=False):
        import json
        import uuid
        import numpy as np
        import omni.timeline
        import omni.usd
        from pxr import Gf, UsdGeom, UsdRender
        from isaacsim.sensors.experimental.rtx import RtxCamera, CameraSensor
        import omni.replicator.core as rep
        from ...artifacts import RendererSelectionV1
        from ...render.camera.source import CameraCaptureIdentityV1

        metadata = resolve_camera(camera, state)
        timeline = omni.timeline.get_timeline_interface()
        before = self._counter()
        timeline.pause()
        if timeline.is_playing():
            self._app_owner.app.update()
        self._check_observer_clock(before, playing=timeline.is_playing(), operation='pause confirmation')
        # A reset can update tensor state after the last PhysX-to-Fabric
        # publication.  Flush the public kinematic/Fabric interfaces before
        # rendering, without advancing the native simulation clock.
        from omni.physxfabric import get_physx_fabric_interface
        fabric = get_physx_fabric_interface()
        force_update = getattr(fabric, 'force_update', None)
        if not callable(force_update):
            raise RuntimeError('Isaac observer requires a public Fabric force-update operation')
        view = self._manager.get_physics_simulation_view()
        if view is None:
            raise RuntimeError('Isaac observer requires the live physics simulation view')
        view.update_articulations_kinematic()
        force_update(0.0, 0.0)
        self._sync()
        self._check_observer_clock(before, playing=timeline.is_playing(), operation='Fabric update')
        published_bodies = self._publish_observer_body_transforms()
        task_clock_mapping = None
        if task:
            state_sample_time = float(state.sample_clock.simulation_time_s)
            state_boundary = state.boundary.to_mapping()
            episode_id = str(state_boundary['episode_id'])
            task_clock_mapping = _task_render_clock_mapping(
                provider_time_s=before[1], episode_time_s=state_sample_time,
            )
            prior_epoch = getattr(self, '_task_render_clock_epoch', None)
            if (prior_epoch is not None and prior_epoch['episode_id'] == episode_id
                    and not math.isclose(
                        float(prior_epoch['provider_epoch_offset_s']),
                        float(task_clock_mapping['provider_epoch_offset_s']),
                        rel_tol=0.0, abs_tol=1e-9,
                    )):
                raise RuntimeError(
                    'Isaac provider-to-episode clock epoch changed within one episode: '
                    f'previous={prior_epoch!r}, current={task_clock_mapping!r}'
                )
            self._task_render_clock_epoch = {
                'episode_id': episode_id,
                'provider_epoch_offset_s': task_clock_mapping['provider_epoch_offset_s'],
            }
            print('G05_TASK_RGB_CLOCK_MAPPING '
                  + json.dumps(task_clock_mapping, sort_keys=True), flush=True)
        stage = omni.usd.get_context().get_stage()
        if stage is None or stage != self._stage:
            raise RuntimeError('Isaac observer lost its leased USD stage')
        task_sensor_created = False
        if task:
            path = self._task_camera_path
            if path is None:
                raise RuntimeError('Isaac task camera lost its source-bound USD prim')
            if self._task_camera_sensor is None:
                authoring = RtxCamera(path, tick_rate=0.0, reset_xform_op_properties=False)
                self._task_camera_sensor = CameraSensor(
                    authoring, resolution=(camera.height, camera.width), annotators=['rgb'],
                )
                task_sensor_created = True
            sensor = self._task_camera_sensor
        else:
            if self._observer_sensor is None:
                path = '/GeoChoraObserver_' + uuid.uuid4().hex
                self._observer_path = path
                authoring = RtxCamera(path, tick_rate=0.0)
                self._observer_sensor = CameraSensor(
                    authoring, resolution=(camera.height, camera.width), annotators=['rgb'],
                )
            path, sensor = self._observer_path, self._observer_sensor
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsValid() or not prim.IsA(UsdGeom.Camera):
            raise RuntimeError('Isaac observer camera prim is unavailable')
        usd_camera = UsdGeom.Camera(prim)
        focal = 24.0
        vertical = 2.0 * focal * math.tan(camera.fov_y / 2.0)
        world = np.asarray(metadata.T_world_from_camera, dtype=np.float64).copy()
        world[:3, :3] = world[:3, :3] @ np.diag([1.0, -1.0, -1.0])
        if task:
            binding = self.task_camera_binding(state)
            actual = np.asarray(binding['native_world_transform'], dtype=np.float64)
            if (binding['native_camera_prim'] != path
                    or not np.allclose(actual, world, atol=1e-6, rtol=0)):
                raise RuntimeError('Isaac task sensor is not attached to its verified bound camera')
        else:
            usd_camera.GetFocalLengthAttr().Set(focal)
            usd_camera.GetVerticalApertureAttr().Set(vertical)
            usd_camera.GetHorizontalApertureAttr().Set(vertical * camera.width / camera.height)
            usd_camera.GetClippingRangeAttr().Set(Gf.Vec2f(camera.near, camera.far))
            xform = UsdGeom.Xformable(prim)
            xform.ClearXformOpOrder()
            op = xform.AddTransformOp()
            op.Set(Gf.Matrix4d(*[float(value) for value in world.T.reshape(-1)]))
            actual = np.asarray(UsdGeom.XformCache().GetLocalToWorldTransform(prim)).T
            if not np.allclose(actual, world, atol=1e-6, rtol=0):
                raise RuntimeError('Isaac realized observer camera transform differs from the request')
        task_completions = []
        dispatcher_path = '/Render/PostProcess/SDGPipeline/PostProcessDispatcher'

        def log_task_scheduler_snapshot(phase, operation):
            import carb
            import omni.graph.core as og

            snapshot = {
                'phase': phase,
                'operation': operation,
                'physics_step': int(before[0]),
                'physics_time_s': float(before[1]),
                'timeline_playing': bool(timeline.is_playing()),
                'timeline_time_s': float(timeline.get_current_time()),
                'task_clock_mapping': task_clock_mapping,
                'task_renderer_stage_preparation': copy.deepcopy(
                    getattr(self, '_task_renderer_stage_preparation', None)
                ),
                'usd_stage_time_range': {
                    'start_time_code': float(self._stage.GetStartTimeCode()),
                    'end_time_code': float(self._stage.GetEndTimeCode()),
                    'time_codes_per_second': float(self._stage.GetTimeCodesPerSecond()),
                    'frames_per_second': float(self._stage.GetFramesPerSecond()),
                },
                'sensor_camera_prim': path,
            }
            try:
                import usdrt
                node = og.get_node_by_path(dispatcher_path)
                snapshot['dispatcher_present'] = node is not None
                if node is not None:
                    snapshot['dispatcher_compute_count'] = int(node.get_compute_count())
                    numerator = node.get_attribute('outputs:referenceTimeNumerator').get()
                    denominator = node.get_attribute('outputs:referenceTimeDenominator').get()
                    snapshot['dispatcher_reference_time_numerator'] = (
                        None if numerator is None else int(numerator)
                    )
                    snapshot['dispatcher_reference_time_denominator'] = (
                        None if denominator is None else int(denominator)
                    )
                    snapshot['dispatcher_reference_time_s'] = (
                        float(numerator) / float(denominator)
                        if numerator is not None and denominator not in (None, 0) else None
                    )
                settings = carb.settings.get_settings()
                stage_id = int(omni.usd.get_context().get_stage_id())
                snapshot['usd_stage_id'] = stage_id
                snapshot['play_simulations_setting'] = settings.get_as_bool(
                    '/app/player/playSimulations'
                )
                fabric_stage = usdrt.Usd.Stage.Attach(stage_id)
                external_time_prim = fabric_stage.GetPrimAtPath('/ExternalSimulationTime')
                snapshot['fabric_external_simulation_time_prim_present'] = bool(
                    external_time_prim and external_time_prim.IsValid()
                )
                if external_time_prim and external_time_prim.HasAttribute('omni:time'):
                    external_time = external_time_prim.GetAttribute('omni:time').Get()
                    snapshot['fabric_external_simulation_time_s'] = (
                        None if external_time is None else float(external_time)
                    )
                else:
                    snapshot['fabric_external_simulation_time_s'] = None
                snapshot['support_multi_tick_rate'] = bool(
                    settings.get_as_bool('/rtx/hydra/supportMultiTickRate')
                )
                snapshot['async_rendering'] = bool(
                    settings.get_as_bool('/omni/replicator/asyncRendering')
                )
                snapshot['sensor_has_data'] = bool(sensor.has_data())
                product = sensor.render_product
                product_prim = product.GetPrim()
                snapshot['render_product_path'] = (
                    str(product_prim.GetPath()) if product_prim and product_prim.IsValid() else None
                )
                if product_prim and product_prim.IsValid():
                    resolution = product_prim.GetAttribute('resolution').Get()
                    snapshot['render_product_resolution'] = (
                        list(resolution) if resolution is not None else []
                    )
                    viewport_handle = product_prim.GetAttribute('viewportHandle')
                    snapshot['render_product_viewport_handle'] = (
                        None if not viewport_handle or not viewport_handle.IsValid()
                        else viewport_handle.Get()
                    )
                    camera_rel = UsdRender.Product(product_prim).GetCameraRel()
                    snapshot['render_product_camera_targets'] = [
                        str(target) for target in camera_rel.GetTargets()
                    ]
                if task:
                    snapshot['replicator_status'] = str(rep.orchestrator.get_status())
                    snapshot['replicator_sim_times_to_write'] = [
                        [int(numerator), int(denominator)]
                        for numerator, denominator in rep.orchestrator.get_sim_times_to_write()
                    ]
            except Exception as error:
                snapshot['diagnostic_read_error'] = f'{type(error).__name__}: {error}'
            print('G05_TASK_RGB_RENDER_DIAG ' + json.dumps(snapshot, sort_keys=True), flush=True)
            return snapshot

        task_rgb_data = None

        def render_once(operation, *, allow_unready=False):
            nonlocal task_rgb_data
            task_render_pulse = None
            task_sensor_progress = None
            if task:
                import carb
                import omni.graph.core as og
                before_render_snapshot = log_task_scheduler_snapshot('before_render', operation)
                node = og.get_node_by_path(dispatcher_path)
                prior_count = int(node.get_compute_count()) if node else 0
                previous_data, previous_info = sensor.get_data('rgb')
                previous_frame_id = (
                    previous_info.get('frameId') if isinstance(previous_info, Mapping) else None
                )
                if previous_frame_id is not None and type(previous_frame_id) not in (int, float, str):
                    previous_frame_id = repr(previous_frame_id)
                timeline_before_s = float(timeline.get_current_time())
                settings = carb.settings.get_settings()
                play_simulations_before = bool(
                    settings.get_as_bool('/app/player/playSimulations')
                )
                # The task sensor is attached to its bound task prim. Match the
                # known-good zero-delta synchronous Replicator path under this
                # existing App owner; there is no second renderer or physics owner.
                rep.orchestrator.step(rt_subframes=1, pause_timeline=True,
                                      delta_time=0.0, wait_for_render=True)
                after_render_snapshot = log_task_scheduler_snapshot('after_render', operation)
                attempt_data, sensor_info = sensor.get_data('rgb')
                timeline_after_s = float(timeline.get_current_time())
                play_simulations_after = bool(
                    settings.get_as_bool('/app/player/playSimulations')
                )
                frame_id = sensor_info.get('frameId') if isinstance(sensor_info, Mapping) else None
                if frame_id is not None and type(frame_id) not in (int, float, str):
                    frame_id = repr(frame_id)
                sensor_has_data = bool(sensor.has_data())
                timeline_time_unchanged = math.isclose(
                    timeline_before_s, timeline_after_s, rel_tol=0.0, abs_tol=1e-9,
                )
                frame_id_advanced = (
                    frame_id != previous_frame_id
                    if frame_id is not None and previous_frame_id is not None else None
                )
                task_sensor_progress = {
                    'sensor_had_payload_before': previous_data is not None,
                    'sensor_has_data_after': sensor_has_data,
                    'rgb_payload_available_after': attempt_data is not None,
                    'frame_id_before': previous_frame_id,
                    'frame_id_after': frame_id,
                    'frame_id_advanced': frame_id_advanced,
                }
                task_render_pulse = {
                    'render_owner': 'omni.replicator.core.orchestrator.step(wait_for_render=True)',
                    'delta_time_s': 0.0,
                    'timeline_time_before_s': timeline_before_s,
                    'timeline_time_after_s': timeline_after_s,
                    'timeline_time_unchanged': timeline_time_unchanged,
                    'timeline_paused_after': not bool(timeline.is_playing()),
                    'play_simulations_before': play_simulations_before,
                    'play_simulations_after': play_simulations_after,
                    'play_simulations_restored': play_simulations_before == play_simulations_after,
                    'sensor_progress': task_sensor_progress,
                }
                print('G05_TASK_RGB_SYNC_CAPTURE '
                      + json.dumps(task_render_pulse, sort_keys=True), flush=True)
            else:
                rep.orchestrator.step(rt_subframes=1, pause_timeline=True, delta_time=0.0,
                                      wait_for_render=True)
            self._check_observer_clock(before, playing=timeline.is_playing(), operation=operation)
            if task:
                node = og.get_node_by_path(dispatcher_path)
                after_count = int(node.get_compute_count()) if node else 0
                numerator = node.get_attribute('outputs:referenceTimeNumerator').get() if node else None
                denominator = node.get_attribute('outputs:referenceTimeDenominator').get() if node else None
                reference = (float(numerator) / float(denominator)
                             if numerator is not None and denominator not in (None, 0) else None)
                count_delta = after_count - prior_count
                fabric_before_time = before_render_snapshot.get('fabric_external_simulation_time_s')
                fabric_after_time = after_render_snapshot.get('fabric_external_simulation_time_s')
                fabric_clock_matches_provider = (
                    fabric_before_time is not None and fabric_after_time is not None
                    and math.isfinite(float(fabric_before_time))
                    and math.isfinite(float(fabric_after_time))
                    and abs(float(fabric_before_time) - float(before[1])) <= 1e-6
                    and abs(float(fabric_after_time) - float(before[1])) <= 1e-6
                )
                timeline_matches_provider = math.isclose(
                    float(timeline.get_current_time()), float(before[1]),
                    rel_tol=0.0, abs_tol=1e-9,
                )
                frame_is_fresh = (
                    task_sensor_progress['frame_id_advanced']
                    if task_sensor_progress['frame_id_advanced'] is not None else count_delta > 0
                )
                # Timeline/provider equality is diagnostic only: the task
                # renderer is fenced by dispatcher/Fabric time and the paused
                # timeline must remain unchanged, not be rewritten to match.
                complete = (0 < count_delta < 1000 and reference is not None
                            and math.isfinite(reference) and abs(reference - float(before[1])) <= 1e-6
                            and sensor_has_data and attempt_data is not None and frame_is_fresh
                            and fabric_clock_matches_provider
                            and task_render_pulse['timeline_time_unchanged']
                            and task_render_pulse['timeline_paused_after']
                            and task_render_pulse['play_simulations_restored'])
                if complete:
                    task_rgb_data = attempt_data
                task_completions.append({'operation': operation, 'dispatcher_before': prior_count,
                                         'dispatcher_after': after_count,
                                         'reference_time': reference, 'physics_time': float(before[1]),
                                         'state_sample_time': float(state.sample_clock.simulation_time_s),
                                         'provider_epoch_offset_s': task_clock_mapping['provider_epoch_offset_s'],
                                         'task_clock_mapping': task_clock_mapping,
                                         'timeline_matches_provider': timeline_matches_provider,
                                         'timeline_time_unchanged': task_render_pulse['timeline_time_unchanged'],
                                         'fabric_clock_matches_provider': fabric_clock_matches_provider,
                                         'sensor_camera_prim': path,
                                         'synchronous_render_owner': task_render_pulse['render_owner'],
                                         'synchronous_capture': task_render_pulse,
                                         'timeline_time_s': float(timeline.get_current_time()),
                                         'fabric_external_simulation_time': after_render_snapshot.get(
                                             'fabric_external_simulation_time_s'
                                         ),
                                         'fabric_stage_id': after_render_snapshot.get('usd_stage_id'),
                                         'fabric_clock_before': before_render_snapshot.get(
                                             'fabric_external_simulation_time_s'
                                         ),
                                         'sensor_frame_id': frame_id,
                                         'sensor_progress': task_sensor_progress,
                                         'sensor_payload_available': attempt_data is not None,
                                         'completed': complete})
                if not complete and not allow_unready:
                    raise RuntimeError(f'Isaac task render did not complete at the current physics time: {task_completions[-1]!r}')
                return complete

        if task:
            # A newly created render product needs App updates before its
            # first synchronous request. Neither initialization nor warmup may
            # advance the physical boundary owned by the RuntimeSession.
            if task_sensor_created:
                for _ in range(4):
                    self._app_owner.app.update()
                    self._check_observer_clock(
                        before, playing=timeline.is_playing(),
                        operation='task sensor initialization',
                    )
            # Cold RTX initialization may outlast four synchronous polls.
            # Bound readiness retries; every poll retains the completion and
            # no-physics-advance fences, and the worker enforces wall/memory limits.
            for _ in range(8):
                if render_once('task sensor warmup', allow_unready=True):
                    break
            else:
                raise RuntimeError(
                    f'Isaac task sensor did not complete bounded warmup: {task_completions!r}'
                )
        color_settings = _read_isaac_observer_color_settings()
        data = task_rgb_data if task else None
        if not task:
            for _ in range(8):
                render_once('observer rendering')
                data, _info = sensor.get_data('rgb')
                if data is not None:
                    break
        if data is None:
            raise RuntimeError('Isaac observer RGB did not complete within the bounded render wait')
        if _read_isaac_observer_color_settings() != color_settings:
            raise RuntimeError('Isaac observer color settings changed during capture')
        self._verify_observer_fabric(state, world, published_bodies, camera_path=path)
        if not task:
            self._observer_camera_contract = (world.copy(), camera.width, camera.height,
                                              camera.fov_y, camera.near, camera.far)
        else:
            self._task_camera_completion = {'state_boundary': state.boundary.to_mapping(),
                                            'task_camera_binding': self._task_camera_binding_receipt,
                                            'dispatcher_completions': task_completions}
        rgb = np.array(data.numpy(), copy=True)
        selection = RendererSelectionV1('renderer-selection-v1', 'isaacsim', 'rtx',
                                        'v211_isaac_rtx_task_rgb_v1' if task else
                                        'v211_isaac_rtx_observer_v1', 'cuda:0')
        capability = {'schema': 'v211-isaac-rtx-observer-v1', 'sdk': '6.2.0.0',
                      'capture': ('source-bound task CameraSensor RGB; in-memory stage time range/light '
                                  'receipt; one bounded synchronous zero-delta Replicator capture; owned host copy'
                                  if task else 'CameraSensor RGB; Replicator wait_for_render; owned host copy'),
                      'sensor_owner': ('task-camera-sensor' if task else
                                       'observer-camera-sensor'),
                      'rendered_camera_prim': path,
                      'color': color_settings,
                      'stage_time_range': self._observer_stage_time_range_receipt,
                      'render_light': self._observer_render_light_receipt,
                      'task_renderer_stage_preparation': getattr(
                          self, '_task_renderer_stage_preparation', None
                      )}
        capability_hash = hashlib.sha256(json.dumps(capability, sort_keys=True,
                                                  separators=(',', ':')).encode()).hexdigest()
        identity = CameraCaptureIdentityV1(
            'camera-capture-identity-v1', camera.task_artifact_hash, camera.camera_id,
            camera.identity_hash, self._source.source_closure_digest, self._execution.identity_hash,
            selection, capability_hash, state.boundary, state.sample_clock, ('rgb',), camera.capture_phase)
        identity.validate()
        return observation_type(normalize_rgb(rgb, camera), None, metadata, identity)

    def _publish_observer_body_transforms(self):
        """Copy public PhysX body poses to renderer-facing Fabric without stepping."""
        import numpy as np
        import isaacsim.core.experimental.utils.backend as backend_utils
        from isaacsim.core.experimental.prims import RigidPrim, XformPrim
        from pxr import UsdPhysics

        before = self._counter()
        entry = str(self._source.scene_source.loaded_delivery.delivery.entry_prim).rstrip('/')
        paths = sorted((str(prim.GetPath()) for prim in self._stage.Traverse()
                        if str(prim.GetPath()).startswith(entry + '/')
                        and prim.HasAPI(UsdPhysics.RigidBodyAPI)),
                       key=lambda path: (path.count('/'), path))
        if not paths:
            raise RuntimeError('Isaac observer has no source-bound rigid bodies')
        bodies = []
        for path in paths:
            rigid = RigidPrim(path)
            with backend_utils.use_backend('tensor', raise_on_unsupported=True, raise_on_fallback=True):
                position, quaternion = rigid.get_world_poses()
            p = np.asarray(position.numpy()).reshape(-1, 3)[0].copy()
            q = np.asarray(quaternion.numpy()).reshape(-1, 4)[0].copy()
            if not np.isfinite(p).all() or not np.isfinite(q).all():
                raise RuntimeError(f'Isaac observer body pose is non-finite: {path}')
            bodies.append((path, p, q))
        for path, p, q in bodies:
            with backend_utils.use_backend('usdrt', raise_on_unsupported=True, raise_on_fallback=True):
                XformPrim(path).set_world_poses(positions=[p.tolist()], orientations=[q.tolist()])
        self._sync()
        self._check_observer_clock(before, playing=False, operation='observer body publication')
        return bodies

    def _verify_observer_fabric(self, state, camera_world, published_bodies=(), *, camera_path=None):
        """Reject a frame unless the public renderer-facing poses match publication."""
        import numpy as np
        import isaacsim.core.experimental.utils.backend as backend_utils
        from isaacsim.core.experimental.prims import XformPrim

        expected = {(item.frame.entity_id, item.frame.frame_id): item.pose_world
                    for item in state.frames}
        delivery = self._source.scene_source.loaded_delivery.delivery
        checks = []
        for semantic, native in {**self._source.bodies, **self._source.frames}.items():
            frame = self._artifact.legacy_frame_bindings.get(semantic)
            if frame is None or (frame.entity_id, frame.frame_id) not in expected:
                raise RuntimeError(f'Isaac observer lacks a published frame for {semantic!r}')
            pose = expected[(frame.entity_id, frame.frame_id)]
            checks.append((_native_prim_path(native, delivery.entry_prim), pose.position,
                           pose.quaternion_wxyz, semantic))
        if not checks:
            raise RuntimeError('Isaac observer has no source-bound Fabric frames to verify')
        with backend_utils.use_backend('usdrt', raise_on_unsupported=True, raise_on_fallback=True):
            for path, position, quaternion in published_bodies:
                p, q = XformPrim(path).get_world_poses()
                p = np.asarray(p.numpy()).reshape(-1, 3)[0]
                q = np.asarray(q.numpy()).reshape(-1, 4)[0]
                if (np.linalg.norm(p - position) > 1e-4 or
                        min(np.linalg.norm(q - quaternion), np.linalg.norm(q + quaternion)) > 1e-4):
                    raise RuntimeError(f'Isaac observer body publication changed before completion: {path}')
            for path, position, quaternion, semantic in checks:
                actual_position, actual_quaternion = XformPrim(path).get_world_poses()
                actual_position = np.asarray(actual_position.numpy()).reshape(-1, 3)[0]
                actual_quaternion = np.asarray(actual_quaternion.numpy()).reshape(-1, 4)[0]
                p_error = float(np.linalg.norm(actual_position - np.asarray(position)))
                q_error = min(float(np.linalg.norm(actual_quaternion - np.asarray(quaternion))),
                              float(np.linalg.norm(actual_quaternion + np.asarray(quaternion))))
                if p_error > 1e-4 or q_error > 1e-4:
                    raise RuntimeError(f'Isaac renderer-facing frame {semantic!r} differs from published state: '
                                       f'{p_error:g} m, {q_error:g} quaternion L2')
            position, quaternion = XformPrim(camera_path or self._observer_path).get_world_poses()
            position = np.asarray(position.numpy()).reshape(-1, 3)[0]
            quaternion = np.asarray(quaternion.numpy()).reshape(-1, 4)[0]
        w, x, y, z = quaternion / np.linalg.norm(quaternion)
        rotation = np.asarray(((1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)),
                               (2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)),
                               (2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y))))
        if (not np.allclose(position, camera_world[:3, 3], atol=1e-4, rtol=0) or
                not np.allclose(rotation, camera_world[:3, :3], atol=1e-4, rtol=0)):
            raise RuntimeError('Isaac renderer-facing camera pose differs from the requested camera')

    @staticmethod
    def _viewport_frame_matches_observer(info, contract):
        """Check the camera and projection of an actually delivered viewport frame."""
        import numpy as np
        world, width, height, fov_y, near, far = contract
        view, projection = info.get('view'), info.get('projection')
        if view is None or projection is None or tuple(info.get('resolution', ())) != (width, height):
            return False
        expected_view = np.linalg.inv(world).T.reshape(-1)
        expected_focal = 1.0 / math.tan(fov_y / 2.0)
        return bool(np.allclose(np.asarray(view), expected_view, rtol=0, atol=1e-4)
                    and math.isclose(float(projection[0]), expected_focal * height / width, abs_tol=1e-4)
                    and math.isclose(float(projection[5]), expected_focal, abs_tol=1e-4)
                    and math.isclose(float(projection[10]), near / (far - near), abs_tol=1e-5)
                    and math.isclose(float(projection[14]), near * far / (far - near), abs_tol=1e-5))

    def present_observer(self):
        """Present the observer camera in Isaac's headed viewport without physics."""
        if self._closed or self._observer_faulted or self._observer_sensor is None:
            raise RuntimeError('Isaac observer presentation requires a completed capture')
        try:
            import omni.timeline
            from isaacsim.core.rendering_manager import RenderingManager, ViewportManager
            before = self._counter()
            windows = ViewportManager.get_viewport_windows()
            if not windows:
                raise RuntimeError('Isaac headed viewport is unavailable')
            viewport = ViewportManager.get_viewport_api()
            contract = getattr(self, '_observer_camera_contract', None)
            if viewport is None or contract is None:
                raise RuntimeError('Isaac viewport lacks the completed observer camera contract')
            _world, width, height, _fov_y, _near, _far = contract
            delivered = []
            subscription = viewport.subscribe_to_frame_change(lambda *_args: delivered.append(True))
            previous_number = viewport.frame_info.get('frame_number', -1)
            ViewportManager.set_camera(self._observer_path)
            ViewportManager.set_resolution((width, height))
            matched = []
            for _ in range(16):
                RenderingManager.render()
                self._check_observer_clock(before, playing=omni.timeline.get_timeline_interface().is_playing(),
                                           operation='viewport update')
                info = viewport.frame_info
                number = info.get('frame_number', -1)
                if (delivered and number > previous_number
                        and self._viewport_frame_matches_observer(info, contract)):
                    matched.append(int(number))
                    previous_number = number
                    if len(matched) >= 2:
                        break
            if len(matched) < 2:
                raise RuntimeError('Isaac viewport did not deliver two frames with the requested camera and projection')
            realized = ViewportManager.get_camera()
            if str(realized.GetPrim().GetPath()) != self._observer_path:
                raise RuntimeError('Isaac viewport did not retain the requested observer camera')
            return {'backend': 'Isaac Sim native viewport', 'camera_prim': self._observer_path,
                    'viewport_titles': [str(window.title) for window in windows],
                    'event_pump': 'RenderingManager.render', 'viewport_frame_events': len(delivered),
                    'matched_viewport_frame_numbers': matched, 'render_resolution': [width, height],
                    'physics_counter': list(before), 'window_id': None}
        except BaseException as error:
            self._observer_faulted = True
            try:
                self._close_observer()
            except BaseException as cleanup_error:
                error.add_note(f'Isaac observer cleanup after presentation failure also failed: {cleanup_error!r}')
            raise

    def invalidate_observer(self):
        self._observer_faulted = True
        self._close_observer()

    def _close_observer(self):
        self._observer_camera_contract = None
        sensor, self._observer_sensor = self._observer_sensor, None
        path, self._observer_path = self._observer_path, None
        primary = None
        if sensor is not None:
            try:
                sensor.detach_annotators('rgb')
            except BaseException as error:
                primary = error
        if path is not None and self._stage is not None:
            try:
                if self._stage.GetPrimAtPath(path):
                    self._stage.RemovePrim(path)
            except BaseException as error:
                if primary is None:
                    primary = error
                else:
                    primary.add_note(f'Isaac observer prim cleanup also failed: {error!r}')
        if primary is not None:
            raise primary

    def _close_task_camera_sensor(self):
        sensor, self._task_camera_sensor = getattr(self, '_task_camera_sensor', None), None
        if sensor is not None:
            sensor.detach_annotators('rgb')

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        import gc

        primary = None
        try:
            self._close_task_camera_sensor()
        except BaseException as error:
            primary = error
        task_camera_path, self._task_camera_path = self._task_camera_path, None
        self._task_camera_geometry = None
        if task_camera_path is not None and self._stage is not None:
            try:
                if self._stage.GetPrimAtPath(task_camera_path):
                    self._stage.RemovePrim(task_camera_path)
            except BaseException as error:
                if primary is None:
                    primary = error
                else:
                    primary.add_note(f'Isaac task camera prim cleanup also failed: {error!r}')
        try:
            self._close_observer()
        except BaseException as error:
            if primary is None:
                primary = error
            else:
                primary.add_note(f'Isaac observer cleanup also failed: {error!r}')
        try:
            from isaacsim.core.experimental.utils import app as app_utils
            app_utils.stop()
        except BaseException as error:
            if primary is None:
                primary = error
            else:
                primary.add_note(f'Isaac stop after observer cleanup also failed: {error!r}')
        self._free_views.clear()
        self._f06_robot_contact_views = {}
        self._frame_views.clear()
        self._frame_local_poses.clear()
        self._frame_pose_readback_receipts.clear()
        self._body_views.clear()
        self._articulation = None
        self._physics_scene = None
        self._manager = None
        gc.collect()
        context = self._context
        self._context = None
        self._stage = None
        try:
            if context is not None:
                context.close_stage()
        except BaseException as error:
            if primary is None:
                primary = error
            else:
                primary.add_note(f"USD stage close also failed: {type(error).__name__}: {error}")
        finally:
            try:
                self._lease.close()
            except BaseException as cleanup_error:
                if primary is None:
                    primary = cleanup_error
                else:
                    primary.add_note(f"USD snapshot lease cleanup also failed: {type(cleanup_error).__name__}: {cleanup_error}")
        if primary is not None:
            raise primary

    def close_runtime_owner(self) -> None:
        if self._runtime_owner_closed:
            return
        self._runtime_owner_closed = True
        self._app_owner.close()

    def close_receipt(self):
        """Owned close facts from the App and USD snapshot lease owners."""
        return {'schema_version': 'isaac-native-close-v1',
                'native_io_closed': self._closed,
                'runtime_owner_close_requested': self._runtime_owner_closed,
                'usd_snapshot_lease_closed': self._lease.closed,
                'app_owner': self._app_owner.close_receipt()}


def create_isaac_native_runtime_io(artifact: TaskArtifactV1, execution: ExecutionSpecV1,
                                  source: UsdRuntimeSourceV1, *,
                                  f06_pickcube_input=None,
                                  g05_effort=False, observer_render_request=None,
                                  task_render_requested=False):
    """Create the production adapter only after Core source verification."""
    source.assert_fresh()
    f06_pickcube = execution.physics_profile == 'isaac-gpu-physx-pickcube-f06-v1'
    g05_simple_effort = execution.physics_profile == 'isaac-gpu-physx-g05-5c-effort-v1'
    if not (f06_pickcube or g05_simple_effort):
        raise ValueError('unsupported Isaac native execution profile')
    if (f06_pickcube != (f06_pickcube_input is not None)
            or g05_simple_effort != bool(g05_effort)
            or (f06_pickcube and g05_simple_effort)):
        raise ValueError('Isaac native adapter requires exactly one versioned input/profile pair')
    if not (source.scene_source.source_verified or source.scene_source.locally_validated):
        raise ValueError("Isaac Core adapter requires an upstream-validated or exact locally validated USD delivery")
    if source.scene_source.representation.provider != "isaacsim":
        raise ValueError("Isaac Core adapter requires an Isaac Sim representation selection")
    if f06_pickcube:
        from .source import UsdRuntimeInputV1
        from .api import _validate_f06_pickcube_isaac_input

        if type(f06_pickcube_input) is not UsdRuntimeInputV1:
            raise TypeError('F06 Isaac adapter requires exact PickCubeIsaacRuntimeInputV1')
        _validate_f06_pickcube_isaac_input(f06_pickcube_input, artifact, execution, source)
        if (f06_pickcube_input.artifact is not artifact
                or f06_pickcube_input.execution.identity_hash != execution.identity_hash
                or f06_pickcube_input.runtime_source is not source):
            raise ValueError('F06 Isaac adapter input differs from the exact artifact/execution/source')
    launch_profile = _isaac_app_launch_profile_id(
        f06_pickcube=f06_pickcube,
        observer_render_request=observer_render_request,
        task_render_requested=task_render_requested,
    )
    owner = _process_app_owner(launch_profile_id=launch_profile)
    lease = source.scene_source.acquire_snapshot()
    try:
        return IsaacSimNativeRuntimeIOV1(
            artifact, execution, source, lease, owner,
            f06_pickcube_input=f06_pickcube_input,
            g05_effort=g05_effort,
            observer_render_request=observer_render_request,
        )
    except BaseException as primary:
        # Constructor cleanup owns the lease/App when startup begins; this is
        # idempotent and protects failures before its first import as well.
        if not lease.closed:
            try:
                lease.close()
            except BaseException as cleanup_error:
                primary.add_note(f"snapshot lease cleanup after adapter construction failure also failed: "
                                 f"{type(cleanup_error).__name__}: {cleanup_error}")
        try:
            owner.close()
        except BaseException as cleanup_error:
            primary.add_note(f"App owner cleanup after adapter construction failure also failed: "
                             f"{type(cleanup_error).__name__}: {cleanup_error}")
        raise


__all__ = ["IsaacSimAppOwnerV1", "IsaacSimNativeRuntimeIOV1", "create_isaac_native_runtime_io"]
