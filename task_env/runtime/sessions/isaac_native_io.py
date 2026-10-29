"""Narrow Isaac Sim 6.2 public-API implementation of NativeRuntimeIOV1.

This module is imported only by the admitted runtime materialization route.
It owns Isaac's process App and one stage/view lease; Core's shared USD
RuntimeSession continues to own reset, control, clock projection and faults.
"""
from __future__ import annotations

from collections.abc import Mapping
from importlib import metadata as importlib_metadata
from threading import RLock
from typing import Any

from ...artifacts import ExecutionSpecV1, PoseWorld, TaskArtifactV1
from ...artifacts.execution import ResetSample
from ...assembly.source import UsdSnapshotLeaseV1
from .free_joint_state import PublicRigidBodyReadbackV1, _quaternion_wxyz
from .native_io import (
    NativeAdvanceReceiptV1, NativePositionWriteAckV1,
    NativeResetWriteReceiptV1, NativeRuntimeIOMetadataV1,
    NativeRuntimeReadbackV1,
)
from .source import UsdRuntimeSourceV1


_APP_LOCK = RLock()
_PROCESS_APP_OWNER: "IsaacSimAppOwnerV1 | None" = None


def _validate_isaac_task_thread_count(actual: int) -> int:
    if type(actual) is not int or not 1 <= actual <= 4:
        raise RuntimeError(f"Isaac task thread pool is outside the F04 1-4 thread bound: {actual}")
    return actual


