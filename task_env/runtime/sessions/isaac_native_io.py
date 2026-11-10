"""Narrow Isaac Sim public-API implementation of NativeRuntimeIOV1.

This module is imported only by the admitted runtime materialization route.
It owns Isaac's process App and one stage/view lease; Core's shared USD
RuntimeSession continues to own reset, control, clock projection and faults.
"""
from __future__ import annotations

from collections.abc import Mapping
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




def _f05_collision_filter_witness(stage, UsdPhysics) -> dict[str, list[dict[str, object]]]:
    """Preserve source-robot filters while detecting filters that touch F05Scene."""
    def in_task_scene(path: str) -> bool:
        return path == '/F05Scene' or path.startswith('/F05Scene/')

    filter_relationships = []
    task_scene_filter_relationships = []
    collision_groups = []
    task_scene_collision_groups = []
    for prim in stage.Traverse():
        prim_path = str(prim.GetPath())
        is_group = prim.IsA(UsdPhysics.CollisionGroup)
        if is_group:
            collision_groups.append(prim_path)
            if in_task_scene(prim_path):
                task_scene_collision_groups.append(prim_path)
        for relationship in prim.GetRelationships():
            relationship_name = str(relationship.GetName())
            targets = [str(value) for value in relationship.GetTargets()]
            if relationship_name.startswith('physics:filteredPairs') and targets:
                row = {
                    'prim_path': prim_path,
                    'relationship': relationship_name,
                    'targets': targets,
                }
                filter_relationships.append(row)
                if in_task_scene(prim_path) or any(in_task_scene(path) for path in targets):
                    task_scene_filter_relationships.append(row)
            if is_group and any(token in relationship_name for token in ('includes', 'excludes')):
                if any(in_task_scene(path) for path in targets):
                    task_scene_collision_groups.append(prim_path)
    return {
        'collision_groups': sorted(set(collision_groups)),
        'filtered_pairs': filter_relationships,
        'task_scene_collision_groups': sorted(set(task_scene_collision_groups)),
        'task_scene_filtered_pairs': task_scene_filter_relationships,
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
                 dg04_native_input=None, f06_pickcube_input=None,
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
        self._observer_sensor = None
        self._observer_path = None
        self._task_camera_path = None
        self._task_camera_geometry = None
        self._task_camera_sensor = None
        self._observer_faulted = False
        self._dg04_native_input = dg04_native_input
        self._dg04_native = execution.physics_profile == 'isaac-gpu-physx-f05-dg04-native-mimic-v1'
        self._f06_pickcube_input = f06_pickcube_input
        self._f06_pickcube = execution.physics_profile == 'isaac-gpu-physx-pickcube-f06-v1'
        self._g05_effort = execution.physics_profile == 'isaac-gpu-physx-g05-5c-effort-v1'
        if type(g05_effort) is not bool or g05_effort != self._g05_effort:
            raise ValueError('G05 Isaac I/O requires its exact effort profile flag')
        if self._dg04_native != (dg04_native_input is not None):
            raise ValueError('DG04 Isaac I/O requires its exact native candidate/profile alone')
        if self._f06_pickcube != (f06_pickcube_input is not None) or sum((
                self._dg04_native, self._f06_pickcube, self._g05_effort)) > 1:
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
        self._dg04_native_mimic_receipt = None
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
            from pxr import Gf, PhysxSchema, Sdf, UsdGeom, UsdLux, UsdPhysics
            from isaacsim.core.experimental.prims import Articulation, RigidPrim, XformPrim
            from isaacsim.core.simulation_manager import SimulationManager
            from isaacsim.core.experimental.utils import app as app_utils

            if not torch.cuda.is_available() or torch.cuda.current_device() != 0:
                raise RuntimeError("F04 requires CUDA device 0; CPU fallback is not admitted")
            expected_profile = (
                'isaac-gpu-physx-pickcube-f06-v1' if self._f06_pickcube
                else 'isaac-gpu-physx-f05-dg04-native-mimic-v1' if self._dg04_native
                else 'isaac-gpu-physx-g05-5c-effort-v1' if self._g05_effort
                else 'isaac-gpu-physx-f04-position-v1'
            )
            if (self._execution.physics_provider, self._execution.physics_backend,
                    self._execution.physics_device, self._execution.determinism_mode,
                    self._execution.physics_profile) != (
                    "isaacsim", "cuda", "cuda:0", "best_effort", expected_profile):
                raise ValueError("unsupported exact F04/F05 Isaac execution identity")
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

            if self._dg04_native:
                self._dg04_native_input.validate()
                self._verify_native_mimic_profile(
                    PhysxSchema, UsdPhysics, route='dg04',
                )
            elif self._f06_pickcube:
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
                conflicting_scene_apis = [
                    schema for schema in scene_applied_schemas_before
                    if schema.startswith(("NewtonSceneAPI", "MjcSceneAPI"))
                ]
                if conflicting_scene_apis:
                    self._update_startup_observation(
                        status="failed",
                        failure_boundary="physics_scene_semantic_conflict",
                        runtime_scene_owner_adaptation={
                            "schema_version": "g05-runtime-physx-scene-owner-adaptation-v1",
                            "status": "rejected_semantic_conflict",
                            "scene_path": str(scene_prim.GetPath()),
                            "conflicting_apis": conflicting_scene_apis,
                        },
                    )
                    raise ValueError(
                        "G05 PhysX scene has a conflicting Newton/MuJoCo scene API: "
                        f"{conflicting_scene_apis!r}"
                    )
                had_physx_scene_api = bool(scene_prim.HasAPI(PhysxSchema.PhysxSceneAPI))
                if not had_physx_scene_api:
                    scene_prim.ApplyAPI(PhysxSchema.PhysxSceneAPI)
                physx_scene_api = PhysxSchema.PhysxSceneAPI(scene_prim)
                configured_steps_per_second = int(round(1.0 / float(self._artifact.timebase.physics_dt)))
                physx_scene_api.GetTimeStepsPerSecondAttr().Set(configured_steps_per_second)
                runtime_scene_owner_adaptation = {
                    "schema_version": "g05-runtime-physx-scene-owner-adaptation-v1",
                    "status": "applied" if not had_physx_scene_api else "reaffirmed",
                    "scene_path": str(scene_prim.GetPath()),
                    "physx_scene_api": "PhysxSceneAPI",
                    "time_steps_per_second": configured_steps_per_second,
                    "physics_dt_s": float(self._artifact.timebase.physics_dt),
                    "source_bytes_modified": False,
                    "owner": "IsaacSimNativeRuntimeIOV1",
                }
                self._update_startup_observation(
                    status="runtime_scene_owner_adapted",
                    runtime_scene_owner_adaptation=runtime_scene_owner_adaptation,
                    scene_applied_schemas_after=sorted(
                        str(value) for value in scene_prim.GetAppliedSchemas()
                    ),
                    scene_time_steps_per_second_after_setup={
                        "physx:timeStepsPerSecond": int(
                            physx_scene_api.GetTimeStepsPerSecondAttr().Get()
                        ),
                    },
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
            self._update_startup_observation(
                status="simulation_manager_scene_checked",
                simulation_manager_scene_count=len(scenes),
                simulation_manager_device=str(SimulationManager.get_device()),
                public_physics_scene_paths=authored_scene_paths,
            )
            if len(scenes) != 1:
                self._update_startup_observation(
                    status="failed",
                    failure_boundary="simulation_manager_scene_count",
                )
                raise ValueError(f"F04 requires exactly one public PhysX scene, found {len(scenes)}")
            self._physics_scene = scenes[0]
            self._physics_scene.set_enabled_gpu_dynamics(True)
            if self._physics_scene.get_enabled_gpu_dynamics() is not True:
                raise RuntimeError("GPU PhysX dynamics did not remain enabled")
            scene_time_steps_after_setup = {}
            if authored_scenes and authored_scenes[0].HasAPI(PhysxSchema.PhysxSceneAPI):
                scene_time_steps_after_setup = {
                    "physx:timeStepsPerSecond": int(
                        PhysxSchema.PhysxSceneAPI(authored_scenes[0])
                        .GetTimeStepsPerSecondAttr().Get()
                    ),
                }
            self._update_startup_observation(
                physics_scene_dt_s=float(self._physics_scene.get_dt()),
                scene_applied_schemas_after=(sorted(
                    str(value) for value in authored_scenes[0].GetAppliedSchemas()
                ) if authored_scenes else []),
                scene_time_steps_per_second_after_setup=scene_time_steps_after_setup,
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
                    if self._dg04_native and semantic == 'free-cube/free_cube':
                        self._body_views[path] = RigidPrim(path, max_contact_count=32)
                        self._body_views[path].set_enabled_contact_tracking(True, threshold=0.0)
                    elif (self._f06_pickcube and semantic == 'cube-v1' and self._artifact.artifact_id in {
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
            if self._dg04_native:
                from .leaf_control import compile_isaac_native_mimic_position_receipt_v1

                witness = self._verify_public_drives(route='dg04')
                self.drive_receipt = compile_isaac_native_mimic_position_receipt_v1(
                    execution=self._execution, source=self._source,
                    native_metadata=self._metadata,
                    writer_id='panda-main/position-servo-v1',
                    native_drive_witness=witness,
                    provenance_kind='native_runtime',
                )
                self._bootstrap_receipt['native_mimic_drive_witness'] = witness
                self._bootstrap_receipt['native_adaptation_receipt'] = self.drive_receipt.to_mapping()
                self._bootstrap_receipt['source_scene_witness'] = (
                    self._verify_f05_public_scene(UsdGeom, UsdPhysics)
                )
            elif self._f06_pickcube:
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


    def _verify_f05_public_scene(self, UsdGeom, UsdPhysics) -> dict[str, object]:
        """Bind the F05 task geometry and effective public body properties."""
        support_path = '/F05Scene/support'
        cube_path = '/F05Scene/free_cube'
        support = self._stage.GetPrimAtPath(support_path)
        cube = self._stage.GetPrimAtPath(cube_path)
        support_collision_path = f'{support_path}/collision'
        cube_collision_path = f'{cube_path}/collision'
        support_collision = self._stage.GetPrimAtPath(support_collision_path)
        cube_collision = self._stage.GetPrimAtPath(cube_collision_path)
        if any(not prim or not prim.IsValid() for prim in (
                support, cube, support_collision, cube_collision)):
            raise ValueError('F05 F05 support/cube task scene prims are incomplete')
        if (not support_collision.HasAPI(UsdPhysics.CollisionAPI)
                or not cube_collision.HasAPI(UsdPhysics.CollisionAPI)
                or not cube.HasAPI(UsdPhysics.RigidBodyAPI)
                or not cube.HasAPI(UsdPhysics.MassAPI)):
            raise ValueError('F05 F05 task scene physics schemas differ from its exact recipe')
        scene_prims = [prim for prim in self._stage.Traverse() if prim.IsA(UsdPhysics.Scene)]
        if len(scene_prims) != 1:
            raise ValueError('F05 F05 task scene must bind exactly one PhysicsScene')
        gravity_direction = tuple(float(x) for x in scene_prims[0].GetAttribute(
            'physics:gravityDirection').Get())
        gravity_magnitude = float(scene_prims[0].GetAttribute('physics:gravityMagnitude').Get())
        if (not _numeric_tuple_matches(
                gravity_direction, (0.0, 0.0, -1.0), abs_tol=1e-7)
                or not _numeric_value_matches(gravity_magnitude, 9.81, abs_tol=1e-6)):
            raise ValueError('F05 F05 gravity differs from the frozen task-scene recipe')

        def box_geometry(prim, path, expected_center, expected_size):
            geom = UsdGeom.Cube(prim)
            size = float(geom.GetSizeAttr().Get())
            scale = tuple(float(x) for x in prim.GetAttribute('xformOp:scale').Get())
            root = self._stage.GetPrimAtPath(path)
            center = tuple(float(x) for x in root.GetAttribute('xformOp:translate').Get())
            dimensions = tuple(size * value for value in scale)
            if (not _numeric_tuple_matches(center, expected_center, abs_tol=1e-6)
                    or not _numeric_tuple_matches(dimensions, expected_size, abs_tol=1e-6)):
                raise ValueError(f'F05 task-scene box differs from the frozen recipe: {path}')
            return {'center_m': list(center), 'dimensions_m': list(dimensions),
                    'usd_cube_size': size, 'usd_scale': list(scale)}

        cube_geometry_receipt = box_geometry(
            cube_collision, cube_path, (1.0, 0.5, 0.9), (0.06, 0.06, 0.06),
        )
        support_geometry_receipt = box_geometry(
            support_collision, support_path, (1.0, 0.5, 0.45), (0.35, 0.35, 0.05),
        )
        mass_attr = cube.GetAttribute('physics:mass')
        if (not mass_attr or not mass_attr.IsValid()
                or not _numeric_value_matches(float(mass_attr.Get()), 0.1, abs_tol=1e-7)):
            raise ValueError('F05 task cube authored mass differs from the frozen 0.1 kg recipe')
        collision_enabled = {
            path: bool(self._stage.GetPrimAtPath(path).GetAttribute(
                'physics:collisionEnabled').Get())
            for path in (support_collision_path, cube_collision_path)
        }
        if collision_enabled != {support_collision_path: True, cube_collision_path: True}:
            raise ValueError('F05 task collision geometry is not enabled on both recipe shapes')

        material_bindings = {}
        for path in (support_collision_path, cube_collision_path):
            prim = self._stage.GetPrimAtPath(path)
            rows = []
            while prim and prim.IsValid():
                relationship = prim.GetRelationship('material:binding')
                if relationship and relationship.IsValid():
                    targets = tuple(str(target) for target in relationship.GetTargets())
                    if targets:
                        rows.append({'prim_path': str(prim.GetPath()), 'targets': list(targets)})
                prim = prim.GetParent()
            material_bindings[path] = rows
        if any(material_bindings.values()):
            raise ValueError('F05 cube/support source profile must remain without authored material bindings')

        filter_witness = _f05_collision_filter_witness(self._stage, UsdPhysics)
        filter_relationships = filter_witness['filtered_pairs']
        collision_groups = filter_witness['collision_groups']
        task_scene_filter_relationships = filter_witness['task_scene_filtered_pairs']
        task_scene_collision_groups = filter_witness['task_scene_collision_groups']
        if task_scene_collision_groups or task_scene_filter_relationships:
            raise ValueError('F05 task scene unexpectedly adds collision filtering')

        if len(self._free_views) != 1:
            raise ValueError('F05 source scene requires exactly one floating free-cube body')
        view = next(iter(self._free_views.values()))
        masses = _tensor_rows(view.get_masses(), width=1, label='F05 public cube mass')[0]
        com_positions, com_orientations = view.get_coms()
        com_position = _tensor_rows(com_positions, width=3,
                                    label='F05 public cube COM position')[0]
        com_orientation = _tensor_rows(com_orientations, width=4,
                                       label='F05 public cube COM orientation')[0]
        inertias = _tensor_rows(view.get_inertias(), width=9,
                                label='F05 public cube inertia tensor')[0]
        expected_inertia = 0.1 * 0.06 * 0.06 / 6.0
        diagonal = (inertias[0], inertias[4], inertias[8])
        if (not math.isclose(masses[0], 0.1, rel_tol=0.0, abs_tol=1e-6)
                or any(not math.isclose(value, 0.0, rel_tol=0.0, abs_tol=1e-6)
                       for value in com_position)
                or any(not math.isclose(actual, expected_inertia, rel_tol=0.05, abs_tol=1e-7)
                       for actual in diagonal)
                or any(not math.isclose(inertias[index], 0.0, rel_tol=0.0, abs_tol=1e-7)
                       for index in (1, 2, 3, 5, 6, 7))):
            raise ValueError('F05 public cube mass/COM/inertia differ from the 0.1 kg uniform cube profile')
        return {
            'schema_version': 'f05-isaac-public-source-scene-witness-v1',
            'gravity_direction': list(gravity_direction),
            'gravity_magnitude_m_s2': gravity_magnitude,
            'support_geometry': support_geometry_receipt,
            'free_cube_geometry': cube_geometry_receipt,
            'authored_mass_kg': float(mass_attr.Get()),
            'public_mass_kg': masses[0],
            'public_com_position_body_m': list(com_position),
            'public_com_orientation_body_wxyz': list(com_orientation),
            'public_inertia_tensor_kg_m2_row_major': list(inertias),
            'uniform_cube_inertia_reference_kg_m2': expected_inertia,
            'collision_enabled': collision_enabled,
            'material_binding_targets': material_bindings,
            'collision_groups': collision_groups,
            'filtered_pairs': filter_relationships,
            'task_scene_collision_groups': task_scene_collision_groups,
            'task_scene_filtered_pairs': task_scene_filter_relationships,
            'contact_query': {
                'public_api': 'RigidPrim.get_raw_contact_data',
                'sensor_path': cube_path,
                'matched_actor_path': support_collision_path,
                'contact_report_api_enabled_via': 'RigidPrim.set_enabled_contact_tracking',
                'physics_collision_filter_authored': bool(
                    task_scene_collision_groups or task_scene_filter_relationships
                ),
            },
            'cross_engine_material_equivalence_claimed': False,
        }

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

    def _read_dg04_contact_witness(self) -> dict[str, object]:
        """Read public raw contacts and select only the frozen support collider."""
        if not self._dg04_native or not self._free_views:
            raise RuntimeError('F05 Isaac contact readback requires the exact free-cube view')
        view = next(iter(self._free_views.values()))
        result = view.get_raw_contact_data(dt=float(self._artifact.timebase.physics_dt))
        if type(result) is not tuple or len(result) != 7:
            raise ValueError('DG04 public raw contact API returned an unexpected seven-array result')
        normal_forces, _points, normals, distances, counts, starts, actor_ids = result
        count_rows = counts.numpy().tolist()
        start_rows = starts.numpy().tolist()
        if len(count_rows) != 1 or len(start_rows) != 1:
            raise ValueError('DG04 public raw contact view must return one free-cube sensor row')
        raw_contact_count = int(count_rows[0])
        contact_start = int(start_rows[0])
        if raw_contact_count < 0 or raw_contact_count > 32 or contact_start < 0:
            raise ValueError('DG04 public contact count/start index is outside the bounded view')
        force_rows = normal_forces.numpy().tolist()
        actor_paths = (
            view.get_actor_paths_from_ids(
                actor_ids.to('cpu')[contact_start:contact_start + raw_contact_count],
            )
            if raw_contact_count else []
        )
        selected = force_rows[contact_start:contact_start + raw_contact_count]
        if len(selected) != raw_contact_count or len(actor_paths) != raw_contact_count:
            raise ValueError('DG04 public contact force slice exceeds the returned contact buffer')
        force_values = tuple(float(row[0]) for row in selected)
        normal_rows = normals.numpy().tolist()
        distance_rows = distances.numpy().tolist()
        selected_normals = tuple(
            tuple(float(value) for value in normal_rows[contact_start + index])
            for index in range(raw_contact_count)
        )
        selected_separations = tuple(
            float(distance_rows[contact_start + index][0])
            for index in range(raw_contact_count)
        )
        if (len(selected_normals) != raw_contact_count
                or len(selected_separations) != raw_contact_count):
            raise ValueError('DG04 public contact normal/separation slices exceed the returned buffer')
        invalid_force_indices = tuple(
            index for index, value in enumerate(force_values)
            if (not math.isfinite(value)
                or not all(math.isfinite(component) for component in selected_normals[index])
                or not math.isfinite(selected_separations[index]))
        )
        if invalid_force_indices:
            invalid_samples = tuple({
                'contact_index': contact_start + index,
                'actor_path': actor_paths[index],
                'force_scalar_N': force_values[index],
                'normal_world': selected_normals[index],
                'separation_m': selected_separations[index],
            } for index in (invalid_force_indices or tuple(
                index for index, value in enumerate(force_values) if value < 0.0
            )))
            raise ValueError(
                'F05 public raw contact data contains invalid force/normal/separation values; '
                f'count={raw_contact_count}, start={contact_start}, invalid={invalid_samples!r}'
            )
        force_magnitudes = tuple(abs(value) for value in force_values)
        support_path = '/F05Scene/support/collision'
        support_indices = tuple(
            index for index, path in enumerate(actor_paths)
            if path == '/F05Scene/support' or path == support_path
            or path.startswith(support_path + '/')
        )
        support_forces = tuple(force_magnitudes[index] for index in support_indices)
        witness = {
            'schema_version': (
                'f05-dg04-native-contact-witness-v1'
            ),
            'provenance_kind': 'native_runtime',
            'api': 'RigidPrim.get_raw_contact_data',
            'sensor_path': '/F05Scene/free_cube',
            'support_path': support_path,
            'physics_dt_s': float(self._artifact.timebase.physics_dt),
            'raw_contact_count': raw_contact_count,
            'raw_contact_actor_paths': list(actor_paths),
            'raw_contact_normal_forces_N': list(force_magnitudes),
            'contact_count': len(support_indices),
            'support_contact_normal_forces_N': list(support_forces),
            'normal_force_sum_N': math.fsum(support_forces),
            'contact_present': bool(support_indices),
        }
        if self._dg04_native:
            witness.update({
                'raw_contact_signed_normal_force_scalars_N': list(force_values),
                'raw_contact_normals_world': [list(row) for row in selected_normals],
                'raw_contact_separations_m': list(selected_separations),
                'force_magnitude_mapping': 'abs(raw_signed_normal_force_scalar_N)',
            })
        return witness

    def _verify_native_mimic_profile(self, PhysxSchema, UsdPhysics, *, route: str) -> None:
        """Verify the shared Panda mimic relation with route-owned drive settings."""
        if route == 'dg04':
            if not self._dg04_native or self._stage is None:
                raise RuntimeError('DG04 native mimic requires its exact composed USD stage')
            label, entity_id = 'DG04', 'panda-main'
            expected_source_sha256 = '96ad67da03710f17f798c9478fd9e9efdf24a3bf8359f05e456dd9fb158ea273'
            leader_drive = ('force', 2000.0, 100.0, 100.0)
            authors_drive = True
        elif route == 'f06':
            if not self._f06_pickcube or self._stage is None:
                raise RuntimeError('F06 native mimic requires its exact composed USD stage')
            label, entity_id = 'F06', 'panda-v1'
            expected_source_sha256 = None
            leader_drive = ('force', 5000.0, 120.0, 5.0)
            authors_drive = False
        else:
            raise ValueError(f'unsupported Isaac mimic profile route: {route!r}')

        import xml.etree.ElementTree as ET

        finger_joints = ('finger_joint1', 'finger_joint2')
        if {self._source.joints.get(f'{entity_id}/{name}') for name in finger_joints} != set(finger_joints):
            raise ValueError(f'{label} RuntimeSource does not bind the exact finger Joint pair')
        source_xml = self._source.scene_source.loaded_delivery.source_input_bytes.get('panda.xml')
        if type(source_xml) is not bytes:
            raise ValueError(f'{label} source delivery omits the original Panda XML bytes')
        source_xml_sha256 = hashlib.sha256(source_xml).hexdigest()
        if expected_source_sha256 is not None and source_xml_sha256 != expected_source_sha256:
            raise ValueError('DG04 source adaptation requires the exact frozen Menagerie Panda XML bytes')
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
        if authors_drive:
            if drive_exists:
                raise ValueError('DG04 source leader unexpectedly already has a second linear DriveAPI')
            drive = UsdPhysics.DriveAPI.Apply(reference, 'linear')
            if not drive:
                raise RuntimeError('DG04 could not apply the public linear DriveAPI to the mimic leader')
            for attr_name, value in zip(('Type', 'Stiffness', 'Damping', 'MaxForce'), leader_drive):
                creator = getattr(drive, f'Create{attr_name}Attr', None)
                if not callable(creator):
                    raise RuntimeError(f'DG04 installed UsdPhysics DriveAPI lacks Create{attr_name}Attr')
                attribute = creator()
                if not attribute or not attribute.IsValid() or attribute.Set(value) is False:
                    raise RuntimeError(f'DG04 public DriveAPI rejected the fixed leader {attr_name} value')
        else:
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

        if route == 'dg04':
            self._dg04_native_mimic_receipt = {
                'schema_version': 'isaac-dg04-native-mimic-stage-receipt-v1',
                'source_entry_sha256': source_xml_sha256,
                'follower_joint': 'finger_joint2', 'follower_path': str(follower.GetPath()),
                'reference_joint': 'finger_joint1', 'reference_path': str(reference.GetPath()),
                'source_polycoef': polycoef,
                'native_mimic_api': 'PhysxMimicJointAPI:transX',
                'native_mimic_properties': {
                    'gearing': float(follower.GetAttribute('physxMimicJoint:transX:gearing').Get()),
                    'offset': float(follower.GetAttribute('physxMimicJoint:transX:offset').Get()),
                    'naturalFrequency': float(frequency_attr.Get()),
                    'dampingRatio': float(damping_attr.Get()),
                },
                'native_drive_api': 'PhysicsDriveAPI:linear',
                'leader_drive_joint': 'finger_joint1', 'leader_drive_path': str(reference.GetPath()),
                'leader_drive_properties': {
                    'type': actual_drive[0], 'stiffness_N_m': actual_drive[1],
                    'damping_N_s_m': actual_drive[2], 'max_force_N': actual_drive[3],
                },
                'profile_id': 'isaacsim-6.2-physx-native-mimic-leader-drive-v1',
                'runtime_stage_mutated': True,
            }
        else:
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
        elif route == 'dg04':
            if (not self._dg04_native or self._stage is None
                    or self._dg04_native_mimic_receipt is None):
                raise RuntimeError('DG04 stage mimic/drive profile was not initialized before public view checks')
            label = 'DG04'
            schema_version = 'isaac-dg04-native-mimic-drive-witness-v1'
            # Keep the source-derived Menagerie actuator force limits distinct
            # from F06's task-specific 250 N arm limits.
            arm_expected = {
                'joint1': (4500.0, 450.0, 87.0),
                'joint2': (4500.0, 450.0, 87.0),
                'joint3': (3500.0, 350.0, 87.0),
                'joint4': (3500.0, 350.0, 87.0),
                'joint5': (2000.0, 200.0, 12.0),
                'joint6': (2000.0, 200.0, 12.0),
                'joint7': (2000.0, 200.0, 12.0),
            }
            leader_expected = (2000.0, 100.0, 100.0)
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
        dg04_native = getattr(self, "_dg04_native", False)
        f06_pickcube = getattr(self, "_f06_pickcube", False)
        g05_effort = getattr(self, "_g05_effort", False)
        if g05_effort:
            valid_targets = not expected_targets
        elif dg04_native or f06_pickcube:
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
            if dg04_native or f06_pickcube:
                self._articulation.set_dof_position_targets(
                    [item[2] for item in expected_targets],
                    dof_indices=[int(item[0]) for item in expected_targets],
                )
                target_readback = _tensor_rows(
                    self._articulation.get_dof_position_targets(
                        dof_indices=[int(item[0]) for item in expected_targets],
                    ),
                    width=8, label=('F06' if f06_pickcube else 'DG04')
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
        dg04_native = getattr(self, "_dg04_native", False)
        if dg04_native or f06_pickcube:
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
            if dg04_native or f06_pickcube:
                label = 'F06' if f06_pickcube else 'DG04'
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
            if dg04_native or f06_pickcube:
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
            elif self._dg04_native or self._f06_pickcube:
                target = self._last_native_mimic_target
                if (not isinstance(target, dict)
                        or target.get('drive_receipt_identity_sha256') != self.drive_receipt.identity_sha256
                        or not _is_sha256_identity(target.get('target_identity_sha256'))):
                    raise RuntimeError('DG04 physics substep has no current acknowledged leader position target')
                self._sync()
                q = _tensor_rows(self._articulation.get_dof_positions(), width=len(self._dof_names),
                                 label='DG04 post-step DOF position')[0]
                qd = _tensor_rows(self._articulation.get_dof_velocities(), width=len(self._dof_names),
                                  label='DG04 post-step DOF velocity')[0]
                reference_index = self._dof_index['finger_joint1']
                follower_index = self._dof_index['finger_joint2']
                if self._f06_pickcube:
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
                else:
                    applied_effort = _tensor_rows(
                        self._articulation.get_dof_projected_joint_forces(
                            dof_indices=[reference_index],
                        ),
                        width=1, label='DG04 public projected active leader effort readback',
                    )[0][0]
                    projected_joint_force = None
                reference_position = float(q[reference_index])
                follower_position = float(q[follower_index])
                reference_velocity = float(qd[reference_index])
                follower_velocity = float(qd[follower_index])
                native_adaptation_application = {
                    'schema_version': 'native-physx-mimic-substep-application-v1',
                    'profile_id': (
                        ('isaacsim-' + self._app_owner.sdk_identity['normalized_version'].rsplit('.', 2)[0]
                         + '-pickcube-physx-mimic-5n-v1') if self._f06_pickcube
                        else 'isaacsim-6.2-physx-native-mimic-leader-drive-v1'
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
                    'maximum_effort_N': 5.0 if self._f06_pickcube else 100.0,
                    'public_effort_api': (
                        'Articulation.get_dof_efforts' if self._f06_pickcube
                        else 'Articulation.get_dof_projected_joint_forces'
                    ),
                    'effort_measurement_semantics': (
                        'actuation_force' if self._f06_pickcube
                        else 'projected_active_joint_force'
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
                if self._dg04_native:
                    native_adaptation_application['public_contact_witness'] = (
                        self._read_dg04_contact_witness()
                    )
        except BaseException as error:
            if getattr(self, '_physical_effort_pending', None) is not None:
                self._physical_effort_fault = True
            error.add_note(
                f"one native physics step was attempted; pre-step counter={before!r}; "
                f"DG04 native adaptation receipt={native_adaptation_application!r}"
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
        self.task_camera_binding(state)
        try:
            return self._capture_observer_admitted(camera, state, resolve_camera, normalize_rgb,
                                                   CanonicalCameraObservation, task=True)
        except BaseException as error:
            self._observer_faulted = True
            try:
                self._close_task_camera_sensor()
            except BaseException as cleanup_error:
                error.add_note(f'Isaac task sensor cleanup also failed: {cleanup_error!r}')
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

    def _capture_observer_admitted(self, camera, state, resolve_camera, normalize_rgb, observation_type, *, task=False):
        import json
        import uuid
        import numpy as np
        import omni.replicator.core as rep
        import omni.timeline
        import omni.usd
        from pxr import Gf, UsdGeom
        from isaacsim.sensors.experimental.rtx import RtxCamera, CameraSensor
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
        task_sensor_created = False
        if task:
            path = self._task_camera_path
            if self._task_camera_sensor is None:
                authoring = RtxCamera(path, tick_rate=0.0, reset_xform_op_properties=False)
                self._task_camera_sensor = CameraSensor(authoring, resolution=(camera.height, camera.width),
                                                        annotators=['rgb'])
                task_sensor_created = True
            sensor = self._task_camera_sensor
        else:
            if self._observer_sensor is None:
                path = '/GeoChoraObserver_' + uuid.uuid4().hex
                self._observer_path = path
                authoring = RtxCamera(path, tick_rate=0.0)
                self._observer_sensor = CameraSensor(authoring, resolution=(camera.height, camera.width),
                                                     annotators=['rgb'])
            path, sensor = self._observer_path, self._observer_sensor
        stage = omni.usd.get_context().get_stage()
        if stage is None or stage != self._stage:
            raise RuntimeError('Isaac observer lost its leased USD stage')
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsValid():
            raise RuntimeError('Isaac observer camera prim is unavailable')
        usd_camera = UsdGeom.Camera(prim)
        focal = 24.0
        vertical = 2.0 * focal * math.tan(camera.fov_y / 2.0)
        usd_camera.GetFocalLengthAttr().Set(focal)
        usd_camera.GetVerticalApertureAttr().Set(vertical)
        usd_camera.GetHorizontalApertureAttr().Set(vertical * camera.width / camera.height)
        usd_camera.GetClippingRangeAttr().Set(Gf.Vec2f(camera.near, camera.far))
        world = np.asarray(metadata.T_world_from_camera, dtype=np.float64).copy()
        world[:3, :3] = world[:3, :3] @ np.diag([1.0, -1.0, -1.0])
        xform = UsdGeom.Xformable(prim)
        xform.ClearXformOpOrder()
        op = xform.AddTransformOp()
        op.Set(Gf.Matrix4d(*[float(value) for value in world.T.reshape(-1)]))
        actual = np.asarray(UsdGeom.XformCache().GetLocalToWorldTransform(prim)).T
        if not np.allclose(actual, world, atol=1e-6, rtol=0):
            raise RuntimeError('Isaac realized observer camera transform differs from the request')
        task_completions = []

        def render_once(operation, *, allow_unready=False):
            if task:
                import omni.graph.core as og
                path = '/Render/PostProcess/SDGPipeline/PostProcessDispatcher'
                node = og.get_node_by_path(path)
                prior_count = int(node.get_compute_count()) if node else 0
            rep.orchestrator.step(rt_subframes=1, pause_timeline=True, delta_time=0.0, wait_for_render=True)
            self._check_observer_clock(before, playing=timeline.is_playing(), operation=operation)
            if task:
                node = og.get_node_by_path(path)
                after_count = int(node.get_compute_count()) if node else 0
                numerator = node.get_attribute('outputs:referenceTimeNumerator').get() if node else None
                denominator = node.get_attribute('outputs:referenceTimeDenominator').get() if node else None
                reference = (float(numerator) / float(denominator)
                             if numerator is not None and denominator not in (None, 0) else None)
                count_delta = after_count - prior_count
                # Replicator 6.2 logs and returns at 1000 wait iterations.
                # Only a new dispatch with a reference time matching the
                # native physics clock is eligible as a completed capture.
                complete = (0 < count_delta < 1000 and reference is not None
                            and math.isfinite(reference) and abs(reference - float(before[1])) <= 1e-6)
                task_completions.append({'operation': operation, 'dispatcher_before': prior_count,
                                         'dispatcher_after': after_count,
                                         'reference_time': reference, 'physics_time': float(before[1]),
                                         'timeline_time': float(timeline.get_current_time()),
                                         'completed': complete})
                if not complete and not allow_unready:
                    raise RuntimeError(f'Isaac task render did not complete at the current physics time: {task_completions[-1]!r}')
                return complete

        if task:
            # The task sensor is first created inside reset, before the old
            # post-reset observer ever rendered.  Let RTX initialize its
            # settings without publishing this warm-up frame or advancing
            # the already observed physics boundary.
            if task_sensor_created:
                for _ in range(4):
                    self._app_owner.app.update()
                    self._check_observer_clock(before, playing=timeline.is_playing(), operation='task sensor initialization')
            for _ in range(4):
                if render_once('task sensor warmup', allow_unready=True):
                    break
            else:
                raise RuntimeError(f'Isaac task sensor did not complete bounded warmup: {task_completions!r}')
        color_settings = _read_isaac_observer_color_settings()
        data = None
        for _ in range(8):
            render_once('task sensor rendering' if task else 'observer rendering')
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
                                            'dispatcher_completions': task_completions}
        rgb = np.array(data.numpy(), copy=True)
        selection = RendererSelectionV1('renderer-selection-v1', 'isaacsim', 'rtx',
                                        'v211_isaac_rtx_task_rgb_v1' if task else
                                        'v211_isaac_rtx_observer_v1', 'cuda:0')
        capability = {'schema': 'v211-isaac-rtx-observer-v1', 'sdk': '6.2.0.0',
                      'capture': 'CameraSensor RGB; Replicator wait_for_render; owned host copy',
                      'color': color_settings,
                      'stage_time_range': self._observer_stage_time_range_receipt,
                      'render_light': self._observer_render_light_receipt}
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
                                  dg04_native_input=None, f06_pickcube_input=None,
                                  g05_effort=False, observer_render_request=None):
    """Create the production adapter only after Core source verification."""
    source.assert_fresh()
    dg04_native = execution.physics_profile == 'isaac-gpu-physx-f05-dg04-native-mimic-v1'
    f06_pickcube = execution.physics_profile == 'isaac-gpu-physx-pickcube-f06-v1'
    g05_simple_effort = execution.physics_profile == 'isaac-gpu-physx-g05-5c-effort-v1'
    if (dg04_native != (dg04_native_input is not None)
            or f06_pickcube != (f06_pickcube_input is not None)
            or g05_simple_effort != bool(g05_effort)
            or sum((dg04_native, f06_pickcube, g05_simple_effort)) > 1):
        raise ValueError('Isaac native adapter requires exactly one versioned input/profile pair')
    if not (source.scene_source.source_verified or source.scene_source.locally_validated):
        raise ValueError("Isaac Core adapter requires an upstream-validated or exact locally validated USD delivery")
    if source.scene_source.representation.provider != "isaacsim":
        raise ValueError("Isaac Core adapter requires an Isaac Sim representation selection")
    if dg04_native:
        from .api import _require_session_admission_input_route

        _require_session_admission_input_route(
            dg04_native_input, 'f05_dg04',
            'DG04 Isaac adapter requires exact F05Dg04IsaacNativeCandidateInputV1',
        )
        dg04_native_input.validate()
        if (dg04_native_input.artifact is not artifact
                or dg04_native_input.execution.identity_hash != execution.identity_hash
                or dg04_native_input.runtime_source is not source):
            raise ValueError('DG04 Isaac adapter candidate differs from the exact artifact/execution/source')
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
    launch_profile = (V211_ISAAC_RENDER_APP_LAUNCH_PROFILE_V1 if observer_render_request is not None
                      else F06_ISAAC_APP_LAUNCH_PROFILE_V1 if f06_pickcube else None)
    owner = _process_app_owner(launch_profile_id=launch_profile)
    lease = source.scene_source.acquire_snapshot()
    try:
        return IsaacSimNativeRuntimeIOV1(
            artifact, execution, source, lease, owner,
            dg04_native_input=dg04_native_input,
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
