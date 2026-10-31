"""Narrow Isaac Sim 6.2 public-API implementation of NativeRuntimeIOV1.

This module is imported only by the admitted runtime materialization route.
It owns Isaac's process App and one stage/view lease; Core's shared USD
RuntimeSession continues to own reset, control, clock projection and faults.
"""
from __future__ import annotations

from collections.abc import Mapping
from importlib import metadata as importlib_metadata
import math
from threading import RLock
from typing import Any

from ...artifacts import ExecutionSpecV1, PoseWorld, TaskArtifactV1
from ...artifacts.execution import ResetSample
from ...assembly.source import UsdSnapshotLeaseV1
from .free_joint_state import PublicRigidBodyReadbackV1
from .native_io import (
    NativeAdvanceReceiptV1, NativePositionWriteAckV1,
    NativeResetWriteReceiptV1, NativeRuntimeIOMetadataV1, NativeSourceTendonWriteAckV1,
    NativeRuntimeReadbackV1,
)
from .source import UsdRuntimeSourceV1


_APP_LOCK = RLock()
_PROCESS_APP_OWNER: "IsaacSimAppOwnerV1 | None" = None


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


def _dg03_collision_filter_witness(stage, UsdPhysics) -> dict[str, list[dict[str, object]]]:
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

    def __init__(self) -> None:
        self._app = None
        self._closed = False
        self._process_lifetime_holds = 0
        self._close_requested = False
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

    @property
    def app(self):
        return self._app

    def open(self):
        if self._closed or self._close_attempted:
            raise RuntimeError("Isaac App owner cannot reopen after close")
        if self._app is None:
            installed = importlib_metadata.version("isaacsim")
            if installed != "6.2.0.0":
                raise RuntimeError(
                    f"F04 requires the installed isaacsim 6.2.0.0 distribution, found {installed}"
                )
            self.start_attempts += 1
            from isaacsim.simulation_app import SimulationApp

            self._app = SimulationApp({
                "headless": True,
                "enable_cameras": False,
                "limit_cpu_threads": 4,
                # Kit's default fast shutdown can terminate Python before the
                # worker writes its producer-owned completion receipt.
                "fast_shutdown": False,
            })
            import carb

            actual = int(carb.settings.get_settings().get_as_int(
                "/plugins/carb.tasking.plugin/threadCount"
            ))
            try:
                _validate_isaac_task_thread_count(actual)
            except RuntimeError as primary:
                try:
                    self._close_now()
                except BaseException as cleanup_error:
                    primary.add_note(
                        "Isaac App cleanup after task-thread validation also failed: "
                        f"{type(cleanup_error).__name__}: {cleanup_error}"
                    )
                raise
        return self._app

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


def _process_app_owner() -> IsaacSimAppOwnerV1:
    global _PROCESS_APP_OWNER
    with _APP_LOCK:
        if _PROCESS_APP_OWNER is None:
            _PROCESS_APP_OWNER = IsaacSimAppOwnerV1()
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


def _pose_from_view(view) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
    positions, orientations = view.get_world_poses()
    p = _tensor_rows(positions, width=3, label="world position")[0]
    q = _tensor_rows(orientations, width=4, label="world orientation")[0]
    # Isaac Sim's experimental public RigidPrim API returns scalar-first wxyz.
    return p, q


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