class IsaacSimAppOwnerV1:
    """One headless Isaac App per worker process, separate from Env sessions."""

    def __init__(self) -> None:
        self._app = None
        self._closed = False
        self.start_attempts = 0
        self.close_attempts = 0

    @property
    def app(self):
        return self._app

    def open(self):
        if self._closed:
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
            })
            import carb

            actual = int(carb.settings.get_settings().get_as_int(
                "/plugins/carb.tasking.plugin/threadCount"
            ))
            try:
                _validate_isaac_task_thread_count(actual)
            except RuntimeError:
                app, self._app = self._app, None
                self._closed = True
                app.close()
                raise
        return self._app

    def close(self) -> None:
        if self._closed:
            return
        self.close_attempts += 1
        self._closed = True
        app, self._app = self._app, None
        if app is not None:
            app.close()


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

    def __init__(self, artifact: TaskArtifactV1, execution: ExecutionSpecV1,
                 source: UsdRuntimeSourceV1, lease: UsdSnapshotLeaseV1,
                 app_owner: IsaacSimAppOwnerV1):
        if type(artifact) is not TaskArtifactV1 or type(execution) is not ExecutionSpecV1:
            raise TypeError("Isaac native I/O requires exact TaskArtifactV1 and ExecutionSpecV1")
        if type(source) is not UsdRuntimeSourceV1 or type(lease) is not UsdSnapshotLeaseV1:
            raise TypeError("Isaac native I/O requires verified USD RuntimeSource and owned snapshot lease")
        self._artifact, self._execution, self._source = artifact, execution, source
        self._lease, self._app_owner = lease, app_owner
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
        self._open_public_runtime()

    def _open_public_runtime(self) -> None:
        self._app_owner.open()
        try:
            import omni.usd
            import torch
            from pxr import UsdGeom, UsdPhysics
            from isaacsim.core.experimental.prims import Articulation, RigidPrim, XformPrim
            from isaacsim.core.simulation_manager import SimulationManager
            from isaacsim.core.experimental.utils import app as app_utils

            if not torch.cuda.is_available() or torch.cuda.current_device() != 0:
                raise RuntimeError("F04 requires CUDA device 0; CPU fallback is not admitted")
            if (self._execution.physics_provider, self._execution.physics_backend,
                    self._execution.physics_device, self._execution.determinism_mode,
                    self._execution.physics_profile) != (
                    "isaacsim", "cuda", "cuda:0", "best_effort",
                    "isaac-gpu-physx-f04-position-v1"):
                raise ValueError("unsupported F04 Isaac execution identity")
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
            self._dof_names = tuple(str(name) for name in self._articulation.dof_names)
            expected_dofs = {
                *(f"panda_joint{index}" for index in range(1, 8)),
                "panda_finger_joint1", "panda_finger_joint2",
            }
            if len(self._dof_names) != 9 or set(self._dof_names) != expected_dofs:
                raise ValueError("F04 requires the exact seven named Panda Arm and two finger DOFs")
            self._dof_index = {name: index for index, name in enumerate(self._dof_names)}
            low_array, high_array = self._articulation.get_dof_limits()
            lows = _tensor_rows(low_array, width=len(self._dof_names), label="joint lower limits")[0]
            highs = _tensor_rows(high_array, width=len(self._dof_names), label="joint upper limits")[0]
            self._position_limits = {
                name: (float(lows[index]), float(highs[index]))
                for index, name in enumerate(self._dof_names)
            }

            entry_prim = delivery.entry_prim
            for semantic, native in self._source.bodies.items():
                path = _native_prim_path(native, entry_prim)
                if path not in self._body_views:
                    prim = self._stage.GetPrimAtPath(path)
                    if not prim or not prim.IsValid():
                        raise ValueError(f"USD RuntimeSource frame binding is not a composed prim: {path}")
                    if not prim.HasAPI(UsdPhysics.RigidBodyAPI):
                        raise ValueError(f"USD RuntimeSource body lacks authored RigidBodyAPI: {path}")
                    self._body_views[path] = RigidPrim(path)
                self._frame_views[semantic] = self._body_views[path]
            for semantic, native in self._source.frames.items():
                path = _native_prim_path(native, entry_prim)
                if path not in self._frame_views:
                    prim = self._stage.GetPrimAtPath(path)
                    if not prim or not prim.IsValid():
                        raise ValueError(f"USD RuntimeSource Frame binding is not a composed prim: {path}")
                    self._frame_views[semantic] = XformPrim(path)
            for semantic in self._source.free_joints:
                body_path = _native_prim_path(self._source.bodies[semantic], entry_prim)
                self._free_views[semantic] = self._body_views[body_path]
            if len(self._free_views) != 1:
                raise ValueError("F04 requires exactly one mapped floating rigid body")
            for view in self._body_views.values():
                if hasattr(view, "is_physics_tensor_entity_valid") and not view.is_physics_tensor_entity_valid():
                    raise RuntimeError("public RigidPrim view is not bound to a valid physics entity")

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
            for view in (self._articulation, *self._body_views.values()):
                if not view.is_physics_tensor_entity_valid():
                    raise RuntimeError("public physics tensor view did not initialize after Kit bootstrap")
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
            self._manager = SimulationManager
        except BaseException:
            try:
                if self._context is not None:
                    self._context.close_stage()
            finally:
                self._lease.close()
                self._app_owner.close()
            raise

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
        if (len(expected_targets) != 9 or tuple(item[1] for item in expected_targets)
                != tuple(self._dof_names[index] for index, _name, _value in expected_targets)
                or tuple(item[0] for item in expected_targets) != tuple(range(9))):
            raise ValueError("reset targets differ from actual post-materialization DOF metadata")
        written_joints: list[str] = []
        written_free: list[str] = []
        attempted = 0
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
            self._episode_origin_step, self._episode_origin_time = self._counter()
            self._native_step_count = 0
            return NativeResetWriteReceiptV1(
                "native-reset-write-receipt-v1", sample.sample_id,
                tuple(sorted(written_joints)), tuple(sorted(written_free)),
                tuple(item[1] for item in expected_targets), True, False,
            )
        except BaseException as error:
            error.add_note(
                "Isaac reset may have partially applied; no physical rollback is claimed. "
                f"joint writes={written_joints!r}, free-body writes={written_free!r}, "
                f"target channels attempted={attempted}/9."
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
            com_positions, _com_orientations = view.get_coms()
            p_com = _tensor_rows(com_positions, width=3, label="world COM position")[0]
            rotation = _quaternion_wxyz(q_wxyz)
            com_world = tuple(p_com[index] - p[index] for index in range(3))
            com = tuple(float(value) for value in rotation.T @ com_world)
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
        if (len(ordered) != 9 or tuple(item[0] for item in ordered) != tuple(range(9))
                or tuple(item[1] for item in ordered) != self._dof_names):
            raise ValueError("Position Target names/index order differ from actual Isaac metadata")
        attempted = 0
        try:
            attempted = len(ordered)
            self._articulation.set_dof_position_targets(
                [float(item[2]) for item in ordered],
                dof_indices=[int(item[0]) for item in ordered],
            )
            self._sync()
            return NativePositionWriteAckV1(
                "native-position-write-ack-v1", target_identity_sha256,
                tuple(item[1] for item in ordered), tuple(float(item[2]) for item in ordered),
                False, attempted,
            )
        except BaseException as error:
            error.add_note(
                f"Position target setter failed after attempting {attempted}/{len(ordered)} channels; "
                "no physical rollback is claimed."
            )
            raise

    def advance(self) -> NativeAdvanceReceiptV1:
        if self._closed or self._episode_origin_step is None:
            raise RuntimeError("Isaac advance requires an active reset episode")
        before = self._counter()
        attempted_index = self._native_step_count + 1
        try:
            self._manager.step(steps=1, update_fabric=False)
            self._sync()
        except BaseException as error:
            error.add_note(f"one native physics step was attempted; pre-step counter={before!r}")
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
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
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
        try:
            if self._context is not None:
                self._context.close_stage()
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
                                  source: UsdRuntimeSourceV1):
    """Create the production adapter only after Core source verification."""
    source.assert_fresh()
    if not source.scene_source.source_verified:
        raise ValueError("Isaac Core adapter requires the exact upstream-validated USD delivery")
    if source.scene_source.representation.provider != "isaacsim":
        raise ValueError("Isaac Core adapter requires an Isaac Sim representation selection")
    owner = _process_app_owner()
    lease = source.scene_source.acquire_snapshot()
    try:
        return IsaacSimNativeRuntimeIOV1(artifact, execution, source, lease, owner)
    except BaseException:
        # Constructor cleanup owns the lease/App when startup begins; this is
        # idempotent and protects failures before its first import as well.
        if not lease.closed:
            lease.close()
        owner.close()
        raise


__all__ = ["IsaacSimAppOwnerV1", "IsaacSimNativeRuntimeIOV1", "create_isaac_native_runtime_io"]