class IsaacSimNativeRuntimeIOV1:
    """Implement the six Core native-I/O operations over public Isaac APIs."""

    execution_provenance_kind = "native_runtime"

    def __init__(self, artifact: TaskArtifactV1, execution: ExecutionSpecV1,
                 source: UsdRuntimeSourceV1, lease: UsdSnapshotLeaseV1,
                 app_owner: IsaacSimAppOwnerV1, *, dg03_input=None):
        if type(artifact) is not TaskArtifactV1 or type(execution) is not ExecutionSpecV1:
            raise TypeError("Isaac native I/O requires exact TaskArtifactV1 and ExecutionSpecV1")
        if type(source) is not UsdRuntimeSourceV1 or type(lease) is not UsdSnapshotLeaseV1:
            raise TypeError("Isaac native I/O requires verified USD RuntimeSource and owned snapshot lease")
        self._artifact, self._execution, self._source = artifact, execution, source
        self._lease, self._app_owner = lease, app_owner
        self._dg03_input = dg03_input
        self._dg03 = execution.physics_profile == 'isaac-gpu-physx-f05-dg03-usd-v1'
        if self._dg03 != (dg03_input is not None):
            raise ValueError('DG03 Isaac I/O requires its exact candidate input and profile together')
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
        self._free_views: dict[str, Any] = {}
        self._dof_names: tuple[str, ...] = ()
        self._dof_index: dict[str, int] = {}
        self._position_limits: dict[str, tuple[float, float]] = {}
        self._episode_origin_step: int | None = None
        self._episode_origin_time: float | None = None
        self._native_step_count = 0
        self._metadata: NativeRuntimeIOMetadataV1 | None = None
        self.drive_receipt = None
        self._dg03_mimic_receipt = None
        self._dg03_mimic_frequency_attribute = None
        self._dg03_mimic_damping_attribute = None
        self._source_tendon_target = None
        self._open_public_runtime()

    def _open_public_runtime(self) -> None:
        try:
            self._app_owner.open()
            import omni.usd
            import torch
            from pxr import PhysxSchema, Sdf, UsdGeom, UsdPhysics
            from isaacsim.core.experimental.prims import Articulation, RigidPrim, XformPrim
            from isaacsim.core.simulation_manager import SimulationManager
            from isaacsim.core.experimental.utils import app as app_utils

            if not torch.cuda.is_available() or torch.cuda.current_device() != 0:
                raise RuntimeError("F04 requires CUDA device 0; CPU fallback is not admitted")
            expected_profile = (
                'isaac-gpu-physx-f05-dg03-usd-v1' if self._dg03
                else 'isaac-gpu-physx-f04-position-v1'
            )
            if (self._execution.physics_provider, self._execution.physics_backend,
                    self._execution.physics_device, self._execution.determinism_mode,
                    self._execution.physics_profile) != (
                    "isaacsim", "cuda", "cuda:0", "best_effort", expected_profile):
                raise ValueError("unsupported exact F04/DG03 Isaac execution identity")
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

            if self._dg03:
                self._dg03_input.validate()
                self._verify_dg03_mimic(PhysxSchema, UsdPhysics)

            authored_scenes = [p for p in self._stage.Traverse() if p.IsA(UsdPhysics.Scene)]
            if len(authored_scenes) != 1:
                raise ValueError(
                    "verified USD source must author exactly one PhysicsScene before SimulationManager setup"
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
            if len(scenes) != 1:
                raise ValueError(f"F04 requires exactly one public PhysX scene, found {len(scenes)}")
            self._physics_scene = scenes[0]
            self._physics_scene.set_enabled_gpu_dynamics(True)
            if self._physics_scene.get_enabled_gpu_dynamics() is not True:
                raise RuntimeError("GPU PhysX dynamics did not remain enabled")
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
                    if self._dg03 and semantic == 'free-cube/free_cube':
                        self._body_views[path] = RigidPrim(path, max_contact_count=32)
                        self._body_views[path].set_enabled_contact_tracking(True, threshold=0.0)
                    else:
                        self._body_views[path] = RigidPrim(path)
                self._frame_views[semantic] = self._body_views[path]
            for semantic, native in self._source.frames.items():
                path = _native_prim_path(native, entry_prim)
                if path not in self._frame_views:
                    prim = self._stage.GetPrimAtPath(path)
                    if not prim or not prim.IsValid():
                        raise ValueError(f"USD RuntimeSource Frame binding is not a composed prim: {path}")
                    self._frame_views[semantic] = (
                        RigidPrim(path) if prim.HasAPI(UsdPhysics.RigidBodyAPI) else XformPrim(path)
                    )
            for semantic in self._source.free_joints:
                body_path = _native_prim_path(self._source.bodies[semantic], entry_prim)
                self._free_views[semantic] = self._body_views[body_path]
            if len(self._free_views) != 1:
                raise ValueError("F04 requires exactly one mapped floating rigid body")
            # Isaac's tensor views become live only after the public timeline
            # starts and Kit processes its stage callbacks. Count this bootstrap
            # separately from Core reset and public interval advances.
            self._bootstrap_before = (
                int(SimulationManager.get_num_physics_steps()),
                float(SimulationManager.get_simulation_time()),
            )
            app_utils.play()
            app_utils.update_app(steps=2)
            self._bootstrap_after = (
                int(SimulationManager.get_num_physics_steps()),
                float(SimulationManager.get_simulation_time()),
            )
            for view in (self._articulation, *self._body_views.values(),
                         *(v for v in self._frame_views.values() if isinstance(v, RigidPrim))):
                if hasattr(view, "is_physics_tensor_entity_valid") and not view.is_physics_tensor_entity_valid():
                    raise RuntimeError("public physics tensor view did not initialize after Kit bootstrap")
            self._dof_names = tuple(str(name) for name in self._articulation.dof_names)
            expected_dofs = set(self._source.joint_targets.values())
            if len(self._dof_names) != 9 or len(set(self._dof_names)) != 9 or set(self._dof_names) != expected_dofs:
                raise ValueError(
                    "public articulation DOF names differ from the exact source-bound nine-joint mapping: "
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
                raise RuntimeError("public physics counters moved backwards during bootstrap")
            if abs(bootstrap_time - bootstrap_steps * float(self._artifact.timebase.physics_dt)) > 1e-8:
                raise RuntimeError("public physics bootstrap counter/time deltas disagree with the configured dt")
            self._bootstrap_receipt = {
                "schema_version": "isaac-public-physics-bootstrap-v1",
                "step_index_before": self._bootstrap_before[0],
                "step_index_after": self._bootstrap_after[0],
                "simulation_time_before_s": self._bootstrap_before[1],
                "simulation_time_after_s": self._bootstrap_after[1],
                "physics_steps": bootstrap_steps,
                "physics_time_s": bootstrap_time,
                "physics_dt_s": float(self._artifact.timebase.physics_dt),
                "application_updates": 2,
                "mapped_floating_body_paths": sorted(
                    _native_prim_path(self._source.bodies[semantic], entry_prim)
                    for semantic in self._source.free_joints
                ),
                "static_collision_paths": list(static_collision_paths),
            }
            self._torch = torch
            self._metadata = NativeRuntimeIOMetadataV1(
                "native-runtime-io-metadata-v1", self._source.source_id,
                self._source.source_closure_digest, self._source.scene_definition.identity_hash,
                self._artifact.identity_hash, self._execution.identity_hash,
                "isaacsim", "isaacsim-6.2.0.0", "cuda", "cuda:0", "best_effort",
                float(self._artifact.timebase.physics_dt),
                int(self._artifact.timebase.control_substeps), self._dof_names,
                self._position_limits,
            )
            if self._dg03:
                from .leaf_control import compile_isaac_source_tendon_receipt_v1

                self.drive_receipt = compile_isaac_source_tendon_receipt_v1(
                    execution=self._execution, source=self._source,
                    native_metadata=self._metadata, writer_id='panda-main/position-servo-v1',
                )
                mimic = self._dg03_mimic_receipt
                expected_mimic = {
                    'schema_version': 'physx-public-source-mimic-verification-v1',
                    'follower_joint': 'finger_joint2', 'reference_joint': 'finger_joint1',
                    'source_polycoef': (0.0, 1.0, 0.0, 0.0, 0.0),
                    'source_solref': (0.005, 1.0), 'source_solimp': (0.95, 0.99, 0.001),
                    'schema_authored_in_delivery': True, 'runtime_stage_mutated': True,
                }
                if (mimic is None or any(mimic.get(name) != value
                                         for name, value in expected_mimic.items())
                        or mimic.get('source_solimp_effective') != (0.95, 0.99, 0.001, 0.5, 2.0)
                        or not math.isclose(
                            float(mimic['physx_attributes']['naturalFrequency']),
                            self.drive_receipt.mimic_frequency_for_residual(0.0),
                            rel_tol=0.0, abs_tol=1e-6)
                        or not math.isclose(
                            float(mimic['physx_attributes']['dampingRatio']),
                            self.drive_receipt.mimic_damping_ratio_for_residual(0.0),
                            rel_tol=0.0, abs_tol=1e-6)):
                    raise ValueError('DG03 public mimic source mapping differs from its source-bound drive receipt')
                self._bootstrap_receipt['source_arm_drive_witness'] = (
                    self._verify_dg03_public_drives(UsdPhysics)
                )
                self._bootstrap_receipt['source_scene_witness'] = (
                    self._verify_dg03_public_scene(UsdGeom, UsdPhysics)
                )
            self._manager = SimulationManager
        except BaseException as primary:
            import gc
            import traceback

            original_traceback = "".join(traceback.format_exception(
                type(primary), primary, primary.__traceback__,
            ))
            # Failed construction can keep CUDA/Warp views alive through the
            # traceback. Detach it and release views before closing Kit.
            primary.__traceback__ = None
            self._free_views.clear()
            self._frame_views.clear()
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

    def _verify_dg03_public_drives(self, UsdPhysics) -> dict[str, object]:
        """Compare exact MJCF Arm actuators with public Stage and Articulation views."""
        receipt = self.drive_receipt
        if receipt is None or receipt.arm_control_ranges is None:
            raise RuntimeError('DG03 source Arm drive receipt is not bound to the compiled source')
        authored = []
        for prim in self._stage.Traverse():
            for schema in prim.GetAppliedSchemas():
                if str(schema).startswith('PhysicsDriveAPI:'):
                    authored.append((str(prim.GetPath()), str(prim.GetName()), str(schema)))
        expected_prim_names = {f'joint{index}' for index in range(1, 8)}
        if (len(authored) != 7 or {name for _path, name, _schema in authored} != expected_prim_names
                or any(schema != 'PhysicsDriveAPI:angular' for _path, _name, schema in authored)):
            raise ValueError('DG03 composed stage must contain exactly seven angular Arm DriveAPI consumers')

        stiffness_tensor, damping_tensor = self._articulation.get_dof_gains()
        stiffness = _tensor_rows(stiffness_tensor, width=len(self._dof_names),
                                 label='DG03 public DOF stiffness')[0]
        damping = _tensor_rows(damping_tensor, width=len(self._dof_names),
                               label='DG03 public DOF damping')[0]
        effort_tensor = self._articulation.get_dof_max_efforts()
        effort_rows = effort_tensor.numpy().tolist()
        if effort_rows and not isinstance(effort_rows[0], (tuple, list)):
            effort_rows = [effort_rows]
        if not effort_rows or len(effort_rows[0]) != len(self._dof_names):
            raise ValueError('DG03 public maximum-effort view has unexpected shape')
        max_effort = tuple(float(value) for value in effort_rows[0])
        drive_types_rows = self._articulation.get_dof_drive_types()
        if (not drive_types_rows or len(drive_types_rows[0]) != len(self._dof_names)):
            raise ValueError('DG03 public drive-type view has unexpected shape')
        drive_types = tuple(
            None if value is None else str(value).lower()
            for value in drive_types_rows[0]
        )
        if any(not math.isfinite(value) for value in max_effort[:len(self._dof_names)]):
            raise ValueError('DG03 public maximum-effort values must be finite in the pinned profile')

        values = {}
        for index, native_name in enumerate(self._dof_names):
            if native_name in receipt.arm_stiffnesses:
                expected = (
                    receipt.arm_stiffnesses[native_name],
                    receipt.arm_dampings[native_name],
                    receipt.arm_max_efforts[native_name],
                    'force',
                )
                actual = (stiffness[index], damping[index], max_effort[index], drive_types[index])
                if (any(not math.isclose(float(actual[i]), float(expected[i]),
                                         rel_tol=0.0, abs_tol=1e-4) for i in range(3))
                        or actual[3] != expected[3]):
                    raise ValueError(
                        f'DG03 public Arm consumer differs from source actuator {native_name}: '
                        f'actual={actual!r}, expected={expected!r}'
                    )
                control_range = receipt.arm_control_ranges[native_name]
                position_range = self._position_limits[native_name]
                if (control_range[0] < position_range[0] - 1e-6
                        or control_range[1] > position_range[1] + 1e-6):
                    raise ValueError(f'DG03 source control range escapes public position limits: {native_name}')
                values[native_name] = {
                    'control_range': list(control_range),
                    'position_range': list(position_range),
                    'stiffness': stiffness[index], 'damping': damping[index],
                    'max_effort': max_effort[index], 'drive_type': drive_types[index],
                    'source_actuator': f'actuator{native_name.removeprefix("joint")}',
                    'readback_api': 'Articulation.get_dof_gains/get_dof_max_efforts/get_dof_drive_types',
                }
            else:
                actual = (stiffness[index], damping[index], drive_types[index])
                if (not math.isclose(stiffness[index], 0.0, rel_tol=0.0, abs_tol=1e-8)
                        or not math.isclose(damping[index], 0.0, rel_tol=0.0, abs_tol=1e-8)
                        or drive_types[index] not in (None, 'none')):
                    raise ValueError(
                        f'DG03 fingers must be free of duplicate public position drives: '
                        f'{native_name}={actual!r}'
                    )
                values[native_name] = {
                    'stiffness': stiffness[index], 'damping': damping[index],
                    'max_effort': max_effort[index], 'drive_type': drive_types[index],
                    'position_drive_api_absent': True,
                }
        return {
            'schema_version': 'f05-dg03-public-arm-drive-witness-v1',
            'authored_drive_apis': [
                {'prim_path': path, 'joint': name, 'api': schema}
                for path, name, schema in sorted(authored)
            ],
            'native_dof_order': list(self._dof_names),
            'consumers': values,
        }

    def _verify_dg03_public_scene(self, UsdGeom, UsdPhysics) -> dict[str, object]:
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
            raise ValueError('DG03 F05 support/cube task scene prims are incomplete')
        if (not support_collision.HasAPI(UsdPhysics.CollisionAPI)
                or not cube_collision.HasAPI(UsdPhysics.CollisionAPI)
                or not cube.HasAPI(UsdPhysics.RigidBodyAPI)
                or not cube.HasAPI(UsdPhysics.MassAPI)):
            raise ValueError('DG03 F05 task scene physics schemas differ from its exact recipe')
        scene_prims = [prim for prim in self._stage.Traverse() if prim.IsA(UsdPhysics.Scene)]
        if len(scene_prims) != 1:
            raise ValueError('DG03 F05 task scene must bind exactly one PhysicsScene')
        gravity_direction = tuple(float(x) for x in scene_prims[0].GetAttribute(
            'physics:gravityDirection').Get())
        gravity_magnitude = float(scene_prims[0].GetAttribute('physics:gravityMagnitude').Get())
        if (not _numeric_tuple_matches(
                gravity_direction, (0.0, 0.0, -1.0), abs_tol=1e-7)
                or not _numeric_value_matches(gravity_magnitude, 9.81, abs_tol=1e-6)):
            raise ValueError('DG03 F05 gravity differs from the frozen task-scene recipe')

        def box_geometry(prim, path, expected_center, expected_size):
            geom = UsdGeom.Cube(prim)
            size = float(geom.GetSizeAttr().Get())
            scale = tuple(float(x) for x in prim.GetAttribute('xformOp:scale').Get())
            root = self._stage.GetPrimAtPath(path)
            center = tuple(float(x) for x in root.GetAttribute('xformOp:translate').Get())
            dimensions = tuple(size * value for value in scale)
            if (not _numeric_tuple_matches(center, expected_center, abs_tol=1e-6)
                    or not _numeric_tuple_matches(dimensions, expected_size, abs_tol=1e-6)):
                raise ValueError(f'DG03 task-scene box differs from the frozen recipe: {path}')
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
            raise ValueError('DG03 task cube authored mass differs from the frozen 0.1 kg recipe')
        collision_enabled = {
            path: bool(self._stage.GetPrimAtPath(path).GetAttribute(
                'physics:collisionEnabled').Get())
            for path in (support_collision_path, cube_collision_path)
        }
        if collision_enabled != {support_collision_path: True, cube_collision_path: True}:
            raise ValueError('DG03 task collision geometry is not enabled on both recipe shapes')

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
            raise ValueError('DG03 cube/support source profile must remain without authored material bindings')

        filter_witness = _dg03_collision_filter_witness(self._stage, UsdPhysics)
        filter_relationships = filter_witness['filtered_pairs']
        collision_groups = filter_witness['collision_groups']
        task_scene_filter_relationships = filter_witness['task_scene_filtered_pairs']
        task_scene_collision_groups = filter_witness['task_scene_collision_groups']
        if task_scene_collision_groups or task_scene_filter_relationships:
            raise ValueError('DG03 task scene unexpectedly adds collision filtering')

        if len(self._free_views) != 1:
            raise ValueError('DG03 source scene requires exactly one floating free-cube body')
        view = next(iter(self._free_views.values()))
        masses = _tensor_rows(view.get_masses(), width=1, label='DG03 public cube mass')[0]
        com_positions, com_orientations = view.get_coms()
        com_position = _tensor_rows(com_positions, width=3,
                                    label='DG03 public cube COM position')[0]
        com_orientation = _tensor_rows(com_orientations, width=4,
                                       label='DG03 public cube COM orientation')[0]
        inertias = _tensor_rows(view.get_inertias(), width=9,
                                label='DG03 public cube inertia tensor')[0]
        expected_inertia = 0.1 * 0.06 * 0.06 / 6.0
        diagonal = (inertias[0], inertias[4], inertias[8])
        if (not math.isclose(masses[0], 0.1, rel_tol=0.0, abs_tol=1e-6)
                or any(not math.isclose(value, 0.0, rel_tol=0.0, abs_tol=1e-6)
                       for value in com_position)
                or any(not math.isclose(actual, expected_inertia, rel_tol=0.05, abs_tol=1e-7)
                       for actual in diagonal)
                or any(not math.isclose(inertias[index], 0.0, rel_tol=0.0, abs_tol=1e-7)
                       for index in (1, 2, 3, 5, 6, 7))):
            raise ValueError('DG03 public cube mass/COM/inertia differ from the 0.1 kg uniform cube profile')
        return {
            'schema_version': 'f05-dg03-public-scene-witness-v2',
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

    def _read_dg03_contact_witness(self) -> dict[str, object]:
        """Read public raw contacts and select only the frozen support collider."""
        if not self._dg03 or not self._free_views:
            raise RuntimeError('DG03 contact readback requires the exact free-cube view')
        view = next(iter(self._free_views.values()))
        result = view.get_raw_contact_data(dt=float(self._artifact.timebase.physics_dt))
        if type(result) is not tuple or len(result) != 7:
            raise ValueError('DG03 public raw contact API returned an unexpected seven-array result')
        normal_forces, _points, _normals, _distances, counts, starts, actor_ids = result
        count_rows = counts.numpy().tolist()
        start_rows = starts.numpy().tolist()
        if len(count_rows) != 1 or len(start_rows) != 1:
            raise ValueError('DG03 public raw contact view must return one free-cube sensor row')
        raw_contact_count = int(count_rows[0])
        contact_start = int(start_rows[0])
        if raw_contact_count < 0 or raw_contact_count > 32 or contact_start < 0:
            raise ValueError('DG03 public contact count/start index is outside the bounded view')
        force_rows = normal_forces.numpy().tolist()
        actor_paths = (
            view.get_actor_paths_from_ids(
                actor_ids.to('cpu')[contact_start:contact_start + raw_contact_count],
            )
            if raw_contact_count else []
        )
        selected = force_rows[contact_start:contact_start + raw_contact_count]
        if len(selected) != raw_contact_count or len(actor_paths) != raw_contact_count:
            raise ValueError('DG03 public contact force slice exceeds the returned contact buffer')
        force_values = tuple(float(row[0]) for row in selected)
        if any(not math.isfinite(value) or value < 0.0 for value in force_values):
            raise ValueError('DG03 public normal contact forces must be finite nonnegative SI values')
        support_path = '/F05Scene/support/collision'
        support_indices = tuple(
            index for index, path in enumerate(actor_paths)
            if path == '/F05Scene/support' or path == support_path
            or path.startswith(support_path + '/')
        )
        support_forces = tuple(force_values[index] for index in support_indices)
        return {
            'schema_version': 'f05-dg03-public-contact-witness-v2',
            'provenance_kind': 'native_runtime',
            'api': 'RigidPrim.get_raw_contact_data',
            'sensor_path': '/F05Scene/free_cube',
            'support_path': support_path,
            'physics_dt_s': float(self._artifact.timebase.physics_dt),
            'raw_contact_count': raw_contact_count,
            'raw_contact_actor_paths': list(actor_paths),
            'contact_count': len(support_indices),
            'support_contact_normal_forces_N': list(support_forces),
            'normal_force_sum_N': math.fsum(support_forces),
            'contact_present': bool(support_indices),
        }

    def _verify_dg03_mimic(self, PhysxSchema, UsdPhysics) -> None:
        """Bind and initialize the public mimic properties from the exact source equality."""
        if not self._dg03 or self._stage is None:
            raise RuntimeError('DG03 mimic verification requires its exact composed USD stage')
        import math
        import xml.etree.ElementTree as ET

        expected_native = ('finger_joint1', 'finger_joint2')
        if {self._source.joints.get(f'panda-main/{name}') for name in expected_native} != set(expected_native):
            raise ValueError('DG03 RuntimeSource does not bind the exact finger Joint pair')
        loaded = self._source.scene_source.loaded_delivery
        source_xml = loaded.source_input_bytes.get('panda.xml')
        if type(source_xml) is not bytes:
            raise ValueError('DG03 delivery does not retain the exact source MJCF bytes')
        root = ET.fromstring(source_xml)
        equalities = root.findall('./equality/joint')
        if len(equalities) != 1:
            raise ValueError('DG03 source must contain exactly one joint equality')
        equality = equalities[0]
        if (equality.get('joint1'), equality.get('joint2'), equality.get('active', 'true')) != (
                'finger_joint1', 'finger_joint2', 'true'):
            raise ValueError('DG03 source equality differs from its exact active finger pair')
        polycoef = tuple(float(x) for x in equality.get('polycoef', '0 1 0 0 0').split())
        solref = tuple(float(x) for x in equality.get('solref', '0.02 1').split())
        solimp = tuple(float(x) for x in equality.get('solimp', '0.9 0.95 0.001').split())
        home = root.find("./keyframe/key[@name='home']")
        qpos = () if home is None else tuple(float(x) for x in home.get('qpos', '').split())
        if (polycoef != (0.0, 1.0, 0.0, 0.0, 0.0) or len(solref) != 2
                or len(solimp) != 3 or solref[0] <= 0.0 or len(qpos) != 9
                or qpos[7] != qpos[8]):
            raise ValueError('DG03 source equality is outside the exact affine/home mapping subset')
        expected_gearing = 1.0 / polycoef[1]
        expected_offset = qpos[8] - qpos[7] - polycoef[0] / polycoef[1]
        expected_frequency = 1.0 / (2.0 * math.pi * solref[0])
        matches = {name: [] for name in expected_native}
        for prim in self._stage.Traverse():
            if prim.GetName() in matches and prim.IsA(UsdPhysics.PrismaticJoint):
                matches[prim.GetName()].append(prim)
        if any(len(rows) != 1 for rows in matches.values()):
            raise ValueError('DG03 source must compose exactly one public prismatic prim per finger Joint')
        reference, follower = matches['finger_joint1'][0], matches['finger_joint2'][0]
        if not follower.HasAPI(PhysxSchema.PhysxMimicJointAPI, 'transX'):
            raise ValueError('DG03 source-derived PhysxMimicJointAPI is absent from the composed delivery')
        relationship = follower.GetRelationship('physxMimicJoint:transX:referenceJoint')
        if not relationship or relationship.GetTargets() != [reference.GetPath()]:
            raise ValueError('DG03 source-derived mimic reference differs from the source equality')
        expected_attrs = {
            'gearing': expected_gearing,
            'offset': expected_offset,
            # The delivered static value is the saturated solimp endpoint.
            # It is changed on the live stage to d(0)'s source-derived value
            # before PhysX setup, then updated from public q before each step.
            'naturalFrequency': expected_frequency,
            'dampingRatio': solref[1],
        }
        authored_attrs = {}
        actual_attrs = {}
        for name, expected in expected_attrs.items():
            attr = follower.GetAttribute(f'physxMimicJoint:transX:{name}')
            if not attr or not attr.IsValid():
                raise ValueError(f'DG03 source-derived mimic omits PhysX field {name}')
            actual = float(attr.Get())
            if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-6):
                raise ValueError(f'DG03 source-derived mimic {name} differs from source mapping')
            authored_attrs[name] = actual
            if name != 'naturalFrequency':
                actual_attrs[name] = actual
        from .leaf_control import IsaacSourceEqualityComplianceV1
        compliance = IsaacSourceEqualityComplianceV1(
            'isaac-source-equality-compliance-v1', 'finger_joint1', 'finger_joint2',
            solref, solimp, (*solimp, 0.5, 2.0),
        )
        initial_frequency = compliance.natural_frequency_hz(0.0)
        initial_damping_ratio = compliance.damping_ratio_for_residual(0.0)
        frequency_attr = follower.GetAttribute('physxMimicJoint:transX:naturalFrequency')
        damping_attr = follower.GetAttribute('physxMimicJoint:transX:dampingRatio')
        if frequency_attr.Set(initial_frequency) is False:
            raise RuntimeError('DG03 could not set the source-compliant live PhysX mimic frequency')
        if damping_attr.Set(initial_damping_ratio) is False:
            raise RuntimeError('DG03 could not set the source-compliant live PhysX mimic damping ratio')
        runtime_frequency = float(frequency_attr.Get())
        runtime_damping_ratio = float(damping_attr.Get())
        if not math.isclose(runtime_frequency, initial_frequency, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError('DG03 live PhysX mimic frequency did not read back the source-compliant d(0) value')
        if not math.isclose(runtime_damping_ratio, initial_damping_ratio,
                            rel_tol=0.0, abs_tol=1e-6):
            raise ValueError('DG03 live PhysX mimic damping ratio did not read back the source-compliant d(0) value')
        self._dg03_mimic_frequency_attribute = frequency_attr
        self._dg03_mimic_damping_attribute = damping_attr
        self._dg03_mimic_receipt = {
            'schema_version': 'physx-public-source-mimic-verification-v1',
            'follower_joint': 'finger_joint2', 'follower_path': str(follower.GetPath()),
            'reference_joint': 'finger_joint1', 'reference_path': str(reference.GetPath()),
            'source_polycoef': polycoef,
            'source_home_qpos_m': (qpos[7], qpos[8]),
            'source_solref': solref, 'source_solimp': solimp,
            'source_solimp_effective': (*solimp, 0.5, 2.0),
            'mapping_algorithm': compliance.mapping_algorithm,
            'initial_equality_residual_m': 0.0,
            'initial_impedance': compliance.impedance(0.0),
            'initial_runtime_frequency_hz': runtime_frequency,
            'initial_runtime_damping_ratio': runtime_damping_ratio,
            'authored_physx_attributes': authored_attrs,
            'physx_attributes': {
                **actual_attrs,
                'naturalFrequency': runtime_frequency,
                'dampingRatio': runtime_damping_ratio,
            },
            'solimp_native_mapping': 'live public PhysX mimic naturalFrequency/dampingRatio follow the MuJoCo 3.8.1 source reference coefficients',
            'schema_authored_in_delivery': True,
            'runtime_stage_mutated': True,
            'runtime_property_api': 'Usd.Prim.GetAttribute(...).Set/Get',
            'applied_schemas': list(follower.GetAppliedSchemas()),
        }

    def metadata(self) -> NativeRuntimeIOMetadataV1:
        if self._closed or self._metadata is None:
            raise RuntimeError("Isaac native I/O is closed or not materialized")
        return self._metadata

    def bootstrap_receipt(self) -> Mapping[str, object]:
        """Return measured public Kit/view bootstrap facts for the worker ledger."""
        if self._closed or not hasattr(self, "_bootstrap_receipt"):
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
        sample.validate()
        if set(sample.joint_position) != set(self._source.joints):
            raise ValueError("reset joint sample differs from exact USD RuntimeSource mapping")
        expected_targets = tuple(sorted(position_targets))
        # A few provider-free F04 boundary tests construct this adapter with
        # ``__new__`` to exercise reset behavior without opening Isaac. Keep
        # those legacy-shaped instances on the F04 path when __init__ has not
        # established the DG03 profile flag.
        dg03 = getattr(self, "_dg03", False)
        if dg03:
            expected_arm_names = {f'joint{index}' for index in range(1, 8)}
            valid_targets = (
                len(expected_targets) == 7
                and {item[1] for item in expected_targets} == expected_arm_names
                and len({item[0] for item in expected_targets}) == 7
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
            self._articulation.set_dof_velocities([0.0] * len(self._dof_names))
            if dg03:
                self._articulation.set_dof_position_targets(
                    [item[2] for item in expected_targets],
                    dof_indices=[int(item[0]) for item in expected_targets],
                )
                if dg03:
                    target_readback = _tensor_rows(
                        self._articulation.get_dof_position_targets(
                            dof_indices=[int(item[0]) for item in expected_targets],
                        ),
                        width=7, label='DG03 reset position-target readback',
                    )[0]
                    if any(not math.isclose(actual, item[2], rel_tol=0.0, abs_tol=1e-6)
                           for actual, item in zip(target_readback, expected_targets, strict=True)):
                        raise ValueError('DG03 public reset target readback differs from source-bound target')
                finger_indices = [self._dof_index[name] for name in ('finger_joint1', 'finger_joint2')]
                self._articulation.set_dof_efforts([0.0, 0.0], dof_indices=finger_indices)
                opening = sum(float(sample.joint_position[f'panda-main/finger_joint{index}'])
                              for index in (1, 2))
                ctrl = 255.0 * opening / 0.08
                self._source_tendon_target = {
                    'target_identity_sha256': None,
                    'receipt_identity_sha256': self.drive_receipt.identity_sha256,
                    'actuator_name': 'actuator8', 'control_value': float(min(255.0, max(0.0, ctrl))),
                    'scalar_force_limit_N': 100.0,
                }
            else:
                self._articulation.set_dof_position_targets([item[2] for item in expected_targets])
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
                tuple(item[1] for item in expected_targets), True, False,
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
        ordered = tuple(sorted(targets))
        if self._dg03:
            valid_targets = (
                len(ordered) == 7
                and {item[1] for item in ordered} == {f'joint{index}' for index in range(1, 8)}
                and len({item[0] for item in ordered}) == 7
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
            if self._dg03:
                target_readback = _tensor_rows(
                    self._articulation.get_dof_position_targets(
                        dof_indices=[int(item[0]) for item in ordered],
                    ),
                    width=7, label='DG03 public position-target readback',
                )[0]
                if any(not math.isclose(actual, item[2], rel_tol=0.0, abs_tol=1e-6)
                       for actual, item in zip(target_readback, ordered, strict=True)):
                    raise ValueError('DG03 public Articulation position-target readback differs from source law')
                applied_values = tuple(float(value) for value in target_readback)
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

    def write_source_tendon_target(
        self, target_identity_sha256: str, receipt_identity_sha256: str,
        actuator_name: str, control_value: float, scalar_force_limit_N: float,
    ) -> NativeSourceTendonWriteAckV1:
        if not self._dg03 or self._closed:
            raise RuntimeError('source tendon targets are admitted only by an open DG03 native adapter')
        receipt = self.drive_receipt
        if (receipt is None or receipt.identity_sha256 != receipt_identity_sha256
                or actuator_name != receipt.actuator_name):
            raise ValueError('source tendon target does not bind the model-bound DG03 receipt')
        expected_control, expected_limit = receipt.tendon_control(
            float(control_value) * receipt.canonical_opening_range_m / receipt.actuator_control_range[1],
            float(scalar_force_limit_N),
        )
        if expected_control != float(control_value) or expected_limit != float(scalar_force_limit_N):
            raise ValueError('source tendon target differs from canonical opening/force mapping')
        self._source_tendon_target = {
            'target_identity_sha256': target_identity_sha256,
            'receipt_identity_sha256': receipt_identity_sha256,
            'actuator_name': actuator_name,
            'control_value': float(control_value),
            'scalar_force_limit_N': float(scalar_force_limit_N),
        }
        self._sync()
        return NativeSourceTendonWriteAckV1(
            'native-source-tendon-write-ack-v1', target_identity_sha256,
            receipt_identity_sha256, actuator_name, float(control_value),
            float(scalar_force_limit_N), False,
        )

    def advance(self) -> NativeAdvanceReceiptV1:
        if self._closed or self._episode_origin_step is None:
            raise RuntimeError("Isaac advance requires an active reset episode")
        before = self._counter()
        attempted_index = self._native_step_count + 1
        tendon_application = None
        try:
            if self._dg03:
                if self._source_tendon_target is None:
                    raise RuntimeError('DG03 physics substep has no validated source tendon target')
                receipt = self.drive_receipt
                target = dict(self._source_tendon_target)
                if (target.get('receipt_identity_sha256') != receipt.identity_sha256
                        or not target.get('target_identity_sha256')):
                    raise ValueError('DG03 source tendon target identity is stale or incomplete')
                self._sync()
                q = _tensor_rows(self._articulation.get_dof_positions(), width=len(self._dof_names),
                                 label='DG03 pre-effort DOF position')[0]
                qd = _tensor_rows(self._articulation.get_dof_velocities(), width=len(self._dof_names),
                                  label='DG03 pre-effort DOF velocity')[0]
                finger_names = receipt.tendon_native_joint_names
                q_fingers = tuple(float(q[self._dof_index[name]]) for name in finger_names)
                qd_fingers = tuple(float(qd[self._dof_index[name]]) for name in finger_names)
                tendon_length = sum(coef * value for coef, value in zip(
                    receipt.tendon_coefficients, q_fingers, strict=True,
                ))
                tendon_rate = sum(coef * value for coef, value in zip(
                    receipt.tendon_coefficients, qd_fingers, strict=True,
                ))
                raw_force = (
                    receipt.actuator_gain * float(target['control_value'])
                    + receipt.actuator_length_bias * tendon_length
                    + receipt.actuator_rate_bias * tendon_rate
                )
                source_low, source_high = receipt.actuator_force_range
                scalar_limit = min(float(target['scalar_force_limit_N']), source_high)
                force = min(scalar_limit, max(-scalar_limit, min(source_high, max(source_low, raw_force))))
                dof_efforts = tuple(coef * force for coef in receipt.tendon_coefficients)
                finger_indices = [self._dof_index[name] for name in finger_names]
                compliance = receipt.equality_compliance
                if (compliance is None or self._dg03_mimic_frequency_attribute is None
                        or self._dg03_mimic_damping_attribute is None):
                    raise RuntimeError('DG03 native substep has no source-bound live equality consumer')
                equality_residual = q_fingers[1] - q_fingers[0]
                source_impedance = compliance.impedance(equality_residual)
                mimic_frequency = compliance.natural_frequency_hz(equality_residual)
                mimic_damping_ratio = compliance.damping_ratio_for_residual(equality_residual)
                frequency_attribute = self._dg03_mimic_frequency_attribute
                damping_attribute = self._dg03_mimic_damping_attribute
                if frequency_attribute.Set(mimic_frequency) is False:
                    raise RuntimeError('DG03 public USD property setter rejected source solimp frequency')
                if damping_attribute.Set(mimic_damping_ratio) is False:
                    raise RuntimeError('DG03 public USD property setter rejected source solimp damping ratio')
                applied_frequency = float(frequency_attribute.Get())
                applied_damping_ratio = float(damping_attribute.Get())
                if not math.isclose(applied_frequency, mimic_frequency, rel_tol=0.0, abs_tol=1e-6):
                    raise ValueError('DG03 live PhysX mimic frequency readback differs from source solimp')
                if not math.isclose(applied_damping_ratio, mimic_damping_ratio,
                                    rel_tol=0.0, abs_tol=1e-6):
                    raise ValueError('DG03 live PhysX mimic damping readback differs from source solimp')
                self._articulation.set_dof_efforts(
                    [float(value) for value in dof_efforts], dof_indices=finger_indices,
                )
                applied_efforts = _tensor_rows(
                    self._articulation.get_dof_efforts(dof_indices=finger_indices),
                    width=2, label='DG03 public applied DOF effort',
                )[0]
                if any(not math.isclose(actual, expected, rel_tol=1e-7, abs_tol=1e-7)
                       for actual, expected in zip(applied_efforts, dof_efforts, strict=True)):
                    raise ValueError(
                        'DG03 public Articulation.get_dof_efforts readback differs from independent J^T force'
                    )
                tendon_application = {
                    'schema_version': 'native-source-tendon-substep-v1',
                    'target_identity_sha256': target['target_identity_sha256'],
                    'receipt_identity_sha256': target['receipt_identity_sha256'],
                    'actuator_name': target['actuator_name'],
                    'control_value': float(target['control_value']),
                    'scalar_force_limit_N': float(target['scalar_force_limit_N']),
                    'native_step_index': attempted_index,
                    'public_effort_api': 'Articulation.set_dof_efforts',
                    'effort_write_attempted_count': 2,
                    'effort_write_completed_count': 2,
                    'native_finger_joint_names': finger_names,
                    'native_finger_dof_indices': tuple(finger_indices),
                    'finger_positions_m': q_fingers,
                    'finger_velocities_m_s': qd_fingers,
                    'tendon_coefficients': receipt.tendon_coefficients,
                    'tendon_length_m': float(tendon_length),
                    'tendon_rate_m_s': float(tendon_rate),
                    'unclipped_scalar_force_N': float(raw_force),
                    'scalar_force_N': float(force),
                    'dof_efforts_N': tuple(float(value) for value in dof_efforts),
                    'public_applied_efforts_N': tuple(float(value) for value in applied_efforts),
                    'public_effort_readback_api': 'Articulation.get_dof_efforts',
                    'source_equality_residual_m': float(equality_residual),
                    'source_equality_impedance': float(source_impedance),
                    'source_mimic_natural_frequency_hz': float(mimic_frequency),
                    'source_mimic_damping_ratio': float(mimic_damping_ratio),
                    'public_mimic_frequency_api': 'Usd.Prim.GetAttribute(...).Set/Get',
                    'public_mimic_frequency_readback_hz': applied_frequency,
                    'public_mimic_damping_ratio_readback': applied_damping_ratio,
                }
                self._sync()
            self._manager.step(steps=1, update_fabric=False)
            self._sync()
            if self._dg03:
                contact_witness = self._read_dg03_contact_witness()
                if tendon_application is not None:
                    tendon_application['public_contact_witness'] = contact_witness
        except BaseException as error:
            error.add_note(
                f"one native physics step was attempted; pre-step counter={before!r}; "
                f"DG03 source tendon effort receipt={tendon_application!r}"
            )
            raise
        after = self._counter()
        delta_steps = after[0] - before[0]
        delta_time = after[1] - before[1]
        if delta_steps != 1 or abs(delta_time - float(self._artifact.timebase.physics_dt)) > 1e-9:
            raise RuntimeError(
                "Isaac public step did not accept exactly one configured physics substep: "
                f"counter_delta={delta_steps}, time_delta={delta_time}"
            )
        self._native_step_count = attempted_index
        assert self._episode_origin_time is not None
        episode_time = after[1] - self._episode_origin_time
        return NativeAdvanceReceiptV1(
            "native-advance-receipt-v1", 1, attempted_index, episode_time,
            tendon_application,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        import gc

        primary = None
        try:
            from isaacsim.core.experimental.utils import app as app_utils
            app_utils.stop()
        except BaseException as error:
            primary = error
        self._free_views.clear()
        self._frame_views.clear()
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


def create_isaac_native_runtime_io(artifact: TaskArtifactV1, execution: ExecutionSpecV1,
                                  source: UsdRuntimeSourceV1, *, dg03_input=None):
    """Create the production adapter only after Core source verification."""
    source.assert_fresh()
    dg03 = execution.physics_profile == 'isaac-gpu-physx-f05-dg03-usd-v1'
    if dg03 != (dg03_input is not None):
        raise ValueError('DG03 Isaac native adapter requires its exact candidate input and profile together')
    if not (source.scene_source.source_verified or source.scene_source.locally_validated):
        raise ValueError("Isaac Core adapter requires an upstream-validated or exact locally validated USD delivery")
    if source.scene_source.representation.provider != "isaacsim":
        raise ValueError("Isaac Core adapter requires an Isaac Sim representation selection")
    if dg03:
        from ...tasks.position_candidate.builder import F05Dg03IsaacUsdCandidateInputV1

        if type(dg03_input) is not F05Dg03IsaacUsdCandidateInputV1:
            raise TypeError('DG03 Isaac adapter requires exact F05Dg03IsaacUsdCandidateInputV1')
        dg03_input.validate()
        if (dg03_input.artifact is not artifact or dg03_input.execution.identity_hash != execution.identity_hash
                or dg03_input.runtime_source is not source):
            raise ValueError('DG03 Isaac adapter candidate differs from the exact artifact/execution/source')
    owner = _process_app_owner()
    lease = source.scene_source.acquire_snapshot()
    try:
        return IsaacSimNativeRuntimeIOV1(
            artifact, execution, source, lease, owner, dg03_input=dg03_input,
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
